"""Frozen cumulative input sets; mechanical checks never grant release readiness."""
import csv
import hashlib
from webcollect import workspace_json as json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .contract import digest, fingerprint
from .category_coverage import parent_category, category_coverage
from .duplicates import analyze_inputs, analysis_error, summarize
from .format_checks import run as format_run
from .layout import discover
from .profiles import load as load_profile, package_files, DEFAULT_DELIVERY_PROFILE
from .version_compare import compare_versions


QUALITY_BATCH_SIZE = 5000


def _quality_batch_ids(value):
    if (not isinstance(value, list) or not value or any(not isinstance(sid, str) or not sid.strip() for sid in value)
            or len(value) != len(set(value))):
        raise ValueError('Quality batch membership must be a nonempty list of unique sample IDs')
    return sorted(value)


def build_set_manifest(package_paths, *, quality_batch_ids=None, application_registry=None, application_capacity_policy=None):
    """Return facts, not approval. Caller persists this versioned manifest explicitly."""
    paths = [Path(path).resolve() for path in package_paths]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Cumulative set needs unique package paths')
    if any(a != b and (a.is_relative_to(b) or b.is_relative_to(a)) for a in paths for b in paths):
        raise ValueError('Cumulative package roots must not overlap')
    result = {'schema_version': 'qc-cumulative-set',
            'packages': [{'path': str(path), 'package_files_sha256': package_files(path)} for path in paths],
            'scope': 'explicit effective delivery versions only; excludes superseded copies',
            'not_an_acceptance': True}
    if application_capacity_policy is not None:
        if application_capacity_policy != 'flexible-total-200000-v1':
            raise ValueError('Unknown application capacity policy')
        result['application_capacity_policy'] = application_capacity_policy
    if quality_batch_ids is not None:
        result['quality_batch_ids'] = _quality_batch_ids(quality_batch_ids)
    if application_registry is not None:
        path=Path(application_registry).resolve()
        result['application_registry']={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def _check_quality_batch(ids, categories, short_ids, duplicate, targets):
    """The explicitly frozen batch is the denominator; the other effective IDs are history."""
    count = len(ids)
    missing = set(ids) - categories.keys()
    if missing:
        raise ValueError('Quality batch IDs missing from effective metadata: ' + ', '.join(sorted(missing)[:10]))
    if (duplicate['summary'].get('analysis_status') != 'COMPLETE'
            or duplicate['summary'].get('unadjudicated_pair_count') != 0):
        raise ValueError('Quality batch requires a complete four-route scan with no unresolved pairs')
    distribution = Counter(parent_category(categories[sid]) for sid in ids)
    short = len(short_ids.intersection(ids))
    resolution = summarize(duplicate, ids)
    routes = resolution['current_route_pair_counts']
    errors = []
    if count != QUALITY_BATCH_SIZE:
        errors.append('quality batch requires exactly 5000 effective samples')
    if short / count > targets['max_short_flow_share']:
        errors.append('quality batch short-flow share exceeds the limit')
    if max(distribution.values()) / count > targets['max_category_share']:
        errors.append('quality batch category share exceeds the limit')
    if (not resolution['sample_rate_within_requested_limit'] or resolution['unadjudicated_pair_count'] != 0
            or routes['route1'] or routes['route2']):
        errors.append('quality batch four-route duplicate check failed')
    return {'status': 'FAIL' if errors else 'PASS', 'errors': errors, 'sample_count': count,
            'short_flow_count': short, 'categories': dict(distribution), 'route_pair_counts': routes,
            'near_duplicate_sample_rate': resolution['near_duplicate_sample_rate'],
            'affected_sample_ids': resolution['affected_current_sample_ids'],
            'unadjudicated_pair_count': resolution['unadjudicated_pair_count']}


def inspect_set(manifest, profile=None, *, cache=None, verify_exhaustive=False):
    """Check declared packages as one set; no sample/doc review is inferred.

    Production/planning may use mechanical_status for duplicate/distribution
    screening. Final release still requires engine.inspect on the final actual
    customer directory with valid actual reviews and final report checks.
    """
    if isinstance(manifest, (str, Path)):
        manifest_path = Path(manifest).resolve()
        raw = json.loads(manifest_path.read_text()); base = manifest_path.parent
        if cache and Path(cache).resolve() == manifest_path:
            raise ValueError('Cache must not overwrite the frozen manifest')
    else:
        raw = manifest; base = Path.cwd()
    if not isinstance(raw, dict) or raw.get('schema_version') not in ('qc-cumulative-set','qc-cumulative-set-1') or not isinstance(raw.get('packages'), list) or not raw['packages']:
        raise ValueError('Expected a nonempty qc-cumulative-set manifest')
    versions = compare_versions(raw, base=base)
    effective_paths = {Path(row['sample_path']) for row in versions['effective_samples']}
    selected = load_profile(profile or DEFAULT_DELIVERY_PROFILE)
    if cache and Path(cache).resolve() == Path(selected['path']):
        raise ValueError('Cache must not overwrite the selected profile')
    if selected['configuration']['scope'] != 'delivery':
        raise ValueError('Cumulative checking needs an explicit delivery profile')
    targets = selected['configuration']['targets']; errors = []; paths = []; snapshots = {}; annotations = []
    errors.extend(versions['errors'])
    samples = []; rows = []; packages = []; sites = {}; uri_owners = {}; ids = set(); active_sites = set()
    mapped_categories = {}
    contract, contract_hash = fingerprint()
    if selected['configuration']['attachments'] != contract['attachments']:
        errors.append({'reason': 'Profile attachments differ from installed authority'})
    for item in raw['packages']:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('package_files_sha256'), dict):
            raise ValueError('Each cumulative package must have a path and complete file hashes')
        root = Path(item['path']); root = (base / root).resolve() if not root.is_absolute() else root.resolve()
        if root in paths or any(root.is_relative_to(other) or other.is_relative_to(root) for other in paths):
            raise ValueError('Duplicate or overlapping cumulative input roots')
        paths.append(root)
        if cache and Path(cache).resolve().is_relative_to(root):
            raise ValueError('Cache must be outside every inspected package')
        actual = package_files(root); snapshots[str(root)] = actual
        if actual != item['package_files_sha256']:
            errors.append({'package': str(root), 'reason': 'frozen package hash set differs from actual files'})
        formats = format_run(None, root); layout = discover(root)
        package_errors = formats['package_errors'] + [row for sample in formats['samples'] for row in sample['errors']] + [row for batch in formats['batches'] for row in batch['errors']]
        packages.append({'path': str(root), 'sample_count': len(formats['samples']),
                         'format_status': 'FAIL' if package_errors else 'PASS', 'errors': package_errors})
        errors.extend({'package': str(root), 'reason': row['message']} for row in package_errors)
        for sample in formats['samples']:
            if Path(sample['sample_path']).resolve() not in effective_paths:
                continue
            sid = sample.get('sample_id')
            if not isinstance(sid, str) or not sid or sid in ids:
                errors.append({'package': str(root), 'reason': 'missing or repeated sample_id: ' + str(sid)})
            if isinstance(sid, str): ids.add(sid)
            samples.append(sample)
        annotations.extend(path for path in layout.annotations if path.parent.resolve() in effective_paths)
        try:
            with (root / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
                local_rows = list(csv.DictReader(stream))
            effective_ids = {row['sample_id'] for row in versions['effective_samples'] if row['package'] == str(root)}
            rows.extend(row for row in local_rows if row['sample_id'] in effective_ids)
            listing = json.loads((root / 'site-list.json').read_text())
            local_sites = {row['site_id']: row for row in listing['sites']}
            assignments = {row['sample_id']: row['site_id'] for row in listing['samples']}
            local_ids = {sample['sample_id'] for sample in formats['samples']}
            metadata_ids = [row.get('sample_id') for row in local_rows]
            metadata_counts = Counter(metadata_ids)
            if len(metadata_ids) != len(set(metadata_ids)) or set(metadata_ids) != local_ids:
                errors.append({'package': str(root), 'reason': 'metadata IDs must cover local samples exactly once'})
            if (listing.get('schema_version') != 'webcollect-site-list-1'
                    or len(local_sites) != len(listing['sites']) or len(assignments) != len(listing['samples'])
                    or set(assignments) != local_ids):
                errors.append({'package': str(root), 'reason': 'site-list population must cover local samples exactly once'})
            for row in local_rows:
                if row['sample_id'] in effective_ids:
                    active_sites.add(row['site_id'])
                site = local_sites.get(row['site_id'])
                if not site or site.get('site_category') != row['site_category'] or assignments.get(row['sample_id']) != row['site_id']:
                    errors.append({'package': str(root), 'reason': 'site/category/sample mapping differs: ' + row['sample_id']})
                elif row['sample_id'] in effective_ids and metadata_counts[row['sample_id']] == 1:
                    mapped_categories[row['sample_id']] = parent_category(site.get('site_category'))
            for sid, site in local_sites.items():
                uri = urlsplit(site['uri'])
                if uri.scheme not in ('http', 'https') or not uri.hostname or uri.username or uri.password:
                    errors.append({'package': str(root), 'reason': 'invalid site URI: ' + str(sid)})
                assigned = {sample_id for sample_id, site_id in assignments.items() if site_id == sid}
                members = site.get('sample_ids')
                if not isinstance(members, list) or len(members) != len(set(members)) or set(members) != assigned:
                    errors.append({'package': str(root), 'reason': 'site membership differs: ' + str(sid)})
                identity = (site['uri'], parent_category(site['site_category']))
                if sid in sites and sites[sid] != identity:
                    errors.append({'package': str(root), 'reason': 'site identity/category changes across packages: ' + sid})
                if site['uri'] in uri_owners and uri_owners[site['uri']] != sid:
                    errors.append({'package': str(root), 'reason': 'same URI has multiple site IDs'})
                sites[sid] = identity; uri_owners[site['uri']] = sid
        except (OSError, ValueError, KeyError, TypeError, AttributeError, csv.Error) as error:
            errors.append({'package': str(root), 'reason': 'cumulative metadata/source error: ' + str(error)})
    batch_ids = _quality_batch_ids(raw['quality_batch_ids']) if 'quality_batch_ids' in raw else None
    categories = Counter(parent_category(row.get('site_category')) for row in rows); resolutions = set(); short = 0
    coverage = category_coverage(Counter(mapped_categories.values()), selected['configuration'])
    if coverage['status'] == 'FAIL':
        errors.append({'rule_id': 'FORMAL_CATEGORY_COVERAGE',
                       'reason': 'Formal corpus missing required site categories: ' + ', '.join(coverage['missing']),
                       'missing_categories': coverage['missing']})
    short_ids = set()
    batch_members = set(batch_ids or ())
    task_types, action_types, lengths = Counter(), Counter(), Counter()
    for path in annotations:
        try:
            annotation = json.loads(path.read_text())
            resolutions.add(tuple(annotation['device_info']['screen_resolution'])); short += int(annotation.get('short_flow') is True)
            if annotation.get('sample_id') in batch_members:
                if annotation.get('short_flow') is True:
                    short_ids.add(annotation['sample_id'])
                actions = [step['action']['action_type'] for step in annotation['steps']]
                task_types.update(annotation['task_type'])
                action_types.update(actions)
                lengths[str(sum(action not in ('wait', 'complete') for action in actions))] += 1
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({'sample': str(path), 'reason': str(error)})
    count = len(samples); share = max(categories.values(), default=0) / count if count else 0
    capacity_policy = raw.get('application_capacity_policy', 'flexible-total-200000-v1')
    if capacity_policy not in ('legacy-per-application-500-v1', 'flexible-total-200000-v1'):
        raise ValueError('Unknown application capacity policy')
    # Old manifest labels remain provenance; current capacity has no site quota.
    application_limit = None
    application_counts = Counter(); application_categories = {}; application_errors=[]
    try:
        from .application_capacity import application_key
        registry=None
        if raw.get('application_registry'):
            from site_planner.site_pool import SitePool
            ref=raw['application_registry']; registry_path=Path(ref['path'])
            if hashlib.sha256(registry_path.read_bytes()).hexdigest()!=ref['sha256']: raise ValueError('Application registry binding changed')
            registry=SitePool(registry_path,readonly=True)
        for row in rows:
            aid=application_key(sites[row['site_id']][0],registry)
            if registry and parent_category(registry.application(sites[row['site_id']][0])['category'])!=parent_category(row['site_category']):
                raise ValueError('Effective sample category differs from the bound Table1 parent category')
            application_counts[aid]+=1
            category=parent_category(row['site_category'])
            if aid in application_categories and application_categories[aid]!=category:
                raise ValueError('Effective application has conflicting categories')
            application_categories[aid]=category
    except (ValueError,KeyError,TypeError,OSError) as error:
        application_errors.append(str(error)); errors.append({'reason':'application capacity: '+str(error)})
    from .profiles import release_errors
    errors.extend(release_errors(selected['configuration'], packages, versions, count))
    if len(rows) != count: errors.append({'reason': 'cumulative metadata count differs from sample population'})
    if targets['expected_samples'] is not None and count != targets['expected_samples']:
        errors.append({'reason': f'Expected {targets["expected_samples"]} samples; inspected {count}'})
    if targets.get('expected_sites') is not None and len(active_sites) != targets['expected_sites']:
        errors.append({'reason': f'Expected {targets["expected_sites"]} sites; inspected {len(active_sites)}'})
    if not resolutions or len(resolutions) > targets['max_viewport_specs']:
        errors.append({'reason': 'cumulative viewport specifications exceed contract limit or are missing'})
    if not count or short / count > targets['max_short_flow_share']:
        errors.append({'reason': 'cumulative short-flow share exceeds contract limit or population is empty'})
    if (batch_ids is not None or targets['category_share'] == 'enforced') and share > targets['max_category_share']:
        errors.append({'reason': 'cumulative category share exceeds configured contract limit'})
    duplicate = None
    try:
        duplicate = analyze_inputs(annotations, cache=cache, verify_exhaustive=verify_exhaustive, dataset_label='cumulative:' + digest(raw))
        # Unified verdict: the explicit effective set's near-duplicate sample
        # rate must stay <=0.1%; exact/sequence pairs (routes 1/2) are also
        # duplicate registration facts and always fail regardless of the rate.
        summary = duplicate.get('summary', {})
        if summary.get('sample_rate_within_requested_limit') is False:
            errors.append({'reason': 'cumulative near-duplicate sample rate exceeds 0.1% of the explicit effective set'})
        if any(duplicate[route].get('confirmed_pair_count' if route == 'route1' else 'count', 0)
               for route in ('route1', 'route2')):
            errors.append({'reason': 'cumulative exact/sequence duplicate routes hit; duplicate registration is not near-duplicate quota'})
        if duplicate['search']['exhaustive_verification']['status'] == 'FAIL':
            errors.append({'reason': 'index/exhaustive or cached/raw fingerprint disagreement'})
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        duplicate = analysis_error(error,sample_count=count,dataset_label='cumulative:' + digest(raw))
        errors.append({'reason': 'cumulative duplicate inspection failed: ' + str(error)})
    batch_statistics = {}
    if batch_ids is not None:
        try:
            batch = _check_quality_batch(batch_ids, {r['sample_id']: r['site_category'] for r in rows},
                                         short_ids, duplicate, targets)
        except (KeyError, ValueError, TypeError) as error:
            batch = {'status': 'FAIL', 'errors': [str(error)], 'sample_count': len(batch_ids)}
        batch['distributions'] = {'task_types': dict(task_types), 'actions': dict(action_types),
                                  'effective_steps': dict(lengths)}
        batch_statistics['quality_batch'] = batch
        errors.extend({'reason': reason} for reason in batch['errors'])
    for root in paths:
        if package_files(root) != snapshots[str(root)]:
            errors.append({'package': str(root), 'reason': 'input changed during cumulative inspection'})
    return {'schema_version': 'qc-cumulative-report-1', 'scope': 'cumulative-mechanical',
            'status': 'FAIL' if errors else 'PASS', 'mechanical_status': 'FAIL' if errors else 'PASS',
            'cross_package_status': 'FAIL' if errors else 'PASS', 'version_comparison': versions,
            'release_ready': False, 'local_acceptance_status': 'NOT_EVALUATED',
            'semantic_review_status': 'NOT_EVALUATED', 'delivery_document_review_status': 'NOT_EVALUATED',
            'customer_actual_acceptance': 'UNKNOWN', 'customer_actual_program_executed': False,
            'manifest': raw, 'manifest_sha256': digest(raw), 'contract_sha256': contract_hash,
            'local_profile': selected, 'sample_count': count, 'site_count': len(active_sites),
            'statistics': {'categories': dict(categories), 'maximum_category_share': share,
                           'category_coverage': coverage,
                           'applications':{'limit':application_limit,'policy':'flexible-total-200000-v1','source_policy':capacity_policy,'counts':dict(application_counts),
                                           'category_counts':dict(Counter(application_categories.values())),
                                           'identity_basis':'bound_registry' if raw.get('application_registry') else 'canonical_hostname',
                                           'status':'FAIL' if application_errors else 'PASS','errors':application_errors},
                           'viewport_specs': sorted(map(list, resolutions)), 'short_flow_count': short,
                           **batch_statistics},
            'packages': packages, 'duplicates': duplicate, 'errors': errors,
            'input_files_sha256': snapshots, 'input_integrity_checked_before_and_after': True,
            'internal_targets': selected['configuration'].get('internal_targets', {}),
            'internal_targets_enforced_as_customer_contract': False,
            'note': 'Mechanical cumulative scope only. A final actual customer directory, real reviews and final report QC are still required.'}
