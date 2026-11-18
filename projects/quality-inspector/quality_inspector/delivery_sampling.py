"""Explicit delivery sampling and human escalation; never invents a review.

The default inspector still requires complete review. This separate, opt-in
contract freezes sample slots and random selection. Original failures survive
replacement; unselected samples are admitted by policy, not called AI PASS.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from contextlib import closing
from copy import deepcopy
import csv
import hashlib
from webcollect import workspace_json as json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

from .contract import fingerprint
from .reviews import SEMANTIC, evidence_files, intake, record_hash, sha

VERSION = 'delivery-semantic-sampling-1'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)  # exclusive publication: never overwrite a prior plan
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def _percent(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('Sampling percentages must be finite numbers in [0,100]')
    return value


def count(total, percent):
    return min(total, math.ceil(total * _percent(percent) / 100))


def binding(root):
    root = Path(root).resolve(); annotation = read(root / 'annotation.json')
    sid = annotation['sample_id']
    if not isinstance(sid, str) or not sid or sid != root.name:
        raise ValueError('Sample ID must match its directory')
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Sampling evidence must not contain symlinks')
        if path.is_file(): files[path.relative_to(root).as_posix()] = sha(path)
    return {'sample_id': sid, 'source_path': str(root), 'annotation_sha256': sha(root / 'annotation.json'),
            'evidence_sha256': evidence_files(root), 'files_sha256': files}


def _same_bytes(expected, root):
    actual = binding(root)
    return all(actual[key] == expected[key] for key in
               ('sample_id', 'annotation_sha256', 'evidence_sha256', 'files_sha256'))


def _selection(slots, policy, role, *, random_only=False):
    if role == 'ai' and policy.get('production_sampling'):
        from .production_sampling import selected
        return selected(slots, policy, random_only=random_only)
    groups = {}
    for slot in slots:
        key = slot['site_id'] if policy['stratify'] == 'site' else 'batch'
        groups.setdefault(key, []).append(slot['slot_id'])
    selected = set()
    for key, ids in sorted(groups.items()):
        ranked = sorted(ids, key=lambda sid: (digest([policy['seed'], role, key, sid]), sid))
        selected.update(ranked[:count(len(ids), policy[role + '_percent'])])
    risk=policy.get('risk_selected',{})
    known={slot['slot_id'] for slot in slots}
    if (not isinstance(risk,dict) or set(risk)-known or any(not isinstance(reasons,list) or not reasons
            or any(not isinstance(reason,str) or not reason.strip() for reason in reasons) for reasons in risk.values())):
        raise ValueError('Risk selection must bind actual frozen slots and explicit reasons')
    if role=='ai' and not random_only:selected.update(risk)
    return selected


def _seal(plan):
    plan = deepcopy(plan); plan.pop('plan_sha256', None)
    plan['plan_sha256'] = digest(plan)
    return plan


def freeze(dataset, output, *, ai_percent=100, human_percent=0, seed, stratify='batch', risk_selected=None, production_context=None):
    """Freeze one candidate population; mechanical acceptance remains separate."""
    from .format_checks import run
    root = Path(dataset).resolve(); output = Path(output).resolve()
    if output.is_relative_to(root): raise ValueError('Sampling plan must be outside the customer package')
    if not isinstance(seed, str) or not seed.strip() or stratify not in ('batch', 'site'):
        raise ValueError('An explicit seed and batch/site stratification are required')
    policy = {'ai_percent': _percent(ai_percent), 'human_percent': _percent(human_percent),
              'seed': seed, 'stratify': stratify, 'rounding': 'ceil',
              'replacement_human_required': True}
    if risk_selected is not None:
        policy['risk_selected']=deepcopy(risk_selected)
    formats = run(None, root)
    if not formats['samples']:
        raise ValueError('Cannot freeze an empty candidate population')
    if any(not row.get('confirmed_format_pass') for row in formats['samples']):
        raise ValueError('Every frozen sample must pass deterministic format checks')
    metadata = {}
    if (root / 'metadata.csv').is_file():
        with (root / 'metadata.csv').open(newline='', encoding='utf-8-sig') as stream:
            for row in csv.DictReader(stream):
                if row['sample_id'] in metadata: raise ValueError('Duplicate metadata sample')
                metadata[row['sample_id']] = row.get('site_id')
    slots = []
    for row in sorted(formats['samples'], key=lambda item: item['sample_id']):
        item = binding(row['sample_path']); sid = item['sample_id']; site = metadata.get(sid)
        if not isinstance(site, str) or not site.strip(): raise ValueError('Every frozen sample needs an actual site_id')
        slots.append({'slot_id': sid, 'site_id': site, 'initial': item, 'current': item,
                      'replacement_history': []})
    if production_context is not None:
        if ai_percent != 10 or human_percent != 0:
            raise ValueError('Versioned production policy uses 10% base AI and no new fixed human gate')
        from .production_sampling import attach
        attach(policy, slots, production_context)
    for role in ('ai', 'human'):
        chosen = _selection(slots, policy, role)
        for slot in slots: slot[role + '_selected'] = slot['slot_id'] in chosen
    plan = _seal({'schema_version': VERSION, 'contract_sha256': fingerprint()[1],
                  'implementation_sha256':sha(__file__),
                  'policy': policy, 'original_denominator': len(slots), 'slots': slots,
                  'parent': None, 'revision': 0, 'not_an_actual_review': True})
    write(output, plan)
    return plan


def _source(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path)}


def _records(paths, samples, kind, contract):
    records = {}; errors = []; sources = []
    roots={row['sample_id']:Path(row['sample_path']) for row in samples}
    for path in paths:
        source = _source(path); sources.append(source)
        accepted, invalid, _ = intake(path, samples, contract)
        errors += [dict(row, source=source) for row in invalid]
        for sid, record in accepted.items():
            steps=[step['step_id'] for step in read(roots[sid]/'annotation.json')['steps']]
            viewed=record.get('provenance',{}).get('frames_viewed')
            observations=record.get('step_observations')
            complete=(isinstance(viewed,list) and all(type(item)is int for item in viewed)
                      and len(viewed)==len(steps) and set(viewed)==set(steps)
                      and isinstance(observations,list) and len(observations)==len(steps)
                      and all(isinstance(row,dict) and type(row.get('step_id'))is int for row in observations)
                      and {row['step_id'] for row in observations}==set(steps))
            if record['reviewer']['kind'] != kind:
                errors.append({'sample_id': sid, 'reason': 'Reviewer kind differs from the declared input role', 'source': source})
            elif not complete:
                errors.append({'sample_id':sid,'reason':'Untouched/pending template is not a complete trajectory inspection','source':source})
            elif sid in records:
                errors.append({'sample_id': sid, 'reason': 'Multiple decisions for one sample and role require explicit resolution', 'source': source})
            else:
                records[sid] = {'record': record, 'source': source, 'record_sha256': record_hash(record)}
        if sha(path) != source['sha256']: raise ValueError('Review input changed during evaluation')
    return records, errors, sources


def _status(record):
    if not record: return 'NOT_REVIEWED'
    statuses = [item['status'] for item in record['record']['checks'].values()]
    return 'FAIL' if 'FAIL' in statuses else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in statuses else 'PASS'


def verify(plan_path, dataset=None, _visited=None):
    path = Path(plan_path).resolve(); before = sha(path); plan = read(path)
    visited=set(_visited or ())
    if path in visited:raise ValueError('Cyclic replacement plan lineage')
    visited.add(path)
    unsigned = deepcopy(plan); saved = unsigned.pop('plan_sha256', None)
    if plan.get('schema_version') != VERSION or saved != digest(unsigned):
        raise ValueError('Invalid or changed delivery sampling plan')
    if plan.get('contract_sha256') != fingerprint()[1]: raise ValueError('Sampling contract changed; freeze a new scope')
    if 'sampling_rules_version' in plan:
        raise ValueError('Historical sampling plan carries a retired rules version; freeze a new scope')
    # plan['implementation_sha256'] is provenance recorded at freeze time. The
    # current source changes directly in the no-version mode, so a sealed plan is
    # never re-compared against today's bytes; integrity stays bound by the plan
    # self-hash and the contract fingerprint above.
    policy = plan['policy']; _percent(policy['ai_percent']); _percent(policy['human_percent'])
    if policy.get('production_sampling'):
        from .production_sampling import verify as verify_production
        verify_production(plan)
    if (policy.get('rounding') != 'ceil' or policy.get('replacement_human_required') is not True
            or policy.get('stratify') not in ('batch', 'site') or not isinstance(policy.get('seed'), str) or not policy['seed'].strip()):
        raise ValueError('Invalid frozen sampling policy')
    slots = plan['slots']; ids = [row['slot_id'] for row in slots]
    if (len(ids) != len(set(ids)) or not ids or type(plan['original_denominator'])is not int
            or len(ids) != plan['original_denominator']):
        raise ValueError('Frozen denominator or slot identities changed')
    for role in ('ai', 'human'):
        selected = _selection(slots, policy, role)
        if any(type(slot[role+'_selected'])is not bool or slot[role + '_selected'] != (slot['slot_id'] in selected) for slot in slots):
            raise ValueError('Frozen sampling selection changed')
    parent = plan.get('parent')
    previous = None
    if parent:
        if sha(parent['path']) != parent['sha256']: raise ValueError('Replacement parent plan changed')
        previous = verify(parent['path'], _visited=visited)
        if plan.get('expansion'):
            from .production_sampling import verify_expansion
            verify_expansion(plan, previous)
            previous = None  # Expansion changes selection, never sample slots/replacement history.
        else:
            if (plan['revision'] != previous['revision'] + 1 or policy != previous['policy']
                    or ids != [row['slot_id'] for row in previous['slots']]):
                raise ValueError('Replacement cannot change denominator, policy or frozen slots')
    elif plan.get('revision') != 0 or any(slot['replacement_history'] or slot['initial'] != slot['current'] for slot in slots):
        raise ValueError('Initial sampling plan cannot invent replacement history')
    seen = []
    for slot in slots:
        if slot['slot_id'] != slot['initial']['sample_id']: raise ValueError('Initial slot identity changed')
        history = slot['replacement_history']
        old = slot['initial']
        for event in history:
            if event['from'] != old: raise ValueError('Broken replacement lineage')
            if not _same_bytes(old, old['source_path']): raise ValueError('Original rejected evidence changed')
            proof = event['human_rejection']
            if sha(proof['path']) != proof['sha256']: raise ValueError('Human rejection evidence changed')
            accepted, invalid, _ = intake(proof['path'], [{'sample_id': old['sample_id'], 'sample_path': old['source_path']}], plan['contract_sha256'])
            record = accepted.get(old['sample_id'])
            # Other sample records in a real multi-sample export may be outside
            # this one-slot check; never suppress errors on the rejected sample.
            if (any(row.get('sample_id') in (None, old['sample_id']) for row in invalid)
                    or not record or record['reviewer']['kind'] != 'human'
                    or not any(check['status'] == 'FAIL' for check in record['checks'].values())
                    or record_hash(record) != proof['record_sha256']):
                raise ValueError('Replacement requires actual evidence-bound human FAIL')
            seen.append(old['sample_id']); old = event['to']
        if old != slot['current']: raise ValueError('Replacement current evidence differs from lineage')
        seen.append(old['sample_id'])
    if len(seen) != len(set(seen)): raise ValueError('A sample identity cannot be reused across slots or replacements')
    if previous:
        old_slots = {row['slot_id']: row for row in previous['slots']}
        changed = [row for row in slots if row != old_slots[row['slot_id']]]
        if len(changed) != 1: raise ValueError('Each replacement plan must append exactly one replacement event')
        new = changed[0]; old = old_slots[new['slot_id']]
        if (new['initial'] != old['initial'] or new['site_id'] != old['site_id']
                or new['replacement_history'][:-1] != old['replacement_history']
                or len(new['replacement_history']) != len(old['replacement_history']) + 1):
            raise ValueError('A replacement cannot rewrite prior sample history')
    if dataset is not None:
        root = Path(dataset).resolve(); samples = root / 'samples'
        expected = {row['current']['sample_id'] for row in slots}
        actual = {p.name for p in samples.iterdir() if p.is_dir()}
        if actual != expected: raise ValueError('Current delivery population differs from frozen sampling slots')
        for slot in slots:
            if not _same_bytes(slot['current'], samples / slot['current']['sample_id']):
                raise ValueError('Frozen sample annotation, image or tree bytes changed')
    if sha(path) != before: raise ValueError('Sampling plan changed during verification')
    return plan


def replace(plan_path, rejected_sample, replacement_sample, human_reviews, output, *, reason):
    plan = verify(plan_path)
    target=Path(output).resolve()
    protected=[Path(plan_path).resolve(),Path(human_reviews).resolve()]
    protected += [Path(item['source_path']) for row in plan['slots'] for item in [row['initial'],row['current']]]
    protected.append(Path(replacement_sample).resolve())
    if any(target==path or target.is_relative_to(path) for path in protected):
        raise ValueError('Replacement plan must be outside source plans, reviews and sample evidence')
    if not isinstance(reason, str) or not reason.strip(): raise ValueError('Replacement needs its actual reason')
    matches = [row for row in plan['slots'] if row['current']['sample_id'] == rejected_sample]
    if len(matches) != 1: raise ValueError('Rejected sample is not a current frozen slot')
    slot = matches[0]; old = slot['current']
    if not _same_bytes(old, old['source_path']): raise ValueError('Original rejected sample changed')
    accepted, invalid, _ = intake(human_reviews, [{'sample_id': rejected_sample, 'sample_path': old['source_path']}], plan['contract_sha256'])
    record = accepted.get(rejected_sample)
    if (any(row.get('sample_id') in (None, rejected_sample) for row in invalid) or not record
            or record['reviewer']['kind'] != 'human'
            or not any(check['status'] == 'FAIL' for check in record['checks'].values())):
        raise ValueError('Only a bound human FAIL can request a replacement')
    new = binding(replacement_sample)
    used = {item['sample_id'] for row in plan['slots'] for item in
            [row['initial'], row['current'], *[event['from'] for event in row['replacement_history']]]}
    if new['sample_id'] in used: raise ValueError('Replacement needs a new sample identifier')
    proof = dict(_source(human_reviews), record_sha256=record_hash(record))
    slot['replacement_history'].append({'from': old, 'to': new, 'reason': reason,
                                        'human_rejection': proof})
    slot['current'] = new
    plan['parent'] = _source(plan_path); plan['revision'] += 1; plan = _seal(plan)
    write(output, plan); verify(output)
    return plan


def _post_validation_failure(job,request,candidate,provider):
    """Reproduce a worker protocol rejection without altering settled usage."""
    if 'error' not in job.keys() or not job['error'] or 'response' not in request.keys() or not request['response']:
        raise ValueError('A terminal failed request or verified worker validation failure is required')
    from jsonschema import Draft202012Validator
    from webcollect.model_gateway import parse_content
    from . import ai_worker
    response=json.loads(request['response']);result=response.get('result');raw=response.get('provider_response')
    if not isinstance(raw,dict):raise ValueError('Post-validation failure needs the original provider response')
    parsed,_=parse_content(raw['choices'][0]['message']['content'],provider)
    if parsed!=result:raise ValueError('Stored worker result differs from the original provider reply')
    dispatched=json.loads(request['request_json']);schema=dispatched['schema']
    Draft202012Validator(schema).validate(result)
    actual_steps=[step['step_id'] for step in read(Path(candidate['path'])/'annotation.json')['steps']]
    if job['kind']=='ai-visual':
        ids=schema['properties']['step_observations']['items']['properties']['step_id']['enum']
        validator=ai_worker.validate_review;name='quality_inspector.ai_worker.validate_review'
    else:
        ids=schema['properties']['evidence_steps']['items']['enum']
        validator=ai_worker.validate_difference;name='quality_inspector.ai_worker.validate_difference'
    if (not ids or len(ids)!=len(set(ids)) or not set(ids)<=set(actual_steps)):
        raise ValueError('Worker validator frame scope is not the actual frozen sample')
    try:validator(result,ids)
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        if type(error).__name__!=job['error']:
            raise ValueError('Recorded worker error does not match the reproduced validation rejection') from None
        return {'validator':name,'validator_source_sha256':sha(ai_worker.__file__),
                'error_type':type(error).__name__,'reason':str(error),'frame_ids':ids,
                'original_response_sha256':digest(response),'request_schema_sha256':digest(schema)}
    raise ValueError('A changed job error alone does not prove a worker validation failure')


def _failure_row(con, job_id, request_id, plan):
    job=con.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    request=con.execute('SELECT * FROM model_requests WHERE id=? AND job_id=?',(request_id,job_id)).fetchone()
    if (job is None or request is None or job['kind'] not in ('ai-visual','ai-difference')
            or job['state']!='review_required' or request['state'] not in ('unknown','invalid_response','failed','succeeded')
            or request['started'] is None or not request['request_json']
            or request['finished'] is not None and request['finished']<request['started'] or job['attempts']<1):
        raise ValueError('AI failure needs a terminal failed/unknown/invalid request and review_required worker job')
    recovery=None
    if request['finished'] is None:
        if request['state']!='unknown':raise ValueError('Unfinished model request needs verified unknown-outcome recovery evidence')
        reserved_sequence=None;previous_recovery=0
        for event in con.execute("SELECT seq,event,detail FROM batch_events WHERE event IN ('model_reserved','lease_expired') ORDER BY seq"):
            detail=json.loads(event['detail'])
            if detail.get('job_id')!=job_id:continue
            if event['event']=='model_reserved' and detail.get('request_id')==request_id:
                reserved_sequence=event['seq']
            elif event['event']=='lease_expired':
                unknown=detail.get('unknown_requests')
                recorded=(request_id in unknown) if isinstance(unknown,list) else type(unknown)is int and unknown>0
                if (recorded and reserved_sequence is not None and previous_recovery<reserved_sequence<event['seq']
                        and request['error']=='lease_expired_after_dispatch'):
                    recovery={'sequence':event['seq'],'reservation_sequence':reserved_sequence,
                              'event_sha256':digest(detail),'event':'lease_expired'}
                previous_recovery=event['seq']
        if recovery is None:raise ValueError('Unknown unfinished model request lacks its actual lease recovery event')
    payload=json.loads(job['payload']);candidate=payload.get('candidate',{})
    if payload.get('mode')!='real' or payload.get('contract_sha256')!=plan['contract_sha256']:
        raise ValueError('AI failure job must bind the current real-mode contract')
    matching=[row for row in plan['slots'] if row['current']['annotation_sha256']==candidate.get('annotation_sha256')
              and row['current']['evidence_sha256']==candidate.get('evidence_sha256')]
    if len(matching)!=1:raise ValueError('Failed AI request is not bound to one frozen current sample')
    validation=None
    if request['state']=='succeeded':
        configuration=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
        validation=_post_validation_failure(job,request,candidate,configuration['model']['provider'])
    return {'sample_id':matching[0]['current']['sample_id'],'job_id':job_id,'request_id':request_id,
            'request_state':request['state'],'job_state':job['state'],
            'job_payload_sha256':digest(payload),'request_row_sha256':digest(dict(request)),
            'annotation_sha256':candidate['annotation_sha256'],'evidence_sha256':candidate['evidence_sha256'],
            **({'recovery_event':recovery} if recovery else {}),
            **({'outcome':'CALL_POST_VALIDATION_FAILED','worker_validation_failure':validation} if validation else {})}


def export_failures(plan_path, ledger_path, output):
    """Read actual settled model rows; no dispatch or automatic retry is made."""
    plan=verify(plan_path);ledger=Path(ledger_path).resolve();target=Path(output).resolve()
    if target==ledger or target==Path(plan_path).resolve():raise ValueError('Failure receipt cannot overwrite its inputs')
    for slot in plan['slots']:
        if target.is_relative_to(Path(slot['current']['source_path'])):
            raise ValueError('Failure receipt must be outside frozen sample evidence')
    with closing(workspace_connect(ledger.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
        if config.get('mode')!='real' or not config.get('model') or config['model'].get('provider')=='synthetic':
            raise ValueError('AI failure receipts require an existing real model ledger')
        rows=[]
        for row in con.execute("SELECT r.id,r.job_id,r.state FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE j.state='review_required' AND j.kind IN ('ai-visual','ai-difference') AND r.state IN ('unknown','invalid_response','failed','succeeded') AND (r.finished IS NOT NULL OR r.state='unknown') ORDER BY r.id"):
            job=con.execute('SELECT payload FROM jobs WHERE id=?',(row['job_id'],)).fetchone()
            candidate=json.loads(job['payload']).get('candidate',{})
            if not any(slot['current']['annotation_sha256']==candidate.get('annotation_sha256')
                       and slot['current']['evidence_sha256']==candidate.get('evidence_sha256') for slot in plan['slots']):continue
            try:failure=_failure_row(con,row['job_id'],row['id'],plan)
            except (ValueError,KeyError,TypeError,IndexError):
                if row['state']=='succeeded':continue
                raise
            rows.append(failure)
    if not rows:raise ValueError('No actual failed model requests for the frozen current samples')
    result={'schema_version':VERSION+'-ai-failures','plan_sha256':plan['plan_sha256'],
            'ledger':str(ledger),'ledger_config_sha256':digest(config),'rows':rows,
            'automatic_retries':0,'unknown_fees_remain_unknown':True}
    write(output,result);return result


def _failures(paths, plan):
    by_sample={};sources=[]
    for path in paths:
        source=_source(path);receipt=read(path)
        if receipt.get('schema_version')!=VERSION+'-ai-failures' or receipt.get('plan_sha256')!=plan['plan_sha256']:
            raise ValueError('AI failure receipt differs from current frozen sampling plan')
        ledger=Path(receipt['ledger']).resolve()
        with closing(workspace_connect(ledger.as_uri()+'?mode=ro',uri=True)) as con:
            con.row_factory=sqlite3.Row
            config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
            if (config.get('mode')!='real' or not config.get('model') or config['model'].get('provider')=='synthetic'
                    or digest(config)!=receipt.get('ledger_config_sha256')):
                raise ValueError('AI failure ledger configuration differs or is not real')
            if not receipt.get('rows'):raise ValueError('AI failure receipt is empty')
            seen=set()
            for row in receipt['rows']:
                if row['request_id'] in seen:raise ValueError('Duplicate failure request evidence')
                seen.add(row['request_id'])
                actual=_failure_row(con,row['job_id'],row['request_id'],plan)
                if actual!=row:raise ValueError('AI failure receipt differs from actual model ledger request')
                by_sample.setdefault(row['sample_id'],[]).append(dict(source,job_id=row['job_id'],request_id=row['request_id'],
                    outcome=row.get('outcome','CALL_FAILED')))
        if sha(path)!=source['sha256']:raise ValueError('AI failure receipt changed during validation')
        sources.append(source)
    return by_sample,sources


def evaluate(plan_path, dataset, *, ai_reviews=(), human_reviews=(),ai_failures=()):
    plan_path = Path(plan_path).resolve(); source = _source(plan_path)
    plan = verify(plan_path, dataset)
    samples = [{'sample_id': row['current']['sample_id'],
                'sample_path': str(Path(dataset).resolve() / 'samples' / row['current']['sample_id'])}
               for row in plan['slots']]
    known = {sample['sample_id'] for sample in samples}
    for slot in plan['slots']:
        for item in [slot['initial'], *[event['from'] for event in slot['replacement_history']]]:
            if item['sample_id'] not in known:
                samples.append({'sample_id': item['sample_id'], 'sample_path': item['source_path']})
                known.add(item['sample_id'])
    ai, errors, ai_sources = _records(ai_reviews, samples, 'ai', plan['contract_sha256'])
    ai_errors=list(errors)
    human, invalid, human_sources = _records(human_reviews, samples, 'human', plan['contract_sha256'])
    try:failures,failure_sources=_failures(ai_failures,plan)
    except (sqlite3.Error,IndexError,KeyError) as error:
        raise ValueError('Cannot validate AI failure model-ledger evidence: '+type(error).__name__) from None
    human_errors = invalid; errors += invalid; rows = []; effective = {}
    for slot in plan['slots']:
        sid = slot['current']['sample_id']; ar = ai.get(sid); hr = human.get(sid)
        ast = _status(ar); hst = _status(hr)
        # Any actually supplied AI issue is escalated, even on a randomly
        # unselected sample. Invalid/missing AI decisions on selected samples
        # also enter the human queue rather than being silently accepted.
        invalid_ai=any(error.get('sample_id') in (None,sid) for error in ai_errors)
        failed_call=bool(failures.get(sid));ai_attempted=bool(ar or failed_call)
        human_required = bool(slot['human_selected'] or slot['replacement_history'] or
                              (ar and ast != 'PASS') or invalid_ai or failed_call)
        has_invalid = any(error.get('sample_id') in (None, sid) for error in errors)
        invalid_human = any(error.get('sample_id') in (None, sid) for error in human_errors)
        # Unknown source IDs are input-scope errors, not an AI semantic issue.
        unknown_errors = any(error.get('sample_id') not in known and error.get('sample_id') is not None for error in errors)
        if hst == 'FAIL': status = 'REPLACE_REQUIRED'; admission = 'FAIL'
        elif slot['ai_selected'] and not ai_attempted and (not invalid_ai or hr):
            status='AI_REQUIRED';admission='REVIEW_REQUIRED'
        elif hr and hst == 'PASS' and not invalid_human and not unknown_errors:
            status = 'HUMAN_PASS'; admission = 'PASS'; effective[sid] = hr['record']
        elif human_required or hr or has_invalid or unknown_errors:
            status = 'HUMAN_REQUIRED'; admission = 'REVIEW_REQUIRED'
        elif slot['ai_selected'] or ar:
            status = 'AI_PASS' if ast == 'PASS' else 'HUMAN_REQUIRED'
            admission = 'PASS' if ast == 'PASS' else 'REVIEW_REQUIRED'
            if ast == 'PASS': effective[sid] = ar['record']
        else: status = 'NOT_SELECTED'; admission = 'PASS'
        rows.append({'sample_id': sid, 'slot_id': slot['slot_id'], 'site_id': slot['site_id'],
                     'ai_selected': slot['ai_selected'], 'human_random_selected': slot['human_selected'],
                     'ai_status': ('CALL_POST_VALIDATION_FAILED' if any(row.get('outcome')=='CALL_POST_VALIDATION_FAILED' for row in failures.get(sid,[])) else 'CALL_FAILED') if failed_call else ast if ar or slot['ai_selected'] else 'NOT_SELECTED',
                     'ai_failure_sources':failures.get(sid,[]),
                     'human_status': hst if hr or human_required else 'NOT_SELECTED',
                     'human_required': human_required, 'replacement': bool(slot['replacement_history']),
                     'status': status, 'admission_status': admission,
                     'ai_source': ar['source'] if ar else None, 'human_source': hr['source'] if hr else None,
                     'evidence_sha256': slot['current']['evidence_sha256'],
                     'annotation_sha256': slot['current']['annotation_sha256'],
                     'semantic_review_claimed': status in ('AI_PASS', 'HUMAN_PASS')})
    states = [row['admission_status'] for row in rows]
    status = 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in states else 'PASS'
    if sha(plan_path) != source['sha256']: raise ValueError('Sampling plan changed during assessment')
    result = {'schema_version': VERSION + '-assessment', 'status': status,
              'acceptance_basis': 'explicit-frozen-sampling-policy', 'plan': source,
              'plan_sha256': plan['plan_sha256'], 'contract_sha256': plan['contract_sha256'],
              'policy': plan['policy'], 'original_denominator': plan['original_denominator'],
              'ai_random_selected': len(_selection(plan['slots'],plan['policy'],'ai',random_only=True)),
              'ai_risk_selected':len(plan['policy'].get('risk_selected',{})),
              'ai_actual_selected':sum(row['ai_selected'] for row in rows),
              'human_random_selected': sum(row['human_random_selected'] for row in rows),
              'actual_ai_reviewed': sum(row['sample_id'] in ai for row in rows),
              'actual_human_reviewed': sum(row['sample_id'] in human for row in rows),
              'not_selected': sum(row['status'] == 'NOT_SELECTED' for row in rows),
              'human_pending_count': sum(row['status'] == 'HUMAN_REQUIRED' for row in rows),
              'ai_pending_count':sum(row['status']=='AI_REQUIRED' for row in rows),
              'replacement_required_count': sum(row['status'] == 'REPLACE_REQUIRED' for row in rows),
              'human_queue': [row['sample_id'] for row in rows if row['status'] in ('HUMAN_REQUIRED', 'REPLACE_REQUIRED')],
              'rows': rows, 'review_sources': {'ai': ai_sources, 'human': human_sources}, 'invalid_records': errors,
              'ai_failure_sources':failure_sources,
              'identity_authenticated': False, 'actual_reading_authenticated': False,
              'unselected_semantic_pass_claimed': False}
    if plan['policy'].get('production_sampling'):
        from .production_sampling import evaluate as evaluate_production
        rows, effective, units = evaluate_production(plan, ai, human, failures, errors)
        result.update(rows=rows, quality_units=units, production_policy=plan['policy']['production_sampling']['version'],
            status='REVIEW_REQUIRED' if any(u['status'] != 'ACCEPTED' for u in units.values()) else 'PASS',
            batch_accepted=sum(r['quality_admission']=='ACCEPTED_BY_BATCH_POLICY' for r in rows),
            accepted_ai_pass=sum(r['quality_admission']=='ACCEPTED_BY_BATCH_POLICY' and r['ai_status']=='PASS' for r in rows),
            accepted_not_selected=sum(r['quality_admission']=='ACCEPTED_BY_BATCH_POLICY' and r['ai_status']=='NOT_SELECTED' for r in rows),
            ai_pending_count=sum(r['ai_status']=='REVIEW_REQUIRED' for r in rows), human_pending_count=0,
            replacement_required_count=sum(r['ai_status']=='FAIL' for r in rows), human_queue=[])
    return result, effective


def human_workspace(report_path, output, *, context_path, receipt_path, reviewer_name):
    """Build a blank blind workspace for pending humans, never copy AI verdicts."""
    from .blind import write_workspace
    report_path=Path(report_path).resolve(); report=read(report_path)
    state=report.get('semantic_sampling')
    if not isinstance(state,dict):raise ValueError('A delivery report with an explicit sampling assessment is required')
    ref=state['plan']
    if sha(ref['path'])!=ref['sha256']:raise ValueError('Human queue sampling plan changed')
    sources=state['review_sources']
    for source in sources['ai']+sources['human']:
        if sha(source['path'])!=source['sha256']:raise ValueError('Human queue source review changed')
    current,_=evaluate(ref['path'],report['dataset'],ai_reviews=[r['path'] for r in sources['ai']],
                       human_reviews=[r['path'] for r in sources['human']],
                       ai_failures=[r['path'] for r in state.get('ai_failure_sources',[])])
    if current!=state:raise ValueError('Human queue differs from current bound evidence')
    selected={row['sample_id'] for row in current['rows'] if row['status']=='HUMAN_REQUIRED'}
    if not selected:raise ValueError('No pending human samples; rejected samples need replacement, not a second vote')
    subset=deepcopy(report);subset['samples']=[row for row in report['samples'] if row['sample_id'] in selected]
    if {row['sample_id'] for row in subset['samples']}!=selected:raise ValueError('Human queue samples are missing')
    subset['sample_count']=len(selected)
    subset['human_queue_source']={'report':_source(report_path),'selected_sample_ids':sorted(selected),
                                  'not_a_new_qc_run':True,'not_a_human_decision':True}
    receipt_path=Path(receipt_path).resolve()
    derived=receipt_path.with_name(receipt_path.stem+'-queue-source.json')
    dataset=Path(report['dataset']).resolve();output=Path(output).resolve()
    if (derived.is_relative_to(dataset) or derived.is_relative_to(output)
            or output.exists() or receipt_path.exists()):
        raise ValueError('Use new human workspace/receipt paths outside inspected samples')
    write(derived,subset)
    result=write_workspace(derived,output,context_path=context_path,receipt_path=receipt_path,reviewer_name=reviewer_name)
    return {'sample_count':len(selected),'selected_sample_ids':sorted(selected),'workspace':str(output),
            'receipt':str(receipt_path),'source_report':_source(report_path),'human_reviews_created':0,
            'data_id':result['data_id']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--input', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ai-percent', type=float, default=100); p.add_argument('--human-percent', type=float, default=0)
    p.add_argument('--seed', required=True); p.add_argument('--stratify', choices=('batch', 'site'), default='batch')
    p = sub.add_parser('status'); p.add_argument('--plan', type=Path, required=True); p.add_argument('--input', type=Path, required=True)
    p.add_argument('--ai-reviews', type=Path, action='append', default=[]); p.add_argument('--human-reviews', type=Path, action='append', default=[])
    p.add_argument('--ai-failures',type=Path,action='append',default=[])
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('replace'); p.add_argument('--plan', type=Path, required=True); p.add_argument('--sample-id', required=True)
    p.add_argument('--replacement', type=Path, required=True); p.add_argument('--human-reviews', type=Path, required=True)
    p.add_argument('--reason', required=True); p.add_argument('--output', type=Path, required=True)
    p=sub.add_parser('human-workspace');p.add_argument('--report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--context',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True);p.add_argument('--reviewer',required=True)
    p=sub.add_parser('export-ai-failures');p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--ledger',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            value = freeze(args.input, args.output, ai_percent=args.ai_percent, human_percent=args.human_percent, seed=args.seed, stratify=args.stratify)
            summary = {'plan': str(args.output), 'original_denominator': value['original_denominator'], 'model_requests': 0}
        elif args.command == 'replace':
            value = replace(args.plan, args.sample_id, args.replacement, args.human_reviews, args.output, reason=args.reason)
            summary = {'plan': str(args.output), 'revision': value['revision'], 'human_reinspection_required': True}
        elif args.command=='human-workspace':
            summary=human_workspace(args.report,args.output,context_path=args.context,
                                    receipt_path=args.receipt,reviewer_name=args.reviewer)
        elif args.command=='export-ai-failures':
            value=export_failures(args.plan,args.ledger,args.output)
            summary={'output':str(args.output),'failed_model_requests':len(value['rows']),'new_model_requests':0}
        else:
            if args.output.resolve().is_relative_to(args.input.resolve()):
                raise ValueError('Sampling reports must be outside the inspected package')
            value, _ = evaluate(args.plan, args.input, ai_reviews=args.ai_reviews, human_reviews=args.human_reviews,ai_failures=args.ai_failures)
            write(args.output, value); summary = {key: value[key] for key in
                ('status', 'original_denominator', 'actual_ai_reviewed', 'actual_human_reviewed', 'human_pending_count', 'replacement_required_count')}
        print(json.dumps(summary, ensure_ascii=False)); return 0
    except (OSError, ValueError, KeyError, TypeError,sqlite3.Error) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, ensure_ascii=False)); return 1


if __name__ == '__main__': raise SystemExit(main())
