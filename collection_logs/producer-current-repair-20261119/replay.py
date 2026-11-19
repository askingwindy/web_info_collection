"""Offline producer replay. Production SQLite connections are read-only."""
import argparse
from collections import Counter
from contextlib import closing, ExitStack
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

from site_planner import grounded_entries, page_consumption, producer_business_content as purpose, producer_dispatch, producer_query_plan
from site_planner.application_discovery import Discovery
from site_planner.candidate_pool import CandidatePool, entry_identity, VERSION2
from site_planner.discovery_tools import reference
from site_planner.entry_selection import simplified_chinese_evidence
from site_planner.site_pool import SitePool
from webcollect.batch_core import BatchLedger
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256, verify_evidence


def read(path):return json.loads(Path(path).read_text())


def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def readonly(path):
    connection=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def copy_row(target,table,row):
    columns=','.join(row.keys());marks=','.join('?' for _ in row)
    target.execute(f'INSERT OR IGNORE INTO {table}({columns}) VALUES({marks})',tuple(row[column] for column in row.keys()))


def config():return {'run_id':'offline-producing','mode':'synthetic','model':None,'budget':{
    'max_concurrent_jobs':4,'min_domain_interval_seconds':1,'lease_seconds':120,'max_job_attempts':1}}


def baseline(project,scratch):
    archive=project/'collection_logs/producer-new100-20261118'; start=read(archive/'active-run.json')
    audit=read(archive/'final-audit.json');scope=read(start['scope'])
    rows=[json.loads(line) for line in (archive/'candidate-batch-rows.jsonl').read_text().splitlines()]
    good={row['entry_url'] for row in rows if row['result']=='NEW'}
    rejected={row['entry_url'] for row in rows if row['reason']=='simplified_chinese_not_evidenced'}
    earlier=set();duplicates=0
    for row in sorted(rows,key=lambda item:item['created']):
        identity=(row['candidate_id'],row['entry_url'])
        if row['result']=='DUPLICATE':
            assert identity in earlier;duplicates+=1
        elif row['result']=='NEW':earlier.add(identity)
    pool_path=scratch/'candidate-pool.sqlite3'; SitePool(pool_path,initialize=True)
    pool=CandidatePool(pool_path,install=True);Discovery(pool,install=True)
    ledger=BatchLedger(scratch/'producer-jobs.sqlite3',config(),initialize=True)
    docs={};samples={};probes={};loaded={}
    with closing(readonly(scope['pool'])) as source, closing(readonly(scope['producer_db'])) as jobs:
        for row in rows:
            uri=row['entry_url']
            if uri not in good|rejected or uri in docs:continue
            key=(row['run_id'],row['selection_key'])
            if key not in loaded:
                receipt=json.loads(source.execute("SELECT json_extract(value,'$.reference') FROM checkpoints WHERE run_id=? AND key=?",key).fetchone()[0]);verify_evidence([receipt]);loaded[key]=read(receipt['path'])
            record=next(entry for entry in loaded[key]['records'] if entry['link_id']==row['link_id'])
            proof=record['target_evidence'];verify_evidence([proof['document']]);doc=read(proof['document']['path'])
            assert entry_identity(doc['uri'])==entry_identity(uri)
            language=simplified_chinese_evidence(doc);assert language['eligible']==(uri in good)
            docs[uri]=language['reason'];label='good' if uri in good else 'reject'
            if len(samples.get(label,[])) >= (7 if label=='good' else 1):continue
            prepared_key=row['selection_key'].rsplit('/',2)[0]+'/prepared'
            prepared=json.loads(source.execute('SELECT value FROM checkpoints WHERE run_id=? AND key=?',(row['run_id'],prepared_key)).fetchone()[0]);link=next(link for link in prepared['links'] if link['link_id']==row['link_id'])
            samples.setdefault(label,[]).append(link);application=link['application_id'];origin=prepared['site_origins'][application]
            probe=dict(source.execute('SELECT * FROM tool_requests WHERE id=?',(object_sha256([page_consumption.SCREEN_RUN,'browser',entry_identity(uri)]),)).fetchone());probes[uri]=probe
            with ledger.transaction() as target:
                copy_row(target,'jobs',jobs.execute('SELECT * FROM jobs WHERE id=?',(doc['job_id'],)).fetchone())
                copy_row(target,'top_level_visits',jobs.execute('SELECT * FROM top_level_visits WHERE id=?',(doc['visit_id'],)).fetchone())
        assert set(docs)==good|rejected and len(good)==100 and len(rejected)==22 and not good & rejected
        with pool.transaction() as target:
            for table,column in [('applications','id'),('application_decisions','application_id'),('application_discovery','application_id')]:
                for item in source.execute(f'SELECT * FROM {table} WHERE {column}=?',(application,)):copy_row(target,table,item)
        requests=jobs.execute("SELECT json_extract(j.payload,'$.input.source_uris') AS uris FROM jobs j JOIN model_requests r ON r.job_id=j.id "
            "WHERE j.kind='ai-target-page-purpose-1' AND r.started BETWEEN ? AND ? AND json_extract(j.payload,'$.input.scope') LIKE ?",
            (start['started_at'],audit['snapshot_at'],'%/entry-batch/producer-new100-20261118-dpm-%')).fetchall()
        original_queries=[set(json.loads(row[0])) for row in requests];affected=[uris for uris in original_queries if uris & rejected]
        assert set.union(*affected)&rejected==rejected
        history=producer_dispatch.section_history(CandidatePool(scope['pool'],readonly=True),application)
    samples['site_origins']={application:origin};samples['probes']=probes
    save(scratch/'samples.json',samples)
    meter=audit['accounting'];return {'original_rows':dict(Counter(row['result'] for row in rows)),
        'approved_passed_script_gate':len(good),'blocked_unique':len(rejected),'blocked_original_rows':sum(row['reason']=='simplified_chinese_not_evidenced' for row in rows),
        'duplicate_rows_same_as_previous_NEW':duplicates,'original_purpose_requests':len(original_queries),'affected_original_requests':len(affected),
        'all_pages_blocked_in_original_request':sum(uris<=rejected for uris in affected),'actual_original_GET_per_100':meter['GET_requests'],
        'actual_original_input_tokens_per_100':meter['tokens']['input_tokens'],'actual_original_wall_seconds_per_100':round(max(read(archive/'expansion-exit.json')['finished_at'],read(archive/'controller-exit.json')['finished_at'])-start['started_at'],2),
        'sampled_catalog_history':dict(history)}


def worker(scratch,name):
    samples=read(scratch/'samples.json'); pool_path=scratch/'candidate-pool.sqlite3';ledger_path=scratch/'producer-jobs.sqlite3'
    pool=CandidatePool(pool_path);output=scratch/name;output.mkdir(exist_ok=True);run='offline-producing/entry-batch/'+name
    good=samples['good'];bad=samples['reject'][0]
    links={'serial':[bad,good[0]],'overlap':[good[1],good[2],good[0],bad],'owner':[good[3]],'peer':[good[3]],'invalid':[good[4]],'partial':good[5:7]}[name]
    key='grounded-unit/0';pool.pool.checkpoint(run,key+'/input',{'seeds':[]})
    pool.pool.checkpoint(run,key+'/prepared',{'links':links,'site_origins':samples['site_origins'],'failures':[],'dropped':[]})
    counts=Counter();menus=[]
    frozen={'version':'old-row-namespace','model_protocol':'retired','table_policy':'retired',
        'purpose_version':'retired','purpose_system':'retired','config_sha256':'not-a-release-gate',
        'ledger':str(ledger_path),'sources':[],'directions':[],'queries':[],'target':8,'max_searches':0,'max_batches':2,
        'batch_size':2,'search_engine':'public','stall_threshold':2,'per_direction_cap':None,'entry_selection':'rule',
        'discovery_mode':'expand','feedback_scope':None,'feedback':None,'search_count':10,'goals':None,
        'excluded_applications':[],'output':str(output),'producer_pipeline':'serial'}
    if name=='serial':pool.pool.freeze_run(run,frozen,inventory=False)

    def probe(local_pool,ledger,uri,root):
        counts['probe_dispatch']+=1;row=samples['probes'][uri]
        with local_pool.transaction() as target:copy_row(target,'tool_requests',row)
        return json.loads(row['result'])

    def screen(local_pool,ledger,items,root,**options):
        return page_consumption.screen(local_pool,ledger,items,root,probe=probe,eligibility_policy=options['eligibility_policy'])

    def reply(gateway,job,kind,body,tools,**options):
        payload=json.loads(body);pages=payload['pages'];counts['model_dispatch']+=1
        assert options['system']==purpose.SYSTEM
        menu=[page['page_key'] for page in pages];assert menu==[f'p{index}' for index in range(1,len(menu)+1)]
        assert all(set(page['site_context'])=={'category'} for page in pages)
        assert bad['uri'] not in payload['source_uris'];menus.append(dict(zip(menu,payload['source_uris'])))
        schema=tools[0]['function']['parameters']['properties']['decisions'];assert schema['required']==menu
        assert all(set(rule['properties'])=={'business','business_quote_ids','content_kind','public_access'} for rule in schema['properties'].values())
        if name=='owner':
            (scratch/'owner-ready').touch();deadline=time.monotonic()+35
            while not (scratch/'peer-finished').exists():
                if time.monotonic()>deadline:raise RuntimeError('peer did not finish')
                time.sleep(.05)
        decisions={page['page_key']:{'business':'public_business','business_quote_ids':[page['content_evidence_ids'][0]],
            'content_kind':'business_content','public_access':'public_content'} for page in pages}
        invalid=name in ('invalid','partial')
        submitted=({'p1_reason':'unexpected'} if name=='invalid' else {'p1':decisions['p1'],'p2_reason':'unexpected'} if name=='partial' else decisions)
        rid='fake-'+job['id'];arguments={'decisions':submitted}
        response={'provider_response':{'choices':[{'message':{'content':json.dumps(arguments)}}]}}
        with BatchLedger(ledger_path,config()).transaction() as target:
            target.execute('INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,finished,usage,response) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (rid,job['id'],kind,1,'invalid_response' if invalid else 'succeeded',0,0,time.time(),time.time(),json.dumps({'input_tokens':1,'output_tokens':1,'cached_input_tokens':0}),json.dumps(response)))
        if invalid:raise ValueError('offline invalid response')
        return {'arguments':arguments,'request_id':rid,'tool_call_id':'controlled-tool'}

    with ExitStack() as stack:
        stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('socket.getaddrinfo',side_effect=AssertionError('DNS forbidden')))
        stack.enter_context(patch('site_planner.producer_observation.screen',screen))
        stack.enter_context(patch.object(ModelGateway,'__init__',lambda self,ledger:None))
        stack.enter_context(patch.object(ModelGateway,'call_tool',reply))
        report=grounded_entries.produce(config(),pool_path=pool_path,ledger_path=ledger_path,output=output,history_set=None,
            queries=[],sources=[],directions=[],goals_path=None,target=8,max_searches=0,max_batches=2,batch_size=2,search_engine='public',
            stall_threshold=2,per_direction_cap=None,batch_key=name,excluded_applications=[],discovery_mode='expand',feedback_scope=None,
            search_count=10,producer_pipeline='overlap-1' if name=='overlap' else 'serial')
    assert not report['stopped'],report['stopped']
    if name=='serial':
        with pool.pool.connect() as connection:
            assert json.loads(connection.execute('SELECT config FROM runs WHERE id=?',(run,)).fetchone()[0])==frozen
    outcomes=[]
    for path in sorted(output.glob('entry-links-*.json')):
        body=read(path);outcomes.extend((item.get('selection_reason'),item.get('page_key')) for item in body['records']);outcomes.extend((item['decision']['reason'],None) for item in body['page_consumption'] if item['decision']['status'] in ('DUPLICATE','HELD'))
        if name=='partial':assert body['calls'][0]['missing_page_keys']==['p2'] and body['calls'][0]['unexpected_page_keys']==['p2_reason']
    result={'counts':dict(counts),'new':report['new_candidates_this_invocation'],'rows':report['row_results'],'outcomes':outcomes,'menus':menus}
    save(output/'offline.json',result)
    if name=='peer':(scratch/'peer-finished').touch()


def query_boundaries(pool,ledger,scratch):
    state={'queries':{},'blocked':[]};kind='ai-search-plan';key='category-query-plan'
    result=[]
    for name,started in [('queued-plan',False),('dispatched-plan',True)]:
        run='offline-planner/'+name;scope=run+'/'+key;old={'version':'old','scope':scope,'instruction':'retired'}
        pool.pool.checkpoint(run,key+'/input',old)
        job_id=ledger.enqueue(kind,{'input':old,'schema':producer_query_plan.PLAN_SCHEMA,'image_refs':[],'output_limit':123})
        if started:
            ledger.finish(ledger.claim(kind,job_id=job_id),result={'queries':['已结算旧词']})
        before=ledger.get(job_id)
        def decide(gateway,job,unused,body,schema,**options):
            payload=json.loads(body);assert payload['scope']==scope and producer_query_plan.PROMPT in payload['instruction']
            return {'queries':['当前规则新词']}
        with patch.object(ModelGateway,'__init__',side_effect=AssertionError('settled job cannot dispatch')) if started else patch.object(ModelGateway,'__init__',lambda self,ledger:None), patch.object(ModelGateway,'call',decide):
            decision=producer_query_plan.next_query(pool.pool,ledger,run,'unit',['图书文化'],state,[],scratch)
        result.append(decision['query']);assert ledger.get(job_id)==before and pool.pool.checkpoint(run,key+'/input')==old
    assert result==['当前规则新词','已结算旧词'];return result


def edge_cases(scratch):
    pool=CandidatePool(scratch/'candidate-pool.sqlite3');ledger=BatchLedger(scratch/'producer-jobs.sqlite3',config())
    link=read(scratch/'samples.json')['good'][0];application=link['application_id'];site=Discovery(pool).get(application)
    link={**link,'site_category':site['category'],'site_decision_id':site['decision_id']}
    goals=[{'kind':'查询','entity':name,'parameters':{}} for name in ('馆藏甲','馆藏乙')]
    targeted={**link,'producer_goals':goals};alias={**link,'uri':'https://www.dpm.org.cn/offline-alias.html'}
    assert producer_dispatch.unpublished(pool,alias)[0]==[None]
    assert producer_dispatch.unpublished(pool,alias,link['uri'])[0]==[]
    assert producer_dispatch.unpublished(pool,{**alias,'uri':alias['uri']+'#/other'},link['uri'])[0]==[None]
    assert producer_dispatch.unpublished(pool,targeted)[0]==goals
    with ExitStack() as owner, ExitStack() as peer:
        assert producer_dispatch.claim_pages(pool,{**targeted,'producer_goals':goals[:1]},link['uri'],owner)[0]==goals[:1]
        assert producer_dispatch.claim_pages(pool,targeted,link['uri'],peer)[0]==goals[1:]
    pool._put_v2({'schema_version':VERSION2,'candidate_kind':'target','entry_url':link['uri'],'requested_goal':goals[0]},
        {'origin':'codex_session','run_id':'offline-goal','references':[link['reference']]},application_id=application)
    assert producer_dispatch.unpublished(pool,targeted)[0]==goals[1:]
    with patch.object(ModelGateway,'__init__',side_effect=AssertionError('new model dispatch forbidden')):
        rows,receipt=purpose.classify(ledger,[targeted],'independent-goal',scratch,pool=pool)
        assert len(rows)==1 and not receipt['calls'] and receipt['records'][0]['model_calls'][0]['reused']
        with patch.object(purpose,'SYSTEM',purpose.SYSTEM+' changed offline'):
            rows,receipt=purpose.classify(ledger,[targeted],'another-goal',scratch,pool=pool)
            result=receipt['records'][0]
            assert len(rows)==1 and not receipt['calls'] and result['reassessed_original_with_current_rules']
            incomplete={'target_evidence':result['target_evidence']}
            purpose.reuse_proposal(incomplete,{**result,'proposal':{'business':'public_business'}})
            assert not incomplete['selected'] and incomplete['status']=='HELD'
        original_states=['reserved','unknown'];links=[]
        for number,state in enumerate(original_states):
            held={**link,'uri':f'https://www.dpm.org.cn/offline-held-{number}.html'};links.append(held)
            job_id=ledger.enqueue('ai-target-page-purpose-1',{'input':{'scope':'original-'+state,'source_uris':[held['uri']]}})
            with ledger.transaction() as connection:
                connection.execute('INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started) VALUES(?,?,?,?,?,?,?,?)',
                    ('offline-'+state,job_id,'ai-target-page-purpose-1',1,state,1,0,time.time()))
        with ledger.connect() as connection:before=[tuple(row) for row in connection.execute('SELECT * FROM model_requests ORDER BY id')]
        rows,receipt=purpose.classify(ledger,links,'another-scope',scratch,pool=pool)
        assert not rows and not receipt['calls'] and [record['original_requests'][0]['state'] for record in receipt['records']]==original_states
        with ledger.connect() as connection:assert before==[tuple(row) for row in connection.execute('SELECT * FROM model_requests ORDER BY id')]
    links=[{'uri':f'https://offline.example/{section}/{index}'} for section in ('low','high','new') for index in range(8)]
    ranked=producer_dispatch.rank_sections(links,{'high':{'NEW':9},'low':{'DUPLICATE':6,'NEW':1}})
    order=[item['section_yield']['section'] for item in ranked]
    assert order[:10]==['high']*4+['new']+['high']*4+['new']
    return {'planning_queued_vs_dispatched':query_boundaries(pool,ledger,scratch),
            'target_isolation':True,'landing_alias_deduplication':True,'hash_route_preserved':True,
            'historical_cache_read_only':True,'held_request_states_unchanged':original_states,'rank_first_ten':order[:10]}


def run(project,scratch):
    scratch.mkdir(parents=True,exist_ok=False);report={'production':baseline(project,scratch)}
    def start(name):
        with (scratch/(name+'.log')).open('w') as log:
            return subprocess.Popen([sys.executable,'-B',__file__,str(project),str(scratch),'--worker',name],stdout=log,stderr=log)
    def finish(name,process):
        code=process.wait(timeout=90)
        if code:raise RuntimeError((scratch/(name+'.log')).read_text()[-4000:])
        return read(scratch/name/'offline.json')
    for name in ('serial','overlap','invalid','partial'):report[name]=finish(name,start(name))
    owner=start('owner');deadline=time.monotonic()+35
    try:
        while not (scratch/'owner-ready').exists():
            if owner.poll() is not None:raise RuntimeError(f"owner exited before dispatch: {finish('owner',owner)}")
            if time.monotonic()>deadline:raise RuntimeError('owner not ready')
            time.sleep(.05)
        report['peer']=finish('peer',start('peer'))
    finally:
        (scratch/'peer-finished').touch();report['owner']=finish('owner',owner)
    assert [report[name]['new'] for name in ('serial','overlap','owner','peer','invalid')]==[1,2,1,0,0],report
    assert report['owner']['counts']=={'probe_dispatch':1,'model_dispatch':1} and not report['peer']['counts'],report
    assert report['overlap']['counts']['probe_dispatch']==2 and report['invalid']['counts']['model_dispatch']==1
    assert list(report['overlap']['menus'][0])==['p1','p2']
    assert ['simplified_chinese_not_evidenced',None] in report['serial']['outcomes']
    assert ['invalid_business_decision','p1'] in report['invalid']['outcomes']
    assert report['partial']['new']==1 and report['partial']['counts']['model_dispatch']==1 and ['invalid_business_decision','p2'] in report['partial']['outcomes']
    report['edge_cases']=edge_cases(scratch)
    report['real_network_or_model_calls']=0;report['production_mutations']=0;save(scratch/'summary.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('scratch',type=Path);parser.add_argument('--worker');args=parser.parse_args()
    with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')), patch('socket.getaddrinfo',side_effect=AssertionError('DNS forbidden')):
        worker(args.scratch,args.worker) if args.worker else run(args.project,args.scratch)
