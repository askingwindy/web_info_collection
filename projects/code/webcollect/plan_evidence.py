"""Observation-bound fact coverage and earned navigation for conditional plan v2."""
from urllib.parse import urldefrag, urlsplit, unquote
import re
import asyncio
import unicodedata
from copy import deepcopy
from .batch_core import load_json
from .plan_protocol import (PLAN_FACTS_PROTOCOL, READING_PLAN_COMPLETION_POLICY as _READING_POLICY,
                            PLAN_EXECUTION_POLICY as _EXECUTION_POLICY, NUMERIC_RESULT_EVIDENCE_POLICY)

VERSION = PLAN_FACTS_PROTOCOL


def same_url(a,b):
    return bool(a and b and urldefrag(a)[0] == urldefrag(b)[0])


def page_label(value, *, decorative_year=False):
    """Only presentation aliases; never infer a business destination."""
    value=unicodedata.normalize('NFKC',unquote(str(value or ''))).replace('_',' ')
    value=re.sub(r'\s+编辑\s*$','',value)
    # Decorative symbols and a trailing current-year title badge are not names.
    value=''.join(c for c in value if unicodedata.category(c) not in ('So','Cf'))
    if decorative_year:
        value=re.sub(r'\s+[（(]?20\d{2}[）)]?\s*$','',value)
    return re.sub(r'\s+','',value).strip()


def page_matches(page,state,navigation=()):
    # Bound URLs are complete identities; parentheses belong to Wiki paths.
    if same_url(page,state['url']):return True
    if urlsplit(page).scheme in ('http','https') and not re.search(r'\s',page):
        return any(same_url(page,n.get('clicked_href')) and same_url(n.get('landed_url'),state['url']) for n in navigation)
    embedded=re.findall(r'https?://[^\s)）]+',page)
    if embedded:
        return any(same_url(u,state['url']) or any(same_url(u,n.get('clicked_href'))
                   and same_url(n.get('landed_url'),state['url']) for n in navigation) for u in embedded)
    if same_url(page,state['url']):return True
    label=page_label(page)
    parsed=urlsplit(state['url'])
    candidates=[state.get('title','')]
    candidates += [e.get('text','') for e in state.get('elements',[])
                   if e.get('visible') is True and e.get('native_role') == 'h1']
    if parsed.path.startswith('/wiki/'):
        candidates.append(unquote(parsed.path[len('/wiki/'):]))
    decoration=parsed.hostname in ('www.muxtly.com','muxtly.com')
    if label and label in {page_label(c,decorative_year=decoration) for c in candidates}:return True
    # A captured click label and its actual synchronized landing prove redirects.
    return any(page_label(n.get('actual_visible_target'))==label
               and same_url(n.get('landed_url'),state['url']) for n in navigation)


def unverified_required_checks(evidence):
    """PENDING semantic auxiliary checks retain their non-blocking meaning."""
    missing=[{'field':c.get('field'),'status':c.get('status'),
             'page':c.get('page'),'region':c.get('region')}
            for c in evidence.get('checks',[]) if c.get('status')=='UNVERIFIED']
    if evidence.get('result_execution_status')=='UNVERIFIED':
        missing.append({'field':'本次输入提交与实际结果绑定','status':'UNVERIFIED',
                        'binding':'result_execution_status'})
    return missing


READING_COMPLETION_POLICY = _READING_POLICY


def remaining_plan_coverage(s, plan, position, evidence):
    """Prove exact remaining purposes from earned body observations only.

    Free purpose paraphrases, navigation labels and heading matches cannot
    establish semantic redundancy. Unknown mappings keep the useful route.
    """
    rows=[]
    after_ids={r.get('after_observation_id') for r in s.trajectory}
    for index,step in enumerate(plan.get('steps',[])[position:],position+1):
        predicate=step.get('expected') or {}
        purpose=str(step.get('purpose') or '').strip()
        proofs=[]
        if predicate.get('kind')=='visible_text' and predicate.get('text') and purpose:
            for check in evidence.get('checks',[]):
                if check.get('status')!='VERIFIED' or purpose not in (
                        str(check.get('field') or '').strip(),str(check.get('purpose') or '').strip()):
                    continue
                for proof in check.get('evidence',[]):
                    oid=proof.get('observation_id');obs=s.observation_records.get(oid)
                    if oid not in after_ids or not obs or not obs.get('capture_verified'):continue
                    state=load_json(obs['evidence']['state']['path'])
                    node=next((e for e in state.get('elements',[]) if e['element_id']==proof.get('node')),None)
                    # A heading, link, input echo or isolated year is not a body
                    # answer. Reading it may still end as an honest short flow.
                    text=(node or {}).get('text') or ''
                    if (not node or node.get('visible') is not True
                            or node.get('native_role') not in ('p','li','dd','dt','td','th','blockquote','pre')
                            or not re.search(r'[A-Za-z\u4e00-\u9fff]',text)
                            or predicate['text'] not in text):continue
                    region=predicate.get('region') or check.get('region')
                    if not region_matches(state,node['element_id'],region,business_aliases=True):continue
                    proofs.append({'field':check.get('field'),'observation_id':oid,'node':node['element_id'],
                        'quote':text,'url':state['url'],
                        'action_refs':[{'operation_id':r['operation_id'],'after_observation_id':oid}
                                       for r in s.trajectory if r.get('after_observation_id')==oid]})
        rows.append({'plan_step':index,'purpose':purpose,'expected':predicate,
                     'status':'COVERED' if proofs else 'UNRESOLVED','evidence':proofs,
                     'reason':None if proofs else 'No exact purpose-to-verified-body-fact binding; keep remaining useful work'})
    return {'policy':READING_COMPLETION_POLICY,'status':'COVERED' if all(r['status']=='COVERED' for r in rows) else 'UNRESOLVED',
            'remaining_steps':rows,'model_semantic_review':False}


def region_matches(state, cid, region, *, business_aliases=False):
    if not region: return True
    elements={e['element_id']:e for e in state.get('elements',[])}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    e=elements.get(cid,{})
    selector=bindings.get(cid,{}).get('selector','')
    if business_aliases and region in ('结果区','结果区域','计算结果','计算结果/正文','计算结果/业务区域','IRS计算器结果区') and bindings.get(cid,{}).get('result_region_selector'):
        return True
    # A free result-area name is not proof that an arbitrary main paragraph
    # contains this execution's result. Demand captured semantic containment.
    if business_aliases and region in ('结果区','结果区域','计算结果','计算结果/正文','计算结果/业务区域','IRS计算器结果区'):
        visited=set();node=e
        while node and node.get('element_id') not in visited:
            visited.add(node['element_id'])
            if (node.get('visible') is True and node.get('native_role') in ('table','output','status')
                    and re.search(r'\d',node.get('text') or '')):
                return True
            node=elements.get(node.get('parent_id'),{})
        # Canonical selectors record real tag ancestry even when a container
        # has no independent rendered node. Match tag tokens, never CSS names.
        return bool(re.search(r'(?:^| > )(?:table|output)(?=:| > |$)',selector))
    if region in ('正文','main','article'):
        if any(x in selector for x in ('main','article','#content','.article','.content')):return True
        # Canonical selectors deliberately omit classes/IDs. Use a unique
        # rendered heading and its captured container, never a guessed class.
        headings=[n for n in elements.values() if n.get('visible') is True and n.get('native_role')=='h1' and n.get('bbox')]
        if len(headings)==1:
            title=headings[0];ts=bindings.get(title['element_id'],{}).get('selector','')
            parent=ts.rsplit(' > ',1)[0] if ' > ' in ts else ''
            b=e.get('bbox');h=title['bbox']
            if parent.count(' > ')>=3 and selector.startswith(parent+' > ') and b and h[0]<=b[0]<b[2]<=h[2]:return True
        return False
    if region in ('左栏','左栏菜单','左侧目录','左侧菜单'):
        b=e.get('bbox');width=state.get('screen_resolution',[0])[0]
        if not b or b[2]>width*.35:return False
        if any(x in selector for x in ('left','sidebar','menu','nav','aside')):return True
        # A visible aligned group in the same captured DOM container, with
        # distinct labels and same-site hrefs, establishes an actual menu.
        parent=selector.rsplit(' > ',1)[0] if ' > ' in selector else ''
        if parent.count(' > ')<3:return False
        siblings=[]
        host=urlsplit(state['url']).hostname
        for key,n in elements.items():
            bind=bindings.get(key,{})
            box=n.get('bbox');sel=bind.get('selector','')
            if (n.get('visible') is True and n.get('native_role')=='a' and n.get('text') and box
                and box[2]<=width*.35 and abs(box[0]-b[0])<=8
                and sel.rsplit(' > ',1)[0]==parent and urlsplit(bind.get('href') or '').hostname==host):siblings.append(n)
        return len({n.get('text') for n in siblings})>=3 and len({n['bbox'][1] for n in siblings})>=3
    titles=[n for n in elements.values() if n.get('visible') is True and n.get('bbox') and n.get('native_role') in ('h1','h2','h3') and region in (n.get('text') or '')]
    if len(titles)==1:
        title=titles[0];ts=bindings.get(title['element_id'],{}).get('selector','')
        parent=ts.rsplit(' > ',1)[0] if ' > ' in ts else ''
        b=e.get('bbox');h=title['bbox']
        if parent.count(' > ')>=3 and selector.startswith(parent+' > ') and b and h[0]<=b[0]<b[2]<=h[2]:return True
    visited=set()
    while e and e.get('element_id') not in visited:
        visited.add(e['element_id'])
        if e.get('visible') is True and region in (e.get('text') or ''):return True
        e=elements.get(e.get('parent_id'),{})
    return False


def observed_basis(s, objective_evidence):
    """Archive-derived witnesses, without interpreting a free-text check field."""
    selected = (objective_evidence or {}).get('selected_passage')
    # The full citation remains owned by session_objective, with its original
    # observation. Do not copy every observed paragraph into every fact check.
    passages = ([{'reference':'session_objective.selected_passage',
                  **{k:selected[k] for k in ('observation_id','node') if k in selected}}]
                if selected else [])
    observations = {}
    for row in s.trajectory:
        if row.get('action') not in ('click', 'back'):continue
        for key in ('before_observation_id', 'after_observation_id'):
            oid = row[key]
            obs = s.observation_records.get(oid)
            if oid not in observations and obs and obs.get('capture_verified'):
                observations[oid] = (obs, load_json(obs['evidence']['state']['path']))
    navigation = []
    for row in s.trajectory:
        if row.get('action') not in ('click', 'back'):continue
        before = observations.get(row['before_observation_id'])
        after = observations.get(row['after_observation_id'])
        if not before or not after:continue
        _, origin = before; _, landing = after
        cid = (row.get('target') or {}).get('control_id')
        element = next((e for e in origin.get('elements',[]) if e['element_id']==cid), {})
        binding = next((b for b in origin.get('capture_controls',[]) if b['element_id']==cid), {})
        navigation.append({'operation_id':row['operation_id'], 'action':row['action'],
            'before_observation_id':row['before_observation_id'],
            'after_observation_id':row['after_observation_id'], 'node':cid,
            'actual_visible_target':element.get('text'), 'clicked_href':binding.get('href'),
            'origin_url':origin['url'], 'landed_url':landing['url'],
            'origin_document_identity':origin.get('document_identity'),
            'landed_document_identity':landing.get('document_identity'),
            'landed_title':landing.get('title')})
    return {'passages':passages, 'navigation':navigation,
        'interpretation':'Observed witnesses only; no semantic mapping from free-text checks or independent QC judgment'}


PLAN_EXECUTION_POLICY = _EXECUTION_POLICY


def bind_check_pages(plan, registered_pages):
    """Freeze this plan's original checks against its own registered page IDs."""
    from .planning import object_sha256
    pages={}
    for row in registered_pages:
        key,url=row['page_id'],row['url']
        if key in pages and pages[key]!=url:
            raise ValueError('A registered page ID cannot identify different URLs in one plan')
        pages[key]=url
    resolved=[]
    for check in plan.get('checks',[]):
        label=check.get('page') or ''
        url=pages.get(label)
        if url is None and re.fullmatch(r'(?:p[0-9]+(?:或p[0-9]+)+(?:对应章节正文)?|p[0-9]+对应章节正文)',label):
            urls=[pages.get(key) for key in re.findall(r'p[0-9]+',label)]
            if all(urls) and len({urldefrag(value)[0] for value in urls})==1:
                url=urldefrag(urls[0])[0]
        resolved.append(url)
    body={'policy':PLAN_EXECUTION_POLICY,'pages':pages,
          'checks':deepcopy(plan.get('checks',[])),'resolved_pages':resolved}
    return {**body,'binding_sha256':object_sha256(body)}


def verify_page_binding(plan, binding):
    if not isinstance(binding,dict):raise ValueError('New plan execution requires its frozen page binding')
    expected=bind_check_pages(plan,[{'page_id':key,'url':url} for key,url in binding.get('pages',{}).items()])
    if expected!=binding:raise ValueError('Frozen plan page binding differs from its original checks or registry')
    return binding


def facts(s,plan, *, page_urls=None, objective_evidence=None, page_binding=None):
    checks=plan.get('checks',[]); rows=[]
    bound_plan=bool(hasattr(s,'task') and s.task.get('fragment',{}).get('plan_execution_policy')==PLAN_EXECUTION_POLICY)
    if bound_plan:verify_page_binding(plan,page_binding)
    modern=bool(hasattr(s,'task'))
    basis=observed_basis(s,objective_evidence) if modern else None
    navigation=basis['navigation'] if basis else []
    from .result_completion import answer_rows
    mapped_rows=answer_rows(s,plan,page_binding=page_binding)
    for check_index,original_check in enumerate(checks):
        if mapped_rows is not None:
            rows.append(mapped_rows[check_index]);continue
        check=deepcopy(original_check)
        # A process check can name its business item before the answer exists.
        # Resolve only explicit submitted algebra steps on its frozen page.
        from .numeric_result_evidence import process_field, process_result_text
        process_check=bool(check.get('page') and process_field(check.get('field','')))
        from .result_execution import VERSION as RESULT_VERSION
        execution_policy=getattr(s,'task',{}).get('fragment',{}).get('result_execution_policy')==RESULT_VERSION
        inferred_result_region=bool(execution_policy and check.get('page') and check.get('visible_text') and not check.get('region'))
        if inferred_result_region:check['region']='结果区'
        if process_check and check.get('page'):
            check['region']=check.get('region') or '结果区'
            check['visible_text']=check.get('visible_text') or ''
        if not process_check and not all(check.get(key) for key in ('page','region','visible_text')):
            rows.append({**check,'status':'PENDING','evidence':[], 'seen_outside_allowed_source':[],
                         'missing_binding_fields':[key for key in ('page','region','visible_text') if not check.get(key)],
                         'available_basis':'host_observed_basis',
                         'binding_status':'PENDING_SEMANTIC_MAPPING'})
            continue
        proofs=[];other=[];seen=set()
        from .result_execution import VERSION as RESULT_VERSION, RESULT_REGIONS, result_execution_binding
        execution_policy=getattr(s,'task',{}).get('fragment',{}).get('result_execution_policy')==RESULT_VERSION
        # A page ID denotes the URL shown in this plan's first request, even after navigation.
        bound_url = page_binding['resolved_pages'][check_index] if bound_plan else (page_urls or {}).get(check['page'])
        if (not bound_plan and bound_url is None and hasattr(s,'task')
                and s.task.get('fragment',{}).get('reading_completion_policy')==READING_COMPLETION_POLICY
                and re.fullmatch(r'(?:p[0-9]+(?:或p[0-9]+)+(?:对应章节正文)?|p[0-9]+对应章节正文)',check['page'])):
            # The model may name alternative registered section anchors of
            # one article. Resolve only this finite ID syntax; prose, unknown
            # IDs and alternatives belonging to different documents stay unbound.
            page_ids=re.findall(r'p[0-9]+',check['page'])
            urls=[(page_urls or {}).get(page_id) for page_id in page_ids]
            if all(urls) and len({urldefrag(url)[0] for url in urls})==1:
                bound_url=urldefrag(urls[0])[0]
        if execution_policy and bound_url is None:
            known_pages=page_binding.get('pages',{}) if page_binding else (page_urls or {})
            if check['page'] in known_pages.values():bound_url=check['page']
        for oid,obs in s.observation_records.items():
            if not obs.get('capture_verified'):continue
            state=load_json(obs['evidence']['state']['path'])
            headings=[e.get('text') for e in state.get('elements',[]) if e.get('visible') is True and e.get('native_role') in ('h1','h2','h3')]
            if bound_url is not None:
                page_ok = (page_matches(bound_url,state,navigation) if modern
                           else same_url(bound_url,state['url']))
            elif bound_plan and re.match(r'^p[0-9]+',check['page']):
                page_ok=False
            else:
                page_ok = (page_matches(check['page'],state,navigation) if modern else
                           same_url(check['page'], state['url']) or check['page'] in headings)
            values={v['element_id']:v for v in state.get('values',[])}
            for e in state.get('elements',[]):
                quote=e.get('text') or ''
                value=values.get(e['element_id'],{})
                source='host_synchronized_rendered_node'
                if (check['visible_text'] not in quote and value.get('value_visible') is True
                        and value.get('display_value')==check['visible_text']):
                    quote=value['display_value'];source='host_synchronized_visible_input_value'
                execution_binding=None
                if execution_policy:
                    from .numeric_result_evidence import numeric_target
                    result_check=(check.get('region') in RESULT_REGIONS or numeric_target(check['visible_text'],check.get('field','')))
                    if result_check:
                        if not bound_url or not page_ok:continue
                        execution_binding=result_execution_binding(s,oid,state,e)
                        if not execution_binding:continue
                if execution_binding:
                    from .numeric_result_evidence import substantive_result_text
                    if not substantive_result_text(quote,field=check.get('field','')):continue
                process_match=bool(process_check and execution_binding and process_result_text(quote,check.get('field','')))
                numeric_match=None
                numeric_policy=(getattr(s,'task',{}).get('fragment',{}).get('numeric_result_evidence_policy')
                                in (NUMERIC_RESULT_EVIDENCE_POLICY,'webcollect-numeric-result-evidence-1'))
                if numeric_policy:
                    from .numeric_result_evidence import match_result, numeric_target, weak_result_text
                    if weak_result_text(check['visible_text']):continue
                    numeric_match=match_result(check['visible_text'],quote,field=check.get('field',''),
                        result_bound=bool(bound_url and page_ok and check.get('region') and
                            region_matches(state,e['element_id'],check['region'],business_aliases=modern) and
                            region_matches(state,e['element_id'],'结果区',business_aliases=True)),
                        input_node=bool(e.get('inputable') or e.get('native_role') in ('input','select','textarea')
                                        or source=='host_synchronized_visible_input_value'))
                    if (check['region'] in ('结果区','结果区域','计算结果','计算结果/正文','计算结果/业务区域','IRS计算器结果区')
                            and numeric_target(check['visible_text'],check.get('field','')) and not numeric_match):continue
                if e.get('visible') is not True or (not process_match and (not check['visible_text'] or check['visible_text'] not in quote) and not numeric_match):continue
                if process_check and not process_match:continue
                key=(state['url'],e['element_id'],quote)
                if key in seen:continue
                seen.add(key)
                proof={'observation_id':oid,'url':state['url'],'document_identity':state.get('document_identity'),
                       'image':obs['evidence']['image'],'state':obs['evidence']['state'],
                       'node':e['element_id'],'bbox':e.get('bbox'),'quote':quote,
                       'source':source, **({'result_execution_binding':execution_binding} if execution_binding else {}), **({'numeric_result_match':numeric_match} if numeric_match else {})}
                if modern:
                    proof['action_refs']=[{'operation_id':r['operation_id'],'before_observation_id':r['before_observation_id'],'after_observation_id':r['after_observation_id']} for r in s.trajectory if oid in (r.get('before_observation_id'),r.get('after_observation_id'))]
                (proofs if page_ok and region_matches(state,e['element_id'],check['region'],business_aliases=modern) else other).append(proof)
        rows.append({**original_check,**({'host_resolved_process_check':True} if process_check else {}),**({'host_resolved_region':'结果区'} if inferred_result_region else {}),**({'resolved_page':bound_url} if bound_url is not None else {}),
                     'status':'VERIFIED' if proofs else 'UNVERIFIED',
                     'evidence':proofs,'seen_outside_allowed_source':other,
                     **({'observed_visible_text':proofs[0]['quote']} if any(p.get('numeric_result_match') for p in proofs) else {})})
    done=sum(r['status']=='VERIFIED' for r in rows)
    from .result_execution import VERSION as RESULT_VERSION
    result_policy=getattr(s,'task',{}).get('fragment',{}).get('result_execution_policy')==RESULT_VERSION
    result_task=result_policy and any(r.get('action') in ('type','select') for r in s.trajectory) and (
        any(urlsplit(obs.get('url','')).hostname in ('muxtly.com','www.muxtly.com') for obs in s.observation_records.values())
        or bool(re.search(r'计算|計算|换算|換算',s.requested_goal or s.working_goal or '')))
    has_result=any(p.get('result_execution_binding') for row in rows for p in row.get('evidence',[]))
    execution_status='VERIFIED' if has_result else 'UNVERIFIED' if result_task else 'NOT_REQUIRED'
    return {'protocol':VERSION,'requested_goal':s.requested_goal,'working_goal':s.working_goal,
            'checks':rows,'verified':done,'total':len(rows),
            **({'host_observed_basis':observed_basis(s, objective_evidence)} if any(r['status']=='PENDING' for r in rows) else {}),
            'business_goal_status':('UNVERIFIED' if execution_status=='UNVERIFIED' else ('VERIFIED' if done==len(rows) else 'PARTIAL' if done else 'UNVERIFIED') if rows else 'NOT_SPECIFIED'),
            **({'result_execution_status':execution_status} if result_policy else {}),
            'fragment_effective_steps':len(s.trajectory),'is_ai_review':False,
            **({'result_completion':deepcopy(s.result_completion)} if getattr(s,'result_completion',None) else {})}


def expected_navigation(s,controller):
    if not controller.last or not s.trajectory or controller.position>=len(controller.plan['steps']):return None
    row=s.trajectory[-1]
    if row.get('after_observation_id')!=s.current['observation_id']:return None
    before=s.observation_records[row['before_observation_id']]
    if before['document_identity']==s.current['document_identity']:return None
    action=row.get('action')
    previous=controller.plan['steps'][controller.position-1]
    contracted_search = (previous['expected']['kind'] == 'search_results'
                         and action in ('click','hotkey')
                         and urlsplit(before['url']).netloc == urlsplit(s.current['url']).netloc
                         and controller.proved(previous['expected'], s))
    href=None;execution_proof=None
    from .plan_execution import enabled, step_execution_proof
    if enabled(s.task):
        execution_proof=step_execution_proof(s.task,previous,row,
            load_json(before['evidence']['state']['path']),
            load_json(s.current['evidence']['state']['path']),
            target_id=(row.get('target') or {}).get('control_id'))
    if action=='click':
        cid=(row.get('target') or {}).get('control_id')
        href=(before['controls'].get(cid,{}).get('binding') or {}).get('href')
        if not same_url(href,s.current['url']) and not contracted_search and not execution_proof:return None
    elif action not in ('open_url','back') and not contracted_search:return None
    from .banded_plan import proves,bind_target
    if execution_proof:
        pass
    elif previous['expected']['kind'] in ('document_changed','search_results'):
        if not controller.proved(previous['expected'], s, load_json(before['evidence']['state']['path'])):return None
    elif not proves(previous['expected'],s.current):return None
    step=controller.plan['steps'][controller.position]
    if step.get('target'):
        matches = controller.targets(s,step['target'])
        if len(matches)!=1:return None
    if step['action']=='open_url' and step['page_id'] not in ['p'+str(i) for i in range(len(s.page_urls))]:return None
    return {'source_observation_id':before['observation_id'],'landing_observation_id':s.current['observation_id'],
            'operation_id':row['operation_id'],'clicked_href':href,'landed_url':s.current['url'],
            'expected':previous['expected'],'next_step':step,'new_model_requests':0,
            **({'execution_proof':execution_proof} if execution_proof else {})}


def native_form_intent(operation, state):
    """Only a snapshot-bound native submit click or focused single Enter."""
    action = operation.get('action_type')
    evidence = operation.get('evidence', {})
    cid = evidence.get('anchor_element_id') or evidence.get('focused_element_id')
    binding = next((b for b in state.get('capture_controls', []) if b['element_id'] == cid), {})
    form = binding.get('form_submission')
    if not form or form.get('target') != '_blank':return None
    if action == 'click':
        if binding.get('tag') not in ('button', 'input') or binding.get('input_type') != 'submit':return None
        if binding.get('selector') != form.get('submitter_selector'):return None
    elif action == 'hotkey':
        if [str(k).lower() for k in operation.get('arguments', {}).get('keys', [])] != ['enter']:return None
        if binding.get('tag') != 'input' or binding.get('input_type') not in ('text','search','url','tel','email','number'):return None
        if not any(v.get('element_id') == cid and v.get('focused') is True for v in state.get('values', [])):return None
    else:return None
    return deepcopy(form)


async def arm_native_form(origin, operation, state):
    intent = native_form_intent(operation, state)
    if not intent:return None
    # A short-lived listener observes the default browser path. It never
    # cancels or repeats an event, and FormData is deliberately not constructed.
    await asyncio.wait_for(origin.evaluate("""intent=>{
      const key=Symbol.for('webcollect.native-form-submit');
      const previous=globalThis[key];if(previous)previous.form.removeEventListener('submit',previous.listener,true);
      const form=document.querySelector(intent.form_selector);
      if(!form)throw new Error('FORM_SOURCE_STALE');
      const selector=n=>{if(!n)return null;const parts=[];for(;n&&n.nodeType===1;n=n.parentElement){const siblings=n.parentElement?[...n.parentElement.children].filter(x=>x.localName===n.localName):[n];parts.unshift(n.localName+':nth-of-type('+(siblings.indexOf(n)+1)+')');}return parts.join(' > ');};
      const entry={form,events:[]};
      entry.listener=e=>{if(e.target!==form)return;entry.events.push({event:e,
        source_url:location.href,source_document:{url_without_fragment:location.href.split('#')[0],performance_time_origin:performance.timeOrigin}});};
      entry.serialize=r=>({trusted:r.event.isTrusted,default_prevented:r.event.defaultPrevented,
        form_selector:selector(r.event.target),submitter_selector:selector(r.event.submitter),
        source_url:r.source_url,source_document:r.source_document});
      form.addEventListener('submit',entry.listener,true);globalThis[key]=entry;
    }""", intent), timeout=2)
    requests=[];request_log=[]
    def requested(request):
        if request.is_navigation_request():
            requests.append(request)
            request_log.append({'url':request.url,'method':request.method,'post_data':request.post_data,
                'content_type':request.headers.get('content-type',''),'redirected':request.redirected_from is not None})
    origin.context.on('request', requested)
    return {'intent':intent,'requests':requests,'listener':requested,'context':origin.context,'request_log':request_log}


async def finish_native_form(origin, watcher):
    if not watcher:return None
    watcher['events'] = await origin.evaluate("""()=>{
      const key=Symbol.for('webcollect.native-form-submit'),entry=globalThis[key];
      if(!entry)return [];entry.form.removeEventListener('submit',entry.listener,true);
      delete globalThis[key];return entry.events.map(entry.serialize);
    }""")
    return {'intent':watcher['intent'],'events':watcher['events']}


def validate_native_form_popup(proof, operation, state, landed_url):
    """Recompute frozen form encoding, real submit/request/opener witnesses.

    Called online and from sealed postprocessing; flags alone grant no source.
    Redirects and script interception remain unsupported.
    """
    from urllib.parse import urlencode, urlunsplit
    from .collect import verify_public_url
    intent = native_form_intent(operation, state)
    if not intent or proof.get('form_intent') != intent:raise ValueError('POPUP_FORM_BINDING_UNPROVEN')
    if intent.get('method') not in ('get','post') or intent.get('enctype') != 'application/x-www-form-urlencoded':
        raise ValueError('POPUP_FORM_ENCODING_UNSUPPORTED')
    events = proof.get('submit_events', [])
    if len(events) != 1:raise ValueError('POPUP_NATIVE_SUBMIT_UNPROVEN')
    event=events[0]
    if (event.get('trusted') is not True or event.get('default_prevented') is not False
            or event.get('form_selector') != intent['form_selector']
            or event.get('submitter_selector') != intent['submitter_selector']
            or event.get('source_url') != state['url'] or event.get('source_document') != state.get('document_identity')):
        raise ValueError('POPUP_NATIVE_SUBMIT_UNPROVEN')
    if proof.get('opener') != {'url':state['url'],'document_identity':state.get('document_identity')}:
        raise ValueError('POPUP_SOURCE_UNPROVEN')
    fields=intent.get('fields')
    if not isinstance(fields,list) or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,str) for v in p) for p in fields):
        raise ValueError('POPUP_FORM_ENCODING_UNSUPPORTED')
    normalize=lambda v:re.sub(r'\r\n|\r|\n', '\r\n', v)
    encoded=urlencode([(normalize(k),normalize(v)) for k,v in fields], safe='*').replace('~','%7E')
    action=urlsplit(intent['action']);verify_public_url(intent['action']);verify_public_url(landed_url)
    expected_url=urlunsplit((action.scheme,action.netloc,action.path,encoded if intent['method']=='get' else action.query,''))
    request=proof.get('initial_request') or {}
    if (request.get('method') != intent['method'].upper() or request.get('url') != expected_url
            or request.get('redirected') is not False or proof.get('initial_request_count') != 1
            or (intent['method']=='post' and (request.get('post_data') != encoded
                or request.get('content_type','').split(';')[0].strip() != intent['enctype']))
            or (intent['method']=='get' and request.get('post_data') not in (None,''))
            or urldefrag(landed_url)[0] != expected_url or proof.get('landed_url') != landed_url):
        raise ValueError('POPUP_FORM_REQUEST_UNPROVEN')
    if (proof.get('source_url') != state['url'] or proof.get('source_document') != state.get('document_identity')
            or proof.get('source_node') != (operation.get('evidence',{}).get('anchor_element_id') or operation.get('evidence',{}).get('focused_element_id'))):
        raise ValueError('POPUP_SOURCE_UNPROVEN')
    return True


async def verify_popup(origin,opened,operation,state,form_watcher=None):
    """Earned links or witnessed native form submits; uncertainty stays blocked."""
    if await opened.opener()!=origin:raise ValueError('POPUP_SOURCE_UNPROVEN')
    cid=operation.get('evidence',{}).get('anchor_element_id') or operation.get('evidence',{}).get('focused_element_id')
    binding=next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})
    href=binding.get('href')
    await opened.wait_for_load_state('domcontentloaded',timeout=30000)
    if operation['action_type']=='click' and href and urlsplit(href).scheme in ('http','https') and same_url(href,opened.url):
        return {'source_url':state['url'],'source_document':state.get('document_identity'),
            'source_node':cid,'clicked_href':href,'opener_verified':True,'landed_url':opened.url,
            'atomic_actions':1,'new_page_first_frame':'following synchronized observation'}
    if not form_watcher:raise ValueError('POPUP_LANDING_UNPROVEN')
    requests=[]
    for request in form_watcher['requests']:
        try:
            if request.frame==opened.main_frame:requests.append(request)
        except Exception:continue  # An unbound service-worker request proves nothing.
    request=requests[0] if requests else None
    opener_document=await asyncio.wait_for(origin.evaluate('()=>({url_without_fragment:location.href.split("#")[0],performance_time_origin:performance.timeOrigin})'),timeout=2)
    proof={'kind':'native_form','source_url':state['url'],'source_document':state.get('document_identity'),
        'source_node':cid,'form_intent':form_watcher['intent'],'submit_events':form_watcher.get('events',[]),
        'initial_request_count':len(requests),'initial_request':({'url':request.url,'method':request.method,
            'post_data':request.post_data,'content_type':request.headers.get('content-type',''),
            'redirected':request.redirected_from is not None} if request else None),
        'opener':{'url':origin.url,'document_identity':opener_document},'landed_url':opened.url,
        'atomic_actions':1,'new_page_first_frame':'following synchronized observation'}
    form_watcher['popup_proof'] = deepcopy(proof)
    validate_native_form_popup(proof,operation,state,opened.url)
    return proof
