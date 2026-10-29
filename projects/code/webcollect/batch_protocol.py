"""Portable static whole-site shards and qualified-result accounting.

No dispatcher, network, model or production run is started here. A shard must
have one owner: copying the same shard to two live workers is not failover.
Task site_uri must equal the explicit canonical root; pages use initial_url.
"""
from collections import defaultdict
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, urlunsplit

from .batch_core import file_sha
from .planning import object_sha256
from .site_failure_stop import application_key

VERSION = 'webcollect-machine-batch-1'
MARKER = 'batch_shard_meta'


def site_key(uri, registry=None, *, strict=False):
    if uri.startswith('//'):
        uri = 'https:' + uri
    key = application_key(uri, registry)
    # Frozen v1 manifests retain their conventional-www identity. Newly planned
    # manifests use explicit ownership evidence, including for www aliases.
    return key if strict or registry is not None else '//' + key[2:].removeprefix('www.')


def manifest_site_key(manifest, uri):
    return site_key(uri, manifest.get('application_registry'),
                    strict=manifest.get('site_identity_policy') == 'evidence-aliases-1')


def _seal(value, field):
    result = deepcopy(value); result.pop(field, None)
    result[field] = object_sha256(result)
    return result


def _ref_path(ref, base=None):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise ValueError('An exact file path/SHA256 reference is required')
    path = Path(ref['path']); path = Path(base or Path.cwd()) / path if not path.is_absolute() else path
    path = path.resolve()
    if not path.is_file() or file_sha(path) != ref['sha256']:
        raise ValueError('Bound batch evidence is missing or changed')
    return path


def _read_ref(ref, base=None):
    path = _ref_path(ref, base)
    value = json.loads(path.read_text())
    if file_sha(path) != ref['sha256']:
        raise ValueError('Batch evidence changed while reading')
    return value, path


def _capacity(record, base, registry=None, *, strict=False):
    count = record.get('capacity'); ref = record.get('capacity_ref')
    if count is None or ref is None:
        return None, None
    if type(count) is not int or count < 1:
        raise ValueError('Capacity must be an explicit positive integer or unknown')
    proof, path = _read_ref(ref, base)
    if (proof.get('schema_version') != 'webcollect-site-capacity-1' or proof.get('status') != 'verified'
            or proof.get('capacity') != count
            or site_key(proof.get('site_uri', ''), registry, strict=strict) != site_key(record['site_uri'], registry, strict=strict)
            or not isinstance(proof.get('evidence'), list) or not proof['evidence']):
        raise ValueError('Capacity requires a matching verified, evidenced site-capacity receipt')
    for item in proof['evidence']:
        _ref_path(item, path.parent)
    return count, {'receipt_sha256': ref['sha256'], 'evidence_sha256': sorted(item['sha256'] for item in proof['evidence'])}


def facts_state(refs, run_id, registry=None, *, strict=False):
    """Recompute exclusions from immutable facts, ignoring claimed summaries."""
    executions = {}; execution_keys = {}; successes = {}; sources = []; formal_since = None
    for ref in refs:
        value, _ = _read_ref(ref)
        keys = ('schema_version', 'campaign_id', 'formal_since', 'failure_limit', 'executions', 'successes')
        core = {key: value.get(key) for key in keys}
        if (core['schema_version'] != 'webcollect-site-execution-facts-1' or core['campaign_id'] != run_id
                or core['failure_limit'] != 3 or object_sha256(core) != value.get('facts_sha256')):
            raise ValueError('Batch facts must bind this run, original limit and exact portable facts')
        if formal_since is not None and formal_since != core['formal_since']:
            raise ValueError('A batch cannot mix facts from different formal cutoffs')
        formal_since = core['formal_since']; sources.append(deepcopy(ref))
        for fact in core['executions']:
            identity = fact.get('fact_id')
            if not isinstance(identity, str) or not identity or fact.get('state') not in ('failed', 'unknown'):
                raise ValueError('Invalid immutable execution fact')
            if identity in executions and executions[identity] != fact:
                raise ValueError('One execution fact cannot be changed or reclassified')
            key = fact.get('execution_key', identity)
            if key in execution_keys and execution_keys[key] != identity:
                raise ValueError('One original execution cannot acquire another fact ID alias')
            execution_keys[key] = identity
            executions[identity] = fact
        for fact in core['successes']:
            identity = fact.get('fact_id', fact.get('success_id'))
            if not isinstance(identity, str) or not identity:
                raise ValueError('Immutable success fact identity required')
            if identity in successes and successes[identity] != fact:
                raise ValueError('One success fact cannot be changed')
            successes[identity] = fact
    counts = defaultdict(lambda: {'failed': 0, 'unknown': 0})
    for fact in executions.values():
        counts[site_key(fact['application_key'], registry, strict=strict)][fact['state']] += 1
    excluded = sorted(key for key, states in counts.items() if states['failed'] >= 3 or states['unknown'])
    used = sorted(set(counts) | {site_key(row['application_key'], registry, strict=strict) for row in successes.values()})
    return {'sources': sources, 'excluded_sites': excluded, 'used_sites': used,
            'formal_since': formal_since, 'execution_counts': dict(counts),
            'execution_facts': [executions[key] for key in sorted(executions)],
            'qualified_count_from_imported_facts': 0}


def _assign(sites, target, shard_ids):
    loads = dict.fromkeys(shard_ids, 0)
    candidates = sorted((row for row in sites if row['state'] == 'reserve' and row['capacity'] is not None),
                        key=lambda row: (-row['capacity'], row['site_id']))
    for row in candidates:
        if sum(loads.values()) >= target:
            break
        owner = row['shard_id']
        row.update(state='assigned'); loads[owner] += row['capacity']
    return [{'shard_id': owner, 'site_ids': [row['site_id'] for row in sites if row['state'] == 'assigned' and row['shard_id'] == owner],
             'active_site_ids': [row['site_id'] for row in sites if row['state'] == 'assigned' and row['shard_id'] == owner],
             'owned_site_ids': [row['site_id'] for row in sites if row['shard_id'] == owner],
             'planned_capacity': loads[owner]} for owner in shard_ids]


def shard_names(worker_count):
    if type(worker_count) is not int or worker_count < 1:
        raise ValueError('Worker count must be a positive integer')
    return tuple(f'worker-{number:03}' for number in range(1, worker_count + 1))


def plan_shards(catalog, *, run_id, target, shard_ids=None, worker_count=None, facts=(), base=None):
    if not isinstance(run_id, str) or not run_id.strip() or type(target) is not int or target < 1:
        raise ValueError('An explicit run ID and positive qualified target are required')
    shard_ids = tuple(shard_ids) if shard_ids is not None else shard_names(worker_count or 2)
    if not shard_ids or len(set(shard_ids)) != len(shard_ids) or any(not isinstance(s, str) or not s for s in shard_ids):
        raise ValueError('Static shard IDs must be nonempty and unique')
    if worker_count is not None and (type(worker_count) is not int or worker_count < 1 or worker_count != len(shard_ids)):
        raise ValueError('Worker count differs from explicit shard IDs')
    records = catalog.get('records') if isinstance(catalog, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError('A nonempty explicit candidate catalog is required')
    registry = catalog.get('application_registry')
    if registry is not None:
        from .application_identity import aliases
        aliases(registry)
    state = facts_state(facts, run_id, registry, strict=True); groups = defaultdict(list)
    for record in records:
        groups[site_key(record['site_uri'], registry, strict=True)].append(record)
    sites = []
    for number, (key, members) in enumerate(sorted(groups.items()), 1):
        if number > 999999:
            raise ValueError('Global site ID space exhausted')
        categories = {row['site_category'] for row in members}
        if len(categories) != 1 or not next(iter(categories)).strip():
            raise ValueError('Whole-site aliases cannot change category')
        origins = sorted({urlunsplit((urlsplit(row['site_uri']).scheme, urlsplit(row['site_uri']).netloc.lower(), '/', '', '')) for row in members})
        if registry is not None:
            from .batch_core import load_json
            declared = [row['canonical_uri'] for row in load_json(registry['path'])['applications']
                        if site_key(row['canonical_uri'], registry, strict=True) == key]
            if declared:
                origins = declared
        capacities = [_capacity(row, base, registry, strict=True) for row in members]
        known = [(count, proof) for count, proof in capacities if count is not None]
        capacity, proof = max(known, key=lambda item: item[0]) if known else (None, None)
        sites.append({'site_id': f'S{number:06}', 'application_key': key, 'site_uri': origins[0],
                      'site_category': next(iter(categories)), 'capacity': capacity, 'capacity_binding': proof,
                      'capacity_policy': 'maximum verified whole-site capacity; aliases never sum',
                      'state': 'unavailable' if key in state['excluded_sites'] else ('used' if key in state['used_sites'] else 'reserve'),
                      'shard_id': None, 'candidates': deepcopy(members)})
    owned_loads = dict.fromkeys(shard_ids, 0)
    for row in sorted(sites, key=lambda value: (-(value['capacity'] or 1), value['site_id'])):
        owner = min(owned_loads, key=lambda value: (owned_loads[value], value))
        row['shard_id'] = owner; owned_loads[owner] += row['capacity'] or 1
    shards = _assign(sites, target, shard_ids)
    return _seal({'schema_version': VERSION, 'run_id': run_id, 'round_index': 0, 'target': target,
                  'catalog_sha256': object_sha256(catalog), 'raw_candidate_count': len(records),
                  'sites': sites, 'shards': shards, 'facts': state, 'ancestor_sha256': [],
                  'site_identity_policy': 'evidence-aliases-1', 'application_registry': registry,
                  'production_started': False}, 'manifest_sha256')


def verify_manifest(manifest):
    if manifest.get('schema_version') != VERSION or _seal(manifest, 'manifest_sha256') != manifest:
        raise ValueError('Changed or unsupported static batch manifest')
    if manifest.get('site_identity_policy') not in (None, 'evidence-aliases-1'):
        raise ValueError('Unsupported static application ownership policy')
    ids = [row['site_id'] for row in manifest['sites']]; keys = [row['application_key'] for row in manifest['sites']]
    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        raise ValueError('Global site identities must be unique')
    owners = [row['shard_id'] for row in manifest['shards']]
    if not owners or len(owners) != len(set(owners)):
        raise ValueError('Worker shard identities must be unique')
    for row in manifest['sites']:
        parsed = urlsplit(row['site_uri'])
        if (not re.fullmatch(r'S[0-9]{6}', row['site_id']) or row['shard_id'] not in owners
                or row['application_key'] != manifest_site_key(manifest, row['site_uri']) or parsed.path != '/'
                or parsed.query or parsed.fragment or row['state'] not in ('assigned', 'reserve', 'used', 'unavailable')
                or (row['state'] == 'assigned' and (type(row['capacity']) is not int or row['capacity'] < 1))):
            raise ValueError('Invalid canonical site, capacity, state or owner')
    for shard in manifest['shards']:
        owned = [row['site_id'] for row in manifest['sites'] if row['shard_id'] == shard['shard_id']]
        active = [row['site_id'] for row in manifest['sites'] if row['shard_id'] == shard['shard_id'] and row['state'] == 'assigned']
        if shard['owned_site_ids'] != owned or shard['active_site_ids'] != active or shard['site_ids'] != active:
            raise ValueError('Shard ownership/active coverage differs from the global site map')
    return manifest


def global_task_id(run_id, site_id, local_task_id):
    if not all(isinstance(value, str) and value for value in (run_id, site_id, local_task_id)):
        raise ValueError('Run, site and local task identity required')
    return site_id + '-T-' + object_sha256([run_id, site_id, local_task_id])[:32]


def guard_shard_task(manifest, shard_id, task):
    verify_manifest(manifest)
    matches = [row for row in manifest['sites'] if row['application_key'] == manifest_site_key(manifest, task['site_uri'])]
    if len(matches) != 1:
        raise ValueError('Task site is outside the frozen catalog')
    site = matches[0]; binding = task.get('batch_identity')
    expected = {'run_id': manifest['run_id'], 'shard_id': shard_id, 'site_id': site['site_id'], 'task_id': task['task_id']}
    if (site['state'] != 'assigned' or site['shard_id'] != shard_id or binding != expected
            or not task['task_id'].startswith(site['site_id'] + '-T-')
            or task['site_uri'] != site['site_uri'] or task['site_category'] != site['site_category']
            or manifest_site_key(manifest, task.get('initial_url', task['site_uri'])) != site['application_key']):
        raise ValueError('Task must belong to this shard and use its exact canonical site URI and identity')
    return site


def _marker(con):
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (MARKER,)).fetchone() is None:
        return None
    row = con.execute('SELECT value FROM batch_shard_meta WHERE id=1').fetchone()
    if row is None:
        raise ValueError('Seeded shard registry has no binding')
    return json.loads(row[0])


def seed_registry(manifest, registry, shard_id):
    from .storage import ensure_registry_schema
    verify_manifest(manifest); registry = Path(registry).resolve()
    if shard_id not in {row['shard_id'] for row in manifest['shards']}:
        raise ValueError('Unknown shard owner')
    marker = {'manifest': manifest, 'shard_id': shard_id}
    expected = {int(row['site_id'][1:]): (row['site_uri'], row['site_category'], 'real') for row in manifest['sites']}
    if registry.exists():
        with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'sites', 'allocations', 'batches'} <= tables:
                raise ValueError('Existing registry is not an explicit compatible production registry')
            previous = _marker(con)
            if previous is not None and previous != marker:
                old = previous['manifest']
                if (old['run_id'] != manifest['run_id'] or previous['shard_id'] != shard_id
                        or manifest.get('parent_sha256') != old['manifest_sha256']):
                    raise ValueError('Cannot replace/reassign a seeded shard registry')
                new_sites = {row['site_id']: row for row in manifest['sites']}
                if any(any(new_sites.get(row['site_id'], {}).get(key) != row[key]
                           for key in ('site_uri', 'site_category', 'shard_id')) for row in old['sites']):
                    raise ValueError('A new round cannot renumber or change a previous whole-site owner')
            if previous is None and con.execute('SELECT 1 FROM allocations LIMIT 1').fetchone():
                raise ValueError('An unmarked allocated registry cannot be silently adopted')
            for number, uri, category, kind in con.execute('SELECT id,uri,category,kind FROM sites'):
                if expected.get(number) != (uri, category, kind):
                    raise ValueError('Existing global site mapping is incompatible; registry remains unchanged')
    registry.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(registry)) as con:
        ensure_registry_schema(con); con.execute('BEGIN IMMEDIATE')
        con.execute('CREATE TABLE IF NOT EXISTS batch_shard_meta(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
        for number, (uri, category, kind) in expected.items():
            con.execute('INSERT OR IGNORE INTO sites VALUES(?,?,?,?,1)', (number, uri, category, kind))
        con.execute('INSERT OR REPLACE INTO batch_shard_meta VALUES(1,?)', (json.dumps(marker, sort_keys=True),))
        con.commit()
    return {'registry': str(registry), 'run_id': manifest['run_id'], 'shard_id': shard_id,
            'global_site_count': len(expected), 'collection_started': False}


def guard_registry_site(con, uri, category):
    marker = _marker(con)
    if marker is None:
        return
    manifest = verify_manifest(marker['manifest'])
    if not any(row['site_uri'] == uri and row['site_category'] == category and row['state'] == 'assigned'
               and row['shard_id'] == marker['shard_id'] for row in manifest['sites']):
        raise ValueError('Seeded worker cannot allocate an out-of-shard or noncanonical site URI')


def verify_plan_shard(plan, registry):
    path = Path(registry).resolve(); binding = plan.get('batch_shard')
    marker = None
    if path.is_file():
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
            marker = _marker(con)
    if marker is None:
        if binding is not None or any('batch_identity' in task for task in plan['tasks']):
            raise ValueError('A sharded plan requires its explicitly seeded registry')
        return
    manifest = verify_manifest(marker['manifest'])
    expected = {'schema_version': 'webcollect-plan-shard-1', 'run_id': manifest['run_id'],
                'shard_id': marker['shard_id'], 'manifest_sha256': manifest['manifest_sha256']}
    if binding != expected:
        raise ValueError('Worker plan and seeded shard binding differ')
    for task in plan['tasks']:
        guard_shard_task(manifest, marker['shard_id'], task)


def verify_shard_policy(registry, policy):
    """A seeded worker always uses the original run's local failure ledger."""
    from .site_failure_stop import SiteFailureStore
    path = Path(registry).resolve()
    if not path.is_file():
        return
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        marker = _marker(con)
    if marker is None:
        return
    manifest = verify_manifest(marker['manifest']); binding = policy.get('site_failure_guard')
    if not isinstance(binding, dict) or binding.get('campaign_id') != manifest['run_id']:
        raise ValueError('A sharded worker requires the same run site_failure_guard')
    if binding.get('application_registry') != manifest.get('application_registry'):
        raise ValueError('Shard and original site guard must use the same frozen application aliases')
    store = SiteFailureStore(binding)
    if manifest['facts']['formal_since'] is not None and binding['formal_since'] != manifest['facts']['formal_since']:
        raise ValueError('Shard failure cutoff differs from its frozen portable facts')
    imported = store.export_facts()
    originals = {row['fact_id']: row for row in imported['executions']}
    if any(originals.get(row['fact_id']) != row for row in manifest['facts']['execution_facts']):
        raise ValueError('Worker must import exact immutable original failure/unknown facts before dispatch')
    counts = defaultdict(lambda: {'failed': 0, 'unknown': 0})
    for fact in imported['executions']:
        counts[manifest_site_key(manifest, fact['application_key'])][fact['state']] += 1
    for key, states in manifest['facts']['execution_counts'].items():
        if any(counts[key][state] < count for state, count in states.items()):
            raise ValueError('Worker must import the frozen original failure/unknown facts before dispatch')


def freeze_result(registry, qc_report, dataset):
    """Read a seeded worker's actual final QC acceptance into a portable receipt."""
    from .client_reports import _bound_report
    from .collect_runtime import verify_committed_samples
    from quality_inspector.profiles import package_files
    registry = Path(registry).resolve(); dataset = Path(dataset).resolve(); qc_report = Path(qc_report).resolve()
    report, files = _bound_report(dataset, qc_report)
    if (report.get('delivery_status') != 'PASS' or report.get('inspection_stage') != 'final'
            or report.get('release_ready') is not True):
        raise ValueError('Only final, exactly bound, release-ready QC PASS may enter a shard result')
    report_hash = file_sha(qc_report); samples = []
    with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
        marker = _marker(con)
        if marker is None:
            raise ValueError('Qualified result must originate in a seeded shard registry')
        manifest = verify_manifest(marker['manifest'])
        for sample in report['samples']:
            sid = sample['sample_id']
            rows = con.execute('SELECT a.status,t.task_json,r.decision,r.evidence_json,a.attempt_id,a.evidence_json,a.site_id,x.site_id FROM m4_attempts a '
                'JOIN m4_tasks t ON t.task_key=a.task_key JOIN m4_reviews r ON r.sample_id=a.sample_id '
                'JOIN allocations x ON x.sample_id=a.sample_id '
                'WHERE a.sample_id=?', (sid,)).fetchall()
            if len(rows) != 1 or rows[0][0] != 'collected_pending_review' or rows[0][2] != 'pass' or sample.get('status') != 'PASS':
                raise ValueError('Sample lacks its original saved attempt and independently accepted QC PASS')
            task = json.loads(rows[0][1]); refs = json.loads(rows[0][3])
            guard_shard_task(manifest, marker['shard_id'], task)
            if not any(ref.get('path') == str(qc_report) and ref.get('sha256') == report_hash for ref in refs):
                raise ValueError('Registry acceptance does not bind this exact final QC report')
            capture_refs = json.loads(rows[0][5])
            saved = [ref for ref in capture_refs if Path(ref.get('path', '')).parts[-3:] == ('evidence', sid, 'saved_sample.json')]
            if len(saved) != 1:
                raise ValueError('Qualified shard result needs its original committed capture receipt')
            receipt, receipt_path = _read_ref(saved[0])
            package_files(receipt_path.parent); package_files(receipt_path.parents[2] / 'samples' / sid)
            verify_committed_samples(receipt_path.parents[2], [{'attempt_id': rows[0][4], 'sample_id': sid,
                'status': rows[0][0], 'evidence': capture_refs}])
            if package_files(dataset / 'samples' / sid) != receipt['sample_files_sha256']:
                raise ValueError('Qualified candidate differs from the original committed sample')
            identity = task['batch_identity']
            if not sid.startswith(identity['site_id'] + '_sample_') or rows[0][6] != identity['site_id'] or rows[0][7] != identity['site_id']:
                raise ValueError('Sample ID differs from its shared global site ID')
            samples.append({**identity, 'sample_id': sid, 'annotation_sha256': sample['annotation_sha256'],
                            'evidence_sha256': sample['evidence_sha256']})
    if file_sha(qc_report) != report_hash:
        raise ValueError('QC report changed during result freezing')
    return _seal({'schema_version': 'webcollect-shard-result-1', 'run_id': manifest['run_id'],
                  'shard_id': marker['shard_id'], 'manifest_sha256': manifest['manifest_sha256'],
                  'report_sha256': report_hash, 'source_dataset': str(dataset),
                  'dataset_files_sha256': files, 'samples': samples, 'QC_approval_created': False}, 'result_sha256')


def merge_qualified(manifest, inputs, *, facts=(), global_reviews=(), global_sampling_plan=None):
    """Count immutable qualified originals; reports may relocate with exact bytes.

    Inputs contain result_ref, report_ref and the local dataset path. Facts and
    reports are hash-bound, not caller-supplied PASS/unavailable flags. Different
    ID duplicate hits select a deterministic nonconflicting subset, never two
    conflicting samples. No customer package is edited or approved here.
    """
    from quality_inspector.checksums import verify_manifest as verify_checksums
    from quality_inspector.duplicates import analyze_inputs, summarize
    from quality_inspector.format_checks import run as format_run
    from quality_inspector.profiles import package_files
    from .client_reports import validate_report_semantic_rules
    global_reviews = list(global_reviews)
    verify_manifest(manifest)
    state = facts_state(facts, manifest['run_id'], manifest.get('application_registry'),
                        strict=manifest.get('site_identity_policy') == 'evidence-aliases-1')
    sites = {row['site_id']: row for row in manifest['sites']}; versions = {}; sources = []; copies = []; shard_results = {}
    for item in inputs:
        result, _ = _read_ref(item['result_ref']); report, _ = _read_ref(item['report_ref'])
        if (result.get('schema_version') != 'webcollect-shard-result-1' or _seal(result, 'result_sha256') != result
                or result.get('run_id') != manifest['run_id'] or result.get('manifest_sha256') not in
                [manifest['manifest_sha256'], *manifest['ancestor_sha256']]
                or result.get('report_sha256') != item['report_ref']['sha256']):
            raise ValueError('Shard result does not bind this run, plan ancestry and exact QC report')
        shard_key = (result['manifest_sha256'], result.get('shard_id'))
        if result.get('shard_id') not in {row['shard_id'] for row in manifest['shards']}:
            raise ValueError('Result refers to an unknown worker shard')
        if shard_key in shard_results and shard_results[shard_key] != result['result_sha256']:
            raise ValueError('Conflicting result bodies for one shard round need explicit resolution')
        shard_results[shard_key] = result['result_sha256']
        if (report.get('dataset') != result['source_dataset'] or report.get('delivery_status') != 'PASS'
                or report.get('inspection_stage') != 'final' or report.get('release_ready') is not True
                or report.get('input_files_sha256', report.get('package_files_sha256')) != result['dataset_files_sha256']):
            raise ValueError('Result and final QC acceptance/binding differ')
        validate_report_semantic_rules(report)
        root = Path(item['dataset']).resolve(); files = package_files(root)
        formats = format_run(None, root)
        if (files != result['dataset_files_sha256'] or not verify_checksums(root)['pass']
                or formats['package_errors'] or any(not row.get('confirmed_format_pass') for row in formats['samples'])):
            raise ValueError('Moved qualified dataset bytes, checksums or deterministic format differ')
        rows = {row['sample_id']: row for row in report['samples']}
        if set(rows) != {row['sample_id'] for row in result['samples']} or len(rows) != len(result['samples']):
            raise ValueError('Qualified result population differs from exact QC population')
        for row in result['samples']:
            sid = row['sample_id']; site = sites.get(row['site_id']); reviewed = rows[sid]
            if (site is None or site['shard_id'] != result['shard_id'] or row['shard_id'] != result['shard_id']
                    or row['run_id'] != manifest['run_id'] or reviewed.get('status') != 'PASS'
                    or not sid.startswith(row['site_id'] + '_sample_')
                    or any(row[key] != reviewed.get(key) for key in ('annotation_sha256', 'evidence_sha256'))):
                raise ValueError('Qualified sample identity, owner or review binding differs')
            actual = package_files(root / 'samples' / sid)
            if actual != {'annotation.json': row['annotation_sha256'], **row['evidence_sha256']}:
                raise ValueError('Qualified sample no longer matches its actual review bytes')
            version = object_sha256(actual)
            occurrence = {**row, 'version_id': version, 'qc_report_sha256': result['report_sha256'],
                          'annotation_path': str(root / 'samples' / sid / 'annotation.json')}
            if sid in versions:
                if versions[sid]['version_id'] != version:
                    raise ValueError('Same sample ID has conflicting qualified revisions; explicit resolution required')
                copies.append(occurrence)
            else:
                versions[sid] = occurrence
        if package_files(root) != files:
            raise ValueError('Qualified source changed during merge')
        sources.append({'result': item['result_ref'], 'report': item['report_ref'], 'dataset': str(root)})
    ordered = [versions[sid] for sid in sorted(versions)]
    duplicate = analyze_inputs([row['annotation_path'] for row in ordered], dataset_label='batch:' + manifest['run_id']) if ordered else None
    conflicts = {frozenset(row['sample_ids']) for row in summarize(duplicate)['pair_adjudications']} if duplicate else set()
    effective = []; excluded = []
    for row in ordered:
        if any(frozenset((row['sample_id'], prior['sample_id'])) in conflicts for prior in effective):
            excluded.append(row)
        else:
            effective.append(row)
    for source in sources:
        result, _ = _read_ref(source['result']); _read_ref(source['report'])
        if package_files(source['dataset']) != result['dataset_files_sha256']:
            raise ValueError('Qualified source changed during whole-set duplicate comparison')
    contexts = {row['qc_report_sha256'] for row in effective}
    global_pending = len(contexts) > 1 and len(effective) > 1
    globally_qualified = 0 if global_pending else len(effective)
    global_result = None
    global_checks = [{'sample_id': row['sample_id'], 'source_report_sha256': row['qc_report_sha256'],
                      'substantive_difference': 'REVIEW_REQUIRED' if global_pending else 'SOURCE_SCOPE_UNCHANGED',
                      'reason': 'comparison_population_expanded' if global_pending else 'same_original_report_population',
                      'original_review_modified': False} for row in effective]
    if global_reviews or global_sampling_plan is not None:
        from quality_inspector.global_difference import resolve
        population = [{'sample_id': row['sample_id'], 'annotation_sha256': row['annotation_sha256'],
                       'evidence_sha256': row['evidence_sha256'], 'sample_path': str(Path(row['annotation_path']).parent)}
                      for row in effective]
        source_reports = list({row['report']['sha256']: row['report'] for row in sources}.values())
        global_result = resolve(population, global_reviews, sampling_plan=global_sampling_plan,
                                source_reports=source_reports)
        decisions = {row['sample_id']: row for row in global_result['decisions']}
        if set(decisions) != {row['sample_id'] for row in effective}:
            raise ValueError('Global difference decisions do not cover this exact effective population')
        qualified = set(global_result['qualified_sample_ids'])
        if qualified != {sid for sid, row in decisions.items() if row.get('admission_status', row['status']) == 'PASS'}:
            raise ValueError('Global qualified IDs differ from actual independent difference decisions')
        globally_qualified = len(qualified)
        global_pending = any(row.get('admission_status', row['status']) == 'REVIEW_REQUIRED' for row in decisions.values())
        global_checks = [{**row, 'substantive_difference': decisions[row['sample_id']]['status'],
                          'reason': 'independent_full_population_difference',
                          'difference_decision': decisions[row['sample_id']]} for row in global_checks]
    missing = [shard['shard_id'] for shard in manifest['shards'] if shard['active_site_ids']
               and (manifest['manifest_sha256'], shard['shard_id']) not in shard_results
               and any(sites[sid]['application_key'] not in state['excluded_sites'] for sid in shard['active_site_ids'])]
    return _seal({'schema_version': 'webcollect-batch-merge-1', 'run_id': manifest['run_id'],
                  'manifest_sha256': manifest['manifest_sha256'], 'target': manifest['target'],
                  'mechanical_unique_count': len(effective), 'globally_qualified_count': globally_qualified,
                  'qualified_unique_count': globally_qualified, 'deficit': max(0, manifest['target'] - globally_qualified),
                  'global_semantic_review_required': global_pending, 'missing_shards': missing,
                  'global_qualification_status': ('REVIEW_REQUIRED' if global_pending or missing else
                                                'FAIL' if any(row['substantive_difference'] == 'FAIL' for row in global_checks) else 'PASS'),
                  'global_checks': global_checks, 'global_reviews': deepcopy(list(global_reviews)),
                  'global_difference': global_result, 'global_sampling_plan': deepcopy(global_sampling_plan),
                  'global_actual_fifth_pass_count': (len(global_result['actual_fifth_pass_sample_ids']) if global_result else 0),
                  'global_policy_admitted_count': (len(global_result['policy_admitted_sample_ids']) if global_result else 0),
                  'effective_samples': effective, 'identical_copies': copies, 'duplicate_exclusions': excluded,
                  'duplicates': duplicate, 'facts': state, 'sources': sources, 'QC_approval_created': False,
                  'release_ready': False}, 'merge_sha256')


def next_round(manifest, merged, *, new_catalog=None, base=None):
    verify_manifest(manifest)
    if (merged.get('schema_version') != 'webcollect-batch-merge-1' or _seal(merged, 'merge_sha256') != merged
            or merged.get('manifest_sha256') != manifest['manifest_sha256'] or merged.get('run_id') != manifest['run_id']):
        raise ValueError('Next round needs the exact bound qualified merge result')
    current = merge_qualified(manifest, [{'result_ref': row['result'], 'report_ref': row['report'], 'dataset': row['dataset']}
                                      for row in merged['sources']], facts=merged['facts']['sources'],
                              global_reviews=merged['global_reviews'], global_sampling_plan=merged['global_sampling_plan'])
    if current != merged:
        raise ValueError('Qualified merge evidence changed before replenishment')
    if merged['global_semantic_review_required'] or merged['missing_shards']:
        raise ValueError('Finish missing shards and independent global semantic comparison before replenishment')
    result = deepcopy(manifest)
    for row in result['sites']:
        if row['state'] == 'assigned':
            row['state'] = 'used'
        if row['application_key'] in merged['facts']['excluded_sites']:
            row['state'] = 'unavailable'
        elif row['application_key'] in merged['facts']['used_sites']:
            row['state'] = 'used'
    owners = [row['shard_id'] for row in manifest['shards']]
    if new_catalog is not None:
        if new_catalog.get('application_registry') != manifest.get('application_registry'):
            raise ValueError('A replenishment round cannot change frozen application ownership')
        addition = plan_shards(new_catalog, run_id=manifest['run_id'], target=max(1, merged['deficit']),
                               shard_ids=owners, facts=merged['facts']['sources'], base=base)
        old_keys = {row['application_key'] for row in result['sites']}
        if old_keys & {row['application_key'] for row in addition['sites']}:
            raise ValueError('New candidates must be new whole hosts; old pages/query/aliases cannot re-enter')
        loads = {owner: sum((row['capacity'] or 1) for row in result['sites'] if row['shard_id'] == owner) for owner in owners}
        number = max(int(row['site_id'][1:]) for row in result['sites'])
        for row in addition['sites']:
            number += 1
            if number > 999999: raise ValueError('Global site ID space exhausted')
            owner = min(loads, key=lambda key: (loads[key], key)); loads[owner] += row['capacity'] or 1
            row.update(site_id=f'S{number:06}', shard_id=owner,
                       state='unavailable' if row['application_key'] in merged['facts']['excluded_sites'] else
                       ('used' if row['application_key'] in merged['facts']['used_sites'] else 'reserve'))
            result['sites'].append(row)
        result['raw_candidate_count'] += addition['raw_candidate_count']
        result['additional_catalog_sha256'] = addition['catalog_sha256']
    result.update(round_index=manifest['round_index'] + 1, parent_sha256=manifest['manifest_sha256'],
                  ancestor_sha256=[*manifest['ancestor_sha256'], manifest['manifest_sha256']], facts=merged['facts'],
                  previous_merge_sha256=merged['merge_sha256'], previous_global_reviews=deepcopy(merged['global_reviews']),
                  previous_global_sampling_plan=deepcopy(merged['global_sampling_plan']))
    result['shards'] = _assign(result['sites'], merged['deficit'], owners)
    return _seal(result, 'manifest_sha256')
