"""Private continuation package. Does not alter application sources or its database."""
import ast
import csv
import hashlib
import io
import json
import shutil
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / 'youth_secretary_ready'
BUILD = HERE / '.build'
ARCHIVE = ROOT / '청년비서_새채팅_인계패키지_2026-11-17.zip'
SOURCE_XLSX = Path('C:/Users/User/Downloads/API코드정보.xlsx')
EXCLUDED_DIRS = {'.git', '.venv', '.local', '__pycache__', '.pytest_cache', '.build'}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def excluded_reason(relative):
    if relative.name == 'ontong_api_key.txt' or relative.name.startswith('.env'):
        return '비공개 설정: 내용과 해시 제외'
    if '.git' in relative.parts:
        return 'Git 메타데이터: 제외'
    if '.venv' in relative.parts:
        return 'Python 설치 환경: 재생성'
    if '.local' in relative.parts:
        if 'models' in relative.parts or 'ollama' in relative.parts or relative.suffix == '.zip':
            return '로컬 AI 바이너리/모델: 기존 위치 재사용 또는 별도 설치'
        if relative.suffix == '.png':
            return '과거 검증 캡처: evidence/previous_ui에 사본 포함'
        return '로컬 실행/검증/수집 부속 파일: 원본 보존, ZIP 제외'
    if '__pycache__' in relative.parts or '.pytest_cache' in relative.parts or relative.suffix == '.pyc':
        return '캐시: 제외'
    if '.build' in relative.parts:
        return '패키지 생성 중간물: 목록 제외'
    if relative.suffix == '.sqlite3':
        return 'DB: SQLite backup 사본으로 포함'
    if relative.name.endswith(('.sqlite3-wal', '.sqlite3-shm')):
        return 'DB 보조파일: 일관된 backup에 통합'
    return '소스/문서/데이터: 포함'


def main():
    BUILD.mkdir(exist_ok=True)
    source_db = APP / 'data/youth_secretary.sqlite3'
    backup_db = BUILD / 'youth_secretary.sqlite3'
    with sqlite3.connect(source_db.as_uri() + '?mode=ro', uri=True) as source:
        integrity = source.execute('pragma integrity_check').fetchone()[0]
        foreign_keys = len(source.execute('pragma foreign_key_check').fetchall())
        names = [r[0] for r in source.execute("select name from sqlite_master where type='table' order by name")]
        tables = {name: source.execute('select count(*) from ' + name).fetchone()[0] for name in names}
        with sqlite3.connect(backup_db) as target:
            source.backup(target)
    assert integrity == 'ok' and foreign_keys == 0
    with sqlite3.connect(backup_db) as check:
        assert check.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert check.execute('select count(*) from ontong_candidates').fetchone()[0] == 4020

    pyfiles = [p for p in APP.rglob('*.py') if not any(part in EXCLUDED_DIRS for part in p.relative_to(APP).parts)]
    for file in pyfiles:
        ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(file))
    codebook = json.loads((APP / 'data/ontong_codebook.json').read_text(encoding='utf-8'))
    assert len(codebook['groups']) == 11
    assert sum(len(g['codes']) for g in codebook['groups'].values()) == 69
    assert SOURCE_XLSX.exists() and digest(SOURCE_XLSX) == codebook['source']['sha256']
    export = APP / 'data/exports/ontong_policy_all_2026-11-16.json'
    assert digest(export) == '26c62cd07fdb845610ed26865db5bb5f0e8fb0341a234a04995e2f53710e1bad'

    external = [SOURCE_XLSX,
        Path('C:/Users/User/Documents/카카오톡 받은 파일/청년비서_주제제안.html'),
        Path('C:/Users/User/Downloads/%EC%B2%AD%EB%85%84%EB%B9%84%EC%84%9C_%EC%BD%94%EB%8D%B1%EC%8A%A4_%EC%9D%B8%EA%B3%84%ED%8C%A8%ED%82%A4%EC%A7%80 (2).zip')]
    snapshot = {
        'as_of_kst': '2026-11-17', 'original_root': str(ROOT), 'application': str(APP),
        'database': {'integrity': integrity, 'foreign_key_errors': foreign_keys, 'tables': tables,
                     'backup_method': 'sqlite3.Connection.backup from read-only source', 'backup_sha256': digest(backup_db)},
        'policy_export': {'relative_path': str(export.relative_to(ROOT)), 'bytes': export.stat().st_size, 'sha256': digest(export)},
        'codebook': {'groups': 11, 'codes': 69, 'source_sha256': digest(SOURCE_XLSX),
                     'missing': ['zipCd地域mapping', 'income amount unit', 'age Y/N semantics']},
        'validation': {'python_ast_files': len(pyfiles), 'python_ast': 'passed during handoff',
                       'desk_js_syntax': 'Node --check passed during handoff',
                       'last_full_pytest_record': '145 passed before two later desk AI tests',
                       'last_targeted_record': 'test_desk.py: 13 passed before codebook/app UI changes',
                       'latest_pytest_attempt': 'interrupted; no passing result; exit 1',
                       'latest_codebook_filters': 'no dedicated regression tests yet',
                       'latest_app_ui': 'not browser-tested; old screenshots must not be reused as new evidence'},
        'git': 'application and parent planning documents were untracked; no commit/tag recorded',
        'services_running': 'not verified at handoff; do not reuse prior PIDs',
        'secrets': {'ontong_key_present': (APP / '.local/ontong_api_key.txt').exists(),
                    'contents_included': False, 'hash_included': False},
        'external_references': [{'path': str(p), 'exists': p.exists(), 'bytes': p.stat().st_size if p.exists() else None} for p in external],
        'next_action': 'Read handoff, run regression, validate latest code filters and mobile app UI before further features.'
    }
    write_json(HERE / '04_현재상태.json', snapshot)

    inventory = []
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p == ARCHIVE:
            continue
        rel = p.relative_to(ROOT)
        if '.build' in rel.parts or rel.name in {'05_전체파일목록.csv', '06_패키지구성.json'}:
            continue
        reason = excluded_reason(rel)
        has_hash = reason == '소스/문서/데이터: 포함'
        inventory.append({'relative_path': rel.as_posix(), 'bytes': p.stat().st_size,
                          'category': reason, 'sha256': digest(p) if has_hash else ''})
    with (HERE / '05_전체파일목록.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['relative_path', 'bytes', 'category', 'sha256'])
        writer.writeheader()
        writer.writerows(inventory)

    files = {}
    for row in inventory:
        rel = Path(row['relative_path'])
        if row['category'] == '소스/문서/데이터: 포함':
            files[rel.as_posix()] = ROOT / rel
    files['youth_secretary_ready/data/youth_secretary.sqlite3'] = backup_db
    files['references/API코드정보.xlsx'] = SOURCE_XLSX
    # Original proposal is supporting history only. If present, preserve it without executing it.
    if external[1].exists():
        files['references/청년비서_주제제안.html'] = external[1]
    for path in (APP / '.local').glob('*.png'):
        files['evidence/previous_ui/' + path.name] = path
    files['HANDOFF_2026-11-17/05_전체파일목록.csv'] = HERE / '05_전체파일목록.csv'
    manifest = {
        'purpose': 'Private development continuation, not a public submission package',
        'source_inventory_count': len(inventory),
        'source_inventory_bytes': sum(x['bytes'] for x in inventory),
        'category_counts': dict(Counter(x['category'] for x in inventory)),
        'inventory_excludes': ['this ZIP', 'handoff/.build intermediates', 'self-generated inventory and manifest'],
        'excluded_contents': ['API key and .env', 'models and Ollama binaries', '.venv', 'logs and local JSON runs', '.git', 'caches'],
        'notes': ['No source or active database files modified by packaging.',
                  'DB is a consistent backup and retains development sessions and workspace tokens.',
                  'Previous UI screenshots are historical evidence, not validation of latest UI.',
                  'SHA256 of the inventory covers the CSV as a file; CSV does not inventory itself.',
                  'Manifest is included in ZIP but does not contain its own hash.'],
        'entries': [{'archive_path': name, 'bytes': p.stat().st_size, 'sha256': digest(p)} for name, p in sorted(files.items())]
    }
    write_json(HERE / '06_패키지구성.json', manifest)
    files['HANDOFF_2026-11-17/06_패키지구성.json'] = HERE / '06_패키지구성.json'

    # Compare the known secret only in memory. Never log it or a hash of it.
    key_path = APP / '.local/ontong_api_key.txt'
    secret = key_path.read_text(encoding='utf-8-sig').strip() if key_path.exists() else ''
    needles = [secret.encode('utf-8'), secret.encode('utf-16-le')] if secret else []
    for name, path in files.items():
        assert not any(x in Path(name).parts for x in {'.venv', '.git', '.local'})
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            raise RuntimeError('Known secret detected in a proposed package file; packaging stopped.')
    with zipfile.ZipFile(ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, path in sorted(files.items()):
            z.write(path, arcname=name)
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(files)
        for entry in manifest['entries']:
            assert hashlib.sha256(z.read(entry['archive_path'])).hexdigest() == entry['sha256']
    print(json.dumps({'archive': str(ARCHIVE), 'archive_bytes': ARCHIVE.stat().st_size,
                      'archive_entries': len(files), 'inventory_files': len(inventory),
                      'database_policies': tables['ontong_candidates'], 'integrity': integrity,
                      'known_api_key_included': False, 'zip_crc_and_hash_checks': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
