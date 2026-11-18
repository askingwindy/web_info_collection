"""策略 3 附件A annotation 生成：交付字段唯一来源见 SDD §10.1。

交付图片使用原始干净截图（编号图只作模型输入）；界面树与截图同一时刻。
screen_changed 按实际相邻交付原图字节计算并保留真实值；末步 complete 省略。
"""
import platform as _platform
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from webcollect import workspace_json as json

from ..action_normalization import normalize_delivery_step
from ..batch_core import file_sha

POINTER_WITH_COORDINATE = ('click', 'double_click', 'right_click', 'scroll', 'select')


def _context_host(url, fallback):
    host = urlsplit(url or '').hostname
    return 'Web / ' + (host or fallback)


def _action_fields(row, native_arguments):
    action_type = row['operation']['action_type']
    element = row.get('element')
    action = {'action_type': action_type,
              'target_element_id': '', 'target_text': '',
              'coordinate': [], 'input_text': '',
              'precondition': row['decision'].get('precondition', ''),
              'expected_result': row['decision'].get('expected_result', '')}
    if action_type == 'type':
        action['input_text'] = native_arguments.get('text', '')
    elif action_type == 'hotkey':
        action['input_text'] = '+'.join(native_arguments.get('keys') or [])
    if action_type in POINTER_WITH_COORDINATE:
        action['coordinate'] = [native_arguments['x'], native_arguments['y']]
    if element is not None and action_type in ('click', 'double_click', 'right_click',
                                               'type', 'select'):
        action['target_element_id'] = element['element_id']
        action['target_text'] = (element.get('text') or '').strip()
        action['target_bbox'] = list(element['bbox'])
        if element.get('element_type'):
            action['target_control_type'] = element['element_type']
    return action


def build_delivery(sample_dir, journal, task, *, delivered, complete_row, omitted,
                   instruction_text, writeback, judgement, specified=False):
    """写入 samples/<sid>/{annotation.json, images/, ui_tree/} 与 ground truth。

    delivered 行按交付顺序携带 dispatch/decision/element/frame；complete_row
    携带终态帧与 complete 决策。返回 annotation dict（含实际 screen_changed）。
    """
    sample = Path(sample_dir)
    (sample / 'images').mkdir(parents=True, exist_ok=True)
    (sample / 'ui_tree').mkdir(parents=True, exist_ok=True)
    sample_id = sample.name
    host_fallback = task.get('app_name') or ''
    steps = []
    frame_texts = []
    delivered_rows = list(delivered) + [complete_row]
    for index, row in enumerate(delivered_rows, 1):
        frame = journal.frames[row['frame_id']]
        state = frame['state']
        image_path = 'images/step_%03d.png' % index
        shutil.copyfile(frame['png'], sample / image_path)
        write_tree(sample / 'ui_tree' / ('step_%03d.json' % index),
                   {'image_path': image_path,
                    'screen_resolution': state.get('screen_resolution'),
                    'elements': state.get('elements') or []})
        frame_texts.append({'title': state.get('title'),
                            'visible_text': state.get('visible_text'),
                            'elements': state.get('elements') or []})
        is_complete = row is complete_row
        decision = row.get('decision') or {}
        if is_complete:
            native = {'status': 'success'}
            action = {'action_type': 'complete', 'target_element_id': '',
                      'target_text': '', 'coordinate': [], 'input_text': '',
                      'precondition': decision.get('precondition', ''),
                      'expected_result': decision.get('expected_result', '')}
            step_result = writeback['final_result']
            timestamp = row.get('completed_at') or ''
        else:
            operation = row['operation']
            native = dict(operation['arguments'])
            action = _action_fields(row, native)
            step_result = row['step_result']
            timestamp = row.get('dispatched_at') or ''
        step = {'step_id': index, 'image_path': image_path,
                'ui_tree_path': 'ui_tree/step_%03d.json' % index,
                'page_name': decision.get('page_name', ''),
                'user_goal': decision.get('user_goal', ''),
                'action': action,
                'tool_call': {'tool_name': action['action_type'],
                              'call_id': '%s_%03d' % (sample_id, index),
                              'arguments': native, 'timestamp': timestamp,
                              'context': _context_host(state.get('url'), host_fallback)},
                'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                'next_step_rationale': decision.get('thought', ''),
                'step_result': step_result,
                'exception_evidence': []}
        steps.append(normalize_delivery_step(step, _platform.system()))
    # 非末步 screen_changed 按实际相邻交付原图计算；末步 complete 省略。
    for position in range(len(steps) - 1):
        steps[position]['tool_result']['return_value']['screen_changed'] = (
            file_sha(sample / steps[position]['image_path'])
            != file_sha(sample / steps[position + 1]['image_path']))
    final_state = journal.frames[complete_row['frame_id']]['state']
    annotation = {'sample_id': sample_id,
                  'task_instruction': instruction_text,
                  'task_type': writeback['task_type'],
                  'terminal_type': 'Web',
                  'device_info': {'device_model': '',
                                  'os_name': 'macOS' if _platform.system() == 'Darwin' else _platform.system(),
                                  'os_version': (_platform.mac_ver()[0] or _platform.release())
                                  if _platform.system() == 'Darwin' else _platform.release(),
                                  'screen_resolution': final_state.get('screen_resolution')},
                  'app_info': {'app_name': task.get('app_name') or host_fallback,
                               'app_version': '', 'environment': '真实网站 / 隔离浏览器上下文',
                               'ui_language': 'zh'},
                  'risk_level': 'normal',
                  'trajectory_source': {'source_type': 'agent', 'data_type': 'stepwise',
                                        'action_space': 'unified_gui_v4'},
                  'steps': steps,
                  'final_state_image': steps[-1]['image_path'],
                  'final_result': writeback['final_result'],
                  'completion_status': 'success',
                  'completion_judgement': writeback['completion_judgement']}
    _write_json(sample / 'annotation.json', annotation)
    ground_truth = [{'step_id': step['step_id'],
                     'element_id': step['action']['target_element_id'],
                     'text': step['action']['target_text'],
                     'bbox': step['action']['target_bbox']}
                    for step in steps
                    if step['action'].get('target_element_id') and 'target_bbox' in step['action']]
    _write_json(journal.evidence / 'ground_truth.json', ground_truth)
    return annotation, frame_texts


def write_tree(path, tree):
    Path(path).write_text(json.dumps(tree, ensure_ascii=False) + '\n', encoding='utf-8')


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
