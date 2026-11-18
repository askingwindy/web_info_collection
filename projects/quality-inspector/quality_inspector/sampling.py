"""Frozen, evidence-bound internal sampling. No model request is made by this module.

Sampling selects extra inspections; it never supplies missing per-sample contract
proof. The unchanged delivery inspector remains the release authority. A signed-in
operator or a JSON reviewer identity is not authenticated by these local files.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from webcollect import workspace_json as json
import math
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from webcollect.batch_core import BatchLedger, load_json, file_sha, save_json
from webcollect.planning import object_sha256
from .contract import fingerprint
from .engine import inspect
from .format_checks import catalog, run as format_run
from .profiles import package_files, DEFAULT_DELIVERY_PROFILE
from .reviews import SEMANTIC, intake

VERSION = 'stratified-risk-sampling-1'
DEFAULT_POLICY = {
    'version': VERSION, 'mode': 'stratified', 'seed': 'webcollect-s0-default-1',
    'random_fraction': 0.2, 'minimum_per_stratum': 1,
    'expand_after_issues': 1, 'stop_after_failures': 2,
    'critical_checks': ['privacy', 'terminal_semantics'],
}


def implementation():
    root = Path(__file__).parent
    return {name: file_sha(root / name) for name in ('sampling.py', 'ai_worker.py')}


def producer_implementation():
    import webcollect
    root = Path(webcollect.__file__).parent
    return {name: file_sha(root / name) for name in (
        'collect.py', 'task_generation.py', 'task_contract.py', 'runtime.py',
        'storage.py', 'narrative_revisions.py', 'client_package.py',
        'browser.py', 'snapshot.js', 'history_business.py', 'task_replanning.py',
        'bmi_strategy.py', 'date_strategy.py', 'ascii_art_strategy.py',
        'loan_strategy.py', 'html_table_strategy.py', 'qr_strategy.py', 'qr_pixel.py',
        'placeholder_strategy.py', 'placeholder_pixel.py')}


def policy_load(value=None):
    value = dict(DEFAULT_POLICY if value is None else value)
    if set(value) != set(DEFAULT_POLICY) or value['version'] != VERSION:
        raise ValueError('Exact versioned sampling policy fields required')
    if value['mode'] not in ('stratified', 'full') or not isinstance(value['seed'], str) or not value['seed'].strip():
        raise ValueError('Explicit sampling mode and seed required')
    if type(value['random_fraction']) not in (float, int) or not 0 <= value['random_fraction'] <= 1:
        raise ValueError('random_fraction must be finite within [0,1]')
    for key in ('minimum_per_stratum', 'expand_after_issues', 'stop_after_failures'):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    if (not isinstance(value['critical_checks'], list) or not value['critical_checks']
            or len(value['critical_checks']) != len(set(value['critical_checks']))
            or not set(value['critical_checks']) <= set(SEMANTIC)):
        raise ValueError('critical_checks must name distinct semantic checks')
    return value


def sample_context(sample):
    root = Path(sample['sample_path']); a = load_json(root / 'annotation.json')
    site = None
    for step in a.get('steps', []):
        action = step.get('tool_call', {})
        if action.get('tool_name') == 'open_url':
            site = urlsplit(action.get('arguments', {}).get('url', '')).hostname
            if site: break
    # Customer metadata is inspected by the existing full deterministic QC.
    if not site:
        for parent in root.parents:
            metadata = parent / 'metadata.csv'
            if metadata.is_file():
                with metadata.open(newline='', encoding='utf-8-sig') as stream:
                    rows = [row for row in csv.DictReader(stream) if row.get('sample_id') == a['sample_id']]
                if len(rows) == 1 and rows[0].get('site_id'):
                    site = 'metadata:' + rows[0]['site_id']
                break
    site = site or 'unresolved-site'
    shape = sorted({(step['action']['action_type'], step['action'].get('target_control_type', ''))
                    for step in a.get('steps', []) if step['action']['action_type'] not in ('wait', 'complete')})
    family = sorted(a.get('task_type', []))
    capability = object_sha256({'family': family, 'action_shape': shape})
    return {'site': site, 'task_family': family, 'capability': capability,
            'stratum': object_sha256({'site': site, 'family': family}), 'annotation': a}


def coverage_map():
    rows = [{'requirement': r['id'], 'sources': r['sources'],
             'checker': 'format_checks.sample_check/run',
             'evidence': 'actual annotation/image/tree/batch files and rule-specific errors',
             'automatic_scope': r['rule'], 'boundary': 'literal/schema evidence only; no pixel-semantic inference',
             'required_for_release': r['certainty'] == 'confirmed'} for r in catalog()]
    rows += [{'requirement': name, 'sources': ['需求书§1/4/5/6/7', '需求澄清记录'],
              'checker': 'reviews.intake + coverage_errors; E3 all-frame visual/difference worker',
              'evidence': 'bound annotation/all original frame/tree hashes, every step observation, all five decisions',
              'automatic_scope': 'bindings/coverage/decision validity only',
              'boundary': 'not automatically proved by DOM presence, task generation or random selection; missing -> REVIEW_REQUIRED',
              'required_for_release': True} for name in SEMANTIC]
    clauses = {
        1: ('C01', 'parsed annotation and required field/type checks'),
        2: ('C05/C06', 'exact step files, consecutive names and no extras'),
        3: ('C05/C06', 'safe existing image/tree paths for every step'),
        4: ('C06', 'decoded PNG dimensions and declared screen_resolution'),
        5: ('C05', 'actual ordered integer step IDs'),
        6: ('C11', 'effective page actions exclude wait/complete; explicit short-flow reason'),
        7: ('C08', 'integer point inside nonempty in-viewport target box'),
        8: ('C07/C08', 'resolvable synchronized tree target and literal target text'),
        9: ('C09', 'action/tool equality and documented arguments'),
        10: ('C10', 'every tool success and completion_status != failed'),
        11: ('C10/terminal_semantics', 'explicit final complete plus concrete final-page goal and pixel-visible completion'),
        12: ('C03', 'one to three task_type values in archived enum'),
        13: ('language/visual_alignment', 'actual simplified Chinese, intact prose and Chinese visible page/controls'),
        14: ('C12/visual_alignment', 'literal prohibited tokens plus actual unbroken narrative'),
        15: ('C12/visual_alignment', 'literal collection-process tokens plus actual narrative review'),
        16: ('visual_alignment', 'every adjacent frame/action/step_result transition'),
        17: ('privacy', 'actual screenshots/text and source/account declaration under clarification'),
    }
    rows += [{'requirement': '需求书§7.' + str(number), 'sources': ['需求书§7.' + str(number), '附件A/B', '需求澄清记录'],
              'checker': checker, 'evidence': evidence,
              'automatic_scope': 'literal structural tests' if number not in (11,13,14,15,16,17) else 'structural/literal clues only',
              'boundary': 'does not authenticate real-world truth' if number not in (11,13,14,15,16,17) else 'requires bound whole-trajectory review; missing evidence remains REVIEW_REQUIRED',
              'required_for_release': True} for number,(checker,evidence) in clauses.items()]
    rows += [
        {'requirement': 'four-route-cumulative-duplicates', 'sources': ['需求书§6'],
         'checker': 'duplicates.analyze_inputs', 'evidence': 'explicit effective set plus current candidate index/pairs',
         'automatic_scope': 'exact image/sequence and configured dHash/SimHash routes',
         'boundary': 'zero hits does not prove substantive semantic differences', 'required_for_release': True},
        {'requirement': 'delivery-documents-and-distributions', 'sources': ['需求书§2/3/5/7'],
         'checker': 'engine.inspect + profiles.delivery_document_review',
         'evidence': 'metadata/distribution/source and exact payload-bound documentary decisions',
         'automatic_scope': 'file structure, counts, checksums and consistency',
         'boundary': 'documentary facts need actual evidence-bound review; customer acceptance remains UNKNOWN',
         'required_for_release': True},
        {'requirement': 'truth-and-visible-completion', 'sources': ['需求书§1/4/6', '需求澄清记录'],
         'checker': 'engine deterministic checks plus visual_alignment/terminal_semantics/privacy review',
         'evidence': 'original screenshots, actions, synchronized trees and actual review',
         'automatic_scope': 'structural consistency only',
         'boundary': 'file integrity does not authenticate real-world truth; pixel-visible state and privacy need review',
         'required_for_release': True},
        {'requirement': '需求书§5中文与导航控件', 'sources': ['需求书§5', '附件A', '需求澄清记录：控件语言与页面语言一致'],
         'checker': 'language review', 'evidence': 'all original visible screenshots and page/control language observations',
         'automatic_scope': 'ui_language=zh enum is a clue only',
         'boundary': 'DOM letter ratios or ui_language cannot prove page/control language consistency; inspect originals, allowing technical terms in their original spelling', 'required_for_release': True},
        {'requirement': '需求书§6有效操作/终态/实质差异', 'sources': ['需求书§6', '需求澄清记录'],
         'checker': 'C11/C10 + visual_alignment/terminal_semantics/substantive_difference',
         'evidence': 'effective actions, every adjacent original frame, terminal frame and frozen nearest-task comparison set',
         'automatic_scope': 'step counts, literal terminal fields and four duplicate routes',
         'boundary': 'no padding, meaningless reversal or parameter-only variants accepted by sampling', 'required_for_release': True},
        {'requirement': '附件A/B及澄清优先级', 'sources': ['附件A', '附件B', '需求澄清记录'],
         'checker': 'installed contract authority + C01-C17 + reviews',
         'evidence': 'version-bound four authority documents and the actual delivered annotation/tree/action bytes',
         'automatic_scope': 'field/action/coordinate rules; wait/complete excluded; four-route zero-hit rule',
         'boundary': 'clarifications override replay, site counting, account declarations and completion interpretation; customer 2% human acceptance is separate',
         'required_for_release': True},
    ]
    return {'version': 'contract-check-coverage-1', 'contract_sha256': fingerprint()[1],
            'rules': rows, 'customer_actual_acceptance': 'UNKNOWN'}


def _outside(path, dataset):
    if Path(path).resolve().is_relative_to(Path(dataset).resolve()):
        raise ValueError('Sampling outputs/ledger must be outside candidates')


def _protected(dataset, effective_set=None, calibration=None):
    roots = [Path(dataset).resolve()]
    if effective_set:
        manifest = load_json(effective_set)
        for item in manifest.get('packages', []):
            root = Path(item['path'])
            roots.append(root.resolve() if root.is_absolute() else (Path(effective_set).resolve().parent/root).resolve())
    if calibration:
        value = load_json(calibration); roots.append(Path(value['dataset']).resolve())
    return roots


def _destinations(paths, roots):
    for path in paths:
        for root in roots: _outside(path, root)


def _assert_binding(plan):
    unsigned = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if object_sha256(unsigned) != plan.get('plan_sha256'):
        raise ValueError('Sampling plan content/hash changed')


def verify_plan(plan):
    _assert_binding(plan)
    if plan.get('schema_version') != 'webcollect-sampling-plan-1': raise ValueError('Invalid sampling plan')
    marker = Path(plan['state_directory']) / (plan['plan_sha256'] + '.superseded.json')
    if marker.exists(): raise ValueError('Sampling plan superseded by expansion/stop; follow ' + load_json(marker)['successor'])
    if plan['implementation_sha256'] != implementation(): raise ValueError('Sampling implementation changed; freeze plan again')
    if plan['producer_implementation_sha256'] != producer_implementation():
        raise ValueError('Producer implementation changed; freeze plan again')
    if plan['contract_sha256'] != fingerprint()[1]: raise ValueError('Contract changed; freeze plan again')
    if file_sha(plan['profile']['path']) != plan['profile']['sha256']: raise ValueError('Frozen QC profile changed')
    if package_files(plan['dataset']) != plan['candidate_package_sha256']:
        raise ValueError('Candidate set changed; freeze plan again')
    effective = plan.get('effective_set')
    if effective:
        if file_sha(effective['path']) != effective['sha256']: raise ValueError('Effective set manifest changed')
        manifest = load_json(effective['path'])
        for item in manifest['packages']:
            root = Path(item['path'])
            if not root.is_absolute(): root = Path(effective['path']).parent / root
            if package_files(root) != item['package_files_sha256']: raise ValueError('Effective set bytes changed')
    calibration = plan.get('calibration')
    if calibration and file_sha(calibration['path']) != calibration['sha256']:
        raise ValueError('Calibration evidence changed')
    expansion = plan.get('expansion')
    if expansion and file_sha(expansion['review_evidence']['path']) != expansion['review_evidence']['sha256']:
        raise ValueError('Expansion review evidence changed')
    policy_load(plan['policy'])
    return plan


def calibrate(dataset, reviews, output):
    """Derive stability evidence from actual, current, fully passing review records.

    Accepts the existing qc-review-2 provenance rules; does not authenticate who
    authored them. No hand-entered known-site list is accepted by sampling.
    """
    _outside(output, dataset)
    formats = format_run(None, dataset); contract = fingerprint()[1]
    accepted, errors, _ = intake(reviews, formats['samples'], contract)
    if errors: raise ValueError('Invalid calibration reviews: ' + json.dumps(errors, ensure_ascii=False))
    valid = [row for row in formats['samples'] if row.get('confirmed_format_pass') and
             row.get('sample_id') in accepted and
             all(c['status'] == 'PASS' for c in accepted[row['sample_id']]['checks'].values())]
    if not valid: raise ValueError('No fully reviewed passing calibration evidence')
    value = {'schema_version': 'webcollect-sampling-calibration-1', 'dataset': str(Path(dataset).resolve()),
             'candidate_package_sha256': package_files(dataset), 'reviews': {'path': str(Path(reviews).resolve()), 'sha256': file_sha(reviews)},
             'sample_ids': sorted(row['sample_id'] for row in valid), 'contract_sha256': contract,
             'producer_implementation_sha256': producer_implementation(), 'implementation_sha256': implementation(),
             'identity_authenticated': False, 'actual_reading_authenticated': False}
    save_json(output, value); return {'calibration_file': str(Path(output).resolve()), 'calibrated_samples': len(valid)}


def _calibration(path):
    if path is None: return set(), set(), False, None
    value = load_json(path)
    if value.get('schema_version') != 'webcollect-sampling-calibration-1': raise ValueError('Invalid calibration')
    if package_files(value['dataset']) != value['candidate_package_sha256']: raise ValueError('Calibration sample bytes changed')
    if file_sha(value['reviews']['path']) != value['reviews']['sha256']: raise ValueError('Calibration reviews changed')
    if value['contract_sha256'] != fingerprint()[1]: raise ValueError('Calibration contract changed; explicit reassessment required')
    formats = format_run(None, value['dataset'])
    accepted, errors, _ = intake(value['reviews']['path'], formats['samples'], value['contract_sha256'])
    if errors: raise ValueError('Invalid calibration review bindings')
    expected = set(value['sample_ids']); sites = set(); capabilities = set()
    for row in formats['samples']:
        sid = row.get('sample_id')
        if sid not in expected: continue
        record = accepted.get(sid)
        if not row.get('confirmed_format_pass') or not record or any(c['status'] != 'PASS' for c in record['checks'].values()):
            raise ValueError('Calibration must retain complete passing review evidence')
        context = sample_context(row); sites.add(context['site']); capabilities.add((context['site'], context['capability']))
        expected.remove(sid)
    if expected: raise ValueError('Calibration sample set missing')
    changed = value['producer_implementation_sha256'] != producer_implementation() or value['implementation_sha256'] != implementation()
    return sites, capabilities, changed, {'path': str(Path(path).resolve()), 'sha256': file_sha(path)}


def freeze_rows(rows, policy):
    """Pure reproducible selection; identities and risk reasons come from inspected bytes."""
    groups = defaultdict(list)
    for row in rows:
        if row['automatic_status'] == 'PASS': groups[row['stratum']].append(row)
    selected = set(); random_ids = set()
    for key, values in sorted(groups.items()):
        ordered = sorted(values, key=lambda row: (hashlib.sha256(
            (policy['seed'] + '\0' + key + '\0' + row['sample_id']).encode()).hexdigest(), row['sample_id']))
        count = len(values) if policy['mode'] == 'full' else min(len(values), max(policy['minimum_per_stratum'], math.ceil(len(values)*policy['random_fraction'])))
        random_ids.update(row['sample_id'] for row in ordered[:count])
    for row in rows:
        row['random_selected'] = row['sample_id'] in random_ids
        row['risk_required'] = bool(row['risk_reasons'])
        row['selected'] = row['automatic_status'] == 'PASS' and (row['random_selected'] or row['risk_required'])
        row['selection_reasons'] = (['full-review-policy' if policy['mode'] == 'full' else 'stratified-random'] if row['random_selected'] else []) + row['risk_reasons']
        row['ai_status'] = 'NOT_REVIEWED'
        row['required_evidence_status'] = 'REVIEW_REQUIRED'
        if row['selected']: selected.add(row['sample_id'])
    return rows


def prepare(ledger, dataset, output, *, policy=None, effective_set=None, profile=None, calibration=None):
    from .ai_worker import prepare as worker_prepare
    dataset = Path(dataset).resolve(); output = Path(output).resolve()
    _destinations([output, ledger.path], _protected(dataset, effective_set, calibration))
    profile = Path(profile or DEFAULT_DELIVERY_PROFILE).resolve()
    policy = policy_load(policy)
    before = package_files(dataset)
    identity = {'dataset': str(dataset), 'files': before, 'policy': policy,
                'implementation': implementation(), 'producer': producer_implementation(),
                'effective_set': file_sha(effective_set) if effective_set else None,
                'calibration': file_sha(calibration) if calibration else None,
                'profile': file_sha(profile)}
    jid = ledger.enqueue('qc-sampling-prepare', identity); existing = ledger.get(jid)
    if existing['state'] == 'done':
        saved = existing['result']; verify_plan(load_json(saved['plan_file'])); return saved
    job = ledger.claim('qc-sampling-prepare', job_id=jid)
    if not job: raise ValueError('Sampling preparation already leased or requires recovery')
    try:
        automatic = inspect(None, dataset, profile=profile, inspection_stage='payload')
        ledger.heartbeat(job)
        preliminary = worker_prepare(ledger, dataset, output / 'automatic-prefilter', effective_set=effective_set, sample_ids=set())
        prefilter = load_json(preliminary['queue_file'])
        blocked = {row['sample_id'] for row in prefilter['mechanically_blocked']}
        known_sites, known_capabilities, code_changed, calibration_binding = _calibration(calibration)
        rows = []
        for sample in automatic['samples']:
            ledger.heartbeat(job)
            sid = sample['sample_id']; mechanics = [c for c in sample['checks'] if not c['rule_id'].startswith('REVIEW_')]
            status = 'FAIL' if sid in blocked or any(c['status'] == 'FAIL' for c in mechanics) else 'REVIEW_REQUIRED' if any(c['status'] != 'PASS' for c in mechanics) else 'PASS'
            try: context = sample_context(sample)
            except (OSError, ValueError, KeyError, TypeError): context = {'site': 'unresolved-site', 'task_family': [], 'capability': 'invalid', 'stratum': 'invalid', 'annotation': {}}
            a = context.pop('annotation'); reasons = []
            if context['site'] not in known_sites: reasons.append('new-or-uncalibrated-site')
            if (context['site'], context['capability']) not in known_capabilities: reasons.append('new-or-uncalibrated-capability')
            if code_changed: reasons.append('relevant-code-changed-since-calibration')
            if a.get('risk_level') != 'normal': reasons.append('sensitive-or-unknown-risk')
            if a.get('short_flow'): reasons.append('short-flow')
            if a.get('completion_status') != 'success': reasons.append('exception-or-incomplete-completion')
            if any(s.get('exception_evidence') or s.get('tool_result', {}).get('status') != 'success' for s in a.get('steps', [])):
                reasons.append('recorded-exception')
            rows.append({'sample_id': sid, 'sample_path': sample['sample_path'], **context,
                         'automatic_status': status, 'risk_reasons': reasons,
                         'automatic_checks': [{'rule_id': c['rule_id'], 'status': c['status']} for c in mechanics]})
        rows = freeze_rows(rows, policy)
        value = {'schema_version': 'webcollect-sampling-plan-1', 'dataset': str(dataset),
                 'candidate_package_sha256': before, 'candidate_set_sha256': object_sha256(before),
                 'original_denominator': len(rows), 'policy': policy, 'policy_sha256': object_sha256(policy),
                 'implementation_sha256': implementation(), 'producer_implementation_sha256': producer_implementation(),
                 'contract_sha256': fingerprint()[1], 'rows': rows,
                 'profile': {'path': str(profile), 'sha256': file_sha(profile)},
                 'state_directory': str(output / 'sampling-state'),
                 'effective_set': {'path': str(Path(effective_set).resolve()), 'sha256': file_sha(effective_set)} if effective_set else None,
                 'calibration': calibration_binding, 'automatic_qc_status': automatic['status'],
                 'batch_automatic_checks': [c for c in automatic['dataset_checks'] if c['rule_id'] != 'DELIVERY_DOCUMENT_REVIEW'],
                 'automatic_report': str(output / 'automatic-qc.json'), 'prefilter_queue': preliminary['queue_file'],
                 'coverage_map': coverage_map(), 'release_ready': False,
                 'release_rule': 'Existing delivery engine requires every necessary sample/document check to have evidence; sampling never supplies approval.',
                 'actual_model_requests': 0, 'customer_acceptance': 'UNKNOWN'}
        value['plan_sha256'] = object_sha256(value)
        verify_plan(value)
        save_json(output / 'automatic-qc.json', automatic)
        path = output / ('sampling-plan-' + value['plan_sha256'][:20] + '.json'); save_json(path, value)
        result = {'plan_file': str(path), 'original_denominator': len(rows),
                  'automatically_blocked': sum(r['automatic_status'] != 'PASS' for r in rows),
                  'random_selected': sum(r['random_selected'] for r in rows),
                  'risk_required': sum(r['risk_required'] for r in rows),
                  'selected_samples': sum(r['selected'] for r in rows), 'model_requests': ledger.summary()['model_requests'],
                  'release_ready': False}
        ledger.finish(job, result=result); return result
    except Exception as error:
        from .layout import discover
        receipt = {'status': 'REVIEW_REQUIRED', 'dataset': str(dataset),
                   'candidate_package_sha256': before, 'original_denominator': len(discover(dataset).annotations),
                   'reason': type(error).__name__ + ': ' + str(error), 'release_ready': False,
                   'model_requests': ledger.summary()['model_requests']}
        failure_path = output / ('preparation-failure-' + jid[:20] + '.json')
        save_json(failure_path, receipt)
        ledger.finish(job, 'review_required', result={'failure_receipt': str(failure_path)}, error=type(error).__name__); raise


def enqueue(ledger, plan_path, output):
    from .ai_worker import prepare as worker_prepare
    plan = verify_plan(load_json(plan_path))
    _destinations([output, ledger.path], _protected(plan['dataset'],
        plan['effective_set']['path'] if plan.get('effective_set') else None,
        plan['calibration']['path'] if plan.get('calibration') else None))
    if plan.get('expansion', {}).get('stop'):
        raise ValueError('Sampling stop condition active; resolve the evidence-bound failure before dispatch')
    if ledger.config.get('model') is None: raise ValueError('Model branch disabled; retain plan for session review or use a separately budgeted model ledger')
    selected = {row['sample_id'] for row in plan['rows'] if row['selected']}
    return worker_prepare(ledger, plan['dataset'], output,
        effective_set=plan['effective_set']['path'] if plan.get('effective_set') else None,
        sample_ids=selected, sampling_binding={'path': str(Path(plan_path).resolve()), 'sha256': object_sha256(plan)})


def report(plan_path, output, *, reviews=None, profile=None):
    plan = verify_plan(load_json(plan_path))
    _destinations([output], _protected(plan['dataset'],
        plan['effective_set']['path'] if plan.get('effective_set') else None,
        plan['calibration']['path'] if plan.get('calibration') else None))
    if profile and file_sha(profile) != plan['profile']['sha256']: raise ValueError('Report profile differs from frozen sampling profile')
    profile = plan['profile']['path']
    # The existing intake rejects synthetic worker exports, stale pixels and incomplete observations.
    checked = inspect(None, plan['dataset'], reviews=reviews, profile=profile, inspection_stage='payload')
    accepted, errors, _ = intake(reviews, format_run(None, plan['dataset'])['samples'], plan['contract_sha256'])
    rows = []; sources = Counter()
    for original in plan['rows']:
        row = dict(original); review = accepted.get(row['sample_id'])
        if review:
            states = [c['status'] for c in review['checks'].values()]
            row['required_evidence_status'] = 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in states else 'PASS'
            kind = review['reviewer']['kind']; sources[(kind, review['reviewer']['name'])] += 1
            row['ai_status'] = row['required_evidence_status'] if kind == 'ai' else 'NOT_REVIEWED'
            row['review_source'] = review['reviewer']
        rows.append(row)
    selected = [r for r in rows if r['selected']]
    summary = {'schema_version': 'webcollect-sampling-report-1', 'plan_sha256': plan['plan_sha256'],
               'original_denominator': plan['original_denominator'], 'rows': rows,
               'automatically_blocked': sum(r['automatic_status'] != 'PASS' for r in rows),
               'random_selected': sum(r['random_selected'] for r in rows),
               'risk_required': sum(r['risk_required'] for r in rows),
               'selected_samples': len(selected),
               'actual_ai_reviewed': sum(r['ai_status'] != 'NOT_REVIEWED' for r in rows),
               'not_ai_reviewed': sum(r['ai_status'] == 'NOT_REVIEWED' for r in rows),
               'selected_unresolved': sum(r['required_evidence_status'] == 'REVIEW_REQUIRED' for r in selected),
               'failed': sum(r['required_evidence_status'] == 'FAIL' for r in rows),
               'required_evidence_pending': sum(r['required_evidence_status'] == 'REVIEW_REQUIRED' for r in rows),
               'reviewer_sources': [{'kind': k, 'name': n, 'samples': count} for (k,n),count in sorted(sources.items())],
               'invalid_records': errors,
               'production_stop': bool(plan.get('expansion', {}).get('stop')),
               'sampling_complete': not plan.get('expansion', {}).get('stop') and bool(selected) and not errors and all(r['required_evidence_status'] == 'PASS' for r in selected),
               'independent_qc_status': checked['status'], 'release_ready': False,
               'release_reason': 'Payload-stage report; final sealed package plus all required evidence must pass unchanged delivery QC.',
               'risk_defect_rate_is_not_unbiased_population_estimate': True,
               'customer_acceptance': 'UNKNOWN'}
    save_json(output, summary); return summary


def expand(plan_path, reviews, output):
    plan = load_json(plan_path); _assert_binding(plan)
    marker_path = Path(plan['state_directory']) / (plan['plan_sha256'] + '.superseded.json')
    if marker_path.exists():
        marker = load_json(marker_path); successor = marker.get('successor_plan')
        if (not isinstance(successor, dict)
                or marker.get('successor') != str(Path(output).resolve())
                or marker.get('successor_sha256') != successor.get('plan_sha256')
                or successor.get('expansion', {}).get('parent_plan_sha256') != plan['plan_sha256']
                or marker.get('review_evidence') != {'path': str(Path(reviews).resolve()), 'sha256': file_sha(reviews)}):
            raise ValueError('Existing expansion hold binds different successor/review evidence; do not remove the hold')
        verify_plan(successor)
        _destinations([output], _protected(successor['dataset'],
            successor['effective_set']['path'] if successor.get('effective_set') else None,
            successor['calibration']['path'] if successor.get('calibration') else None))
        save_json(output, successor)
        return {'plan_file': str(Path(output).resolve()), **successor['expansion'],
                'resumed_from_persistent_hold': True}
    plan = verify_plan(plan)
    _destinations([output], _protected(plan['dataset'],
        plan['effective_set']['path'] if plan.get('effective_set') else None,
        plan['calibration']['path'] if plan.get('calibration') else None))
    accepted, errors, _ = intake(reviews, format_run(None, plan['dataset'])['samples'], plan['contract_sha256'])
    if errors: raise ValueError('Invalid issue review evidence: ' + json.dumps(errors, ensure_ascii=False))
    issues = defaultdict(list); critical = []; failed = []
    for row in plan['rows']:
        if not row['selected']: continue
        record = accepted.get(row['sample_id'])
        if not record: continue
        bad = [name for name, c in record['checks'].items() if c['status'] != 'PASS']
        if bad: issues[row['stratum']].append({'sample_id': row['sample_id'], 'checks': bad})
        failures = [name for name, c in record['checks'].items() if c['status'] == 'FAIL']
        if failures: failed.append(row['sample_id'])
        if set(failures) & set(plan['policy']['critical_checks']): critical.append(row['sample_id'])
    strata = {s for s, items in issues.items() if len(items) >= plan['policy']['expand_after_issues']}
    changed = []; value = dict(plan); value.pop('plan_sha256')
    for row in plan['rows']:
        row = dict(row)
        if row['stratum'] in strata and row['automatic_status'] == 'PASS':
            row['selected'] = True
            row['selection_reasons'] = sorted(set(row['selection_reasons'] + ['issue-triggered-stratum-expansion']))
            changed.append(row['sample_id'])
        value.setdefault('_expanded_rows', []).append(row)
    value['rows'] = value.pop('_expanded_rows')
    value['expansion'] = {'parent_plan_sha256': plan['plan_sha256'],
        'review_evidence': {'path': str(Path(reviews).resolve()), 'sha256': file_sha(reviews)},
        'issues_by_stratum': dict(issues), 'expanded_strata': sorted(strata), 'expanded_samples': sorted(changed),
        'stop': bool(critical) or len(failed) >= plan['policy']['stop_after_failures'],
        'stop_reasons': (['critical-review-failure'] if critical else []) + (['failure-count-threshold'] if len(failed) >= plan['policy']['stop_after_failures'] else []),
        'critical_failed_samples': critical, 'failed_samples': failed,
        'action': 'hold related batch; resolve before additional collection or release'}
    value['plan_sha256'] = object_sha256(value)
    if strata or critical or len(failed) >= plan['policy']['stop_after_failures']:
        # Hold the old plan before publication. A crash after this atomic marker
        # must fail closed, even if the successor file has not appeared yet.
        # Retain the entire successor in the receipt for explicit recovery.
        save_json(Path(plan['state_directory']) / (plan['plan_sha256'] + '.superseded.json'),
                  {'successor': str(Path(output).resolve()), 'successor_sha256': value['plan_sha256'],
                   'stop': value['expansion']['stop'], 'review_evidence': value['expansion']['review_evidence'],
                   'successor_plan': value})
    save_json(output, value)
    return {'plan_file': str(Path(output).resolve()), **value['expansion']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'enqueue', 'report', 'expand', 'calibrate'):
        p = sub.add_parser(name); p.add_argument('--output', required=True, type=Path)
        if name in ('prepare', 'enqueue'):
            p.add_argument('--config', required=True, type=Path); p.add_argument('--ledger', required=True, type=Path)
        if name in ('prepare', 'calibrate'): p.add_argument('--input', required=True, type=Path)
        if name == 'prepare':
            p.add_argument('--policy', type=Path); p.add_argument('--effective-set', type=Path)
            p.add_argument('--calibration', type=Path); p.add_argument('--profile', type=Path)
        if name in ('enqueue', 'report', 'expand'): p.add_argument('--plan', required=True, type=Path)
        if name in ('expand', 'calibrate'): p.add_argument('--reviews', required=True, type=Path)
        if name == 'report': p.add_argument('--reviews', type=Path); p.add_argument('--profile', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in ('prepare', 'enqueue'):
            ledger = BatchLedger(args.ledger, load_json(args.config))
            result = prepare(ledger, args.input, args.output, policy=load_json(args.policy) if args.policy else None,
                             effective_set=args.effective_set, profile=args.profile, calibration=args.calibration) if args.command == 'prepare' else enqueue(ledger, args.plan, args.output)
        elif args.command == 'report': result = report(args.plan, args.output, reviews=args.reviews, profile=args.profile)
        elif args.command == 'expand': result = expand(args.plan, args.reviews, args.output)
        else: result = calibrate(args.input, args.reviews, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False)); return 2


if __name__ == '__main__': raise SystemExit(main())
