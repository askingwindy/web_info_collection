"""Controlled admission protocol fixtures; never real review/production evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image

from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.planning import object_sha256
from webcollect.task_admission import (CHECKS, SCHEMAS, attach, context, prepare_packet, reference,
                                      static_identity, verify_live, load_reviews, verify_collection_entry)
from webcollect.task_generation import (compile_form, customer_history_decision, generate,
    generation_source_identity, register_task, semantic_signature, verify_task_admissions)
from test_s0_task_generation import capability, catalog, config


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.registry = self.root / 'CONTROLLED-original-registry.sqlite3'
        with sqlite3.connect(self.registry) as con:
            con.execute('CREATE TABLE m4_tasks(scope_id TEXT,campaign_id TEXT,task_json TEXT)')
        self.manifest = self.root / 'controlled-history.json'; save_json(self.manifest, {'controlled': True})
        self.latest = self.root / 'CONTROLLED-LATEST.md'; self.latest.write_text('Controlled formal-anchor fixture only.\n')
        self.history_scope = {'schema_version': 'webcollect-task-history-scope-1',
                              'manifest': reference(self.manifest), 'formal_anchor': reference(self.latest)}
        self.customer = [{'sample_id': 'CONTROLLED-old-1', 'origin': 'https://example.org',
                          'strategy_id': None, 'semantic_signature': None, 'annotation_sha256': 'fixture'}]
        self.cap, self.spec, self.task, self.frames = self.proposal('base')
        self.ctx = context(self.history_scope, self.customer, self.registry)
        self.packet, self.review = self.prepare('base', self.cap, self.spec, self.task, self.frames)

    def proposal(self, name, *, value='100', uri='https://example.org/tool', selector_suffix=''):
        cap = capability(self.root / name, uri=uri)
        cap['capability_id'] = 'CONTROLLED-' + name
        page = cap['capabilities'][0]; page['title'] = '受控税费估算'
        form = page['forms'][0]; form['label'] = '税费估算'
        for field, label in zip(form['fields'], ['计税金额', '适用税率', '核算税额']):
            field['label'] = label; field['selector'] += selector_suffix
        page['result_targets'] = [{'selector': '#result' + selector_suffix, 'text': '税额等待核算'}]
        spec = {'page_uri': uri, 'form_label': form['label'], 'goal': '在「受控税费估算」中填写计税金额和适用税率，核算并确认税额。',
                'inputs': [{'selector': form['fields'][0]['selector'], 'label': '计税金额', 'value': value},
                           {'selector': form['fields'][1]['selector'], 'label': '适用税率', 'value': '0.1'}],
                'submit': {'selector': form['fields'][2]['selector'], 'label': '核算税额'},
                'completion': {'selector': '#result' + selector_suffix, 'contains': '税额为10元'}}
        task = compile_form(cap, spec)
        folder = self.root / (name + '-frames'); folder.mkdir()
        image = folder / 'CONTROLLED.png'; Image.new('RGB', (1280, 720), 'white').save(image)
        state = {'fixture': True, 'mode': 'synthetic', 'url': uri, 'screen_resolution': [1280, 720],
                 'visible_text': '计税金额\n适用税率\n核算税额\n税额等待核算',
                 'elements': [{'element_id': 'e' + str(n), 'text': label, 'visible': True, 'enabled': True,
                               'inputable': n < 2, 'clickable': True}
                              for n, label in enumerate(['计税金额', '适用税率', '核算税额'])]}
        state_path = folder / 'CONTROLLED-state.json'; save_json(state_path, state)
        capture_path = folder / 'CONTROLLED-capture.json'
        save_json(capture_path, {'fixture': True, 'screenshot_sha256': reference(image)['sha256'],
                                 'observer_sha256': generation_source_identity()['snapshot.js']})
        frames = [{'image': reference(image), 'state': reference(state_path), 'capture': reference(capture_path)}]
        return cap, spec, task, frames

    def prepare(self, name, cap, spec, task, frames, *, mode='synthetic'):
        result = prepare_packet(cap, spec, task, self.ctx, frames, self.root / (name + '-packet'),
                                mode=mode, producer_context_id='CONTROLLED-producer')
        review = load_json(result['review_template']); review.update(completed=True,
            reviewer={'id': 'CONTROLLED-independent-session', 'kind': 'session_ai', 'context_id': 'CONTROLLED-reviewer'},
            reviewed_at=load_json(result['packet']['path'])['created_at'], expires_at=time.time() + 60,
            checks={key: 'PASS' for key in CHECKS}, reason='Controlled fixture protocol positive, not a real reviewer decision.')
        for row in review['role_observations']:
            row.update(frame_index=0, observation='Controlled original tree/PNG contract fixture role.')
        for row in review['history_comparisons']:
            row.update(relation='DISTINCT', reason='Controlled explicit history comparison fixture.')
        review_path = self.root / (name + '-review.json')
        self.write_review(review_path, review, result['packet'])
        return result['packet'], reference(review_path)

    def write_review(self, path, review, packet):
        review = deepcopy(review)
        source_path = self.root / (Path(path).stem + '-source.json')
        frozen = load_json(packet['path'])
        source = {'schema_version': ('webcollect-independent-task-review-source-1' if frozen['mode'] == 'real'
                                    else 'webcollect-controlled-task-review-source-1'),
                  'controlled_protocol_test': True,
                  'reviewed_frame_sha256': sorted({frame['image']['sha256'] for frame in frozen['frames']}),
                  'reviewed_tree_sha256': sorted({frame['state']['sha256'] for frame in frozen['frames']}),
                  'reviewer': review['reviewer'], 'packet_sha256': packet['sha256'], 'completed': True,
                  'reviewed_at': review['reviewed_at'], 'actual_external_model_call': False,
                  'review_body_sha256': object_sha256({k: v for k, v in review.items() if k != 'provenance'})}
        if frozen['mode'] == 'synthetic':
            source['fixture'] = True
        save_json(source_path, source); review['provenance'] = reference(source_path); save_json(path, review)
        return reference(path)

    def altered_review(self, mutate):
        review = load_json(self.review['path']); mutate(review)
        name = 'altered-' + object_sha256(review)[:16] + '-review.json'
        return self.write_review(self.root / name, review, self.packet)

    def admitted(self):
        return attach(self.task, self.packet, self.review, self.ctx, mode='synthetic')

    def test_unknown_task_can_be_admitted_only_with_bound_independent_complete_review(self):
        self.assertIsNone(semantic_signature(self.task))
        self.assertEqual(customer_history_decision(self.task, self.customer)['status'], 'REVIEW_REQUIRED')
        admitted = self.admitted()
        self.assertTrue(semantic_signature(admitted))
        self.assertIsNone(customer_history_decision(admitted, self.customer))
        self.assertFalse(admitted['task_admission']['QC_approval'])
        self.assertEqual(verify_live(admitted, self.ctx, mode='synthetic'), static_identity(admitted))

    def test_parameter_keyword_uri_selector_and_prose_changes_do_not_create_new_business(self):
        admitted = self.admitted()
        cap, spec, task, frames = self.proposal('variant', value='250', uri='https://copy.example/other?amount=250', selector_suffix='-copy')
        spec['goal'] = '另一种文案，仍填写相同金额与税率并核算税额。'
        spec['inputs'].reverse(); spec['completion']['contains'] = '税额为25元'
        task = compile_form(cap, spec)
        packet, review = self.prepare('variant', cap, spec, task, frames)
        variant = attach(task, packet, review, self.ctx, mode='synthetic')
        self.assertEqual(semantic_signature(admitted), semantic_signature(variant))
        ledger = BatchLedger(self.root / 'CONTROLLED-jobs.sqlite3', config(), initialize=True)
        register_task(ledger, admitted, 'first')
        with self.assertRaisesRegex(ValueError, 'parameter/selector substitutions rejected'):
            register_task(ledger, variant, 'copy')

    def test_real_path_rejects_controlled_packet_and_provenance(self):
        with self.assertRaisesRegex(ValueError, 'mode mismatch'):
            attach(self.task, self.packet, self.review, self.ctx, mode='real')

    def test_missing_fail_uncertain_and_unreviewed_checks_never_admit(self):
        for value in ('FAIL', 'REVIEW_REQUIRED', 'NOT_REVIEWED', None):
            ref = self.altered_review(lambda r: r['checks'].__setitem__('business_novelty', value))
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'FAIL/uncertainty'):
                attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_same_or_uncertain_or_omitted_history_comparison_rejects(self):
        for change in ('SAME', 'UNCERTAIN', 'omit'):
            def mutate(review):
                if change == 'omit': review['history_comparisons'] = []
                else: review['history_comparisons'][0]['relation'] = change
            ref = self.altered_review(mutate)
            with self.subTest(change=change), self.assertRaises(ValueError):
                attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_expired_review_rejects_dispatch_but_historical_signature_is_retained(self):
        task = self.admitted(); expiry = load_json(self.review['path'])['expires_at']
        with self.assertRaisesRegex(ValueError, 'expired'):
            verify_live(task, self.ctx, mode='synthetic', now=expiry + 1)
        self.assertEqual(semantic_signature(task), task['task_admission']['semantic_signature'])

    def test_expiry_cannot_extend_original_capability(self):
        ref = self.altered_review(lambda r: r.__setitem__('expires_at', self.cap['expires_at'] + 1))
        with self.assertRaisesRegex(ValueError, 'extends capability'):
            attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_self_review_and_uncalled_glm_claim_reject(self):
        for change in ('self', 'model'):
            def mutate(review):
                if change == 'self': review['reviewer']['context_id'] = 'CONTROLLED-producer'
                else: review['reviewer'].update(kind='model', id='glm-5.3-flash')
            ref = self.altered_review(mutate)
            with self.subTest(change=change), self.assertRaises(ValueError):
                attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_random_business_id_cannot_self_approve(self):
        for change in ('extra', 'registered'):
            def mutate(review):
                if change == 'extra': review['business_id'] = 'infinite-new-business-123'
                else: review['registered_business_id'] = 'infinite-new-business-123'
            ref = self.altered_review(mutate)
            with self.subTest(change=change), self.assertRaises(ValueError):
                attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_registered_business_resolution_preserves_legacy_hash_and_duplicate_gate(self):
        ref = self.altered_review(lambda r: r.__setitem__('registered_business_id', 'body-mass-index-v1'))
        task = attach(self.task, self.packet, ref, self.ctx, mode='synthetic')
        old = {'sample_id': 'old-bmi', 'strategy_id': 'body-mass-index-v1', 'origin': 'https://other.example',
               'semantic_signature': semantic_signature({'deterministic_strategy': {'id': 'body-mass-index-v1'}})}
        self.assertEqual(customer_history_decision(task, [old])['status'], 'REJECTED')

    def test_proposal_and_bound_review_tampering_rejects(self):
        task = deepcopy(self.task); task['operations'][1]['arguments']['text'] = '999'
        with self.assertRaisesRegex(ValueError, 'proposal'):
            attach(task, self.packet, self.review, self.ctx, mode='synthetic')
        self.review_path = Path(self.review['path']); self.review_path.write_text(self.review_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
            attach(self.task, self.packet, self.review, self.ctx, mode='synthetic')

    def test_packet_frame_png_and_independent_source_tampering_rejects(self):
        source = load_json(self.review['path'])['provenance']; Path(source['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
            self.admitted()

    def test_missing_or_unpainted_role_evidence_rejects(self):
        ref = self.altered_review(lambda r: r['role_observations'][0].__setitem__('frame_index', 999))
        with self.assertRaisesRegex(ValueError, 'role observation'):
            attach(self.task, self.packet, ref, self.ctx, mode='synthetic')
        ref = self.altered_review(lambda r: r.__setitem__('role_observations', r['role_observations'][:-1]))
        with self.assertRaisesRegex(ValueError, 'every actual role'):
            attach(self.task, self.packet, ref, self.ctx, mode='synthetic')

    def test_registry_new_task_or_old_payload_drift_invalidates_live_admission(self):
        task = self.admitted()
        with sqlite3.connect(self.registry) as con:
            con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', ('other', 'original', json.dumps({'task_id': 'new'})))
        changed = context(self.history_scope, self.customer, self.registry)
        with self.assertRaisesRegex(ValueError, 'history drift'):
            verify_live(task, changed, mode='synthetic')

    def test_original_history_manifest_and_latest_anchor_drift_rejects(self):
        self.manifest.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
            context(self.history_scope, self.customer, self.registry)

    def test_customer_snapshot_or_capability_provenance_drift_rejects(self):
        changed = deepcopy(self.ctx); changed['customer_history_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'history drift'):
            attach(self.task, self.packet, self.review, changed, mode='synthetic')
        evidence = self.cap['evidence'][0]; Path(evidence['path']).write_text('changed observation')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.admitted()

    def test_source_drift_rejects_new_dispatch_and_does_not_erase_historical_signature(self):
        task = self.admitted()
        source = generation_source_identity(); source['task_admission.py'] = '0' * 64
        with patch('webcollect.task_generation.generation_source_identity', return_value=source):
            with self.assertRaisesRegex(ValueError, 'source version changed'):
                verify_live(task, self.ctx, mode='synthetic')
            self.assertEqual(static_identity(task), task['task_admission']['semantic_signature'])

    def test_same_executor_can_admit_a_genuinely_different_observed_role_workflow(self):
        first = self.admitted()
        cap, spec, _, frames = self.proposal('different')
        labels = ['行程距离', '行程耗时', '核算行程速度']
        for field, label in zip(cap['capabilities'][0]['forms'][0]['fields'], labels):
            field['label'] = label
        cap['capabilities'][0]['result_targets'][0]['text'] = '行程速度等待核算'
        for row, label in zip(spec['inputs'], labels): row['label'] = label
        spec['submit']['label'] = labels[2]
        state = load_json(frames[0]['state']['path'])
        state['visible_text'] = '\n'.join(labels + ['行程速度等待核算'])
        for element, label in zip(state['elements'], labels): element['text'] = label
        Path(frames[0]['state']['path']).write_text(json.dumps(state))
        frames[0]['state'] = reference(frames[0]['state']['path'])
        task = compile_form(cap, spec)
        packet, review = self.prepare('different', cap, spec, task, frames)
        other = attach(task, packet, review, self.ctx, mode='synthetic')
        self.assertNotEqual(semantic_signature(first), semantic_signature(other))
        ledger = BatchLedger(self.root / 'different-jobs.sqlite3', config(), initialize=True)
        register_task(ledger, first, 'first')
        register_task(ledger, other, 'other')

    def test_changed_original_frame_or_observer_binding_rejects(self):
        image = Path(self.frames[0]['image']['path'])
        image.write_bytes(image.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
            self.admitted()

    def real_history_fixture(self):
        from test_client_package import fixture as customer_fixture
        from webcollect.task_generation import _history_package_files, read_customer_history, bind_formal_history
        delivery = self.root / 'controlled-delivery'; package = delivery / 'fixture-package'
        sample = customer_fixture(package, sid='CONTROLLED-history-001')
        save_json(package / 'site-list.json', {'schema_version': 'webcollect-site-list-1',
            'sites': [{'site_id': 'CONTROLLED-site', 'uri': 'https://history.example.org/', 'sample_ids': [sample.name]}],
            'samples': [{'sample_id': sample.name, 'site_id': 'CONTROLLED-site'}]})
        (package / 'README.md').write_text('Controlled customer-layout history fixture, not real delivery.\n')
        latest = delivery / 'LATEST.md'; latest.write_text('[Controlled fixture](fixture-package/README.md)\n')
        manifest = self.root / 'history-set.json'; save_json(manifest, {'schema_version': 'qc-cumulative-set-1',
            'packages': [{'path': str(package), 'package_files_sha256': _history_package_files(package)}]})
        records, scope = read_customer_history(manifest)
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest): scope = bind_formal_history(scope)
        return latest, manifest, records, scope

    def test_reviewed_generator_and_predispatch_recheck_use_original_history_and_no_model(self):
        latest, manifest, records, scope = self.real_history_fixture()
        self.ctx = context(scope, records, self.registry)
        packet, review = self.prepare('generation', self.cap, self.spec, self.task, self.frames)
        references = self.root / 'references.json'; save_json(references, {'schema_version': 'webcollect-task-admission-references-1',
            'reviews': [{'packet': packet, 'review': review}]})
        cat = catalog(self.root / 'catalog.json', [self.cap])
        ledger = BatchLedger(self.root / 'reviewed-jobs.sqlite3', config(), initialize=True)
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest), patch(
                'webcollect.model_gateway.ModelGateway', side_effect=AssertionError('review import must not call a model')):
            result = generate(ledger, cat, self.root / 'generated', history_registry=self.registry,
                              history_set=manifest, generator='reviewed', admission_reviews=[references])
            self.assertEqual(result['generated_tasks'], 1, result)
            plan = load_json(result['plan_file'])
            self.assertIn('task_admission', plan['tasks'][0])
            self.assertEqual(ledger.summary()['model_requests'], 0)
            verify_task_admissions(plan, load_json(cat), self.registry, self.root / 'execution',
                                   customer_history=records, history_scope=scope)
            other = deepcopy(self.task); other['site_uri'] = other['initial_url'] = 'https://other.example/tool'
            with sqlite3.connect(self.registry) as con:
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', ('other-scope', 'original', json.dumps(other)))
            with self.assertRaisesRegex(ValueError, 'history drift'):
                verify_task_admissions(plan, load_json(cat), self.registry, self.root / 'execution',
                                       customer_history=records, history_scope=scope)

    def test_bound_own_resume_does_not_count_original_task_again_but_rejects_unbound_scope_rows(self):
        from webcollect.collect_runtime import runtime_scope
        latest, manifest, records, scope = self.real_history_fixture()
        self.ctx = context(scope, records, self.registry)
        packet, review = self.prepare('resume', self.cap, self.spec, self.task, self.frames)
        admitted = attach(self.task, packet, review, self.ctx, mode='synthetic')
        plan = {'tasks': [admitted], 'generation': {'mode': 'synthetic', 'history_scope': scope}}
        output = self.root / 'execution'; capture = output / 'capture'; capture.mkdir(parents=True)
        own = runtime_scope(capture)
        save_json(capture / 'bootstrap.json', {'schema_version': 'webcollect-bootstrap-m4-1', 'output_path': str(capture),
            'registry_path': str(self.registry), 'manifest': {'runtime_scope_id': own}, 'plan': plan})
        with sqlite3.connect(self.registry) as con:
            con.execute('CREATE TABLE m4_plans(scope_id TEXT,plan_json TEXT)')
            con.execute('INSERT INTO m4_plans VALUES(?,?)', (own, json.dumps(plan)))
            con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', (own, 'original', json.dumps(admitted)))
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            verify_task_admissions(plan, {'records': [self.cap]}, self.registry, output,
                                   customer_history=records, history_scope=scope)
            changed = deepcopy(self.task); changed['site_uri'] = changed['initial_url'] = 'https://other.example/tool'
            with sqlite3.connect(self.registry) as con:
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', (own, 'original', json.dumps(changed)))
            with self.assertRaises(ValueError):
                verify_task_admissions(plan, {'records': [self.cap]}, self.registry, output,
                                       customer_history=records, history_scope=scope)

    def test_reference_manifest_duplicates_cannot_overwrite_review(self):
        path = self.root / 'references.json'; save_json(path, {'schema_version': 'webcollect-task-admission-references-1',
            'reviews': [{'packet': self.packet, 'review': self.review}] * 2})
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            load_reviews([path])

    def collection_entry_fixture(self):
        """Authored real-protocol shape in a temporary CONTROLLED fixture only."""
        from webcollect.browser import fingerprint
        latest, _, records, scope = self.real_history_fixture()
        self.ctx = context(scope, records, self.registry)
        cap = deepcopy(self.cap); cap['mode'] = 'real'
        state = load_json(self.frames[0]['state']['path']); state.pop('fixture'); state['mode'] = 'real'
        state['controlled_protocol_test'] = True
        state_path = self.root / 'CONTROLLED-real-protocol-state.json'; save_json(state_path, state)
        capture = {'controlled_protocol_test': True, 'screenshot_sha256': self.frames[0]['image']['sha256'],
                   'observer_sha256': generation_source_identity()['snapshot.js'], 'snapshot_source': 'browser_dom',
                   'coordinate_space': 'screenshot_css_pixels', 'attempts': [{'dom_stable': True,
                       'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state)}]}
        capture_path = self.root / 'CONTROLLED-real-protocol-capture.json'; save_json(capture_path, capture)
        frames = [{'image': self.frames[0]['image'], 'state': reference(state_path), 'capture': reference(capture_path)}]
        packet, review = self.prepare('CONTROLLED-real-protocol', cap, self.spec, self.task, frames, mode='real')
        task = attach(self.task, packet, review, self.ctx, mode='real')
        plan = {'tasks': [task], 'generation': {'mode': 'real', 'history_scope': scope,
                                             'source_identity': generation_source_identity()}}
        return latest, plan

    def test_direct_collection_entry_rechecks_real_protocol_source_original_history_and_registry(self):
        latest, plan = self.collection_entry_fixture()
        before = self.registry.read_bytes()
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            result = verify_collection_entry(plan, self.registry, self.root / 'wrapper' / 'capture')
        self.assertEqual(result['admitted_tasks_checked'], 1)
        self.assertIn('not QC', result['scope'])
        self.assertEqual(before, self.registry.read_bytes())
        self.assertFalse((self.root / 'wrapper').exists())
        self.assertIsNone(verify_collection_entry({'tasks': [self.task]}, None, None))

    def test_direct_collection_rejects_source_history_and_latest_drift_before_dispatch(self):
        latest, plan = self.collection_entry_fixture()
        capture = self.root / 'wrapper' / 'capture'
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            altered = deepcopy(plan); altered['generation']['source_identity']['preflight.py'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'generation source changed'):
                verify_collection_entry(altered, self.registry, capture)
            latest.write_text(latest.read_text() + 'CONTROLLED changed formal anchor\n')
            with self.assertRaisesRegex(ValueError, 'LATEST/customer history changed'):
                verify_collection_entry(plan, self.registry, capture)
        self.assertFalse(capture.exists())

    def test_direct_collection_rejects_unbound_output_and_controlled_mode(self):
        latest, plan = self.collection_entry_fixture()
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            with self.assertRaisesRegex(ValueError, 'use generation execute'):
                verify_collection_entry(plan, self.registry, self.root / 'arbitrary-output')
            plan['generation']['mode'] = 'synthetic'
            with self.assertRaisesRegex(ValueError, 'requires real generation'):
                verify_collection_entry(plan, self.registry, self.root / 'wrapper' / 'capture')

    def test_direct_collection_rejects_new_original_registry_rows_and_changed_manifest(self):
        latest, plan = self.collection_entry_fixture()
        capture = self.root / 'wrapper' / 'capture'
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            old = deepcopy(self.task); old['site_uri'] = old['initial_url'] = 'https://other.example/tool'
            with sqlite3.connect(self.registry) as con:
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', ('other-scope', 'original', json.dumps(old)))
            with self.assertRaisesRegex(ValueError, 'history drift'):
                verify_collection_entry(plan, self.registry, capture)
            manifest = Path(plan['generation']['history_scope']['manifest']['path'])
            manifest.write_text(manifest.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
                verify_collection_entry(plan, self.registry, capture)
        self.assertFalse(capture.exists())





class CompletionViewTests(unittest.TestCase):
    def setUp(self):
        self.helper = AdmissionTests('test_unknown_task_can_be_admitted_only_with_bound_independent_complete_review')
        self.helper.setUp(); self.addCleanup(self.helper.doCleanups)
        self.root = self.helper.root

    def flow(self, name='flow', *, before_visible=False, after_visible=True, distance=60, moved=60,
             action_changed=False, double_scroll=False, source_pass=True):
        from webcollect.task_admission import completion_scroll
        h = self.helper; folder = self.root / name; folder.mkdir()
        cap, spec, task = deepcopy(h.cap), deepcopy(h.spec), deepcopy(h.task)
        ops = task['operations']; frames = []; count = len(ops)
        for index in range(count + 2):
            state = load_json(h.frames[0]['state']['path'])
            state['scroll'] = [0, moved if index == count + 1 else 0]
            if index >= count:
                state['assertion_targets'] = [{'selector': '#result', 'index': 0,
                    'bbox': [100, 680 - (moved if index == count + 1 else 0), 500, 760 - (moved if index == count + 1 else 0)],
                    'visible': after_visible if index == count + 1 else before_visible,
                    'value': None, 'value_visible': False,
                    'text': '税额为10元' if index == count + 1 else '税额为'}]
            image = folder / f'frame-{index}.png'; Image.new('RGB', (1280, 720), (255, 255, 255-index)).save(image)
            state_file = folder / f'state-{index}.json'; save_json(state_file, state)
            capture = folder / f'capture-{index}.json'; save_json(capture, {'fixture': True,
                'screenshot_sha256': reference(image)['sha256'], 'observer_sha256': generation_source_identity()['snapshot.js']})
            frames.append({'image': reference(image), 'state': reference(state_file), 'capture': reference(capture)})
        action_refs = []
        for index, op in enumerate(ops):
            operation = deepcopy(op)
            if action_changed and index == 1: operation['arguments']['text'] = '999'
            action = {'operation': operation, 'ordinal': index+1, 'before_frame': index, 'after_frame': index+1,
                      'before_state_sha256': frames[index]['state']['sha256'], 'after_state_sha256': frames[index+1]['state']['sha256'],
                      'dispatch_returned': True, 'prepared_element': {'visible': True, 'enabled': True, 'inputable': index<count-1},
                      'pre_execute_same_state': {'matched': True, 'target': {'focused': False}}}
            path = folder / f'action-{index}.json'; save_json(path, action); action_refs.append(reference(path))
        start = {'action': 'necessary_result_scroll_start', 'operation': {'action_type': 'scroll',
                 'arguments': {'direction': 'down'}, 'execution': {'distance': distance}}, 'same_state': {'matched': True}}
        finish = {'action': 'necessary_result_scroll_finished', 'frame': count+1, 'scroll': [0, moved]}
        log = folder / 'operations.jsonl'; log.write_text('\n'.join(json.dumps(row) for row in [start, *([start] if double_scroll else []), finish]))
        summary = folder / 'source-summary.json'; save_json(summary, {'status': 'PASS' if source_pass else 'FAIL', 'failure': None,
            'controlled_saved_html_mode': True, 'actual_frame_count': count+2, 'explicit_actions_dispatched': count,
            'necessary_scrolls_dispatched': 1, 'initial_gate_pass': True, 'terminal_oracle_visibility_pass': True})
        record = folder / 'functional-flow-record.json'; save_json(record, {'schema_version': 'webcollect-controlled-form-functional-flow-1',
            'mode': 'synthetic', 'initial_url': spec['page_uri'], 'frames': frames, 'action_refs': action_refs,
            'scroll_log': reference(log), 'source_summary': reference(summary)})
        spec['completion_view'] = {'schema_version': 'webcollect-bound-completion-view-1', 'record': reference(record)}
        return cap, spec, frames

    def test_only_proven_necessary_scroll_is_appended_and_owns_full_terminal_evidence(self):
        cap, spec, frames = self.flow(); task = compile_form(cap, spec)
        self.assertEqual(len(task['operations']), 6)
        self.assertNotIn('postconditions', task['operations'][-2])
        self.assertEqual(task['operations'][-1]['action_type'], 'scroll')
        self.assertEqual(task['operations'][-1]['execution']['distance'], 60)
        self.assertEqual(task['operations'][-1]['postconditions'], task['final_assertions'])
        self.assertIn('reveal-complete-result', task['required_actions'])
        self.assertEqual(task['subgoals'][-1]['evidence'], [{'operation_id': 'reveal-complete-result', 'postcondition_index': 0}])
        self.assertTrue(task['stop_when_final'])
        packet, review = self.helper.prepare('scroll-approved', cap, spec, task, self.helper.frames)
        admitted = attach(task, packet, review, self.helper.ctx, mode='synthetic')
        from webcollect.task_admission import validate_live_completion_scroll
        current = load_json(frames[-2]['state']['path'])
        self.assertEqual(validate_live_completion_scroll(admitted, admitted['operations'][-1], current)['machine_status'], 'PASS')
        current['assertion_targets'][0]['visible'] = True
        with self.assertRaisesRegex(ValueError, 'PADDING_SCROLL'):
            validate_live_completion_scroll(admitted, admitted['operations'][-1], current)

    def test_padding_scroll_hidden_terminal_wrong_actions_missing_proof_and_extra_scroll_reject(self):
        cases = [('already-visible', {'before_visible': True}), ('still-clipped', {'after_visible': False}),
                 ('wrong-distance', {'moved': 50}), ('wrong-input', {'action_changed': True}),
                 ('two-scrolls', {'double_scroll': True}), ('failed-observation', {'source_pass': False})]
        for name, kwargs in cases:
            cap, spec, _ = self.flow(name, **kwargs)
            with self.subTest(name=name), self.assertRaises(ValueError): compile_form(cap, spec)
        cap, spec = deepcopy(self.helper.cap), deepcopy(self.helper.spec)
        spec['completion_view'] = {'distance': 60}
        with self.assertRaisesRegex(ValueError, 'unbound completion'):
            compile_form(cap, spec)

    def test_default_behavior_and_unknown_model_schema_are_not_extended(self):
        from jsonschema import Draft202012Validator
        from webcollect.task_generation import SPEC_SCHEMA
        self.assertEqual(len(self.helper.task['operations']), 5)
        self.assertIn('postconditions', self.helper.task['operations'][-1])
        cap, spec, _ = self.flow()
        self.assertTrue(list(Draft202012Validator(SPEC_SCHEMA).iter_errors({'tasks': [spec]})))


if __name__ == '__main__':
    unittest.main()
