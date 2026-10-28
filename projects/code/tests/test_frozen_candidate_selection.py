"""Offline provenance and routing tests; all pages are unexecuted fixtures."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'site-planner'))
from site_planner.candidate_selection import default_rules, select_candidates


class FrozenSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.supply = self.root / 'supply'
        self.supply.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        (self.supply / name).write_text(json.dumps(value, ensure_ascii=False))

    def prepare(self, html, count, extra_sources=None):
        sources = [{'kind': 'directory', 'uri': 'https://tools.example.com/index', 'category': '工具',
                    'allowed_domains': ['tools.example.com']}] + (extra_sources or [])
        self.write('sources-frozen.json', {'schema_version': 'webcollect-site-sources-1', 'sources': sources})
        self.write('source-0.json', {'landed_uri': sources[0]['uri'], 'html': html})
        self.write('candidates.json', {'schema_version': 'webcollect-site-candidates-1', 'mode': 'real',
            'records': [], 'deferred_links': [{'uri': 'https://tools.example.com/math/area'}],
            'discovery_link_occurrences': count, 'source_errors': []})

    def run_selection(self, rules=None):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            return select_candidates([self.supply], self.root / 'out', rules)

    def test_all_occurrences_and_order_survive_filters_and_duplicates(self):
        self.prepare('<a href="/">Home</a><a href="/base/class?classID=1">分类</a>'
                     '<a href="/basic/api/info">Open API</a><a href="/article/a">文章</a>'
                     '<a href="/math/area">计算器</a><a href="/math/area">Again</a>'
                     '<a href="javascript:void(0)">void</a><a href="#here">Jump</a>', 8)
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.supply.iterdir()}
        result = self.run_selection()
        rows = json.loads((self.root / 'out/selection-evidence.json').read_text())['occurrences']
        self.assertEqual([r['source_link_index'] for r in rows], list(range(1, 9)))
        self.assertEqual(result['selected_unique_uris'], 1)
        self.assertEqual(result['selected_from_prior_deferred'], 1)
        self.assertEqual([r['classification'] for r in rows[:5]], ['entry', 'navigation', 'api_document', 'article', 'functional_candidate'])
        self.assertEqual(rows[5]['reason'], 'duplicate_selected_uri')
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.supply.iterdir()})

    def test_source_scope_and_private_uri_cannot_be_promoted(self):
        self.prepare('<a href="https://elsewhere.example.com/math/x">计算器</a>'
                     '<a href="http://127.0.0.1/math/x">计算器</a>'
                     '<a href="https://user:pass@tools.example.com/math/x">计算器</a>', 3)
        result = self.run_selection()
        self.assertEqual(result['selected_unique_uris'], 0)
        self.assertEqual(result['decision_counts']['outside_frozen_source_domain_scope'], 1)
        self.assertEqual(result['classification_counts']['invalid'], 2)

    def test_api_and_articles_override_tool_label(self):
        self.prepare('<a href="/coordinate/convert-documentation">开始使用</a>'
                     '<a href="/article/calculator">在线计算器</a>'
                     '<a href="/string/json">开始使用</a>', 3)
        result = self.run_selection()
        self.assertEqual(result['selected_unique_uris'], 1)
        self.assertEqual(result['classification_counts']['api_document'], 1)
        self.assertEqual(result['classification_counts']['article'], 1)

    def test_caps_keep_all_remaining_occurrences_and_reasons(self):
        self.prepare(''.join('<a href="/math/%s">计算器</a>' % i for i in range(5)), 5)
        rules = default_rules()
        rules['max_selected_per_source'] = 2
        result = self.run_selection(rules)
        self.assertEqual(result['observed_link_occurrences'], 5)
        self.assertEqual(result['selected_unique_uris'], 2)
        self.assertEqual(result['decision_counts']['selection_per_source_limit'], 3)

    def test_source_failure_retains_unknown_denominator(self):
        self.prepare('<a href="/math/a">计算器</a>', 1,
                     [{'kind': 'directory', 'uri': 'https://broken.example.com', 'category': '工具'}])
        self.write('source-failure-1.json', {'source': 'https://broken.example.com', 'reason': 'TLS_FAIL'})
        result = self.run_selection()
        self.assertEqual(result['sources_without_raw_link_denominator'], 1)
        self.assertEqual(result['total_source_link_denominator'], 'UNKNOWN')
        original = json.loads((self.root / 'out/selection-evidence.json').read_text())
        self.assertEqual(original['sources'][1]['unavailable']['source_failure']['reason'], 'TLS_FAIL')

    def test_raw_denominator_mismatch_fails_before_output(self):
        self.prepare('<a href="/math/a">计算器</a>', 2)
        with self.assertRaisesRegex(ValueError, 'denominator'):
            self.run_selection()
        self.assertFalse((self.root / 'out').exists())

    def test_immutable_output_and_no_input_directory_write(self):
        self.prepare('<a href="/math/a">计算器</a>', 1)
        self.run_selection()
        with self.assertRaises(FileExistsError):
            self.run_selection()
        with self.assertRaises(ValueError):
            select_candidates([self.supply], self.supply / 'new')

    def test_every_selected_record_is_unprobed_not_ready(self):
        self.prepare('<a href="/math/a">计算器</a>', 1)
        self.run_selection()
        candidates = json.loads((self.root / 'out/candidates.json').read_text())
        self.assertFalse(candidates['real_supply_verified'])
        self.assertEqual(candidates['sample_ids_allocated'], 0)
        self.assertEqual(candidates['records'][0]['status'], 'not_probed')
        self.assertFalse(candidates['records'][0]['ready'])

    def test_invalid_rules_do_not_create_output(self):
        self.prepare('<a href="/math/a">计算器</a>', 1)
        rules = default_rules()
        rules['rules'][0]['select'] = True
        with self.assertRaises(ValueError):
            self.run_selection(rules)
        self.assertFalse((self.root / 'out').exists())

    def test_nested_anchor_text_has_no_host_or_success_allowlist(self):
        self.prepare('<a href="/unfamiliar/abc"><strong>速度</strong>计算器</a>'
                     '<a href="/unfamiliar/def">无明确线索</a>', 2)
        result = self.run_selection()
        self.assertEqual(result['selected_unique_uris'], 1)
        self.assertEqual(result['decision_counts']['no_functional_cue'], 1)


if __name__ == '__main__':
    unittest.main()
