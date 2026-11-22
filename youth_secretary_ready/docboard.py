"""서류 준비판: 고른 정책들의 서류를 합치고, 가진 것과 없는 것을 나눠, 없는 서류를 어떤 순서로 어디서 준비하는지 알려 준다.

규칙만 쓴다(AI를 부르지 않는다). 입력은 정책 목록과 가진 서류, 출력은 작은 JSON이라 다른 AI가 도구로 불러 쓸 수 있다(TOOL).
- 서류는 온통청년의 서류 안내 글에서 '이름이 그대로 나온' 것만 찾는다. 사람 검수 전이다.
- 글이 비어 있으면 '서류 불필요'가 아니라 '안내 없음'이다. 이름을 찾은 서류를 다 가졌어도 '준비 끝'이라고 하지 않는다(공고의 전체 목록은 확인해야 한다).
- 발급처는 일반 안내다. 발급일·포함 항목·대체서류는 정책마다 달라 그 정책의 문장을 그대로 보여 준다.
- 가진 서류는 요청에 담아 받는다. 저장하지 않는다.
"""
import re
from datetime import date
from policy_structure import DOCS, DOC_KIND, _BULLET, _DOC_CUT, _DOC_IF, _PLACEHOLDER, doc_hit

# 준비하는 순서: 남에게 요청(시간을 내가 정할 수 없다) → 직접 작성 → 온라인·앱 발급 → 가지고 있는 것 찾기
LEAD = {**dict.fromkeys(('employment_cert', 'medical', 'career', 'recommendation', 'estimate', 'payslip', 'interview', 'completion'), 'request'),
        **dict.fromkeys(('application', 'consent', 'pledge', 'business_plan', 'self_intro', 'resume', 'proxy'), 'write'),
        **dict.fromkeys(('id_card', 'lease', 'labor_contract', 'receipt', 'license'), 'keep')}
LEAD_LABEL = {'request': '다른 사람·기관에 요청', 'write': '직접 작성', 'online': '온라인·앱·창구에서 발급', 'keep': '가지고 있는 것 찾기'}
_TIER = ('request', 'write', 'online', 'keep')
# 발급처 이름 → 공식 누리집(2026-11-19 열리는 것을 확인)
SITES = {'정부24': 'https://www.gov.kr', '홈택스': 'https://www.hometax.go.kr', '위택스': 'https://www.wetax.go.kr',
         '국민건강보험공단': 'https://www.nhis.or.kr', '전자가족관계등록시스템': 'https://efamily.scourt.go.kr',
         '고용24': 'https://www.work24.go.kr', '인터넷등기소': 'https://www.iros.go.kr'}
# 발급일 조건. '발급·발행'이라는 말이 있을 때만 읽는다('월세이체 증빙서류(최근 3개월 이내)', '최근 2년 이내 주소변동 포함'은 발급일이 아니다).
_ISSUED = re.compile(r'(?:최근|공고일|모집공고일|신청일|접수일)[^,)]{0,16}(?:이내|이후)\s*(?:발급|발행)분?|(?:발급|발행)[^,)]{0,10}(?:이내|이후)')
_EITHER = re.compile(r'또는|대체|중\s*(?:택|하나|1)|혹은')
_DOCLIKE = re.compile(r'서\b|증\b|서류|자료|사본|내역|등본|초본|대장|확인원|증명|명세')


def segments(text):
    """서류 안내 글을 서류 하나쯤 되는 조각으로 나눈다. 괄호 안의 쉼표에서는 자르지 않는다."""
    out = []
    for piece in _DOC_CUT.split(text):
        depth, start = 0, 0
        for i, ch in enumerate(piece + ','):
            depth += (ch in '([（') - (ch in ')]）')
            if ch == ',' and (depth <= 0 or i == len(piece)):   # 닫는 괄호가 빠진 글도 끝에서는 끊는다
                part = _BULLET.sub('', piece[start:i]).strip()
                if len(part) >= 2:
                    out.append(part)
                start, depth = i + 1, 0
    return out


def board(policies, have=(), on=None):
    """policies: external_id, name, documents_text, documents_note, period_status, period_label, deadline. have: 가진 서류의 키."""
    have = {k for k in have if k in DOC_KIND}
    docs, per_policy = {}, []
    for p in policies:
        text, parts = p['documents_text'], segments(p['documents_text'])
        needed, used = [], set()
        # '재직증명서(사업자등록증명원 또는 자격득실확인서로 대체 가능)'처럼 한 조각에 서류가 여럿이고 '또는·대체'가 있으면 그중 하나만 내는 것일 수 있다.
        either = {i: [name for _, name, needles, _ in DOCS if doc_hit(s, needles)] for i, s in enumerate(parts) if _EITHER.search(s)}
        for key, name, needles, how in DOCS:
            if not doc_hit(text, needles):
                continue
            at = next((i for i, s in enumerate(parts) if doc_hit(s, needles)), None)
            quote = parts[at] if at is not None else None
            used.update(i for i, s in enumerate(parts) if doc_hit(s, needles))
            issued = _ISSUED.search(quote or '')
            doc = docs.setdefault(key, {'key': key, 'name': name, 'kind': DOC_KIND[key], 'lead': LEAD.get(key, 'online'), 'how': how,
                                        'sites': [{'name': site, 'url': url} for site, url in SITES.items() if site in how], 'policies': []})
            doc['policies'].append({'external_id': p['external_id'], 'name': p['name'], 'quote': quote[:160] if quote else None,
                                    'conditional': bool(quote and _DOC_IF.search(quote)), 'issue_rule': issued.group(0) if issued else None,
                                    'one_of': [n for n in either.get(at, []) if n != name]})
            needed.append(key)
        # 이름을 못 찾았지만 서류처럼 보이는 조각. 빠뜨리지 않도록 그대로 보여 준다.
        other = [s[:120] for i, s in enumerate(parts) if i not in used and len(s) >= 4 and _DOCLIKE.search(s) and not _PLACEHOLDER.fullmatch(s)][:6]
        missing = [k for k in needed if k not in have]
        per_policy.append({'external_id': p['external_id'], 'name': p['name'], 'deadline': p['deadline'] if p['period_status'] == 'open' else None,
                           'needed': needed, 'missing': missing, 'other_lines': other, 'note': p.get('documents_note', ''),
                           # unlisted: 서류 안내가 없다(서류가 필요 없다는 뜻이 아니다). found_all: 이름을 찾은 서류는 다 있다(전체 목록은 공고 확인).
                           'status': 'unlisted' if not text else 'unread' if not needed else 'missing' if missing else 'found_all'})
    due = {p['external_id']: p['deadline'] for p in policies if p['period_status'] == 'open' and p['deadline'] and '연중' not in p['period_label']}
    for doc in docs.values():
        dates = [due[x['external_id']] for x in doc['policies'] if x['external_id'] in due]
        rules = sorted({x['issue_rule'] for x in doc['policies'] if x['issue_rule']})
        doc.update(have=doc['key'] in have, need_by=min(dates) if dates else None, issue_rules=rules,
                   only_if=all(x['conditional'] for x in doc['policies']))
        why = [f"{LEAD_LABEL[doc['lead']]}: {doc['how']}"]
        if doc['need_by']:
            why.append(f"가장 빠른 등록 마감일은 {doc['need_by']}이에요" + (f"({(date.fromisoformat(doc['need_by']) - on).days}일 남음)." if on else '.'))
        if rules:
            why.append(f"발급일 조건이 적혀 있어요(“{rules[0]}”). 너무 일찍 떼지 말고 신청 직전에 떼세요.")
        pick = next((x['one_of'] for x in doc['policies'] if x['one_of']), None)
        if pick:
            why.append(f"{', '.join(pick)}와(과) 함께 '또는·대체'로 적혀 있어요. 그중 하나만 내도 되는지 공고에서 확인하세요.")
        if doc['only_if']:
            why.append('해당하는 사람만 내는 서류로 적혀 있어요. 내가 해당하는지 먼저 확인하세요.')
        doc['reasons'] = why
    listed = sorted(docs.values(), key=lambda d: (_TIER.index(d['lead']), d['need_by'] or '9999', [k for k, *_ in DOCS].index(d['key'])))
    rank = {d['key']: i for i, d in enumerate(listed)}
    for x in per_policy:   # 정책별 목록도 준비 순서대로
        x['needed'].sort(key=rank.get)
        x['missing'].sort(key=rank.get)
    to_get, ready = [d for d in listed if not d['have']], [d for d in listed if d['have']]
    brief = [f"이름을 찾은 서류 {len(listed)}종 가운데 가진 것 {len(ready)}종, 준비할 것 {len(to_get)}종"]
    if to_get:
        brief.append('준비 순서: ' + ' → '.join(f"{d['name']}({LEAD_LABEL[d['lead']]})" for d in to_get))
    for x in per_policy:
        names = [docs[k]['name'] for k in x['missing']]
        brief.append(f"「{x['name']}」: " + {'unlisted': '서류 안내가 글에 없어요. 서류가 필요 없다는 뜻이 아니니 공고에서 확인하세요.',
                                          'unread': '서류 안내는 있지만 이름을 찾은 서류가 없어요. 공고에서 확인하세요.',
                                          'missing': '남은 서류 ' + ', '.join(names),
                                          'found_all': '이름을 찾은 서류는 모두 있어요. 전체 목록은 공고에서 확인하세요.'}[x['status']]
                     + (f" (이름을 못 찾은 안내 {len(x['other_lines'])}줄 있음)" if x['other_lines'] else ''))
    return {'as_of': on.isoformat() if on else None, 'to_get': to_get, 'ready': ready, 'policies': per_policy,
            'counts': {'documents': len(listed), 'ready': len(ready), 'to_get': len(to_get)}, 'brief': brief, 'saved': False,
            'notice': '온통청년에 등록된 서류 안내 글에서 이름이 그대로 나온 서류만 찾은 참고 결과입니다. 사람 검수 전이라 전체 서류와 발급 조건은 공고에서 확인하세요.'}


# 다른 AI(오케스트레이터)가 이 계산을 도구로 부를 때 쓰는 선언. 실행은 POST /api/desk/workspaces/{wid}/docboard 이다.
TOOL = {'name': 'prepare_documents',
        'description': '사용자가 고른 청년 정책들(1~5개)의 서류를 합치고, 가진 서류와 없는 서류를 나눠, 없는 서류의 준비 순서·발급처·정책별 조건 문장을 준다. '
                       '결과의 brief만 읽어도 답할 수 있다. 서류 목록을 확정하지 않으며 공고에서 확인하라고 함께 전해야 한다.',
        'parameters': {'type': 'object', 'required': ['external_ids'],
                       'properties': {'external_ids': {'type': 'array', 'items': {'type': 'string'}, 'description': '온통청년 정책 번호(plcyNo) 1~5개'},
                                      'have': {'type': 'array', 'items': {'type': 'string', 'enum': [key for key, *_ in DOCS]},
                                               'description': '사용자가 이미 가진 서류의 키. 모르면 비운다.'}}}}
