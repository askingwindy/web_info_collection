"""Freeze current-chain candidates for independent QC; never run a review or collect.

Only indexed results from the explicit current chain enter the comparison set.
It neither promotes observation traces nor writes the production registry;
identical frozen requests can be reused after deterministic integrity checks.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from .batch_core import file_sha, save_json
from .current_chain import assert_current_result_path, assert_current_evidence, read_chain_history


def _attempts(scope, dataset, sample_ids):
    from quality_inspector.profiles import package_files
    from .collect_runtime import verify_committed_samples
    rows = []
    with closing(sqlite3.connect(Path(scope['registry']).as_uri() + '?mode=ro', uri=True)) as con:
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
            if package_files(dataset / 'samples' / sample_id) != receipt['sample_files_sha256']:
                raise ValueError('Candidate bytes differ from the original saved sample: ' + sample_id)
            rows.append({**attempt, 'saved_sample': saved[0]})
    return rows


def prepare_qc_inputs(dataset, history_set, output, *, ai_percent, human_percent, seed, collection_checks=None, stratify='batch', risk_selected=None, production_sampling=False):
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
        if (checks.get('schema_version') != 'webcollect-pending-quality-checks-1'
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
    production_context = None
    if production_sampling:
        from .sampling_context import production_context as capture_context
        production_context = capture_context(scope, sample_ids)
    manifest = {'schema_version': 'qc-cumulative-set-1',
                'scope': 'Explicit current-chain candidate and indexed current results; zero legacy history',
                'packages': [{'path': str(dataset), 'package_files_sha256': original}]}
    prior_roots = {}
    for record in records:
        path = assert_current_result_path(scope, record['annotation_path'])
        if path.parent.parent.name != 'samples':
            raise ValueError('Current result must belong to a complete samples package')
        root = path.parent.parent.parent
        if record['sample_id'] in sample_ids:
            if file_sha(dataset/'samples'/record['sample_id']/'annotation.json')!=record['annotation_sha256']:
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
        _attempts(scope, root, sorted(ids))
        manifest['packages'].append({'path': str(root), 'package_files_sha256': package_files(root)})
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
                                      if collection_checks is not None else None),
                'distribution_thresholds_unchanged': True}
    if output.exists():
        receipt = json.loads((output / 'receipt.json').read_text())
        expected_files = {'receipt.json', 'sampling-plan.json', 'effective-set.json'}
        if collection_checks is not None: expected_files.add('collection-checks.json')
        if (set(package_files(output)) != expected_files
                or receipt.get('request') != request
                or file_sha(output / 'sampling-plan.json') != receipt.get('sampling_plan_sha256')
                or file_sha(output / 'effective-set.json') != receipt.get('effective_set_sha256')
                or collection_checks is not None and file_sha(output / 'collection-checks.json') != receipt.get('bound_checks_sha256')):
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
        if collection_checks is not None:
            bindings = [{key: row[key] for key in ('sample_id', 'task_id', 'task_version', 'task_key')}
                        for row in attempts]
            save_json(staged / 'collection-checks.json', {
                'schema_version': 'webcollect-qc-collection-checks-1', 'source': collection_checks,
                'sample_bindings': bindings, 'checks': checks['checks'],
                'QC_approval': False, 'requires_independent_QC': True})
        if (package_files(dataset) != original or read_chain_history(history_set) != (records, scope)
                or _attempts(scope, dataset, sample_ids) != attempts
                or any(package_files(item['path']) != item['package_files_sha256'] for item in manifest['packages'])):
            raise ValueError('Current candidate or chain changed during QC handoff')
        if collection_checks is not None:
            assert_current_evidence(scope, collection_checks)
        receipt = {'schema_version': 'webcollect-qc-handoff-1', 'chain_id': scope['chain_id'],
            'request': request, 'collection_checks': collection_checks,
            'bound_checks_sha256': file_sha(staged / 'collection-checks.json') if collection_checks is not None else None,
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
