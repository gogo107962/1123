"""Bounded official API collector. Candidates never become approved engine policies.

Contract verified against the official getPlcy endpoint on 2026-11-16.
Only public policy fields are retained; credentials and staff names are excluded.
"""
import hashlib
import json
import logging
import os
import re
import threading
import uuid
from urllib.parse import urlsplit

import httpx
from db import BASE, connect
from temporal import korean_now

ENDPOINT = 'https://www.youthcenter.go.kr/go/ythip/getPlcy'
KEY_FILE = BASE / '.local' / 'ontong_api_key.txt'
LOCK = threading.Lock()
FIELDS = set('''plcyNo plcyNm plcyKywdNm plcyExplnCn lclsfNm mclsfNm plcySprtCn
sprvsnInstCdNm operInstCdNm aplyPrdSeCd bizPrdSeCd bizPrdBgngYmd bizPrdEndYmd
bizPrdEtcCn plcyAplyMthdCn srngMthdCn aplyUrlAddr sbmsnDcmntCn etcMttrCn
refUrlAddr1 refUrlAddr2 sprtSclCnt sprtSclLmtYn sprtArvlSeqYn sprtTrgtMinAge
sprtTrgtMaxAge sprtTrgtAgeLmtYn mrgSttsCd earnCndSeCd earnMinAmt earnMaxAmt
earnEtcCn addAplyQlfcCndCn ptcpPrpTrgtCn zipCd plcyMajorCd jobCd schoolCd
aplyYmd frstRegDt lastMdfcnDt sbizCd plcyPvsnMthdCd plcyAprvSttsCd pvsnInstGroupCd'''.split())
MESSAGES = {
    'missing_key': '인증키 파일에 키를 저장하거나 ONTONG_YOUTH_API_KEY를 설정하세요.',
    'invalid_key': '인증키는 공백 없이 한 줄로 입력하세요.',
    'auth': '온통청년 인증이 거부되었습니다. 키와 발급 승인 상태를 확인하세요.',
    'upstream': '온통청년 API 요청에 실패했습니다. 잠시 후 다시 시도하세요.',
    'rate_limit': '온통청년 요청 한도에 도달했습니다. 나중에 다시 시도하세요.',
    'schema': '온통청년 응답 형식 또는 페이지 정보가 예상과 달라 저장하지 않았습니다.',
    'busy': '이미 정책을 가져오는 중입니다.',
    'storage': '정책 저장에 실패했습니다. 이번 수집 결과는 반영하지 않았습니다.',
    'input': '검색어는 80자 이하, 페이지 크기는 1~10, 페이지 수는 1~3이어야 합니다.',
}


class OntongError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES[code])


class _NoCredentialLogs(logging.Filter):
    def filter(self, record):
        # httpx INFO and httpcore DEBUG can include the URL query string.
        return 'apikeynm' not in record.getMessage().lower()


for _name in ('httpx', 'httpcore.connection', 'httpcore.http11', 'httpcore.http2', 'httpcore.proxy'):
    logging.getLogger(_name).addFilter(_NoCredentialLogs())


def read_key():
    key = os.environ.get('ONTONG_YOUTH_API_KEY', '').strip()
    if not key:
        try: key = KEY_FILE.read_text(encoding='utf-8-sig').strip()
        except (OSError, UnicodeError): key = ''
    if not key: raise OntongError('missing_key')
    if len(key) > 1024 or any(c.isspace() for c in key): raise OntongError('invalid_key')
    return key


def safe_url(value):
    """Never turn an ambiguous bare host into an asserted verified source."""
    if not isinstance(value, str) or any(ord(c) < 33 for c in value): return ''
    try:
        u = urlsplit(value)
        if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password: return ''
        return value
    except ValueError: return ''


def _normalize(item, key):
    if not isinstance(item, dict): raise OntongError('schema')
    payload = {}
    for field in FIELDS & item.keys():
        value = item[field]
        if value is None: value = ''
        if isinstance(value, bool) or not isinstance(value, (str, int, float)): raise OntongError('schema')
        value = str(value).strip()
        if len(value) > 40000 or key in value: raise OntongError('schema')
        payload[field] = value
    external_id, name = payload.get('plcyNo', ''), payload.get('plcyNm', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', external_id) or not name: raise OntongError('schema')
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'external_id': external_id, 'name': name,
            'agency': payload.get('sprvsnInstCdNm', ''),
            'summary': payload.get('plcyExplnCn', ''),
            'application_text': payload.get('aplyYmd', ''),
            'source_url': safe_url(payload.get('refUrlAddr1', '')) or safe_url(payload.get('refUrlAddr2', '')),
            'payload_json': raw, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}


def _page(client, key, keyword, page, size):
    params = {'apiKeyNm': key, 'pageNum': page, 'pageSize': size, 'rtnType': 'json'}
    if keyword: params['plcyNm'] = keyword
    try:
        # No redirects: credentials must only be sent to the official endpoint.
        with client.stream('GET', ENDPOINT, params=params) as response:
            if response.status_code in (401, 403): raise OntongError('auth')
            if response.status_code == 429: raise OntongError('rate_limit')
            if response.status_code != 200: raise OntongError('upstream')
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2_000_000: raise OntongError('schema')
        data = json.loads(body)
    except (httpx.HTTPError, OSError): raise OntongError('upstream') from None
    except (ValueError, UnicodeError): raise OntongError('schema') from None
    if not isinstance(data, dict) or str(data.get('resultCode')) != '200': raise OntongError('schema')
    result = data.get('result')
    if not isinstance(result, dict): raise OntongError('schema')
    paging, items = result.get('pagging'), result.get('youthPolicyList')
    if not isinstance(paging, dict) or not isinstance(items, list): raise OntongError('schema')
    try:
        total = int(paging['totCount'])
        if int(paging['pageNum']) != page or int(paging['pageSize']) != size or total < 0: raise ValueError
    except (KeyError, TypeError, ValueError): raise OntongError('schema') from None
    if len(items) != min(size, max(0, total - (page - 1) * size)): raise OntongError('schema')
    return [_normalize(item, key) for item in items], total


def save_candidates(con, collected, finished, run_id):
    """Caller owns the transaction; shared by bounded and full collectors."""
    changed = 0
    for item in collected:
        old = con.execute('SELECT sha256 FROM ontong_candidates WHERE external_id=?', (item['external_id'],)).fetchone()
        changed += int(old is None or old['sha256'] != item['sha256'])
        con.execute('''INSERT INTO ontong_candidates
            (external_id,name,agency,summary,application_text,source_url,payload_json,sha256,first_seen_at,last_seen_at,last_run_id)
            VALUES(:external_id,:name,:agency,:summary,:application_text,:source_url,:payload_json,:sha256,:now,:now,:run_id)
            ON CONFLICT(external_id) DO UPDATE SET name=excluded.name,agency=excluded.agency,
            summary=excluded.summary,application_text=excluded.application_text,source_url=excluded.source_url,
            payload_json=excluded.payload_json,sha256=excluded.sha256,last_seen_at=excluded.last_seen_at,last_run_id=excluded.last_run_id''',
            {**item, 'now': finished, 'run_id': run_id})
        con.execute('INSERT OR IGNORE INTO ontong_snapshots VALUES(?,?,?,?,?)',
                    (item['external_id'], item['sha256'], item['payload_json'], finished, run_id))
    return changed


def sync(keyword='', page_size=10, max_pages=1, *, transport=None):
    keyword = keyword.strip()
    if len(keyword) > 80 or not 1 <= page_size <= 10 or not 1 <= max_pages <= 3: raise OntongError('input')
    key = read_key()
    # Prevent even accidental use of a credential as a search query (it is stored).
    if key in keyword: raise OntongError('input')
    if not LOCK.acquire(blocking=False): raise OntongError('busy')
    run_id, now = uuid.uuid4().hex, korean_now().isoformat()
    try:
        with connect() as con:
            con.execute('INSERT INTO ontong_sync_runs(id,keyword,status,started_at) VALUES(?,?,?,?)',
                        (run_id, keyword, 'running', now))
        try:
            collected, seen, total, pages = [], set(), None, 0
            with httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False,
                              trust_env=False, transport=transport) as client:
                for page in range(1, max_pages + 1):
                    items, matched = _page(client, key, keyword, page, page_size)
                    if total is not None and matched != total: raise OntongError('schema')
                    total, pages = matched, page
                    for item in items:
                        if item['external_id'] in seen: raise OntongError('schema')
                        seen.add(item['external_id']); collected.append(item)
                    if len(collected) >= total: break
            finished, changed = korean_now().isoformat(), 0
            with connect() as con:
                con.execute('BEGIN IMMEDIATE')
                changed = save_candidates(con, collected, finished, run_id)
                con.execute('''UPDATE ontong_sync_runs SET status='success',finished_at=?,pages=?,received=?,changed=?,matched_total=?,has_more=? WHERE id=?''',
                            (finished, pages, len(collected), changed, total, int(total > len(collected)), run_id))
            return get_run(run_id)
        except Exception as exc:
            error = exc if isinstance(exc, OntongError) else OntongError('storage')
            with connect() as con:
                con.execute("UPDATE ontong_sync_runs SET status='failed',finished_at=?,error_code=? WHERE id=?",
                            (korean_now().isoformat(), error.code, run_id))
            raise error from None
    finally:
        LOCK.release()


def get_run(run_id):
    with connect() as con:
        row = con.execute('SELECT * FROM ontong_sync_runs WHERE id=?', (run_id,)).fetchone()
    return dict(row) if row else None


def status():
    try: read_key(); configured = True
    except OntongError: configured = False
    with connect() as con:
        count = con.execute('SELECT count(*) FROM ontong_candidates').fetchone()[0]
        last = con.execute('SELECT * FROM ontong_sync_runs ORDER BY started_at DESC LIMIT 1').fetchone()
    return {'configured': configured, 'candidate_count': count, 'last_run': dict(last) if last else None,
            'busy': LOCK.locked(), 'notice': 'API 수집 정보는 검수 대기 상태이며 자격 판별에 사용하지 않습니다.'}


def candidates():
    with connect() as con:
        rows = con.execute('''SELECT external_id,name,agency,summary,application_text,source_url,
            sha256,first_seen_at,last_seen_at FROM ontong_candidates ORDER BY last_seen_at DESC,external_id DESC LIMIT 100''').fetchall()
    return [{**dict(row), 'review_status': 'unreviewed'} for row in rows]


def source_check(external_id, sha256):
    path=BASE/'data'/'source_checks.json'
    checks=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    check=next((x for x in checks if x['external_id']==external_id),None)
    if not check:return None
    return {**check,'api_changed_since_check':check['api_sha256']!=sha256,
            'notice':'공식 원문의 표시된 항목만 대조했습니다. 전체 자격 검수나 정책 승인이 아닙니다.'}


def all_supplements():
    """공식 페이지에서 찾아 따로 적어 둔 보완 기록 전체. 수집 원문은 바꾸지 않는다.
    tools/verify_supplements.py 가 출처 페이지에서 인용 문장을 다시 찾아본 결과(auto_check)를 함께 붙인다:
    found(문장이 그대로 있음) / partly / not_found / unreachable. 대조 기록에 없는 항목은 unchecked 다."""
    path,checks=BASE/'data'/'supplements.json',BASE/'data'/'supplement_checks.json'
    rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if not checks.exists():return rows
    seen={(c['external_id'],c['field'],c['quotes'][0]['sha1']):c['state'] for c in json.loads(checks.read_text(encoding='utf-8'))['items']}
    return [{**x,'auto_check':seen.get((x['external_id'],x['field'],hashlib.sha1(x['quotes'][0].encode()).hexdigest()[:10]),'unchecked')} for x in rows]


def supplements(external_id):
    return [x for x in all_supplements() if x['external_id']==external_id]


def search_candidates(query='',category='',quality='',page=1,page_size=20,application_code='',job_code='',income_code=''):
    from policy_codes import application_hint
    clauses=[];params=[]
    query=query.strip()
    if query:
        escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses.append("(name LIKE ? ESCAPE '\\' OR agency LIKE ? ESCAPE '\\' OR external_id LIKE ? ESCAPE '\\')")
        params.extend(['%'+escaped+'%']*3)
    if category:
        clauses.append("COALESCE(json_extract(payload_json,'$.lclsfNm'),'')=?");params.append(category)
    for field,value in [('aplyPrdSeCd',application_code),('jobCd',job_code),('earnCndSeCd',income_code)]:
        if value:
            clauses.append("instr(',' || replace(COALESCE(json_extract(payload_json, ?),''),' ','') || ',', ?) > 0")
            params.extend(['$.'+field,','+value+','])
    if quality=='missing_period':clauses.append("application_text=''")
    elif quality=='missing_documents':clauses.append("COALESCE(json_extract(payload_json,'$.sbmsnDcmntCn'),'')=''")
    elif quality=='missing_link':clauses.append("source_url=''")
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    with connect() as con:
        total=con.execute('SELECT count(*) FROM ontong_candidates'+where,params).fetchone()[0]
        rows=con.execute('''SELECT external_id,name,agency,summary,application_text,source_url,
            sha256,first_seen_at,last_seen_at,json_extract(payload_json,'$.lclsfNm') AS category,
            COALESCE(json_extract(payload_json,'$.sbmsnDcmntCn'),'')='' AS missing_documents,
            json_extract(payload_json,'$.aplyPrdSeCd') AS application_code
            FROM ontong_candidates'''+where+' ORDER BY external_id DESC LIMIT ? OFFSET ?',
            [*params,page_size,(page-1)*page_size]).fetchall()
        categories=[r[0] for r in con.execute("SELECT DISTINCT json_extract(payload_json,'$.lclsfNm') FROM ontong_candidates WHERE COALESCE(json_extract(payload_json,'$.lclsfNm'),'')!='' ORDER BY 1")]
    items=[]
    for r in rows:
        check=source_check(r['external_id'],r['sha256'])
        items.append({**dict(r),'review_status':'unreviewed','source_check':check,
                      'application_hint':application_hint({'aplyPrdSeCd':r['application_code']},check)})
    return {'items':items,
            'total':total,'page':page,'page_size':page_size,'pages':(total+page_size-1)//page_size,'categories':categories}


def review_bundle(external_id):
    from policy_codes import describe,questions,application_hint
    from policy_structure import structure,period_status,tier,timing
    with connect() as con:
        row = con.execute('SELECT * FROM ontong_candidates WHERE external_id=?', (external_id,)).fetchone()
    if not row: return None
    payload=json.loads(row['payload_json'])
    check=source_check(external_id,row['sha256'])
    structured=structure(payload);status=period_status(structured['application'],korean_now().date(),check)
    return {'source': '온통청년 정책 API', 'external_id': external_id, 'review_status': 'unreviewed',
            'structured':structured,'period_status':status,'tier':tier(structured,status),
            # 화면에 보여 줄 기간 표시(D-day 등). 목록과 같은 함수로 만든다.
            'period_label':timing(structured['application'],status,korean_now().date())[1],
            'decoded':describe(payload),'questions':questions(payload),'application_hint':application_hint(payload,check),
            'fetched_at': row['last_seen_at'], 'sha256': row['sha256'], 'public_fields': json.loads(row['payload_json']),
            'source_check':source_check(external_id,row['sha256']),'supplements':supplements(external_id),
            'checklist': ['공식 모집 공고·첨부 문서 대조', '신청 시작·마감 시각 및 기준일 확인',
                          '자격·중복 제한 규칙과 근거 입력', '서류·대체 증빙·예외 확인',
                          '정책 JSON 검증과 정답 사례 테스트', '사람 검수 후 명시적으로 승인'],
            'notice': '수집 원문 검토용입니다. 승인된 정책 JSON이 아니며 자동으로 판별 목록에 등록되지 않습니다.'}
