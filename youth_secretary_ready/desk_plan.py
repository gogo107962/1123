"""신청 계획: 고른 정책들의 서류를 합치고 API 기재 마감일 순서로 늘어놓는다. 읽기 전용.

검수 전 정책이라 서류 목록은 API의 서류 안내 글에서 '이름이 그대로 나온' 서류만 찾는다.
- 글이 비어 있으면 '서류 불필요'가 아니라 '안내 없음'으로 남긴다.
- 발급처는 일반 안내다. 발급일·포함 항목·대체서류는 공고에서 확인해야 한다.
- 순서는 API에 적힌 마감일 기준이다. 다음 모집일을 추정하지 않는다.
"""
import re
from datetime import date
from fastapi import HTTPException
from policy_structure import DOC_KIND, DOCS, EXCLUDE, RANK, period_status, structure, timing
from screening import NOTICE, age_rule, confirmed, provided, screen

SIMILAR = re.compile(r'유사|동일|중복|타\s*(지자체|기관|시군|시·군|자치구)')
TOPICS = ('응시료', '월세', '수당', '대출', '계좌', '교통', '장학', '인턴')
GENERIC = {'지원사업', '지원제도', '프로젝트', '프로그램', '청년정책', '청년지원'}


def core_tokens(name):
    """정책 이름에서 연도·괄호를 빼고, 다른 정책 글에서 찾을 만한 고유한 낱말만 남긴다."""
    plain = re.sub(r'\(.*?\)|\[.*?\]|［.*?］|\d{4}\s*년?도?', ' ', name)
    return [t for t in plain.split() if len(t) >= 4 and t not in GENERIC]


def conflicts(policies):
    """A의 참여 제한 문장이 B를 가리키면 A→B로만 적는다. 뒤집어 적용하지 않고, 판단이 아니라 확인할 근거다."""
    found = []
    for a in policies:
        for b in policies:
            if a is b:
                continue
            for sentence in a['exclusions']:
                flat = sentence.replace(' ', '')
                named = any(t in flat for t in core_tokens(b['name']))
                similar = bool(SIMILAR.search(sentence)) and any(t in a['name'] and t in b['name'] for t in TOPICS)
                if named or similar:
                    found.append({'from': a['external_id'], 'to': b['external_id'],
                                  'kind': 'named' if named else 'similar', 'quote': sentence})
                    break
    return found


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
            'amounts': item['amounts'], 'channels': item['access']['channels'], 'documents_source': source,
            # 서류 칸에 '해당없음'이라고 적힌 경우와, 목록 없이 붙임파일만 가리키는 경우를 빈칸과 구분해 알린다.
            'documents_note': ("API 서류 칸에 '해당없음'으로 적혀 있습니다. 실제로 서류가 없는지 공고에서 확인하세요." if docs['stated_none'] and not text
                               else '서류 목록이 글에 없고 붙임파일·공고문을 보라고만 적혀 있습니다.' if docs['pointer_only'] and source == 'api' else ''),
            'scale': item['scale'], 'selection': item['selection'],
            'criteria': result['criteria'] if result else None, 'links': links,
            # 수집 글의 참여 제한 문장 + 공식 페이지에서 보완한 조건 문장 중 제외·중복 문구
            'exclusions': item['exclusions']['sentences'] + [q for x in bundle['supplements'] if x['field'] == 'conditions'
                                                              for q in x['quotes'] if EXCLUDE.search(q)],
            'tasks': [{'key': t['key'], 'title': t['title'], 'instructions': t['instructions']} for t in plan['tasks']],
            'preview_token': plan['preview_token']})
    # 연중으로 적힌 정책은 날짜가 정해진 접수 중 정책 뒤에 둔다.
    order = [p['external_id'] for p in sorted(policies, key=lambda p: (RANK[p['period_status']] + (1.5 if '연중' in p['period_label'] else 0), p['deadline'] or ''))]
    return {'as_of': on.isoformat(), 'policies': policies, 'order': order,
            'documents': [found[key] for key, *_ in DOCS if key in found], 'documents_unlisted': unlisted,
            'conflicts': conflicts(policies), 'overlap_checked': False, 'saved': False,
            'notice': NOTICE + ' 서류는 API 서류 안내 글에서 이름을 찾은 것이며, 중복 수혜 제한은 검수하지 않았습니다.'}
