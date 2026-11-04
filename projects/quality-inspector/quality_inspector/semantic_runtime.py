"""Ledger-local semantic reuse, including sticky uncertain/failed attempts.

The immutable original job stays the source. A new pipeline/package may obtain
an alias result, but cannot dispatch the same check again. A process lock spans
lookup and dispatch so concurrent aliases cannot both spend a request.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
from webcollect.batch_core import BudgetStop

from .semantic import digest, sample_identity

VISUAL_CHECKS = ('visual_alignment', 'terminal_semantics', 'language', 'privacy')


class SemanticBusy(BudgetStop):
    """Another worker owns this evidence; keep the alias queued without dispatch."""


def _sample(value):
    # Only new explicitly identified snapshots are eligible for automatic reuse.
    return sample_identity(value)


def subject(kind, payload):
    if kind == 'ai-documents':
        return {'payload': payload['payload_files_sha256'],
                'profile': payload['template']['profile_sha256'],
                'supporting': sorted(item['sha256'] for item in payload.get(
                    'supplementary_evidence', {}).get('supporting_run_files_outside_customer_payload', []))}
    value = {'sample': _sample(payload['candidate'])}
    if kind == 'ai-difference':
        value['neighbors'] = [_sample(item) for item in payload['neighbors']]
        value['pending_collection_checks'] = payload.get('pending_collection_checks', [])
        value['required_history_missing'] = payload.get('required_history_missing', [])
        if payload.get('difference_protocol'):
            value['difference_protocol'] = payload['difference_protocol']
    return value


def names(kind):
    return VISUAL_CHECKS if kind == 'ai-visual' else ('substantive_difference',) if kind == 'ai-difference' else ('documents',)


def rules(kind, payload):
    if kind == 'ai-documents':
        return {'documents': payload['prompt_version']}
    return payload.get('semantic_rule_ids', {})


@contextmanager
def guard(ledger, job):
    key = digest({'kind': job['kind'], 'subject': subject(job['kind'], job['payload'])})
    path = ledger.path.with_name(ledger.path.name + '.semantic-' + key + '.lock')
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SemanticBusy('Exact semantic evidence is already being inspected; no duplicate dispatch') from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def lookup(ledger, job):
    kind = job['kind']; payload = job['payload']; expected = subject(kind, payload)
    current_rules = rules(kind, payload); cached = {}; sources = {}; blocked = set(); observations = None
    with ledger.connect() as con:
        rows = con.execute('SELECT id,payload,result,state FROM jobs WHERE kind=? AND id<>? ORDER BY created,id',
                           (kind, job['id'])).fetchall()
        bound = {value['job_id']:value['result_sha256'] for (raw,) in con.execute(
            "SELECT detail FROM batch_events WHERE event='semantic_result_bound'") for value in [json.loads(raw)]}
    for row in rows:
        old = json.loads(row['payload'])
        if (old.get('model') != payload.get('model') or old.get('mode') != payload.get('mode')
                or old.get('prompt_version') != payload.get('prompt_version')):
            continue
        try:
            if subject(kind, old) != expected:
                continue
        except (KeyError, TypeError):
            continue  # Legacy jobs lack explicit sample/rule identity.
        matches = [name for name in names(kind) if name in current_rules
                   and rules(kind, old).get(name) == current_rules[name]]
        if not matches:
            continue
        if row['id'] != digest({'kind': kind, 'payload': old}):
            raise ValueError('Semantic source job payload identity changed')
        if row['state'] in ('running', 'review_required', 'failed'):
            blocked.add(row['id']); continue
        if row['state'] != 'done' or not row['result']:
            continue
        result = json.loads(row['result'])
        if bound.get(row['id'])!=digest(result):
            raise ValueError('Completed semantic source result has changed or lacks its original binding')
        for name in matches:
            value = result.get('checks', {}).get(name) if kind == 'ai-visual' else result
            if not isinstance(value, dict) or value.get('status') not in ('PASS', 'FAIL', 'REVIEW_REQUIRED'):
                # Documentary results are a complete bound review, not a status.
                if kind != 'ai-documents' or not isinstance(value, dict) or 'checks' not in value:
                    raise ValueError('Malformed completed semantic source result')
            if name not in cached:
                cached[name] = deepcopy(value); sources[name] = row['id']
                observations = observations or deepcopy(result.get('step_observations'))
    return cached, sources, sorted(blocked), observations


def record(ledger, job, sources, *, blocked=False):
    if not sources:
        return
    with ledger.transaction() as con:
        ledger.event(con, 'semantic_reuse_blocked' if blocked else 'semantic_reused', {
            'job_id': job['id'], 'source_jobs': sorted(set(sources)),
            'reason': 'prior_exact_attempt_unresolved_no_resend' if blocked else 'same_sample_evidence_and_relevant_rules'})


def bind_result(ledger,job,result):
    with ledger.transaction() as con:
        ledger.event(con,'semantic_result_bound',{'job_id':job['id'],'result_sha256':digest(result),
            'subject_sha256':digest(subject(job['kind'],job['payload']))})


def failure_jobs(ledger, current_jobs):
    """Trace alias failures to the actual original billed/unknown request rows."""
    result = set(current_jobs)
    with ledger.connect() as con:
        events = [json.loads(row[0]) for row in con.execute(
            "SELECT detail FROM batch_events WHERE event='semantic_reuse_blocked'")]
    changed = True
    while changed:
        before = len(result)
        for event in events:
            if event.get('job_id') in result:
                result.update(event.get('source_jobs', []))
        changed = len(result) != before
    return result
