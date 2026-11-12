"""Serial M4 collector adapter; the SQLite attempt ledger owns recovery state.

An interrupted browser trajectory is retained as a failed attempt. Resume never
stitches it to another session or reuses its allocated sample ID.
"""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone

from .closing_policy import enabled as closing_enabled
from .production_quality import ConcurrentExactImageIndex, contract_identity, sha
from .storage import write_json, verify_existing_registry
from .validate import read_json, validate_sample
from .navigation import NavigationTimeoutError


class CollectionFailure(ValueError):
    def __init__(self, message, failure_class):
        super().__init__(message)
        self.failure_class = failure_class


def runtime_scope(output):
    return 'output-' + hashlib.sha256(str(Path(output).resolve()).encode()).hexdigest()


def classify_failure(error):
    """Only explicit transport failures are retried; selector timeouts are not."""
    if isinstance(error, CollectionFailure):
        return error.failure_class
    if isinstance(error, sqlite3.OperationalError):
        return 'program'
    from .agent_controller import ControllerStop
    if isinstance(error, ControllerStop):
        return {'UNRESOLVED':'interrupted', 'DUPLICATE':'duplicate', 'EXECUTION_FAILED':'model',
                'ENGINEERING_ERROR':'program', 'MODEL_FAULT':'model'}.get(getattr(error,'category',''), 'collector')
    from .session_core import ReactStop
    if isinstance(error, ReactStop):
        return getattr(error, 'failure_class', None) or 'collector'
    from .browser import EvidenceStale, PlanViewportInfeasible, PlanLabelUnreadable
    if isinstance(error,EvidenceStale):return 'program'
    if isinstance(error,PlanViewportInfeasible):return 'collector'
    if isinstance(error,PlanLabelUnreadable):return 'model'
    from .runtime import ImageCommitConflict
    if isinstance(error, ImageCommitConflict):
        return 'duplicate'
    if isinstance(error, NavigationTimeoutError):
        return 'network'
    # Unhandled internal contract bugs are the collector's own fault, never
    # the site's; they must not consume whole-site failure margin.
    if isinstance(error,(KeyError,TypeError,AttributeError)):
        return 'collector'
    message = str(error)
    if any(token in message for token in ('net::ERR_CONNECTION', 'net::ERR_TIMED_OUT',
                                          'net::ERR_NAME_NOT_RESOLVED', 'net::ERR_NETWORK')):
        return 'network'
    if 'Page.goto: Timeout' in message:
        return 'network'
    if '公开任务遇到登录门槛' in message:
        return 'unsupported'
    return 'semantic'


def source_identity():
    base = Path(__file__).parent
    names = ['collect.py', 'collect_runtime.py', 'navigation.py', 'batch_core.py', 'runtime.py', 'storage.py', 'planning.py',
             'task_contract.py', 'browser.py', 'snapshot.js', 'production_quality.py',
             'content_preparation.py', 'content_preparation.js', 'production_facts.py',
             '__main__.py', 'validate.py', 'evidence.py', 'metadata.py', 'task_instruction.py', 'telemetry.py',
             'action_normalization.py', 'task_generation.py', 'task_admission.py', 'site_scheduler.py', 'observed_workflow.py',
             'admission_cohort.py', 'production_identity.py', 'batch_protocol.py',
             'workflow_proposal.py', 'fragment_workflow.py', 'agent_controller.py', 'agent_observation.py', 'agent_audit.py', 'agent_feedback.py', 'sampling_context.py', 'current_chain.py', 'application_identity.py', 'site_failure_stop.py', 'site_pool_sync.py',
             'react_session.py', 'react_context.py', 'collection_context.py', 'postprocess.py', 'request_quarantine.py','closing_policy.py','trusted_prefix.py','action_stability.py','goal_evidence.py']
    # Bind both model-facing execution and the owning candidate/campaign
    # adapters. Hash source only; credential/configuration values never enter
    # the receipt. Existing frozen receipts are preserved and not rewritten.
    names += ['banded_plan.py', 'plan_evidence.py', 'plan_execution.py',
              'direct_completion.py', 'direct_article.py', 'session_objective.py',
              'wiki_reading.py', 'reading_sections.py', 'numeric_result_evidence.py',
              'key_health.py', 'model_gateway.py', 'model_credentials.py',
              'candidate_consumer.py', 'consumer_campaign.py',
              'collection_strategy.py', 'screenshot_plan.py', 'screenshot_session.py',
              'session_core.py', 'screenshot_execution.py', 'screenshot_observation.py']
    names += [path.relative_to(base).as_posix() for path in sorted((base / 'schemas').glob('*.json'))]
    names += [name for name in ('hmac_strategy.py', 'pbkdf2_strategy.py') if (base / name).is_file()]
    if (base / 'react_protocol.py').is_file():
        names.append('react_protocol.py')
    return {name: sha(base / name) for name in names}


def sample_hashes(sample):
    sample = Path(sample)
    return {p.relative_to(sample).as_posix(): sha(p)
            for p in sorted(sample.rglob('*')) if p.is_file()}


def _merge_quarantined_sample(sample, destination):
    """Complete a repeated close-out: verify same-attempt bytes, never overwrite.

    The failure close-out may have materialized packaging files (feedback
    image copies) under the destination before the move itself ran. Every
    file present on both sides must be byte-equal; files only in the source
    move in; any conflict keeps the attempt failed without touching bytes.
    """
    sample, destination = Path(sample), Path(destination)
    for path in sorted(p for p in sample.rglob('*') if p.is_file()):
        relative = path.relative_to(sample)
        target = destination / relative
        if target.exists():
            if path.read_bytes() != target.read_bytes():
                raise ValueError('隔离目录已有同名不同内容的文件，拒绝覆盖：' + str(target))
            path.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
    for path in sorted((p for p in sample.rglob('*') if p.is_dir()), reverse=True):
        path.rmdir()
    sample.rmdir()


def quarantine_interrupted(output, attempts):
    """Move only rejected attempts, keeping finished samples where they belong.

    A destination that already exists is not automatically a conflict: the
    crashed first close-out (or its feedback receipt) may have created the
    same attempt's packaging files there. Verify-and-continue only on equal
    bytes; a real conflict still fails without overwriting anything.
    """
    output = Path(output)
    for attempt in attempts:
        if attempt['status'] not in ('rejected', 'interrupted'):
            continue
        sample = output / 'samples' / attempt['sample_id']
        if sample.exists():
            destination = output / 'rejected' / attempt['sample_id']
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                _merge_quarantined_sample(sample, destination)
            else:
                shutil.move(str(sample), str(destination))


def verify_committed_samples(output, attempts):
    """A committed success must still match its bytes before resume can skip it."""
    for attempt in attempts:
        if attempt['status'] != 'collected_pending_review':
            continue
        receipt_path = Path(output) / 'evidence' / attempt['sample_id'] / 'saved_sample.json'
        evidence = attempt.get('evidence', [])
        if not receipt_path.is_file() or not any(
                row.get('path') == str(receipt_path.resolve()) and row.get('sha256') == sha(receipt_path)
                for row in evidence):
            raise ValueError('已完成样本缺少已提交的保存收据，停止续跑：' + attempt['sample_id'])
        receipt = read_json(receipt_path)
        from .postprocess import post_seal_name
        expected = {name: digest for name, digest in (receipt.get('sample_files_sha256') or {}).items()}
        actual = sample_hashes(Path(output) / 'samples' / attempt['sample_id'])
        if (receipt.get('attempt_id') != attempt['attempt_id'] or
                receipt.get('sample_id') != attempt['sample_id'] or not expected or actual != expected):
            raise ValueError('已完成样本缺失或证据改变，停止续跑：' + attempt['sample_id'])
        # Post-seal close-out receipts (append-only derivation ledger, attempt
        # feedback and every versioned appended receipt) never belong to the
        # frozen capture hash on either side.
        expected_raw = {name: digest for name, digest in (receipt.get('capture_files_sha256') or {}).items()
                        if not post_seal_name(name)}
        actual_raw = {name: digest for name, digest in sample_hashes(receipt_path.parent).items()
                      if not post_seal_name(name)}
        if not expected_raw or expected_raw != actual_raw:
            raise ValueError('已完成样本的原始采集证据改变，停止续跑：' + attempt['sample_id'])


async def heartbeat_lease(store, attempt, seconds):
    while True:
        await asyncio.to_thread(store.heartbeat, attempt['attempt_id'], attempt['worker_id'], attempt['lease_token'])
        await asyncio.sleep(max(0.1, seconds / 3))


def _evidence(path):
    return [{'path': str(Path(path).resolve()), 'sha256': sha(path)}]


def _root_cause(error):
    import re
    if isinstance(error, sqlite3.OperationalError):
        return type(error).__name__ + ': ' + str(error)
    if isinstance(error, NavigationTimeoutError):
        return 'navigation_timeout'
    match = re.search(r'net::ERR_[A-Z_]+', str(error))
    return match.group() if match else 'navigation_timeout' if 'Page.goto: Timeout' in str(error) else classify_failure(error)


def sync_manifest(store, output, manifest):
    from .collect import checkpoint_json, checkpoint_manifest
    snapshot = store.snapshot()
    if snapshot['scope']['state'] == 'closed_replanned':
        raise ValueError('scope已永久closed_replanned，禁止重写冻结manifest和runtime快照')
    ledger = store.attempt_ledger()
    records = []
    for row in ledger['attempts']:
        # Facts distinguish the actual execution denominator from reserved IDs.
        record = {key: row.get(key) for key in ('attempt_id', 'task_id', 'task_version',
            'sample_id', 'site_id', 'batch_id', 'retry_of', 'failure_class', 'root_cause')}
        record['started_at'] = datetime.fromtimestamp(row['started_at'], timezone.utc).isoformat()
        record['runtime_status'] = row['status']
        record['status'] = 'rejected' if row['status'] == 'interrupted' else row['status']
        if record['status'] == 'rejected':
            record['error'] = row['root_cause'] or row['failure_class'] or 'interrupted'
            failure = Path(output) / 'evidence' / row['sample_id'] / 'failure.json'
            if failure.is_file():
                record['error'] = read_json(failure).get('error') or record['error']
            record['failure_evidence'] = row.get('evidence', [])
        records.append(record)
    # Reconcile saved results on every resume before another allocation. Index and
    # shared-pool sync are idempotent projections of the original attempt ledger.
    from .current_chain import scope_for_registry, append_current_result, is_current_registry
    scope=scope_for_registry(store.registry) if is_current_registry(store.registry) else None
    if scope:
        for row in snapshot['attempts']:
            if row['status'] in ('collected_pending_review','reviewed_pass','published'):
                append_current_result(scope['manifest']['path'],
                    Path(output)/'samples'/row['sample_id']/'annotation.json',
                    site_uri=row['task']['site_uri'],task_key=row['task_key'])
    manifest['attempts'] = records
    manifest['reserved_attempts'] = [{key: row.get(key) for key in
        ('attempt_id', 'task_id', 'task_version', 'sample_id', 'site_id', 'batch_id',
         'retry_of', 'status', 'started_at', 'failure_class', 'root_cause')}
        for row in ledger['reserved_attempts']]
    manifest['samples'] = [row['sample_id'] for row in records if row['status'] == 'collected_pending_review']
    from .production_identity import allocation_uri
    from .react_protocol import VERSION as native_protocol
    if snapshot['attempts'] and all(row['task'].get('fragment',{}).get('decision_protocol') == native_protocol for row in snapshot['attempts']):
        manifest['classification_metadata_version'] = 'source-category-1'
    manifest['sites'] = list({row['site_id']: {'site_id': row['site_id'],
        'uri': allocation_uri(row['task']), 'site_category': row['task']['site_category']}
        for row in snapshot['attempts']}.values())
    batches = {row['batch_id'] for row in snapshot['attempts']}
    if len(batches) > 1:
        raise ValueError('同输出scope出现多个batch_id，停止运行并核账')
    manifest['batch_id'] = next(iter(batches), None)
    active = [row for row in snapshot['attempts'] if row['status'] in ('running', 'reserved')]
    manifest['active_task'] = [{key: row[key] for key in ('attempt_id', 'task_id', 'sample_id', 'status')}
                               for row in active]
    terminal = {'collected_pending_review', 'reviewed_pass', 'published', 'needs_replan'}
    finished = bool(snapshot['tasks']) and all(row['status'] in terminal for row in snapshot['tasks'])
    # A never-started task (e.g. expired capability) is not a completed production batch.
    attempted = {row['task_id'] for row in records}
    finished = finished and all(row['task_id'] in attempted for row in snapshot['tasks'])
    manifest['collection_status'] = 'finished_pending_review' if finished else 'paused_pending_resume'
    manifest['runtime_policy'] = snapshot['policy']
    manifest['actual_attempt_count'] = ledger['actual_attempt_count']
    manifest['reserved_allocation_count'] = ledger['reserved_allocation_count']
    checkpoint_json(Path(output) / 'runtime-snapshot.json', snapshot)
    checkpoint_manifest(output, manifest)
    return snapshot


async def _with_lease(job, store, attempt, lease_seconds):
    running = asyncio.create_task(job)
    heartbeat = asyncio.create_task(heartbeat_lease(store, attempt, lease_seconds))
    try:
        done, _ = await asyncio.wait((running, heartbeat), return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done and running not in done:
            # A lost lease fences further page actions, not just the final commit.
            from .runtime import OwnedAttemptClosed
            try:
                heartbeat.result()
            except OwnedAttemptClosed:
                # finish_attempt committed while its thread's return was still
                # pending. Only same-owner normal completion reaches this type;
                # expiry, recovery and owner changes still cancel the runner.
                # Remaining work is close-out; RuntimeStore still rejects every
                # attempt operation after terminal status.
                return await running
            raise ValueError('租约心跳意外结束')
        return await running
    finally:
        for task in (running, heartbeat):
            if not task.done():
                task.cancel()
        await asyncio.gather(running, heartbeat, return_exceptions=True)


def refresh_metadata(output):
    """Regenerate a derived index while preserving every previous version."""
    from .metadata import export_metadata
    import os
    output = Path(output)
    history = output / 'metadata-history'
    history.mkdir(exist_ok=True)
    current = output / 'metadata.csv'
    previous = None
    if current.exists():
        previous = sha(current)
        preserved = history / ('previous-' + previous + '.csv')
        if not preserved.exists():
            with preserved.open('xb') as stream:
                stream.write(current.read_bytes())
        elif sha(preserved) != previous:
            raise ValueError('已有metadata历史副本内容改变，停止更新')
    generated = history / (str(uuid.uuid4()) + '.csv')
    export_metadata(output, generated)
    staging = output / ('.metadata-' + str(uuid.uuid4()) + '.tmp')
    with staging.open('xb') as stream:
        stream.write(generated.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    staging.replace(current)
    return {'path': 'metadata.csv', 'sha256': sha(current), 'previous_sha256': previous,
            'generated_history': str(generated.relative_to(output))}


async def collect_m4(plan_path, output, registry, **options):
    """The lease protects tasks; an output lock protects derived files and snapshots."""
    import fcntl
    plan_path, registry = Path(plan_path), Path(registry)
    for key in ('publication_path','policy_path'):
        if options.get(key) is not None:
            options[key]=Path(options[key])
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / ('.' + runtime_scope(output) + '.lock')
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('本输出目录已有采集/恢复进程，拒绝第二runner并发写入') from error
        try:
            return await _collect_m4_locked(plan_path, output, registry, **options)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def close_scope_for_replan(output, registry, reason, evidence, *, now=None):
    """Use the same output lock as collection; never rewrite original files."""
    import fcntl
    from .runtime import RuntimeStore
    output = Path(output).resolve()
    if not output.is_dir():
        raise ValueError('关闭需要已有批次目录')
    lock_path = output.parent / ('.' + runtime_scope(output) + '.lock')
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('本输出目录仍有采集/恢复进程，禁止并发关闭') from error
        try:
            return RuntimeStore(registry, runtime_scope(output)).close_failed_scope(output, reason, evidence, now=now)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def react_close_event(store, attempt, kind, now, payload):
    """Record a react close-out event through the store's transaction API."""
    with store._transaction() as con:
        store._event(con, kind, now, payload,
                     task_key=attempt['task_key'], attempt_id=attempt['attempt_id'])


async def _react_collection(context, task, attempt, sample, evidence, output, store, *,
                            ledger, parent_job, registry, manifest, index, navigation=None,
                            page=None, entry_observation=None, host_limits=None, runlog=None):
    """One react session in one browser context; raw first, derivation offline.

    The attempt is always finished here once the raw journal is saved: derived
    delivery commits collected_pending_review; every other honest closure
    (no path, budget, length-unqualified, derivation failure) keeps the raw
    receipt in the attempt evidence and records its own failure class.
    """
    from .postprocess import process as postprocess_derivation
    from .collect import checkpoint_json, now, verify_public_url
    from .agent_feedback import save_attempt_feedback, site_context
    from .production_quality import require_public_task_state
    from .scaffold import program_version
    from .telemetry import phase as telemetry_phase
    from .collection_strategy import enabled as screenshot_strategy
    from .react_protocol import VERSION as NATIVE_REACT
    if screenshot_strategy(task):
        # 策略 2 显式选择：截图会话与专属chooser，不挂策略1 band/finish_when门禁。
        from .screenshot_session import ScreenshotPlanSession as Session
        from .screenshot_plan import screenshot_chooser as chooser_factory
    else:
        from .react_session import ReactSession as Session, react_chooser as chooser_factory
    if runlog is not None:
        runlog.attach(attemptId=attempt['attempt_id'], sampleId=attempt['sample_id'],
                      siteId=attempt.get('site_id'))
        runlog.banner(task['site_uri'])
        runlog.info('attempt_started', attemptId=attempt['attempt_id'])
    ids = {**{key: attempt[key] for key in ('sample_id', 'site_id', 'batch_id')},
           'attempt_id': attempt['attempt_id']}
    phase_ledger = Path(output) / 'metering' / 'phases.jsonl'
    meter_identity = {'attempt_id': attempt['attempt_id'], 'sample_id': attempt['sample_id']}
    entry_host = verify_public_url(task['initial_url'])
    allowed_hosts = {verify_public_url(task['site_uri']), entry_host, *task.get('allowed_hosts', [])}
    def url_check(url):
        if 'candidate_binding' in task:
            from .candidate_contract import same_application, guard_claim
            guard_claim(task)
            if not same_application(task, url):
                raise ValueError('Candidate navigation left the evidence-backed application')
        else:
            verify_public_url(url, allowed_hosts)
        require_public_task_state({'url': url})
    def frame_guard(ref):
        from .planning import verify_evidence
        verify_evidence([ref])
        conflicts = [row for row in store.exact_image_claims()
                     if row['digest'] == ref['sha256'] and row['sample_id'] != attempt['sample_id']]
        for row in conflicts:
            verify_evidence([{'path': row['path'], 'sha256': row['digest']}])
        return conflicts
    async def preflight(page, directory):
        if entry_observation is None:
            ledger.consume('probe_pages', (parent_job or {'id': 'collection'})['id'] + ':react-preflight', 1)
        from .preflight import inspect_page
        return await inspect_page(page, task, directory, samples=2, interval_ms=100, url_check=url_check)
    feedback_context = await asyncio.to_thread(site_context, registry, task['site_uri'], model_ledger=ledger,
        candidate_id=(task.get('candidate_binding') or {}).get('candidate_id'))
    if not closing_enabled(task) and feedback_context['unresolved']:
        if any(row.get('attempt_id') != attempt['attempt_id'] for row in feedback_context['unresolved']):
            raise CollectionFailure('Unresolved prior attempt blocks react dispatch', 'program')
    if not screenshot_strategy(task):
        # Band budgets belong to 策略 1's conditional-plan chain only; the
        # strategy-2 path never loads the 策略 1 controller module.
        from .banded_plan import enabled as banded_plan_enabled
        if banded_plan_enabled(task):
            from .band_budget import reserve as reserve_plan_band
            feedback_context['band_budget'] = reserve_plan_band(registry, task, attempt)
    chooser = chooser_factory(ledger, task, attempt['attempt_id'], parent_job=parent_job,
                              **({'runlog': runlog} if screenshot_strategy(task) else {}))
    if page is None:
        page = await context.new_page()
    page.set_default_timeout(15000)
    session = Session(task, evidence / 'raw', chooser, page, steps_directory=evidence,
        navigation=navigation, url_check=url_check, preflight=preflight,
        frame_guard=frame_guard, site_context=feedback_context, attempt_id=attempt['attempt_id'],
        phase_ledger=phase_ledger, host_limits=host_limits,
        **({'entry_observation': entry_observation} if entry_observation is not None else {}),
        **({'runlog': runlog} if screenshot_strategy(task) else {}))
    with telemetry_phase(phase_ledger, 'react_session_run', scope=meter_identity):
        summary = await session.run()
    raw_receipt = summary['raw_receipt']
    stop_data = {'stop_details': summary['stop_details']} if 'stop_details' in summary else {}
    def _event_now():
        return datetime.now(timezone.utc).isoformat()
    async def finish_failure(failure_class, root_cause, extra_evidence=(),
                            strategy_save_status='not_saved', strategy_eligibility=None):
        if strategy_eligibility is None:
            strategy_eligibility = ('unresolved' if not screenshot_strategy(task) or summary.get('unknown')
                                    else 'ineligible')
        failure = evidence / 'failure.json'
        if not failure.exists():
            write_json(failure, {'error': root_cause, 'timestamp': now(),
                'attempt_id': attempt['attempt_id'], 'task_id': attempt['task_id'],
                'failure_class': failure_class, 'raw_saved': True,
                'stop_reason': summary['stop_reason'], **stop_data})
        # The feedback receipt globs/copies step files; keep it off the event
        # loop so the two heartbeat layers keep renewing during close-out.
        settlement_error = None
        try:
            with telemetry_phase(phase_ledger, 'attempt_feedback', scope=meter_identity):
                feedback_ref = await asyncio.to_thread(save_attempt_feedback, evidence, attempt,
                                                       'rejected', root_cause)
            await asyncio.to_thread(store.finish_attempt,attempt['attempt_id'], attempt['worker_id'], attempt['lease_token'],
                'rejected', failure_class=failure_class, root_cause=root_cause,
                evidence=_evidence(failure) + [feedback_ref, raw_receipt, *extra_evidence])
        except Exception as error:
            if not screenshot_strategy(task):
                raise
            # Preserve the failed settlement separately; never claim the ledger
            # is rejected when its transaction did not succeed.
            settlement_error = {'error_type': type(error).__name__, 'error': str(error)}
            write_json(evidence / 'settlement-failed.json', settlement_error)
        if failure_class == 'program' and not closing_enabled(task):
            store.set_scope_paused(True,
                'React derivation program failure; raw execution preserved and dispatch stopped')
        final_result = None
        if summary.get('strategy_result'):
            # The session-stage end facts were transient (unresolved / not_saved).
            # This closure is a decision not to save, so the actual outcome facts
            # are finalized here; explicit rejections are ineligible, a failed save
            # action is save_failed, and unknown/pending outcomes stay unresolved.
            from . import collection_strategy as _cs
            final_result = _cs.finalize_strategy_result(
                summary['strategy_result'], save_status=strategy_save_status,
                eligibility=strategy_eligibility)
        if final_result is not None and screenshot_strategy(task):
            write_json(evidence / 'strategy-result.json', {'strategy_result': final_result,
                'runtime_settled': settlement_error is None, 'settlement_error': settlement_error})
        if runlog is not None:
            runlog.info('save_failed' if strategy_save_status == 'save_failed' else 'failed',
                failureClass=failure_class, rootCause=str(root_cause)[:200],
                saveStatus=strategy_save_status, stopReason=summary['stop_reason'],
                unknown=bool(summary.get('unknown')),
                effectiveSteps=summary.get('effective_steps'))
        return {'status': 'settlement_failed' if settlement_error else 'rejected', 'failure_class': failure_class,
                **({'settlement_error': settlement_error} if settlement_error else {}),
                'stop_reason': summary['stop_reason'], 'raw_receipt': raw_receipt,
                **({'strategy_result': final_result} if final_result else {}),
                **stop_data}
    ending=summary.get('collection_ending')
    prefix_end=None
    verified_session=None
    from .plan_protocol import TRUSTED_PREFIX_POLICY
    from .trusted_prefix import candidate_end, project_prefix
    prefix_rule=task['fragment'].get('trusted_prefix_protocol')
    ready_with_missing_checks=False
    prefix_requested=(prefix_rule == TRUSTED_PREFIX_POLICY and
        (summary['unknown'] or summary.get('host_failure') or ready_with_missing_checks or
         (ending and ending.get('flagged')) or summary.get('stop_reason') in ('blocked','no_path','budget')))
    if prefix_requested:
        try:
            from .postprocess import _VerifiedSession
            # Build once and retain the sealed-source verification through this
            # close-out; file digests are checked again before reuse and saving.
            with telemetry_phase(phase_ledger, 'prefix_projection', scope=meter_identity):
                verified_session=await asyncio.to_thread(_VerifiedSession, evidence/'raw')
                prefix_end=await asyncio.to_thread(candidate_end, evidence/'raw', rule=prefix_rule,
                                                   _verified=verified_session)
                if prefix_end is not None:
                    source=await asyncio.to_thread(verified_session.record, evidence/'raw')
                    await asyncio.to_thread(project_prefix, source, evidence/'raw', prefix_end, ids,
                                            rule=prefix_rule, _verified=verified_session)
                    write_json(evidence/'prefix-source-closeout.json',{'protocol':prefix_rule,
                        'attempt_id':attempt['attempt_id'],'raw_receipt':raw_receipt,
                        'original_stop_reason':summary['stop_reason'],'original_unknown':summary['unknown'],
                        'original_failure_class':summary['failure_class'],
                        'original_host_failure':summary.get('host_failure'),
                        'original_collection_ending':ending,'original_goal_completed':False,
                        'ready_with_unverified_required_checks':ready_with_missing_checks,
                        'original_request_ledger_unchanged':True})
        except (ValueError,KeyError,TypeError,OSError) as prefix_error:
            prefix_end=None
            write_json(evidence/'prefix-ineligible.json',{'protocol':prefix_rule,
                'error':str(prefix_error),'raw_receipt':raw_receipt,'normal_sample_saved':False})
    from .screenshot_plan import RAW_ONLY_ENDINGS
    if ending and ending.get('kind') in RAW_ONLY_ENDINGS and prefix_end is None:
        # 策略 2 的 give_up/unsuitable/no_progress 只留原始记录，不进入正式派生。
        receipt=evidence/'screenshot-raw-only.json'
        write_json(receipt,{'schema_version':'screenshot-raw-only',
            'attempt_id':attempt['attempt_id'],'collection_ending':ending,'raw_receipt':raw_receipt,
            'saved_raw':True,'normal_sample_saved':False,'QC_status':'NOT_RUN'})
        return await finish_failure('collector','react_screenshot_raw_only:'+str(ending.get('kind'))
                                    +':'+str(ending.get('reason')),_evidence(receipt))
    if ending and not ending.get('safe_for_pending_sample') and prefix_end is None:
        pending=evidence/'raw-ending-pending.json'
        write_json(pending,{'schema_version':'raw-ending-pending',
            'attempt_id':attempt['attempt_id'],'collection_ending':ending,'raw_receipt':raw_receipt,
            'saved_raw':True,'normal_sample_saved':False,'requires_reconciliation':True,'QC_status':'NOT_RUN'})
        result=await finish_failure(summary.get('failure_class')
                                    or ('interrupted' if summary['unknown'] else 'collector'),
            'react_raw_ending_pending:'+ending['reason'],_evidence(pending),
            strategy_eligibility='unresolved')
        return {**result,'raw_preservation_status':'saved_pending_reconciliation','collection_ending':ending,
                'pending_receipt':str(pending),'QC_status':'NOT_RUN'}
    if (summary['unknown'] or summary['failure_class'] == 'interrupted') and prefix_end is None:
        react_close_event(store, attempt, 'react_raw_unknown', _event_now(),
            {'stop_reason': summary['stop_reason'], 'raw_receipt': raw_receipt, 'unknown': True})
        return await finish_failure('interrupted',
                              'react_unknown:' + str(summary['stop_summary'] or summary['stop_reason']))
    if summary.get('host_failure') and prefix_end is None:
        react_close_event(store, attempt, 'react_raw_rejected', _event_now(),
            {'stop_reason':summary['stop_reason'],'raw_receipt':raw_receipt,'primary_failure':summary['stop_summary']})
        return await finish_failure(summary['failure_class'], 'react_' + str(summary['stop_summary'] or summary['stop_reason']))
    def audit_validator(delivery_root):
        from .evidence import audit_capture
        audited = audit_capture(output, attempt['sample_id'])
        write_json(evidence / 'capture_audit.json', audited)
        if not audited['capture_evidence_pass']:
            return ['capture_audit: ' + str(audited['issues'])[:400]]
        return []
    def dedup_validator(delivery_root):
        conflicts = index.conflicts(delivery_root)
        from .candidate_contract import research_duplicate_basis, research_overlap_sample_ids
        research = research_duplicate_basis(task, store.registry)
        overlaps = research_overlap_sample_ids(research)
        blocked = [item for item in conflicts if Path(item['other_sample']).name not in overlaps]
        write_json(evidence / 'producer_dedup.json', {'exact_conflicts': conflicts,
            'research_original_overlap': research, 'blocking_conflicts': blocked,
            'other_routes': 'independent_QC_required', 'not_qualified': True})
        return ['producer_exact_dedup: ' + str(blocked)[:400]] if blocked else []
    # The structural check validates a runtime-manifest shape: inherit the
    # real manifest (schema_version pins rule_version=m4-1) with this sample.
    delivery_manifest = {**manifest, 'samples': list(manifest.get('samples') or []) + [ids['sample_id']]}
    # The full derivation (raw record rebuild, effective-trajectory recount,
    # capture audit, dedup and file hashing) is offline work on this attempt's
    # own files; it runs in a bounded worker thread. Runtime commits, the exact
    # index registration and ledger transactions keep their original loop-side
    # boundaries below.
    try:
        with telemetry_phase(phase_ledger, 'react_postprocess', scope=meter_identity):
            derived = await asyncio.to_thread(postprocess_derivation, evidence, sample, ids,
                                              delivery_manifest,
                                              validators=(audit_validator, dedup_validator),
                                              prefix_end_step=prefix_end, prefix_rule=prefix_rule,
                                              _verified=verified_session)
    except Exception as error:
        if not screenshot_strategy(task):
            raise
        return await finish_failure('program', 'derivation_failed:' + str(error)[:300],
            strategy_save_status='save_failed', strategy_eligibility='unresolved')
    react_close_event(store, attempt, 'react_raw_saved', _event_now(),
        {'stop_reason': summary['stop_reason'], 'effective_steps': summary['effective_steps'],
         'derivation_status': derived['status'], 'raw_receipt': raw_receipt, **stop_data})
    if runlog is not None:
        runlog.info('raw_sealed', derivationStatus=derived['status'],
            effectiveSteps=summary['effective_steps'], stopReason=summary['stop_reason'])
    if derived['status'] != 'derived_saved':
        if runlog is not None and derived['status'] == 'processing_failed':
            runlog.info('derivation_failed', errorCode=derived.get('error'),
                stepId=derived.get('step_id'), operationId=derived.get('operation_id'),
                recordRef=derived.get('record_ref'))
        errors = derived.get('errors') or []
        if (task['fragment'].get('decision_protocol') == NATIVE_REACT and derived['status'] == 'delivery_rejected'
                and errors and all(error.startswith('producer_exact_dedup:') for error in errors)):
            return await finish_failure('collector', 'react_exact_image_conflict',
                                  _evidence(evidence / 'producer_dedup.json') + [derived['record_ref']],
                                  strategy_eligibility='ineligible')
        if derived['status'] in ('processing_failed', 'delivery_rejected'):
            # A program failure of the derivation/save action is an actual
            # save failure; an explicit delivery rejection is not saved and
            # ineligible.
            return await finish_failure('program', 'derivation_' + derived['status'] + ': ' +
                                  str(derived.get('error') or derived.get('errors') or '')[:240] +
                                  ('; step_id=' + str(derived['step_id']) if 'step_id' in derived else '') +
                                  ('; operation_id=' + str(derived['operation_id']) if 'operation_id' in derived else ''),
                                  strategy_save_status=('save_failed' if derived['status'] == 'processing_failed' else 'not_saved'),
                                  strategy_eligibility=(derived.get('save_eligibility', 'unresolved')
                                      if screenshot_strategy(task) and derived['status'] == 'processing_failed'
                                      else 'ineligible'))
        cause = summary['stop_details']['code'] if stop_data else 'react_' + derived['status']
        return await finish_failure('collector', cause)
    saved = evidence / 'saved_sample.json'
    from .closing_policy import completion_delivery_decision
    if task['fragment'].get('decision_protocol') == NATIVE_REACT:
        completion_decision = completion_delivery_decision(
            read_json(sample/'annotation.json'), read_json(saved)['raw_execution'])
        if not completion_decision['delivery_eligible']:
            return await finish_failure('collector', 'react_completion_delivery_ineligible',
                                  strategy_eligibility='ineligible')
    try:
        with telemetry_phase(phase_ledger, 'react_commit', scope=meter_identity):
            with telemetry_phase(phase_ledger, 'attempt_feedback', scope=meter_identity):
                feedback_ref = await asyncio.to_thread(save_attempt_feedback, evidence, attempt,
                                                       'collected_pending_review')
            derived_ref = {'path': str((evidence / 'derived.json').resolve()),
                           'sha256': sha(evidence / 'derived.json')}
            from .runtime import ImageCommitConflict
            try:
                await asyncio.to_thread(store.finish_attempt,attempt['attempt_id'], attempt['worker_id'], attempt['lease_token'],
                    'collected_pending_review',
                    evidence=_evidence(saved) + [feedback_ref, raw_receipt, derived_ref],
                    exact_images=index.sample_images(sample))
            except ImageCommitConflict as conflict:
                if task['fragment'].get('decision_protocol') != NATIVE_REACT:
                    raise
                collision = evidence / 'concurrent_image_conflict.json'
                write_json(collision, {'exact_conflicts': conflict.conflicts})
                return await finish_failure('collector', 'react_exact_image_commit_conflict',
                                      _evidence(collision) + [derived_ref],
                                      strategy_save_status='save_failed', strategy_eligibility='ineligible')
            index.add_sample(sample)
    except Exception as error:
        if not screenshot_strategy(task):
            raise
        # A secondary index may fail after SQLite committed. The actual ledger
        # receipt owns save status; never turn that committed save into rejection.
        try:
            runtime_row = next(row for row in store.snapshot()['attempts']
                               if row['attempt_id'] == attempt['attempt_id'])
        except Exception as lookup_error:
            write_json(evidence / 'commit-outcome-unresolved.json', {
                'error': str(error), 'lookup_error': str(lookup_error),
                'requires_reconciliation': True})
            if summary.get('strategy_result'):
                from .collection_strategy import finalize_strategy_result
                unresolved = finalize_strategy_result(summary['strategy_result'],
                    save_status='unresolved', eligibility='eligible',
                    details={'runtime_commit': 'unresolved', 'requires_reconciliation': True})
                write_json(evidence / 'strategy-result.json', {'strategy_result': unresolved,
                    'runtime_settled': False})
                return {'status': 'settlement_failed', 'strategy_result': unresolved,
                        'raw_receipt': raw_receipt, 'requires_reconciliation': True}
            raise
        if runtime_row['status'] != 'collected_pending_review':
            return await finish_failure('program', 'runtime_commit_failed:' + str(error)[:300],
                strategy_save_status='save_failed', strategy_eligibility='eligible')
        write_json(evidence / 'secondary-index-failed.json', {'error': str(error),
            'runtime_status': runtime_row['status'], 'requires_index_reconciliation': True})
    if runlog is not None:
        # success仅在正式保存提交（store.finish_attempt + 索引登记）完成后输出。
        runlog.info('success', saveStatus='collected_pending_review',
            effectiveSteps=derived['effective_steps'], stopReason=summary['stop_reason'])
    from .closing_policy import completion_delivery_decision
    from . import collection_strategy as _cs
    completion_decision = completion_delivery_decision(read_json(sample/'annotation.json'), read_json(saved)['raw_execution'])
    final_result = None
    if summary.get('strategy_result'):
        # The session-stage end facts were transient (unresolved / not_saved);
        # the committed outcome and the eligibility decision are authoritative.
        final_result = _cs.finalize_strategy_result(
            summary['strategy_result'], save_status='collected_pending_review',
            eligibility=('eligible' if completion_decision['delivery_eligible'] else 'ineligible'),
            details={'effective_steps': derived['effective_steps'],
                     'completion_status': completion_decision['completion_status'],
                     'delivery_policy': completion_decision['delivery_policy']})
    if final_result is not None and screenshot_strategy(task):
        write_json(evidence / 'strategy-result.json', {'strategy_result': final_result, 'runtime_settled': True})
    return {'status': 'collected_pending_review', 'effective_steps': derived['effective_steps'],
            'completion_delivery':completion_decision,
            'original_goal_completed':completion_decision['original_goal_completed'],
            **({'collection_ending':ending} if ending else {}),
            **({'trusted_prefix':derived['trusted_prefix'],'original_goal_completed':False} if derived.get('trusted_prefix') else {}),
            'short_flow': derived.get('short_flow'), 'stop_reason': summary['stop_reason'],
            **({'strategy_result': final_result} if final_result else {}),
            'raw_receipt': raw_receipt, 'saved_sample': str(saved.resolve()), **stop_data}


@asynccontextmanager
async def _collection_browser(channel, headless, entry_session):
    if entry_session is not None:
        yield entry_session['browser']
        return  # The candidate consumer owns and closes its context/browser.
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=channel, headless=headless)
        try:
            yield browser
        finally:
            await asyncio.wait_for(browser.close(), timeout=10)


async def _collect_m4_locked(plan_path, output, registry, *, publication_path=None,
                     policy_path=None, resume=False, channel='chrome', headless=True, navigation=None, site_pool=None, controller_ledger=None, controller_parent_job=None, entry_session=None, runlog=None, log_level='INFO', log_dir=None):
    from importlib.metadata import version
    from .collect import collect_one, validate_plan, checkpoint_json, checkpoint_manifest, now
    from .planning import verify_publication, object_sha256
    from .runtime import RuntimeStore, continuous_task
    from .scaffold import program_version
    from .evidence import audit_capture
    from .telemetry import NetworkMeter, phase, worker_measurement

    from .telemetry import preparation_phase
    from .task_admission import frame_validation_scope
    timing = Path(output).parent / "preparation-timings.jsonl"
    startup_frames = {}
    if runlog is None:
        # 无claim直接执行的策略2计划：会话开始时生成一次展示sessionId。
        # 策略1计划不接线，保持原有行为。
        from .collection_strategy import strategy_id, STRATEGY_SCREENSHOT_PLAN
        if any(strategy_id(task) == STRATEGY_SCREENSHOT_PLAN for task in read_json(plan_path)['tasks']):
            from .runlog import for_direct_run
            runlog = for_direct_run(output, strategy=STRATEGY_SCREENSHOT_PLAN, level=log_level, log_dir=log_dir)
    with frame_validation_scope(startup_frames), preparation_phase(timing, "runtime_validate"):
        plan = read_json(plan_path)
        continuous = bool(plan.get('tasks')) and all(continuous_task(task) for task in plan['tasks'])
        history = plan.get('generation', {}).get('history_scope') or plan.get('observed_workflow_generation', {}).get('history_scope') or {}
        if history.get('candidate_project'):
            from .current_chain import assert_current_result_path
            assert_current_result_path(history, Path(output).resolve())
        validate_plan(plan)
        if entry_session is not None:
            from .candidate_contract import guard_claim
            from .session_core import is_react_task
            if len(plan['tasks']) != 1 or not is_react_task(plan['tasks'][0]):
                raise ValueError('Candidate entry session requires exactly one ReAct task')
            guard_claim(plan['tasks'][0])
            if plan['tasks'][0]['candidate_binding']['claim_id'] != entry_session['claim_id']:
                raise ValueError('Entry page belongs to another candidate claim')
        from .agent_controller import verify_ledger_binding
        verify_ledger_binding(plan, controller_ledger)
        from .batch_protocol import verify_plan_shard, verify_shard_policy
        verify_plan_shard(plan, registry)  # Read-only ownership check before any dispatch side effect.
        if publication_path is None:
            raise ValueError('M4采集必须提供 --publication；先发布已预检的计划')
        publication = read_json(publication_path)
        verify_publication(plan, publication)
        if not resume and policy_path is None:
            raise ValueError('首次M4采集必须提供 --policy，明确累计基线类目计数与本波预算；不能默认忽略旧样本')
        output, registry = Path(output).resolve(), Path(registry).resolve()
        # New ordinary plans collect once without any prior workflow execution.
        # Explicit legacy evidence bindings still need their original validator;
        # an observation trace alone never becomes a saved production sample.
        if any('task_admission' in task for task in plan['tasks']):
            from .task_admission import verify_collection_entry
            verify_collection_entry(plan, registry, output)
        if any('observed_workflow' in task or 'workflow_admission' in task
               or task.get('task_family') == 'observed-workflow' for task in plan['tasks']):
            from .observed_workflow import verify_entry as verify_workflow_entry
            verify_workflow_entry(plan, registry, output)
        scope = runtime_scope(output)
        store = RuntimeStore(registry, scope)
        if resume:
            import sqlite3
            try:
                prior_scope = store.snapshot()['scope']['state']
            except (ValueError, sqlite3.OperationalError) as error:
                if str(error) != '运行范围尚未初始化' and 'no such table: m4_scopes' not in str(error):
                    raise
                prior_scope = None
            if prior_scope == 'closed_replanned':
                raise ValueError('scope已永久closed_replanned；新任务版本必须使用新输出范围')
    with frame_validation_scope(startup_frames), preparation_phase(timing, "runtime_bootstrap"):
        sources = source_identity()
        bootstrap_path = output / 'bootstrap.json'
        if resume and bootstrap_path.exists():
            bootstrap = read_json(bootstrap_path)
            if (bootstrap.get('plan') != plan or bootstrap.get('publication') != publication
                    or bootstrap.get('registry_path') != str(registry)
                    or bootstrap.get('output_path') != str(output)
                    or bootstrap.get('manifest', {}).get('contract_profile') != contract_identity(Path(__file__).resolve().parents[3])):
                raise ValueError('续跑bootstrap绑定发生变化，拒绝更换输入或程序')
            from .runtime import validate_policy
            from sqlite3 import OperationalError
            try:
                snapshot = store.snapshot()
            except (ValueError, OperationalError) as error:
                if str(error) != '运行范围尚未初始化' and 'no such table: m4_scopes' not in str(error):
                    raise
                verify_existing_registry(registry, output.parent)
                verify_shard_policy(registry, validate_policy(bootstrap['policy']))
                store.initialize(bootstrap['policy'])
                snapshot = store.snapshot()
            verify_shard_policy(registry, snapshot['policy'])
            if policy_path and validate_policy(read_json(policy_path)) != snapshot['policy']:
                raise ValueError('续跑不能静默替换预算，请显式记录预算调整原因')
            original_pool = bootstrap.get('site_pool')
            if site_pool is not None and str(Path(site_pool).resolve()) != original_pool:
                raise ValueError('Resume cannot replace the frozen shared pool')
            if original_pool:
                store.bind_site_pool(original_pool)
            store.enqueue_plan(plan, publication)
            binding = store.plan_binding()
            if binding['plan'] != plan or binding['publication'] != publication:
                raise ValueError('数据库冻结计划与bootstrap不一致')
            missing = [name for name in ('plan.json', 'publication.json', 'manifest.json') if not (output / name).is_file()]
            if missing and snapshot['attempts']:
                raise ValueError('已有attempt但初始化文件缺失，必须保留现场核账，不能重建程序身份')
            if missing and any((output / name).exists() for name in ('samples', 'evidence', 'rejected')):
                raise ValueError('初始化不完整且存在未知样本文件，停止自动恢复')
            for name, value in (('plan.json', plan), ('publication.json', publication)):
                path = output / name
                if path.exists():
                    if read_json(path) != value:
                        raise ValueError('续跑冻结文件发生变化：' + name)
                else:
                    write_json(path, value)
            manifest = read_json(output / 'manifest.json') if 'manifest.json' not in missing else bootstrap['manifest']
            if (manifest.get('runtime_scope_id') != scope or manifest.get('registry_path') != str(registry)
                    or manifest.get('generator_files_sha256') != sources
                    or manifest.get('contract_profile') != contract_identity(Path(__file__).resolve().parents[3])
                    or manifest.get('configuration', {}).get('channel') != channel
                    or manifest.get('configuration', {}).get('headless') != headless):
                raise ValueError('续跑输出、账本或代码版本不匹配；不能拼接新版本')
            if missing:
                checkpoint_manifest(output, manifest)
                recovery = output / 'bootstrap-recovery' / (str(uuid.uuid4()) + '.json')
                recovery.parent.mkdir(exist_ok=True)
                write_json(recovery, {'restored_files': missing, 'attempts_before_recovery': 0,
                    'files_sha256': {name: sha(output / name) for name in ('plan.json', 'publication.json', 'manifest.json')}})
                store.record_bootstrap_recovery(plan, publication,
                    _evidence(bootstrap_path) + _evidence(recovery),
                    'Restore frozen initialization files with no attempt: ' + ', '.join(missing))
        else:
            # An empty directory is the only state allowed before the durable bootstrap.
            if output.exists() and not (resume and output.is_dir() and not any(output.iterdir())):
                raise FileExistsError('输出已存在且缺少可验证bootstrap；保留现场，不能覆盖')
            if policy_path is None:
                raise ValueError('未完成初始化的空目录恢复需要原 --policy，不能猜测预算')
            verify_existing_registry(registry, output.parent)
            from .runtime import validate_policy
            supplied_policy = read_json(policy_path)
            if 'baseline_category_counts' not in supplied_policy:
                raise ValueError('M4预算必须显式声明baseline_category_counts；旧基线尚未确认时不能开始采集')
            policy = validate_policy(supplied_policy)
            verify_shard_policy(registry, policy)
            manifest = {'schema_version': 'runtime-manifest',
                'runtime_scope_id': scope, 'registry_path': str(registry),
                'contract_profile': contract_identity(Path(__file__).resolve().parents[3]),
                'plan_sha256': sha(plan_path), 'plan_object_sha256': object_sha256(plan),
                'preparation_policy': 'content-preparation-v1', 'generator_files_sha256': sources,
                'batch_id': None, 'sample_kind': 'real', 'program_version': program_version(),
                'rule_version': 'm4-1', 'configuration': {'viewport': [1280, 720],
                    'device_scale_factor': 1, 'locale': 'zh-CN', 'timezone': 'Asia/Shanghai',
                    'channel': channel, 'headless': headless, 'default_settle_ms': 500,
                    'task_interval_seconds': policy['task_interval_seconds']},
                'sites': [], 'samples': [], 'collection_status': 'in_progress',
                'producer_index_status': 'PENDING',
                'human_review': 'pending', 'created_at': now()}
            if not output.exists():
                output.mkdir(parents=True)
            checkpoint_json(bootstrap_path, {'schema_version': 'runtime-bootstrap',
                'plan': plan, 'publication': publication, 'policy': policy, 'manifest': manifest,
                'source_files_sha256': sources, 'registry_path': str(registry), 'output_path': str(output),
                **({'site_pool': str(Path(site_pool).resolve())} if site_pool is not None else {})})
            # Save a recoverable initialization record before touching persistent queue state.
            write_json(output / 'plan.json', plan)
            write_json(output / 'publication.json', publication)
            checkpoint_manifest(output, manifest)
            store.initialize(policy)
            if site_pool is not None:
                store.bind_site_pool(site_pool)
            store.enqueue_plan(plan, publication)
    del startup_frames
    with preparation_phase(timing, "runtime_recovery_snapshot"):
        # Reap this scope's expired leases plus any other dead-scope attempt of
        # the same campaign: an expired lease can never be resumed by its owner
        # (lease fencing), and without a campaign-wide reap a crashed close-out in
        # an abandoned scope would block its whole site as an unresolved attempt
        # with no remaining reaper (real-run v13/v14 fact).
        store.recover_expired(campaign_wide=True)
        attempts = store.attempt_ledger()['attempts']
        verify_committed_samples(output, attempts)
        quarantine_interrupted(output, attempts)
        snapshot = sync_manifest(store, output, manifest)
    with preparation_phase(timing, "exact_index_initialize"):
        roots = [output.parent, *[Path(path) for path in plan.get('dedup_roots', [])]]
        index = ConcurrentExactImageIndex(roots, store)
    worker_id = 'serial-' + str(uuid.uuid4())
    phase_ledger = output / 'metering' / 'phases.jsonl'
    stopping_checkpoint = None
    async with worker_measurement(store, worker_id, output), _collection_browser(channel, headless, entry_session) as browser:
        manifest.update(browser_version=browser.version, playwright_version=version('playwright'))
        try:
            while True:
                verify_publication(plan, publication)
                checkpoint = store.resource_checkpoint(output)
                if checkpoint['status'] == 'STOP':
                    manifest['resource_stop'] = checkpoint
                    stopping_checkpoint = checkpoint
                    break
                attempt = store.claim_next(worker_id, request_id=str(uuid.uuid4()),
                    plan_sha256=publication['plan_sha256'], batch_id=manifest['batch_id'])
                if attempt is None:
                    latest = store.snapshot()
                    active = any(row['status'] in ('running', 'reserved') for row in latest['tasks'])
                    if (latest['scope']['state'] == 'active' and not active
                            and any(row['status'] == 'queued' for row in latest['tasks'])):
                        # Briefly accommodate a scheduler/domain backoff.
                        await asyncio.sleep(1)
                        continue
                    break
                async def prepare_attempt():
                    # A reservation already owns a lease. Keep renewing while
                    # history/manifest preparation runs outside the event loop.
                    prepared_snapshot = await asyncio.to_thread(sync_manifest, store, output, manifest)
                    started = await asyncio.to_thread(store.start_attempt, attempt['attempt_id'],
                                                     worker_id, attempt['lease_token'])
                    return prepared_snapshot, started
                snapshot, attempt = await _with_lease(prepare_attempt(), store, attempt,
                                                      snapshot['policy']['lease_seconds'])
                if entry_session is not None:
                    entry_session['bind_attempt'](attempt)
                sample = output / 'samples' / attempt['sample_id']
                evidence = output / 'evidence' / attempt['sample_id']
                context = None
                meter = None
                meter_identity = {key: attempt[key] for key in ('attempt_id', 'task_id', 'task_version', 'sample_id')}
                async def execute_and_finish():
                    nonlocal context, meter
                    try:
                        context = (entry_session['context'] if entry_session is not None else
                            await browser.new_context(viewport={'width': 1280, 'height': 720},
                                device_scale_factor=1, locale='zh-CN', timezone_id='Asia/Shanghai'))
                        meter = NetworkMeter(context, output / 'metering' / attempt['attempt_id'], meter_identity)
                        ids = {key: attempt[key] for key in ('sample_id', 'site_id', 'batch_id')}
                        task = {**attempt['task'], '_plan_schema_version': plan['schema_version'],
                                'require_public_origin': True}
                        from .session_core import is_react_task
                        if is_react_task(task):
                            if controller_ledger is None:
                                raise ValueError('React session requires its original BatchLedger')
                            react_result = await _react_collection(context, task, attempt, sample, evidence, output,
                                store, ledger=controller_ledger, parent_job=controller_parent_job,
                                registry=registry, manifest=manifest, index=index,
                                navigation=navigation, runlog=runlog,
                                **({'page': entry_session['page'], 'entry_observation': entry_session['entry_observation'],
                                    'host_limits': entry_session.get('host_limits')}
                                   if entry_session is not None else {}))
                            if react_result['status'] == 'collected_pending_review':
                                meter.ensure_recorded()
                        else:
                            from .agent_controller import is_controlled, FragmentController, model_chooser
                            controller_options = {}
                            if is_controlled(task):
                                if controller_ledger is None:
                                    raise ValueError('Dynamic controller requires original BatchLedger')
                                from .agent_feedback import site_context
                                planning_context = plan.get('generation',{}).get('site_planning_context') or {}
                                feedback_context = await asyncio.to_thread(site_context, registry, task['site_uri'], model_ledger=controller_ledger,
                                    candidate_id=(task.get('candidate_binding') or {}).get('candidate_id'),
                                    generation=planning_context.get('history',[]),
                                    quality=[q['reference'] for q in planning_context.get('quality_feedback',[])])
                                if not continuous_task(task) and feedback_context['unresolved']:
                                    # Exclude only this already claimed attempt.
                                    if any(r.get('attempt_id') != attempt['attempt_id'] for r in feedback_context['unresolved']):
                                        raise CollectionFailure('Unresolved prior attempt blocks dynamic dispatch', 'program')
                                def frame_guard(ref):
                                    from .planning import verify_evidence
                                    verify_evidence([ref])
                                    conflicts = [row for row in store.exact_image_claims()
                                            if row['digest'] == ref['sha256'] and row['sample_id'] != attempt['sample_id']]
                                    for row in conflicts:
                                        verify_evidence([{'path':row['path'],'sha256':row['digest']}])
                                    return conflicts
                                def controller_factory(bound_task, directory):
                                    return FragmentController(bound_task, directory,
                                        model_chooser(controller_ledger, bound_task, attempt['attempt_id'],parent_job=controller_parent_job),
                                        frame_guard=frame_guard, site_context=feedback_context)
                                controller_options['controller_factory'] = controller_factory
                            with phase(phase_ledger, 'browser_collection', scope=meter_identity):
                                await collect_one(context, task, sample, evidence, ids,
                                    **({'navigation': navigation} if navigation is not None else {}), **controller_options)
                            with phase(phase_ledger, 'structural_check', scope=meter_identity):
                                report = await asyncio.to_thread(validate_sample, sample, 'delivery', {**manifest,
                                    'samples': manifest['samples'] + [attempt['sample_id']]})
                            write_json(evidence / 'structural_report.json', report)
                            if not report['structural_pass']:
                                raise CollectionFailure('结构检查不通过：' + str(report['issues']), 'program')
                            with phase(phase_ledger, 'capture_audit', scope=meter_identity):
                                audited = await asyncio.to_thread(audit_capture, output, attempt['sample_id'])
                            write_json(evidence / 'capture_audit.json', audited)
                            if not audited['capture_evidence_pass']:
                                raise CollectionFailure('采集证据核对不通过：' + str(audited['issues']), 'program')
                            with phase(phase_ledger, 'producer_exact_dedup', scope=meter_identity):
                                conflicts = await asyncio.to_thread(index.conflicts, sample)
                            write_json(evidence / 'producer_dedup.json', {'exact_conflicts': conflicts,
                                'other_routes': 'independent_QC_required', 'not_qualified': True})
                            if conflicts:
                                raise CollectionFailure('跨样本截图重复，需重新规划：' + str(conflicts), 'duplicate')
                            meter.ensure_recorded()
                            from .agent_feedback import save_attempt_feedback
                            feedback_ref = save_attempt_feedback(evidence, attempt, 'collected_pending_review')
                            saved = evidence / 'saved_sample.json'
                            write_json(saved, {'attempt_id': attempt['attempt_id'], 'sample_id': attempt['sample_id'],
                                'sample_files_sha256': await asyncio.to_thread(sample_hashes, sample),
                                'capture_files_sha256': await asyncio.to_thread(sample_hashes, evidence),
                                'semantic_review': 'REVIEW_REQUIRED'})
                            await asyncio.to_thread(store.finish_attempt,attempt['attempt_id'], worker_id, attempt['lease_token'],
                                                 'collected_pending_review', evidence=_evidence(saved) + [feedback_ref],
                                                 exact_images=index.sample_images(sample))
                            index.add_sample(sample)
                    except asyncio.CancelledError:
                        # A normal stop owns its lease and can close its partial
                        # attempt immediately. If lease ownership was lost,
                        # recover_expired remains authoritative instead.
                        committed = next(row for row in store.attempt_ledger()['attempts']
                                         if row['attempt_id'] == attempt['attempt_id'])
                        if committed['status'] == 'running':
                            evidence.mkdir(parents=True, exist_ok=True)
                            failure = evidence / 'failure.json'
                            if not failure.exists():
                                write_json(failure, {'error': 'runner cancelled; partial trajectory is not success',
                                    'timestamp': now(), 'attempt_id': attempt['attempt_id'],
                                    'task_id': attempt['task_id'], 'failure_class': 'interrupted'})
                            # Settle the ledger first: a cleanup failure must not
                            # mask the primary outcome or strand a running row.
                            try:
                                await asyncio.to_thread(store.finish_attempt,attempt['attempt_id'], worker_id, attempt['lease_token'],
                                    'rejected', failure_class='interrupted', root_cause='runner_cancelled',
                                    evidence=_evidence(failure))
                            except ValueError as cancellation_error:
                                if not str(cancellation_error).startswith(('worker/lease fencing不匹配',
                                        '租约已过期', 'attempt已结束', '已终结attempt不可覆盖')):
                                    raise
                                # A revoked/expired lease must never be revived
                                # merely to write a cancellation outcome.
                            else:
                                try:
                                    quarantine_interrupted(output, [{**attempt, 'status': 'interrupted'}])
                                except Exception as cleanup_error:
                                    checkpoint_json(evidence / 'closeout-cleanup-error.json',
                                        {'primary_error': 'runner cancelled; partial trajectory is not success',
                                         'cleanup_error_type': type(cleanup_error).__name__,
                                         'cleanup_error': str(cleanup_error), 'ledger_settled': True,
                                         'not_business_success_evidence': True})
                        raise
                    except Exception as error:
                        if isinstance(error, sqlite3.OperationalError) and runlog is not None:
                            runlog.info('failed', failureClass='program',
                                errorType=type(error).__name__, rootCause=_root_cause(error))
                        # If success already committed, never reinterpret it as a failed attempt.
                        committed = next(row for row in store.attempt_ledger()['attempts']
                                         if row['attempt_id'] == attempt['attempt_id'])
                        if committed['status'] == 'collected_pending_review':
                            raise
                        evidence.mkdir(parents=True, exist_ok=True)
                        failure = evidence / 'failure.json'
                        if not failure.exists():
                            write_json(failure, {'error': str(error), 'timestamp': now(),
                                'attempt_id': attempt['attempt_id'], 'task_id': attempt['task_id'],
                                'failure_class': classify_failure(error),
                                **({'error_type': type(error).__name__, 'root_cause': _root_cause(error)}
                                   if isinstance(error, sqlite3.OperationalError) else {})})
                        from .agent_feedback import save_attempt_feedback
                        feedback_ref = await asyncio.to_thread(save_attempt_feedback, evidence, attempt, 'rejected', str(error))
                        # The attempt ledger settles before any file relocation:
                        # a later quarantine crash (e.g. a destination already
                        # materialized by the feedback receipt) must not strand
                        # this attempt as running. Cleanup errors are recorded
                        # separately and never mask the primary failure.
                        await asyncio.to_thread(store.finish_attempt,attempt['attempt_id'], worker_id, attempt['lease_token'],
                            'rejected', failure_class=classify_failure(error), root_cause=_root_cause(error),
                            evidence=_evidence(failure) + [feedback_ref])
                        try:
                            quarantine_interrupted(output, [{**attempt, 'status': 'rejected'}])
                        except Exception as cleanup_error:
                            checkpoint_json(evidence / 'closeout-cleanup-error.json',
                                {'primary_error': str(error),
                                 'primary_failure_class': classify_failure(error),
                                 'cleanup_error_type': type(cleanup_error).__name__,
                                 'cleanup_error': str(cleanup_error), 'ledger_settled': True,
                                 'not_business_success_evidence': True})
                        if classify_failure(error) == 'program' and not continuous:
                            store.set_scope_paused(True, 'Program validation failure; preserve rejected attempt and stop before another allocation')
                try:
                    with phase(phase_ledger, 'attempt_runner', scope=meter_identity):
                        await _with_lease(execute_and_finish(), store, attempt, snapshot['policy']['lease_seconds'])
                finally:
                    if context is not None and entry_session is None:
                        try:
                            await asyncio.wait_for(context.close(), timeout=10)
                        except Exception as cleanup_error:
                            checkpoint_json(evidence / 'context_cleanup_error.json',
                                {'error': str(cleanup_error), 'not_business_success_evidence': True})
                    if meter is not None:
                        current_attempt = next(row for row in store.attempt_ledger()['attempts']
                                               if row['attempt_id'] == attempt['attempt_id'])
                        measurement = meter.close(current_attempt['status'])
                        if measurement['measurement_status'] != 'PASS' and not continuous:
                            store.set_scope_paused(True, 'Network measurement incomplete; retain original attempt outcome')
                            raise ValueError('网络计量不完整；保留真实attempt结果并暂停后续任务')
                    snapshot = sync_manifest(store, output, manifest)
                if entry_session is not None:
                    break  # A second formal attempt requires a fresh candidate session.
                if not continuous:
                    await asyncio.sleep(snapshot['policy']['task_interval_seconds'])
        finally:
            sync_manifest(store, output, manifest)
    # Include the durable worker-finish event in the derived snapshot too.
    sync_manifest(store, output, manifest)
    # This second content read prevents an incrementally cached root from hiding changes.
    try:
        if contract_identity(Path(__file__).resolve().parents[3]) != manifest['contract_profile']:
            raise ValueError('采集期间代码或合同来源发生变化，停止本批发布并保留原始证据')
        checkpoint_json(output / 'exact-index-receipt.json', index.verify_snapshot())
    except Exception as error:
        manifest.update(producer_index_status='FAIL', collection_status='blocked_integrity')
        checkpoint_json(output / 'exact-index-failure.json', {'status': 'FAIL', 'reason': str(error)})
        checkpoint_manifest(output, manifest)
        raise
    manifest['producer_index_status'] = 'PASS'
    checkpoint_manifest(output, manifest)
    if manifest['samples']:
        manifest['metadata_receipt'] = refresh_metadata(output)
        checkpoint_manifest(output, manifest)
    return {'batch_id': manifest['batch_id'], 'collected': len(manifest['samples']),
        'rejected': sum(row['status'] == 'rejected' for row in manifest['attempts']),
        'actual_attempts': manifest['actual_attempt_count'],
        'reserved_allocations': manifest['reserved_allocation_count'],
        'collection_status': manifest['collection_status'], 'qualified_samples': 0,
        **({'resource_stop':stopping_checkpoint} if stopping_checkpoint else {}),
        'human_review': 'pending', 'customer_acceptance': 'UNKNOWN', 'output': str(output)}
