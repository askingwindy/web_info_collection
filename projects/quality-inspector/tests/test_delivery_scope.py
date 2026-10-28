"""Explicit cross-package delivery binding; offline fixtures only."""
import json
import shutil
import unittest

import test_delivery
from delivery_scope_fixture import freeze_scope
from quality_inspector.delivery_scope import verify_delivery_scope
from quality_inspector.profiles import package_files
from quality_inspector.cumulative import build_set_manifest
from quality_inspector.version_compare import compare_versions
from quality_inspector.checksums import write_manifest


class DeliveryScopeTests(unittest.TestCase):
    setUp = test_delivery.DeliveryContractTests.setUp
    tearDown = test_delivery.DeliveryContractTests.tearDown
    seal = test_delivery.DeliveryContractTests.seal

    def scope(self):
        return freeze_scope(self.root / 'scope', [self.client])

    def test_exact_member_and_only_two_wrapping_files_can_relocate(self):
        manifest, report = self.scope(); original = package_files(self.client)
        binding = verify_delivery_scope(manifest, report, dataset=self.client.resolve())
        final = self.root.resolve() / 'relocated'; shutil.copytree(self.client, final)
        (final / 'qc_report.md').write_text('New deterministic wrapper')
        (final / 'SHA256SUMS').write_text('New deterministic checksum wrapper')
        self.assertEqual(verify_delivery_scope(manifest, report, dataset=final, phase='final'), binding)
        self.assertFalse(binding['semantic_review_repeated'])
        self.assertEqual(package_files(self.client), original)
        with self.assertRaisesRegex(ValueError, 'exact current effective member'):
            verify_delivery_scope(manifest, report, dataset=final, phase='payload')

    def test_missing_scope_or_only_forged_pass_cannot_authorize_delivery(self):
        with self.assertRaisesRegex(ValueError, 'Explicit effective-set'):
            verify_delivery_scope(None, None, dataset=self.client)
        manifest, report = self.scope(); value = json.loads(report.read_text())
        value['version_comparison']['effective_samples'] = []
        report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'report binding changed'):
            verify_delivery_scope(manifest, report, dataset=self.client.resolve())

    def test_original_or_final_payload_tamper_and_addition_reject(self):
        manifest, report = self.scope()
        final = self.root.resolve() / 'final'; shutil.copytree(self.client, final)
        (final / 'README.md').write_text('changed payload')
        with self.assertRaisesRegex(ValueError, 'exact current effective member'):
            verify_delivery_scope(manifest, report, dataset=final, phase='final')
        shutil.copyfile(self.client / 'README.md', final / 'README.md')
        (final / 'unreviewed.txt').write_text('unexpected addition')
        with self.assertRaisesRegex(ValueError, 'exact current effective member'):
            verify_delivery_scope(manifest, report, dataset=final, phase='final')
        (self.client / 'README.md').write_text('original changed')
        with self.assertRaisesRegex(ValueError, 'no longer passes'):
            verify_delivery_scope(manifest, report, dataset=self.client.resolve())

    def test_contract_and_manifest_and_profile_binding_are_checked(self):
        manifest, report = self.scope()
        with self.assertRaisesRegex(ValueError, 'contract identities'):
            verify_delivery_scope(manifest, report, dataset=self.client.resolve(), expected_contract='wrong-contract')
        value = json.loads(manifest.read_text()); value['scope'] = 'different effective set'
        manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'exact effective-set'):
            verify_delivery_scope(manifest, report, dataset=self.client.resolve())

    def test_superseded_member_cannot_be_sealed_even_with_passing_set(self):
        other = self.root.resolve() / 'other'; shutil.copytree(self.client, other)
        path = next(other.glob('samples/*/annotation.json')); value = json.loads(path.read_text())
        value['final_result'] = '页面显示新的结果'
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        (other / 'SHA256SUMS').unlink(); write_manifest(other)
        old = compare_versions(build_set_manifest([self.client]))['effective_samples'][0]
        new = compare_versions(build_set_manifest([other]))['effective_samples'][0]
        relation = {'sample_id': old['sample_id'], 'previous': old['version_id'],
                    'current': new['version_id'], 'reason': 'Explicit offline test revision'}
        manifest, report = freeze_scope(self.root / 'scope', [self.client, other], supersedes=[relation])
        with self.assertRaisesRegex(ValueError, 'superseded/partial/changed'):
            verify_delivery_scope(manifest, report, dataset=self.client.resolve())
        binding = verify_delivery_scope(manifest, report, dataset=other)
        self.assertEqual(binding['source_member'], str(other))


if __name__ == '__main__':
    unittest.main()
