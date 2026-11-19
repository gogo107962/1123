"""실제 수집본 전체로 판별 엔진을 검증한다. 실행 DB는 읽기 전용으로 복사해서 쓰고 원본은 건드리지 않는다.

    .venv\\Scripts\\python.exe -X utf8 tools\\verify_engine.py

모의 데이터 단위 테스트(pytest)와 달리, 실제 4,020건의 온갖 값(빈값·이상한 날짜·긴 글)에서
엔진이 멈추지 않는지와 결과가 스스로 한 약속(불변식)을 지키는지를 본다. 공고 원문과의 대조는 아니다.
"""
import json
import random
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / 'tools'))
import db  # noqa: E402

ON = date(2026, 11, 18)
RESULTS = {'match', 'mismatch', 'unknown', 'skipped'}
PROFILES = [
    {}, {'age': 26}, {'sido': '11'}, {'region_code': '11305'}, {'age': 26, 'sido': '11', 'job_code': '0013003'},
    {'age': 26, 'region_code': '11305', 'job_code': '0013003', 'benefits': ['국민취업지원제도', '청년수당']},
    {'age': 0, 'sido': '50'}, {'age': 120, 'region_code': '47940'}, {'age': 19, 'sido': '26', 'school_code': '0049005'},
    {'age': 34, 'sido': '41', 'job_code': '0013001', 'major_code': '0011003', 'marriage_code': '0055002', 'benefits': []},
    {'age': 39, 'sido': '12', 'job_code': '0013006', 'benefits': ['기초생활수급(생계·주거급여)', '실업급여(구직급여)']},
    {'benefits': ['청년도약계좌']},
    {'age': 26, 'sido': '11', 'exams': ['정보처리기사', '토익'], 'housing': '자가'}, {'exams': ['없는시험'], 'housing': '월세'},
]
failures = []


def check(ok, label, detail=''):
    if not ok:
        failures.append(f'{label}: {detail}'[:300])


def main():
    work = Path(tempfile.mkdtemp(prefix='youth-verify-')) / 'copy.sqlite3'
    source = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    target = sqlite3.connect(work)
    source.backup(target)
    target.close()
    source.close()
    db.DB_PATH = work                      # 이후 모든 읽기·쓰기는 복사본에만 한다
    from fastapi.testclient import TestClient
    import desk_finder
    from app import app
    from draft_policy import draft
    from policy_structure import PARENT, RANK, structure, period_status, tier, timing
    from screening import provided, screen, screen_catalog
    client, report = TestClient(app), {}
    from ontong import CURRENT   # API에서 사라진 정책은 앱 목록에 없으므로 검증 대상에서도 뺀다
    rows = [json.loads(p) for (p,) in sqlite3.connect(work).execute('SELECT payload_json FROM ontong_candidates WHERE ' + CURRENT)]
    report['records'] = len(rows)

    # 1) 모든 정책 × 모든 프로필: 멈추지 않고, 결과가 스스로 일관되는가
    started, judged = time.time(), 0
    for payload in rows:
        eid = payload['plcyNo']
        try:
            st = structure(payload)
            status = period_status(st['application'], ON)
            placed = tier(st, status)
            deadline, label = timing(st['application'], status, ON)
        except Exception as exc:
            check(False, f'structure {eid}', repr(exc))
            continue
        check(status in RANK and label, f'status {eid}', status)
        check((placed['tier'] == 'link_only') == bool(placed['reasons']), f'tier {eid}', placed)
        check(status != 'open' or (deadline and deadline >= ON.isoformat()), f'deadline {eid}', deadline)
        check(len(st['exclusions']['sentences']) <= 8 and all(0 < len(s) <= 200 for s in st['exclusions']['sentences']), f'exclusions {eid}')
        for profile in PROFILES:
            try:
                out = screen(st, profile, status)
            except Exception as exc:
                check(False, f'screen {eid} {profile}', repr(exc))
                continue
            judged += 1
            got = {c['key']: c['result'] for c in out['criteria']}
            check(set(got.values()) <= RESULTS and all(c['basis'] for c in out['criteria']), f'criteria {eid}', got)
            expected = 'api_mismatch' if 'mismatch' in got.values() else 'needs_check' if 'unknown' in got.values() else 'api_match'
            check(out['outcome'] == expected and out['qualification_determined'] is False, f'outcome {eid}', (out['outcome'], got))
            check(out['to_confirm'] == [k for k, r in got.items() if r in ('unknown', 'mismatch')], f'to_confirm {eid}')
            check(got['age'] == 'skipped' if profile.get('age') is None else got['age'] != 'skipped', f'age skip {eid}', profile)
            has_area = bool(profile.get('sido') or profile.get('region_code'))
            check((got['region'] == 'skipped') != has_area, f'region skip {eid}', profile)
            code = profile.get('region_code')
            if code and st['region']['codes'] and code not in st['region']['codes']:
                # 목록에 없는 코드가 '맞아요'가 되는 것은 시도 전체 등록이거나 내 구의 '시' 코드로 등록된 경우뿐이다.
                check(got['region'] != 'match' or code[:2] in st['region']['full_sido'] or PARENT.get(code) in st['region']['codes'], f'region code {eid}', got['region'])
            age, a = profile.get('age'), st['age']
            if age is not None and a['kind'] == 'range':
                # 범위 밖인데 '제한없음' 표기가 함께 있으면 어긋난 값이라 '확인 필요'다.
                check(got['age'] == ('match' if a['min'] <= age <= a['max'] else 'unknown' if a['no_limit'] else 'mismatch'), f'age range {eid}', (age, a))
            # 대상 시험은 응시료 지원에만 나오고 '달라요'가 될 수 없다. 주거는 무주택 문장이 있을 때만 나오고, 자가라고 했을 때만 '달라요'가 될 수 있다.
            check(('exam' in got) == st['exam']['fee'] and got.get('exam') != 'mismatch', f'exam {eid}', got.get('exam'))
            check(('housing' in got) == bool(st['housing']['no_home']), f'housing row {eid}', got.get('housing'))
            check(got.get('housing') != 'mismatch' or (profile.get('housing') == '자가' and not st['housing']['hedged']), f'housing {eid}', profile.get('housing'))
            # 빈 프로필은 어떤 정책에서도 '달라요'가 나올 수 없다(기간 제외).
            if not provided(profile):
                check(all(r != 'mismatch' for k, r in got.items() if k != 'period'), f'empty profile {eid}', got)
    report['judgements'] = judged
    report['judge_seconds'] = round(time.time() - started, 1)

    # 2) 목록: 건수가 맞는가, 페이지를 끝까지 넘겨도 빠지거나 겹치지 않는가
    for profile in PROFILES:
        first = screen_catalog(profile, ON, page_size=100)
        check(first['total'] == sum(first['tiers'].values()), 'tiers sum', (first['total'], first['tiers']))
        check(sum(first['outcomes'].values()) == first['tiers']['screenable'] + first['tiers']['reviewed'], 'outcomes sum', first['outcomes'])
        check(first['total'] + first['merged'] == len(rows), 'merged', (first['total'], first['merged']))
        ids = []
        for page in range(1, first['pages'] + 1):
            ids += [x['external_id'] for x in screen_catalog(profile, ON, page=page, page_size=100)['items']]
        check(len(ids) == first['total'] == len(set(ids)), 'paging', (len(ids), len(set(ids)), first['total']))
        for outcome, n in first['outcomes'].items():
            check(screen_catalog(profile, ON, outcome=outcome, page_size=1)['total'] == n, 'outcome filter', (outcome, n))
    check(screen_catalog({}, ON, dedupe=False)['total'] == len(rows), 'no dedupe total')
    report['catalog'] = {k: screen_catalog(PROFILES[5], ON, page_size=1)[k] for k in ('total', 'merged', 'outcomes', 'tiers')}

    # 3) API: 무작위 정책 묶음 300개로 신청 계획, 상세 비교 400건
    random.seed(20261118)
    wid = client.post('/api/desk/workspaces').json()['id']
    all_ids = [r['plcyNo'] for r in rows]
    plans = Counter()
    for _ in range(300):
        picked = random.sample(all_ids, random.randint(1, 5))
        r = client.post(f'/api/desk/workspaces/{wid}/plan', json={'external_ids': picked, 'profile': random.choice(PROFILES), 'on': ON.isoformat()})
        check(r.status_code == 200, 'plan status', (r.status_code, picked, r.text[:120]))
        if r.status_code == 200:
            body = r.json()
            check(sorted(body['order']) == sorted(picked) and len(body['policies']) == len(picked), 'plan order', picked)
            check(all(c['from'] != c['to'] and c['quote'] for c in body['conflicts']), 'plan conflicts', body['conflicts'][:1])
            check(all(set(d['policies']) <= set(picked) for d in body['documents']), 'plan docs')
            plans['conflicts'] += bool(body['conflicts'])
            plans['with_documents'] += bool(body['documents'])
    report['plans'] = {'tried': 300, **plans}
    for eid in random.sample(all_ids, 400):
        r = client.post(f'/api/integrations/ontong/candidates/{eid}/screen', json=random.choice(PROFILES))
        check(r.status_code == 200, 'detail screen', (eid, r.status_code))
        check(client.get(f'/api/integrations/ontong/candidates/{eid}').status_code == 200, 'bundle', eid)
    check(client.get(f'/api/desk/workspaces/{wid}').json()['tasks'] == [], 'plan wrote tasks')

    # 4) 검수용 초안: 전 건에서 멈추지 않고, 만들어진 것은 모두 미승인·형식 통과인가
    drafts = Counter()
    for payload in rows:
        try:
            policy = draft(payload)
            drafts['made'] += 1
            check(policy['review']['status'] == 'draft' and not any(s['verified'] for s in policy['sources']), f"draft {payload['plcyNo']}")
        except ValueError as exc:
            drafts['https 주소 없음' if 'https' in str(exc) else '옮길 규칙 없음' if '규칙' in str(exc) else '형식 오류: ' + str(exc)[:60]] += 1
        except Exception as exc:
            check(False, f"draft {payload['plcyNo']}", repr(exc))
    report['drafts'] = dict(drafts)

    # 5) 동시 요청: 걸러보기 40건을 8개 스레드로, 대화는 모델을 끈 대체 경로로 60건
    def one(i):
        return client.post('/api/integrations/ontong/screen', json={'profile': PROFILES[i % len(PROFILES)], 'on': ON.isoformat(), 'page': 1 + i % 3}).status_code
    started = time.time()
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(one, range(40)))
    check(set(codes) == {200}, 'parallel screen', Counter(codes))
    report['parallel_screen'] = {'requests': 40, 'threads': 8, 'seconds': round(time.time() - started, 2)}
    desk_finder.model_status = lambda: {'ready': False}
    words = ['월세 지원 받을 수 있어?', '자격증 시험 응시료', '면접 정장', '창업하고 싶어', '교통비', '그냥 아무거나', '', ' ', 'a' * 600, '<script>alert(1)</script>', "'; DROP TABLE ontong_candidates; --"]
    asked = Counter()
    for i in range(60):
        message = words[i % len(words)]
        r = client.post('/api/integrations/ontong/ask', json={'message': message, 'profile': PROFILES[i % len(PROFILES)], 'on': ON.isoformat()})
        check(r.status_code == (422 if not message.strip() else 200), 'ask fallback', (message[:20], r.status_code))   # 빈 질문·공백뿐인 질문은 거절
        asked[r.status_code] += 1
        if r.status_code == 200:
            check(r.json()['ai'] == 'unavailable' and r.json()['answer'].startswith('로컬 AI가 꺼져'), 'fallback label')
    report['ask_fallback'] = dict(asked)
    check(sqlite3.connect(work).execute('SELECT count(*) FROM ontong_candidates WHERE ' + CURRENT).fetchone()[0] == len(rows), 'data intact')

    report['failures'] = len(failures)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for line in failures[:40]:
        print('FAIL', line)
    by = Counter(f.split(' ')[0] + ' ' + f.split(':')[0].split(' ')[0] for f in failures)
    if failures:
        print('종류별:', Counter(f.split(':')[0].rsplit(' ', 1)[0] if any(c.isdigit() for c in f.split(':')[0]) else f.split(':')[0] for f in failures).most_common(12))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
