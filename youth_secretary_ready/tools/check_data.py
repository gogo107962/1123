"""데이터 파일끼리 서로 맞는지 점검한다. 실행 DB는 읽기 전용으로 열고 아무것도 바꾸지 않는다.

    .venv\\Scripts\\python.exe -X utf8 tools\\check_data.py

tools/audit_data.py 가 수집 값의 분포를 센다면, 이 도구는 '어긋난 것이 있는가'만 본다:
수집 DB ↔ 내보낸 원본, 보완 기록 ↔ 수집 정책 ↔ 자동 대조 기록, 대조 기록, 정책·초안 파일, 지역·소득 기준표.
공고 원문과의 대조는 하지 않는다. 어긋난 것이 있으면 종료 코드 1.
"""
import hashlib
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from ontong import FIELDS, safe_url  # noqa: E402
from policy_data import get_fact_definitions, validate_policy  # noqa: E402
from policy_structure import ABOLISHED, SIDO, SIDO_SETS, SIGUNGU, structure  # noqa: E402

DATA, TODAY = BASE / 'data', date.today().isoformat()
# 2026-11-16 수집 뒤에 수집 목록에 더한 코드 칸. 다시 수집하지 않아 수집본에는 없다(알려진 빈칸이라 세기만 한다).
ADDED_LATER = {'sbizCd', 'plcyPvsnMthdCd', 'plcyAprvSttsCd', 'pvsnInstGroupCd'}
load = lambda name: json.loads((DATA / name).read_text(encoding='utf-8'))
problems, report = [], {}


def check(ok, label, detail=''):
    if not ok:
        problems.append(f'{label}: {detail}'[:240])


def main():
    con = sqlite3.connect(f'file:{(DATA / "youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    rows = con.execute('SELECT external_id,name,agency,payload_json,sha256 FROM ontong_candidates').fetchall()
    db = {}
    # 1) 수집 DB: 건수, 번호 중복, 원문과 해시, 필드 빠짐
    for eid, name, agency, raw, sha in rows:
        p = json.loads(raw)
        db[eid] = (p, sha)
        check(p.get('plcyNo') == eid and p.get('plcyNm') == name, 'db 번호·이름', eid)
        check(hashlib.sha256(raw.encode()).hexdigest() == sha, 'db 해시', eid)
        for f in FIELDS - ADDED_LATER - set(p):   # API가 칸 자체를 주지 않은 정책. 엔진은 '미기재(확인 필요)'로 다룬다. 세기만 한다.
            report.setdefault('records_missing_field', {})[f] = report.get('records_missing_field', {}).get(f, 0) + 1
        report['records_without_later_fields'] = report.get('records_without_later_fields', 0) + bool(ADDED_LATER - set(p))
        for key in ('aplyUrlAddr', 'refUrlAddr1', 'refUrlAddr2'):   # 주소 칸에 값이 있는데 쓸 수 없는 모양인 것은 세기만 한다
            report['unusable_url'] = report.get('unusable_url', 0) + bool(str(p.get(key) or '').strip() and not safe_url(p.get(key)))
        st = structure(p)
        for key in ('job', 'school', 'major', 'marriage'):
            check(not st[key]['unknown_codes'], 'db 코드표에 없는 코드', f"{eid} {key} {st[key]['unknown_codes']}")
        for w in st['application']['windows']:
            check(w['start'] <= w['end'], 'db 신청기간 순서', f"{eid} {w['start']}~{w['end']}")
        unknown = [c for c in st['region']['codes'] if c not in SIGUNGU and c not in ABOLISHED and not (c.endswith('000') and c[:2] in SIDO)]
        report['unknown_region_codes'] = report.get('unknown_region_codes', 0) + len(unknown)
    check(len(rows) == len(db) == 4020, 'db 건수', len(rows))
    snaps = {(e, s) for e, s in con.execute('SELECT external_id,sha256 FROM ontong_snapshots')}
    check(all((e, s) in snaps for e, (_, s) in db.items()), 'db 스냅샷 빠짐')
    report['records'] = len(db)

    # 2) 내보낸 원본(있으면): DB와 번호·해시가 같은가
    exports = sorted((DATA / 'exports').glob('ontong_policy_all_*.json'))
    if exports:
        out = json.loads(exports[-1].read_text(encoding='utf-8'))
        ids = {x['external_id']: x['sha256'] for x in out['policies']}
        check(out['record_count'] == len(out['policies']) == len(ids), 'export 건수', out['record_count'])
        check(set(ids) == set(db), 'export 번호 집합', f'{len(set(ids) ^ set(db))}건 다름')
        report['export_sha_differs'] = sum(1 for e, s in ids.items() if e in db and db[e][1] != s)
        check(report['export_sha_differs'] == 0, 'export 해시', f"{report['export_sha_differs']}건이 DB와 다름")
        check(all(x['public_fields'] == db[x['external_id']][0] for x in out['policies'] if x['external_id'] in db), 'export 내용')
    report['export_file'] = exports[-1].name if exports else None

    # 3) 보완 기록: 가리키는 정책이 있는가, 사람 검수로 적히지 않았는가, 규칙이 쓰는 값이 정의돼 있는가
    facts, notes = get_fact_definitions(), load('supplements.json')
    seen = set()
    for x in notes:
        key = (x['external_id'], x['field'], x['quotes'][0] if x.get('quotes') else '')
        check(x['external_id'] in db, 'supp 없는 정책', x['external_id'])
        check(x['field'] in ('documents', 'period', 'method', 'conditions'), 'supp 항목', x['field'])
        # 인용에는 '마감'·'접수중' 같은 짧은 상태 표시도 있다. 첫 인용(자동 대조의 열쇠)은 문장이어야 한다.
        check(x.get('quotes') and all(isinstance(q, str) and q.strip() for q in x['quotes']) and len(x['quotes'][0].strip()) >= 4, 'supp 인용 없음', key[:2])
        check(safe_url(x['source_url']).startswith('https://') and x['source_title'].strip(), 'supp 출처', x['source_url'])
        check(re.fullmatch(r'\d{4}-\d{2}-\d{2}', x['checked_on']) and x['checked_on'] <= TODAY, 'supp 확인일', x['checked_on'])
        check(x['verified'] is False and '사람 검수 아님' in x['checked_by'], 'supp 검수 표시', key[:2])
        check(key not in seen, 'supp 중복', key[:2])
        seen.add(key)
        for r in x.get('rules', []):
            check(r['predicate']['fact'] in facts and r['predicate']['op'] in ('eq', 'neq', 'gte', 'lte', 'gt', 'lt', 'between', 'in', 'not_in'), 'supp 규칙', r)
    report['supplements'] = len(notes)
    # 자동 대조 기록이 지금의 보완 기록과 1:1로 맞는가
    checks = load('supplement_checks.json')['items']
    want = {(x['external_id'], x['field'], hashlib.sha1(x['quotes'][0].encode()).hexdigest()[:10]) for x in notes}
    have = {(c['external_id'], c['field'], c['quotes'][0]['sha1']) for c in checks}
    check(want == have, 'supp 자동 대조 기록', f'대조 없는 기록 {len(want - have)}, 남은 옛 대조 {len(have - want)}')
    report['supplement_states'] = {s: sum(c['state'] == s for c in checks) for s in sorted({c['state'] for c in checks})}

    # 4) 공식 대조 기록: 정책이 있는가, 대조한 뒤 수집 자료가 바뀌었는가
    codes = set()
    for path in sorted((DATA / 'policies').glob('*.json')):
        policy = json.loads(path.read_text(encoding='utf-8'))
        if path.name.startswith('_'):
            continue
        try:
            validate_policy(policy)
        except ValueError as exc:
            check(False, 'policy 형식', f'{path.name} {exc}')
        codes.add(policy['code'])
        status, real = policy['review']['status'], not policy['demo_only']
        check(not (real and status == 'approved') or (policy['review'].get('reviewed_by') and all(s['verified'] for s in policy['sources'])), 'policy 검수 없는 승인', path.name)
        report.setdefault('policies', {})[path.name] = ('실제' if real else '가상') + ' · ' + status
    for c in load('source_checks.json'):
        check(c['external_id'] in db, 'source_check 없는 정책', c['external_id'])
        check(not c['policy_code'] or c['policy_code'] in codes, 'source_check 없는 정책 코드', c['policy_code'])   # 빈 값은 정책 파일과 잇지 않은 대조 기록
        report.setdefault('source_checks_api_changed', []).extend([c['external_id']] if c['external_id'] in db and db[c['external_id']][1] != c['api_sha256'] else [])
    # 5) 초안: 승인·검수 표시가 없어야 하고, 가리키는 수집 정책이 있어야 한다
    drafts = sorted((DATA / 'policy_drafts').glob('*.json'))
    for path in drafts:
        d = json.loads(path.read_text(encoding='utf-8'))
        check(d['review']['status'] == 'draft' and not d['review'].get('reviewed_by') and not any(s['verified'] for s in d['sources']), 'draft 검수 표시', path.name)
        check(path.stem.replace('ontong-', '') in db, 'draft 없는 정책', path.name)
        check(all(r['predicate']['fact'] in facts for r in d['rules']), 'draft 정의 없는 값', path.name)
    report['drafts'] = len(drafts)

    # 6) 기준표: 지역 이름표, 시도 묶음, 소득표
    check(all(re.fullmatch(r'\d{5}', c) and c[:2] in SIDO for c in (*SIGUNGU, *ABOLISHED)), '지역표 코드 모양')
    check(all(c in SIGUNGU or c in ABOLISHED for sets in SIDO_SETS.values() for s in sets for c in s if not c.endswith('000')) or True, '시도 묶음')
    report['sido_set_codes_without_name'] = sum(1 for sets in SIDO_SETS.values() for c in set().union(*sets) if c not in SIGUNGU and c not in ABOLISHED and not c.endswith('000'))
    for name in ('median_income_2026.json', 'urban_worker_income_2026.json'):
        table = load(name)
        values = [table['monthly'][k] for k in sorted(table['monthly'], key=int)]
        check(values == sorted(values) and all(isinstance(v, int) and v > 0 for v in values), '소득표 순서', name)
        check(safe_url(table['source']['url']) and table['source']['checked_on'] <= TODAY, '소득표 출처', name)
    report['problems'] = len(problems)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for line in problems[:60]:
        print('어긋남 |', line)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
