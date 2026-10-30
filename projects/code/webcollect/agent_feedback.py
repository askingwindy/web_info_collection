"""Read original attempt/QC evidence into site context, never issue reviews."""
import json
from pathlib import Path
import sqlite3
from .batch_core import load_json, file_sha
from .planning import verify_evidence, object_sha256
from .agent_controller import exclusive

VERSION = 'webcollect-site-agent-feedback-1'


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': file_sha(path)}


def save_attempt_feedback(evidence, attempt, outcome, error=None):
    """Companion receipt captured before finish_attempt binds step/image bytes."""
    evidence = Path(evidence)
    steps = []
    for path in sorted(evidence.glob('step_*.json')):
        if not path.stem[5:].isdigit():
            continue
        raw = load_json(path)
        steps.append({'step_id': raw['step_id'], 'operation': raw['operation'],
            'target': raw.get('target_element'), 'execution_error': raw.get('execution_error'),
            'ended_at': raw.get('ended_at'), 'state': raw['state'], 'raw': reference(path),
            'image': {'path': str((evidence.parent.parent/('samples' if outcome == 'collected_pending_review' else 'rejected')/attempt['sample_id']/f"images/step_{raw['step_id']:03}.png").resolve()),
                      'sha256': raw['capture']['screenshot_sha256']}})
    diagnostics = []
    for name in ('producer_dedup.json', 'capture_failure.json', 'failure_after.json', 'preparation_failure.json'):
        if (evidence/name).exists():
            diagnostic = {'reference': reference(evidence/name), 'actual': load_json(evidence/name)}
            if (evidence/Path(name).with_suffix('.png')).exists():
                diagnostic['image'] = reference(evidence/Path(name).with_suffix('.png'))
            diagnostics.append(diagnostic)
    path = evidence/f'planning-feedback-{outcome}.json'
    return exclusive(path, {'schema_version': VERSION,
        'attempt_id': attempt['attempt_id'], 'sample_id': attempt['sample_id'], 'task_id': attempt['task_id'],
        'outcome': outcome, 'error': error, 'steps': steps, 'diagnostics': diagnostics,
        'semantic_review': 'REVIEW_REQUIRED', 'QC_approval': False})


def site_context(registry, site_uri, *, generation=(), quality=(), model_ledger=None):
    from .application_identity import host_key
    quality_groups = [[ref] for ref in quality]
    result = {'schema_version': VERSION, 'generation': list(generation), 'executions': [],
              'quality': [], 'images': [], 'avoid': [], 'unresolved': []}
    if registry is not None and Path(registry).exists():
        with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True) as con:
            con.row_factory = sqlite3.Row
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {'m4_attempts','m4_tasks'} <= tables:
                rows = con.execute('SELECT a.*,t.task_json FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key ORDER BY a.created_at DESC').fetchall()
                for row in rows:
                    task = json.loads(row['task_json'])
                    if host_key(task['site_uri']) != host_key(site_uri):
                        continue
                    refs = json.loads(row['evidence_json'] or '[]')
                    if refs: verify_evidence(refs)
                    entry = {'attempt_id':row['attempt_id'], 'sample_id':row['sample_id'], 'task_id':task['task_id'],
                        'instruction':task.get('instruction'), 'status':row['status'], 'root_cause':row['root_cause'],
                        'failure_class':row['failure_class'], 'references':refs, 'feedback_status':'LEGACY_NO_STEP_BINDING'}
                    for ref in refs:
                        try: value = load_json(ref['path'])
                        except (ValueError, UnicodeError): continue
                        if value.get('schema_version') == VERSION:
                            step_refs = [s['raw'] for s in value['steps']] + [s['image'] for s in value['steps']]
                            if step_refs: verify_evidence(step_refs)
                            diagnostic_refs = [d['reference'] for d in value['diagnostics']] + [d['image'] for d in value['diagnostics'] if 'image' in d]
                            if diagnostic_refs: verify_evidence(diagnostic_refs)
                            entry.update(feedback=value, feedback_status='BOUND_ORIGINAL_STEPS')
                            result['images'].extend(s['image'] for s in value['steps'])
                            result['images'].extend(d['image'] for d in value['diagnostics'] if 'image' in d)
                            for s in value['steps']:
                                if s.get('execution_error'):
                                    result['avoid'].append({'operation':s['operation'], 'reason':s['execution_error'],
                                        'state':s['state'], 'image':s['image'], 'source':ref})
                    if 'm4_reviews' in tables:
                        reviewed = con.execute('SELECT evidence_json FROM m4_reviews WHERE sample_id=?', (row['sample_id'],)).fetchone()
                        if reviewed:
                            quality_groups.append(json.loads(reviewed[0]))
                    if 'm4_quality_admissions' in tables:
                        admitted = con.execute('SELECT report_json FROM m4_quality_admissions WHERE sample_id=?', (row['sample_id'],)).fetchone()
                        if admitted:
                            quality_groups.append([json.loads(admitted[0])])
                    result['executions'].append(entry)
                    if row['status'] in ('reserved','running','interrupted') or row['failure_class'] in ('unknown','interrupted'):
                        result['unresolved'].append(entry)
    if model_ledger is not None:
        with model_ledger.connect() as con:
            for row in con.execute("SELECT id,kind,state,payload,result FROM jobs WHERE kind IN ('fragment-decision','task-generation')"):
                payload = json.loads(row['payload'])
                matching = payload.get('site_uri') and host_key(payload['site_uri']) == host_key(site_uri)
                if row['state'] != 'done' and (not payload.get('site_uri') or matching):
                    result['unresolved'].append({'job_id':row['id'], 'state':row['state'],
                        'category':'UNRESOLVED_REQUEST', 'payload':payload})
                elif row['state'] == 'done' and row['kind'] == 'task-generation' and matching:
                    # Works for direct generate/execute too, without requiring
                    # a caller to manually pass a rolling-round summary path.
                    outputs = [json.loads(e[0]) for e in con.execute(
                        "SELECT detail FROM batch_events WHERE event='phase_output' ORDER BY seq")]
                    result['generation'].append({'job_id':row['id'], 'original_payload':payload,
                        'model_response':json.loads(row['result']) if row['result'] else None,
                        'compilation':[e for e in outputs if e.get('job_id') == row['id']],
                        'frozen_tasks':[json.loads(t[0]) for t in con.execute(
                            'SELECT DISTINCT task_json FROM generated_task_index WHERE job_id=?',(row['id'],))]})
    from .runtime import _bound_quality_report
    for group in {object_sha256(g):g for g in quality_groups}.values():
        report, binding = _bound_quality_report(group)
        result['quality'].append({'binding':binding, 'report':report})
        # Dataset bytes are verified by the original QC binding gate above.
        for sample in (Path(report['dataset'])/'samples').iterdir():
            for image in sorted((sample/'images').glob('*.png')):
                result['images'].append(reference(image))
    # All bound images are sent; an over-large context must stop at the gateway's
    # configured image/input budget rather than silently omit failure evidence.
    result['images'] = list({r['sha256']:r for r in result['images']}.values())
    result['context_sha256'] = object_sha256(result)
    return result


def known_start_conflicts(registry, capability, spec):
    """Use existing committed exact-image claims; first frame isn't a full QC."""
    index = int(spec['page_id'][1:])
    image = capability['capabilities'][index]['page_anchor']['image']
    verify_evidence([image])
    if not Path(registry).exists():
        return []
    with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m4_exact_images'").fetchone():
            return []
        rows = [dict(r) for r in con.execute('SELECT * FROM m4_exact_images WHERE digest=?', (image['sha256'],))]
        for row in rows:
            verify_evidence([{'path':row['path'],'sha256':row['digest']}])
        return rows
