"""Narrow local pixel validator for one fixed Lddgo civil-date task.

Only terminal_semantics is implemented. OCR is always executed against the
original final PNG; UI-tree labels/boxes locate observations, never supply values.
Low confidence is REVIEW_REQUIRED, including the currently observed real sample.
No registration, review, candidate file, or human decision is changed here.
"""
import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

URI = 'https://www.lddgo.net/common/date'
INSTRUCTION = ('在「日期计算器」的「相差天数计算」中，将开始日期填写为2024-02-28、'
               '结束日期填写为2024-03-01，点击「计算」并核对两日期相差2天。')
EXPECTED_DATES = ('2024-02-28', '2024-03-01')
MIN_CONFIDENCE = 0.9
HELPER = Path(__file__).with_name('vision_ocr.swift')
HELPER_SHA256 = hashlib.sha256(HELPER.read_bytes()).hexdigest()
# The existing registry fingerprints a validator's version and Python source.
# Include the Swift dependency in that version; a later in-process change holds.
VERSION = 'date-terminal-vision-1+' + HELPER_SHA256


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _file(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Evidence path escapes sample')
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('Evidence must be an ordinary in-sample file')
    return path


def _box(value, size):
    if (not isinstance(value, list) or len(value) != 4 or
            any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in value)):
        raise ValueError('Invalid pixel box')
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 <= size[0] and 0 <= y1 < y2 <= size[1]):
        raise ValueError('Box clipped or outside original frame')
    return value


def _inside(inner, outer):
    return all((inner[0] >= outer[0], inner[1] >= outer[1], inner[2] <= outer[2], inner[3] <= outer[3]))


def _one(rows, reason):
    if len(rows) != 1:
        raise ValueError(reason)
    return rows[0]


def _anchors(tree, size):
    rows = tree['elements']
    visible = [r for r in rows if r.get('visible') is True and r.get('enabled') is True]
    heading = _one([r for r in visible if r.get('text') == '相差天数计算'], 'Ambiguous date business heading')
    h = _box(heading['bbox'], size)
    next_heading = _one([r for r in visible if r.get('text') == '相差时间计算'], 'Missing lower business boundary')
    lower = _box(next_heading['bbox'], size)[1]
    region = [h[0], h[3], h[2], lower]
    fields = [r for r in visible if r.get('native_role') == 'input' and _inside(_box(r['bbox'], size), region)]
    start = _one([r for r in fields if r.get('text') == '开始日期' and r.get('inputable') is True], 'Ambiguous start input')
    end = _one([r for r in fields if r.get('text') == '结束日期' and r.get('inputable') is True], 'Ambiguous end input')
    results = sorted([r for r in fields if r.get('text') == '相差' and r.get('inputable') is False], key=lambda r: r['bbox'][1])
    if len(results) != 2 or not (start['bbox'][3] < end['bbox'][1] < results[0]['bbox'][1] < results[1]['bbox'][1]):
        raise ValueError('Unsupported date result layout')
    anchors = {'heading': heading, 'start': start, 'end': end, 'result': results[0]}
    for name in ('start', 'end', 'result'):
        field = anchors[name]; b = field['bbox']
        anchors[name + '_label'] = _one([r for r in visible
            if r.get('native_role') == 'label' and r.get('text') == field['text']
            and abs(r['bbox'][1] - b[1]) <= 1 and abs(r['bbox'][3] - b[3]) <= 1
            and r['bbox'][0] < b[0] and r['bbox'][2] <= b[0] + 1], 'Missing visible field label')
    for row in anchors.values(): _box(row['bbox'], size)
    return anchors


def _ocr(image, roi=None):
    if sys.platform != 'darwin' or not Path('/usr/bin/swift').is_file():
        raise ValueError('Local Apple Vision/Swift is unavailable')
    if _sha(HELPER) != HELPER_SHA256:
        raise ValueError('OCR helper changed after validator load')
    command = ['/usr/bin/swift', str(HELPER), str(image)]
    if roi is not None: command.append(','.join(str(n) for n in roi))
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode:
        raise ValueError('Local OCR failed: ' + result.stderr[-500:])
    if _sha(HELPER) != HELPER_SHA256:
        raise ValueError('OCR helper changed during recognition')
    return json.loads(result.stdout)


def _ocr_contract(record, image_sha, size, roi):
    expected = {'schema_version': 'local-vision-ocr-1', 'engine': 'Apple Vision VNRecognizeTextRequest',
        'coordinate_space': 'top-left-original-pixels', 'image_sha256': image_sha,
        'image_width': size[0], 'image_height': size[1], 'recognition_level': 'accurate',
        'recognition_languages': ['zh-Hans', 'en-US'], 'uses_language_correction': False,
        'custom_words': [], 'whole_original_image': roi is None, 'region_of_interest_pixels': roi}
    if any(record.get(k) != v for k, v in expected.items()):
        raise ValueError('OCR provenance/configuration does not bind this original PNG/ROI')
    for row in record['observations']:
        _box(row['bbox'], size)
        confidence = row['confidence']
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1 or not isinstance(row['text'], str)):
            raise ValueError('Malformed OCR observation')


def _read(record, anchor, pattern, name, diagnostics):
    rows = [r for r in record['observations'] if _inside(r['bbox'], anchor['bbox'])]
    row = _one(rows, 'OCR missing or ambiguous in ' + name)
    diagnostics[name] = {'ocr': row, 'ui_element_id': anchor['element_id'], 'ui_visible_bbox': anchor['bbox']}
    if row['confidence'] < MIN_CONFIDENCE:
        raise ValueError(f"OCR confidence {row['confidence']:.6f} below {MIN_CONFIDENCE} in {name}")
    if not re.fullmatch(pattern, row['text'].strip()):
        raise ValueError('Unrecognized OCR text in ' + name)
    return row['text'].strip()


def evaluate(context):
    """Registered-validator compatible return; None means outside narrow scope."""
    supplied = context.get('annotation', {})
    if (context.get('uri') != URI or context.get('task_family') != ['填写表单']
            or supplied.get('task_instruction') != INSTRUCTION):
        return None
    scope = {'uri': URI, 'task_family': ['填写表单'], 'business_rule': 'fixed-leap-day-civil-date-difference',
             'business_rule_version': VERSION}
    root = Path(context['sample_path']).resolve()
    evidence = []; diagnostics = {'minimum_confidence': MIN_CONFIDENCE, 'helper_sha256': HELPER_SHA256,
        'arithmetic_status': 'NOT_RUN', 'pixel_terminal_status': 'REVIEW_REQUIRED',
        'coverage': ['terminal_semantics'], 'human_review': 'NOT_PERFORMED'}
    bindings = {}
    status = 'REVIEW_REQUIRED'; reason = 'Terminal pixel evidence is incomplete'
    try:
        annotation_path = _file(root, 'annotation.json'); annotation = _load(annotation_path)
        if annotation != supplied or annotation.get('sample_id') != context.get('sample_id'):
            raise ValueError('Sample context differs from current annotation bytes')
        last = annotation['steps'][-1]
        paths = ['annotation.json', last['image_path'], last['ui_tree_path']]
        for relative in paths:
            path = _file(root, relative); bindings[relative] = _sha(path)
            evidence.append({'path': relative, 'sha256': bindings[relative], 'detail': 'Original date terminal input binding'})
        if (last['action']['action_type'] != 'complete' or annotation.get('completion_status') != 'success'
                or annotation.get('final_state_image') != last['image_path']):
            raise ValueError('Annotation does not bind its terminal complete frame')
        image = _file(root, last['image_path']); header = image.read_bytes()[:24]
        if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise ValueError('Terminal evidence is not an original PNG')
        size = list(struct.unpack('>II', header[16:24])); tree = _load(_file(root, last['ui_tree_path']))
        if tree.get('screen_resolution') != size or tree.get('image_path') != last['image_path']:
            raise ValueError('Terminal tree geometry/image binding differs from PNG')
        anchors = _anchors(tree, size)
        full = _ocr(image)
        roi = _ocr(image, anchors['result']['bbox'])
        diagnostics['full_image_ocr'] = full; diagnostics['main_result_roi_ocr'] = roi
        for record, box in ((full, None), (roi, anchors['result']['bbox'])):
            _ocr_contract(record, bindings[last['image_path']], size, box)
        for name, text in (('heading', '相差天数计算'), ('start_label', '开始日期'),
                           ('end_label', '结束日期'), ('result_label', '相差')):
            _read(full, anchors[name], re.escape(text), name, diagnostics)
        start = _read(full, anchors['start'], r'\d{4}-\d{2}-\d{2}', 'start', diagnostics)
        end = _read(full, anchors['end'], r'\d{4}-\d{2}-\d{2}', 'end', diagnostics)
        delta = (date.fromisoformat(end) - date.fromisoformat(start)).days
        diagnostics.update(arithmetic_status='PASS' if (start, end) == EXPECTED_DATES and delta == 2 else 'FAIL',
                           arithmetic={'start_ocr': start, 'end_ocr': end, 'python_datetime_date_difference_days': delta})
        result = _read(roi, anchors['result'], r'\d+\s*天', 'main_result', diagnostics)
        days = int(re.match(r'\d+', result).group())
        status = 'PASS' if (start, end) == EXPECTED_DATES and delta == days == 2 else 'FAIL'
        diagnostics['pixel_terminal_status'] = status
        reason = ('Independent original-pixel OCR and Python civil-date arithmetic agree'
                  if status == 'PASS' else 'Confident original-pixel values contradict the fixed task or independent date difference')
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error, subprocess.SubprocessError) as error:
        reason = str(error) or type(error).__name__
    try:
        changed = any(_sha(_file(root, path)) != digest for path, digest in bindings.items())
    except (OSError, ValueError):
        changed = True
    if changed:
        status = 'REVIEW_REQUIRED'; reason = 'Original sample evidence changed during validation'
        diagnostics['pixel_terminal_status'] = 'REVIEW_REQUIRED'
    detail = json.dumps({'method': VERSION, 'status': status, 'reason': reason,
                         'arithmetic': diagnostics.get('arithmetic'), 'main_result': diagnostics.get('main_result')}, ensure_ascii=False)
    for row in evidence: row['detail'] = detail
    return {'scope': scope, 'checks': {'terminal_semantics': {
        'status': status, 'reason': reason, 'evidence': evidence, 'diagnostics': diagnostics}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--sample-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); candidate = args.candidate.resolve()
    if args.output.resolve().is_relative_to(candidate):
        parser.error('Output must be outside the immutable candidate')
    if Path(args.sample_id).name != args.sample_id: parser.error('Invalid sample ID')
    root = candidate / 'samples' / args.sample_id; annotation = _load(root / 'annotation.json')
    listing = _load(candidate / 'site-list.json')
    assigned = _one([r['site_id'] for r in listing['samples'] if r['sample_id'] == args.sample_id], 'Ambiguous site assignment')
    uri = _one([r['uri'] for r in listing['sites'] if r['site_id'] == assigned], 'Ambiguous site URI')
    result = evaluate({'sample_path': str(root), 'sample_id': args.sample_id, 'uri': uri,
                       'task_family': sorted(annotation['task_type']), 'annotation': annotation})
    with args.output.open('x', encoding='utf-8') as stream: json.dump(result, stream, ensure_ascii=False, indent=2)
    status = result['checks']['terminal_semantics']['status'] if result else 'OUT_OF_SCOPE'
    print(json.dumps({'status': status, 'output': str(args.output)}, ensure_ascii=False))
    return 0 if status == 'PASS' else 2


if __name__ == '__main__': raise SystemExit(main())
