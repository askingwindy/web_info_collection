"""Read-only internal batch quality decisions, separate from final delivery QC.

Production validators are registered in code, never loaded from JSON or a plugin.
The initial registry is empty. Calibration re-executes that exact implementation
against bound, independently reviewed positive AND negative examples per check.
No review record, registry, sampling state or inspected package is modified.
"""
import argparse
from collections import Counter
from copy import deepcopy
import inspect as python_inspect
import json
from pathlib import Path

from webcollect.batch_core import file_sha, load_json, save_json
from webcollect.planning import object_sha256
from .contract import fingerprint
from .duplicates import analyze_inputs
from .engine import aggregate, inspect
from .format_checks import run as format_run
from .layout import discover
from .profiles import DEFAULT_DELIVERY_PROFILE, load as load_profile, package_files
from .reviews import SEMANTIC, intake
from .sampling import DEFAULT_POLICY, freeze_rows, producer_implementation, sample_context

# Each entry has version and evaluate(sample_context)->{scope, checks}. Tests
# patch this registry only in process; no production implementation is enabled.
_VALIDATORS = {}
DISTRIBUTION_RULES = {'DELIVERY_CATEGORY_SHARE', 'DELIVERY_EXPECTED_SAMPLES',
                      'DELIVERY_EXPECTED_SITES', 'DELIVERY_VIEWPORT_SPECS',
                      'DELIVERY_SHORT_FLOW_SHARE'}


def _profile(path):
    value = load_profile(path)
    if value['configuration']['scope'] != 'delivery':
        raise ValueError('An explicit delivery profile is required')
    if value['configuration']['targets']['category_share'] != 'enforced':
        raise ValueError('Internal decisions cannot waive the contract category limit')
    return value


def _implementation():
    root = Path(__file__).parent
    registry = {}
    for name, validator in _VALIDATORS.items():
        function = validator['evaluate']; source = python_inspect.getsourcefile(function)
        if not source: raise ValueError('Registered validator needs inspectable implementation')
        registry[name] = {'version': validator['version'], 'source_sha256': file_sha(source),
                          'function': function.__module__ + '.' + function.__qualname__}
    return {'decision': {name: file_sha(root / name) for name in (
        'batch_decision.py', 'engine.py', 'format_checks.py', 'reviews.py', 'profiles.py',
        'duplicates.py', 'contract.py', 'sampling.py')},
        'validators': registry, 'producer': producer_implementation()}


def _set_inputs(manifest, candidate):
    manifest = Path(manifest).resolve(); value = load_json(manifest)
    if value.get('schema_version') not in ('qc-cumulative-set', 'qc-cumulative-set-1') or not value.get('packages'):
        raise ValueError('A nonempty frozen qc-cumulative-set is required')
    roots = []; snapshots = {}
    for item in value['packages']:
        root = Path(item['path']); root = (manifest.parent / root).resolve() if not root.is_absolute() else root.resolve()
        if any(root.is_relative_to(other) or other.is_relative_to(root) for other in roots):
            raise ValueError('Duplicate or overlapping effective package roots')
        actual = package_files(root)
        if actual != item['package_files_sha256']:
            raise ValueError('Frozen effective package bytes changed: ' + str(root))
        roots.append(root); snapshots[str(root)] = actual
    if roots.count(Path(candidate).resolve()) != 1:
        raise ValueError('Effective set must include the exact candidate package once')
    return roots, snapshots


def _history(roots, candidate_ids):
    annotations = [path for root in roots for path in discover(root).annotations]
    ids = [load_json(path)['sample_id'] for path in annotations]
    if len(ids) != len(set(ids)): raise ValueError('Effective set has repeated sample IDs')
    duplicates = analyze_inputs(annotations, dataset_label='internal-batch-effective-set', current_sample_ids=candidate_ids)
    hits = {}; historical = {}
    for route, key in (('route1', 'pairs'), ('route2', 'confirmed_pairs'), ('route3', 'candidates'), ('route4', 'candidates')):
        pairs = duplicates[route][key]
        hits[route] = [pair for pair in pairs if set(pair['sample_ids']) & candidate_ids]
        historical[route] = len(pairs) - len(hits[route])
    return {'status': 'FAIL' if any(hits.values()) else 'PASS', 'sample_count': len(ids),
            'candidate_sample_count': len(candidate_ids), 'history_sample_count': len(ids) - len(candidate_ids),
            'candidate_pair_denominator': len(candidate_ids) * (len(ids) - len(candidate_ids)) + len(candidate_ids) * (len(candidate_ids) - 1) // 2,
            'candidate_involved_hits': hits, 'historical_only_hit_counts': historical,
            'duplicates': duplicates,
            'scope': 'Four-route comparisons against explicit frozen history; historical-only defects retained, never relabelled as candidate failures',
            'not_a_delivery_distribution_scope': True}


def _sample(sample):
    root = Path(sample['sample_path']); context = sample_context(sample)
    listing = load_json(root.parent.parent / 'site-list.json')
    assignment = [row['site_id'] for row in listing['samples'] if row['sample_id'] == sample['sample_id']]
    sites = [row for row in listing['sites'] if assignment == [row['site_id']]]
    if len(sites) != 1: raise ValueError('Validator scope needs exact unambiguous source URI')
    return {**context, 'sample_id': sample['sample_id'], 'sample_path': str(root), 'uri': sites[0]['uri']}


def _evaluate(validator_id, sample):
    if validator_id not in _VALIDATORS:
        raise ValueError('No registered validator: ' + str(validator_id))
    context = _sample(sample); root = Path(context['sample_path'])
    before = package_files(root)
    output = _VALIDATORS[validator_id]['evaluate'](deepcopy(context))
    if package_files(root) != before: raise ValueError('Validator changed inspected sample')
    if output is None: return None
    if not isinstance(output, dict) or set(output) != {'scope', 'checks'}:
        raise ValueError('Registered validator must return exact scope/checks')
    scope = output['scope']; checks = output['checks']
    if (not isinstance(scope, dict) or set(scope) != {'uri', 'task_family', 'business_rule', 'business_rule_version'}
            or scope['uri'] != context['uri'] or scope['task_family'] != context['task_family']
            or any(not isinstance(scope[key], str) or not scope[key].strip() for key in ('business_rule', 'business_rule_version'))):
        raise ValueError('Validator scope differs from exact URI/task family or lacks business version')
    if not isinstance(checks, dict) or not checks or not set(checks) <= set(SEMANTIC):
        raise ValueError('Validator must name implemented semantic checks only')
    for name, result in checks.items():
        if (not isinstance(result, dict) or result.get('status') not in ('PASS', 'FAIL', 'REVIEW_REQUIRED')
                or not isinstance(result.get('reason'), str) or not result['reason'].strip()
                or not isinstance(result.get('evidence'), list) or not result['evidence']):
            raise ValueError('Validator must compute decision and nonempty exact evidence: ' + name)
        for evidence in result['evidence']:
            if (not isinstance(evidence, dict) or evidence.get('path') not in before
                    or evidence.get('sha256') != before.get(evidence.get('path'))
                    or not isinstance(evidence.get('detail'), str) or not evidence['detail'].strip()):
                raise ValueError('Validator evidence is missing/stale/outside sample: ' + name)
        required = ({step['image_path'] for step in context['annotation']['steps']}
                    if name in ('visual_alignment', 'language', 'privacy') else
                    {context['annotation']['steps'][-1]['image_path']}
                    if name == 'terminal_semantics' else {'annotation.json'})
        if name == 'visual_alignment':
            required.update(step['ui_tree_path'] for step in context['annotation']['steps'])
        if not required <= {item['path'] for item in result['evidence']}:
            raise ValueError('Validator lacks required original frame/tree evidence: ' + name)
    return output


def _calibration(path):
    if not path:
        return {'status': 'ABSENT', 'supported': {}, 'validator_id': None, 'bindings': {}, 'roots': {}}
    path = Path(path).resolve(); value = load_json(path)
    if not isinstance(value, dict) or not {'dataset', 'package_files_sha256', 'reviews', 'validator_id', 'sample_ids'} <= set(value):
        raise ValueError('Historical PASS/self-filled certificates are not detector calibration')
    validator_id = value['validator_id']
    if validator_id not in _VALIDATORS: raise ValueError('No registered validator: ' + validator_id)
    dataset = Path(value['dataset']).resolve(); reviews = Path(value['reviews']['path']).resolve()
    files = package_files(dataset)
    if files != value['package_files_sha256'] or file_sha(reviews) != value['reviews']['sha256']:
        raise ValueError('Calibration bytes changed')
    formats = format_run(None, dataset)
    accepted, errors, _ = intake(reviews, formats['samples'], fingerprint()[1])
    if errors: raise ValueError('Calibration review binding invalid: ' + json.dumps(errors, ensure_ascii=False))
    if sorted(value['sample_ids']) != sorted(row['sample_id'] for row in formats['samples']):
        raise ValueError('Calibration denominator differs from original package')
    observed = {}; scope_values = {}; comparisons = []
    for sample in formats['samples']:
        record = accepted.get(sample['sample_id']); result = _evaluate(validator_id, sample)
        if not sample.get('confirmed_format_pass') or not record or not result:
            raise ValueError('Calibration needs mechanically valid examples, complete actual reviews and supported scope')
        if set(record['checks']) != set(SEMANTIC) or any(c['status'] not in ('PASS', 'FAIL') for c in record['checks'].values()):
            raise ValueError('Calibration needs all actual semantic labels resolved')
        scope_id = object_sha256(result['scope']); scope_values[scope_id] = result['scope']
        for name, decision in result['checks'].items():
            expected = record['checks'][name]['status']; actual = decision['status']
            comparisons.append({'sample_id': sample['sample_id'], 'scope_id': scope_id, 'check': name, 'expected': expected, 'actual': actual})
            if actual != expected: raise ValueError('Validator missed/misclassified calibration defect: ' + name)
            observed.setdefault(scope_id, {}).setdefault(name, set()).add(expected)
    supported = {key: {'scope': scope_values[key], 'checks': sorted(name for name, labels in checks.items() if labels == {'PASS', 'FAIL'})}
                 for key, checks in observed.items()}
    supported = {key: value for key, value in supported.items() if value['checks']}
    return {'status': 'VERIFIED' if supported else 'INSUFFICIENT_POSITIVE_NEGATIVE_COVERAGE',
            'validator_id': validator_id, 'supported': supported, 'comparisons': comparisons,
            'bindings': {str(path): file_sha(path), str(reviews): file_sha(reviews)}, 'roots': {str(dataset): files},
            'empirical_examples_are_not_population_accuracy_guarantee': True,
            'identity_authenticated': False, 'actual_reading_authenticated': False}


def prepare_calibration(dataset, reviews, validator_id, output):
    output = Path(output).resolve(); dataset = Path(dataset).resolve(); reviews = Path(reviews).resolve()
    _protect(output, [dataset], [reviews])
    value = {'dataset': str(dataset),
             'package_files_sha256': package_files(dataset), 'reviews': {'path': str(reviews), 'sha256': file_sha(reviews)},
             'validator_id': validator_id, 'implementation_sha256': _implementation(), 'contract_sha256': fingerprint()[1],
             'sample_ids': sorted(r['sample_id'] for r in format_run(None, dataset)['samples'])}
    # Persist immutable inputs only. The subsequent independent verification never
    # trusts a saved PASS field, support list or detector output from this file.
    save_json(output, value)
    return _calibration(output)


def _automatic(checked, calibration):
    rows = []; machine = {}
    for sample in checked['samples']:
        context = _sample(sample); annotation = context.pop('annotation')
        mechanics = [c for c in sample['checks'] if not c['rule_id'].startswith('REVIEW_')]
        result = _evaluate(calibration['validator_id'], sample) if calibration['validator_id'] else None
        supported = calibration['supported'].get(object_sha256(result['scope']), {}).get('checks', []) if result else []
        machine[sample['sample_id']] = {'result': result, 'supported_checks': supported}
        reasons = []
        if set(supported) != set(SEMANTIC): reasons.append('unvalidated-semantic-support')
        if result and any(c['status'] != 'PASS' for c in result['checks'].values()): reasons.append('validator-unresolved-or-failed')
        if annotation.get('risk_level') != 'normal': reasons.append('sensitive-or-unknown-risk')
        if annotation.get('short_flow'): reasons.append('short-flow')
        if annotation.get('completion_status') != 'success': reasons.append('exception-or-incomplete-completion')
        if any(s.get('exception_evidence') or s.get('tool_result', {}).get('status') != 'success' for s in annotation.get('steps', [])):
            reasons.append('recorded-exception')
        rows.append({'sample_id': sample['sample_id'], 'sample_path': sample['sample_path'],
                     'site': context['site'], 'task_family': context['task_family'], 'capability': context['capability'],
                     'uri': context['uri'], 'stratum': object_sha256({'uri': context['uri'], 'family': context['task_family']}),
                     'automatic_status': aggregate(c['status'] for c in mechanics), 'risk_reasons': reasons})
    policy = deepcopy(DEFAULT_POLICY)
    # Fixed seed derivation prevents self-authored selection/seed substitutions.
    policy['seed'] = object_sha256({'namespace': 'internal-batch-decision', 'candidate': checked['input_files_sha256'], 'contract': fingerprint()[1]})
    return freeze_rows(rows, policy), machine, policy


def _plan(dataset, effective_set, profile, calibration, checked, snapshots):
    rows, machine, policy = _automatic(checked, calibration)
    value = {'dataset': str(Path(dataset).resolve()),
             'profile': profile, 'effective_set': {'path': str(Path(effective_set).resolve()), 'sha256': file_sha(effective_set)},
             'package_files_sha256': snapshots, 'contract_sha256': fingerprint()[1], 'implementation_sha256': _implementation(),
             'calibration_bindings': calibration['bindings'], 'policy': policy, 'rows': rows,
             'original_denominator': len(rows), 'release_ready': False}
    value['plan_sha256'] = object_sha256(value)
    return value, machine


def _context(dataset, effective_set, profile, calibration):
    dataset = Path(dataset).resolve(); selected = _profile(profile)
    roots, snapshots = _set_inputs(effective_set, dataset)
    supported = _calibration(calibration)
    checked = inspect(None, dataset, profile=selected['path'], inspection_stage='payload')
    plan, machine = _plan(dataset, effective_set, selected, supported, checked, snapshots)
    return dataset, selected, roots, snapshots, supported, checked, plan, machine


def prepare_plan(dataset, effective_set, output, *, profile=DEFAULT_DELIVERY_PROFILE, calibration=None):
    dataset, selected, roots, snapshots, supported, checked, plan, machine = _context(dataset, effective_set, profile, calibration)
    _protect(Path(output).resolve(), roots + list(supported['roots']),
             [Path(effective_set).resolve(), Path(selected['path'])] + list(supported['bindings']))
    if any(package_files(root) != files for root, files in {**snapshots, **supported['roots']}.items()):
        raise ValueError('Plan input changed during preparation')
    if not {'dataset', 'profile', 'effective_set', 'package_files_sha256', 'policy', 'rows'} <= set(plan):
        raise ValueError('Plan structure incomplete during preparation')
    save_json(output, plan)
    return {'plan_file': str(Path(output).resolve()), 'plan_sha256': plan['plan_sha256'],
            'sample_count': len(plan['rows']), 'selected': sum(r['selected'] for r in plan['rows']),
            'risk_required': sum(r['risk_required'] for r in plan['rows']), 'release_ready': False}


def decide(dataset, effective_set, *, profile=DEFAULT_DELIVERY_PROFILE, reviews=None, sampling_plan=None, calibration=None,delivery_sampling_plan=None,human_reviews=None,ai_failures=None):
    if delivery_sampling_plan and sampling_plan:raise ValueError('Choose either legacy internal sampling or explicit delivery sampling')
    human_paths=[human_reviews] if isinstance(human_reviews,(str,Path)) else list(human_reviews or [])
    failure_paths=[ai_failures] if isinstance(ai_failures,(str,Path)) else list(ai_failures or [])
    dataset, selected, roots, snapshots, supported, automatic, expected_plan, machine = _context(dataset, effective_set, profile, calibration)
    input_paths = [Path(effective_set).resolve(), Path(selected['path'])]
    input_paths += [Path(path).resolve() for path in (reviews, sampling_plan,delivery_sampling_plan,*human_paths,*failure_paths) if path]
    bindings = {str(path): file_sha(path) for path in input_paths}; bindings.update(supported['bindings'])
    if sampling_plan and load_json(sampling_plan) != expected_plan:
        raise ValueError('Sampling plan differs from recomputed bytes, calibration, policy, risk or selection')
    checked = inspect(None, dataset, profile=selected['path'], reviews=reviews, inspection_stage='payload',
                      delivery_sampling_plan=delivery_sampling_plan,human_reviews=human_paths,ai_failures=failure_paths)
    history = _history(roots, {r['sample_id'] for r in checked['samples']})
    selection = {r['sample_id']: r for r in expected_plan['rows']}
    rows = []; reasons = []; validator_failed = []
    for sample in checked['samples']:
        sid = sample['sample_id']; semantic = [c for c in sample['checks'] if c['rule_id'].startswith('REVIEW_')]
        mechanical = [c for c in sample['checks'] if not c['rule_id'].startswith('REVIEW_')]
        review_status = aggregate(c['status'] for c in semantic)
        result = machine[sid]['result']; covered = machine[sid]['supported_checks']
        if result and any(c['status'] == 'FAIL' for c in result['checks'].values()): validator_failed.append(sid)
        machine_pass = bool(result) and set(covered) == set(SEMANTIC) and all(c['status'] == 'PASS' for c in result['checks'].values())
        required = not sampling_plan or selection[sid]['selected']
        admitted = review_status == 'PASS' or (not required and machine_pass and review_status != 'FAIL')
        sampling_row=sample.get('semantic_sampling')
        if sampling_row is not None:
            required=bool(sampling_row['ai_selected'] or sampling_row['human_required'])
            admitted=sampling_row['admission_status']=='PASS'
            if sampling_row['status']=='NOT_SELECTED':review_status='NOT_SELECTED'
        if not admitted and review_status != 'FAIL': reasons.append({'code': 'MISSING_REQUIRED_EVIDENCE', 'sample_id': sid, 'selected_or_full_review_required': required})
        rows.append({'sample_id': sid, 'mechanical_status': aggregate(c['status'] for c in mechanical),
                     'review_status': review_status, 'review_required_by_plan': required,
                     'actual_ai_reviewed': bool(sampling_row['ai_source']) if sampling_row else review_status in ('PASS', 'FAIL') and all((c.get('reviewer') or {}).get('kind') == 'ai' for c in semantic),
                     'actual_human_reviewed': bool(sampling_row['human_source']) if sampling_row else review_status in ('PASS', 'FAIL') and all((c.get('reviewer') or {}).get('kind') == 'human' for c in semantic),
                     'batch_evidence_basis': 'explicit-frozen-sampling-policy' if sampling_row and admitted else 'complete-bound-review' if review_status == 'PASS' else 'validated-machine-checks-and-sampling' if admitted else 'unresolved-or-failed',
                     **({'semantic_sampling':sampling_row} if sampling_row else {}),
                     'machine_evidence': machine[sid], 'selection': selection[sid]})
    failures = [c for sample in checked['samples'] for c in sample['checks'] if c['status'] == 'FAIL']
    failures += [c for c in checked['dataset_checks'] if c['status'] == 'FAIL' and c['rule_id'] not in DISTRIBUTION_RULES]
    if failures: reasons.append({'code': 'CANDIDATE_QUALITY_FAILED', 'rules': sorted({c['rule_id'] for c in failures})})
    if history['status'] != 'PASS': reasons.append({'code': 'CANDIDATE_CUMULATIVE_DUPLICATE'})
    if validator_failed: reasons.append({'code': 'REGISTERED_VALIDATOR_FAILED', 'sample_ids': validator_failed})
    pending = [c['rule_id'] for c in checked['dataset_checks'] if c['status'] == 'REVIEW_REQUIRED']
    if pending: reasons.append({'code': 'BATCH_EVIDENCE_PENDING', 'rules': sorted(set(pending))})
    if any(row['mechanical_status'] == 'REVIEW_REQUIRED' for row in rows): reasons.append({'code': 'AUTOMATIC_EVIDENCE_PENDING'})
    if not rows: reasons.append({'code': 'EMPTY_CANDIDATE'})
    if any(file_sha(path) != digest for path, digest in bindings.items()): raise ValueError('Decision input changed during inspection')
    for root, files in {**snapshots, **supported['roots']}.items():
        if package_files(root) != files: raise ValueError('Inspected package changed during decision')
    if not {'dataset', 'profile', 'effective_set', 'package_files_sha256', 'policy', 'rows', 'contract_sha256'} <= set(expected_plan):
        raise ValueError('Sampling plan structure incomplete during decision')
    status = 'FAIL' if failures or history['status'] != 'PASS' or validator_failed else 'HOLD' if reasons else 'PASS'
    distribution = [c for c in checked['dataset_checks'] if c['rule_id'] in DISTRIBUTION_RULES]
    return {'internal_batch_decision': status,
            'decision_scope': 'Candidate per-sample quality, required actual reviews, documents, and candidate-involved cumulative duplicates. Delivery-set distributions are separate and never waived.',
            'candidate': {'path': str(dataset), 'sample_count': len(rows), 'profile': selected},
            'effective_set': {'path': str(Path(effective_set).resolve()), 'package_paths': list(snapshots), 'sample_count': history['sample_count'],
                              'purpose': 'Historical comparison only; pending history is not the current delivery selection'},
            'input_files_sha256': bindings, 'package_files_sha256': snapshots,
            'contract_sha256': expected_plan['contract_sha256'], 'implementation_sha256': expected_plan['implementation_sha256'],
            'rows': rows, 'review_status_counts': dict(Counter(row['review_status'] for row in rows)),
            'sampling_plan_used': str(Path(sampling_plan).resolve()) if sampling_plan else None,
            'calibration': supported, 'reasons': reasons, 'candidate_qc': checked, 'cumulative_duplicates': history,
            'delivery_distribution': {'scope': str(dataset), 'status': aggregate(c['status'] for c in distribution), 'checks': distribution},
            'unchanged_delivery_status': checked['delivery_status'], 'release_ready': False,
            **({'semantic_sampling':checked['semantic_sampling']} if 'semantic_sampling' in checked else {}),
            'customer_actual_acceptance': 'UNKNOWN', 'identity_authenticated': False, 'actual_reading_authenticated': False,
            'input_integrity_checked_before_and_after': True, 'actual_model_requests': 0, 'actual_network_requests': 0,
            'usage_and_cost': {'this_read_only_command_external_cost': 0, 'upstream_review_usage': 'UNKNOWN', 'upstream_review_cost': 'UNKNOWN'},
            'next_release_gate': 'Unchanged engine final inspection of the actual sealed delivery selection, distributions and QC summary; internal PASS cannot override it'}


def _protect(output, roots, inputs):
    if any(output.is_relative_to(Path(root).resolve()) for root in roots) or output in [Path(path).resolve() for path in inputs]:
        raise ValueError('Output must be outside every inspected package and input')
    if output.exists(): raise ValueError('Output already exists; preserve prior evidence')


def write_decision(output, dataset, effective_set, **kwargs):
    roots, _ = _set_inputs(effective_set, dataset); supported = _calibration(kwargs.get('calibration'))
    paths=[]
    for value in kwargs.values():
        if value:paths.extend(value if isinstance(value,(list,tuple)) else [value])
    inputs = [Path(effective_set).resolve()] + [Path(value).resolve() for value in paths]
    _protect(Path(output).resolve(), roots + list(supported['roots']), inputs + list(supported['bindings']))
    result = decide(dataset, effective_set, **kwargs); save_json(output, result); return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--effective-set', type=Path)
    parser.add_argument('--profile', default=DEFAULT_DELIVERY_PROFILE, type=Path)
    parser.add_argument('--reviews', type=Path); parser.add_argument('--sampling-plan', type=Path)
    parser.add_argument('--delivery-sampling-plan',type=Path)
    parser.add_argument('--human-reviews',type=Path,action='append',default=[])
    parser.add_argument('--ai-failures',type=Path,action='append',default=[])
    parser.add_argument('--calibration', type=Path); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare-plan', action='store_true')
    parser.add_argument('--prepare-calibration', action='store_true'); parser.add_argument('--validator')
    args = parser.parse_args(argv)
    try:
        if args.prepare_plan and args.prepare_calibration: raise ValueError('Choose only one preparation mode')
        if args.prepare_calibration:
            if not args.reviews or not args.validator: raise ValueError('Calibration requires actual reviews and a registered validator')
            result = prepare_calibration(args.input, args.reviews, args.validator, args.output)
        elif args.prepare_plan:
            if not args.effective_set: raise ValueError('Plan requires a frozen effective set')
            result = prepare_plan(args.input, args.effective_set, args.output, profile=args.profile, calibration=args.calibration)
        else:
            if not args.effective_set: raise ValueError('Decision requires a frozen effective set')
            result = write_decision(args.output, args.input, args.effective_set, profile=args.profile,
                                    reviews=args.reviews, sampling_plan=args.sampling_plan, calibration=args.calibration,
                                    delivery_sampling_plan=args.delivery_sampling_plan,human_reviews=args.human_reviews,ai_failures=args.ai_failures)
        print(json.dumps({key: result[key] for key in ('internal_batch_decision', 'review_status_counts', 'release_ready', 'reasons', 'status', 'plan_file', 'selected') if key in result}, ensure_ascii=False))
        return {'PASS': 0, 'HOLD': 2, 'FAIL': 1}.get(result.get('internal_batch_decision'), 0)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(json.dumps({'internal_batch_decision': 'FAIL', 'release_ready': False, 'execution_error': str(error)}, ensure_ascii=False)); return 3


if __name__ == '__main__':
    raise SystemExit(main())
