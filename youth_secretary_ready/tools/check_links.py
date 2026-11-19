"""수집 자료의 참고 주소·신청 주소가 지금 열리는지 본다. 공개 주소를 한 번씩 열어 볼 뿐이고(읽기만), 실행 DB는 읽기 전용이다.

    .venv\\Scripts\\python.exe -X utf8 tools\\check_links.py [--retry]

결과는 data/link_checks.json 이다(열리지 않은 주소만 적고, 열린 주소는 건수만 남긴다). 주소마다:
- ok: 열렸다(마지막 응답이 400 미만). 내용이 그 정책의 공고인지는 보지 않는다(없는 글에도 200을 주는 사이트가 있다).
- gone: 404·410 — 페이지가 없다.
- error: 그 밖의 4xx·5xx. 자동 접속을 막는 사이트도 여기에 든다(사람이 열면 열릴 수 있다).
- unreachable: 연결하지 못했다(시간 초과, 주소 없음, 인증서 오류 등).
온통청년 정책 페이지는 스크립트로 그리는 화면이라 이 방법으로는 확인할 수 없어 넣지 않았다.
"""
import json
import sqlite3
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from ontong import safe_url  # noqa: E402

FIELDS = {'refUrlAddr1': 'notice', 'refUrlAddr2': 'notice', 'aplyUrlAddr': 'apply'}
HEADERS = {'User-Agent': 'youth-desk-link-check/1.0', 'Accept': 'text/html,*/*', 'Accept-Language': 'ko'}
HOSTS = defaultdict(lambda: threading.Semaphore(2))   # 한 사이트에 동시에 두 번까지만


def state(code):
    return 'ok' if code < 400 else 'gone' if code in (404, 410) else 'error'


def fetch(url):
    with HOSTS[urlsplit(url).hostname]:
        for verify in (True, False):   # 인증서 사슬이 불완전한 기관 사이트가 있어, 인증서 오류일 때만 검증 없이 한 번 더 본다
            try:
                with httpx.Client(timeout=15, follow_redirects=True, headers=HEADERS, verify=verify) as client:
                    with client.stream('GET', url) as r:
                        return {'state': state(r.status_code), 'status': r.status_code, **({} if verify else {'tls': 'unverified'}),
                                **({'final_host': r.url.host} if r.url.host != urlsplit(url).hostname else {})}
            except httpx.ConnectError as exc:
                if verify and 'CERTIFICATE' in str(exc).upper():
                    continue
                return {'state': 'unreachable', 'reason': 'connect'}
            except httpx.TimeoutException:
                return {'state': 'unreachable', 'reason': 'timeout'}
            except Exception as exc:
                return {'state': 'unreachable', 'reason': type(exc).__name__}
    return {'state': 'unreachable', 'reason': 'tls'}


def main():
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    uses = defaultdict(list)   # 주소 → [(정책번호, 종류)]
    for eid, raw in con.execute('SELECT external_id,payload_json FROM ontong_candidates'):
        p = json.loads(raw)
        for field, kind in FIELDS.items():
            url = safe_url(p.get(field, ''))
            if url and (eid, kind) not in uses[url]:
                uses[url].append((eid, kind))
    urls = sorted(uses)
    print(f'주소 {len(urls)}개(사이트 {len({urlsplit(u).hostname for u in urls})}곳)를 확인합니다…', flush=True)
    path = BASE / 'data/link_checks.json'
    if '--retry' in sys.argv and path.exists():   # 지난 결과에서 열리지 않은 주소만 천천히 다시 본다(일시적인 실패를 가려내려고)
        old = json.loads(path.read_text(encoding='utf-8'))['urls']   # 파일에는 열리지 않은 주소만 있다
        results = {u: old.get(u, {'state': 'ok'}) for u in urls}
        again = [u for u in urls if u in old]
        print(f'열리지 않았던 주소 {len(again)}개를 다시 확인합니다…', flush=True)
        with ThreadPoolExecutor(4) as pool:
            results.update(zip(again, pool.map(fetch, again)))
    else:
        with ThreadPoolExecutor(24) as pool:
            results = dict(zip(urls, pool.map(fetch, urls)))
    # 정책마다: 공고 주소·신청 주소 가운데 하나라도 열리는가
    per = defaultdict(lambda: defaultdict(set))
    for url, r in results.items():
        for eid, kind in uses[url]:
            per[eid][kind].add(r['state'])
    summary = {'urls': dict(Counter(r['state'] for r in results.values())),
               'policies_with_link': len(per),
               'policies_all_links_dead': sum(1 for kinds in per.values() if not any('ok' in s for s in kinds.values())),
               'policies_notice_ok': sum(1 for kinds in per.values() if 'ok' in kinds.get('notice', ())),
               'policies_apply_ok': sum(1 for kinds in per.values() if 'ok' in kinds.get('apply', ())),
               'policies_notice_listed': sum(1 for kinds in per.values() if 'notice' in kinds),
               'policies_apply_listed': sum(1 for kinds in per.values() if 'apply' in kinds),
               'tls_unverified': sum(1 for r in results.values() if r.get('tls')),
               'redirected_to_other_host': sum(1 for r in results.values() if r.get('final_host'))}
    out = {'checked_on': date.today().isoformat(),
           'method': '공개 주소를 한 번씩 열어 응답 코드만 확인(자동). 내용이 그 정책의 공고인지는 보지 않는다. 사람 검수 아님.',
           # 열린 주소는 건수만 남기고, 열리지 않은 주소만 적는다.
           'summary': summary, 'urls': {u: results[u] for u in urls if results[u]['state'] != 'ok'}}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
