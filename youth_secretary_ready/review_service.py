"""사람 검수 화면용 API.

초안(data/policy_drafts)을 검수자가 공고 원문과 대조한 뒤 승인하면 data/policies 로 옮기고 판별 엔진에 등록한다.
- 승인에는 검수자 이름과, 출처마다 '원문에서 직접 확인한 문장'이 있어야 한다. 서버가 스스로 승인하지 않는다.
- 확인하지 않은 출처와 그 출처에 기댄 규칙·서류는 승인본에서 뺀다. 확인이 필요한 항목(manual_checks)은 버리지 않는다.
- 서버를 실행한 PC(또는 관리 토큰)에서만 쓸 수 있다.
"""
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import ontong
from access import require_admin
from policy_data import import_policy_file, load_policies, validate_policy
from temporal import korean_now

router = APIRouter(prefix='/api/review', dependencies=[Depends(require_admin)])
CODE = re.compile(r'[a-z0-9][a-z0-9_-]{2,63}')


def _draft(code):
    path = ontong.BASE / 'data' / 'policy_drafts' / f'{code}.json'
    if not CODE.fullmatch(code) or not path.exists():
        raise HTTPException(404, '초안을 찾을 수 없습니다.')
    return json.loads(path.read_text(encoding='utf-8'))


@router.get('/drafts')
def drafts():
    folder, approved = ontong.BASE / 'data' / 'policy_drafts', load_policies()
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))] if folder.exists() else []
    return [{'code': d['code'], 'name': d['name'], 'agency': d['agency'], 'rules': len(d['rules']), 'checks': len(d.get('manual_checks', [])),
             'documents': len(d['documents']), 'sources': len(d['sources']), 'approved': d['code'] in approved,
             'approved_by': approved[d['code']]['review'].get('reviewed_by') if d['code'] in approved else None} for d in rows]


@router.get('/drafts/{code}')
def draft(code: str):
    return _draft(code)


class Approval(BaseModel):
    reviewed_by: str = Field(min_length=2, max_length=40)
    confirmed: bool = False
    # 출처 ref → 검수자가 원문에서 직접 확인한 문장. 여기에 없는 출처는 승인본에서 뺀다.
    sources: dict[str, str] = Field(default_factory=dict)
    keep_rules: list[str] = Field(default_factory=list, max_length=40)


@router.post('/drafts/{code}/approve')
def approve(code: str, payload: Approval):
    if not payload.confirmed:
        raise HTTPException(403, '공고 원문과 직접 대조했다는 확인이 필요합니다.')
    name = payload.reviewed_by.strip()
    if len(name) < 2:
        raise HTTPException(422, '검수자 이름을 입력해 주세요.')
    source = _draft(code)
    quotes = {ref: text.strip() for ref, text in payload.sources.items() if len(text.strip()) >= 5}
    sources = [{**s, 'excerpt': quotes[s['ref']], 'verified': True} for s in source['sources'] if s['ref'] in quotes]
    rules = [r for r in source['rules'] if r['id'] in payload.keep_rules and r['source_ref'] in quotes]
    if not sources or not rules:
        raise HTTPException(422, '원문 문장을 확인한 출처와, 그 출처에 근거한 규칙이 하나 이상 필요합니다.')
    first = sources[0]['ref']
    policy = {**source, 'sources': sources, 'rules': rules,
              # 확인이 필요한 항목은 출처를 확인하지 못했어도 남긴다(판정이 '확인 필요'로 유지된다).
              'manual_checks': [c if c['source_ref'] in quotes else {**c, 'source_ref': first} for c in source.get('manual_checks', [])],
              'documents': [d for d in source['documents'] if d['source_ref'] in quotes],
              'review': {'status': 'approved', 'reviewed_by': name, 'reviewed_at': korean_now().date().isoformat()}}
    try:
        validate_policy(policy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    folder = ontong.BASE / 'data' / 'policies'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{code}.json'
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    try:
        outcome, version = import_policy_file(path, replace=True)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {'approved': True, 'code': code, 'version': version, 'outcome': outcome, 'reviewed_by': name,
            'rules': len(rules), 'sources': len(sources), 'dropped_sources': [s['ref'] for s in source['sources'] if s['ref'] not in quotes]}
