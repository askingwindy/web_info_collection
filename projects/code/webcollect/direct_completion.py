"""Explicit direct-article answer and a narrowly bounded terminal bridge.

Citation establishes provenance, never the semantic truth of a whole answer.
The latter remains an independent quality-review question.
"""
from copy import deepcopy
from pathlib import Path
from .batch_core import load_json
from .planning import verify_evidence, object_sha256

VERSION = 'webcollect-direct-reading-completion-1'
BRIDGE = 'webcollect-direct-terminal-overlay-1'


def enabled(task):
    from .direct_article import enabled as direct
    from .wiki_reading import enabled as wiki
    return wiki(task) or (direct(task) and task.get('fragment', {}).get('direct_completion_protocol') == VERSION)


def schema(value, *, max_steps=8):
    from .banded_plan import obj, text
    value = deepcopy(value)
    passage = obj({'observation_id':text(200), 'node':text(120), 'quote':text(4000)})
    passage['additionalProperties']=True
    passage['properties'].update(epoch={'type':'integer','minimum':0},operation_id=text(120),url=text(1000))
    answer = obj({'working_goal':text(300), 'answer':text(3000),
        'check_answers':{'type':'array','maxItems':12,'items':obj({
            'check_index':{'type':'integer','minimum':0,'maximum':11}, 'answer':text(1000),
            'passages':{'type':'array','maxItems':8,'items':{'anyOf':[passage,text(4000)]}},
            'operation_ids':{'type':'array','minItems':1,'maxItems':8,'uniqueItems':True,'items':text(120)}})}})
    answer['required'].remove('working_goal')
    answer['properties']['notes']={'type':'string','maxLength':2000}
    answer['additionalProperties']=True
    answer['properties']['check_answers']['items']['additionalProperties']=True
    answer['properties']['check_answers']['items']['required'].remove('operation_ids')
    def visit(item):
        if isinstance(item,list):
            for child in item:visit(child)
            return
        if not isinstance(item,dict):return
        props=item.get('properties',{})
        if {'node','observation_id','text','href'}<=set(props):
            props['text']['minLength']=0
            item['required']=[k for k in item.get('required',[]) if k!='text']
            item.setdefault('anyOf',[]).extend([{'required':['node']},{'required':['text']}])
            item.setdefault('allOf',[]).append({'if':{'properties':{'text':{'const':''}},'required':['text']},
                'then':{'required':['node']}})
        if 'steps' in props and 'goal' in props:
            props['notes']={'type':'string','maxLength':2000}
        if {'kind','text','region'}<=set(props) and item.get('allOf'):
            condition=item['allOf'][0].get('if')
            if condition:item['allOf'][0]['if']={'allOf':[condition,{'not':{'properties':{'kind':{'const':'visible_text'}},'required':['region']}}]}
        if 'checks' in props:
            props['checks']['minItems']=1
            props['checks']['contains']={'type':'object','properties':{'evidence_kind':{'const':'reading'}},'required':['evidence_kind']}
            check=props['checks']['items'];check['properties'].update(
                evidence_kind={'enum':['reading','actions']},
                required_step_indices={'type':'array',**({'maxItems':max_steps} if max_steps is not None else {}),'uniqueItems':True,
                    'description':'reading is empty and may be omitted; actions requires original zero-based click/back indices',
                    'items':{'type':'integer','minimum':0,**({'maximum':max_steps-1} if max_steps is not None else {})}})
            check['required']=list(dict.fromkeys([*[k for k in check.get('required',[]) if k!='required_step_indices'],'evidence_kind']))
            check['properties']['visible_text']['minLength']=0
            check.setdefault('allOf',[]).append({'if':{'properties':{'evidence_kind':{'const':'reading'}},'required':['evidence_kind']},
                'then':{'properties':{'required_step_indices':{'maxItems':0}}},
                'else':{'required':['required_step_indices'],'properties':{'required_step_indices':{'minItems':1}}}})
        if 'choice' in props and 'plan' in props:
            props['reading_answer']=answer
            props['citations']={'type':'array','maxItems':8,'items':{'anyOf':[passage,text(4000)]}}
            item.setdefault('allOf',[]).append({'if':{'properties':{'choice':{'const':'finish_reading'}},'required':['choice']},
                'then':{'required':['reading_answer']},'else':{'not':{'required':['reading_answer']}}})
        for v in item.values():
            if isinstance(v,dict):visit(v)
            elif isinstance(v,list):
                for child in v:visit(child)
    visit(value)
    return value


def bridge_evidence(task, before, after, *, target_ids=(), unverified_tail=0):
    """Both callers use the same original evidence and deterministic proof."""
    before={k:before[k] for k in ('state','image','capture')}
    after={k:after[k] for k in ('state','image','capture')}
    verify_evidence([before[k] for k in ('state','image','capture')]+[after[k] for k in ('state','image','capture')])
    proof=terminal_bridge(task,load_json(before['state']['path']),load_json(after['state']['path']),
        Path(before['image']['path']).read_bytes(),Path(after['image']['path']).read_bytes(),
        target_ids=target_ids,unverified_tail=unverified_tail)
    return {'before':before,'after':after,'proof':proof}


def validate_plan(plan):
    if not any(c['evidence_kind']=='reading' and c.get('field','').strip() for c in plan.get('checks',[])):
        raise ValueError('Direct reading needs an original substantive reading check')
    for check in plan.get('checks',[]):
        indices=check.get('required_step_indices',[])
        if check['evidence_kind']=='reading':
            if indices:raise ValueError('Reading check cannot require incidental planned actions')
        elif (not indices or indices!=sorted(indices) or any(i>=len(plan['steps']) or plan['steps'][i]['action'] not in ('click','back') for i in indices)):
            raise ValueError('Action check requires ordered original click/back step indices')


def initial_plan_issues(plan, observation, contract, *, max_steps=8):
    """All currently decidable proposal errors; no browser action or field repair."""
    from jsonschema import Draft202012Validator
    from .banded_plan import plan_schema
    from .direct_article import protocol_schema,url_key
    from .goal_evidence import norm
    issues=[{'field_path':list(e.absolute_path),'detail':e.message}
        for e in Draft202012Validator(protocol_schema(plan_schema(True,wire=True,pending_checks=True,max_steps=max_steps),contract,completion=True,max_steps=max_steps)).iter_errors(plan)]
    steps=plan.get('steps',[])
    if not isinstance(steps,list):return issues
    for i,c in enumerate(plan.get('checks',[]) if isinstance(plan.get('checks'),list) else []):
        if not isinstance(c,dict) or c.get('evidence_kind')!='actions':continue
        indices=c.get('required_step_indices',[])
        if not isinstance(indices,list) or not all(type(n)is int for n in indices):continue
        if indices!=sorted(indices):issues.append({'field_path':['checks',i,'required_step_indices'],'detail':'Required original action indices must be ordered'})
        for j in indices:
            if not 0<=j<len(steps) or not isinstance(steps[j],dict) or steps[j].get('action') not in ('click','back'):
                issues.append({'field_path':['checks',i,'required_step_indices'],'detail':f'Index {j} must reference an existing original click/back step'})
    controls=observation.get('controls',{})
    for i,step in enumerate(steps):
        if not isinstance(step,dict) or step.get('action')!='click':continue
        target=step.get('target') or {}
        if not isinstance(target,dict):continue
        node=target.get('node');c=controls.get(node) if node else None
        if node:
            if not c or c.get('element',{}).get('visible') is not True:
                issues.append({'field_path':['steps',i,'target','node'],'detail':'Node is not a visible control in the supplied original observation'})
                continue
            labels=[c['element'].get('text',''),*[v.get('text','') if isinstance(v,dict) else v for v in c.get('readable_labels',[])]]
            if norm(target.get('text','')) not in [norm(x) for x in labels]:
                alternatives=[{'node':key,'text':v['element']['text'],'href':v.get('binding',{}).get('href')} for key,v in controls.items() if v.get('element',{}).get('visible') is True and v['element'].get('text') and v.get('binding',{}).get('href')==c.get('binding',{}).get('href')]
                issues.append({'field_path':['steps',i,'target','text'],'detail':'Node label is not proved by its original visible text; choose a proved target explicitly.','observed_same_href_alternatives':alternatives})
            if target.get('observation_id') not in (None,observation['observation_id']):
                issues.append({'field_path':['steps',i,'target','observation_id'],'detail':'Node belongs to the supplied original observation only'})
            if target.get('href') is not None and target['href']!=c.get('binding',{}).get('href'):
                issues.append({'field_path':['steps',i,'target','href'],'detail':'Explicit href differs from original node binding'})
        elif target.get('text'):
            found=[v for v in controls.values() if v.get('element',{}).get('visible') is True
                   and norm(v['element'].get('text',''))==norm(target['text']) and v.get('binding',{}).get('href')]
            if len(found)==1:c=found[0]
        href=(c or {}).get('binding',{}).get('href')
        if href:
            if url_key(href)!=url_key(contract['entry_url']):
                if i+1>=len(steps) or not isinstance(steps[i+1],dict) or steps[i+1].get('action')!='back':
                    issues.append({'field_path':['steps',i+1],'detail':'This observed href leaves the original article; the immediately next business action must be back'})
            elif '#' in href and step.get('expected',{}).get('kind')=='document_changed':
                issues.append({'field_path':['steps',i,'expected','kind'],'detail':'Observed same-article fragment link is not document_changed'})
    return issues


def action_requirements(session, check, plan, operation_ids):
    """Match the declared original action obligation, not free prose keywords."""
    rows=[r for r in session.trajectory if r['operation_id'] in operation_ids]
    position=0
    for index in check['required_step_indices']:
        wanted=plan['steps'][index];found=False
        while position<len(rows):
            row=rows[position];position+=1
            if row['action']!=wanted['action']:continue
            if wanted['action']=='click':
                state=load_json(session.observation_records[row['before_observation_id']]['evidence']['state']['path'])
                cid=(row.get('target') or {}).get('control_id')
                element=next((e for e in state['elements'] if e['element_id']==cid),{})
                from .goal_evidence import norm
                if wanted['target']['text'] and norm(element.get('text',''))!=norm(wanted['target']['text']):continue
                actual=next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})
                target=wanted['target'];href=target.get('href')
                if target.get('node'):
                    origin=session.observation_records.get(target.get('observation_id'))
                    if not origin:raise ValueError('Original action target observation is missing')
                    original=load_json(origin['evidence']['state']['path'])
                    bound=next((b for b in original.get('capture_controls',[]) if b['element_id']==target['node']),None)
                    if not bound:raise ValueError('Original action target binding is missing')
                    href=bound.get('href')
                if href is not None and actual.get('href')!=href:continue
            found=True;break
        if not found:raise ValueError('DIRECT_COMPLETION_REQUIRED_ACTION_NOT_EXECUTED')


def bind_answer(answer, plan, readings, trajectory):
    """Resolve exact cited text against already executed, archived reading facts."""
    answer=deepcopy(answer)
    answer.setdefault('working_goal',plan['goal'])
    answer['check_answers']=sorted(answer.get('check_answers',[]), key=lambda r:r.get('check_index',-1))
    for item in answer.get('check_answers',[]):
        index=item.get('check_index')
        if type(index)is not int or not 0<=index<len(plan.get('checks',[])):
            raise ValueError('DIRECT_COMPLETION_ORIGINAL_GOAL_OR_CHECKS_CHANGED')
        if plan['checks'][index]['evidence_kind']=='actions':
            if 'operation_ids' not in item:
                item['operation_ids']=[r['operation_id'] for r in trajectory if r['action'] in ('click','back')]
            continue
        bound=[]
        ids=item.get('evidence_ids')
        if ids is not None:
            if item.get('passages'):raise ValueError('DIRECT_COMPLETION_CONFLICTING_REFERENCE_FORMS')
            if (not isinstance(ids,list) or not ids or not all(isinstance(eid,str) for eid in ids)
                    or len(ids)!=len(set(ids))):
                raise ValueError('DIRECT_COMPLETION_INVALID_EVIDENCE_IDS')
            for eid in ids:
                matches=[r for r in readings if r.get('evidence_id')==eid]
                if len(matches)!=1:raise ValueError('DIRECT_COMPLETION_UNKNOWN_EVIDENCE_ID')
                bound.append({k:matches[0][k] for k in
                    ('evidence_id','observation_id','node','quote','operation_id','url','epoch','sections') if k in matches[0]})
        for raw in item.get('passages',[]):
            p={'quote':raw} if isinstance(raw,str) else raw
            if not isinstance(p,dict):raise ValueError('DIRECT_COMPLETION_PASSAGE_NOT_IN_ORIGINAL_READ_TRACE')
            quote=p.get('quote')
            matches=[r for r in readings if isinstance(quote,str) and quote.strip() and quote in r['quote'] and
                all(r.get(k)==p[k] for k in ('observation_id','node','epoch','operation_id','url') if k in p)]
            if len(matches)!=1:raise ValueError('DIRECT_COMPLETION_PASSAGE_NOT_IN_ORIGINAL_READ_TRACE')
            bound.append({**p,**{k:matches[0][k] for k in ('observation_id','node','quote','operation_id')},
                **({'quoted_excerpt':quote} if quote!=matches[0]['quote'] else {})})
        item['passages']=bound
        if 'operation_ids' not in item:item['operation_ids']=list(dict.fromkeys(p['operation_id'] for p in bound))
    return answer


def completion(session, evidence):
    """Recompute identity/references, without deciding whether prose answers a question."""
    reference=getattr(session,'reading_completion',None)
    if not reference:return None
    verify_evidence([reference]);event=load_json(reference['path']);reply=event.get('response',{})
    plan=getattr(session.plan_controller,'frozen_plan',{})
    validate_plan(plan)
    origin=session.observation_records.get(reply.get('observation_id'))
    if (event.get('kind')!='plan-branch' or event.get('boundary')!=session.binding
            or reply.get('attempt_id')!=session.attempt_id or reply.get('choice')!='finish_reading'
            or not origin or origin.get('capture_verified') is not True
            or event.get('provider_reply',{}).get('reading_answer')!=reply.get('reading_answer')
            or not any(o.get('choice')=='finish_reading' for o in event.get('options',[]))):
        raise ValueError('DIRECT_COMPLETION_EVENT_NOT_BOUND')
    model_answer=reply.get('reading_answer') or {}
    answer=bind_answer(model_answer,plan,evidence['new_visible_body'],session.trajectory)
    checks=plan.get('checks',[])
    from .wiki_reading import enabled as wiki, validate_sources
    if wiki(getattr(session,'task',{})):
        answered={r.get('check_index') for r in answer.get('check_answers',[])}
        missing=[i for i in range(len(checks)) if i not in answered]
        if missing:raise ValueError('WIKI_READING_MISSING_ORIGINAL_CHECKS: '+','.join(map(str,missing)))
    if (answer.get('working_goal')!=plan.get('goal') or not answer.get('answer','').strip()
            or [r.get('check_index') for r in answer.get('check_answers',[])]!=list(range(len(checks)))):
        raise ValueError('DIRECT_COMPLETION_ORIGINAL_GOAL_OR_CHECKS_CHANGED')
    operations={r['operation_id']:r for r in session.trajectory}
    readings=evidence['new_visible_body']
    for item in answer['check_answers']:
        if not item.get('answer','').strip() or not item.get('operation_ids') or any(i not in operations for i in item['operation_ids']):
            raise ValueError('DIRECT_COMPLETION_ACTION_REFERENCE_NOT_EXECUTED')
        check=checks[item['check_index']]
        if check['evidence_kind']=='actions':
            action_requirements(session,check,plan,item['operation_ids'])
            # Optional copied control labels describe this action; they are not
            # reading evidence and cannot satisfy a reading check.
            continue
        elif not item.get('passages'):raise ValueError('DIRECT_COMPLETION_READING_REFERENCE_MISSING')
        # An action-only check can cite actual click/back operations; a reading
        # check must additionally cite a paragraph actually exposed by its read.
        if not item.get('passages') and not all(operations[i]['action'] in ('click','back') for i in item['operation_ids']):
            raise ValueError('DIRECT_COMPLETION_READING_REFERENCE_MISSING')
        for p in item.get('passages',[]):
            found=[r for r in readings if all(r.get(k)==p.get(k) for k in ('observation_id','node','quote'))]
            if (len(found)!=1 or found[0]['operation_id'] not in item['operation_ids']
                    or any(p[k]!=found[0].get(k) for k in ('epoch','operation_id','url') if k in p)):
                raise ValueError('DIRECT_COMPLETION_PASSAGE_NOT_IN_ORIGINAL_READ_TRACE')
    if wiki(getattr(session,'task',{})):validate_sources(session,plan,answer,evidence)
    if (not wiki(getattr(session,'task',{})) and not evidence.get('selected_passage')) or evidence.get('return_required'):
        raise ValueError('DIRECT_COMPLETION_CURRENT_CITATION_OR_RETURN_MISSING')
    return {'schema_version':(session.task['fragment'][__import__('webcollect.wiki_reading',fromlist=['FIELD']).FIELD] if wiki(getattr(session,'task',{})) else VERSION),'decision':reference,'original_working_goal':plan['goal'],
        'original_checks':checks,'original_plan_sha256':object_sha256(plan),'answer':answer,
        'model_answer':model_answer,'reference_binding':'exact original passage identity and already executed operation references',
        'actual_operations':[{'operation_id':r['operation_id'],'action':r['action'],
            'before_observation_id':r['before_observation_id'],'after_observation_id':r['after_observation_id'],
            'target':r.get('target'),'purpose':r.get('semantic_goal') or r.get('goal')} for r in session.trajectory],
        'semantic_judgment':'MODEL_REPORTED_REQUIRES_INDEPENDENT_QC'}


def terminal_bridge(task, before, after, png_before, png_after, *, target_ids=(), unverified_tail=0):
    """Only disappearance of outside-main, non-overlapping native image widgets.

    Existing main-region proof stays unchanged. Every other rendered object,
    geometry witness, pixel, and input must be unchanged; no tolerance threshold.
    """
    from PIL import Image,ImageChops,ImageDraw
    from io import BytesIO
    import re
    result={'schema_version':BRIDGE,'accepted':False,'original_viewport_preserved':True,
            'dispatch_permission':False}
    try:
        if not enabled(task) or unverified_tail:raise ValueError('Explicit protocol and fully verified prefix required')
        for key in ('url','title','document_identity','scroll','values','visible_text','screen_resolution','device_pixel_ratio'):
            if before.get(key)!=after.get(key):raise ValueError('Terminal identity/text/input/position changed: '+key)
        old={e['element_id']:e for e in before['elements']};new={e['element_id']:e for e in after['elements']}
        gone=set(old)-set(new)
        if not gone or set(new)-set(old) or any(old[i]!=new[i] for i in new):raise ValueError('Only disappearance of bound outside-main images is supported')
        bindings={b['element_id']:b for b in before['capture_controls']}
        mains=[e for e in old.values() if e.get('native_role')=='main' and e.get('visible') is True]
        if len(mains)!=1:raise ValueError('Unique visible main required')
        boxes=[]
        for i in sorted(gone):
            e=old[i];binding=bindings.get(i,{})
            # A direct native body child establishes the outside-main ancestry;
            # no site, class, label or URL exemptions.
            if (i in target_ids or e.get('native_role')!='img' or e.get('text') or e.get('parent_id')!='root'
                    or not re.fullmatch(r'html:nth-of-type\(1\) > body:nth-of-type\(1\) > img:nth-of-type\([1-9][0-9]*\)',binding.get('selector',''))):
                raise ValueError('Disappeared object is not a bound outside-main image')
            box=e.get('bbox',[])
            if len(box)!=4 or not all(isinstance(n,(int,float)) for n in box):raise ValueError('Native widget box missing')
            boxes.append(box)
        # All non-structural rendered material is protected, including all body
        # text, images, controls, directory and side-panel contents. Main itself
        # is an outer layout envelope, not an exemption for any descendant.
        protected=[e['bbox'] for i,e in old.items() if i not in gone and e.get('visible') is True
                   and e.get('native_role') not in ('main','body','html') and e.get('bbox')]
        for box in boxes:
            if any(box[0]<p[2]+2 and box[2]>p[0]-2 and box[1]<p[3]+2 and box[3]>p[1]-2 for p in protected):
                raise ValueError('Widget overlaps protected rendered material')
        for key in ('capture_controls','geometry_witnesses','text_blocks','paint_borders','capture_media','capture_images'):
            a=[x for x in before.get(key,[]) if x.get('element_id') not in gone]
            b=[x for x in after.get(key,[]) if x.get('element_id') not in gone]
            if a!=b:raise ValueError('Non-widget observation facts changed: '+key)
        for state in (before,after):
            ready=state.get('capture_readiness',{})
            if (ready.get('document_ready')!='complete' or ready.get('fonts_ready') is not True
                    or ready.get('images_ready') is not True or state.get('device_pixel_ratio')!=1):
                raise ValueError('Terminal loading incomplete')
        with Image.open(BytesIO(png_before)) as a,Image.open(BytesIO(png_after)) as b:
            if a.size!=b.size or list(a.size)!=before['screen_resolution']:raise ValueError('Viewport image size differs')
            diff=ImageChops.difference(a.convert('RGB'),b.convert('RGB'));mask=Image.new('L',a.size,0);draw=ImageDraw.Draw(mask)
            for x0,y0,x1,y1 in boxes:
                # Never expand native bounds for a shadow, filter, or stroke.
                import math
                draw.rectangle((math.ceil(x0),math.ceil(y0),math.floor(x1)-1,math.floor(y1)-1),fill=255)
            outside=ImageChops.multiply(diff,Image.merge('RGB',(ImageChops.invert(mask),)*3))
            if outside.getbbox():raise ValueError('Changed pixels extend outside exact native widget bounds')
            result.update(changed_pixel_bbox=list(diff.getbbox()) if diff.getbbox() else None)
        return {**result,'accepted':True,'removed_widgets':[{'element':old[i],'binding':bindings[i]} for i in sorted(gone)],
            'protected_boxes':protected,'reason':'Only isolated outside-main native image widgets disappeared; all other facts and pixels unchanged'}
    except (ValueError,KeyError,TypeError) as error:return {**result,'reason':str(error)}
