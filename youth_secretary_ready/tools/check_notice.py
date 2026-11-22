"""수집 자료의 참고 주소(공식 공고로 쓰는 주소)가 그 정책의 글인지 본다. 공개 주소를 한 번씩 열어 읽기만 하고, 실행 DB는 읽기 전용이다.

    .venv\\Scripts\\python.exe -X utf8 tools\\check_notice.py

결과는 data/notice_checks.json 이다. 정책마다 '그 정책의 이름이 페이지에 나오는 주소'만 적는다(named).
- 누리집 첫 화면(주소에 글 위치가 없음)은 열어 보지 않고 공고가 아니라고 본다. 이름이 첫 화면의 새 소식에 잠깐 떠 있어도 공고는 아니다.
- 열었을 때 첫 화면으로 넘겨지거나, 본문에 정책 이름이 없거나, 열리지 않거나, 스크립트로 그리는 화면이라 글을 읽지 못하면 named에 넣지 않는다.
  읽지 못했다는 것은 틀린 주소라는 뜻이 아니다. 앱은 named가 아닌 주소를 '공식 공고'로 쓰지 않고 그 정책만 나오는 온통청년 정책 페이지로 보낼 뿐이다.
- 이름이 나온다는 것은 자동 확인이고 사람 검수가 아니다. 모집 회차·연도가 지금 것인지는 보지 않는다.
"""
import json
import re
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
from ontong import CURRENT, safe_url  # noqa: E402

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; youth-desk-link-check/1.0)', 'Accept': 'text/html,*/*', 'Accept-Language': 'ko'}
HOSTS = defaultdict(lambda: threading.Semaphore(2))   # 한 사이트에 동시에 두 번까지만
LIMIT = 2_000_000                                     # 페이지마다 읽는 최대 크기


def first_screen(url):
    """주소가 누리집 첫 화면(또는 하위 누리집의 첫 화면)인가. 글 번호나 메뉴 번호 같은 위치가 없으면 첫 화면으로 본다."""
    s = urlsplit(url)
    path = s.path.rstrip('/')
    if s.query:
        return False
    last = path.rsplit('/', 1)[-1]
    return not path or bool(re.fullmatch(r'(index|main|home|intro)(\.\w+)*', last, re.I)) \
        or bool(re.fullmatch(r'/(kr|ko|kor|www|portal|web)', path, re.I))


def squash(text):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', text)


def mentions(name, text):
    """페이지 글에 정책 이름이 나오는가. 띄어쓰기·기호·연도·괄호 안 설명은 빼고 비교하고, 끝의 '사업'·'운영'은 없어도 된다."""
    core = squash(re.sub(r'\(.*?\)|（.*?）|\[.*?\]|「|」|20\d\d\s*(년도|년)?', ' ', name)) or squash(name)
    stem = re.sub(r'(사업|운영|추진)$', '', core)
    key = stem if len(stem) >= 5 else core
    return len(key) >= 4 and key in squash(text)


def read(url):
    """(상태, 마지막 주소, 글). 상태: ok / dead(열리지 않음) / other(글이 아닌 파일)."""
    with HOSTS[urlsplit(url).hostname]:
        for verify in (True, False):   # 인증서 사슬이 불완전한 기관 사이트가 있어, 인증서 오류일 때만 검증 없이 한 번 더 본다
            try:
                with httpx.Client(timeout=15, follow_redirects=True, headers=HEADERS, verify=verify) as client:
                    with client.stream('GET', url) as r:
                        if r.status_code >= 400:
                            return 'dead', str(r.url), ''
                        kind = r.headers.get('content-type', '')
                        if kind and 'html' not in kind and 'text' not in kind:
                            return 'other', str(r.url), ''
                        raw = b''
                        for chunk in r.iter_bytes():
                            raw += chunk
                            if len(raw) > LIMIT:
                                break
                m = re.search(rb'charset=["\']?([\w-]+)', raw[:4000])
                enc = m.group(1).decode('ascii', 'replace') if m else (re.search(r'charset=([\w-]+)', kind) or [None, 'utf-8'])[1]
                try:
                    html = raw.decode(enc, 'replace')
                except LookupError:
                    html = raw.decode('utf-8', 'replace')
                html = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html)
                return 'ok', str(r.url), re.sub(r'(?s)<[^>]+>', ' ', html)
            except httpx.ConnectError as exc:
                if verify and 'CERTIFICATE' in str(exc).upper():
                    continue
                return 'dead', url, ''
            except Exception:
                return 'dead', url, ''
    return 'dead', url, ''


def verdict(names, url, got):
    """주소 하나의 결과와, 그 주소를 쓰는 정책 가운데 이름이 나온 정책들."""
    status, final, text = got
    if status != 'ok':
        return status, []
    if first_screen(final):
        return 'moved_to_first_screen', []
    hit = [eid for eid, name in names if mentions(name, text)]
    return ('named' if hit else 'unreadable' if len(squash(text)) < 300 else 'not_named'), hit


def main():
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    uses = defaultdict(list)   # 주소 → [(정책번호, 정책 이름)]
    policies = 0
    for eid, raw in con.execute('SELECT external_id,payload_json FROM ontong_candidates WHERE ' + CURRENT):
        p = json.loads(raw)
        policies += 1
        for field in ('refUrlAddr1', 'refUrlAddr2'):
            url = safe_url(p.get(field, ''))
            if url and (eid, p.get('plcyNm', '')) not in uses[url]:
                uses[url].append((eid, p.get('plcyNm', '')))
    urls = sorted(u for u in uses if not first_screen(u))
    print(f'공고 주소 {len(uses)}개 가운데 첫 화면 {len(uses) - len(urls)}개를 빼고 {len(urls)}개(사이트 {len({urlsplit(u).hostname for u in urls})}곳)를 엽니다…', flush=True)
    with ThreadPoolExecutor(24) as pool:
        got = dict(zip(urls, pool.map(read, urls)))
    named = defaultdict(list)
    states = Counter({'first_screen': len(uses) - len(urls)})
    for url in urls:
        state, hit = verdict(uses[url], url, got[url])
        states[state] += 1
        for eid in hit:
            named[eid].append(url)
    listed = {eid for pairs in uses.values() for eid, _ in pairs}
    summary = {'policies': policies, 'policies_with_notice_url': len(listed), 'policies_with_named_notice': len(named),
               'policies_sent_to_portal': policies - len(named), 'urls': dict(states)}
    out = {'checked_on': date.today().isoformat(),
           'method': '공고 주소를 한 번씩 열어 본문에 그 정책의 이름이 나오는지 확인(자동). 누리집 첫 화면은 공고로 보지 않는다. 사람 검수 아님.',
           'summary': summary, 'named': {eid: named[eid] for eid in sorted(named)}}
    (BASE / 'data/notice_checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
