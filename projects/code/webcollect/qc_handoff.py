"""Freeze current-chain candidates for independent QC; never run a review or collect.

Only indexed results from the explicit current chain enter the comparison set.
It neither promotes observation traces nor writes the production registry;
identical frozen requests can be reused after deterministic integrity checks.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from contextlib import closing
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3
import tempfile

from .batch_core import file_sha, save_json
from .current_chain import assert_current_result_path, assert_current_evidence, read_chain_history


def qc_layers(sample_report, package_report=None, cross_report=None):
    """Read independent evidence layers without promoting any production state."""
    from quality_inspector.engine import SEMANTIC
    def read(path):
        path = Path(path).resolve()
        return json.loads(path.read_text()), {'path': str(path), 'sha256': file_sha(path)}
    report, ref = read(sample_report)
    rows = []
    for sample in report['samples']:
        checks = {c['rule_id']: c for c in sample['checks'] if c['rule_id'].startswith('REVIEW_')}
        complete = (set(checks) == {'REVIEW_' + k.upper() for k in SEMANTIC}
                    and all(c['status'] in ('PASS', 'FAIL') and
                            (c.get('reviewer') or {}).get('kind') == 'ai' for c in checks.values()))
        expected_frames={s['step_id'] for s in sample.get('steps',[])}
        full_frames=bool(expected_frames) and all(
            (c.get('reviewer') or {}).get('kind') == 'ai'
            and set((c.get('provenance') or {}).get('frames_viewed',[])) == expected_frames
            for c in checks.values()) and set(checks) == {'REVIEW_' + k.upper() for k in SEMANTIC}
        rows.append({'sample_id': sample['sample_id'], 'actual_ai_reviewed': complete,
                     'all_five_decided':complete, 'full_frame_ai_receipt':full_frames,
                     'reported_sample_status':sample['status'],
                     'status': sample['status'] if complete else 'NOT_REVIEWED',
                     'checks': checks})
    result = {'sample_ai': {'report': ref, 'denominator': len(rows),
                           'actually_reviewed': sum(r['actual_ai_reviewed'] for r in rows),
                           'full_frame_ai_receipts':sum(r['full_frame_ai_receipt'] for r in rows),
                           'all_five_decided':sum(r['all_five_decided'] for r in rows),
                           'pass': sum(r['status'] == 'PASS' for r in rows), 'samples': rows},
              'package_document_ai': {'status': 'NOT_RUN'},
              'distribution': {'status': 'NOT_RUN'}, 'cumulative': {'status': 'NOT_RUN'},
              'human_review': 'NOT_CLAIMED', 'published': 'NOT_CLAIMED'}
    if package_report:
        package, source = read(package_report)
        if package.get('payload_sha256') != report.get('payload_sha256'):
            raise ValueError('QC layers refer to different delivered payloads')
        result['package_document_ai'] = {'report': source, **package.get('delivery_document_review', {'status':'NOT_RUN'})}
        checks = [c for c in package['dataset_checks'] if c['rule_id'] in
                  ('DELIVERY_EXPECTED_SAMPLES', 'DELIVERY_SHORT_FLOW_SHARE', 'DELIVERY_CATEGORY_SHARE', 'DELIVERY_NEAR_DUPLICATE_SAMPLE_RATE')]
        result['distribution'] = {'report': source, 'denominator': package['sample_count'], 'checks': checks,
                                  'status': 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else
                                            'PASS' if checks and all(c['status'] == 'PASS' for c in checks) else 'NOT_EVALUATED'}
    if cross_report:
        cross, source = read(cross_report)
        result['cumulative'] = {'report': source, 'status': cross.get('status'),
                                'denominator': cross.get('sample_count'), 'errors': cross.get('errors', [])}
    return result


def _customer_root(scope, annotation):
    """Resolve raw capture through the original export receipt, never by role guess."""
    from quality_inspector.profiles import package_files
    root = annotation.parent.parent.parent
    if root.name != 'capture':
        return root
    export = root.parent / 'candidate'
    receipt_path = root.parent / 'candidate-receipt.json'
    provenance_path = root.parent / 'candidate.evidence.json'
    for path in (export, receipt_path, provenance_path):
        assert_current_result_path(scope, path)
    if not receipt_path.is_file() or not provenance_path.is_file():
        raise ValueError('Raw comparison has no original customer export receipt')
    receipt = json.loads(receipt_path.read_text())
    provenance = json.loads(provenance_path.read_text())
    if (receipt.get('files_sha256') != package_files(export)
            or Path(provenance.get('source_root','')).resolve() != root.resolve()
            or Path(provenance.get('client_root','')).resolve() != export.resolve()):
        raise ValueError('Original customer export binding changed')
    sid = annotation.parent.name
    rows = [row for row in provenance.get('source_samples',[]) if row.get('sample_id') == sid]
    if len(rows) != 1 or rows[0].get('source_annotation_sha256',rows[0].get('annotation_sha256')) != file_sha(annotation):
        raise ValueError('Customer export source sample binding differs')
    return export


def _attempts(scope, dataset, sample_ids):
    from quality_inspector.profiles import package_files
    from .collect_runtime import verify_committed_samples
    rows = []
    with closing(workspace_connect(Path(scope['registry']).as_uri() + '?mode=ro', uri=True)) as con:
        for sample_id in sample_ids:
            found = con.execute('SELECT a.attempt_id,a.task_key,a.sample_id,a.status,t.task_id,t.task_version,a.evidence_json '
                                'FROM m4_attempts a LEFT JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.sample_id=?',
                                (sample_id,)).fetchall()
            if len(found) != 1 or found[0][3] != 'collected_pending_review':
                raise ValueError('Candidate must bind an original saved current-chain attempt: ' + sample_id)
            attempt = dict(zip(('attempt_id', 'task_key', 'sample_id', 'status', 'task_id', 'task_version'), found[0][:6]))
            attempt['evidence'] = json.loads(found[0][6])
            saved = [ref for ref in attempt['evidence'] if isinstance(ref, dict)
                     and Path(ref.get('path', '')).parts[-3:] == ('evidence', sample_id, 'saved_sample.json')]
            if len(saved) != 1:
                raise ValueError('Candidate needs its committed saved-sample receipt: ' + sample_id)
            receipt_path = assert_current_result_path(scope, Path(saved[0]['path']))
            if not receipt_path.is_file() or file_sha(receipt_path) != saved[0].get('sha256'):
                raise ValueError('Committed saved-sample receipt changed: ' + sample_id)
            source = receipt_path.parents[2]
            package_files(source / 'samples' / sample_id)
            package_files(receipt_path.parent)  # Reject symlinks in original evidence too.
            verify_committed_samples(source, [attempt])
            receipt = json.loads(receipt_path.read_text())
            actual_sample = package_files(dataset / 'samples' / sample_id)
            if actual_sample != receipt['sample_files_sha256']:
                source_annotation = source/'samples'/sample_id/'annotation.json'
                if _customer_root(scope, source_annotation) != dataset:
                    raise ValueError('Candidate bytes differ from the original saved sample: ' + sample_id)
                expected = dict(receipt['sample_files_sha256'])
                provenance = json.loads(dataset.with_name(dataset.name+'.evidence.json').read_text())
                row = next(row for row in provenance['source_samples'] if row['sample_id'] == sample_id)
                expected['annotation.json'] = row['export_annotation_sha256']
                if actual_sample != expected:
                    raise ValueError('Customer export sample files changed: ' + sample_id)
            prefix=receipt.get('raw_execution',{}).get('trusted_prefix')
            rows.append({**attempt, 'saved_sample': saved[0],
                **({'trusted_prefix':prefix} if prefix else {}),
                'collection_completion': {'saved_sample':saved[0], 'raw_execution':receipt.get('raw_execution', {}),
                    'completion_evidence':{'path':str(receipt_path.parent/'completion-evidence.json'),
                        'sha256':file_sha(receipt_path.parent/'completion-evidence.json')}}})
    return rows


def prepare_qc_inputs(dataset, history_set, output, *, ai_percent, human_percent, seed, collection_checks=None, stratify='batch', risk_selected=None, production_sampling=False, delivery_policy=None):
    """Create immutable sampling/effective-set inputs without granting QC approval.

    Ratios are explicit, independent parameters. No model/provider configuration,
    old sample population, review result or production dispatcher is consumed.
    """
    from quality_inspector.delivery_sampling import freeze
    from quality_inspector.profiles import package_files

    records, scope = read_chain_history(Path(history_set).resolve())
    dataset = assert_current_result_path(scope, Path(dataset).absolute())
    output = Path(output).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('QC handoff output cannot contain symlinks')
    output = output.resolve()
    protected = [dataset, Path(scope['manifest']['path']), Path(scope['registry'])]
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in protected):
        raise ValueError('Use a fresh QC directory outside the candidate, manifest and registry')
    if collection_checks is not None:
        assert_current_evidence(scope, collection_checks)
        checks = json.loads(Path(collection_checks['path']).read_text())
        if (checks.get('schema_version') not in ('pending-quality-checks', 'webcollect-pending-quality-checks-1')
                or checks.get('QC_approval') is not False or checks.get('requires_independent_QC') is not True
                or not isinstance(checks.get('checks'), list)):
            raise ValueError('Collection checks must be an immutable pending independent-QC request')
    original = package_files(dataset)
    annotations = sorted((dataset / 'samples').glob('*/annotation.json'))
    if not original or not annotations:
        raise ValueError('An actually saved nonempty current candidate is required')
    sample_ids = [json.loads(path.read_text())['sample_id'] for path in annotations]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError('Candidate sample IDs must be unique')
    attempts = _attempts(scope, dataset, sample_ids)
    completion_bindings = []
    def bind_delivery(root, rows):
        from .closing_policy import COMPLETED_GOAL_DELIVERY, completion_delivery_decision
        if delivery_policy not in (None, COMPLETED_GOAL_DELIVERY):raise ValueError('Unknown delivery policy')
        for row in rows:
            annotation = root/'samples'/row['sample_id']/'annotation.json'
            from .collection_strategy import save_eligibility as strategy_save_eligibility
            decision = strategy_save_eligibility(json.loads(annotation.read_text()), row['collection_completion']['raw_execution'])
            if not decision['delivery_eligible']:
                raise ValueError('Explicit delivery set contains an ineligible original goal: '+row['sample_id'])
            completion_bindings.append({'sample_id':row['sample_id'], 'annotation_sha256':file_sha(annotation),
                'saved_sample':row['saved_sample'], 'delivery_decision':decision})
    bind_delivery(dataset, attempts)
    needs_checks=collection_checks is not None or any(row.get('collection_completion') for row in attempts)
    if collection_checks is None:checks={'checks':[]}
    production_context = None
    if production_sampling:
        from .sampling_context import production_context as capture_context
        production_context = capture_context(scope, sample_ids)
    manifest = {'schema_version': 'qc-cumulative-set',
                'scope': 'Explicit current-chain candidate and indexed current results; zero legacy history',
                'packages': [{'path': str(dataset), 'package_files_sha256': original}]}
    prior_roots = {}
    for record in records:
        path = assert_current_result_path(scope, record['annotation_path'])
        if path.parent.parent.name != 'samples':
            raise ValueError('Current result must belong to a complete samples package')
        root = _customer_root(scope, path)
        if record['sample_id'] in sample_ids:
            if package_files(dataset/'samples'/record['sample_id']) != package_files(root/'samples'/record['sample_id']):
                raise ValueError('Indexed current candidate annotation changed')
            continue  # Same committed original, not another comparison sample.
        if root == dataset:
            continue
        prior_roots.setdefault(root, set()).add(record['sample_id'])
    for root, registered in sorted(prior_roots.items()):
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError('QC output must be outside all current packages')
        ids = {json.loads(path.read_text())['sample_id'] for path in (root / 'samples').glob('*/annotation.json')}
        if ids != registered:
            raise ValueError('Prior package contains unregistered current results')
        manifest['packages'].append({'path': str(root), 'package_files_sha256': package_files(root)})
    if delivery_policy is not None:
        manifest['delivery_policy'] = delivery_policy
        # Prior indexed packages are comparison evidence, not new delivery
        # targets. Keep their original files and historical completion policy.
        manifest['delivery_sample_ids'] = sorted(sample_ids)
        manifest['delivery_target'] = {'protocol': 'qc-delivery-target',
            'package': str(dataset)}
        manifest['completion_bindings'] = completion_bindings
    request = {'dataset': str(dataset), 'history_scope': scope, 'attempts': attempts,
               'candidate_files_sha256': original, 'effective_set': manifest,
               'ai_percent': ai_percent, 'human_percent': human_percent, 'seed': seed,
               'collection_checks': collection_checks, 'stratify':stratify,'risk_selected':risk_selected,
               **({'production_context':production_context} if production_sampling else {})}
    def result():
        bound_checks = output / 'collection-checks.json'
        return {'sampling_plan': str(output / 'sampling-plan.json'),
                'effective_set': str(output / 'effective-set.json'), 'receipt': str(output / 'receipt.json'),
                'original_denominator': len(sample_ids), 'ai_percent': ai_percent,
                'human_percent': human_percent, 'external_model_calls': 0,
                'production_registry_writes': 0, 'QC_approval': False,
                'collection_checks': ({'path': str(bound_checks), 'sha256': file_sha(bound_checks)}
                                      if needs_checks else None),
                'distribution_thresholds_unchanged': True}
    if output.exists():
        receipt = json.loads((output / 'receipt.json').read_text())
        expected_files = {'receipt.json', 'sampling-plan.json', 'effective-set.json'}
        if needs_checks: expected_files.add('collection-checks.json')
        if (set(package_files(output)) != expected_files
                or receipt.get('request') != request
                or file_sha(output / 'sampling-plan.json') != receipt.get('sampling_plan_sha256')
                or file_sha(output / 'effective-set.json') != receipt.get('effective_set_sha256')
                or needs_checks and file_sha(output / 'collection-checks.json') != receipt.get('bound_checks_sha256')):
            raise ValueError('Existing QC handoff differs from its immutable request or artifacts')
        from quality_inspector.delivery_sampling import verify
        verify(output / 'sampling-plan.json', dataset)
        return result()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.qc-handoff-', dir=output.parent) as temporary:
        staged = Path(temporary)
        plan = freeze(dataset, staged / 'sampling-plan.json', ai_percent=ai_percent,
                      human_percent=human_percent, seed=seed, stratify=stratify,risk_selected=risk_selected,
                      production_context=production_context)
        save_json(staged / 'effective-set.json', manifest)
        if needs_checks:
            bindings = [{key: row[key] for key in ('sample_id', 'task_id', 'task_version', 'task_key')}
                        for row in attempts]
            for row,binding in zip(attempts,bindings):
                binding['collection_completion'] = {**row['collection_completion'],
                    'candidate_sample':{'sample_id':row['sample_id'],
                        'files_sha256':package_files(dataset/'samples'/row['sample_id'])}}
                if row.get('trusted_prefix'):
                    binding['trusted_prefix']={'saved_sample':row['saved_sample'],'binding':row['trusted_prefix'],
                        'candidate_sample':{'sample_id':row['sample_id'],
                            'files_sha256':package_files(dataset/'samples'/row['sample_id'])}}
            save_json(staged / 'collection-checks.json', {
                'schema_version': 'qc-collection-checks', 'source': collection_checks,
                **({'completion_only':True} if collection_checks is None else {}),
                'sample_bindings': bindings, 'checks': checks['checks'],
                'QC_approval': False, 'requires_independent_QC': True})
        if (package_files(dataset) != original or read_chain_history(history_set) != (records, scope)
                or _attempts(scope, dataset, sample_ids) != attempts
                or any(package_files(item['path']) != item['package_files_sha256'] for item in manifest['packages'])):
            raise ValueError('Current candidate or chain changed during QC handoff')
        if collection_checks is not None:
            assert_current_evidence(scope, collection_checks)
        receipt = {'schema_version': 'qc-handoff', 'chain_id': scope['chain_id'],
            'request': request, 'collection_checks': collection_checks,
            'bound_checks_sha256': file_sha(staged / 'collection-checks.json') if needs_checks else None,
            'history_scope': scope, 'dataset': str(dataset), 'attempts': attempts,
            'candidate_files_sha256': original, 'sampling_plan_sha256': file_sha(staged / 'sampling-plan.json'),
            'effective_set_sha256': file_sha(staged / 'effective-set.json'),
            'original_denominator': plan['original_denominator'],
            'ai_percent': plan['policy']['ai_percent'], 'human_percent': plan['policy']['human_percent'],
            'external_model_calls': 0, 'production_registry_writes': 0, 'QC_approval': False,
            'status': 'QC_NOT_RUN'}
        save_json(staged / 'receipt.json', receipt)
        output.mkdir(exist_ok=False)
        # Exclusive file publication: an existing output is never overwritten.
        for path in sorted(staged.iterdir()):
            with (output / path.name).open('xb') as stream:
                stream.write(path.read_bytes())
    return result()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'history-set', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ai-percent', type=float, required=True)
    parser.add_argument('--human-percent', type=float, required=True)
    parser.add_argument('--seed', required=True)
    parser.add_argument('--collection-checks', type=Path)
    parser.add_argument('--production-sampling', action='store_true', help='Explicit versioned fragment 10/30/100 policy; capture-bound ordinals required')
    args = parser.parse_args(argv)
    try:
        result = prepare_qc_inputs(args.dataset, args.history_set, args.output,
            ai_percent=args.ai_percent, human_percent=args.human_percent, seed=args.seed,
            production_sampling=args.production_sampling,
            collection_checks=({'path': str(args.collection_checks.resolve()), 'sha256': file_sha(args.collection_checks)}
                               if args.collection_checks else None))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
