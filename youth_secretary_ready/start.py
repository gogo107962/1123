"""Run a data-only sync, then start the application."""
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
    print('Open http://127.0.0.1:8000')
    uvicorn.run('app:app', host='127.0.0.1',port=8000, reload=False)
