"""수집 데이터 전체 점검. 실행 DB를 읽기 전용으로 열고 아무것도 바꾸지 않는다.

    .venv\\Scripts\\python.exe -X utf8 tools\\audit_data.py [YYYY-MM-DD]

결과는 data/DATA_AUDIT.md 로 쓴다. 판별 엔진(policy_structure, screening)이 실제 데이터에서
어떻게 동작하는지와, 엔진이 믿으면 안 되는 값을 센다. 공고 원문과의 대조는 하지 않는다.
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from policy_codes import CODEBOOK, api_field  # noqa: E402
from policy_structure import SIDO, UNRESTRICTED, period_status, structure, tier  # noqa: E402
from screening import screen  # noqa: E402
from desk_plan import DOCS  # noqa: E402
from ontong import CURRENT  # noqa: E402

ON = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 11, 17)
PROFILES = {'민지(26세·서울·미취업자)': {'age': 26, 'sido': '11', 'job_code': '0013003'},
            '26세·충남·재직자': {'age': 26, 'sido': '44', 'job_code': '0013001'},
            '19세·부산·대학 재학': {'age': 19, 'sido': '26', 'school_code': '0049005'},
            '35세·경기·자영업자': {'age': 35, 'sido': '41', 'job_code': '0013002'}}


def table(head, rows):
    return ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)] + ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows] + ['']


def main():
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT external_id,name,agency,sha256,source_url,payload_json FROM ontong_candidates' + ' WHERE ' + CURRENT).fetchall()
    total = len(rows)
    integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
    checks = {x['external_id']: x for x in json.loads((BASE / 'data/source_checks.json').read_text(encoding='utf-8'))}
    out = [f'# 수집 데이터 점검 ({ON.isoformat()} 기준)', '',
           f'`tools/audit_data.py`가 실행 DB를 읽기 전용으로 읽어 만든 보고서다. 대상 {total:,}건, DB integrity_check={integrity}.',
           '공고 원문과의 대조가 아니라 **API 기재값의 상태**와 **판별 엔진이 그 값을 어떻게 다루는지**를 센 것이다.', '']

    fill, codes, unknown, uncollected = Counter(), {}, Counter(), []
    ages, periods, tiers, reasons, statuses = Counter(), Counter(), Counter(), Counter(), Counter()
    region, income, docs, names, flags = Counter(), Counter(), Counter(), Counter(), Counter()
    outcomes = {k: Counter() for k in PROFILES}
    examples = {k: [] for k in ('age_invalid', 'period_unparsed', 'region_invalid', 'region_unknown_sido', 'nationwide_local')}
    for field in CODEBOOK['groups']:
        codes[field] = Counter()
    for row in rows:
        p = json.loads(row['payload_json'])
        for key, value in p.items():
            fill[key] += bool(str(value).strip())
        names[(row['name'].strip(), row['agency'].strip())] += 1
        for field, group in CODEBOOK['groups'].items():
            raw = p.get(api_field(field))
            if raw is None:
                continue
            for code in dict.fromkeys(c.strip() for c in str(raw).split(',') if c.strip()):
                codes[field][code] += 1
                unknown[field] += code not in group['codes']
        st = structure(p)
        check = checks.get(row['external_id'])
        if check:
            check = {**check, 'api_changed_since_check': check['api_sha256'] != row['sha256']}
            flags['source_check_rows'] += 1
            flags['source_check_changed'] += check['api_changed_since_check']
        status = period_status(st['application'], ON, check)
        statuses[status] += 1
        placed = tier(st, status)
        tiers[placed['tier']] += 1
        for r in placed['reasons']:
            reasons[r] += 1
        # 나이
        ages[st['age']['kind']] += 1
        flags['age_flag_' + (st['age']['limit_flag_raw'] or '빈값')] += 1
        if st['age']['kind'] == 'invalid':
            examples['age_invalid'].append(f"{row['name']} ({p.get('sprtTrgtMinAge')}~{p.get('sprtTrgtMaxAge')})")
        if st['age']['kind'] == 'range' and (st['age']['min'] < 15 or st['age']['max'] > 49):
            flags['age_range_wide'] += 1
        # 신청기간
        app = st['application']
        periods[(app['kind'], 'windows' if app['windows'] else 'raw_only' if app['raw'].strip() else 'blank')] += 1
        flags['period_multi_window'] += len(app['windows']) > 1
        if app['raw'].strip() and not app['windows']:
            examples['period_unparsed'].append(f"{row['name']}: {app['raw'][:40]!r}")
        if app['kind'] == 'closed' and any(w['start'] <= ON.isoformat() <= w['end'] for w in app['windows']):
            flags['closed_code_but_window_open'] += 1
        if app['kind'] == 'rolling' and app['windows']:
            flags['rolling_with_dates'] += 1
        # 지역
        r = st['region']
        region['코드 없음' if not r['codes'] else '전국(16개 시도 모두)' if r['nationwide'] else '한 시도' if len(r['sido']) == 1 else '여러 시도'] += 1
        if r['invalid_codes']:
            flags['region_invalid_code_rows'] += 1
            examples['region_invalid'].append(f"{row['name']}: {r['invalid_codes'][:3]}")
        if r['unknown_sido']:
            flags['region_unknown_sido_rows'] += 1
            examples['region_unknown_sido'].append(f"{row['name']}: {r['unknown_sido']}")
        if r['nationwide'] and r['local_agency_hint']:
            flags['nationwide_local_agency'] += 1
            examples['nationwide_local'].append(f"{row['name']} / {row['agency']}")
        # 소득
        inc = st['income']
        income[inc['labels'][0] if inc['labels'] else '구분 없음' if inc['missing'] else '미등록 코드'] += 1
        amounts = [x for x in (inc['min_raw'], inc['max_raw']) if x not in ('', '0')]
        flags['income_amount_rows'] += bool(amounts)
        flags['median_pct_rows'] += bool(inc['median_pct'])
        flags['median_bound_rows'] += bool(inc['median_bounds']) and all(b['kind'] != '?' for b in inc['median_bounds'])
        flags['target_rows'] += bool(st['targets'])
        flags['amount_rows'] += bool(st['amounts'])
        flags['channel_rows'] += bool(st['access']['channels'])
        flags['open_rows'] += status == 'open'
        flags['open_long_rows'] += status == 'open' and st['application']['long_window']
        flags['residence_rows'] += bool(st['region']['residence_min_months'])
        flags['exclusion_rows'] += bool(st['exclusions']['sentences'])
        flags['exclusion_none_rows'] += st['exclusions']['explicit_none']
        flags['exclusion_kind_rows'] += bool(st['exclusions']['kinds'])
        flags['annual_income_rows'] += bool(inc['annual'])
        flags['age_no_limit_rows'] += st['age']['kind'] == 'unspecified' and st['age']['no_limit']
        flags['age_conflict_rows'] += st['age']['kind'] != 'unspecified' and st['age']['no_limit']
        flags['no_method_but_link'] += not (st['access']['has_method'] or st['access']['has_apply_url']) and st['access']['has_reference_url']
        flags['age_flag_' + (st['age']['limit_flag_raw'] or '빈값') + ('_범위없음' if st['age']['kind'] == 'unspecified' else '_범위있음')] += 1
        flags['income_unrelated_but_amount'] += inc['code'] == '0043001' and bool(amounts)
        flags['income_text_rows'] += bool(inc['text'].strip())
        flags['income_unrelated_but_text'] += inc['code'] == '0043001' and bool(inc['text'].strip())
        # 코드형 조건
        for key, field in (('job', 'jobCd'), ('school', 'schoolCd'), ('major', 'plcyMajorCd'), ('marriage', 'mrgSttsCd')):
            c = st[key]
            flags[f'{key}_' + ('missing' if c['missing'] else 'unrestricted' if c['unrestricted'] and len(c['codes']) == 1 else
                               'unrestricted_mixed' if c['unrestricted'] else 'restricted')] += 1
        # 서류·링크
        text = p.get('sbmsnDcmntCn', '').strip()
        flags['doc_text_rows'] += bool(text)
        hit = [key for key, _, needles, _ in DOCS if any(n in text for n in needles)]
        flags['doc_text_no_known_name'] += bool(text) and not hit
        for key in hit:
            docs[key] += 1
        flags['no_source_url'] += not row['source_url']
        flags['no_apply_route'] += not (st['access']['has_method'] or st['access']['has_apply_url'])
        flags['apply_url_not_url'] += bool(str(p.get('aplyUrlAddr') or '').strip()) and not st['access']['has_apply_url']
        # 걸러보기
        if placed['tier'] != 'link_only':
            for label, profile in PROFILES.items():
                outcomes[label][screen(st, profile, status)['outcome']] += 1

    dup = {k: v for k, v in names.items() if v > 1}
    out += ['## 1. 한눈에', '']
    out += table(['항목', '건수', '엔진이 다루는 방식'], [
        ['걸러보기 가능 / 원문 링크만', f"{tiers['screenable']:,} / {tiers['link_only']:,}", '링크만인 정책은 조건 비교를 하지 않는다'],
        ['링크만인 이유(중복 집계)', ' · '.join(f'{k} {v:,}' for k, v in reasons.most_common()), '마감 / 신청 경로 없음 / 지역 코드 없음'],
        ['같은 이름·기관으로 두 번 이상 등록', f'{len(dup):,}쌍(묶음), {sum(dup.values()):,}건', '합치지 않고 따로 보여 준다'],
        ['소득 무관 표기인데 소득 글이 있음', f"{flags['income_unrelated_but_text']:,}", "'맞아요'로 보이지만 원문 확인 문구를 붙인다"],
        ['전국 등록 + 지자체 주관', f"{flags['nationwide_local_agency']:,}", "지역을 '확인 필요'로 내린다"],
        ['서류 안내 글 있음', f"{flags['doc_text_rows']:,} ({flags['doc_text_rows'] / total:.0%})", '글이 없으면 서류 없음이 아니라 안내 없음'],
        ['참여 제한(제외·중복) 문장이 있음', f"{flags['exclusion_rows']:,}", "문장을 그대로 보존하고 '확인 필요'로 내린다"],
        ['소득 글에 중위소득 %가 적힘', f"{flags['median_pct_rows']:,}", '숫자는 구조화하지만 비교하지 않는다'],
        ['접수 중인데 신청기간이 300일 이상', f"{flags['open_long_rows']:,} / 접수 중 {flags['open_rows']:,}", "사업기간일 수 있어 '접수 중'으로 보지 않고 확인 필요로 내린다"],
        ['이름에 특정 대상 집단이 있음', f"{flags['target_rows']:,}", "내가 그 대상이라고 고른 경우에만 '맞아요', 아니면 확인 필요"],
        ['소득 글의 중위소득 %가 방향까지 읽힘', f"{flags['median_bound_rows']:,}", '월 소득·가구원 수를 넣으면 비율로 비교(경계 ±5%는 확인 필요)'],
        ['거주 기간 조건이 글에 있음', f"{flags['residence_rows']:,}", '지역이 맞아도 확인 필요'],
        ['지원 내용에 금액 표현이 있음', f"{flags['amount_rows']:,}", '표현 그대로 보여 주고 합산하지 않는다'],
        ['신청 방법에서 경로가 읽힘', f"{flags['channel_rows']:,}", '온라인·방문·우편·이메일·전화로 표시'],
        ["참여 제한 칸에 '해당 없음'만 적힘", f"{flags['exclusion_none_rows']:,}", "제한 문장으로 세지 않고 '맞아요'(원문 확인 문구)로 본다. 빈칸은 여기에 들지 않는다"],
        ['참여 제한 문장의 종류가 읽힘', f"{flags['exclusion_kind_rows']:,}", '확인할 항목 이름(중복·취업·주택 등)으로 보여 준다. 재직자·사업자 제외 문장만 내 취업 상태와 견준다'],
        ["나이 범위 없이 '제한없음(Y)' 표기", f"{flags['age_no_limit_rows']:,}", "온통청년 누리집 표시 기준으로 '맞아요'(원문 확인 문구)"],
        ["나이 범위와 '제한없음(Y)'이 함께 적힘", f"{flags['age_conflict_rows']:,}", "범위 안이면 '맞아요', 밖이면 '달라요'가 아니라 '확인 필요'"],
        ['연소득 구분에 최대 금액이 있음', f"{flags['annual_income_rows']:,}", '월 소득×12를 만원 단위로 견준다(경계 ±5%는 확인 필요)'],
        ['신청 방법은 없지만 참고 주소가 있음', f"{flags['no_method_but_link']:,}", "조건은 비교하고 신청 방법을 '확인 필요'로 남긴다"],
        ['미등록 코드', f'{sum(unknown.values()):,}', 'unknown_codes로 보존'],
        ['원문 대조 기록 / 그 뒤 API 내용 변경', f"{flags['source_check_rows']} / {flags['source_check_changed']}", '바뀌면 공식 종료 표시를 쓰지 않는다']])

    out += ['## 2. 신청기간', '', f'기준일 {ON.isoformat()}의 상태(API 날짜만으로 본 것, 접수 보장이 아님):', '']
    out += table(['상태', '건수'], [[k, f'{v:,}'] for k, v in statuses.most_common()])
    out += table(['구분 코드', '날짜 상태', '건수'], [[k[0], {'windows': '기간 해석됨', 'raw_only': '글은 있으나 기간 해석 안 됨', 'blank': '빈값'}[k[1]], f'{v:,}'] for k, v in sorted(periods.items())])
    out += [f"- 기간이 2개 이상 적힌 정책 {flags['period_multi_window']:,}건, 상시인데 날짜가 적힌 정책 {flags['rolling_with_dates']:,}건, 마감 코드인데 날짜는 오늘을 포함하는 정책 {flags['closed_code_but_window_open']:,}건.",
            f"- 글은 있는데 기간으로 해석하지 못한 예: {'; '.join(examples['period_unparsed'][:4]) or '없음'}", '']

    out += ['## 3. 나이', '']
    out += table(['형태', '건수', '걸러보기 결과'], [
        ['최소~최대 모두 있음', f"{ages['range']:,}", '범위 안이면 맞아요, 밖이면 달라요'],
        ['최소만', f"{ages['min_only']:,}", '미만이면 달라요, 그 외 확인 필요'],
        ['최대만', f"{ages['max_only']:,}", '초과면 달라요, 그 외 확인 필요'],
        ['둘 다 0·빈값', f"{ages['unspecified']:,}", "확인 필요(제한 없음으로 보지 않음)"],
        ['최소 > 최대', f"{ages['invalid']:,}", '확인 필요']])
    out += [f"- 범위가 15세 미만 또는 49세 초과까지 걸친 정책 {flags['age_range_wide']:,}건(청년 범위를 벗어난 기재).",
            f"- 연령 제한 여부(Y/N)와 나이 범위 기재: {', '.join(f'{k[9:]} {v:,}' for k, v in sorted(flags.items()) if k.startswith('age_flag_') and '_범위' in k)}. 명세에는 Y/N의 뜻이 없지만 온통청년 누리집이 Y를 '제한없음'으로 보여 준다(data/api_field_notes.json). 범위 없이 Y면 '제한없음 표기'로, 범위와 Y가 함께 있으면 어긋난 값으로 다룬다.",
            f"- 최소 > 최대 예: {'; '.join(examples['age_invalid'][:5]) or '없음'}", '']

    out += ['## 4. 지역', '']
    out += table(['형태', '건수'], [[k, f'{v:,}'] for k, v in region.most_common()])
    out += [f"- 5자리가 아닌 코드가 섞인 정책 {flags['region_invalid_code_rows']:,}건, 시도표(16개)에 없는 앞 2자리가 있는 정책 {flags['region_unknown_sido_rows']:,}건.",
            f"- 전국 등록 + 지자체 주관 예: {'; '.join(examples['nationwide_local'][:4]) or '없음'}",
            f"- 미등록 시도 예: {'; '.join(examples['region_unknown_sido'][:4]) or '없음'}", '']

    out += ['## 5. 소득', '']
    out += table(['소득 구분', '건수'], [[k, f'{v:,}'] for k, v in income.most_common()])
    out += [f"- 금액(0이 아닌 값)이 적힌 정책 {flags['income_amount_rows']:,}건. 단위·개인/가구 기준이 확인되지 않아 **어느 것도 비교하지 않는다**.",
            f"- '무관' 표기인데 금액이 적힌 정책 {flags['income_unrelated_but_amount']:,}건, 소득 관련 글이 적힌 정책 {flags['income_unrelated_but_text']:,}건. 무관 표기를 그대로 믿으면 안 되는 근거다.", '']

    out += ['## 6. 취업·학력·전공·결혼 코드', '']
    out += table(['조건', '제한없음만', '제한 있음', '제한없음+다른 코드 혼재', '빈값'], [
        [label, f"{flags[key + '_unrestricted']:,}", f"{flags[key + '_restricted']:,}", f"{flags[key + '_unrestricted_mixed']:,}", f"{flags[key + '_missing']:,}"]
        for key, label in (('job', '취업 상태'), ('school', '학력'), ('major', '전공'), ('marriage', '결혼'))])
    out += ["- '제한없음'과 다른 코드가 함께 적힌 경우 엔진은 제한없음으로 읽어 '맞아요'로 본다. 공고 확인이 필요한 기재다.", '']
    for field, group in CODEBOOK['groups'].items():
        if not codes[field]:
            uncollected.append(f"{group['title']}({field})")
            continue
        out += [f"**{group['title']} ({api_field(field)})** — 미등록 코드 {unknown[field]:,}건", '']
        out += table(['코드', '뜻', '건수'], [[c, group['codes'].get(c, {}).get('label', '미등록'), f'{v:,}'] for c, v in codes[field].most_common()])
    out += [f"- 수집하지 않아 분포를 알 수 없는 분류: {', '.join(uncollected) or '없음'}", '']

    out += ['## 7. 서류·링크', '']
    out += table(['항목', '건수'], [
        ['서류 안내 글 있음', f"{flags['doc_text_rows']:,}"], ['글은 있는데 아는 서류 이름이 없음', f"{flags['doc_text_no_known_name']:,}"],
        ['참고 링크(안전한 주소) 없음', f"{flags['no_source_url']:,}"], ['신청 방법·신청 주소 모두 없음', f"{flags['no_apply_route']:,}"],
        ['신청 주소 칸에 주소가 아닌 값', f"{flags['apply_url_not_url']:,}"]])
    names_by_key = {key: name for key, name, *_ in DOCS}
    out += table(['서류 안내에서 찾은 이름', '정책 수'], [[names_by_key[k], f'{v:,}'] for k, v in docs.most_common()])

    out += ['## 8. 가상 프로필로 걸러본 결과', '', f'걸러보기 가능 {tiers["screenable"]:,}건 대상. 자격 판정이 아니라 API 기재값 비교다.', '']
    out += table(['프로필', '맞아요', '확인 필요', '달라요'], [[label, f"{c['api_match']:,}", f"{c['needs_check']:,}", f"{c['api_mismatch']:,}"] for label, c in outcomes.items()])

    out += ['## 9. 항목별 채움 비율', '']
    out += table(['API 항목', '값 있음', '비율'], [[k, f'{v:,}', f'{v / total:.0%}'] for k, v in sorted(fill.items(), key=lambda x: -x[1])])
    out += ['## 10. 같은 이름·기관 중복 등록 (상위 15)', '']
    out += table(['정책명', '기관', '등록 수'], [[k[0], k[1] or '(기관 없음)', v] for k, v in sorted(dup.items(), key=lambda x: -x[1])[:15]])

    (BASE / 'data/DATA_AUDIT.md').write_text('\n'.join(out), encoding='utf-8', newline='\n')
    print(json.dumps({'total': total, 'integrity': integrity, 'tiers': dict(tiers), 'reasons': dict(reasons), 'statuses': dict(statuses),
                      'ages': dict(ages), 'region': dict(region), 'income': dict(income), 'unknown_codes': dict(unknown),
                      'duplicates': [len(dup), sum(dup.values())], 'flags': dict(flags),
                      'outcomes': {k: dict(v) for k, v in outcomes.items()},
                      'examples': {k: v[:5] for k, v in examples.items()}}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
