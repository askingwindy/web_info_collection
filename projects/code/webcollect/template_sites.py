"""Per-site confirmed template registry fed only by formal saves.

A (site, template) pair is registered once three DISTINCT pages carried that
template through a verified formal save: ``candidate_results`` rows exist only
after ``candidate_consumer.finish_or_reconcile`` committed a verified save, so
fixtures, model-complete intermediates and unfinished attempts can never count
here. Re-running or re-saving the same page counts once (DISTINCT
candidate_id); no export/QC gate is added. All access uses the pool's own
short-transaction helpers and tolerates a missing table on read.
"""
import sqlite3
from datetime import datetime, timezone

from .planning import canonical

# Same literal as site_planner.candidate_pool.TEMPLATE_SITES_DDL; kept local so
# this module stays the single webcollect-side owner of its queries.
DDL = '''CREATE TABLE IF NOT EXISTS template_sites(template_name TEXT NOT NULL, application_id TEXT NOT NULL,
  site_url TEXT, sample_ids TEXT NOT NULL, confirmed_at TEXT NOT NULL,
  PRIMARY KEY(template_name, application_id))'''

CONFIRM_THRESHOLD = 3


def ensure_table(pool):
    """Idempotent create; True only when this call created the table."""
    with pool.pool.connect() as con:
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='template_sites'").fetchone():
            return False
    with pool.transaction() as con:
        con.execute(DDL)
    return True


def confirmed_templates(pool, application_id):
    """Ordered template names confirmed for one site; missing table reads as []."""
    if not application_id:
        return []
    try:
        with pool.pool.connect() as con:
            rows = con.execute('SELECT template_name FROM template_sites WHERE application_id=? '
                               'ORDER BY template_name', (application_id,)).fetchall()
    except sqlite3.Error:
        # Read-only consumers must never fail on a pool that lacks the table.
        return []
    return [row[0] for row in rows]


def distinct_saved_pages(pool, application_id, template_name=None):
    """DISTINCT formally saved candidate pages for one site (optionally one template)."""
    sql = ('SELECT COUNT(DISTINCT r.candidate_id) FROM candidate_results r '
           'JOIN data_candidates c ON c.candidate_id=r.candidate_id '
           'WHERE c.application_id=? AND r.effective=1')
    params = [application_id]
    if template_name is not None:
        sql += " AND json_extract(r.record,'$.template_name')=?"
        params.append(template_name)
    with pool.pool.connect() as con:
        return con.execute(sql, params).fetchone()[0]


def site_saved_pages(pool, application_id):
    """Formally saved pages of one site for progress logging (newest last)."""
    sql = ("SELECT r.candidate_id, r.sample_id, r.claim_id, "
           "json_extract(r.record,'$.template_name') FROM candidate_results r "
           'JOIN data_candidates c ON c.candidate_id=r.candidate_id '
           'WHERE c.application_id=? AND r.effective=1 ORDER BY r.rowid')
    with pool.pool.connect() as con:
        return [{'candidate_id': row[0], 'sample_id': row[1], 'claim_id': row[2],
                 'template_name': row[3]} for row in con.execute(sql, (application_id,))]


def record_save(pool, claim, saved_result):
    """Register (site, template) after a verified save; never re-saves twice.

    ``saved_result`` is the verified-save dict returned inside
    finish_or_reconcile's result. A duplicate concurrent registration resolves
    to already-registered (INSERT OR IGNORE / IntegrityError); registration
    failures never change the save outcome—the caller wraps this call.
    """
    template_name = saved_result.get('template_name')
    candidate_id = claim['candidate_id']
    with pool.pool.connect() as con:
        row = con.execute('SELECT application_id FROM data_candidates WHERE candidate_id=?',
                          (candidate_id,)).fetchone()
        if row is None:
            raise ValueError('Saved candidate missing from pool: ' + candidate_id)
        application_id = row[0]
        site = con.execute('SELECT host FROM applications WHERE id=?', (application_id,)).fetchone()
    ensure_table(pool)
    if template_name is None:
        # Historical records without the frozen template marker count toward
        # the site total only; they never register a template.
        return {'application_id': application_id, 'template_name': None,
                'pages': distinct_saved_pages(pool, application_id),
                'reached_three': False, 'registered': False, 'sample_ids': []}
    pages = distinct_saved_pages(pool, application_id, template_name)
    sample_ids = []
    registered = False
    if pages >= CONFIRM_THRESHOLD:
        seen = set()
        with pool.pool.connect() as con:
            existing = con.execute('SELECT 1 FROM template_sites WHERE template_name=? AND application_id=?',
                                   (template_name, application_id)).fetchone()
            if not existing:
                for row in con.execute(
                        "SELECT r.candidate_id, r.sample_id FROM candidate_results r "
                        'JOIN data_candidates c ON c.candidate_id=r.candidate_id '
                        'WHERE c.application_id=? AND r.effective=1 '
                        "AND json_extract(r.record,'$.template_name')=? ORDER BY r.rowid",
                        (application_id, template_name)):
                    if row[0] in seen:
                        continue
                    seen.add(row[0])
                    sample_ids.append(row[1])
                    if len(sample_ids) == CONFIRM_THRESHOLD:
                        break
            try:
                with pool.transaction() as con:
                    inserted = con.execute(
                        'INSERT OR IGNORE INTO template_sites VALUES(?,?,?,?,?)',
                        (template_name, application_id, site[0] if site else None,
                         canonical(sample_ids), datetime.now(timezone.utc).isoformat()))
                registered = inserted.rowcount == 1
            except sqlite3.IntegrityError:
                registered = False  # A concurrent worker registered it first.
    return {'application_id': application_id, 'template_name': template_name,
            'pages': pages, 'reached_three': pages >= CONFIRM_THRESHOLD,
            'registered': registered, 'sample_ids': sample_ids}
