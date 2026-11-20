"""신청 계획: 고른 정책들의 서류를 합치고 등록된 마감일 순서로 늘어놓는다. 읽기 전용.

검수 전 정책이라 서류 목록은 온통청년의 서류 안내 글에서 '이름이 그대로 나온' 서류만 찾는다.
- 글이 비어 있으면 '서류 불필요'가 아니라 '안내 없음'으로 남긴다.
- 발급처는 일반 안내다. 발급일·포함 항목·대체서류는 공고에서 확인해야 한다.
- 순서는 온통청년에 등록된 마감일 기준이다. 다음 모집일을 추정하지 않는다.
"""
import re
from datetime import date
from fastapi import HTTPException
from policy_structure import DOC_KIND, DOCS, EXCLUDE, RANK, doc_hit, doc_optional, period_status, structure, timing
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


GRANT = ('0042006', '0042010')   # 정책제공 방법코드: 보조금, 바우처
# 이보다 큰 금액은 더하지 않는다. 수집 글에서 1,000만원이 넘는 금액은 대부분 창업 사업화자금·기업 인건비·기관 지원금이었다(2026-11-19 확인).
SUM_MAX = 10_000_000


def estimate(policies):
    """예상 지원 금액. 제공 방법이 보조금·바우처로 등록된 정책만, 지원 내용 글의 금액 표현 하나씩(기간이나 '최대'가 붙은 첫 표현)을 더한다.
    대출 한도·보증금·예산·팀당 같은 말이 앞에 붙은 금액과 1,000만원이 넘는 금액은 고르지 않는다.
    매달 받는 금액과 그 밖의 금액은 따로 더한다. 대출·보증은 한도라서 더하지 않고, 제공 방법이 다른 정책은 지원금인지 알 수 없어 더하지 않는다."""
    used, loans, unsure = [], [], []
    for p in policies:
        pick = next((a for a in p['amounts'] if (a['period'] or a['max']) and not a['other'] and a['krw'] <= SUM_MAX), None)
        if p['provision']['loan']:
            loans.append(p['external_id'])
        elif p['provision']['code'] in GRANT and pick:
            used.append({'external_id': p['external_id'], 'text': pick['text'], 'krw': pick['krw'], 'monthly': pick['period'] in ('월', '매월')})
        elif p['amounts']:
            unsure.append(p['external_id'])
    return {'monthly_krw': sum(x['krw'] for x in used if x['monthly']), 'other_krw': sum(x['krw'] for x in used if not x['monthly']),
            'used': used, 'loans': loans, 'unsure': unsure}


_SENTENCE = re.compile(r'[\r\n]+|(?<=[.。])\s+')
_SUBMIT = re.compile(r'제출|첨부|지참|구비')
FILE_READ = ('attachment_pdf', 'attachment_hwpx', 'image')   # 보완 기록의 read_from: 공고의 첨부파일·이미지에서 읽음


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
            'amounts': item['amounts'], 'provision': item['provision'], 'channels': item['access']['channels'], 'documents_source': source,
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
    # 연중으로 적힌 정책은 날짜가 정해진 접수 중 정책 뒤에 둔다.
    order = [p['external_id'] for p in sorted(policies, key=lambda p: (RANK[p['period_status']] + (1.5 if '연중' in p['period_label'] else 0), p['deadline'] or ''))]
    return {'as_of': on.isoformat(), 'policies': policies, 'order': order,
            'documents': [found[key] for key, *_ in DOCS if key in found], 'documents_unlisted': unlisted,
            'conflicts': conflicts(policies), 'overlap_checked': False, 'saved': False, 'estimate': estimate(policies),
            'notice': NOTICE + ' 서류는 등록된 서류 안내 글에서 이름을 찾은 것이며, 중복 수혜 제한은 검수하지 않았습니다.'}
