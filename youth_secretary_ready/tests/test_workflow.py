"""Behavioral regression tests. Model transport is mocked; these are NOT live AI evidence."""
import copy
import json
from datetime import date
import httpx
import pytest
from test_project import ctx, BASE
from db import connect
from engine import document_tasks, status_policy, preview_plan
from policy_data import load_policies, import_policy_file, validate_policy
import local_agent


def session(ctx,persona='unemployed'):
    sid=ctx.post('/api/sessions',json={'persona':persona}).json()['id']
    assert ctx.put(f'/api/sessions/{sid}/selected',json={'selected':['demo_rent']}).status_code==200
    return sid


def preview(ctx,sid):return ctx.post('/api/preview',json={'session_id':sid}).json()
def confirm(ctx,sid,token=None):
    return ctx.post('/api/confirm',json={'session_id':sid,'approved':True,
        'preview_token':token or preview(ctx,sid)['preview_token']})
def model_calls(*pairs):return {'role':'assistant','content':'','tool_calls':[{'function':{'name':name,'arguments':args}} for name,args in pairs]}
def fake_model(monkeypatch,responses):
    monkeypatch.setattr(local_agent,'model_status',lambda:{'ready':True})
    iterator=iter(responses)
    monkeypatch.setattr(local_agent,'chat',lambda *args:next(iterator))


def test_missing_alternative_does_not_choose_default(ctx):
    p=load_policies()['demo_rent']
    tasks=document_tasks(p,{'rent_payment_method':None},{})
    assert any(t['task_key']=='fact:rent_payment_method' for t in tasks)
    assert not any('bank_rent_proof' in t['task_key'] or 'cash_rent_confirmation' in t['task_key'] for t in tasks)


def test_ambiguous_alternatives_do_not_pick_first(ctx):
    p=load_policies()['demo_rent']
    p['documents'][1]['alternatives'].append({**p['documents'][1]['alternatives'][0],'code':'other_cash'})
    tasks=document_tasks(p,{'rent_payment_method':'cash'},{})
    assert any(t['task_key'].startswith('doc-review:') for t in tasks)
    assert not any('doc:cash' in t['task_key'] for t in tasks)


def test_empty_fact_and_unmodeled_rule_stay_unknown(ctx):
    p=load_policies()['demo_rent']
    r=status_policy(p,{'age':26,'region':'','active_benefits':[]},today=date(2026,11,15))
    assert r['missing_facts']==['region']
    p['manual_checks']=[{'id':'date_rule','message':'기준일 이력 확인','source_ref':'notice'}]
    r=status_policy(p,{'age':26,'region':'서울','active_benefits':[]},today=date(2026,11,15))
    assert r['status']=='needs_review'


def test_held_document_still_requires_validation(ctx):
    p=load_policies()['demo_rent'];p['documents'][0]['constraints']={}
    tasks=document_tasks(p,{'rent_payment_method':'cash'},{'lease':'owned'})
    assert any(t['task_key'].startswith('verify:lease:') for t in tasks)


@pytest.mark.parametrize('change', ['facts','selected','documents'])
def test_stale_preview_cannot_write(ctx,change):
    sid=session(ctx); token=preview(ctx,sid)['preview_token']
    body={'facts':{'age':27}} if change=='facts' else {'selected':[]} if change=='selected' else {'code':'lease','status':'owned'}
    assert ctx.put(f'/api/sessions/{sid}/{change}',json=body).status_code==200
    assert confirm(ctx,sid,token).status_code==409
    assert ctx.get(f'/api/sessions/{sid}/tasks').json()==[]


def test_confirmation_requires_preview_token(ctx):
    sid=session(ctx)
    assert ctx.post('/api/confirm',json={'session_id':sid,'approved':True}).status_code==409


def test_token_not_transferable(ctx):
    a=session(ctx);b=session(ctx)
    assert confirm(ctx,b,preview(ctx,a)['preview_token']).status_code==409


def test_policy_version_update_invalidates_tasks(ctx,tmp_path):
    sid=session(ctx); token=preview(ctx,sid)['preview_token']
    task=confirm(ctx,sid,token).json()['tasks'][0]
    p=load_policies()['demo_rent'];p['version']='2026.2'
    path=tmp_path/'next.json';path.write_text(json.dumps(p,ensure_ascii=False),encoding='utf-8');import_policy_file(path)
    assert confirm(ctx,sid,token).status_code==409
    assert all(t['outdated'] for t in ctx.get(f'/api/sessions/{sid}/tasks').json())
    assert ctx.patch('/api/tasks/'+task['id'],json={'session_id':sid,'status':'done'}).status_code==409


def test_reapproval_resets_done_but_retains_obsolete_history(ctx):
    sid=session(ctx);saved=confirm(ctx,sid).json()['tasks']
    for task in saved:assert ctx.patch('/api/tasks/'+task['id'],json={'session_id':sid,'status':'done'}).status_code==200
    ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'rent_payment_method':'bank'}})
    tasks=confirm(ctx,sid).json()['tasks']
    assert any('cash_rent_confirmation' in t['task_key'] and t['outdated'] for t in tasks)
    assert all(t['status']=='todo' for t in tasks if not t['outdated'])


def test_repeated_same_inputs_keep_approval_valid(ctx):
    sid=session(ctx); token=preview(ctx,sid)['preview_token']
    ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'age':26}})
    ctx.put(f'/api/sessions/{sid}/selected',json={'selected':['demo_rent']})
    assert confirm(ctx,sid,token).status_code==200


@pytest.mark.parametrize('predicate',[
    {'fact':'age','op':'between','value':[39,19]},
    {'fact':'age','op':'gte','value':'19'},
    {'fact':'age','op':'eq','value':True},
    {'fact':'region','op':'contains','value':'서울'},
    {'fact':'region','op':'eq','value':'invalid'},
])
def test_bad_rule_type_rejected(ctx,predicate):
    p=load_policies()['demo_rent'];p['rules'][0]['predicate']=predicate
    with pytest.raises(ValueError):validate_policy(p)


def test_real_drafts_import_but_cannot_be_selected(ctx):
    for path in (BASE/'data'/'policies').glob('seoul_*.json'):import_policy_file(path)
    drafts=[p for p in ctx.get('/api/policy-catalog').json() if not p['demo_only']]
    assert len(drafts)==2 and all(p['review']['status']=='draft' for p in drafts)
    sid=session(ctx)
    assert ctx.put(f'/api/sessions/{sid}/selected',json={'selected':[drafts[0]['code']]}).status_code==422
    assert len(ctx.get('/api/policies').json())==3


def test_real_approval_requires_verified_sources(ctx):
    p=load_policies()['demo_rent'];p['demo_only']=False
    with pytest.raises(ValueError):validate_policy(p)


def test_whole_flow_with_model_selected_tools(ctx,monkeypatch):
    sid=session(ctx)
    fake_model(monkeypatch,[model_calls(('update_user_facts',{'facts':{'rent_payment_method':'bank'}})),
        model_calls(('analyze_selected_policies',{}),('preview_preparation_tasks',{})),
        {'role':'assistant','content':'가상 정책의 준비 작업을 확인하세요.'}])
    result=ctx.post('/api/agent/message',json={'session_id':sid,'message':'가상 프로필에서 계좌이체로 바꿔서 준비할 것을 알려줘'}).json()
    assert result['grounded'] is True and len(result['tool_calls'])==3
    assert result['proposed_facts']=={'rent_payment_method':'bank'}
    assert ctx.get(f'/api/sessions/{sid}').json()['facts']['rent_payment_method']=='cash'
    assert ctx.get(f'/api/sessions/{sid}/tasks').json()==[]
    response=ctx.put(f'/api/sessions/{sid}/facts',json={'facts':result['proposed_facts'],'expected_revision':result['base_revision']})
    assert response.status_code==200
    tasks=confirm(ctx,sid).json()['tasks']
    assert any('bank_rent_proof' in t['task_key'] for t in tasks)
    assert not any('cash_rent_confirmation' in t['task_key'] for t in tasks)
    with connect() as con:
        assert con.execute('SELECT count(*) FROM preparation_tasks WHERE session_id=?',(sid,)).fetchone()[0]==len(tasks)
        assert con.execute('SELECT count(*) FROM eligibility_checks WHERE session_id=?',(sid,)).fetchone()[0]>0
    runs=ctx.get(f'/api/sessions/{sid}/agent-runs').json()
    assert runs[0]['status']=='completed' and len(runs[0]['tool_calls'])==3


def test_ai_proposal_rejects_stale_revision(ctx):
    sid=session(ctx);rev=ctx.get(f'/api/sessions/{sid}').json()['revision']
    ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'age':27}})
    assert ctx.put(f'/api/sessions/{sid}/facts',json={'facts':{'age':28},'expected_revision':rev}).status_code==409


def test_bad_tool_and_json_logged_without_mutation(ctx,monkeypatch):
    sid=session(ctx)
    fake_model(monkeypatch,[model_calls(('save_tasks',{}),('update_user_facts','bad-json'),('update_user_facts',{'facts':{'secret':'x'}})),{'role':'assistant','content':'처리할 수 없습니다.'}])
    r=ctx.post('/api/agent/message',json={'session_id':sid,'message':'test'}).json()
    assert len(r['tool_calls'])==3 and all(t['status']=='error' for t in r['tool_calls'])
    assert not r['grounded'] and ctx.get(f'/api/sessions/{sid}/tasks').json()==[]
    assert ctx.get(f'/api/sessions/{sid}/agent-runs').json()[0]['status']=='completed_no_analysis'


@pytest.mark.parametrize('exception,code',[(httpx.ReadTimeout('timeout'),504),(ValueError('bad response'),502)])
def test_model_failure_always_finishes_run(ctx,monkeypatch,exception,code):
    sid=session(ctx);monkeypatch.setattr(local_agent,'model_status',lambda:{'ready':True})
    def fail(*a):raise exception
    monkeypatch.setattr(local_agent,'chat',fail)
    assert ctx.post('/api/agent/message',json={'session_id':sid,'message':'test'}).status_code==code
    assert ctx.get(f'/api/sessions/{sid}/agent-runs').json()[0]['status']=='failed'
    assert ctx.get(f'/api/sessions/{sid}/tasks').json()==[]


def test_model_round_limit(ctx,monkeypatch):
    sid=session(ctx)
    fake_model(monkeypatch,[model_calls(('analyze_selected_policies',{}))]*4)
    assert ctx.post('/api/agent/message',json={'session_id':sid,'message':'test'}).status_code==502
    assert ctx.get(f'/api/sessions/{sid}/agent-runs').json()[0]['status']=='failed'


@pytest.mark.parametrize('url',['https://example.org','http://127.0.0.1:11434/path','http://user@localhost:11434'])
def test_remote_ollama_disallowed(monkeypatch,url):
    monkeypatch.setenv('OLLAMA_BASE_URL',url)
    with pytest.raises(ValueError):local_agent.config()


def test_structured_ollama_request_contract(monkeypatch):
    seen=[]
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':json.dumps({'calls':[{'name':'analyze_selected_policies','arguments':{}}],'answer':''})}})
    real_client=httpx.Client
    monkeypatch.setattr(local_agent.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    output=local_agent.chat([{'role':'user','content':'test'}],local_agent.tool_definitions())
    assert output['tool_calls'][0]['function']['name']=='analyze_selected_policies'
    assert seen[0]['stream'] is False and seen[0]['format']['properties']['calls']


def test_truncated_structured_response_is_not_accepted(monkeypatch):
    real_client=httpx.Client
    def respond(request):
        return httpx.Response(200,json={'done_reason':'length','message':{'content':'{"calls":[],"answer":"partial"}'}})
    monkeypatch.setattr(local_agent.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    with pytest.raises(ValueError,match='Truncated'):
        local_agent.chat([{'role':'system','content':'test'}],local_agent.tool_definitions())


def test_legacy_db_migration_retains_tasks(ctx):
    from db import init_db
    sid=session(ctx);before=confirm(ctx,sid).json()['tasks']
    with connect() as con:con.execute('ALTER TABLE preparation_tasks DROP COLUMN generated_fingerprint')
    init_db();init_db()
    after=ctx.get(f'/api/sessions/{sid}/tasks').json()
    assert [t['id'] for t in before]==[t['id'] for t in after]
    assert all(t['outdated'] for t in after)
    assert confirm(ctx,sid).status_code==200


@pytest.mark.parametrize('persona,status',[('unemployed','review_possible'),('receiving','ineligible'),('worker','ineligible')])
def test_three_personas_through_saved_plan(ctx,persona,status):
    sid=session(ctx,persona)
    result=ctx.post('/api/analyze',json={'session_id':sid}).json()
    assert result['results'][0]['status']==status
    assert confirm(ctx,sid).json()['total_proposed']>0
