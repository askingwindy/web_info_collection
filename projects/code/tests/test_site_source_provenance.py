"""Offline source-config hash hand-off; no site, model or production execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'site-planner'))
from site_planner.candidate_selection import select_candidates
from site_planner.pipeline import discover
from site_planner.reviews import prepare_review
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.planning import object_sha256


class SiteSourceProvenanceTests(unittest.TestCase):
    URI = 'https://offline-source.example.org/math/area'
    HTML = '<a href="/math/area">离线面积计算器</a>'
    NOW = 1500

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Every network/model/browser/production boundary must fail if reached.
        for target in (
                'socket.socket', 'socket.create_connection', 'socket.getaddrinfo',
                'urllib.request.urlopen', 'urllib.request.build_opener',
                'site_planner.pipeline.fetch_public',
                'webcollect.model_gateway.ModelGateway.call',
                'playwright.async_api.async_playwright',
                'webcollect.collect.collect_plan', 'webcollect.collect_runtime.collect_m4',
                'webcollect.runtime.RuntimeStore.enqueue_plan',
                'webcollect.runtime.RuntimeStore.claim_next'):
            guard = patch(target, side_effect=AssertionError('offline source test forbids ' + target))
            guard.start()
            self.addCleanup(guard.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately differ from canonical snapshots; hashes bind file bytes.
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def source(self, kind):
        source = {'kind': kind, 'category': '在线工具'}
        if kind == 'seed':
            source['uris'] = [self.URI]
        elif kind == 'directory':
            source['uri'] = 'https://offline-source.example.org/catalog'
        else:
            source.update(url_template='https://offline-source.example.org/search?q={q}', query='计算器')
        return source

    def ledger(self, path):
        config = {'schema_version': 'webcollect-batch-config-1',
                  'run_id': 'OFFLINE-source-provenance-fixture', 'mode': 'real', 'model': None,
                  'budget': {'max_discovery_candidates': 10, 'max_probe_pages': 10,
                             'max_run_seconds': 60, 'max_concurrent_jobs': 1,
                             'min_domain_interval_seconds': 1, 'lease_seconds': 30,
                             'max_job_attempts': 1}}
        return BatchLedger(path, config, initialize=True)

    def review_packet(self, source, directory):
        directory.mkdir(parents=True, exist_ok=True)
        image = directory / 'offline-fixture.png'
        Image.new('RGB', (2, 2), 'white').save(image)
        record = {'schema_version': 'webcollect-site-capability-1', 'mode': 'synthetic',
                  'capability_id': 'offline-source-fixture', 'version': 'offline-fixture-v1',
                  'site_uri': self.URI, 'site_category': '在线工具',
                  'source': deepcopy(source), 'observed_at': 1000, 'expires_at': 2000,
                  'status': 'review_required', 'reason': 'Unexecuted offline capability fixture',
                  'capability_scope': {'kind': 'exact-candidate-page', 'page_uris': [self.URI], 'sitewide': False},
                  'supported_actions': ['click'], 'task_families': ['form-workflow'],
                  'capabilities': [{'page_uri': self.URI, 'forms': []}],
                  'representative_pages': [{'uri': self.URI, 'accessible': True, 'rendered': True,
                                            'chinese_ratio': 1, 'routing': 'NORMAL_M1', 'error': None}],
                  'evidence': [{'path': str(image), 'sha256': file_sha(image)}], 'QC_approval': False}
        catalog = directory / 'catalog.json'
        save_json(catalog, {'schema_version': 'webcollect-capability-catalog-1', 'mode': 'synthetic',
                            'records': [record], 'real_supply_verified': False})
        result = prepare_review(catalog, directory.parent / (directory.name + '-review'), now=self.NOW)
        return result, load_json(result['packet'])

    def discovered(self, kind):
        directory = self.root / kind
        sources = self.write(directory / 'source-config.json',
                             {'schema_version': 'webcollect-site-sources-1', 'sources': [self.source(kind)]})
        output = directory / 'discovery'
        if kind != 'seed':
            self.write(output / 'source-0.json', {'html': self.HTML,
                       'landed_uri': 'https://offline-source.example.org/catalog'})
        ledger = self.ledger(directory / 'offline.sqlite3')
        # Public-URL DNS lookup is replaced only for the declared fixture host.
        def fixture_url(uri):
            self.assertTrue(uri.startswith('https://offline-source.example.org/'))
            return '93.184.216.34'
        with patch('site_planner.pipeline.verify_public_url', side_effect=fixture_url):
            result = discover(ledger, sources, output)
        self.assertEqual(result['fixed_candidate_count'], 1)
        self.assertEqual(ledger.visits(), [])
        self.assertEqual(ledger.summary()['model_requests'], 0)
        return sources, result['records'][0]['source']

    def test_directory_discovery_enters_review_with_config_hash(self):
        self.assert_discovery_handoff('directory')

    def test_search_template_discovery_enters_review_with_config_hash(self):
        self.assert_discovery_handoff('search-template')

    def assert_discovery_handoff(self, kind):
        sources, refs = self.discovered(kind)
        result, packet = self.review_packet(refs, self.root / (kind + '-capability'))
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(refs[0]['source_sha256'], file_sha(sources))
        self.assertEqual(refs[0]['content_sha256'], object_sha256(self.HTML))
        self.assertNotEqual(refs[0]['source_sha256'], refs[0]['content_sha256'])
        self.assertEqual(packet['records'][0]['binding']['source_versions'], [file_sha(sources)])
        self.assertFalse(packet['QC_approval'])

    def test_seed_hash_keeps_its_source_config_meaning(self):
        sources, refs = self.discovered('seed')
        _, packet = self.review_packet(refs, self.root / 'seed-capability')
        self.assertEqual(refs[0]['source_sha256'], file_sha(sources))
        self.assertEqual(packet['records'][0]['binding']['source_versions'], [file_sha(sources)])

    def test_frozen_reselection_enters_review_without_rewriting_old_evidence(self):
        for kind in ('directory', 'search-template', 'seed'):
            with self.subTest(kind=kind):
                supply = self.root / ('frozen-' + kind)
                sources = self.write(supply / 'sources-frozen.json',
                                     {'schema_version': 'webcollect-site-sources-1', 'sources': [self.source(kind)]})
                raw = None
                if kind != 'seed':
                    raw = self.write(supply / 'source-0.json',
                                     {'html': self.HTML, 'landed_uri': 'https://offline-source.example.org/catalog'})
                # Legacy directory provenance is retained verbatim, never repaired in place.
                self.write(supply / 'candidates.json', {'schema_version': 'webcollect-site-candidates-1',
                    'mode': 'real', 'discovery_link_occurrences': 1, 'deferred_links': [],
                    'records': [{'site_uri': self.URI, 'source': [{'kind': kind,
                                 'content_sha256': object_sha256(self.HTML)}]}]})
                before = {p.name: p.read_bytes() for p in supply.iterdir()}
                output = self.root / ('selected-' + kind)
                select_candidates([supply], output)
                refs = load_json(output / 'candidates.json')['records'][0]['source']
                _, packet = self.review_packet(refs, self.root / (kind + '-selected-capability'))
                self.assertEqual(refs[0]['source_sha256'], file_sha(sources))
                self.assertEqual(refs[0]['sources_sha256'], file_sha(sources))
                self.assertEqual(refs[0]['source_file_sha256'], file_sha(raw or sources))
                self.assertEqual(packet['records'][0]['binding']['source_versions'], [file_sha(sources)])
                self.assertEqual(before, {p.name: p.read_bytes() for p in supply.iterdir()})

    def test_legacy_or_invalid_sources_cannot_borrow_content_or_alias_hash(self):
        for index, source in enumerate(({'kind': 'directory', 'content_sha256': 'a' * 64},
                                        {'kind': 'directory', 'sources_sha256': 'b' * 64},
                                        {'kind': 'seed', 'source_sha256': 'invalid', 'sources_sha256': 'c' * 64})):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, 'source provenance/version missing'):
                    self.review_packet([source], self.root / ('legacy-' + str(index)))

    def test_frozen_reselection_requires_actual_source_config(self):
        supply = self.root / 'missing-config'
        self.write(supply / 'candidates.json', {'schema_version': 'webcollect-site-candidates-1',
                   'mode': 'real', 'records': [], 'discovery_link_occurrences': 0})
        with self.assertRaises(FileNotFoundError):
            select_candidates([supply], self.root / 'must-not-exist')
        self.assertFalse((self.root / 'must-not-exist').exists())


if __name__ == '__main__':
    unittest.main()
