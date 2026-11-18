"""Ledger-local semantic reuse, including sticky uncertain/failed attempts.

The immutable original job stays the source. A new pipeline/package may obtain
an alias result, but cannot dispatch the same check again. A process lock spans
lookup and dispatch so concurrent aliases cannot both spend a request.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
from webcollect import workspace_json as json
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



def bind_result(ledger,job,result):
    with ledger.transaction() as con:
        ledger.event(con,'semantic_result_bound',{'job_id':job['id'],'result_sha256':digest(result),
            'subject_sha256':digest(subject(job['kind'],job['payload']))})



