"""Record operator-approved uncapped discovery and named source quarantines on the original project ledger."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from webcollect.batch_core import BatchLedger, load_json
from webcollect.application_identity import canonical_key
from webcollect.current_chain import check_project_guard, check_project_pool, read_chain_scope
from webcollect.planning import object_sha256
from .site_pool import SitePool


def isolation_host(uri,registry):
    return urlsplit(canonical_key(uri,registry)).hostname.removeprefix('www.')


def authorize(scope_path, deferred_requests, reason):
    if not reason.strip():
        raise ValueError('A dated operator instruction is required')
    scope = load_json(scope_path)
    chain = read_chain_scope(Path(scope['history_set']).absolute())
    if not check_project_pool(chain, SitePool(scope['pool'], readonly=True)):
        raise ValueError('A bound candidate project is required')
    config = load_json(scope['producer_config'])
    check_project_guard(chain, config.get('site_failure_guard'), scope['producer_db'], role='producer')
    if config['run_id'] != chain['chain_id'] + '-producer':
        raise ValueError('The original project producer is required')
    ledger = BatchLedger(scope['producer_db'], config)
    with ledger.transaction() as con:
        if con.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
            raise ValueError('Wait for the original active job or recover its expired lease first')
        previous = con.execute("SELECT detail FROM batch_events WHERE event='producer_budget_unlimited' ORDER BY seq DESC LIMIT 1").fetchone()
        previous = json.loads(previous[0]) if previous else {}
        deferred = dict(previous.get('deferred', {}))
        for rid in sorted(set(deferred_requests)):
            row = con.execute("SELECT r.state,r.error,r.job_id,r.finished,r.response,j.kind,j.payload,j.state AS job_state FROM model_requests r "
                              "JOIN jobs j ON j.id=r.job_id WHERE r.id=?", (rid,)).fetchone()
            if not row or (row['state'],row['kind'],row['job_state']) != ('unknown','ai-candidate-entry-tool-1','review_required'):
                raise ValueError('Original unsettled entry selection required')
            provider=json.loads(row['response'] or '{}').get('provider_error',{})
            content_refused=(config.get('model') or {}).get('provider')=='glm' and row['finished'] is not None and (
                row['error'],provider.get('http_status'),provider.get('provider_code'))==('HTTPError:400',400,'1301')
            if row['error']!='lease_expired_after_dispatch' and not content_refused:
                raise ValueError('Only interrupted or explicitly content-refused entry selections can be isolated')
            sources = json.loads(row['payload'])['input']['sources']
            urls = sorted({item['uri'] for item in sources})
            if not urls:
                raise ValueError('Original input sources are required for isolation')
            deferred[rid] = {'job_id':row['job_id'],'source_urls':urls}
            if content_refused:
                deferred[rid]['provider_refusal']={'http_status':400,'provider_code':'1301','usage':'UNKNOWN'}
        record = {'policy':'producer-metered-unlimited-1','run_id':config['run_id'],'ledger':str(ledger.path),
                  'config_sha256':object_sha256(config),'manifest':chain['manifest'],'reason':reason,
                  'deferred':deferred}
        if record != previous:
            ledger.event(con,'producer_budget_unlimited',record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--defer-request', action='append', default=[])
    parser.add_argument('--closed-entry-get-uri-scope', action='store_true',
                        help='Bind the original project to URI-only isolation of finished, zero-model entry GETs')
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    if args.closed_entry_get_uri_scope:
        if args.defer_request:
            parser.error('URI-only GET isolation and model request quarantine are separate decisions')
        from webcollect.site_failure_stop import SiteFailureStore
        scope = load_json(args.scope)
        guard = SiteFailureStore(load_json(scope['producer_config'])['site_failure_guard'])
        record = guard.enable_closed_entry_uri_scope(scope['history_set'],scope['producer_db'],args.reason)
    else:
        record = authorize(args.scope,args.defer_request,args.reason)
    print(json.dumps(record,ensure_ascii=False))


if __name__ == '__main__':
    main()
