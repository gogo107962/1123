"""가장 최근 전체 수집에 있던 정책을 data/exports/ontong_policy_all_<수집일>.json 으로 내보낸다. 실행 DB는 읽기 전용.

    .venv\\Scripts\\python.exe -X utf8 tools\\export_collection.py

인증키는 수집 단계에서 걸러져 DB에 없다. data/exports/ 는 Git에 올리지 않는다.
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from ontong import CURRENT, ENDPOINT, safe_url  # noqa: E402

con = sqlite3.connect(f'file:{(BASE / "data/youth_secretary.sqlite3").as_posix()}?mode=ro', uri=True)
con.row_factory = sqlite3.Row
run = dict(con.execute("SELECT * FROM ontong_sync_runs WHERE status='success' AND keyword='' AND has_more=0 AND received>30 ORDER BY finished_at DESC LIMIT 1").fetchone())
rows = con.execute('SELECT external_id,first_seen_at,last_seen_at,payload_json,sha256 FROM ontong_candidates WHERE ' + CURRENT + ' ORDER BY external_id').fetchall()
policies = [{'external_id': r['external_id'], 'first_seen_at': r['first_seen_at'], 'last_seen_at': r['last_seen_at'],
             'public_fields': json.loads(r['payload_json']), 'review_status': 'unreviewed', 'sha256': r['sha256']} for r in rows]
fields = [p['public_fields'] for p in policies]
out = {'source': '온통청년 정책 API', 'endpoint': ENDPOINT, 'scope': '검색어 제한 없이 API가 제공한 전체 정책 목록', 'run': run, 'record_count': len(policies),
       'quality': {'missing_application_period': sum(not f.get('aplyYmd') for f in fields),
                   'missing_usable_reference_url': sum(not (safe_url(f.get('refUrlAddr1', '')) or safe_url(f.get('refUrlAddr2', ''))) for f in fields),
                   'missing_document_description': sum(not f.get('sbmsnDcmntCn') for f in fields)},
       'notice': '검수 전 정보입니다. 현재 모집 중이거나 신청 가능한 정책 수가 아닙니다. 원문 첨부파일은 포함하지 않습니다.', 'policies': policies}
path = BASE / 'data/exports' / f"ontong_policy_all_{run['finished_at'][:10]}.json"
path.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
print(path.name, len(policies), out['quality'])
