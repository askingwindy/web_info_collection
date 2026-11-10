"""Explicit direct-article reading: original body, observed links, immediate return.

This version does not change the older search/reading evidence contract. The
browser-native Find bar belongs to browser chrome, which the current headless
viewport host cannot open, type into or evidence; the capability is declared
unavailable rather than prohibited, and page-DOM retrieval never masquerades
as a native Ctrl/Cmd+F.
"""
from urllib.parse import urlsplit,unquote,parse_qs
import re
from .batch_core import load_json
from .planning import verify_evidence

VERSION='webcollect-direct-article-reading-1'
INLINE_BODY_TAGS={'a','span','text','strong','em','b','i','u','s','small','sup','sub','abbr','cite','q','code','kbd','samp','var','mark','del','ins','time','ruby','rt','rp','bdi','bdo','br','wbr','img'}
SCROLL_KEYS={'pagedown','pageup','arrowdown','arrowup','home','end','space'}

def enabled(task):
    from .goal_evidence import contract_for
    return (contract_for(task) or {}).get('version')==VERSION

def url_key(url):
    p=urlsplit(url)
    return p.scheme.lower(),p.netloc.lower(),unquote(p.path),p.query

def body(state):
    from .goal_evidence import norm
    from .plan_evidence import region_matches
    elements={e['element_id']:e for e in state.get('elements',[])}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])};result=[]
    blocks={b['element_id']:b for b in state.get('text_blocks',[])}
    excluded={'a','input','button','select','textarea','h1','h2','h3','h4','h5','h6','main','article','section','nav','navigation','aside','complementary','header','footer','form','body','html'} | INLINE_BODY_TAGS
    for e in elements.values():
        cid=e['element_id'];selector=bindings.get(cid,{}).get('selector','')
        block=blocks.get(cid)
        quote=((block.get('visible_text') if block else e.get('text')) or '').strip()
        if (not e.get('visible') or len(norm(quote))<24 or e.get('native_role') in excluded
                or not region_matches(state,cid,'正文') or re.search(r'(?:^| > )(?:nav|aside|header|footer|form):',selector)):
            continue
        seen=set();parent=e;outside=False
        while parent and parent.get('element_id') not in seen:
            seen.add(parent['element_id'])
            if parent.get('native_role') in {'nav','navigation','aside','complementary','header','footer','form'}:outside=True;break
            parent=elements.get(parent.get('parent_id'))
        # A container aggregating sidebars/links is not a paragraph citation.
        children=[c for c in elements.values() if c.get('parent_id')==cid]
        if outside or any(c.get('native_role') not in INLINE_BODY_TAGS for c in children):continue
        # Own-node text omits linked/emphasized words. Only the existing rendered
        # paragraph block may supply a quote when inline descendants are present.
        if children and not block:continue
        result.append({'node':cid,'quote':quote})
    return result

def initial(task,start,contract):
    from .goal_evidence import norm
    if url_key(start.get('url',''))!=url_key(contract['entry_url']) or url_key(task['initial_url'])!=url_key(contract['entry_url']):
        raise ValueError('DIRECT_ARTICLE_WRONG_ENTRY')
    elements={e['element_id']:e for e in start.get('elements',[])}
    headings=[e for e in elements.values() if e.get('visible') and e.get('native_role')=='h1' and e.get('text')]
    if not isinstance(start.get('title'),str) or not start['title'] or len(headings)!=1:
        raise ValueError('DIRECT_ARTICLE_TITLE_NOT_BOUND')
    heading=headings[0];allowed={norm(t) for t in contract['titles']}
    def under_heading(element):
        seen=set()
        while element and element['element_id'] not in seen:
            if element['element_id']==heading['element_id']:return True
            seen.add(element['element_id']);element=elements.get(element.get('parent_id'))
        return False
    # Full visible heading is retained (including adjacent edit controls).
    # A unique exact visible label within that semantic h1 may bind its title;
    # arbitrary same-host text or document.title never supplies this witness.
    matches=[heading] if norm(heading['text']) in allowed else [e for e in elements.values()
        if e.get('visible') and norm(e.get('text','')) in allowed and under_heading(e)]
    if len(matches)!=1:raise ValueError('DIRECT_ARTICLE_TITLE_NOT_BOUND')
    if not body(start):raise ValueError('DIRECT_ARTICLE_NO_VISIBLE_BODY')
    return {'url':start['url'],'title':start.get('title'),'heading':matches[0]['text'],
            'heading_node':heading['element_id'],'full_visible_heading':heading['text'],
            'heading_label_node':matches[0]['element_id'],'document_identity':start['document_identity']}

def before_action(task,state,action,arguments,cid=None,*,pending=None):
    from .goal_evidence import contract_for
    contract=contract_for(task)
    if contract.get('version')!=VERSION:return
    outside=url_key(state['url'])!=url_key(contract['entry_url'])
    if outside or pending:
        if action!='back' or not pending:raise ValueError('DIRECT_ARTICLE_NEXT_ACTION_MUST_BACK')
        return
    if action=='scroll':return
    if action=='hotkey':
        keys=[str(k).lower() for k in arguments.get('keys',[])]
        elements={e['element_id']:e for e in state.get('elements',[])}
        focused=[elements.get(v['element_id'],{}) for v in state.get('values',[]) if v.get('focused')]
        edits=any(e.get('inputable') or e.get('native_role') in ('input','textarea','select') for e in focused)
        activates_button=keys==['space'] and any(e.get('native_role') in ('button','summary') or e.get('element_type')=='button' for e in focused)
        # The revoked native-find prohibition is gone: Ctrl/Cmd+F may dispatch
        # honestly. In the current host it has no observable effect, so it
        # counts zero effective steps like any other unverified action.
        find_combo=(len(keys)==2 and keys[1]=='f'
                    and keys[0] in ('ctrl','control','meta','cmd','command'))
        if (len(keys)!=1 or keys[0] not in SCROLL_KEYS or edits or activates_button) and not find_combo:
            raise ValueError('DIRECT_ARTICLE_UNSUPPORTED_HOTKEY_NO_SUBMIT')
        return
    if action!='click':raise ValueError('DIRECT_ARTICLE_ONLY_READING_LINKS_AND_RETURN')
    element=next((e for e in state.get('elements',[]) if e['element_id']==cid),{})
    binding=next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})
    href=binding.get('href')
    if (element.get('inputable') or binding.get('input_type')=='search' or element.get('native_role')!='a'
            or not href or binding.get('target') not in (None,'','_self')
            or urlsplit(href).netloc!=urlsplit(contract['entry_url']).netloc):
        raise ValueError('DIRECT_ARTICLE_SEARCH_OR_NON_READING_CONTROL_FORBIDDEN')
    # Same-page TOC anchors are allowed; other links must originate in body.
    from .plan_evidence import region_matches
    if url_key(href)!=url_key(contract['entry_url']) and not region_matches(state,cid,'正文'):
        raise ValueError('DIRECT_ARTICLE_OUTGOING_LINK_NOT_IN_BODY')
    target_url=urlsplit(href);path=unquote(target_url.path).casefold();query=parse_qs(target_url.query)
    search_endpoint=(path in ('/wiki/special:search','/wiki/特殊:搜索','/wiki/特殊:搜尋')
                     or path.endswith('/w/index.php') and ('search' in query or any(v.casefold()=='special:search' for v in query.get('title',[]))))
    if search_endpoint:
        raise ValueError('DIRECT_ARTICLE_SITE_SEARCH_FORBIDDEN')

def transition(task,before,after,action,arguments,cid=None,*,pending=None):
    from .goal_evidence import contract_for,norm
    contract=contract_for(task);before_action(task,before,action,arguments,cid,pending=pending)
    origin=url_key(contract['entry_url']);away=url_key(after['url'])!=origin
    if pending:
        if away or after.get('title')!=pending.get('title') or not ({norm(p['quote']) for p in body(after)} & {norm(p['quote']) for p in pending['body']}):
            raise ValueError('DIRECT_ARTICLE_RETURN_IDENTITY_UNVERIFIED')
        return None,True
    if away:
        if action!='click' or not body(before):raise ValueError('DIRECT_ARTICLE_UNEXPECTED_DEPARTURE')
        return {'url':before['url'],'title':before.get('title'),'body':body(before),'document_identity':before['document_identity']},False
    if after['document_identity']!=before['document_identity'] or after.get('title')!=before.get('title'):
        raise ValueError('DIRECT_ARTICLE_UNEXPLAINED_SAME_URL_DOCUMENT_CHANGE')
    return None,False

def trace(task,start,steps,observations,*,terminal=None):
    from .goal_evidence import contract_for
    contract=contract_for(task);basis=initial(task,start,contract);pending=None;readings=[];epoch=0;previous=start
    for row in steps:
        before=load_json(observations[row['before_observation_id']]['evidence']['state']['path'])
        after=load_json(observations[row['after_observation_id']]['evidence']['state']['path'])
        if not all(observations[row[k]].get('capture_verified') is True for k in ('before_observation_id','after_observation_id')):
            raise ValueError('DIRECT_ARTICLE_UNVERIFIED_FRAME')
        if any(before.get(k)!=previous.get(k) for k in ('document_identity','title')) or url_key(before['url'])!=url_key(previous['url']):
            raise ValueError('DIRECT_ARTICLE_UNEXPLAINED_OBSERVATION_IDENTITY')
        cid=(row.get('target') or {}).get('control_id')
        pending,returned=transition(task,before,after,row['action'],row['arguments'],cid,pending=pending)
        previous=after
        if returned:epoch+=1  # Keep original article reading facts; rebind only text actually visible after verified return.
        if not pending and not returned and url_key(after['url'])==url_key(contract['entry_url']):
            old={p['quote'] for p in body(before)}
            moved=before.get('scroll')!=after.get('scroll')
            if moved and row['action'] in ('scroll','click','hotkey'):
                readings.extend({**p,'url':after['url'],'observation_id':row['after_observation_id'],'operation_id':row['operation_id'],'epoch':epoch}
                                for p in body(after) if p['quote'] not in old)
    if terminal is not None and (pending or url_key(terminal['url'])!=url_key(contract['entry_url'])):
        raise ValueError('DIRECT_ARTICLE_NOT_RETURNED')
    return {'entry':basis,'pending_return':pending,'new_body':readings,'epoch':epoch}

def session_trace(session,start=None):
    controller=getattr(session,'plan_controller',None)
    initial_id=(getattr(controller,'frozen_plan',None) or getattr(controller,'plan',None) or {}).get('observation_id')
    ob=start or session.observation_records.get(initial_id) or next(iter(session.observation_records.values()))
    return trace(session.task,load_json(ob['evidence']['state']['path']),session.trajectory,session.observation_records)

def progress(session,start,contract):
    try:proof=session_trace(session,start)
    except ValueError as error:return {'status':'UNVERIFIED','reason':str(error),'passages':[]}
    now=load_json(session.current['evidence']['state']['path']);visible=body(now)
    last=session.observation_records[session.trajectory[-1]['after_observation_id']] if session.trajectory else start
    last_state=load_json(last['evidence']['state']['path'])
    if any(now.get(k)!=last_state.get(k) for k in ('document_identity','title')) or url_key(now['url'])!=url_key(last_state['url']):
        return {'status':'UNVERIFIED','reason':'DIRECT_ARTICLE_CURRENT_IDENTITY_NOT_IN_TRACE','passages':[]}
    current=url_key(now['url'])==url_key(contract['entry_url']) and not proof['pending_return']
    candidates=[]
    if current:
        for passage in proof['new_body']:
            matches=[p for p in visible if p['quote']==passage['quote']]
            if len(matches)==1:
                candidates.append({**passage,'node':matches[0]['node'],'url':now['url'],
                    'read_observation_id':passage['observation_id'],'read_node':passage['node'],
                    'observation_id':session.current['observation_id']})
    selected=None;citation=getattr(session,'answer_citation',None)
    if citation and current:
        verify_evidence([citation]);branch=load_json(citation['path']);reply=branch.get('response') or {}
        origin=session.observation_records.get(reply.get('observation_id'))
        if (branch.get('kind')=='plan-branch' and branch.get('boundary')==session.binding
                and reply.get('attempt_id')==session.attempt_id and origin and origin.get('capture_verified')
                and url_key(origin['url'])==url_key(contract['entry_url'])
                and (branch.get('provider_reply') or {}).get('choice')==reply.get('choice')):
            origin_body=body(load_json(origin['evidence']['state']['path']))
            for option in branch.get('options',[]):
                p=option.get('passage') or {}
                if (option.get('choice')==reply.get('choice')=='cite:'+str(p.get('node'))
                        and p.get('observation_id')==reply['observation_id']
                        and {'node':p.get('node'),'quote':p.get('quote')} in origin_body
                        and any(c['operation_id']==p.get('operation_id') and c['read_observation_id']==p.get('read_observation_id')
                                and c['read_node']==p.get('read_node') and c['quote']==p.get('quote') for c in candidates)):
                    selected=p;break
    if not selected and citation and current and reply.get('citations'):
        if (branch.get('kind')=='plan-branch' and branch.get('boundary')==session.binding
                and reply.get('attempt_id')==session.attempt_id and origin and origin.get('capture_verified')
                and branch.get('provider_reply',{}).get('citations')==reply['citations']
                and reply.get('choice') in ('continue_plan','replan')):
            from .direct_completion import bind_answer
            plan=session.plan_controller.frozen_plan
            index=next(i for i,c in enumerate(plan['checks']) if c['evidence_kind']=='reading')
            bound=bind_answer({'check_answers':[{'check_index':index,'passages':reply['citations']}]},plan,proof['new_body'],session.trajectory)
            for p in bound['check_answers'][0]['passages']:
                matches=[c for c in candidates if c['read_observation_id']==p['observation_id'] and c['read_node']==p['node'] and c['quote']==p['quote']]
                if len(matches)==1:selected=matches[0];break
    # An explicit answer may select its current citation in the same reply.
    # Selection comes from the model's exact passage, never from a host answer.
    completion_ref=getattr(session,'reading_completion',None)
    if not selected and current and completion_ref:
        verify_evidence([completion_ref]);event=load_json(completion_ref['path']);reply=event.get('response',{})
        origin=session.observation_records.get(reply.get('observation_id'))
        if (event.get('kind')=='plan-branch' and event.get('boundary')==session.binding
                and reply.get('attempt_id')==session.attempt_id and reply.get('choice')=='finish_reading'
                and origin and origin.get('capture_verified') is True
                and url_key(origin['url'])==url_key(contract['entry_url'])
                and event.get('provider_reply',{}).get('reading_answer')==reply.get('reading_answer')):
            from .direct_completion import bind_answer
            plan=session.plan_controller.frozen_plan
            bound_answer=bind_answer(reply.get('reading_answer',{}),plan,proof['new_body'],session.trajectory)
            for item in bound_answer.get('check_answers',[]):
                if plan['checks'][item['check_index']]['evidence_kind']!='reading':continue
                for p in item.get('passages',[]):
                    matches=[c for c in candidates if c['read_observation_id']==p.get('observation_id')
                        and c['read_node']==p.get('node') and c['quote']==p.get('quote')]
                    if len(matches)==1:selected=matches[0];citation=completion_ref;break
                if selected:break
    result={'status':'VERIFIED' if selected and current else 'PASSAGE_AVAILABLE' if candidates and current else 'UNVERIFIED',
        'article_entry':proof['entry'],'return_required':bool(proof['pending_return']),
        'new_visible_body':proof['new_body'],'passages':candidates if current else [],'selected_passage':selected,
        'citation_event':citation if selected else None,'semantic_goal_judgment':'model citation selection; independent QC still required'}
    from .direct_completion import enabled as explicit,completion
    if explicit(session.task):
        result['status']='CITED' if selected and current else result['status']
        result['completion']=completion(session,result)
        if result['completion']:result['status']='VERIFIED'
    return result


def verify_record(record, *, _verified=None):
    """Independent save-time replay from original snapshots/actions/citation."""
    from types import SimpleNamespace
    from .agent_observation import project
    from .goal_evidence import contract_for,progress as goal_progress
    if not enabled(record['task']):return
    raw=__import__('pathlib').Path(record['receipt']['boundary']['path']).parent
    plans=sorted(raw.glob('*-conditional-plan.json'))
    if not plans:raise ValueError('DIRECT_ARTICLE_NO_ORIGINAL_PLAN')
    original_plan=load_json(plans[0])['plan'];initial_id=original_plan['observation_id']
    observations=(_verified.observations(record) if _verified is not None else
        {oid:project(load_json(ob['state_path']),{k:ob['evidence'][k] for k in ('image','state','capture')})
         for oid,ob in record['observations'].items()})
    current=observations[record['terminal']['final_observation_id']]
    result=(record['terminal'].get('goal_evidence') or {}).get('session_objective') or {}
    session=SimpleNamespace(task=record['task'],plan_controller=SimpleNamespace(frozen_plan=original_plan),
        trajectory=record['trajectory'],observation_records=observations,current=current,
        binding=record['receipt']['boundary'],attempt_id=record['boundary']['attempt_id'],answer_citation=result.get('citation_event'),
        reading_completion=(result.get('completion') or {}).get('decision'))
    if session.reading_completion:
        ref=session.reading_completion;p=__import__('pathlib').Path(ref['path'])
        if p.parent!=raw or record['receipt']['files_sha256'].get(p.name)!=ref['sha256']:
            raise ValueError('DIRECT_COMPLETION_OUTSIDE_SEALED_ATTEMPT')
    start=load_json(observations[initial_id]['evidence']['state']['path'])
    trace(record['task'],start,record['trajectory'],observations,terminal=load_json(current['evidence']['state']['path']))
    expected=goal_progress(session,initial_id,contract_for(record['task']))
    if expected.get('status')!='VERIFIED' or expected!=result:
        raise ValueError('DIRECT_ARTICLE_SAVED_GOAL_NOT_REPRODUCIBLE')


def protocol_schema(value,contract,*,completion=False,max_steps=8,wiki=False):
    """Same explicit capability projection for first turn, branch and boundary."""
    if wiki:
        from .wiki_reading import schema
        return schema(value,max_steps=max_steps)
    if (contract or {}).get('version')!=VERSION:
        if completion:
            from .direct_completion import schema
            return schema(value,max_steps=max_steps)
        return value
    from copy import deepcopy
    result=deepcopy(value)
    def visit(item):
        if isinstance(item,dict):
            props=item.get('properties',{})
            if props.get('source',{}).get('const')=='search_results':
                props.pop('source')
                if 'source' in item.get('required',[]):item['required'].remove('source')
                for combiner in ('anyOf','oneOf'):
                    if isinstance(item.get(combiner),list):item[combiner]=[v for v in item[combiner] if 'source' not in v.get('required',[])]
            enums=item.get('enum')
            if isinstance(enums,list):
                if 'search_results' in enums:enums.remove('search_results')
                if {'click','scroll','type'}<=set(enums):item['enum']=[a for a in enums if a in ('click','scroll','back','hotkey')]
            if isinstance(item.get('oneOf'),list):
                item['oneOf']=[v for v in item['oneOf'] if not isinstance(v,dict)
                    or v.get('properties',{}).get('action',{}).get('const') not in ('type','select','set_value','open_url','double_click','right_click')]
            for child in item.values():visit(child)
        elif isinstance(item,list):
            for child in item:visit(child)
    visit(result)
    if completion:
        from .direct_completion import schema
        result=schema(result,max_steps=max_steps)
    return result


def planning_pair(task,before,after,png_before,png_after):
    """Read-only initial planning eligibility; never click/scroll permission."""
    from .dynamic_regions import enabled as dynamic_enabled,pair as dynamic_pair
    if dynamic_enabled(before) and dynamic_enabled(after):
        return {**dynamic_pair(before,after,png_before,png_after),
            "observation_only":True,"dispatch_permission":False}
    from .action_stability import reading_scope,pair
    from .goal_evidence import contract_for
    from PIL import Image,ImageChops
    from io import BytesIO
    contract=contract_for(task)
    result={'schema_version':'webcollect-direct-article-planning-observation-1',
            'accepted':False,'observation_only':True,'dispatch_permission':False,
            'full_page_accepted':False,'original_viewport_preserved':True}
    if not enabled(task):return {**result,'reason':'Explicit direct-article contract required'}
    try:
        identity=initial(task,before,contract)
        if identity!=initial(task,after,contract):raise ValueError('Direct article initial identity changed')
        scope=reading_scope(before);proof=pair(before,after,png_before,png_after,scope)
        result.update(article_identity=identity,main_proof=proof)
        if not proof['accepted']:return {**result,'reason':'Original main region proof rejected'}
        main_ids={e['element_id'] for e in scope['basis']['elements']}
        def anchors(state):
            els={e['element_id']:e for e in state['elements']};geometry={g['element_id']:g for g in state['geometry_witnesses']}
            rows=[]
            for binding in state['capture_controls']:
                e=els.get(binding['element_id'],{});href=binding.get('href') or ''
                if (e.get('visible') is True and e.get('native_role')=='a' and e.get('text')
                        and e['element_id'] not in main_ids and '#' in href and url_key(href)==url_key(contract['entry_url'])):
                    if e['element_id'] not in geometry:raise ValueError('Visible section anchor lacks geometry witness')
                    rows.append({'element':e,'binding':binding,'geometry':geometry[e['element_id']]})
            return rows
        navigation=anchors(before)
        if navigation!=anchors(after):raise ValueError('Visible same-page directory anchors changed')
        with Image.open(BytesIO(png_before)) as a,Image.open(BytesIO(png_after)) as b:
            # The reused main proof has already validated both complete PNGs.
            diff=ImageChops.difference(a.convert('RGB'),b.convert('RGB'))
            protected=[]
            for row in navigation:
                box=row['element']['bbox'];guard=[max(0,box[0]-4),max(0,box[1]-4),min(a.width,box[2]+4),min(a.height,box[3]+4)]
                if diff.crop(tuple(guard)).getbbox():raise ValueError('Visible same-page directory anchor pixels changed')
                protected.append({'element_id':row['element']['element_id'],'bbox':guard})
        return {**result,'accepted':True,'directory_anchors':navigation,'directory_pixel_protection':protected,
                'reason':'Same bound visible article and unchanged original main plus visible section anchors'}
    except ValueError as error:return {**result,'reason':str(error)}
