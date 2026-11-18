import json, sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from db import init_db
import db
from policy_data import import_policy_file, load_policies, validate_policy
from engine import evaluate_predicate,status_policy,preview_plan

@pytest.fixture()
def ctx(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'test.sqlite3')
    init_db()
    for f in sorted((BASE/'data'/'policies').glob('demo_*.json')): import_policy_file(f)
    from app import app
    return TestClient(app)

def test_import_and_approved(ctx):
    data=ctx.get('/api/policies').json()
    assert {x['code'] for x in data}=={'demo_allowance','demo_rent','demo_exam'}
    assert all(x['demo_only'] for x in data)

def test_conflict_direction(ctx):
    pol=load_policies()
    f={'age':26,'region':'서울','employment_status':'unemployed','active_benefits':['demo_allowance'],'rent_payment_method':'cash'}
    rent=status_policy(pol['demo_rent'],f)
    allowance=status_policy(pol['demo_allowance'],f)
    assert rent['status']=='ineligible'
    assert allowance['status']=='review_possible'

def test_missing_fact_not_false(ctx):
    result=status_policy(load_policies()['demo_rent'],{'age':26,'region':'서울'})
    assert result['status']=='needs_review'
    assert 'active_benefits' in result['missing_facts']

def test_out_of_scope_period(ctx):
    from datetime import date
    r=status_policy(load_policies()['demo_rent'],{'age':26,'region':'서울','active_benefits':[]},today=date(2028,1,1))
    assert r['status']=='application_closed'

def test_cash_alternative(ctx):
    pol=load_policies();facts={'age':26,'region':'서울','active_benefits':[],'rent_payment_method':'cash'}
    plan=preview_plan(pol,['demo_rent'],facts,{})
    names=[x['title'] for x in plan['tasks']]
    assert any('월차임 납부확인서' in t for t in names)
    assert not any('월세 이체내역' in t for t in names)

def test_no_task_without_approval(ctx):
    session=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    ctx.put(f'/api/sessions/{session}/selected',json={'selected':['demo_rent']})
    assert ctx.post('/api/preview',json={'session_id':session}).status_code==200
    assert not ctx.get(f'/api/sessions/{session}/tasks').json()
    assert ctx.post('/api/confirm',json={'session_id':session,'approved':False}).status_code==403
    assert not ctx.get(f'/api/sessions/{session}/tasks').json()

def test_save_idempotent_and_complete(ctx):
    session=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    ctx.put(f'/api/sessions/{session}/selected',json={'selected':['demo_rent']})
    first=ctx.post('/api/confirm',json={'session_id':session,'approved':True,'preview_token':ctx.post('/api/preview',json={'session_id':session}).json()['preview_token']}).json()
    second=ctx.post('/api/confirm',json={'session_id':session,'approved':True,'preview_token':ctx.post('/api/preview',json={'session_id':session}).json()['preview_token']}).json()
    assert first['created']>0
    assert second['created']==0
    t=first['tasks'][0]
    assert ctx.patch(f'/api/tasks/{t["id"]}',json={'session_id':session,'status':'done'}).json()['updated']
    assert ctx.get(f'/api/sessions/{session}/tasks').json()[0]['status']=='done'

def test_session_isolation(ctx):
    a=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    b=ctx.post('/api/sessions',json={'persona':'worker'}).json()['id']
    ctx.put(f'/api/sessions/{a}/selected',json={'selected':['demo_rent']})
    tasks=ctx.post('/api/confirm',json={'session_id':a,'approved':True,'preview_token':ctx.post('/api/preview',json={'session_id':a}).json()['preview_token']}).json()['tasks']
    assert ctx.patch(f'/api/tasks/{tasks[0]["id"]}',json={'session_id':b,'status':'done'}).status_code==404

def test_unknown_fact_rejected(ctx):
    sid=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    assert ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'social_security_number':'123'}}).status_code==422

def test_operator_is_whitelisted():
    with pytest.raises(ValueError):
        validate_policy({**json.loads((BASE/'data'/'policies'/'demo_rent.json').read_text(encoding='utf-8')),'rules':[{'id':'x','type':'required','predicate':{'fact':'age','op':'exec','value':1},'message':'bad','source_ref':'notice'}]})

def test_version_changed_requires_replace(ctx,tmp_path):
    doc=json.loads((BASE/'data'/'policies'/'demo_exam.json').read_text(encoding='utf-8'))
    doc['name']='Changed name'
    f=tmp_path/'p.json';f.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
    with pytest.raises(ValueError,match='content changed'):
        import_policy_file(f)

def test_llm_absent_is_truthful(ctx,monkeypatch):
    monkeypatch.setattr('local_agent.model_status',lambda: {'ready':False})
    sid=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    resp=ctx.post('/api/agent/message',json={'session_id':sid,'message':'도와줘'})
    assert resp.status_code==503

def test_generic_predicates():
    assert evaluate_predicate({'all':[{'fact':'age','op':'gte','value':19},{'fact':'region','op':'in','value':['서울','경기']}]},{'age':26,'region':'서울'}) is True
    assert evaluate_predicate({'any':[{'fact':'age','op':'lte','value':18},{'fact':'region','op':'eq','value':'서울'}]},{'age':26,'region':'서울'}) is True

def test_draft_can_be_edited_before_approval(ctx,tmp_path):
    original=json.loads((BASE/'data'/'policies'/'demo_exam.json').read_text(encoding='utf-8'))
    original['code']='draft_change_test';original['review']['status']='draft'
    fn=tmp_path/'draft.json';fn.write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
    assert import_policy_file(fn)[0]=='imported'
    original['name']='Changed while still draft'
    fn.write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
    assert import_policy_file(fn)[0]=='imported'
    assert 'draft_change_test' not in load_policies()

def test_stale_tasks_after_user_facts_changed(ctx):
    sid=ctx.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    ctx.put(f'/api/sessions/{sid}/selected',json={'selected':['demo_rent']})
    first=ctx.post('/api/confirm',json={'session_id':sid,'approved':True,'preview_token':ctx.post('/api/preview',json={'session_id':sid}).json()['preview_token']}).json()
    first_id=first['tasks'][0]['id']
    ctx.patch(f'/api/tasks/{first_id}',json={'session_id':sid,'status':'done'})
    ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'rent_payment_method':'bank'}})
    updated=ctx.get(f'/api/sessions/{sid}/tasks').json()
    assert any(t['outdated'] for t in updated)
