"""Run the untouched consumer CLI from an explicitly frozen source tree.

Only external HTTP/browser responses use the frozen disposable E2E fixture.
The parent publishes into ready.json's pool, then creates go.json. No source
from the current checkout is put on the child import path.
"""
import argparse
import asyncio
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('entry','target','saved_recovery','leased','matrix','race','old_writer',
                                         'category_run','batch_run','cohort_run','poll_run'),default='entry')
    args=parser.parse_args(); frozen=args.frozen.resolve(); out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path[:]=[str(frozen/p) for p in ('projects/code','projects/code/tests','projects/site-planner','projects/quality-inspector')]+[
        p for p in sys.path if 'WebCollect' not in p or 'site-packages' in p]
    # Keep the generated original save receipts and first-frame evidence after exit.
    class PersistentDirectory:
        def __init__(self,*a,**kw):self.name=tempfile.mkdtemp(dir=out)
        def cleanup(self):pass
        def __enter__(self):return self.name
        def __exit__(self,*args):pass
    tempfile.TemporaryDirectory=PersistentDirectory
    import test_pipeline_offline_e2e as fixture
    import webcollect.candidate_consumer as consumer
    import site_planner.candidate_pool as candidate_pool
    from webcollect.batch_core import load_json,save_json
    from site_planner.discovery_tools import reference
    from unittest.mock import patch
    f=fixture.PipelineAcceptance('test_joint_producer_cli_to_same_page_save_and_writeback'); f.setUp()
    def loaded_sources():
        manifest=json.loads((frozen.parent/'source-freeze.json').read_text())
        hashes={r['path']:r['sha256'] for r in manifest['files']}; loaded={}
        for name,module in list(sys.modules.items()):
            path=getattr(module,'__file__',None)
            if name.startswith(('webcollect','site_planner','quality_inspector')) and path and Path(path).suffix in ('.py','.js'):
                path=Path(path).resolve();assert path.is_relative_to(frozen),(name,str(path))
                sha=hashlib.sha256(path.read_bytes()).hexdigest();assert sha==hashes[str(path.relative_to(frozen))]
                loaded[name]={'path':str(path),'sha256':sha}
        return loaded
    command=f.cli_args('frozen','original-worker')
    metadata={'pool':str(f.pool.path),'uri':f.uri,'root':str(f.root),'producer_config':str(f.producer_cfg),
              'producer_ledger':str(f.producer_ledger),'history_set':str(f.chain),'command':command,
              'consumer_candidate':f.candidate,'mode':args.mode}
    if args.mode in ('leased','old_writer'):
        old_source={'origin':'codex_session','run_id':'frozen-old-writer','category_hint':'在线工具',
                    'references':[reference(f.chain.parent.parent/'explicit-source.json')]}
        metadata['old_candidate_id']=f.pool.put(f.v2,old_source)
        if args.mode=='leased':
            metadata['inflight_claim']=f.pool.claim_next('original-worker','frozen/0',protocols=(candidate_pool.VERSION2,))
    save_json(out/'ready.json',metadata)
    for _ in range(1200):
        if (out/'go.json').exists():break
        time.sleep(.1)
    else:raise TimeoutError('Parent did not publish fixture')
    go=load_json(out/'go.json'); results={}
    if args.mode=='category_run':command+=['--category','在线工具']
    if args.mode=='batch_run':command+=['--producer-batch',go['batch']]
    if args.mode=='cohort_run':command+=['--producer-batch',go['batch'],'--cohort',go['cohort']]
    if args.mode=='poll_run':command+=['--poll-seconds','1']
    if args.mode=='matrix':
        # Original CLI, unfiltered V1 visibility; additional original pool APIs
        # exercise selection options not exposed by the claim CLI.
        results['v1']=f.invoke(consumer.main,['--pool',str(f.pool.path),'claim','--worker-id','legacy','--request-id','v1'])
        for item in go['selections']:
            results[item['name']]=f.pool.claim_next('matrix',item['name'],protocols=(candidate_pool.VERSION2,),**item['kwargs'])
        for item in go.get('read_categories',[]):
            with f.pool.pool.connect() as con:
                row=con.execute('SELECT * FROM data_candidates WHERE candidate_id=?',(item,)).fetchone()
                results.setdefault('categories',{})[item]=f.pool._row_category(row,con)
        for cid,category in go.get('expected_categories',{}).items():
            assert results['categories'][cid]==category,(cid,results['categories'][cid],category)
        for item in go['selections']:
            actual=results[item['name']]
            if item.get('expected_state'):assert actual['state']==item['expected_state'],actual
            if item.get('expected_id'):assert actual['candidate_id']==item['expected_id'],actual
    else:
        with f.boundaries():
            empty_observer=None
            if args.mode=='poll_run':
                claim_next=candidate_pool.CandidatePool.claim_next
                def observe_empty(pool,*a,**kw):
                    result=claim_next(pool,*a,**kw)
                    if result['state']=='EMPTY' and not (out/'poll-empty.json').exists():
                        save_json(out/'poll-empty.json',{'state':'EMPTY','request':a,'kwargs':kw})
                    return result
                empty_observer=patch.object(candidate_pool.CandidatePool,'claim_next',observe_empty)
                empty_observer.start()
            if args.mode=='leased':
                original=f.pool.claim_next('original-worker','frozen/0',protocols=(candidate_pool.VERSION2,))
                f.pool.heartbeat(original)
                results['lease_before']=original
            if args.mode=='race':
                import multiprocessing
                context=multiprocessing.get_context('fork'); queue=context.Queue();start=context.Event()
                def worker(i):
                    start.wait(10)
                    try:
                        result=f.invoke(consumer.main,f.cli_args('frozen'+str(i),'original-worker'+str(i)))[0]
                        queue.put({'result':result,'gotos':f.gotos,'loaded_sources':loaded_sources()})
                    except Exception as error:queue.put({'error':repr(error)})
                children=[context.Process(target=worker,args=(i,)) for i in range(2)]
                for child in children:child.start()
                start.set(); race=[queue.get(timeout=40) for _ in children]
                for child in children:
                    child.join(5);assert child.exitcode==0
                assert sorted(r['result']['state'] for r in race)==['EMPTY','succeeded'],race
                winner=next(r for r in race if r['result']['state']=='succeeded')
                results['race']=race;results['result']=winner['result'];f.gotos=winner['gotos']
            elif args.mode=='saved_recovery':
                with patch.object(consumer,'finish_or_reconcile',side_effect=OSError('OFFLINE after save before writeback')):
                    try:
                        first=f.invoke(consumer.main,command)
                    except OSError as error:
                        first={'expected_crash':str(error)}
                results['before_reconcile']=first
                cid=f.pool.rows(protocols=(candidate_pool.VERSION2,))[0]['candidate_id']
                with f.pool.pool.connect() as con: claim_id=con.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=?',(cid,)).fetchone()[0]
                results['result']=f.invoke(consumer.main,['--pool',str(f.pool.path),'reconcile','--claim-id',claim_id])
            else:
                response=f.invoke(consumer.main,command)
                results['result']=response['results'][0] if args.mode=='cohort_run' else response[0]
                if args.mode=='cohort_run':results['cohort_result']=response
            if empty_observer:empty_observer.stop()
            row,claim,task=f.assert_complete(results['result'])
            results.update(candidate_id=row['candidate_id'],claim=claim,task=task,
                           first_frame=f.ledger.get(claim['binding']['entry_job_id'])['result'],gotos=f.gotos,
                           saved=results['result']['result']['save_receipt'],statistics=consumer.statistics(f.pool))
            assert results['statistics']['QC_accepted']==0
            assert results['statistics']['published']==0
            assert len(f.gotos)==1
            from webcollect.planning import verify_evidence
            verify_evidence(list(results['first_frame'].values()))
            if args.mode=='leased':
                assert claim['snapshot']==metadata['inflight_claim']['snapshot']
                assert claim['sources']==metadata['inflight_claim']['sources']
                assert claim['token']==metadata['inflight_claim']['token']
            results['replay_claim']=f.pool.claim_next(claim['worker_id'],claim['request_id'],protocols=(candidate_pool.VERSION2,))
            assert results['replay_claim']['claim_id']==claim['claim_id']
            if args.mode=='target':
                assert claim['snapshot']['requested_goal']==go['requested_goal']
    loaded=loaded_sources()
    save_json(out/'result.json',{'status':'PASS','external_IO':'frozen synthetic HTTP/browser only',
                              'loaded_sources':loaded,'command':command,'results':results})
    print(json.dumps({'status':'PASS','output':str(out),'loaded_modules':len(loaded)}))


if __name__=='__main__':main()
