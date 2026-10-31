"""Consumer-only, source-bound transient observation protocol; never grants ready."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from .batch_core import load_json
from .planning import object_sha256, verify_evidence, validate_capability

VERSION = 'webcollect-candidate-consumption-1'


def instruction(candidate):
    return f'在「{candidate["name"]}」围绕「{candidate["description"]}」操作并查看本段状态。目标条件：' + json.dumps(candidate['target'],ensure_ascii=False,sort_keys=True)


def fragment_ending(candidate):
    """Bind the same business intent without promising its full completion."""
    return f'查看围绕「{candidate["description"]}」操作后的本段实际状态；完整业务完成未声明。'


def application_matches(entry, url, registry=None):
    from site_planner.site_pool import host_identity
    from .collect import verify_public_url
    verify_public_url(url)
    if registry is not None:
        from .application_identity import canonical_key
        return canonical_key(entry,registry)==canonical_key(url,registry)
    return host_identity(entry)==host_identity(url)


def validate_observation(record):
    validate_capability(record, require_ready=False)
    binding=record.get('candidate_observation',{})
    if binding.get('schema_version')!=VERSION or not binding.get('candidate_id') or not binding.get('claim_id') or record['status']!='review_required':
        raise ValueError('Consumer transient observation binding required; no ready conversion')
    verify_evidence([binding['claim_reference']])
    claim=load_json(binding['claim_reference']['path'])
    if (claim['candidate_id'],claim['claim_id'],claim['version'],claim['snapshot']) != (binding['candidate_id'],binding['claim_id'],binding['version'],binding['candidate']):
        raise ValueError('Original claimed target differs')
    anchor=record['capabilities'][0]['page_anchor']
    from .agent_observation import project
    observed=project(load_json(anchor['state']['path']),anchor)
    if binding.get('application_registry')!=claim.get('application_registry'):
        raise ValueError('Original application aliases changed')
    if not observed['capture_verified'] or not observed['document_identity'] or not application_matches(claim['snapshot']['entry_url'],observed['url'],claim.get('application_registry')):
        raise ValueError('First observation lacks synchronized capture or proven application landing')
    if record['site_category']!=binding['candidate']['parent_category'] or record['site_uri']!=observed['url']:
        raise ValueError('Candidate classification/page binding differs')
    return binding


def capability(claim, anchor, claim_reference, mode):
    state=load_json(anchor['state']['path']); now=datetime.now(timezone.utc)
    candidate=claim['snapshot']
    result={'schema_version':'webcollect-site-capability-1','capability_id':'candidate-observation-'+claim['claim_id'],
        'version':VERSION,'site_uri':state['url'],'site_category':candidate['parent_category'],'mode':mode,
        'status':'review_required','reason':'Consumer first observation; qualification NOT_RUN',
        'observed_at':now.isoformat(),'expires_at':(now+timedelta(hours=4)).isoformat(),
        'supported_actions':['click','double_click','right_click','type','select','hotkey','scroll','open_url','back'],
        'task_families':['navigation-reading'], 'evidence':list(anchor.values())+[claim_reference],
        'capabilities':[{'page_uri':state['url'],'title':state.get('title') or candidate['name'],'page_anchor':anchor}],
        'candidate_observation':{'schema_version':VERSION,'candidate_id':claim['candidate_id'],'claim_id':claim['claim_id'],
            'version':claim['version'],'candidate':deepcopy(candidate),'claim_reference':claim_reference,
            'application_registry':claim.get('application_registry')}}
    validate_observation(result)
    return result


def validate_task_binding(task, record=None):
    binding=task.get('candidate_binding')
    if not binding or binding.get('schema_version')!=VERSION:
        raise ValueError('Versioned candidate task binding required')
    verify_evidence([binding['claim_reference']])
    claim=load_json(binding['claim_reference']['path'])
    if any(claim[k]!=binding[k] for k in ('candidate_id','claim_id','version')) or claim['snapshot']!=binding['candidate']:
        raise ValueError('Frozen claim target changed')
    if binding.get('application_registry')!=claim.get('application_registry'):
        raise ValueError('Frozen application aliases changed')
    if task['fragment'].get('candidate_attempt')!=binding['claim_id']:
        raise ValueError('Candidate attempt boundary differs')
    from .react_session import is_react_task
    if is_react_task(task):
        # New protocol: goal identity stays the structured claimed candidate
        # (read-only requested_goal); the natural delivery instruction is
        # generated at derivation and is no longer compared for equality with
        # the goal JSON. Claim identity and scope checks above still bind.
        if record is not None and binding!=validate_observation(record):
            raise ValueError('Task and first observation refer to different candidates')
        return binding
    if task['instruction']!=instruction(binding['candidate']):
        raise ValueError('Candidate cannot be replaced by an unrelated goal')
    if record is not None and binding!=validate_observation(record):
        raise ValueError('Task and first observation refer to different candidates')
    return binding


def guard_claim(task):
    """Called before planning/dispatch: stale credential cannot start new work."""
    binding=validate_task_binding(task)
    guard_reference(binding['claim_reference'])


def guard_reference(reference):
    claim=load_json(reference['path'])
    from site_planner.candidate_pool import CandidatePool
    pool=CandidatePool(claim['pool'])
    with pool.transaction() as con:
        pool._fence(con,claim)


def same_application(task, url):
    binding=task['candidate_binding']
    return application_matches(binding['candidate']['entry_url'],url,binding.get('application_registry'))
