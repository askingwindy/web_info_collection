"""Synthetic planning inputs for controlled tests; never delivery evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3


NOW = 1800000000.0


def evidence(path, text='controlled test evidence, not actual capture or review'):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]


def make_plan(root, count=1, *, task_prefix='task', uri='https://example.org/', category='工具', version='1', expires_at=None):
    from webcollect.planning import publish_plan
    from webcollect.preflight import SOURCE_FILES, _files, digest, object_digest, schedule_plan
    import webcollect.preflight as module
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    capability = {'schema_version': 'webcollect-site-capability-1', 'capability_id': task_prefix + '-cap',
                  'version': '1', 'site_uri': uri, 'site_category': category,
                  'observed_at': NOW - 100, 'expires_at': expires_at or NOW + 10000,
                  'status': 'ready', 'supported_actions': ['scroll'], 'task_families': ['controlled-reading'],
                  'evidence': evidence(root / 'capability-fixture.txt')}
    tasks = []
    for number in range(count):
        tasks.append({'task_id': f'{task_prefix}-{number}', 'task_version': version,
                      'capability_id': capability['capability_id'], 'capability_version': '1',
                      'task_family': 'controlled-reading', 'site_uri': uri, 'site_category': category,
                      'app_name': '受控工程夹具', 'instruction': '查看「受控夹具」并核对最后的完成事实。',
                      'task_type': ['数据查看'], 'initial_url': uri, 'stop_when_final': True,
                      'operations': [{'operation_id': f'op-{i}', 'subgoal_id': 'goal', 'action_type': 'scroll',
                                      'goal': '读取后续内容', 'rationale': '后续事实尚未显示', 'expected': '显示新正文',
                                      'arguments': {'x': 600, 'y': 350, 'direction': 'down'}} for i in range(5)],
                      'required_actions': [], 'subgoals': [{'id': 'goal', 'description': '核对完成事实',
                                                          'evidence': [{'final_assertion_index': 0}]}],
                      'final_assertions': [{'visible_text': '受控完成事实'}],
                      'final_result': '显示受控完成事实', 'completion_judgement': '核对可见正文完成事实'})
    plan = {'schema_version': 'webcollect-plan-m4-1', 'tasks': tasks,
            'production_facts': {'accounts_and_privacy': 'Synthetic fixture only; no real collection.',
                                 'narrative_generation': 'Controlled test template', 'narrative_mode': 'template',
                                 'prompt_stages': {name: {'mode': 'template', 'template_version': 'test-1',
                                                        'description': 'Controlled fixture, not historical model input'}
                                                  for name in ('planning', 'narrative')}}}
    folder = root / 'preflight'
    folder.mkdir()
    (folder / 'input-plan.json').write_text(json.dumps(plan, ensure_ascii=False))
    records = []
    for index, task in enumerate(tasks):
        directory = folder / f'task_{index + 1:03d}'
        directory.mkdir()
        # The binding validator is exercised using explicitly synthetic files.
        for name in ('initial.png', 'initial.json', 'frame_001.png', 'frame_001.json', 'frame_002.png', 'frame_002.json'):
            (directory / name).write_text('synthetic preflight binding fixture; not a browser image')
        record = {'schema_version': 'webcollect-page-preflight-1', 'task_id': task['task_id'],
                  'task_sha256': object_digest(task), 'summary': {'routing': 'NORMAL_M1'},
                  'requested_probe_count': 2,
                  'frames': [{'path': f'frame_{i:03d}.png', 'raw_path': f'frame_{i:03d}.json'} for i in (1, 2)],
                  'synthetic_fixture_not_delivery': True}
        (directory / 'result.json').write_text(json.dumps(record))
        records.append({**record, 'evidence_directory': directory.name})
    report = {'schema_version': 'webcollect-preflight-report-1', 'records': records,
              'input_plan_sha256': digest(folder / 'input-plan.json'), 'fixed_task_denominator': count,
              'source_changed_during_run': [],
              'source_files_sha256': {name: digest(Path(module.__file__).parent / name) for name in SOURCE_FILES},
              'evidence_files_sha256': _files(folder)}
    path = folder / 'report.json'
    path.write_text(json.dumps(report))
    scheduled = schedule_plan(plan, records, path, digest(path), True)
    publication = publish_plan(scheduled, [capability], now=NOW)
    return scheduled, publication


def make_registry(path):
    from webcollect.storage import ensure_registry_schema
    path = Path(path)
    con = sqlite3.connect(path)
    ensure_registry_schema(con)
    con.close()
    return path
