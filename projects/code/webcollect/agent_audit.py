"""Independent checks of the new append-only decision-to-execution bindings."""
from .batch_core import load_json
from .planning import verify_evidence, object_sha256
from .agent_observation import require_action


def terminal_proof(task, records, final_binding):
    actions = [r for r in records if r['operation']['action_type'] not in ('wait','complete')]
    if not 5 <= len(actions) <= task['fragment']['budgets']['max_actions'] or not final_binding.get('screenshot_sha256'):
        raise ValueError('Controlled fragment requires 5-8 actual actions and saved ending')
    if 'candidate_binding' in task:
        from .candidate_navigation import verify_path
        verify_path(task, [r['state'] for r in records], [r['operation'] for r in records])
    seen = set()
    for raw in actions:
        if not raw.get('ended_at') or raw.get('execution_error'):
            raise ValueError('Failed/unresolved dispatch cannot complete')
        ref = raw.get('controller_dispatch')
        if not ref:
            raise ValueError('Missing original pre-action decision')
        verify_evidence([ref]); intent = load_json(ref['path'])
        verify_evidence([intent['boundary'], intent['decision'], intent['actual_image']])
        if load_json(intent['boundary']['path'])['task'] != task:
            # Runtime-only fields are part of the original boundary too.
            raise ValueError('Controller boundary changed')
        if intent['operation'] != raw['operation'] or intent['operation']['operation_id'] in seen:
            raise ValueError('Original decision differs from executed operation')
        if intent['actual_image']['sha256'] != raw['capture']['screenshot_sha256']:
            raise ValueError('Dispatch image changed')
        obs = intent['observation']; verify_evidence(list(obs['evidence'].values()))
        if obs['state_sha256'] != object_sha256(raw['state']):
            raise ValueError('Dispatch state changed')
        require_action(raw['state'], raw['operation'])
        seen.add(raw['operation']['operation_id'])
    return {'schema_version':'controlled-fragment-evidence','machine_status':'PASS',
        'business_completion':'NOT_CLAIMED','effective_steps':len(actions),'ending_frame':final_binding,
        'executed_operation_ids':sorted(seen),'semantic_status':'REVIEW_REQUIRED'}
