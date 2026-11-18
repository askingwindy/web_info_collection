"""策略 3 自有原始记录：帧、决策、派发、动作结果、终态与封存收据。

原始干净图片与同次界面树不可覆盖；编号图只作模型输入留档。全部记录落在
evidence/stepwise/（派发执行收据按宿主约定落在 evidence 根 step_NNN.json，
供保存反馈收据与导出核验读取）。不使用旧策略的 raw journal 结构。
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from webcollect import workspace_json as json

from ..agent_controller import exclusive
from ..batch_core import file_sha
from ..planning import verify_evidence

BOUNDARY_SCHEMA = 'stepwise-boundary-1'
RECEIPT_SCHEMA = 'stepwise-raw-receipt-1'
STEP_RECEIPT_SCHEMA = 'stepwise-step-receipt-1'


def _now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Journal:
    """一次 attempt 的追加式原始记录；已写文件一律不可覆盖。"""

    def __init__(self, evidence_root):
        self.evidence = Path(evidence_root)
        self.root = self.evidence / 'stepwise'
        self.root.mkdir(parents=True, exist_ok=True)
        self.frames = {}          # frame_id -> {'state','png','capture','paths'}
        self.frame_order = []
        self.dispatch_seq = 0
        self.sealed = False

    # ------------------------------------------------------------ boundary
    def write_boundary(self, task, *, mode, requested_goal, site_tasks):
        return exclusive(self.root / 'boundary.json', {
            'schema_version': BOUNDARY_SCHEMA,
            'strategy': {'id': 'stepwise'},
            'task': task, 'mode': mode, 'requested_goal': requested_goal,
            'site_tasks': list(site_tasks), 'created_at': _now()})

    # ------------------------------------------------------------ frames
    def add_frame(self, captured, numbered_png=None):
        number = len(self.frame_order) + 1
        frame_id = 'f%03d' % number
        base = self.root / ('observation-%03d' % number)
        image_ref = {'path': str(base.with_suffix('.png').resolve()),
                     'sha256': None}
        (base.with_suffix('.png')).write_bytes(captured['png'])
        image_ref['sha256'] = file_sha(base.with_suffix('.png'))
        state_ref = exclusive(base.with_suffix('.json'), captured['state'])
        capture_ref = exclusive(base.with_suffix('.capture.json'), captured['capture'])
        numbered_ref = None
        if numbered_png is not None:
            numbered_path = self.root / ('observation-%03d.numbered.png' % number)
            numbered_path.write_bytes(numbered_png)
            numbered_ref = {'path': str(numbered_path.resolve()),
                            'sha256': file_sha(numbered_path)}
        frame = {'frame_id': frame_id,
                 'png': str(base.with_suffix('.png').resolve()),
                 'state': captured['state'],
                 'capture': captured['capture'],
                 'refs': {'image': image_ref, 'state': state_ref,
                          'capture': capture_ref,
                          **({'numbered': numbered_ref} if numbered_ref else {})},
                 'captured_at': _now()}
        self.frames[frame_id] = frame
        self.frame_order.append(frame_id)
        return frame

    def renumbered_copy(self, frame, numbered_png):
        """决策前生成编号副本；原帧事实不变。"""
        path = self.root / (Path(frame['png']).stem + '.numbered.png')
        if not path.exists():
            path.write_bytes(numbered_png)
        frame['refs']['numbered'] = {'path': str(path.resolve()), 'sha256': file_sha(path)}
        return frame['refs']['numbered']

    # ------------------------------------------------------------ decisions
    def add_decision(self, *, round_index, frame_id, request_id, arguments,
                     goal_before, goal_after, note_before, note_after, model_ref):
        record = {'schema_version': 'stepwise-decision-1',
                  'round': round_index, 'frame_id': frame_id,
                  'request_id': request_id, 'arguments': arguments,
                  'task_goal_before': goal_before, 'task_goal_after': goal_after,
                  'note_before': note_before, 'note_after': note_after,
                  'model_response': model_ref, 'decided_at': _now()}
        exclusive(self.root / ('decision-%03d.json' % round_index), record)
        return record

    # ------------------------------------------------------------ dispatch/results
    def begin_dispatch(self, *, frame_id, operation, element):
        self.dispatch_seq += 1
        seq = self.dispatch_seq
        dispatch = {'schema_version': 'stepwise-dispatch-1',
                    'operation': operation,
                    'before_frame': frame_id,
                    'element': ({'element_id': element['element_id'],
                                 'text': element.get('text'),
                                 'bbox': list(element['bbox']),
                                 'element_type': element.get('element_type')}
                                if element else None),
                    'dispatched_at': _now()}
        path = self.root / ('dispatch-%03d.json' % seq)
        exclusive(path, dispatch)
        return seq, dispatch, {'path': str(path.resolve()), 'sha256': file_sha(path)}

    def finish_step(self, *, seq, dispatch_ref, operation, element, dispatched,
                    action_executed, execution_error, before_frame, after_frame,
                    effect, effective, omittable, omit_reason, postconditions_checked,
                    delivery_index=None, after_state=None):
        """执行收据：交付动作按交付序号写 evidence 根 step_NNN.json（宿主反馈/
        导出/试点身份约定的连续序列）；省略或失败派发保留在 stepwise/ 侧档，
        原件不删。step_id 即交付步号，dispatch 序号另记 dispatch_seq。"""
        record = {'schema_version': STEP_RECEIPT_SCHEMA,
                  'step_id': delivery_index if delivery_index is not None else seq,
                  'dispatch_seq': seq,
                  'operation': operation,
                  'target_element': ({'element_id': element['element_id'],
                                      'text': element.get('text'),
                                      'bbox': list(element['bbox']),
                                      'element_type': element.get('element_type'),
                                      'inputable': bool(element.get('inputable'))}
                                     if element else None),
                  'dispatched': dispatched,
                  'action_executed': action_executed,
                  'execution_error': execution_error,
                  'postconditions_checked': postconditions_checked,
                  'controller_dispatch': {'sha256': dispatch_ref['sha256']},
                  'before_frame': before_frame,
                  'after_frame': after_frame,
                  'effect': effect,
                  'effective': effective,
                  'omittable': omittable,
                  'omit_reason': omit_reason,
                  'capture': {'screenshot_sha256': self.frames[before_frame]['refs']['image']['sha256']}
                              if before_frame in self.frames else None,
                  'state': after_state or {},
                  'settlement': 'completed' if execution_error is None else 'failed',
                  'ended_at': _now()}
        if delivery_index is not None:
            path = self.evidence / ('step_%03d.json' % delivery_index)
        else:
            kind = 'omitted' if omittable else 'failed'
            path = self.root / ('%s-%03d.json' % (kind, seq))
        exclusive(path, record)
        return record

    def finish_complete_step(self, *, delivery_index, state, decision, completed_at, frame=None):
        """末步 complete 收据：不派发浏览器，step_result 取回写 final_result；
        与交付动作同序列（step_id 连续、末项为 complete）。"""
        record = {'schema_version': STEP_RECEIPT_SCHEMA,
                  'step_id': delivery_index,
                  'dispatch_seq': None,
                  'operation': {'action_type': 'complete',
                                'arguments': {'status': decision.get('status')},
                                'evidence': {'collection_strategy': 'stepwise',
                                             'terminal': True}},
                  'target_element': None,
                  'dispatched': True,
                  'action_executed': True,
                  'execution_error': None,
                  'postconditions_checked': True,
                  'controller_dispatch': None,
                  'before_frame': frame['frame_id'] if frame else None,
                  'after_frame': None,
                  'effect': 'host_terminal',
                  'effective': False,
                  'omittable': False,
                  'omit_reason': None,
                  'capture': ({'screenshot_sha256': frame['refs']['image']['sha256']}
                              if frame else None),
                  'state': state or {},
                  'settlement': 'completed',
                  'ended_at': completed_at or _now()}
        exclusive(self.evidence / ('step_%03d.json' % delivery_index), record)
        return record

    # ------------------------------------------------------------ delivery map
    def write_delivery_map(self, delivered, complete_step, omitted):
        return exclusive(self.root / 'delivery-map.json', {
            'schema_version': 'stepwise-delivery-map-1',
            'delivered': delivered, 'complete_step': complete_step,
            'omitted': omitted})

    # ------------------------------------------------------------ terminal & seal
    def write_terminal(self, payload):
        return exclusive(self.root / 'terminal.json', payload)

    def seal(self, terminal_ref):
        if self.sealed:
            raise ValueError('stepwise raw journal already sealed')
        files = {path.relative_to(self.root).as_posix(): file_sha(path)
                 for path in sorted(self.root.rglob('*')) if path.is_file()
                 and path.name != 'raw-receipt.json'}
        receipt = {'schema_version': RECEIPT_SCHEMA,
                   'strategy': {'id': 'stepwise'},
                   'boundary': {'path': str((self.root / 'boundary.json').resolve()),
                                'sha256': file_sha(self.root / 'boundary.json')},
                   'terminal': terminal_ref,
                   'files_sha256': files,
                   'not_a_delivery_sample_by_itself': True,
                   'sealed_at': _now()}
        path = self.root / 'raw-receipt.json'
        exclusive(path, receipt)
        self.sealed = True
        return {'path': str(path.resolve()), 'sha256': file_sha(path)}


# ---------------------------------------------------------------- 导出/审计读取
def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def execution_entries(record, supplied=None):
    """按交付 step_id 返回真实动作映射（client_package._execution_record 消费）。

    entries: [{'step_id', 'tool_name', 'arguments', 'dispatch_ref', 'raw_step_ref'}]；
    complete 不需要浏览器派发，由调用方按 HOST_TERMINAL 处理。
    """
    batch = Path(record['batch'])
    sid = record['sample_id']
    root = batch / 'evidence' / sid / 'stepwise'
    receipt = _load(root / 'raw-receipt.json')
    files = receipt.get('files_sha256') or {}
    for name, digest in files.items():
        if file_sha(root / name) != digest:
            raise ValueError('策略3原始记录封存字节改变：' + name)
    mapping = _load(root / 'delivery-map.json')
    verify_evidence([{'path': receipt['terminal']['path'],
                      'sha256': receipt['terminal']['sha256']}])
    entries = []
    for row in mapping['delivered']:
        dispatch_ref = {'path': str((root / row['dispatch_file']).resolve()),
                        'sha256': files[row['dispatch_file']]}
        dispatch = _load(dispatch_ref['path'])
        step_ref = {'path': str((batch / 'evidence' / sid / row['step_file']).resolve()),
                    'sha256': file_sha(batch / 'evidence' / sid / row['step_file'])}
        entries.append({'step_id': row['step_id'],
                        'tool_name': dispatch['operation']['action_type'],
                        'arguments': dispatch['operation']['arguments'],
                        'dispatch_ref': dispatch_ref,
                        'raw_step_ref': step_ref})
    return entries


def unverified_actions(ref):
    """守卫读取：终态 UNKNOWN 或存在已派发但无后帧/未结算的动作时如实上报。"""
    verify_evidence([ref])
    receipt = _load(ref['path'])
    verify_evidence([receipt['terminal']])
    terminal = _load(receipt['terminal']['path'])
    if terminal.get('unknown'):
        yield receipt['terminal']
        return
    for row in terminal.get('steps') or []:
        if row.get('dispatched') is not True:
            continue
        if not row.get('after_frame') or not row.get('ended_at'):
            yield {'path': row['step_file'], 'sha256': file_sha(row['step_file'])}


def read_terminal(evidence_root):
    root = Path(evidence_root) / 'stepwise'
    receipt = _load(root / 'raw-receipt.json')
    verify_evidence([{'path': str((root / 'raw-receipt.json').resolve()),
                      'sha256': file_sha(root / 'raw-receipt.json')}])
    verify_evidence([receipt['terminal']])
    return _load(receipt['terminal']['path'])
