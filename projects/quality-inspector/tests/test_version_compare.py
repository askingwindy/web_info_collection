"""Version relationships use disposable offline packages, never production data."""
import json
import csv
import shutil
import unittest

import test_delivery
from quality_inspector.checksums import write_manifest
from quality_inspector.cumulative import build_set_manifest, inspect_set
from quality_inspector.profiles import package_files
from quality_inspector.version_compare import compare_versions


class VersionComparisonTests(unittest.TestCase):
    setUp = test_delivery.DeliveryContractTests.setUp
    tearDown = test_delivery.DeliveryContractTests.tearDown
    seal = test_delivery.DeliveryContractTests.seal

    def other(self, *, changed=False):
        other = self.root / 'other'; shutil.copytree(self.client, other)
        if changed:
            path = next(other.glob('samples/*/annotation.json'))
            value = json.loads(path.read_text()); value['final_result'] = '页面显示新的结果'
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            (other / 'SHA256SUMS').unlink(); write_manifest(other)
        return other

    def test_identical_copies_are_reported_and_count_once(self):
        other = self.other(); before = package_files(other)
        result = inspect_set(build_set_manifest([self.client, other]), self.profile)
        self.assertEqual(result['cross_package_status'], 'PASS', result['errors'])
        self.assertEqual(result['sample_count'], 1)
        self.assertEqual(len(result['version_comparison']['identical_copies']), 1)
        self.assertFalse(result['release_ready'])
        self.assertEqual(package_files(other), before)

    def test_same_id_different_bytes_conflict_without_supersedes(self):
        result = inspect_set(build_set_manifest([self.client, self.other(changed=True)]), self.profile)
        self.assertEqual(result['cross_package_status'], 'FAIL')
        self.assertTrue(any('conflicting repeated sample_id' in row['reason'] for row in result['errors']))

    def test_explicit_supersedes_selects_exact_content_and_keeps_old_bytes(self):
        other = self.other(changed=True); before = package_files(self.client)
        manifest = build_set_manifest([self.client, other]); comparison = compare_versions(manifest)
        # Conflicts expose neither a guessed head nor any mtime-selected winner.
        self.assertEqual(comparison['effective_samples'], [])
        left = compare_versions(build_set_manifest([self.client]))['effective_samples'][0]
        right = compare_versions(build_set_manifest([other]))['effective_samples'][0]
        link = {'sample_id': left['sample_id'], 'previous': left['version_id'],
                'current': right['version_id'], 'reason': 'Explicit synthetic revised version'}
        manifest = build_set_manifest([self.client, other], supersedes=[link])
        result = inspect_set(manifest, self.profile)
        self.assertEqual(result['cross_package_status'], 'PASS', result['errors'])
        self.assertEqual(result['version_comparison']['effective_samples'][0]['package'], str(other.resolve()))
        self.assertEqual(len(result['version_comparison']['superseded']), 1)
        self.assertFalse(result['version_comparison']['selection_uses_mtime'])
        self.assertEqual(package_files(self.client), before)

    def test_cyclic_or_dangling_supersedes_never_resolves_a_conflict(self):
        other = self.other(changed=True)
        left = compare_versions(build_set_manifest([self.client]))['effective_samples'][0]
        right = compare_versions(build_set_manifest([other]))['effective_samples'][0]
        link = {'sample_id': left['sample_id'], 'previous': left['version_id'],
                'current': right['version_id'], 'reason': 'Synthetic relation'}
        reverse = dict(link, previous=right['version_id'], current=left['version_id'])
        for links in ([link, reverse], [dict(link, previous='missing-version')], [link, link]):
            with self.subTest(links=links):
                result = compare_versions(build_set_manifest([self.client, other], supersedes=links))
                self.assertEqual(result['status'], 'FAIL')

    def test_invalid_policy_is_not_ignored(self):
        manifest = build_set_manifest([self.client]); manifest['version_policy'] = {'supersedes': []}
        with self.assertRaisesRegex(ValueError, 'versions-1'):
            compare_versions(manifest)

    def test_different_ids_still_run_all_four_duplicate_routes(self):
        other = self.other(); sample = next((other / 'samples').iterdir())
        old = sample.name; new = 'S000001_sample_000001'
        path = sample / 'annotation.json'; value = json.loads(path.read_text()); value['sample_id'] = new
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        sample.rename(sample.parent / new)
        (other / 'ground_truth' / (old + '.json')).rename(other / 'ground_truth' / (new + '.json'))
        with (other / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        rows[0]['sample_id'] = new
        rows[0]['bytes'] = str(sum(p.stat().st_size for p in (other / 'samples' / new).rglob('*') if p.is_file()))
        with (other / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        listing = json.loads((other / 'site-list.json').read_text())
        listing['sites'][0]['sample_ids'] = [new]; listing['samples'][0]['sample_id'] = new
        (other / 'site-list.json').write_text(json.dumps(listing))
        (other / 'SHA256SUMS').unlink(); write_manifest(other)
        profile = json.loads(self.profile.read_text()); profile['targets']['expected_samples'] = 2
        self.profile.write_text(json.dumps(profile))
        result = inspect_set(build_set_manifest([self.client, other]), self.profile)
        self.assertEqual(result['version_comparison']['status'], 'PASS')
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['cross_package_status'], 'FAIL')
        self.assertTrue(all(route in result['duplicates'] for route in ('route1', 'route2', 'route3', 'route4')))
        self.assertGreater(result['duplicates']['route2']['count'], 0)


if __name__ == '__main__':
    unittest.main()
