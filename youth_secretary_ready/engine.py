"""Pure rules engine, tri-valued logic, source-traceable preparation plan."""
from datetime import date, datetime
import hashlib, json
from temporal import application_period, benefit_active_on, korean_now, KST

def evaluate_predicate(p, facts):
    """True, False, or None (unknown). No eval, regex execution, or raw SQL."""
    if 'all' in p:
        vals=[evaluate_predicate(x,facts) for x in p['all']]
        return False if False in vals else (None if None in vals else True)
    if 'any' in p:
        vals=[evaluate_predicate(x,facts) for x in p['any']]
        return True if True in vals else (None if None in vals else False)
    fact, op, target=p['fact'],p['op'],p['value']
    if fact not in facts or facts[fact] is None or facts[fact]=='':return None
    value=facts[fact]
    try:
        if op=='benefit_active_on':
            return benefit_active_on(value,target['code'],facts.get(target['date_fact']),facts.get(target['complete_fact']))
        if op=='eq': return value==target
        if op=='neq': return value!=target
        if op=='in': return value in target
        if op=='not_in': return value not in target
        if op=='contains':return target in value
        if op=='gte':return value>=target
        if op=='lte':return value<=target
        if op=='between':return target[0]<=value<=target[1]
    except (TypeError,ValueError):return None
    raise ValueError(f'Unknown predicate op: {op}')

def predicate_facts(p):
    if p.get('op')=='benefit_active_on':return [p['fact'],p['value']['date_fact'],p['value']['complete_fact']]
    if 'fact' in p:return [p['fact']]
    return sorted(set(f for child in next(iter(p.values())) for f in predicate_facts(child)))

def missing_facts(p, facts):
    if 'all' in p or 'any' in p:
        return sorted({key for child in next(iter(p.values())) if evaluate_predicate(child,facts) is None for key in missing_facts(child,facts)})
    missing=[f for f in predicate_facts(p) if facts.get(f) is None or facts.get(f)=='']
    if p.get('op')=='benefit_active_on':
        target=p['value']
        if facts.get(target['complete_fact']) is not True:missing.append(target['complete_fact'])
        if benefit_active_on(facts.get(p['fact']),target['code'],facts.get(target['date_fact']),True) is None:missing.append(p['fact'])
    return sorted(set(missing))

def ref(p, source_ref):
    s=next((x for x in p['sources'] if x['ref']==source_ref),None)
    return {'title':s.get('title','') if s else '', 'url':s.get('url','') if s else '',
        'anchor':s.get('anchor','') if s else '', 'excerpt':s.get('excerpt','') if s else '',
        'verified':bool(s.get('verified')) if s else False}

def status_policy(policy,facts,today=None):
    today=korean_now() if today is None else today
    when=policy['application']; start=when.get('open'); end=when.get('close')
    findings=[]; missing=set(); blocked=False
    for rule in policy['rules']:
        match=evaluate_predicate(rule['predicate'],facts)
        if match is None: missing.update(missing_facts(rule['predicate'], facts))
        effect=('unknown' if match is None else ('block' if rule['type']=='exclude' and match else
                   'pass' if rule['type']=='exclude' else 'pass' if match else 'block'))
        blocked|=effect=='block'
        findings.append({'rule_id':rule['id'],'type':rule['type'],'match':match,'effect':effect,
                          'message':rule['message'],'missing_facts':missing_facts(rule['predicate'], facts) if match is None else [],
                          'source':ref(policy,rule['source_ref'])})
    for check in policy.get('manual_checks', []):
        findings.append({'rule_id':check['id'],'type':'manual','match':None,'effect':'unknown',
                         'message':check['message'],'missing_facts':[], 'source':ref(policy,check['source_ref'])})
    period_status=application_period(when,today)
    if when.get('closure_notice'):
        closure=when['closure_notice']
        findings.append({'rule_id':'early_closure','type':'period','match':None,
                         'effect':'block' if period_status=='closed' else 'unknown',
                         'message':closure['reason']+' (확인일 '+closure['observed_on']+'; 정확한 조기종료일은 미확인)',
                         'missing_facts':[], 'source':ref(policy,closure['source_ref'])})
    if period_status in ('closed','not_open'):status='application_closed'
    elif blocked:status='ineligible'
    elif period_status=='unknown':status='needs_review'
    elif any(x['effect']=='unknown' for x in findings):status='needs_review'
    else:status='review_possible'
    return {'policy_code':policy['code'],'policy_name':policy['name'],'version':policy['version'],
        'demo_only':policy['demo_only'],'status':status,'period_status':period_status,
        'missing_facts':sorted(missing),'findings':findings,
        'application':when,'official_url':policy.get('official_url',''),
        'reviewed_at':policy['review'].get('reviewed_at'), 'review_status':policy['review']['status'],
        'reviewed_by':policy['review'].get('reviewed_by'),
        'checked_on':today.astimezone(KST).date().isoformat() if isinstance(today,datetime) else today.isoformat()}

def analyze(policies,selected,facts,today=None):
    today=korean_now() if today is None else today
    items=[status_policy(policies[code],facts,today) for code in selected if code in policies]
    conflicts=[]
    for item in items:
        for f in item['findings']:
            if f['type']=='exclude' and f['match'] is True:
                conflicts.append({'policy_code':item['policy_code'],'rule_id':f['rule_id'],
                    'message':f['message'],'source':f['source']})
    return {'results':items,'conflicts':conflicts}

def document_tasks(policy, facts, held_docs):
    out=[]
    for doc in policy['documents']:
        required_when=doc.get('required_when')
        applies=evaluate_predicate(required_when,facts) if required_when else True
        if applies is False:continue
        if applies is None:
            missing=missing_facts(required_when, facts)
            for key in missing:
                out.append(_task(f'fact:{key}',f'서류 조건 확인: {key}',f'{doc["title"]}의 필요 여부를 확인하기 위한 정보입니다.',policy,doc['source_ref']))
            continue
        chosen=doc
        alts=[]; unresolved=False
        for a in doc.get('alternatives',[]):
            check=evaluate_predicate(a['when'],facts)
            if check is True:alts.append(a)
            if check is None:
                unresolved=True
                for key in missing_facts(a['when'], facts):
                    if key:
                        out.append(_task(f'fact:{key}',f'대체서류 조건 확인: {key}',
                                f'{doc["title"]}에 대체서류가 적용되는지 확인하세요.',policy,a['source_ref']))
        if unresolved or len(alts)>1:
            if len(alts)>1:
                out.append(_task(f'doc-review:{policy["code"]}:{doc["code"]}',
                    f'대체서류 선택 확인: {doc["title"]}', '여러 조건이 동시에 충족됩니다. 공식 공고에 따라 사용할 서류를 확인하세요.',policy,doc['source_ref']))
            continue
        if alts:
            chosen={**doc,**alts[0], 'constraints':alts[0].get('constraints',doc.get('constraints',{}))}
        code=chosen['code']; constraints=chosen.get('constraints',{})
        digest=hashlib.sha1(json.dumps(constraints,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:10]
        key=f'doc:{code}:{digest}'
        if held_docs.get(code)=='owned':
            out.append(_task(f'verify:{code}:{digest}',f'보유 서류 조건 확인: {chosen["title"]}',
                f'보유 표시는 유효성 검증이 아닙니다. 발급일·내용·공식 요구사항을 확인하세요. 조건: {json.dumps(constraints,ensure_ascii=False)}',policy,chosen.get('source_ref',doc['source_ref'])))
            continue
        title=f'서류 준비: {chosen["title"]}'
        inst=(chosen.get('instructions') or doc.get('instructions') or '해당 공고의 발급 요건을 확인하세요.')
        if constraints:inst+=' / 확인 조건: '+json.dumps(constraints,ensure_ascii=False)
        out.append(_task(key,title,inst,policy,chosen.get('source_ref',doc['source_ref'])))
    return out

def _task(key,title,instructions,policy,source_ref):
    return {'task_key':key,'title':title,'instructions':instructions,
        'sources':[{'policy_code':policy['code'],'version':policy['version'],'demo_only':policy['demo_only'],'source':ref(policy,source_ref)}]}

def preview_plan(policies,selected,facts,held_docs,today=None):
    results=analyze(policies,selected,facts,today)['results']
    output={}
    for result in results:
        p=policies[result['policy_code']]
        if result['status']=='application_closed':
            task=_task(f'watch:{p["code"]}:{p["version"]}',f'공식 차기 모집 공고 확인: {p["name"]}',
                '다음 모집 일정과 조건은 발표될 때까지 미정입니다.',p,p['sources'][0]['ref'])
            output[task['task_key']]=task
            continue
        if result['status']=='ineligible':
            task=_task(f'block:{p["code"]}:{p["version"]}',f'신청 제한 조건 확인: {p["name"]}',
                '현재 조건에서는 신청이 제한될 수 있습니다. 규정과 기준일을 확인하세요.',p,p['sources'][0]['ref'])
            output[task['task_key']]=task
            continue
        for key in result['missing_facts']:
            task=_task(f'fact:{key}',f'추가 정보 확인: {key}',f'이 항목을 알아야 자격 조건을 판별할 수 있어요.',p,p['sources'][0]['ref'])
            _merge(output,task)
        for finding in result['findings']:
            if finding['type']=='manual':
                check=next(c for c in p['manual_checks'] if c['id']==finding['rule_id'])
                _merge(output,_task(f'manual:{p["code"]}:{check["id"]}','공식 조건 추가 확인',check['message'],p,check['source_ref']))
        if result['period_status']=='unknown':
            _merge(output,_task(f'period:{p["code"]}','모집기간 확인', '모집 시작·마감일이 확인되지 않아 신청 가능 여부를 판단할 수 없습니다.',p,p['sources'][0]['ref']))
        for task in document_tasks(p,facts,held_docs):_merge(output,task)
        task=_task(f'final:{p["code"]}:{p["version"]}',f'신청 전 공식 공고 재확인: {p["name"]}',
            '최종 선정을 보장하지 않으며, 실제 신청 시 최신 공식 공고를 다시 확인하세요.',p,p['sources'][0]['ref'])
        _merge(output,task)
    return {'tasks':list(output.values()),'evaluations':results,'notice':'서류 보유 표시는 사용자의 자기 신고이며 유효성 검증이 아닙니다.'}

def _merge(output,task):
    key=task['task_key']
    if key not in output:output[key]=task
    else:
        output[key]['sources'] += [x for x in task['sources'] if x not in output[key]['sources']]
        if task['instructions'] not in output[key]['instructions']:
            output[key]['instructions']+='\n'+task['instructions']
