"""Consumer-only, source-bound transient observation protocol; never grants ready."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from .batch_core import load_json
from .planning import object_sha256, verify_evidence, validate_capability

VERSION = 'webcollect-candidate-consumption-1'
RESEARCH_V2 = 'candidate-research-replay-2'
RESEARCH_V3 = 'candidate-research-replay-3'


def research_v2_inputs(descriptor):
    """Frozen development inputs, never historical page/action evidence."""
    required = {'schema_version', 'original_claim_id', 'objective', 'authorization',
                'comparisons', 'production_counted'}
    if (set(descriptor) != required or descriptor['schema_version'] not in (RESEARCH_V2, RESEARCH_V3)
            or not descriptor['original_claim_id'] or descriptor['production_counted'] is not False):
        raise ValueError('Invalid research v2 input metadata')
    verify_evidence([descriptor['objective'], descriptor['authorization']])
    objective = load_json(descriptor['objective']['path'])
    authorization = load_json(descriptor['authorization']['path'])
    comparisons = descriptor['comparisons']
    if (objective.get('schema_version') != 'webcollect-session-objective-1'
            or authorization.get('scope') != 'fixed-baseline-research-only'
            or authorization.get('candidate_id') != objective.get('candidate_id')
            or authorization.get('version') != objective.get('version')
            or authorization.get('original_claim_id') != descriptor['original_claim_id']
            or authorization.get('objective') != descriptor['objective']
            or authorization.get('comparisons') != comparisons
            or authorization.get('production_counted') is not False
            or not authorization.get('pool') or not authorization.get('registry')
            or not isinstance(comparisons, list)):
        raise ValueError('Research v2 authorization and original objective differ')
    seen = set()
    for item in comparisons:
        if (set(item) != {'role', 'claim_id', 'sample_id', 'save_receipt'}
                or item['role'] != 'comparison' or not item['claim_id'] or not item['sample_id']
                or item['sample_id'] in seen):
            raise ValueError('Research v2 requires uniquely named comparison samples')
        verify_evidence([item['save_receipt']])
        if load_json(item['save_receipt']['path']).get('sample_id') != item['sample_id']:
            raise ValueError('Research comparison save receipt differs')
        seen.add(item['sample_id'])
    return authorization


def validate_research_v2(descriptor, pool, original, registry=None):
    """V2 keeps failed sources; V3 also accepts settled nonproduction saves."""
    authorization = research_v2_inputs(descriptor)
    saved_replay = descriptor['schema_version'] == RESEARCH_V3
    old = original.get('binding') or {}
    objective = load_json(descriptor['objective']['path'])
    if (original['claim_id'] != descriptor['original_claim_id']
            or original['state'] not in (('failed', 'succeeded') if saved_replay else ('failed',))
            or (original['candidate_id'], original['version']) !=
               (objective.get('candidate_id'), objective.get('version'))
            or any(not old.get(k) for k in ('output', 'registry', 'ledger', 'history_set'))):
        raise ValueError('Research v3 requires a settled failed or saved research execution' if saved_replay
                         else 'Research v2 requires the settled failed original execution')
    from .batch_core import file_sha
    original_objective = Path(old['output']) / 'session-objective.json'
    if file_sha(original_objective) != descriptor['objective']['sha256']:
        raise ValueError('Research v2 cannot change original objective bytes')
    if (Path(authorization['pool']).resolve() != pool.path.resolve()
            or Path(authorization['registry']).resolve() != Path(old['registry']).resolve()
            or registry is not None and Path(registry).resolve() != Path(old['registry']).resolve()):
        raise ValueError('Research v2 changes the original pool or registry')
    def nonproduction_save(row, saved, binding):
        replay = binding.get('research_replay') or {}
        return (row['effective'] == 0
                and replay.get('schema_version') in ('candidate-research-replay-1', RESEARCH_V2, RESEARCH_V3)
                and replay.get('production_counted') is False
                and saved.get('production_counted', False) is False
                and saved.get('research_replay', replay) == replay)
    with pool.pool.connect() as con:
        if original['state'] == 'succeeded':
            row = con.execute('SELECT * FROM candidate_results WHERE candidate_id=? AND claim_id=?',
                              (original['candidate_id'], original['claim_id'])).fetchone()
            saved = json.loads(row['record']) if row else {}
            if (not row or not nonproduction_save(row, saved, old)
                    or saved.get('sample_id') != row['sample_id']
                    or Path(saved.get('registry', '')).resolve() != Path(old['registry']).resolve()
                    or not saved.get('save_receipt')):
                raise ValueError('Research v3 requires the original saved nonproduction result')
            verify_evidence([saved['save_receipt']])
            if load_json(saved['save_receipt']['path']).get('sample_id') != row['sample_id']:
                raise ValueError('Research source save receipt differs')
        for comparison in descriptor['comparisons']:
            row = con.execute('''SELECT r.record,r.effective,c.binding,c.state FROM candidate_results r
                JOIN candidate_claims c USING(candidate_id,claim_id)
                WHERE r.claim_id=? AND r.sample_id=?''',
                (comparison['claim_id'], comparison['sample_id'])).fetchone()
            saved = json.loads(row['record']) if row else {}
            binding = json.loads(row['binding'] or '{}') if row else {}
            if (not row or row['state'] != 'succeeded'
                    or not (row['effective'] == 1 or saved_replay and nonproduction_save(row, saved, binding))
                    or saved.get('sample_id') != comparison['sample_id']
                    or saved.get('save_receipt') != comparison['save_receipt']
                    or Path(saved.get('registry', '')).resolve() != Path(old['registry']).resolve()
                    or Path(binding.get('registry', '')).resolve() != Path(old['registry']).resolve()):
                raise ValueError('Research comparison lacks its same-pool/registry historical save')
    return authorization


def research_overlap_sample_ids(basis):
    if not basis:
        return set()
    if basis['schema_version'] == 'candidate-research-duplicate-1':
        return {basis['original_sample_id']}
    return {item['sample_id'] for item in basis['comparisons']}


def research_duplicate_basis(task, registry):
    """Only explicitly bound saved samples may overlap a research replay.

    A task field alone grants nothing: frozen claim, live pool event, original
    result, objective and registry must all describe the same replay. V1 permits
    its same-target original save; V2 permits individually named comparisons.
    """
    if not task.get('candidate_binding'):
        return None
    binding = validate_task_binding(task)
    frozen = load_json(binding['claim_reference']['path'])
    descriptor = (frozen.get('binding') or {}).get('research_replay')
    if descriptor is None:
        return None
    from site_planner.candidate_pool import CandidatePool
    pool = CandidatePool(frozen['pool'])
    live = pool.get_claim(binding['claim_id'])
    if ((live.get('binding') or {}).get('research_replay') != descriptor
            or live['candidate_id'] != binding['candidate_id'] or live['version'] != binding['version']):
        raise ValueError('Research duplicate exception lacks its original pool binding')
    from .current_chain import read_chain_scope, assert_current_evidence
    scope = read_chain_scope(live['binding']['history_set'])
    assert_current_evidence(scope, descriptor)
    with pool.pool.connect() as con:
        original = con.execute('SELECT * FROM candidate_claims WHERE claim_id=? AND candidate_id=? AND version=?',
            (descriptor['original_claim_id'], binding['candidate_id'], binding['version'])).fetchone()
        result = con.execute('SELECT * FROM candidate_results WHERE claim_id=? AND effective=1',
            (descriptor['original_claim_id'],)).fetchone()
        events = [json.loads(r[0]) for r in con.execute("SELECT record FROM candidate_events WHERE claim_id=? AND kind='research_claimed'", (binding['claim_id'],))]
    if descriptor.get('schema_version') in (RESEARCH_V2, RESEARCH_V3):
        if (not original or not any(all(event.get(k) == v for k, v in descriptor.items()) for event in events)
                or Path(live['binding']['registry']).resolve() != Path(registry).resolve()):
            raise ValueError('Research v2 lacks frozen/live original authorization')
        validate_research_v2(descriptor, pool, pool._claim(original), registry)
        return {'schema_version': 'candidate-research-duplicate-2', 'research_claim_id': binding['claim_id'],
                'original_claim_id': descriptor['original_claim_id'], 'comparisons': descriptor['comparisons'],
                'claim_reference': binding['claim_reference'], 'authorization': descriptor['authorization'],
                'production_counted': False, 'production_duplicate_acceptance': False,
                'automatic_review': False}
    if (not original or original['state'] != 'succeeded' or not result
            or not any(all(event.get(k)==v for k,v in descriptor.items()) for event in events)):
        raise ValueError('Research duplicate exception lacks original saved authorization')
    original_binding = json.loads(original['binding'])
    if (Path(original_binding['registry']).resolve() != Path(registry).resolve()
            or Path(live['binding']['registry']).resolve() != Path(registry).resolve()
            or load_json(Path(original_binding['output'])/'session-objective.json') != load_json(descriptor['objective']['path'])):
        raise ValueError('Research duplicate exception changes the registry or original goal')
    saved = json.loads(result['record'])
    return {'schema_version':'candidate-research-duplicate-1', 'research_claim_id':binding['claim_id'],
            'original_claim_id':descriptor['original_claim_id'], 'original_sample_id':saved['sample_id'],
            'claim_reference':binding['claim_reference'], 'authorization':descriptor['authorization'],
            'production_counted':False, 'production_duplicate_acceptance':False}


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
    if (binding.get('site_id_version')!=claim.get('site_id_version')
            or binding.get('site_id')!=claim.get('site_id')
            or claim.get('site_id') is not None and claim.get('site_id_version')!='table1-rowid-site-id-1'):
        raise ValueError('Original Table1 delivery site ID changed')
    if binding.get('sources', claim.get('sources')) != claim.get('sources'):
        raise ValueError('Original frozen candidate sources changed')
    if not observed['capture_verified'] or not observed['document_identity'] or not application_matches(claim['snapshot']['entry_url'],observed['url'],claim.get('application_registry')):
        raise ValueError('First observation lacks synchronized capture or proven application landing')
    category = binding['candidate'].get('parent_category')
    if (category is not None and record['site_category']!=category) or record['site_uri']!=observed['url']:
        raise ValueError('Candidate classification/page binding differs')
    return binding


def capability(claim, anchor, claim_reference, mode, *, category=None, name=None):
    state=load_json(anchor['state']['path']); now=datetime.now(timezone.utc)
    candidate=claim['snapshot']
    result={'schema_version':'webcollect-site-capability-1','capability_id':'candidate-observation-'+claim['claim_id'],
        'version':VERSION,'site_uri':state['url'],'site_category':candidate.get('parent_category') or category or 'UNKNOWN','mode':mode,
        'status':'review_required','reason':'Consumer first observation; qualification NOT_RUN',
        'observed_at':now.isoformat(),'expires_at':(now+timedelta(hours=4)).isoformat(),
        'supported_actions':['click','double_click','right_click','type','select','hotkey','scroll','open_url','back'],
        'task_families':['navigation-reading'], 'evidence':list(anchor.values())+[claim_reference],
        'capabilities':[{'page_uri':state['url'],'title':state.get('title') or candidate.get('name',name),'page_anchor':anchor}],
        'candidate_observation':{'schema_version':VERSION,'candidate_id':claim['candidate_id'],'claim_id':claim['claim_id'],
            'version':claim['version'],'candidate':deepcopy(candidate),'claim_reference':claim_reference,
            'application_registry':claim.get('application_registry'),
            **({'site_id_version':'table1-rowid-site-id-1','site_id':claim['site_id']}
               if claim.get('site_id') else {})}}
    if candidate.get('schema_version') == 'webcollect-data-candidate-2':
        result['candidate_observation']['sources'] = deepcopy(claim.get('sources', []))
    result['classification'] = {'status': 'pending' if result['site_category'] == 'UNKNOWN' else 'source_provided',
                                'value': None if result['site_category'] == 'UNKNOWN' else result['site_category'],
                                'sources': deepcopy(claim.get('sources', []))}
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
    if (binding.get('site_id_version')!=claim.get('site_id_version')
            or binding.get('site_id')!=claim.get('site_id')
            or claim.get('site_id') is not None and claim.get('site_id_version')!='table1-rowid-site-id-1'):
        raise ValueError('Frozen Table1 delivery site ID changed')
    if binding.get('sources', claim.get('sources')) != claim.get('sources'):
        raise ValueError('Frozen candidate sources changed')
    if task['fragment'].get('candidate_attempt')!=binding['claim_id']:
        raise ValueError('Candidate attempt boundary differs')
    from .react_session import is_react_task
    if is_react_task(task):
        candidate = binding['candidate']
        if candidate.get('schema_version') == 'webcollect-data-candidate-2':
            expected = candidate['requested_goal'] if candidate['candidate_kind'] == 'target' else None
            if task['workflow_proposal']['spec']['goal']['structured'] != expected:
                raise ValueError('Frozen V2 requested goal differs from original claim')
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
