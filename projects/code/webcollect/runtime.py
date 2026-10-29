"""SQLite M4 queue: one transaction owns numbering, attempt identity and events.

Scopes bind an output batch. Campaigns share budgets and quota reservations, so
changing a directory cannot reset a production budget. This module never opens a
browser, modifies evidence, or declares a customer/QC acceptance decision.
"""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from .planning import canonical, object_sha256, timestamp, verify_evidence, verify_publication
from .storage import allocate_in_transaction, ensure_registry_schema


DEFAULT_POLICY = {'campaign_id': 'm4-1000', 'max_workers': 1, 'max_domain_workers': 1,
                  'attempt_cap': 40, 'pending_review_cap': 20, 'max_retries': 2,
                  'lease_seconds': 120, 'task_interval_seconds': 1,
                  'retry_backoff_seconds': 1, 'target_total': 1000,
                  'max_category_share': 0.2, 'baseline_category_counts': {}, 'category_limits': {},
                  'min_free_disk_bytes': None, 'max_output_bytes': None,
                  'max_worker_seconds': None, 'resource_root': None}
ACTIVE = ('reserved', 'running')
RETRYABLE = ('network', 'resource')
FAILURES = RETRYABLE + ('interrupted', 'semantic', 'unsupported', 'privacy', 'duplicate', 'program', 'other')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS m4_campaigns (
 campaign_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS m4_scopes (
 scope_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, state TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS m4_plans (
 scope_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL, plan_json TEXT NOT NULL,
 publication_json TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(scope_id,plan_sha256));
CREATE TABLE IF NOT EXISTS m4_tasks (
 task_key TEXT PRIMARY KEY, scope_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
 task_id TEXT NOT NULL, task_version TEXT NOT NULL, task_sha256 TEXT NOT NULL,
 task_json TEXT NOT NULL, category TEXT NOT NULL, domain_key TEXT NOT NULL,
 status TEXT NOT NULL, quota_reserved INTEGER NOT NULL, capability_expires_at REAL NOT NULL,
 next_eligible_at REAL NOT NULL, created_at REAL NOT NULL,
 UNIQUE(campaign_id,task_id,task_version));
CREATE TABLE IF NOT EXISTS m4_plan_tasks (
 scope_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL, task_key TEXT NOT NULL,
 ordinal INTEGER NOT NULL, PRIMARY KEY(scope_id,plan_sha256,task_key));
CREATE TABLE IF NOT EXISTS m4_attempts (
 attempt_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
 task_key TEXT NOT NULL, plan_sha256 TEXT NOT NULL, request_id TEXT NOT NULL,
 worker_id TEXT NOT NULL, lease_token TEXT NOT NULL, lease_expires_at REAL NOT NULL,
 sample_id TEXT NOT NULL UNIQUE, site_id TEXT NOT NULL, batch_id TEXT NOT NULL,
 status TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL, finished_at REAL,
 retry_of TEXT, failure_class TEXT, root_cause TEXT, evidence_json TEXT NOT NULL,
 UNIQUE(scope_id,request_id));
CREATE TABLE IF NOT EXISTS m4_events (
 event_id INTEGER PRIMARY KEY, scope_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
 event_type TEXT NOT NULL, task_key TEXT, attempt_id TEXT, at REAL NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS m4_domains (
 domain_key TEXT PRIMARY KEY, next_start_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS m4_reviews (
 sample_id TEXT PRIMARY KEY, decision TEXT NOT NULL, evidence_json TEXT NOT NULL,
 reason TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS m4_publications (
 campaign_id TEXT NOT NULL, release_id TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 sample_ids_json TEXT NOT NULL, evidence_json TEXT NOT NULL, at REAL NOT NULL,
 PRIMARY KEY(campaign_id,release_id));
CREATE INDEX IF NOT EXISTS m4_attempt_campaign ON m4_attempts(campaign_id,status);
CREATE INDEX IF NOT EXISTS m4_attempt_task ON m4_attempts(task_key,created_at);
CREATE TABLE IF NOT EXISTS m4_exact_images (
 path TEXT PRIMARY KEY, digest TEXT NOT NULL, sample_id TEXT NOT NULL,
 attempt_id TEXT, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS m4_exact_digest ON m4_exact_images(digest);
CREATE TABLE IF NOT EXISTS m4_site_pool (
 scope_id TEXT PRIMARY KEY, pool_path TEXT NOT NULL, pending INTEGER NOT NULL,
 synced_revision INTEGER NOT NULL DEFAULT 0, last_error TEXT);
'''


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - (set(DEFAULT_POLICY) | {'pilot_identity_required', 'site_failure_guard'}):
        raise ValueError('运行预算包含未知字段')
    policy = {**deepcopy(DEFAULT_POLICY), **deepcopy(value)}
    if 'pilot_identity_required' in value and value['pilot_identity_required'] is not True:
        raise ValueError('pilot_identity_required只能显式开启，不能关闭已冻结试点门禁')
    if 'site_failure_guard' in value:
        from .site_failure_stop import validate_binding
        policy['site_failure_guard'] = validate_binding(value['site_failure_guard'])
    if not isinstance(policy['campaign_id'], str) or not policy['campaign_id'].strip():
        raise ValueError('campaign_id必须非空')
    for key in ('max_workers', 'max_domain_workers', 'attempt_cap', 'pending_review_cap', 'lease_seconds', 'target_total'):
        if type(policy[key]) is not int or policy[key] <= 0:
            raise ValueError(key + '必须为正整数')
    if type(policy['max_retries']) is not int or policy['max_retries'] < 0:
        raise ValueError('max_retries必须为非负整数')
    for key in ('task_interval_seconds', 'retry_backoff_seconds'):
        if type(policy[key]) not in (int, float) or not math.isfinite(policy[key]) or policy[key] < 1:
            raise ValueError(key + '须为至少1秒的有限预算')
    share = policy['max_category_share']
    if type(share) not in (int, float) or not 0 < share <= 0.2:
        raise ValueError('类目比例必须大于0且不超过合同20%')
    for key in ('baseline_category_counts', 'category_limits'):
        if not isinstance(policy[key], dict) or any(not isinstance(k, str) or not k.strip() or type(v) is not int or v < 0 for k, v in policy[key].items()):
            raise ValueError(key + '必须为类目到非负整数的映射')
    maximum = math.floor(policy['target_total'] * share)
    if any(limit > maximum for limit in policy['category_limits'].values()):
        raise ValueError('类目预算不得放宽合同占比')
    if sum(policy['baseline_category_counts'].values()) > policy['target_total']:
        raise ValueError('基线计数超过累计目标')
    for key in ('min_free_disk_bytes', 'max_output_bytes', 'max_worker_seconds'):
        value = policy[key]
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError(key + '必须为空或正整数')
    if policy['resource_root'] is not None and (not isinstance(policy['resource_root'], str)
            or not Path(policy['resource_root']).is_absolute()):
        raise ValueError('resource_root必须为空或绝对路径')
    if policy['max_output_bytes'] is not None and policy['resource_root'] is None:
        raise ValueError('存储上限需要固定campaign resource_root，不能按批次重置')
    if policy['resource_root'] is not None:
        policy['resource_root'] = str(Path(policy['resource_root']).resolve())
    return policy


def domain_key(uri):
    """Conservative traffic grouping; subdomains cannot obtain separate budgets.

    Without a mutable public-suffix dependency, co.uk-like suffixes are grouped
    more broadly, never split into extra concurrency allowances.
    """
    host = (urlsplit(uri).hostname or '').lower().rstrip('.')
    if not host:
        raise ValueError('站点URI无主机名')
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return '.'.join(host.split('.')[-2:])


def _bound_quality_report(evidence):
    """Reuse the customer package binding gate, never infer QC from file hashes."""
    from .client_reports import _bound_report
    verify_evidence(evidence)
    candidates = []
    for item in evidence:
        try:
            value = json.loads(Path(item['path']).read_text(encoding='utf-8'))
        except (UnicodeError, ValueError):
            continue
        if isinstance(value, dict) and value.get('program') == 'quality-inspector':
            if not isinstance(value.get('dataset'), str) or not value['dataset'].strip():
                raise ValueError('QC报告缺少实际客户目录')
            candidates.append((item, Path(value['dataset']).resolve()))
    if len(candidates) != 1:
        raise ValueError('审核或发布必须引用恰一份实际quality-inspector报告，任意文件SHA不能授予通过')
    reference, source = candidates[0]
    report, _ = _bound_report(source, Path(reference['path']))
    verify_evidence(evidence)
    return report, {'path': reference['path'], 'sha256': reference['sha256'],
                    'dataset': str(source), 'inspection_stage': report.get('inspection_stage')}


class ImageCommitConflict(ValueError):
    failure_class = 'duplicate'

    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__('跨样本截图重复，拒绝并发提交：' + canonical(conflicts))


class RuntimeStore:
    def __init__(self, registry, scope_id):
        self.registry = Path(registry).resolve()
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise ValueError('scope_id必须非空且稳定绑定输出范围')
        self.scope_id = scope_id

    def _connect(self, readonly=False):
        # mode=rw/ro never silently creates a replacement for a missing ledger.
        con = sqlite3.connect(self.registry.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    @contextmanager
    def _transaction(self):
        con = self._connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            yield con
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m4_site_pool'").fetchone():
                con.execute('UPDATE m4_site_pool SET pending=1 WHERE scope_id=?', (self.scope_id,))
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()
        self.sync_site_pool(strict=False)

    def site_pool_binding(self):
        with closing(self._connect(readonly=True)) as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m4_site_pool'").fetchone():
                return None
            row = con.execute('SELECT * FROM m4_site_pool WHERE scope_id=?', (self.scope_id,)).fetchone()
            return dict(row) if row else None

    def bind_site_pool(self, pool_path):
        from site_planner.site_pool import SitePool
        from .site_pool_sync import guard_plan
        path = str(SitePool(pool_path, readonly=True).path)
        with closing(self._connect()) as con:
            con.execute('CREATE TABLE IF NOT EXISTS m4_site_pool (scope_id TEXT PRIMARY KEY, pool_path TEXT NOT NULL, '
                        'pending INTEGER NOT NULL, synced_revision INTEGER NOT NULL DEFAULT 0, last_error TEXT)')
            con.commit()
        old = self.site_pool_binding()
        if old:
            if old['pool_path'] != path:
                raise ValueError('Cannot replace an existing shared pool binding')
            self.sync_site_pool()
            return
        binding = self.plan_binding()
        if binding.get('plan'):
            guard_plan(path, self.registry, self.scope_id, binding['plan'])
        with self._transaction() as con:
            old = con.execute('SELECT pool_path FROM m4_site_pool WHERE scope_id=?', (self.scope_id,)).fetchone()
            if old and old[0] != path:
                raise ValueError('Cannot replace an existing shared pool binding')
            con.execute('INSERT OR IGNORE INTO m4_site_pool(scope_id,pool_path,pending) VALUES(?,?,1)',
                        (self.scope_id, path))
            self._event(con, 'site_pool_bound', timestamp(None), {'pool': path}) if not old else None
        self.sync_site_pool()

    def sync_site_pool(self, *, strict=True):
        binding = self.site_pool_binding()
        if binding is None:
            return None
        try:
            from .site_pool_sync import sync
            revision = sync(binding['pool_path'], self.registry, self.scope_id)
            with closing(self._connect()) as con:
                con.execute('UPDATE m4_site_pool SET pending=0,synced_revision=?,last_error=NULL '
                            'WHERE scope_id=? AND ?=(SELECT COALESCE(MAX(event_id),0) FROM m4_events WHERE scope_id=?)',
                            (revision, self.scope_id, revision, self.scope_id))
                con.commit()
            return revision
        except Exception as error:
            with closing(self._connect()) as con:
                con.execute('UPDATE m4_site_pool SET pending=1,last_error=? WHERE scope_id=?',
                            (type(error).__name__, self.scope_id))
                con.commit()
            if strict:
                raise
            return None

    def _scope(self, con):
        row = con.execute('SELECT * FROM m4_scopes WHERE scope_id=?', (self.scope_id,)).fetchone()
        if row is None:
            raise ValueError('运行范围尚未初始化')
        return row

    def _policy(self, con):
        scope = self._scope(con)
        return json.loads(con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?', (scope['campaign_id'],)).fetchone()[0])

    def _event(self, con, event, now, payload=None, task_key=None, attempt_id=None):
        campaign = self._scope(con)['campaign_id']
        con.execute('INSERT INTO m4_events(scope_id,campaign_id,event_type,task_key,attempt_id,at,payload_json) VALUES(?,?,?,?,?,?,?)',
                    (self.scope_id, campaign, event, task_key, attempt_id, now, canonical(payload or {})))

    def _customer_history_proof(self, plan=None):
        """Read/hash original customer evidence before taking the writer lock."""
        if plan is None:
            con = self._connect(readonly=True)
            try:
                row = con.execute('SELECT plan_json FROM m4_plans WHERE scope_id=?', (self.scope_id,)).fetchone()
                if row is None:
                    return {}
                plan = json.loads(row[0])
            finally:
                con.close()
        from .admission_cohort import validate_customer_history
        return validate_customer_history(plan)

    def _sync_site_failures(self):
        # Reconcile committed new failures before taking the production writer
        # lock. A crash after finish cannot hide a failure on the next dispatch.
        con = self._connect(readonly=True)
        try:
            policy = self._policy(con)
        finally:
            con.close()
        if policy.get('site_failure_guard'):
            from .site_failure_stop import SiteFailureStore
            site_store = SiteFailureStore(policy['site_failure_guard'])
            site_store.sync_formal(self.registry, policy['campaign_id'])
            site_store.sync_successes(self.registry, policy['campaign_id'])

    @staticmethod
    def _guard_site(policy, task):
        if policy.get('site_failure_guard'):
            from .site_failure_stop import SiteFailureStore
            SiteFailureStore(policy['site_failure_guard']).guard(task)

    def initialize(self, policy=None, *, now=None):
        policy = validate_policy(policy or {})
        current = timestamp(now)
        con = self._connect()
        try:
            # Schema additions leave all legacy rows and counters intact.
            ensure_registry_schema(con)
            con.executescript(SCHEMA)
        finally:
            con.close()
        with self._transaction() as con:
            campaign = con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?', (policy['campaign_id'],)).fetchone()
            if campaign and json.loads(campaign[0]) != policy:
                raise ValueError('已有campaign预算不同；须带原因显式update_policy，不能换scope重置')
            con.execute('INSERT OR IGNORE INTO m4_campaigns VALUES(?,?,?)', (policy['campaign_id'], canonical(policy), current))
            existing = con.execute('SELECT campaign_id FROM m4_scopes WHERE scope_id=?', (self.scope_id,)).fetchone()
            if existing and existing[0] != policy['campaign_id']:
                raise ValueError('已有scope不能更换campaign')
            if not existing:
                con.execute('INSERT INTO m4_scopes VALUES(?,?,?,?)', (self.scope_id, policy['campaign_id'], 'active', current))
                self._event(con, 'scope_initialized', current, {'policy': policy})
        return self.snapshot()

    def update_policy(self, updates, reason, *, now=None):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('预算更新必须记录实际原因')
        with self._transaction() as con:
            old = self._policy(con)
            new = validate_policy({**old, **updates})
            if old.get('pilot_identity_required') and not new.get('pilot_identity_required'):
                raise ValueError('不能关闭已开启的试点身份门禁')
            if old.get('site_failure_guard') and new.get('site_failure_guard') != old['site_failure_guard']:
                raise ValueError('不能更换或清空整站失败账以重置累计停止状态')
            if new['campaign_id'] != old['campaign_id'] or new['baseline_category_counts'] != old['baseline_category_counts']:
                raise ValueError('已有campaign或基线分母不能通过预算更新替换')
            if old.get('resource_root') is not None and new['resource_root'] != old['resource_root']:
                raise ValueError('已有campaign resource_root不能更换或清空来重置存储计量')
            if old.get('resource_root') is None and new['resource_root'] is not None:
                for row in con.execute("SELECT payload_json FROM m4_events WHERE campaign_id=? AND event_type='worker_started'", (old['campaign_id'],)):
                    prior = Path(json.loads(row[0])['output']).resolve()
                    if not prior.is_relative_to(Path(new['resource_root'])):
                        raise ValueError('新resource_root必须包含本campaign已记录的全部输出')
            self._check_quota(con, new)
            con.execute('UPDATE m4_campaigns SET policy_json=? WHERE campaign_id=?', (canonical(new), old['campaign_id']))
            self._event(con, 'policy_updated', timestamp(now), {'before': old, 'after': new, 'reason': reason})
        return new

    def _check_quota(self, con, policy):
        counts = dict(policy['baseline_category_counts'])
        for row in con.execute('SELECT category,COUNT(*) n FROM m4_tasks WHERE campaign_id=? AND quota_reserved=1 GROUP BY category', (policy['campaign_id'],)):
            counts[row['category']] = counts.get(row['category'], 0) + row['n']
        if sum(counts.values()) > policy['target_total']:
            raise ValueError('累计已接纳/在途预留超过目标')
        for category, count in counts.items():
            limit = policy['category_limits'].get(category, math.floor(policy['target_total'] * policy['max_category_share']))
            if count > limit:
                raise ValueError('类目配额不足：' + category)
        return counts

    def enqueue_plan(self, plan, publication, *, now=None):
        current = timestamp(now)
        from .current_chain import require_plan
        connection = self._connect(readonly=True)
        try:
            require_plan(plan, self.registry, self._policy(connection))
        finally:
            connection.close()
        verify_publication(plan, publication, now=current)
        history_proof = self._customer_history_proof(plan)
        current = timestamp(now)
        plan_sha = publication['plan_sha256']
        with self._transaction() as con:
            policy = self._policy(con)
            from .production_identity import validate_plan as pilot_plan
            pilot_plan(plan, required=policy.get('pilot_identity_required', False))
            if self._scope(con)['state'] == 'closed_replanned':
                raise ValueError('scope已永久closed_replanned；新任务版本必须使用新scope')
            from .admission_cohort import guard_enqueue
            guard_enqueue(con, self.registry, self.scope_id, plan, publication, policy['campaign_id'], history_proof=history_proof)
            existing = con.execute('SELECT * FROM m4_plans WHERE scope_id=? AND plan_sha256=?', (self.scope_id, plan_sha)).fetchone()
            if existing:
                if json.loads(existing['publication_json']) != publication:
                    raise ValueError('同计划已有不同发布收据，不能静默替换')
                return {'plan_sha256': plan_sha, 'task_count': len(plan['tasks']), 'already_enqueued': True}
            # A scope is an immutable output batch, not a container for changed plans.
            if con.execute('SELECT 1 FROM m4_plans WHERE scope_id=?', (self.scope_id,)).fetchone():
                raise ValueError('已有scope不能替换计划；新任务版本须显式新scope')
            con.execute('INSERT INTO m4_plans VALUES(?,?,?,?,?)', (self.scope_id, plan_sha, canonical(plan), canonical(publication), current))
            bindings = {(row['task_id'], row['task_version']): row for row in publication['tasks']}
            for ordinal, task in enumerate(plan['tasks']):
                key = object_sha256([policy['campaign_id'], task['task_id'], task['task_version']])
                old = con.execute('SELECT scope_id,status FROM m4_tasks WHERE task_key=?', (key,)).fetchone()
                if old:
                    raise ValueError('同task/version已登记；跨scope不重跑，失败请在原scope恢复')
                active = con.execute('SELECT 1 FROM m4_tasks WHERE campaign_id=? AND task_id=? AND quota_reserved=1', (policy['campaign_id'], task['task_id'])).fetchone()
                if active:
                    raise ValueError('同逻辑任务已有在途或已接纳版本')
                binding = bindings[(task['task_id'], task['task_version'])]
                from .production_identity import reserve as reserve_page
                reserve_page(con, key, task)
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key, self.scope_id, policy['campaign_id'], task['task_id'], task['task_version'], object_sha256(task),
                             canonical(task), task['site_category'], domain_key(task['site_uri']), 'queued', 1,
                             binding['capability_expires_at'], current, current))
                con.execute('INSERT INTO m4_plan_tasks VALUES(?,?,?,?)', (self.scope_id, plan_sha, key, ordinal))
            self._check_quota(con, policy)
            self._event(con, 'plan_enqueued', current, {'plan_sha256': plan_sha, 'publication_sha256': publication['publication_sha256'], 'task_count': len(plan['tasks'])})
        return {'plan_sha256': plan_sha, 'task_count': len(plan['tasks']), 'already_enqueued': False}

    def _attempt(self, con, attempt_id):
        row = con.execute('SELECT a.*,t.task_id,t.task_version,t.task_json,t.domain_key,t.capability_expires_at FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.attempt_id=? AND a.scope_id=?', (attempt_id, self.scope_id)).fetchone()
        if row is None:
            raise ValueError('attempt不属于本scope')
        return row

    @staticmethod
    def _view(row):
        result = dict(row)
        if 'task_json' in result:
            result['task'] = json.loads(result.pop('task_json'))
        if 'evidence_json' in result:
            result['evidence'] = json.loads(result.pop('evidence_json'))
        return result

    def claim_next(self, worker_id, *, request_id, plan_sha256=None, batch_id=None, now=None, _fault=None):
        if not all(isinstance(v, str) and v.strip() for v in (worker_id, request_id)):
            raise ValueError('worker_id和幂等request_id必须非空')
        self.sync_site_pool()
        self._sync_site_failures()
        history_proof = self._customer_history_proof()
        current = timestamp(now)
        with self._transaction() as con:
            policy = self._policy(con)
            old = con.execute('SELECT attempt_id,worker_id,plan_sha256 FROM m4_attempts WHERE scope_id=? AND request_id=?', (self.scope_id, request_id)).fetchone()
            if old:
                if old['worker_id'] != worker_id or (plan_sha256 is not None and old['plan_sha256'] != plan_sha256):
                    raise ValueError('幂等request_id已用于不同worker或计划')
                previous = self._attempt(con, old['attempt_id'])
                self._guard_site(policy, json.loads(previous['task_json']))
                from .production_identity import guard as page_guard
                page_guard(con, previous['task_key'], json.loads(previous['task_json']),
                           required=policy.get('pilot_identity_required', False))
                return self._view(previous)
            if self._scope(con)['state'] != 'active':
                return None
            from .admission_cohort import guard_scope
            guard_scope(con, self.registry, self.scope_id, history_proof=history_proof)
            campaign = policy['campaign_id']
            live = list(con.execute("SELECT a.*,t.domain_key FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.status IN ('reserved','running') AND a.lease_expires_at>?", (current,)))
            if sum(r['campaign_id'] == campaign for r in live) >= policy['max_workers'] or any(r['worker_id'] == worker_id for r in live):
                return None
            started = con.execute('SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=? AND started_at IS NOT NULL', (campaign,)).fetchone()[0]
            reserved = con.execute("SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=? AND status='reserved'", (campaign,)).fetchone()[0]
            if started + reserved >= policy['attempt_cap']:
                return None
            backlog = con.execute("SELECT COUNT(*) FROM m4_tasks WHERE campaign_id=? AND status IN ('reserved','running','collected_pending_review')", (campaign,)).fetchone()[0]
            if backlog >= policy['pending_review_cap']:
                return None
            rows = list(con.execute("SELECT t.*,p.plan_sha256 FROM m4_tasks t JOIN m4_plan_tasks p ON p.task_key=t.task_key AND p.scope_id=t.scope_id WHERE t.scope_id=? AND t.status='queued' AND t.next_eligible_at<=? ORDER BY p.ordinal", (self.scope_id, current)))
            for row in rows:
                if plan_sha256 is not None and row['plan_sha256'] != plan_sha256:
                    continue
                if row['capability_expires_at'] <= current:
                    con.execute("UPDATE m4_tasks SET status='needs_replan',quota_reserved=0 WHERE task_key=?", (row['task_key'],))
                    self._event(con, 'capability_expired', current, task_key=row['task_key'])
                    continue
                if sum(r['domain_key'] == row['domain_key'] for r in live) >= policy['max_domain_workers']:
                    continue
                domain = con.execute('SELECT next_start_at FROM m4_domains WHERE domain_key=?', (row['domain_key'],)).fetchone()
                if domain and domain[0] > current:
                    continue
                task = json.loads(row['task_json'])
                from .site_failure_stop import SiteStopped
                try:
                    self._guard_site(policy, task)
                except SiteStopped:
                    continue  # Other whole applications remain dispatchable.
                from .production_identity import allocation_uri, guard as page_guard
                page_guard(con, row['task_key'], task, required=policy.get('pilot_identity_required', False))
                day = datetime.fromtimestamp(current, ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
                ids = allocate_in_transaction(con, allocation_uri(task), task['site_category'], 'real', day, batch_id)
                if _fault:
                    _fault('after_allocation_before_attempt')
                attempt_id, token = str(uuid.uuid4()), str(uuid.uuid4())
                previous = con.execute('SELECT attempt_id FROM m4_attempts WHERE task_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (row['task_key'],)).fetchone()
                con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (attempt_id, self.scope_id, campaign, row['task_key'], row['plan_sha256'], request_id, worker_id,
                             token, current + policy['lease_seconds'], ids['sample_id'], ids['site_id'], ids['batch_id'],
                             'reserved', current, None, None, previous[0] if previous else None, None, None, canonical([])))
                con.execute("UPDATE m4_tasks SET status='reserved' WHERE task_key=?", (row['task_key'],))
                self._event(con, 'attempt_reserved', current, {**ids, 'request_id': request_id, 'worker_id': worker_id}, row['task_key'], attempt_id)
                if _fault:
                    _fault('before_commit')
                return self._view(self._attempt(con, attempt_id))
        return None

    def _owned(self, con, attempt_id, worker_id, lease_token, current, *, terminal_ok=False):
        row = self._attempt(con, attempt_id)
        if row['worker_id'] != worker_id or row['lease_token'] != lease_token:
            raise ValueError('worker/lease fencing不匹配')
        if row['status'] not in ACTIVE:
            if terminal_ok:
                return row
            raise ValueError('attempt已结束，禁止继续或拼接')
        if row['lease_expires_at'] <= current:
            raise ValueError('租约已过期；先恢复并用新编号重试')
        return row

    def start_attempt(self, attempt_id, worker_id, lease_token, *, now=None):
        self.sync_site_pool()
        self._sync_site_failures()
        history_proof = self._customer_history_proof()
        current = timestamp(now)
        with self._transaction() as con:
            row = self._owned(con, attempt_id, worker_id, lease_token, current)
            self._guard_site(self._policy(con), json.loads(row['task_json']))
            from .production_identity import guard as page_guard
            page_guard(con, row['task_key'], json.loads(row['task_json']),
                       required=self._policy(con).get('pilot_identity_required', False))
            from .admission_cohort import guard_scope
            guard_scope(con, self.registry, self.scope_id, history_proof=history_proof)
            if row['capability_expires_at'] <= current:
                raise ValueError('能力已过期，不能开始真实执行')
            if row['started_at'] is None:
                policy = self._policy(con)
                used = con.execute('SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=? AND started_at IS NOT NULL', (row['campaign_id'],)).fetchone()[0]
                if used >= policy['attempt_cap']:
                    raise ValueError('campaign真实尝试预算已耗尽')
                con.execute("UPDATE m4_attempts SET status='running',started_at=? WHERE attempt_id=?", (current, attempt_id))
                con.execute("UPDATE m4_tasks SET status='running' WHERE task_key=?", (row['task_key'],))
                self._event(con, 'attempt_started', current, task_key=row['task_key'], attempt_id=attempt_id)
            return self._view(self._attempt(con, attempt_id))

    def heartbeat(self, attempt_id, worker_id, lease_token, *, now=None):
        current = timestamp(now)
        with self._transaction() as con:
            self._owned(con, attempt_id, worker_id, lease_token, current)
            from .admission_cohort import guard_scope
            guard_scope(con, self.registry, self.scope_id)
            expires = current + self._policy(con)['lease_seconds']
            con.execute('UPDATE m4_attempts SET lease_expires_at=? WHERE attempt_id=?', (expires, attempt_id))
            self._event(con, 'lease_extended', current, {'lease_expires_at': expires}, attempt_id=attempt_id)
        return expires

    def _failure_transition(self, con, row, current, policy):
        failures = con.execute('SELECT COUNT(*) FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.campaign_id=? AND t.task_id=? AND a.root_cause=? AND a.started_at IS NOT NULL AND a.finished_at IS NOT NULL',
                               (row['campaign_id'], row['task_id'], row['root_cause'])).fetchone()[0]
        retry = row['failure_class'] in RETRYABLE and failures <= policy['max_retries']
        status = 'queued' if retry else 'needs_replan'
        delay = policy['retry_backoff_seconds'] * (2 ** max(0, failures - 1)) if retry else 0
        con.execute('UPDATE m4_tasks SET status=?,quota_reserved=?,next_eligible_at=? WHERE task_key=?',
                    (status, int(retry), current + delay, row['task_key']))
        return {'next_status': status, 'same_root_cause_failures': failures, 'retry_permitted': retry}

    def _domain_finished(self, con, row, current, policy):
        next_at = current + policy['task_interval_seconds']
        con.execute('INSERT INTO m4_domains VALUES(?,?) ON CONFLICT(domain_key) DO UPDATE SET next_start_at=MAX(next_start_at,excluded.next_start_at)', (row['domain_key'], next_at))

    def finish_attempt(self, attempt_id, worker_id, lease_token, outcome, *, failure_class=None, root_cause=None, evidence=None, exact_images=None, now=None):
        if outcome not in ('collected_pending_review', 'rejected'):
            raise ValueError('生产只能保存待审或拒绝，不授予QC/客户PASS')
        evidence = evidence or []
        if evidence:
            verify_evidence(evidence)
        if outcome == 'rejected' and (failure_class not in FAILURES or not isinstance(root_cause, str) or not root_cause.strip()):
            raise ValueError('失败必须有分类与实际根因')
        if outcome == 'collected_pending_review' and (failure_class or root_cause or not evidence):
            raise ValueError('保存成功需要证据且不能带失败原因')
        history_proof = self._customer_history_proof() if outcome == 'collected_pending_review' else None
        current = timestamp(now)
        with self._transaction() as con:
            row = self._owned(con, attempt_id, worker_id, lease_token, current, terminal_ok=True)
            if row['status'] not in ACTIVE:
                if (row['status'], row['failure_class'], row['root_cause'], row['evidence_json']) != (outcome, failure_class, root_cause, canonical(evidence)):
                    raise ValueError('已终结attempt不可覆盖为另一结果')
                return self._view(row)
            if row['started_at'] is None:
                raise ValueError('未开始的预留不能记为真实执行结果')
            if outcome == 'collected_pending_review':
                from .admission_cohort import guard_scope
                guard_scope(con, self.registry, self.scope_id, history_proof=history_proof)
                from .production_identity import guard as page_guard, verify_saved
                task = json.loads(row['task_json'])
                page_guard(con, row['task_key'], task, required=self._policy(con).get('pilot_identity_required', False))
                verify_saved(task, row['sample_id'], evidence)
            if exact_images is not None:
                if outcome != 'collected_pending_review':
                    raise ValueError('精确图片声明只允许与成功保存同事务提交')
                checked = self._checked_images(exact_images, row['sample_id'])
                conflicts = []
                for path, digest in checked.items():
                    for other in con.execute('SELECT path,sample_id FROM m4_exact_images WHERE digest=? AND sample_id<>?',
                                             (digest, row['sample_id'])):
                        conflicts.append({'sha256': digest, 'current_image': path,
                                          'other_image': other['path'], 'other_sample_id': other['sample_id']})
                if conflicts:
                    raise ImageCommitConflict(conflicts)
                for path, digest in checked.items():
                    previous = con.execute('SELECT digest,sample_id FROM m4_exact_images WHERE path=?', (path,)).fetchone()
                    if previous and tuple(previous) != (digest, row['sample_id']):
                        raise ValueError('精确图片声明的原路径发生变化：' + path)
                    con.execute('INSERT OR IGNORE INTO m4_exact_images VALUES(?,?,?,?,?)',
                                (path, digest, row['sample_id'], attempt_id, current))
            policy = self._policy(con)
            con.execute('UPDATE m4_attempts SET status=?,finished_at=?,failure_class=?,root_cause=?,evidence_json=? WHERE attempt_id=?',
                        (outcome, current, failure_class, root_cause, canonical(evidence), attempt_id))
            saved = self._attempt(con, attempt_id)
            transition = {}
            if outcome == 'rejected':
                transition = self._failure_transition(con, saved, current, policy)
            else:
                con.execute('UPDATE m4_tasks SET status=? WHERE task_key=?', (outcome, row['task_key']))
            self._domain_finished(con, row, current, policy)
            self._event(con, 'attempt_finished', current, {'outcome': outcome, 'failure_class': failure_class, 'root_cause': root_cause, 'evidence': evidence, **transition}, row['task_key'], attempt_id)
            return self._view(saved)

    def recover_expired(self, *, now=None, reason='lease expired; prior process must not resume its trajectory'):
        current = timestamp(now)
        recovered = []
        with self._transaction() as con:
            policy = self._policy(con)
            ids = [r[0] for r in con.execute("SELECT attempt_id FROM m4_attempts WHERE scope_id=? AND status IN ('reserved','running') AND lease_expires_at<=?", (self.scope_id, current))]
            for attempt_id in ids:
                row = self._attempt(con, attempt_id)
                status = 'interrupted' if row['started_at'] is not None else 'abandoned'
                con.execute("UPDATE m4_attempts SET status=?,finished_at=?,failure_class='interrupted',root_cause='lease_expired' WHERE attempt_id=?", (status, current, attempt_id))
                saved = self._attempt(con, attempt_id)
                if row['started_at'] is not None:
                    transition = self._failure_transition(con, saved, current, policy)
                else:
                    con.execute("UPDATE m4_tasks SET status='queued',next_eligible_at=? WHERE task_key=?", (current, row['task_key']))
                    transition = {'next_status': 'queued', 'real_attempt': False}
                self._domain_finished(con, row, current, policy)
                self._event(con, 'lease_recovered', current, {'reason': reason, 'status': status, **transition}, row['task_key'], attempt_id)
                recovered.append(self._view(saved))
        return recovered

    @staticmethod
    def _checked_images(images, sample_id=None):
        import hashlib
        if not isinstance(images, dict) or not images:
            raise ValueError('精确图片声明必须为非空路径/SHA映射')
        checked = {}
        for name, digest in images.items():
            path = Path(name)
            resolved = path.resolve()
            if (not path.is_absolute() or resolved.suffix != '.png' or resolved.parent.name != 'images'
                    or (sample_id is not None and path.parent.parent.name != sample_id)
                    or (sample_id is not None and resolved.parent.parent.name != sample_id)
                    or not isinstance(digest, str) or len(digest) != 64
                    or hashlib.sha256(resolved.read_bytes()).hexdigest() != digest):
                raise ValueError('精确图片声明与原文件不一致：' + str(name))
            checked[str(resolved)] = digest
        return checked

    def register_exact_baseline(self, images, *, now=None):
        """Register observed legacy/committed images; never register in-flight captures.

        Existing paths are immutable. Capture claims are inserted only by
        finish_attempt in the same transaction that commits its success.
        """
        if not images:
            return
        current = timestamp(now)
        with self._transaction() as con:
            checked = self._checked_images(images)
            for path, digest in checked.items():
                sid = Path(path).parent.parent.name
                attempt = con.execute('SELECT attempt_id,status FROM m4_attempts WHERE sample_id=?', (sid,)).fetchone()
                if attempt and attempt['status'] != 'collected_pending_review':
                    continue
                previous = con.execute('SELECT digest,sample_id FROM m4_exact_images WHERE path=?', (path,)).fetchone()
                if previous and tuple(previous) != (digest, sid):
                    raise ValueError('已登记精确图片发生变化：' + path)
                con.execute('INSERT OR IGNORE INTO m4_exact_images VALUES(?,?,?,?,?)',
                            (path, digest, sid, attempt['attempt_id'] if attempt else None, current))

    def exact_image_claims(self):
        con = self._connect(readonly=True)
        try:
            return [dict(row) for row in con.execute('SELECT * FROM m4_exact_images ORDER BY path')]
        finally:
            con.close()

    def attempt_image_states(self):
        con = self._connect(readonly=True)
        try:
            return {row['sample_id']: row['status'] for row in con.execute('SELECT sample_id,status FROM m4_attempts')}
        finally:
            con.close()

    @contextmanager
    def exact_image_snapshot(self):
        """Fence only snapshot/commit boundaries, never browser execution."""
        with self._transaction() as con:
            states = {row['sample_id']: row['status'] for row in con.execute('SELECT sample_id,status FROM m4_attempts')}
            claims = [dict(row) for row in con.execute('SELECT * FROM m4_exact_images ORDER BY path')]
            yield states, claims

    def set_scope_paused(self, paused, reason, *, now=None):
        if type(paused) is not bool or not isinstance(reason, str) or not reason.strip():
            raise ValueError('暂停/恢复需要布尔值与真实原因')
        with self._transaction() as con:
            if self._scope(con)['state'] == 'closed_replanned':
                raise ValueError('scope已永久closed_replanned，禁止暂停或恢复')
            con.execute('UPDATE m4_scopes SET state=? WHERE scope_id=?', ('paused' if paused else 'active', self.scope_id))
            self._event(con, 'scope_paused' if paused else 'scope_resumed', timestamp(now), {'reason': reason})

    def close_failed_scope(self, output, reason, evidence, *, now=None, _fault=None):
        """Seal a paused, rejected-only scope without rewriting any capture file.

        SQLite is authoritative for outcomes and quota. Frozen files are checked
        against it, then their complete original inventory is bound in a new
        receipt. Only a prepared file exists before DB commit; the consumable
        closure.json is published afterwards. An orphan preparation is never
        silently adopted. A committed event can recover interrupted publication.
        Call the adapter's close_scope_for_replan to also hold the runner lock.
        """
        from .collect_runtime import runtime_scope
        from .production_quality import sha
        if not isinstance(reason, str) or not reason.strip() or not evidence:
            raise ValueError('关闭scope必须提供实际原因和不可变证据')
        verify_evidence(evidence)
        output = Path(output).resolve()
        if runtime_scope(output) != self.scope_id:
            raise ValueError('关闭输出路径与scope不一致')
        receipt_path = output / 'replanning' / 'closure.json'
        if output.is_symlink() or receipt_path.parent.is_symlink() or receipt_path.is_symlink():
            raise ValueError('关闭收据路径不能使用符号链接')
        with self._transaction() as con:
            scope = dict(self._scope(con))
            events = list(con.execute("SELECT payload_json FROM m4_events WHERE scope_id=? AND event_type='scope_closed_replanned'", (self.scope_id,)))
            if scope['state'] == 'closed_replanned':
                if len(events) != 1:
                    raise ValueError('已关闭scope缺少唯一关闭事件，须保留现场核账')
                binding = json.loads(events[0][0])
                if not receipt_path.exists():
                    prepared = Path(binding.get('prepared_path', ''))
                    if (prepared.parent != receipt_path.parent or prepared.is_symlink() or not prepared.is_file()
                            or sha(prepared) != binding.get('sha256')):
                        raise ValueError('已提交关闭事件缺少匹配prepared收据，须保留现场核账')
                    candidate = json.loads(prepared.read_text(encoding='utf-8'))
                    if candidate.get('reason') != reason or candidate.get('evidence_refs') != evidence:
                        raise ValueError('scope已关闭且原因或证据不同，禁止覆盖关闭记录')
                    verify_evidence(candidate['source_files'])
                    try:
                        os.link(prepared, receipt_path)
                    except FileExistsError:
                        if sha(receipt_path) != binding['sha256']:
                            raise ValueError('并发公开的closure收据SHA不一致')
                    prepared.unlink(missing_ok=True)
                if binding.get('path') != str(receipt_path) or binding.get('sha256') != sha(receipt_path):
                    raise ValueError('closure收据与数据库关闭事件SHA不一致')
                receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                if receipt['reason'] != reason or receipt['evidence_refs'] != evidence:
                    raise ValueError('scope已关闭且原因或证据不同，禁止覆盖关闭记录')
                verify_evidence(receipt['source_files'])
                verify_evidence(receipt['evidence_refs'])
                return {'already_closed': True, 'path': str(receipt_path), 'sha256': binding['sha256'], 'closure': receipt}
            if events or receipt_path.exists() or list(receipt_path.parent.glob('.closure-*.prepared.json')):
                raise ValueError('存在未匹配已提交关闭事件的closure收据；可能发生提交中断，保留现场核账')
            # A completed rejected-only batch has no remaining runner work to
            # pause. Its original final snapshot stays immutable; permit direct
            # closure only after the full terminal population checks below.
            terminal_failed_scope = scope['state'] == 'active'
            if scope['state'] not in ('paused', 'active'):
                raise ValueError('仅允许关闭已暂停且无在途的失败scope')
            rows = list(con.execute('SELECT * FROM m4_tasks WHERE scope_id=? ORDER BY created_at,task_id,task_version', (self.scope_id,)))
            tasks = [self._view(row) for row in rows]
            attempts = [self._view(self._attempt(con, row[0])) for row in con.execute('SELECT attempt_id FROM m4_attempts WHERE scope_id=? ORDER BY created_at,rowid', (self.scope_id,))]
            if terminal_failed_scope and (not tasks or not attempts
                    or any(row['status'] != 'needs_replan' for row in tasks)
                    or {row['task_key'] for row in tasks} != {row['task_key'] for row in attempts}):
                raise ValueError('仅允许关闭已暂停scope或全部已实际拒收的终结scope')
            if any(row['status'] in ACTIVE for row in attempts) or any(row['status'] in ACTIVE for row in tasks):
                raise ValueError('scope存在reserved/running在途attempt，禁止关闭')
            if any(row['started_at'] is None or row['status'] != 'rejected' or row['finished_at'] is None for row in attempts):
                raise ValueError('关闭要求每个已分配attempt均已真实开始且终结rejected；不能隐藏成功或未开始预留')
            if any(row['status'] not in ('queued', 'needs_replan') for row in tasks):
                raise ValueError('scope包含已保存成功或不可关闭任务状态')
            plans = list(con.execute('SELECT * FROM m4_plans WHERE scope_id=?', (self.scope_id,)))
            if len(plans) != 1:
                raise ValueError('关闭要求唯一冻结计划')
            plan = json.loads(plans[0]['plan_json'])
            manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            frozen_plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
            snapshot = json.loads((output / 'runtime-snapshot.json').read_text(encoding='utf-8'))
            if frozen_plan != plan or snapshot['scope'] != scope or snapshot['attempts'] != attempts or snapshot['tasks'] != tasks:
                raise ValueError('原plan/runtime快照与活动数据库身份或状态不匹配，禁止重写原文件掩盖漂移')
            if snapshot['policy'] != self._policy(con):
                raise ValueError('原runtime预算与数据库不同，须保留现场核账')
            keyed_tasks = {(row['task_id'], row['task_version']): row for row in tasks}
            if len(keyed_tasks) != len(plan['tasks']) or any(keyed_tasks.get((task['task_id'], task['task_version']), {}).get('task') != task for task in plan['tasks']):
                raise ValueError('原计划与数据库任务不构成同一完整全集')
            if manifest.get('runtime_scope_id') != self.scope_id or manifest.get('registry_path') != str(self.registry) or manifest.get('samples') or manifest.get('active_task') or manifest.get('reserved_attempts'):
                raise ValueError('原manifest含成功/在途/预留或输出绑定不匹配')
            expected_status = 'finished_pending_review' if terminal_failed_scope else 'paused_pending_resume'
            if manifest.get('collection_status') != expected_status:
                raise ValueError('原manifest不是已暂停待恢复状态')
            manifest_attempts = manifest.get('attempts', [])
            by_id = {row.get('attempt_id'): row for row in manifest_attempts}
            if len(by_id) != len(attempts) or len(by_id) != len(manifest_attempts):
                raise ValueError('原manifest真实attempt分母与数据库不一致')
            for attempt in attempts:
                original = by_id.get(attempt['attempt_id'], {})
                keys = ('attempt_id', 'task_id', 'task_version', 'sample_id', 'site_id', 'batch_id', 'retry_of', 'failure_class', 'root_cause')
                try:
                    original_started = datetime.fromisoformat(original['started_at'].replace('Z', '+00:00'))
                    # sync_manifest serializes SQLite floats to ISO microseconds;
                    # compare that same precision, not a lossy float round trip.
                    same_started = (original_started.tzinfo is not None and
                        original_started.astimezone(timezone.utc).isoformat() ==
                        datetime.fromtimestamp(attempt['started_at'], timezone.utc).isoformat())
                except (KeyError, TypeError, ValueError, AttributeError):
                    same_started = False
                if any(original.get(key) != attempt.get(key) for key in keys) or original.get('status') != 'rejected' or not original.get('error') or not same_started:
                    raise ValueError('原manifest的真实attempt身份、开始时间或拒收原因不匹配')
                if original.get('failure_evidence') != attempt['evidence']:
                    raise ValueError('原manifest拒收证据与数据库不一致')
                verify_evidence(attempt['evidence'])
            attempted = {(row['task_id'], row['task_version']) for row in attempts}
            unstarted = [{'task_id': task['task_id'], 'task_version': task['task_version'], 'plan_entry': task}
                         for task in plan['tasks'] if (task['task_id'], task['task_version']) not in attempted]
            if any(keyed_tasks[(row['task_id'], row['task_version'])]['status'] != 'queued' for row in unstarted):
                raise ValueError('零attempt任务必须仍为queued；其他历史状态须单独核账')
            roles = {'manifest.json': 'manifest', 'plan.json': 'plan', 'runtime-snapshot.json': 'runtime_snapshot',
                     'publication.json': 'publication', 'bootstrap.json': 'bootstrap'}
            sources = []
            for path in sorted(output.rglob('*')):
                if path.is_relative_to(receipt_path.parent):
                    continue
                if path.is_symlink():
                    raise ValueError('原批次含符号链接，不能冻结完整证据')
                if path.is_file():
                    sources.append({'role': roles.get(path.relative_to(output).as_posix(), 'capture_evidence'),
                                    'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size})
            receipt = {'schema_version': 'webcollect-runtime-scope-closure-1', 'closure_id': str(uuid.uuid4()),
                'scope_id': self.scope_id, 'campaign_id': scope['campaign_id'], 'batch_id': manifest['batch_id'],
                'closed_at': datetime.fromtimestamp(timestamp(now), timezone.utc).isoformat(), 'reason': reason, 'prior_scope_status': scope['state'],
                'final_scope_status': 'closed_replanned', 'source_files': sources, 'evidence_refs': evidence,
                'counts': {'planned_tasks': len(plan['tasks']), 'actual_attempts': len(attempts),
                           'rejected_attempts': len(attempts), 'saved_attempts': 0, 'inflight_attempts': 0,
                           'reserved_unstarted': 0, 'unstarted_tasks': len(unstarted)},
                'attempts': manifest_attempts, 'unstarted_tasks': unstarted, 'planned_tasks': plan['tasks'],
                'registry_attempt_ledger': attempts, 'registry_attempt_ledger_sha256': object_sha256(attempts),
                'registry_tasks_before': tasks, 'registry_policy': self._policy(con),
                'not_a_QC_approval': True, 'human_review': 'pending', 'customer_acceptance': 'UNKNOWN'}
            verify_evidence(sources)
            verify_evidence(evidence)
            if _fault:
                _fault('before_receipt')
            receipt_path.parent.mkdir(exist_ok=True)
            prepared_path = receipt_path.parent / ('.closure-' + receipt['closure_id'] + '.prepared.json')
            with prepared_path.open('x', encoding='utf-8') as handle:
                handle.write(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            if _fault:
                _fault('after_receipt_before_commit')
            con.execute("UPDATE m4_tasks SET status='needs_replan',quota_reserved=0 WHERE scope_id=?", (self.scope_id,))
            con.execute("UPDATE m4_scopes SET state='closed_replanned' WHERE scope_id=?", (self.scope_id,))
            binding = {'closure_id': receipt['closure_id'], 'path': str(receipt_path), 'sha256': sha(prepared_path),
                       'prepared_path': str(prepared_path),
                       'reason': reason, 'counts': receipt['counts']}
            self._event(con, 'scope_closed_replanned', timestamp(receipt['closed_at']), binding)
            verify_evidence(sources)
        if _fault:
            _fault('after_commit_before_publish')
        # link is an exclusive, atomic publication: facts never sees uncommitted closure.json.
        if not receipt_path.exists():
            try:
                os.link(prepared_path, receipt_path)
            except FileExistsError:
                if sha(receipt_path) != binding['sha256']:
                    raise ValueError('并发公开的closure收据SHA不一致')
            except FileNotFoundError:
                if not receipt_path.is_file() or sha(receipt_path) != binding['sha256']:
                    raise ValueError('已提交关闭收据公开中断，须使用相同命令核账恢复')
        elif sha(receipt_path) != binding['sha256']:
            raise ValueError('并发公开的closure收据SHA不一致')
        prepared_path.unlink(missing_ok=True)
        return {'already_closed': False, **binding, 'closure': receipt}

    def worker_session(self, worker_id, output, *, finished=False, now=None):
        """Count campaign worker wall time across invocations and output scopes.

        A process killed before its finish has an upper-bound duration ending at
        the next checkpoint, never a silently reset or zero running cost.
        """
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError('Worker session needs a stable identity')
        current = timestamp(now)
        with self._transaction() as con:
            scope = self._scope(con)
            if scope['state'] == 'closed_replanned':
                raise ValueError('scope已永久closed_replanned，禁止启动worker')
            events = [(row['event_type'], json.loads(row['payload_json'])) for row in con.execute(
                "SELECT event_type,payload_json FROM m4_events WHERE campaign_id=? AND event_type IN ('worker_started','worker_finished')",
                (scope['campaign_id'],))]
            own = [kind for kind, value in events if value.get('worker_id') == worker_id]
            expected = ['worker_started'] if finished else []
            if own != expected:
                raise ValueError('Worker session start/finish must be unique and ordered')
            self._event(con, 'worker_finished' if finished else 'worker_started', current,
                        {'worker_id': worker_id, 'output': str(Path(output).resolve())})

    def resource_checkpoint(self, output, *, now=None):
        """Fail closed before claiming another ID; preserve all evidence on stop."""
        import shutil
        current = timestamp(now)
        output = Path(output).resolve()
        with self._transaction() as con:
            scope = self._scope(con)
            if scope['state'] == 'closed_replanned':
                raise ValueError('scope已永久closed_replanned，禁止资源检查改变其状态')
            policy = self._policy(con)
            root = Path(policy.get('resource_root') or output).resolve()
            if not output.is_relative_to(root):
                raise ValueError('本输出不属于冻结resource_root，拒绝规避存储预算')
            disk_path = root
            while not disk_path.exists():
                disk_path = disk_path.parent
            free = shutil.disk_usage(disk_path).free
            files = list(root.rglob('*')) if root.exists() else []
            if any(path.is_symlink() for path in files):
                raise ValueError('resource_root含符号链接，无法完整核算存储')
            stored = sum(path.stat().st_size for path in files if path.is_file())
            sessions = {}
            for row in con.execute("SELECT event_type,at,payload_json FROM m4_events WHERE campaign_id=? AND event_type IN ('worker_started','worker_finished') ORDER BY event_id", (scope['campaign_id'],)):
                value = json.loads(row['payload_json'])
                session = sessions.setdefault(value['worker_id'], {})
                session['start' if row['event_type'] == 'worker_started' else 'finish'] = row['at']
            seconds = sum(max(0, session.get('finish', current) - session['start']) for session in sessions.values())
            reasons = []
            if policy.get('min_free_disk_bytes') is not None and free < policy['min_free_disk_bytes']:
                reasons.append('free_disk_below_minimum')
            if policy.get('max_output_bytes') is not None and stored >= policy['max_output_bytes']:
                reasons.append('campaign_storage_limit')
            if policy.get('max_worker_seconds') is not None and seconds >= policy['max_worker_seconds']:
                reasons.append('campaign_worker_time_limit')
            value = {'status': 'STOP' if reasons else 'PASS', 'reasons': reasons,
                'resource_root': str(root), 'free_disk_bytes': free, 'stored_bytes': stored,
                'campaign_worker_seconds': seconds,
                'open_sessions': [key for key, session in sessions.items() if 'finish' not in session],
                'unfinished_duration_is_upper_bound': True,
                'checkpoint': 'before_claim_next', 'sample_id_allocated_by_check': False}
            self._event(con, 'resource_checkpoint', current, value)
            if reasons:
                con.execute("UPDATE m4_scopes SET state='paused' WHERE scope_id=?", (self.scope_id,))
                self._event(con, 'scope_paused', current, {'reason': ','.join(reasons), 'resource_checkpoint': value})
            return value

    def plan_binding(self):
        """Read the frozen queue binding without creating a database or schema.

        A scope initialized immediately before a crash may not yet have a plan.
        Even an unstarted, abandoned allocation prevents bootstrap repair: its
        original manifest and source identity must remain independently bound.
        """
        con = self._connect(readonly=True)
        try:
            con.execute('BEGIN')
            scope = self._scope(con)
            plans = con.execute('SELECT * FROM m4_plans WHERE scope_id=?', (self.scope_id,)).fetchall()
            if len(plans) > 1:
                raise ValueError('同scope存在多个冻结计划，停止恢复并核账')
            row = plans[0] if plans else None
            count = con.execute('SELECT COUNT(*) FROM m4_attempts WHERE scope_id=?', (self.scope_id,)).fetchone()[0]
            return {'schema_version': 'webcollect-runtime-plan-binding-1', 'scope_id': self.scope_id,
                    'campaign_id': scope['campaign_id'], 'policy': self._policy(con),
                    'plan': json.loads(row['plan_json']) if row else None,
                    'publication': json.loads(row['publication_json']) if row else None,
                    'plan_sha256': row['plan_sha256'] if row else None,
                    'attempt_count': count, 'bootstrap_recoverable': count == 0}
        finally:
            con.close()

    def record_bootstrap_recovery(self, plan, publication, evidence, reason, *, now=None):
        """Audit reconstruction of initial files, never alter a frozen binding.

        The adapter must verify its bootstrap source/output/configuration receipt
        before writing files. This API fences recovery against any allocated
        attempt and records the actual completed recovery receipt by SHA.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('初始化恢复必须记录实际原因')
        verify_evidence(evidence)
        payload = {'plan_sha256': object_sha256(plan),
                   'publication_object_sha256': object_sha256(publication),
                   'evidence': evidence, 'reason': reason,
                   'attempt_count': 0, 'existing_bindings_unchanged': True}
        digest = object_sha256(payload)
        with self._transaction() as con:
            self._scope(con)
            if con.execute('SELECT 1 FROM m4_attempts WHERE scope_id=?', (self.scope_id,)).fetchone():
                raise ValueError('已有attempt或预留编号，不允许补写初始化文件')
            rows = con.execute('SELECT * FROM m4_plans WHERE scope_id=?', (self.scope_id,)).fetchall()
            if (len(rows) != 1 or json.loads(rows[0]['plan_json']) != plan or
                    json.loads(rows[0]['publication_json']) != publication):
                raise ValueError('初始化恢复输入与冻结计划/发布收据不匹配')
            for row in con.execute("SELECT event_id,payload_json FROM m4_events WHERE scope_id=? AND event_type='bootstrap_recovered'", (self.scope_id,)):
                if json.loads(row['payload_json']).get('recovery_sha256') == digest:
                    return {'event_id': row['event_id'], 'recovery_sha256': digest, 'already_recorded': True}
            self._event(con, 'bootstrap_recovered', timestamp(now), {**payload, 'recovery_sha256': digest})
            event_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
        return {'event_id': event_id, 'recovery_sha256': digest, 'already_recorded': False}

    def record_review(self, sample_id, decision, evidence, reason, *, now=None):
        """Record selection/quota decisions; retain the immutable raw capture.

        Rejection must not move, rewrite or delete the original batch sample.
        Export selects reviewed samples separately. A moved original deliberately
        fails collector resume integrity checks instead of receiving a new ID.
        This API never certifies reviewer identity or contract compliance.
        """
        if decision not in ('pass', 'reject') or not isinstance(reason, str) or not reason.strip():
            raise ValueError('审核需pass/reject和具体原因')
        report, qc_binding = _bound_quality_report(evidence)
        matching = [row for row in report['samples'] if row['sample_id'] == sample_id]
        allowed = ('PASS',) if decision == 'pass' else ('FAIL', 'REVIEW_REQUIRED')
        if len(matching) != 1 or matching[0].get('status') not in allowed:
            raise ValueError('审核决定必须与绑定QC报告中的该样本实际状态一致')
        current = timestamp(now)
        with self._transaction() as con:
            attempt = con.execute('SELECT attempt_id FROM m4_attempts WHERE sample_id=? AND scope_id=?', (sample_id, self.scope_id)).fetchone()
            if not attempt:
                raise ValueError('审核样本不属于本scope')
            row = self._attempt(con, attempt[0])
            if row['status'] != 'collected_pending_review':
                raise ValueError('仅成功保存的实际样本可进入审核')
            if decision == 'pass':
                from .production_identity import guard as page_guard, verify_saved, accept
                task = json.loads(row['task_json'])
                page_guard(con, row['task_key'], task, required=self._policy(con).get('pilot_identity_required', False))
                verify_saved(task, sample_id, json.loads(row['evidence_json']))
                accept(con, row['task_key'], task, sample_id)
            retention = {'raw_retained': True, 'capture_outcome': row['status'],
                         'selection_only': True, 'identity_authenticated': False,
                         'qc_binding': qc_binding, 'qc_sample_status': matching[0]['status']}
            old = con.execute('SELECT * FROM m4_reviews WHERE sample_id=?', (sample_id,)).fetchone()
            if old:
                if (old['decision'], old['evidence_json'], old['reason']) != (decision, canonical(evidence), reason):
                    raise ValueError('已有审核事件不可覆盖；变更需新候选版本与显式裁决')
                result = {**dict(old), **retention}
            else:
                con.execute('INSERT INTO m4_reviews VALUES(?,?,?,?,?)', (sample_id, decision, canonical(evidence), reason, current))
                status = 'reviewed_pass' if decision == 'pass' else 'needs_replan'
                con.execute('UPDATE m4_tasks SET status=?,quota_reserved=? WHERE task_key=?', (status, int(decision == 'pass'), row['task_key']))
                self._event(con, 'review_recorded', current, {'sample_id': sample_id, 'decision': decision, 'evidence': evidence, 'reason': reason, **retention}, row['task_key'], row['attempt_id'])
                result = {'sample_id': sample_id, 'decision': decision, **retention}
            site_guard = self._policy(con).get('site_failure_guard')
        if decision == 'pass' and site_guard:
            from .site_failure_stop import SiteFailureStore
            SiteFailureStore(site_guard).sync_successes(self.registry, self.snapshot()['scope']['campaign_id'])
        return result

    def record_qc_report(self, reference):
        """Register actual QC, retaining unresolved checks and immutable capture outcomes."""
        report, _ = _bound_quality_report([reference])
        with closing(self._connect(readonly=True)) as con:
            samples = {r['sample_id']: dict(r) for r in con.execute(
                'SELECT sample_id,task_key,evidence_json FROM m4_attempts WHERE scope_id=? '
                "AND status='collected_pending_review'", (self.scope_id,))}
        for row in report['samples']:
            sid = row['sample_id']
            if sid not in samples:
                continue
            status = row['status']
            if status not in ('PASS', 'FAIL', 'REVIEW_REQUIRED'):
                raise ValueError('Unsupported actual QC status')
            # Package/document checks must pass too before accepting a task.
            if status == 'PASS' and report.get('status') != 'PASS':
                status = 'REVIEW_REQUIRED'
            payload = {'sample_id': sid, 'status': status, 'report': reference}
            with closing(self._connect(readonly=True)) as con:
                prior = con.execute("SELECT 1 FROM m4_events WHERE scope_id=? AND task_key=? "
                    "AND event_type='pool_qc_result' AND payload_json=?",
                    (self.scope_id, samples[sid]['task_key'], canonical(payload))).fetchone()
                review = con.execute('SELECT decision FROM m4_reviews WHERE sample_id=?', (sid,)).fetchone()
            if prior:
                continue
            if status in ('PASS', 'FAIL'):
                decision = 'pass' if status == 'PASS' else 'reject'
                if review and review[0] != decision:
                    raise ValueError('Existing review cannot be overwritten; use an explicit replacement')
                if not review:
                    self.record_review(sid, decision, [reference], 'Automatic evidence-bound independent QC registration')
            with self._transaction() as con:
                self._event(con, 'pool_qc_result', timestamp(None), payload, samples[sid]['task_key'])
        self.sync_site_pool()

    def record_publication(self, release_id, sample_ids, evidence, *, now=None):
        if not isinstance(release_id, str) or not release_id.strip() or not isinstance(sample_ids, list) or not sample_ids or len(set(sample_ids)) != len(sample_ids):
            raise ValueError('发布需要稳定release_id与不重复sample_ids')
        report, qc_binding = _bound_quality_report(evidence)
        if (report.get('inspection_stage') != 'final' or report.get('delivery_status') != 'PASS'
                or report.get('release_ready') is not True):
            raise ValueError('发布必须绑定final阶段delivery_status PASS且release_ready=true的实际QC报告')
        sample_states = {row['sample_id']: row.get('status') for row in report['samples']}
        if any(sample_states.get(sid) != 'PASS' for sid in sample_ids):
            raise ValueError('发布样本必须全部包含在绑定最终QC报告且状态为PASS')
        content = {'sample_ids': sorted(sample_ids), 'evidence': evidence}
        digest = object_sha256(content)
        current = timestamp(now)
        with self._transaction() as con:
            policy = self._policy(con)
            old = con.execute('SELECT content_sha256 FROM m4_publications WHERE campaign_id=? AND release_id=?', (policy['campaign_id'], release_id)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('同release_id不能发布不同内容')
                return {'release_id': release_id, 'already_recorded': True, 'qc_binding': qc_binding,
                        'customer_acceptance': 'UNKNOWN'}
            tasks = []
            for sid in sample_ids:
                row = con.execute("SELECT t.task_key,t.status FROM m4_tasks t JOIN m4_attempts a ON a.task_key=t.task_key JOIN m4_reviews r ON r.sample_id=a.sample_id WHERE a.sample_id=? AND t.campaign_id=? AND a.status='collected_pending_review' AND r.decision='pass'", (sid, policy['campaign_id'])).fetchone()
                if not row or row['status'] not in ('reviewed_pass', 'published'):
                    raise ValueError('发布包含未审核或不属于campaign的样本')
                tasks.append(row['task_key'])
            con.execute('INSERT INTO m4_publications VALUES(?,?,?,?,?,?)', (policy['campaign_id'], release_id, digest, canonical(sorted(sample_ids)), canonical(evidence), current))
            for key in tasks:
                con.execute("UPDATE m4_tasks SET status='published' WHERE task_key=?", (key,))
            self._event(con, 'publication_recorded', current, {'release_id': release_id, 'content_sha256': digest, 'sample_ids': sorted(sample_ids), 'qc_binding': qc_binding, 'customer_acceptance': 'UNKNOWN'})
        return {'release_id': release_id, 'already_recorded': False, 'qc_binding': qc_binding,
                'customer_acceptance': 'UNKNOWN'}

    def snapshot(self):
        con = self._connect(readonly=True)
        try:
            scope = dict(self._scope(con))
            policy = self._policy(con)
            tasks = []
            for row in con.execute('SELECT * FROM m4_tasks WHERE scope_id=? ORDER BY created_at,task_id,task_version', (self.scope_id,)):
                item = dict(row); item['task'] = json.loads(item.pop('task_json')); tasks.append(item)
            attempts = [self._view(self._attempt(con, row[0])) for row in con.execute('SELECT attempt_id FROM m4_attempts WHERE scope_id=? ORDER BY created_at,rowid', (self.scope_id,))]
            events = []
            for row in con.execute('SELECT * FROM m4_events WHERE scope_id=? ORDER BY event_id', (self.scope_id,)):
                item = dict(row); item['payload'] = json.loads(item.pop('payload_json')); events.append(item)
            campaign_attempts = con.execute('SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=? AND started_at IS NOT NULL', (scope['campaign_id'],)).fetchone()[0]
            return {'schema_version': 'webcollect-runtime-snapshot-1', 'scope': scope, 'policy': policy,
                    'tasks': tasks, 'attempts': attempts, 'events': events,
                    'campaign_actual_attempt_count': campaign_attempts,
                    'site_pool': self.site_pool_binding(),
                    'QC_approval': False, 'customer_acceptance': 'UNKNOWN'}
        finally:
            con.close()

    def attempt_ledger(self):
        snapshot = self.snapshot()
        rows = snapshot['attempts']
        return {'schema_version': 'webcollect-runtime-attempts-1', 'scope_id': self.scope_id,
                'campaign_id': snapshot['scope']['campaign_id'],
                'attempts': [row for row in rows if row['started_at'] is not None],
                'reserved_attempts': [row for row in rows if row['started_at'] is None],
                'actual_attempt_count': sum(row['started_at'] is not None for row in rows),
                'reserved_allocation_count': sum(row['started_at'] is None for row in rows),
                'not_a_QC_approval': True}
