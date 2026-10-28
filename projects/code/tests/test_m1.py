import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from PIL import Image
from webcollect.__main__ import main
from webcollect.scaffold import scaffold, make_step
from webcollect.metadata import export_metadata, COLUMNS, ARRAY_COLUMNS
from webcollect.storage import allocate
from webcollect.validate import read_json, validate_sample, StrictValidator, SCHEMAS


class M1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=tempfile.TemporaryDirectory()
        cls.fixture=Path(cls.master.name)/'fixture'
        cls.manifest=scaffold(cls.fixture)

    @classmethod
    def tearDownClass(cls): cls.master.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.batch=self.root/'batch'
        shutil.copytree(self.fixture,self.batch)
        self.sample=self.batch/'samples'/self.manifest['sample_id']
        self.data=read_json(self.sample/'annotation.json')

    def save(self):
        (self.sample/'annotation.json').write_text(json.dumps(self.data,ensure_ascii=False))

    def result(self):
        self.save()
        return validate_sample(self.sample,'integration',self.manifest)

    def assert_code(self,code):
        result=self.result()
        self.assertFalse(result['structural_pass'])
        self.assertIn(code,{i['code'] for i in result['issues']},result)

    def test_fixture_passes_not_deliverable(self):
        r=self.result()
        self.assertTrue(r['structural_pass'],r)
        self.assertEqual((r['total_steps'],r['effective_steps']),(6,5))
        self.assertFalse(r['delivery_ready'])
        self.assertTrue(r['pending_checks'])

    def test_all_web_actions_valid(self):
        cases={'click':{'x':200,'y':150},'double_click':{'x':200,'y':150},
            'right_click':{'x':200,'y':150},'type':{'text':'测试文字'},
            'hotkey':{'keys':['ctrl','s']},'scroll':{'x':600,'y':400,'direction':'down'},
            'drag':{'x':200,'y':150,'end_x':700,'end_y':400},'back':{},
            'open_url':{'url':'https://example.invalid/test'},
            'select':{'x':200,'y':150,'option':'测试选项'},'wait':{}}
        for action,args in cases.items():
            with self.subTest(action=action):
                self.data=read_json(self.fixture/'samples'/self.manifest['sample_id']/'annotation.json')
                self.data['steps'][0]=make_step(1,action,args)
                if action=='wait':self.data.update(short_flow=True,short_flow_reason='测试等待不计有效步')
                self.assertTrue(self.result()['structural_pass'],self.result())

    def test_legal_short_flow(self):
        self.data['steps'][0]=make_step(1,'wait',{})
        self.data.update(short_flow=True,short_flow_reason='测试短流程说明')
        self.assertTrue(self.result()['structural_pass'])
        self.assertEqual(self.result()['effective_steps'],4)

    def test_missing_short_reason(self):
        self.data['steps'][0]=make_step(1,'wait',{})
        self.data['short_flow']=True
        self.assert_code('effective_steps')

    def test_spurious_short_flow(self):
        self.data.update(short_flow=True,short_flow_reason='错误短流程标记')
        self.assert_code('short_flow')

    def test_missing_field(self):
        del self.data['task_instruction']; self.assert_code('schema')

    def test_enum(self):
        self.data['task_type']=['不存在']; self.assert_code('schema')

    def test_wrong_types(self):
        for value in [None,[],True,3,'wrong']:
            with self.subTest(value=value):
                self.data['steps']=value; self.assert_code('schema')

    def test_coordinate_integer_not_float_or_bool(self):
        for value in [200.0,True]:
            with self.subTest(value=value):
                self.data['steps'][0]['action']['coordinate']=[value,150]; self.assert_code('schema')

    def test_sequence(self):
        self.data['steps'][1]['step_id']=8; self.assert_code('step_sequence')

    def test_file_sequence(self):
        self.data['steps'][1]['image_path']='images/step_099.png'; self.assert_code('file_sequence')

    def test_missing_image(self):
        (self.sample/'images/step_001.png').unlink(); self.assert_code('missing_file')

    def test_corrupt_image(self):
        (self.sample/'images/step_001.png').write_bytes(b'not png'); self.assert_code('image')

    def test_resolution(self):
        Image.new('RGB',(100,100)).save(self.sample/'images/step_001.png'); self.assert_code('image')

    def test_extra_file(self):
        (self.sample/'debug.txt').write_text('extra'); self.assert_code('extra_file')

    def test_target_reference(self):
        self.data['steps'][0]['action']['target_element_id']='missing'; self.assert_code('target_reference')

    def test_target_text(self):
        self.data['steps'][0]['action']['target_text']='不一致'; self.assert_code('target_text')

    def test_coordinate_bounds(self):
        self.data['steps'][0]['action']['coordinate']=[1280,150]; self.assert_code('coordinate')

    def test_coordinate_bbox(self):
        self.data['steps'][0]['action']['coordinate']=[400,150]
        self.data['steps'][0]['tool_call']['arguments']['x']=400
        self.assert_code('coordinate_bbox')

    def test_tool_arguments(self):
        self.data['steps'][0]['tool_call']['arguments']['selector']='#test'; self.assert_code('schema')

    def test_tool_name_mismatch(self):
        self.data['steps'][0]['tool_call'].update(tool_name='back',arguments={})
        self.assert_code('tool_name')

    def test_invalid_hotkey_call_does_not_crash(self):
        self.data['steps'][0]['action']=make_step(1,'hotkey',{'keys':['enter']})['action']
        self.assert_code('tool_name')

    def test_input_mismatch(self):
        self.data['steps'][1]['action']['input_text']='别的文字'; self.assert_code('input_text')

    def test_noncontrol_empty_values(self):
        self.data['steps'][3]['action']['target_text']='页面'; self.assert_code('noncontrol')

    def test_invalid_drag_end(self):
        self.data['steps'][0]=make_step(1,'drag',{'x':200,'y':150,'end_x':1400,'end_y':400})
        self.assert_code('drag_end')

    def test_end_coordinate_only_for_drag(self):
        self.data['steps'][0]['action']['end_coordinate']=[200,150]; self.assert_code('end_coordinate')

    def test_failed_trajectory(self):
        self.data['completion_status']='failed'; self.assert_code('completion')

    def test_failed_tool(self):
        self.data['steps'][0]['tool_result']['status']='error'; self.assert_code('tool_result')

    def test_final_reference(self):
        self.data['final_state_image']='images/step_001.png'; self.assert_code('final_image')

    def test_complete_only_at_end(self):
        self.data['steps'][0]=make_step(1,'complete',{'status':'success'}); self.assert_code('complete')

    def test_call_ids_unique(self):
        self.data['steps'][1]['tool_call']['call_id']='call_001'; self.assert_code('call_id')

    def test_path_escape(self):
        self.data['steps'][0]['image_path']='../../outside.png'; self.assert_code('path_escape')

    def test_symlink_escape(self):
        path=self.sample/'images/step_001.png'
        path.unlink(); path.symlink_to(self.fixture/'samples'/self.manifest['sample_id']/'images/step_001.png')
        self.assert_code('path_escape')

    def test_annotation_symlink_escape(self):
        path=self.sample/'annotation.json'
        path.unlink(); path.symlink_to(self.fixture/'samples'/self.manifest['sample_id']/'annotation.json')
        r=validate_sample(self.sample,'integration')
        self.assertIn('path_escape',{i['code'] for i in r['issues']})

    def test_corrupt_json(self):
        (self.sample/'annotation.json').write_text('{bad')
        self.assertFalse(validate_sample(self.sample,'integration')['structural_pass'])

    def test_wrong_top_level_json(self):
        for value in [None,[],42]:
            (self.sample/'annotation.json').write_text(json.dumps(value))
            self.assertFalse(validate_sample(self.sample,'integration')['structural_pass'])

    def test_invalid_manifest(self):
        for value in [[],{'sample_kind':'real','sites':[None]},'bad']:
            with self.subTest(value=value):
                r=validate_sample(self.sample,'delivery',value)
                self.assertFalse(r['structural_pass'])

    def test_real_manifest_cannot_relabel_fixture(self):
        manifest={**self.manifest,'sample_kind':'real'}
        self.assertFalse(validate_sample(self.sample,'delivery',manifest)['structural_pass'])

    def test_real_structure_still_needs_semantic_checks(self):
        self.data['task_instruction']='验证测试控件并确认最终页面'
        self.save()
        manifest={**self.manifest,'sample_kind':'real'}
        r=validate_sample(self.sample,'delivery',manifest)
        self.assertTrue(r['structural_pass'],r)
        self.assertFalse(r['delivery_ready'])
        self.assertTrue(r['pending_checks'])

    def test_null_byte_path_is_controlled_error(self):
        self.data['steps'][0]['image_path']='images/invalid\\x00.png'.replace('\\x00',chr(0))
        self.assert_code('path_escape')

    def test_bad_tree_json_and_duplicate_element(self):
        path=self.sample/'ui_tree/step_001.json'
        tree=read_json(path)
        tree['elements']*=2
        path.write_text(json.dumps(tree))
        self.assert_code('element_id')
        path.write_text('{broken')
        self.assert_code('json')

    def test_nonstandard_json_constant(self):
        (self.sample/'annotation.json').write_text('NaN')
        self.assertFalse(validate_sample(self.sample,'integration')['structural_pass'])

    def test_language_prefilter(self):
        self.data['final_result']='DOM 显示内容'; self.assert_code('narrative')

    def test_whitespace_required(self):
        self.data['task_instruction']='  '; self.assert_code('schema')

    def test_tree_parent_cycle(self):
        path=self.sample/'ui_tree/step_001.json'
        tree=read_json(path); tree['elements'][0]['parent_id']='e_1'
        path.write_text(json.dumps(tree)); self.assert_code('parent')

    def test_metadata_roundtrip(self):
        target=self.root/'metadata.csv'
        export_metadata(self.batch,target)
        with target.open(newline='') as f:
            reader=csv.DictReader(f); self.assertEqual(reader.fieldnames,COLUMNS); row=next(reader)
        for key in ARRAY_COLUMNS:self.assertIsInstance(json.loads(row[key]),list)
        self.assertEqual(int(row['bytes']),sum(p.stat().st_size for p in self.sample.rglob('*') if p.is_file()))

    def test_metadata_overwrite_rejected(self):
        with self.assertRaises(FileExistsError): export_metadata(self.batch,self.batch/'metadata.csv')

    def test_metadata_inside_samples_rejected(self):
        with self.assertRaises(ValueError): export_metadata(self.batch,self.sample/'metadata.csv')

    def test_duplicate_manifest_samples(self):
        manifest=read_json(self.batch/'manifest.json'); manifest['samples']*=2
        (self.batch/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): export_metadata(self.batch,self.root/'new.csv')

    def test_registry_cross_batch_and_uri_mapping(self):
        reg=self.root/'registry.sqlite3'
        a=allocate(reg,'https://example.invalid/a','工具',day='20261021')
        b=allocate(reg,'https://example.invalid/a','工具',day='20261021')
        c=allocate(reg,'https://example.invalid/b','工具',day='20261021')
        self.assertEqual(a['site_id'],b['site_id'])
        self.assertTrue(b['sample_id'].endswith('000002'))
        self.assertNotEqual(a['batch_id'],b['batch_id'])
        self.assertNotEqual(a['site_id'],c['site_id'])
        with self.assertRaises(ValueError):allocate(reg,'https://example.invalid/a','其他')
        with sqlite3.connect(reg) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute('INSERT INTO allocations VALUES(?,?,?)',(a['sample_id'],a['site_id'],a['batch_id']))

    def test_scaffold_overwrite_rejected(self):
        with self.assertRaises(FileExistsError):scaffold(self.batch)

    def test_missing_registry_cannot_reuse_existing_batch_ids(self):
        with self.assertRaises(ValueError):scaffold(self.root/'another-batch')
        self.assertFalse((self.root/'another-batch').exists())

    def cli(self,args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return main(args)

    def test_cli_exit_codes_and_report(self):
        report=self.root/'report.json'
        self.assertEqual(self.cli(['validate',str(self.sample),'--mode','integration','--report',str(report)]),0)
        self.assertTrue(read_json(report)['structural_pass'])
        self.assertEqual(self.cli(['validate',str(self.sample)]),2)
        self.assertEqual(self.cli(['validate',str(self.sample),'--manifest',str(self.batch/'manifest.json')]),1)
        self.assertEqual(self.cli(['validate',str(self.sample),'--mode','integration','--report',str(report)]),2)
        self.assertEqual(self.cli(['validate',str(self.sample),'--mode','integration','--report',str(self.sample/'report.json')]),2)

    def test_cli_bad_data_exit_one(self):
        (self.sample/'annotation.json').write_text('{bad')
        self.assertEqual(self.cli(['validate',str(self.sample),'--mode','integration']),1)

    def test_null_tree_even_for_noncontrol_action(self):
        (self.sample/'ui_tree/step_006.json').write_text('null')
        self.assert_code('schema')

    def test_manifest_site_mapping_required(self):
        manifest=copy.deepcopy(self.manifest)
        manifest['sites'][0]['site_id']='S999999'
        self.save()
        self.assertFalse(validate_sample(self.sample,'integration',manifest)['structural_pass'])

    def test_schemas_valid(self):
        for p in SCHEMAS.iterdir():
            if p.name.endswith('.json'): StrictValidator.check_schema(json.loads(p.read_text()))

if __name__=='__main__':unittest.main()
