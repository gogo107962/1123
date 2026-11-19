"""신청 계획: 고른 정책들의 서류를 합치고 등록된 마감일 순서로 늘어놓는다. 읽기 전용.

검수 전 정책이라 서류 목록은 온통청년의 서류 안내 글에서 '이름이 그대로 나온' 서류만 찾는다.
- 글이 비어 있으면 '서류 불필요'가 아니라 '안내 없음'으로 남긴다.
- 발급처는 일반 안내다. 발급일·포함 항목·대체서류는 공고에서 확인해야 한다.
- 순서는 온통청년에 등록된 마감일 기준이다. 다음 모집일을 추정하지 않는다.
"""
from fastapi import HTTPException
from policy_structure import DOC_KIND, DOCS, EXCLUDE, RANK, period_status, structure, timing
from screening import NOTICE, age_rule, confirmed, provided, screen

from planner import conflicts, core_tokens, estimate, plan as plan_order   # 충돌·순서·금액 계산은 planner.py (이전 이름으로도 불러 쓸 수 있게 둔다)


def build(wid, external_ids, profile, on):
    from desk_service import evidence, preview
    ids = list(dict.fromkeys(external_ids))
    compared = provided(profile)
    policies, found, unlisted = [], {}, []
    for eid in ids:
        plan = preview(wid, eid)  # 없는 정책·없는 준비 공간이면 404
        bundle, links, _ = evidence(eid)
        fields, item = bundle['public_fields'], structure(bundle['public_fields'])
        status = period_status(item['application'], on, bundle['source_check'])
        deadline, label = timing(item['application'], status, on)
        result = screen(item, profile, status, age_rule(bundle['supplements']), bundle['supplements'], on) if compared else None
        docs = item['documents']
        text, source = (fields.get('sbmsnDcmntCn', '').strip() if docs['has_text'] else ''), 'api'
        if not text:  # API가 비어 있으면 공식 페이지에서 확인해 둔 서류 안내를 쓴다(사람 검수 전).
            found_docs = [x for x in bundle['supplements'] if x['field'] == 'documents' and confirmed(x)]   # 출처에서 문장이 확인된 것만
            if found_docs:
                text, source = ' '.join(found_docs[0]['quotes']), 'web_check'
        if not text:
            unlisted.append(eid)
        for key, name, needles, how in DOCS:
            if any(n in text for n in needles):
                found.setdefault(key, {'key': key, 'name': name, 'how': how, 'kind': DOC_KIND[key], 'policies': []})['policies'].append(eid)
        policies.append({
            'external_id': eid, 'name': fields['plcyNm'], 'agency': fields.get('sprvsnInstCdNm', ''),
            'period_status': status, 'period_label': label, 'deadline': deadline, 'documents_text': text,
            'amounts': item['amounts'], 'provision': item['provision'], 'early_close': item['said']['early_close'], 'channels': item['access']['channels'], 'documents_source': source,
            # 서류 칸에 '해당없음'이라고 적힌 경우와, 목록 없이 붙임파일만 가리키는 경우를 빈칸과 구분해 알린다.
            'documents_note': ("등록된 서류 칸에 '해당없음'으로 적혀 있습니다. 실제로 서류가 없는지 공고에서 확인하세요." if docs['stated_none'] and not text
                               else '서류 목록이 글에 없고 붙임파일·공고문을 보라고만 적혀 있습니다.' if docs['pointer_only'] and source == 'api' else ''),
            'scale': item['scale'], 'selection': item['selection'],
            'criteria': result['criteria'] if result else None, 'links': links,
            # 수집 글의 참여 제한 문장 + 공식 페이지에서 보완한 조건 문장 중 제외·중복 문구
            'exclusions': item['exclusions']['sentences'] + [q for x in bundle['supplements'] if x['field'] == 'conditions'
                                                              for q in x['quotes'] if EXCLUDE.search(q)],
            'tasks': [{'key': t['key'], 'title': t['title'], 'instructions': t['instructions']} for t in plan['tasks']],
            'preview_token': plan['preview_token']})
    planned = plan_order(policies, on)
    return {'as_of': on.isoformat(), 'policies': policies, 'order': planned['order'],
            'documents': [found[key] for key, *_ in DOCS if key in found], 'documents_unlisted': unlisted,
            'conflicts': planned['conflicts'], 'overlap_checked': False, 'saved': False, 'estimate': estimate(policies), 'planner': planned,
            'notice': NOTICE + ' 서류는 등록된 서류 안내 글에서 이름을 찾은 것이며, 중복 수혜 제한은 검수하지 않았습니다.'}
