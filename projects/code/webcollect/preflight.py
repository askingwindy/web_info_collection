"""Read-only, evidence-bound candidate screening. No sample IDs or QC approval."""
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from .browser import fingerprint, observe, viewport_png
from .content_preparation import assess_content
from .storage import write_json

ROUTES = ('NORMAL_M1', 'PREPARE_RECHECK', 'DYNAMIC_CONTENT_TRACK', 'REVIEW_REQUIRED')
SOURCE_FILES = ('preflight.py', 'navigation.py', 'batch_core.py', 'media_preflight.py', 'media_preflight.js', 'browser.py',
                'content_preparation.py', 'content_preparation.js', 'snapshot.js',
                'collect.py', 'production_quality.py', 'task_contract.py', 'html_table_strategy.py',
                'qr_strategy.py', 'qr_pixel.py', 'placeholder_strategy.py', 'placeholder_pixel.py',
                'hmac_strategy.py', 'pbkdf2_strategy.py', 'task_generation.py', 'task_admission.py')


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def object_digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def pixel_change(before, after, threshold=8):
    """Measure two original diagnostic frames; this cannot identify an ad."""
    with Image.open(BytesIO(before)) as first, Image.open(BytesIO(after)) as last:
        if first.size != last.size:
            raise ValueError('预检帧分辨率不同，不能比较画面变化')
        delta = ImageChops.difference(first.convert('RGB'), last.convert('RGB'))
        bands = delta.split()
        maximum = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
        mask = maximum.point(lambda value: 255 if value > threshold else 0)
        count = mask.histogram()[255]
        return {'changed_fraction': count / (first.width * first.height),
                'changed_pixels': count, 'bbox': list(mask.getbbox()) if mask.getbbox() else None,
                'channel_difference_threshold': threshold,
                'interpretation': 'Pixel change only; cause, advertisement and task impact are not inferred.'}


def _files(root):
    found = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('预检证据不能包含符号链接')
        if path.is_file():
            found[path.relative_to(root).as_posix()] = digest(path)
    return found


async def _failure_viewport(page, directory, stem):
    """Keep partially loaded/error pages without claiming synchronized evidence."""
    meta = {'observed_at_utc': now(), 'url': page.url,
            'diagnostic_only': True, 'accepted_as_formal_frame': False}
    try:
        png, method = await asyncio.wait_for(viewport_png(page), timeout=5)
        (directory / (stem + '.png')).write_bytes(png)
        meta.update(screenshot_path=stem + '.png', screenshot_sha256=sha256(png).hexdigest(), screenshot=method)
    except Exception as failure:
        meta['capture_error'] = {'kind': type(failure).__name__, 'message': str(failure)}
    write_json(directory / (stem + '.json'), meta)
    return meta


def _limits(samples, interval_ms):
    if type(samples) is not int or not 2 <= samples <= 5:
        raise ValueError('预检 samples 必须为2至5整数')
    if type(interval_ms) is not int or not 100 <= interval_ms <= 2000:
        raise ValueError('预检 interval-ms 必须为100至2000整数')


async def inspect_page(page, task, directory, samples=3, interval_ms=400, url_check=None):
    """Inspect an already loaded page, without clicking, scrolling or playback changes.

    Also used against explicitly synthetic local fixtures. Public production
    navigation is validated by preflight_plan, never via a CLI bypass flag.
    """
    from .media_preflight import probe_media, summarize_preflight
    _limits(samples, interval_ms)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    probes, assessments, changes, frames = [], [], [], []
    previous = None
    operation = task.get('operations', [{}])[0]
    error = None
    entry = None
    try:
        if url_check:
            url_check(page.url)
        # First original viewport precedes the new media/content analysis.
        png, method = await asyncio.wait_for(viewport_png(page), timeout=25)
        (directory / 'initial.png').write_bytes(png)
        write_json(directory / 'initial.json', {
            'observed_at_utc': now(), 'url': page.url, 'screenshot': method,
            'screenshot_sha256': sha256(png).hexdigest(),
            'diagnostic_only': True, 'formal_synchronized_capture': False,
            'actions_executed': [], 'page_content_modified_by_preflight': False})
        for index in range(samples):
            if index:
                await asyncio.sleep(interval_ms / 1000)
            if url_check:
                url_check(page.url)
            entry = {'probe_index': index, 'started_at_utc': now(),
                     'diagnostic_only': True, 'accepted_as_formal_frame': False}
            entry['media_before'] = await probe_media(page, task)
            entry['content_before'] = await assess_content(page, task, operation)
            entry['state_before'] = await observe(page, operation.get('selector'), operation.get('index', 0))
            png, method = await asyncio.wait_for(viewport_png(page), timeout=25)
            filename = f'probe_{index:03d}.png'
            (directory / filename).write_bytes(png)
            entry['screenshot'] = method
            entry['screenshot_path'] = filename
            entry['screenshot_sha256'] = sha256(png).hexdigest()
            entry['state_after'] = await observe(page, operation.get('selector'), operation.get('index', 0))
            entry['media_after'] = await probe_media(page, task)
            if url_check:
                url_check(page.url)
            entry['before_fingerprint'] = fingerprint(entry['state_before'])
            entry['after_fingerprint'] = fingerprint(entry['state_after'])
            entry['DOM_consistent_in_diagnostic_pair'] = entry['before_fingerprint'] == entry['after_fingerprint']
            entry['ended_at_utc'] = now()
            write_json(directory / f'probe_{index:03d}.json', entry)
            probes.extend([entry['media_before'], entry['media_after']])
            assessments.append(entry['content_before'])
            if previous is not None:
                changes.append({'from_probe': index - 1, 'to_probe': index,
                                **pixel_change(previous, png)})
            previous = png
            frames.append({'path': filename, 'sha256': entry['screenshot_sha256'],
                           'raw_path': f'probe_{index:03d}.json'})
    except Exception as failure:
        error = {'kind': type(failure).__name__, 'message': str(failure),
                 'at_utc': now(), 'partial_probe_count': len(frames)}
        if entry is not None and len(frames) <= entry['probe_index']:
            write_json(directory / f"probe_{entry['probe_index']:03d}.partial.json",
                       {**entry, 'error': error, 'incomplete': True})
        if not (directory / 'initial.png').exists():
            await _failure_viewport(page, directory, 'initial_failure_capture')
        write_json(directory / 'failure.json', error)
    summary = summarize_preflight(probes, assessments, changes)
    if error:
        summary = {**summary, 'routing': 'REVIEW_REQUIRED', 'incomplete': True,
                   'probe_failure': error, 'routing_override': 'Incomplete evidence is not low risk.'}
    if summary.get('routing') not in ROUTES:
        raise ValueError('预检识别器返回未知 routing')
    result = {'schema_version': 'webcollect-page-preflight-1',
              'task_id': task['task_id'], 'site_uri': task['site_uri'],
              'initial_url': task['initial_url'], 'landed_url': page.url,
              'task_sha256': object_digest(task), 'requested_probe_count': samples,
              'completed_probe_count': len(frames), 'interval_ms': interval_ms,
              'elapsed_seconds': time.monotonic() - started,
              'pixel_changes': changes, 'frames': frames, 'summary': summary,
              'actions_executed': [], 'sample_ids_allocated': 0,
              'QC_executed': False, 'formal_delivery_sample': False,
              'human_review_count': 0, 'error': error}
    write_json(directory / 'result.json', result)
    return result


def schedule_plan(plan, records, report_path, report_sha256, preserve_order=False):
    if type(preserve_order) is not bool:
        raise ValueError('preserve_order 必须为布尔值')
    expected = {task['task_id']: object_digest(task) for task in plan['tasks']}
    actual = {record['task_id']: record['task_sha256'] for record in records}
    if len(records) != len(expected) or actual != expected:
        raise ValueError('预检必须对应全部原任务，不能遗漏、重复或更换任务')
    routes = {record['task_id']: record['summary']['routing'] for record in records}
    if any(route not in ROUTES for route in routes.values()):
        raise ValueError('未知预检分组')
    scheduled = deepcopy(plan)
    if not preserve_order:
        scheduled['tasks'].sort(key=lambda task: ROUTES.index(routes[task['task_id']]))
    scheduled['media_preflight'] = {
        'schema_version': 'webcollect-preflight-binding-1',
        'report_path': str(Path(report_path).resolve()), 'report_sha256': report_sha256,
        'all_original_tasks_retained': True, 'preserve_order': preserve_order,
        'routing_is_QC_acceptance': False}
    return scheduled


def validate_preflight_binding(plan, plan_path=None):
    """Reject altered, partial or stale scheduling hand-offs, never approve QC."""
    binding = plan.get('media_preflight')
    if binding is None:
        return
    if not isinstance(binding, dict) or binding.get('schema_version') != 'webcollect-preflight-binding-1':
        raise ValueError('预检绑定格式错误')
    path = Path(binding['report_path'])
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or digest(path) != binding['report_sha256']:
        raise ValueError('预检报告缺失或SHA变化')
    report = json.loads(path.read_text())
    if report.get('schema_version') != 'webcollect-preflight-report-1':
        raise ValueError('预检报告格式错误')
    if report.get('source_changed_during_run'):
        raise ValueError('预检运行中源码变化，不能交给正式采集')
    sources = report.get('source_files_sha256', {})
    if set(sources) != set(SOURCE_FILES) or any(digest(Path(__file__).parent / name) != value for name, value in sources.items()):
        raise ValueError('预检运行源码已变化，请重新预检')
    original_path = path.parent / 'input-plan.json'
    if digest(original_path) != report['input_plan_sha256']:
        raise ValueError('预检原始计划SHA变化')
    original = json.loads(original_path.read_text())
    if report.get('fixed_task_denominator') != len(original['tasks']):
        raise ValueError('预检分母与原任务数不一致')
    expected = schedule_plan(original, report['records'], path, binding['report_sha256'], binding['preserve_order'])
    if plan != expected:
        raise ValueError('采集计划与完整预检任务绑定不一致')
    excluded = {'report.json', 'scheduled-plan.json', 'manifest.json', 'SHA256SUMS'}
    actual_files = {p: s for p, s in _files(path.parent).items() if p not in excluded}
    if not actual_files or actual_files != report['evidence_files_sha256']:
        raise ValueError('预检证据清单不完整或文件已变化')
    for relative, value in report['evidence_files_sha256'].items():
        target = path.parent / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or target.is_symlink() or not target.resolve().is_relative_to(path.parent.resolve()):
            raise ValueError('预检证据路径越界')
        if not target.is_file() or digest(target) != value:
            raise ValueError('预检证据缺失或SHA变化：' + relative)
    for index, record in enumerate(report['records']):
        directory = record.get('evidence_directory')
        if directory != f'task_{index + 1:03d}':
            raise ValueError('预检任务证据目录缺失或顺序错误')
        result = path.parent / directory / 'result.json'
        if not result.exists():
            result = path.parent / directory / 'navigation_failure.json'
        if not result.is_file() or result.relative_to(path.parent).as_posix() not in actual_files:
            raise ValueError('预检任务原始结果缺失')
        saved = json.loads(result.read_text())
        if saved != {key: value for key, value in record.items() if key not in ['evidence_directory', 'cleanup_error']}:
            raise ValueError('预检任务结果与报告不一致')
        if not saved.get('error'):
            required = ['initial.png', 'initial.json']
            if len(saved.get('frames', [])) != saved.get('requested_probe_count'):
                raise ValueError('预检观察帧不足但未声明失败')
            for frame in saved['frames']:
                required.extend([frame['path'], frame['raw_path']])
            if any(f'{directory}/{name}' not in actual_files for name in required):
                raise ValueError('预检任务首图或观察帧缺失')


async def preflight_plan(plan_path, output, samples=3, interval_ms=400,
                         preserve_order=False, channel='chrome', headless=True, navigation=None):
    from playwright.async_api import async_playwright
    from .collect import validate_plan, verify_public_url
    from .production_quality import require_public_task_state
    _limits(samples, interval_ms)
    plan_path = Path(plan_path)
    source_input_bytes = plan_path.read_bytes()
    plan = json.loads(source_input_bytes)
    validate_plan(plan)
    if plan.get('media_preflight'):
        validate_preflight_binding(plan)
        raise ValueError('请使用原始计划重新预检，不叠加旧预检绑定')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('预检输出已存在，拒绝覆盖')
    output.mkdir(parents=True)
    write_json(output / 'input-plan.json', plan)
    source = Path(__file__).parent
    source_before = {name: digest(source / name) for name in SOURCE_FILES}
    write_json(output / 'source-before.json', source_before)
    started = time.monotonic()
    records = []
    from .collect import checkpoint_json
    progress = {'status': 'in_progress', 'fixed_task_denominator': len(plan['tasks']),
                'records': records, 'formal_delivery_samples': 0}
    checkpoint_json(output / 'progress.json', progress)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(channel=channel, headless=headless)
        browser_version = browser.version
        try:
            for index, task in enumerate(plan['tasks']):
                context = await browser.new_context(viewport={'width': 1280, 'height': 720},
                    device_scale_factor=1, locale='zh-CN', timezone_id='Asia/Shanghai')
                folder = output / f'task_{index + 1:03d}'
                page = None
                navigation_failure = None
                def check_url(url):
                    verify_public_url(url, {verify_public_url(task['site_uri']), *task.get('allowed_hosts', [])})
                    require_public_task_state({'url': url})
                try:
                    page = await context.new_page()
                    if navigation is None:
                        await page.goto(task['initial_url'], wait_until='domcontentloaded', timeout=30000)
                    else:
                        await navigation.goto(page, task['initial_url'], purpose='preflight:' + task['task_id'])
                    await asyncio.sleep(task.get('initial_settle_ms', 1000) / 1000)
                    record = await inspect_page(page, task, folder, samples, interval_ms, check_url)
                except Exception as failure:
                    navigation_failure = failure
                    folder.mkdir(parents=True, exist_ok=True)
                    record = {'task_id': task['task_id'], 'site_uri': task['site_uri'],
                              'initial_url': task['initial_url'], 'task_sha256': object_digest(task),
                              'summary': {'routing': 'REVIEW_REQUIRED', 'incomplete': True},
                              'error': {'kind': type(failure).__name__, 'message': str(failure)},
                              'QC_executed': False, 'formal_delivery_sample': False}
                    if page is not None:
                        record['diagnostic_capture'] = await _failure_viewport(page, folder, 'navigation_failure_capture')
                    write_json(folder / 'navigation_failure.json', record)
                finally:
                    try:
                        await asyncio.wait_for(context.close(), timeout=10)
                    except Exception as cleanup:
                        write_json(folder / 'context_cleanup_failure.json', {'error': str(cleanup)})
                        record['cleanup_error'] = str(cleanup)
                records.append({**record, 'evidence_directory': folder.name})
                checkpoint_json(output / 'progress.json', progress)
                from .batch_core import BudgetStop
                if isinstance(navigation_failure, BudgetStop):
                    raise navigation_failure
                print(json.dumps({'task_id': task['task_id'], 'routing': record['summary']['routing'],
                                  'error': record.get('error')}, ensure_ascii=False), flush=True)
                await asyncio.sleep(1)
        finally:
            try:
                await asyncio.wait_for(browser.close(), timeout=10)
            except Exception as cleanup:
                write_json(output / 'browser_cleanup_failure.json', {'error': str(cleanup)})
    progress['status'] = 'finished'
    checkpoint_json(output / 'progress.json', progress)
    source_after = {name: digest(source / name) for name in SOURCE_FILES}
    changed = [name for name in SOURCE_FILES if source_before[name] != source_after[name]]
    write_json(output / 'source-after.json', source_after)
    report = {'schema_version': 'webcollect-preflight-report-1', 'created_at_utc': now(),
              'input_plan_sha256': digest(output / 'input-plan.json'),
              'source_input_file_sha256': sha256(source_input_bytes).hexdigest(),
              'source_files_sha256': source_before, 'source_changed_during_run': changed,
              'configuration': {'viewport': [1280, 720], 'device_scale_factor': 1,
                  'locale': 'zh-CN', 'timezone': 'Asia/Shanghai', 'browser_version': browser_version,
                  'samples': samples, 'interval_ms': interval_ms},
              'fixed_task_denominator': len(plan['tasks']), 'records': records,
              'routing_counts': dict(Counter(r['summary']['routing'] for r in records)),
              'probe_errors': sum(bool(r.get('error')) for r in records),
              'total_elapsed_seconds_including_navigation_and_probes': time.monotonic() - started,
              'evidence_files_sha256': _files(output), 'all_original_tasks_retained': True,
              'actions_executed': [], 'sample_ids_allocated': 0, 'QC_executed': False,
              'scope': 'Read-only planning advice, not synchronized delivery evidence or QC approval.'}
    write_json(output / 'report.json', report)
    if changed:
        raise ValueError('预检运行中源码变化，证据已保留但不输出可采集计划：' + ','.join(changed))
    scheduled = schedule_plan(plan, records, output / 'report.json', digest(output / 'report.json'), preserve_order)
    write_json(output / 'scheduled-plan.json', scheduled)
    validate_preflight_binding(scheduled)
    write_json(output / 'manifest.json', {'schema_version': 'webcollect-preflight-manifest-1',
        'files_sha256': _files(output), 'sample_ids_allocated': 0, 'formal_delivery_samples': 0})
    (output / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in _files(output).items()))
    return {'output': str(output), 'task_count': len(records), 'routing_counts': report['routing_counts'],
            'probe_errors': report['probe_errors'], 'scheduled_plan': str(output / 'scheduled-plan.json'),
            'all_original_tasks_retained': True, 'QC_executed': False}
