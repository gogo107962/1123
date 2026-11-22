"""충돌·순서 플래너: 고른 정책들에서 함께 받기 어려울 수 있는 조합, 신청 순서와 그 이유, 조합별 예상 금액을 계산한다.

규칙만 쓴다(AI를 부르지 않는다). 입력은 정책 목록, 출력은 작은 JSON이라 다른 AI가 도구로 불러 쓸 수 있다(TOOL).
- 근거는 온통청년의 참여 제한 문장이다. 사람 검수 전이므로 '못 받는다'로 단정하지 않고 문장을 그대로 보여 준다.
- A의 글이 B를 가리키면 A→B로만 적는다. 뒤집어 적용하지 않는다.
- 등록된 지역이 겹치지 않는 정책끼리는 함께 받을 일이 없으므로 충돌로 적지 않는다(지역을 모르면 겹치는 것으로 본다).
- 순서는 등록된 마감일과 글의 조기 마감 문구만 쓴다. 다음 모집일을 추정하지 않는다.
- 금액은 글에 적힌 금액을 더한 참고 값이다. 지원 기간(몇 달)을 곱하지 않는다.
"""
import re
from datetime import date, timedelta
from itertools import combinations
from policy_structure import RANK

SIMILAR = re.compile(r'유사|동일|중복|타\s*(지자체|기관|시군|시·군|자치구)')
TOPICS = ('응시료', '월세', '수당', '대출', '계좌', '교통', '장학', '인턴', '면접', '이사', '전세', '이자', '통장', '적금', '공제', '저축')
# 정책 이름에 흔해서 다른 정책을 가리킨다고 볼 수 없는 낱말(2026-11-19 수집본 3,995건의 참여 제한 문장에서 잘못 걸리던 것)
GENERIC = {'지원사업', '지원제도', '프로젝트', '프로그램', '청년정책', '청년지원', '지원대상자', '모집공고', '자치단체', '지방자치단체',
           '대한민국', '공공기관', '중소기업', '고등학교', '대학원생', '소상공인', '자영업자', '청년농업인', '청년창업', '청년일자리',
           '일자리사업', '아카데미', '네트워크', '아르바이트', '신혼부부', '사관학교', '역량강화', '산업단지', '오프라인', '취업준비', '창업지원사업'}
# 시도 이름과 '취업지원'·'창업지원'처럼 두 글자 뒤에 '지원'이 붙은 말은 분야를 말할 뿐이다('국민취업지원제도' 안에도 들어 있다).
# '거주청년'·'광주청년'처럼 '청년'으로 끝나는 말은 사람을 가리킬 뿐이다.
_PLACE = re.compile(r'(특별시|광역시|자치시|자치도|남도|북도|청년)$|^..지원$')
# 아래 식은 띄어쓰기를 뺀 글에 쓴다.
_STATUS = re.compile(r'(?:에|의|등)?(?:재직|근무|재학|졸업|소속|임직원|종사|직원|국적|취업|거주|입주)')   # 받는 지원이 아니라 신분을 말하는 문장('공공임대주택 거주자')
_WORDS = r'수혜|수급|참여|지원금?[을를]?받|선정|이용|중복'
_RECEIVE = re.compile(_WORDS)
_BREAK = re.compile(r'[①-⑳.;]')                      # 다음 항목으로 넘어가는 자리. 그 뒤의 말은 이 낱말과 상관없다
_SUFFIX = re.compile(r'(?:지원)?(?:사업|제도|금)?')      # 이름 뒤에 흔히 붙는 말
# 낱말 바로 뒤가 이렇게 이어지면 그 낱말로 끝나는 이름이다: 나열(및·등·또는), 조사, '기수혜자' 같은 받는 말, 글자가 아닌 것
_NEXT = re.compile(r'및|등|또는|이나|과|와|(?:[을를에의은는이가도로])?(?:기|이미|현재)?(?:' + _WORDS + r'|가입)|[^가-힣]|$')
_ALIKE = re.compile(r'유사|동일')
_JOIN = re.compile(r'가입')                            # 통장·적금·공제 같은 이름 뒤에서만 '받는 지원'으로 본다(고용보험 가입자는 신분이다)
_SAVINGS = re.compile(r'통장|계좌|적금|공제|저축|펀드')
_ALLOW = re.compile(r'(?:중복|동시|병행|함께)[^.]{0,8}가능|제외대상이?아님|제외하지않|제한하지않')
_DENY = re.compile(r'제외|불가|제한|안됨|못받')


def core_tokens(name):
    """정책 이름에서 연도·괄호를 빼고, 다른 정책 글에서 찾을 만한 고유한 낱말만 남긴다."""
    plain = re.sub(r'\(.*?\)|\[.*?\]|［.*?］|\d{4}\s*년?도?', ' ', name)
    return [t for t in plain.split() if len(t) >= 4 and t not in GENERIC and not _PLACE.search(t)]


def _named(flat, name):
    """문장이 그 정책을 '받는 지원'으로 가리키면 'named', 함께 받을 수 있다고 적었으면 'allowed', 아니면 None."""
    target = name.replace(' ', '')
    for token in core_tokens(name):
        at = flat.find(token)
        if at < 0:
            continue
        tail = _BREAK.split(flat[at + len(token):at + len(token) + 40])[0]
        if _STATUS.match(tail) or (_JOIN.match(tail) and not _SAVINGS.search(token)):   # '고용보험 가입자'도 신분이다
            continue
        # 낱말 뒤에 다른 말이 이어지면 더 좁은 이름이다('청년월세 한시 특별지원'). 그 말까지 이름에 있는 정책만 가리킨다.
        rest = tail[_SUFFIX.match(tail).end():]
        if not _NEXT.match(rest) and rest[:2] not in target:
            continue
        if not (_RECEIVE.search(tail) or (_JOIN.search(tail) and _SAVINGS.search(token))):
            continue
        allow, deny = _ALLOW.search(tail), _DENY.search(tail)
        return 'allowed' if allow and (not deny or allow.start() <= deny.start()) else 'named'
    return None


def overlap(a, b):
    """등록된 지역이 겹치는가. 어느 한쪽이라도 지역을 모르면 겹치는 것으로 본다(모르는 것을 '안 겹친다'로 바꾸지 않는다)."""
    x, y = a.get('region_codes'), b.get('region_codes')
    return not x or not y or bool(set(x) & set(y))


def relations(policies):
    """정책 쌍마다 A의 참여 제한 문장이 B를 가리키는지 본다. conflicts는 함께 받기 어려울 수 있는 것, compatible은 함께 받을 수 있다고 적힌 것."""
    conflicts, compatible = [], []
    for a in policies:
        for b in policies:
            if a is b or not overlap(a, b):
                continue
            for sentence in a['exclusions']:
                kind = _named(sentence.replace(' ', ''), b['name'])
                # '유사한 사업(대출이자 사업 등)'처럼 비슷한 사업을 말하는 문장은 분야가 같은 정책만 가리킨다(주거 이자 지원과 학자금 대출이자).
                apart = bool(a.get('category') and b.get('category') and a['category'] != b['category'])
                if kind and _ALIKE.search(sentence) and apart:
                    kind = None
                if not kind and not apart and SIMILAR.search(sentence) and any(t in a['name'] and t in b['name'] for t in TOPICS):
                    kind = 'allowed' if _ALLOW.search(sentence.replace(' ', '')) else 'similar'
                if kind:
                    (compatible if kind == 'allowed' else conflicts).append(
                        {'from': a['external_id'], 'to': b['external_id'], 'kind': kind, 'quote': sentence})
                    break
    return conflicts, compatible


def conflicts(policies):
    return relations(policies)[0]


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


def groups(ids, found, money):
    """충돌 문구로 이어진 정책 묶음과, 묶음 안에서 함께 고를 수 있는 조합(더 넣을 수 없는 조합만).
    money는 정책 번호 → (매달 금액, 그 밖의 금액)이고 더하지 않는 정책은 없다."""
    edges = {frozenset((c['from'], c['to'])) for c in found}
    out, seen = [], set()
    for start in ids:
        if start in seen or not any(start in e for e in edges):
            continue
        members, stack = [], [start]
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                members.append(x)
                stack.extend(y for e in edges if x in e for y in e)
        members.sort(key=ids.index)
        free = [set(c) for n in range(len(members), 0, -1) for c in combinations(members, n)
                if not any(e <= set(c) for e in edges)]
        options = [{'keep': [m for m in members if m in s], 'drop': [m for m in members if m not in s],
                    'monthly_krw': sum(money.get(m, (0, 0))[0] for m in s), 'other_krw': sum(money.get(m, (0, 0))[1] for m in s)}
                   for s in free if not any(s < bigger for bigger in free)]
        out.append({'policies': members, 'options': options})
    return out


SOON = 7   # 조기 마감 문구가 있는 접수 중 정책은 이 날수 안에 마감하는 정책처럼 앞에 둔다(날짜를 만드는 것이 아니라 줄 세우는 기준이다)


def steps(policies, on, found):
    """신청 순서와 이유. 접수 중(마감 빠른 순) → 시작 전 → 상시 → 기간 미기재 → 마감. 연중 표기는 날짜가 정해진 접수 중 정책 뒤."""
    name = {p['external_id']: p['name'] for p in policies}
    soon = (on + timedelta(days=SOON)).isoformat()

    def key(p):
        rush = p['period_status'] == 'open' and p.get('early_close')
        yearly = '연중' in p['period_label']
        due = p['deadline'] or ''
        return (RANK[p['period_status']] + (1.5 if yearly and not rush else 0), min(due, soon) if rush and not yearly and due else soon if rush else due)

    out = []
    for p in sorted(policies, key=key):
        eid, why = p['external_id'], []
        if p['period_status'] == 'open' and '연중' in p['period_label']:
            why.append('신청기간이 연중으로 적혀 있어요. 모집 회차는 공고에서 확인하세요.')
        elif p['period_status'] == 'open':
            why.append(f"등록된 마감일({p['deadline']})까지 {(date.fromisoformat(p['deadline']) - on).days}일 남았어요.")
        elif p['period_status'] == 'upcoming':
            why.append(f"{p['deadline']}에 접수가 시작된다고 등록돼 있어요.")
        else:
            why.append({'rolling': '상시로 등록돼 있어요. 지금 접수하는지 공고에서 확인하세요.',
                        'unknown': '신청기간이 적혀 있지 않아요. 공고에서 확인하세요.'}.get(p['period_status'], '등록된 신청기간이 끝났어요. 다음 모집은 공고에서 확인하세요.'))
        if p['period_status'] == 'open' and p.get('early_close'):
            why.append(f"글에 예산 소진·선착순·조기 마감이 적혀 있어 서두르는 순서에 뒀어요: “{p['early_close']}”")
        for c in found:
            if c['from'] == eid:
                why.append(f"이 정책의 안내 글에 「{name[c['to']]}」와 함께 받기 어려울 수 있다는 문구가 있어요. 신청 전에 기관에 확인하세요.")
            elif c['to'] == eid and not any(r['from'] == eid and r['to'] == c['from'] for r in found):
                why.append(f"「{name[c['from']]}」의 안내 글이 이 정책을 받는 사람을 제외할 수 있다고 적고 있어요. 둘 다 받으려면 그쪽 기관에 먼저 확인하세요.")
        out.append({'external_id': eid, 'name': p['name'], 'period_status': p['period_status'], 'deadline': p['deadline'],
                    'reasons': why, 'check_with': sorted({c['to'] if c['from'] == eid else c['from'] for c in found if eid in (c['from'], c['to'])})})
    return out


NOTICE = '온통청년에 등록된 글만으로 계산한 참고 결과입니다. 사람 검수 전이라 함께 받을 수 있는지와 금액은 공고와 기관에서 확인하세요.'


def plan(policies, on):
    """policies: external_id, name, exclusions(문장 목록), amounts, provision, period_status, period_label, deadline, early_close(없으면 None),
    region_codes(등록된 시군구 코드. 모르면 빈 목록), category(분야. 모르면 빈 글)."""
    ids = [p['external_id'] for p in policies]
    found, compatible = relations(policies)
    total = estimate(policies)
    money = {x['external_id']: (x['krw'], 0) if x['monthly'] else (0, x['krw']) for x in total['used']}
    grouped = groups(ids, found, money)
    low, high = [total['monthly_krw'], total['other_krw']], [total['monthly_krw'], total['other_krw']]
    for g in grouped:   # 묶음에서 한 조합만 받는 경우: 묶음 전체를 빼고 조합의 가장 적은/많은 금액을 넣는다
        for i, k in enumerate(('monthly_krw', 'other_krw')):
            whole = sum(money.get(m, (0, 0))[i] for m in g['policies'])
            low[i] += min(o[k] for o in g['options']) - whole
            high[i] += max(o[k] for o in g['options']) - whole
    order = steps(policies, on, found)
    name = {p['external_id']: p['name'] for p in policies}
    brief = [f"신청 순서: {' → '.join(s['name'] for s in order)}"]
    brief += [f"함께 받기 어려울 수 있음({'이름이 나옴' if c['kind'] == 'named' else '유사 사업 문구'}): 「{name[c['from']]}」의 글 “{c['quote'][:80]}” → 「{name[c['to']]}」" for c in found]
    brief += [f"함께 받을 수 있다고 적힘: 「{name[c['from']]}」의 글 “{c['quote'][:80]}” → 「{name[c['to']]}」" for c in compatible]
    if total['used']:
        brief.append(f"예상 지원 금액(모두 받을 때): 매달 {total['monthly_krw']:,}원 + 그 밖에 {total['other_krw']:,}원"
                     + (f". 묶음에서 한 조합만 받으면 매달 {low[0]:,}~{high[0]:,}원 + 그 밖에 {low[1]:,}~{high[1]:,}원(금액을 더하지 않는 정책은 0원으로 셈)" if grouped else ''))
    return {'as_of': on.isoformat(), 'order': [s['external_id'] for s in order], 'steps': order,
            'conflicts': found, 'compatible': compatible, 'groups': grouped,
            'amounts': {'all': {'monthly_krw': total['monthly_krw'], 'other_krw': total['other_krw']},
                        'one_per_group': {'monthly_krw': [low[0], high[0]], 'other_krw': [low[1], high[1]]},
                        'used': total['used'], 'loans': total['loans'], 'unsure': total['unsure']},
            'brief': brief, 'overlap_checked': False, 'notice': NOTICE}


# 다른 AI(오케스트레이터)가 이 계산을 도구로 부를 때 쓰는 선언. 실행은 POST /api/desk/workspaces/{wid}/planner 이다.
TOOL = {'name': 'plan_applications',
        'description': '사용자가 고른 청년 정책들(1~5개)에서 함께 받기 어려울 수 있는 조합, 신청 순서와 이유, 조합별 예상 지원 금액을 계산한다. '
                       '결과의 brief만 읽어도 답할 수 있다. 자격이나 중복 수혜를 확정하지 않으며 근거 문장(quote)을 함께 전해야 한다.',
        'parameters': {'type': 'object', 'required': ['external_ids'],
                       'properties': {'external_ids': {'type': 'array', 'items': {'type': 'string'}, 'description': '온통청년 정책 번호(plcyNo) 1~5개'}}}}
