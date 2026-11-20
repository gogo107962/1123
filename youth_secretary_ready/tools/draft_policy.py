"""수집 정책을 사람 검수용 '정책 초안'으로 옮긴다. 승인하지 않고, 엔진에 등록하지도 않는다.

    .venv\\Scripts\\python.exe -X utf8 tools\\draft_policy.py <정책번호> [<정책번호> ...]

결과는 data/policy_drafts/<code>.json 이다(data/policies/ 가 아니므로 서버가 자동으로 읽지 않는다).
검수자가 공고 원문과 대조해 고친 뒤 data/policies/ 로 옮기고 review 를 채워야 engine.py 가 판정에 쓴다.
- 온통청년 정보에서 규칙으로 옮길 수 있는 것(나이 범위, 시도, 취업·학력·전공·결혼 코드)만 rules 로 만든다.
- 옮길 수 없는 것(소득, 참여 제한 문장, 거주 기간, 시군구, 대상 집단, 접수기간 대조)은 manual_checks 로 남긴다.
- 온통청년 정보에 규칙으로 옮길 값이 없는 정책은, 공식 페이지에서 찾아 data/supplements.json 의 rules 에 적어 둔 규칙을 쓴다.
- 모든 출처는 verified=false, 검수자·검수일은 비워 둔다.
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from desk_plan import DOCS, doc_hit  # noqa: E402
from policy_data import https_url, validate_policy  # noqa: E402
from policy_structure import structure  # noqa: E402

REGION = {'11': '서울', '41': '경기', '28': '인천', '26': '부산'}   # fact_definitions.json 의 region 선택지에 있는 시도만
JOB = {'0013003': 'unemployed', '0013001': 'employed'}


def draft(payload, supplements=()):
    """등록된 한 건(+공식 페이지 보완 기록)으로 초안을 만든다. 만들 수 없으면 이유와 함께 ValueError."""
    st = structure(payload)
    url = next((payload.get(k) for k in ('refUrlAddr1', 'refUrlAddr2', 'aplyUrlAddr') if https_url(payload.get(k))), None)
    if not url:
        raise ValueError('https 공식 주소가 없어 출처를 적을 수 없습니다.')
    sources = [{'ref': 'api', 'kind': 'api', 'title': '온통청년 등록된 수집값(공고 원문 아님)', 'url': url, 'anchor': '', 'excerpt': '', 'verified': False}]
    found = []   # 공식 페이지에서 찾아 문장과 함께 적어 둔 규칙(사람 검수 전)
    for n, x in enumerate(supplements, 1):
        sources.append({'ref': f'web{n}', 'kind': 'notice', 'title': x['source_title'], 'url': x['source_url'], 'anchor': x['field'],
                        'excerpt': x['quotes'][0], 'verified': False})
        found += [{**rule, 'source_ref': f'web{n}'} for rule in x.get('rules', [])]
    rules, checks = [], [{'id': 'period', 'source_ref': 'api',
                          'message': f"등록된 신청기간({st['application']['raw'] or '기재 없음'})을 최신 공고의 회차·시작일·마감 시각과 대조하세요."}]
    age = st['age']
    if age['text_ranges'] and (age['min'], age['max']) not in [tuple(r) for r in age['text_ranges']]:
        checks.append({'id': 'age_text', 'source_ref': 'api', 'message': '등록된 나이 칸과 조건 글에 적힌 나이('
                       + ', '.join(f'{a}~{b}세' for a, b in age['text_ranges']) + ')가 다릅니다. 공고의 나이 기준으로 규칙을 고치세요.'})
    if age['kind'] == 'range' and age['max'] >= 99:
        # 상한 99·100·120·999는 '상한 없음'을 뜻하는 자리표시로 보인다. 하한만 규칙으로 옮기고 상한은 사람이 확인한다.
        rules.append({'id': 'age', 'type': 'required', 'predicate': {'fact': 'age', 'op': 'gte', 'value': age['min']},
                      'message': f"등록된 연령 {age['min']}세 이상. 공고의 기준일을 확인하세요.", 'source_ref': 'api'})
        checks.append({'id': 'age', 'source_ref': 'api', 'message': f"등록된 연령 상한이 {age['max']}로 적혀 있습니다. 실제 상한이 있는지 공고에서 확인하세요."})
    elif age['kind'] == 'range':
        rules.append({'id': 'age', 'type': 'required', 'predicate': {'fact': 'age', 'op': 'between', 'value': [age['min'], age['max']]},
                      'message': f"등록된 연령 {age['min']}~{age['max']}세. 공고의 기준일과 출생연도 표현을 확인하세요.", 'source_ref': 'api'})
    elif age['kind'] == 'unspecified' and age['no_limit']:
        checks.append({'id': 'age', 'source_ref': 'api', 'message': "온통청년 정보에 연령 '제한없음'으로 적혀 있습니다(온통청년 누리집 표시 기준). 실제로 연령 제한이 없는지 공고에서 확인하세요."})
    else:
        checks.append({'id': 'age', 'source_ref': 'api', 'message': f"등록된 연령이 {age['kind']} 상태입니다(최소 {age['min']}, 최대 {age['max']}). 공고에서 연령 기준을 확인하세요."})
    if age['kind'] != 'unspecified' and age['no_limit']:
        checks.append({'id': 'age_flag', 'source_ref': 'api', 'message': "온통청년 정보에 연령 범위와 '제한없음' 표기가 함께 적혀 있습니다. 어느 쪽이 맞는지 공고에서 확인하세요."})
    area = st['region']
    if len(area['sido']) == 1 and area['sido'][0] in REGION:
        rules.append({'id': 'region', 'type': 'required', 'predicate': {'fact': 'region', 'op': 'eq', 'value': REGION[area['sido'][0]]},
                      'message': f"등록된 지역 코드가 {area['sido_names'][0]}입니다. 주민등록 기준일을 확인하세요.", 'source_ref': 'api'})
        if not area['full_sido']:
            checks.append({'id': 'district', 'source_ref': 'api', 'message': f"시도 안의 일부 시군구만 등록돼 있습니다(코드 {', '.join(area['codes'][:8])}). 대상 시군구를 확인하세요."})
    elif not area['nationwide'] and area['sido'] and not area['unknown_sido']:
        rules.append({'id': 'region', 'type': 'required', 'predicate': {'fact': 'sido_code', 'op': 'in', 'value': area['sido']},
                      'message': f"등록된 지역 코드의 시도: {', '.join(area['sido_names'])}. 주민등록 기준일을 확인하세요.", 'source_ref': 'api'})
        if set(area['sido']) - set(area['full_sido']):
            checks.append({'id': 'district', 'source_ref': 'api', 'message': f"시도 안의 일부 시군구만 등록돼 있습니다(코드 {', '.join(area['codes'][:8])}). 대상 시군구를 확인하세요."})
    elif not area['nationwide']:
        checks.append({'id': 'region', 'source_ref': 'api', 'message': f"등록된 지역: {', '.join(area['sido_names']) or '기재 없음'}. 규칙으로 옮기지 못했습니다. 대상 지역을 확인하세요."})
    elif area['local_agency_hint']:
        checks.append({'id': 'region', 'source_ref': 'api', 'message': '전국으로 등록됐지만 주관기관이 지자체로 보입니다. 실제 대상 지역을 확인하세요.'})
    if area['residence_min_months']:
        checks.append({'id': 'residence', 'source_ref': 'api', 'message': f"글에 {area['residence_min_months']}개월 이상 거주 조건이 있습니다. 기준일과 연속 거주 여부를 확인하세요."})
    job = st['job']
    if not job['unrestricted'] and len(job['codes']) == 1 and job['codes'][0] in JOB:
        rules.append({'id': 'employment', 'type': 'required', 'predicate': {'fact': 'employment_status', 'op': 'eq', 'value': JOB[job['codes'][0]]},
                      'message': f"등록된 취업 요건: {job['labels'][0]}. 단기근로·사업자등록 예외를 확인하세요.", 'source_ref': 'api'})
    elif not job['unrestricted'] and job['codes'] and not job['unknown_codes']:
        rules.append({'id': 'employment', 'type': 'required', 'predicate': {'fact': 'job_code', 'op': 'in', 'value': job['codes']},
                      'message': f"등록된 취업 요건: {', '.join(job['labels'])} 중 하나. 공고의 표현과 예외를 확인하세요.", 'source_ref': 'api'})
    elif not job['unrestricted']:
        checks.append({'id': 'employment', 'source_ref': 'api', 'message': f"등록된 취업 요건: {', '.join(job['labels'] + job['unknown_codes']) or '기재 없음'}. 규칙으로 옮기지 못했습니다."})
    for key, title in [('school', '학력'), ('major', '전공'), ('marriage', '결혼 상태')]:
        item = st[key]
        if item['unrestricted']:
            continue
        if item['codes'] and not item['unknown_codes']:
            rules.append({'id': key, 'type': 'required', 'predicate': {'fact': key + '_code', 'op': 'in', 'value': item['codes']},
                          'message': f"등록된 {title} 요건: {', '.join(item['labels'])} 중 하나. 공고의 표현을 확인하세요.", 'source_ref': 'api'})
        else:
            checks.append({'id': key, 'source_ref': 'api', 'message': f"등록된 {title} 요건이 비었거나 코드표에 없는 값입니다. 공고에서 확인하세요."})
    if st['targets']:
        checks.append({'id': 'target', 'source_ref': 'api', 'message': f"정책 이름·특화 요건에 특정 대상({', '.join(st['targets'])})이 있습니다. 대상 요건을 공고에서 확인해 규칙으로 옮기세요."})
    if not (st['access']['has_method'] or st['access']['has_apply_url']):
        checks.append({'id': 'apply', 'source_ref': 'api', 'message': '온통청년 정보에 신청 방법과 신청 주소가 없습니다. 공고에서 신청 방법을 확인하세요.'})
    if st['exam']['fee']:
        checks.append({'id': 'exam', 'source_ref': 'api', 'message': '응시료 지원입니다. 대상 시험 종목과 응시일 기준을 공고에서 확인해 규칙으로 옮기세요.'
                       + (f" 글에 적힌 시험 종류: {', '.join(st['exam']['kinds'])}." if st['exam']['kinds'] else '')})
    if st['housing']['no_home']:
        checks.append({'id': 'housing', 'source_ref': 'api', 'message': f"무주택 문장: “{st['housing']['no_home']}” — 주택 소유 기준(본인·세대)을 공고에서 확인하세요."})
    income = st['income']
    if income['code'] != '0043001':
        checks.append({'id': 'income', 'source_ref': 'api', 'message': (
            f"등록된 소득: {', '.join(income['labels']) or '구분 없음'} {income['text'][:120]}".strip()
            + (f" 연 {income['annual']['max']:,}만원 이하(단위는 온통청년 누리집 표시 기준)" if income['annual'] else '')
            + ' · 금액 단위, 개인/가구 기준, 산정 방식을 공고에서 확인하세요.')})
    if st['exclusions']['explicit_none']:
        checks.append({'id': 'exclusion', 'source_ref': 'api', 'message': "등록된 참여 제한 칸에 '해당 없음'으로 적혀 있습니다. 공고에 제외·중복 수혜 제한이 없는지 확인하세요."})
    for n, sentence in enumerate(st['exclusions']['sentences'], 1):
        checks.append({'id': f'exclusion{n}', 'source_ref': 'api', 'message': f'참여 제한 문장: “{sentence}” — 제외 규칙으로 옮길지 검수하세요.'})
    for rule in found:   # 같은 항목이면 등록 정보 대신 공식 페이지의 규칙을 쓴다
        rules = [r for r in rules if r['id'] != rule['id']] + [rule]
    if not rules:
        raise ValueError('규칙으로 옮길 수 있는 등록 정보가 없습니다(나이 범위·지역·취업·학력·전공·결혼 요건 모두 불가).')
    text, ref = ((payload.get('sbmsnDcmntCn') or '').strip() if st['documents']['has_text'] else ''), 'api'   # '해당없음'·'-'는 안내 글로 치지 않는다
    for n, x in enumerate(supplements, 1):
        if not text and x['field'] == 'documents':
            text, ref = ' '.join(x['quotes']), f'web{n}'
    documents = [{'code': key, 'title': name, 'source_ref': ref, 'constraints': {},
                  'instructions': how + ' · 발급일, 포함 항목, 대체서류는 공고에서 확인하세요.', 'alternatives': []}
                 for key, name, needles, how in DOCS if doc_hit(text, needles)]
    checks.append({'id': 'documents', 'source_ref': ref, 'message': ('서류 안내 글에서 이름을 찾은 서류만 옮겼습니다. 목록 전체를 공고와 대조하세요.' if text
                                                                     else '서류 안내가 없습니다. 서류가 필요 없다는 뜻이 아닙니다.')})
    if st['scale']['first_come']:
        checks.append({'id': 'first_come', 'source_ref': 'api', 'message': f"온통청년 정보에 선착순{(' ' + format(st['scale']['count'], ',') + '명') if st['scale']['count'] else ''}으로 적혀 있습니다. 조기 마감 여부와 실제 마감일을 공고에서 확인하세요."})
    windows = st['application']['windows']
    return validate_policy({
        'code': 'ontong-' + payload['plcyNo'].lower(), 'version': '2026.1', 'name': payload['plcyNm'],
        'description': (payload.get('plcyExplnCn') or '')[:300], 'agency': payload.get('sprvsnInstCdNm') or '기관 확인 필요',
        'region': '전국' if area['nationwide'] else ', '.join(area['sido_names']) or '지역 확인 필요',
        'category': payload.get('lclsfNm') or '분류 확인 필요', 'demo_only': False, 'official_url': url,
        'application': ({'open': windows[0]['start'], 'close': windows[-1]['end'], 'period_note': '등록된 날짜. 공고와 대조 전.'} if windows
                        else {'period_note': f"등록된 신청기간 구분: {st['application']['kind']}. 날짜 없음."}),
        'review': {'status': 'draft', 'reviewed_by': '', 'reviewed_at': None},
        'sources': sources, 'rules': rules, 'manual_checks': checks, 'documents': documents})


def main(ids):
    con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
    notes = json.loads((BASE / 'data/supplements.json').read_text(encoding='utf-8'))
    out = BASE / 'data' / 'policy_drafts'
    out.mkdir(exist_ok=True)
    for eid in ids:
        row = con.execute('SELECT payload_json FROM ontong_candidates WHERE external_id=?', (eid,)).fetchone()
        if not row:
            print(eid, '→ 수집 자료에 없음')
            continue
        try:
            policy = draft(json.loads(row[0]), [x for x in notes if x['external_id'] == eid])
        except ValueError as exc:
            print(eid, '→ 초안을 만들지 않음:', exc)
            continue
        (out / f"{policy['code']}.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(eid, '→', policy['name'], f"| 규칙 {len(policy['rules'])} · 검수 항목 {len(policy['manual_checks'])} · 서류 {len(policy['documents'])}")


if __name__ == '__main__':
    main(sys.argv[1:])
