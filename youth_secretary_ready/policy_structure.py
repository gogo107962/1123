"""온통청년 API 필드를 비교 가능한 구조로 정리한다. 개인 자격을 판정하지 않는다.

모든 값은 API 기재값이다. 팀의 원문 대조(2026-11-17)에서 API와 공고가 다른 사례가
확인됐으므로, 이 구조는 걸러보기와 '원문에서 확인할 것' 찾기에만 쓴다.
빈값·0은 '제한 없음'으로 바꾸지 않고 '기재 없음'으로 남긴다.
"""
import json
import re
from datetime import date
from pathlib import Path
from policy_codes import CODEBOOK, api_field

SIDO = json.loads((Path(__file__).parent / 'data/region_sido.json').read_text(encoding='utf-8'))['sido']
# 전국 대상 정책이 시도별로 넣는 시군구 코드 묶음(tools/build_region_sets.py가 수집본에서 만든 기준표).
# 정책의 코드가 이 묶음을 모두 포함하면 '그 시도 전체 대상'으로 본다. 파일이 없으면 이 판단을 하지 않는다.
_SETS = Path(__file__).parent / 'data/region_sido_sets.json'
SIDO_SETS = ({k: [set(x['codes']) for x in v] for k, v in json.loads(_SETS.read_text(encoding='utf-8'))['sets'].items()}
             if _SETS.exists() else {})
# 시군구 코드 → 이름. 행정표준코드관리시스템에서 확인한 표(region_sigungu_official.json)를 쓰고,
# 그 파일이 없을 때만 수집본에서 유도한 표(tools/build_region_names.py)를 쓴다. 둘 다 없으면 시군구를 고를 수 없다.
_NAMES = next((p for p in (Path(__file__).parent / 'data' / n for n in ('region_sigungu_official.json', 'region_sigungu.json')) if p.exists()), None)
_TABLE = json.loads(_NAMES.read_text(encoding='utf-8'))['sigungu'] if _NAMES else {}
# 폐지된 코드(이름과 함께). 사용자에게 고르게 하지 않고, 이 코드로 등록된 정책은 지금의 시군구와 맞다/다르다를 정하지 않는다.
ABOLISHED = {k: v['name'] for k, v in _TABLE.items() if v.get('abolished')}
SIGUNGU = {k: v['name'] for k, v in _TABLE.items() if k not in ABOLISHED}
# 구가 있는 시는 시 코드와 구 코드가 따로 있다(수원시 41110, 수원시 장안구 41111). 구 코드 → 시 코드.
# 번호 앞자리만으로 묶으면 영동군(43740)과 증평군(43745)이 묶이므로 이름으로 잇는다.
PARENT = {k: p for k, n in SIGUNGU.items() if ' ' in n
          for p, city in SIGUNGU.items() if p[:2] == k[:2] and city == n.split()[0]}
# 시군구 이름이 빠짐없이 있는 시도. 되물을 때는 이런 시도만 고르게 한다(일부만 있는 목록을 내밀지 않는다).
SIGUNGU_COMPLETE = {s for s, sets in SIDO_SETS.items() if sets and all(c in SIGUNGU for c in max(sets, key=len))}
# 각 분류에서 '제한없음'을 뜻하는 코드 (코드표 원문 기준)
UNRESTRICTED = {'jobCd': '0013010', 'schoolCd': '0049010', 'plcyMajorCd': '0011009', 'mrgSttsCd': '0055003', 'sbizCd': '0014010'}
PROFILE_FIELDS = {'job_code': 'jobCd', 'school_code': 'schoolCd', 'major_code': 'plcyMajorCd', 'marriage_code': 'mrgSttsCd'}
WINDOW = re.compile(r'(\d{8})\s*~\s*(\d{8})')
# 주관기관명이 지자체로 보이는지에 대한 참고 표시. 기관 소재지로 지원 지역을 정하지 않는다.
LOCAL_AGENCY = re.compile(r'특별시|광역시|특별자치시|특별자치도|통합특별시|[가-힣](도|시|군|구)$')
CLOSED = ('ended', 'closed_code', 'closed_official')
# 제외·중복 수혜를 말하는 문장을 찾는 표지. 문장을 해석하지 않고 그대로 보존하는 데만 쓴다.
EXCLUDE = re.compile(r'제외|중복|불가|제한|유사')
# 참여 제한 칸에 '없음'이라고 적은 표기(실제 532문장 중 약 100개). 제한 문장으로 세지 않고 '없다고 적혀 있음'으로 따로 남긴다.
_NONE = re.compile(r'(해당\s*(사항)?\s*없음|제한\s*없음|없음|무관)\.?')
# 제한 문장이 무엇에 관한 것인지. 문장을 해석해 판정하지 않고, 사용자가 확인할 항목 이름으로만 쓴다.
LIMIT_KINDS = {'다른 지원과 중복': r'중복|유사|동일|타 ?사업|다른 ?사업|기 ?수혜|수혜 ?중|참여 ?중|참여자|참여한|수혜자|지원을 받고',
               '취업·사업자': r'재직|근로자|직장가입자|취업자|사업자|자영업|고용보험', '공무원·공공기관': r'공무원|공공기관|직업군인',
               '수급': r'수급자|생계급여|주거급여|실업급여|구직급여', '재학·휴학': r'재학|휴학|대학생|학생',
               '주택': r'주택|임차|임대', '체납·연체': r'체납|연체|신용', '거주': r'거주|주소|전입|주민등록',
               '소득·재산': r'소득|재산|자산', '국적': r'외국인|국적'}
_SPLIT = re.compile(r'[\r\n]+|\s/\s|(?<=[.。])\s+')
_BULLET = re.compile(r'^(?:[\s\-–·•○□▪◦※*]+|[①-⑳]\s*|\d{1,2}[.)]\s+)+')
_RESIDENCE = re.compile(r'(\d{1,2})\s*(년|개월)\s*이상\s*(?:계속\s*|연속\s*|연속하여\s*)?(?:거주|주민등록)')
# 정렬 순서: 접수 중(마감 빠른 순) → 시작 전 → 상시 → 기간 미기재 → 마감
RANK = {'open': 0, 'upcoming': 1, 'rolling': 2, 'unknown': 3, 'ended': 4, 'closed_code': 4, 'closed_official': 4}
LABEL = {'rolling': '상시(API)', 'unknown': '기간 확인 필요', 'ended': 'API 기간 지남',
         'closed_code': '마감(API)', 'closed_official': '공식 공고 종료'}
# 정책 이름에 드러난 특정 대상. 이름에 있을 때만 '그 집단을 위한 정책'으로 본다(설명 글의 낱말은 우연히 걸리는 경우가 많다).
TARGETS = {'여성': r'여성', '대학(원)생': r'대학생|대학원생|재학생', '군 복무·전역': r'장병|군인|군 ?복무|전역|제대군인|간부', '신혼·예비부부': r'신혼|예비부부',
           '한부모·양육': r'한부모|양육|육아|임산부|다자녀', '장애': r'장애', '자립준비청년': r'자립준비|보호종료|시설 ?퇴소',
           '농어업인': r'농업|영농|귀농|어업인|농촌', '예술인': r'예술인|예술가|예술활동|청년예술', '창업(예비 포함)': r'창업|스타트업',
           '중소기업 재직': r'중소기업|중견기업', '고립·은둔': r'고립|은둔', '기초생활수급·차상위': r'수급자|차상위|저소득'}
# 정책특화 요건코드(sbizCd) → 내 정보의 '해당하는 것'. 지역인재·기타는 고를 수 없는 항목이라 이름 그대로 남긴다.
SPECIAL = {'0014001': '중소기업 재직', '0014002': '여성', '0014003': '기초생활수급·차상위', '0014004': '한부모·양육',
           '0014005': '장애', '0014006': '농어업인', '0014007': '군 복무·전역', '0014008': '지역인재', '0014009': '기타 특화 요건'}
LOAN = ('0042003', '0042007')   # 정책제공 방법코드: 직접대출, 대출보증
_AMOUNT = re.compile(r'((?:월|매월|연|연간|매년|1회|회당|1인당|총)\s*)?(최대\s*)?(\d[\d,]*(?:\.\d+)?)\s*(천|백)?\s*(만|억)\s*원')
CHANNELS = {'온라인': r'온라인|누리집|홈페이지|인터넷|사이트|http|앱\b', '방문': r'방문|내방|창구|주민센터|행정복지센터', '우편': r'우편|등기',
            '이메일': r'이메일|e-?mail|메일', '전화': r'전화|유선'}
# 신청기간이 이 일수 이상이면 모집기간이 아니라 사업기간을 적은 것으로 본다. 팀 대조에서 API 1/1~12/31인데
# 실제 접수는 2주였던 사례(서울 청년월세, 청년인턴 직무캠프)가 이 형태였고, '접수 중' 237건 중 169건이 300일 이상이다.
LONG_WINDOW_DAYS = 300
_MEDIAN = re.compile(r'중위\s*소득')
_PERCENT = re.compile(r'(\d{2,3})\s*%\s*(이하|이내|미만|초과|이상)?')


def _number(value):
    text = str(value if value is not None else '').strip()
    return int(text) if text.isdigit() else None


def _url(value):
    return isinstance(value, str) and bool(re.match(r'https?://[^\s/]+', value.strip()))


def _codes(payload, field):
    raw = str(payload.get(api_field(field)) or '')
    codes = list(dict.fromkeys(x.strip() for x in raw.split(',') if x.strip()))
    known = CODEBOOK['groups'][field]['codes']
    return {'codes': codes, 'labels': [known[c]['label'] for c in codes if c in known],
            'unknown_codes': [c for c in codes if c not in known], 'missing': not codes,
            'unrestricted': UNRESTRICTED.get(field) in codes}


def age(payload):
    low, high = _number(payload.get('sprtTrgtMinAge')) or None, _number(payload.get('sprtTrgtMaxAge')) or None
    if low and high:
        kind = 'range' if low <= high else 'invalid'
    else:
        kind = 'min_only' if low else 'max_only' if high else 'unspecified'
    flag = str(payload.get('sprtTrgtAgeLmtYn') or '')
    return {'min': low, 'max': high, 'kind': kind,
            # 명세에는 Y/N의 뜻이 없지만 온통청년 누리집은 Y를 '제한없음'으로 보여 준다(data/api_field_notes.json).
            # 실제 수집본에서 범위가 빈 1,120건 중 1,046건이 Y다. 범위와 Y가 함께 적힌 741건은 서로 어긋난 값이다.
            'no_limit': flag == 'Y', 'limit_flag_raw': flag, 'limit_flag_verified': False}


def application(payload):
    code = str(payload.get('aplyPrdSeCd') or '')
    windows = []
    for start, end in WINDOW.findall(str(payload.get('aplyYmd') or '')):
        try:
            first = date(int(start[:4]), int(start[4:6]), int(start[6:]))
            last = date(int(end[:4]), int(end[4:6]), int(end[6:]))
        except ValueError:
            continue
        if first <= last:
            windows.append({'start': first.isoformat(), 'end': last.isoformat()})
    kind = {'0057001': 'fixed', '0057002': 'rolling', '0057003': 'closed'}.get(code, 'unknown')
    return {'code': code, 'kind': kind, 'windows': windows, 'raw': str(payload.get('aplyYmd') or ''),
            'long_window': bool(windows) and all((date.fromisoformat(w['end']) - date.fromisoformat(w['start'])).days >= LONG_WINDOW_DAYS for w in windows)}


def period_status(app, on, check=None):
    """API 날짜만으로 본 상태. 시각·조기 마감·회차는 알 수 없으므로 'open'도 접수 보장이 아니다."""
    if check and check.get('official_status') == 'closed' and not check.get('api_changed_since_check'):
        return 'closed_official'
    if app['kind'] == 'closed':
        return 'closed_code'
    if app['kind'] == 'rolling':
        return 'rolling'
    if app['kind'] == 'fixed' and app['windows']:
        day = on.isoformat()
        if any(w['start'] <= day <= w['end'] for w in app['windows']):
            return 'open'
        return 'upcoming' if any(w['start'] > day for w in app['windows']) else 'ended'
    return 'unknown'


def timing(app, status, on):
    """화면 표시와 정렬에 쓸 날짜. API 기재값만 쓰고 다음 모집일을 만들지 않는다."""
    day = on.isoformat()
    if status == 'open':
        end = min(w['end'] for w in app['windows'] if w['start'] <= day <= w['end'])
        if app['long_window']:   # 1년 가까운 기간의 끝날을 '마감 임박'처럼 보여 주지 않는다
            return end, '연중 표기(API) · 모집 회차 확인'
        return end, f'D-{(date.fromisoformat(end) - on).days} (API 마감일)'
    if status == 'upcoming':
        start = min(w['start'] for w in app['windows'] if w['start'] > day)
        return start, f'{start} 시작(API)'
    return None, LABEL[status]


def region(payload):
    codes = list(dict.fromkeys(c.strip() for c in str(payload.get('zipCd') or '').split(',') if c.strip()))
    valid = [c for c in codes if re.fullmatch(r'\d{5}', c)]
    sido = sorted({c[:2] for c in valid})
    unknown = [s for s in sido if s not in SIDO]
    # 글에 적힌 '1년 이상 거주' 같은 조건. 전입일을 모르므로 지역이 맞아도 확인 필요로 내리는 데 쓴다.
    stay = _RESIDENCE.search(' '.join(str(payload.get(f) or '') for f in ('addAplyQlfcCndCn', 'ptcpPrpTrgtCn', 'plcySprtCn', 'plcyExplnCn', 'etcMttrCn')))
    return {'codes': valid, 'invalid_codes': [c for c in codes if c not in valid], 'count': len(valid),
            'sido': sido, 'sido_names': [SIDO[s] for s in sido if s in SIDO], 'unknown_sido': unknown,
            'residence_min_months': int(stay.group(1)) * (12 if stay.group(2) == '년' else 1) if stay else None,
            'nationwide': bool(valid) and not unknown and set(sido) == set(SIDO),
            'full_sido': [s for s in sido if any(full <= set(valid) for full in SIDO_SETS.get(s, []))],
            'local_agency_hint': bool(LOCAL_AGENCY.search(str(payload.get('sprvsnInstCdNm') or '').strip()))}


def income(payload):
    kind = _codes(payload, 'earnCndSeCd')
    # 연소득(0043002)의 금액은 만원 단위다(온통청년 누리집 표시 기준, data/api_field_notes.json). 최대 금액이 있을 때만 비교에 쓴다.
    top = _number(payload.get('earnMaxAmt'))
    annual = {'min': _number(payload.get('earnMinAmt')) or 0, 'max': top} if kind['codes'][:1] == ['0043002'] and top else None
    return {'code': kind['codes'][0] if kind['codes'] else '', 'labels': kind['labels'],
            'unknown_codes': kind['unknown_codes'], 'missing': kind['missing'],
            'min_raw': str(payload.get('earnMinAmt') or ''), 'max_raw': str(payload.get('earnMaxAmt') or ''),
            'text': str(payload.get('earnEtcCn') or '')[:300],
            # 소득 글에 적힌 '중위소득 N%'. 가구원 수·산정 방식(소득금액증명/건강보험료)을 몰라 비교에는 쓰지 않는다.
            'median_pct': sorted({b['pct'] for b in _median(str(payload.get('earnEtcCn') or ''))}),
            # 방향까지 읽힌 기준만 비교에 쓴다. 방향이 없는 숫자가 하나라도 섞이면('?') 비교하지 않는다.
            'median_bounds': _median(str(payload.get('earnEtcCn') or '')),
            # 개인/가구·산정연도 근거는 없다. 연소득 구분이 아니면 숫자를 비교하지 않는다.
            'annual': annual, 'unit': '만원/년' if annual else None, 'comparable': bool(annual)}


def exclusions(payload):
    """참여 제한 안내(전체)와 추가 조건 중 제외·중복 문구. 개인에게 해당하는지는 판단하지 않는다."""
    found, none = [], False
    for field, marked_only in (('ptcpPrpTrgtCn', False), ('addAplyQlfcCndCn', True)):
        for raw in _SPLIT.split(str(payload.get(field) or '')):
            line = _BULLET.sub('', raw).strip()
            if not marked_only and _NONE.fullmatch(line):
                none = True
            elif len(line) >= 4 and (not marked_only or EXCLUDE.search(line)) and line[:200] not in found:
                found.append(line[:200])
    return {'sentences': found[:8], 'count': len(found),
            # '해당 없음'만 적혀 있고 다른 제한 문장이 없을 때만 참. 빈칸은 여기에 들지 않는다.
            'explicit_none': none and not found,
            'kinds': [k for k, pattern in LIMIT_KINDS.items() if any(re.search(pattern, s) for s in found[:8])]}


def _median(text):
    """'중위소득' 뒤 40자 안의 'N% 이하/초과'를 모두 읽는다('중위소득 60% 초과 150% 이하'의 뒤쪽 상한을 놓치지 않게)."""
    found = []
    for mention in _MEDIAN.finditer(text):
        for pct, word in _PERCENT.findall(text[mention.end():mention.end() + 40]):
            bound = {'pct': int(pct), 'kind': 'max' if word in ('이하', '이내', '미만') else 'min' if word else '?'}
            if bound not in found:
                found.append(bound)
    return found


def targets(payload):
    """정책 이름에 드러난 특정 대상 집단과 정책특화 요건코드. 없으면 빈 목록(누구나 대상이라는 뜻은 아니다)."""
    named = [group for group, pattern in TARGETS.items() if re.search(pattern, str(payload.get('plcyNm') or ''))]
    coded = [SPECIAL[c] for c in _codes(payload, 'sbizCd')['codes'] if c in SPECIAL]
    return list(dict.fromkeys(named + coded))


def provision(payload):
    """정책제공 방법(보조금·바우처·대출 등). 금액 표현이 지원금인지 대출 한도인지 가리는 데 쓴다. 수집되지 않았으면 loan은 None."""
    code = str(payload.get('plcyPvsnMthdCd') or '').strip()
    known = CODEBOOK['groups']['plcyPvsnMthdCd']['codes']
    return {'code': code, 'label': known[code]['label'] if code in known else '', 'loan': code in LOAN if code in known else None}


def amounts(payload):
    """지원 내용 글에 적힌 금액 표현(앞 3개). 지원금인지 대출 한도인지는 구분하지 않으므로 합산하지 않는다."""
    found = []
    for m in _AMOUNT.finditer(str(payload.get('plcySprtCn') or '')):
        period, cap, number, scale, unit = m.groups()
        krw = float(number.replace(',', '')) * {'천': 1000, '백': 100, None: 1}[scale] * (10 ** 8 if unit == '억' else 10 ** 4)
        item = {'text': ' '.join(m.group(0).split()), 'krw': int(krw), 'period': (period or '').strip() or None, 'max': bool(cap) or (period or '').strip() == '최대'}
        if item['text'] not in [x['text'] for x in found]:
            found.append(item)
    return found[:3]


def structure(payload):
    return {'external_id': payload.get('plcyNo', ''), 'name': payload.get('plcyNm', ''),
            'agency': payload.get('sprvsnInstCdNm', ''), 'category': payload.get('lclsfNm', ''),
            'age': age(payload), 'application': application(payload), 'region': region(payload),
            'income': income(payload), 'exclusions': exclusions(payload), 'targets': targets(payload), 'amounts': amounts(payload),
            'special': _codes(payload, 'sbizCd'), 'provision': provision(payload),
            'subcategory': str(payload.get('mclsfNm') or ''),
            'keywords': [k.strip() for k in str(payload.get('plcyKywdNm') or '').split(',') if k.strip()],
            **{key: _codes(payload, field) for key, field in
               [('job', 'jobCd'), ('school', 'schoolCd'), ('major', 'plcyMajorCd'), ('marriage', 'mrgSttsCd')]},
            'access': {'channels': [k for k, pattern in CHANNELS.items() if re.search(pattern, str(payload.get('plcyAplyMthdCn') or ''), re.I)],
                       'has_method': bool(str(payload.get('plcyAplyMthdCn') or '').strip()),
                       'has_apply_url': _url(payload.get('aplyUrlAddr')),
                       'has_reference_url': _url(payload.get('refUrlAddr1')) or _url(payload.get('refUrlAddr2'))},
            'basis': 'ontong_api', 'verified_against_notice': False}


def tier(structured, status, reviewed=False):
    """표시 갈래. reviewed=사람 검수로 승인된 정책, screenable=API 값으로 걸러볼 수 있음, link_only=원문 링크만."""
    if reviewed:
        return {'tier': 'reviewed', 'reasons': []}
    reasons = []
    if status in CLOSED:
        reasons.append('closed')
    # 신청 방법이 비어 있어도 공고로 갈 참고 주소가 있으면 조건은 비교한다(신청 방법은 '확인 필요'로 남긴다).
    if not (structured['access']['has_method'] or structured['access']['has_apply_url'] or structured['access']['has_reference_url']):
        reasons.append('no_application_route')
    if not structured['region']['codes']:
        reasons.append('no_region_code')
    return {'tier': 'link_only' if reasons else 'screenable', 'reasons': reasons}
