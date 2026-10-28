"""Controlled detector-boundary tests, never OCR calibration or human review."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from quality_inspector import date_validator as v


class DateTerminalValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'images').mkdir(); (self.root/'ui_tree').mkdir()
        Image.new('RGB', (1280, 720), 'white').save(self.root/'images/final.png')
        self.annotation = {'sample_id': 'CONTROLLED-date', 'task_instruction': v.INSTRUCTION,
            'task_type': ['填写表单'], 'completion_status': 'success', 'final_state_image': 'images/final.png',
            'steps': [{'action': {'action_type': 'complete'}, 'image_path': 'images/final.png', 'ui_tree_path': 'ui_tree/final.json'}]}
        self.tree = {'image_path': 'images/final.png', 'screen_resolution': [1280, 720], 'elements': []}
        for key, text, role, box, editable in [
            ('h','相差天数计算','div',[21,320,632,363],False),
            ('sl','开始日期','label',[36,373,146,411],False), ('s','开始日期','input',[145,373,616,411],True),
            ('el','结束日期','label',[36,426,146,464],False), ('e','结束日期','input',[145,426,616,464],True),
            ('rl','相差','label',[36,537,146,575],False), ('r','相差','input',[145,537,616,575],False),
            ('r2','相差','input',[145,590,616,628],False), ('h2','相差时间计算','div',[21,670,632,713],False)]:
            self.tree['elements'].append({'element_id': key, 'text': text, 'native_role': role,
                'bbox': box, 'visible': True, 'enabled': True, 'inputable': editable})
        self.write_inputs()
        def observation(text, box, confidence=1): return {'text': text, 'bbox': box, 'confidence': confidence}
        self.full = self.ocr_record(None, [observation('相差天数计算',[33,333,120,352]),
            observation('开始日期',[62,384,120,402]), observation('结束日期',[60,438,120,454]),
            observation('相差',[74,548,106,566]), observation('2024-02-28',[152,384,230,402]),
            observation('2024-03-01',[152,438,230,454]), observation('2天',[152,548,184,566],0.5),
            observation('0年0月2天',[154,602,242,620],1)])
        self.roi = self.ocr_record([145,537,616,575], [observation('2天',[153,548,184,565])])

    def write_inputs(self):
        (self.root/'annotation.json').write_text(json.dumps(self.annotation, ensure_ascii=False))
        (self.root/'ui_tree/final.json').write_text(json.dumps(self.tree, ensure_ascii=False))
        self.context = {'uri': v.URI, 'task_family': ['填写表单'], 'sample_path': str(self.root),
                        'sample_id': 'CONTROLLED-date', 'annotation': deepcopy(self.annotation)}

    def ocr_record(self, roi, observations):
        return {'schema_version': 'local-vision-ocr-1', 'engine': 'Apple Vision VNRecognizeTextRequest',
            'coordinate_space': 'top-left-original-pixels', 'image_sha256': v._sha(self.root/'images/final.png'),
            'image_width': 1280, 'image_height': 720, 'recognition_level': 'accurate',
            'recognition_languages': ['zh-Hans','en-US'], 'uses_language_correction': False,
            'custom_words': [], 'whole_original_image': roi is None, 'region_of_interest_pixels': roi,
            'observations': observations}

    def evaluate(self):
        with patch.object(v, '_ocr', side_effect=[self.full, self.roi]) as ocr:
            result = v.evaluate(self.context)
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(ocr.call_args_list[1].args[1], [145,537,616,575])
        return result['checks']['terminal_semantics']

    def test_controlled_confident_pixels_cover_only_terminal_and_preserve_inputs(self):
        before = {str(p): v._sha(p) for p in self.root.rglob('*') if p.is_file()}
        result = self.evaluate()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['diagnostics']['arithmetic']['python_datetime_date_difference_days'], 2)
        self.assertEqual(result['diagnostics']['coverage'], ['terminal_semantics'])
        self.assertEqual(result['diagnostics']['human_review'], 'NOT_PERFORMED')
        self.assertEqual({r['path'] for r in result['evidence']}, {'annotation.json','images/final.png','ui_tree/final.json'})
        self.assertEqual(before, {str(p): v._sha(p) for p in self.root.rglob('*') if p.is_file()})

    def test_real_observed_low_roi_confidence_holds_despite_correct_arithmetic_and_auxiliary_row(self):
        self.roi['observations'][0]['confidence'] = 0.30000001192092896
        result = self.evaluate()
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['diagnostics']['arithmetic_status'], 'PASS')
        self.assertIn('below 0.9', result['reason'])
        self.assertEqual(result['diagnostics']['pixel_terminal_status'], 'REVIEW_REQUIRED')

    def test_no_roi_recognition_cannot_fall_back_to_full_page_or_dom(self):
        self.roi['observations'] = []
        self.tree['elements'][6]['value'] = '2 天'; self.write_inputs()
        self.assertEqual(self.evaluate()['status'], 'REVIEW_REQUIRED')

    def test_low_or_missing_date_ocr_never_uses_annotation_dates(self):
        self.full['observations'][4]['confidence'] = 0.89
        result = self.evaluate()
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['diagnostics']['arithmetic_status'], 'NOT_RUN')

    def test_roi_box_must_be_original_pixels_inside_visible_field(self):
        # Raw ROI-normalized coordinates erroneously scaled by full frame.
        self.roi['observations'][0]['bbox'] = [21,216,103,504]
        self.assertEqual(self.evaluate()['status'], 'REVIEW_REQUIRED')

    def test_confident_wrong_primary_result_is_failure(self):
        self.roi['observations'][0]['text'] = '3天'
        self.assertEqual(self.evaluate()['status'], 'FAIL')

    def test_confident_wrong_dates_are_failure(self):
        self.full['observations'][4]['text'] = '2024-02-27'
        self.roi['observations'][0]['text'] = '3天'
        result = self.evaluate()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['diagnostics']['arithmetic_status'], 'FAIL')

    def test_wrong_image_hash_or_language_correction_holds(self):
        for field, value in [('image_sha256','0'*64), ('uses_language_correction',True)]:
            with self.subTest(field=field):
                old = self.roi[field]; self.roi[field] = value
                self.assertEqual(self.evaluate()['status'], 'REVIEW_REQUIRED')
                self.roi[field] = old

    def test_duplicate_recognition_is_not_cherry_picked(self):
        self.roi['observations'].append(deepcopy(self.roi['observations'][0]))
        self.assertEqual(self.evaluate()['status'], 'REVIEW_REQUIRED')

    def test_exact_uri_and_fixed_task_are_required_before_ocr(self):
        with patch.object(v, '_ocr', side_effect=AssertionError('must not OCR')):
            for key, value in [('uri',v.URI+'?copy=1'), ('task_family',['信息查询'])]:
                context = deepcopy(self.context); context[key] = value
                self.assertIsNone(v.evaluate(context))
            context = deepcopy(self.context); context['annotation']['task_instruction'] += '再做其他任务'
            self.assertIsNone(v.evaluate(context))

    def test_terminal_path_and_tree_resolution_are_bound(self):
        for change in ('final', 'tree', 'context'):
            with self.subTest(change=change):
                self.write_inputs()
                if change == 'final':
                    self.annotation['final_state_image'] = 'images/other.png'; self.write_inputs()
                elif change == 'tree':
                    self.tree['screen_resolution'] = [640,360]; self.write_inputs()
                else: self.context['annotation']['completion_status'] = 'failed'
                with patch.object(v, '_ocr', side_effect=AssertionError('must not OCR')):
                    self.assertEqual(v.evaluate(self.context)['checks']['terminal_semantics']['status'], 'REVIEW_REQUIRED')
                self.annotation['final_state_image'] = 'images/final.png'; self.tree['screen_resolution'] = [1280,720]

    def test_ocr_unavailable_or_timeout_holds(self):
        for error in (ValueError('Vision unavailable'), subprocess.TimeoutExpired('swift',90)):
            with self.subTest(error=str(error)), patch.object(v, '_ocr', side_effect=error):
                result = v.evaluate(self.context)['checks']['terminal_semantics']
                self.assertEqual(result['status'], 'REVIEW_REQUIRED')

    def test_drift_during_ocr_holds(self):
        calls = []
        def run(*args):
            calls.append(1)
            if len(calls) == 2:
                (self.root/'images/final.png').write_bytes(b'changed')
                return self.roi
            return self.full
        with patch.object(v, '_ocr', side_effect=run):
            result = v.evaluate(self.context)['checks']['terminal_semantics']
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertIn('changed during', result['reason'])


if __name__ == '__main__': unittest.main()
