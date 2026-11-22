"""신청 계획: 고른 정책들의 서류를 합치고 등록된 마감일 순서로 늘어놓는다. 읽기 전용.

검수 전 정책이라 서류 목록은 온통청년의 서류 안내 글에서 '이름이 그대로 나온' 서류만 찾는다.
- 글이 비어 있으면 '서류 불필요'가 아니라 '안내 없음'으로 남긴다.
- 발급처는 일반 안내다. 발급일·포함 항목·대체서류는 공고에서 확인해야 한다.
- 순서는 온통청년에 등록된 마감일 기준이다. 다음 모집일을 추정하지 않는다.
"""
import re
from fastapi import HTTPException
from policy_structure import DOC_KIND, DOCS, EXCLUDE, RANK, doc_hit, doc_optional, period_status, structure, timing
from screening import NOTICE, age_rule, confirmed, provided, screen

from docboard import board
from planner import conflicts, core_tokens, estimate, plan as plan_order   # 충돌·순서·금액 계산은 planner.py (이전 이름으로도 불러 쓸 수 있게 둔다)

_SENTENCE = re.compile(r'[\r\n]+|(?<=[.。])\s+')
_SUBMIT = re.compile(r'제출|첨부|지참|구비')
FILE_READ = ('attachment_pdf', 'attachment_hwpx', 'image')   # 보완 기록의 read_from: 공고의 첨부파일·이미지에서 읽음


def _exclusions(item, bundle):
    return item['exclusions']['sentences'] + [q for x in bundle['supplements'] if x['field'] == 'conditions' for q in x['quotes'] if EXCLUDE.search(q)]


def compare(external_ids, on):
    """대화 오케스트레이터가 충돌·순서 플래너(planner.plan)를 부를 때 쓴다. 찾은 정책 몇 건의 순서·함께 받기 어려운 조합·예상 금액.
    읽기 전용이고 준비 공간이 필요 없다. 화면 문장(text)은 플래너가 틀로 만든 brief를 그대로 쓴다(모델이 쓰지 않는다)."""
    from desk_service import evidence
    policies = []
    for eid in external_ids:
        bundle = evidence(eid)[0]
        fields, item = bundle['public_fields'], structure(bundle['public_fields'])
        status = period_status(item['application'], on, bundle['source_check'])
        deadline, label = timing(item['application'], status, on)
        policies.append({'external_id': eid, 'name': fields['plcyNm'], 'period_status': status, 'period_label': label, 'deadline': deadline,
                         'amounts': item['amounts'], 'provision': item['provision'], 'early_close': item['said']['early_close'],
                         'region_codes': item['region']['codes'], 'category': item['category'], 'exclusions': _exclusions(item, bundle)})
    planned = plan_order(policies, on)
    return {**planned, 'policies': [{'external_id': p['external_id'], 'name': p['name'], 'period_label': p['period_label']} for p in policies],
            'text': '\n'.join(planned['brief']) + '\n' + planned['notice']}


def build(wid, external_ids, profile, on, have=()):
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
        # 서류 칸이 비었거나 '붙임파일을 확인'처럼 서류 이름이 하나도 없으면, 공식 페이지에서 확인해 둔 서류 안내를 쓴다(사람 검수 전).
        if not text or not docs['known']:
            # 출처 페이지에서 문장이 자동 확인된 것을 먼저 쓰고, 없으면 공고의 첨부파일·이미지에서 읽은 것을 쓴다.
            # 첨부파일·이미지에서 읽은 문장은 자동 대조를 할 수 없어 어디서 읽었는지를 화면에 함께 적는다(판정에는 쓰지 않는다).
            listed = [x for x in bundle['supplements'] if x['field'] == 'documents']
            usable = [x for x in listed if confirmed(x)] + [x for x in listed if not confirmed(x) and x.get('read_from') in FILE_READ]
            # 서류 이름이 가장 많이 읽히는 기록을 쓴다(페이지 글에는 한두 줄뿐이고 첨부 공고문에 전체 목록이 있는 정책이 있다). 같으면 자동 확인된 것 먼저.
            found_docs = sorted(usable, key=lambda x: -sum(doc_hit('\n'.join(x['quotes']), needles) for _, _, needles, _ in DOCS))[:1]
            if found_docs:
                text, source = '\n'.join(found_docs[0]['quotes']), ('web_check' if confirmed(found_docs[0]) else found_docs[0]['read_from'])
        if not any(doc_hit(text, needles) for _, _, needles, _ in DOCS):
            # 서류 칸에도 보완 기록에도 서류 이름이 없으면, 신청 방법·기타 안내 글에서 '…를 제출·첨부·지참'이라고 적힌 문장을 쓴다.
            other = [s.strip() for f in ('plcyAplyMthdCn', 'etcMttrCn') for s in _SENTENCE.split(fields.get(f) or '')
                     if _SUBMIT.search(s) and any(doc_hit(s, needles) for _, _, needles, _ in DOCS)]
            if other:
                text, source = '\n'.join(other), 'api_other'
        if not text:
            unlisted.append(eid)
        for key, name, needles, how in DOCS:
            if doc_hit(text, needles):
                doc = found.setdefault(key, {'key': key, 'name': name, 'how': how, 'kind': DOC_KIND[key], 'policies': [], 'optional': True})
                doc['policies'].append(eid)
                # 고른 정책 모두에서 '해당자·선택'으로 적힌 서류만 '해당하는 경우만'으로 표시한다(하나라도 필수면 필수).
                doc['optional'] = doc['optional'] and doc_optional(text, needles)
        policies.append({
            'external_id': eid, 'name': fields['plcyNm'], 'agency': fields.get('sprvsnInstCdNm', ''),
            'period_status': status, 'period_label': label, 'deadline': deadline, 'documents_text': text,
            'amounts': item['amounts'], 'provision': item['provision'], 'early_close': item['said']['early_close'],
            'region_codes': item['region']['codes'], 'category': item['category'], 'channels': item['access']['channels'], 'documents_source': source,
            # 서류 칸에 '해당없음'이라고 적힌 경우와, 목록 없이 붙임파일만 가리키는 경우를 빈칸과 구분해 알린다.
            'documents_note': ("등록된 서류 칸에 '해당없음'으로 적혀 있습니다. 실제로 서류가 없는지 공고에서 확인하세요." if docs['stated_none'] and not text
                               else '서류 목록이 글에 없고 붙임파일·공고문을 보라고만 적혀 있습니다.' if docs['pointer_only'] and source == 'api' else ''),
            'scale': item['scale'], 'selection': item['selection'],
            'criteria': result['criteria'] if result else None, 'links': links,
            # 수집 글의 참여 제한 문장 + 공식 페이지에서 보완한 조건 문장 중 제외·중복 문구
            'exclusions': _exclusions(item, bundle),
            'tasks': [{'key': t['key'], 'title': t['title'], 'instructions': t['instructions']} for t in plan['tasks']],
            'preview_token': plan['preview_token']})
    planned = plan_order(policies, on)
    return {'as_of': on.isoformat(), 'policies': policies, 'order': planned['order'],
            'documents': [found[key] for key, *_ in DOCS if key in found], 'documents_unlisted': unlisted,
            'conflicts': planned['conflicts'], 'overlap_checked': False, 'saved': False, 'estimate': estimate(policies),
            'planner': planned, 'docboard': board(policies, have, on),
            'notice': NOTICE + ' 서류는 등록된 서류 안내 글에서 이름을 찾은 것이며, 중복 수혜 제한은 검수하지 않았습니다.'}
