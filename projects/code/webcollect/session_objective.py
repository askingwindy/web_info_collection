"""Explicit user objective beside an immutable producer candidate goal."""
from copy import deepcopy
from .batch_core import load_json
from .planning import verify_evidence, object_sha256

VERSION='webcollect-session-objective-1'
# Per-objective execution-evidence policies a frozen objective may select. The
# chosen protocol is stamped into spec+fragment before the task-id hash, so it
# is part of frozen task identity; older objectives without the field keep the
# protocol their generator bound.
EVIDENCE_POLICIES=('webcollect-action-scoped-evidence-1',)

def bind(reference,claim):
    verify_evidence([reference]);value=load_json(reference['path'])
    if (value.get('schema_version')!=VERSION or value.get('candidate_id')!=claim['candidate_id']
            or value.get('version')!=claim['version'] or value.get('entry_url')!=claim['snapshot']['entry_url']
            or value.get('requested_goal')!=claim['snapshot'].get('requested_goal')):
        raise ValueError('Session objective differs from original candidate identity/goal')
    objective=value.get('objective') or {}
    minimum=objective.get('minimum_effective_steps');band=objective.get('preferred_band')
    if (not objective.get('description') or type(minimum) is not int
            or band not in ('five','long') or not (minimum==5 if band=='five' else 5<=minimum<=8)):
        raise ValueError('Explicit objective and compatible five/long operation minimum required')
    policy=objective.get('evidence_policy')
    if policy is not None and policy not in EVIDENCE_POLICIES:
        raise ValueError('Unknown objective evidence policy')
    return {'reference':deepcopy(reference),'objective':deepcopy(objective)}

def apply(task,binding):
    spec=task['workflow_proposal']['spec'];spec['session_objective']=deepcopy(binding)
    task['fragment']['session_objective']=deepcopy(binding)
    from .direct_article import enabled as direct
    if direct(task):
        from .direct_completion import VERSION as COMPLETION
        spec['direct_completion_protocol']=task['fragment']['direct_completion_protocol']=COMPLETION
    policy=binding['objective'].get('evidence_policy')
    if policy:
        from .action_stability import ACTION_SCOPED_VERSION
        if policy!=ACTION_SCOPED_VERSION or not task['fragment'].get('plan_protocol'):
            raise ValueError('Objective evidence policy requires a conditional-plan task')
        spec['action_stability_protocol']=policy
        task['fragment']['action_stability_protocol']=policy
    instruction=binding['objective']['description']
    spec['goal']['instruction']=instruction
    for field in ('instruction','final_result','completion_judgement'):task[field]=instruction
    task['task_id']='react-'+object_sha256({'url':spec['entry_url'],'spec':spec})[:24]


def progress(session,initial_observation_id):
    """Goal evidence from actual parameter changes/results or search/read actions.

    No URL, action sequence or answer is supplied here. This is a verifier of
    this session's actual trace and synchronized visible nodes, not an executor.
    """
    from .goal_evidence import contract_for, progress as contracted_progress
    contract = contract_for(session.task)
    if contract:
        return contracted_progress(session, initial_observation_id, contract)
    from decimal import Decimal,InvalidOperation
    from pathlib import Path
    from urllib.parse import urlsplit,parse_qs
    objective=session.task.get('fragment',{}).get('session_objective',{}).get('objective',{})
    kind=objective.get('kind');supported=kind in ('mortgage_calculation','site_search_reading')
    result={'kind':kind,'required':supported,'status':'UNVERIFIED' if supported else 'NOT_CONFIGURED','is_AI_review':False}
    if not supported:return result
    observations=session.observation_records;initial=observations.get(initial_observation_id)
    if not initial:return {**result,'reason':'initial objective observation missing'}
    def state(ob):return load_json(ob['evidence']['state']['path'])
    def html(ob):
        if isinstance(ob.get('html'),str):return ob['html']
        ref=ob.get('evidence',{}).get('html') or ob.get('html_ref')
        return Path(ref['path']).read_text() if ref else ''
    def decimal(value):
        try:return Decimal(str(value).replace(',','').replace('%','').strip())
        except (InvalidOperation,ValueError):return None
    current=session.current;now=state(current);base=state(initial);trace=session.trajectory
    if kind=='mortgage_calculation':
        wanted={decimal(v) for v in objective.get('parameters',{}).values() if isinstance(v,(int,float))}
        changes=[]
        for action in trace:
            if action['action']!='type':continue
            before=state(observations[action['before_observation_id']]);after=state(observations[action['after_observation_id']])
            cid=(action.get('target') or {}).get('control_id')
            old=next((v for v in before.get('values',[]) if v['element_id']==cid),{})
            new=next((v for v in after.get('values',[]) if v['element_id']==cid),{})
            if old.get('value')!=new.get('value') and decimal(new.get('value')) in wanted:
                changes.append({'operation_id':action['operation_id'],'node':cid,'before_value':old.get('value'),'after_value':new.get('value'),
                    'after_observation_id':action['after_observation_id'],'evidence':observations[action['after_observation_id']]['evidence']})
        # Reject echoes of both original and newly entered parameters.
        union={**base,'values':list(base.get('values',[]))+[{'value':c['after_value']} for c in changes]}
        from .template_learning import result_evidence
        proofs=result_evidence(now,union,html(current),html(initial)) if current.get('capture_verified') else []
        covered={decimal(c['after_value']) for c in changes}
        ok=bool(len({c['node'] for c in changes})>=2 and wanted<=covered and proofs)
        return {**result,'status':'VERIFIED' if ok else 'UNVERIFIED','parameter_changes':changes,'expected_numeric_parameters_covered':wanted<=covered,
                'new_visible_named_results':proofs,'result_observation_id':current['observation_id'],'result_evidence':current['evidence']}
    query=objective.get('parameters',{}).get('query');typed=[];search=[];opened=[];body=[]
    initial_links={c.get('binding',{}).get('href') for c in initial.get('controls',{}).values()}
    for action in trace:
        if action['action']=='type' and action.get('arguments',{}).get('text')==query:
            after=state(observations[action['after_observation_id']]);cid=(action.get('target') or {}).get('control_id')
            if any(v['element_id']==cid and v.get('value')==query for v in after.get('values',[])):typed.append(action['operation_id'])
    if typed:
        for oid,ob in observations.items():
            st=state(ob);query_seen=query in (st.get('visible_text') or '') or any(v.get('value')==query for v in st.get('values',[]))
            full_search=query in parse_qs(urlsplit(st['url']).query).get('search',[])
            links=[{'node':cid,'href':c.get('binding',{}).get('href'),'text':c['element'].get('text')} for cid,c in ob.get('controls',{}).items()
                if c['element'].get('visible') is True and c['element'].get('native_role')=='a' and c['element'].get('text') and c.get('binding',{}).get('href') not in initial_links]
            if ob.get('capture_verified') and (full_search or (query_seen and links)):
                search.append({'observation_id':oid,'url':st['url'],'visible_result_or_suggestion_links':links,'evidence':ob['evidence']})
        sources={s['observation_id']:s for s in search}
        for action in trace:
            if action['action']!='click' or action['before_observation_id'] not in sources:continue
            before=observations[action['before_observation_id']];after=observations[action['after_observation_id']]
            cid=(action.get('target') or {}).get('control_id');href=before.get('controls',{}).get(cid,{}).get('binding',{}).get('href')
            if href and before['document_identity']!=after['document_identity'] and before['url']!=after['url']:
                opened.append({'operation_id':action['operation_id'],'source_observation_id':before['observation_id'],'landing_observation_id':after['observation_id'],'href':href,'landed_url':after['url'],'trace_index':trace.index(action),'evidence':after['evidence']})
        from .plan_evidence import region_matches
        for action in trace:
            if action['action']!='scroll':continue
            before=state(observations[action['before_observation_id']]);after=state(observations[action['after_observation_id']])
            if not any(o['landed_url']==after['url'] and o['trace_index']<trace.index(action) for o in opened) or before.get('scroll')==after.get('scroll'):continue
            old_text={e.get('text') for e in before.get('elements',[]) if e.get('visible') is True}
            for e in after.get('elements',[]):
                text=e.get('text') or ''
                if e.get('visible') is True and len(text)>=30 and text not in old_text and region_matches(after,e['element_id'],'正文'):
                    body.append({'operation_id':action['operation_id'],'node':e['element_id'],'quote':text,'observation_id':action['after_observation_id'],
                        'title':after.get('title'),'url':after['url'],'evidence':observations[action['after_observation_id']]['evidence']})
    final_body=[b for b in body if b['url']==now['url'] and any(e.get('element_id')==b['node'] and e.get('visible') is True and e.get('text')==b['quote'] for e in now.get('elements',[]))]
    return {**result,'status':'VERIFIED' if typed and search and opened and final_body else 'UNVERIFIED','final_visible_body':final_body,'query':query,'typed_operations':typed,'search_results_or_suggestions':search,'opened_results':opened,'new_visible_body':body}
