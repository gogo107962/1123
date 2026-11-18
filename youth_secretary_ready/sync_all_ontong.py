"""Explicit full-API enumeration with durable checkpoints and atomic publication.

No search filter. This CLI is not called by the web UI or application startup.
The API has no snapshot token: count/ID/first-page checks detect common drift,
but do not establish that all records were read at one atomic upstream instant.
"""
import argparse
import json
import time
import uuid
from pathlib import Path
import httpx
from db import BASE, connect, init_db
from ontong import read_key, _page, save_candidates, get_run, LOCK, OntongError
from temporal import korean_now

CHECKPOINT = BASE / '.local' / 'ontong-full-checkpoint.json'


def checkpoint_write(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def fetch(client, key, page, size, pause):
    for attempt in range(3):
        try:return _page(client, key, '', page, size)
        except OntongError as exc:
            # Never retry authentication, 429 or schema errors automatically.
            if exc.code != 'upstream' or attempt == 2:raise
            pause(attempt + 1)


def sync_all(*, resume=False, checkpoint=CHECKPOINT, transport=None, pause=time.sleep,
             progress=lambda info:None, page_size=100):
    if not 1 <= page_size <= 100:raise ValueError('page_size must be 1..100')
    key = read_key()
    if not LOCK.acquire(blocking=False):raise OntongError('busy')
    state = None
    try:
        if resume:
            state = json.loads(Path(checkpoint).read_text(encoding='utf-8'))
            if state['complete'] or state['page_size'] != page_size:raise ValueError('Start a new run; checkpoint is completed or has a different page size.')
            previous=get_run(state['run_id'])
            if not previous or previous['status']=='success':raise ValueError('Checkpoint is completed or belongs to a different database.')
            with connect() as con:
                con.execute("UPDATE ontong_sync_runs SET status='running',error_code=NULL,finished_at=NULL WHERE id=?",(state['run_id'],))
        else:
            state = {'run_id':uuid.uuid4().hex,'page_size':page_size,'total':None,'pages':0,
                     'items':[],'first_page':[],'complete':False,'started_at':korean_now().isoformat()}
            with connect() as con:
                con.execute('INSERT INTO ontong_sync_runs(id,keyword,status,started_at) VALUES(?,?,?,?)',
                            (state['run_id'],'','running',state['started_at']))
            checkpoint_write(checkpoint,state)
        try:
            seen = {x['external_id'] for x in state['items']}
            if len(seen)!=len(state['items']):raise OntongError('schema')
            with httpx.Client(timeout=httpx.Timeout(40,connect=8),trust_env=False,
                              follow_redirects=False,transport=transport) as client:
                if resume and state['pages']:
                    first,total=fetch(client,key,1,page_size,pause)
                    if total!=state['total'] or [(x['external_id'],x['sha256']) for x in first]!=[tuple(x) for x in state['first_page']]:raise OntongError('schema')
                while state['total'] is None or len(state['items'])<state['total']:
                    page=state['pages']+1
                    items,total=fetch(client,key,page,page_size,pause)
                    if state['total'] is not None and total!=state['total']:raise OntongError('schema')
                    if len({x['external_id'] for x in items})!=len(items) or seen.intersection(x['external_id'] for x in items):raise OntongError('schema')
                    if page==1:state['first_page']=[(x['external_id'],x['sha256']) for x in items]
                    state.update(total=total,pages=page)
                    state['items'].extend(items);seen.update(x['external_id'] for x in items)
                    checkpoint_write(checkpoint,state)
                    with connect() as con:
                        con.execute('UPDATE ontong_sync_runs SET pages=?,received=?,matched_total=?,has_more=? WHERE id=?',
                                    (page,len(seen),total,int(len(seen)<total),state['run_id']))
                    progress({'page':page,'collected':len(seen),'total':total})
                    if len(seen)<total:pause(0.4)
                first,total=fetch(client,key,1,page_size,pause)
                if total!=len(seen) or [(x['external_id'],x['sha256']) for x in first]!=[tuple(x) for x in state['first_page']]:raise OntongError('schema')
            finished=korean_now().isoformat()
            with connect() as con:
                con.execute('BEGIN IMMEDIATE')
                changed=save_candidates(con,state['items'],finished,state['run_id'])
                con.execute("UPDATE ontong_sync_runs SET status='success',finished_at=?,changed=?,has_more=0 WHERE id=?",
                            (finished,changed,state['run_id']))
            state.update(complete=True,finished_at=finished)
            try:checkpoint_write(checkpoint,state)
            except OSError:pass  # Committed DB status remains the source of truth.
            return get_run(state['run_id'])
        except Exception as exc:
            error=exc if isinstance(exc,OntongError) else OntongError('storage')
            with connect() as con:
                con.execute("UPDATE ontong_sync_runs SET status='failed',finished_at=?,error_code=? WHERE id=?",
                            (korean_now().isoformat(),error.code,state['run_id']))
            raise error from None
    finally:LOCK.release()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='온통청년 전체 정책 수집. 키는 서버 파일/환경변수로만 읽습니다.')
    parser.add_argument('--resume',action='store_true',help='마지막 미완료 수집을 이어갑니다.')
    args=parser.parse_args()
    init_db()
    try:
        result=sync_all(resume=args.resume,progress=lambda info:print(json.dumps(info,ensure_ascii=False),flush=True))
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    except (OntongError,ValueError,OSError) as exc:
        print(str(exc) if isinstance(exc,OntongError) else '체크포인트를 확인하세요. 새 수집은 --resume 없이 실행합니다.',flush=True)
        raise SystemExit(1) from None
