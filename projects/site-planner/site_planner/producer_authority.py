"""Record operator-approved uncapped discovery and named source quarantines on the original project ledger."""
import argparse
from webcollect import workspace_json as json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from webcollect.batch_core import BatchLedger, BudgetStop, load_json
from webcollect.application_identity import canonical_key
from webcollect.current_chain import check_project_guard, check_project_pool, read_chain_scope
from webcollect.planning import object_sha256
from .site_pool import SitePool


def check_producer_stop():
    marker = os.environ.get('WEBCOLLECT_PRODUCER_STOP_FILE')
    if marker and Path(marker).is_file():
        raise BudgetStop('producer_stop_requested; current work retained')


def claim_producer_job(ledger, kind, *, job_id, **kwargs):
    """Wait only for a local slot before dispatch; never retry a model call."""
    waiting = False
    while True:
        check_producer_stop()
        try:
            return ledger.claim(kind, job_id=job_id, **kwargs)
        except BudgetStop as error:
            if str(error) != 'max_concurrent_jobs reached; queued work retained':
                raise
            if not waiting:
                with ledger.transaction() as con:
                    ledger.event(con, 'producer_capacity_wait', {'job_id': job_id, 'kind': kind})
                waiting = True
            time.sleep(1)


def isolation_host(uri,registry):
    return urlsplit(canonical_key(uri,registry)).hostname.removeprefix('www.')


def grounded_timeout_scope(pool, config, row):
    """Bind the timed-out numbered rows to their original checkpoint and hosts."""
    payload = json.loads(row['payload'])['input']
    scope = payload['scope']
    match = re.fullmatch(r'(.+)/grounded-unit/(\d+)/(\d+)', scope)
    if (not match or payload.get('original_settled_cause') or row['error'] != 'TimeoutError'
            or row['finished'] is None or row['attempts'] < 1 or row['job_state'] not in ('queued','review_required')):
        raise ValueError('Only a finished original grounded selection timeout can be isolated')
    run, unit, offset = match.groups()
    if not run.startswith(config['run_id']+'/entry-batch/'):
        raise ValueError('Grounded selection is outside the original producer')
    with pool.connect() as con:
        frozen = json.loads(con.execute('SELECT config FROM runs WHERE id=?',(run,)).fetchone()[0])
    key = 'grounded-unit/'+unit+'/prepared'
    prepared = pool.checkpoint(run,key)
    links = prepared['links'][int(offset):int(offset)+frozen['batch_size']]
    menu = [{'row':i,'quotes':{str(j):q for j,q in enumerate(dict.fromkeys(
        q for q in (h['anchor'],h['heading']) if q))}} for i,h in enumerate(links)]
    if (not links or frozen['config_sha256'] != object_sha256(config) or menu != payload['links']):
        raise ValueError('Cannot bind original model rows to frozen site URLs')
    return {'job_id':row['job_id'],'scope':scope,'checkpoint':key,'checkpoint_sha256':object_sha256(prepared),
            'source_urls':sorted({h['uri'] for h in links})}


def disjoint_requests(ledger, *, scope=None, urls=(), categories=(), independent=False):
    """Return only operator-quarantined requests disjoint from this new work."""
    from webcollect.batch_core import OutcomeUnknown
    deferred = (ledger.producer_policy or {}).get('deferred', {})
    registry = (ledger.config.get('site_failure_guard') or {}).get('application_registry')
    hosts = {isolation_host(uri,registry) for uri in urls}
    for item in deferred.values():
        old_scope = item.get('scope')
        if old_scope and scope and old_scope.split('/grounded-unit/')[0] == scope.split('/category-query-plan')[0].split('/grounded-unit/')[0]:
            raise OutcomeUnknown('Original model batch remains isolated')
        if hosts.intersection(isolation_host(uri,registry) for uri in item['source_urls']):
            raise OutcomeUnknown('Original model source remains isolated')
    allowed=set(deferred)
    if independent and ledger.producer_policy:
        # These new protocols record their semantic work unit before dispatch.
        # A refusal/timeout stays on that unit, even across later batches.
        with ledger.connect() as con:
            rows=con.execute("SELECT r.id,r.state,r.error,r.response,j.kind,j.payload FROM model_requests r JOIN jobs j ON j.id=r.job_id "
                "WHERE r.state IN ('unknown','failed') AND r.finished IS NOT NULL AND j.state IN ('review_required','queued','failed') AND j.attempts>0")
            for row in rows:
                response=json.loads(row['response'] or '{}')
                code=response.get('provider_error',{}).get('provider_code')
                status=response.get('provider_error',{}).get('http_status')
                rejected=row['state']=='failed' and type(status) is int and 400<=status<500
                if not rejected and row['error']!='TimeoutError' and code not in ('1113','1301','1302','1305'):
                    continue
                original=json.loads(row['payload']).get('input',{})
                # New plans stamp the stable name; old rows keep their generational values.
                if row['kind']=='ai-search-plan' and original.get('version') in ('producer-category-query','producer-category-query-2','producer-category-query-4'):
                    if not set(categories).intersection(original['categories']):
                        allowed.add(row['id'])
                elif row['kind']=='ai-application-site-classification-1' and original.get('protocol') in ('producer-site-classification','producer-site-classification-3','producer-site-classification-4'):
                    if isolation_host(original['homepage_uri'],registry) not in hosts:
                        allowed.add(row['id'])
                elif row['kind']=='ai-target-page-purpose-1' and original.get('source_uris'):
                    if set(urls).intersection(original['source_uris']):
                        if rejected:
                            from webcollect.model_gateway import ProviderRejected
                            raise ProviderRejected(status, row['id'], response['provider_error'])
                        raise OutcomeUnknown('Original target purpose request unsettled; reconcile original job: '+str(row['id']))
                    allowed.add(row['id'])
                elif row['kind']=='ai-grounded-entry-ids-1' and original.get('target_site_categories') and original.get('source_hosts'):
                    if not hosts.intersection(original['source_hosts']):
                        allowed.add(row['id'])
    return tuple(sorted(allowed))


def authorize(scope_path, deferred_requests, reason):
    if not reason.strip():
        raise ValueError('A dated operator instruction is required')
    scope = load_json(scope_path)
    chain = read_chain_scope(Path(scope['history_set']).absolute())
    pool = SitePool(scope['pool'], readonly=True)
    if not check_project_pool(chain, pool):
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
            row = con.execute("SELECT r.state,r.error,r.job_id,r.finished,r.response,j.kind,j.payload,j.attempts,j.state AS job_state FROM model_requests r "
                              "JOIN jobs j ON j.id=r.job_id WHERE r.id=?", (rid,)).fetchone()
            if row and row['state']=='unknown' and row['kind']=='ai-grounded-entry-ids-1':
                deferred[rid] = grounded_timeout_scope(pool,config,row)
                continue
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


def authorize_concurrency(scope_path, maximum, reason):
    """Append a producer-only scheduler decision; keep frozen config and all work."""
    if type(maximum) is not int or maximum < 1 or not reason.strip():
        raise ValueError('Positive max_concurrent_jobs and an operator instruction are required')
    scope = load_json(scope_path)
    chain = read_chain_scope(Path(scope['history_set']).absolute())
    if not check_project_pool(chain, SitePool(scope['pool'], readonly=True)):
        raise ValueError('A bound candidate project is required')
    config = load_json(scope['producer_config'])
    check_project_guard(chain, config.get('site_failure_guard'), scope['producer_db'], role='producer')
    if config['run_id'] != chain['chain_id'] + '-producer':
        raise ValueError('The original project producer is required')
    ledger = BatchLedger(scope['producer_db'], config)
    # webcollect/batch_core.py pins this schema_version on resume; it stays a cross-package literal.
    record = {'schema_version':'webcollect-producer-concurrency-1',
              'run_id':config['run_id'], 'ledger':str(ledger.path),
              'config_sha256':object_sha256(config), 'manifest':chain['manifest'],
              'frozen_max_concurrent_jobs':config['budget']['max_concurrent_jobs'],
              'max_concurrent_jobs':maximum, 'reason':reason}
    with ledger.transaction() as con:
        if con.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
            raise ValueError('Wait for the original active job or recover its expired lease first')
        previous = con.execute("SELECT detail FROM batch_events WHERE event='producer_concurrency' ORDER BY seq DESC LIMIT 1").fetchone()
        if not previous or json.loads(previous[0]) != record:
            ledger.event(con, 'producer_concurrency', record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--defer-request', action='append', default=[])
    parser.add_argument('--max-concurrent-jobs', type=int,
                        help='Append a producer scheduler limit without changing its frozen config or requests')
    parser.add_argument('--closed-entry-get-uri-scope', action='store_true',
                        help='Bind the original project to URI-only isolation of finished, zero-model entry GETs')
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    if args.max_concurrent_jobs is not None:
        if args.defer_request or args.closed_entry_get_uri_scope:
            parser.error('Concurrency and request quarantine are separate decisions')
        record = authorize_concurrency(args.scope, args.max_concurrent_jobs, args.reason)
    elif args.closed_entry_get_uri_scope:
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
