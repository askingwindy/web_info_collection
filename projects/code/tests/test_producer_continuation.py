from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from site_planner.candidate_discovery import read_directions, produce_entries
from site_planner.discovery_agent import model_tool_decision, SettledSelectionRejected
from site_planner.producer_authority import authorize
from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json, save_json
from webcollect.candidate_project import initialize
from webcollect.candidate_accounting import build_report
from site_planner.candidate_pool import CandidatePool, VERSION2
from site_planner.discovery_tools import reference


class Continuation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        cfg = load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        cfg['budget'].update(max_discovery_candidates=1,max_probe_pages=1)
        self.path = initialize(self.root/'project','unit',{'max_worker_seconds':15},cfg,cfg)
        self.scope = load_json(self.path)
        self.ledger = self.role('producer',True)

    def role(self,name,initialize=False):
        return BatchLedger(self.scope[name+'_db'],load_json(self.scope[name+'_config']),initialize=initialize)

    def test_independent_work_uses_original_accounting(self):
        ledger = self.ledger
        purpose = 'ai-candidate-entry-tool-1'
        payload = {'sources':[{'uri':'https://first.example.org/old'}]}
        frozen = {'protocol':'native-tool-1','input':payload,'tools':[],'system':'test','reasoning_effort':'low'}
        jid = ledger.enqueue(purpose,frozen)
        ledger.claim(purpose,job_id=jid)
        with ledger.transaction() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started) "
                        "VALUES('uncertain',?,?,0,'reserved',10,20,1)",(jid,purpose))
            con.execute('UPDATE jobs SET lease=0 WHERE id=?',(jid,))
        ledger.recover()
        ledger.consume('discovery_candidates','before')
        ledger.consume('discovery_candidates','after')
        self.assertEqual(ledger.summary()['resources'],[{'kind':'discovery_candidates','used':2}])
        authorize(self.path,['uncertain'],'test explicit producer decision')
        ledger = self.role('producer')
        ledger.consume('discovery_candidates','after')
        self.assertGreater(ledger.remaining_seconds(),1e9)
        consumer = self.role('consumer',True)
        consumer.consume('discovery_candidates','item')
        consumer.consume('discovery_candidates','other')
        self.assertIsNone(consumer.producer_policy)
        gateway=Mock()
        gateway.call_tool.return_value={'arguments':{}}
        allowed={'system':'test','isolated_requests':['uncertain']}
        with self.assertRaises(OutcomeUnknown):
            model_tool_decision(ledger,gateway,purpose,payload,[],**allowed)
        with self.assertRaises(OutcomeUnknown):
            model_tool_decision(ledger,gateway,purpose,{'sources':[{'uri':'https://first.example.org/other'}]},[],**allowed)
        with self.assertRaises(OutcomeUnknown):
            model_tool_decision(ledger,gateway,purpose,{'sources':[{'uri':'http://www.first.example.org/other'}]},[],**allowed)
        independent={'sources':[{'uri':'https://other.example.org/new'}]}
        with self.assertRaises(OutcomeUnknown):
            model_tool_decision(ledger,gateway,purpose,independent,[],system='test')
        model_tool_decision(ledger,gateway,purpose,independent,[],**allowed)
        model_tool_decision(ledger,gateway,purpose,independent,[],**allowed)
        self.assertEqual(gateway.call_tool.call_count,1)
        with ledger.connect() as con:
            self.assertEqual(tuple(con.execute("SELECT state,usage,reserved_tokens FROM model_requests WHERE id='uncertain'").fetchone()),('unknown',None,10))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM resources").fetchone()[0],2)

    def test_cli_directions_accepts_both_documented_inputs(self):
        directions=[{'direction':'检索','category':'UNKNOWN','queries':['图书检索']}]
        for i,data in enumerate([directions,{'directions':directions}]):
            path=self.root/f'directions-{i}.json'
            save_json(path,data)
            self.assertEqual(read_directions(path),directions)
        path=self.root/'invalid-directions.json'
        save_json(path,{'queries':[]})
        with self.assertRaises(ValueError):
            read_directions(path)

    def test_role_totals_shared_allocation_and_consumer_results(self):
        ledger = self.ledger
        pool = CandidatePool(self.scope['pool'])
        job = ledger.enqueue('ai-candidate-entry-tool-1',{'batch':1})
        def receipt(account,rid,jid,usage):
            with account.transaction() as con:
                con.execute('INSERT INTO model_requests(id,job_id,purpose,attempt,state,started,usage,reserved_tokens,reserved_cost) '
                            'VALUES(?,?,?,0,?,1,?,40,1)',(rid,jid,'test','succeeded' if usage else 'unknown',
                            json.dumps(dict(zip(('input_tokens','output_tokens'),usage))) if usage else None))
        receipt(ledger,'discovery',job,(11,5))
        receipt(ledger,'unallocated',ledger.enqueue('discovery-other',{}),(2,3))
        receipt(ledger,'old-unknown',ledger.enqueue('discovery-quarantined',{}),None)
        ids=[]
        for i in range(2):
            candidate={'schema_version':VERSION2,'candidate_kind':'entry','entry_url':f'https://site{i}.example.org/','requested_goal':None}
            header={'row_id':str(i),'run_id':'batch','batch':0,'request_id':job,'response_sha256':str(i),'raw_index':i}
            ids.append(pool.publish_row(header,candidate,{'origin':'glm_agent','run_id':'unit-producer',
                       'references':[reference(self.path)]})['candidate_id'])
        consumer=self.role('consumer',True)
        planning=consumer.enqueue('candidate-planning',{})
        receipt(consumer,'plan',planning,(7,1))
        receipt(consumer,'unbound',consumer.enqueue('diagnostic',{}),(2,1))
        claim=pool.claim_next('w','take',candidate_id=ids[0],protocols=[VERSION2])
        pool.stage(claim,'planning',{'planning_jobs':[planning]})
        pool.finish(claim,state='failed',stage='planning',reason='fixture failure')
        report=build_report(self.scope,batches=['batch'],since=0)
        prod=report['roles']['producer']['window']
        self.assertEqual((prod['known_input_tokens'],prod['known_output_tokens'],prod['total_tokens']),(13,8,None))
        self.assertEqual([x['id'] for x in prod['unsettled']],['old-unknown'])
        self.assertEqual(report['roles']['consumer']['project']['total_tokens'],11)
        self.assertEqual(report['roles']['consumer']['linked_to_selected_candidates_in_window']['total_tokens'],8)
        self.assertEqual(report['roles']['consumer']['other_window_requests']['total_tokens'],3)
        self.assertEqual(report['roles']['producer']['linked_to_selected_candidates_in_window']['total_tokens'],16)
        self.assertEqual(report['unlinked_project_consumer']['total_tokens'],3)
        self.assertEqual(report['unallocated_project_discovery']['known_total_tokens'],5)
        one,two=report['candidates']
        self.assertEqual([r['discovery_tokens']['allocated']['total_tokens'] for r in (one,two)],[9,7])
        self.assertEqual(one['consumer_result']['glm']['total_tokens'],8)
        self.assertEqual(one['consumer_result']['claims'][0]['reason'],'fixture failure')
        self.assertEqual(two['consumer_result']['state'],'unclaimed')

    def test_settled_bad_selection_advances_to_other_query_and_replays_without_sending(self):
        scope=self.scope
        from application_discovery_fixtures import seed
        seed(CandidatePool(scope['pool']),self.path.parent,'https://second.example.org/tool')
        authorize(self.path,[],'explicit unlimited producer for this project')
        source={'uri':'https://second.example.org/tool','title':'第二个工具','content':'主营科学计算',
                'index':0,'reference':reference(self.path)}
        def search(_pool,_run,_model,query,_out,**opts):
            self.assertIsNone(opts.get('maximum'))
            return {'request_id':query,'results':[dict(source,uri='https://'+query+'.example.org/tool')]}
        invalid=SettledSelectionRejected('bad-job',['bad-request'])
        envelope={'request_id':'good','tool_call_id':'tc','name':'submit_candidates',
                  'arguments':{'candidates':[{'source_index':0}]},'assistant_message':{'tool_calls':[]}}
        kwargs=dict(pool_path=scope['pool'],ledger_path=scope['producer_db'],history_set=scope['history_set'],
                    queries=['first','second'],target=1,batch_size=1,
                    model_protocol='entry-tools-2',batch_key='independent')
        config=load_json(scope['producer_config'])
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search) as queries, \
             patch('site_planner.candidate_discovery.model_tool_decision',side_effect=[invalid,('good-job',envelope)]) as model, \
             patch('site_planner.entry_access.fetch_status',side_effect=lambda uri,*_: (200,uri)):
            result=produce_entries(config,**kwargs)
            self.assertEqual(result['listed_unique_candidates'],1,result.get('stopped'))
            self.assertEqual(produce_entries(config,**kwargs)['new_candidates_this_invocation'],0)
            self.assertEqual((queries.call_count,model.call_count),(2,2))
        pool=CandidatePool(scope['pool'])
        receipt=pool.pool.checkpoint(config['run_id']+'/entry-batch/independent','entry-batch/0/committed')
        self.assertEqual(receipt['selection_rejected'],invalid.receipt)

    def test_original_paid_invalid_response_is_not_retried_or_called_unknown(self):
        authorize(self.path,[],'continue only independent paid selections')
        ledger=self.role('producer')
        kind='ai-candidate-entry-tool-1'
        payload={'sources':[{'uri':'https://paid.example.org/'}]}
        jid=ledger.enqueue(kind,{'protocol':'native-tool-1','input':payload,'tools':[],
                                'system':'test','reasoning_effort':'low'})
        job=ledger.claim(kind,job_id=jid)
        with ledger.transaction() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,usage) "
                        "VALUES('bad',?,?,0,'invalid_response',100,1,1,?)",(jid,kind,json.dumps({'input_tokens':15,'output_tokens':5})))
        ledger.finish(job,'review_required',error='ValueError')
        gateway=Mock()
        with self.assertRaises(SettledSelectionRejected) as caught:
            model_tool_decision(ledger,gateway,kind,payload,[],system='test')
        self.assertEqual(caught.exception.receipt['request_ids'],['bad'])
        gateway.call_tool.assert_not_called()

    def test_search_rate_limit_waits_before_other_query_and_preserves_charge_unknown(self):
        scope=self.scope
        authorize(self.path,[],'continue other sources, maintain rate limits')
        calls=[]
        def search(pool,run,model,query,root,**opts):
            calls.append(query)
            rid,_=pool.reserve_tool(run,'search',query,{'search_query':query})
            if query=='first':
                pool.settle_tool(rid,'unknown',{'http_status':429,'retry_after_seconds':120,'outcome_and_charge':'UNKNOWN'})
                raise OutcomeUnknown('rate limited')
            result={'request_id':rid,'results':[]}
            pool.settle_tool(rid,'succeeded',result)
            return result
        cfg=load_json(scope['producer_config'])
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search), \
             patch('site_planner.candidate_discovery.time.sleep') as pause:
            result=produce_entries(cfg,pool_path=scope['pool'],ledger_path=scope['producer_db'],history_set=scope['history_set'],
                queries=['first','second'],target=1,batch_size=1,max_batches=1,
                model_protocol='entry-tools-2',batch_key='rate')
        self.assertEqual(calls,['first','second'])
        self.assertGreater(pause.call_args.args[0],119)
        self.assertEqual({r['state']:r['count'] for r in result['search_usage']},{'unknown':1,'succeeded':1})

    def test_only_explicit_content_refusal_can_use_independent_successor(self):
        from test_model_provider_protocols import ProviderProtocolTests
        config_dir=Path(__file__).resolve().parents[1]/'config'
        path=initialize(self.root/'other','other',{'max_worker_seconds':15},
                        ProviderProtocolTests().config('glm'),load_json(config_dir/'batch-synthetic.json'))
        scope=load_json(path);ledger=BatchLedger(scope['producer_db'],load_json(scope['producer_config']),initialize=True)
        for rid,http,code in [('refused',400,'1301'),('balance',429,'1113'),('auth',401,'1001')]:
            kind='ai-candidate-entry-tool-1'
            jid=ledger.enqueue(kind,{'input':{'sources':[{'uri':'https://'+rid+'.example.org/'}]}})
            job=ledger.claim(kind,job_id=jid)
            with ledger.transaction() as con:
                con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,finished,error,response) "
                            "VALUES(?,?,?,0,'unknown',100,1,1,2,?,?)",(rid,jid,kind,'HTTPError:'+str(http),
                            json.dumps({'provider_error':{'http_status':http,'provider_code':code}})))
            ledger.finish(job,'review_required',error='OutcomeUnknown')
        for other in ('auth','balance'):
            with self.assertRaises(ValueError):authorize(path,[other],'do not release account holds')
        decision=authorize(path,['refused'],'preserve refusal and use other sources')
        self.assertEqual(decision['deferred']['refused']['provider_refusal']['usage'],'UNKNOWN')
        with ledger.connect() as con:
            self.assertEqual(tuple(con.execute("select state,usage from model_requests where id='refused'").fetchone()),('unknown',None))

    def test_closed_producer_get_only_holds_its_uri_on_project_opt_in(self):
        from test_model_provider_protocols import ProviderProtocolTests
        from site_planner.entry_access import check_entry
        from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
        path=initialize(self.root/'uri-project','uri-project',{'max_worker_seconds':15},
                        ProviderProtocolTests().config('glm'),self.ledger.config)
        scope=load_json(path)
        ledger=BatchLedger(scope['producer_db'],load_json(scope['producer_config']),initialize=True)
        guard=SiteFailureStore(ledger.config['site_failure_guard'])
        first='https://www.tools.example.org/retirement/'
        second='https://www.tools.example.org/scientific/'
        with patch('site_planner.entry_access.fetch_status',side_effect=ConnectionResetError('test closed')):
            record,ref=check_entry(ledger,'a',first,self.root)
        self.assertEqual(record['result'],'HELD')
        with self.assertRaises(SiteStopped):guard.guard(second)
        with self.assertRaises(ValueError):
            guard.enable_closed_entry_uri_scope(scope['history_set'],scope['consumer_db'],'operator decision')
        guard.enable_closed_entry_uri_scope(scope['history_set'],scope['producer_db'],'operator decision')
        for original in (first,first+'?utm_source=test#other','http://tools.example.org/retirement'):
            with self.assertRaisesRegex(SiteStopped,'entry_uri_hold'):guard.guard(original)
        self.assertEqual(guard.guard(second)['unknown_execution_count'],1)
        with patch('site_planner.entry_access.fetch_status',side_effect=lambda uri,*_: (200,uri)) as fetch:
            self.assertEqual(check_entry(ledger,'b',second,self.root)[0]['result'],'PASS')
            self.assertEqual(fetch.call_count,1)
        with ledger.connect() as con:
            self.assertEqual(tuple(con.execute("select state,count(*) from top_level_visits where target_uri=? group by state",(first,)).fetchone()),('unknown',1))
            con.execute("update jobs set state='running' where id=?",(record['job_id'],))
            con.commit()
        with self.assertRaises(SiteStopped):guard.guard(second)
        with ledger.connect() as con:
            con.execute("update jobs set state='done' where id=?",(record['job_id'],))
            con.commit()
        guard.record(second,'formal:separate-original',stage='formal',state='unknown',reason='original interrupted',
                     real_execution=True,evidence=[ref],usage_refs=[])
        with self.assertRaisesRegex(SiteStopped,'unknown_hold'):guard.guard(second)
