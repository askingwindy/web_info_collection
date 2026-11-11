"""Optional, evidence-bound annotation repair. No model or browser entry point.

This produces a pending revision, never re-derives a trajectory or decides
business completion. Callers choose fields and samples before delivery export.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

VERSION = 'annotation-corrections'
FIELDS = frozenset({'hotkey', 'expected_result', 'next_step_rationale',
                    'short_flow_reason', 'final_result', 'completion_judgement',
                    'completion_status', 'narrative_language'})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_ref(ref):
    path = Path(ref['path'])
    if path.is_symlink() or not path.is_file() or sha(path) != ref['sha256']:
        raise ValueError('Evidence file missing or hash differs: ' + path.name)
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def step_narratives(row, before, element=None, *, current_facts=False):
    """Only pre-action facts and recorded purpose/expectation; no hindsight."""
    action = row['action']; args = row.get('arguments', {})
    expected = str(row.get('expected', '')); purpose = str(row.get('semantic_goal') or row.get('goal') or '')
    element = element or {}
    target = row.get('target') or {}
    cid = target.get('control_id') or element.get('element_id')
    values = before.get('values') or []
    current = next((v for v in values if v.get('element_id') == cid), {})
    label = element.get('text') or target.get('label') or ''
    if not label and action == 'hotkey':
        focused = [v for v in values if v.get('focused')]
        if len(focused) == 1:
            current = focused[0]
            focus_element = next((e for e in before.get('elements', [])
                                  if e.get('element_id') == current['element_id']), {})
            label = focus_element.get('text') or ''
    visible = bool(label and any(e.get('element_id') == (cid or current.get('element_id'))
                                for e in before.get('elements', [])))
    result = {}
    if action == 'scroll' and expected in ('实测滚动位置改变', '核验预期条件：scroll_changed', 'scroll_changed'):
        direction = {'down': '下', 'up': '上', 'left': '左', 'right': '右'}.get(args.get('direction'))
        if direction:
            result['expected_result'] = f'预期视口向{direction}移动，显示该方向的页面内容。'
            if re.search('查看|阅读|閱讀|定位|滚动|滾動|浏览|瀏覽|露出', purpose):
                result['next_step_rationale'] = f'原计划需要查看当前视口之外的内容，因此向{direction}滚动以继续定位或阅读。'
    elif action == 'click' and visible and expected in ('核验预期条件：focused', 'focused'):
        result['expected_result'] = f'预期「{label}」获得焦点。'
        if current and not current.get('focused') and re.search('焦点|焦點|输入|輸入|聚焦', purpose):
            result['next_step_rationale'] = f'原计划需要在「{label}」中输入内容；当前焦点不在该控件，因此先点击使其获得焦点。'
    elif action == 'type' and visible and isinstance(args.get('text'), str):
        value = args['text']
        if expected == value and value:
            result['expected_result'] = f'预期「{label}」中的输入值为「{value}」。'
        if (current.get('focused') or current_facts) and value and (value in purpose or re.search('输入|輸入|填写|填寫|设置|設置', purpose)):
            prefix = f'「{label}」已获得焦点' if current.get('focused') else f'当前页面可见「{label}」输入控件'
            result['next_step_rationale'] = prefix + f'，原计划要求填写该字段，因此输入「{value}」。'
    elif action == 'hotkey' and visible and current.get('focused'):
        keys = [str(k).lower() for k in args.get('keys', [])]
        if keys in (['meta', 'a'], ['ctrl', 'a'], ['command', 'a']) and current.get('value') and re.search('全选|全選|覆盖|覆蓋', purpose):
            result['expected_result'] = f'预期选中「{label}」中的现有输入内容。'
            result['next_step_rationale'] = f'「{label}」已获得焦点且已有内容，原计划需要全选或覆盖输入，因此先选中现有内容。'
    return result


def _differences(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict) and before.keys() == after.keys():
        return [p for key in before for p in _differences(before[key], after[key], f'{prefix}/{key}'.strip('/'))]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [p for i, (a, b) in enumerate(zip(before, after)) for p in _differences(a, b, f'{prefix}/{i}')]
    return [] if before == after else [prefix]


def _load_original(sample, source):
    from .postprocess import session_record
    from .planning import object_sha256
    saved = read_ref(source['save_receipt'])
    if saved['sample_id'] != sample.name:
        raise ValueError('Save receipt identity differs')
    evidence = Path(source['save_receipt']['path']).parent
    captured_annotation = evidence.parent.parent / 'samples' / sample.name / 'annotation.json'
    captured = read_ref({'path': str(captured_annotation), 'sha256': saved['sample_files_sha256']['annotation.json']})
    delivered = json.loads((sample / 'annotation.json').read_text())
    for name in ('sample_id', 'task_instruction', 'completion_status', 'final_state_image'):
        if captured.get(name) != delivered.get(name):
            raise ValueError('Delivered original goal/status identity differs: ' + name)
    if len(captured['steps']) != len(delivered['steps']):
        raise ValueError('Delivered step count differs from original')
    for old, new in zip(captured['steps'], delivered['steps']):
        for name in ('step_id', 'image_path', 'ui_tree_path', 'user_goal'):
            if old[name] != new[name]:
                raise ValueError('Delivered step identity or purpose differs: ' + name)
        for name in ('action_type', 'target_element_id', 'coordinate', 'target_bbox', 'target_control_type'):
            if old['action'].get(name) != new['action'].get(name):
                raise ValueError('Delivered action target differs: ' + name)
    derivation_ref = saved['derivation']['record']
    derived = read_ref(derivation_ref)
    if object_sha256(derived['source_mapping']) != saved['derivation']['source_mapping_sha256']:
        raise ValueError('Original step mapping hash differs')
    # Delivered prose may have historical normalization; images/tree must be the
    # exact saved evidence. Their identity anchors step ordering before repair.
    for name, digest in saved['sample_files_sha256'].items():
        if name == 'annotation.json':
            continue
        p = sample / name
        if Path(name).is_absolute() or not p.resolve().is_relative_to(sample.resolve()) or sha(p) != digest:
            raise ValueError('Delivered evidence differs from saved sample: ' + name)
    receipt = evidence / 'raw/raw-receipt.json'
    sealed_digest = saved['capture_files_sha256'].get('raw/raw-receipt.json')
    if not sealed_digest or sha(receipt) != sealed_digest:
        raise ValueError('Original raw receipt is not bound by save receipt')
    record = session_record(evidence / 'raw', allow_unknown_for_prefix=True)
    mapping = {r['step_id']: r for r in derived['source_mapping']}
    if len(mapping) != len(derived['source_mapping']):
        raise ValueError('Ambiguous original step mapping')
    operations = {r['operation_id']: r for r in record['trajectory']}
    if len(operations) != len(record['trajectory']):
        raise ValueError('Ambiguous original operation mapping')
    return saved, derived, record, mapping, operations, derivation_ref


def correct_annotations(source, output, *, source_index, sample_ids=None, fields=None, apply=False):
    """Inspect or create optional pending revisions using sealed local evidence.

    source_index: path to JSONL (or list) of {sample_id, save_receipt:{path,sha256}}.
    The caller explicitly sets apply=True to write revised samples. The default
    writes only the report. Neither mode starts collection or semantic review.
    """
    source, output = Path(source).resolve(), Path(output).absolute()
    fields = set(FIELDS if fields is None else fields)
    if fields - FIELDS:
        raise ValueError('Unsupported correction fields: ' + ','.join(sorted(fields - FIELDS)))
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output) or any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('Correction output must be a fresh directory outside source')
    sources = ([json.loads(line) for line in Path(source_index).read_text().splitlines() if line.strip()]
               if isinstance(source_index, (str, Path)) else list(source_index))
    index = {r['sample_id']: r for r in sources}
    if len(index) != len(sources):
        raise ValueError('Duplicate source index sample')
    available = {p.name: p for p in (source / 'samples').iterdir() if p.is_dir() and not p.is_symlink()}
    selected = sorted(available if sample_ids is None else sample_ids)
    if len(selected) != len(set(selected)) or any(s not in available for s in selected):
        raise ValueError('Unknown or duplicate selected sample')
    output.mkdir(parents=True)
    report = {'mode': 'apply' if apply else 'inspect',
              'purpose': 'optional_delivery_annotation_repair', 'source': str(source),
              'status': 'revision_pending_review' if apply else 'inspection_only',
              'model_calls': 0, 'browser_actions': 0, 'business_completion_rejudged': False,
              'quality_review': 'NOT_RUN', 'published': False, 'samples': []}
    execution = {'schema_version': 'actual-execution', 'samples': []}
    source_sites = json.loads((source / 'site-list.json').read_text()) if (source / 'site-list.json').is_file() else None
    for sid in selected:
        sample = available[sid]; annotation_path = sample / 'annotation.json'
        annotation_hash = sha(annotation_path)
        original = json.loads(annotation_path.read_text()); revised = deepcopy(original)
        item = {'sample_id': sid, 'annotation_sha256': annotation_hash, 'fields': [],
                'source_save_receipt': index.get(sid, {}).get('save_receipt')}
        edits = []
        def add(path, value, rule, refs):
            node = revised
            for part in path.split('/')[:-1]:
                node = node[int(part)] if isinstance(node, list) else node[part]
            key = path.split('/')[-1]; old = node[key]
            outcome = 'unchanged' if old == value else 'corrected'
            item['fields'].append({'path': path, 'before': old, 'after': value,
                'outcome': outcome, 'rule': VERSION + '/' + rule, 'evidence': refs})
            if old != value:
                node[key] = value; edits.append(path)
        def pending(path, reason, outcome='uncertain'):
            item['fields'].append({'path': path, 'outcome': outcome, 'reason': reason, 'rule': VERSION})
        try:
            if sid not in index:
                raise ValueError('No original save receipt supplied')
            saved, derived, record, mapping, operations, derivation_ref = _load_original(sample, index[sid])
            actual_steps = []
            for position, step in enumerate(original['steps']):
                action = step['action']['action_type']
                if action == 'complete':
                    continue
                mapped = mapping.get(step['step_id'])
                if not mapped or mapped['source_operation_id'] not in operations:
                    raise ValueError('Step has no unique original operation')
                row = operations[mapped['source_operation_id']]
                if row['action'] != action or any(mapped[k] != row[k] for k in ('before_observation_id','after_observation_id')):
                    raise ValueError('Step operation or observation binding differs')
                observation = record['observations'][row['before_observation_id']]
                if sha(sample / step['image_path']) != observation['evidence']['image']['sha256']:
                    raise ValueError('Step image differs from original pre-action observation')
                dispatch = read_ref(row['dispatch']); raw_step = read_ref(row['raw_step'])
                operation = dispatch['operation']
                if operation['action_type'] != action or operation['arguments'] != row['arguments']:
                    raise ValueError('Dispatch and trajectory arguments conflict')
                if not all(raw_step.get(k) for k in ('dispatched','action_executed','postconditions_checked')) or raw_step.get('execution_error'):
                    raise ValueError('Original operation has no confirmed execution')
                if raw_step.get('controller_dispatch', {}).get('sha256') != row['dispatch']['sha256']:
                    raise ValueError('Executed step is not bound to dispatch')
                if raw_step.get('operation') != operation:
                    raise ValueError('Executed operation differs from dispatch')
                from .action_normalization import canonical_windows_keys
                old_args = step['tool_call']['arguments']; actual_args = row['arguments']
                compatible = old_args == actual_args
                if action == 'hotkey' and set(old_args) == set(actual_args) == {'keys'}:
                    compatible = compatible or old_args['keys'] == canonical_windows_keys(actual_args['keys'], original['device_info']['os_name'])
                if not compatible:
                    raise ValueError('Delivered operation differs beyond historical key representation')
                refs = [index[sid]['save_receipt'], derivation_ref, row['dispatch'], row['raw_step'], observation['evidence']['state']]
                actual_steps.append({'step_id': step['step_id'], 'tool_name': action,
                    'arguments': actual_args, 'dispatch_ref': row['dispatch'], 'raw_step_ref': row['raw_step']})
                if action == 'hotkey' and 'hotkey' in fields:
                    keys = actual_args['keys']
                    add(f'steps/{position}/tool_call/arguments/keys', keys, 'actual-dispatch-keys', refs)
                    add(f'steps/{position}/action/input_text', '+'.join(keys), 'actual-dispatch-keys', refs)
                    from .action_normalization import display_actual_keys
                    add(f'steps/{position}/action/target_text', display_actual_keys(keys), 'actual-dispatch-keys', refs)
                before = read_ref(observation['evidence']['state'])
                narratives = step_narratives(row, before, raw_step.get('target_element'))
                for name in ('expected_result','next_step_rationale'):
                    if name not in fields:
                        continue
                    path = f'steps/{position}/' + ('action/' if name == 'expected_result' else '') + name
                    if name in narratives:
                        add(path, narratives[name], 'pre-action-' + name, refs)
                    else:
                        pending(path, 'Original pre-action facts do not uniquely support a better narrative')
            if 'short_flow_reason' in fields and original.get('short_flow'):
                ending = record['terminal'].get('ending_reason') or record['terminal'].get('stop_reason')
                if isinstance(ending, str) and ending.strip() and 'short_flow_reason' in original:
                    count = sum(s['action']['action_type'] not in ('wait','complete') for s in original['steps'])
                    add('short_flow_reason', f'实际保留{count}个有效业务动作；原始结束原因：{ending}。此说明不代表原目标已完成。',
                        'original-ending', [index[sid]['save_receipt'], {'path': str(Path(index[sid]['save_receipt']['path']).parent/'raw/terminal.json'), 'sha256':sha(Path(index[sid]['save_receipt']['path']).parent/'raw/terminal.json')}])
                else:
                    pending('short_flow_reason', 'No unique original ending reason')
            for name in ('final_result','completion_judgement','completion_status'):
                if name in fields:
                    pending(name, 'Requires original-goal/terminal semantic decision; no automatic status or result inference')
            if 'narrative_language' in fields:
                pending('narrative_language', 'Arbitrary prose conversion is not enabled; UI quotations and goal meaning preserved')
            if original.get('short_flow') or original['completion_status'] != 'success':
                pending('delivery_eligibility', 'Annotation repair cannot add actions or establish original-goal completion', 'capture_defect')
            if any(not any(path == edit or path.startswith(edit + '/') for edit in edits)
                   for path in _differences(original, revised)):
                raise ValueError('Correction changed a non-whitelisted field')
            if sha(annotation_path) != annotation_hash:
                raise ValueError('Source annotation changed during repair')
            if apply and edits:
                dest = output / 'samples' / sid
                shutil.copytree(sample, dest)
                (dest / 'annotation.json').unlink()
                write(dest / 'annotation.json', revised)
                item['revision_annotation_sha256'] = sha(dest / 'annotation.json')
                item['revision_files_sha256'] = {p.relative_to(dest).as_posix(): sha(p) for p in sorted(dest.rglob('*')) if p.is_file()}
                truth = source / 'ground_truth' / (sid + '.json')
                if truth.is_file() and not truth.is_symlink():
                    target_truth = output / 'ground_truth' / truth.name
                    target_truth.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(truth, target_truth)
                    item['original_ground_truth'] = {'path': str(truth), 'sha256': sha(truth)}
                execution['samples'].append({'sample_id': sid, 'annotation_sha256': item['revision_annotation_sha256'],
                    'platform': original['device_info']['os_name'], 'steps': actual_steps})
            item['changed_fields'] = len(edits)
            item['status'] = 'corrected_pending_review' if edits else 'unchanged_with_pending_items'
        except (ValueError, KeyError, TypeError, OSError) as exc:
            # No partial sample may escape after a failed evidence check.
            item['fields'] = [dict(f, outcome='not_applied') if f.get('outcome') == 'corrected' else f for f in item['fields']]
            item.update(status='evidence_unresolved', changed_fields=0, error=str(exc))
            failed = output / 'samples' / sid
            if failed.exists():
                rejected = output / 'incomplete' / sid
                rejected.parent.mkdir(parents=True, exist_ok=True)
                failed.rename(rejected)
        report['samples'].append(item)
    report['summary'] = {'sample_count': len(report['samples']),
        'changed_samples': sum(bool(r['changed_fields']) for r in report['samples']),
        'changed_fields': sum(r['changed_fields'] for r in report['samples']),
        'sample_statuses': dict(Counter(r['status'] for r in report['samples'])),
        'field_outcomes': dict(Counter(f['outcome'] for r in report['samples'] for f in r['fields']))}
    if apply and source_sites and execution['samples']:
        selected_ids = {r['sample_id'] for r in execution['samples']}
        sites = deepcopy(source_sites)
        sites['samples'] = [r for r in sites['samples'] if r['sample_id'] in selected_ids]
        for site in sites['sites']:
            site['sample_ids'] = [sid for sid in site['sample_ids'] if sid in selected_ids]
        sites['sites'] = [site for site in sites['sites'] if site['sample_ids']]
        write(output / 'site-list.json', sites)
    write(output / 'corrections.json', report)
    write(output / 'execution-evidence.json', execution)
    return {k:v for k,v in report.items() if k != 'samples'} | {'report': str(output / 'corrections.json'),
        'execution_evidence': str(output / 'execution-evidence.json')}
