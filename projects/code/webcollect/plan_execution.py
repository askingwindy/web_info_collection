"""Evidence-only advancement of a planned navigation; never goal acceptance."""
from urllib.parse import urldefrag, unquote

from .batch_core import load_json
from .planning import object_sha256, verify_evidence

from .plan_protocol import PLAN_EXECUTION_POLICY as VERSION


def enabled(task):
    return task.get('fragment',{}).get('plan_execution_policy')==VERSION


def same_destination(a,b):
    if not a or not b:return False
    base_a,fragment_a=urldefrag(a);base_b,fragment_b=urldefrag(b)
    return base_a==base_b and unquote(fragment_a)==unquote(fragment_b)


def step_execution_proof(task,step,row,before,after,*,target_id=None):
    """An observed planned link reached its actual href with a verified effect.

    Only a literal-text expectation may be superseded. Input, focus, result
    checks and the finish predicate retain their own evidence semantics.
    Redirects without an archived route witness remain unresolved.
    """
    from .wiki_reading import enabled as wiki
    ordinary=wiki(task)
    action=step.get('action')
    if (not enabled(task) or row.get('action')!=action
            or action not in (('click','scroll','hotkey','back') if ordinary else ('click',))
            or (step.get('expected') or {}).get('kind') not in (('visible_text','url') if ordinary else ('visible_text',))
            or not str(step.get('purpose') or '').strip()):return None
    cid=(row.get('target') or {}).get('control_id')
    if (action=='click' and not cid) or (target_id is not None and cid!=target_id):return None
    node=next((e for e in before.get('elements',[]) if e['element_id']==cid),None)
    binding=next((b for b in before.get('capture_controls',[]) if b['element_id']==cid),None)
    href=None;anchor=False;navigation=False;reading=False
    if action=='click':
        target=step.get('target') or {}
        if (not node or node.get('visible') is not True or not binding
                or binding.get('tag')!='a' or not binding.get('href')
                or (not target.get('text') and not ordinary)
                or target.get('text','') not in (node.get('text') or '')
                or (target.get('href') and not same_destination(target['href'],binding['href']))):return None
        href=binding['href']
        if not same_destination(href,after.get('url')):return None
        same_document=before.get('document_identity')==after.get('document_identity')
        before_base,_=urldefrag(before.get('url',''));href_base,fragment=urldefrag(href)
        anchor=(same_document and before_base==href_base and bool(fragment)
                and (before.get('url')!=after.get('url') or before.get('scroll')!=after.get('scroll')))
        navigation=(before.get('url')!=after.get('url') and not same_document)
        if not anchor and not navigation:return None
    elif action in ('scroll','hotkey'):
        from .direct_article import body
        old={p['quote'] for p in body(before)}
        reading=(before.get('document_identity')==after.get('document_identity')
                 and before.get('scroll')!=after.get('scroll')
                 and bool({p['quote'] for p in body(after)}-old))
        if not reading:return None
    elif action=='back':
        navigation=(before.get('url')!=after.get('url') or before.get('document_identity')!=after.get('document_identity'))
        if not navigation:return None
    refs=[row.get('raw_step'),row.get('dispatch')]
    if not all(refs):return None
    verify_evidence(refs)
    raw=load_json(row['raw_step']['path']);dispatch=load_json(row['dispatch']['path'])
    operation=raw.get('operation') or {};react=raw.get('react') or {}
    if (raw.get('dispatched') is not True or raw.get('action_executed') is not True
            or raw.get('postconditions_checked') is not True or raw.get('execution_error')
            or raw.get('unknown') is True or react.get('unknown') is True
            or operation.get('operation_id')!=row.get('operation_id')
            or operation.get('action_type')!=action or operation.get('arguments')!=row.get('arguments')
            or operation.get('goal')!=step['purpose']
            or operation.get('evidence',{}).get('anchor_element_id')!=cid
            or operation.get('evidence',{}).get('state_sha256')!=object_sha256(before)
            or dispatch.get('operation')!=operation or raw.get('state')!=before
            or react.get('before_observation_id')!=row.get('before_observation_id')
            or react.get('after_observation_id')!=row.get('after_observation_id')):return None
    from .react_protocol import atomic_effect, RULE_VERSION
    effect=atomic_effect(before,after,action,row['arguments'],cid,
                         rule_version=task['fragment'].get('effective_action_rule',RULE_VERSION))
    if not effect['verified'] or react.get('effect_evidence')!=effect:return None
    from .react_session import struct_goal
    return {'policy':VERSION,'kind':('PLANNED_BODY_READING' if reading else 'PLANNED_BACK_LANDING' if action=='back' else 'PLANNED_ANCHOR_LANDING' if anchor else 'PLANNED_LINK_LANDING'),
        'plan_step_sha256':object_sha256(step),'requested_goal_sha256':object_sha256(struct_goal(task)),
        'operation_id':row['operation_id'],'raw_step':row['raw_step'],'dispatch':row['dispatch'],
        'before_observation_id':row['before_observation_id'],'after_observation_id':row['after_observation_id'],
        'source_node':cid,'actual_visible_target':(node or {}).get('text'),'clicked_href':href,
        'origin_url':before['url'],'landed_url':after['url'],'atomic_effect':effect,
        'business_goal_completed':False,'literal_expectation_proven':False}
