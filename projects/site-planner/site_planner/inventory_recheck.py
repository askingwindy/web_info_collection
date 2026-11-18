"""Producer inventory maintenance: lightweight re-check, culling and audit.

Pending claim-free candidates rot after publication (the 2026-11-06 consumer
experiment measured ~35% unreachable at dispatch time). This job re-verifies
them with plain GETs (no browser, no model), culls the definitely-dead, and
optionally samples a headless browser smoke or a category-hint audit. It only
touches producer-owned pool state; no claim, no consumer chain, no model call.

Access (plain GET), navigation and page observation keep separate results:
only a confirmed dead entry (hard 404/410, unresolvable host, browser-confirmed
entry 403) is culled; forensics/geometry failures, single timeouts and host
quirks stay strikes or observation-only notes and never become a permanent
dead page on their own.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
import asyncio
from webcollect import workspace_json as json
import random
import sqlite3
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15;7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HARD_DEAD_HTTP = (404, 410)
STRIKE_HTTP = (403, 429, 500, 502, 503, 504)
# A browser-confirmed 403 on the Table2 entry itself follows the established
# 2026-11-05 abandon rule; a plain GET 403 may still be bot filtering.
ENTRY_403_HTTP = 403

AUDIT_KEYWORDS = {
    '开发者站与 API 文档': ['api', 'docs', '文档', 'developer', '开发', 'sdk', 'reference', 'github', '编程'],
    '在线工具': ['计算', '转换', '工具', 'calculator', '在线', '生成', 'converter', '查询'],
    '图书文化': ['图书', '书', '图书馆', '博物馆', '文化', '展览', '馆藏', 'book', '文献'],
    '学习教育': ['课程', '学习', '教程', '教育', '培训', '考试', 'learn', 'course', '题'],
    '百科与文档': ['百科', 'wiki', '词条', 'encyclopedia', '知识'],
    '知识文库': ['文库', '文章', '专栏', '知识', '阅读', '期刊'],
    '金融股票交易': ['股票', '基金', '行情', '金融', '交易', '财经', '证券', '投资'],
    '新闻资讯': ['新闻', '资讯', '报道', '快讯', 'news', '头条', '日报'],
}


def _connect(pool_path):
    return workspace_connect(pool_path, timeout=90)


def _ensure_recheck_table(con):
    con.execute('''CREATE TABLE IF NOT EXISTS inventory_rechecks(
        id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, checked_at REAL NOT NULL,
        http_status INTEGER, verdict TEXT NOT NULL, error TEXT)''')
    con.execute('CREATE INDEX IF NOT EXISTS inventory_rechecks_candidate ON inventory_rechecks(candidate_id, id)')
    con.commit()


def _table_exists(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_rechecks'").fetchone())


def _pending_unclaimed(con, *, stale_hours, limit):
    cutoff = time.time() - stale_hours * 3600
    if not _table_exists(con):
        # A dry-run may read a pool that never had the auxiliary table; that is
        # indistinguishable from "never re-checked" for selection purposes.
        rows = con.execute(
            "SELECT c.candidate_id, c.body FROM data_candidates c "
            "WHERE c.state='pending' AND NOT EXISTS (SELECT 1 FROM candidate_claims cl WHERE cl.candidate_id=c.candidate_id) "
            "ORDER BY c.created").fetchall()
        return [(cid, json.loads(body).get('entry_url', '')) for cid, body in rows[:limit]]
    rows = con.execute(
        "SELECT c.candidate_id, c.body FROM data_candidates c "
        "WHERE c.state='pending' AND NOT EXISTS (SELECT 1 FROM candidate_claims cl WHERE cl.candidate_id=c.candidate_id) "
        "ORDER BY c.created").fetchall()
    selected = []
    for cid, body in rows:
        last = con.execute('SELECT checked_at FROM inventory_rechecks WHERE candidate_id=? ORDER BY id DESC LIMIT 1',
                           (cid,)).fetchone()
        if last and last[0] >= cutoff:
            continue
        selected.append((cid, json.loads(body).get('entry_url', '')))
        if len(selected) >= limit:
            break
    return selected


def _get_check(url, timeout):
    """Plain GET verdict: (verdict, http_status, error).

    DNS failure is a proved dead host. Certificates, refused connections,
    resets and client blocks are host-side quirks: a strike, never a cull.
    """
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 'ok', response.status, None
    except urllib.error.HTTPError as error:
        status = error.code
        if status in HARD_DEAD_HTTP:
            return 'dead_hard', status, None
        return 'strike', status, None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
        reason = f'{type(error).__name__}: {error}'
        inner = getattr(error, 'reason', None)
        text = f'{reason} / {inner}' if inner else reason
        if any(mark in text for mark in ('Name or service not known', 'nodename nor servname')):
            return 'dead_hard', None, text[:200]
        return 'strike', None, text[:200]


def _record(con, cid, verdict, status, error):
    con.execute('INSERT INTO inventory_rechecks(candidate_id, checked_at, http_status, verdict, error) VALUES(?,?,?,?,?)',
                (cid, time.time(), status, verdict, error))
    con.commit()


def _cull(con, cid, verdict, detail):
    """Producer-owned culling inside one short transaction.

    The UPDATE itself re-checks pending and claim-freedom: a claim that raced
    in after selection keeps the candidate and its claim untouched.
    """
    changed = con.execute(
        "UPDATE data_candidates SET state='failed' WHERE candidate_id=? AND state='pending' "
        "AND NOT EXISTS (SELECT 1 FROM candidate_claims cl WHERE cl.candidate_id=data_candidates.candidate_id)",
        (cid,)).rowcount
    if changed:
        con.execute("INSERT INTO candidate_events(candidate_id, claim_id, kind, record, created) VALUES(?,?,?,?,?)",
                    (cid, None, 'recheck_failed',
                     json.dumps({'verdict': verdict, **detail}, ensure_ascii=False), time.time()))
        con.commit()
    return bool(changed)


def _strike_is_second(con, cid):
    if not _table_exists(con):
        return False
    prev = con.execute('SELECT verdict FROM inventory_rechecks WHERE candidate_id=? ORDER BY id DESC LIMIT 1',
                       (cid,)).fetchone()
    return bool(prev and prev[0] == 'strike')


def _host_of(url):
    return urlsplit(url).hostname or ''


def _classify_navigation_failure(error):
    """Browser navigation errors keep their transport class, never geometry."""
    from playwright.async_api import Error as PlaywrightError
    if isinstance(error, PlaywrightError):
        message = str(error)
        if 'ERR_BLOCKED_BY_CLIENT' in message:
            return 'strike', None  # A client block proves interception, not a dead page.
        if 'net::ERR_NAME_NOT_RESOLVED' in message:
            return 'dead_hard', None
        return 'strike', None
    if isinstance(error, asyncio.TimeoutError) or isinstance(error, TimeoutError):
        return 'strike', None
    return 'strike', None


async def _smoke(urls, timeout):
    """Headless browser smoke for sampled GET-passed URLs.

    Reuses the consumer entry context (viewport/locale/timezone/service
    workers). One navigation plus one full observation per URL. The verdict
    separates navigation outcome from observation capability: this smoke proves
    navigation and DOM observation, not the full image/tree capture chain, so
    an observation failure is recorded as browser_observe_failed and never
    culled. Returns {url: (verdict, error, http_status)}.
    """
    from playwright.async_api import async_playwright
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720}, device_scale_factor=1,
                                            locale='zh-CN', timezone_id='Asia/Shanghai',
                                            service_workers='block', accept_downloads=False)
        page = await context.new_page()
        for url in urls:
            try:
                response = await page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')
                status = response.status if response else None
                if status in HARD_DEAD_HTTP:
                    results[url] = ('dead_hard', None, status)
                    continue
                if status == ENTRY_403_HTTP:
                    results[url] = ('entry_403', None, status)
                    continue
                if status is not None and status >= 400:
                    results[url] = ('strike', None, status)
                    continue
            except Exception as error:
                verdict, _ = _classify_navigation_failure(error)
                results[url] = (verdict, f'{type(error).__name__}: {error}'[:200], None)
                continue
            try:
                state = await asyncio.wait_for(_observe_state(page), timeout=timeout)
                results[url] = ('browser_ok' if (state or {}).get('visible_text') else 'browser_empty', None, None)
            except Exception as error:
                # Snapshot/geometry/stability faults are forensics limitations,
                # not dead pages; a single timeout is also not permanent.
                results[url] = ('browser_observe_failed', f'{type(error).__name__}: {error}'[:200], None)
        await context.close()
        await browser.close()
    return results


async def _observe_state(page):
    from webcollect.browser import observe
    state = await observe(page)
    return state


def run(pool_path, *, limit, stale_hours, timeout, host_interval, dry_run, smoke, audit, report_dir):
    pool_path = str(Path(pool_path).resolve())
    con = _connect(pool_path)
    if not dry_run:
        _ensure_recheck_table(con)
    report_dir = Path(report_dir) if report_dir else None
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
    tally = Counter(); culled = []; last_host = {}
    selected = _pending_unclaimed(con, stale_hours=stale_hours, limit=limit)
    print(f'recheck target: {len(selected)} pending claim-free candidates (stale>{stale_hours}h)', flush=True)
    smoke_urls, smoke_map = [], {}
    for cid, url in selected:
        if not url:
            tally['skip_no_url'] += 1
            continue
        host = _host_of(url)
        wait = host_interval - (time.time() - last_host.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        last_host[host] = time.time()
        verdict, status, error = _get_check(url, timeout)
        prev_strike = verdict == 'strike' and _strike_is_second(con, cid)
        if not dry_run:
            # Dry-run has zero side effects: verdict rows would otherwise arm
            # the next real run into an immediate second-strike cull.
            _record(con, cid, verdict, status, error)
        tally[verdict] += 1
        if verdict == 'dead_hard' or prev_strike:
            reason = verdict if verdict == 'dead_hard' else 'strike x2'
            if not dry_run:
                if _cull(con, cid, verdict, {'http_status': status, 'error': error, 'reason': reason, 'url': url}):
                    culled.append({'candidate_id': cid, 'url': url, 'verdict': verdict, 'http_status': status})
                    tally['culled'] += 1
            else:
                tally['would_cull'] += 1
        elif verdict == 'ok' and smoke > len(smoke_urls):
            smoke_urls.append(url)
            smoke_map[url] = cid
    print('recheck tally:', dict(tally), flush=True)

    smoke_results = {}
    if smoke_urls:
        smoke_results = asyncio.run(_smoke(smoke_urls, timeout=timeout))
        for url, (verdict, error, status) in smoke_results.items():
            cid = smoke_map[url]
            tally[verdict] += 1
            if not dry_run:
                _record(con, cid, verdict, status, error)
            # Only navigation-proved outcomes can retire a page: hard-dead and
            # the browser-confirmed entry 403. Observation failures and empty
            # pages stay recorded facts without culling.
            if verdict in ('dead_hard', 'entry_403') and not dry_run:
                if _cull(con, cid, verdict, {'http_status': status, 'error': error, 'url': url,
                                             'reason': ('browser_entry_403 (candidate-entry-403-user-rule-20261105)'
                                                        if verdict == 'entry_403' else 'browser hard dead')}):
                    culled.append({'candidate_id': cid, 'url': url, 'verdict': verdict, 'http_status': status})
                    tally['culled'] += 1
        print('smoke tally:', {k: v for k, v in tally.items() if k.startswith('browser') or k in ('entry_403', 'dead_hard')}, flush=True)

    audit_rows = []
    if audit:
        audited = 0; agreed = 0; hinted = 0
        sample = selected[:audit] if len(selected) >= audit else selected
        for cid, url in sample:
            hint = None
            row = con.execute("SELECT s.source FROM candidate_sources s WHERE s.candidate_id=? LIMIT 1", (cid,)).fetchone()
            if row:
                hint = json.loads(row[0]).get('category_hint')
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    html = response.read(200_000).decode('utf-8', 'replace').lower()
            except Exception as error:
                audit_rows.append({'candidate_id': cid, 'url': url, 'hint': hint, 'fetch': 'error',
                                   'error': f'{type(error).__name__}'[:60]})
                continue
            head = html[:12000]
            keywords = AUDIT_KEYWORDS.get(hint) or []
            hit = [k for k in keywords if k.lower() in head]
            if hint: hinted += 1
            if hit: agreed += 1
            audited += 1
            audit_rows.append({'candidate_id': cid, 'url': url, 'hint': hint,
                               'fetch': 'ok', 'keyword_hits': hit[:3]})
        print(f'audit: sampled {audited}, hinted {hinted}, keyword-agreed {agreed} '
              f'({agreed * 100 // max(audited, 1)}% of sampled)', flush=True)

    if report_dir:
        (report_dir / 'recheck-report.json').write_text(json.dumps({
            'pool': pool_path, 'dry_run': dry_run, 'selected': len(selected),
            'tally': dict(tally), 'culled': culled,
            'smoke': {u: v for u, v in smoke_results.items()},
            'audit_rows': audit_rows}, ensure_ascii=False, indent=1))
        print('report:', report_dir / 'recheck-report.json', flush=True)
    con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pool', required=True)
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--stale-hours', type=float, default=72.0)
    parser.add_argument('--timeout', type=int, default=15)
    parser.add_argument('--host-interval', type=float, default=2.0)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--smoke', type=int, default=0)
    parser.add_argument('--audit', type=int, default=0)
    parser.add_argument('--report-dir', default=None)
    args = parser.parse_args()
    run(args.pool, limit=args.limit, stale_hours=args.stale_hours, timeout=args.timeout,
        host_interval=args.host_interval, dry_run=args.dry_run, smoke=args.smoke, report_dir=args.report_dir)


if __name__ == '__main__':
    main()
