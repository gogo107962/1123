import json
import httpx
import pytest
from test_project import ctx
from test_catalog_review import seeded
from db import connect
import desk_agent
import ontong


def setup(ctx):
    seeded()
    wid=ctx.post('/api/desk/workspaces').json()['id']
    return '/api/desk/workspaces/'+wid


def plan(ctx,base,eid='0001'):return ctx.get(base+'/policies/'+eid+'/preview').json()
def approve(ctx,base,eid='0001',token=None):
    return ctx.post(base+'/policies/'+eid+'/confirm',json={'approved':True,'preview_token':token or plan(ctx,base,eid)['preview_token']})


def test_service_routes_preserve_lab(ctx):
    assert 'mobile.js' in ctx.get('/').text
    assert 'mobile.js' in ctx.get('/desk/').text
    assert 'desk.js' in ctx.get('/classic').text
    assert '/static/app.js' in ctx.get('/lab').text


def test_bookmark_restore_idempotency_and_isolation(ctx):
    base=setup(ctx);other='/api/desk/workspaces/'+ctx.post('/api/desk/workspaces').json()['id']
    for _ in range(2):assert ctx.put(base+'/bookmarks/0001').status_code==200
    assert len(ctx.get(base).json()['bookmarks'])==1
    assert ctx.get(other).json()['bookmarks']==[]
    assert ctx.put(base+'/bookmarks/not-found').status_code==404
    ctx.delete(base+'/bookmarks/0001')
    assert ctx.get(base).json()['bookmarks']==[]


def test_preview_never_writes_and_unapproved_real_policy_is_not_eligibility(ctx):
    base=setup(ctx);p=plan(ctx,base)
    assert len(p['tasks'])==3 and '자격 판정' in p['notice']
    assert ctx.get(base).json()['tasks']==[]
    assert ctx.post(base+'/policies/0001/confirm',json={'approved':False,'preview_token':p['preview_token']}).status_code==403
    assert len(ctx.get('/api/policies').json())==3


def test_approval_task_toggle_and_repeat_keep_completion(ctx):
    base=setup(ctx);first=approve(ctx,base).json();task=first['tasks'][0]
    assert len(first['tasks'])==3
    assert ctx.patch(base+'/tasks/'+task['id'],json={'status':'done'}).status_code==200
    assert len(approve(ctx,base).json()['tasks'])==3
    assert next(t for t in ctx.get(base).json()['tasks'] if t['id']==task['id'])['status']=='done'
    other='/api/desk/workspaces/'+ctx.post('/api/desk/workspaces').json()['id']
    assert ctx.patch(other+'/tasks/'+task['id'],json={'status':'done'}).status_code==404
    assert approve(ctx,other,token=plan(ctx,base)['preview_token']).status_code==409


def test_changed_evidence_blocks_old_approval_and_completion(ctx):
    base=setup(ctx);old=plan(ctx,base);task=approve(ctx,base).json()['tasks'][0]
    ctx.patch(base+'/tasks/'+task['id'],json={'status':'done'})
    # 수집 해시가 아니라 준비 작업에 영향을 주는 내용(신청기간)이 바뀌어야 '자료가 바뀌었어요'가 된다.
    with connect() as con:con.execute("UPDATE ontong_candidates SET payload_json=json_set(payload_json,'$.aplyYmd','20270101 ~ 20270131') WHERE external_id='0001'")
    assert all(t['outdated'] for t in ctx.get(base).json()['tasks'])
    assert approve(ctx,base,token=old['preview_token']).status_code==409
    assert ctx.patch(base+'/tasks/'+task['id'],json={'status':'done'}).status_code==409
    assert all(t['status']=='todo' and not t['outdated'] for t in approve(ctx,base).json()['tasks'])


def test_source_review_change_invalidates_plan_and_replaces_tasks(ctx,tmp_path,monkeypatch):
    base=setup(ctx);old=plan(ctx,base);approve(ctx,base)
    with connect() as con:sha=con.execute("SELECT sha256 FROM ontong_candidates WHERE external_id='0001'").fetchone()[0]
    (tmp_path/'data').mkdir()
    check={'external_id':'0001','api_sha256':sha,'official_status':'closed','checked_on':'2026-11-16','source_url':'https://example.org/notice'}
    (tmp_path/'data/source_checks.json').write_text(json.dumps([check]),encoding='utf-8');monkeypatch.setattr(ontong,'BASE',tmp_path)
    assert plan(ctx,base)['closed_notice'] is True
    assert approve(ctx,base,token=old['preview_token']).status_code==409
    new=approve(ctx,base).json()['tasks']
    assert len(new)==1 and new[0]['task_key']=='notice'


def test_removing_bookmark_does_not_remove_work(ctx):
    base=setup(ctx);ctx.put(base+'/bookmarks/0001');approve(ctx,base);ctx.delete(base+'/bookmarks/0001')
    assert len(ctx.get(base).json()['tasks'])==3


def test_unknown_workspace_is_not_created_implicitly(ctx):
    assert ctx.get('/api/desk/workspaces/missing').status_code==404
    assert ctx.put('/api/desk/workspaces/missing/bookmarks/0001').status_code==404


def test_ai_calls_read_tools_without_writing_tasks(ctx,monkeypatch):
    base=setup(ctx)
    monkeypatch.setattr(desk_agent,'model_status',lambda:{'ready':True})
    calls=iter([{'calls':['read_policy','preview_tasks'],'focus':[]},{'calls':[],'focus':['application','documents']}])
    monkeypatch.setattr(desk_agent,'generate',lambda messages:next(calls))
    r=ctx.post(base+'/assistant',json={'external_id':'0001','message':'가상 상황에서 무엇부터 확인할까?'})
    assert r.status_code==200
    assert [t['tool'] for t in r.json()['tools']]==['read_policy','preview_tasks']
    assert r.json()['focus']==['application','documents']
    assert r.json()['answer_origin']=='validated_action_selection'
    assert ctx.get(base).json()['tasks']==[]
    with connect() as con:assert con.execute('SELECT status FROM desk_agent_runs').fetchone()[0]=='completed'


def test_ai_without_evidence_is_not_reported_as_success(ctx,monkeypatch):
    base=setup(ctx);monkeypatch.setattr(desk_agent,'model_status',lambda:{'ready':True})
    monkeypatch.setattr(desk_agent,'generate',lambda messages:{'calls':[],'focus':['eligibility']})
    assert ctx.post(base+'/assistant',json={'external_id':'0001','message':'확인'}).status_code==502
    assert ctx.get(base).json()['tasks']==[]


def test_ai_unavailable_preserves_normal_service(ctx,monkeypatch):
    base=setup(ctx);monkeypatch.setattr(desk_agent,'model_status',lambda:{'ready':False})
    assert ctx.post(base+'/assistant',json={'external_id':'0001','message':'확인'}).status_code==503
    assert ctx.put(base+'/bookmarks/0001').status_code==200
    assert approve(ctx,base).status_code==200


@pytest.mark.parametrize('output',[
    {'calls':[],'focus':['auto_apply']},
    {'calls':[],'focus':['documents'],'answer':'신청 가능 확정'}
])
def test_model_cannot_add_unvalidated_action_or_free_claim(monkeypatch,output):
    original=httpx.Client
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'message':{'content':json.dumps(output)}}))
    monkeypatch.setattr(desk_agent.httpx,'Client',lambda **kwargs:original(transport=transport))
    with pytest.raises(ValueError):desk_agent.generate([{'role':'user','content':'test'}])


def test_workspace_lists_the_plans_i_saved_with_progress_and_links(ctx):
    base=setup(ctx)
    assert ctx.get(base).json()['plans']==[]                                  # 승인 전에는 세워 둔 계획이 없다
    saved=approve(ctx,base).json()
    one=saved['plans'][0]
    assert len(saved['plans'])==1 and one['external_id']=='0001' and one['total']==len(saved['tasks']) and one['done']==0 and one['outdated'] is False
    assert len(one['saved_on'])==10 and one['name']==saved['tasks'][0]['policy_name'] and {'period_status','period_label','deadline','links','agency'}<=set(one)
    first=saved['tasks'][0]['id']
    assert ctx.patch(base+'/tasks/'+first,json={'status':'done'}).status_code==200
    assert ctx.get(base).json()['plans'][0]['done']==1                        # 준비 작업을 끝내면 진행이 오른다
    other='/api/desk/workspaces/'+ctx.post('/api/desk/workspaces').json()['id']
    assert ctx.get(other).json()['plans']==[]                                 # 다른 준비 공간에는 보이지 않는다


def test_moving_a_plan_to_ready_marks_all_its_tasks_and_unchecking_one_moves_it_back(ctx):
    base=setup(ctx);approve(ctx,base);approve(ctx,base,'0002')
    assert [p['ready'] for p in ctx.get(base).json()['plans']]==[False,False]   # 승인만 하면 준비 중
    assert ctx.patch(base+'/plans/0001',json={'status':'done'}).json()=={'updated':3}
    now=ctx.get(base).json()
    assert {p['external_id']:p['ready'] for p in now['plans']}=={'0001':True,'0002':False}   # 누른 정책만 옮겨진다
    assert all(t['status']==('done' if t['external_id']=='0001' else 'todo') for t in now['tasks'])
    first=next(t for t in now['tasks'] if t['external_id']=='0001')['id']
    ctx.patch(base+'/tasks/'+first,json={'status':'todo'})                    # 준비 완료에서 체크를 하나 풀면 다시 준비 중
    assert ctx.get(base).json()['plans'][0]['ready'] is False
    for t in ctx.get(base).json()['tasks']:                                   # 하나씩 모두 체크해도 준비 완료
        if t['external_id']=='0002':ctx.patch(base+'/tasks/'+t['id'],json={'status':'done'})
    assert ctx.get(base).json()['plans'][1]['ready'] is True
    other='/api/desk/workspaces/'+ctx.post('/api/desk/workspaces').json()['id']
    assert ctx.patch(other+'/plans/0001',json={'status':'done'}).status_code==404   # 다른 준비 공간의 계획은 바꾸지 못한다
    assert ctx.patch(base+'/plans/0003',json={'status':'done'}).status_code==404    # 세우지 않은 계획
    assert ctx.patch(base+'/plans/0001',json={'status':'ready'}).status_code==422
    # 자료가 바뀐 계획은 옮길 수 없고, 모두 체크돼 있어도 준비 완료로 보지 않는다(다시 승인해야 한다)
    with connect() as con:con.execute("UPDATE ontong_candidates SET payload_json=json_set(payload_json,'$.aplyYmd','20270101 ~ 20270131') WHERE external_id='0002'")
    assert ctx.patch(base+'/plans/0002',json={'status':'done'}).status_code==409
    assert ctx.get(base).json()['plans'][1]['ready'] is False

