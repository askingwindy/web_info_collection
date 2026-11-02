"""Read-only first-visit accounting and evidence-bound feedback for explicit batches."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .batch_core import load_json, save_json
from .candidate_monitor import rows
from .planning import verify_evidence, object_sha256

VERSION = 'candidate-first-frame-feedback-1'


def fold_groups(outcomes):
    groups = {}
    for row in sorted(outcomes,key=lambda r:(r.get('first_dispatched_at') or float('inf'),r['candidate_id'])):
        key = (row['host'],row['page_type'])
        g = groups.setdefault(key,{'host':key[0],'page_type':key[1],'successful':0,'determinate':0,
            'attributable_failures':0,'reasons':Counter(),'streak_candidate_ids':[], 'candidate_ids':[]})
        g['candidate_ids'].append(row['candidate_id']); g['reasons'][row['reason']] += 1
        if row['outcome'] in ('SUCCESS','FAILURE'):
            g['determinate'] += 1
        if row['outcome']=='SUCCESS':
            g['successful'] += 1; g['streak_candidate_ids'] = []
        elif row.get('attributable'):
            g['attributable_failures'] += 1;g['streak_candidate_ids'].append(row['candidate_id'])
        # Unassessed/collector failures supply no site evidence and break the
        # consecutive-candidate streak; they can never join two unrelated fails.
        else:
            g['streak_candidate_ids'] = []
    for g in groups.values():
        g['reasons'] = dict(g['reasons']);g['deprioritized'] = len(g['streak_candidate_ids']) >= 2
        g['success_rate'] = g['successful']/g['determinate'] if g['determinate'] else None
    return list(groups.values())


def _availability(state):
    texts = [state.get('title',''),state.get('visible_text','')]
    for element in state.get('elements',[]):
        texts.extend(element.get(k,'') for k in ('text','label','accessible_name'))
    text = ' '.join(t for t in texts if isinstance(t,str)).casefold()
    for reason, phrases in (('soft_404',('页面不存在','页面未找到','404 not found')),
                            ('captcha',('请输入验证码','安全验证','人机验证')),
                            ('login_wall',('请先登录','登录后查看'))):
        if any(p in text for p in phrases): return reason
    return 'public_page'


def _frame(job, visit, uri, aliases=None):
    refs = json.loads(job['result'] or '{}')
    if job['state']!='done' or set(refs) != {'image','state','capture'}:
        return None, 'missing_frame_receipt', []
    evidence = list(refs.values())
    try:
        if any(not Path(ref['path']).is_file() for ref in evidence):
            return None, 'missing_evidence', evidence
        verify_evidence(evidence)
        from .browser import validate_capture_receipt
        from .candidate_contract import application_matches
        state = load_json(refs['state']['path'])
        validate_capture_receipt(state,load_json(refs['capture']['path']),Path(refs['image']['path']).read_bytes())
        if not application_matches(uri,state['url'],aliases):
            raise ValueError('First frame leaves source application')
        if not visit or visit['job_id']!=job['id'] or visit['state']!='succeeded':
            raise ValueError('First frame lacks successful original navigation')
        return True, _availability(state), evidence
    except FileNotFoundError:
        return None, 'missing_evidence', evidence
    except (ValueError,KeyError,TypeError,OSError) as error:
        return False, 'invalid_frame_receipt:'+type(error).__name__, evidence


def summarize_scope(scope):
    """Never opens any source for writing. One candidate, earliest real visit,
    across explicitly bound ledgers/workers; later retries cannot inflate rates."""
    scopes = scope.get('scopes',[scope])
    outcomes = {}; all_claim_ids = set(); attempts = {}; resource_events = {}
    for s in scopes:
        publications = rows(s['pool'], "SELECT DISTINCT candidate_id FROM candidate_batch_rows WHERE run_id=? AND result='NEW'",(s['batch'],))
        ledgers = list(dict.fromkeys([s['consumer_db'],*s.get('consumer_dbs',[])]))
        for publication in publications:
            cid = publication['candidate_id']
            claims = rows(s['pool'],'SELECT * FROM candidate_claims WHERE candidate_id=? ORDER BY created,claim_id',(cid,))
            # The NEW row's discovered source is immutable provenance, including
            # old missing page type, independent of later source appends.
            discovered = rows(s['pool'],"SELECT record FROM candidate_events WHERE candidate_id=? AND kind='discovered' ORDER BY id LIMIT 1",(cid,))
            source = json.loads(discovered[0]['record']).get('source',{}) if discovered else {}
            body = rows(s['pool'],'SELECT body FROM data_candidates WHERE candidate_id=?',(cid,))
            uri = json.loads(body[0]['body'])['entry_url']
            page_type = source.get('page_type','UNKNOWN') if source.get('selection_version')=='entry-selection-2' else 'UNKNOWN'
            firsts = []; jobs_seen = []; time_events = []
            for claim in claims:
                claim_id = claim['claim_id'];all_claim_ids.add(claim_id)
                binding = json.loads(claim['binding'] or '{}')
                bound_ledgers = list(dict.fromkeys([*ledgers,*([binding['ledger']] if binding.get('ledger') else [])]))
                for ledger in bound_ledgers:
                    jobs = rows(ledger,"SELECT * FROM jobs WHERE kind='candidate-observation' AND json_extract(payload,'$.claim_id')=?",(claim_id,))
                    for job in jobs:
                        jobs_seen.append((job,claim,ledger))
                        visits = rows(ledger,'SELECT * FROM top_level_visits WHERE job_id=? ORDER BY dispatched_at,id',(job['id'],))
                        if visits: firsts.append((visits[0],job,claim,ledger))
                if s.get('registry'):
                    tasks = rows(s['registry'],"SELECT task_key,scope_id FROM m4_tasks WHERE json_extract(task_json,'$.candidate_binding.claim_id')=?",(claim_id,))
                    scope_ids = {t['scope_id'] for t in tasks}
                    if binding.get('output'):
                        path = str((Path(binding['output'])/'execution/capture').resolve())
                        scope_ids.add('output-'+hashlib.sha256(path.encode()).hexdigest())
                    for scope_id in scope_ids:
                        for event in rows(s['registry'],"SELECT * FROM m4_events WHERE scope_id=? AND event_type='resource_checkpoint'",(scope_id,)):
                            payload = json.loads(event['payload_json'])
                            if 'campaign_worker_time_limit' in payload.get('reasons',[]):
                                time_events.append({'registry':s['registry'],'event_id':event['event_id'],'at':event['at'], 'claim_id':claim_id})
                    for task in tasks:
                        for attempt in rows(s['registry'],'SELECT attempt_id,status FROM m4_attempts WHERE task_key=?',(task['task_key'],)):
                            attempts[(s['registry'],attempt['attempt_id'])] = attempt
            producer_http = source.get('entry_http')
            producer_status = None
            if producer_http:
                verify_evidence([producer_http])
                producer_status = load_json(producer_http['path']).get('http_status')
            row = {'candidate_id':cid,'entry_uri':uri,'host':urlsplit(uri).hostname,'page_type':page_type,
                'outcome':'UNASSESSED','reason':'unclaimed' if not claims else 'not_dispatched',
                'attributable':False,'claims':[c['claim_id'] for c in claims],'first_dispatched_at':None,
                'evidence':[],'producer_entry_http':producer_http,'producer_http_status':producer_status, 'time_events':[]}
            chosen = min(firsts,key=lambda x:(x[0]['dispatched_at'],x[0]['id'])) if firsts else None
            if chosen:
                visit,job,claim,ledger = chosen
                row.update(first_dispatched_at=visit['dispatched_at'],claim_id=claim['claim_id'],
                    observation_job_id=job['id'],ledger=ledger,visit_id=visit['id'],
                    browser_http_status=visit['response_status'],landed_host=urlsplit(visit['landed_uri'] or uri).hostname)
                binding = json.loads(claim['binding'] or '{}')
                failure = None
                if binding.get('output'):
                    path = Path(binding['output'])/'first-observation-failure.json'
                    if path.is_file():
                        failure = load_json(path)
                        if failure.get('job_id')!=job['id']:
                            raise ValueError('Failure receipt belongs to another observation job')
                        from site_planner.discovery_tools import reference
                        row['failure_evidence'] = reference(path)
                if visit['state'] in ('unknown','reserved'):
                    row.update(reason='unresolved_visit')
                elif visit['response_status'] is not None and visit['response_status']>=400:
                    row.update(outcome='FAILURE',reason='browser_http_'+str(visit['response_status']),attributable=True)
                elif visit['state']=='failed':
                    # Only explicit network errors are attributable. Collector
                    # exceptions and local budget/cancellation remain neutral.
                    attributable = visit.get('error_type') in ('TimeoutError','Error') and any(
                        t in (visit.get('error_message') or '') for t in ('net::ERR_','Timeout'))
                    row.update(outcome='FAILURE',reason='navigation_failure',attributable=attributable)
                else:
                    aliases = None
                    if binding.get('claim_reference'):
                        verify_evidence([binding['claim_reference']])
                        original_claim = load_json(binding['claim_reference']['path'])
                        if original_claim.get('claim_id')!=claim['claim_id']:
                            raise ValueError('Original claim receipt identity changed')
                        aliases = original_claim.get('application_registry')
                    valid,availability,evidence = _frame(job,visit,uri,aliases)
                    row['evidence'] = evidence
                    if valid:
                        row['page_availability'] = availability
                        row.update(outcome='SUCCESS' if availability=='public_page' else 'FAILURE',
                                   reason='trusted_frame' if availability=='public_page' else availability,
                                   attributable=availability!='public_page', frame_verified=True)
                    elif valid is False:
                        row.update(outcome='FAILURE',reason=availability)
                    elif job.get('error')=='EvidenceStale' and failure and failure.get('error_type')=='EvidenceStale':
                        row.update(outcome='FAILURE',reason='capture_unsynchronized')
                    else:
                        row.update(reason='missing_evidence')
                if 'category UNKNOWN' in (claim.get('reason') or ''):
                    row['category_unknown_stage'] = 'after_frame' if row.get('frame_verified') else 'before_frame'
            for event in {(e['registry'],e['event_id']):e for e in time_events}.values():
                event = {**event,'stage':'after_frame' if chosen and row.get('frame_verified') and event['at']>=chosen[1]['updated'] else 'before_frame'}
                row['time_events'].append(event);resource_events[(event['registry'],event['event_id'])]=event
            # Same batch can be repeated in scopes without multiplying candidates.
            old = outcomes.get(cid)
            if old is None or (row['first_dispatched_at'] is not None and
                (old['first_dispatched_at'] is None or row['first_dispatched_at']<old['first_dispatched_at'])):
                outcomes[cid] = row
    values = list(outcomes.values());new = len(values)
    determinate = sum(r['outcome'] in ('SUCCESS','FAILURE') for r in values)
    success = sum(r['outcome']=='SUCCESS' for r in values)
    verified = sum(bool(r.get('frame_verified')) for r in values)
    return {'schema_version':VERSION,'scope_sha256':object_sha256(scope),'scope':scope,'net_new':new,
        'trusted_first_frames':verified,'usable_first_frames':success,'determinate':determinate,
        'success_rate':verified/determinate if determinate else None,'coverage':determinate/new if new else None,
        'usable_first_frame_rate':success/determinate if determinate else None,
        'reasons':dict(Counter(r['reason'] for r in values)),
        'producer_http_statuses':dict(Counter(str(r['producer_http_status']) for r in values)),
        'browser_http_statuses':dict(Counter(str(r.get('browser_http_status')) for r in values)),
        'unassessed':dict(Counter(r['reason'] for r in values if r['outcome']=='UNASSESSED')),
        'time_pauses':dict(Counter(e['stage'] for e in resource_events.values())),
        'category_unknown':dict(Counter(r['category_unknown_stage'] for r in values if 'category_unknown_stage' in r)),
        'formal_attempts':len(attempts),'saved':sum(a['status']=='collected_pending_review' for a in attempts.values()),
        'groups':fold_groups(values),'outcomes':values,
        'independent_QC':'NOT_EVALUATED','published':'NOT_EVALUATED','customer_acceptance':'UNKNOWN'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New report path outside original evidence')
    args = parser.parse_args(argv)
    if args.output.exists(): raise ValueError('New report path required')
    report = summarize_scope(load_json(args.scope))
    # Do not allow a report to become an original ledger/evidence file.
    for s in report['scope'].get('scopes',[report['scope']]):
        for k in ('pool','consumer_db','registry','producer_db'):
            if s.get(k) and args.output.resolve()==Path(s[k]).resolve(): raise ValueError('Original source is read-only')
    save_json(args.output,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('scope','groups','outcomes')},ensure_ascii=False))


if __name__=='__main__': main()
