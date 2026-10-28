"""Revised annotations have export provenance, never unchanged capture bindings."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_client_package import fixture, write, REPO
from webcollect.client_package import build_client_package, sample_hashes, sha
from webcollect.narrative_revisions import apply as apply_revision


class RevisionProvenance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source'
        self.sample=fixture(self.source)

    def plan(self, sample=None):
        sample=sample or self.sample
        annotation=json.loads((sample/'annotation.json').read_text());hashes=sample_hashes(sample)
        plan={'schema_version':'webcollect-narrative-revisions-1','author':'AI synthetic regression, not human review',
              'prompt':'仅依据已交付图树修订末步目标，不修改执行动作或原始图树。',
              'samples':[{'sample_id':sample.name,'annotation_sha256':hashes['annotation.json'],
                          'evidence_sha256':{k:v for k,v in hashes.items() if k!='annotation.json'},
                          'edits':[{'path':'steps/5/user_goal','before':annotation['steps'][-1]['user_goal'],
                                    'after':'确认最终测试页面显示已完成结果',
                                    'evidence':['images/step_006.png','ui_tree/step_006.json']}]}]}
        path=self.root/'revisions.json';write(path,plan)
        return path,plan

    def test_revised_index_names_both_annotation_hashes_without_claiming_capture_binding(self):
        original=sample_hashes(self.sample);path,plan=self.plan()
        result=build_client_package(REPO,self.source,self.root/'client',revisions=path)
        output=Path(result['output']);current=sample_hashes(output/'samples'/self.sample.name)
        index=json.loads(Path(result['evidence_output']).read_text());row=index['samples'][0]
        self.assertEqual(index['schema_version'],'webcollect-narrative-provenance-1')
        self.assertFalse(index['capture_binding']);self.assertTrue(index['requires_fresh_export_review'])
        self.assertEqual(row['source_annotation_sha256'],original['annotation.json'])
        self.assertEqual(row['export_annotation_sha256'],current['annotation.json'])
        self.assertNotEqual(row['source_annotation_sha256'],row['export_annotation_sha256'])
        self.assertNotIn('annotation_sha256',row);self.assertNotIn('machine_evidence_status',row)
        self.assertEqual(row['capture_binding_status'],'NOT_A_CAPTURE_BINDING')
        self.assertEqual(row['source_capture_evidence_status'],'AVAILABLE')
        self.assertEqual(row['evidence_sha256'],{k:v for k,v in current.items() if k!='annotation.json'})
        self.assertEqual(index['revision_plan']['sha256'],sha(path))
        self.assertEqual(index['revision_plan']['canonical_sha256'],hashlib.sha256(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(Path(row['export_sample_path']),output/'samples'/self.sample.name)
        self.assertEqual(index['source_samples'][0],row)
        self.assertEqual(original,sample_hashes(self.sample))

    def test_unrevised_export_keeps_legacy_capture_evidence_contract(self):
        result=build_client_package(REPO,self.source,self.root/'client')
        index=json.loads(Path(result['evidence_output']).read_text());row=index['samples'][0]
        self.assertEqual(index['schema_version'],'webcollect-client-evidence-1')
        self.assertEqual(row['annotation_sha256'],sha(self.sample/'annotation.json'))
        self.assertEqual(row['machine_evidence_status'],'AVAILABLE')
        self.assertNotIn('export_annotation_sha256',row);self.assertNotIn('revision_plan',index)
        self.assertEqual(sample_hashes(self.sample),sample_hashes(Path(result['output'])/'samples'/self.sample.name))

    def test_partially_revised_export_reports_unchanged_samples_honestly(self):
        other=fixture(self.source,'Web_fixture_002');path,_=self.plan()
        result=build_client_package(REPO,self.source,self.root/'client',revisions=path)
        index=json.loads(Path(result['evidence_output']).read_text())
        rows={row['sample_id']:row for row in index['samples']}
        self.assertTrue(rows[self.sample.name]['narrative_revision_applied'])
        self.assertFalse(rows[other.name]['narrative_revision_applied'])
        self.assertEqual(rows[other.name]['source_annotation_sha256'],rows[other.name]['export_annotation_sha256'])
        self.assertEqual(rows[other.name]['export_annotation_sha256'],sha(other/'annotation.json'))
        self.assertEqual(index['source_population'],{'total_samples':2,'selected_count':2,'excluded_count':0})

    def test_changed_revision_file_cannot_be_sealed_as_another_applied_plan(self):
        path,_=self.plan()
        def apply_and_change(sample,revision):
            result=apply_revision(sample,revision)
            changed=json.loads(path.read_text());changed['author']='Different author after application';write(path,changed)
            return result
        with patch('webcollect.narrative_revisions.apply',side_effect=apply_and_change):
            with self.assertRaisesRegex(ValueError,'revision plan changed'):
                build_client_package(REPO,self.source,self.root/'client',revisions=path)
        self.assertFalse((self.root/'client').exists());self.assertFalse((self.root/'client.evidence.json').exists())


if __name__=='__main__':unittest.main()
