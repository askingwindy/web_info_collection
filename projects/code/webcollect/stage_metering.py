"""Read-only per-request stage report; missing metering is never zero billing."""
import json
from collections import Counter

STAGES=('search_planning','search_api','result_selection','page_opportunity','source_qualification',
        'workflow_planning','collection','mechanical_qc','sample_ai','substantive_difference','document_review')

def stage_for(kind):
    if 'search-plan' in kind:return 'search_planning'
    if kind in ('ai-select-results','ai-batch-selection'):return 'result_selection'
    if kind in ('ai-discovery-assess','ai-batch-assessment'):return 'page_opportunity'
    if kind in ('site-probe','site-qualification'):return 'source_qualification'
    if kind=='task-generation':return 'workflow_planning'
    if 'difference' in kind or 'novelty' in kind:return 'substantive_difference'
    if 'document' in kind or 'material' in kind:return 'document_review'
    if 'sample' in kind or 'semantic' in kind:return 'sample_ai'
    if 'collection' in kind:return 'collection'
    return kind

def report(ledger):
    stages={name:{'requests':0,'succeeded':0,'invalid':0,'unknown':0,'cache_hits':0,
        'input_tokens_known':0,'output_tokens_known':0,'cached_input_tokens_known':0,
        'usage_unknown_requests':0,'elapsed_seconds_known':0,'elapsed_unknown_requests':0,
        'known_cost_micros':0,'unknown_cost_requests':0,'effective_outputs':'UNKNOWN','status':'NOT_RUN'} for name in STAGES}
    timeline=[]
    with ledger.connect() as con:
        rows=con.execute('SELECT r.*,j.kind FROM model_requests r JOIN jobs j ON r.job_id=j.id ORDER BY r.started,r.id').fetchall()
        outputs=[json.loads(r[0]) for r in con.execute("SELECT detail FROM batch_events WHERE event='phase_output'")]
        events=con.execute("SELECT detail FROM batch_events WHERE event='model_cache_hit'").fetchall()
    for row in rows:
        name=stage_for(row['kind']);s=stages.setdefault(name,dict(stages['search_api']));s['status']='RECORDED';s['requests']+=1
        outcome='succeeded' if row['state']=='succeeded' else 'unknown' if row['state'] in ('unknown','reserved','new') else 'invalid'
        s[outcome]+=1
        usage=json.loads(row['usage']) if row['usage'] else None
        if usage:
            for field in ('input_tokens','output_tokens','cached_input_tokens'):s[field+'_known']+=usage.get(field,0)
        else:s['usage_unknown_requests']+=1
        if row['finished'] is not None:s['elapsed_seconds_known']+=row['finished']-row['started']
        else:s['elapsed_unknown_requests']+=1
        if row['cost'] is None:s['unknown_cost_requests']+=1
        else:s['known_cost_micros']+=row['cost']
        timeline.append({'request_id':row['id'],'job_id':row['job_id'],'stage':name,'purpose':row['purpose'],
            'state':row['state'],'error':row['error'],'usage':usage or 'UNKNOWN',
            'cost_micros':row['cost'] if row['cost'] is not None else 'UNKNOWN','effective_output':'UNKNOWN'})
    unique={(e['job_id'],e['identity']):e for e in outputs}
    for name in stages:
        observed=[e for e in unique.values() if stage_for(e['kind'])==name]
        if observed:
            stages[name]['effective_outputs']=sum(e['status']=='valid' for e in observed)
            stages[name]['rejected_outputs']=sum(e['status']=='rejected' for e in observed)
    for request in timeline:
        observed=[e for e in unique.values() if e['job_id']==request['job_id']]
        if observed:request['effective_output']={'valid':sum(e['status']=='valid' for e in observed),'rejected':sum(e['status']=='rejected' for e in observed)}
    for (raw,) in events:
        event=json.loads(raw);name=stage_for(event['kind']);stages[name]['cache_hits']+=1
    return {'version':'webcollect-stage-metering-2','stages':stages,'requests':timeline,
        'limits':'Effective outputs require compiled plans, qualification receipts, or actual QC evidence; token success alone is not effective output. Search billing is separate.'}
