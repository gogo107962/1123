"""Explicit local LLM extraction + approval check, using only a fictional profile."""
import json
from pathlib import Path
import time
import httpx

started=time.monotonic()
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=400,trust_env=False) as client:
    sid=client.post('/api/sessions',json={'persona':'unemployed'}).json()['id']
    client.put(f'/api/sessions/{sid}/selected',json={'selected':['demo_rent']}).raise_for_status()
    response=client.post('/api/agent/message',json={'session_id':sid,'message':
        '가상 프로필에서 나이는 27세이고 월세는 계좌이체로 냈어. 이 두 정보만 변경 제안하고, 변경된 조건으로 자격 분석과 준비 서류를 도구로 확인해 줘. 아직 저장하지 마.'})
    result=response.json()
    evidence={'http_status':response.status_code,'elapsed_seconds':round(time.monotonic()-started,2),'result':result}
    path=Path(__file__).resolve().parents[1]/'.local'/'live-facts-smoke.json'
    path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    response.raise_for_status()
    assert result['proposed_facts']=={'age':27,'rent_payment_method':'bank'},result
    assert client.get(f'/api/sessions/{sid}').json()['facts']['age']==26
    assert client.get(f'/api/sessions/{sid}/tasks').json()==[]
    confirmed=client.put(f'/api/sessions/{sid}/facts',json={'facts':result['proposed_facts'],'expected_revision':result['base_revision']})
    confirmed.raise_for_status();assert confirmed.json()['facts']['age']==27
    plan=client.post('/api/preview',json={'session_id':sid}).json()
    assert any('bank_rent_proof' in t['task_key'] for t in plan['tasks'])
    saved=client.post('/api/confirm',json={'session_id':sid,'approved':True,'preview_token':plan['preview_token']})
    saved.raise_for_status()
    evidence['facts_persisted_after_confirmation']=True;evidence['db_tasks_saved']=len(saved.json()['tasks'])
    path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'elapsed_seconds':evidence['elapsed_seconds'],'tool_calls':result['tool_calls'],'proposed_facts':result['proposed_facts'],'db_tasks_saved':evidence['db_tasks_saved']},ensure_ascii=False))
