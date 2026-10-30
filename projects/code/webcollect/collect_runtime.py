"""Serial M4 collector adapter; the SQLite attempt ledger owns recovery state.

An interrupted browser trajectory is retained as a failed attempt. Resume never
stitches it to another session or reuses its allocated sample ID.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from datetime import datetime, timezone

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
    from .agent_controller import ControllerStop
    if isinstance(error, ControllerStop):
        return {'UNRESOLVED':'interrupted', 'DUPLICATE':'duplicate', 'EXECUTION_FAILED':'model',
                'ENGINEERING_ERROR':'program'}.get(getattr(error,'category',''), 'collector')
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
             'workflow_proposal.py', 'fragment_workflow.py', 'agent_controller.py', 'agent_observation.py', 'agent_audit.py', 'agent_feedback.py', 'sampling_context.py', 'current_chain.py', 'application_identity.py', 'site_failure_stop.py', 'site_pool_sync.py']
    names += [path.relative_to(base).as_posix() for path in sorted((base / 'schemas').glob('*.json'))]
    names += [name for name in ('hmac_strategy.py', 'pbkdf2_strategy.py') if (base / name).is_file()]
    return {name: sha(base / name) for name in names}


def sample_hashes(sample):
    sample = Path(sample)
    return {p.relative_to(sample).as_posix(): sha(p)
            for p in sorted(sample.rglob('*')) if p.is_file()}


def quarantine_interrupted(output, attempts):
    """Move only rejected attempts, keeping finished samples where they belong."""
    output = Path(output)
    for attempt in attempts:
        if attempt['status'] not in ('rejected', 'interrupted'):
            continue
        sample = output / 'samples' / attempt['sample_id']
        if sample.exists():
            destination = output / 'rejected' / attempt['sample_id']
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError('中断样本的隔离目录已存在，拒绝覆盖：' + str(destination))
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
        expected = receipt.get('sample_files_sha256')
        actual = sample_hashes(Path(output) / 'samples' / attempt['sample_id'])
        if (receipt.get('attempt_id') != attempt['attempt_id'] or
                receipt.get('sample_id') != attempt['sample_id'] or not expected or actual != expected):
            raise ValueError('已完成样本缺失或证据改变，停止续跑：' + attempt['sample_id'])
        actual_raw = {name: digest for name, digest in sample_hashes(receipt_path.parent).items()
                      if name not in ('saved_sample.json', 'context_cleanup_error.json')}
        if not receipt.get('capture_files_sha256') or receipt['capture_files_sha256'] != actual_raw:
            raise ValueError('已完成样本的原始采集证据改变，停止续跑：' + attempt['sample_id'])


async def heartbeat_lease(store, attempt, seconds):
    while True:
        await asyncio.sleep(max(0.1, seconds / 3))
        store.heartbeat(attempt['attempt_id'], attempt['worker_id'], attempt['lease_token'])


def _evidence(path):
    return [{'path': str(Path(path).resolve()), 'sha256': sha(path)}]


def _root_cause(error):
    import re
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
            heartbeat.result()
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


async def _collect_m4_locked(plan_path, output, registry, *, publication_path=None,
                     policy_path=None, resume=False, channel='chrome', headless=True, navigation=None, site_pool=None, controller_ledger=None):
    from playwright.async_api import async_playwright
    from importlib.metadata import version
    from .collect import collect_one, validate_plan, checkpoint_json, checkpoint_manifest, now
    from .planning import verify_publication, object_sha256
    from .runtime import RuntimeStore
    from .scaffold import program_version
    from .evidence import audit_capture
    from .telemetry import NetworkMeter, phase, worker_measurement

    plan = read_json(plan_path)
    validate_plan(plan)
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
    sources = source_identity()
    bootstrap_path = output / 'bootstrap.json'
    if resume and bootstrap_path.exists():
        bootstrap = read_json(bootstrap_path)
        if (bootstrap.get('plan') != plan or bootstrap.get('publication') != publication
                or bootstrap.get('source_files_sha256') != sources
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
        manifest = {'schema_version': 'webcollect-runtime-manifest-m4-1',
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
        checkpoint_json(bootstrap_path, {'schema_version': 'webcollect-bootstrap-m4-1',
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
    store.recover_expired()
    attempts = store.attempt_ledger()['attempts']
    verify_committed_samples(output, attempts)
    quarantine_interrupted(output, attempts)
    snapshot = sync_manifest(store, output, manifest)
    roots = [output.parent, *[Path(path) for path in plan.get('dedup_roots', [])]]
    index = ConcurrentExactImageIndex(roots, store)
    worker_id = 'serial-' + str(uuid.uuid4())
    phase_ledger = output / 'metering' / 'phases.jsonl'
    async with worker_measurement(store, worker_id, output), async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=channel, headless=headless)
        manifest.update(browser_version=browser.version, playwright_version=version('playwright'))
        idle_waited = 0
        try:
            while True:
                verify_publication(plan, publication)
                checkpoint = store.resource_checkpoint(output)
                if checkpoint['status'] == 'STOP':
                    manifest['resource_stop'] = checkpoint
                    break
                attempt = store.claim_next(worker_id, request_id=str(uuid.uuid4()),
                    plan_sha256=publication['plan_sha256'], batch_id=manifest['batch_id'])
                if attempt is None:
                    latest = store.snapshot()
                    pending = sum(row['status'] == 'collected_pending_review' for row in latest['tasks'])
                    active = any(row['status'] in ('running', 'reserved') for row in latest['tasks'])
                    if (idle_waited < 5 and latest['scope']['state'] == 'active' and not active
                            and any(row['status'] == 'queued' for row in latest['tasks'])
                            and latest['campaign_actual_attempt_count'] < latest['policy']['attempt_cap']
                            and pending < latest['policy']['pending_review_cap']):
                        # Briefly accommodate retry/domain backoff; never wait forever on a budget.
                        await asyncio.sleep(1)
                        idle_waited += 1
                        continue
                    break
                idle_waited = 0
                snapshot = sync_manifest(store, output, manifest)
                attempt = store.start_attempt(attempt['attempt_id'], worker_id, attempt['lease_token'])
                sample = output / 'samples' / attempt['sample_id']
                evidence = output / 'evidence' / attempt['sample_id']
                context = None
                meter = None
                meter_identity = {key: attempt[key] for key in ('attempt_id', 'task_id', 'task_version', 'sample_id')}
                async def execute_and_finish():
                    nonlocal context, meter
                    try:
                        context = await browser.new_context(viewport={'width': 1280, 'height': 720},
                            device_scale_factor=1, locale='zh-CN', timezone_id='Asia/Shanghai')
                        meter = NetworkMeter(context, output / 'metering' / attempt['attempt_id'], meter_identity)
                        ids = {key: attempt[key] for key in ('sample_id', 'site_id', 'batch_id')}
                        task = {**attempt['task'], '_plan_schema_version': plan['schema_version'],
                                'require_public_origin': True}
                        from .agent_controller import is_controlled, FragmentController, model_chooser
                        controller_options = {}
                        if is_controlled(task):
                            if controller_ledger is None:
                                raise ValueError('Dynamic controller requires original BatchLedger')
                            from .agent_feedback import site_context
                            planning_context = plan.get('generation',{}).get('site_planning_context') or {}
                            feedback_context = site_context(registry, task['site_uri'], model_ledger=controller_ledger,
                                generation=planning_context.get('history',[]),
                                quality=[q['reference'] for q in planning_context.get('quality_feedback',[])])
                            if feedback_context['unresolved']:
                                # Exclude only this already claimed attempt.
                                if any(r.get('attempt_id') != attempt['attempt_id'] for r in feedback_context['unresolved']):
                                    raise ValueError('Unresolved prior attempt blocks dynamic dispatch')
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
                                    model_chooser(controller_ledger, bound_task, attempt['attempt_id']),
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
                        store.finish_attempt(attempt['attempt_id'], worker_id, attempt['lease_token'],
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
                            quarantine_interrupted(output, [{**attempt, 'status': 'interrupted'}])
                            try:
                                store.finish_attempt(attempt['attempt_id'], worker_id, attempt['lease_token'],
                                    'rejected', failure_class='interrupted', root_cause='runner_cancelled',
                                    evidence=_evidence(failure))
                            except ValueError as cancellation_error:
                                if not str(cancellation_error).startswith(('worker/lease fencing不匹配',
                                        '租约已过期', 'attempt已结束', '已终结attempt不可覆盖')):
                                    raise
                                # A revoked/expired lease must never be revived
                                # merely to write a cancellation outcome.
                        raise
                    except Exception as error:
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
                                'failure_class': classify_failure(error)})
                        from .agent_feedback import save_attempt_feedback
                        feedback_ref = save_attempt_feedback(evidence, attempt, 'rejected', str(error))
                        quarantine_interrupted(output, [{**attempt, 'status': 'rejected'}])
                        store.finish_attempt(attempt['attempt_id'], worker_id, attempt['lease_token'],
                            'rejected', failure_class=classify_failure(error), root_cause=_root_cause(error),
                            evidence=_evidence(failure) + [feedback_ref])
                        if classify_failure(error) == 'program':
                            store.set_scope_paused(True, 'Program validation failure; preserve rejected attempt and stop before another allocation')
                try:
                    with phase(phase_ledger, 'attempt_runner', scope=meter_identity):
                        await _with_lease(execute_and_finish(), store, attempt, snapshot['policy']['lease_seconds'])
                finally:
                    if context is not None:
                        try:
                            await asyncio.wait_for(context.close(), timeout=10)
                        except Exception as cleanup_error:
                            checkpoint_json(evidence / 'context_cleanup_error.json',
                                {'error': str(cleanup_error), 'not_business_success_evidence': True})
                    if meter is not None:
                        current_attempt = next(row for row in store.attempt_ledger()['attempts']
                                               if row['attempt_id'] == attempt['attempt_id'])
                        measurement = meter.close(current_attempt['status'])
                        if measurement['measurement_status'] != 'PASS':
                            store.set_scope_paused(True, 'Network measurement incomplete; retain original attempt outcome')
                            raise ValueError('网络计量不完整；保留真实attempt结果并暂停后续任务')
                    snapshot = sync_manifest(store, output, manifest)
                await asyncio.sleep(snapshot['policy']['task_interval_seconds'])
        finally:
            try:
                await asyncio.wait_for(browser.close(), timeout=10)
            finally:
                sync_manifest(store, output, manifest)
    # Include the durable worker-finish event in the derived snapshot too.
    sync_manifest(store, output, manifest)
    # This second content read prevents an incrementally cached root from hiding changes.
    try:
        if source_identity() != sources or contract_identity(Path(__file__).resolve().parents[3]) != manifest['contract_profile']:
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
        'human_review': 'pending', 'customer_acceptance': 'UNKNOWN', 'output': str(output)}
