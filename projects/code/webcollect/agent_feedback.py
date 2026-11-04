"""Read original attempt/QC evidence into site context, never issue reviews."""
import json
from pathlib import Path
import sqlite3
from .batch_core import load_json, file_sha
from .planning import verify_evidence, object_sha256
from .agent_controller import exclusive

VERSION = 'webcollect-site-agent-feedback-1'
# Every decision request carries only the current observation image plus at
# most this many most-recent context images; older evidence stays on disk and
# is reachable through the session's inspect tool instead of growing prompts.
PLANNING_IMAGES_LIMIT = 4


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': file_sha(path)}


def save_attempt_feedback(evidence, attempt, outcome, error=None):
    """Companion receipt captured before finish_attempt binds step/image bytes."""
    evidence = Path(evidence)
    from .batch_core import file_sha
    import shutil
    packaged_root = evidence.parent.parent / ('samples' if outcome == 'collected_pending_review' else 'rejected')
    steps = []
    for path in sorted(evidence.glob('step_*.json')):
        if not path.stem[5:].isdigit():
            continue
        raw = load_json(path)
        declared = packaged_root / attempt['sample_id'] / 'images' / f"step_{raw['step_id']:03}.png"
        if not declared.is_file():
            # React close-out orders: the receipt declares packaging paths the
            # later bind step materializes. Verify every later reader against
            # real bytes immediately: copy the preserved original whose digest
            # equals the step's own capture screenshot receipt, when present.
            want = (raw.get('capture') or {}).get('screenshot_sha256')
            if want:
                source = next((png for png in (evidence / 'raw').glob('*.png')
                               if file_sha(png) == want), None)
                if source is not None:
                    declared.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, declared)
        steps.append({'step_id': raw['step_id'], 'operation': raw['operation'],
            'target': raw.get('target_element'), 'execution_error': raw.get('execution_error'),
            'ended_at': raw.get('ended_at'), 'state': raw['state'], 'raw': reference(path),
            'image': {'path': str(declared.resolve()),
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


def site_context(registry, site_uri, *, generation=(), quality=(), model_ledger=None, collection_report=None,
                 candidate_id=None):
    from urllib.parse import urlsplit
    from .application_identity import aliases, host_key
    from .current_chain import PROJECT_RULES, check_project_guard, registry_project
    from .request_quarantine import job_conflicts
    guard = (model_ledger.config.get('site_failure_guard') or {}) if candidate_id and model_ledger else {}
    scoped = guard.get('dispatch_rules') == PROJECT_RULES
    known_hosts = aliases(guard.get('application_registry')) if scoped else {}
    def context_host(uri):
        key = host_key(uri)
        return urlsplit(known_hosts.get(key, key)).netloc.removeprefix('www.') if scoped else key
    host = context_host(site_uri)
    quality_groups = [[ref] for ref in quality]
    result = {'schema_version': VERSION, 'generation': list(generation), 'executions': [],
              'quality': [], 'images': [], 'avoid': [], 'unresolved': []}
    if registry is not None and Path(registry).exists():
        with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True) as con:
            con.row_factory = sqlite3.Row
            if scoped:
                check_project_guard(registry_project(con), guard, model_ledger.path, role='consumer')
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {'m4_attempts','m4_tasks'} <= tables:
                rows = con.execute('SELECT a.*,t.task_json FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key ORDER BY a.created_at DESC').fetchall()
                for row in rows:
                    task = json.loads(row['task_json'])
                    owner_id = (task.get('candidate_binding') or {}).get('candidate_id') if scoped else None
                    if context_host(task['site_uri']) != host and not (owner_id and owner_id == candidate_id):
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
                            for step in value['steps']:
                                raw=load_json(step['raw']['path'])
                                dispatch=raw.get('controller_dispatch')
                                if not dispatch:continue
                                verify_evidence([dispatch]);formal=load_json(dispatch['path']).get('formal_frame')
                                if formal and not Path(formal['path']).exists():
                                    result.setdefault('frame_relocations',[]).append({
                                        'schema_version':'webcollect-rejected-frame-relocation-1',
                                        'original_path':formal['path'],'original_sha256':formal['sha256'],
                                        'current':step['image'],'dispatch':dispatch})
                            diagnostic_refs = [d['reference'] for d in value['diagnostics']] + [d['image'] for d in value['diagnostics'] if 'image' in d]
                            if diagnostic_refs: verify_evidence(diagnostic_refs)
                            # Rolling context bound: only the two most recent attempts
                            # (rows arrive newest-first) keep full step states and
                            # attach images. Older attempts keep every reason,
                            # operation and reference in a compact form; without
                            # this bound the growing prompt exceeds the gateway
                            # input reservation and blocks all later rounds.
                            recent = len(result['executions']) < 2
                            if recent:
                                # Diagnostic bodies can be large; the advisory
                                # context carries references only — the original
                                # companion files remain on disk unchanged.
                                entry.update(feedback={**{k: v for k, v in value.items() if k != 'diagnostics'},
                                    'diagnostics': [{dk: dv for dk, dv in d.items() if dk != 'actual'}
                                                    for d in value['diagnostics']]},
                                    feedback_status='BOUND_ORIGINAL_STEPS')
                                result['images'].extend(s['image'] for s in value['steps'])
                                result['images'].extend(d['image'] for d in value['diagnostics'] if 'image' in d)
                            else:
                                entry.update(feedback={k: value[k] for k in ('schema_version', 'attempt_id',
                                    'sample_id', 'task_id', 'outcome', 'error')},
                                    feedback_status='BOUND_COMPACT_OLD_ATTEMPT',
                                    steps=[{'step_id': s['step_id'], 'operation': s['operation'],
                                            'execution_error': s['execution_error']} for s in value['steps']],
                                    diagnostics=[{'name': Path(d['reference']['path']).name} for d in value['diagnostics']])
                            for s in value['steps']:
                                if s.get('execution_error'):
                                    row_avoid = {'operation':s['operation'], 'reason':s['execution_error'],
                                        'image':s['image'], 'source':ref}
                                    if recent:
                                        row_avoid['state'] = s['state']
                                    result['avoid'].append(row_avoid)
                    if 'm4_reviews' in tables:
                        reviewed = con.execute('SELECT evidence_json FROM m4_reviews WHERE sample_id=?', (row['sample_id'],)).fetchone()
                        if reviewed:
                            quality_groups.append(json.loads(reviewed[0]))
                    if 'm4_quality_admissions' in tables:
                        admitted = con.execute('SELECT report_json FROM m4_quality_admissions WHERE sample_id=?', (row['sample_id'],)).fetchone()
                        if admitted:
                            quality_groups.append([json.loads(admitted[0])])
                    result['executions'].append(entry)
                    unresolved = row['status'] in ('reserved','running','interrupted') or row['failure_class'] in ('unknown','interrupted')
                    if unresolved and (not owner_id or owner_id == candidate_id):
                        result['unresolved'].append(entry)
    if model_ledger is not None:
        with model_ledger.connect() as con:
            generation_rows = con.execute("SELECT id,payload,result,created FROM jobs WHERE kind='task-generation' "
                                          "AND state='done' ORDER BY created DESC").fetchall()
            for row in con.execute("""SELECT j.id,j.state,j.payload,json_extract(p.payload,'$.registry') AS registry
                    FROM jobs j LEFT JOIN jobs p ON p.id=json_extract(j.payload,'$.parent_job_id')
                    WHERE j.kind IN ('task-generation','fragment-decision','react-decision','react-native-decision')
                    AND j.state IN ('queued','running','review_required')"""):
                payload = json.loads(row['payload'])
                if scoped:
                    blocks = job_conflicts(model_ledger, site_uri, candidate_id, payload,
                                          running=row['state']=='running', registry=row['registry'])
                else:
                    blocks = not payload.get('site_uri') or host_key(payload['site_uri']) == host
                if blocks:
                    # Only the payload identity enters the advisory context:
                    # payloads embed the full prior prompt, and embedding them
                    # back would compound context growth every round. The
                    # original payload stays in the ledger for audit.
                    result['unresolved'].append({'job_id':row['id'], 'state':row['state'],
                        'category':'UNRESOLVED_REQUEST',
                        'payload_identity':{k: payload.get(k) for k in ('site_uri', 'capability_sha256', 'version', 'generator')}})
            # Rolling generation feedback: the two most recent done rounds keep
            # full responses and frozen tasks; older rounds reduce to counts and
            # compile reasons so the advisory context stays inside the gateway
            # input reservation as rounds accumulate.
            outputs = [json.loads(e[0]) for e in con.execute(
                "SELECT detail FROM batch_events WHERE event='phase_output' ORDER BY seq")]
            for position, row in enumerate(generation_rows):
                payload = json.loads(row['payload'])
                if not (payload.get('site_uri') and host_key(payload['site_uri']) == host_key(site_uri)):
                    continue
                compilation = [e for e in outputs if e.get('job_id') == row['id']]
                if position < 2:
                    # The payload body embeds the previous round's prompt (which
                    # embeds its own context); carrying it verbatim compounds
                    # growth. Keep only its identity keys; the original stays in
                    # the ledger for audit.
                    result['generation'].append({'job_id':row['id'],
                        'payload_identity':{k: payload[k] for k in payload if k in ('site_uri', 'task_id', 'attempt_id', 'decision')},
                        'model_response':json.loads(row['result']) if row['result'] else None,
                        'compilation':compilation,
                        'frozen_tasks':[json.loads(t[0]) for t in con.execute(
                            'SELECT DISTINCT task_json FROM generated_task_index WHERE job_id=?',(row['id'],))]})
                else:
                    result['generation'].append({'job_id':row['id'], 'summary_only':True,
                        'frozen_task_count':con.execute(
                            'SELECT COUNT(DISTINCT task_json) FROM generated_task_index WHERE job_id=?',
                            (row['id'],)).fetchone()[0],
                        'compilation_reasons':[e.get('reason') for e in compilation if e.get('reason')]})
    from .runtime import _bound_quality_report
    from .client_reports import StaleSemanticRules
    for digest, group in {object_sha256(g):g for g in quality_groups}.items():
        # Advisory planning context only: a cached report that merely predates the
        # current semantic rules is dropped with an explicit marker instead of
        # blocking every new round on that site. Review/packaging gates keep
        # rejecting it; nothing here reuses or re-signs the stale PASS.
        try:
            report, binding = _bound_quality_report(group)
        except StaleSemanticRules as error:
            result.setdefault('quality_stale', []).append({'reason': str(error), 'group_sha256': digest})
            continue
        result['quality'].append({'binding':binding, 'report':report})
        # Dataset bytes are verified by the original QC binding gate above.
        for sample in (Path(report['dataset'])/'samples').iterdir():
            for image in sorted((sample/'images').glob('*.png')):
                result['images'].append(reference(image))
    # All bound images are sent; an over-large context must stop at the gateway's
    # configured image/input budget rather than silently omit failure evidence.
    result['images'] = list({r['sha256']:r for r in result['images']}.values())
    from .collection_context import from_registry
    result['collection_facts'] = from_registry(registry, collection_report)
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
