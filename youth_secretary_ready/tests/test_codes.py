"""코드 해석·코드 필터 회귀 (HANDOFF 03 문서 P0-1 표). 모의 응답 기반이며 실제 등록된 증거가 아니다."""
import httpx
import pytest
from test_project import ctx
from test_ontong import item, response, fake_key
from db import connect
import ontong
from policy_codes import CODEBOOK, application_hint, decode, describe, questions

SEARCH = '/api/integrations/ontong/search'
BUNDLE = '/api/integrations/ontong/candidates/'


def seed(items):
    """실제 수집 경로(_normalize)로 넣는다. sync 한 번에 10건까지라 나눠 넣는다."""
    for i in range(0, len(items), 10):
        chunk = items[i:i + 10]
        ontong.sync('', transport=httpx.MockTransport(lambda r: response(chunk)))


def snapshot():
    with connect() as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}


def found(ctx, **params):
    r = ctx.get(SEARCH, params={'page_size': 100, **params})
    assert r.status_code == 200
    return {x['external_id'] for x in r.json()['items']}


def field(described, name):
    return next(f for f in described['fields'] if f['field'] == name)


def test_leading_zero_code_stays_text_and_reads_as_rolling(ctx):
    seed([item('A1', aplyPrdSeCd='0057002')])
    bundle = ctx.get(BUNDLE + 'A1').json()
    assert bundle['public_fields']['aplyPrdSeCd'] == '0057002'
    decoded = field(bundle['decoded'], 'aplyPrdSeCd')
    assert decoded['labels'] == ['상시'] and decoded['unknown_codes'] == []
    # 선행 0이 빠진 값은 같은 코드로 취급하지 않는다.
    assert decode('aplyPrdSeCd', '57002') == {'field': 'aplyPrdSeCd', 'raw': '57002', 'labels': [],
                                              'unknown_codes': ['57002'], 'missing': False}


def test_job_filter_matches_exact_code_in_comma_list(ctx):
    seed([item('J1', jobCd='0013002,0013001'), item('J2', jobCd='0013002, 0013001'),
          item('J3', jobCd='0013002,0013003'), item('J4', jobCd='0013010'),
          item('J5', jobCd='00130010'), item('J6', jobCd='')])
    assert found(ctx, job_code='0013001') == {'J1', 'J2'}
    # 0013001 ⊂ 00130010, 0013010 ⊂ 00130010 같은 부분 문자열로 걸리지 않는다.
    assert found(ctx, job_code='0013010') == {'J4'}
    assert decode('jobCd', '00130010')['labels'] == []
    assert decode('jobCd', '00130010')['unknown_codes'] == ['00130010']


def test_unknown_code_is_kept_not_dropped_or_read_as_unrestricted():
    result = decode('jobCd', '0013001,9999999,0013001')
    assert result['labels'] == [CODEBOOK['groups']['jobCd']['codes']['0013001']['label']]
    assert result['unknown_codes'] == ['9999999'] and result['missing'] is False
    assert field(describe({'jobCd': '9999999'}), 'jobCd')['unknown_codes'] == ['9999999']


@pytest.mark.parametrize('value', ['', None, '  ', ' , '])
def test_blank_is_missing_not_a_label(value):
    result = decode('jobCd', value)
    assert result['missing'] is True and result['labels'] == [] and result['unknown_codes'] == []


def test_blank_payload_does_not_become_open_eligible_or_document_free():
    hint = application_hint({})
    assert hint['kind'] == 'unknown' and hint['current_open'] is None
    described = describe({})
    assert all(f['missing'] and not f['collected'] for f in described['fields'])
    assert described['income']['kind']['missing'] and described['income']['comparable'] is False
    # 소득 구분이 비어 있으면 '무관'으로 보지 않고 확인 질문을 남긴다. 서류 질문은 항상 남는다.
    assert {'period', 'income', 'benefits', 'documents'} <= {q['key'] for q in questions({})}


def test_code_filters_combine_with_existing_filters_and_paging(ctx):
    base = dict(plcyNm='취업 지원', lclsfNm='일자리', aplyPrdSeCd='0057001',
                jobCd='0013001,0013003', earnCndSeCd='0043001')
    wanted = ['M%d' % i for i in range(5)]
    seed([item(n, **base) for n in wanted] + [
        item('N1', **{**base, 'plcyNm': '월세 지원'}), item('N2', **{**base, 'lclsfNm': '주거'}),
        item('N3', **{**base, 'aplyPrdSeCd': '0057002'}), item('N4', **{**base, 'jobCd': '0013002'}),
        item('N5', **{**base, 'earnCndSeCd': '0043002'}), item('N6', **base, aplyYmd='20260101 ~ 20260131')])
    params = dict(q='취업', category='일자리', quality='missing_period', application_code='0057001',
                  job_code='0013001', income_code='0043001', page_size=2)
    pages = [ctx.get(SEARCH, params={**params, 'page': p}).json() for p in (1, 2, 3)]
    assert all(p['total'] == 5 and p['pages'] == 3 for p in pages)
    assert [len(p['items']) for p in pages] == [2, 2, 1]
    assert [x['external_id'] for p in pages for x in p['items']] == sorted(wanted, reverse=True)


@pytest.mark.parametrize('params', [
    {'job_code': "0013001' OR '1'='1"}, {'job_code': '00130010'}, {'job_code': '0013011'},
    {'application_code': '0057004'}, {'income_code': '43001'}, {'quality': 'x'},
    {'page': 0}, {'page_size': 101}, {'q': 'x' * 81}])
def test_invalid_query_is_422(ctx, params):
    assert ctx.get(SEARCH, params=params).status_code == 422


def test_sql_text_in_query_is_literal(ctx):
    seed([item('S1'), item('S2')])
    for q in ("' OR 1=1 --", "x'; DROP TABLE ontong_candidates; --"):
        body = ctx.get(SEARCH, params={'q': q})
        assert body.status_code == 200 and body.json()['total'] == 0
    assert found(ctx) == {'S1', 'S2'}


def test_clearing_filters_restores_every_policy_without_region_or_20_cap(ctx):
    zips = ['11110', '26110,26140', '']
    seed([item('R%02d' % i, zipCd=zips[i % 3], jobCd='0013001' if i < 4 else '0013002') for i in range(23)])
    assert len(found(ctx, job_code='0013001')) == 4
    body = ctx.get(SEARCH).json()
    assert body['total'] == 23 and body['pages'] == 2 and len(body['items']) == 20
    assert len(ctx.get(SEARCH, params={'page': 2}).json()['items']) == 3
    assert len(found(ctx)) == 23


@pytest.mark.parametrize('code,kind', [('0057001', 'fixed'), ('0057002', 'rolling'), ('0057003', 'closed'),
                                       ('', 'unknown'), ('0057009', 'unknown')])
def test_application_code_never_asserts_currently_open(code, kind):
    hint = application_hint({'aplyPrdSeCd': code})
    assert hint['kind'] == kind and hint['current_open'] is None and hint['basis'] == 'api_code'


def test_official_closure_is_dropped_when_api_content_changed():
    payload, check = {'aplyPrdSeCd': '0057002'}, {'official_status': 'closed'}
    kept = application_hint(payload, {**check, 'api_changed_since_check': False})
    assert kept['kind'] == 'closed' and kept['basis'] == 'source_check' and kept['current_open'] is None
    dropped = application_hint(payload, {**check, 'api_changed_since_check': True})
    assert dropped['kind'] == 'rolling' and dropped['basis'] == 'api_code'
    assert application_hint(payload, {'official_status': 'open'})['basis'] == 'api_code'


def test_income_amounts_are_kept_raw_and_never_compared():
    payload = {'earnCndSeCd': '0043002', 'earnMinAmt': '0', 'earnMaxAmt': '5000'}
    income = describe(payload)['income']
    assert income['comparable'] is False and income['unit'] is None
    assert (income['minimum_raw'], income['maximum_raw']) == ('0', '5000')
    assert 'income' in {q['key'] for q in questions(payload)}
    assert 'income' not in {q['key'] for q in questions({'earnCndSeCd': '0043001'})}


def test_zip_code_is_not_resolved_into_a_residence_decision():
    region = describe({'zipCd': '11305,11110'})['region']
    assert region == {'raw': '11305,11110', 'resolved': False, 'notice': region['notice']}
    assert 'region' in {q['key'] for q in questions({'zipCd': '11305'})}
    assert 'region' not in {q['key'] for q in questions({})}


def test_business_period_reads_real_api_field_name():
    described = describe({'bizPrdSeCd': '0056001'})
    biz = field(described, 'bizPrdSecd')
    assert biz['api_field'] == 'bizPrdSeCd' and biz['labels'] == ['특정기간'] and biz['collected'] is True
    # 수집 목록에 없는 분류는 '값 없음'과 구분된다.
    assert field(described, 'sbizCd')['collected'] is False


def test_reads_create_no_rows(ctx):
    seed([item('Q1', aplyPrdSeCd='0057002', jobCd='0013001', zipCd='11305'), item('Q2')])
    before = snapshot()
    for url in ('/api/integrations/ontong/codebook', '/api/integrations/ontong/regions', SEARCH,
                SEARCH + '?q=월세&job_code=0013001&application_code=0057002', BUNDLE + 'Q1',
                '/api/integrations/ontong/candidates', '/api/integrations/ontong'):
        assert ctx.get(url).status_code == 200
    assert ctx.get(BUNDLE + 'none').status_code == 404
    assert snapshot() == before
