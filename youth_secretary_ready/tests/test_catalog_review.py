import copy
import json
from datetime import date,datetime
import pytest
from test_project import ctx,BASE
from test_ontong import item,KEY
from db import connect
import ontong
from engine import document_tasks,status_policy,preview_plan
from temporal import application_period
from policy_data import validate_policy,import_policy_file


def seeded():
    with connect() as con:
        con.execute("INSERT INTO ontong_sync_runs(id,keyword,status,started_at) VALUES('seed','','success','2026-11-16')")
        rows=[ontong._normalize(item(f'{n:04}',plcyNm=f'정책 {n}',lclsfNm='주거' if n%2==0 else '일자리',
                   sbmsnDcmntCn='' if n%3==0 else '서류',aplyYmd='' if n%4==0 else '20260101 ~ 20261231'),KEY) for n in range(125)]
        ontong.save_candidates(con,rows,'2026-11-16','seed')


def test_search_all_pages_reaches_beyond_old_100_limit(ctx):
    seeded();seen=[]
    for page in range(1,8):
        result=ctx.get('/api/integrations/ontong/search',params={'page':page}).json()
        assert result['total']==125 and result['pages']==7
        seen.extend(x['external_id'] for x in result['items'])
    assert len(seen)==len(set(seen))==125
    assert ctx.get('/api/integrations/ontong/search',params={'page':8}).json()['items']==[]


def test_search_filters_and_literal_wildcards(ctx):
    seeded()
    endpoint='/api/integrations/ontong/search'
    assert ctx.get(endpoint,params={'q':'0124'}).json()['total']==1
    assert ctx.get(endpoint,params={'category':'주거'}).json()['total']==63
    assert ctx.get(endpoint,params={'quality':'missing_documents'}).json()['total']==42
    assert ctx.get(endpoint,params={'quality':'missing_period'}).json()['total']==32
    assert ctx.get(endpoint,params={'category':'주거','quality':'missing_period'}).json()['total']==32
    for value in ['%', '_', "' OR 1=1 --", '\\']:
        assert ctx.get(endpoint,params={'q':value}).json()['total']==0
    for params in [{'page':0},{'page_size':101},{'q':'x'*81},{'quality':'wrong'}]:
        assert ctx.get(endpoint,params=params).status_code==422


def test_source_check_is_invalidated_by_api_content_change(ctx,tmp_path,monkeypatch):
    seeded()
    (tmp_path/'data').mkdir()
    with connect() as con:sha=con.execute("SELECT sha256 FROM ontong_candidates WHERE external_id='0001'").fetchone()[0]
    (tmp_path/'data'/'source_checks.json').write_text(json.dumps([{'external_id':'0001','api_sha256':sha,'kind':'period_conflict'}]),encoding='utf-8')
    monkeypatch.setattr(ontong,'BASE',tmp_path)
    assert ontong.review_bundle('0001')['source_check']['api_changed_since_check'] is False
    with connect() as con:con.execute("UPDATE ontong_candidates SET sha256='changed' WHERE external_id='0001'")
    assert ontong.review_bundle('0001')['source_check']['api_changed_since_check'] is True
    assert ontong.review_bundle('0002')['source_check'] is None


def draft():return json.loads((BASE/'data/policies/seongbuk_exam_2026.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('day,expected',[
    ('2026-01-31','not_open'),('2026-02-01','unknown'),('2026-11-15','unknown'),
    ('2026-11-16','closed'),('2026-12-01','closed'),('2026-12-11','closed')])
def test_early_closure_does_not_invent_effective_date(day,expected):
    assert application_period(draft()['application'],date.fromisoformat(day))==expected


def test_closure_uses_korean_calendar():
    assert application_period(draft()['application'],datetime.fromisoformat('2026-11-15T15:00:00+00:00'))=='closed'


@pytest.mark.parametrize('change', ['source','date','reason'])
def test_closure_requires_valid_source_and_date(change):
    p=draft();notice=p['application']['closure_notice']
    notice[{'source':'source_ref','date':'observed_on','reason':'reason'}[change]]={'source':'missing','date':'2026-02-30','reason':''}[change]
    with pytest.raises(ValueError):validate_policy(p)


def test_closed_policy_only_proposes_checking_future_notice():
    p=draft()
    result=status_policy(p,{},date(2026,11,16))
    assert result['status']=='application_closed'
    assert any(f['rule_id']=='early_closure' and f['source']['url']==p['official_url'] for f in result['findings'])
    plan=preview_plan({p['code']:p},[p['code']],{}, {},date(2026,11,16))
    assert len(plan['tasks'])==1 and plan['tasks'][0]['task_key'].startswith('watch:')


def test_consent_selects_document_and_unknown_does_not_assume():
    p=draft()
    yes=document_tasks(p,{'admin_info_consent':True,'employment_status':'unemployed'}, {})
    no=document_tasks(p,{'admin_info_consent':False,'employment_status':'unemployed'}, {})
    unknown=document_tasks(p,{}, {})
    assert any('doc:sb_exam_consent:' in x['task_key'] for x in yes)
    assert not any('doc:sb_exam_residence:' in x['task_key'] for x in yes)
    assert any('doc:sb_exam_residence:' in x['task_key'] for x in no)
    assert not any('doc:sb_exam_consent:' in x['task_key'] for x in no)
    assert any(x['task_key']=='fact:admin_info_consent' for x in unknown)
    assert not any('doc:sb_exam_residence:' in x['task_key'] for x in unknown)


def test_real_draft_stays_outside_approved_engine_and_review_is_read_only(ctx):
    import_policy_file(BASE/'data/policies/seongbuk_exam_2026.json')
    assert not any(p['code']=='seongbuk_exam_2026' for p in ctx.get('/api/policies').json())
    response=ctx.post('/api/policy-review/preview',json={'code':'seongbuk_exam_2026','version':'2026.1',
        'facts':{'region':'서울','residence_district':'성북구','resident_since':'2025-12-31','business_registered':False},
        'at':'2026-11-16T12:00:00+09:00'})
    assert response.status_code==200
    assert response.json()['analysis']['results'][0]['status']=='application_closed'
    with connect() as con:assert con.execute('SELECT count(*) FROM preparation_tasks').fetchone()[0]==0


def test_residence_boundary_and_business_exclusion():
    facts={'region':'서울','residence_district':'성북구','resident_since':'2025-12-31','business_registered':False}
    p=draft()
    before=status_policy(p,facts,date(2026,3,1))
    assert before['status']=='needs_review'
    assert next(x for x in before['findings'] if x['rule_id']=='residence_start')['effect']=='pass'
    after=status_policy(p,{**facts,'resident_since':'2026-01-01'},date(2026,3,1))
    assert next(x for x in after['findings'] if x['rule_id']=='residence_start')['effect']=='block'
    registered=status_policy(p,{**facts,'business_registered':True},date(2026,3,1))
    assert next(x for x in registered['findings'] if x['rule_id']=='business')['effect']=='block'
