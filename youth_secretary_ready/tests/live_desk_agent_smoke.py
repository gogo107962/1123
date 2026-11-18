"""Explicit real local-model call on a public policy; no real user profile."""
import json,time
from pathlib import Path
import httpx

started=time.monotonic()
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=360,trust_env=False) as c:
    state=c.get('/api/health').json()
    assert state['llm_enabled'],'Ollama must be running with the downloaded local model'
    wid=c.post('/api/desk/workspaces').json()['id'];base='/api/desk/workspaces/'+wid
    r=c.post(base+'/assistant',json={'external_id':'20261021005400214208','message':'이 공고를 지금 신청할 수 있는지 확정하지 말고, 공식 안내의 모집기간과 다음에 확인할 일을 도구로 확인해줘.'})
    data=r.json()
    result={'http_status':r.status_code,'elapsed_seconds':round(time.monotonic()-started,2),'result':data}
    Path('.local/live-desk-agent.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    r.raise_for_status()
    assert {t['tool'] for t in data['tools']}=={'read_policy','preview_tasks'}
    assert c.get(base).json()['tasks']==[]
    assert data['sources']
    assert data['evidence_context']['checked_on']=='2026-11-16'
    assert '2026-05-19' in data['evidence_context']['period']
    print(json.dumps({'passed':True,'elapsed_seconds':result['elapsed_seconds'],'tools':data['tools'],'saved_tasks':0,'answer':data['answer']},ensure_ascii=False))
