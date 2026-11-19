"""Consumer workspace for real, unreviewed policy data. No eligibility claims."""
import hashlib
import json
import secrets
import uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from db import connect
from functools import lru_cache
from ontong import BASE,review_bundle,safe_url

router=APIRouter(prefix='/api/desk')


def require_workspace(wid,con):
    if not con.execute('SELECT 1 FROM desk_workspaces WHERE id=?',(wid,)).fetchone():
        raise HTTPException(404,'준비 공간을 찾을 수 없습니다. 새 공간을 만들어 주세요.')


LINK_CHECKS=BASE/'data'/'link_checks.json'

@lru_cache(maxsize=1)
def _gone(stamp):
    return frozenset(u for u,r in json.loads(LINK_CHECKS.read_text(encoding='utf-8'))['urls'].items() if r['state']=='gone')

def gone_links():
    """링크 점검(tools/check_links.py)에서 페이지가 없다고(404·410) 확인된 주소. 점검 파일이 없으면 아무것도 빼지 않는다.
    연결 실패나 접속 차단(error·unreachable)은 사람이 열면 열릴 수 있어 빼지 않는다."""
    return _gone(LINK_CHECKS.stat().st_mtime_ns) if LINK_CHECKS.exists() else frozenset()


def evidence(external_id):
    bundle=review_bundle(external_id)
    if not bundle:raise HTTPException(404,'정책을 찾을 수 없습니다.')
    p=bundle['public_fields'];check=bundle['source_check']
    links=[]
    for title,value in [('공식 대조 출처',check.get('source_url','') if check else ''),
                        ('참고 안내',p.get('refUrlAddr1','')),('추가 안내',p.get('refUrlAddr2','')),
                        ('신청 안내 사이트',p.get('aplyUrlAddr',''))]:
        url=safe_url(value)
        if url and url not in gone_links() and not any(x['url']==url for x in links):links.append({'title':title,'url':url})
    # Include review evidence in the fingerprint: API data may be unchanged when a notice is corrected.
    fingerprint=hashlib.sha256(json.dumps({'sha':bundle['sha256'],'check':check,'contract':1},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return bundle,links,fingerprint


def preview(wid,external_id):
    with connect() as con:require_workspace(wid,con)
    bundle,links,fingerprint=evidence(external_id)
    p=bundle['public_fields'];check=bundle['source_check']
    closed=bool(check and check['official_status']=='closed' and not check['api_changed_since_check'])
    if closed:
        tasks=[{'key':'notice','title':'다음 모집 공고 확인하기',
                'instructions':f"{check['checked_on']}에 대조한 공식 안내는 접수 종료 상태였습니다. 새 모집 여부와 조건을 공식 사이트에서 확인하세요. 다음 모집일은 아직 입력하지 않았습니다."}]
    else:
        tasks=[{'key':'period','title':'실제 접수기간과 모집 여부 확인하기',
                'instructions':'API 기간은 실제 접수기간과 다를 수 있습니다. 최신 모집공고의 회차·시작일·마감 시각·예산 소진 여부를 확인하세요.'},
               {'key':'conditions','title':'자격과 중복 수혜 제한 확인하기',
                'instructions':'공식 공고에서 거주·연령·소득·취업·이미 받는 지원의 제한을 대조하세요. 이 정책은 전체 조건 검수 전이므로 자격을 확정하지 않았습니다.'},
               {'key':'documents','title':'제출서류와 발급 조건 확인하기',
                'instructions':('API의 서류 안내를 최신 공고와 대조하고 발급일·포함 항목·대체 가능 여부를 확인하세요.' if p.get('sbmsnDcmntCn') else 'API에 서류 안내가 없습니다. 서류가 필요 없다는 뜻이 아니므로 공식 공고나 담당 기관에서 확인하세요.')}]
    if not links:tasks.append({'key':'source','title':'공식 모집공고 주소 찾기','instructions':'수집 정보에 사용 가능한 참고 링크가 없습니다. 담당 기관의 공식 홈페이지에서 같은 연도·회차 공고를 찾아 주세요.'})
    token=hashlib.sha256((wid+'|'+external_id+'|'+fingerprint).encode()).hexdigest()
    return {'external_id':external_id,'name':p['plcyNm'],'preview_token':token,'evidence_hash':fingerprint,
            'tasks':[{**t,'sources':links} for t in tasks],'source_check':check,'closed_notice':closed,
            'notice':'공식 안내를 확인하기 위한 작업입니다. 신청 자격 판정·서류 적합 판정·신청 접수가 아닙니다.'}


class Approval(BaseModel):
    approved:bool=False
    preview_token:str=Field(min_length=1,max_length=100)


class TaskStatus(BaseModel):
    status:str=Field(pattern='^(todo|done)$')


class Ask(BaseModel):
    external_id:str=Field(min_length=1,max_length=80)
    message:str=Field(min_length=1,max_length=600)


@router.post('/workspaces')
def create_workspace():
    wid=secrets.token_urlsafe(32)
    with connect() as con:con.execute('INSERT INTO desk_workspaces(id) VALUES(?)',(wid,))
    return {'id':wid}


@router.get('/workspaces/{wid}')
def workspace(wid:str):
    with connect() as con:
        require_workspace(wid,con)
        saved=[dict(r) for r in con.execute('''SELECT c.external_id,c.name,c.agency,c.summary,c.application_text,
            c.sha256,c.last_seen_at FROM desk_bookmarks b JOIN ontong_candidates c ON c.external_id=b.external_id
            WHERE b.workspace_id=? ORDER BY b.created_at DESC,c.external_id DESC''',(wid,))]
        rows=[dict(r) for r in con.execute('''SELECT t.*,c.name AS policy_name FROM desk_tasks t
            JOIN ontong_candidates c ON c.external_id=t.external_id WHERE workspace_id=? ORDER BY t.created_at,t.external_id,t.task_key''',(wid,))]
    fingerprints={}
    for row in rows:
        eid=row['external_id']
        if eid not in fingerprints:fingerprints[eid]=evidence(eid)[2]
        row['outdated']=row.pop('evidence_hash')!=fingerprints[eid]
        row['sources']=json.loads(row.pop('sources_json'));row.pop('workspace_id')
    return {'id':wid,'bookmarks':saved,'tasks':rows}


@router.put('/workspaces/{wid}/bookmarks/{external_id}')
def bookmark(wid:str,external_id:str):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');require_workspace(wid,con)
        if not con.execute('SELECT 1 FROM ontong_candidates WHERE external_id=?',(external_id,)).fetchone():raise HTTPException(404,'정책을 찾을 수 없습니다.')
        count=con.execute('SELECT count(*) FROM desk_bookmarks WHERE workspace_id=?',(wid,)).fetchone()[0]
        exists=con.execute('SELECT 1 FROM desk_bookmarks WHERE workspace_id=? AND external_id=?',(wid,external_id)).fetchone()
        if count>=100 and not exists:raise HTTPException(422,'관심 정책은 최대 100개까지 저장할 수 있습니다.')
        con.execute('INSERT OR IGNORE INTO desk_bookmarks(workspace_id,external_id) VALUES(?,?)',(wid,external_id))
    return {'saved':True}


@router.delete('/workspaces/{wid}/bookmarks/{external_id}')
def unbookmark(wid:str,external_id:str):
    with connect() as con:
        require_workspace(wid,con)
        con.execute('DELETE FROM desk_bookmarks WHERE workspace_id=? AND external_id=?',(wid,external_id))
    return {'removed':True,'notice':'이미 저장한 준비 작업은 유지됩니다.'}


@router.get('/workspaces/{wid}/policies/{external_id}/preview')
def get_preview(wid:str,external_id:str):return preview(wid,external_id)


@router.post('/workspaces/{wid}/policies/{external_id}/confirm')
def confirm(wid:str,external_id:str,payload:Approval):
    if not payload.approved:raise HTTPException(403,'미리보기 확인과 승인이 필요합니다.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');require_workspace(wid,con)
        plan=preview(wid,external_id)
        if payload.preview_token!=plan['preview_token']:raise HTTPException(409,'정책 정보가 변경됐습니다. 미리보기를 다시 확인하세요.')
        count=con.execute('SELECT count(DISTINCT external_id) FROM desk_tasks WHERE workspace_id=?',(wid,)).fetchone()[0]
        exists=con.execute('SELECT 1 FROM desk_tasks WHERE workspace_id=? AND external_id=?',(wid,external_id)).fetchone()
        if count>=100 and not exists:raise HTTPException(422,'동시에 준비할 수 있는 정책은 최대 100개입니다.')
        keys=[t['key'] for t in plan['tasks']]
        con.execute('DELETE FROM desk_tasks WHERE workspace_id=? AND external_id=? AND task_key NOT IN ('+','.join('?' for _ in keys)+')',[wid,external_id,*keys])
        for task in plan['tasks']:
            con.execute('''INSERT INTO desk_tasks(id,workspace_id,external_id,task_key,title,instructions,sources_json,evidence_hash)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,external_id,task_key) DO UPDATE SET
                title=excluded.title,instructions=excluded.instructions,sources_json=excluded.sources_json,
                status=CASE WHEN desk_tasks.evidence_hash=excluded.evidence_hash THEN desk_tasks.status ELSE 'todo' END,
                evidence_hash=excluded.evidence_hash''',
                (uuid.uuid4().hex,wid,external_id,task['key'],task['title'],task['instructions'],json.dumps(task['sources'],ensure_ascii=False),plan['evidence_hash']))
    return workspace(wid)


@router.patch('/workspaces/{wid}/tasks/{task_id}')
def update_task(wid:str,task_id:str,payload:TaskStatus):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');require_workspace(wid,con)
        row=con.execute('SELECT * FROM desk_tasks WHERE id=? AND workspace_id=?',(task_id,wid)).fetchone()
        if not row:raise HTTPException(404,'이 준비 공간의 작업을 찾을 수 없습니다.')
        if evidence(row['external_id'])[2]!=row['evidence_hash']:raise HTTPException(409,'정보가 바뀐 작업입니다. 정책 상세에서 준비할 일을 다시 확인해 주세요.')
        con.execute('UPDATE desk_tasks SET status=? WHERE id=?',(payload.status,task_id))
    return {'updated':True}


@router.post('/workspaces/{wid}/assistant')
def ask(wid:str,payload:Ask):
    with connect() as con:require_workspace(wid,con)
    from desk_agent import run
    return run(wid,payload.external_id,payload.message)
