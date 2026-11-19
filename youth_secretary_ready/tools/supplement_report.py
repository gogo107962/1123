"""웹에서 찾아 붙인 데이터를 한 문서로 정리한다. 실행 DB를 읽기 전용으로 읽고 data/SUPPLEMENTS.md 를 쓴다.

    .venv\\Scripts\\python.exe -X utf8 tools\\supplement_report.py [기준일 YYYY-MM-DD]

여기 나오는 것은 모두 사람 검수 전이다. 수집 원문(API)은 바꾸지 않았고, 찾은 문장과 출처를 따로 저장했다.
"""
import json
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from policy_structure import period_status, structure, timing  # noqa: E402
from screening import official_window  # noqa: E402

FIELD = {'documents': '제출서류', 'method': '신청 방법', 'period': '신청 시기', 'conditions': '대상·조건'}


def load(name):
    return json.loads((BASE / 'data' / name).read_text(encoding='utf-8'))


def main(on):
    from ontong import all_supplements
    notes = all_supplements()          # 출처에서 문장을 다시 찾아본 결과(auto_check)가 붙어 있다
    checks = load('supplement_checks.json') if (BASE / 'data/supplement_checks.json').exists() else None
    sure = sum(x.get('auto_check') == 'found' for x in notes)
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    rows = {eid: json.loads(p) for eid, p in con.execute('SELECT external_id, payload_json FROM ontong_candidates')}
    by = {}
    for x in notes:
        by.setdefault(x['external_id'], []).append(x)
    fields = Counter(x['field'] for x in notes)
    rules = sum(len(x.get('rules', [])) for x in notes)
    sites = Counter(urlsplit(x['source_url']).hostname for x in notes)
    names, sido = load('region_sigungu_official.json'), load('urban_worker_income_2026.json')
    out = [f'# 검색으로 찾아 붙인 데이터 ({on.isoformat()} 기준)', '',
           '`tools/supplement_report.py`가 만든 문서다. API 수집값이 비어 있거나 뜻이 불분명한 곳을 공식 페이지에서 찾아 채운 내용이며, **모두 사람 검수 전**이다.',
           '수집 원문은 바꾸지 않았다. 찾은 문장은 출처 주소와 함께 따로 저장하고, 화면에는 "공식 페이지"라고 표시해 보여 준다.', '',
           '## 1. 한눈에', '', '| 무엇을 | 얼마나 | 어디에 저장 | 화면·판별에서 쓰는 곳 |', '|---|---|---|---|',
           f"| 정책별 빈 항목(서류·신청 방법·신청 시기·조건) | 정책 {len(by)}개, 항목 {len(notes)}개 | `data/supplements.json` | 상세의 '지원 조건'·'더 보기', 신청 계획의 서류, 신청기간·나이·소득 판별 |",
           f"| 그중 나이 기준(규칙) | {rules}개 | 위 파일의 `rules` | API 나이 대신 이 기준으로 비교 |",
           f"| 시군구 이름 | {len(names['sigungu'])}개 (폐지 {sum('abolished' in v for v in names['sigungu'].values())}개 표시) | `data/region_sigungu_official.json` | 내 정보의 주소 선택, 챗봇의 지역 되묻기, 지역 비교 |",
           "| API 필드의 뜻(연령·규모 표기 Y, 금액 단위, 선착순, 분류 이름) | 필드 12종 | `data/api_field_notes.json` | 나이 '제한없음', 연소득 비교, 선착순 → 확인 필요 |",
           "| 2026년 기준 중위소득 | 1~6인 가구 | `data/median_income_2026.json` | 소득 금액·소득 구간 비교 |",
           f"| 도시근로자 가구원수별 월평균소득({sido['year_label']}) | 1~8인 가구 | `data/urban_worker_income_2026.json` | '월평균소득 N% 이하' 비교 |",
           f"| 공식 공고와 대조한 접수 상태 | {len(load('source_checks.json'))}건 | `data/source_checks.json` | 공식 종료 표시 |", '',
           '항목별 건수: ' + ' · '.join(f'{FIELD[k]} {v}' for k, v in fields.most_common()),
           '', (f"**자동 대조({checks['checked_on']})**: 출처 주소 {sum(checks['pages'].values())}곳을 다시 열어 인용 문장이 그대로 있는지 확인했다. "
                f"항목 {len(notes)}개 중 **{sure}개는 문장이 페이지에 그대로 있었고**, {len(notes) - sure}개는 찾지 못했다(첨부파일·스크립트로 그려지는 페이지·열리지 않는 페이지). "
                "찾지 못한 항목은 화면에 '자동 대조 안 됨'으로 표시하고, '맞아요/달라요'를 정하는 데 쓰지 않는다(`tools/verify_supplements.py`)." if checks else '자동 대조 기록이 없다.'),
           '', '출처 사이트(많은 순): ' + ', '.join(f'{h} {n}' for h, n in sites.most_common(12)) + f' 외 {max(len(sites) - 12, 0)}곳', '',
           '## 2. API와 달랐던 것', '']
    closed, ages = [], []
    for eid, items in by.items():
        payload = rows.get(eid)
        if not payload:
            continue
        st = structure(payload)
        status = period_status(st['application'], on)
        spans = {w for x in items if x['field'] == 'period' and x.get('auto_check', 'found') == 'found' for q in x['quotes'] for w in [official_window(q, int(x['checked_on'][:4]))] if w}
        if status == 'open' and len(spans) == 1 and on > next(iter(spans))[1]:
            start, end = next(iter(spans))
            closed.append(f"| {payload['plcyNm']} | {timing(st['application'], status, on)[1]} | {start.isoformat()} ~ {end.isoformat()} |")
        for x in items:
            for rule in (x.get('rules', []) if x.get('auto_check', 'found') == 'found' else []):
                low, high = rule['predicate']['value'] if rule['predicate']['op'] == 'between' else (None, None)
                api = st['age']
                if low is not None and (api['min'], api['max']) != (low, high):
                    shown = f"{api['min'] or '?'}~{api['max'] or '?'}세" if api['kind'] != 'unspecified' else ('제한없음 표기' if api['no_limit'] else '미기재')
                    ages.append(f"| {payload['plcyNm']} | {shown} | {low}~{high}세 | {x['quotes'][0][:60]} |")
    out += [f'### 2-1. API는 접수 중인데 공식 페이지의 신청 기간은 지난 정책 ({len(closed)}건)', '',
            '공식 페이지 문장에서 기간이 하나로 분명히 읽힌 경우만 센 것이다. 화면에서는 "맞아요"가 아니라 "확인 필요"로 나온다.',
            '찾은 공고에 없는 추가 모집이 따로 있을 수 있어 "마감"이라고 단정하지 않는다(예: 청년 문화예술패스는 1차 공고의 기간이다).', '',
            '| 정책 | API 표시 | 공식 페이지의 신청 기간 |', '|---|---|---|', *closed, '',
            f'### 2-2. 공식 페이지의 나이 기준이 API와 다른 정책 ({len(ages)}건)', '',
            '| 정책 | API 나이 | 공식 페이지 | 근거 문장(앞부분) |', '|---|---|---|---|', *ages, '',
            '## 3. 정책별로 채운 항목', '', '| 정책 | 주관기관 | 채운 항목 | 나이 규칙 | 문장 확인 | 출처 |', '|---|---|---|---|---|---|']
    for eid, items in sorted(by.items(), key=lambda kv: rows.get(kv[0], {}).get('plcyNm', '')):
        payload = rows.get(eid, {})
        got = ' · '.join(FIELD[k] for k in FIELD if any(x['field'] == k for x in items))
        rule = next((r['predicate'] for x in items for r in x.get('rules', [])), None)
        age = '' if not rule else f"{rule['value'][0]}~{rule['value'][1]}세" if rule['op'] == 'between' else f"{rule['value']}세 {'이하' if rule['op'] == 'lte' else '이상'}"
        hosts = ', '.join(sorted({urlsplit(x['source_url']).hostname for x in items}))
        seen = f"{sum(x.get('auto_check') == 'found' for x in items)} / {len(items)}"
        out.append(f"| {payload.get('plcyNm', eid)} | {(payload.get('sprvsnInstCdNm') or '')[:18]} | {got} | {age} | {seen} | {hosts} |")
    out += ['', '## 4. 한계', '',
            '- 조회 도구가 연 페이지의 문장을 옮긴 것이다. 첨부파일(hwp·pdf) 안에만 있는 서류 목록은 대부분 들어 있지 않다.',
            '- 정책과 페이지의 연결이 추정인 것, 이미지에서 눈으로 읽은 문장, 지역 포털의 등록 정보(API와 같은 성격)는 넣지 않았다.',
            '- 사람이 원문과 대조해 승인하기 전에는 자격 판정에 쓰지 않는다. 걸러보기에서 "공식 페이지 기준(사람 검수 전)"이라고 밝히고 쓴다.', '']
    text = '\n'.join(out)
    (BASE / 'data/SUPPLEMENTS.md').write_text(text, encoding='utf-8', newline='\n')
    print(text[:2600])
    print(f'... 전체 {len(out)}줄, 지난 정책 {len(closed)}건, 나이 다른 정책 {len(ages)}건')


if __name__ == '__main__':
    main(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
