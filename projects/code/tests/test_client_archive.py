"""Final archive binding tests using synthetic fixtures, never real acceptance."""
import json
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile
from test_client_package import fixture,REPO
from webcollect.client_package import build_client_package,sha,sample_hashes
from webcollect.client_reports import archive_client_package
sys.path.insert(0, str(REPO / 'projects/quality-inspector/tests'))
from delivery_scope_fixture import freeze_scope
from quality_inspector.semantic import CHECKS


def rule_ids():
    return {name: digest_value for name, digest_value in
            zip(CHECKS, ['qc-' + name for name in CHECKS])}


class ClientArchive(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);fixture(self.root/'source')
        self.client=Path(build_client_package(REPO,self.root/'source',self.root/'client')['output'])
        sample=self.client/'samples/Web_fixture_001';hashes=sample_hashes(sample)
        self.report={'program':'quality-inspector','dataset':str(self.client),'delivery_status':'PASS','inspection_stage':'final','release_ready':True,
            'semantic_rule_ids':rule_ids(),
            'input_files_sha256':{str(p.relative_to(self.client)):sha(p) for p in self.client.rglob('*') if p.is_file()},
            'root_checksum':{'pass':True},'samples':[{'sample_id':sample.name,'sample_path':str(sample),'annotation_sha256':hashes['annotation.json'],'evidence_sha256':{k:v for k,v in hashes.items() if k!='annotation.json'}}],
            'synthetic_unit_fixture':True}
        self.path=self.root/'qc.json';self.save()
        self.scope_manifest,self.cross_report=freeze_scope(self.root/'scope',[self.client])
    def save(self):self.path.write_text(json.dumps(self.report))
    def test_archive_matches_every_verified_file(self):
        result=archive_client_package(self.client,self.path,self.root/'release.zip',
            effective_set=self.scope_manifest,cross_package_report=self.cross_report)
        with zipfile.ZipFile(result['archive']) as z:
            self.assertEqual(len(z.namelist()),len(self.report['input_files_sha256']))
            for name in z.namelist():self.assertEqual(z.read(name),(self.client/Path(name).relative_to(self.client.name)).read_bytes())
        self.assertEqual(sha(Path(result['archive'])),result['archive_sha256'])
    def test_payload_pending_and_tamper_are_rejected(self):
        for update in [{'inspection_stage':'payload'},{'delivery_status':'FAIL'},{'release_ready':False}]:
            original=dict(self.report);self.report.update(update);self.save()
            self.assertRaisesRegex(ValueError,'final PASS',archive_client_package,self.client,self.path,self.root/'bad.zip')
            self.report=original
        self.save();(self.client/'README.md').write_text('changed')
        self.assertRaises(ValueError,archive_client_package,self.client,self.path,self.root/'tampered.zip')
