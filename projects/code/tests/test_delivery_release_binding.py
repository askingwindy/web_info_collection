"""Offline payload -> final -> ZIP reuses actual fixture decisions without AI."""
import json
from copy import deepcopy
from pathlib import Path
import sys
import shutil
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'), str(REPO / 'projects/quality-inspector/tests')]
import test_delivery
from delivery_scope_fixture import freeze_scope
from quality_inspector.engine import inspect
from quality_inspector.profiles import package_files
from quality_inspector import semantic, contract
from webcollect.client_reports import finalize_client_package, archive_client_package


class DeliveryReleaseBindingTests(unittest.TestCase):
    def setUp(self):
        test_delivery.DeliveryContractTests.setUp(self)
        prompt = self.client / '动作空间与系统提示.md'
        prompt.write_text('# 离线测试动作空间\n' + prompt.read_text())
        self.seal()
    tearDown = test_delivery.DeliveryContractTests.tearDown
    seal = test_delivery.DeliveryContractTests.seal
    report = test_delivery.DeliveryContractTests.report
    reviewed = test_delivery.DeliveryContractTests.reviewed

    def test_payload_final_zip_reuse_review_without_any_model_dispatch(self):
        original = package_files(self.client)
        with patch('webcollect.model_gateway.ModelGateway.call', side_effect=AssertionError('No model dispatch')) as model:
            reviews = self.reviewed()
            payload = inspect(None, self.client, profile=self.profile, reviews=reviews, inspection_stage='payload')
            self.assertEqual(payload['delivery_status'], 'PASS')
            payload_path = self.root / 'payload.json'; payload_path.write_text(json.dumps(payload))
            manifest, cross = freeze_scope(self.root / 'scope', [self.client])
            finalized = finalize_client_package(self.root, self.client, payload_path, self.root / 'final',
                effective_set=manifest, cross_package_report=cross)
            final = inspect(None, finalized['output'], profile=self.profile, reviews=reviews, inspection_stage='final')
            self.assertEqual(final['delivery_status'], 'PASS')
            self.assertTrue(final['release_ready'])
            final_path = self.root / 'final.json'; final_path.write_text(json.dumps(final))
            archived = archive_client_package(finalized['output'], final_path, self.root / 'release.zip',
                effective_set=manifest, cross_package_report=cross)
            with zipfile.ZipFile(archived['archive']) as archive:
                final_root = Path(finalized['output'])
                self.assertEqual(len(archive.namelist()), len(package_files(final_root)))
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), (final_root / Path(name).relative_to(final_root.name)).read_bytes())
            model.assert_not_called()
        self.assertEqual(package_files(self.client), original)
        self.assertEqual(finalized['delivery_scope'], archived['delivery_scope'])

    def test_single_package_pass_alone_cannot_finalize_or_archive(self):
        payload = self.report(reviews=self.reviewed())
        self.assertEqual(payload['delivery_status'], 'PASS')
        path = self.root / 'payload.json'; path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'Explicit effective-set'):
            finalize_client_package(self.root, self.client, path, self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())
        manifest, cross = freeze_scope(self.root / 'scope', [self.client])
        finalized = finalize_client_package(self.root, self.client, path, self.root / 'final',
            effective_set=manifest, cross_package_report=cross)
        final = inspect(None, finalized['output'], profile=self.profile, reviews=self.reviewed(), inspection_stage='final')
        final_path = self.root / 'final.json'; final_path.write_text(json.dumps(final))
        with self.assertRaisesRegex(ValueError, 'Explicit effective-set'):
            archive_client_package(finalized['output'], final_path, self.root / 'blocked.zip')
        self.assertFalse((self.root / 'blocked.zip').exists())

    def test_release_output_cannot_mutate_any_other_declared_input_package(self):
        other = self.root / 'other'; shutil.copytree(self.client, other)
        before = package_files(other)
        payload = self.report(reviews=self.reviewed())
        path = self.root / 'payload.json'; path.write_text(json.dumps(payload))
        manifest, cross = freeze_scope(self.root / 'scope', [self.client, other])
        with self.assertRaisesRegex(ValueError, 'outside every effective-set'):
            finalize_client_package(self.root, self.client, path, other / 'bad-output',
                effective_set=manifest, cross_package_report=cross)
        self.assertEqual(package_files(other), before)

    def prepare_actual_final(self):
        reviews = self.reviewed(); payload = self.report(reviews=reviews)
        self.assertEqual(payload['delivery_status'], 'PASS')
        payload_path = self.root / 'payload.json'; payload_path.write_text(json.dumps(payload))
        manifest, cross = freeze_scope(self.root / 'scope', [self.client])
        result = finalize_client_package(self.root, self.client, payload_path, self.root / 'final',
            effective_set=manifest, cross_package_report=cross)
        final = inspect(None, result['output'], profile=self.profile, reviews=reviews, inspection_stage='final')
        self.assertEqual(final['delivery_status'], 'PASS')
        final_path = self.root / 'final.json'; final_path.write_text(json.dumps(final))
        return payload_path, result, final_path, manifest, cross

    def test_cached_true_payload_and_final_reports_reject_a_changed_relevant_rule(self):
        with patch('webcollect.model_gateway.ModelGateway.call', side_effect=AssertionError('No model dispatch')) as model:
            payload, result, final, manifest, cross = self.prepare_actual_final()
            original = package_files(result['output'])
            with patch.dict(semantic.RULE_VERSIONS, privacy='SYNTHETIC-privacy-rule-change'):
                with self.assertRaisesRegex(ValueError, 'affected checks: privacy;'):
                    finalize_client_package(self.root, self.client, payload, self.root / 'stale-final',
                        effective_set=manifest, cross_package_report=cross)
                with self.assertRaisesRegex(ValueError, 'affected checks: privacy;'):
                    archive_client_package(result['output'], final, self.root / 'stale.zip',
                        effective_set=manifest, cross_package_report=cross)
            old = json.loads(payload.read_text()); old.pop('semantic_rule_ids')
            old_path = self.root / 'legacy-payload.json'; old_path.write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError, 'missing/changed semantic rules'):
                finalize_client_package(self.root, self.client, old_path, self.root / 'missing-header',
                    effective_set=manifest, cross_package_report=cross)
            self.assertEqual(package_files(result['output']), original)
            self.assertFalse((self.root / 'stale.zip').exists())
            model.assert_not_called()

    def test_engineering_source_hash_changes_do_not_expire_unchanged_semantic_report(self):
        with patch('webcollect.model_gateway.ModelGateway.call', side_effect=AssertionError('No model dispatch')) as model:
            payload, result, final, manifest, cross = self.prepare_actual_final()
            before = package_files(result['output'])
            engineering_changed = deepcopy(contract.installed_contract())
            engineering_changed['implementation_sha256'] = {'unrelated_engineering_source.py': '0' * 64}
            with patch.object(contract, 'installed_contract', return_value=engineering_changed):
                archived = archive_client_package(result['output'], final, self.root / 'same-semantic.zip',
                    effective_set=manifest, cross_package_report=cross)
            self.assertTrue(Path(archived['archive']).is_file())
            self.assertEqual(package_files(result['output']), before)
            model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
