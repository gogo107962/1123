"""'시도 전체 대상'을 가리는 기준표를 수집본에서 만든다. 실행 DB는 읽기 전용으로만 연다.

    .venv\\Scripts\\python.exe -X utf8 tools\\build_region_sets.py

시군구 이름표가 없어도, 전국 대상 정책(16개 시도를 모두 등록)이 각 시도에 넣는 시군구 코드 묶음은
'그 시도 전체'를 뜻한다. 그 묶음을 시도별로 모아 data/region_sido_sets.json 에 둔다.
행정구역 개편으로 같은 시도에 묶음이 여러 벌 있을 수 있어(인천·경기 등) 10건 이상 쓰인 묶음을 모두 남긴다.
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SIDO = json.loads((BASE / 'data/region_sido.json').read_text(encoding='utf-8'))['sido']
MIN_USES = 10


def main():
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    variants, nationwide = defaultdict(Counter), 0
    for (payload,) in con.execute('SELECT payload_json FROM ontong_candidates'):
        codes = {c.strip() for c in json.loads(payload).get('zipCd', '').split(',') if re.fullmatch(r'\d{5}', c.strip())}
        if {c[:2] for c in codes} != set(SIDO):
            continue
        nationwide += 1
        for sido in SIDO:
            variants[sido][tuple(sorted(c for c in codes if c[:2] == sido))] += 1
    sets = {sido: [{'codes': list(codes), 'used_by': uses} for codes, uses in variants[sido].most_common() if uses >= MIN_USES]
            for sido in sorted(SIDO)}
    out = {'source': {'basis': f'2026-11-16 수집본에서 16개 시도를 모두 등록한 정책 {nationwide}건이 시도별로 넣은 시군구 코드 묶음',
                      'rule': f'{MIN_USES}건 이상 쓰인 묶음만 남김. 정책의 코드가 이 묶음 중 하나를 모두 포함하면 그 시도 전체 대상으로 본다.',
                      'limitations': ['시군구 이름과 행정구역 개편 이력은 확인하지 않음', '공고 원문의 실제 지원 지역과 다를 수 있음']},
           'sets': sets}
    (BASE / 'data/region_sido_sets.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    for sido, items in sets.items():
        print(sido, SIDO[sido], [(len(x['codes']), x['used_by']) for x in items])


if __name__ == '__main__':
    main()
