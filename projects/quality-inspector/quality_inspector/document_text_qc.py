"""Auditable AI-only documentary consistency lane linked to an issued sample QC.

Existing pipeline receipts and their software, jobs, failures, human decisions
and charges remain immutable. This policy amendment changes document routing,
not sample review or formal delivery requirements. No trajectory is collected.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from webcollect.batch_core import BatchLedger, BudgetStop
from webcollect.model_gateway import ModelGateway
from . import ai_worker, delivery_pipeline as pipeline, delivery_sampling
from .engine import inspect
from .profiles import DELIVERY_DOCUMENT_CHECKS, package_files
from .reporting import write_outputs

VERSION = 'document-text-qc-1'
KIND = 'ai-document-text-consistency'
POLICY = {
    'version': VERSION,
    'document_review': 'engineering-text-comparison-plus-ai-text-consistency',
    'document_human_percent': 0,
    'document_ai_percent': 100,
    'ai_fail_route': 'REVISE_DOCUMENTS_REQUIRED',
    'ai_unknown_route': 'AI_REVIEW_REQUIRED',
    'sample_human_policy': 'unchanged-original-frozen-sampling-plan',
    'formal_delivery_requirements': 'unchanged-original-profile-and-engine',
    'historical_export_stub': 'stage-specific-history-not-a-claim-of-current-final-approval',
}


def _read(path): return pipeline._read(path)
def _ref(path): return pipeline._ref(path)
def _digest(value): return pipeline._digest(value)
def _write(path, value): delivery_sampling.write(path, value)


def _implementation():
    return {**pipeline._implementation(), str(Path(__file__).resolve()): pipeline._sha(__file__)}


def _stable(value):
    """Canonical facts retain hashes, removing only relocatable evidence paths.

    Exact original files are separately frozen in the amendment receipt. A new
    status output directory or elapsed timer must not buy a repeated AI call.
    """
    if isinstance(value, list): return [_stable(item) for item in value]
    if not isinstance(value, dict): return value
    return {key: ({'sha256': pipeline._sha(item), 'location': 'frozen-separately-in-receipt'}
                  if key == 'source' and isinstance(item, str) and item.startswith('/') and Path(item).is_file()
                  else _stable(item)) for key, item in value.items()
            if not (key == 'path' and 'sha256' in value)}


def _parent(receipt_path, status_path):
    receipt = pipeline.verify(receipt_path)
    ledger = pipeline._ledger(receipt)
    state = _read(status_path)
    history = pipeline._human_history_hash(ledger, receipt)
    pipeline._verify_issued_status(ledger, receipt_path, _ref(status_path), state.get('human_history_sha256'))
    if state.get('receipt') != _ref(receipt_path) or state.get('human_history_sha256') != history:
        raise ValueError('Parent status receipt/human history is stale or mismatched')
    refs = [state['report'], state['review_file'], state['worker_review_file'],
            *state['human_reviews'], *state['human_input_sources'], *state['ai_failure_sources']]
    for reference in refs: pipeline._check_ref(reference)
    current = inspect(None, receipt['dataset'], profile=receipt['profile']['path'],
        reviews=state['review_file']['path'], inspection_stage='payload',
        delivery_sampling_plan=receipt['plan']['path'],
        human_reviews=[ref['path'] for ref in state['human_reviews']],
        ai_failures=[ref['path'] for ref in state['ai_failure_sources']])
    saved = _read(state['report']['path'])
    for key in ('semantic_sampling', 'input_files_sha256', 'delivery_document_review', 'delivery_status'):
        if current.get(key) != saved.get(key): raise ValueError('Issued parent QC no longer reproduces')
    for key in ('actual_ai_reviewed', 'actual_human_reviewed', 'ai_pending_count',
                'human_pending_count', 'replacement_required_count'):
        if state.get(key) != current['semantic_sampling'][key]:
            raise ValueError('Parent sample counts do not match reproduced QC')
    if state.get('payload_status') != current['delivery_status']:
        raise ValueError('Parent payload status does not match reproduced QC')
    return receipt, ledger, state, current


def _request(value):
    # Reuse the exact five-check payload citation schema, not its legacy prompt.
    _, schema = ai_worker._document_request(value)
    text = json.dumps({
        'instruction':
            '你是专用资料文本核对员。仅比较完整交付资料、结构化文本与已核验的真实运行事实。'
            '五项检查判断声明是否准确、完整、互相一致；引用给定的包内path/sha256。'
            '资料中的历史提示词、规划值和示例不是本次实际统计；历史导出qc_report尚未执行的说明'
            '不是对后来包外质检结果的否认，不要求回写不可变原包。'
            '当前已执行的样本AI和真人结论以verified_current_evidence为准。'
            '保留原AI FAIL和后续HUMAN_PASS，不能把真人复核说成AI通过；不能重新裁决样本视觉或语义、'
            '要求重看截图或要求真人再次审核。此lane不接收图片，不能声称审核像素。'
            '如实写明单站试跑类目100%、尚未正式放行，与事实一致可以文本PASS；'
            '类目上限20%等正式门禁由原engine单独保留FAIL，文本PASS不得宣称正式交付或客户验收。'
            '资料AI失败只进入资料修订/AI复核，不进入人工队列。'
            '真实矛盾为FAIL；缺少判断所需事实为REVIEW_REQUIRED；不得补造事实或虚构PASS。'
            '资料核对自身尚未完成不构成循环缺证，按本次请求开始前的实际阶段核对声明。',
        'policy': POLICY, 'required_checks': DELIVERY_DOCUMENT_CHECKS,
        'documents': value['documents'],
        'document_files_sha256': {key: value['payload_files_sha256'][key] for key in value['documents']},
        'supplementary_evidence': value['supplementary_evidence'],
        'documentary_material_sha256': value['documentary_material_sha256'],
    }, ensure_ascii=False, sort_keys=True)
    return text, schema


def _parent_jobs(ledger, receipt):
    return {jid: {'kind': ledger.get(jid)['kind'], 'state': ledger.get(jid)['state'],
                  'result_sha256': _digest(ledger.get(jid)['result'])}
            for jid in receipt['jobs']}


def _mechanical(dataset, report):
    """Compare explicitly declared README statistics, never arbitrary prose numbers."""
    dataset = Path(dataset)
    expected = {key: report['statistics'][key] for key in
                ('sample_count', 'site_count', 'site_sample_counts', 'categories', 'task_types', 'step_counts')}
    annotations = [_read(path) for path in sorted(dataset.glob('samples/*/annotation.json'))]
    expected['frames'] = sum(len(row['steps']) for row in annotations)
    expected['actions'] = dict(Counter(step['action']['action_type'] for row in annotations for step in row['steps']))
    formats = ai_worker.format_run(None, dataset)
    expected['effective_step_counts'] = dict(Counter(str(row['effective_steps']) for row in formats['samples']))
    expected = json.loads(json.dumps(expected))
    comparisons = []
    # Only README's explicit structured statistical declarations are compared.
    # Planning prompts and example JSON in other files are not actual claims.
    for index, text in enumerate(re.findall(r'```json\s*\n(.*?)\n```', (dataset / 'README.md').read_text(), re.S)):
        try: declared = json.loads(text)
        except ValueError: continue  # Original document-content/AI gates handle prose and malformed examples.
        if not isinstance(declared, dict) or not set(declared).intersection(expected): continue
        for key, actual in expected.items():
            if key in declared:
                comparisons.append({'source': 'README.md', 'block': index, 'field': key,
                    'declared': declared[key], 'actual': actual,
                    'status': 'PASS' if _digest(declared[key]) == _digest(actual) else 'FAIL'})
    return {'schema_version': VERSION + '-engineering-text-comparison',
            'status': 'FAIL' if any(row['status'] == 'FAIL' for row in comparisons) else 'PASS',
            'comparison_scope': 'explicit README structured statistics versus current package/annotations/format engine',
            'comparisons': comparisons, 'actual_statistics': expected,
            'free_text_and_compliance_claims': 'AI_REVIEW_REQUIRED'}


def _materials(receipt, old_ledger, state, report, ledger, supporting_files):
    # The complete legacy text snapshot is reused as source material only; its
    # already charged result and original five decisions remain in provenance.
    value = deepcopy(old_ledger.get(receipt['document_job'])['payload'])
    value.pop('delivery_pipeline_binding', None)
    ai_worker._verify_document_materials(value)
    existing = value['supplementary_evidence']['supporting_run_files_outside_customer_payload']
    for path in supporting_files:
        item = ai_worker._supporting_document(path, Path(receipt['dataset']))
        if not any(row['path'] == item['path'] for row in existing): existing.append(item)
    existing.sort(key=lambda item: (item['path'], item['sha256']))
    value['supplementary_evidence']['verified_current_evidence'] = {
        'authentication': 'original-issued-status-and-reproduced-engine-QC-and-current-human-history',
        'parent_receipt_sha256': receipt['receipt_sha256'],
        'human_history_sha256': state['human_history_sha256'],
        'sample_qc': _stable(report),
        'engineering_text_comparison': _mechanical(receipt['dataset'], report),
        'original_worker_review': _read(state['worker_review_file']['path']),
        'actual_current_human_reviews': [_read(ref['path']) for ref in state['human_reviews']],
        'original_human_input_exports': [_read(ref['path']) for ref in state['human_input_sources']],
        'frozen_sampling_plan': _read(receipt['plan']['path']),
        'original_bound_model_usage': pipeline._usage(old_ledger, receipt),
        'policy_amendment': POLICY,
        'formal_release_ready': False,
        'customer_acceptance': 'UNKNOWN',
    }
    value['supplementary_evidence']['review_boundaries'].update(
        human_review_status='SEE_AUTHENTICATED_CURRENT_SAMPLE_QC',
        formal_release_status='NOT_CLEARED_BY_DOCUMENT_TEXT_QC')
    value['model'] = ledger.config['model']
    value['documentary_material_sha256'] = ai_worker._document_material_sha(value)
    value['document_text_policy'] = POLICY
    value['implementation_sha256'] = _implementation()
    value['parent_binding'] = {'receipt_sha256': receipt['receipt_sha256'],
                               'human_history_sha256': state['human_history_sha256']}
    if not ledger.config.get('model'):
        raise ValueError('Documentary model review requires an explicit model')
    return value


def _semantic_request(value):
    text, schema = _request(value)
    return _digest({'policy': POLICY, 'text': text, 'schema': schema,
        'model': {key: value['model'][key] for key in ('provider', 'model', 'endpoint') if key in value['model']}})


def _linked_event(ledger, value):
    with ledger.connect() as con:
        return [json.loads(row['detail']) for row in con.execute(
            "SELECT detail FROM batch_events WHERE event='document_text_policy_amendment'")
            if json.loads(row['detail']).get('cache_key') == value]


def prepare(ledger, parent_receipt, parent_status, output, *, supporting_files=()):
    """Freeze one complete text request in a separate bounded, linked ledger."""
    with pipeline._lock(parent_receipt):
        receipt, old, state, report = _parent(parent_receipt, parent_status)
        pipeline._mode(ledger, receipt['mode'])
        if ledger.path == old.path: raise ValueError('Document amendment requires a separate bounded ledger; never reset the parent budget')
        if any(ledger.path.is_relative_to(root) for root in pipeline._roots(receipt)):
            raise ValueError('Document ledger must be outside all inspected packages')
        if any(old.get(jid)['state'] in ('queued', 'running') for jid in receipt['jobs'] if jid != receipt['document_job']):
            raise ValueError('Finish original visual/difference jobs using run-samples before document preparation')
        output = pipeline._external(output, pipeline._roots(receipt), [parent_receipt, parent_status, *supporting_files])
        value = _materials(receipt, old, state, report, ledger, supporting_files)
        cache_key = _digest({'kind': KIND, 'payload': value})
        semantic_request = _semantic_request(value)
        link = {'schema_version': VERSION + '-amendment', 'cache_key': cache_key,
            'semantic_request_sha256': semantic_request,
            'parent_receipt': _ref(parent_receipt), 'parent_status': _ref(parent_status),
            'human_history_sha256': state['human_history_sha256'], 'policy': POLICY,
            'ledger': str(ledger.path), 'ledger_config_sha256': _digest(ledger.config),
            'job_id': cache_key, 'original_bound_model_usage': pipeline._usage(old, receipt),
            'old_document_job': receipt['document_job'], 'old_document_result_preserved': True}
        with pipeline._human_gate(old), old.transaction() as con:
            if pipeline._human_history_hash(old, receipt, connection=con) != state['human_history_sha256']:
                raise ValueError('Human history changed before document amendment')
            linked = [json.loads(row['detail']) for row in con.execute(
                "SELECT detail FROM batch_events WHERE event='document_text_policy_amendment'")
                if json.loads(row['detail']).get('cache_key') == cache_key
                or json.loads(row['detail']).get('semantic_request_sha256') == semantic_request]
            if any(row['ledger'] != str(ledger.path) or row['ledger_config_sha256'] != _digest(ledger.config)
                   or row['job_id'] != cache_key for row in linked):
                raise ValueError('Identical documentary request is already linked to another ledger; resume it without duplicate charging')
            if not linked: old.event(con, 'document_text_policy_amendment', link)
        jid = ledger.enqueue(KIND, value)
        if jid != cache_key: raise ValueError('Document cache identity mismatch')
        output.mkdir(parents=True, exist_ok=False)
        refs = [_ref(parent_status), state['report'], state['worker_review_file'], state['review_file'],
                *state['human_reviews'], *state['human_input_sources'], *state['ai_failure_sources'],
                receipt['plan'], receipt['profile'], receipt['effective_set'], *receipt['supporting_files'],
                *[_ref(path) for path in supporting_files]]
        unique = {row['path']: row for row in refs}
        result = {'schema_version': VERSION, 'policy': POLICY, 'parent_receipt': _ref(parent_receipt),
            'parent_status': _ref(parent_status), 'human_history_sha256': state['human_history_sha256'],
            'evidence_refs': list(unique.values()), 'parent_jobs': _parent_jobs(old, receipt),
            'original_bound_model_usage': pipeline._usage(old, receipt),
            'ledger': str(ledger.path), 'ledger_config_sha256': _digest(ledger.config),
            'mode': receipt['mode'], 'job_id': jid, 'payload_sha256': _digest(value),
            'semantic_request_sha256': semantic_request,
            'documentary_material_sha256': value['documentary_material_sha256'],
            'implementation_sha256': _implementation(), 'human_document_pending_count': 0,
            'release_ready': False}
        result['receipt_sha256'] = _digest(result)
        _write(output / 'document-text-receipt.json', result)
        verify(output / 'document-text-receipt.json')
        return {'receipt': str(output / 'document-text-receipt.json'), 'job_id': jid,
                'external_model_requests_created': 0, 'human_document_pending_count': 0,
                'original_bound_model_usage': result['original_bound_model_usage']}


def verify(receipt_path):
    value = _read(receipt_path)
    if value.get('schema_version') != VERSION or value.get('receipt_sha256') != _digest(
            {key: item for key, item in value.items() if key != 'receipt_sha256'}):
        raise ValueError('Document amendment receipt changed')
    if value.get('policy') != POLICY or value['implementation_sha256'] != _implementation():
        raise ValueError('Document policy/software changed; preserve receipt and prepare a new explicit version')
    pipeline._check_ref(value['parent_receipt'])
    receipt, old, state, _ = _parent(value['parent_receipt']['path'], value['parent_status']['path'])
    for ref in value['evidence_refs']: pipeline._check_ref(ref)
    if value['human_history_sha256'] != state['human_history_sha256']:
        raise ValueError('Document amendment human history is stale')
    if value['parent_jobs'] != _parent_jobs(old, receipt) or value['original_bound_model_usage'] != pipeline._usage(old, receipt):
        raise ValueError('Parent jobs/results/charges changed after document preparation')
    ledger = pipeline._ledger(value)
    pipeline._mode(ledger, value['mode'])
    job = ledger.get(value['job_id'])
    if job['kind'] != KIND or _digest(job['payload']) != value['payload_sha256']:
        raise ValueError('Document job identity/payload changed')
    if _digest({'kind': KIND, 'payload': job['payload']}) != value['job_id']:
        raise ValueError('Document job hash changed')
    if _semantic_request(job['payload']) != value['semantic_request_sha256']:
        raise ValueError('Document semantic request changed')
    ai_worker._verify_document_materials(job['payload'])
    if not any(row['ledger'] == str(ledger.path) and row['ledger_config_sha256'] == value['ledger_config_sha256']
               for row in _linked_event(old, value['job_id'])):
        raise ValueError('Document job lacks original-ledger policy amendment')
    return value


def _response(job, ledger, gateway):
    value = job['payload']; actual = ai_worker._verify_document_materials(value)
    text, schema = _request(value)
    first = next(iter(value['documents']))
    blank = {'checks': {name: {'status': 'REVIEW_REQUIRED', 'note': 'SYNTHETIC protocol; no actual documentary AI approval',
        'evidence': [{'path': first, 'sha256': actual[first], 'detail': 'SYNTHETIC fixture'}]} for name in DELIVERY_DOCUMENT_CHECKS}}
    result = gateway.call(job, 'document-text-consistency', text, schema, attempts=1, synthetic_response=blank)
    Draft202012Validator(schema).validate(result)
    ai_worker._verify_document_materials(value)
    for check in result['checks'].values():
        if not check['note'].strip() or check['status'] != 'REVIEW_REQUIRED' and not check['evidence']:
            raise ValueError('Document decisions require actual notes and bound evidence')
        for ref in check['evidence']:
            if actual.get(ref['path']) != ref['sha256'] or not ref['detail'].strip():
                raise ValueError('Document citation is unbound or empty')
    return {**value['template'], 'reviewer': {'kind': 'ai' if ledger.config['mode'] == 'real' else 'synthetic',
            'name': ledger.config['model']['model']},
        'provenance': {'description': VERSION + '; actual text-only bounded model job=' + job['id'] +
            '; complete documentary material SHA256=' + value['documentary_material_sha256']},
        'checks': result['checks']}


def _check_result(ledger, job, mode):
    if job['state'] != 'done' or mode != 'real': return None
    checks = job['result']['checks']
    expected = {**job['payload']['template'], 'reviewer': {'kind': 'ai', 'name': ledger.config['model']['model']},
        'provenance': {'description': VERSION + '; actual text-only bounded model job=' + job['id'] +
            '; complete documentary material SHA256=' + job['payload']['documentary_material_sha256']},
        'checks': checks}
    if job['result'] != expected:
        raise ValueError('Document result actor/template/provenance changed after the model call')
    _, schema = _request(job['payload']); Draft202012Validator(schema).validate({'checks': checks})
    with ledger.connect() as con:
        requests = [dict(row) for row in con.execute('SELECT * FROM model_requests WHERE job_id=? ORDER BY started', (job['id'],))]
    if not any(row['state'] == 'succeeded' and row['response'] and json.loads(row['response']).get('result') == {'checks': checks}
               for row in requests):
        raise ValueError('Document approval has no matching successful persisted model response')
    return job['result']


def status(receipt_path, output):
    value = verify(receipt_path)
    parent_path = value['parent_receipt']['path']
    with pipeline._lock(parent_path):
        receipt, old, state, parent_report = _parent(parent_path, value['parent_status']['path'])
        ledger = pipeline._ledger(value); job = ledger.get(value['job_id'])
        output = pipeline._external(output, pipeline._roots(receipt), [receipt_path, parent_path])
        output.mkdir(parents=True, exist_ok=False)
        document = _check_result(ledger, job, value['mode'])
        mechanical = _mechanical(receipt['dataset'], parent_report)
        reviews = _read(state['worker_review_file']['path'])
        original = deepcopy(reviews.get('delivery_document_review'))
        reviews.pop('delivery_document_review', None)
        if document is not None: reviews['delivery_document_review'] = document
        reviews['document_policy_amendment'] = {'policy': POLICY,
            'receipt': _ref(receipt_path), 'original_worker_review': state['worker_review_file'],
            'original_document_review': original, 'original_sample_decisions_retained': True,
            'original_human_history_sha256': state['human_history_sha256']}
        review_path = output / 'effective-reviews.json'
        _write(review_path, reviews)
        effective_reviews = review_path if value['mode'] == 'real' else None
        report = inspect(None, receipt['dataset'], profile=receipt['profile']['path'], reviews=effective_reviews,
            inspection_stage='payload', delivery_sampling_plan=receipt['plan']['path'],
            human_reviews=[ref['path'] for ref in state['human_reviews']],
            ai_failures=[ref['path'] for ref in state['ai_failure_sources']])
        write_outputs(report, output / 'payload-qc')
        text_status = ('FAIL' if mechanical['status'] == 'FAIL' else
                       report['delivery_document_review']['status'] if document is not None else 'REVIEW_REQUIRED')
        doc_state = ('AI_PASS' if text_status == 'PASS' else 'REVISE_DOCUMENTS_REQUIRED'
                     if text_status == 'FAIL' else 'AI_REVIEW_REQUIRED')
        checks = [row for row in report['dataset_checks'] if row['status'] != 'PASS']
        sampling = report['semantic_sampling']
        summary = {**state, 'schema_version': VERSION + '-status',
            'document_text_receipt': _ref(receipt_path), 'parent_status': value['parent_status'],
            'payload_status': 'FAIL' if mechanical['status'] == 'FAIL' else report['delivery_status'],
            'report': _ref(output / 'payload-qc/report.json'),
            'review_file': _ref(review_path), 'worker_review_file': state['worker_review_file'],
            'human_document_pending_count': 0, 'document_review_status': doc_state,
            'text_consistency': {'status': text_status, 'route': doc_state, 'human_pending_count': 0,
                'job_state': job['state'], 'document_review': document, 'engineering_text_comparison': mechanical},
            'formal_blockers': {'delivery_status': 'FAIL' if mechanical['status'] == 'FAIL' else report['delivery_status'],
                'engineering_text_comparison': mechanical, 'dataset_checks': checks,
                'sample_status_counts': report.get('sample_status_counts'),
                'sample_human_pending_count': sampling['human_pending_count'],
                'sample_replacement_required_count': sampling['replacement_required_count']},
            'original_bound_model_usage': value['original_bound_model_usage'],
            'document_model_usage': pipeline._usage(ledger, {'jobs': {value['job_id']: {}}, 'mode': value['mode']}),
            'document_model_budget': ledger.summary(), 'release_ready': False,
            'customer_acceptance': 'UNKNOWN'}
        for key in ('actual_ai_reviewed', 'actual_human_reviewed', 'ai_pending_count', 'human_pending_count', 'replacement_required_count'):
            summary[key] = sampling[key]
        verify(receipt_path)
        _write(output / 'status.json', summary)
        pipeline._issue_status(old, parent_path, receipt, output / 'status.json', state['human_history_sha256'])
        with ledger.transaction() as con:
            ledger.event(con, 'document_text_status_issued', {'receipt': _ref(receipt_path), 'status': _ref(output / 'status.json')})
        return summary


def run(receipt_path, output):
    value = verify(receipt_path); ledger = pipeline._ledger(value)
    parent = pipeline.verify(value['parent_receipt']['path'])
    pipeline._external(output, pipeline._roots(parent), [receipt_path])
    bound = pipeline._BoundLedger(ledger, {}, allowed={value['job_id']: {'payload_sha256': value['payload_sha256']}},
                                  validate=lambda: verify(receipt_path))
    job = bound.claim(KIND, job_id=value['job_id'])
    if job:
        try:
            comparison = job['payload']['supplementary_evidence']['verified_current_evidence']['engineering_text_comparison']
            if comparison['status'] == 'FAIL':
                bound.finish(job, 'review_required', error='mechanical_text_contradiction')
            else: bound.finish(job, result=_response(job, bound, ModelGateway(bound)))
        except BudgetStop as error: bound.finish(job, 'queued', error=str(error))
        except Exception as error:
            bound.finish(job, 'review_required', error=type(error).__name__)
    return status(receipt_path, output)


def finalize(receipt_path, status_path, output, *, archive=None):
    """Use the unchanged finalizer only after verifying this lane's issuance."""
    value = verify(receipt_path); ledger = pipeline._ledger(value); state = _read(status_path)
    expected = {'receipt': _ref(receipt_path), 'status': _ref(status_path)}
    with ledger.connect() as con:
        issued = [json.loads(row['detail']) for row in con.execute(
            "SELECT detail FROM batch_events WHERE event='document_text_status_issued'")]
    if expected not in issued or state.get('document_text_receipt') != _ref(receipt_path):
        raise ValueError('Status was not issued by this documentary amendment')
    if state['text_consistency']['status'] != 'PASS': raise ValueError('Document text consistency is unresolved')
    # The original finalizer rechecks real mode, parent issuance, current human
    # history, hashes, all sample/distribution/document gates and final payload.
    return pipeline.finalize(value['parent_receipt']['path'], status_path, output, archive=archive)


def run_samples(parent_receipt, output, *, max_jobs=None):
    """Future entry: dispatch visual/difference only, never legacy documents."""
    with pipeline._lock(parent_receipt):
        receipt = pipeline.verify(parent_receipt); ledger = pipeline._ledger(receipt)
        pipeline._external(output, pipeline._roots(receipt), [parent_receipt])
        allowed = {jid: row for jid, row in receipt['jobs'].items() if row['kind'] in ('ai-visual', 'ai-difference')}
        with ledger.transaction() as con:
            events = [json.loads(row['detail']) for row in con.execute(
                "SELECT detail FROM batch_events WHERE event='document_text_legacy_job_superseded'")]
            event = {'parent_receipt': _ref(parent_receipt), 'legacy_document_job': receipt['document_job'],
                     'policy': POLICY, 'original_job_and_result_preserved': True}
            if event not in events: ledger.event(con, 'document_text_legacy_job_superseded', event)
        bound = pipeline._BoundLedger(ledger, receipt['binding'], allowed=allowed,
                                      validate=lambda: pipeline.verify(parent_receipt))
        ai_worker.run(bound, max_jobs=max_jobs)
        result = pipeline._status(ledger, parent_receipt, output)
        return {'schema_version': VERSION + '-sample-phase', 'parent_status': str(Path(output) / 'status.json'),
            'original_sample_status': result, 'legacy_document_job_superseded': True,
            'document_review_status': 'AI_REVIEW_REQUIRED', 'human_document_pending_count': 0,
            'next': 'prepare then run this module using a separately bounded linked document ledger'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for name in ('parent-receipt', 'parent-status', 'ledger', 'config', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--initialize-ledger', action='store_true')
    p.add_argument('--supporting-file', type=Path, action='append', default=[])
    for name in ('run', 'status', 'finalize'):
        p = sub.add_parser(name); p.add_argument('--receipt', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
        if name == 'finalize':
            p.add_argument('--status', type=Path, required=True); p.add_argument('--archive', type=Path)
    p = sub.add_parser('run-samples'); p.add_argument('--parent-receipt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--max-jobs', type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            # Check all protected roots before even creating a ledger file.
            parent = pipeline.verify(args.parent_receipt)
            if args.initialize_ledger and args.ledger.exists(): raise ValueError('Cannot reset an existing document ledger')
            if any(args.ledger.resolve().is_relative_to(root) for root in pipeline._roots(parent)):
                raise ValueError('Document ledger cannot be inside inspected packages')
            result = prepare(BatchLedger(args.ledger, _read(args.config), initialize=args.initialize_ledger),
                args.parent_receipt, args.parent_status, args.output, supporting_files=args.supporting_file)
        elif args.command == 'run-samples': result = run_samples(args.parent_receipt, args.output, max_jobs=args.max_jobs)
        elif args.command == 'finalize': result = finalize(args.receipt, args.status, args.output, archive=args.archive)
        else: result = globals()[args.command](args.receipt, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__': raise SystemExit(main())
