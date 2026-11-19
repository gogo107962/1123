"""Decode sourced API labels. This module never determines personal eligibility."""
import json
from pathlib import Path

CODEBOOK = json.loads((Path(__file__).parent / 'data/ontong_codebook.json').read_text(encoding='utf-8'))

# 코드표 표기(bizPrdSecd)와 수집 등록된 필드명(bizPrdSeCd)이 다르다. 코드표 원문 표기는 그대로 두고
# 값을 읽을 때만 실제 필드명으로 바꾼다. 이 별칭이 없으면 4,020건 모두 값이 있는데도 해석되지 않는다.
API_FIELD = {'bizPrdSecd': 'bizPrdSeCd'}


def api_field(field):
    return API_FIELD.get(field, field)


def decode(field, value):
    raw = str(value or '').strip()
    codes = list(dict.fromkeys(x.strip() for x in raw.split(',') if x.strip()))
    mapping = CODEBOOK['groups'].get(field, {}).get('codes', {})
    return {'field': field, 'raw': raw,
            'labels': [mapping[c]['label'] for c in codes if c in mapping],
            'unknown_codes': [c for c in codes if c not in mapping],
            'missing': not codes}


def application_hint(payload, check=None):
    if check and check.get('official_status') == 'closed' and not check.get('api_changed_since_check'):
        return {'kind': 'closed', 'label': '공식 공고 종료 기록', 'basis': 'source_check', 'current_open': None}
    code = str(payload.get('aplyPrdSeCd') or '')
    kind, label = {'0057001': ('fixed', '등록된 특정기간'), '0057002': ('rolling', '등록된 상시'),
                   '0057003': ('closed', '등록된 마감')}.get(code, ('unknown', '접수 상태 확인 필요'))
    return {'kind': kind, 'label': label, 'basis': 'api_code', 'current_open': None}


def describe(payload):
    fields = [decode(field, payload.get(api_field(field))) for field in CODEBOOK['groups']]
    for field in fields:
        field['title'] = CODEBOOK['groups'][field['field']]['title']
        field['api_field'] = api_field(field['field'])
        # 수집 허용 목록에 없어 저장되지 않은 분류는 '값 없음'과 구분한다.
        field['collected'] = field['api_field'] in payload
    return {'fields': fields, 'source': CODEBOOK['source'],
            'income': {'kind': decode('earnCndSeCd', payload.get('earnCndSeCd')),
                       'minimum_raw': payload.get('earnMinAmt'), 'maximum_raw': payload.get('earnMaxAmt'),
                       'unit': None, 'comparable': False,
                       'notice': '금액 단위·개인/가구 기준·공제 기준을 공고에서 확인하기 전에는 소득을 비교하지 않습니다.'},
            'region': {'raw': payload.get('zipCd', ''), 'resolved': False,
                       'notice': '제공된 코드표에 지역 코드가 없어 지원 지역을 자동 판정하지 않았습니다.'},
            'notice': '코드 뜻을 해석한 참고 정보입니다. 자격·중복 수혜·현재 접수 여부를 확정하지 않습니다.'}


def questions(payload):
    """Prioritized source checks, not invented user facts or LLM judgments."""
    result = [{'key': 'period', 'question': '최신 공고의 실제 접수기간과 예산 소진 여부를 확인했나요?'}]
    if payload.get('zipCd'):
        result.append({'key': 'region', 'question': '공고의 지원 지역과 거주 기준일을 확인했나요?'})
    income = decode('earnCndSeCd', payload.get('earnCndSeCd'))
    if income['raw'] != '0043001':
        result.append({'key': 'income', 'question': '소득의 금액 단위·개인/가구 범위·산정 기준을 확인했나요?'})
    result.extend([{'key': 'benefits', 'question': '현재 받는 지원과 과거 참여 이력에 대한 중복 제한을 공고에서 확인했나요?'},
                   {'key': 'documents', 'question': '서류 목록·발급일·대체서류 조건을 최신 공고와 대조했나요?'}])
    return result
