"""Youth secretary MVP: data-driven public policy prep, optional LLM tool-calling.
Run `python import_policies.py && uvicorn app:app --reload`.
"""
import os, json, uuid, hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from fastapi import Depends, FastAPI, HTTPException, Body, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from db import connect, init_db, BASE
from policy_data import load_policies, get_fact_definitions, valid_value
from engine import analyze, preview_plan, status_policy
from temporal import korean_now, application_period, aware_time

init_db()
app=FastAPI(title='청년비서 정책 준비 API',version='0.8.0',description='로컬 정책 준비 서비스. 실제 지원 자격을 확정하지 않습니다.')
app.mount('/static',StaticFiles(directory=str(BASE/'static')),name='static')
from desk_service import router as desk_router
app.include_router(desk_router)
from review_service import router as review_router
app.include_router(review_router)
from access import check_rate, require_admin

# 인증이 없는 주소라 한 곳에서 몰아 부르는 요청을 막는다(서버 한 대의 메모리 기준).
@app.middleware('http')
async def rate_limit(request,call_next):
    message=check_rate(request)
    if message:return JSONResponse({'detail':message},status_code=429)
    return await call_next(request)

# 화면은 서버 데이터를 innerHTML로 그리므로, 이스케이프가 빠져도 외부·인라인 스크립트가 실행되지 않게 막는다.
CSP=("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
     "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request)
    response.headers.setdefault('X-Content-Type-Options','nosniff')
    response.headers.setdefault('X-Frame-Options','DENY')
    response.headers.setdefault('Referrer-Policy','no-referrer')
    # API 문서 화면(/docs)은 외부 스크립트를 쓰므로 CSP에서 뺀다.
    if not request.url.path.startswith(('/docs','/redoc','/openapi.json')):response.headers.setdefault('Content-Security-Policy',CSP)
    return response

DEMO_PERSONAS={
 'unemployed': {'age':26,'region':'서울','employment_status':'unemployed','active_benefits':[], 'rent_payment_method':'cash'},
 'receiving': {'age':26,'region':'서울','employment_status':'unemployed','active_benefits':['demo_allowance'], 'rent_payment_method':'cash'},
 'worker': {'age':30,'region':'경기','employment_status':'employed','active_benefits':[], 'rent_payment_method':'bank'}
}

class SessionCreate(BaseModel):
    persona: str='unemployed'
class FactUpdate(BaseModel):
    facts: dict[str,Any]
    expected_revision: int | None=None
class SelectedUpdate(BaseModel):
    selected: list[str]
class DocumentUpdate(BaseModel):
    code: str
    status: str
class SessionRequest(BaseModel):
    session_id: str
class ConfirmRequest(BaseModel):
    session_id: str
    approved: bool=False
    preview_token: str | None=None
class StatusRequest(BaseModel):
    session_id: str
    status: str
class AgentRequest(BaseModel):
    session_id: str
    message: str=Field(min_length=1,max_length=1200)
class PolicyReviewRequest(BaseModel):
    code: str=Field(min_length=3,max_length=64)
    version: str=Field(min_length=1,max_length=48)
    facts: dict[str,Any]
    at: str

class OntongSyncRequest(BaseModel):
    keyword: str=Field(default='월세',max_length=80)
    page_size: int=Field(default=10,ge=1,le=10)
    max_pages: int=Field(default=1,ge=1,le=3)

@app.get('/api/integrations/ontong')
def ontong_status():
    from ontong import status
    return status()

# 외부 API를 부르고 수집 자료를 바꾸는 관리 기능이라 서버 PC(또는 관리 토큰)에서만 실행한다.
@app.post('/api/integrations/ontong/sync',dependencies=[Depends(require_admin)])
def ontong_sync(payload:OntongSyncRequest):
    from ontong import sync, OntongError
    try:return sync(payload.keyword,payload.page_size,payload.max_pages)
    except OntongError as exc:
        status_code={'missing_key':503,'invalid_key':503,'busy':409,'input':422,'rate_limit':429}.get(exc.code,502)
        raise HTTPException(status_code,str(exc)) from None

@app.get('/api/integrations/ontong/candidates')
def ontong_candidates():
    from ontong import candidates
    return candidates()

@app.get('/api/integrations/ontong/search')
def ontong_search(q:str=Query(default='',max_length=80),category:str=Query(default='',max_length=80),
                  quality:str=Query(default='',pattern='^(|missing_period|missing_documents|missing_link)$'),
                  application_code:str=Query(default='',pattern='^(|005700[123])$'),
                  job_code:str=Query(default='',pattern='^(|001300[1-9]|0013010)$'),
                  income_code:str=Query(default='',pattern='^(|004300[123])$'),
                  page:int=Query(default=1,ge=1,le=100000),page_size:int=Query(default=20,ge=1,le=100)):
    from ontong import search_candidates
    return search_candidates(q,category,quality,page,page_size,application_code,job_code,income_code)

@app.get('/api/integrations/ontong/codebook')
def ontong_codebook():
    from policy_codes import CODEBOOK
    return CODEBOOK

class ScreenProfile(BaseModel):
    age: int | None=Field(default=None,ge=0,le=120)
    sido: str | None=Field(default=None,pattern=r'^\d{2}$')
    region_code: str | None=Field(default=None,pattern=r'^\d{5}$')
    job_code: str | None=Field(default=None,pattern=r'^\d{7}$')
    school_code: str | None=Field(default=None,pattern=r'^\d{7}$')
    major_code: str | None=Field(default=None,pattern=r'^\d{7}$')
    marriage_code: str | None=Field(default=None,pattern=r'^\d{7}$')
    # 받고 있는 지원. None=묻지 않음, []=없다고 답함. 이름은 screening.BENEFITS에서 검증한다.
    benefits: list[Annotated[str,Field(min_length=1,max_length=30)]] | None=Field(default=None,max_length=6)
    # 월 소득(만원)과 가구원 수. 기준 중위소득 대비 비율로만 쓴다.
    income_monthly: int | None=Field(default=None,ge=0,le=10000)
    # 내가 해당하는 대상 집단. None=묻지 않음. 이름은 policy_structure.TARGETS에서 검증한다.
    groups: list[Annotated[str,Field(min_length=1,max_length=30)]] | None=Field(default=None,max_length=12)
    household: int | None=Field(default=None,ge=1,le=6)

class ScreenRequest(BaseModel):
    profile: ScreenProfile
    on: str | None=None
    q: str=Field(default='',max_length=80)
    category: str=Field(default='',max_length=80)
    keywords: list[Annotated[str,Field(min_length=1,max_length=20)]]=Field(default=[],max_length=4)
    outcome: str=Field(default='',pattern='^(|api_match|needs_check|api_mismatch)$')
    tier: str=Field(default='',pattern='^(|reviewed|screenable|link_only)$')
    page: int=Field(default=1,ge=1,le=100000)
    page_size: int=Field(default=20,ge=1,le=100)

@app.get('/api/integrations/ontong/regions')
def ontong_regions():
    from policy_structure import SIDO
    from screening import BENEFITS
    from policy_structure import SIGUNGU,TARGETS
    return {'sido':SIDO,'sigungu':SIGUNGU,'benefits':list(BENEFITS),'groups':list(TARGETS),'notice':'시군구 이름은 행정표준코드관리시스템에서 2026-11-18에 확인한 표입니다(사람 검수 전). 폐지된 코드는 고를 수 없습니다.'}

# 가상 프로필과 API 기재값을 비교하는 읽기 전용 걸러보기. 자격 판정·저장을 하지 않는다.
@app.post('/api/integrations/ontong/screen')
def ontong_screen(payload:ScreenRequest):
    from screening import screen_catalog
    from temporal import iso_date
    try:
        on=iso_date(payload.on) if payload.on else korean_now().date()
        return screen_catalog(payload.profile.model_dump(),on,payload.q,payload.outcome,payload.tier,payload.page,payload.page_size,payload.category,payload.keywords)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

class PlanRequest(BaseModel):
    external_ids: list[Annotated[str,Field(min_length=1,max_length=80)]]=Field(min_length=1,max_length=5)
    profile: ScreenProfile=ScreenProfile()
    on: str | None=None

# 고른 정책들의 통합 서류·신청 순서·확인 작업 미리보기. 저장하지 않는다(저장은 정책별 confirm 승인).
@app.post('/api/desk/workspaces/{wid}/plan')
def desk_plan(wid:str,payload:PlanRequest):
    from desk_plan import build
    from screening import validate_profile
    from temporal import iso_date
    try:
        on=iso_date(payload.on) if payload.on else korean_now().date()
        validate_profile(payload.profile.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return build(wid,payload.external_ids,payload.profile.model_dump(),on)

class AskRequest(BaseModel):
    message: str=Field(min_length=1,max_length=600)
    profile: ScreenProfile=ScreenProfile()
    on: str | None=None

# 대화로 정책 찾기. 로컬 모델이 검색어를 고르고 걸러보기·문장은 코드가 만든다. 저장하지 않는다.
@app.post('/api/integrations/ontong/ask')
def ontong_ask(payload:AskRequest):
    from desk_finder import find
    from temporal import iso_date
    try:
        on=iso_date(payload.on) if payload.on else korean_now().date()
        if not payload.message.strip():raise ValueError('질문을 입력해 주세요.')
        return find(payload.message.strip(),payload.profile.model_dump(),on)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

# 정책 하나를 내 정보와 비교한다. API 기재값 비교이며 자격 판정이 아니다.
@app.post('/api/integrations/ontong/candidates/{external_id}/screen')
def ontong_candidate_screen(external_id:str,profile:ScreenProfile):
    from ontong import review_bundle
    from screening import age_rule,approved_policy,engine_view,screen,validate_profile,NOTICE
    bundle=review_bundle(external_id)
    if not bundle:raise HTTPException(404,'수집된 정책을 찾을 수 없습니다.')
    try:validate_profile(profile.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    policy=approved_policy(external_id,bundle['source_check'],load_policies())
    link_only=not policy and bundle['tier']['tier']=='link_only'
    return {**({'tier':'reviewed','reasons':[]} if policy else bundle['tier']),'period_status':bundle['period_status'],'notice':NOTICE,
            'engine':engine_view(policy,profile.model_dump(),korean_now().date()) if policy else None,
            'screen':None if link_only else screen(bundle['structured'],profile.model_dump(),bundle['period_status'],age_rule(bundle['supplements']))}

@app.get('/api/integrations/ontong/candidates/{external_id}')
def ontong_candidate_bundle(external_id:str):
    from ontong import review_bundle
    bundle=review_bundle(external_id)
    if not bundle:raise HTTPException(404,'수집된 정책을 찾을 수 없습니다.')
    return bundle

def _json(data):return json.dumps(data,ensure_ascii=False)

def _session(session_id, con=None):
    if con is None:
        with connect() as dbcon:return _session(session_id,dbcon)
    row=con.execute('SELECT * FROM demo_sessions WHERE id=?',(session_id,)).fetchone()
    if row is None:raise HTTPException(404,'Session not found')
    docs=con.execute('SELECT document_code,status FROM session_documents WHERE session_id=?',(session_id,)).fetchall()
    return {'id':row['id'],'persona':row['persona'],'revision':row['revision'],'facts':json.loads(row['facts_json']),
            'selected':json.loads(row['selected_json']),'documents':{x['document_code']:x['status'] for x in docs}}

def _validate_facts(facts):
    if not isinstance(facts,dict):raise HTTPException(422,'facts must be an object')
    definitions=get_fact_definitions()
    for key,value in facts.items():
        if key not in definitions:raise HTTPException(422,f'Unknown fact: {key}')
        if value is None:continue
        if not valid_value(value,definitions[key]):raise HTTPException(422,f'{key}: invalid value')

def _evaluate(sess):
    policies=load_policies()
    return analyze(policies,sess['selected'],sess['facts'])

def _preview(sess):
    policies=load_policies()
    at=korean_now()
    plan=preview_plan(policies,sess['selected'],sess['facts'],sess['documents'],today=at)
    token=_fingerprint(sess,policies,at)
    plan.update(preview_token=token,revision=sess['revision'])
    return plan

def _fingerprint(sess,policies=None,at=None):
    policies=load_policies() if policies is None else policies
    at=korean_now() if at is None else at
    body={'session':sess,'policies':{code:policies.get(code) for code in sess['selected']},'date':at.date().isoformat(),'plan_contract':3,
          'periods':{code:application_period(policies[code]['application'],at) for code in sess['selected'] if code in policies}}
    return hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

# 앱 화면(팀 프로토타입 기준). 이전 소비자 화면은 /classic 에 보존한다.
@app.get('/')
@app.get('/desk')
@app.get('/desk/')
def root():return FileResponse(str(BASE/'static'/'mobile.html'))

@app.get('/classic')
def classic():return FileResponse(str(BASE/'static'/'desk.html'))

# 사람 검수 화면. 화면 자체는 누구나 열 수 있지만 그 안의 API는 서버 PC(또는 관리 토큰)에서만 응답한다.
@app.get('/review')
def review_page():return FileResponse(str(BASE/'static'/'review.html'))

@app.get('/lab')
def lab():return FileResponse(str(BASE/'static'/'index.html'))

@app.get('/api/health')
def health():
    from local_agent import model_status
    status=model_status()
    return {'ok':True,'policy_count':len(load_policies()),'llm_enabled':status['ready'],'llm':status,'demo_mode':True}

@app.get('/api/policy-catalog')
def policy_catalog():
    with connect() as con:rows=con.execute('SELECT payload_json FROM policy_versions ORDER BY policy_code,version DESC').fetchall()
    return [{'code':p['code'],'name':p['name'],'version':p['version'],'demo_only':p['demo_only'],
             'review':p['review'],'application':p['application'],'official_url':p.get('official_url',''),
             'manual_checks':p.get('manual_checks',[]),'sources':p['sources'],
             'rules':p['rules'],'documents':p['documents'],
             'period_status':application_period(p['application'])} for p in (json.loads(r['payload_json']) for r in rows)]

@app.get('/api/fact-definitions')
def fact_definitions():return {k:v for k,v in get_fact_definitions().items() if not v.get('internal')}

@app.post('/api/policy-review/preview')
def review_policy(payload:PolicyReviewRequest):
    _validate_facts(payload.facts)
    try:at=aware_time(payload.at)
    except (ValueError,TypeError):raise HTTPException(422,'검토 시각과 시간대가 필요합니다.')
    with connect() as con:
        row=con.execute('SELECT payload_json FROM policy_versions WHERE policy_code=? AND version=?',(payload.code,payload.version)).fetchone()
    if not row:raise HTTPException(404,'Policy version not found')
    policy=json.loads(row['payload_json'])
    return {'review_only':True,'at':at.isoformat(),'review_status':policy['review']['status'],
            'analysis':analyze({policy['code']:policy},[policy['code']],payload.facts,today=at),
            'plan':preview_plan({policy['code']:policy},[policy['code']],payload.facts,{},today=at),
            'notice':'가상 조건을 넣은 규칙 검토입니다. 검수 승인·실제 자격 판정·신청·준비판 저장이 아닙니다.'}

@app.get('/api/policies')
def get_policies(q:str=''):
    data=load_policies()
    return [{'code':p['code'],'name':p['name'],'version':p['version'],'agency':p['agency'],
             'region':p['region'],'category':p['category'],'description':p.get('description',''),
             'demo_only':p['demo_only'],'application':p['application'],
             'source_count':len(p['sources']),'rule_count':len(p['rules']),
             'document_count':len(p['documents'])} for p in data.values() if not q or q.lower() in (' '.join([p['name'],p['agency'],p['category'],p['region'],p.get('description','')])).lower()]

@app.get('/api/policies/{code}')
def get_policy(code:str):
    p=load_policies().get(code)
    if not p:raise HTTPException(404,'Policy not found')
    return p

@app.post('/api/sessions')
def create_session(payload:SessionCreate):
    if payload.persona not in DEMO_PERSONAS:raise HTTPException(422,'Invalid demo persona')
    sid=str(uuid.uuid4()); facts=DEMO_PERSONAS[payload.persona].copy()
    with connect() as con:
        con.execute('INSERT INTO demo_sessions(id,persona,facts_json,selected_json) VALUES(?,?,?,?)',
                    (sid,payload.persona,_json(facts),'[]'))
    return _session(sid)

@app.get('/api/sessions/{sid}')
def get_session(sid:str):return _session(sid)

@app.put('/api/sessions/{sid}/facts')
def update_facts(sid:str,payload:FactUpdate):
    _validate_facts(payload.facts)
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        sess=_session(sid,con)
        if payload.expected_revision is not None and payload.expected_revision!=sess['revision']:
            raise HTTPException(409,'조건이 변경되었습니다. 다시 확인하세요.')
        updated={**sess['facts'],**payload.facts}
        if updated==sess['facts']:return sess
        sess['facts']=updated
        con.execute('UPDATE demo_sessions SET facts_json=?,revision=revision+1 WHERE id=?',(_json(sess['facts']),sid))
    return _session(sid)

@app.put('/api/sessions/{sid}/selected')
def update_selected(sid:str,payload:SelectedUpdate):
    _session(sid)
    codes=list(dict.fromkeys(payload.selected))
    if len(codes)>20:raise HTTPException(422,'Too many policies')
    missing=set(codes)-set(load_policies())
    if missing:raise HTTPException(422,f'Unknown/unapproved policy codes: {sorted(missing)}')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if _session(sid,con)['selected']==codes:return _session(sid,con)
        con.execute('UPDATE demo_sessions SET selected_json=?,revision=revision+1 WHERE id=?',(_json(codes),sid))
    return _session(sid)

@app.put('/api/sessions/{sid}/documents')
def set_document(sid:str,payload:DocumentUpdate):
    _session(sid)
    if payload.status not in ('unknown','owned','missing'):raise HTTPException(422,'Invalid document state')
    if not payload.code or len(payload.code)>100:raise HTTPException(422,'Invalid document code')
    allowed={d['code'] for p in load_policies().values() for doc in p['documents'] for d in [doc,*doc.get('alternatives',[])]}
    if payload.code not in allowed:raise HTTPException(422,'Unknown document code')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if _session(sid,con)['documents'].get(payload.code)==payload.status:return _session(sid,con)
        con.execute('INSERT INTO session_documents(session_id,document_code,status) VALUES(?,?,?) ON CONFLICT(session_id,document_code) DO UPDATE SET status=excluded.status',
                    (sid,payload.code,payload.status))
        con.execute('UPDATE demo_sessions SET revision=revision+1 WHERE id=?',(sid,))
    return _session(sid)

@app.post('/api/analyze')
def analyze_request(payload:SessionRequest):
    sess=_session(payload.session_id)
    result=_evaluate(sess)
    with connect() as con:
        for p in result['results']:
            con.execute('INSERT INTO eligibility_checks(id,session_id,policy_version_id,status,result_json) VALUES(?,?,?,?,?)',
                        (str(uuid.uuid4()),payload.session_id,p['policy_code']+':'+p['version'],p['status'],_json(p)))
    return result

@app.post('/api/preview')
def preview_request(payload:SessionRequest):return _preview(_session(payload.session_id))

@app.post('/api/confirm')
def confirm_tasks(payload:ConfirmRequest):
    if not payload.approved:raise HTTPException(403,'Explicit user approval required')
    created=0
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        sess=_session(payload.session_id,con)
        plan=_preview(sess)
        if not payload.preview_token or payload.preview_token!=plan['preview_token']:
            raise HTTPException(409,'미리보기가 없거나 조건·정책이 변경되었습니다. 미리보기를 다시 확인하세요.')
        existing={r['task_key'] for r in con.execute('SELECT task_key FROM preparation_tasks WHERE session_id=?',(payload.session_id,)).fetchall()}
        for task in plan['tasks']:
            if task['task_key'] not in existing:created+=1
            con.execute("""INSERT INTO preparation_tasks(id,session_id,task_key,title,instructions,source_refs_json,generated_revision,generated_fingerprint)
                  VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id,task_key) DO UPDATE SET
                  title=excluded.title,instructions=excluded.instructions,source_refs_json=excluded.source_refs_json,
                  status=CASE WHEN preparation_tasks.generated_fingerprint!=excluded.generated_fingerprint
                              THEN 'todo' ELSE preparation_tasks.status END,
                  generated_revision=excluded.generated_revision,generated_fingerprint=excluded.generated_fingerprint,updated_at=CURRENT_TIMESTAMP""",
                  (str(uuid.uuid4()),payload.session_id,task['task_key'],task['title'],task['instructions'],_json(task['sources']),sess['revision'],plan['preview_token']))
    return {'created':created,'total_proposed':len(plan['tasks']),'tasks':get_tasks(payload.session_id)}

@app.get('/api/sessions/{sid}/tasks')
def get_tasks(sid:str):
    _session(sid)
    with connect() as con:
        con.execute('BEGIN')
        fingerprint=_fingerprint(_session(sid,con))
        rows=con.execute('SELECT id,task_key,title,instructions,status,generated_revision,generated_fingerprint,source_refs_json,created_at FROM preparation_tasks WHERE session_id=? ORDER BY created_at,id',(sid,)).fetchall()
    return [dict(x) | {'sources':json.loads(x['source_refs_json']),'outdated':x['generated_fingerprint']!=fingerprint} for x in rows]

@app.patch('/api/tasks/{task_id}')
def update_task(task_id:str,payload:StatusRequest):
    _session(payload.session_id)
    if payload.status not in ('todo','doing','done'):raise HTTPException(422,'Invalid task status')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT generated_fingerprint FROM preparation_tasks WHERE id=? AND session_id=?',(task_id,payload.session_id)).fetchone()
        if not row:raise HTTPException(404,'Task not found in session')
        if row['generated_fingerprint']!=_fingerprint(_session(payload.session_id,con)):
            raise HTTPException(409,'오래된 준비 작업입니다. 미리보기를 다시 승인하세요.')
        changed=con.execute('UPDATE preparation_tasks SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND session_id=?',(payload.status,task_id,payload.session_id))
        if changed.rowcount==0:raise HTTPException(404,'Task not found in session')
    return {'updated':True,'id':task_id,'status':payload.status}

# Model-selected tools are executed by the server; task writes remain /api/confirm only.
@app.post('/api/agent/message')
def agent_message(payload:AgentRequest):
    from local_agent import run_agent
    return run_agent(_session(payload.session_id),payload.message)

@app.get('/api/sessions/{sid}/agent-runs')
def agent_runs(sid:str):
    _session(sid)
    with connect() as con:
        runs=con.execute('SELECT id,status,response_text,created_at FROM agent_runs WHERE session_id=? ORDER BY created_at DESC,rowid DESC LIMIT 20',(sid,)).fetchall()
        return [dict(r) | {'tool_calls':[dict(t) for t in con.execute('SELECT tool_name,status,sanitized_result_json FROM agent_tool_calls WHERE run_id=? ORDER BY rowid',(r['id'],))]} for r in runs]
