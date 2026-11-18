"""策略 3 采集外壳：collect_runtime 按冻结策略分流进入；负责结束加工与结算。

成功路径 = 一次回写 + 一次单独判定 + annotation 生成 + 事实引文核对 +
sample_check + 去重 + RuntimeStore 正式提交（collected_pending_review）+
候选回写所需的收据。失败路径保留全部原始记录并如实结算。
"""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from webcollect import workspace_json as json

from ..agent_feedback import save_attempt_feedback, site_context
from ..batch_core import load_json
from ..production_quality import sha
from ..runtime import ImageCommitConflict
from ..storage import write_json
from . import annotation as annotation_module
from . import finalize, prompt, records
from .session import StepwiseSession, stepwise_caller

STEPWISE_FINALIZATION = 'stepwise-finalization.json'


def _evidence(path):
    return [{'path': str(Path(path).resolve()), 'sha256': sha(path)}]


def _now():
    return datetime.now(timezone.utc).isoformat()


def recent_site_tasks(registry, site_uri, limit=10):
    """本站已采任务：从已有正式保存结果取精简任务文本，仅作避免重复提示。"""
    import sqlite3

    from ..sqlite_connection import raw_connect

    tasks = []
    try:
        with closing(raw_connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True,
                                 timeout=90)) as con:
            con.row_factory = sqlite3.Row
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='m4_attempts'").fetchone():
                return []
            rows = con.execute(
                'SELECT t.task_json FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key '
                "WHERE a.status='collected_pending_review' AND a.finished_at IS NOT NULL "
                'ORDER BY a.finished_at DESC LIMIT 200').fetchall()
    except sqlite3.Error:
        return []
    for row in rows:
        try:
            task = json.loads(row['task_json'])
        except (TypeError, ValueError):
            continue
        if (task.get('site_uri') or '') != (site_uri or '') and site_uri not in (task.get('site_uri') or ''):
            continue
        instruction = (task.get('instruction') or '').strip()
        if instruction:
            tasks.append(instruction[:60])
        if len(tasks) >= limit:
            break
    return tasks


async def run_collection(context, task, attempt, sample, evidence, output, store, *,
                         ledger, parent_job, registry, manifest, index, navigation=None,
                         page=None, entry_observation=None, host_limits=None, runlog=None):
    """策略 3 的一次完整采集（会话、结束加工、结算）。"""
    from ..collect_runtime import _run_owned_session, sample_hashes
    from ..postprocess import post_seal_name

    evidence, sample = Path(evidence), Path(sample)
    if runlog is not None:
        runlog.attach(attemptId=attempt['attempt_id'], sampleId=attempt['sample_id'],
                      siteId=attempt.get('site_id'))
        runlog.banner(task['site_uri'])
        runlog.info('attempt_started', attemptId=attempt['attempt_id'])
    spec = (task.get('workflow_proposal') or {}).get('spec') or {}
    requested_goal = (spec.get('goal') or {}).get('structured')
    # 宿主claim卫生：同一候选的未决旧attempt阻断新派发（与其它策略同规则）。
    feedback_context = await asyncio.to_thread(site_context, registry, task['site_uri'],
        model_ledger=ledger, candidate_id=(task.get('candidate_binding') or {}).get('candidate_id'))
    if feedback_context['unresolved'] and any(
            row.get('attempt_id') != attempt['attempt_id'] for row in feedback_context['unresolved']):
        from ..collect_runtime import CollectionFailure
        raise CollectionFailure('Unresolved prior attempt blocks stepwise dispatch', 'program')
    site_tasks = await asyncio.to_thread(recent_site_tasks, registry, task['site_uri'])
    call = stepwise_caller(ledger, task, attempt['attempt_id'], parent_job=parent_job, runlog=runlog)
    entry_ready = entry_observation is not None
    if page is None:
        page = await context.new_page()
        page.set_default_timeout(15000)
    session = StepwiseSession(task, evidence, call, page, attempt_id=attempt['attempt_id'],
                              host_limits=host_limits, requested_goal=requested_goal,
                              site_tasks=site_tasks, runlog=runlog, entry_ready=entry_ready)
    try:
        summary = await _run_owned_session(session, host_limits)
    except asyncio.CancelledError as error:
        if error.args and error.args[0] == 'consumer_session_hard_deadline':
            summary = _recovered_summary(session, evidence)
        else:
            raise

    raw_receipt = summary['raw_receipt']
    terminal = {}
    if raw_receipt is not None:
        sealed = load_json(raw_receipt['path'])
        terminal = load_json(sealed['terminal']['path'])

    # ---------------------------------------------------------------- 结算外壳
    async def settle_failure(failure_class, root_cause, *, extra_evidence=(),
                             strategy_save_status='not_saved', strategy_eligibility=None):
        if strategy_eligibility is None:
            strategy_eligibility = 'unresolved' if summary.get('unknown') else 'ineligible'
        failure = evidence / 'failure.json'
        if not failure.exists():
            write_json(failure, {'error': root_cause, 'timestamp': _now(),
                'attempt_id': attempt['attempt_id'], 'task_id': attempt['task_id'],
                'failure_class': failure_class, 'raw_saved': True,
                'stop_reason': summary.get('stop_reason'), 'stop_summary': summary.get('stop_summary')})
        from ..failure_policy import disposition
        handling = disposition(failure_class=failure_class, reason=root_cause)
        feedback_ref = await asyncio.to_thread(save_attempt_feedback, evidence, attempt,
                                               'rejected', root_cause)
        await asyncio.to_thread(store.finish_attempt, attempt['attempt_id'],
            attempt['worker_id'], attempt['lease_token'], 'rejected',
            failure_class=failure_class, root_cause=root_cause,
            evidence=[ref for ref in (_evidence(failure) + [feedback_ref, raw_receipt,
                                                            *extra_evidence]) if ref])
        if handling['disposition'] == 'global':
            store.set_scope_paused(True, 'Stepwise program failure; raw execution preserved')
        final_result = _finalized_result(task, summary, terminal,
                                         save_status=strategy_save_status,
                                         eligibility=strategy_eligibility)
        write_json(evidence / 'strategy-result.json',
                   {'strategy_result': final_result, 'runtime_settled': True})
        if runlog is not None:
            runlog.info('save_failed' if strategy_save_status == 'save_failed' else 'failed',
                        failureClass=failure_class, rootCause=str(root_cause)[:200],
                        saveStatus=strategy_save_status, stopReason=summary.get('stop_reason'),
                        unknown=bool(summary.get('unknown')),
                        effectiveSteps=summary.get('effective_steps'))
        return {'status': 'rejected', 'failure_class': failure_class,
                'failure_disposition': handling, 'stop_reason': summary.get('stop_reason'),
                'raw_receipt': raw_receipt, 'strategy_result': final_result}

    if summary.get('unknown') or summary.get('failure_class') == 'interrupted':
        return await settle_failure('interrupted',
            'stepwise_unknown:' + str(summary.get('stop_summary') or summary.get('stop_reason')))
    if summary.get('stop_reason') != 'complete_success':
        return await settle_failure(
            summary.get('failure_class') or 'collector',
            'stepwise_' + str(summary.get('stop_reason')) + ':' + str(summary.get('stop_summary') or '')[:200])

    # ---------------------------------------------------------------- 结束加工
    delivered, omitted = session.delivery_plan()
    if not (finalize.MIN_EFFECTIVE_STEPS <= summary['effective_steps'] <= finalize.MAX_EFFECTIVE_STEPS):
        return await settle_failure('collector', 'stepwise_effective_steps_out_of_range:%d'
                                    % summary['effective_steps'])
    if session.complete_decision is None or session.current is None:
        return await settle_failure('program', 'stepwise_missing_terminal_decision')
    # 回写/判定必须在软截止前完成；来不及则不保存。
    import time as _time
    if host_limits:
        remaining = (host_limits['started_monotonic'] + host_limits['soft_seconds']
                     - _time.monotonic())
        if remaining <= 0:
            return await settle_failure('collector', 'stepwise_soft_deadline_before_finalization')

    actions_summary = ['%s %s → %s' % (row['operation']['action_type'],
                                       (row['element'].get('text') or '')[:40] if row['element'] else '',
                                       (row['step_result'] or '')[:80])
                       for row in delivered]
    first_frame = session.journal.frames[session.journal.frame_order[0]]
    final_frame = session.journal.frames[session.current['frame_id']]
    writeback = None
    judgement = None
    try:
        response = await call(
            phase='writeback',
            system='你是采集回写器。只依据所给材料输出 submit_writeback，不添加新信息。',
            tools=prompt.writeback_tools(),
            user_text=prompt.writeback_message(mode=session.mode,
                requested_goal_text=session._requested_text() if session.mode == 'specified' else None,
                task_goal=session.goal, actions_summary=actions_summary, site_tasks=site_tasks),
            images=[first_frame['png'], final_frame['png']],
            reasoning_effort='high', dispatch_deadline=session._soft_deadline(),
            round_index=session.decision_round + 1, tool_name='submit_writeback')
        writeback = finalize.validate_writeback(
            response.get('arguments') or {}, mode=session.mode,
            app_name=task.get('app_name') or task.get('site_uri'))
        writeback['request_id'] = response.get('request_id')
        # 判定输入：首帧、最后保留动作前帧、终态帧（重合帧去重）。
        last_kept_before = session.journal.frames[delivered[-1]['frame_id']] if delivered else final_frame
        judge_images = [first_frame['png'], last_kept_before['png'], final_frame['png']]
        seen, unique_images = set(), []
        for path in judge_images:
            if path not in seen:
                seen.add(path)
                unique_images.append(path)
        response = await call(
            phase='judgement',
            system='你是独立复核者。只依据截图与动作记录输出 submit_judgement。',
            tools=prompt.judgement_tools(),
            user_text=prompt.judgement_message(
                task_instruction=(finalize.specified_instruction(requested_goal, task.get('app_name'))
                                  if session.mode == 'specified' else writeback['model_instruction']),
                actions_summary=actions_summary, final_result=writeback['final_result'],
                completion_judgement=writeback['completion_judgement']),
            images=unique_images, reasoning_effort='high',
            dispatch_deadline=session._soft_deadline(),
            round_index=session.decision_round + 2, tool_name='submit_judgement')
        judgement = finalize.validate_judgement(response.get('arguments') or {})
        judgement['request_id'] = response.get('request_id')
    except finalize.FinalizationRejected as error:
        return await settle_failure('collector', 'stepwise_' + str(error))
    if not finalize.judgement_passed(judgement):
        return await settle_failure('collector', 'stepwise_judgement_failed:'
                                    + judgement['reason'][:200])

    # annotation 生成与引文核对
    instruction_text = (finalize.specified_instruction(requested_goal, task.get('app_name'))
                        if session.mode == 'specified' else writeback['model_instruction'])
    complete_row = {'frame_id': session.current['frame_id'],
                    'decision': session.complete_decision,
                    'completed_at': session.complete_completed_at}
    annotation, frame_texts = annotation_module.build_delivery(
        sample, session.journal, task, delivered=delivered, complete_row=complete_row,
        omitted=omitted, instruction_text=instruction_text, writeback=writeback,
        judgement=judgement, specified=session.mode == 'specified')
    citation_problems = finalize.citations_check(annotation, frame_texts)
    if citation_problems:
        return await settle_failure('collector', 'stepwise_citation_check_failed:'
                                    + '; '.join(citation_problems)[:200])
    # 相邻交付原图必须有可核验画面变化（非末步）。
    unchanged = [step['step_id'] for step in annotation['steps'][:-1]
                 if step['tool_result']['return_value'].get('screen_changed') is False]
    if unchanged:
        return await settle_failure('collector', 'stepwise_unchanged_delivered_frames:'
                                    + str(unchanged)[:120])

    # 客户格式检查（quality_inspector.sample_check）：确定性错误为0。
    from quality_inspector.format_checks import sample_check
    checked = await asyncio.to_thread(sample_check, sample)
    if checked.get('errors'):
        return await settle_failure('collector', 'stepwise_format_check_failed:'
                                    + str(checked['errors'])[:240],
            extra_evidence=(), strategy_save_status='not_saved')

    # 交付去重：与 RuntimeStore 相同的研究性重叠豁免。
    conflicts = await asyncio.to_thread(index.conflicts, sample)
    from ..candidate_contract import research_duplicate_basis, research_overlap_sample_ids
    research = research_duplicate_basis(task, store.registry)
    overlaps = research_overlap_sample_ids(research)
    blocked = [item for item in conflicts if Path(item['other_sample']).name not in overlaps]
    write_json(evidence / 'producer_dedup.json', {'exact_conflicts': conflicts,
        'research_original_overlap': research, 'blocking_conflicts': blocked,
        'other_routes': 'independent_QC_required', 'not_qualified': True})
    if blocked:
        return await settle_failure('duplicate', 'stepwise_exact_image_conflict',
            extra_evidence=_evidence(evidence / 'producer_dedup.json'))

    # 试点身份收据（宿主保存底线合同：production_identity 为共享基础设施，
    # 非策略2业务；pilot 任务缺少该收据时 RuntimeStore 拒绝保存）。
    if task.get('pilot_identity') is not None:
        from ..production_identity import actual_proof
        raw_rows = [load_json(evidence / row['step_file']) for row in delivered]
        raw_rows.append(load_json(evidence / ('step_%03d.json' % (len(delivered) + 1))))
        proof = actual_proof(task, raw_rows)
        write_json(evidence / 'pilot_identity.json',
                   {**proof, 'annotation_sha256': sha(sample / 'annotation.json')})

    # 结束加工原件（封存入 capture 哈希）
    finalization_receipt = {'schema_version': 'stepwise-finalization-1',
                            'strategy': {'id': 'stepwise'},
                            'attempt_id': attempt['attempt_id'],
                            'writeback': writeback, 'judgement': judgement,
                            'citation_problems': citation_problems,
                            'format_check': {'sample_path': checked.get('sample_path'),
                                             'confirmed_format_pass': checked.get('confirmed_format_pass'),
                                             'errors': checked.get('errors'),
                                             'observations_count': len(checked.get('observations') or [])},
                            'delivered_steps': len(delivered), 'omitted': omitted,
                            'finalized_at': _now()}
    write_json(evidence / STEPWISE_FINALIZATION, finalization_receipt)

    raw_execution = finalize.raw_execution_facts(
        stop_reason='complete_success', stop_details=None, unknown=False,
        effective_steps=summary['effective_steps'],
        actual_dispatches=summary['actual_actions'],
        completion_status='success', writeback=writeback, judgement=judgement,
        continuity_gaps=[], specified_instruction_text=(
            instruction_text if session.mode == 'specified' else None))
    saved = evidence / 'saved_sample.json'
    sample_hashes_map = await asyncio.to_thread(sample_hashes, sample)
    capture_hashes = {name: digest for name, digest in
                      ((path.relative_to(evidence).as_posix(), sha(path))
                       for path in sorted(evidence.rglob('*')) if path.is_file())
                      if not post_seal_name(name)}
    write_json(saved, {'attempt_id': attempt['attempt_id'], 'sample_id': attempt['sample_id'],
                       'sample_files_sha256': sample_hashes_map,
                       'capture_files_sha256': capture_hashes,
                       'semantic_review': 'REVIEW_REQUIRED',
                       'raw_execution': raw_execution,
                       'derivation': {'record': _evidence(evidence / STEPWISE_FINALIZATION)[0],
                                      'delivery_map': _evidence(
                                          session.journal.root / 'delivery-map.json')[0]}})
    commit_error = None
    try:
        feedback_ref = await asyncio.to_thread(save_attempt_feedback, evidence, attempt,
                                               'collected_pending_review')
        finalization_ref = _evidence(evidence / STEPWISE_FINALIZATION)[0]
        await asyncio.to_thread(store.finish_attempt, attempt['attempt_id'],
            attempt['worker_id'], attempt['lease_token'], 'collected_pending_review',
            evidence=_evidence(saved) + [feedback_ref, raw_receipt, finalization_ref],
            exact_images=index.sample_images(sample))
        index.add_sample(sample)
    except ImageCommitConflict as conflict:
        write_json(evidence / 'concurrent_image_conflict.json', {'exact_conflicts': conflict.conflicts})
        return await settle_failure('duplicate', 'stepwise_exact_image_commit_conflict',
            extra_evidence=_evidence(evidence / 'concurrent_image_conflict.json'),
            strategy_save_status='save_failed', strategy_eligibility='ineligible')
    except Exception as error:
        commit_error = error
        import traceback as _traceback
        write_json(evidence / 'commit-exception.json',
                   {'error_type': type(error).__name__, 'error': str(error),
                    'traceback': _traceback.format_exc()[-4000:],
                    'not_business_success_evidence': True})
        try:
            runtime_row = next(row for row in store.snapshot()['attempts']
                               if row['attempt_id'] == attempt['attempt_id'])
        except Exception as lookup_error:
            write_json(evidence / 'commit-outcome-unresolved.json',
                       {'error': str(error), 'lookup_error': str(lookup_error),
                        'requires_reconciliation': True})
            final_result = _finalized_result(task, summary, terminal, save_status='unresolved',
                                             eligibility='eligible')
            write_json(evidence / 'strategy-result.json',
                       {'strategy_result': final_result, 'runtime_settled': False})
            return {'status': 'settlement_failed', 'strategy_result': final_result,
                    'raw_receipt': raw_receipt, 'requires_reconciliation': True}
        if runtime_row['status'] != 'collected_pending_review':
            from ..failure_policy import disposition
            return await settle_failure('program', 'stepwise_runtime_commit_failed:' + str(error)[:200],
                strategy_save_status='save_failed', strategy_eligibility='eligible')
        write_json(evidence / 'secondary-index-failed.json',
                   {'error': str(error), 'runtime_status': runtime_row['status'],
                    'requires_index_reconciliation': True})
    from .. import collection_strategy as _cs
    completion_decision = _cs.save_eligibility(
        load_json(sample / 'annotation.json'), raw_execution)
    final_result = _finalized_result(task, summary, terminal,
                                     save_status='collected_pending_review',
                                     eligibility=('eligible' if completion_decision['delivery_eligible']
                                                  else 'ineligible'),
                                     writeback=writeback, judgement=judgement)
    write_json(evidence / 'strategy-result.json', {'strategy_result': final_result,
                                                   'runtime_settled': commit_error is None})
    if runlog is not None:
        runlog.info('success', saveStatus='collected_pending_review',
                    effectiveSteps=completion_decision['effective_steps'],
                    stopReason='complete_success')
    return {'status': 'collected_pending_review',
            'effective_steps': completion_decision['effective_steps'],
            'completion_delivery': completion_decision,
            'original_goal_completed': completion_decision['original_goal_completed'],
            'short_flow': False, 'stop_reason': 'complete_success',
            'strategy_result': final_result, 'raw_receipt': raw_receipt,
            'saved_sample': str(saved.resolve())}


def _finalized_result(task, summary, terminal, *, save_status, eligibility,
                      writeback=None, judgement=None):
    """组装共享 result_contract 的策略 3 StrategyResult 并替换终态事实。"""
    from ..collection_strategy import RESULT_CONTRACT, finalize_strategy_result, outcome_facts
    goal_status = 'completed' if terminal.get('stop_reason') == 'complete_success' else 'unconfirmed'
    end_reason = summary['end']['end_reason'] if summary.get('end') else 'unknown'
    base = {'result_contract': RESULT_CONTRACT,
            'strategy': {'id': 'stepwise', 'result_contract': RESULT_CONTRACT},
            'binding': {key: task.get(key) for key in ('task_id', 'task_version', 'site_uri')
                        if key in task},
            'goal': {'goal_status': goal_status,
                     'evidence': {'writeback': writeback, 'judgement': judgement}},
            'execution': {'effective_steps': terminal.get('effective_steps'),
                          'actual_dispatches': terminal.get('actual_dispatches'),
                          'evidence_refs': []},
            'end': outcome_facts(goal_status=goal_status, end_reason=end_reason,
                                 eligibility='unresolved', save_status='not_saved'),
            'usage_refs': [], 'raw_receipt': summary['raw_receipt']}
    return finalize_strategy_result(base, save_status=save_status, eligibility=eligibility)


def _recovered_summary(session, evidence):
    """硬截止取消后：已封存则按封存终态重建摘要，否则按 interrupted/unknown 结算。"""
    receipt = getattr(session, '_raw_receipt', None)
    if receipt is not None:
        summary = session._summary(receipt)
        try:
            sealed = records.read_terminal(session.evidence)
            for key in ('stop_reason', 'stop_summary', 'failure_class', 'unknown',
                        'effective_steps', 'actual_dispatches'):
                if sealed.get(key) is not None:
                    summary[key if key != 'actual_dispatches' else 'actual_actions'] = sealed[key]
        except (ValueError, OSError, KeyError):
            pass
        return summary
    return {'strategy': {'id': 'stepwise'}, 'stop_reason': 'blocked',
            'stop_summary': 'consumer_session_hard_deadline', 'unknown': True,
            'failure_class': 'interrupted', 'host_failure': True, 'effective_steps': 0,
            'actual_actions': 0, 'short_flow': False, 'mode': session.mode,
            'task_goal': session.goal, 'raw_receipt': None,
            'end': {'goal_status': 'unconfirmed', 'end_reason': 'unknown',
                    'save_eligibility': 'unresolved', 'save_status': 'not_saved'}}
