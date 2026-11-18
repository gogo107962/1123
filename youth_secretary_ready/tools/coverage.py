"""데이터 구조화와 판별 엔진이 실제 수집본을 얼마나 덮는지 잰다. 실행 DB를 읽기 전용으로 읽고 data/COVERAGE.md 를 쓴다.

    .venv\\Scripts\\python.exe -X utf8 tools\\coverage.py [기준일 YYYY-MM-DD]

퍼센트는 모두 'API에 적힌 값을 코드가 어디까지 다루는가'다. 공고 원문과 맞는지는 재지 않는다(그건 사람 검수다).
"""
import json
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import ontong  # noqa: E402
from policy_structure import CLOSED, period_status, structure, tier  # noqa: E402
from screening import age_rule, screen  # noqa: E402

FULL = {'age': 26, 'region_code': '11305', 'job_code': '0013003', 'school_code': '0049007', 'major_code': '0011003',
        'marriage_code': '0055002', 'income_monthly': 180, 'household': 1, 'income_bracket': 5, 'residence_months': 24, 'benefits': [], 'groups': []}
NAMES = {'period': '신청기간', 'age': '나이', 'region': '거주지', 'income': '소득', 'job': '취업 상태', 'school': '학력', 'major': '전공',
         'marriage': '결혼', 'target': '대상 집단', 'exclusion': '참여 제한', 'apply': '신청 방법'}


def pct(part, whole):
    return f'{part:,} / {whole:,} ({part / whole * 100:.1f}%)' if whole else '0 / 0'


def measure(on):
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    rows = [json.loads(p) for (p,) in con.execute('SELECT payload_json FROM ontong_candidates')]
    notes = json.loads((BASE / 'data/supplements.json').read_text(encoding='utf-8'))
    c, verdicts, used = Counter(), Counter(), set()
    by_policy = {}
    for x in notes:
        by_policy.setdefault(x['external_id'], []).append(x)

    class Seen(dict):   # structure()가 실제로 읽은 필드를 적는다
        def get(self, key, default=None):
            used.add(key)
            return super().get(key, default)
    for payload in rows:
        st = structure(Seen(payload))
        status = period_status(st['application'], on)
        a, app, inc, ex, doc, acc = st['age'], st['application'], st['income'], st['exclusions'], st['documents'], st['access']
        c['age_ok'] += a['kind'] == 'range' or (a['kind'] == 'unspecified' and a['no_limit'])
        c['age_half'] += a['kind'] in ('min_only', 'max_only')
        c['period_fixed'] += app['kind'] == 'fixed'
        c['period_dated'] += app['kind'] == 'fixed' and bool(app['windows'])
        c['period_known_kind'] += app['kind'] != 'unknown'
        c['region_ok'] += bool(st['region']['codes']) and not st['region']['invalid_codes'] and not st['region']['unknown_sido']
        # 비교할 수 있는 소득 기준: 연소득 상한 하나, 중위소득·도시근로자 월평균소득 %(방향까지), 학자금 지원구간 하나
        clear = lambda bounds: bool(bounds) and all(b['kind'] != '?' for b in bounds)
        readable = bool(inc['annual'] and not inc['annual']['min']) or clear(inc['median_bounds']) or clear(inc['urban_bounds']) or inc['bracket_max'] is not None
        c['income_ok'] += inc['code'] == '0043001' or readable
        c['income_cond'] += inc['code'] != '0043001'
        c['income_cond_ok'] += inc['code'] != '0043001' and readable
        for key in ('job', 'school', 'major', 'marriage'):
            c[key + '_ok'] += not st[key]['missing'] and not st[key]['unknown_codes']
        c['excl_filled'] += bool(ex['sentences']) or ex['explicit_none']
        c['excl_ok'] += ex['explicit_none'] or bool(ex['kinds'])
        c['doc_text'] += doc['has_text']
        c['doc_ok'] += bool(doc['known']) or doc['pointer_only']
        c['method_text'] += acc['has_method']
        c['method_ok'] += bool(acc['channels'])
        c['scale_ok'] += st['scale']['no_limit'] or bool(st['scale']['count'])
        c['project_ok'] += bool(st['project']['start']) or bool(st['project']['text'])
        c['amounts'] += bool(st['amounts'])
        c['link'] += acc['has_apply_url'] or acc['has_reference_url']
        c['open_now'] += status not in CLOSED
        if tier(st, status)['tier'] == 'link_only':
            continue
        c['comparable'] += 1
        mine = by_policy.get(payload.get('plcyNo'), [])
        live = status == 'open' and not app['long_window']   # 날짜가 정해진 접수 중
        c['live'] += live
        c['live_checked'] += live and bool(mine)
        out = screen(st, FULL, status, age_rule(mine), mine, on)
        for row in out['criteria']:
            verdicts[(row['key'], row['result'])] += 1
        c['outcome_' + out['outcome']] += 1
        c['all_decided'] += all(r['result'] != 'unknown' for r in out['criteria'])
    return rows, c, verdicts, used, notes


def main(on):
    rows, c, verdicts, used, notes = measure(on)
    n = len(rows)
    collected = {k for d in rows for k in d}
    out = [f'# 구조화·판별 범위 ({on.isoformat()} 기준)', '',
           f'`tools/coverage.py`가 실행 DB {n:,}건을 읽기 전용으로 읽어 만든 표다. API에 적힌 값을 코드가 어디까지 다루는지를 잰 것이고, 공고 원문과 맞는지는 재지 않는다.', '',
           '## 1. 데이터 구조화', '', '| 항목 | 다룬 것 / 대상 | 무엇을 센 것인가 |', '|---|---|---|',
           f"| API 필드 | {pct(len(used & collected), len(collected))} | 수집된 필드 중 구조화가 읽는 필드. 허용 목록에 있지만 수집되지 않은 필드: {', '.join(sorted(ontong.FIELDS - collected)) or '없음'} |",
           f"| 나이 | {pct(c['age_ok'], n)} | 범위가 있거나 '제한없음' 표기. 한쪽만 있는 것 {c['age_half']:,}건, 나머지는 미기재 |",
           f"| 신청기간 구분 | {pct(c['period_known_kind'], n)} | 특정기간·상시·마감 코드가 읽힘 |",
           f"| 신청기간 날짜 | {pct(c['period_dated'], c['period_fixed'])} | 특정기간인 정책 중 날짜가 읽힘 |",
           f"| 지역 코드 | {pct(c['region_ok'], n)} | 5자리 코드이고 시도·시군구 이름이 모두 있음 |",
           f"| 소득(전체) | {pct(c['income_ok'], n)} | 무관 표기이거나 비교할 수 있는 기준(연소득 상한, 중위소득 %, 도시근로자 월평균소득 %, 학자금 지원구간)이 읽힘 |",
           f"| 소득(조건이 있는 정책) | {pct(c['income_cond_ok'], c['income_cond'])} | 조건이 있는 정책 중 비교할 수 있는 기준이 읽힘. 나머지는 글로만 보여 준다 |",
           *[f"| {NAMES[k]} 코드 | {pct(c[k + '_ok'], n)} | 코드표로 풀림 |" for k in ('job', 'school', 'major', 'marriage')],
           f"| 참여 제한 | {pct(c['excl_ok'], c['excl_filled'])} | 칸에 내용이 있는 정책 중 '해당 없음'이거나 문장 종류가 읽힘 |",
           f"| 제출서류 | {pct(c['doc_ok'], c['doc_text'])} | 안내 글이 있는 정책 중 서류 이름이 읽히거나 '붙임파일 확인'으로 분류됨 |",
           f"| 신청 방법 | {pct(c['method_ok'], c['method_text'])} | 안내 글이 있는 정책 중 온라인·방문 등 경로가 읽힘 |",
           f"| 지원 규모 | {pct(c['scale_ok'], n)} | 인원 수가 있거나 '제한없음' 표기. 나머지는 미기재 |",
           f"| 사업기간 | {pct(c['project_ok'], n)} | 날짜나 글이 읽힘 |",
           f"| 금액 표현 | {pct(c['amounts'], n)} | 지원 내용 글에 금액 표현이 있어 뽑힘(없는 정책은 원래 금액이 없을 수 있다) |",
           f"| 공고로 가는 주소 | {pct(c['link'], n)} | 신청 주소나 참고 주소가 있음 |",
           f"| 공식 페이지로 보완 | {len({x['external_id'] for x in notes}):,}개 정책, {len(notes):,}개 항목 | 웹에서 확인해 문장과 함께 적은 것(사람 검수 전) |", '',
           '## 2. 판별(걸러보기)', '',
           f"- 마감이 아닌 정책 {c['open_now']:,}건 가운데 조건을 비교하는 정책: **{pct(c['comparable'], c['open_now'])}** (전체 {n:,}건의 {c['comparable'] / n * 100:.1f}%)",
           f"- 모든 항목을 입력한 가상 프로필(26세·서울 강북구·미취업·대졸·미혼·월 180만원 1인 가구·받는 지원 없음)로 본 결과: 맞아요 {c['outcome_api_match']:,} · 확인 필요 {c['outcome_needs_check']:,} · 달라요 {c['outcome_api_mismatch']:,}",
           f"- 지금 접수 중이고 날짜가 정해진 비교 가능 정책 가운데 공식 페이지를 찾아 확인한 정책: {pct(c['live_checked'], c['live'])} (중복 등록 포함, 사람 검수 전)",
           f"- 입력한 기준이 모두 맞음/다름으로 갈린 정책: {pct(c['all_decided'] + 0, c['comparable'])}", '',
           '| 기준 | 맞음·다름으로 갈림 | 확인 필요 | 갈린 비율 |', '|---|---|---|---|']
    for key, name in NAMES.items():
        decided = verdicts[(key, 'match')] + verdicts[(key, 'mismatch')]
        unknown = verdicts[(key, 'unknown')]
        if decided + unknown:
            out.append(f'| {name} | {decided:,} | {unknown:,} | {decided / (decided + unknown) * 100:.1f}% |')
    out += ['', "'확인 필요'는 API에 값이 없거나(상시·연중 표기, 선착순, 미기재) 문장을 해석해야 하는 경우다. 모르는 것을 맞다고 하지 않기 위해 남긴 것이다.", '']
    text = '\n'.join(out)
    (BASE / 'data/COVERAGE.md').write_text(text, encoding='utf-8', newline='\n')
    print(text)


if __name__ == '__main__':
    main(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
