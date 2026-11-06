"""Producer inventory maintenance: lightweight re-check, culling and audit.

Pending claim-free candidates rot after publication (the 2026-11-06 consumer
experiment measured ~35% unreachable at dispatch time). This job re-verifies
them with plain GETs (no browser, no model), culls the definitely-dead, and
optionally samples a headless browser smoke or a category-hint audit. It only
touches producer-owned pool state; no claim, no consumer chain, no model call.
"""
import argparse
import asyncio
import json
import random
import sqlite3
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HARD_DEAD_HTTP = (404, 410)
STRIKE_HTTP = (403, 429, 500, 502, 503, 504)

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
    return sqlite3.connect(pool_path, timeout=30)


def _ensure_recheck_table(con):
    con.execute('''CREATE TABLE IF NOT EXISTS inventory_rechecks(
        id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, checked_at REAL NOT NULL,
        http_status INTEGER, verdict TEXT NOT NULL, error TEXT)''')
    con.execute('CREATE INDEX IF NOT EXISTS inventory_rechecks_candidate ON inventory_rechecks(candidate_id, id)')
    con.commit()


def _pending_unclaimed(con, *, stale_hours, limit):
    cutoff = time.time() - stale_hours * 3600
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
    """Plain GET verdict: (verdict, http_status, error)."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 'ok', response.status, None
    except urllib.error.HTTPError as error:
        status = error.code
        if status in HARD_DEAD_HTTP:
            return 'dead_hard', status, None
        if status in STRIKE_HTTP:
            return 'strike', status, None
        return 'strike', status, None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
        reason = f'{type(error).__name__}: {error}'
        inner = getattr(error, 'reason', None)
        text = f'{reason} / {inner}' if inner else reason
        if any(mark in text for mark in ('Name or service not known', 'nodename nor servname',
                                         'CERTIFICATE', 'ssl', 'SSL', ' Connection refused')):
            return 'dead_hard', None, text[:200]
        return 'strike', None, text[:200]


def _record(con, cid, verdict, status, error):
    con.execute('INSERT INTO inventory_rechecks(candidate_id, checked_at, http_status, verdict, error) VALUES(?,?,?,?,?)',
                (cid, time.time(), status, verdict, error))
    con.commit()


def _cull(con, cid, verdict, detail):
    """Producer-owned culling: pending -> failed, with an audit event."""
    changed = con.execute("UPDATE data_candidates SET state='failed' WHERE candidate_id=? AND state='pending'",
                          (cid,)).rowcount
    if changed:
        con.execute("INSERT INTO candidate_events(candidate_id, claim_id, kind, record, created) VALUES(?,?,?,?,?)",
                    (cid, None, 'recheck_failed',
                     json.dumps({'verdict': verdict, **detail}, ensure_ascii=False), time.time()))
        con.commit()
    return bool(changed)


def _strike_is_second(con, cid):
    prev = con.execute('SELECT verdict FROM inventory_rechecks WHERE candidate_id=? ORDER BY id DESC LIMIT 1',
                       (cid,)).fetchone()
    return bool(prev and prev[0] == 'strike')


def _host_of(url):
    return urlsplit(url).hostname or ''


async def _smoke(urls, timeout):
    """Headless browser smoke for sampled GET-passed URLs: navigation and one
    observation, no model. Returns {url: (verdict, error)}."""
    from playwright.async_api import async_playwright
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        page = await browser.new_page()
        for url in urls:
            try:
                await page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')
                state = await asyncio.wait_for(_observe_state(page), timeout=timeout)
                results[url] = ('browser_ok' if (state or {}).get('visible_text') else 'browser_empty', None)
            except Exception as error:
                results[url] = ('browser_dead', f'{type(error).__name__}: {error}'[:200])
        await browser.close()
    return results


async def _observe_state(page):
    from webcollect.browser import observe
    state = await observe(page)
    return state


def run(pool_path, *, limit, stale_hours, timeout, host_interval, dry_run, smoke, audit, report_dir):
    pool_path = str(Path(pool_path).resolve())
    con = _connect(pool_path)
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
        for url, (verdict, error) in smoke_results.items():
            cid = smoke_map[url]
            _record(con, cid, verdict, None, error)
            tally[verdict] += 1
            if verdict == 'browser_dead' and not dry_run:
                if _cull(con, cid, verdict, {'error': error, 'url': url}):
                    culled.append({'candidate_id': cid, 'url': url, 'verdict': verdict})
                    tally['culled'] += 1
        print('smoke tally:', {k: v for k, v in tally.items() if k.startswith('browser')}, flush=True)

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
        host_interval=args.host_interval, dry_run=args.dry_run, smoke=args.smoke,
        audit=args.audit, report_dir=args.report_dir)


if __name__ == '__main__':
    main()
