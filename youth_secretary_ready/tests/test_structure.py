"""API 필드 구조화와 걸러보기 회귀. 모의 데이터 기반이며 실제 4,020건·실제 공고 검증이 아니다."""
import json
from pathlib import Path
from datetime import date
import pytest
from test_project import ctx
from test_ontong import item, fake_key
from test_codes import seed, snapshot
from db import connect
import ontong
from policy_codes import CODEBOOK
from policy_structure import PROFILE_FIELDS, SIDO, UNRESTRICTED, age, application, period_status, region, structure, tier
from screening import screen, validate_profile
from policy_data import load_policies, validate_predicate

SCREEN = '/api/integrations/ontong/screen'
DAY = date(2026, 11, 17)
# 16개 시도를 모두 덮는 지역 코드. 서울은 강북구(11305)로 넣는다.
ALL = ','.join(['11305'] + [s + '000' for s in SIDO])
BASE = dict(aplyPrdSeCd='0057001', aplyYmd='20261101 ~ 20261130', sprtTrgtMinAge='19', sprtTrgtMaxAge='34',
            zipCd='11305,11110', earnCndSeCd='0043001', jobCd='0013010', plcyAplyMthdCn='온라인 신청')
PROFILE = {'age': 26, 'region_code': '11305', 'job_code': '0013003'}


def made(**over):
    return structure({**BASE, **over})


def verdict(structured, profile, status='open'):
    out = screen(structured, profile, status)
    return out, {c['key']: c['result'] for c in out['criteria']}


def post(ctx, profile=PROFILE, **body):
    return ctx.post(SCREEN, json={'profile': profile, 'on': '2026-11-17', **body})


# ── 나이 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize('low,high,kind,expect', [
    ('0', '0', 'unspecified', (None, None)), ('', '', 'unspecified', (None, None)),
    (None, None, 'unspecified', (None, None)), ('19', '0', 'min_only', (19, None)),
    ('', '34', 'max_only', (None, 34)), ('abc', '34', 'max_only', (None, 34)),
    ('19', '34', 'range', (19, 34)), ('34', '19', 'invalid', (34, 19))])
def test_age_zero_or_blank_is_unspecified_not_unlimited(low, high, kind, expect):
    result = age({'sprtTrgtMinAge': low, 'sprtTrgtMaxAge': high, 'sprtTrgtAgeLmtYn': 'N'})
    assert result['kind'] == kind and (result['min'], result['max']) == expect
    assert result['limit_flag_raw'] == 'N' and result['limit_flag_verified'] is False


@pytest.mark.parametrize('low,high,value,expected', [
    ('0', '0', 26, 'unknown'), ('', '', 26, 'unknown'), ('34', '19', 26, 'unknown'),
    ('19', '34', 19, 'match'), ('19', '34', 34, 'match'), ('19', '34', 18, 'mismatch'), ('19', '34', 35, 'mismatch'),
    ('19', '0', 26, 'unknown'), ('19', '0', 18, 'mismatch'), ('0', '34', 26, 'unknown'), ('0', '34', 35, 'mismatch'),
    ('19', '34', None, 'skipped')])
def test_age_screening(low, high, value, expected):
    _, results = verdict(made(sprtTrgtMinAge=low, sprtTrgtMaxAge=high), {'age': value})
    assert results['age'] == expected


# ── 신청기간 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize('day,expected', [(date(2026, 4, 30), 'upcoming'), (date(2026, 5, 1), 'open'),
                                          (date(2026, 5, 31), 'open'), (date(2026, 6, 1), 'ended')])
def test_period_boundary_days_are_inclusive(day, expected):
    app = application({'aplyPrdSeCd': '0057001', 'aplyYmd': '20260501 ~ 20260531'})
    assert app['windows'] == [{'start': '2026-05-01', 'end': '2026-05-31'}]
    assert period_status(app, day) == expected


@pytest.mark.parametrize('day,expected', [(date(2026, 1, 31), 'open'), (date(2026, 3, 1), 'upcoming'),
                                          (date(2026, 6, 1), 'open'), (date(2026, 7, 1), 'ended')])
def test_multiple_periods_joined_by_backslash_n(day, expected):
    raw = r'20260101 ~ 20260131\N20260601 ~ 20260630'  # 실제 수집본의 구분 표기
    app = application({'aplyPrdSeCd': '0057001', 'aplyYmd': raw})
    assert len(app['windows']) == 2 and app['raw'] == raw
    assert period_status(app, day) == expected


def test_impossible_or_reversed_dates_are_not_turned_into_a_period():
    for raw in ('20260231 ~ 20260301', '20260601 ~ 20260501', '상시', ''):
        app = application({'aplyPrdSeCd': '0057001', 'aplyYmd': raw})
        assert app['windows'] == [] and app['raw'] == raw
        assert period_status(app, DAY) == 'unknown'


def test_period_status_follows_code_and_never_guesses():
    today = '20260101 ~ 20261231'
    assert period_status(application({'aplyPrdSeCd': '0057002', 'aplyYmd': today}), DAY) == 'rolling'
    assert period_status(application({'aplyPrdSeCd': '0057003', 'aplyYmd': today}), DAY) == 'closed_code'
    # 구분 코드가 없으면 날짜가 오늘을 포함해도 '접수 중'으로 올리지 않는다.
    assert period_status(application({'aplyYmd': today}), DAY) == 'unknown'
    assert period_status(application({}), DAY) == 'unknown'


def test_official_closure_applies_only_while_api_content_is_unchanged():
    app, check = application(BASE), {'official_status': 'closed'}
    assert period_status(app, DAY, {**check, 'api_changed_since_check': False}) == 'closed_official'
    assert period_status(app, DAY, {**check, 'api_changed_since_check': True}) == 'open'
    assert period_status(app, DAY, {'official_status': 'open', 'api_changed_since_check': False}) == 'open'


@pytest.mark.parametrize('status,expected', [('open', 'match'), ('rolling', 'unknown'), ('upcoming', 'unknown'),
                                             ('unknown', 'unknown'), ('ended', 'mismatch'),
                                             ('closed_code', 'mismatch'), ('closed_official', 'mismatch')])
def test_period_screening_rolling_is_not_confirmed_open(status, expected):
    assert verdict(made(), {}, status)[1]['period'] == expected


# ── 지역 ──────────────────────────────────────────────────────────────
def test_region_codes_are_parsed_without_guessing():
    parsed = region({'zipCd': '11305,11110, 11305,abc,1130'})
    assert parsed['codes'] == ['11305', '11110'] and parsed['invalid_codes'] == ['abc', '1130']
    assert parsed['sido'] == ['11'] and parsed['sido_names'] == ['서울특별시'] and parsed['nationwide'] is False
    assert region({'zipCd': ALL})['nationwide'] is True
    assert region({'zipCd': ALL.replace(',52000', '')})['nationwide'] is False
    unknown = region({'zipCd': ALL + ',99000'})
    assert unknown['unknown_sido'] == ['99'] and unknown['nationwide'] is False
    blank = region({})
    assert blank['codes'] == [] and blank['count'] == 0 and blank['nationwide'] is False


@pytest.mark.parametrize('agency,hint', [('서울특별시', True), ('강북구', True), ('경기도', True), ('고용노동부', False), ('', False)])
def test_local_agency_hint(agency, hint):
    assert region({'sprvsnInstCdNm': agency})['local_agency_hint'] is hint


@pytest.mark.parametrize('over,profile,expected', [
    ({}, {}, 'skipped'),
    ({}, {'sido': '11'}, 'unknown'),                    # 시도만 입력: 시군구 확인 필요
    ({}, {'region_code': '11305'}, 'match'),
    ({}, {'sido': '11', 'region_code': '11305'}, 'match'),
    ({}, {'region_code': '11740'}, 'mismatch'),         # 같은 시도라도 API에 없는 시군구
    ({}, {'sido': '26'}, 'mismatch'),
    ({'zipCd': ''}, {'sido': '11'}, 'unknown'),         # 지역 코드 없음 ≠ 전국
    ({'zipCd': ALL, 'sprvsnInstCdNm': '고용노동부'}, {'sido': '11'}, 'match'),
    ({'zipCd': ALL, 'sprvsnInstCdNm': '부산광역시'}, {'sido': '11'}, 'unknown'),   # 전국 등록 + 지자체 주관
    ({'zipCd': ALL, 'sprvsnInstCdNm': '부산광역시'}, {'region_code': '11305'}, 'unknown')])
def test_region_screening(over, profile, expected):
    assert verdict(made(**over), profile)[1]['region'] == expected


# ── 취업·학력·전공·결혼 코드, 소득 ────────────────────────────────────
@pytest.mark.parametrize('key,field', PROFILE_FIELDS.items())
def test_coded_criteria(key, field):
    codes = [c for c in CODEBOOK['groups'][field]['codes'] if c != UNRESTRICTED[field]]
    mine, other = codes[0], codes[1]
    name = {'jobCd': 'job', 'schoolCd': 'school', 'plcyMajorCd': 'major', 'mrgSttsCd': 'marriage'}[field]
    check = lambda value, profile={key: mine}: verdict(made(**{field: value}), profile)[1][name]
    assert check(UNRESTRICTED[field]) == 'match'
    assert check(other + ',' + mine) == 'match'
    assert check(other) == 'mismatch'
    assert check('') == 'unknown'                 # 빈값은 '제한 없음'이 아니다
    assert check(other + ',9999999') == 'unknown'  # 모르는 코드가 섞이면 불일치로 단정하지 않는다
    assert check(other, {}) == 'skipped'


def test_income_is_never_compared():
    assert verdict(made(), {})[1]['income'] == 'match'  # API '무관' 표기
    assert verdict(made(earnCndSeCd=''), {})[1]['income'] == 'unknown'
    limited = made(earnCndSeCd='0043002', earnMinAmt='0', earnMaxAmt='5000')
    assert limited['income']['comparable'] is False and limited['income']['unit'] is None
    assert (limited['income']['min_raw'], limited['income']['max_raw']) == ('0', '5000')
    assert verdict(limited, {})[1]['income'] == 'unknown'


# ── 종합 결과와 갈래 ─────────────────────────────────────────────────
def test_outcome_and_it_is_never_a_qualification():
    out, results = verdict(made(), PROFILE)
    assert out['outcome'] == 'api_match' and out['to_confirm'] == [] and 'mismatch' not in results.values()
    out, _ = verdict(made(), PROFILE, 'rolling')
    assert out['outcome'] == 'needs_check' and out['to_confirm'] == ['period']
    out, _ = verdict(made(zipCd=''), {**PROFILE, 'age': 40}, 'rolling')
    assert out['outcome'] == 'api_mismatch' and set(out['to_confirm']) == {'period', 'age', 'region'}
    assert all(verdict(made(), p, s)[0]['qualification_determined'] is False
               for p in (PROFILE, {}) for s in ('open', 'ended'))


def test_empty_api_record_matches_nothing():
    item_ = structure({})
    assert item_['basis'] == 'ontong_api' and item_['verified_against_notice'] is False
    out, results = verdict(item_, {**PROFILE, 'school_code': '0049005', 'major_code': '0011001', 'marriage_code': '0055002'},
                           period_status(item_['application'], DAY))
    assert set(results.values()) == {'unknown'} and out['outcome'] == 'needs_check'


def test_tier():
    assert tier(made(), 'open') == {'tier': 'screenable', 'reasons': []}
    assert all(tier(made(), s)['tier'] == 'screenable' for s in ('rolling', 'upcoming', 'unknown'))
    for status in ('ended', 'closed_code', 'closed_official'):
        assert tier(made(), status) == {'tier': 'link_only', 'reasons': ['closed']}
    assert tier(made(plcyAplyMthdCn=''), 'open')['reasons'] == ['no_application_route']
    # 주소 형식이 아닌 값은 신청 경로로 치지 않는다.
    assert tier(made(plcyAplyMthdCn=' ', aplyUrlAddr='www.example.org'), 'open')['reasons'] == ['no_application_route']
    assert tier(made(plcyAplyMthdCn='', aplyUrlAddr='https://example.org/apply'), 'open')['tier'] == 'screenable'
    assert tier(made(zipCd=''), 'open')['reasons'] == ['no_region_code']
    assert tier(structure({}), 'ended')['reasons'] == ['closed', 'no_application_route', 'no_region_code']
    assert tier(structure({}), 'ended', reviewed=True) == {'tier': 'reviewed', 'reasons': []}


# ── 프로필 검증과 API ────────────────────────────────────────────────
@pytest.mark.parametrize('profile', [{'job_code': '0013099'}, {'school_code': '0013001'}, {'sido': '99'},
                                     {'region_code': '99123'}, {'sido': '11', 'region_code': '26110'}])
def test_profile_outside_codebook_is_rejected(ctx, profile):
    with pytest.raises(ValueError):
        validate_profile(profile)
    assert post(ctx, profile).status_code == 422


def test_valid_or_empty_profile_passes():
    for profile in ({}, {'age': None, 'sido': None, 'job_code': None}, PROFILE, {'sido': '11', 'region_code': '11305'}):
        validate_profile(profile)


@pytest.mark.parametrize('body', [
    {'profile': {'job_code': '13001'}}, {'profile': {'sido': '1'}}, {'profile': {'region_code': '1130'}},
    {'profile': {'age': -1}}, {'profile': {'age': 121}}, {'profile': {}, 'on': '2026-2-1'},
    {'profile': {}, 'on': '20261117'}, {'profile': {}, 'outcome': 'eligible'}, {'profile': {}, 'tier': 'x'},
    {'profile': {}, 'page': 0}, {'profile': {}, 'page_size': 101}, {}])
def test_malformed_screen_request_is_422(ctx, body):
    assert ctx.post(SCREEN, json=body).status_code == 422


def good(number, **over):
    return item(number, **{**BASE, 'plcyNm': '정책 ' + number, **over})


def catalog(ctx):
    seed([good('SM'), good('SR', aplyPrdSeCd='0057002'), good('SX', zipCd='26110'),
          good('SL1', zipCd=''), good('SL2', aplyYmd='20260101 ~ 20260131')])


def test_screen_catalog_counts_order_and_link_only(ctx):
    catalog(ctx)
    body = post(ctx).json()
    assert body['as_of'] == '2026-11-17' and body['total'] == 5 and body['pages'] == 1 and body['notice']
    assert body['tiers'] == {'reviewed': 0, 'screenable': 3, 'link_only': 2}
    assert body['outcomes'] == {'api_match': 1, 'needs_check': 1, 'api_mismatch': 1}
    # 원문 링크만인 정책끼리도 접수 중(SL1)이 기간이 지난 것(SL2)보다 먼저다.
    assert [x['external_id'] for x in body['items']] == ['SM', 'SR', 'SX', 'SL1', 'SL2']
    by_id = {x['external_id']: x for x in body['items']}
    assert [by_id[k]['screen']['outcome'] for k in ('SM', 'SR', 'SX')] == ['api_match', 'needs_check', 'api_mismatch']
    # 원문 링크만 보여줄 정책에는 걸러보기 결과를 만들지 않는다.
    assert by_id['SL1']['screen'] is None and by_id['SL1']['reasons'] == ['no_region_code']
    assert by_id['SL2']['screen'] is None and by_id['SL2']['period_status'] == 'ended'
    assert all(x['screen']['qualification_determined'] is False for x in body['items'] if x['screen'])


def test_screen_catalog_filters_paging_and_reference_date(ctx):
    catalog(ctx)
    only = post(ctx, outcome='needs_check').json()
    assert [x['external_id'] for x in only['items']] == ['SR'] and only['total'] == 1
    assert only['outcomes'] == {'api_match': 1, 'needs_check': 1, 'api_mismatch': 1}
    assert {x['external_id'] for x in post(ctx, tier='link_only').json()['items']} == {'SL1', 'SL2'}
    assert [x['external_id'] for x in post(ctx, q='sr').json()['items']] == ['SR']
    pages = [post(ctx, page=p, page_size=2).json() for p in (1, 2, 3)]
    assert all(p['total'] == 5 and p['pages'] == 3 for p in pages) and [len(p['items']) for p in pages] == [2, 2, 1]
    # 기준일이 신청기간 뒤면 같은 정책도 걸러보기 대상에서 빠진다.
    later = ctx.post(SCREEN, json={'profile': PROFILE, 'on': '2027-01-01'}).json()
    assert later['tiers'] == {'reviewed': 0, 'screenable': 1, 'link_only': 4}
    assert [x['external_id'] for x in later['items'] if x['screen']] == ['SR']


def test_catalog_uses_source_check_only_for_unchanged_api_content(ctx, tmp_path, monkeypatch):
    seed([good('C1')])
    with connect() as con:
        sha = con.execute("SELECT sha256 FROM ontong_candidates WHERE external_id='C1'").fetchone()[0]
    (tmp_path / 'data').mkdir()
    checks = tmp_path / 'data' / 'source_checks.json'
    write = lambda code: checks.write_text(json.dumps([{'external_id': 'C1', 'api_sha256': sha,
                                                        'official_status': 'closed', 'policy_code': code}]), encoding='utf-8')
    monkeypatch.setattr(ontong, 'BASE', tmp_path)
    one = lambda: post(ctx).json()['items'][0]
    write('not_approved')
    assert (one()['period_status'], one()['tier'], one()['screen']) == ('closed_official', 'link_only', None)
    # 승인된 정책과 연결된 수집 정책만 '검수 통과' 갈래가 된다(여기서는 가상 정책).
    write('demo_rent')
    assert one()['tier'] == 'reviewed' and one()['screen']['outcome'] == 'api_mismatch'
    # API 내용이 바뀌면 예전 공식 종료 기록을 계속 쓰지 않는다.
    seed([good('C1', plcyExplnCn='내용 변경')])
    assert (one()['period_status'], one()['tier']) == ('open', 'reviewed')


def test_bundle_carries_structure_without_claiming_verification(ctx):
    seed([good('B1', aplyPrdSeCd='0057002')])
    bundle = ctx.get('/api/integrations/ontong/candidates/B1').json()
    assert bundle['period_status'] == 'rolling' and bundle['tier'] == {'tier': 'screenable', 'reasons': []}
    assert bundle['structured']['verified_against_notice'] is False and bundle['review_status'] == 'unreviewed'
    assert bundle['structured']['age']['kind'] == 'range' and bundle['structured']['region']['sido_names'] == ['서울특별시']


def test_regions_and_screening_write_nothing(ctx):
    catalog(ctx)
    before = snapshot()
    regions = ctx.get('/api/integrations/ontong/regions').json()
    assert regions['sido'] == SIDO and len(SIDO) == 16 and regions['sido']['12'] == '전남광주통합특별시' and '국민취업지원제도' in regions['benefits']
    for body in ({}, {'outcome': 'api_match'}, {'tier': 'link_only'}, {'q': '정책', 'page': 2, 'page_size': 2}):
        assert post(ctx, **body).status_code == 200
    assert post(ctx, {}).status_code == 200 and post(ctx, {'job_code': '0013099'}).status_code == 422
    assert snapshot() == before


def test_screen_catalog_category_filter(ctx):
    seed([good('K1', lclsfNm='주거'), good('K2', lclsfNm='일자리')])
    body = post(ctx, category='주거').json()
    assert [x['external_id'] for x in body['items']] == ['K1'] and body['tiers']['screenable'] == 1
    assert post(ctx, category='x' * 81).status_code == 422


# ── 대화로 찾기·정책별 비교 (모델은 모의 응답. 실제 Ollama 증거가 아니다) ──
import desk_finder
ASK = '/api/integrations/ontong/ask'


def picked(**over):
    return {'keywords': [], 'age': None, 'sido': '', 'job_code': '', **over}


def test_keywords_search_body_text_and_rank_name_hits_first(ctx):
    seed([good('W1', plcyNm='청년 역량 지원', plcySprtCn='자격시험 응시료 실비'), good('W2', plcyNm='자격증 응시료 지원'),
          good('W3', plcyNm='월세 지원')])
    body = post(ctx, keywords=['응시료', '없는말']).json()
    assert [x['external_id'] for x in body['items']] == ['W2', 'W1'] and body['total'] == 2
    assert post(ctx, keywords=['a'] * 5).status_code == 422 and post(ctx, keywords=['']).status_code == 422


def test_single_policy_comparison(ctx):
    seed([good('P1'), good('P2', zipCd='')])
    url = '/api/integrations/ontong/candidates/%s/screen'
    # 실제 시계 기준이라 기간 결과는 고정하지 않고 나이·지역만 본다.
    body = ctx.post(url % 'P1', json=PROFILE).json()
    results = {c['key']: c['result'] for c in body['screen']['criteria']}
    assert results['age'] == 'match' and results['region'] == 'match' and body['screen']['qualification_determined'] is False
    assert ctx.post(url % 'P2', json=PROFILE).json()['screen'] is None  # 원문 링크만
    assert ctx.post(url % 'none', json=PROFILE).status_code == 404
    assert ctx.post(url % 'P1', json={'job_code': '0013099'}).status_code == 422


def test_ask_uses_model_only_for_arguments(ctx, monkeypatch):
    catalog(ctx)
    seed([good('SE', plcyNm='자격증 응시료 지원')])
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked(keywords=['응시료'], age=27, sido='11', job_code='0013003'))
    before = snapshot()
    body = ctx.post(ASK, json={'message': '서울 사는 27살인데 자격증 시험 쳤어. 지원받을 수 있어?', 'profile': PROFILE, 'on': '2026-11-17'}).json()
    assert body['keywords'] == ['응시료'] and body['total'] == 1 and body['items'][0]['external_id'] == 'SE'
    assert body['outcomes']['api_match'] == 1 and "'응시료' 관련 정책 1건" in body['answer']
    assert body['answer_origin'] == 'validated_template'
    # 저장된 값과 다른 것만 제안한다(나이 26→27, 시도 추가). 같은 취업 상태는 다시 묻지 않는다.
    assert body['profile_suggestion'] == {'age': 27, 'sido': '11'}
    assert snapshot() == before


def test_ask_without_profile_does_not_claim_matches(ctx, monkeypatch):
    catalog(ctx)
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked())
    body = ctx.post(ASK, json={'message': '나에게 맞는 정책 찾아줘', 'on': '2026-11-17'}).json()
    assert body['compared'] is False and body['total'] == 5 and '비교하지 않았어요' in body['answer']
    assert all(x['screen'] is None for x in body['items'])
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked(keywords=['없는주제']))
    assert '찾지 못했어요' in ctx.post(ASK, json={'message': 'x', 'profile': PROFILE}).json()['answer']


def test_ask_failure_modes(ctx, monkeypatch):
    # 모델이 꺼졌거나 응답이 틀려도 멈추지 않고 낱말로 찾되, AI가 한 것처럼 보이지 않게 표시한다.
    seed([good('FB1', plcyNm='청년 월세 지원'), good('FB2', plcyNm='면접 정장 대여', plcyExplnCn='면접 준비')])  # 기본 설명 글에 '월세'가 있어 바꿔 둔다
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': False})
    off = ctx.post(ASK, json={'message': '26살인데 월세 지원 있어?', 'on': '2026-11-17'}).json()
    assert off['ai'] == 'unavailable' and off['keywords'] == ['월세'] and off['answer'].startswith('로컬 AI가 꺼져 있어 낱말로 찾았어요.')
    assert off['tools'][0]['tool'] == 'keyword_match' and off['total'] == 1 and off['profile_suggestion'] == {'age': 26}
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    def broken(m): raise ValueError('schema')
    monkeypatch.setattr(desk_finder, 'generate', broken)
    bad = ctx.post(ASK, json={'message': '면접 준비'}).json()
    assert bad['ai'] == 'invalid' and bad['keywords'] == ['면접'] and '검증하지 못해' in bad['answer']
    # 모델이 이미 답하는 중이면 기다리게 하지 않고 거절한다.
    desk_finder.LLM_LOCK.acquire()
    try:
        assert ctx.post(ASK, json={'message': '월세'}).status_code == 429
    finally:
        desk_finder.LLM_LOCK.release()
    assert ctx.post(ASK, json={'message': ''}).status_code == 422
    assert ctx.post(ASK, json={'message': '월세', 'profile': {'sido': '99'}}).status_code == 422
    # 프로필과 어긋나는 제안(다른 시도)은 버린다.
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked(sido='26'))
    body = ctx.post(ASK, json={'message': '부산 살아', 'profile': {'region_code': '11305'}}).json()
    assert body['profile_suggestion'] == {}
    # 모델이 나이 27을 시도 코드 27(대구)로 골라도, 말에 있는 지역 이름(부산)으로만 정한다. 말에 없는 나이도 버린다.
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked(sido='27', age=31))
    # 모델이 지어낸 나이(31)는 버리고, 말에 있는 '27살'은 코드가 읽는다.
    assert ctx.post(ASK, json={'message': '부산 사는 27살이야'}).json()['profile_suggestion'] == {'age': 27, 'sido': '26'}
    # 이름표에 있는 시군구 이름은 코드가 읽는다. 긴 이름을 먼저 보고(강동구 ≠ 동구), 여러 곳에 있는 이름은 정하지 않는다.
    suggest = lambda message, profile={}: ctx.post(ASK, json={'message': message, 'profile': profile}).json()['profile_suggestion']
    assert suggest('강북구 살아') == {'sido': '11', 'region_code': '11305'}
    assert suggest('강동구로 이사했어') == {'sido': '11', 'region_code': '11740'}
    assert suggest('서구 살아') == {} and suggest('서구 살아', {'sido': '27'}) == {'region_code': '27170'}


@pytest.mark.parametrize('bad', [
    {'keywords': 'x', 'age': None, 'sido': '', 'job_code': ''}, picked(age=200), picked(age=True), picked(sido='99'),
    picked(job_code='0013010'), picked(keywords=['a'] * 5), {'keywords': []}, picked(extra=1), []])
def test_model_output_is_validated(bad):
    with pytest.raises(ValueError):
        desk_finder.check(bad)


def test_model_output_keywords_are_cleaned():
    assert desk_finder.check(picked(keywords=[' 응시료 ', '', '응시료', 'x' * 21]))['keywords'] == ['응시료']
    # 숫자·한 글자 검색어는 거의 모든 정책에 걸리므로 버린다.
    assert desk_finder.check(picked(keywords=['26', '구', '26살', '월세']))['keywords'] == ['월세']


# ── 신청 계획 ────────────────────────────────────────────────────────
def plan_of(ctx, ids, profile=PROFILE, **body):
    wid = ctx.post('/api/desk/workspaces').json()['id']
    return wid, ctx.post(f'/api/desk/workspaces/{wid}/plan', json={'external_ids': ids, 'profile': profile, 'on': '2026-11-17', **body})


def test_plan_merges_documents_orders_by_api_deadline_and_writes_nothing(ctx):
    seed([good('D1', aplyYmd='20261101 ~ 20261130', sbmsnDcmntCn='신청서, 주민등록초본, 통장사본'),
          good('D2', aplyYmd='20261101 ~ 20261120', sbmsnDcmntCn='주민등록초본 1부, 응시확인서, 결제 영수증'),
          good('D3', aplyPrdSeCd='0057002', sbmsnDcmntCn=''), good('D4', aplyYmd='20260101 ~ 20260131', sbmsnDcmntCn='')])
    wid = ctx.post('/api/desk/workspaces').json()['id']
    before = snapshot()
    body = ctx.post(f'/api/desk/workspaces/{wid}/plan', json={'external_ids': ['D4', 'D3', 'D1', 'D2', 'D1'], 'profile': PROFILE, 'on': '2026-11-17'}).json()
    assert snapshot() == before and body['saved'] is False and body['overlap_checked'] is False
    # 접수 중(마감 빠른 순) → 상시 → 마감. 상시·마감은 날짜를 만들지 않는다.
    assert body['order'] == ['D2', 'D1', 'D3', 'D4']
    by_id = {p['external_id']: p for p in body['policies']}
    assert by_id['D2']['period_label'] == 'D-3 (API 마감일)' and by_id['D1']['deadline'] == '2026-11-30'
    assert by_id['D3']['deadline'] is None and by_id['D3']['period_label'] == '상시(API)' and by_id['D4']['deadline'] is None
    docs = {d['key']: d['policies'] for d in body['documents']}
    assert docs == {'resident_abstract': ['D1', 'D2'], 'bankbook': ['D1'], 'exam': ['D2'], 'receipt': ['D2'], 'application': ['D1']}
    # 서류 안내가 비어 있으면 '서류 없음'이 아니라 '안내 없음'으로 따로 남는다.
    assert body['documents_unlisted'] == ['D4', 'D3']  # 요청한 순서
    assert {c['key']: c['result'] for c in by_id['D1']['criteria']}['age'] == 'match'
    assert [t['key'] for t in by_id['D1']['tasks']] == ['period', 'conditions', 'documents'] and by_id['D1']['preview_token']


def test_plan_without_profile_skips_comparison(ctx):
    seed([good('E1')])
    _, r = plan_of(ctx, ['E1'], profile={})
    assert r.json()['policies'][0]['criteria'] is None


def test_plan_token_approves_through_existing_confirm(ctx):
    seed([good('F1')])
    wid, r = plan_of(ctx, ['F1'])
    token = r.json()['policies'][0]['preview_token']
    saved = ctx.post(f'/api/desk/workspaces/{wid}/policies/F1/confirm', json={'approved': True, 'preview_token': token})
    assert saved.status_code == 200 and len(saved.json()['tasks']) == 3


def test_plan_rejects_bad_requests(ctx):
    seed([good('G1')])
    assert plan_of(ctx, ['none'])[1].status_code == 404
    assert plan_of(ctx, [])[1].status_code == 422 and plan_of(ctx, ['G1'] * 6)[1].status_code == 422
    assert plan_of(ctx, ['G1'], profile={'sido': '99'})[1].status_code == 422
    assert plan_of(ctx, ['G1'], on='2026-2-1')[1].status_code == 422
    assert ctx.post('/api/desk/workspaces/missing/plan', json={'external_ids': ['G1']}).status_code == 404


# ── 시도 전체 대상 · 되묻기 ──────────────────────────────────────────
def test_whole_sido_policy_matches_sido_only_profile():
    from policy_structure import SIDO_SETS
    assert set(SIDO_SETS) == set(SIDO)
    codes = sorted(SIDO_SETS['11'][0])
    whole, partial = ','.join(codes), ','.join(codes[1:])
    assert region({'zipCd': whole})['full_sido'] == ['11'] and region({'zipCd': whole})['nationwide'] is False
    assert verdict(made(zipCd=whole), {'sido': '11'})[1]['region'] == 'match'
    assert verdict(made(zipCd=whole), {'sido': '26'})[1]['region'] == 'mismatch'
    # 시군구가 하나라도 빠지면 '시도 전체'로 보지 않는다.
    assert region({'zipCd': partial})['full_sido'] == []
    assert verdict(made(zipCd=partial), {'sido': '11'})[1]['region'] == 'unknown'


def test_ask_asks_one_missing_fact_in_order(ctx, monkeypatch):
    catalog(ctx)
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked())
    ask = lambda profile, message='월세': ctx.post(ASK, json={'message': message, 'profile': profile, 'on': '2026-11-17'}).json()['question']
    first = ask({})
    assert first['key'] == 'sido' and len(first['options']) == 16
    # 시도 다음에는 이름표가 있는 시도에 한해 시군구를 묻는다(서울 25개 구). 이름표가 없는 시도(울산)는 건너뛴다.
    area = ask({'sido': '11'})
    assert area['key'] == 'region_code' and len(area['options']) == 25 and {'value': '11305', 'label': '강북구'} in area['options']
    assert ask({'sido': '31'})['key'] == 'age' and ask({'sido': '31'})['options'] == []
    job = ask({'region_code': '11305', 'age': 26})
    assert job['key'] == 'job_code' and '0013010' not in [o['value'] for o in job['options']]
    benefits = ask({'region_code': '11305', 'age': 26, 'job_code': '0013003'})
    assert benefits['key'] == 'benefits' and benefits['options'][-1] == {'value': '', 'label': '없어요'}
    # '없어요'([])도 답한 것으로 보고 다시 묻지 않는다.
    assert ask({'sido': '31', 'age': 26, 'job_code': '0013003', 'benefits': []}) is None
    assert ask({'region_code': '11305', 'age': 0, 'job_code': '0013003', 'benefits': ['청년수당']}) is None  # 0세도 '입력함', 시군구가 있으면 시도를 묻지 않음
    # 방금 말에서 읽은 지역은 제안으로 가고, 다음으로 모르는 나이를 묻는다.
    assert ask({}, '부산 살아')['key'] == 'age'


def test_same_policy_registered_twice_is_shown_once(ctx):
    seed([good('H1', plcyNm='같은 정책'), good('H2', plcyNm='같은 정책', aplyYmd='20250101 ~ 20250131'),
          good('H3', plcyNm='같은 정책', zipCd='26110'), good('H4', plcyNm='다른 정책')])
    body = post(ctx).json()
    by_id = {x['external_id']: x for x in body['items']}
    # 지난 회차(H2)는 비교 가능한 최신 등록(H1)에 묶이고, 지역이 다른 정책(H3)은 따로 남는다.
    assert set(by_id) == {'H1', 'H3', 'H4'} and body['total'] == 3 and body['merged'] == 1
    assert by_id['H1']['same_policy_count'] == 2 and by_id['H3']['same_policy_count'] == 1
    assert body['tiers'] == {'reviewed': 0, 'screenable': 3, 'link_only': 0}
    from screening import screen_catalog
    assert screen_catalog(PROFILE, DAY, dedupe=False)['total'] == 4


def test_one_sided_age_says_which_side_is_missing():
    out, results = verdict(made(sprtTrgtMinAge='0', sprtTrgtMaxAge='34'), {'age': 26})
    basis = next(c['basis'] for c in out['criteria'] if c['key'] == 'age')
    assert results['age'] == 'unknown' and '최대 34세만' in basis


# ── 공식 페이지 보완 기록 ────────────────────────────────────────────
def test_supplement_file_keeps_source_quote_and_unverified_mark():
    rows = json.loads((Path(ontong.BASE) / 'data' / 'supplements.json').read_text(encoding='utf-8'))
    assert rows
    for x in rows:
        assert set(x) - {'rules'} == {'external_id', 'field', 'value', 'quotes', 'source_url', 'source_title', 'checked_on', 'checked_by', 'verified'}
        # 공식 페이지에서 찾은 규칙은 엔진이 읽는 형식이어야 하고, 근거 문장이 함께 있어야 한다.
        for rule in x.get('rules', []):
            assert set(rule) == {'id', 'type', 'predicate', 'message'} and rule['type'] in ('required', 'exclude')
            validate_predicate(rule['predicate'])
        assert x['field'] in ('documents', 'period', 'method', 'conditions') and x['value'] and x['source_title']
        assert x['quotes'] and all(isinstance(q, str) and q.strip() for q in x['quotes'])
        assert x['source_url'].startswith('https://') and date.fromisoformat(x['checked_on'])
        # 사람이 검수하지 않은 기록을 검수된 것처럼 두지 않는다.
        assert x['verified'] is False and '사람 검수 아님' in x['checked_by']


def test_supplement_fills_blank_documents_without_touching_collected_data(ctx, tmp_path, monkeypatch):
    seed([good('U1', sbmsnDcmntCn=''), good('U2', sbmsnDcmntCn=''), good('U3', sbmsnDcmntCn='신청서')])
    (tmp_path / 'data').mkdir()
    entry = lambda eid: {'external_id': eid, 'field': 'documents', 'value': '응시 확인 서류', 'quotes': ['응시사실 확인서류 첨부하여 신청'],
                         'source_url': 'https://example.org/notice', 'source_title': '안내', 'checked_on': '2026-11-18',
                         'checked_by': '웹 확인; 사람 검수 아님', 'verified': False}
    (tmp_path / 'data' / 'supplements.json').write_text(json.dumps([entry('U1'), entry('U3')], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(ontong, 'BASE', tmp_path)
    bundle = ctx.get('/api/integrations/ontong/candidates/U1').json()
    assert bundle['supplements'][0]['value'] == '응시 확인 서류' and bundle['public_fields']['sbmsnDcmntCn'] == ''
    assert ctx.get('/api/integrations/ontong/candidates/U2').json()['supplements'] == []
    body = plan_of(ctx, ['U1', 'U2', 'U3'])[1].json()
    by_id = {p['external_id']: p for p in body['policies']}
    assert by_id['U1']['documents_source'] == 'web_check' and by_id['U3']['documents_source'] == 'api'
    assert by_id['U3']['documents_text'] == '신청서'  # API에 값이 있으면 보완 기록으로 덮지 않는다
    assert body['documents_unlisted'] == ['U2']
    assert {d['key']: d['policies'] for d in body['documents']} == {'exam': ['U1'], 'application': ['U3']}


# ── 참여 제한 문장 · 서로 막는 정책 ──────────────────────────────────
def test_exclusion_sentences_are_kept_verbatim_and_block_a_clean_match():
    from policy_structure import exclusions
    text = '- 2026년 서울 청년수당, 국민취업지원제도(1,2유형) 참여자는 지원 제외\n- 재학생 및 휴학생\n① 2026년 타자치구 유사사업 참여자 지원 제외'
    found = exclusions({'ptcpPrpTrgtCn': text, 'addAplyQlfcCndCn': '서울 거주자. 공공임대주택 입주자는 신청 불가'})
    assert found['sentences'] == ['2026년 서울 청년수당, 국민취업지원제도(1,2유형) 참여자는 지원 제외', '재학생 및 휴학생',
                                  '2026년 타자치구 유사사업 참여자 지원 제외', '공공임대주택 입주자는 신청 불가']
    assert found['count'] == 4 and exclusions({})['sentences'] == []
    # 다른 조건이 모두 맞아도 참여 제한 안내가 있으면 '확인 필요'다.
    clean, _ = verdict(made(), PROFILE)
    out, results = verdict(made(ptcpPrpTrgtCn=text), PROFILE)
    assert clean['outcome'] == 'api_match' and 'exclusion' not in {c['key'] for c in clean['criteria']}
    assert out['outcome'] == 'needs_check' and results['exclusion'] == 'unknown' and out['to_confirm'] == ['exclusion']
    assert '서울 청년수당' in next(c['basis'] for c in out['criteria'] if c['key'] == 'exclusion')


def test_income_text_median_percent_is_structured_but_not_compared():
    item = made(earnCndSeCd='0043003', earnEtcCn='기준 중위소득 150% 이하 (건강보험료 기준), 중위소득 60%초과')
    assert item['income']['median_pct'] == [60, 150] and item['income']['comparable'] is False
    out, results = verdict(item, {})
    assert results['income'] == 'unknown' and '60%·150%' in next(c['basis'] for c in out['criteria'] if c['key'] == 'income')


def test_plan_flags_conflicts_in_the_direction_the_text_says(ctx):
    seed([good('X1', plcyNm='중랑구 미취업청년 자격증 응시료 지원사업', ptcpPrpTrgtCn='2026년 서울 청년수당, 국민취업지원제도 참여자는 지원 제외'),
          good('X2', plcyNm='2026 서울시 청년수당'),
          good('X3', plcyNm='청주시 자격증 시험 응시료 지원사업', ptcpPrpTrgtCn='정부 및 타 지자체 동일/유사사업 수혜자'),
          good('X4', plcyNm='청년 문화패스')])
    body = plan_of(ctx, ['X1', 'X2', 'X3', 'X4'])[1].json()
    found = {(c['from'], c['to']): c['kind'] for c in body['conflicts']}
    # X1의 글이 X2(청년수당)를 이름으로 가리킨다. X2의 글에는 그런 문장이 없으므로 X2→X1은 만들지 않는다.
    assert found[('X1', 'X2')] == 'named' and ('X2', 'X1') not in found
    # X3의 '유사사업' 문구는 같은 주제(응시료)인 X1에만 걸린다.
    assert found[('X3', 'X1')] == 'similar' and ('X3', 'X2') not in found and ('X3', 'X4') not in found
    assert all(c['quote'] for c in body['conflicts']) and body['overlap_checked'] is False
    assert plan_of(ctx, ['X2', 'X4'])[1].json()['conflicts'] == []


def test_current_benefit_named_in_exclusion_text_is_a_mismatch(ctx):
    limited = made(ptcpPrpTrgtCn='- 2026년 서울 청년수당, 국민취업지원제도(1,2유형) 참여자는 지원 제외\n- 재학생 및 휴학생')
    basis = lambda out: next(c['basis'] for c in out['criteria'] if c['key'] == 'exclusion')
    out, results = verdict(limited, {**PROFILE, 'benefits': ['국민취업지원제도']})
    assert results['exclusion'] == 'mismatch' and out['outcome'] == 'api_mismatch'
    assert '받고 있는 지원(국민취업지원제도)' in basis(out) and '지원 제외' in basis(out)
    # 문장에 없는 지원, '없음', 묻지 않음은 모두 '확인 필요'로 남는다(없다고 해서 통과가 아니다).
    for benefits in (['청년도약계좌'], [], None):
        out, results = verdict(limited, {**PROFILE, 'benefits': benefits})
        assert results['exclusion'] == 'unknown' and out['outcome'] == 'needs_check'
    # 참여 제한 문장이 없는 정책은 받는 지원이 있어도 영향을 받지 않는다.
    assert verdict(made(), {**PROFILE, 'benefits': ['국민취업지원제도']})[0]['outcome'] == 'api_match'
    with pytest.raises(ValueError):
        validate_profile({'benefits': ['없는 지원']})
    assert post(ctx, {'benefits': ['없는 지원']}).status_code == 422 and post(ctx, {'benefits': ['청년수당']}).status_code == 200


def test_no_benefits_alone_is_not_a_comparison(ctx, monkeypatch):
    from screening import provided
    assert provided({'benefits': []}) is False and provided({'benefits': ['청년수당']}) is True and provided({'age': 0}) is True
    catalog(ctx)
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked())
    body = ctx.post(ASK, json={'message': '찾아줘', 'profile': {'benefits': []}, 'on': '2026-11-17'}).json()
    assert body['compared'] is False and '비교하지 않았어요' in body['answer']


# ── 시군구 이름표 · 거주 기간 · 마감 임박 순 ─────────────────────────
def test_district_table_and_district_level_matching(ctx):
    from policy_structure import SIGUNGU, SIDO_SETS
    assert SIGUNGU['11305'] == '강북구' and sum(c.startswith('11') for c in SIGUNGU) == 25
    assert all(c[:2] in SIDO and len(c) == 5 for c in SIGUNGU)
    assert set(SIDO_SETS['11'][0]) == {c for c in SIGUNGU if c.startswith('11')}  # 전국 정책이 넣는 서울 묶음과 같은 25곳
    assert ctx.get('/api/integrations/ontong/regions').json()['sigungu']['11305'] == '강북구'
    seoul = ','.join(sorted(SIDO_SETS['11'][0]))
    me = {'region_code': '11305'}
    assert verdict(made(zipCd=seoul), me)[1]['region'] == 'match'          # 서울 전체 대상
    assert verdict(made(zipCd='11305'), me)[1]['region'] == 'match'        # 강북구 정책
    assert verdict(made(zipCd='11260'), me)[1]['region'] == 'mismatch'     # 중랑구 정책


def test_residence_duration_in_text_keeps_region_unconfirmed():
    item = made(zipCd='11305', addAplyQlfcCndCn='신청일 기준 강북구에 1년 이상 계속 거주한 청년')
    assert item['region']['residence_min_months'] == 12
    out, results = verdict(item, {'region_code': '11305'})
    assert results['region'] == 'unknown' and '12개월 이상 거주' in next(c['basis'] for c in out['criteria'] if c['key'] == 'region')
    assert verdict(item, {'region_code': '11260'})[1]['region'] == 'mismatch'   # 지역이 다르면 그대로 달라요
    assert made(addAplyQlfcCndCn='6개월 이상 주민등록')['region']['residence_min_months'] == 6
    assert made()['region']['residence_min_months'] is None


def test_matches_are_ordered_by_nearest_api_deadline(ctx):
    seed([good('T1', aplyYmd='20261101 ~ 20261231'), good('T2', aplyYmd='20261101 ~ 20261120'),
          good('T3', aplyYmd='20261201 ~ 20261231'), good('T4', aplyYmd='20261101 ~ 20261125')])
    items = post(ctx).json()['items']
    # 접수 중(T2 → T4 → T1, 마감 빠른 순) 다음에 시작 전(T3, 확인 필요)
    assert [x['external_id'] for x in items] == ['T2', 'T4', 'T1', 'T3']
    assert items[0]['period_label'] == 'D-3 (API 마감일)' and items[0]['deadline'] == '2026-11-20'
    assert items[3]['period_label'] == '2026-12-01 시작(API)'


# ── 취약점 보완 · 검수용 초안 ────────────────────────────────────────
def test_security_headers_and_no_inline_script(ctx):
    for path in ('/', '/classic', '/lab', '/api/health', '/static/mobile.js'):
        headers = ctx.get(path).headers
        assert headers['x-content-type-options'] == 'nosniff' and headers['x-frame-options'] == 'DENY'
        assert "script-src 'self'" in headers['content-security-policy'] and "frame-ancestors 'none'" in headers['content-security-policy']
    assert 'content-security-policy' not in ctx.get('/docs').headers   # API 문서는 외부 스크립트를 쓴다
    import re
    for name in ('mobile.html', 'desk.html', 'index.html'):
        html = (Path(ontong.BASE) / 'static' / name).read_text(encoding='utf-8')
        assert not re.search(r'\son[a-z]+\s*=', html) and not re.search(r'<script(?![^>]*\ssrc=)', html), name


def test_markup_in_policy_text_is_returned_as_data(ctx):
    # 화면은 esc()로 그리지만, 서버도 값을 바꾸지 않고 JSON 문자열로만 돌려준다(실행되는 HTML로 내보내지 않는다).
    seed([good('XS1', plcyNm='<img src=x onerror=alert(1)> 지원', ptcpPrpTrgtCn='<script>alert(1)</script> 제외')])
    r = post(ctx)
    assert r.headers['content-type'].startswith('application/json') and r.json()['items'][0]['name'].startswith('<img')


def test_catalog_cache_follows_data_changes(ctx):
    import screening
    seed([good('CA1')])
    assert post(ctx).json()['total'] == 1
    first = screening._CACHE['rows']
    assert post(ctx, q='CA1').json()['total'] == 1 and screening._CACHE['rows'] is first   # 같은 자료면 다시 만들지 않는다
    seed([good('CA1', zipCd='26110'), good('CA2')])                                        # 내용이 바뀌면 새로 만든다
    body = post(ctx).json()
    assert body['total'] == 2 and screening._CACHE['rows'] is not first
    assert {x['external_id']: x['screen']['outcome'] for x in body['items']} == {'CA1': 'api_mismatch', 'CA2': 'api_match'}


def test_draft_policy_is_valid_unapproved_and_keeps_unknowns_as_checks():
    import sys
    sys.path.insert(0, str(Path(ontong.BASE) / 'tools'))
    from draft_policy import draft
    payload = {**BASE, 'plcyNo': 'DR-1', 'plcyNm': '성북구 응시료 지원', 'refUrlAddr1': 'https://example.go.kr/notice', 'jobCd': '0013003',
               'earnCndSeCd': '0043002', 'earnEtcCn': '중위소득 150% 이하', 'ptcpPrpTrgtCn': '국민취업지원제도 참여자 제외',
               'addAplyQlfcCndCn': '1년 이상 거주', 'sbmsnDcmntCn': '신청서, 주민등록초본'}
    note = {'field': 'conditions', 'quotes': ['공고 문장'], 'source_url': 'https://example.go.kr/a', 'source_title': '공고'}
    policy = draft(payload, [note])
    assert policy['review'] == {'status': 'draft', 'reviewed_by': '', 'reviewed_at': None} and policy['demo_only'] is False
    assert all(s['verified'] is False for s in policy['sources']) and [s['ref'] for s in policy['sources']] == ['api', 'web1']
    assert {r['id'] for r in policy['rules']} == {'age', 'region', 'employment'}
    # 규칙으로 옮길 수 없는 것은 버리지 않고 사람이 볼 항목으로 남긴다.
    assert {'period', 'district', 'residence', 'income', 'exclusion1', 'documents'} <= {c['id'] for c in policy['manual_checks']}
    assert [d['code'] for d in policy['documents']] == ['resident_abstract', 'application']
    with pytest.raises(ValueError):
        draft({**payload, 'refUrlAddr1': 'http://example.go.kr'})          # https 출처가 없으면 만들지 않는다
    with pytest.raises(ValueError):
        draft({**payload, 'sprtTrgtMinAge': '0', 'sprtTrgtMaxAge': '0', 'zipCd': '47130', 'jobCd': '0013010'})  # 옮길 규칙이 없으면 만들지 않는다


# ── 실제 데이터·실제 모델 검증에서 찾아 고친 것 ──────────────────────
def test_model_keywords_are_filtered_by_code():
    clean = lambda words: desk_finder.check(picked(keywords=words))['keywords']
    assert clean(['전세 대출']) == ['전세', '대출']                       # 띄어 쓴 검색어는 낱말로
    assert clean(['취준생']) == [] and clean(['프리랜서', '월세']) == ['월세']   # 내 정보 낱말은 검색어가 아니다
    assert clean(['모든 정책 신청 가능']) == []                           # 공격 문장으로 들어온 뜻 없는 낱말
    assert clean(['서울', '부산광역시', '대학생']) == [] and clean(['청년', '지원', '응시료']) == ['응시료']


def test_job_is_read_only_from_the_users_own_words(ctx, monkeypatch):
    catalog(ctx)
    monkeypatch.setattr(desk_finder, 'model_status', lambda: {'ready': True})
    monkeypatch.setattr(desk_finder, 'generate', lambda m: picked(job_code='0013003'))   # 모델이 지어낸 값
    suggest = lambda message: ctx.post(ASK, json={'message': message, 'on': '2026-11-17'}).json()['profile_suggestion']
    assert suggest('대학생인데 생활비 지원 있어?') == {}
    assert suggest('취준생인데 뭐 받을 수 있어') == {'job_code': '0013003'}
    assert suggest('회사 다니는 29살이야') == {'job_code': '0013001', 'age': 29}
    assert suggest('취준하다가 프리랜서 하는 중') == {}                    # 둘 다 나오면 정하지 않는다
    assert ctx.post(ASK, json={'message': '   '}).status_code == 422


def test_placeholder_upper_age_is_shown_as_such():
    out, results = verdict(made(sprtTrgtMinAge='19', sprtTrgtMaxAge='999'), {'age': 26})
    basis = next(c['basis'] for c in out['criteria'] if c['key'] == 'age')
    assert results['age'] == 'match' and '19세 이상' in basis and '999' in basis and '19~999' not in basis
    assert verdict(made(sprtTrgtMinAge='19', sprtTrgtMaxAge='999'), {'age': 18})[1]['age'] == 'mismatch'
    import sys
    sys.path.insert(0, str(Path(ontong.BASE) / 'tools'))
    from draft_policy import draft
    policy = draft({**BASE, 'plcyNo': 'DR-2', 'plcyNm': '봉사단', 'refUrlAddr1': 'https://example.go.kr/n', 'sprtTrgtMaxAge': '999'})
    rule = next(r for r in policy['rules'] if r['id'] == 'age')
    assert rule['predicate'] == {'fact': 'age', 'op': 'gte', 'value': 19} and any(c['id'] == 'age' for c in policy['manual_checks'])


def test_rules_found_on_official_pages_fill_ruleless_drafts():
    import sys
    sys.path.insert(0, str(Path(ontong.BASE) / 'tools'))
    from draft_policy import draft
    # API에 최대 나이만 있고 전국·제한없음이라 규칙으로 옮길 값이 없는 정책
    payload = {**BASE, 'plcyNo': 'DR-3', 'plcyNm': '응시료 지원', 'refUrlAddr1': 'https://example.go.kr/n', 'sprtTrgtMinAge': '0', 'sprtTrgtMaxAge': '34', 'zipCd': ALL}
    with pytest.raises(ValueError):
        draft(payload)
    note = {'field': 'conditions', 'quotes': ['가. 지원대상: 만 34세 이하 청년 누구나'], 'source_url': 'https://example.or.kr/notice', 'source_title': '안내문',
            'rules': [{'id': 'age', 'type': 'required', 'predicate': {'fact': 'age', 'op': 'lte', 'value': 34}, 'message': '만 34세 이하'}]}
    policy = draft(payload, [note])
    rule = policy['rules'][0]
    assert rule['predicate'] == {'fact': 'age', 'op': 'lte', 'value': 34} and rule['source_ref'] == 'web1'
    source = next(s for s in policy['sources'] if s['ref'] == 'web1')
    assert source['excerpt'] == '가. 지원대상: 만 34세 이하 청년 누구나' and source['verified'] is False and policy['review']['status'] == 'draft'
    # API에 같은 항목의 규칙이 있으면 공식 페이지 규칙으로 바꾼다(둘 다 두지 않는다).
    both = draft({**payload, 'sprtTrgtMinAge': '19'}, [note])
    assert [r['predicate']['op'] for r in both['rules'] if r['id'] == 'age'] == ['lte']
    real = json.loads((Path(ontong.BASE) / 'data' / 'supplements.json').read_text(encoding='utf-8'))
    assert sum('rules' in x for x in real) >= 6


def test_official_page_age_rule_decides_where_api_cannot(ctx, tmp_path, monkeypatch):
    from screening import age_rule
    api_only = made(sprtTrgtMinAge='0', sprtTrgtMaxAge='34')
    note = {'external_id': 'AR1', 'field': 'conditions', 'value': '만 34세 이하', 'quotes': ['만 34세 이하 청년 누구나'], 'source_url': 'https://example.or.kr/n',
            'source_title': '안내', 'checked_on': '2026-11-18', 'checked_by': '웹 확인; 사람 검수 아님', 'verified': False,
            'rules': [{'id': 'age', 'type': 'required', 'predicate': {'fact': 'age', 'op': 'lte', 'value': 34}, 'message': '만 34세 이하'}]}
    rule = age_rule([note])
    assert verdict(api_only, {'age': 26})[1]['age'] == 'unknown'                      # API만으로는 정하지 못한다
    out = screen(api_only, {'age': 26}, 'open', rule)
    age = next(c for c in out['criteria'] if c['key'] == 'age')
    assert age['result'] == 'match' and '공식 페이지 기준(사람 검수 전)' in age['basis'] and '만 34세 이하 청년 누구나' in age['basis']
    assert next(c for c in screen(api_only, {'age': 35}, 'open', rule)['criteria'] if c['key'] == 'age')['result'] == 'mismatch'
    assert next(c for c in screen(api_only, {}, 'open', rule)['criteria'] if c['key'] == 'age')['result'] == 'skipped'
    assert out['qualification_determined'] is False and age_rule([]) is None
    # 목록·상세·신청 계획이 같은 기준을 쓴다.
    seed([good('AR1', sprtTrgtMinAge='0', sprtTrgtMaxAge='34'), good('AR2', sprtTrgtMinAge='0', sprtTrgtMaxAge='34')])
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'supplements.json').write_text(json.dumps([note], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(ontong, 'BASE', tmp_path)
    by_id = {x['external_id']: x['screen']['outcome'] for x in post(ctx).json()['items']}
    assert by_id == {'AR1': 'api_match', 'AR2': 'needs_check'}
    detail = ctx.post('/api/integrations/ontong/candidates/AR1/screen', json=PROFILE).json()['screen']
    assert next(c for c in detail['criteria'] if c['key'] == 'age')['result'] == 'match'
    plan = plan_of(ctx, ['AR1'])[1].json()['policies'][0]
    assert next(c for c in plan['criteria'] if c['key'] == 'age')['result'] == 'match'


# ── 사람 검수 → 승인 → 엔진 판정 ────────────────────────────────────
def review_setup(ctx, tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(ontong.BASE) / 'tools'))
    from draft_policy import draft
    payload = {**BASE, 'plcyNo': 'RV1', 'plcyNm': '검수 대상 정책', 'refUrlAddr1': 'https://www.gov.kr/notice', 'zipCd': '11305',
               'ptcpPrpTrgtCn': '국민취업지원제도 참여자 제외', 'sbmsnDcmntCn': '신청서'}
    note = {'external_id': 'RV1', 'field': 'conditions', 'value': '요약', 'quotes': ['만 19세 이상 34세 이하'], 'source_url': 'https://www.gov.kr/a', 'source_title': '공고',
            'checked_on': '2026-11-18', 'checked_by': '웹 확인; 사람 검수 아님', 'verified': False}
    seed([good('RV1', plcyNm='검수 대상 정책', zipCd='11305')])
    policy = draft(payload, [note])
    (tmp_path / 'data' / 'policy_drafts').mkdir(parents=True)
    (tmp_path / 'data' / 'policy_drafts' / 'ontong-rv1.json').write_text(json.dumps(policy, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(ontong, 'BASE', tmp_path)
    return policy


def test_review_approval_needs_a_person_and_confirmed_sources(ctx, tmp_path, monkeypatch):
    draft_policy = review_setup(ctx, tmp_path, monkeypatch)
    url = '/api/review/drafts/ontong-rv1/approve'
    listed = ctx.get('/api/review/drafts').json()
    assert listed[0]['code'] == 'ontong-rv1' and listed[0]['approved'] is False and ctx.get('/api/review/drafts/none-x').status_code == 404
    body = {'reviewed_by': '검수자', 'confirmed': True, 'sources': {'api': '신청일 기준 만 19세 이상 34세 이하인 사람'}, 'keep_rules': ['age', 'region']}
    assert ctx.post(url, json={**body, 'confirmed': False}).status_code == 403            # 대조 확인 없이 승인 불가
    assert ctx.post(url, json={**body, 'reviewed_by': '  '}).status_code == 422            # 이름 없이 승인 불가
    assert ctx.post(url, json={**body, 'sources': {}}).status_code == 422                  # 확인한 출처 없이 승인 불가
    assert ctx.post(url, json={**body, 'sources': {'api': '짧'}}).status_code == 422        # 문장이 아닌 값
    assert ctx.post(url, json={**body, 'keep_rules': []}).status_code == 422               # 남긴 규칙 없이 승인 불가
    assert load_policies().get('ontong-rv1') is None and not (tmp_path / 'data' / 'policies').exists()
    done = ctx.post(url, json=body).json()
    assert done['approved'] and done['reviewed_by'] == '검수자' and done['dropped_sources'] == ['web1']
    saved = json.loads((tmp_path / 'data' / 'policies' / 'ontong-rv1.json').read_text(encoding='utf-8'))
    assert saved['review']['status'] == 'approved' and saved['review']['reviewed_by'] == '검수자' and saved['review']['reviewed_at']
    assert [x['ref'] for x in saved['sources']] == ['api'] and saved['sources'][0]['verified'] is True
    assert saved['sources'][0]['excerpt'] == '신청일 기준 만 19세 이상 34세 이하인 사람'
    # 확인이 필요한 항목은 승인해도 버리지 않는다.
    assert len(saved['manual_checks']) == len(draft_policy['manual_checks']) and all(c['source_ref'] == 'api' for c in saved['manual_checks'])
    assert 'ontong-rv1' in load_policies() and ctx.get('/api/review/drafts').json()[0]['approved_by'] == '검수자'


def test_approved_policy_is_judged_by_the_rule_engine(ctx, tmp_path, monkeypatch):
    review_setup(ctx, tmp_path, monkeypatch)
    before = post(ctx).json()['items'][0]
    assert before['tier'] == 'screenable' and before['engine'] is None
    ctx.post('/api/review/drafts/ontong-rv1/approve', json={'reviewed_by': '검수자', 'confirmed': True,
                                                           'sources': {'api': '신청일 기준 만 19세 이상 34세 이하인 사람'}, 'keep_rules': ['age', 'region']})
    item = post(ctx).json()['items'][0]
    assert item['tier'] == 'reviewed' and item['engine']['policy_code'] == 'ontong-rv1' and item['engine']['reviewed_by'] == '검수자'
    effects = {f['rule_id']: f['effect'] for f in item['engine']['findings']}
    assert effects['age'] == 'pass' and effects['region'] == 'pass'
    # 사람이 따로 볼 항목이 남아 있으므로 '신청 검토 가능'으로 올리지 않는다.
    assert item['engine']['status'] == 'needs_review' and effects['period'] == 'unknown'
    old = post(ctx, {**PROFILE, 'age': 40}).json()['items'][0]['engine']
    assert old['status'] == 'ineligible' and {f['rule_id']: f['effect'] for f in old['findings']}['age'] == 'block'
    detail = ctx.post('/api/integrations/ontong/candidates/RV1/screen', json=PROFILE).json()
    assert detail['tier'] == 'reviewed' and detail['engine']['status'] == 'needs_review'


def test_admin_only_actions_and_rate_limit(monkeypatch):
    import access
    from fastapi import HTTPException
    from types import SimpleNamespace as NS
    request = lambda host, path='/api/review/drafts', method='GET', headers=None: NS(client=NS(host=host), url=NS(path=path), method=method, headers=headers or {})
    access.require_admin(request('127.0.0.1'))
    with pytest.raises(HTTPException) as denied:
        access.require_admin(request('203.0.113.9'))
    assert denied.value.status_code == 403
    monkeypatch.setenv('ADMIN_TOKEN', 'secret-for-test')
    access.require_admin(request('203.0.113.9', headers={'x-admin-token': 'secret-for-test'}))
    with pytest.raises(HTTPException):
        access.require_admin(request('203.0.113.9', headers={'x-admin-token': 'wrong'}))
    assert [access.allow('k-test', 2, 60, now=t) for t in (0, 1, 2, 61, 62)] == [True, True, False, True, True]
    ask = request('203.0.113.50', '/api/integrations/ontong/ask', 'POST')
    assert [access.check_rate(ask) for _ in range(21)].count(None) == 20 and access.check_rate(ask)
    assert access.check_rate(request('203.0.113.51', '/api/integrations/ontong/screen', 'GET')) is None      # 조회는 세지 않는다
    assert access.check_rate(request('testclient', '/api/integrations/ontong/ask', 'POST')) is None
    new = request('203.0.113.52', '/api/desk/workspaces', 'POST')
    assert [access.check_rate(new) for _ in range(31)].count(None) == 30


# ── 소득: 기준 중위소득 대비 비율 ────────────────────────────────────
def test_income_is_compared_only_as_a_share_of_median_income(ctx):
    limited = made(earnCndSeCd='0043003', earnEtcCn='기준 중위소득 150% 이하')
    assert limited['income']['median_bounds'] == [{'pct': 150, 'kind': 'max'}]
    income = lambda item, **profile: next(c for c in screen(item, profile, 'open')['criteria'] if c['key'] == 'income')
    # 1인 가구 기준 중위소득 2,564,238원 → 150%는 약 385만원
    assert income(limited, income_monthly=180, household=1)['result'] == 'match' and '약 70%' in income(limited, income_monthly=180, household=1)['basis']
    assert income(limited, income_monthly=450, household=1)['result'] == 'mismatch'
    assert income(limited, income_monthly=390, household=1)['result'] == 'unknown'           # 경계 ±5%
    assert income(limited, income_monthly=450, household=4)['result'] == 'match'             # 가구원 수에 따라 달라진다
    assert income(limited, income_monthly=180)['result'] == 'unknown' and income(limited)['result'] == 'unknown'   # 가구원 수나 소득이 없으면 비교하지 않는다
    both = made(earnCndSeCd='0043003', earnEtcCn='중위소득 60% 초과 150% 이하')
    # 뒤쪽 상한('150% 이하')까지 읽어야 소득이 높은 사람을 '맞아요'로 잘못 보지 않는다.
    assert both['income']['median_bounds'] == [{'pct': 60, 'kind': 'min'}, {'pct': 150, 'kind': 'max'}]
    assert income(both, income_monthly=100, household=1)['result'] == 'mismatch'             # 하한 미달(약 39%)
    assert income(both, income_monthly=450, household=1)['result'] == 'mismatch'             # 상한 초과(약 175%)
    assert income(both, income_monthly=250, household=1)['result'] == 'match'                # 약 97%
    mixed = made(earnCndSeCd='0043003', earnEtcCn='중위소득 150% 이하, 지원율 50%')              # 뜻을 모르는 숫자가 섞이면 비교하지 않는다
    assert income(mixed, income_monthly=180, household=1)['result'] == 'unknown'
    vague = made(earnCndSeCd='0043003', earnEtcCn='중위소득 120% 수준')                          # 방향이 없으면 비교하지 않는다
    assert vague['income']['median_bounds'] == [{'pct': 120, 'kind': '?'}] and income(vague, income_monthly=100, household=1)['result'] == 'unknown'
    assert post(ctx, {'income_monthly': 180, 'household': 1}).status_code == 200
    assert post(ctx, {'household': 7}).status_code == 422 and post(ctx, {'income_monthly': -1}).status_code == 422


# ── 연중 기간 · 대상 집단 · 금액 · 신청 경로 ─────────────────────────
def test_year_long_window_is_not_treated_as_currently_recruiting(ctx):
    short, year = made(), made(aplyYmd='20260101 ~ 20261231')
    assert short['application']['long_window'] is False and year['application']['long_window'] is True
    assert made(aplyYmd=r'20260101 ~ 20261231\N20261101 ~ 20261115')['application']['long_window'] is False   # 짧은 회차가 함께 있으면 그대로 본다
    assert period_status(year['application'], DAY) == 'open'                    # 날짜로는 기간 안이지만
    out, results = verdict(year, PROFILE)
    assert results['period'] == 'unknown' and out['outcome'] == 'needs_check'   # 접수 중이라고 하지 않는다
    assert '사업기간' in next(c['basis'] for c in out['criteria'] if c['key'] == 'period')
    assert verdict(short, PROFILE)[0]['outcome'] == 'api_match'
    seed([good('LW1', aplyYmd='20260101 ~ 20261231'), good('LW2', aplyYmd='20261101 ~ 20261225'), good('LW3')])
    items = post(ctx).json()['items']
    # 날짜가 정해진 접수 중(LW3 → LW2) 다음에 연중 표기(LW1)가 온다. 연중 표기는 D-day를 보여 주지 않는다.
    assert [x['external_id'] for x in items] == ['LW3', 'LW2', 'LW1']
    assert items[2]['period_label'] == '연중 표기(API) · 모집 회차 확인' and items[0]['period_label'].startswith('D-')


def test_target_group_in_policy_name(ctx):
    art = made(plcyNm='2026 청년예술지원사업')
    assert art['targets'] == ['예술인'] and made(plcyNm='청년 월세 지원')['targets'] == []
    assert made(plcyNm='대학생 창업 동아리 지원')['targets'] == ['대학(원)생', '창업(예비 포함)']
    assert made(plcyNm='청년 지원', plcyExplnCn='대학생도 신청할 수 있습니다')['targets'] == []          # 설명 글의 낱말로는 정하지 않는다
    target = lambda groups: next(c for c in screen(art, {**PROFILE, 'groups': groups}, 'open')['criteria'] if c['key'] == 'target')['result']
    assert target(None) == 'unknown' and target([]) == 'unknown' and target(['대학(원)생']) == 'unknown'   # 아니라고 단정하지 않는다
    assert target(['예술인']) == 'match'
    assert screen(art, PROFILE, 'open')['outcome'] == 'needs_check' and screen(art, {**PROFILE, 'groups': ['예술인']}, 'open')['outcome'] == 'api_match'
    assert 'target' not in {c['key'] for c in screen(made(), PROFILE, 'open')['criteria']}
    with pytest.raises(ValueError):
        validate_profile({'groups': ['없는 대상']})
    assert post(ctx, {'groups': ['없는 대상']}).status_code == 422 and post(ctx, {'groups': ['예술인']}).status_code == 200
    assert '예술인' in ctx.get('/api/integrations/ontong/regions').json()['groups']


def test_amounts_and_channels_are_structured_without_summing(ctx):
    item = made(plcySprtCn='월 최대 20만원씩 12개월 지원, 연 최대 240만원. 보증금 대출은 최대 4,500만원, 한도 1.5억원',
                plcyAplyMthdCn='청년포털 누리집에서 온라인 신청 또는 주민센터 방문, 우편 접수 불가')
    assert [(a['text'], a['krw'], a['period'], a['max']) for a in item['amounts']] == [
        ('월 최대 20만원', 200000, '월', True), ('연 최대 240만원', 2400000, '연', True), ('최대 4,500만원', 45000000, None, True)]
    assert item['access']['channels'] == ['온라인', '방문', '우편']
    assert made(plcySprtCn='상담 제공')['amounts'] == [] and made(plcyAplyMthdCn='')['access']['channels'] == []
    seed([good('AM1', plcySprtCn='응시료 실비, 연 최대 10만원'), good('AM2')])
    by_id = {x['external_id']: x for x in post(ctx).json()['items']}
    assert by_id['AM1']['amounts'][0]['text'] == '연 최대 10만원' and by_id['AM1']['channels'] == ['온라인'] and by_id['AM2']['amounts'] == []
    plan = plan_of(ctx, ['AM1', 'AM2'])[1].json()
    assert plan['policies'][0]['amounts'][0]['krw'] == 100000 and 'total_amount' not in plan      # 합산 값은 만들지 않는다
