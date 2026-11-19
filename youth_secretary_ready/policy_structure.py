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
# '기타' 코드. 정책에 이 코드가 있으면 코드표에 없는 다른 요건이 있다는 뜻이라, 내 값이 목록에 없어도 다르다고 단정하지 않는다.
OTHER = {'jobCd': '0013009', 'schoolCd': '0049009', 'plcyMajorCd': '0011008'}
UNRESTRICTED = {'jobCd': '0013010', 'schoolCd': '0049010', 'plcyMajorCd': '0011009', 'mrgSttsCd': '0055003', 'sbizCd': '0014010'}
PROFILE_FIELDS = {'job_code': 'jobCd', 'school_code': 'schoolCd', 'major_code': 'plcyMajorCd', 'marriage_code': 'mrgSttsCd'}
WINDOW = re.compile(r'(\d{8})\s*~\s*(\d{8})')
# 주관기관명이 지자체로 보이는지에 대한 참고 표시. 기관 소재지로 지원 지역을 정하지 않는다.
# 주관기관이 지자체인가. '경상북도 의성군 관광복지국'처럼 부서 이름으로 끝나는 기관도 읽는다(전국 등록 정책 26건이 이 모양이었다).
LOCAL_AGENCY = re.compile(r'특별시|광역시|특별자치시|특별자치도|통합특별시|[가-힣](도|시|군|구)(\s|$)')
CLOSED = ('ended', 'closed_code', 'closed_official')
# 제외·중복 수혜를 말하는 문장을 찾는 표지. 문장을 해석하지 않고 그대로 보존하는 데만 쓴다.
EXCLUDE = re.compile(r'제외|중복|불가|제한|유사')
# 참여 제한 칸에 '없음'이라고 적은 표기(실제 532문장 중 약 100개). 제한 문장으로 세지 않고 '없다고 적혀 있음'으로 따로 남긴다.
_NONE = re.compile(r'(해당\s*(사항)?\s*없음|제한\s*없음|(별도\s*)?(제출\s*)?서류\s*없음|없음|무관)\.?')
# 제한 문장이 무엇에 관한 것인지. 문장을 해석해 판정하지 않고, 사용자가 확인할 항목 이름으로만 쓴다.
LIMIT_KINDS = {'다른 지원과 중복': r'중복|유사|동일|타 ?사업|다른 ?사업|기 ?수혜|수혜 ?중|참여 ?중|참여자|참여한|수혜자|지원을 받고',
               '취업·사업자': r'재직|근로자|직장가입자|취업자|사업자|자영업|고용보험', '공무원·공공기관': r'공무원|공공기관|직업군인',
               '수급': r'수급자|생계급여|주거급여|실업급여|구직급여', '재학·휴학': r'재학|휴학|대학생|학생',
               '주택': r'주택|임차|임대', '체납·연체': r'체납|연체|신용', '거주': r'거주|주소|전입|주민등록',
               '소득·재산': r'소득|재산|자산', '국적': r'외국인|국적',
               # 아래는 분류가 안 되던 252문장을 보고 더한 종류
               '과거 참여·선정 이력': r'기존|이용자|수료|기선정|선정된|선정자|연임|\d{4}년도?.{0,20}(참여|이용|선정|지원받)|회 이상',
               '업종': r'업종', '채무·신용': r'채무|불량거래|신용유의|파산|회생', '활동 목적': r'종교|정당|선거|영리',
               '건강 상태': r'질환|중독|질병', '공고에서 확인': r'공고'}
# 서류 준비판의 칸: 공공기관이 발급 / 학교·회사·은행 등이 발행 / 내가 작성·보관. 동의로 대체되는지는 공고를 봐야 알 수 있어 나누지 않는다.
DOC_KIND = {**dict.fromkeys(('resident_register', 'resident_abstract', 'family', 'marriage', 'insurance_status', 'insurance_premium', 'income',
                             'business', 'employment_insurance', 'disability', 'recipient', 'military', 'tax'), '공공 발급'),
            **dict.fromkeys(('enrollment', 'graduation', 'employment_cert', 'transfer', 'bankbook', 'exam', 'receipt', 'license', 'medical'), '기관·학교·은행 발행'),
            **dict.fromkeys(('lease', 'labor_contract', 'id_card', 'application', 'consent', 'pledge', 'business_plan', 'self_intro', 'resume'), '직접 작성·보관')}
# 칸에 줄표나 '없음'만 적은 자리표시. 내용이 있는 것으로 세지 않는다(신청 방법 '해당없음' 45건, 서류 124건 등).
_PLACEHOLDER = re.compile(r'(-+|\.+|해당\s*(사항)?\s*없음|없음|제한\s*없음|무관)\.?')
# 서류 안내가 목록 없이 다른 곳을 가리키기만 하는 표현
_POINTER = re.compile(r'붙임|첨부|참조|참고|공고|공지|안내문|별도\s*(문의|안내)|에 따름|확인|상이|미정|서식')
# (키, 표시 이름, API 글에서 찾을 말, 발급·준비 방법)
DOCS = [
    ('resident_register', '주민등록등본', ('주민등록등본', '주민등록표등본', '주민등록표 등본', '주민등록 등본'), '정부24에서 발급'),
    ('resident_abstract', '주민등록초본', ('초본',), '정부24에서 발급'),
    ('family', '가족관계증명서', ('가족관계증명',), '대법원 전자가족관계등록시스템 또는 정부24'),
    ('insurance_status', '건강보험 자격득실확인서', ('자격득실',), '국민건강보험공단 누리집·앱'),
    ('insurance_premium', '건강보험료 납부확인서', ('건강보험료',), '국민건강보험공단 누리집·앱'),
    ('income', '소득금액증명', ('소득금액증명',), '홈택스'),
    ('business', '사업자등록 관련 서류', ('사업자등록',), '홈택스 · 등록증인지 사실증명인지는 공고 확인'),
    ('employment_insurance', '고용보험 관련 서류', ('고용보험',), '고용24 · 서류 종류는 공고 확인'),
    ('lease', '임대차계약서', ('임대차계약서', '임대차 계약서'), '보관 중인 계약서 사본 · 확정일자 필요 여부는 공고 확인'),
    ('transfer', '이체 확인 자료', ('이체',), '은행 앱·창구'),
    ('bankbook', '통장 사본', ('통장',), '은행 앱에서 저장'),
    ('id_card', '신분증 사본', ('신분증',), '본인 보관'),
    ('enrollment', '재학증명서', ('재학증명',), '학교 증명 발급 시스템'),
    ('graduation', '졸업증명서', ('졸업증명',), '학교 증명 발급 시스템'),
    ('exam', '응시 확인 자료', ('응시',), '시험 주관기관 누리집'),
    ('receipt', '결제 영수증', ('영수증',), '결제처·시험 주관기관 누리집'),
    ('application', '신청서', ('신청서', '지원서'), '공고의 서식을 내려받아 작성'),
    ('consent', '동의서', ('동의서',), '공고의 서식을 내려받아 작성'),
    ('marriage', '혼인관계증명서', ('혼인관계증명',), '대법원 전자가족관계등록시스템 또는 정부24'),
    ('employment_cert', '재직증명서', ('재직증명',), '재직 중인 회사에서 발급'),
    ('labor_contract', '근로계약서', ('근로계약서',), '보관 중인 계약서 사본'),
    ('business_plan', '계획서(사업·활동 계획 등)', ('계획서',), '공고의 서식을 내려받아 작성'),
    ('medical', '진단서·소견서', ('진단서', '소견서'), '진료받은 의료기관에서 발급'),
    ('self_intro', '자기소개서', ('자기소개서',), '공고의 서식을 내려받아 작성'),
    ('resume', '이력서', ('이력서',), '공고의 서식이 있는지 확인해 작성'),
    ('pledge', '서약서', ('서약서',), '공고의 서식을 내려받아 작성'),
    ('license', '자격증 사본', ('자격증 사본', '자격증사본', '합격증'), '자격 발급기관 누리집'),
    ('disability', '장애인 증명서', ('장애인증명', '장애인 증명', '복지카드'), '정부24 또는 주민센터'),
    ('recipient', '수급자·차상위 증명서', ('수급자증명', '수급자 증명', '차상위'), '정부24 또는 주민센터'),
    ('military', '병적증명서', ('병적증명', '전역증'), '정부24'),
    ('tax', '납세·체납 관련 증명', ('납세증명', '완납증명', '체납'), '홈택스·위택스 · 국세인지 지방세인지는 공고 확인'),
]
_SPLIT = re.compile(r'[\r\n]+|\s/\s|(?<=[.。])\s+')
_BULLET = re.compile(r'^(?:[\s\-–·•○□▪◦※*]+|[①-⑳]\s*|\d{1,2}[.)]\s+)+')
# 'N년(개월) 이상 (계속) (○○시에) 거주·주민등록·주소', '전입한 지 N개월 이상'. 재직 기간·창업 기간 같은 다른 기간은 읽지 않는다.
_RESIDENCE = re.compile(r'(\d{1,2})\s*(년|개월)\s*이상\s*(?:계속(?:하여|해서)?\s*|연속(?:하여)?\s*)?(?:[가-힣]{1,8}(?:시|군|구|도|市|내)에?\s*)?(?:거주|주민등록|주소)'
                        r'|전입한?\s*지\s*(\d{1,2})\s*(년|개월)\s*이상')
# 지역에 사는 기간이 아니라 고시원·시설에 머문 기간을 말하는 문장, 우대·유형별 조건인 문장은 거주 기간 조건으로 단정하지 않는다.
_NOT_RESIDENCE = re.compile(r'고시원|쪽방|반지하|시설|기숙사|환경')
_SOFT = re.compile(r'우대|가점|가산|유형|추가')
# 조건을 적은 글에서 코드 값과 견줄 말. 코드와 글이 어긋나면 걸러보기가 단정하지 않는다(screening.screen).
_AGE_RANGE = re.compile(r'(?:만\s*)?(\d{2})\s*세?\s*(?:이상)?\s*[~∼～\-]\s*(?:만\s*)?(\d{2})\s*세')
SAID = {'unemployed': r'미취업|구직 ?중|구직자|취업 ?준비', 'employed': r'재직 ?중|재직자|근로자|직장인',
        'short_work': r'단기 ?근로|주 ?\d+ ?시간 ?(?:이하|미만)|아르바이트|재직자[^.\n]{0,12}(?:가능|포함)',
        'income': r'중위 ?소득|소득[^.\n]{0,12}(?:이하|이내|미만)|차상위|수급자|저소득|건강보험료',
        'student': r'재학생|대학생|대학원생|휴학생|졸업 ?예정자|고등학생',
        'school_floor': r'(?:고졸|고등학교 ?졸업|대졸|전문대 ?졸업|학사|석사)[^.\n]{0,6}이상',
        'unmarried': r'미혼', 'child': r'보호자|부모|자녀|아동|영아|출생아|임산부|양육|아이', 'graduate': r'졸업 ?후|졸업생|졸업자',
        'early_close': r'예산 ?소진|조기 ?(?:마감|종료)|선착순 ?(?:접수|마감|모집)'}
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
# 수집본에는 옛 분류 이름(코드표 xlsx의 목록, 774건)과 누리집이 지금 쓰는 이름이 섞여 있다. 같은 분류로 묶어 보여 주려고 새 이름으로 맞춘다.
# 옛 이름 → 새 이름의 짝은 이름을 보고 맞춘 것이다(공식 대응표는 찾지 못함, data/api_field_notes.json).
CATEGORY_ALIAS = {'교육': '교육･직업훈련', '복지문화': '금융･복지･문화', '참여권리': '참여･기반',
                  '문화활동': '문화활동 및 생활지원', '온라인교육': '온·오프라인교육'}
LOAN = ('0042003', '0042007')   # 정책제공 방법코드: 직접대출, 대출보증
_AMOUNT = re.compile(r'((?:월|매월|연|연간|매년|1회|회당|1인당|총)\s*)?(최대\s*)?(\d[\d,]*(?:\.\d+)?)\s*(천|백)?\s*(만|억)\s*원')
# 실제 수집본에서 경로가 안 읽히던 609건을 보고 더한 표현: QR·구글폼·정부24 같은 온라인 창구, 읍면사무소, 학교·기관을 거치는 신청, '공고에 따라'.
CHANNELS = {'온라인': r'온라인|누리집|홈페이지|인터넷|사이트|http|앱\b|QR|큐알|구글 ?폼|링크|URL|포털|정부24|보조금24|복지로|고용24|워크넷|잡아바|플랫폼|접속|회원 ?가입',
            '방문': r'방문|내방|창구|주민센터|행정복지센터|읍\W?면|사무소|보건소', '우편': r'우편|등기',
            '이메일': r'이메일|e-?mail|메일', '전화': r'전화|유선',
            '학교·기관 경유': r'추천|학교 ?별|대학교?로|각 대학|소속 ?(학교|기관|대학)|학교를 통해', '공고에서 확인': r'공고'}
# 신청기간이 이 일수 이상이면 모집기간이 아니라 사업기간을 적은 것으로 본다. 팀 대조에서 API 1/1~12/31인데
# 실제 접수는 2주였던 사례(서울 청년월세, 청년인턴 직무캠프)가 이 형태였고, '접수 중' 237건 중 169건이 300일 이상이다.
LONG_WINDOW_DAYS = 300
_MEDIAN = re.compile(r'중위\s*소득')
# '학자금 지원 8구간 이하', '소득 8분위 이하'. 학자금 지원구간은 옛 소득분위를 이어받은 10단계 구간이다.
_BRACKET = re.compile(r'(\d{1,2})\s*(?:구간|분위)\s*(?:이하|이내)')
# '도시근로자 가구당 월평균 소득의 100% 이하', '월평균소득 140%이하'
_URBAN = re.compile(r'(?:도시근로자[^%\d]{0,25}|월평균\s?소득[^%\d]{0,14})(\d{2,3})\s*%\s*(이하|이내|미만|초과|이상)?')
_PERCENT = re.compile(r'(\d{2,3})\s*%\s*(이하|이내|미만|초과|이상)?')


def _number(value):
    text = str(value if value is not None else '').strip()
    return int(text) if text.isdigit() else None


def _text(payload, field):
    """글 칸의 내용. 자리표시(-, 해당없음)는 빈 값으로 본다."""
    text = str(payload.get(field) or '').strip()
    return '' if _PLACEHOLDER.fullmatch(text) else text


def _stated_none(payload, field):
    """칸에 '해당 없음'이라고 적혀 있는가. 빈칸과 줄표는 아니다."""
    return bool(_NONE.fullmatch(str(payload.get(field) or '').strip()))


def _day(value):
    text = re.sub(r'\D', '', str(value or ''))[:8]
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])).isoformat() if len(text) == 8 else None
    except ValueError:
        return None


def _url(value):
    return isinstance(value, str) and bool(re.match(r'https?://[^\s/]+', value.strip()))


def _codes(payload, field):
    raw = str(payload.get(api_field(field)) or '')
    codes = list(dict.fromkeys(x.strip() for x in raw.split(',') if x.strip()))
    known = CODEBOOK['groups'][field]['codes']
    return {'codes': codes, 'labels': [known[c]['label'] for c in codes if c in known],
            'unknown_codes': [c for c in codes if c not in known], 'missing': not codes,
            'unrestricted': UNRESTRICTED.get(field) in codes, 'other': OTHER.get(field) in codes}


def _conditions(payload):
    """대상·조건을 적는 두 칸(추가 조건, 지원 내용)의 글. 줄바꿈과 겹친 빈칸은 한 칸으로 줄인다."""
    return ' '.join(' '.join(str(payload.get(f) or '') for f in ('addAplyQlfcCndCn', 'plcySprtCn')).split())


def said(payload):
    """조건 글에 그 말이 나오면 앞뒤 글(근거로 보여 줄 인용), 없으면 None. 조기 마감 표현은 신청 방법·기타 칸까지 본다."""
    cond = _conditions(payload)
    wide = cond + ' ' + ' '.join(' '.join(str(payload.get(f) or '') for f in ('plcyAplyMthdCn', 'etcMttrCn', 'bizPrdEtcCn', 'plcyExplnCn')).split())
    out = {}
    for key, pattern in SAID.items():
        text = wide if key == 'early_close' else cond
        m = re.search(pattern, text)
        out[key] = text[max(0, m.start() - 20):m.end() + 20].strip() if m else None
    return out


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
            'no_limit': flag == 'Y', 'limit_flag_raw': flag, 'limit_flag_verified': False,
            # 조건 글에 적힌 나이 범위('만 19~39세'). 나이 칸과 다르면 걸러보기가 단정하지 않는다. 10세 미만으로 시작하는 범위(자녀 나이 등)는 뺀다.
            'text_ranges': sorted({(int(a), int(b)) for a, b in _AGE_RANGE.findall(_conditions(payload)) if 10 <= int(a) < int(b) <= 70})}


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
    text = ' '.join(' '.join(str(payload.get(f) or '') for f in ('addAplyQlfcCndCn', 'ptcpPrpTrgtCn', 'plcySprtCn', 'plcyExplnCn', 'etcMttrCn')).split())
    stays = [m for m in _RESIDENCE.finditer(text) if not _NOT_RESIDENCE.search(text[max(0, m.start() - 25):m.start()])]
    months = sorted({int(m.group(1) or m.group(3)) * (12 if (m.group(2) or m.group(4)) == '년' else 1) for m in stays})
    # 기간이 여러 가지이거나 우대·유형별 조건으로 적힌 글은 어느 기간이 내게 해당하는지 알 수 없다.
    unclear = len(months) > 1 or any(_SOFT.search(text[max(0, m.start() - 30):m.end() + 30]) for m in stays)
    # 시도의 시·군·구(구가 있는 시는 시 단위로 센다) 가운데 꼭 하나만 빠진 등록. 실제 수집본에서 충남 전체 정책 102건에 서산시만 빠져 있어
    # 등록 누락으로 보이지만 확인할 수 없으므로, 그 한 곳에 사는 사람에게 '달라요'로 단정하지 않는 데 쓴다.
    missing_one = {}
    for s in sido:
        units = {PARENT.get(c, c) for c in SIGUNGU if c[:2] == s}
        left = units - {PARENT.get(c, c) for c in valid if c in SIGUNGU}
        if len(units) >= 5 and len(left) == 1:
            missing_one[s] = left.pop()
    return {'codes': valid, 'invalid_codes': [c for c in codes if c not in valid], 'count': len(valid), 'missing_one': missing_one,
            'sido': sido, 'sido_names': [SIDO[s] for s in sido if s in SIDO], 'unknown_sido': unknown,
            'residence_min_months': months[0] if months else None, 'residence_unclear': unclear,
            'nationwide': bool(valid) and not unknown and set(sido) == set(SIDO),
            'full_sido': [s for s in sido if any(full <= set(valid) for full in SIDO_SETS.get(s, []))],
            'local_agency_hint': bool(LOCAL_AGENCY.search(str(payload.get('sprvsnInstCdNm') or '').strip()))}


# 소득 글이 어떤 방식의 기준인지(비교하지는 못해도 무엇을 확인할지 알려 준다)
INCOME_KINDS = {'기준 중위소득': r'중위', '도시근로자 월평균소득': r'도시근로자|월평균 ?소득', '건강보험료': r'건강보험료|건보료',
                '학자금 지원구간': r'지원구간|소득분위|소득구간|구간', '수급·차상위': r'수급|차상위|저소득', '금액 기준': r'만 ?원|억 ?원',
                '공고에서 확인': r'공고|문의|참조|참고'}


def income(payload):
    kind = _codes(payload, 'earnCndSeCd')
    # 연소득(0043002)의 금액은 만원 단위다(온통청년 누리집 표시 기준, data/api_field_notes.json). 최대 금액이 있을 때만 비교에 쓴다.
    top = _number(payload.get('earnMaxAmt'))
    annual = {'min': _number(payload.get('earnMinAmt')) or 0, 'max': top} if kind['codes'][:1] == ['0043002'] and top else None
    return {'code': kind['codes'][0] if kind['codes'] else '', 'labels': kind['labels'],
            'unknown_codes': kind['unknown_codes'], 'missing': kind['missing'],
            'min_raw': str(payload.get('earnMinAmt') or ''), 'max_raw': str(payload.get('earnMaxAmt') or ''),
            'text': str(payload.get('earnEtcCn') or '')[:300],
            'kinds': [k for k, pattern in INCOME_KINDS.items() if re.search(pattern, _text(payload, 'earnEtcCn'))],
            # 소득 칸에 구간이 하나만 적혀 있을 때만 비교에 쓴다(학부·대학원이 다른 구간, 긴급 예외가 함께 적힌 글은 쓰지 않는다).
            'bracket_max': (lambda found: int(found.pop()) if len(found) == 1 else None)(set(_BRACKET.findall(_text(payload, 'earnEtcCn')))),
            # 도시근로자 월평균소득 대비 %. 소득 칸과 추가 조건 칸에서 읽고, 방향이 없는 숫자는 '?'로 남긴다.
            'urban_bounds': _urban(' '.join(_text(payload, f) for f in ('earnEtcCn', 'addAplyQlfcCndCn'))),
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


def _urban(text):
    found = []
    for pct, word in _URBAN.findall(text):
        bound = {'pct': int(pct), 'kind': 'max' if word in ('이하', '이내', '미만') else 'min' if word else '?'}
        if bound not in found:
            found.append(bound)
    return found


def _median(text):
    """'중위소득' 뒤 40자 안의 'N% 이하/초과'를 모두 읽는다('중위소득 60% 초과 150% 이하'의 뒤쪽 상한을 놓치지 않게)."""
    found = []
    for mention in _MEDIAN.finditer(text):
        for pct, word in _PERCENT.findall(text[mention.end():mention.end() + 40]):
            bound = {'pct': int(pct), 'kind': 'max' if word in ('이하', '이내', '미만') else 'min' if word else '?'}
            if bound not in found:
                found.append(bound)
    return found


def summary(payload):
    """지원 내용 글의 첫 줄. 목록 카드에 한 줄로 보여 준다. 글머리표와 자리표시는 뺀다."""
    for raw in _SPLIT.split(_text(payload, 'plcySprtCn')):
        line = _BULLET.sub('', raw).strip().lstrip('ㆍ❍▶■◆▣▷◇◈►☞✔✓ㅇ').strip()   # 수집 글에 자주 나오는 글머리표
        if len(line) >= 4:
            return line[:60]
    return ''


# 응시료 지원 글에 적힌 대상 시험 종류. 넓은 말만 읽는다(토익만 적힌 글을 '어학 전체'로 넓히지 않는다).
# 국가자격은 국가기술자격과 국가전문자격을 함께 이르는 말이다(자격기본법).
EXAM_KINDS = {'국가기술자격': r'국가\s?기술\s?자격|국가\s?자격', '어학': r'어학|외국어', '한국사': r'한국사'}
# 무주택 문장에 이 낱말이 함께 있으면 '자가라서 달라요'로 단정하지 않는다(주택 구입 지원, 우대 조건 등).
_HOME_HEDGE = re.compile(r'우대|우선|가능|예외|무관|관계\s?없|구입|구매|매입|분양|취득|생애')
_APART = re.compile(r'부모[^.]{0,8}(별도|따로)')


def exam(payload):
    """응시료 지원인가(이름·설명·지원 내용에 '응시료'), 글에 적힌 시험 종류, 시험 이름을 찾아볼 글(띄어쓰기 없이 소문자)."""
    core = ' '.join(_text(payload, f) for f in ('plcyNm', 'plcyExplnCn', 'plcySprtCn'))
    if '응시료' not in core:
        return {'fee': False, 'kinds': [], 'text': ''}
    full = core + ' ' + _text(payload, 'addAplyQlfcCndCn')
    return {'fee': True, 'kinds': [k for k, pattern in EXAM_KINDS.items() if re.search(pattern, full)], 'text': ''.join(full.split()).lower()}


def housing(payload):
    """조건·지원 내용·참여 제한 글의 무주택 문장과 '부모와 따로 거주' 문장. 없으면 None(주거 요건이 없다는 뜻은 아니다)."""
    lines = [_BULLET.sub('', raw).strip()[:200] for f in ('addAplyQlfcCndCn', 'plcySprtCn', 'ptcpPrpTrgtCn') for raw in _SPLIT.split(str(payload.get(f) or ''))]
    no_home = next((s for s in lines if '무주택' in s), None)
    return {'no_home': no_home, 'apart': next((s for s in lines if _APART.search(s)), None),
            'hedged': bool(no_home and _HOME_HEDGE.search(str(payload.get('plcyNm') or '') + ' ' + no_home))}


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


def _label(payload, field):
    """코드 하나짜리 칸의 코드와 이름. 수집되지 않았거나 코드표에 없으면 이름은 빈 값이다."""
    code = str(payload.get(field) or '').strip()
    return {'code': code, 'label': CODEBOOK['groups'][field]['codes'].get(code, {}).get('label', '')}


# 금액 바로 앞에 이런 말이 있으면 개인이 받는 지원금이 아닐 수 있다(대출 한도, 보증금 조건, 사업 예산, 팀·기업 단위 금액).
_NOT_PERSONAL = re.compile(r'대출|융자|보증금|보증 ?공급|예산|사업비|자금|팀당|기업당|업체당|개소당|기관당|학교당|개사|개소')


def amounts(payload):
    """지원 내용 글에 적힌 금액 표현(앞 3개). 지원금인지 대출 한도인지는 구분하지 않으므로 합산하지 않는다."""
    found = []
    text = str(payload.get('plcySprtCn') or '')
    for m in _AMOUNT.finditer(text):
        period, cap, number, scale, unit = m.groups()
        krw = float(number.replace(',', '')) * {'천': 1000, '백': 100, None: 1}[scale] * (10 ** 8 if unit == '억' else 10 ** 4)
        item = {'text': ' '.join(m.group(0).split()), 'krw': int(krw), 'period': (period or '').strip() or None, 'max': bool(cap) or (period or '').strip() == '최대',
                # 앞 14자 안에 대출·보증금·예산·팀당 같은 말이 있는가. 예상 지원 금액을 더할 때 이런 표현은 고르지 않는다.
                'other': bool(_NOT_PERSONAL.search(text[max(0, m.start() - 14):m.start()]))}
        if item['text'] not in [x['text'] for x in found]:
            found.append(item)
    return found[:3]


def structure(payload):
    return {'external_id': payload.get('plcyNo', ''), 'name': payload.get('plcyNm', ''),
            'agency': payload.get('sprvsnInstCdNm', ''), 'category_raw': payload.get('lclsfNm', ''),
            'category': CATEGORY_ALIAS.get(str(payload.get('lclsfNm') or '').strip(), str(payload.get('lclsfNm') or '').strip()),
            'age': age(payload), 'application': application(payload), 'region': region(payload),
            'income': income(payload), 'exclusions': exclusions(payload), 'targets': targets(payload), 'amounts': amounts(payload), 'summary': summary(payload),
            'exam': exam(payload), 'housing': housing(payload), 'said': said(payload),
            'special': _codes(payload, 'sbizCd'), 'provision': provision(payload),
            # 정책 승인 상태(수집본은 모두 '승인')와 제공 기관 구분(중앙부처·지자체)
            'approval': _label(payload, 'plcyAprvSttsCd'), 'provider_group': _label(payload, 'pvsnInstGroupCd'),
            'subcategory': CATEGORY_ALIAS.get(str(payload.get('mclsfNm') or '').strip(), str(payload.get('mclsfNm') or '').strip()), 'operator': str(payload.get('operInstCdNm') or '').strip(),
            'scale': scale(payload), 'project': project(payload, application(payload)), 'documents': documents(payload),
            'selection': selection(payload), 'updated': updated(payload), 'notes': _text(payload, 'etcMttrCn')[:300],
            'keywords': [k.strip() for k in str(payload.get('plcyKywdNm') or '').split(',') if k.strip()],
            **{key: _codes(payload, field) for key, field in
               [('job', 'jobCd'), ('school', 'schoolCd'), ('major', 'plcyMajorCd'), ('marriage', 'mrgSttsCd')]},
            'access': {'channels': [k for k, pattern in CHANNELS.items() if re.search(pattern, str(payload.get('plcyAplyMthdCn') or ''), re.I)],
                       'has_method': bool(_text(payload, 'plcyAplyMthdCn')), 'method_stated_none': _stated_none(payload, 'plcyAplyMthdCn'),
                       'has_apply_url': _url(payload.get('aplyUrlAddr')),
                       'has_reference_url': _url(payload.get('refUrlAddr1')) or _url(payload.get('refUrlAddr2'))},
            'basis': 'ontong_api', 'verified_against_notice': False}


def scale(payload):
    """지원 규모와 선착순. 누리집 표시 기준으로 규모 제한 표기 Y는 '제한없음', 단위는 명이다(data/api_field_notes.json).
    누리집은 규모에 제한이 있을 때만 선착순 표기를 읽는다. 0명은 '0명 선발'이 아니라 미기재다."""
    count, free = _number(payload.get('sprtSclCnt')) or None, str(payload.get('sprtSclLmtYn') or '') == 'Y'
    arrival = str(payload.get('sprtArvlSeqYn') or '')
    return {'count': count, 'no_limit': free, 'first_come': None if free or not arrival else arrival == 'Y',
            'limit_flag_raw': str(payload.get('sprtSclLmtYn') or ''), 'arrival_flag_raw': arrival}


def project(payload, app):
    """사업 운영 기간. 신청기간과 다른 칸이지만 같은 날짜가 그대로 들어간 정책이 많다(same_as_application)."""
    code = str(payload.get('bizPrdSeCd') or '')
    start, end = _day(payload.get('bizPrdBgngYmd')), _day(payload.get('bizPrdEndYmd'))
    return {'code': code, 'kind': {'0056001': 'fixed', '0056002': 'other'}.get(code, 'unknown'), 'start': start, 'end': end,
            'text': _text(payload, 'bizPrdEtcCn')[:200],
            'same_as_application': bool(start and end) and app['windows'] == [{'start': start, 'end': end}]}


def documents(payload):
    """제출서류 안내 글에서 이름이 그대로 나온 서류. 글이 비었으면 '서류 불필요'가 아니라 '안내 없음'이다."""
    text = _text(payload, 'sbmsnDcmntCn')
    known = [key for key, _, needles, _ in DOCS if any(n in text for n in needles)]
    return {'has_text': bool(text), 'stated_none': _stated_none(payload, 'sbmsnDcmntCn'), 'known': known,
            # 목록 없이 '붙임파일 확인'처럼 다른 곳만 가리키는 안내
            'pointer_only': bool(text) and not known and bool(_POINTER.search(text))}


def selection(payload):
    """심사·발표 안내 글과 거기 나오는 선발 방식 낱말."""
    text = _text(payload, 'srngMthdCn')
    return {'text': text[:300], 'methods': [k for k in ('선착순', '추첨', '서류', '면접', '심사') if k in text]}


def updated(payload):
    """API 등록·수정 시각. 2026-01-01 00:00:00은 725건에 똑같이 찍힌 일괄 처리 시각이라 실제 수정일로 보지 않는다."""
    stamp = str(payload.get('lastMdfcnDt') or '')
    return {'registered': _day(payload.get('frstRegDt')), 'modified': _day(stamp), 'modified_is_bulk': stamp.startswith('2026-01-01 00:00:00')}


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
