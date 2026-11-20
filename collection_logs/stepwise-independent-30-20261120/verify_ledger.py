"""在 SQLite 在线备份的临时副本上实测新增索引；不修改正式账本。"""
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from time import perf_counter

from validate import ARCHIVE, RUN, campaign
from progress import read, write
from webcollect.batch_core import BatchLedger


def timed(con, sql, params=()):
    plan = [r[3] for r in con.execute('EXPLAIN QUERY PLAN ' + sql, params)]
    start = perf_counter()
    rows = con.execute(sql, params).fetchall()
    return rows, {'plan': plan, 'seconds': round(perf_counter() - start, 6), 'rows': len(rows)}


def main():
    scope = read(campaign.SCOPE)
    source = Path(scope['consumer_db'])
    with tempfile.TemporaryDirectory(dir=RUN) as tmp:
        clone = Path(tmp) / source.name
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(clone)) as dst:
            src.backup(dst)
        ledger = BatchLedger(clone, read(Path(scope['consumer_config'])))
        with closing(sqlite3.connect(clone)) as db:
            account, since = db.execute('SELECT account_id,last_success FROM consumer_key_health WHERE last_success IS NOT NULL ORDER BY last_success DESC LIMIT 1').fetchone()
            recent = """SELECT 1 FROM model_requests WHERE json_extract(request_json,'$.account_id')=?
                AND finished>? AND json_extract(response,'$.provider_error.provider_code')='1113' LIMIT 1"""
            failed = "SELECT request_json,response,finished FROM model_requests WHERE state IN ('unknown','failed')"
            queries = [('balance_after_probe', recent, (account, since)), ('prior_account_failures', failed, ())]
            results, original = {}, {}
            source_count = db.execute('SELECT count(*) FROM model_requests').fetchone()[0]
            for name, sql, values in queries:
                original[name], measured = timed(db, sql, values)
                results[name] = {'before': measured}
            start = perf_counter()
            ledger.prepare_dispatch_indexes()
            build_seconds = round(perf_counter() - start, 6)
        with closing(sqlite3.connect(clone)) as db:
            expected_indexes = {'balance_after_probe': 'request_balance_failure', 'prior_account_failures': 'request_historical_failure'}
            for name, sql, values in queries:
                found, measured = timed(db, sql, values)
                # The historical health query has no ORDER BY. Compare complete multisets.
                assert sorted(found, key=repr) == sorted(original[name], key=repr)
                results[name].update(after=measured, same_rows=True)
                assert any(expected_indexes[name] in step for step in measured['plan']), measured['plan']
            assert db.execute('SELECT count(*) FROM model_requests').fetchone()[0] == source_count
        write(ARCHIVE / 'ledger-verification.json', {'source_rows_in_snapshot': source_count,
              'preparation_seconds': build_seconds, 'queries': results, 'production_ledger_writes': 0})


if __name__ == '__main__':
    main()
