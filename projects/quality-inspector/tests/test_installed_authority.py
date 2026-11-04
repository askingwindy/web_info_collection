"""Installed-wheel authority checks, no historical payloads or network access."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from quality_inspector import contract, semantic

REPO = Path(__file__).resolve().parents[3]
PACKAGE = Path(contract.__file__).parent
ROLES = {'clarification', 'site_trajectory_scope', 'trajectory_supplement', 'qc_sampling',
         'requirement', 'annex_a', 'annex_b'}


class InstalledAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_source_resource_and_manifest_match_byte_for_byte(self):
        authority = contract.authority()
        self.assertEqual({row['role'] for row in authority['documents']}, ROLES)
        self.assertEqual(authority['source_precedence'], [row['role'] for row in authority['documents']])
        for row in authority['documents']:
            with self.subTest(role=row['role']):
                source = (REPO / row['path']).read_bytes()
                self.assertEqual(source, (PACKAGE / row['resource']).read_bytes())
                self.assertEqual(hashlib.sha256(source).hexdigest(), row['sha256'])

    def test_missing_or_tampered_resource_fails_outside_repository(self):
        copied = self.root / 'installed'; shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns('__pycache__'))
        with patch.object(contract, '__file__', str(copied / 'contract.py')):
            self.assertEqual({row['role'] for row in contract.authority()['documents']}, ROLES)
            path = copied / 'authority/站点分类与轨迹采集口径-20261102.md'
            original = path.read_bytes(); path.write_text('SYNTHETIC tamper')
            with self.assertRaisesRegex(ValueError, 'Installed contract authority changed'): contract.authority()
            path.write_bytes(original); path.unlink()
            with self.assertRaisesRegex(ValueError, 'Installed contract authority changed'): contract.authority()

    def test_wheel_contains_and_loads_authority_from_unrelated_cwd(self):
        project = self.root / 'build-source'
        shutil.copytree(PACKAGE, project / 'quality_inspector', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(PACKAGE.parent / 'pyproject.toml', project / 'pyproject.toml')
        wheels = self.root / 'wheels'
        built = subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'wheel',
                                '--no-cache-dir', '--no-index', '--no-deps', '--no-build-isolation', '--wheel-dir', str(wheels), str(project)],
                               cwd=self.root, capture_output=True, text=True,
                               env={**os.environ, 'PYTHONPATH': os.environ.get('QC_OFFLINE_BUILD_TOOLS', '')})
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        installed = self.root / 'installed'; installed.mkdir()
        with zipfile.ZipFile(next(wheels.glob('*.whl'))) as wheel: wheel.extractall(installed)
        unrelated = self.root / 'unrelated'; unrelated.mkdir()
        script = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
                  'from quality_inspector.contract import fingerprint; '
                  'value,sha=fingerprint(); print(json.dumps({"sha256":sha,"authority":value["authority"]},ensure_ascii=False))')
        result = subprocess.run([sys.executable, '-I', '-c', script, str(installed)],
                                cwd=unrelated, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['sha256'], contract.fingerprint()[1])
        self.assertEqual({row['role'] for row in value['authority']['documents']}, ROLES)
        print('WHEEL offline build/extraction + isolated unrelated-cwd fingerprint PASS; documents=7')

    def test_authority_refresh_changes_contract_but_preserves_all_five_review_decisions(self):
        authority = deepcopy(contract.authority()); before = contract.fingerprint()[1]
        authority['documents'][0]['sha256'] = '0' * 64
        saved_ids = semantic.rule_ids()
        with patch.object(contract, 'authority', return_value=authority):
            self.assertNotEqual(contract.fingerprint()[1], before)
            self.assertEqual(semantic.rule_ids(), saved_ids)
            for status in ('PASS', 'FAIL', 'REVIEW_REQUIRED', 'UNKNOWN'):
                record = {'semantic_rule_ids': saved_ids,
                          'checks': {name: {'status': status, 'note': 'SYNTHETIC historical decision'} for name in saved_ids}}
                original = deepcopy(record); reused = semantic.invalidate_record(record)
                self.assertEqual(reused['checks'], original['checks']); self.assertEqual(record, original)
                self.assertEqual(reused['semantic_reuse']['invalidated_checks'], [])

    def test_coverage_policy_is_bound_without_changing_sample_semantics(self):
        before = contract.fingerprint()[1]; rules = semantic.rule_ids()
        value = deepcopy(contract.installed_contract())
        value['category_coverage_policy']['required_categories']['SYNTHETIC extra'] = 'SYNTHETIC extra'
        with patch.object(contract, 'installed_contract', return_value=value):
            self.assertNotEqual(contract.fingerprint()[1], before)
            self.assertEqual(semantic.rule_ids(), rules)

    def test_modern_intake_reuses_same_evidence_after_authority_refresh_without_resigning(self):
        from test_delivery import DeliveryContractTests
        from quality_inspector.reviews import intake
        case = DeliveryContractTests(); case.setUp(); self.addCleanup(case.tearDown)
        path = case.reviewed(); original = path.read_bytes(); saved = json.loads(original)
        samples = [{'sample_id': row['sample_id'], 'sample_path': str(case.client / 'samples' / row['sample_id'])}
                   for row in saved['records']]
        authority = deepcopy(contract.authority()); authority['documents'][0]['sha256'] = '0' * 64
        with patch.object(contract, 'authority', return_value=authority):
            current = contract.fingerprint()[1]
            self.assertNotEqual(current, saved['records'][0]['baseline_sha256'])
            accepted, errors, migrations = intake(path, samples, current)
        self.assertFalse(errors); self.assertFalse(migrations)
        self.assertEqual(len(accepted), len(samples)); self.assertEqual(path.read_bytes(), original)
        for row in accepted.values():
            self.assertEqual(row['semantic_reuse']['invalidated_checks'], [])
            self.assertEqual(row['baseline_sha256'], saved['records'][0]['baseline_sha256'])
