"""Disposable corpus probes; 200000 counts are in-memory, not real samples."""
from collections import Counter
import csv
import json
from pathlib import Path
import tempfile
import unittest

from test_customer_layout import fixture, put
from quality_inspector.category_coverage import category_coverage
from quality_inspector.checksums import write_manifest
from quality_inspector.cumulative import build_set_manifest, inspect_set, _check_quality_batch
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, load, release_errors


# Authored from requirement section 5, not imported from implementation policy.
PARENTS = ['百科与文档', '新闻资讯', '企业后台与开源演示站', '在线工具',
           '开发者站与 API 文档', '学习教育', '政务与公共服务查询', '图书文化',
           '电商浏览', '交通出行查询', '健康科普', '招聘房产分类信息', '小游戏', '金融股票交易']
FORMAL = {'release': {'kind': 'formal', 'version': 'SYNTHETIC-ONLY'}}


class CoverageDistributionTests(unittest.TestCase):
    def test_five_equal_categories_meet_share_but_miss_nine_required_parents(self):
        counts = dict.fromkeys(PARENTS[:5], 40000)
        result = category_coverage(counts, FORMAL)
        self.assertEqual(sum(counts.values()), 200000)
        self.assertEqual(max(counts.values()) / 200000, .2)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['missing'], PARENTS[5:])
        print('SYNTHETIC 200000-count five-category counterexample:', json.dumps(result, ensure_ascii=False))

    def test_all_fourteen_pass_without_requiring_engineering_category(self):
        counts = dict.fromkeys(PARENTS, 14285); counts[PARENTS[0]] += 10
        result = category_coverage(counts, FORMAL)
        self.assertEqual(sum(counts.values()), 200000)
        self.assertEqual(result['status'], 'PASS'); self.assertEqual(result['missing'], [])
        self.assertNotIn('知识文库', result['required'])
        self.assertEqual(result['sample_counts'], counts)
        print('SYNTHETIC 200000-count all-fourteen positive:', json.dumps(result, ensure_ascii=False))

    def test_aliases_count_once_and_unknown_or_empty_never_fill_a_parent(self):
        result = category_coverage({'医疗健康科普': 3, '健康科普': 2, '图书影音榜单': 7,
                                    '百科与文档站': 1, '开发者站与API文档': 1,
                                    '金融股票交易': 1, 'UNKNOWN': 200000, '': 50,
                                    '知识文库': 10, '新闻资讯/小游戏': 20}, FORMAL)
        self.assertEqual(result['sample_counts']['健康科普'], 5)
        self.assertEqual(result['sample_counts']['图书文化'], 7)
        self.assertEqual(len(result['present']), 5)
        self.assertIn('小游戏', result['missing']); self.assertIn('新闻资讯', result['missing'])
        self.assertEqual(result['other_category_counts']['UNKNOWN'], 200000)

    def test_trailing_enumeration_word_is_free_text_not_a_finance_alias(self):
        counts = dict.fromkeys(PARENTS[:-1], 1); counts['金融股票交易等'] = 500
        result = category_coverage(counts, FORMAL)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['missing'], ['金融股票交易'])
        self.assertEqual(result['sample_counts']['金融股票交易'], 0)
        self.assertEqual(result['other_category_counts']['金融股票交易等'], 500)
        counts['金融股票交易'] = 1
        self.assertEqual(category_coverage(counts, FORMAL)['status'], 'PASS')

    def test_scope_is_explicit_formal_only(self):
        for configuration in ({}, {'release': {'kind': 'experiment'}},
                              {'release': {'kind': 'formal-package'}}, {'scope': 'pilot'}):
            with self.subTest(configuration=configuration):
                self.assertEqual(category_coverage({'在线工具': 10000}, configuration)['status'], 'NOT_APPLICABLE')

    def test_quality_batch_5000_share_short_and_unique_near_duplicate_limits(self):
        ids = [f'fixture-{i}' for i in range(5000)]
        categories = {sid: PARENTS[i % 5] for i, sid in enumerate(ids)}
        scan = {'rows': [{'sample_id': sid} for sid in ids + ['old']],
                'summary': {'analysis_status': 'COMPLETE', 'unadjudicated_pair_count': 0},
                'route1': {'confirmed_pair_count': 0, 'pairs': []},
                'route2': {'count': 0, 'confirmed_pairs': []},
                'route3': {'count': 0, 'candidates': []}, 'route4': {'count': 0, 'candidates': []}}
        targets = {'max_short_flow_share': .02, 'max_category_share': .2}
        self.assertEqual(_check_quality_batch(ids, categories, set(ids[:100]), scan, targets)['status'], 'PASS')
        # Exactly 20% per parent is legal despite missing nine final-corpus classes.
        categories[ids[1]] = categories[ids[0]]
        rejected = _check_quality_batch(ids, categories, set(), scan, targets)
        self.assertIn('quality batch category share exceeds the limit', rejected['errors'])
        categories = {sid: PARENTS[i % 5] for i, sid in enumerate(ids)}
        self.assertIn('quality batch short-flow share exceeds the limit',
                      _check_quality_batch(ids, categories, set(ids[:101]), scan, targets)['errors'])
        scan['route3'].update(count=6, candidates=[{'sample_ids': [sid, 'old']} for sid in ids[:6]])
        self.assertIn('quality batch four-route duplicate check failed',
                      _check_quality_batch(ids, categories, set(), scan, targets)['errors'])

    def test_aliases_cannot_split_quality_batch_twenty_percent_quota(self):
        ids = [f'fixture-{i}' for i in range(5000)]
        categories = {sid: ['医疗健康科普', '健康科普', '新闻资讯', '在线工具', '小游戏'][i % 5]
                      for i, sid in enumerate(ids)}
        scan = {'rows': [{'sample_id': sid} for sid in ids],
                'summary': {'analysis_status': 'COMPLETE', 'unadjudicated_pair_count': 0},
                'route1': {'confirmed_pair_count': 0, 'pairs': []},
                'route2': {'count': 0, 'confirmed_pairs': []},
                'route3': {'count': 0, 'candidates': []}, 'route4': {'count': 0, 'candidates': []}}
        result = _check_quality_batch(ids, categories, set(), scan,
                                      {'max_short_flow_share': .02, 'max_category_share': .2})
        self.assertEqual(result['categories']['健康科普'], 2000)
        self.assertEqual(result['status'], 'FAIL')


class EffectiveCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def package(self, labels):
        _, client, _ = fixture(self.root / 'fixture', len(labels))
        with (client / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        sites = []; assignments = []
        for index, (row, label) in enumerate(zip(rows, labels)):
            site = f'SITE{index}'; row.update(site_id=site, site_category=label)
            sites.append({'site_id': site, 'uri': f'https://fixture{index}.invalid/',
                          'site_category': label, 'sample_ids': [row['sample_id']]})
            assignments.append({'sample_id': row['sample_id'], 'site_id': site})
        with (client / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
        put(client / 'site-list.json', {'schema_version': 'webcollect-site-list-1', 'sites': sites, 'samples': assignments})
        (client / 'SHA256SUMS').unlink(); write_manifest(client)
        return client

    def profile(self, kind='formal'):
        value = json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
        value.update(FORMAL if kind == 'formal' else {'release': {'kind': kind, 'version': 'SYNTHETIC-ONLY'}})
        value['targets'].update(expected_samples=200000 if kind == 'formal' else 10000,
                                category_share='enforced')
        path = self.root / 'profile.json'; put(path, value); return path

    def test_normal_inspect_set_all_classes_pass_coverage_but_other_gates_still_fail(self):
        client = self.package(PARENTS)
        result = inspect_set(build_set_manifest([client]), self.profile())
        self.assertEqual(result['sample_count'], 14)
        self.assertEqual(result['statistics']['category_coverage']['status'], 'PASS')
        self.assertEqual(set(result['statistics']['category_coverage']['sample_counts'].values()), {1})
        self.assertEqual(result['mechanical_status'], 'FAIL')
        self.assertTrue(any('20 packages' in row['reason'] for row in result['errors']))
        self.assertGreater(result['duplicates']['route2']['count'], 0)
        self.assertFalse(result['release_ready'])
        print('NORMAL inspect_set: 14 disposable samples; coverage PASS, formal totals and duplicates FAIL')

    def test_normal_inspect_set_missing_categories_is_locatable_and_member_scope_is_isolated(self):
        client = self.package(PARENTS[:5])
        result = inspect_set(build_set_manifest([client]), self.profile())
        error = next(row for row in result['errors'] if row.get('rule_id') == 'FORMAL_CATEGORY_COVERAGE')
        self.assertEqual(error['missing_categories'], PARENTS[5:])
        self.assertEqual(result['statistics']['maximum_category_share'], .2)
        member = inspect_set(build_set_manifest([client]), self.profile('formal-package'))
        self.assertEqual(member['statistics']['category_coverage']['status'], 'NOT_APPLICABLE')
        self.assertFalse(any(row.get('rule_id') == 'FORMAL_CATEGORY_COVERAGE' for row in member['errors']))
        print('NORMAL inspect_set: 5 disposable samples, each 20%; missing:', ', '.join(error['missing_categories']))

    def test_unresolved_versions_and_unmapped_metadata_cannot_supply_a_class(self):
        import shutil
        client = self.package(['医疗健康科普'])
        other = self.root / 'conflict'; shutil.copytree(client, other)
        annotation = next(other.glob('samples/*/annotation.json'))
        value = json.loads(annotation.read_text()); value['final_result'] = '不同版本的合成结果'; put(annotation, value)
        (other / 'SHA256SUMS').unlink(); write_manifest(other)
        result = inspect_set(build_set_manifest([client, other]), self.profile())
        self.assertEqual(result['sample_count'], 0)
        self.assertEqual(result['statistics']['category_coverage']['sample_counts']['健康科普'], 0)
        self.assertEqual(result['version_comparison']['status'], 'FAIL')
        listing = json.loads((client / 'site-list.json').read_text()); listing['sites'][0]['site_category'] = 'UNKNOWN'
        put(client / 'site-list.json', listing); (client / 'SHA256SUMS').unlink(); write_manifest(client)
        result = inspect_set(build_set_manifest([client]), self.profile())
        self.assertIn('健康科普', result['statistics']['category_coverage']['missing'])

    def test_10000_member_profile_and_20x10000_formal_totals_remain_separate(self):
        configuration = load(self.profile('formal-package'))['configuration']
        self.assertEqual(configuration['targets']['expected_samples'], 10000)
        self.assertEqual(release_errors(configuration, [{'sample_count': 10000}], {}, 10000), [])
        configuration = load(self.profile())['configuration']
        self.assertEqual(release_errors(configuration, [{'sample_count': 10000}] * 20, {}, 200000), [])
        self.assertTrue(release_errors(configuration, [{'sample_count': 10000}] * 19, {}, 190000))

    def test_same_site_alias_across_packages_merges_parent_but_keeps_local_source_binding(self):
        import shutil
        client = self.package(['医疗健康科普'])
        other = self.root / 'other'; shutil.copytree(client, other)
        old = next((other / 'samples').iterdir()); sid = 'OTHER_sample_000001'; sample = old.rename(old.with_name(sid))
        annotation = json.loads((sample / 'annotation.json').read_text()); annotation['sample_id'] = sid
        put(sample / 'annotation.json', annotation)
        (other / 'ground_truth' / (old.name + '.json')).rename(other / 'ground_truth' / (sid + '.json'))
        with (other / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        rows[0].update(sample_id=sid, site_category='健康科普',
                       bytes=str(sum(p.stat().st_size for p in sample.rglob('*') if p.is_file())))
        with (other / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
        listing = json.loads((other / 'site-list.json').read_text())
        listing['sites'][0].update(site_category='健康科普', sample_ids=[sid]); listing['samples'][0]['sample_id'] = sid
        put(other / 'site-list.json', listing); (other / 'SHA256SUMS').unlink(); write_manifest(other)
        manifest = build_set_manifest([client, other])
        result = inspect_set(manifest, self.profile())
        self.assertEqual(result['statistics']['categories'], {'健康科普': 2})
        self.assertEqual(result['statistics']['category_coverage']['sample_counts']['健康科普'], 2)
        self.assertEqual(result['statistics']['applications']['counts'], {'fixture0.invalid': 2})
        self.assertFalse(any('identity/category changes' in row['reason'] for row in result['errors']))
        self.assertEqual(result['manifest'], manifest)
        # An alias in metadata alone cannot override this package's site list.
        listing['sites'][0]['site_category'] = '在线工具'; put(other / 'site-list.json', listing)
        (other / 'SHA256SUMS').unlink(); write_manifest(other)
        rejected = inspect_set(build_set_manifest([client, other]), self.profile())
        self.assertTrue(any('site/category/sample mapping differs' in row['reason'] for row in rejected['errors']))
        self.assertEqual(rejected['statistics']['category_coverage']['sample_counts']['健康科普'], 1)

    def test_single_package_qc_enforces_parent_share_without_splitting_aliases(self):
        from quality_inspector.engine import inspect
        from quality_inspector.profiles import package_files
        client = self.package(['医疗健康科普', '健康科普', '在线工具', '小游戏', '新闻资讯'])
        profile = json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
        profile['targets'].update(expected_samples=5, category_share='enforced')
        profile['release'] = {'kind': 'experiment', 'version': 'SYNTHETIC-ONLY'}
        path = self.root / 'profile.json'; put(path, profile)
        original = package_files(client)
        report = inspect(None, client, profile=path, inspection_stage='payload')
        share = next(row for row in report['dataset_checks'] if row['rule_id'] == 'DELIVERY_CATEGORY_SHARE')
        self.assertEqual(share['status'], 'FAIL')
        self.assertEqual(share['actual'], .4)
        self.assertEqual(report['statistics']['categories']['健康科普'], 2)
        self.assertEqual(next(row['status'] for row in report['dataset_checks']
                              if row['rule_id'] == 'DELIVERY_ACCOUNTING'), 'PASS')
        profile['targets']['category_share'] = 'report-only'
        profile['authority'] = 'Explicit disposable fixture scope only, never a production waiver'
        put(path, profile)
        local = inspect(None, client, profile=path, inspection_stage='payload')
        self.assertFalse(any(row['rule_id'] == 'DELIVERY_CATEGORY_SHARE' for row in local['dataset_checks']))
        self.assertEqual(local['statistics']['categories']['健康科普'], 2)
        self.assertEqual(package_files(client), original)

    def test_alias_labels_do_not_collapse_different_raw_source_versions(self):
        import shutil
        from quality_inspector.profiles import package_files
        client = self.package(['医疗健康科普'])
        other = self.root / 'other-source-version'; shutil.copytree(client, other)
        with (other / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        rows[0]['site_category'] = '健康科普'
        with (other / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
        listing = json.loads((other / 'site-list.json').read_text()); listing['sites'][0]['site_category'] = '健康科普'
        put(other / 'site-list.json', listing); (other / 'SHA256SUMS').unlink(); write_manifest(other)
        before = [package_files(package) for package in (client, other)]
        report = inspect_set(build_set_manifest([client, other]), self.profile())
        self.assertEqual(report['version_comparison']['status'], 'FAIL')
        self.assertEqual(report['version_comparison']['occurrence_count'], 2)
        self.assertEqual(report['sample_count'], 0)
        self.assertEqual(report['statistics']['category_coverage']['sample_counts']['健康科普'], 0)
        self.assertEqual([package_files(package) for package in (client, other)], before)
