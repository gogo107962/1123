"""API 기재값으로 하는 1차 걸러보기. 자격 판정이 아니며 DB에 아무것도 쓰지 않는다.

결과는 기준마다 match / mismatch / unknown 세 값이다. 프로필이 주지 않은 기준은 skipped.
- mismatch는 'API 값과 맞지 않음'이지 '자격 없음'이 아니다(API와 공고가 다른 사례가 확인됨).
- 빈값, 상시, 소득 금액, 시군구 미지정은 unknown으로 남긴다.
사람 검수를 통과한 정책의 실제 판정은 engine.py가 맡는다.
"""
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
import db
from db import connect
from policy_codes import CODEBOOK
from policy_structure import ABOLISHED, CLOSED, PARENT, PROFILE_FIELDS, RANK, SIDO, TARGETS, period_status, structure, tier, timing

NOTICE = 'API에 적힌 값으로 걸러본 결과입니다. 자격 판정이 아니며, 신청 전 공고 원문을 확인해야 합니다.'
ORDER = {'api_match': 0, 'needs_check': 1, 'api_mismatch': 2}
# 내 정보에서 고를 수 있는 '받고 있는 지원'과, 정책의 참여 제한 문장에서 그 지원을 찾을 낱말.
# 실제 수집본의 참여 제한 문장에 이름이 나오는 지원만 넣었다(data/DATA_AUDIT.md 점검 때 센 것).
BENEFITS = {'국민취업지원제도': ('국민취업지원제도', '국취제'), '청년수당': ('청년수당',),
            '실업급여(구직급여)': ('실업급여', '구직급여'), '기초생활수급(생계·주거급여)': ('기초생활수급', '생계급여', '주거급여'),
            '청년도약계좌': ('청년도약계좌',), '청년내일채움공제': ('내일채움공제',)}


# 참여 제한 문장이 '재직자·사업자는 제외'일 때 내 취업 상태와 견줄 낱말. 부정·예외 표현이 섞인 문장은 견주지 않는다.
JOB_LIMIT = {'0013001': ('재직자', r'재직자|직장가입자|재직 ?중|취업자'), '0013002': ('자영업자', r'개인사업자|자영업자|사업자등록')}
_AGE_SAID = re.compile(r'\d{1,2}\s*세|년생|출생')
# 공식 페이지 인용에서 '2026. 3. 25.(수) ~ 11. 30.(월)' 꼴의 기간 하나를 읽는다. 끝날의 연도가 없으면 시작 연도를 쓴다.
_RANGE = re.compile(r"(?:20(\d{2})|[’'](\d{2}))\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})\.?"
                    r"\s*(?:\([^)]{1,4}\))?\s*(?:\d{1,2}(?::\d{2}|시))?\s*[~∼～]\s*"
                    r"(?:(?:20(\d{2})|[’'](\d{2}))\s*[.\-]\s*)?(\d{1,2})\s*[.\-]\s*(\d{1,2})")


_RANGE_KO = re.compile(r'(_d{1,2})월_s*(_d{1,2})일[^~∼～]{0,20}[~∼～]_s*(_d{1,2})월_s*(_d{1,2})일'.replace('_', chr(92)))


def official_window(quote, year=None):
    """공식 페이지 문장의 신청 기간(시작, 끝). 기간이 하나만 분명히 읽힐 때만 돌려준다.
    '예산 소진 시', '선착순', '상시', '마감'이 붙은 문장은 끝날을 믿을 수 없어 읽지 않는다."""
    if re.search(r'소진|선착순|상시|마감|연장', quote):
        return None
    found, korean = _RANGE.findall(quote), _RANGE_KO.findall(quote)
    if not found and year and len(korean) == 1:   # 'M월 D일 ~ M월 D일'은 그 문장을 확인한 해의 날짜로 읽는다
        found = [(str(year)[2:], '', korean[0][0], korean[0][1], '', '', korean[0][2], korean[0][3])]
    if len(found) != 1:
        return None
    y1, y1s, m1, d1, y2, y2s, m2, d2 = found[0]
    year = 2000 + int(y1 or y1s)
    try:
        start, end = date(year, int(m1), int(d1)), date(2000 + int(y2 or y2s) if (y2 or y2s) else year, int(m2), int(d2))
    except ValueError:
        return None
    return (start, end) if start <= end else None


_HEDGE = re.compile(r'아닌|않|미취업|우대|가능|단,|다만|예외')


# 내 정보에서 고르는 소득 구간(기준 중위소득 대비 %): 60 이하 / 60 초과 100 이하 / 100 초과 150 이하 / 150 초과
INCOME_BANDS = {60: (0, 60), 100: (60, 100), 150: (100, 150), 999: (150, None)}
RESIDENCE_BANDS = (0, 6, 12, 24, 36, 60)   # 내 정보에서 고르는 거주 기간 구간의 아래쪽 값(개월)
PROFILE_NAMES = {'job_code': 'job', 'school_code': 'school', 'major_code': 'major', 'marriage_code': 'marriage'}


def provided(profile):
    """비교할 정보가 하나라도 있는가. '받는 지원 없음'([])만으로는 비교했다고 하지 않는다."""
    return any(v not in (None, '', []) for v in profile.values())


# 2026년 기준 중위소득(월, 원). 출처와 한계는 파일 안에 적혀 있다.
MEDIAN = json.loads((Path(__file__).parent / 'data/median_income_2026.json').read_text(encoding='utf-8'))['monthly']
# 도시근로자 가구원수별 가구당 월평균소득(월, 원). 파일이 없으면 이 기준은 비교하지 않는다. 출처와 한계는 파일 안에 있다.
_URBAN_FILE = Path(__file__).parent / 'data/urban_worker_income_2026.json'
URBAN = json.loads(_URBAN_FILE.read_text(encoding='utf-8')) if _URBAN_FILE.exists() else {}
# 승인된 정책(engine.py)에 넘길 사실 값으로 바꾸는 표. fact_definitions.json 의 선택지에 맞춘다.
REGION_FACT = {'11': '서울', '41': '경기', '28': '인천', '26': '부산'}
JOB_FACT = {'0013003': 'unemployed', '0013001': 'employed'}
_CACHE = {'key': None, 'rows': []}


def _catalog():
    """수집 정책과 그 구조화 결과. 수집 내용이 바뀌면(건수·마지막 수집 시각·원문 길이 합) 다시 만든다."""
    with connect() as con:
        key = (str(db.DB_PATH), *con.execute('SELECT count(*), max(last_seen_at), total(length(payload_json)) FROM ontong_candidates').fetchone())
        if _CACHE['key'] != key:
            rows = con.execute('SELECT external_id,name,agency,sha256,payload_json FROM ontong_candidates').fetchall()
            _CACHE.update(key=key, rows=[(dict(r), structure(json.loads(r['payload_json']))) for r in rows])
    return _CACHE['rows']


def validate_profile(profile):
    """코드표에 없는 코드를 조용히 무시하지 않는다."""
    for key, field in PROFILE_FIELDS.items():
        value = profile.get(key)
        if value and value not in CODEBOOK['groups'][field]['codes']:
            raise ValueError(f'{key}: 코드표에 없는 값입니다.')
    if any(g not in TARGETS for g in profile.get('groups') or []):
        raise ValueError('groups: 목록에 없는 대상입니다.')
    if any(b not in BENEFITS for b in profile.get('benefits') or []):
        raise ValueError('benefits: 목록에 없는 지원입니다.')
    for key in ('sido', 'region_code'):
        value = profile.get(key)
        if value and value[:2] not in SIDO:
            raise ValueError(f'{key}: 확인된 시도 코드가 아닙니다.')
    if profile.get('income_band') not in (None, *INCOME_BANDS):
        raise ValueError('income_band: 목록에 없는 소득 구간입니다.')
    if profile.get('sido') and profile.get('region_code') and profile['region_code'][:2] != profile['sido']:
        raise ValueError('sido와 region_code가 서로 다릅니다.')


def age_rule(supplements):
    """공식 페이지에서 찾아 문장과 함께 적어 둔 나이 규칙(사람 검수 전). 없으면 None."""
    return next(({**r, 'quote': x['quotes'][0]} for x in supplements for r in x.get('rules', []) if r['predicate'].get('fact') == 'age'), None)


def _age(item, value, rule=None):
    if value is None:
        return 'skipped', '나이를 입력하지 않았습니다.'
    if rule:
        # API 나이 값이 비었거나 공고와 다른 경우가 많아, 공식 페이지에서 확인한 문장이 있으면 그 기준을 쓴다.
        op, bound = rule['predicate']['op'], rule['predicate']['value']
        fits = value >= bound if op == 'gte' else value <= bound if op == 'lte' else bound[0] <= value <= bound[1]
        return ('match' if fits else 'mismatch'), f"공식 페이지 기준(사람 검수 전): “{rule['quote']}” — {rule['message']}"
    low, high, kind = item['min'], item['max'], item['kind']
    if kind in ('unspecified', 'invalid'):
        if kind == 'unspecified' and item['no_limit']:
            return 'match', "API에 연령 '제한없음'으로 적혀 있습니다(온통청년 누리집 표시 기준). 공고와 다른 사례가 있어 원문 확인이 필요합니다."
        return 'unknown', 'API에 연령 범위가 없습니다. 제한이 없다는 뜻은 아닙니다.'
    if (low and value < low) or (high and value > high):
        if item['no_limit']:   # 범위와 '제한없음'이 함께 적힌 어긋난 값. 어느 쪽도 믿지 않는다.
            return 'unknown', f"API에 연령 {low or '?'}~{high or '?'}세와 '제한없음' 표기가 함께 적혀 있습니다. 어느 쪽이 맞는지 공고에서 확인하세요."
        return 'mismatch', f'API 연령 {low or "?"}~{high or "?"}세 밖입니다.'
    if kind == 'range':
        if high >= 99:  # 실제 수집본에 99·100·120·999가 100건 있다. 숫자를 그대로 보여 주면 '19~999세'가 된다.
            return 'match', f'API 연령 {low}세 이상입니다(상한이 {high}로 적혀 있어 사실상 상한 없음으로 보임). 공고에서 상한을 확인하세요.'
        return 'match', f'API 연령 {low}~{high}세 안입니다.'
    side = f'최소 {low}세' if low else f'최대 {high}세'
    return 'unknown', f'API에 {side}만 적혀 있습니다. 반대쪽 기준은 공고에서 확인하세요.'


def _region(item, profile):
    result, basis = _area(item, profile)
    need, lived = item['residence_min_months'], profile.get('residence_months')
    if result == 'match' and need and lived is not None:
        # 내 정보의 거주 기간은 구간(6개월~1년 등)의 아래쪽 값이다. 구간 전체가 조건 위·아래에 있을 때만 정한다.
        upper = next((b for b in RESIDENCE_BANDS if b > lived), None)
        if lived >= need:
            return 'match', f'지역이 맞고, 입력한 거주 기간이 API 글의 {need}개월 이상 거주 조건을 넘습니다. 기준일과 연속 거주 여부는 공고에서 확인하세요.'
        if upper is not None and upper <= need:
            return 'mismatch', f'지역은 맞지만 API 글에 {need}개월 이상 거주 조건이 있고, 입력한 거주 기간은 그보다 짧습니다. 기준일은 공고에서 확인하세요.'
    if result == 'match' and need:
        return 'unknown', f"지역은 맞지만 API 글에 {need}개월 이상 거주 조건이 있습니다. 전입일을 공고의 기준일과 대조하세요."
    return result, basis


def _area(item, profile):
    code, sido = profile.get('region_code'), profile.get('sido') or (profile.get('region_code') or '')[:2]
    if not sido:
        return 'skipped', '지역을 입력하지 않았습니다.'
    if not item['codes']:
        return 'unknown', 'API에 지역 코드가 없습니다.'
    if sido not in item['sido']:
        return 'mismatch', 'API 지역 코드에 해당 지역이 없습니다.'
    # 시도 전체가 등록된 정책, 내가 사는 구의 '시' 코드로 등록된 정책은 내 코드가 목록에 없어도 다르다고 하지 않는다.
    if code and code not in item['codes'] and sido not in item['full_sido'] and PARENT.get(code) not in item['codes']:
        if any(PARENT.get(c) == code for c in item['codes']):
            return 'unknown', '같은 시의 일부 구만 등록돼 있습니다. 내가 사는 구가 대상인지 공고에서 확인하세요.'
        old = [ABOLISHED[c] for c in item['codes'] if c in ABOLISHED and c[:2] == sido]
        if old:   # 폐지 코드가 어느 새 구로 이어지는지는 공식 코드 목록에 없다
            return 'unknown', f"행정구역 개편 전 시군구 코드({', '.join(old)})로 등록돼 있어 지금의 시군구와 견줄 수 없습니다. 대상 지역을 공고에서 확인하세요."
        return 'mismatch', 'API 지역 코드에 해당 지역이 없습니다.'
    if item['nationwide'] and item['local_agency_hint']:
        return 'unknown', '전국으로 등록됐지만 주관기관이 지자체로 보입니다. 실제 지원 지역을 확인하세요.'
    if code or item['nationwide']:
        return 'match', 'API 지역 코드에 해당 지역이 있습니다.'
    if sido in item['full_sido']:
        return 'match', 'API 지역 코드가 이 시도의 시군구 전체를 포함합니다.'
    return 'unknown', '시도는 포함되지만 시군구를 입력하지 않아 확인이 필요합니다.'


def _coded(item, value):
    if not value:
        return 'skipped', '입력하지 않았습니다.'
    if item['missing']:
        return 'unknown', 'API에 값이 없습니다. 제한이 없다는 뜻은 아닙니다.'
    if item['unrestricted'] or value in item['codes']:
        return 'match', 'API 기재: ' + ', '.join(item['labels'] or item['codes'])
    if item['unknown_codes']:
        return 'unknown', '코드표에 없는 코드가 있어 확인이 필요합니다.'
    return 'mismatch', 'API 기재: ' + ', '.join(item['labels'])


def _period(status, long_window=False, scale=None):
    if status == 'open' and not long_window and scale and scale['first_come']:
        people = f" {scale['count']:,}명" if scale['count'] else ''
        return 'unknown', f'API 신청기간 안이지만 선착순{people}으로 적혀 있습니다. 마감일 전에 끝났을 수 있어 접수 여부를 공고나 기관에서 확인하세요.'
    if status == 'open' and long_window:
        return 'unknown', 'API 신청기간이 1년 가까이로 적혀 있습니다. 사업기간을 적은 것일 수 있어 실제 모집 회차와 마감일을 공고에서 확인하세요.'
    return {'open': ('match', 'API 신청기간 안입니다. 시각·조기 마감은 공고에서 확인하세요.'),
            'rolling': ('unknown', 'API 상시 표기입니다. 현재 접수 여부는 확인이 필요합니다.'),
            'upcoming': ('unknown', 'API 신청기간이 아직 시작되지 않았습니다.'),
            'unknown': ('unknown', 'API에 신청기간이 없습니다.'),
            'ended': ('mismatch', 'API 신청기간이 지났습니다.'),
            'closed_code': ('mismatch', 'API 마감 표기입니다.'),
            'closed_official': ('mismatch', '대조한 공식 공고가 접수 종료 상태였습니다.')}[status]


def _side(pct, bounds, extra=0):
    """소득 비율이 기준 안인지. 상한이 여럿 적힌 글(유형별 70%·100%·130% 이하)은 가장 높은 상한을 넘어야 '달라요',
    가장 낮은 상한 안이어야 '맞아요'이고 그 사이는 '확인 필요'다. 경계 ±5%도 '확인 필요'다."""
    tops, floors = [b['pct'] for b in bounds if b['kind'] == 'max'], [b['pct'] for b in bounds if b['kind'] == 'min']
    if (tops and pct > (max(tops) + extra) * 1.05) or (floors and pct < min(floors) * 0.95):
        return 'mismatch'
    if (tops and pct > min(tops) * 0.95) or (floors and pct < max(floors) * 1.05):
        return 'unknown'
    return 'match'


def _income(item, profile):
    if item['code'] == '0043001':
        return 'match', 'API 소득 무관 표기입니다. 공고와 다른 사례가 있어 원문 확인이 필요합니다.'
    if item['missing']:
        return 'unknown', 'API에 소득 구분이 없습니다.'
    pay, size, bounds = profile.get('income_monthly'), profile.get('household'), item['median_bounds']
    top, mine = item['bracket_max'], profile.get('income_bracket')
    if top is not None:
        if mine is None:
            return 'unknown', f'API 소득 글에 학자금 지원 {top}구간(소득분위) 이하 기준이 있습니다. 내 정보에 구간을 넣으면 견줘 봅니다.'
        mark = '기초·차상위' if mine == 0 else f'{mine}구간'
        if mine <= top:
            return 'match', f'입력한 학자금 지원구간({mark})이 API 소득 글의 {top}구간 이하 안입니다. 어느 학기 구간을 보는지와 예외는 공고에서 확인하세요.'
        return 'mismatch', f'입력한 학자금 지원구간({mark})이 API 소득 글의 {top}구간 이하 밖입니다. 다자녀·긴급 사유 같은 예외는 공고에서 확인하세요.'
    city = item['urban_bounds']
    if city and not bounds and all(b['kind'] != '?' for b in city):
        text = ', '.join(f"{b['pct']}% {'이하' if b['kind'] == 'max' else '이상'}" for b in city)
        table = URBAN.get('monthly', {})
        if pay is None or not size or str(size) not in table:
            return 'unknown', f'API 글에 도시근로자 월평균소득 {text} 기준이 있습니다. 월 소득과 가구원 수를 넣으면 견줘 봅니다.'
        pct = pay * 10000 / table[str(size)] * 100
        # 1·2인 가구에 기준을 더 얹어 주는 정책이 있어(표 파일의 small_household_addition), 그만큼은 '달라요'로 보지 않는다.
        extra = URBAN.get('small_household_addition', {}).get(str(size), 0)
        head = f"입력한 월 소득은 {URBAN['year_label']} 도시근로자 월평균소득({size}인 가구)의 약 {pct:.0f}%이고, API 글의 기준은 {text}입니다. "
        side = _side(pct, city, extra)
        if side == 'mismatch':
            return 'mismatch', head + '기준 밖으로 보입니다. 가구 소득 합산 범위와 산정 방식은 공고에서 확인하세요.'
        if side == 'unknown':
            return 'unknown', head + ('경계에 가깝거나 1·2인 가구 가산이 적용될 수 있어 확인이 필요합니다.' if extra else '경계(±5%)에 가깝거나 여러 기준 사이에 있어 확인이 필요합니다.')
        return 'match', head + '기준 안으로 보입니다. 가구 소득 합산 범위(부모·배우자)와 자산 기준은 공고에서 확인하세요.'
    band = profile.get('income_band')
    if band and pay is None and bounds and all(b['kind'] != '?' for b in bounds):
        # 금액 대신 구간으로 받은 소득. 구간 전체가 기준 안이면 '맞아요', 전체가 밖이면 '달라요', 걸치면 '확인 필요'다.
        low, high = INCOME_BANDS[band]
        tops, floors = [b['pct'] for b in bounds if b['kind'] == 'max'], [b['pct'] for b in bounds if b['kind'] == 'min']
        text = ', '.join(f"{b['pct']}% {'이하' if b['kind'] == 'max' else '이상'}" for b in bounds)
        name = '중위소득 150% 초과' if high is None else f'중위소득 {high}% 이하'
        head = f'입력한 소득 구간은 {name}이고, API 소득 글의 기준은 {text}입니다. '
        if (tops and low >= max(tops)) or (floors and high is not None and high < min(floors)):
            return 'mismatch', head + '기준 밖으로 보입니다. 소득 산정 방식은 공고에서 확인하세요.'
        if (not tops or (high is not None and high <= min(tops))) and (not floors or low >= max(floors)):
            return 'match', head + '기준 안으로 보입니다. 산정 방식(소득금액증명·건강보험료)과 가구 기준은 공고에서 확인하세요.'
        return 'unknown', head + '구간이 기준에 걸쳐 있어 확인이 필요합니다.'
    if pay is not None and size and bounds and all(b['kind'] != '?' for b in bounds):
        # 기준 중위소득 대비 비율로만 비교한다. 경계 ±5%는 산정 방식에 따라 뒤집힐 수 있어 확인 필요로 둔다.
        pct = pay * 10000 / MEDIAN[str(size)] * 100
        text = ', '.join(f"{b['pct']}% {'이하' if b['kind'] == 'max' else '이상'}" for b in bounds)
        head = f'입력한 월 소득은 2026년 기준 중위소득({size}인 가구)의 약 {pct:.0f}%이고, API 소득 글의 기준은 {text}입니다. '
        side = _side(pct, bounds)
        if side == 'mismatch':
            return 'mismatch', head + '기준 밖으로 보입니다. 소득 산정 방식은 공고에서 확인하세요.'
        if side == 'unknown':
            return 'unknown', head + '경계(±5%)에 가깝거나 여러 기준 사이에 있어 확인이 필요합니다.'
        return 'match', head + '기준 안으로 보입니다. 산정 방식(소득금액증명·건강보험료)과 가구 기준은 공고에서 확인하세요.'
    annual = item['annual']
    if annual:
        text = f"연 {annual['max']:,}만원 이하"
        if annual['min']:
            # 최소 금액 칸이 하한이 아니라 다른 대상의 상한으로 쓰인 사례가 있다(전세보증금반환보증: 청년 5,000 / 신혼부부 7,500).
            # 실제 47건 중 8건에 두 값이 있고 어느 뜻인지 가릴 수 없어 견주지 않는다.
            return 'unknown', (f"API 소득 칸에 {annual['min']:,}만원과 {annual['max']:,}만원 두 값이 적혀 있습니다. 하한·상한인지 대상별 상한인지 알 수 없어 견주지 않았습니다. "
                               '공고에서 내 대상의 소득 기준을 확인하세요.')
        if pay is None:
            return 'unknown', f'API 소득 기준은 {text}입니다(단위는 온통청년 누리집 표시 기준). 월 소득을 넣으면 견줘 봅니다.'
        yearly = pay * 12
        head = f'입력한 월 소득으로 본 연소득은 약 {yearly:,}만원이고, API 소득 기준은 {text}입니다(단위는 온통청년 누리집 표시 기준). '
        if yearly > annual['max'] * 1.05:
            return 'mismatch', head + '기준 밖으로 보입니다. 개인·가구 기준과 산정 방식은 공고에서 확인하세요.'
        if yearly >= annual['max'] * 0.95:
            return 'unknown', head + '경계(±5%)에 가까워 확인이 필요합니다.'
        return 'match', head + '기준 안으로 보입니다. 개인·가구 기준과 산정 방식은 공고에서 확인하세요.'
    if item['median_pct']:
        return 'unknown', ('API 소득 글에 중위소득 ' + '·'.join(f'{x}%' for x in item['median_pct'])
                           + ' 기준이 적혀 있습니다. 가구원 수와 산정 방식을 공고에서 확인하세요.')
    kinds = [k for k in item['kinds'] if k != '공고에서 확인']
    return 'unknown', ('소득 조건이 있습니다. ' + (f"기준 방식: {', '.join(kinds)}. " if kinds else '')
                       + '금액 단위·개인/가구 기준이 확인되지 않아 비교하지 않았습니다.')


def restricts(item):
    """이 정책의 API 값이 가르는 내 정보 항목. 질문 선택기가 찾은 정책들에서 이것을 세어 무엇을 물을지 고른다."""
    keys, area, limits = set(), item['region'], item['exclusions']['kinds']
    if not area['nationwide']:
        keys.add('sido')
        if set(area['sido']) - set(area['full_sido']):
            keys.add('region_code')
    if item['age']['kind'] in ('range', 'min_only', 'max_only'):
        keys.add('age')
    keys.update(key for key, field in PROFILE_NAMES.items() if not item[field]['unrestricted'] and not item[field]['missing'])
    if '다른 지원과 중복' in limits or '수급' in limits:
        keys.add('benefits')
    if item['targets']:
        keys.add('groups')
    if item['income']['annual'] or item['income']['median_bounds'] or item['income']['urban_bounds']:
        keys.add('income_monthly')
    if item['income']['bracket_max'] is not None:
        keys.add('income_bracket')
    if area['residence_min_months']:
        keys.add('residence_months')
    return keys


def screen(structured, profile, status, rule=None, notes=(), on=None):
    rows = [('period', *_period(status, structured['application']['long_window'], structured['scale'])), ('age', *_age(structured['age'], profile.get('age'), rule)),
            ('region', *_region(structured['region'], profile)), ('income', *_income(structured['income'], profile))]
    rows += [(name, *_coded(structured[name], profile.get(key)))
             for key, name in [('job_code', 'job'), ('school_code', 'school'), ('major_code', 'major'), ('marriage_code', 'marriage')]]
    # 공식 페이지에서 확인해 둔 문장(사람 검수 전)이 API 값과 어긋나면 API 값을 믿지 않는다.
    said = next((q for x in notes if x['field'] == 'conditions' for q in x['quotes'] if '소득' in q), None)
    if said and structured['income']['code'] == '0043001':
        rows[3] = ('income', 'unknown', f'API는 소득 무관으로 적혀 있지만 공식 페이지에 소득 조건이 있습니다(사람 검수 전): “{said}”')
    official = next((x['quotes'][0] for x in notes if x['field'] == 'period'), None)
    # 신청 시기 인용들에서 기간이 꼭 하나로 읽힐 때만 쓴다(여러 회차·행사일이 섞이면 쓰지 않는다).
    spans = {w for x in notes if x['field'] == 'period' for q in x['quotes']
             for w in [official_window(q, int(x['checked_on'][:4]) if x.get('checked_on') else None)] if w} if on else set()
    window = next(iter(spans)) if len(spans) == 1 else None
    if window:
        official = next(q for x in notes if x['field'] == 'period' for q in x['quotes']
                        if official_window(q, int(x['checked_on'][:4]) if x.get('checked_on') else None) == window)
    if window and window[0] <= on <= window[1]:
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] + f' 공식 페이지에도 신청 시기가 “{official}”로 적혀 있습니다(사람 검수 전).')
    elif window and on > window[1] and rows[0][1] != 'mismatch':
        # 공식 페이지 확인에서 API는 접수 중인데 회차가 이미 끝난 정책이 여럿 나왔다(사람 검수 전이라 '달라요'로 단정하지는 않는다).
        rows[0] = ('period', 'unknown', f'공식 페이지에 적힌 신청 시기 “{official}”는 이미 지났습니다(사람 검수 전). API 날짜와 달라 추가 모집이 있는지 확인하세요.')
    elif official and rows[0][1] == 'match':
        rows[0] = ('period', 'unknown', f'API 신청기간 안이지만 공식 페이지에 신청 시기가 따로 적혀 있습니다(사람 검수 전): “{official}”. 지금 접수 중인지 대조하세요.')
    elif official:
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] + f' 공식 페이지에 적힌 신청 시기(사람 검수 전): “{official}”')
    # 공식 페이지에 나이 문장이 있는데 규칙으로 옮기지 못한 경우(출생연도 기준, 문장이 서로 다름)에는 API 나이로 단정하지 않는다.
    aged = next((q for x in notes if x['field'] == 'conditions' for q in x['quotes'] if _AGE_SAID.search(q)), None)
    if aged and not rule and rows[1][1] in ('match', 'mismatch'):
        rows[1] = ('age', 'unknown', f'공식 페이지의 나이 기준이 API 값과 다를 수 있습니다(사람 검수 전): “{aged}”')
    # 이름에 특정 대상이 드러난 정책은, 내가 그 대상이라고 한 경우에만 '맞아요'로 본다. 아니라고 단정하지는 않는다.
    if structured['targets']:
        mine, names = profile.get('groups'), ', '.join(structured['targets'])
        if mine and set(mine) & set(structured['targets']):
            rows.append(('target', 'match', f'정책 이름의 대상({names})에 내가 고른 항목이 있습니다.'))
        else:
            rows.append(('target', 'unknown', f'정책 이름에 특정 대상({names})이 있습니다. 해당하는지 공고에서 확인하세요.'))
    if not (structured['access']['has_method'] or structured['access']['has_apply_url']):
        rows.append(('apply', 'unknown', ("API 신청 방법 칸에 '해당없음'으로 적혀 있습니다. 신청 없이 이용하는 정책인지 공고에서 확인하세요." if structured['access']['method_stated_none']
                                         else 'API에 신청 방법과 신청 주소가 없습니다. 참고 주소의 공고에서 신청 방법을 확인하세요.')))
    # 참여 제한(제외·중복 수혜) 안내가 있으면 해당 여부를 알 수 없으므로 확인 필요로 남긴다.
    limits = structured['exclusions']
    if limits['explicit_none']:
        rows.append(('exclusion', 'match', "API 참여 제한 칸에 '해당 없음'으로 적혀 있습니다. 공고와 다른 사례가 있어 원문 확인이 필요합니다."))
    if limits['sentences']:
        more = f" 외 {limits['count'] - 1}건" if limits['count'] > 1 else ''
        # 정책의 제한 문장이 '내가 받고 있는 지원'을 가리키는 방향만 본다(반대 방향으로 뒤집지 않는다).
        held = next(((name, s) for name in profile.get('benefits') or [] for s in limits['sentences']
                     if any(word in s.replace(' ', '') for word in BENEFITS[name])), None)
        label, pattern = JOB_LIMIT.get(profile.get('job_code'), ('', None))
        job = next((s for s in limits['sentences'] if pattern and re.search(pattern, s) and not _HEDGE.search(s)), None)
        if held:
            rows.append(('exclusion', 'mismatch', f"API 참여 제한 안내에 받고 있는 지원({held[0]})이 나옵니다: “{held[1]}”. 함께 받을 수 있는지 기관에 확인하세요."))
        elif job:
            rows.append(('exclusion', 'mismatch', f"API 참여 제한 안내에 내 취업 상태({label})가 나옵니다: “{job}”. 해당하는지 공고에서 확인하세요."))
        else:
            kinds = f" 확인할 것: {', '.join(limits['kinds'])}." if limits['kinds'] else ''
            rows.append(('exclusion', 'unknown', f"API에 참여 제한 안내가 있습니다: “{limits['sentences'][0]}”{more}.{kinds} 해당하는지는 공고에서 확인하세요."))
    results = {r[1] for r in rows}
    outcome = 'api_mismatch' if 'mismatch' in results else 'needs_check' if 'unknown' in results else 'api_match'
    return {'outcome': outcome, 'qualification_determined': False,
            'criteria': [{'key': k, 'result': r, 'basis': b} for k, r, b in rows],
            'to_confirm': [k for k, r, _ in rows if r in ('unknown', 'mismatch')], 'notice': NOTICE}


def approved_policy(external_id, check, approved):
    """이 수집 정책에 연결된 '사람이 승인한 정책'. 대조 기록의 policy_code 또는 검수 화면이 만든 ontong-<정책번호>."""
    return approved.get((check or {}).get('policy_code')) or approved.get('ontong-' + external_id.lower())


def engine_view(policy, profile, on):
    """승인된 정책을 engine.py 의 규칙으로 판정한 결과. 사람 검수를 거친 정책에만 쓴다."""
    from engine import status_policy
    sido, facts = profile.get('sido') or (profile.get('region_code') or '')[:2], {}
    if profile.get('age') is not None:
        facts['age'] = profile['age']
    if sido:
        facts['region'] = REGION_FACT.get(sido, '기타')
    if profile.get('job_code'):
        facts['employment_status'] = JOB_FACT.get(profile['job_code'], 'other')
    # 초안 도구가 API 코드 조건을 그대로 옮긴 규칙(sido_code in [...], job_code in [...])에 쓸 값
    facts.update({k: v for k, v in [('sido_code', sido), *((key, profile.get(key)) for key in PROFILE_FIELDS)] if v})
    out = status_policy(policy, facts, on)
    return {'policy_code': policy['code'], 'status': out['status'], 'missing_facts': out['missing_facts'],
            'reviewed_by': out['reviewed_by'], 'reviewed_at': out['reviewed_at'],
            # 조건마다 근거(출처 이름·주소·인용 문장·검수 여부)를 함께 넘긴다.
            'findings': [{'rule_id': f['rule_id'], 'type': f['type'], 'effect': f['effect'], 'message': f['message'], 'source': f['source']} for f in out['findings']]}


def screen_catalog(profile, on, query='', outcome='', only_tier='', page=1, page_size=20, category='', keywords=(), dedupe=True):
    """수집 정책 전체를 걸러 건수와 한 페이지를 돌려준다. 읽기 전용."""
    from ontong import BASE
    from policy_data import load_policies
    validate_profile(profile)
    approved = load_policies()
    # 대조 기록 파일은 한 번만 읽는다(정책마다 다시 읽으면 수천 번 파일을 연다).
    path = BASE / 'data' / 'source_checks.json'
    checks = {x['external_id']: x for x in (json.loads(path.read_text(encoding='utf-8')) if path.exists() else [])}
    notes_path, notes = BASE / 'data' / 'supplements.json', {}
    for x in (json.loads(notes_path.read_text(encoding='utf-8')) if notes_path.exists() else []):
        notes.setdefault(x['external_id'], []).append(x)
    needle = query.strip().lower()
    words = [w for w in keywords if w]
    found, outcomes, tiers = [], {k: 0 for k in ORDER}, {'reviewed': 0, 'screenable': 0, 'link_only': 0}
    splits = Counter()   # 비교 가능한 정책 가운데 내 정보 항목마다 그 항목으로 갈리는 정책 수
    for row, item in _catalog():
        # 대화 검색어는 이름뿐 아니라 수집 원문 전체에서 찾는다(이름에 없는 '응시료' 지원 등).
        if words and not any(w in row['payload_json'] for w in words):
            continue
        if needle and needle not in (row['name'] + ' ' + row['agency'] + ' ' + row['external_id']).lower():
            continue
        check = checks.get(row['external_id'])
        if check:
            check = {**check, 'api_changed_since_check': check['api_sha256'] != row['sha256']}
        if category and item['category'] != category:
            continue
        status = period_status(item['application'], on, check)
        policy = approved_policy(row['external_id'], check, approved)
        placed = tier(item, status, bool(policy))
        # 원문 링크만 보여줄 정책은 걸러보기 결과를 만들지 않는다.
        mine = notes.get(row['external_id'], [])
        result = screen(item, profile, status, age_rule(mine), mine, on) if placed['tier'] != 'link_only' else None
        if result:
            splits.update(restricts(item))
        deadline, label = timing(item['application'], status, on)
        found.append({'external_id': row['external_id'], 'name': row['name'], 'agency': row['agency'], 'deadline': deadline, 'period_label': label,
                      'long_window': item['application']['long_window'],
                      'category': item['category'], 'period_status': status, 'engine': engine_view(policy, profile, on) if policy else None, 'name_hit': any(w in row['name'] for w in words), **placed, 'screen': result,
                      'amounts': item['amounts'], 'channels': item['access']['channels'], 'provision': item['provision']['label'],
                      'scale': item['scale'], 'selection': item['selection']['methods'], 'summary': item['summary'],
                      'age': item['age'], 'sido_names': item['region']['sido_names'], 'nationwide': item['region']['nationwide'],
                      # 전국 대상은 시군구 묶음이 두 벌이라(행정구역 개편) 코드가 달라도 같은 지역으로 본다.
                      '_same': (row['name'].strip(), 'nationwide' if item['region']['nationwide'] else ','.join(sorted(item['region']['codes'])))})
    found.sort(key=lambda x: x['external_id'], reverse=True)
    # 주제를 물었을 때는 이름에 그 말이 있는 정책을 먼저, 그 안에서 비교 결과 순으로 보여 준다.
    # 같은 결과 안에서는 접수 중인 정책을 마감이 가까운 순으로 먼저 보여 준다(API 기재 마감일 기준).
    # 사람이 승인한 정책 가운데 신청을 검토할 수 있는 것은 맨 앞에 둔다.
    found.sort(key=lambda x: (bool(words) and not x['name_hit'], not (x['engine'] and x['engine']['status'] == 'review_possible'),
                              ORDER[x['screen']['outcome']] if x['screen'] else 3,
                              # 신청 방법이 비어 있는 정책(제도·과제 성격이 섞여 있다)은 같은 결과 안에서 뒤에 둔다.
                              bool(x['screen']) and 'apply' in x['screen']['to_confirm'],
                              RANK[x['period_status']] + (1.5 if x['long_window'] and x['period_status'] == 'open' else 0), x['deadline'] or ''))
    # 같은 이름·같은 지역 코드로 여러 번 등록된 정책(지난 회차·재등록, 실제 4,020건 중 292건)은 하나로 묶는다.
    # 정렬 뒤 첫 항목(비교 가능한 것, 그다음 최신 등록)을 남기고 몇 건이 등록돼 있는지 알려 준다.
    items, kept = [], {}
    for x in found:
        key = x.pop('_same')
        if dedupe and key in kept:
            kept[key]['same_policy_count'] += 1
            continue
        x['same_policy_count'] = 1
        kept[key] = x
        items.append(x)
    merged = len(found) - len(items)
    for x in items:
        tiers[x['tier']] += 1
    if only_tier:
        items = [x for x in items if x['tier'] == only_tier]
    for x in items:
        if x['screen']:
            outcomes[x['screen']['outcome']] += 1
    if outcome:
        items = [x for x in items if x['screen'] and x['screen']['outcome'] == outcome]
    total = len(items)
    return {'as_of': on.isoformat(), 'total': total, 'page': page, 'page_size': page_size,
            'pages': (total + page_size - 1) // page_size, 'tiers': tiers, 'outcomes': outcomes, 'merged': merged, 'splits': dict(splits),
            'items': items[(page - 1) * page_size: page * page_size], 'notice': NOTICE}
