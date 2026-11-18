"""시군구 코드 → 이름표를 만든다. 실행 DB는 읽기 전용으로만 연다.

    .venv\\Scripts\\python.exe -X utf8 tools\\build_region_names.py

두 가지 근거만 쓴다.
1. 수집본에서 유도: 지역 코드가 하나뿐인 정책의 주관·운영기관 이름에 나온 시·군·구 이름을 모아,
   2건 이상이고 70% 이상이 같은 이름일 때만 채택한다.
2. 서울 25개 구: 법정동코드 표준 번호. 1번으로 유도된 서울 코드와 모두 일치할 때만 넣는다(다르면 중단).
이름을 못 정한 코드는 표에 넣지 않는다. 팀의 data/region_codes.json(행정안전부 대조본)이 오면 이 파일을 대체한다.
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SIDO = json.loads((BASE / 'data/region_sido.json').read_text(encoding='utf-8'))['sido']
SEOUL = {'11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구', '11215': '광진구', '11230': '동대문구',
         '11260': '중랑구', '11290': '성북구', '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
         '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구', '11530': '구로구', '11545': '금천구',
         '11560': '영등포구', '11590': '동작구', '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구',
         '11740': '강동구'}
NAME = re.compile(r'([가-힣]{1,4}(?:시|군|구))(?=\s|$|[^가-힣])')
BROAD = ('특별시', '광역시', '특별자치시', '통합특별시')


def main():
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    votes, seen = defaultdict(Counter), set()
    for (payload,) in con.execute('SELECT payload_json FROM ontong_candidates'):
        d = json.loads(payload)
        codes = {c.strip() for c in d.get('zipCd', '').split(',') if re.fullmatch(r'\d{5}', c.strip())}
        seen |= codes
        if len(codes) != 1:
            continue
        code = next(iter(codes))
        if code.endswith('000'):   # 시도 전체를 가리키는 코드라 시군구 이름을 붙이지 않는다
            continue
        agency = ((d.get('sprvsnInstCdNm') or '') + ' ' + (d.get('operInstCdNm') or '')).replace(SIDO.get(code[:2], ''), ' ')
        names = [x for x in NAME.findall(agency) if not x.endswith(BROAD)]
        if names:
            votes[code][names[0]] += 1
    table = {}
    for code, counter in votes.items():
        name, count = counter.most_common(1)[0]
        if count >= 2 and count / sum(counter.values()) >= 0.7:
            table[code] = {'name': name, 'basis': 'derived', 'votes': count}
        elif len(counter) == 1:   # 근거 정책이 1건뿐이지만 다른 이름과 겹치지 않는 경우. 신뢰도가 낮아 따로 표시한다.
            table[code] = {'name': name, 'basis': 'derived_single', 'votes': count}
    clash = {c: (table[c]['name'], n) for c, n in SEOUL.items() if c in table and table[c]['name'] != n}
    assert not clash, f'서울 표준 번호와 수집본 유도 결과가 다릅니다: {clash}'
    assert set(SEOUL) <= seen, '수집본에 없는 서울 코드가 있습니다.'
    checked = sorted(c for c in SEOUL if c in table)
    for code, name in SEOUL.items():
        table.setdefault(code, {'name': name, 'basis': 'standard_seoul'})
    out = {'source': {'derived': '2026-11-16 수집본에서 지역 코드가 하나뿐인 정책의 기관 이름으로 유도(2건 이상, 70% 이상 일치)',
                      'derived_single': '같은 방법이지만 근거 정책이 1건뿐인 이름(다른 이름과 겹치지 않을 때만). 신뢰도 낮음',
                      'standard_seoul': f'법정동코드 표준 번호의 서울 25개 구. 수집본 유도 결과와 겹치는 {len(checked)}곳({", ".join(checked)})이 모두 일치',
                      'limitations': [f'수집본에 나오는 시군구 코드 {len(seen)}개 중 {len(table)}개만 이름을 정함', '사람 검수 전',
                                      '행정구역 개편으로 이름이 바뀐 곳은 반영하지 못했을 수 있음']},
           'sigungu': dict(sorted(table.items()))}
    (BASE / 'data/region_sigungu.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    by = Counter(c[:2] for c in table)
    print(len(table), '/', len(seen), {SIDO[s]: n for s, n in sorted(by.items())})


if __name__ == '__main__':
    main()
