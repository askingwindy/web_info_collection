"""策略 3 回写、单独判定、事实引文核对与保存资格（唯一所有者）。

回写机械校验失败最多修正一次、判定一次；语义不通过即不保存，不请求模型改成通过。保存资格只
依据封存事实：完成状态、有效步数、判定结果、连续性与未知状态。
"""
import re

from ..closing_policy import COMPLETED_GOAL_DELIVERY
from . import prompt

STEPWISE_PROTOCOL = 'stepwise-1'
MIN_EFFECTIVE_STEPS = 5
MAX_EFFECTIVE_STEPS = 12


class FinalizationRejected(ValueError):
    """回写/判定/引文核对不通过；保留原件、不保存。"""


def specified_instruction(goal, app_name):
    """指定目标的交付指令：使用原指令文本；结构化目标由宿主如实渲染。

    原指令不是可交付文本时抛错并记录原因（SDD §3：不能在回写中换成更容易
    的任务，也不能把结构化目标静默丢弃）。
    """
    if isinstance(goal, str) and goal.strip():
        return goal.strip()
    if isinstance(goal, dict):
        text = goal.get('instruction')
        if isinstance(text, str) and text.strip():
            return text.strip()
        pieces = [str(item) for item in (goal.get('kind'), goal.get('entity')) if item]
        parameters = goal.get('parameters')
        detail = ''
        if isinstance(parameters, dict) and parameters:
            detail = '：' + '、'.join('%s为%s' % (key, value)
                                     for key, value in parameters.items())
        if pieces:
            return '在「%s」上完成%s%s' % (app_name, '/'.join(pieces), detail)
        if detail:
            return '在「%s」上完成指定目标%s' % (app_name, detail)
    raise ValueError('STEPWISE_GOAL_NOT_DELIVERABLE: 指定目标缺少可交付的任务指令文本：' + repr(goal)[:200])


def validate_writeback(arguments, *, mode, app_name):
    """字段级校验与上限；指定模式指令保持原目标，不接受模型改写。"""
    if not isinstance(arguments, dict):
        raise FinalizationRejected('WRITEBACK_NOT_OBJECT')
    instruction = arguments.get('task_instruction')
    if not isinstance(instruction, str) or not instruction.strip():
        raise FinalizationRejected('WRITEBACK_INSTRUCTION_REQUIRED')
    instruction = instruction.strip()
    if len(instruction) > prompt.LIMIT_INSTRUCTION:
        raise FinalizationRejected('WRITEBACK_INSTRUCTION_TOO_LONG')
    from ..task_instruction import validate_task_instruction
    try:
        validate_task_instruction(instruction)
    except ValueError as error:
        raise FinalizationRejected('WRITEBACK_INSTRUCTION_INVALID:' + str(error))
    if mode == 'specified':
        # 指定目标：最终指令由宿主使用原目标文本；模型输出仅保留供审计对照。
        instruction = None
    task_type = arguments.get('task_type')
    if (not isinstance(task_type, list) or not 1 <= len(task_type) <= 3
            or any(label not in prompt.TASK_TYPE_LABELS for label in task_type)):
        raise FinalizationRejected('WRITEBACK_TASK_TYPE_INVALID')
    final_result = arguments.get('final_result')
    if not isinstance(final_result, str) or not final_result.strip():
        raise FinalizationRejected('WRITEBACK_FINAL_RESULT_REQUIRED')
    final_result = final_result.strip()
    if len(final_result) > prompt.LIMIT_FINAL_RESULT:
        raise FinalizationRejected('WRITEBACK_FINAL_RESULT_TOO_LONG')
    judgement = arguments.get('completion_judgement')
    if not isinstance(judgement, str) or not judgement.strip():
        raise FinalizationRejected('WRITEBACK_JUDGEMENT_REQUIRED')
    judgement = judgement.strip()
    if len(judgement) > prompt.LIMIT_COMPLETION_JUDGEMENT:
        raise FinalizationRejected('WRITEBACK_JUDGEMENT_TOO_LONG')
    return {'task_type': list(task_type), 'final_result': final_result,
            'completion_judgement': judgement, 'model_instruction': instruction}


def validate_judgement(arguments):
    if not isinstance(arguments, dict):
        raise FinalizationRejected('JUDGEMENT_NOT_OBJECT')
    for key in ('instruction_specific', 'completed', 'judgement_supported'):
        if not isinstance(arguments.get(key), bool):
            raise FinalizationRejected('JUDGEMENT_FIELD_INVALID:' + key)
    for key in ('redundant_steps', 'mismatch_steps'):
        value = arguments.get(key)
        if (not isinstance(value, list)
                or any(type(item) is not int or item < 1 for item in value)):
            raise FinalizationRejected('JUDGEMENT_FIELD_INVALID:' + key)
    reason = arguments.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise FinalizationRejected('JUDGEMENT_REASON_REQUIRED')
    return {'instruction_specific': arguments['instruction_specific'],
            'completed': arguments['completed'],
            'judgement_supported': arguments['judgement_supported'],
            'redundant_steps': list(arguments['redundant_steps']),
            'mismatch_steps': list(arguments['mismatch_steps']),
            'reason': reason.strip()[:prompt.LIMIT_JUDGEMENT_REASON]}


def judgement_passed(judgement):
    return (judgement['instruction_specific'] is True
            and judgement['completed'] is True
            and judgement['judgement_supported'] is True
            and judgement['redundant_steps'] == []
            and judgement['mismatch_steps'] == [])


# ---------------------------------------------------------------- 事实引文核对
_QUOTED = re.compile(r'「([^」]{1,200})」')
_COMPACT = re.compile(r'\s+')


def _corpus(text_source):
    parts = []
    if isinstance(text_source, dict):
        parts.append(text_source.get('title') or '')
        parts.append(text_source.get('visible_text') or '')
        for element in text_source.get('elements') or []:
            parts.append(element.get('text') or '')
            parts.append(element.get('visible_text') or '')
    else:
        parts.append(str(text_source or ''))
    return _COMPACT.sub('', ' '.join(parts))


def quoted_segments(text):
    return [match.group(1) for match in _QUOTED.finditer(text or '')]


_PUNCTUATION = str.maketrans('？！，：（）', '?!,:()')


def missing_quotes(fields, state, location):
    corpus = _corpus(state)
    selected = prompt.selected_option_labels(state) if isinstance(state, dict) else {}
    option_labels = {_COMPACT.sub('', label) for label in selected.values()}
    problems = []
    for field, text in fields:
        for quote in quoted_segments(text):
            compact = _COMPACT.sub('', quote)
            if compact in corpus or compact in option_labels:
                continue
            problem = f'{field} 引文「{quote[:60]}」不在{location}'
            # Suggest the original spelling. A punctuation variant still fails the check.
            position = corpus.translate(_PUNCTUATION).find(compact.translate(_PUNCTUATION))
            if position >= 0:
                problem += f'，本帧原文为「{corpus[position:position + len(compact)]}」'
            problems.append(problem)
    return problems


def decision_citations_check(arguments, state, *, previous_action):
    fields = ['page_name', 'precondition']
    if previous_action:
        fields.append('last_step_result')
    return missing_quotes(((name, arguments.get(name)) for name in fields), state, '本帧')


def citations_check(annotation, frame_texts):
    """引文按字段所属帧检查；输入值与 expected_result 不作事实核对。

    frame_texts[i] 对应交付 steps[i] 的本帧（操作前帧）；末元素即终态帧。
    precondition/page_name 命中本帧；step_result 命中下一交付帧（末步命中
    终态帧）；final_result/completion_judgement 命中终态帧。
    """
    problems = []
    steps = annotation.get('steps') or []
    if len(frame_texts) != len(steps):
        raise ValueError('STEPWISE_CITATION_FRAMES_MISMATCH')
    for index, step in enumerate(steps):
        prefix = f"step {step.get('step_id')}"
        precondition = step.get('precondition')
        if precondition is None:
            precondition = (step.get('action') or {}).get('precondition')
        problems.extend(missing_quotes([(prefix + ' page_name', step.get('page_name')),
                                        (prefix + ' precondition', precondition)], frame_texts[index], '本帧'))
        target = frame_texts[min(index + 1, len(steps) - 1)]
        problems.extend(missing_quotes([(f"step {step.get('step_id')} step_result", step.get('step_result'))],
                                       target, '下一交付帧'))
    problems.extend(writeback_citations_check(annotation, frame_texts[-1]))
    return problems


def writeback_citations_check(writeback, final_state):
    """仅检查可重写的回写字段；不修改历史决策或轨迹引文。"""
    return missing_quotes(((name, writeback.get(name)) for name in ('final_result', 'completion_judgement')),
                          final_state, '终态帧')


# ---------------------------------------------------------------- 保存资格
def save_eligibility(annotation, raw_execution):
    """策略 3 唯一保存资格判定（collection_strategy.save_eligibility 分流至此）。

    通过 = 判定三布尔全真且两个列表为空 ∧ completion success ∧ 5–12 有效步
    ∧ 无 unknown/中断/连续性缺口/可信前缀/步骤异常证据。
    """
    steps = annotation.get('steps') or []
    effective = sum(step.get('action', {}).get('action_type') not in ('wait', 'complete')
                    for step in steps)
    judgement = raw_execution.get('judgement') or {}
    passed = (isinstance(judgement, dict)
              and judgement.get('instruction_specific') is True
              and judgement.get('completed') is True
              and judgement.get('judgement_supported') is True
              and judgement.get('redundant_steps') == []
              and judgement.get('mismatch_steps') == [])
    completed = bool(passed
                     and annotation.get('completion_status') == 'success'
                     and raw_execution.get('stop_reason') == 'complete_success'
                     and not raw_execution.get('unknown')
                     and not raw_execution.get('continuity_gaps')
                     and not raw_execution.get('trusted_prefix')
                     and not any(step.get('exception_evidence') for step in steps))
    # 封存原始记录的有效步数必须与交付 annotation 一致；不一致即不可保存。
    sealed_effective = raw_execution.get('effective_steps')
    consistent = sealed_effective is None or sealed_effective == effective
    eligible = bool(completed and consistent
                    and MIN_EFFECTIVE_STEPS <= effective <= MAX_EFFECTIVE_STEPS
                    and MIN_EFFECTIVE_STEPS <= sealed_effective <= MAX_EFFECTIVE_STEPS
                    and not annotation.get('short_flow'))
    return {'delivery_policy': COMPLETED_GOAL_DELIVERY,
            'effective_steps': effective,
            'completion_status': annotation.get('completion_status'),
            'original_goal_completed': completed,
            'ordinary_target_eligible': eligible,
            'delivery_eligible': eligible,
            'QC_approval': False}


def raw_execution_facts(*, stop_reason, stop_details, unknown, effective_steps,
                        actual_dispatches, completion_status, writeback, judgement,
                        continuity_gaps, specified_instruction_text=None):
    """saved_sample.json 的 raw_execution 载荷（含冻结策略标记）。"""
    return {'protocol': STEPWISE_PROTOCOL,
            'collection_strategy': {'id': 'stepwise'},
            'stop_reason': stop_reason,
            **({'stop_details': stop_details} if stop_details else {}),
            'unknown': bool(unknown),
            'effective_steps': effective_steps,
            'actual_dispatches': actual_dispatches,
            'completion_status': completion_status,
            'writeback': writeback,
            'judgement': judgement,
            'continuity_gaps': list(continuity_gaps or []),
            'goal_evidence': {'business_goal_status':
                              'VERIFIED' if judgement and judgement_passed(judgement) else 'UNCONFIRMED'},
            **({'specified_instruction': specified_instruction_text}
               if specified_instruction_text is not None else {})}
