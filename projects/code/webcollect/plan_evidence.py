"""Observation-bound fact coverage and earned navigation for conditional plan v2."""
from urllib.parse import urldefrag, urlsplit
from .batch_core import load_json

VERSION = 'webcollect-plan-facts-1'


def same_url(a,b):
    return bool(a and b and urldefrag(a)[0] == urldefrag(b)[0])


def region_matches(state, cid, region):
    if not region: return True
    elements={e['element_id']:e for e in state.get('elements',[])}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    e=elements.get(cid,{})
    selector=bindings.get(cid,{}).get('selector','')
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


def facts(s,plan, *, page_urls=None, objective_evidence=None):
    checks=plan.get('checks',[]); rows=[]
    for check in checks:
        if not all(check.get(key) for key in ('page','region','visible_text')):
            rows.append({**check,'status':'PENDING','evidence':[], 'seen_outside_allowed_source':[],
                         'missing_binding_fields':[key for key in ('page','region','visible_text') if not check.get(key)],
                         'available_basis':'host_observed_basis',
                         'binding_status':'PENDING_SEMANTIC_MAPPING'})
            continue
        proofs=[];other=[];seen=set()
        # A page ID denotes the URL shown in this plan's first request, even after navigation.
        bound_url = (page_urls or {}).get(check['page'])
        for oid,obs in s.observation_records.items():
            if not obs.get('capture_verified'):continue
            state=load_json(obs['evidence']['state']['path'])
            headings=[e.get('text') for e in state.get('elements',[]) if e.get('visible') is True and e.get('native_role') in ('h1','h2','h3')]
            if bound_url is not None:
                page_ok = same_url(bound_url, state['url'])
            else:
                page_ok = same_url(check['page'], state['url']) or check['page'] in headings
            values={v['element_id']:v for v in state.get('values',[])}
            for e in state.get('elements',[]):
                quote=e.get('text') or ''
                value=values.get(e['element_id'],{})
                source='host_synchronized_rendered_node'
                if (check['visible_text'] not in quote and value.get('value_visible') is True
                        and value.get('display_value')==check['visible_text']):
                    quote=value['display_value'];source='host_synchronized_visible_input_value'
                if e.get('visible') is not True or check['visible_text'] not in quote:continue
                key=(state['url'],e['element_id'],quote)
                if key in seen:continue
                seen.add(key)
                proof={'observation_id':oid,'url':state['url'],'document_identity':state.get('document_identity'),
                       'image':obs['evidence']['image'],'state':obs['evidence']['state'],
                       'node':e['element_id'],'bbox':e.get('bbox'),'quote':quote,
                       'source':source}
                (proofs if page_ok and region_matches(state,e['element_id'],check['region']) else other).append(proof)
        rows.append({**check,**({'resolved_page':bound_url} if bound_url is not None else {}),
                     'status':'VERIFIED' if proofs else 'UNVERIFIED',
                     'evidence':proofs,'seen_outside_allowed_source':other})
    done=sum(r['status']=='VERIFIED' for r in rows)
    return {'protocol':VERSION,'requested_goal':s.requested_goal,'working_goal':s.working_goal,
            'checks':rows,'verified':done,'total':len(rows),
            **({'host_observed_basis':observed_basis(s, objective_evidence)} if any(r['status']=='PENDING' for r in rows) else {}),
            'business_goal_status':('VERIFIED' if done==len(rows) else 'PARTIAL' if done else 'UNVERIFIED') if rows else 'NOT_SPECIFIED',
            'fragment_effective_steps':len(s.trajectory),'is_ai_review':False}


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
    href=None
    if action=='click':
        cid=(row.get('target') or {}).get('control_id')
        href=(before['controls'].get(cid,{}).get('binding') or {}).get('href')
        if not same_url(href,s.current['url']) and not contracted_search:return None
    elif action not in ('open_url','back') and not contracted_search:return None
    from .banded_plan import proves,bind_target
    if previous['expected']['kind'] in ('document_changed','search_results'):
        if not controller.proved(previous['expected'], s, load_json(before['evidence']['state']['path'])):return None
    elif not proves(previous['expected'],s.current):return None
    step=controller.plan['steps'][controller.position]
    if step.get('target'):
        matches = controller.targets(s,step['target'])
        if len(matches)!=1:return None
    if step['action']=='open_url' and step['page_id'] not in ['p'+str(i) for i in range(len(s.page_urls))]:return None
    return {'source_observation_id':before['observation_id'],'landing_observation_id':s.current['observation_id'],
            'operation_id':row['operation_id'],'clicked_href':href,'landed_url':s.current['url'],
            'expected':previous['expected'],'next_step':step,'new_model_requests':0}


async def verify_popup(origin,opened,operation,state):
    """Only one earned click, exact opener and public href; uncertainty stays blocked."""
    if operation['action_type']!='click' or await opened.opener()!=origin:
        raise ValueError('POPUP_SOURCE_UNPROVEN')
    cid=operation.get('evidence',{}).get('anchor_element_id')
    binding=next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})
    href=binding.get('href')
    await opened.wait_for_load_state('domcontentloaded',timeout=30000)
    if not href or urlsplit(href).scheme not in ('http','https') or not same_url(href,opened.url):
        raise ValueError('POPUP_LANDING_UNPROVEN')
    return {'source_url':state['url'],'source_document':state.get('document_identity'),
            'source_node':cid,'clicked_href':href,'opener_verified':True,'landed_url':opened.url,
            'atomic_actions':1,'new_page_first_frame':'following synchronized observation'}
