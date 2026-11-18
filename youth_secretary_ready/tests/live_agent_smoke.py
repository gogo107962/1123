"""Explicit live local-model smoke test; never collected by pytest."""
import json
import time
from pathlib import Path
import httpx

BASE=Path(__file__).resolve().parents[1]
started=time.monotonic()
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=400,trust_env=False) as client:
    health=client.get('/api/health').json()
    assert health['llm_enabled'],health
    sid=client.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    client.put(f'/api/sessions/{sid}/selected',json={'selected':['demo_rent','demo_allowance']}).raise_for_status()
    response=client.post('/api/agent/message',json={'session_id':sid,'message':
        '가상 사용자야. 선택한 가상 정책의 자격과 중복 제한을 분석하고, 현금으로 월세를 낸 경우 필요한 서류와 준비 작업을 도구로 확인해 줘.'})
    result=response.json()
    evidence={'session_id':sid,'http_status':response.status_code,'model':health['llm'],
              'elapsed_seconds':round(time.monotonic()-started,2),'result':result}
    output=BASE/'.local'/'live-agent-smoke.json'
    output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    response.raise_for_status()
    names={t['tool'] for t in result['tool_calls'] if t['status']=='ok'}
    assert {'analyze_selected_policies','preview_preparation_tasks'}<=names,result
    assert result['grounded']
    assert client.get(f'/api/sessions/{sid}/tasks').json()==[]
    plan=client.post('/api/preview',json={'session_id':sid}).json()
    assert any('cash_rent_confirmation' in t['task_key'] for t in plan['tasks'])
    saved=client.post('/api/confirm',json={'session_id':sid,'approved':True,'preview_token':plan['preview_token']})
    saved.raise_for_status();tasks=saved.json()['tasks']
    assert tasks
    client.patch('/api/tasks/'+tasks[0]['id'],json={'session_id':sid,'status':'done'}).raise_for_status()
    assert client.get(f'/api/sessions/{sid}/tasks').json()[0]['status']=='done'
    evidence['db_tasks_saved']=len(tasks);evidence['completion_persisted']=True
    evidence['runs']=client.get(f'/api/sessions/{sid}/agent-runs').json()
    output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'elapsed_seconds':evidence['elapsed_seconds'],'tool_calls':result['tool_calls'],
                      'db_tasks_saved':len(tasks),'evidence':str(output)},ensure_ascii=False))
