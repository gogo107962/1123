"""Run a data-only sync, then start the application.

공개 배포 서버는 HOST=0.0.0.0 과 PORT 를 환경 변수로 준다. 정하지 않으면 전처럼 이 PC(127.0.0.1:8000)에서만 열린다.
"""
import os
from pathlib import Path
from db import init_db
from policy_data import import_policy_file
import uvicorn

if __name__=='__main__':
    init_db()
    for path in sorted((Path(__file__).parent/'data'/'policies').glob('*.json')):
        if path.name.startswith('_'):continue
        outcome,policy_id=import_policy_file(path)
        print(f'[policy] {policy_id}: {outcome}')
    host,port=os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','8000'))
    print(f'Open http://{host}:{port}')
    uvicorn.run('app:app', host=host,port=port, reload=False)
