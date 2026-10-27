"""Customer layout export. Copies evidence bytes; never manufactures review or truth."""
import copy
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from .metadata import COLUMNS
from .validate import SCHEMAS, StrictValidator, read_json
from .task_instruction import validate_task_instruction
from .action_normalization import WINDOWS_KEYBOARD_NORMALIZATION_VERSION, normalize_delivery_step

ROOT_FILES = {'README.md', 'metadata.csv', 'qc_report.md', 'SHA256SUMS', 'site-list.json',
              '附件A-字段说明.md', '附件B-动作空间与坐标系.md', '合成方式说明.md',
              '来源与合规说明.md', '动作空间与系统提示.md'}
CHECKS = {'visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference'}
PARAMS = {'click': {'x', 'y'}, 'double_click': {'x', 'y'}, 'right_click': {'x', 'y'},
          'type': {'text'}, 'hotkey': {'keys'}, 'scroll': {'x', 'y', 'direction'},
          'drag': {'x', 'y', 'end_x', 'end_y'}, 'back': set(), 'open_url': {'url'},
          'select': {'x', 'y', 'option'}, 'wait': set(), 'complete': {'status'}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_name(value):
    if (not isinstance(value, str) or not value.strip() or value in ('.', '..') or
            any(c in value for c in ('/', '\\')) or any(ord(c) < 32 for c in value)):
        raise ValueError('Unsafe sample or site ID: ' + repr(value))
    return value


def real_file(path, base):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Missing, symbolic, or escaping source file: ' + str(path))
    if any(p.is_symlink() for p in path.parents if p.is_relative_to(base)):
        raise ValueError('Symbolic source directory: ' + str(path))
    return path


def sample_hashes(sample):
    return {p.relative_to(sample).as_posix(): sha(real_file(p, sample))
            for p in sorted(sample.rglob('*')) if p.is_file() or p.is_symlink()}


def validate_client_sample(sample, *, allow_legacy_narrative=False, allow_legacy_hotkeys=False):
    """Annex A/B structural contract, without producer-only ID/source constants."""
    sample = Path(sample)
    data = read_json(real_file(sample / 'annotation.json', sample))
    schema = copy.deepcopy(json.loads(SCHEMAS.joinpath('annotation.schema.json').read_text()))
    schema['properties']['sample_id'] = {'type': 'string', 'minLength': 1}
    source = schema['properties']['trajectory_source']['properties']
    source['source_type'] = {'enum': ['human', 'agent', 'human_agent_hybrid']}
    source['data_type'] = {'type': 'string', 'minLength': 1}
    source['action_space'] = {'type': 'string', 'minLength': 1}
    errors = list(StrictValidator(schema).iter_errors(data))
    if errors:
        raise ValueError('Invalid customer annotation ' + str(sample) + ': ' + errors[0].message)
    if not allow_legacy_narrative:
        validate_task_instruction(data['task_instruction'])
    if safe_name(data['sample_id']) != sample.name:
        raise ValueError('Sample directory and sample_id differ')
    dtype = data['trajectory_source']['data_type']
    if not dtype.strip() or '\n' in dtype or '\r' in dtype or any(ord(c) < 32 for c in dtype):
        raise ValueError('Unsafe data_type chapter name')
    if data['terminal_type'] != 'Web':
        raise ValueError('This exporter supports Web trajectories')
    if {p.name for p in sample.iterdir()} != {'annotation.json', 'images', 'ui_tree'}:
        raise ValueError('A sample must contain only annotation.json, images/, ui_tree/')
    if not all((sample / d).is_dir() and not (sample / d).is_symlink() for d in ('images', 'ui_tree')):
        raise ValueError('Sample asset folders must be real directories')
    if {p.relative_to(sample).as_posix() for p in sample.rglob('*') if p.is_dir()} != {'images', 'ui_tree'}:
        raise ValueError('Sample asset folders must not contain extra directories')
    expected = {'annotation.json'}
    res = data['device_info']['screen_resolution']
    if data['app_info']['ui_language'] != 'zh' or data['completion_status'] == 'failed':
        raise ValueError('Customer delivery requires Chinese UI and a completed trajectory')
    effective = sum(s['action']['action_type'] not in ('wait', 'complete') for s in data['steps'])
    if effective < 5 and not (data.get('short_flow') is True and data.get('short_flow_reason', '').strip()):
        raise ValueError('Fewer than five effective actions require a short-flow reason')
    if data.get('short_flow') is True and (effective >= 5 or not data.get('short_flow_reason', '').strip()):
        raise ValueError('Invalid short-flow declaration')
    if data['steps'][-1]['action']['action_type'] != 'complete':
        raise ValueError('Customer delivery must end with complete(success)')
    generic_goal = re.sub(r'[\s，。！：、]', '', data['steps'][-1]['user_goal'])
    if not allow_legacy_narrative and generic_goal in {'确认最终页面符合任务要求', '确认任务完成', '确认最终状态', '完成任务'}:
        raise ValueError('Final user_goal must identify the actual page/content, not a generic confirmation')
    calls = set()
    for n, step in enumerate(data['steps'], 1):
        action = step['action']; call = step['tool_call']; name = action['action_type']; args = call['arguments']
        if step['step_id'] != n or name not in PARAMS or call['tool_name'] != name or set(args) != PARAMS[name]:
            raise ValueError('Step numbering or Annex B action/parameter mismatch')
        if call['call_id'] in calls or not call['call_id'].strip():
            raise ValueError('Tool call IDs must be nonempty and unique')
        calls.add(call['call_id'])
        if call['timestamp']:
            try:
                if datetime.fromisoformat(call['timestamp'].replace('Z', '+00:00')).tzinfo is None:
                    raise ValueError('Missing timezone')
            except ValueError as error:
                raise ValueError('Tool timestamp must be ISO8601 with timezone, or empty') from error
        if step['tool_result']['status'] != 'success' or step['tool_result']['error']:
            raise ValueError('Every delivered tool result must be success without an error')
        if n < len(data['steps']) and 'screen_changed' not in step['tool_result']['return_value']:
            raise ValueError('Nonterminal steps require screen_changed')
        for key in ('x', 'y', 'end_x', 'end_y'):
            if key in args and type(args[key]) is not int:
                raise ValueError('Coordinates must be integer screenshot pixels')
        for key in ('text', 'url', 'option', 'direction', 'status'):
            if key in args and not isinstance(args[key], str):
                raise ValueError('Action string parameter has wrong type')
        if 'x' in args and (action['coordinate'] != [args['x'], args['y']] or
                            not (0 <= args['x'] < res[0] and 0 <= args['y'] < res[1])):
            raise ValueError('Pointer is outside screenshot or differs from action.coordinate')
        if 'x' not in args and action['coordinate']:
            raise ValueError('Non-pointer coordinate must be empty')
        if name == 'drag' and (action.get('end_coordinate') != [args['end_x'], args['end_y']] or
                               not (0 <= args['end_x'] < res[0] and 0 <= args['end_y'] < res[1])):
            raise ValueError('Drag end coordinate differs or lies outside screenshot')
        if name != 'drag' and 'end_coordinate' in action:
            raise ValueError('Only drag can have end_coordinate')
        box = action.get('target_bbox')
        if box is not None and not (0 <= box[0] < box[2] <= res[0] and 0 <= box[1] < box[3] <= res[1]):
            raise ValueError('Action target bbox lies outside screenshot')
        if name in {'scroll', 'wait', 'back', 'open_url', 'complete'} and (
                action['target_element_id'] or action['target_text'] or box is not None or action.get('target_control_type')):
            raise ValueError('Non-control action must not claim a target control')
        if name == 'hotkey' and (action['target_element_id'] or box is not None or
                                 action.get('target_control_type') or not action['target_text']):
            raise ValueError('Hotkey must name keys without claiming a target control')
        if name == 'scroll' and args['direction'] not in ('up', 'down', 'left', 'right'):
            raise ValueError('Invalid scroll direction')
        if name == 'hotkey' and (not isinstance(args['keys'], list) or not args['keys'] or
                                any(not isinstance(k, str) or not k for k in args['keys']) or
                                action['input_text'] != '+'.join(args['keys'])):
            raise ValueError('Hotkey input_text must preserve actual keys')
        if not allow_legacy_hotkeys and normalize_delivery_step(step, data['device_info'].get('os_name')) != step:
            raise ValueError('Windows keyboard delivery requires canonical keys, input_text and target_text')
        if name == 'type' and action['input_text'] != args['text']:
            raise ValueError('Type input_text differs from executed text')
        if name not in ('type', 'hotkey') and action['input_text']:
            raise ValueError('Non-input action must have empty input_text')
        if name == 'complete' and (n != len(data['steps']) or args['status'] != 'success'):
            raise ValueError('Complete must be the final step with status success')
        if step['image_path'] != f'images/step_{n:03}.png':
            raise ValueError('Step image path must use images/step_NNN.png')
        expected.add(step['image_path'])
        with Image.open(real_file(sample / step['image_path'], sample)) as image:
            if image.format != 'PNG' or list(image.size) != res:
                raise ValueError('PNG resolution differs from annotation')
            image.verify()
        if not step['ui_tree_path']:
            raise ValueError('Every Web delivery step requires a synchronized UI tree')
        if step['ui_tree_path']:
            if step['ui_tree_path'] != f'ui_tree/step_{n:03}.json':
                raise ValueError('Tree path must use ui_tree/step_NNN.json')
            expected.add(step['ui_tree_path'])
            tree = read_json(real_file(sample / step['ui_tree_path'], sample))
            errors = list(StrictValidator(json.loads(SCHEMAS.joinpath('ui_tree.schema.json').read_text())).iter_errors(tree))
            if errors or tree['image_path'] != step['image_path'] or tree['screen_resolution'] != res:
                raise ValueError('Tree schema or image/resolution synchronization mismatch')
            elements = {e['element_id']: e for e in tree['elements']}
            if len(elements) != len(tree['elements']):
                raise ValueError('Duplicate tree element ID')
            for e in elements.values():
                b = e['bbox']
                if not (0 <= b[0] < b[2] <= res[0] and 0 <= b[1] < b[3] <= res[1]):
                    raise ValueError('Tree bbox lies outside screenshot pixels')
                if not e['visible'] or e['element_id'] == 'root':
                    raise ValueError('Only visible elements with non-reserved IDs may be delivered')
                seen = {e['element_id']}; parent = e['parent_id']
                while parent != 'root':
                    if parent not in elements or parent in seen:
                        raise ValueError('Tree parent is missing or cyclic')
                    seen.add(parent); parent = elements[parent]['parent_id']
            target_id = action['target_element_id']
            if name in {'click', 'double_click', 'right_click', 'type', 'drag', 'select'} and not target_id:
                raise ValueError('Control actions require a synchronized target ID and bbox')
            if target_id:
                target = elements.get(target_id)
                if not target or target['text'] != action['target_text'] or target['bbox'] != action.get('target_bbox'):
                    raise ValueError('Action target and synchronized tree differ')
                if not target['enabled'] or (name == 'type' and not target['inputable']):
                    raise ValueError('Target must be enabled and accept the requested action')
                if action.get('target_control_type') and action['target_control_type'] != target['element_type']:
                    raise ValueError('Target control type differs from synchronized tree')
                if 'x' in args:
                    b = target['bbox']
                    if not (b[0] <= args['x'] < b[2] and b[1] <= args['y'] < b[3]):
                        raise ValueError('Pointer lies outside target bbox')
        elif action['target_element_id']:
            raise ValueError('A sample without a tree cannot reference tree element IDs')
    final = data.get('final_state_image', '')
    if final != data['steps'][-1]['image_path']:
        raise ValueError('Web final_state_image must identify the final step screenshot')
    if final:
        if Path(final).parent.as_posix() != 'images':
            raise ValueError('Final image must stay inside images/')
        with Image.open(real_file(sample / final, sample)) as image:
            if image.format != 'PNG' or list(image.size) != res:
                raise ValueError('Final PNG resolution differs from annotation')
            image.verify()
        expected.add(final)
    if final and data['steps'][-1]['action']['action_type'] == 'complete' and final != data['steps'][-1]['image_path']:
        raise ValueError('Complete final_state_image must identify final step screenshot')
    if set(sample_hashes(sample)) != expected:
        raise ValueError('Sample contains unreferenced or missing files')
    return data


def _discover(source):
    if (source / 'samples').is_dir():
        roots = [source]
    else:
        roots = [p for p in sorted(source.iterdir()) if p.is_dir() and (p / 'samples').is_dir()]
    if not roots:
        raise ValueError('No samples/ source found')
    records = []; seen = set()
    for batch in roots:
        if batch.is_symlink() or (batch / 'samples').is_symlink():
            raise ValueError('Symbolic sample source')
        manifest_path = batch / 'manifest.json'
        manifest = read_json(real_file(manifest_path, batch)) if manifest_path.exists() else None
        if manifest and manifest.get('sample_kind') == 'integration':
            raise ValueError('Synthetic integration batches cannot be exported as customer data')
        sites = manifest.get('sites', []) if manifest else []
        mapping = {}
        if (batch / 'site-list.json').exists():
            site_list = read_json(real_file(batch / 'site-list.json', batch))
            sites = site_list['sites']
            mapping = {r['sample_id']: r['site_id'] for r in site_list['samples']}
            actual_ids = {p.name for p in (batch / 'samples').iterdir()}
            if len(mapping) != len(site_list['samples']) or set(mapping) != actual_ids:
                raise ValueError('Source site-list has duplicate or unmatched samples')
            for site in sites:
                if (len(site.get('sample_ids', [])) != len(set(site.get('sample_ids', []))) or
                        set(site.get('sample_ids', [])) != {sid for sid, key in mapping.items() if key == site['site_id']}):
                    raise ValueError('Source site-list ownership mismatch')
        site_map = {s['site_id']: s for s in sites}
        if len(site_map) != len(sites):
            raise ValueError('Duplicate site ID in source')
        for sample in sorted((batch / 'samples').iterdir()):
            if not sample.is_dir() or sample.is_symlink():
                raise ValueError('Sample source must be a real directory')
            data = validate_client_sample(sample, allow_legacy_narrative=True, allow_legacy_hotkeys=True); sid = data['sample_id']
            if sid in seen:
                raise ValueError('Duplicate sample ID: ' + sid)
            seen.add(sid)
            site_id = mapping.get(sid)
            if site_id is None and manifest:
                attempts = [r for r in manifest.get('attempts', []) if r.get('sample_id') == sid and r.get('site_id')]
                site_id = attempts[-1]['site_id'] if attempts else sid.split('_sample_')[0]
            site = site_map.get(site_id)
            if not site or not all(isinstance(site.get(k), str) and site[k].strip() for k in ('site_id', 'uri', 'site_category')):
                raise ValueError('Missing explicit URI/category/site mapping for ' + sid)
            safe_name(site_id)
            if not re.match(r'^https?://[^\s/]+', site['uri']):
                raise ValueError('Invalid source site URI')
            truths = [p for p in (batch / 'ground_truth' / (sid + '.json'), batch / 'evidence' / sid / 'ground_truth.json') if p.exists()]
            if not truths:
                raise ValueError('Missing original capture ground truth for ' + sid)
            for truth in truths:
                real_file(truth, batch)
            if len({sha(p) for p in truths}) != 1:
                raise ValueError('Conflicting source truth files')
            truth = truths[0]; observed = read_json(truth)
            expected = [{'step_id': s['step_id'], 'element_id': s['action']['target_element_id'],
                         'text': s['action']['target_text'], 'bbox': s['action']['target_bbox']}
                        for s in data['steps'] if s['action'].get('target_element_id') and 'target_bbox' in s['action']]
            if observed != expected:
                raise ValueError('Original ground truth differs from annotation targets: ' + sid)
            hashes = sample_hashes(sample)
            raw_dir = batch / 'evidence' / sid
            raw_hashes = {p.relative_to(batch).as_posix(): sha(real_file(p, batch))
                          for p in sorted(raw_dir.rglob('*')) if p.is_file() or p.is_symlink()} if raw_dir.is_dir() else {}
            files = dict(raw_hashes)
            if manifest:
                files['manifest.json'] = sha(manifest_path)
            records.append(dict(sample_id=sid, sample=sample, batch=batch, data=data, site=dict(site_id=site_id, uri=site['uri'], site_category=site['site_category']), truth=truth,
                                hashes=hashes, truth_sha256=sha(truth), raw_hashes=raw_hashes, source_files=files, manifest=manifest,
                                manifest_path=manifest_path if manifest else None))
        if manifest and isinstance(manifest.get('samples'), list) and set(manifest['samples']) != {r['sample_id'] for r in records if r['batch'] == batch}:
            raise ValueError('Manifest sample list differs from source samples/')
    return records


def _v2_review_records(repo, path, records, source, report_path):
    """Reuse the independent checker's intake against an inspected client directory.

    The report may contain rejected samples. Only a current PASS sample and an
    actual human PASS record can be selected; package-level PASS is not inferred.
    """
    if report_path is None:
        raise ValueError('qc-review-2 selection requires --selection-report from the actual client source')
    from .client_reports import _bound_report
    import importlib.util
    import importlib
    import sys
    report, _ = _bound_report(source, Path(report_path))
    # Keep the checker independent: load its real implementation, do not copy or
    # weaken its coverage/contract rules in the producer.
    package = Path(repo) / 'projects' / 'quality-inspector' / 'quality_inspector'
    name = '_webcollect_selection_qc'
    if not (package / '__init__.py').is_file():
        raise ValueError('Independent QC source is required for qc-review-2 selection')
    implementation = {file: sha(package / file) for file in ('__init__.py', 'contract.py',
        'format_checks.py', 'engine.py', 'reviews.py', 'profiles.py', 'duplicates.py',
        'cumulative.py', 'checksums.py', 'layout.py')}
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, package / '__init__.py',
                                                     submodule_search_locations=[str(package)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        module._selection_code_sha256 = implementation
    elif Path(sys.modules[name].__file__).resolve() != (package / '__init__.py').resolve():
        raise ValueError('Independent QC module path changed during selection')
    elif sys.modules[name]._selection_code_sha256 != implementation:
        raise ValueError('Independent QC implementation changed during selection process')
    contract = importlib.import_module(name + '.contract')
    review_rules = importlib.import_module(name + '.reviews')
    _, fingerprint = contract.fingerprint()
    if report.get('baseline', {}).get('config_sha256') != fingerprint:
        raise ValueError('Selection QC report uses a stale/different contract')
    byid, errors, migrated = review_rules.intake(path,
        [{'sample_id': row['sample_id'], 'sample_path': str(row['sample'])} for row in records], fingerprint)
    if errors or migrated:
        raise ValueError('Invalid current qc-review-2 selection records: ' + str(errors or migrated))
    rows = {row['sample_id']: row for row in report['samples']}
    for sid, review in byid.items():
        checks = {row['rule_id']: row for row in rows[sid].get('checks', [])}
        for key, value in review['checks'].items():
            check = checks.get('REVIEW_' + key.upper(), {})
            if (check.get('status') != value['status'] or check.get('reason') != value.get('note')
                    or check.get('reviewer') != review['reviewer']
                    or check.get('provenance') != review['provenance']):
                raise ValueError('Selection report does not contain the supplied review decision: ' + sid)
    return byid, read_json(path), rows


def _review_records(path, records, approved_only, baseline_sha256=None):
    if not path:
        if approved_only:
            raise ValueError('--approved-only requires --reviews')
        return {}, None
    export = read_json(path)
    if export.get('schema_version') != 'qc-review-1' or not isinstance(export.get('records'), list):
        raise ValueError('Review export must be qc-review-1')
    byid = {}; samples = {r['sample_id']: r for r in records}
    for review in export['records']:
        sid = review.get('sample_id')
        if sid in byid or sid not in samples:
            raise ValueError('Duplicate or unknown review sample: ' + str(sid))
        sample = samples[sid]
        evidence = {p: h for p, h in sample['hashes'].items() if p != 'annotation.json'}
        if review.get('annotation_sha256') != sample['hashes']['annotation.json'] or review.get('evidence_sha256') != evidence:
            raise ValueError('Review annotation/evidence binding mismatch: ' + sid)
        if baseline_sha256 is not None and review.get('baseline_sha256') != baseline_sha256:
            raise ValueError('Review customer baseline binding mismatch: ' + sid)
        byid[sid] = review
    return byid, export


def _approved(review):
    return (isinstance(review, dict) and review.get('reviewer', {}).get('kind') == 'human'
            and isinstance(review.get('reviewer', {}).get('name'), str) and bool(review['reviewer']['name'].strip())
            and isinstance(review.get('provenance'), dict)
            and all(isinstance(review['provenance'].get(k), str) and review['provenance'][k].strip()
                    for k in ('description', 'reviewed_at'))
            and all(review.get('checks', {}).get(k, {}).get('status') == 'PASS'
                    and isinstance(review['checks'][k].get('note'), str) and review['checks'][k]['note'].strip()
                    for k in CHECKS))


def render_qc_report(report):
    """Render a separately verified report, retaining its original dataset scope.

    This function does not verify report identity. A caller must bind dataset,
    root checksum manifest and all sample/evidence hashes before using it in a
    new export, then QC that new package separately.
    """
    return ('# 独立质检记录\n\n本报告的检查对象以dataset字段和报告内文件哈希为准。'
            '附入新目录不表示新目录已被检查；新目录仍须单独QC。客户验收仅以实际执行记录为准。\n\n```json\n'
            + json.dumps(report, ensure_ascii=False, indent=2) + '\n```\n')


def _documents(repo, out, records):
    authority = repo / 'request/web操作采集需求'
    for name in ('附件A-字段说明.md', '附件B-动作空间与坐标系.md'):
        shutil.copyfile(real_file(authority / name, repo), out / name)
    annex = (out / '附件B-动作空间与坐标系.md').read_text()
    dtypes = sorted({r['data']['trajectory_source']['data_type'] for r in records})
    chapters = []; descriptions = []
    for dtype in dtypes:
        origins = sorted({r['data']['trajectory_source']['source_type'] for r in records if r['data']['trajectory_source']['data_type'] == dtype})
        spaces = sorted({r['data']['trajectory_source']['action_space'] for r in records if r['data']['trajectory_source']['data_type'] == dtype})
        version = '实际声明的action_space版本为' + '、'.join(spaces) + '。'
        known = dtype == 'webcollect_agent_v1' and set(origins) <= {'agent', 'human_agent_hybrid'}
        chapters.append('\n## ' + dtype + '\n\n原始source_type为' + '、'.join(origins) + '。' + version + '本类型的输出动作格式采用第1节Web子集，坐标采用第2节。第3节是随附参考系统提示，不据此声称历史采集实际调用了该提示。' + ('本线为计划驱动采集；采集参数和原始记录在包外证据索引绑定。' if known else '原始操作/提示生成过程为待核验项；导出器没有改写来源或补造历史系统提示。') + '\n')
        descriptions.append('## ' + dtype + '\n\n来源身份保留为' + '、'.join(origins) + '。' + version + '同名动作格式章节见[动作空间与系统提示](动作空间与系统提示.md)。PNG和界面树按字节复制；标注中的所有快捷键按用户确认的Windows交付口径归一化，其他标注修订见包外追溯清单；导出器未进行新采集、模型重写或真人审核。' + ('本线采集状态差异模板的声明与离线标注修订须结合包外记录核验，不能将全部历史文字笼统称为模板生成。' if known else '历史文字生成方式和原始系统提示缺少可验证记录时保持UNKNOWN。') + '\n')
    (out / '动作空间与系统提示.md').write_text(annex + '\n' + '\n'.join(chapters))
    mapping = '''\n## 动作映射与坐标\n\n输出tool_call遵循统一动作空间，所有快捷键按已确认的Windows表达及跨平台功能映射归一化，其他动作保留原始参数：click→{x,y}；type→{text}；hotkey→{keys}；scroll→{x,y,direction}；back→{}；complete→{status}，其他Web动作遵循[附件B](附件B-动作空间与坐标系.md)。指针坐标来自原采集同步树，采用PNG截图像素整数，原点左上。向下阅读对应direction=down；执行滚动距离不另加进统一参数。\n\n当前采集器的对应实现为mouse.click→click，keyboard.insert_text→type，keyboard.press→hotkey，mouse.move+mouse.wheel→scroll，go_back→back，终态断言后结束→complete。历史实现可能不同，实际动作及参数以包外绑定的原始记录为准。所有hotkey统一Windows键名及显示，例如复制Ctrl+C、粘贴Ctrl+V、剪切Ctrl+X、全选Ctrl+A；keys与input_text使用规范小写，显示使用Ctrl+V、Enter、Tab、Home等。macOS实际Command组合按已声明同功能映射为Ctrl，Windows原生Meta则为Win；未定义Mac特殊组合须显式阻止交付。原始证据保持真实按键；变更前后标注哈希及逐步映射保存在包外追溯清单，不能将归一化的交付参数冒称为未改写的原始执行。\n\n图像为本步动作前界面，末步complete的图像同时为终态。相邻图与step_result提供变化证据；生成器不在此宣告视觉语义或客户验收通过。\n'''
    (out / '合成方式说明.md').write_text('# 合成方式说明\n\n' + '\n'.join(descriptions) + mapping)
    capture_configuration = []
    for manifest_path in sorted({r['manifest_path'] for r in records if r['manifest_path']}):
        manifest = read_json(manifest_path)
        configuration = manifest.get('configuration', {})
        if not isinstance(configuration, dict):
            configuration = {}
        capture_configuration.append({
            'source_batch': manifest.get('batch_id', manifest_path.parent.name),
            'selected_samples': sum(r['manifest_path'] == manifest_path for r in records),
            'recorded_configuration': {key: configuration[key] for key in
                ['viewport', 'device_scale_factor', 'locale', 'timezone',
                 'task_interval_seconds', 'default_settle_ms'] if key in configuration},
            'configuration_is_not_a_full_network_frequency_audit': True,
        })
    (out / '来源与合规说明.md').write_text('# 来源与合规说明\n\n站点URI、类目与样本归属见[site-list.json](site-list.json)。来源身份逐条保留trajectory_source；导出器不访问网站、不登录、不推断授权许可。未记录的账号、实际网络访问频率和合规事实保持UNKNOWN。人工审核记录和原始总体分母留在包外，样本筛选不改写来源采集总体的通过率。\n\n## 已记录的捕获配置\n\n下列为原捕获清单实际记载的配置；配置间隔不是完整请求日志审计。来源未提供捕获清单时不补造配置。\n\n```json\n' + json.dumps(capture_configuration, ensure_ascii=False, indent=2) + '\n```\n')
    statistics = {
        'sample_count': len(records),
        'site_count': len({r['site']['site_id'] for r in records}),
        'site_sample_counts': dict(Counter(r['site']['site_id'] for r in records)),
        'categories': dict(Counter(r['site']['site_category'] for r in records)),
        'task_types': dict(Counter(t for r in records for t in r['data']['task_type'])),
        'step_counts': dict(Counter(len(r['data']['steps']) for r in records)),
        'effective_step_counts': dict(Counter(sum(s['action']['action_type'] not in ('wait', 'complete')
                                                  for s in r['data']['steps']) for r in records)),
        'frames': sum(len(r['data']['steps']) for r in records),
        'actions': dict(Counter(s['action']['action_type'] for r in records for s in r['data']['steps'])),
    }
    (out / 'README.md').write_text('# Web轨迹样本\n\n样本位于samples/<sample_id>/，每条仅有annotation.json、images和ui_tree。字段与动作见根目录附件A/B；原采集目标真值位于ground_truth/<sample_id>.json。站点归属见site-list.json，索引见metadata.csv。\n\n```text\nsamples/<sample_id>/\n  annotation.json\n  images/step_NNN.png\n  ui_tree/step_NNN.json\n```\n\n## 实际分布\n\n统计取自本目录实际选入的样本，不重命名类目或变更原输入总体分母。\n\n```json\n' + json.dumps(statistics, ensure_ascii=False, indent=2) + '\n```\n\n本次导出样本' + str(len(records)) + '条；不包含内部raw、审核记录、批次manifest或追溯档案。导出结构检查不代表独立QC、真人审核或客户验收。当前独立QC状态：NOT_RUN；客户验收：UNKNOWN。\n')
    (out / 'qc_report.md').write_text('# 质检状态\n\n独立QC：NOT_RUN（本次仅完成导出与结构自检）。客户验收：UNKNOWN。真实QC报告必须由后续程序在包外生成，不能回写或伪称本输入包已经通过。\n')


def validate_client_layout(root):
    root = Path(root)
    if {p.name for p in root.iterdir()} != ROOT_FILES | {'samples', 'ground_truth'}:
        raise ValueError('Customer root contains missing or internal files')
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Customer export must not contain symlinks')
    site_list = read_json(root / 'site-list.json')
    if site_list.get('schema_version') != 'webcollect-site-list-1':
        raise ValueError('Unknown site-list schema')
    sample_map = {r['sample_id']: r['site_id'] for r in site_list['samples']}
    sites = {r['site_id']: r for r in site_list['sites']}
    if len(sites) != len(site_list['sites']):
        raise ValueError('Duplicate client site ID')
    ids = {p.name for p in (root / 'samples').iterdir()}
    if len(sample_map) != len(site_list['samples']) or set(sample_map) != ids:
        raise ValueError('Site map sample coverage mismatch')
    if {p.name for p in (root / 'ground_truth').iterdir()} != {sid + '.json' for sid in ids}:
        raise ValueError('Ground truth coverage mismatch')
    for key, site in sites.items():
        if (not all(isinstance(site.get(k), str) and site[k].strip() for k in ('site_id', 'uri', 'site_category')) or
                len(site['sample_ids']) != len(set(site['sample_ids'])) or
                set(site['sample_ids']) != {sid for sid, site_id in sample_map.items() if site_id == key}):
            raise ValueError('Site list and sample mapping disagree')
    with (root / 'metadata.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Metadata columns differ from customer export contract')
        metadata = list(reader)
    meta = {row['sample_id']: row for row in metadata}
    if len(meta) != len(metadata) or set(meta) != ids:
        raise ValueError('Metadata sample coverage mismatch')
    steps = 0
    for sid in sorted(ids):
        d = validate_client_sample(root / 'samples' / sid); steps += len(d['steps'])
        if sample_map[sid] not in sites or sid not in sites[sample_map[sid]]['sample_ids']:
            raise ValueError('Site ownership mismatch')
        row = meta[sid]
        if (row['site_id'] != sample_map[sid] or row['site_category'] != sites[sample_map[sid]]['site_category'] or
                int(row['steps']) != len(d['steps']) or json.loads(row['actions']) != [s['action']['action_type'] for s in d['steps']] or
                json.loads(row['screen_resolution']) != d['device_info']['screen_resolution'] or
                json.loads(row['task_type']) != d['task_type'] or row['task_instruction'] != d['task_instruction'] or
                row['app_name'] != d['app_info']['app_name'] or row['completion_status'] != d['completion_status'] or
                int(row['bytes']) != sum(p.stat().st_size for p in (root / 'samples' / sid).rglob('*') if p.is_file())):
            raise ValueError('Metadata values differ from annotation/site mapping')
        expected_truth = [{'step_id': s['step_id'], 'element_id': s['action']['target_element_id'],
                           'text': s['action']['target_text'], 'bbox': s['action']['target_bbox']}
                          for s in d['steps'] if s['action'].get('target_element_id') and 'target_bbox' in s['action']]
        if read_json(root / 'ground_truth' / (sid + '.json')) != expected_truth:
            raise ValueError('Customer truth differs from sample targets')
        if '\n## ' + d['trajectory_source']['data_type'] + '\n' not in (root / '动作空间与系统提示.md').read_text():
            raise ValueError('Missing data_type system prompt chapter')
    listed = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, relative = line.split('  ', 1)
        if relative in listed or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid or duplicate checksum entry')
        listed[relative] = digest
    actual = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file() and p != root / 'SHA256SUMS'}
    if listed != actual:
        raise ValueError('Root checksum manifest differs from complete customer files')
    return {'structural_pass': True, 'samples': len(ids), 'steps': steps, 'customer_acceptance': 'UNKNOWN'}


def build_client_package(repo, source, output, *, reviews=None, approved_only=False,
                         evidence_output=None, review_output=None, facts=None, revisions=None,
                         selection_report=None):
    repo = Path(repo).resolve(); source = Path(source).resolve(); output = Path(output).absolute()
    from .contract_documents import load_facts, render as render_documents
    from .narrative_revisions import load_plan, apply as revise_narratives
    production_facts = load_facts(facts)
    revision_plan = load_plan(revisions)
    frozen_review_sha = sha(reviews) if reviews else None
    frozen_selection_sha = sha(selection_report) if selection_report else None
    if review_output is not None and reviews is None:
        raise ValueError('--review-output requires --reviews')
    if selection_report is not None and reviews is None:
        raise ValueError('--selection-report requires --reviews')
    if output.is_symlink() or output.exists():
        raise FileExistsError('Refuse to overwrite customer output')
    output = output.resolve()
    if not source.is_dir() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Source/output missing or containing each other')
    evidence_output = Path(evidence_output).absolute() if evidence_output else output.with_name(output.name + '.evidence.json')
    review_output = Path(review_output).absolute() if review_output else evidence_output.with_name(evidence_output.stem + '.selected-reviews.json')
    destinations = [output, evidence_output] + ([review_output] if reviews else [])
    if len(set(p.resolve() for p in destinations)) != len(destinations):
        raise ValueError('Output paths must be distinct')
    for path in destinations[1:]:
        if path.exists() or path.is_symlink():
            raise FileExistsError('Refuse to overwrite sidecar: ' + str(path))
        if path.resolve().is_relative_to(output) or path.resolve().is_relative_to(source):
            raise ValueError('Evidence/review output must be outside customer output and source')
    records = _discover(source)
    if not records:
        raise ValueError('No samples found')
    baseline = repo / 'projects/quality-inspector/config/customer-samples.json'
    if reviews and not baseline.is_file():
        raise ValueError('Customer review baseline is missing')
    selection_rows = None
    if reviews and read_json(reviews).get('schema_version') == 'qc-review-2':
        review_map, review_export, selection_rows = _v2_review_records(repo, Path(reviews), records,
                                                                     source, selection_report)
    else:
        if selection_report is not None:
            raise ValueError('--selection-report is only supported for qc-review-2')
        review_map, review_export = _review_records(Path(reviews) if reviews else None, records, approved_only,
                                                   sha(baseline) if reviews else None)
    selected = [r for r in records if not approved_only or
                (_approved(review_map.get(r['sample_id'])) and
                 (selection_rows is None or selection_rows[r['sample_id']]['status'] == 'PASS'))]
    if not selected:
        raise ValueError('No selected samples; approved-only never infers approval')
    if selection_rows is not None and approved_only and production_facts is not None:
        if production_facts['selection'].get('selected_count') != len(selected):
            raise ValueError('Selected facts must describe the new selected population, retaining original exclusions')
    revision_map = {row['sample_id']: row for row in revision_plan['samples']} if revision_plan else {}
    if set(revision_map) - {r['sample_id'] for r in selected}:
        raise ValueError('Narrative revision refers to an unselected sample')
    if revision_plan is not None and reviews is not None:
        raise ValueError('Revised annotations require fresh QC reviews; do not re-sign old records')
    normalization_map = {}
    for record in selected:
        changes = []
        for step in record['data']['steps']:
            normalized = normalize_delivery_step(step, record['data']['device_info'].get('os_name'))
            if normalized != step:
                changes.append({'step_id': step['step_id'],
                    'before': {'action': step['action'], 'tool_call': step['tool_call']},
                    'after': {'action': normalized['action'], 'tool_call': normalized['tool_call']}})
        if changes:
            normalization_map[record['sample_id']] = changes
    if normalization_map and reviews is not None:
        raise ValueError('Normalized annotations require fresh QC reviews; do not re-sign old records')
    excluded = [dict(sample_id=r['sample_id'], reason=(
        'CURRENT_QC_SAMPLE_NOT_PASS' if selection_rows is not None and selection_rows[r['sample_id']]['status'] != 'PASS'
        else 'HUMAN_FIVE_CHECKS_NOT_ALL_PASS' if r['sample_id'] in review_map else 'MISSING_REVIEW'),
        review=review_map.get(r['sample_id'])) for r in records if r not in selected]
    # Validate every source before creating anything. Staging keeps failed contracts out of final output.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '.staging-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'client'; staged.mkdir(); (staged / 'samples').mkdir(); (staged / 'ground_truth').mkdir()
        exported = []
        for record in selected:
            sid = record['sample_id']; shutil.copytree(record['sample'], staged / 'samples' / sid)
            shutil.copyfile(record['truth'], staged / 'ground_truth' / (sid + '.json'))
            if (sample_hashes(staged / 'samples' / sid) != record['hashes'] or
                    sha(staged / 'ground_truth' / (sid + '.json')) != record['truth_sha256']):
                raise ValueError('Copied sample hashes differ')
            if sid in revision_map:
                revise_narratives(staged / 'samples' / sid, revision_map[sid])
            if sid in normalization_map:
                annotation_path = staged / 'samples' / sid / 'annotation.json'
                annotation = read_json(annotation_path)
                annotation['steps'] = [normalize_delivery_step(step, annotation['device_info'].get('os_name')) for step in annotation['steps']]
                write_json(annotation_path, annotation)
            current = validate_client_sample(staged / 'samples' / sid)
            current_hashes = sample_hashes(staged / 'samples' / sid)
            if any(h != current_hashes[k] for k, h in record['hashes'].items() if k != 'annotation.json'):
                raise ValueError('Revision modified immutable image/tree evidence')
            exported.append({**record, 'data': current, 'export_hashes': current_hashes})
        site_map = {}
        for r in selected:
            site = r['site']; key = site['site_id']
            if key in site_map and any(site_map[key][k] != site[k] for k in ('uri', 'site_category')):
                raise ValueError('Conflicting source site mapping')
            site_map.setdefault(key, {**site, 'sample_ids': []})['sample_ids'].append(r['sample_id'])
        write_json(staged / 'site-list.json', {'schema_version': 'webcollect-site-list-1', 'sites': list(site_map.values()), 'samples': [dict(sample_id=r['sample_id'], site_id=r['site']['site_id']) for r in selected]})
        with (staged / 'metadata.csv').open('x', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS); writer.writeheader()
            for r in exported:
                a = r['data']; writer.writerow(dict(sample_id=r['sample_id'], site_id=r['site']['site_id'], site_category=r['site']['site_category'], app_name=a['app_info']['app_name'], task_type=json.dumps(a['task_type'], ensure_ascii=False), task_instruction=a['task_instruction'], steps=len(a['steps']), screen_resolution=json.dumps(a['device_info']['screen_resolution']), completion_status=a['completion_status'], actions=json.dumps([s['action']['action_type'] for s in a['steps']], ensure_ascii=False), bytes=sum(p.stat().st_size for p in (staged / 'samples' / r['sample_id']).rglob('*') if p.is_file())))
        _documents(repo, staged, exported)
        render_documents(staged, exported, production_facts, revision_plan)
        (staged / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.relative_to(staged).as_posix() + '\n' for p in sorted(staged.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
        contract = validate_client_layout(staged)
        sidecar_samples = []
        for r in records:
            sidecar_samples.append(dict(sample_id=r['sample_id'], selected=r in selected, source_sample_path=str(r['sample']), source_batch_path=str(r['batch']), annotation_sha256=r['hashes']['annotation.json'], evidence_sha256={k: v for k, v in r['hashes'].items() if k != 'annotation.json'}, ground_truth_sha256=r['truth_sha256'], source_ground_truth_path=str(r['truth']), source_manifest_path=str(r['manifest_path']) if r['manifest_path'] else None, source_manifest_sha256=sha(r['manifest_path']) if r['manifest_path'] else None, raw_evidence_files_sha256=r['raw_hashes'], source_files_sha256=r['source_files'], machine_evidence_status='AVAILABLE' if r['manifest_path'] and r['raw_hashes'] else 'UNAVAILABLE'))
        selected_sidecar = [r for r in sidecar_samples if r['selected']]
        evidence = dict(schema_version='webcollect-client-evidence-1', created_at=datetime.now(timezone.utc).isoformat(), client_root=str(output), source_root=str(source), samples=selected_sidecar, source_population=dict(total_samples=len(records), selected_count=len(selected), excluded_count=len(excluded)), source_samples=sidecar_samples, excluded_samples=excluded, source_review_export=dict(path=str(Path(reviews).resolve()), sha256=sha(reviews)) if reviews else None, source_review_records=review_export['records'] if review_export else None, source_review_document=review_export, source_package_review_applied=False, selected_review_output=str(review_output.resolve()) if reviews else None, independent_qc_status='NOT_RUN', customer_acceptance='UNKNOWN')
        if selection_report is not None:
            evidence['selection_qc_report'] = {'path': str(Path(selection_report).resolve()),
                                               'sha256': sha(selection_report)}
            evidence['selection_does_not_release_new_package'] = True
        if revision_plan is not None:
            # Original capture evidence binds the source annotation only. A prose
            # revision must never masquerade as an unchanged capture index.
            revision_path = Path(revisions).resolve()
            revision_bytes = revision_path.read_bytes()
            if json.loads(revision_bytes.decode('utf-8')) != revision_plan:
                raise ValueError('Narrative revision plan changed during export')
            revision_sha256 = hashlib.sha256(revision_bytes).hexdigest()
            exports_by_id = {r['sample_id']: r for r in exported}
            for row in sidecar_samples:
                row['source_annotation_sha256'] = row.pop('annotation_sha256')
                exported_record = exports_by_id.get(row['sample_id'])
                row['export_annotation_sha256'] = exported_record['export_hashes']['annotation.json'] if exported_record else None
                row['export_sample_path'] = str(output / 'samples' / row['sample_id']) if exported_record else None
                row['source_capture_evidence_status'] = row.pop('machine_evidence_status')
                row['capture_binding_status'] = 'NOT_A_CAPTURE_BINDING'
                row['narrative_revision_applied'] = row['sample_id'] in revision_map
            evidence.update(schema_version='webcollect-narrative-provenance-1',
                            capture_binding=False,
                            provenance_scope='Source-to-export annotation revisions; not proof that revised prose was captured or human-approved',
                            revision_plan={'path': str(revision_path), 'sha256': revision_sha256,
                                           'canonical_sha256': hashlib.sha256(json.dumps(revision_plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()},
                            requires_fresh_export_review=True)
        if normalization_map:
            exports_by_id = {r['sample_id']: r for r in exported}
            for row in sidecar_samples:
                row['source_annotation_sha256'] = row.pop('annotation_sha256', row.get('source_annotation_sha256'))
                exported_record = exports_by_id.get(row['sample_id'])
                row['export_annotation_sha256'] = exported_record['export_hashes']['annotation.json'] if exported_record else None
                row['export_sample_path'] = str(output / 'samples' / row['sample_id']) if exported_record else None
                row['source_capture_evidence_status'] = row.pop('machine_evidence_status', row.get('source_capture_evidence_status'))
                row['capture_binding_status'] = 'NOT_A_CAPTURE_BINDING'
                row['action_normalization_changes'] = normalization_map.get(row['sample_id'], [])
            evidence.update(schema_version='webcollect-action-normalization-provenance-1',
                            capture_binding=False,
                            provenance_scope='Source-to-export annotation normalization; original executed keys remain in source capture evidence',
                            action_normalization_policy=WINDOWS_KEYBOARD_NORMALIZATION_VERSION,
                            requires_fresh_export_review=True)
        # Recheck source bytes after staging; do not silently bind changed sources.
        if any(sample_hashes(r['sample']) != r['hashes'] or sha(r['truth']) != r['truth_sha256'] or
               any(sha(r['batch'] / k) != h for k, h in r['source_files'].items()) for r in records):
            raise ValueError('Source changed during export')
        if revision_plan is not None and sha(revision_path) != revision_sha256:
            raise ValueError('Narrative revision plan changed before provenance was sealed')
        if (reviews and sha(reviews) != frozen_review_sha) or (selection_report and sha(selection_report) != frozen_selection_sha):
            raise ValueError('Review or selection report changed during export')
        for path in destinations[1:]:
            path.parent.mkdir(parents=True, exist_ok=True)
        if reviews:
            with review_output.open('x', encoding='utf-8') as stream:
                json.dump({'schema_version': review_export['schema_version'], 'records': [review_map[r['sample_id']] for r in selected if r['sample_id'] in review_map]}, stream, ensure_ascii=False, indent=2); stream.write('\n')
        with evidence_output.open('x', encoding='utf-8') as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write('\n')
        if output.exists():
            raise FileExistsError('Customer output appeared during export')
        staged.rename(output)
    return dict(output=str(output), layout='client', evidence_output=str(evidence_output.resolve()), review_output=str(review_output.resolve()) if reviews else None, source_population=evidence['source_population'], samples=len(selected), frames=contract['steps'], contract=contract, independent_qc_status='NOT_RUN', customer_acceptance='UNKNOWN')
