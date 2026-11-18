"""Validates policy JSON, upserts normalized SQLite data, loads approved policies.

Never treat raw external API text as verified policy rules.
"""
import json, re, hashlib, sqlite3
import math
from urllib.parse import urlparse
from datetime import date
from pathlib import Path
from db import connect, init_db
from temporal import iso_date, valid_benefit_history, validate_application

FACT_CATALOG = Path(__file__).resolve().parent / 'data' / 'fact_definitions.json'

def get_fact_definitions():
    return json.loads(FACT_CATALOG.read_text(encoding='utf-8'))

ALLOWED_FACTS = set(get_fact_definitions())
ALLOWED_OPS = {'eq', 'neq', 'in', 'not_in', 'contains', 'gte', 'lte', 'between', 'benefit_active_on'}

def https_url(value):
    parsed=urlparse(value if isinstance(value,str) else '')
    return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username

def valid_value(value, spec):
    typ=spec['type']
    if typ in ('integer','number'):
        return (type(value) is int if typ=='integer' else type(value) in (int,float)) and math.isfinite(value) and spec.get('min',-10**12)<=value<=spec.get('max',10**12)
    if typ=='boolean':return type(value) is bool
    if typ=='enum':return isinstance(value,str) and value in spec['options']
    if typ=='string':return isinstance(value,str) and len(value)<=100
    if typ=='string_list':return isinstance(value,list) and len(value)<=30 and all(isinstance(x,str) and len(x)<=80 for x in value)
    if typ=='date':
        try:iso_date(value);return True
        except (TypeError,ValueError):return False
    if typ=='benefit_history':return valid_benefit_history(value)
    return False

def validate_predicate(p, path='predicate'):
    if not isinstance(p, dict): raise ValueError(f'{path}: JSON object required')
    if 'all' in p or 'any' in p:
        if set(p)-{'all','any'}: raise ValueError(f'{path}: unknown logical keys')
        if len(p)!=1: raise ValueError(f'{path}: only one logical operator')
        values = next(iter(p.values()))
        if not isinstance(values,list) or not values: raise ValueError(f'{path}: nonempty array required')
        for n, child in enumerate(values): validate_predicate(child, f'{path}[{n}]')
        return
    if set(p)!={'fact','op','value'}: raise ValueError(f'{path}: fact/op/value required')
    if p['fact'] not in get_fact_definitions(): raise ValueError(f'{path}: unsupported fact {p["fact"]}')
    if p['op'] not in ALLOWED_OPS: raise ValueError(f'{path}: unsupported operator')
    if p['op'] in {'in','not_in','between'} and (not isinstance(p['value'],list) or (p['op']=='between' and len(p['value'])!=2)):
        raise ValueError(f'{path}: this operator expects an array')
    spec=get_fact_definitions()[p['fact']]; op=p['op']; value=p['value']
    if op=='benefit_active_on':
        definitions=get_fact_definitions()
        okay=(spec['type']=='benefit_history' and isinstance(value,dict) and set(value)=={'code','date_fact','complete_fact'}
              and isinstance(value['code'],str) and 1<=len(value['code'])<=80
              and isinstance(value['date_fact'],str) and isinstance(value['complete_fact'],str)
              and definitions.get(value['date_fact'],{}).get('type')=='date'
              and definitions.get(value['complete_fact'],{}).get('type')=='boolean')
    elif op=='contains':
        okay=spec['type']=='string_list' and isinstance(value,str) and len(value)<=80
    elif op in ('gte','lte','between'):
        values=value if op=='between' else [value]
        okay=spec['type'] in ('integer','number','date') and all(valid_value(v,spec) for v in values)
        if okay and op=='between':okay=values[0]<=values[1]
    elif op in ('in','not_in'):
        okay=bool(value) and spec['type'] not in ('string_list','benefit_history') and all(valid_value(v,spec) for v in value)
    else:okay=spec['type']!='benefit_history' and valid_value(value,spec)
    if not okay:raise ValueError(f'{path}: operator/value incompatible with fact type')

def validate_policy(obj):
    if not isinstance(obj,dict):raise ValueError('policy must be an object')
    required = ['code','version','name','category','region','agency','demo_only','application','review','sources','rules','documents']
    for k in required:
        if k not in obj: raise ValueError(f'Missing field: {k}')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,63}',str(obj['code'])): raise ValueError('policy.code: use lowercase ascii/digits/_/-')
    if not re.fullmatch(r'[a-zA-Z0-9._-]{1,48}',str(obj['version'])): raise ValueError('version: invalid')
    if obj.get('official_url') and not https_url(obj['official_url']):
        raise ValueError('official_url: HTTPS URL required')
    if not isinstance(obj['demo_only'],bool): raise ValueError('demo_only must be boolean')
    if not isinstance(obj['sources'],list) or not obj['sources']: raise ValueError('sources: at least one')
    if not isinstance(obj['rules'],list) or not obj['rules']: raise ValueError('rules: at least one')
    if not isinstance(obj['documents'],list): raise ValueError('documents: array required')
    if not isinstance(obj['review'],dict) or not isinstance(obj['application'],dict):raise ValueError('review/application must be objects')
    for key in ('name','category','region','agency'):
        if not isinstance(obj[key],str) or not obj[key].strip():raise ValueError(f'{key}: nonempty text required')
    r = obj['review']; status=r.get('status')
    if status not in {'draft','approved'}: raise ValueError('review.status must be draft or approved')
    app=obj['application']
    validate_application(app)
    ids=set()
    for s in obj['sources']:
        if not s.get('ref') or s['ref'] in ids: raise ValueError('unique source ref required')
        ids.add(s['ref'])
        if not https_url(s.get('url','')): raise ValueError(f'source {s["ref"]}: HTTPS URL required')
        if type(s.get('verified',False)) is not bool:raise ValueError('verified must be boolean')
    if app.get('closure_notice') and app['closure_notice']['source_ref'] not in ids:
        raise ValueError('closure notice source ref missing')
    if status=='approved' and not obj['demo_only']:
        if not r.get('reviewed_by') or not r.get('reviewed_at'): raise ValueError('real approved policy needs reviewer and review date')
        date.fromisoformat(r['reviewed_at'])
        for s in obj['sources']:
            if not s.get('verified') or not s.get('excerpt'): raise ValueError('real approved policy requires verified sources and quotations')
            if 'example.' in s['url']: raise ValueError('real policy cannot use example URL')
    rule_ids=set()
    checks=obj.get('manual_checks',[])
    if not isinstance(checks,list):raise ValueError('manual_checks must be an array')
    check_ids=set()
    for check in checks:
        if not isinstance(check,dict) or not check.get('id') or not check.get('message') or check.get('source_ref') not in ids:
            raise ValueError('manual check needs id/message/source_ref')
        if check['id'] in check_ids:raise ValueError('duplicate manual check id')
        check_ids.add(check['id'])
    for rule in obj['rules']:
        for k in ('id','type','predicate','message','source_ref'):
            if k not in rule: raise ValueError(f'rule missing {k}')
        if rule['id'] in rule_ids: raise ValueError('duplicate rule id')
        rule_ids.add(rule['id'])
        if rule['type'] not in {'required','exclude'}: raise ValueError('rule.type: required or exclude')
        if rule['source_ref'] not in ids: raise ValueError('rule source ref missing')
        validate_predicate(rule['predicate'],f'rule[{rule["id"]}]')
    doc_ids=set()
    for doc in obj['documents']:
        for k in ('code','title','source_ref'):
            if not doc.get(k): raise ValueError(f'document missing {k}')
        if doc['code'] in doc_ids: raise ValueError('duplicate document code')
        doc_ids.add(doc['code'])
        if doc['source_ref'] not in ids: raise ValueError('document source ref missing')
        if doc.get('required_when'):validate_predicate(doc['required_when'],f'doc[{doc["code"]}].required_when')
        if not isinstance(doc.get('constraints',{}),dict):raise ValueError('constraints must be object')
        for alt in doc.get('alternatives',[]):
            if not alt.get('code') or not alt.get('title') or not alt.get('source_ref') or not alt.get('when'): raise ValueError('alternative missing fields')
            if alt['source_ref'] not in ids:raise ValueError('alternative source ref missing')
            validate_predicate(alt['when'],f'alt[{alt["code"]}].when')
            if not isinstance(alt.get('constraints',{}),dict):raise ValueError('alternative constraints must be object')
    return obj

def import_policy_file(path,replace=False):
    obj=validate_policy(json.loads(Path(path).read_text(encoding='utf-8')))
    body=json.dumps(obj, ensure_ascii=False,sort_keys=True)
    sha=hashlib.sha256(body.encode()).hexdigest()
    vid=f'{obj["code"]}:{obj["version"]}'
    with connect() as con:
        old=con.execute('SELECT sha256,status FROM policy_versions WHERE id=?',(vid,)).fetchone()
        if old and old['sha256'] != sha and old['status'] != 'draft' and not replace:
            raise ValueError(f'{vid}: content changed; create a new version or pass --replace intentionally')
        if old and old['sha256']==sha: return ('unchanged',vid)
        con.execute('INSERT INTO policies(code,name,agency,region,category,description,demo_only) VALUES(?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,agency=excluded.agency,region=excluded.region,category=excluded.category,description=excluded.description,demo_only=excluded.demo_only',
            (obj['code'],obj['name'],obj['agency'],obj['region'],obj['category'],obj.get('description',''),int(obj['demo_only'])))
        if old:
            # Foreign keys cascade dependent official sources/rules/docs when replacing version.
            con.execute('DELETE FROM policy_versions WHERE id=?',(vid,))
        con.execute('INSERT INTO policy_versions(id,policy_code,version,status,reviewed_by,reviewed_at,open_date,close_date,source_url,payload_json,sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (vid,obj['code'],obj['version'],obj['review']['status'],obj['review'].get('reviewed_by'),obj['review'].get('reviewed_at'),obj['application'].get('open'),obj['application'].get('close'),obj.get('official_url',''),body,sha))
        for s in obj['sources']:
            con.execute('INSERT INTO policy_sources(id,version_id,reference,kind,title,url,anchor,excerpt,verified) VALUES(?,?,?,?,?,?,?,?,?)',
                (f'{vid}:{s["ref"]}',vid,s['ref'],s.get('kind','notice'),s.get('title',''),s['url'],s.get('anchor',''),s.get('excerpt',''),int(bool(s.get('verified')))))
        for rule in obj['rules']:
            con.execute('INSERT INTO policy_rules(id,version_id,rule_type,source_ref,predicate_json,message) VALUES(?,?,?,?,?,?)',
                (f'{vid}:{rule["id"]}',vid,rule['type'],rule['source_ref'],json.dumps(rule['predicate'],ensure_ascii=False),rule['message']))
        for doc in obj['documents']:
            con.execute('INSERT INTO document_requirements(id,version_id,document_code,title,issuer,source_ref,constraints_json,required_when_json,alternatives_json,instructions) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (f'{vid}:{doc["code"]}',vid,doc['code'],doc['title'],doc.get('issuer',''),doc['source_ref'],json.dumps(doc.get('constraints',{}),ensure_ascii=False),json.dumps(doc.get('required_when'),ensure_ascii=False),json.dumps(doc.get('alternatives',[]),ensure_ascii=False),doc.get('instructions','')))
    return ('imported',vid)

def load_policies():
    # Only approved policy versions, latest version lexicographically (use YYYY or zero-padded integer).
    with connect() as con:
        rows=con.execute("SELECT payload_json FROM policy_versions WHERE status='approved' ORDER BY version DESC").fetchall()
    out={}
    policies_by_code={}
    for row in rows:
        p=json.loads(row['payload_json'])
        policies_by_code.setdefault(p['code'],[]).append(p)
    for code, versions in policies_by_code.items():
        versions.sort(key=lambda x:tuple(int(n) for n in re.findall(r'\d+',x['version'])),reverse=True)
        out[code]=versions[0]
    return out
