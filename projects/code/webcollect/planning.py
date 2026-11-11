"""Versioned planning hand-offs; capability evidence never grants QC approval."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlsplit


CAPABILITY_REVIEW_RULES = {
    'version': 'capability-review',
    'checks': ['visible_chinese', 'chinese_controls', 'no_login_or_overlay',
               'task_capability_visible', 'exact_page_scope'],
    'ready_requires': 'all PASS', 'minimum_chinese_ratio': 0.7,
    'validity': 'cannot extend original observation expiry',
    'approval_scope': 'exact candidate capability only; not trajectory QC',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def object_sha256(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(value=None):
    if value is None:
        return time.time()
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('时间必须带时区')
        return parsed.timestamp()
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('时间必须为有限UTC时间戳或带时区ISO时间')
    return float(value)


def verify_evidence(evidence):
    """Check references/bytes, not whether an asserted semantic review occurred."""
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('必须提供真实证据引用')
    seen = set()
    for entry in evidence:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            raise ValueError('证据需要path和sha256')
        path = Path(entry['path'])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError('证据路径必须为已有绝对文件路径')
        if str(path.resolve()) in seen:
            raise ValueError('证据引用不得重复')
        seen.add(str(path.resolve()))
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            raise ValueError('证据SHA不匹配')


def _scoped_page_uris(record):
    """Enforce new exact-page records while preserving frozen legacy records."""
    if 'capability_scope' not in record:
        return None
    scope = record['capability_scope']
    if isinstance(scope, dict) and scope.get('kind') == 'observed-workflow-pages':
        from .observed_workflow import validate_scope
        return validate_scope(record)
    if (not isinstance(scope, dict) or set(scope) != {'kind', 'page_uris', 'sitewide'}
            or scope.get('kind') != 'exact-candidate-page' or scope.get('sitewide') is not False
            or scope.get('page_uris') != [record['site_uri']]):
        raise ValueError('精确页面能力范围必须仅包含候选URI且不能声明全站能力')
    uris = scope['page_uris']
    inventories, pages = record.get('capabilities'), record.get('representative_pages')
    if (not isinstance(inventories, list) or not isinstance(pages, list)
            or len(inventories) != 1 or len(pages) != 1
            or not isinstance(inventories[0], dict) or not isinstance(pages[0], dict)
            or inventories[0].get('page_uri') != uris[0] or pages[0].get('uri') != uris[0]):
        raise ValueError('能力范围与实际库存或代表页URI不一致')
    for page in (inventories[0], pages[0]):
        if any(page.get(name) not in (None, uris[0]) for name in ('requested_uri', 'landed_uri')):
            raise ValueError('精确页面能力不能复用其他请求或落地页面的证据')
    return set(uris)


def _validate_capability_review(record, current):
    """Recheck new review provenance at every publication; legacy records stay intact."""
    provenance = record['review_provenance']
    if not isinstance(provenance, dict) or provenance.get('schema_version') != 'capability-review-provenance':
        raise ValueError('能力复核来源协议错误')
    refs = [provenance[name] for name in ('catalog', 'packet', 'review')]
    verify_evidence(refs)
    if any(ref not in record['evidence'] for ref in refs):
        raise ValueError('能力复核文件必须进入发布证据链')
    original_catalog, packet, review = [json.loads(Path(ref['path']).read_text()) for ref in refs]
    originals = [r for r in original_catalog.get('records', [])
                 if r.get('capability_id') == record['capability_id']]
    if len(originals) != 1:
        raise ValueError('能力复核原始记录缺失或重复')
    original = originals[0]
    verify_evidence(original.get('evidence'))
    if (packet.get('schema_version') != 'capability-review-packet'
            or packet.get('catalog') != provenance['catalog']
            or packet.get('rules') != CAPABILITY_REVIEW_RULES
            or provenance.get('parent_version') != original['version']):
        raise ValueError('能力复核原目录、规则或父版本绑定不一致')
    if (review.get('schema_version') != 'capability-review'
            or review.get('packet_sha256') != provenance['packet']['sha256']
            or review.get('completed') is not True):
        raise ValueError('能力复核未完成或审核包摘要不匹配')
    reviewer = review.get('reviewer', {})
    if (not isinstance(reviewer.get('id'), str) or not reviewer['id'].strip()
            or reviewer.get('kind') not in ('human', 'session_ai')):
        raise ValueError('能力复核身份缺失或类型无效')
    if review.get('reviewed_at') is None:
        raise ValueError('能力复核缺少时间')
    reviewed = timestamp(review['reviewed_at'])
    if not timestamp(original['observed_at']) <= reviewed <= current:
        raise ValueError('能力复核时间不属于有效观察区间')
    binding = {'capability_id': original['capability_id'], 'original_version': original['version'],
               'record_sha256': object_sha256(original), 'site_uri': original['site_uri'],
               'inventory_sha256': object_sha256(original['capabilities']),
               'source_sha256': object_sha256(original['source']),
               'source_versions': [x.get('source_sha256') for x in original['source']],
               'rules_sha256': object_sha256(CAPABILITY_REVIEW_RULES)}
    items = [i for i in packet.get('records', []) if i.get('binding', {}).get('capability_id') == record['capability_id']]
    rows = [i for i in review.get('records', []) if i.get('binding', {}).get('capability_id') == record['capability_id']]
    if len(items) != 1 or len(rows) != 1 or items[0].get('binding') != binding or rows[0].get('binding') != binding:
        raise ValueError('能力复核页面、库存、来源或规则绑定不一致')
    row = rows[0]
    if (record['status'] != row.get('status') or record['reason'] != row.get('reason')
            or record['expires_at'] != row.get('expires_at')
            or not isinstance(row.get('reason'), str) or not row['reason'].strip()):
        raise ValueError('发布能力与实际复核结论不一致')
    expiry = timestamp(row['expires_at'])
    if not max(current, reviewed) < expiry <= timestamp(original['expires_at']):
        raise ValueError('能力复核已过期或非法延长原始有效期')
    mutable = {'status', 'reason', 'expires_at', 'version', 'evidence', 'screening',
               'prior_screening', 'review_provenance', 'QC_approval'}
    if ({k: v for k, v in record.items() if k not in mutable}
            != {k: v for k, v in original.items() if k not in mutable}):
        raise ValueError('复核不能扩展原始页面、动作或任务能力')
    expected_version = object_sha256({'parent_version': original['version'],
        'packet_sha256': provenance['packet']['sha256'], 'review_sha256': provenance['review']['sha256'],
        'capability_id': record['capability_id']})[:24]
    if record['version'] != expected_version or record.get('QC_approval') is not False:
        raise ValueError('复核能力版本无效或错误声明轨迹QC放行')
    if record.get('capability_scope') != {'kind': 'exact-candidate-page', 'page_uris': [record['site_uri']], 'sitewide': False}:
        raise ValueError('复核只能适用于精确观察页面')
    pages = row.get('pages')
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError('能力复核需要完整逐页观察')
    page = pages[0]
    images = sorted({e['sha256'] for e in original['evidence'] if Path(e['path']).suffix.lower() == '.png'})
    if (not images or page.get('uri') != original['site_uri'] or page.get('reviewed_image_sha256') != images
            or not isinstance(page.get('observations'), str) or not page['observations'].strip()):
        raise ValueError('能力复核缺少原图观察或页面不符')
    checks = page.get('checks')
    if (not isinstance(checks, dict) or set(checks) != set(CAPABILITY_REVIEW_RULES['checks'])
            or any(v not in ('PASS', 'FAIL', 'UNKNOWN') for v in checks.values())):
        raise ValueError('能力复核必需检查未完成')
    expected_screening = {'status': row['status'], 'reason': row['reason'],
        'page_observations': [page['observations']], 'review_source': reviewer['kind'],
        'reviewer': reviewer, 'reviewed_at': review['reviewed_at']}
    if record.get('screening') != expected_screening or record.get('prior_screening') != original.get('screening'):
        raise ValueError('能力复核身份或观察与冻结记录不一致')
    if record['status'] == 'ready':
        mechanical = original['representative_pages'][0]
        if (any(v != 'PASS' for v in checks.values()) or original['status'] == 'rejected'
                or mechanical.get('accessible') is not True or mechanical.get('rendered') is not True
                or mechanical.get('error') or mechanical.get('routing') != 'NORMAL_M1'
                or mechanical.get('chinese_ratio', 0) < 0.7):
            raise ValueError('能力复核未消除原始门禁，不能发布ready')


def validate_capability(record, *, now=None, require_ready=True):
    if not isinstance(record, dict) or record.get('schema_version') != 'site-capability':
        raise ValueError('能力记录schema错误')
    for name in ('capability_id', 'version', 'site_uri', 'site_category'):
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise ValueError('能力记录缺少' + name)
    url = urlsplit(record['site_uri'])
    if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
        raise ValueError('能力URI必须为无凭据HTTP(S)地址')
    observed, expires = timestamp(record.get('observed_at')), timestamp(record.get('expires_at'))
    current = timestamp(now)
    if record.get('observed_at') is None or record.get('expires_at') is None or observed > current or expires <= observed:
        raise ValueError('能力记录实测/失效时间无效')
    if record.get('status') not in ('ready', 'review_required', 'rejected'):
        raise ValueError('能力状态无效')
    if record['status'] != 'ready' and (not isinstance(record.get('reason'), str) or not record['reason'].strip()):
        raise ValueError('待审/拒绝能力必须保存实际原因')
    for name in ('supported_actions', 'task_families'):
        values = record.get(name)
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
            raise ValueError('能力记录需要非重复的' + name)
    from .validate import CONTROL, NONCONTROL
    if not set(record['supported_actions']) <= CONTROL | NONCONTROL | {'hotkey'}:
        raise ValueError('能力记录包含动作空间以外的动作')
    _scoped_page_uris(record)
    if 'site_qualification' in record:
        from site_planner.qualification import validate_qualification
        qualification = validate_qualification(record)
        if record['status'] != qualification['status']:
            raise ValueError('站点状态与绑定的资格判断不一致')
    if 'observed_workflow_parent' in record:
        from .observed_workflow import validate_derived_capability
        validate_derived_capability(record, now=current if require_ready else None)
    if require_ready and (record['status'] != 'ready' or expires <= current):
        raise ValueError('站点能力尚待审核、被拒绝或已过期')
    verify_evidence(record.get('evidence'))
    if ('review_provenance' in record or 'prior_screening' in record
            or record.get('screening', {}).get('review_source') in ('human', 'session_ai')):
        if 'review_provenance' not in record:
            raise ValueError('新能力复核记录缺少持久来源证明')
        _validate_capability_review(record, current)
    return deepcopy(record)


def is_probe_failure(record):
    return (record.get('schema_version') in ('site-probe-failure', 'webcollect-site-probe-failure-1')
            or not record.get('schema_version') and bool(record.get('error_message')))


def _records(capabilities):
    if isinstance(capabilities, dict):
        if capabilities.get('schema_version') not in ('capability-catalog','webcollect-capability-catalog-1'):
            raise ValueError('能力目录schema错误')
        capabilities = capabilities.get('records')
    if not isinstance(capabilities, list):
        raise ValueError('能力目录必须包含records数组')
    result = {}
    for record in capabilities:
        if not isinstance(record, dict):
            raise ValueError('能力目录项必须为对象')
        if is_probe_failure(record):
            if not record.get('reason') or not record.get('site_uri'):
                raise ValueError('失败能力记录必须保留原原因和页面')
            continue
        key = (record.get('capability_id'), record.get('version'))
        if not all(isinstance(v, str) and v for v in key) or key in result:
            raise ValueError('能力版本缺失或重复')
        result[key] = record
    return result


def publish_plan(plan, capabilities, *, now=None, require_preflight=True):
    """Return an immutable receipt. Does not save a file or allocate any IDs.

    Tasks add capability_id, capability_version and task_family to the existing
    M4 contract. The original preflight retains the full task denominator.
    """
    from .task_admission import frame_validation_scope
    with frame_validation_scope():
        receipt, prepared = _build_publication(plan, capabilities, now=now,
                                               require_preflight=require_preflight)
    # Preserve publication's existing advisory task exclusion. Verification
    # below only inspects the prepared copy and never edits its input plan.
    if prepared['tasks'] != plan['tasks']:
        plan['tasks'] = prepared['tasks']
    return receipt


def _build_publication(plan, capabilities, *, now=None, require_preflight=True):
    """Validate current bindings and derive a receipt without editing inputs."""
    from .collect import validate_plan
    from .preflight import validate_preflight_binding
    from .react_session import is_react_task
    if not isinstance(plan, dict) or plan.get('schema_version') != 'plan-m4':
        raise ValueError('规划发布仅接受严格M4计划')
    plan = deepcopy(plan)
    validate_plan(plan)
    # React sessions preflight the already-open entry page inside their own
    # browser session (same-context requirement); an outer preflight binding
    # would re-open the site in a second context before any action.
    react_only = bool(plan['tasks']) and all(is_react_task(task) for task in plan['tasks'])
    if react_only and plan.get('media_preflight'):
        raise ValueError('React 计划在同会话内预检，不携带外部预检绑定')
    if not react_only and (not require_preflight or not plan.get('media_preflight')):
        raise ValueError('M4计划发布不能跳过正式预检绑定')
    if plan.get('media_preflight'):
        validate_preflight_binding(plan)
        report = json.loads(Path(plan['media_preflight']['report_path']).read_text())
        if any(row.get('error') for row in report['records']):
            raise ValueError('预检仍有失败任务，必须重新规划并保留原分母')
        # Advisory review routing excludes only that task; the denominator and the
        # retained preflight report keep the risk visible for post-hoc QC.
        advisory = {row.get('task_id') for row in report['records']
                    if row.get('summary', {}).get('routing') == 'REVIEW_REQUIRED'}
        if advisory:
            from .fragment_workflow import is_fragment
            blocked = {task['task_id'] for task in plan['tasks'] if task['task_id'] in advisory and is_fragment(task)}
            if blocked:
                plan['tasks'] = [task for task in plan['tasks'] if task['task_id'] not in blocked]
            if any(task_id in advisory and task_id not in blocked for task_id in advisory):
                raise ValueError('非片段任务的预检待审仍须重新规划并保留原分母')
        if not plan['tasks']:
            raise ValueError('预检待审排除后无可派发任务，保留原分母')
    catalog = _records(capabilities)
    current = timestamp(now)
    # Retain the supplied candidate denominator, including rejected/expired sites.
    # Their status is not a permission to execute a task, but must not disappear
    # simply because this publication only chooses ready capabilities.
    catalog_records = [validate_capability(record, now=current, require_ready=False)
                       for record in catalog.values()]
    used, tasks = {}, []
    for task in plan['tasks']:
        key = (task.get('capability_id'), task.get('capability_version'))
        if not all(isinstance(value, str) and value for value in key) or key not in catalog:
            raise ValueError('任务缺少精确版本的站点能力记录')
        if 'candidate_binding' in task:
            from .candidate_contract import validate_task_binding, guard_claim
            validate_task_binding(task, catalog[key]); guard_claim(task)
            capability = validate_capability(catalog[key], now=current, require_ready=False)
            if (task.get('fragment',{}).get('ending_policy') not in ('webcollect-continuous-attempt-ending-4', 'webcollect-five-ten-effective-ending-5', 'webcollect-five-eight-complete-ending-6')
                    and timestamp(capability['expires_at']) <= current):
                raise ValueError('Consumer observation expired')
        elif is_react_task(task):
            # React URL entries qualify inside their own session preflight;
            # the catalog record is a host-bound placeholder capability.
            capability = validate_capability(catalog[key], now=current, require_ready=False)
            if timestamp(capability['expires_at']) <= current:
                raise ValueError('React entry capability expired')
        else:
            capability = validate_capability(catalog[key], now=current)
        if not is_react_task(task):
            from .workflow_proposal import verify_task
            verify_task(task, capability)
        if (capability['site_uri'], capability['site_category']) != (task['site_uri'], task['site_category']):
            raise ValueError('任务URI/类目与能力记录不一致')
        page_uris = _scoped_page_uris(capability)
        if page_uris is not None and task['initial_url'] not in page_uris:
            raise ValueError('任务初始页面未包含在实际观察的精确能力范围中')
        if task.get('task_family') not in capability['task_families']:
            raise ValueError('任务族未在实际能力记录中登记')
        actions = {op['action_type'] for op in task['operations']} - {'wait', 'complete'}
        from .agent_controller import is_controlled
        if is_controlled(task):
            actions = set(task['fragment']['allowed_actions']) - {'set_value'}
            if 'set_value' in task['fragment']['allowed_actions']:
                actions |= {'click','hotkey','type'}
        if not actions <= set(capability['supported_actions']):
            raise ValueError('任务要求未验证的站点动作能力')
        used[key] = capability
        tasks.append({'task_id': task['task_id'], 'task_version': task['task_version'],
                      'task_sha256': object_sha256(task), 'capability_id': key[0],
                      'capability_version': key[1], 'capability_sha256': object_sha256(capability),
                      'capability_expires_at': timestamp(capability['expires_at'])})
    receipt = {'schema_version': 'plan-publication', 'published_at': current,
               'plan_sha256': object_sha256(plan), 'task_count': len(tasks), 'tasks': tasks,
               'capabilities': list(used.values()),
               'preflight_report_sha256': (plan['media_preflight']['report_sha256']
                                           if plan.get('media_preflight') else None),
               'capability_catalog': catalog_records,
               'capability_catalog_sha256': object_sha256(catalog_records),
               'capability_candidate_count': len(capabilities.get('records', [])) if isinstance(capabilities, dict) else len(capabilities),
               'probe_failures': [record for record in (capabilities.get('records', []) if isinstance(capabilities, dict) else capabilities)
                                  if is_probe_failure(record)],
               'sample_ids_allocated': 0, 'QC_approval': False}
    receipt['publication_sha256'] = object_sha256(receipt)
    return receipt, plan


def verify_publication(plan, publication, *, now=None):
    from .task_admission import frame_validation_scope
    with frame_validation_scope():
        return _verify_publication(plan, publication, now=now)


def _verify_publication(plan, publication, *, now=None):
    if not isinstance(publication, dict) or publication.get('schema_version') != 'plan-publication':
        raise ValueError('计划发布收据格式错误')
    body = {k: v for k, v in publication.items() if k != 'publication_sha256'}
    if publication.get('publication_sha256') != object_sha256(body):
        raise ValueError('计划发布收据SHA不一致')
    # Recheck actual evidence and current expiry; publishing is not a permanent permit.
    catalog = list(publication.get('capability_catalog') or []) + list(publication.get('probe_failures', []))
    expected, _ = _build_publication(plan, catalog, now=now)
    for key in ('plan_sha256', 'task_count', 'tasks', 'capabilities', 'preflight_report_sha256',
                'capability_catalog', 'capability_catalog_sha256', 'capability_candidate_count',
                'sample_ids_allocated', 'QC_approval'):
        if publication.get(key) != expected.get(key):
            raise ValueError('计划发布绑定已改变：' + key)
    if timestamp(publication.get('published_at')) > timestamp(now):
        raise ValueError('计划发布时点晚于执行时点')
    return publication
