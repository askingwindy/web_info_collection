"""Static N-worker protocol with temporary offline records; no production IO."""
from contextlib import closing
import csv
import json
from pathlib import Path
import shutil
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'), str(REPO / 'projects/quality-inspector/tests')]
import test_delivery as delivery_tests
from quality_inspector.checksums import write_manifest
from quality_inspector.engine import inspect
from quality_inspector import semantic
from quality_inspector.profiles import package_files
from delivery_scope_fixture import freeze_scope
from webcollect.client_reports import finalize_client_package
from webcollect import batch_protocol as batch
from webcollect.batch_core import file_sha
from webcollect.current_chain import initialize_chain, read_chain_history
from webcollect.runtime import SCHEMA
from webcollect.site_failure_stop import SiteFailureStore
from webcollect.storage import allocate


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False))
    return {'path': str(path), 'sha256': file_sha(path)}


class StaticBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.run = 'SYNTHETIC-TWO-WORKERS'
        self.guards = patch('webcollect.model_gateway.ModelGateway.call', side_effect=AssertionError('Offline only'))
        self.model = self.guards.start(); self.addCleanup(self.guards.stop)

    def catalog(self, count=4):
        records = []
        for number in range(count):
            uri = f'https://site{number:05}.example/'
            record = {'site_uri': uri, 'site_category': '学习教育'}
            if number < 4:
                capacity = [120, 80, 65, 40][number]
                support = put(self.root / f'measurement-{number}.json', {'fixture': True, 'site_uri': uri, 'capacity': capacity})
                proof = put(self.root / f'capacity-{number}.json', {'schema_version': 'webcollect-site-capacity-1',
                    'site_uri': uri, 'capacity': capacity, 'status': 'verified', 'evidence': [support]})
                record.update(capacity=capacity, capacity_ref=proof)
            records.append(record)
        return {'records': records}

    def manifest(self, count=4, target=170):
        return batch.plan_shards(self.catalog(count), run_id=self.run, target=target, shard_ids=('A', 'B'))

    def task(self, manifest, site):
        identity = batch.global_task_id(self.run, site['site_id'], 'task-one')
        return {'task_id': identity, 'site_uri': site['site_uri'], 'site_category': site['site_category'],
                'initial_url': site['site_uri'] + 'a/page?q=1',
                'batch_identity': {'run_id': self.run, 'shard_id': site['shard_id'], 'site_id': site['site_id'], 'task_id': identity}}

    def test_large_catalog_keeps_unknown_reserve_and_groups_entire_host(self):
        catalog = self.catalog(11001)
        catalog['records'].append(dict(catalog['records'][0], site_uri='http://WWW.site00000.example/page?q=9#fragment'))
        evidence = put(self.root / 'www-ownership-evidence.json', {'CONTROLLED': 'observed canonical application ownership'})
        catalog['application_registry'] = put(self.root / 'www-aliases.json', {
            'schema_version': 'webcollect-application-aliases-1', 'applications': [{
                'canonical_uri': 'https://site00000.example/',
                'aliases': ['https://site00000.example/', 'http://www.site00000.example/'], 'evidence': [evidence]}]})
        manifest = batch.plan_shards(catalog, run_id=self.run, target=170, shard_ids=('A', 'B'))
        self.assertEqual(manifest['raw_candidate_count'], 11002)
        self.assertEqual(len(manifest['sites']), 11001)
        assigned = [row for row in manifest['sites'] if row['state'] == 'assigned']
        self.assertEqual(len(assigned), 2)  # capacity 120+80, never fixed 20 per site
        self.assertEqual(len({row['shard_id'] for row in assigned}), 2)
        self.assertEqual(manifest['sites'][0]['capacity'], 120)  # alias capacity does not sum
        self.assertEqual(len([row for row in manifest['sites'] if row['capacity'] is None]), 10997)
        self.assertFalse(manifest['production_started'])

    def test_unproven_hosts_stay_distinct_and_proven_crosshost_aliases_share_owner(self):
        catalog = {'records': [{'site_uri': uri, 'site_category': '在线工具'} for uri in (
            'https://example.org/a', 'https://www.example.org/b', 'https://m.example.org/c')]}
        plain = batch.plan_shards(catalog, run_id=self.run, target=1, worker_count=3)
        self.assertEqual(len(plain['sites']), 3)
        proof = put(self.root / 'alias-proof.json', {'CONTROLLED': 'observed common application'})
        catalog['application_registry'] = put(self.root / 'application-aliases.json', {
            'schema_version': 'webcollect-application-aliases-1', 'applications': [{
                'canonical_uri': 'https://example.org/',
                'aliases': ['https://example.org/', 'https://www.example.org/', 'https://m.example.org/'],
                'evidence': [proof]}]})
        combined = batch.plan_shards(catalog, run_id=self.run, target=1, worker_count=3)
        batch.verify_manifest(combined)
        self.assertEqual(len(combined['sites']), 1)
        self.assertEqual(combined['sites'][0]['application_key'], '//example.org/')
        self.assertEqual(sum(len(row['owned_site_ids']) for row in combined['shards']), 1)

    def test_n_workers_cover_every_site_once_without_filling_empty_active_shards(self):
        catalog = self.catalog()
        for workers in (1, 2, 3, 4, 7):
            with self.subTest(workers=workers):
                manifest = batch.plan_shards(catalog, run_id=self.run, target=1, worker_count=workers)
                self.assertEqual(len(manifest['shards']), workers)
                owned = [sid for shard in manifest['shards'] for sid in shard['owned_site_ids']]
                self.assertEqual(len(owned), len(set(owned)))
                self.assertEqual(set(owned), {site['site_id'] for site in manifest['sites']})
                self.assertEqual(sum(len(shard['active_site_ids']) for shard in manifest['shards']), 1)
        for invalid in (0, -1, True):
            with self.assertRaises(ValueError): batch.plan_shards(catalog, run_id=self.run, target=1, worker_count=invalid)
        with self.assertRaises(ValueError): batch.plan_shards(catalog, run_id=self.run, target=1, shard_ids=['same', 'same'])

    def test_shared_ids_seed_after_chain_and_real_allocator_rejects_other_owner(self):
        manifest = self.manifest(); assigned = [row for row in manifest['sites'] if row['state'] == 'assigned']
        registry_a = self.root / 'a.sqlite3'; history = self.root / 'chain/manifest.json'
        initialize_chain(history, registry_a, chain_id='SYNTHETIC-chain', current_result_roots=[self.root / 'results'])
        before = read_chain_history(history)[1]
        batch.seed_registry(manifest, registry_a, 'A'); batch.seed_registry(manifest, self.root / 'b.sqlite3', 'B')
        self.assertEqual(read_chain_history(history), ([], before))
        for site in assigned:
            registry = registry_a if site['shard_id'] == 'A' else self.root / 'b.sqlite3'
            result = allocate(registry, site['site_uri'], site['site_category'], 'real')
            self.assertEqual(result['site_id'], site['site_id'])
            with self.assertRaisesRegex(ValueError, 'out-of-shard'):
                allocate(registry_a if site['shard_id'] == 'B' else self.root / 'b.sqlite3', site['site_uri'], site['site_category'], 'real')
            with self.assertRaisesRegex(ValueError, 'noncanonical'):
                allocate(registry, site['site_uri'] + 'page', site['site_category'], 'real')
        with closing(sqlite3.connect(registry_a)) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM sites').fetchone()[0], 4)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM current_chain_results').fetchone()[0], 0)
        # Global inventory rows are not counted as active/collected sites.
        batch.seed_registry(manifest, registry_a, 'A')
        own = next(row for row in assigned if row['shard_id'] == 'A')
        self.assertTrue(allocate(registry_a, own['site_uri'], own['site_category'], 'real')['sample_id'].endswith('000002'))

    def test_task_guard_is_strict_without_rewriting_frozen_uri(self):
        manifest = self.manifest(); site = next(row for row in manifest['sites'] if row['state'] == 'assigned')
        task = self.task(manifest, site); original = json.loads(json.dumps(task))
        batch.guard_shard_task(manifest, site['shard_id'], task)
        registry = self.root / 'worker.sqlite3'; batch.seed_registry(manifest, registry, site['shard_id'])
        binding = {'schema_version': 'webcollect-plan-shard-1', 'run_id': self.run,
                   'shard_id': site['shard_id'], 'manifest_sha256': manifest['manifest_sha256']}
        batch.verify_plan_shard({'tasks': [task], 'batch_shard': binding}, registry)
        with self.assertRaises(ValueError): batch.verify_plan_shard({'tasks': [task]}, registry)
        with self.assertRaises(ValueError): batch.guard_shard_task(manifest, 'wrong-worker', task)
        with self.assertRaises(ValueError): batch.guard_shard_task(manifest, site['shard_id'], dict(task, site_uri=site['site_uri'] + 'page'))
        self.assertEqual(task, original)

    def test_unknown_or_changed_capacity_and_incompatible_registry_are_not_adopted(self):
        catalog = self.catalog(); catalog['records'][0].pop('capacity_ref')
        manifest = batch.plan_shards(catalog, run_id=self.run, target=170)
        self.assertIsNone(manifest['sites'][0]['capacity'])
        proof_path = Path(catalog['records'][1]['capacity_ref']['path']); proof_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            batch.plan_shards(catalog, run_id=self.run, target=170)
        registry = self.root / 'incompatible.sqlite3'; allocate(registry, 'https://unrelated.example/', '其他', 'real')
        original = file_sha(registry)
        with self.assertRaisesRegex(ValueError, 'silently adopted'):
            batch.seed_registry(self.manifest(), registry, 'A')
        self.assertEqual(file_sha(registry), original)

    def result_bundle(self, manifest, site, name, *, distinct=False):
        case = delivery_tests.DeliveryContractTests('test_delivery_needs_no_reference_samples_or_capture_archives')
        case.setUp(); self.addCleanup(case.tearDown)
        client = case.client.resolve(); sample = next((client / 'samples').iterdir())
        old = sample.name; sid = site['site_id'] + '_sample_000001'
        annotation = json.loads((sample / 'annotation.json').read_text()); annotation['sample_id'] = sid
        if distinct:
            annotation['task_instruction'] = '比较山地河川地貌、岩层分类以及高原海拔分布'
            for step in annotation['steps']:
                step['page_name'] = '山地地质分布'
                rng = random.Random(31415 + step['step_id'])
                Image.frombytes('RGB', (100, 80), bytes(rng.randrange(256) for _ in range(24000))).save(sample / step['image_path'])
        put(sample / 'annotation.json', annotation); sample.rename(sample.parent / sid)
        (client / 'ground_truth' / (old + '.json')).rename(client / 'ground_truth' / (sid + '.json'))
        with (client / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        rows[0].update(sample_id=sid, site_id=site['site_id'], task_instruction=annotation['task_instruction'],
                       bytes=str(sum(p.stat().st_size for p in (client / 'samples' / sid).rglob('*') if p.is_file())))
        with (client / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        listing = json.loads((client / 'site-list.json').read_text())
        listing['sites'][0].update(site_id=site['site_id'], uri=site['site_uri'], sample_ids=[sid])
        listing['samples'][0].update(sample_id=sid, site_id=site['site_id']); put(client / 'site-list.json', listing)
        prompt = client / '动作空间与系统提示.md'; prompt.write_text('\n' + prompt.read_text()); case.seal()
        reviews = case.reviewed(); report = inspect(None, client, profile=case.profile, reviews=reviews, inspection_stage='payload')
        self.assertEqual(report['delivery_status'], 'PASS')
        payload_path = self.root / (name + '-payload.json'); put(payload_path, report)
        effective, cross = freeze_scope(self.root / (name + '-scope'), [client])
        finalized = finalize_client_package(REPO, client, payload_path, self.root / (name + '-final'),
            effective_set=effective, cross_package_report=cross)
        client = Path(finalized['output'])
        report = inspect(None, client, profile=case.profile, reviews=reviews, inspection_stage='final')
        self.assertEqual(report['delivery_status'], 'PASS'); self.assertTrue(report['release_ready'])
        report_path = self.root / (name + '-qc.json'); report_ref = put(report_path, report)
        registry = self.root / (name + '.sqlite3'); batch.seed_registry(manifest, registry, site['shard_id'])
        self.assertEqual(allocate(registry, site['site_uri'], site['site_category'], 'real', day='20261028', batch_id='B20261028_001')['sample_id'], sid)
        task = self.task(manifest, site)
        raw = self.root / (name + '-capture'); shutil.copytree(client / 'samples' / sid, raw / 'samples' / sid)
        evidence = raw / 'evidence' / sid; evidence.mkdir(parents=True)
        put(evidence / 'step_001.json', {'SYNTHETIC_original_capture': True})
        saved = put(evidence / 'saved_sample.json', {'attempt_id': name, 'sample_id': sid,
            'sample_files_sha256': package_files(raw / 'samples' / sid), 'capture_files_sha256': package_files(evidence)})
        with closing(sqlite3.connect(registry)) as con, con:
            con.executescript(SCHEMA)
            con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (name, 'scope', self.run, task['task_id'], 'v1', 'fixture', json.dumps(task), '学习教育', 'domain', 'reviewed_pass', 1, 9999999999, 0, 1))
            con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (name, 'scope', self.run, name, 'plan', 'request', 'worker', 'lease', 9999999999, sid,
                 site['site_id'], 'B20261028_001', 'collected_pending_review', 1, 1, 2, None, None, None, json.dumps([saved])))
            con.execute('INSERT INTO m4_reviews VALUES(?,?,?,?,?)', (sid, 'pass', json.dumps([report_ref]), 'SYNTHETIC fixture acceptance', 3))
        receipt = batch.freeze_result(registry, report_path, client)
        receipt_ref = put(self.root / (name + '-result.json'), receipt)
        return {'result_ref': receipt_ref, 'report_ref': report_ref, 'dataset': str(client)}, registry

    def test_qc_bound_merge_transport_copy_duplicate_deficit_and_new_sites_only(self):
        manifest = self.manifest(target=170); assigned = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, assigned[0], 'first')
        second, _ = self.result_bundle(manifest, assigned[1], 'second')
        moved = self.root / 'moved-package'; shutil.copytree(first['dataset'], moved)
        relocated = dict(first, dataset=str(moved))
        merged = batch.merge_qualified(manifest, [first, relocated, second])
        self.assertEqual(len(merged['identical_copies']), 1)
        self.assertEqual(merged['qualified_unique_count'], 1)  # identical visual/action content, two IDs -> one effective
        self.assertEqual(len(merged['duplicate_exclusions']), 1)
        self.assertEqual(merged['deficit'], 169)
        next_plan = batch.next_round(manifest, merged)
        next_ids = {row['site_id'] for row in next_plan['sites'] if row['state'] == 'assigned'}
        self.assertFalse(next_ids & {row['site_id'] for row in assigned})
        self.assertEqual({row['site_id']: row['site_uri'] for row in next_plan['sites']},
                         {row['site_id']: row['site_uri'] for row in manifest['sites']})
        batch.seed_registry(next_plan, self.root / 'first.sqlite3', assigned[0]['shard_id'])
        self.model.assert_not_called()

    def test_failure_facts_exclude_reserve_and_unknown_outcomes_are_not_retried(self):
        manifest = self.manifest(); reserve = next(row for row in manifest['sites'] if row['state'] == 'reserve')
        store = SiteFailureStore.initialize({'ledger': str(self.root / 'failure.sqlite3'), 'campaign_id': self.run, 'formal_since': 1})
        store.record(reserve['site_uri'], 'SYNTHETIC-unknown', stage='formal', state='unknown', reason='Synthetic outcome unknown',
            real_execution=True, evidence=[{'fixture': True}], usage_refs=[])
        # Every active worker has closed as unavailable, so missing work cannot
        # be mistaken for completed zero-qualified work during replenishment.
        for site in (row for row in manifest['sites'] if row['state'] == 'assigned'):
            store.record(site['site_uri'], site['site_id'] + '-unknown', stage='formal', state='unknown',
                reason='Synthetic closed unknown shard', real_execution=True, evidence=[{'fixture': True}], usage_refs=[])
        facts = put(self.root / 'facts.json', store.export_facts())
        merged = batch.merge_qualified(manifest, [], facts=[facts]); next_plan = batch.next_round(manifest, merged)
        self.assertEqual(next(row for row in next_plan['sites'] if row['site_id'] == reserve['site_id'])['state'], 'unavailable')
        self.assertEqual(merged['qualified_unique_count'], 0)
        self.assertEqual(merged['deficit'], 170)
        aliased = json.loads(Path(facts['path']).read_text())
        alias = dict(aliased['executions'][0], fact_id='another-fact-id')
        aliased['executions'].append(alias)
        core = {key: aliased[key] for key in ('schema_version', 'campaign_id', 'formal_since', 'failure_limit', 'executions', 'successes')}
        aliased['facts_sha256'] = batch.object_sha256(core)
        alias_ref = put(self.root / 'aliased-facts.json', aliased)
        with self.assertRaisesRegex(ValueError, 'fact ID alias'):
            batch.merge_qualified(manifest, [], facts=[alias_ref])
        value = json.loads(Path(facts['path']).read_text()); value['executions'][0]['state'] = 'failed'
        put(Path(facts['path']), value)
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            batch.merge_qualified(manifest, [], facts=[facts])

    def test_report_or_sample_tamper_and_unaccepted_qc_do_not_count(self):
        manifest = self.manifest(); site = next(row for row in manifest['sites'] if row['state'] == 'assigned')
        bundle, registry = self.result_bundle(manifest, site, 'accepted')
        with closing(sqlite3.connect(registry)) as con, con: con.execute("UPDATE m4_reviews SET decision='reject'")
        with self.assertRaisesRegex(ValueError, 'independently accepted'):
            batch.freeze_result(registry, bundle['report_ref']['path'], bundle['dataset'])
        (Path(bundle['dataset']) / 'README.md').write_text('tampered transport')
        with self.assertRaisesRegex(ValueError, 'dataset bytes'):
            batch.merge_qualified(manifest, [bundle])

    def test_missing_and_conflicting_shard_results_do_not_silently_finish(self):
        manifest = self.manifest(); own = next(row for row in manifest['sites'] if row['state'] == 'assigned')
        bundle, _ = self.result_bundle(manifest, own, 'one-shard')
        merged = batch.merge_qualified(manifest, [bundle])
        self.assertEqual(len(merged['missing_shards']), 1)
        with self.assertRaisesRegex(ValueError, 'missing shards'):
            batch.next_round(manifest, merged)
        value = json.loads(Path(bundle['result_ref']['path']).read_text()); value['source_dataset'] += '-different-body'
        ref = put(self.root / 'conflicting-result.json', batch._seal(value, 'result_sha256'))
        with self.assertRaisesRegex(ValueError, 'Conflicting result bodies'):
            batch.merge_qualified(manifest, [bundle, dict(bundle, result_ref=ref)])

    def test_new_domain_replenishment_preserves_ids_owners_and_rejects_old_aliases(self):
        manifest = self.manifest()
        store = SiteFailureStore.initialize({'ledger': str(self.root / 'closed.sqlite3'), 'campaign_id': self.run, 'formal_since': 1})
        for site in (row for row in manifest['sites'] if row['state'] == 'assigned'):
            store.record(site['site_uri'], site['site_id'], stage='formal', state='unknown', reason='SYNTHETIC closed worker',
                real_execution=True, evidence=[{'fixture': True}], usage_refs=[])
        facts = put(self.root / 'closed-facts.json', store.export_facts())
        merged = batch.merge_qualified(manifest, [], facts=[facts])
        uri = 'https://brand-new.example/'
        evidence = put(self.root / 'new-measurement.json', {'SYNTHETIC': True, 'capacity': 100})
        proof = put(self.root / 'new-capacity.json', {'schema_version': 'webcollect-site-capacity-1', 'site_uri': uri,
            'capacity': 100, 'status': 'verified', 'evidence': [evidence]})
        new = {'records': [{'site_uri': uri, 'site_category': '学习教育', 'capacity': 100, 'capacity_ref': proof}]}
        planned = batch.next_round(manifest, merged, new_catalog=new)
        self.assertTrue(any(row['site_uri'] == uri and row['state'] == 'assigned' for row in planned['sites']))
        for old, current in zip(manifest['sites'], planned['sites']):
            self.assertEqual((old['site_id'], old['shard_id']), (current['site_id'], current['shard_id']))
        old_alias = {'records': [{'site_uri': manifest['sites'][0]['site_uri'] + 'new-page?q=9', 'site_category': '学习教育'}]}
        with self.assertRaisesRegex(ValueError, 'new whole hosts'):
            batch.next_round(manifest, merged, new_catalog=old_alias)

    def test_seeded_worker_policy_requires_exact_original_portable_facts(self):
        store = SiteFailureStore.initialize({'ledger': str(self.root / 'original-stop.sqlite3'), 'campaign_id': self.run, 'formal_since': 1})
        store.record('https://unused.example/', 'original-unknown', stage='formal', state='unknown', reason='SYNTHETIC unknown',
            real_execution=True, evidence=[{'fixture': True}], usage_refs=[])
        facts = put(self.root / 'original-facts.json', store.export_facts())
        manifest = batch.plan_shards(self.catalog(), run_id=self.run, target=170, shard_ids=('A', 'B'), facts=[facts])
        registry = self.root / 'seeded.sqlite3'; batch.seed_registry(manifest, registry, 'A')
        with self.assertRaisesRegex(ValueError, 'site_failure_guard'):
            batch.verify_shard_policy(registry, {})
        other = SiteFailureStore.initialize({'ledger': str(self.root / 'worker-stop.sqlite3'), 'campaign_id': self.run, 'formal_since': 1})
        policy = {'site_failure_guard': other.binding}
        with self.assertRaisesRegex(ValueError, 'exact immutable'):
            batch.verify_shard_policy(registry, policy)
        other.import_facts(store.export_facts())
        batch.verify_shard_policy(registry, policy)

    def test_two_local_semantic_passes_do_not_invent_a_global_difference_pass(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, sites[0], 'local-first')
        second, _ = self.result_bundle(manifest, sites[1], 'local-distinct', distinct=True)
        merged = batch.merge_qualified(manifest, [first, second])
        self.assertEqual(merged['mechanical_unique_count'], 2)
        self.assertEqual(merged['globally_qualified_count'], 0)
        self.assertTrue(merged['global_semantic_review_required'])
        self.assertFalse(merged['release_ready'])
        self.assertTrue(all(row['substantive_difference'] == 'REVIEW_REQUIRED' for row in merged['global_checks']))
        with self.assertRaisesRegex(ValueError, 'global semantic comparison'):
            batch.next_round(manifest, merged)
        self.model.assert_not_called()

    def global_review(self, merged, name, statuses=None, global_sampling_plan=None):
        from quality_inspector.global_difference import review_template
        population = [{'sample_id': row['sample_id'], 'annotation_sha256': row['annotation_sha256'],
                       'evidence_sha256': row['evidence_sha256'], 'sample_path': str(Path(row['annotation_path']).parent)}
                      for row in merged['effective_samples']]
        source_reports = list({row['report']['sha256']: row['report'] for row in merged['sources']}.values())
        value = review_template(population, sampling_plan=global_sampling_plan, source_reports=source_reports)
        by_id = {row['sample_id']: row for row in population}
        for record in value['records']:
            sid = record['sample_id']
            annotation = json.loads((Path(by_id[sid]['sample_path']) / 'annotation.json').read_text())
            steps = [step['step_id'] for step in annotation['steps']]
            record['reviewer'] = {'kind': 'human', 'name': 'SYNTHETIC GLOBAL HUMAN FIXTURE - NO REAL SIGNATURE'}
            record['provenance'].update(description='Authored offline full-population test decision only; no real human service.', frames_viewed=steps)
            record['step_observations'] = [{'step_id': step, 'note': 'SYNTHETIC full-population comparison observation'} for step in steps]
            for key in record['checks']:
                record['checks'][key] = {'status': (statuses or {}).get(sid, 'PASS') if key == 'substantive_difference' else 'REVIEW_REQUIRED',
                    'note': 'SYNTHETIC actual difference fixture only; original four visual decisions are retained.',
                    'evidence_steps': steps if key == 'substantive_difference' else []}
        return put(self.root / (name + '.json'), value)

    def global_sample_plan(self, merged, name, *, human_percent):
        from quality_inspector.delivery_sampling import freeze
        joined = self.root / (name + '-population')
        shutil.copytree(merged['sources'][0]['dataset'], joined)
        for path in (joined / 'samples').iterdir(): shutil.rmtree(path)
        for path in (joined / 'ground_truth').iterdir(): path.unlink()
        rows = []; sites = {}; assignments = []; fields = None
        for sample in merged['effective_samples']:
            path = Path(sample['annotation_path']); source = path.parents[2]; sid = sample['sample_id']
            shutil.copytree(path.parent, joined / 'samples' / sid)
            shutil.copyfile(source / 'ground_truth' / (sid + '.json'), joined / 'ground_truth' / (sid + '.json'))
            with (source / 'metadata.csv').open(newline='') as stream:
                reader = csv.DictReader(stream); fields = reader.fieldnames
                rows.extend(row for row in reader if row['sample_id'] == sid)
            listing = json.loads((source / 'site-list.json').read_text())
            assignment = next(row for row in listing['samples'] if row['sample_id'] == sid); assignments.append(assignment)
            site = next(row for row in listing['sites'] if row['site_id'] == assignment['site_id'])
            sites.setdefault(site['site_id'], {**site, 'sample_ids': []})['sample_ids'].append(sid)
        with (joined / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        put(joined / 'site-list.json', {'schema_version': 'webcollect-site-list-1', 'sites': list(sites.values()), 'samples': assignments})
        (joined / 'SHA256SUMS').unlink(); write_manifest(joined)
        path = self.root / (name + '-sampling.json')
        freeze(joined, path, ai_percent=0, human_percent=human_percent, seed='EXPLICIT-SYNTHETIC-global-policy')
        return {'path': str(path), 'sha256': file_sha(path)}

    def test_global_human_difference_import_recounts_deficit_without_repeating_visual_ai(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, sites[0], 'global-first')
        second, _ = self.result_bundle(manifest, sites[1], 'global-distinct', distinct=True)
        pending = batch.merge_qualified(manifest, [first, second])
        original = [package_files(row['dataset']) for row in (first, second)]
        ref = self.global_review(pending, 'global-human')
        resolved = batch.merge_qualified(manifest, [first, second], global_reviews=[ref])
        self.assertEqual(resolved['globally_qualified_count'], 2)
        self.assertEqual(resolved['deficit'], 168)
        self.assertFalse(resolved['global_semantic_review_required'])
        self.assertEqual(resolved['global_qualification_status'], 'PASS')
        next_plan = batch.next_round(manifest, resolved)
        self.assertEqual(next_plan['previous_global_reviews'], [ref])
        self.assertEqual([package_files(row['dataset']) for row in (first, second)], original)
        self.model.assert_not_called()
        Path(ref['path']).write_text('{}')
        with self.assertRaises(ValueError): batch.next_round(manifest, resolved)

    def test_global_fail_or_pending_never_counts_as_qualified_and_old_scope_cannot_pass(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, sites[0], 'fail-first')
        second, _ = self.result_bundle(manifest, sites[1], 'fail-distinct', distinct=True)
        pending = batch.merge_qualified(manifest, [first, second]); sid = pending['effective_samples'][1]['sample_id']
        for status in ('FAIL', 'REVIEW_REQUIRED'):
            ref = self.global_review(pending, 'global-' + status, {sid: status})
            merged = batch.merge_qualified(manifest, [first, second], global_reviews=[ref])
            self.assertEqual(merged['globally_qualified_count'], 1)
            self.assertEqual(merged['deficit'], 169)
            if status == 'REVIEW_REQUIRED':
                with self.assertRaisesRegex(ValueError, 'global semantic comparison'):
                    batch.next_round(manifest, merged)
            else:
                batch.next_round(manifest, merged)
        ref = self.global_review(pending, 'global-stale-scope')
        value = json.loads(Path(ref['path']).read_text()); value['global_difference_scope']['population_sha256'] = '0' * 64
        stale_ref = put(self.root / 'global-stale.json', value)
        with self.assertRaises(ValueError): batch.merge_qualified(manifest, [first, second], global_reviews=[stale_ref])

    def test_fresh_global_difference_cannot_cover_a_stale_local_visual_rule(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, registry = self.result_bundle(manifest, sites[0], 'stale-rule-first')
        second, _ = self.result_bundle(manifest, sites[1], 'stale-rule-distinct', distinct=True)
        pending = batch.merge_qualified(manifest, [first, second])
        ref = self.global_review(pending, 'fresh-global-difference')
        with patch.dict(semantic.RULE_VERSIONS, privacy='SYNTHETIC-new-privacy-rule'):
            with self.assertRaisesRegex(ValueError, 'affected checks: privacy;'):
                batch.merge_qualified(manifest, [first, second], global_reviews=[ref])
            with self.assertRaisesRegex(ValueError, 'affected checks: privacy;'):
                batch.freeze_result(registry, first['report_ref']['path'], first['dataset'])

    def test_explicit_global_sampling_does_not_force_all_human_or_claim_unselected_semantic_pass(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, sites[0], 'sampling-first')
        second, _ = self.result_bundle(manifest, sites[1], 'sampling-distinct', distinct=True)
        pending = batch.merge_qualified(manifest, [first, second])
        plan = self.global_sample_plan(pending, 'half-human', human_percent=50)
        review = self.global_review(pending, 'half-human-review', global_sampling_plan=plan)
        self.assertEqual(len(json.loads(Path(review['path']).read_text())['records']), 1)
        merged = batch.merge_qualified(manifest, [first, second], global_reviews=[review], global_sampling_plan=plan)
        self.assertEqual(merged['globally_qualified_count'], 2)
        self.assertEqual(merged['global_actual_fifth_pass_count'], 1)
        self.assertEqual(merged['global_policy_admitted_count'], 1)
        self.assertEqual(sum(row['substantive_difference'] == 'NOT_SELECTED' for row in merged['global_checks']), 1)
        self.assertEqual(batch.next_round(manifest, merged)['previous_global_sampling_plan'], plan)
        Path(plan['path']).write_text('{}')
        with self.assertRaises(ValueError): batch.next_round(manifest, merged)
        self.model.assert_not_called()

    def test_explicit_zero_global_sampling_is_policy_admission_not_fabricated_review(self):
        manifest = self.manifest(); sites = [row for row in manifest['sites'] if row['state'] == 'assigned']
        first, _ = self.result_bundle(manifest, sites[0], 'zero-first')
        second, _ = self.result_bundle(manifest, sites[1], 'zero-distinct', distinct=True)
        pending = batch.merge_qualified(manifest, [first, second])
        plan = self.global_sample_plan(pending, 'explicit-zero', human_percent=0)
        merged = batch.merge_qualified(manifest, [first, second], global_sampling_plan=plan)
        self.assertEqual(merged['global_actual_fifth_pass_count'], 0)
        self.assertEqual(merged['global_policy_admitted_count'], 2)
        self.assertEqual(merged['globally_qualified_count'], 2)
        self.assertTrue(all(row['substantive_difference'] == 'NOT_SELECTED' for row in merged['global_checks']))
        batch.next_round(manifest, merged)
        self.model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
