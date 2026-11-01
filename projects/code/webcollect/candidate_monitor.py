"""Read-only observer for a producer/consumer trial. Workers are started independently."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from .planning import object_sha256


def rows(database, query, args=()):
    path = Path(database).absolute()
    if not path.is_file():  # A producer can start after the observer.
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(query, args)]


def events(scope):
    since = scope['started_at']
    for role in ('producer', 'consumer'):
        ledger = scope[role + '_db']
        if not Path(ledger).is_file():
            yield role + '-calls', 'ledger_not_ready', {'ledger':ledger, 'since':since}
            continue
        requests = rows(ledger, """SELECT id,job_id,purpose,state,started,finished,cost,usage,error,
            json_extract(request_json,'$.model') AS model,
            json_extract(request_json,'$.reasoning_effort') AS effort,
            json_extract(request_json,'$.dispatch_attempt_id') AS formal_attempt,
            json_extract(request_json,'$.http_dispatch') AS http_dispatch,
            json_extract(response,'$.result.name') AS tool,
            json_extract(response,'$.result.tool_call_id') AS tool_call_id,
            json_extract(response,'$.provider_response.id') AS provider_request_id,
            json_extract(response,'$.provider_error.http_status') AS http_status,
            json_extract(response,'$.provider_error.provider_code') AS provider_code
            FROM model_requests WHERE started>=? ORDER BY started,id""", (since,))
        for row in requests:
            dispatch = {k: row[k] for k in ('id','job_id','purpose','started','model','effort','formal_attempt','http_dispatch')}
            yield role + '-calls', 'dispatch_recorded', dispatch
            if row['state'] != 'reserved':
                row['usage'] = json.loads(row['usage']) if row['usage'] else None
                yield role + '-calls', 'accounted', row
                if row['state'] != 'succeeded':
                    yield 'issues', 'model_request', {**row, 'role': role}
        yield role + '-calls', 'account_count', {'request_count': len(requests), 'ledger':ledger, 'since':since}

    pool, batch, worker = scope['pool'], scope['batch'], scope['consumer_worker']
    for search in rows(pool, """SELECT id,kind,state,started,finished FROM tool_requests
            WHERE run_id=? AND kind='search' ORDER BY started,id""", (batch.rsplit('/entry-batch/',1)[0],)):
        yield 'producer-calls', 'search_request', search
        if search['state'] in ('unknown', 'failed'):
            yield 'issues', 'search_request', search
    for publication in rows(pool, """SELECT row_id,batch,candidate_id,result,reason,created,
            json_extract(record,'$.entry_http.path') AS entry_http_receipt, json_extract(record,'$.http_status') AS http_status
            FROM candidate_batch_rows WHERE run_id=? ORDER BY created,row_id""", (batch,)):
        if publication['entry_http_receipt'] is None:
            del publication['entry_http_receipt'], publication['http_status']
        elif publication['result'] in ('REJECTED','HELD'):
            yield 'issues', 'producer_entry_http', publication
        yield 'pipeline', 'published_row', publication
    claims = rows(pool, """SELECT claim_id,candidate_id,state,stage,reason,updated FROM candidate_claims
            WHERE worker_id=? AND candidate_id IN
            (SELECT candidate_id FROM candidate_batch_rows WHERE run_id=? AND result='NEW')
            ORDER BY created,claim_id""", (worker, batch))
    for claim in claims:
        claim['reason'] = (claim['reason'] or '')[:600]
        yield 'pipeline', 'claim', claim
        if claim['state'] in ('failed', 'reconcile'):
            yield 'issues', 'candidate', claim
    for visit in rows(scope['consumer_db'], """SELECT id,job_id,target_uri,state,response_status,error_type,
            dispatched_at,finished_at FROM top_level_visits WHERE dispatched_at>=? ORDER BY dispatched_at,id""", (since,)):
        uri = urlsplit(visit['target_uri'])
        visit['target_uri'] = urlunsplit((uri.scheme, uri.hostname or '', uri.path, '', ''))
        yield 'consumer-visits', 'visit', visit
        if visit['state'] in ('failed', 'unknown'):
            yield 'issues', 'navigation', visit
    if claims:
        for attempt in rows(scope['registry'], """SELECT a.attempt_id,a.sample_id,a.status,a.failure_class,a.root_cause,
                json_extract(t.task_json,'$.candidate_binding.claim_id') AS claim_id
                FROM m4_attempts a JOIN m4_tasks t USING(task_key)
                WHERE json_extract(t.task_json,'$.candidate_binding.claim_id') IN (SELECT value FROM json_each(?))
                ORDER BY a.attempt_id""", (json.dumps([row['claim_id'] for row in claims]),)):
            yield 'pipeline', 'formal_attempt', attempt
            if attempt['status'] in ('rejected', 'interrupted'):
                yield 'issues', 'formal_attempt', attempt


def project(scope, log_dir, seen):
    log_dir.mkdir(parents=True, exist_ok=True)
    for stream, event, fields in events(scope):
        path = log_dir / (stream + '.jsonl')
        if path not in seen:
            saved = set()
            if path.exists():
                with path.open(encoding='utf-8') as handle:
                    saved.update(json.loads(line)['event_id'] for line in handle)
            seen[path] = saved
        # The SQL kind (e.g. 'search') is independent of the observer's event.
        event_id = object_sha256([event, fields])
        if event_id in seen[path]:
            continue
        record = {**fields, 'event': event, 'event_id': event_id,
                  'observed_at': datetime.now(timezone.utc).isoformat()}
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        seen[path].add(event_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', type=Path, required=True, help='Trial scope JSON with pool, batch, worker, ledgers, registry and starting time')
    parser.add_argument('--log-dir', type=Path, required=True, help='Directory for this observer, separate from the evidence')
    parser.add_argument('--once', action='store_true', help='Project the original records once, then exit')
    args = parser.parse_args(argv)
    scope = json.loads(args.scope.read_text(encoding='utf-8'))
    seen = {}
    while True:
        try:
            project(scope, args.log_dir, seen)
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError) as error:
            print(f'Observer projection failed: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
            if args.once:
                return 1
        else:
            if args.once:
                return 0
        time.sleep(1)


if __name__ == '__main__':
    raise SystemExit(main())
