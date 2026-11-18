import copy
import json
from datetime import date, datetime

import pytest
from test_project import ctx, BASE
from test_workflow import session, preview, confirm
from db import connect
from engine import evaluate_predicate, status_policy, missing_facts
from policy_data import import_policy_file, load_policies, validate_policy, valid_value
from temporal import application_period, benefit_active_on, validate_application

PERIOD={'open':'2026-05-06','close':'2026-05-19',
        'open_at':'2026-05-06T10:00:00+09:00','close_at':'2026-05-19T18:00:00+09:00'}
PREDICATE={'fact':'benefit_history','op':'benefit_active_on',
           'value':{'code':'seoul_youth_allowance','date_fact':'application_date','complete_fact':'benefit_history_complete'}}


@pytest.mark.parametrize('at,expected',[
    ('2026-05-06T09:59:59+09:00','not_open'),
    ('2026-05-06T10:00:00+09:00','active'),
    ('2026-05-19T17:59:59+09:00','active'),
    ('2026-05-19T18:00:00+09:00','closed'),
    ('2026-05-19T09:00:00+00:00','closed'),
    ('2026-05-20T00:00:00+09:00','closed'),
])
def test_korean_application_boundaries(at,expected):
    assert application_period(PERIOD,datetime.fromisoformat(at))==expected


def test_date_only_cannot_invent_cutoff_time():
    assert application_period(PERIOD,date(2026,5,19))=='unknown'
    assert application_period(PERIOD,date(2026,5,10))=='active'
    assert application_period({'open':'2026-05-06','close':'2026-05-19'},date(2026,5,19))=='active'


@pytest.mark.parametrize('change',[
    {'close_at':None},{'open_at':'2026-05-06T10:00:00'},
    {'close_at':'2026-05-06T10:00:00+09:00'},
    {'open':'20260506'}, {'close':'2026-05-18'},
])
def test_inconsistent_period_rejected(change):
    with pytest.raises(ValueError):validate_application({**PERIOD,**change})


@pytest.mark.parametrize('start,end,ongoing,expected',[
    ('2026-03-01','2026-05-05',False,False),
    ('2026-03-01','2026-05-06',False,True),
    ('2026-05-06','2026-05-30',False,True),
    ('2026-05-07','2026-05-30',False,False),
    ('2026-03-01',None,True,True),
    ('2026-03-01',None,False,None),
    (None,'2026-05-30',False,None),
    (None,'2026-05-05',False,False),
])
def test_benefit_last_covered_day(start,end,ongoing,expected):
    records=[{'code':'seoul_youth_allowance','start':start,'end':end,'ongoing':ongoing}]
    assert benefit_active_on(records,'seoul_youth_allowance','2026-05-06',True) is expected


def test_incomplete_negative_evidence_is_not_no_benefit():
    assert benefit_active_on([],'seoul_youth_allowance','2026-05-06',False) is None
    assert benefit_active_on([],'seoul_youth_allowance','2026-05-06',None) is None
    assert benefit_active_on([],'seoul_youth_allowance','2026-05-06',True) is False
    assert benefit_active_on([],'seoul_youth_allowance',None,True) is None


def test_positive_overlap_does_not_require_complete_history():
    record={'code':'seoul_youth_allowance','start':'2026-03-01','end':None,'ongoing':True}
    assert benefit_active_on([record],'seoul_youth_allowance','2026-05-06',False) is True


def test_uncertain_history_creates_actionable_missing_facts():
    facts={'application_date':'2026-05-06','benefit_history_complete':False,'benefit_history':[]}
    assert evaluate_predicate(PREDICATE,facts) is None
    assert missing_facts(PREDICATE,facts)==['benefit_history_complete']
    facts['benefit_history_complete']=True
    facts['benefit_history']=[{'code':'seoul_youth_allowance','start':'2026-03-01','end':None,'ongoing':None}]
    assert missing_facts(PREDICATE,facts)==['benefit_history']


@pytest.mark.parametrize('record',[
    {'code':'x','start':'2026-05-09','end':'2026-05-06','ongoing':False},
    {'code':'x','start':'2026-03-01','end':'2026-05-06','ongoing':True},
    {'code':'x','start':'bad-date','end':None,'ongoing':None},
    {'code':'x','start':None,'end':None,'ongoing':'yes'},
])
def test_bad_history_is_rejected_at_api(ctx,record):
    sid=session(ctx)
    response=ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'benefit_history':[record]}})
    assert response.status_code==422


def test_deadline_change_invalidates_preview_and_saved_tasks(ctx,tmp_path,monkeypatch):
    import app
    policy=load_policies()['demo_rent'];policy['version']='2026.3';policy['application']=PERIOD
    file=tmp_path/'new.json';file.write_text(json.dumps(policy,ensure_ascii=False),encoding='utf-8');import_policy_file(file)
    sid=session(ctx)
    monkeypatch.setattr(app,'korean_now',lambda:datetime.fromisoformat('2026-05-19T17:59:59+09:00'))
    token=preview(ctx,sid)['preview_token']
    tasks=confirm(ctx,sid,token).json()['tasks']
    monkeypatch.setattr(app,'korean_now',lambda:datetime.fromisoformat('2026-05-19T18:00:00+09:00'))
    assert confirm(ctx,sid,token).status_code==409
    assert all(t['outdated'] for t in ctx.get(f'/api/sessions/{sid}/tasks').json())
    assert ctx.patch('/api/tasks/'+tasks[0]['id'],json={'session_id':sid,'status':'done'}).status_code==409


def test_real_draft_review_has_no_session_or_task_side_effects(ctx):
    import_policy_file(BASE/'data'/'policies'/'seoul_rent_2026.json')
    sid=session(ctx)
    facts={'region':'서울','application_date':'2026-05-06','benefit_history_complete':True,
           'benefit_history':[{'code':'seoul_youth_allowance','start':'2026-03-01','end':'2026-05-06','ongoing':False}]}
    request={'code':'seoul_rent_2026','version':'2026.1','facts':facts,'at':'2026-05-06T12:00:00+09:00'}
    result=ctx.post('/api/policy-review/preview',json=request).json()
    assert result['review_only'] is True and result['review_status']=='draft'
    assert result['analysis']['results'][0]['status']=='ineligible'
    assert len(result['analysis']['conflicts'])==1
    assert 'preview_token' not in result['plan']
    with connect() as con:
        assert con.execute('SELECT count(*) FROM eligibility_checks').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM preparation_tasks').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM demo_sessions').fetchone()[0]==1
    assert ctx.put(f'/api/sessions/{sid}/selected',json={'selected':['seoul_rent_2026']}).status_code==422
    facts['benefit_history'][0]['end']='2026-05-05'
    safe=ctx.post('/api/policy-review/preview',json=request).json()
    assert safe['analysis']['conflicts']==[]
    # Other unmodeled rules still prohibit a positive eligibility conclusion.
    assert safe['analysis']['results'][0]['status']=='needs_review'


def test_review_deadline_and_no_time_zone(ctx):
    import_policy_file(BASE/'data'/'policies'/'seoul_allowance_2026_round2.json')
    request={'code':'seoul_allowance_2026_round2','version':'2026.1','facts':{},'at':'2026-05-29T16:00:00+09:00'}
    result=ctx.post('/api/policy-review/preview',json=request).json()
    assert result['analysis']['results'][0]['period_status']=='closed'
    request['at']='2026-05-29T16:00:00'
    assert ctx.post('/api/policy-review/preview',json=request).status_code==422
