"""보완 기록의 인용 문장이 출처 페이지에 실제로 있는지 다시 대조한다. data/supplement_checks.json 을 쓴다.

    .venv\\Scripts\\python.exe -X utf8 tools\\verify_supplements.py

출처 주소를 하나씩 열어(읽기만 한다) 글자만 남긴 뒤, 인용 문장이 띄어쓰기를 무시하고 그대로 들어 있는지 본다.
- found: 페이지 글에 문장이 그대로 있다.
- not_found: 페이지는 열렸지만 문장이 없다(스크립트로 그려지는 페이지, 첨부파일·다른 탭에 있는 문장, 페이지가 바뀐 경우를 포함한다).
- unreachable: 페이지를 열지 못했다.
사람 검수를 대신하지 않는다. supplements.json 의 verified 값은 건드리지 않는다.
"""
import hashlib
import html
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parents[1]
TAG = re.compile(r'<(script|style)\b.*?</\1>|<!--.*?-->|<[^>]+>', re.S | re.I)
SQUASH = re.compile(r'\s+')


def flat(text):
    """띄어쓰기·줄바꿈과 따옴표 모양 차이를 없앤 글."""
    text = html.unescape(text).replace(' ', ' ').translate(str.maketrans('‘’“”', "''\"\""))
    return SQUASH.sub('', text)


def page_text(url):
    with httpx.Client(timeout=20, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0 (quote-check)'}, verify=False) as client:
        response = client.get(url)
    response.raise_for_status()
    raw = response.content
    for encoding in (response.encoding, 'utf-8', 'euc-kr', 'cp949'):
        try:
            return flat(TAG.sub(' ', raw.decode(encoding or 'utf-8')))
        except (UnicodeDecodeError, LookupError):
            continue
    return flat(TAG.sub(' ', raw.decode('utf-8', 'replace')))


def check(url, quotes):
    try:
        text = page_text(url)
    except Exception as exc:
        return url, {'status': 'unreachable', 'reason': type(exc).__name__, 'quotes': {q: None for q in quotes}}
    return url, {'status': 'opened', 'chars': len(text), 'quotes': {q: flat(q) in text for q in quotes}}


def main():
    notes = json.loads((BASE / 'data/supplements.json').read_text(encoding='utf-8'))
    wanted = {}
    for x in notes:
        wanted.setdefault(x['source_url'], set()).update(x['quotes'])
    with ThreadPoolExecutor(8) as pool:
        results = dict(pool.map(lambda kv: check(kv[0], sorted(kv[1])), wanted.items()))
    tally, entries = Counter(), []
    for x in notes:
        page = results[x['source_url']]
        marks = [page['quotes'][q] for q in x['quotes']]
        state = 'unreachable' if page['status'] == 'unreachable' else 'found' if all(marks) else 'partly' if any(marks) else 'not_found'
        if state != 'found' and x.get('read_from') in ('attachment_pdf', 'attachment_hwpx', 'image'):
            state = 'file'   # 공고의 첨부파일·이미지에서 읽은 문장이라 페이지 글로는 대조할 수 없다
        tally[state] += 1
        entries.append({'external_id': x['external_id'], 'field': x['field'], 'source_url': x['source_url'], 'state': state,
                        'quotes': [{'sha1': hashlib.sha1(q.encode()).hexdigest()[:10], 'found': m} for q, m in zip(x['quotes'], marks)]})
    quotes = Counter('found' if m else 'unreachable' if m is None else 'not_found' for p in results.values() for m in p['quotes'].values())
    out = {'checked_on': date.today().isoformat(), 'method': '출처 주소를 열어 글자만 남긴 뒤, 인용 문장이 띄어쓰기를 무시하고 그대로 있는지 확인(자동). 사람 검수 아님.',
           'pages': dict(Counter(p['status'] for p in results.values())), 'entries': dict(tally), 'quotes': dict(quotes), 'items': entries}
    (BASE / 'data/supplement_checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: out[k] for k in ('checked_on', 'pages', 'entries', 'quotes')}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
