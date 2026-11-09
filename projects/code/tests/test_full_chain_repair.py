"""Disposable schema/state/account tests; no real provider or production writes."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,time,unittest
from jsonschema import Draft202012Validator
from webcollect.banded_plan import bind_reply_scope, plan_schema, choice_schema, proves
from webcollect.model_gateway import schema_error_feedback
from webcollect.agent_controller import exclusive
from webcollect.candidate_consumer import finish_or_reconcile
from site_planner.site_pool import SitePool
from site_planner.candidate_pool import CandidatePool

class Protocol(unittest.TestCase):
    def test_missing_focus_semantics_derived_only_from_one_visible_bound_node(self):
        prompt={'attempt_id':'a','observation':{'observation_id':'o','rendered_dom':[{'node':'e1','text':'搜索','labels':['搜索网页']} ]}}
        reply={'steps':[{'action':'click','target':{'node':'e1','text':'搜索网页'},'expected':{'kind':'focused'}}]}
        self.assertEqual(bind_reply_scope(reply,prompt)['steps'][0]['expected']['text'],'搜索网页')
        self.assertNotIn('text',reply['steps'][0]['expected'])
        for rows,text,node in [([], '搜索网页','e1'),(prompt['observation']['rendered_dom']*2,'搜索网页','e1'),(prompt['observation']['rendered_dom'],'错标签','e1')]:
            bad=deepcopy(reply);bad['steps'][0]['target'].update(text=text,node=node)
            with self.assertRaises(ValueError):bind_reply_scope(bad,{'attempt_id':'a','observation':{'observation_id':'o','rendered_dom':rows}})
    def test_schema_error_reports_extra_stop_without_dump(self):
        reply={'choice':'replan','plan':{'steps':[{'action':'scroll','direction':'down','purpose':'阅读','expected':{'kind':'scroll_changed'}}],'stop':{'finish_when':{'kind':'goal_evidence'}}}}
        try:Draft202012Validator(choice_schema(True,inherited=True)).validate(reply)
        except Exception as e:feedback=schema_error_feedback(e)
        self.assertTrue(any('stop' in x['field_path'] for x in feedback),feedback)
        self.assertLess(len(json.dumps(feedback)),2000)
    def test_focus_transition_only_after_same_document_unique_semantics(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'s.json';base={'document_identity':{'id':'a'},'url':'https://x/','elements':[{'element_id':'old','inputable':True,'text':'搜索'}]}
            new={'document_identity':{'id':'a'},'url':'https://x/'};path.write_text(json.dumps(new))
            c={'element':{'visible':True,'inputable':True,'text':'搜索'},'value':{'focused':True},'readable_labels':[]}
            ob={'capture_verified':True,'evidence':{'state':{'path':str(path)}},'controls':{'new':c}}
            self.assertTrue(proves({'kind':'focused','text':'搜索'},ob,base,'old'))
            for mode in ('ambiguous','wrongfocus','document','beforelabel'):
                b=deepcopy(base);o=deepcopy(ob);s=deepcopy(new)
                if mode=='ambiguous':o['controls']['second']=deepcopy(c)
                if mode=='wrongfocus':o['controls']['new']['value']['focused']=False
                if mode=='document':s['document_identity']={'id':'b'}
                if mode=='beforelabel':b['elements'][0]['text']='其他'
                path.write_text(json.dumps(s));self.assertFalse(proves({'kind':'focused','text':'搜索'},o,b,'old'),mode)

class Research(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        SitePool(self.root/'pool.db',initialize=True);self.pool=CandidatePool(self.root/'pool.db',install=True)
        source=exclusive(self.root/'source.json',{'controlled':True})
        body={'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry','entry_url':'https://example.org/','requested_goal':None}
        self.cid=self.pool.put(body,{'origin':'codex_session','run_id':'local','references':[source],'category_hint':'在线工具','application_hint':'本地'})
        self.old=self.pool.claim_next('w','old',candidate_id=self.cid,protocols=('webcollect-data-candidate-2',))
        self.obj=exclusive(self.root/'session-objective.json',{'schema_version':'webcollect-session-objective-1','candidate_id':self.cid,'version':self.old['version'],'entry_url':body['entry_url'],'requested_goal':None,'objective':{'description':'固定目标','minimum_effective_steps':6,'preferred_band':'long'}})
        self.auth=exclusive(self.root/'authorization.json',{'scope':'explicit same-target development'})
        self.result={'sample_id':'old','registry':str(self.root/'registry'),'scope_id':'old','task_key':'old'}
        from webcollect.planning import canonical
        with self.pool.transaction() as con:
            con.execute("UPDATE candidate_claims SET state='succeeded',binding=? WHERE claim_id=?",(canonical({'output':str(self.root)}),self.old['claim_id']))
            con.execute("UPDATE data_candidates SET state='succeeded' WHERE candidate_id=?",(self.cid,))
            con.execute("INSERT INTO candidate_results VALUES(?,?,?,?,?,NULL,1)",(self.cid,self.old['claim_id'],'old',canonical(self.result),'pending_review'))
    def claim(self,request='research'):
        return self.pool.claim_research('w',request,candidate_id=self.cid,version=self.old['version'],original_claim_id=self.old['claim_id'],objective=self.obj,authorization=self.auth)
    def original(self):
        with self.pool.pool.connect() as con:return tuple(con.execute('SELECT state FROM data_candidates WHERE candidate_id=?',(self.cid,)).fetchone()),tuple(con.execute('SELECT * FROM candidate_results WHERE effective=1').fetchone())
    def test_research_duplicate_exception_requires_frozen_and_live_authorization(self):
        from webcollect.current_chain import initialize_chain
        from webcollect.candidate_contract import research_duplicate_basis, VERSION
        from webcollect.react_session import REACT_VERSION
        from webcollect.planning import canonical
        registry=self.root/'registry';manifest=self.root/'chain/manifest.json'
        initialize_chain(manifest,registry,chain_id='local',current_result_roots=[self.root/'results'])
        self.auth=exclusive(self.root/'scoped-authorization.json',{'scope':'original-two-baselines-only',
            'candidate_id':self.cid,'version':self.old['version'],'objective':self.obj,'production_counted':False})
        original_binding={'output':str(self.root),'registry':str(registry)}
        with self.pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',(canonical(original_binding),self.old['claim_id']))
        claim=self.claim();bound={**claim['binding'],'registry':str(registry),'history_set':str(manifest)}
        with self.pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',(canonical(bound),claim['claim_id']))
        claim=self.pool.get_claim(claim['claim_id']);frozen={**claim,'pool':str(self.pool.path)}
        ref=exclusive(self.root/'research-claim.json',frozen)
        binding={'schema_version':VERSION,'candidate_id':self.cid,'claim_id':claim['claim_id'],
                 'version':claim['version'],'candidate':claim['snapshot'],'claim_reference':ref}
        task={'candidate_binding':binding,'fragment':{'schema_version':REACT_VERSION,'candidate_attempt':claim['claim_id']},
              'workflow_proposal':{'spec':{'goal':{'structured':None}}}}
        self.assertEqual(research_duplicate_basis(task,registry)['original_sample_id'],'old')
        self.assertIsNone(research_duplicate_basis({'research_replay':claim['binding']['research_replay']},registry))
        with self.assertRaisesRegex(ValueError,'registry'):research_duplicate_basis(task,self.root/'other-registry')
        with self.pool.transaction() as con:
            con.execute("DELETE FROM candidate_events WHERE claim_id=? AND kind='research_claimed'",(claim['claim_id'],))
        with self.assertRaisesRegex(ValueError,'authorization'):research_duplicate_basis(task,registry)

    def test_failure_expiry_and_idempotency_preserve_original(self):
        before=self.original();claim=self.claim();self.assertEqual(claim,self.claim())
        with self.assertRaises(ValueError):self.claim('concurrent')
        self.pool.finish(claim,state='failed',reason='known',stage='capture');self.assertEqual(before,self.original())
        claim=self.claim('next')
        with self.pool.transaction() as con:con.execute('UPDATE candidate_claims SET expires=0 WHERE claim_id=?',(claim['claim_id'],))
        self.pool.claim_next('other','expiry-sweep');self.assertEqual(before,self.original())
        with self.assertRaises(ValueError):self.claim('unknown-resend')
    def test_save_and_reconcile_keep_nonproduction_result(self):
        before=self.original();claim=self.claim();new={**self.result,'sample_id':'research'}
        with patch('webcollect.candidate_consumer.verified_saved',return_value=new),patch('webcollect.site_pool_sync.sync_candidate_qc'):
            r=finish_or_reconcile(self.pool,claim);self.assertTrue(r['saved'])
            self.assertEqual(r,finish_or_reconcile(self.pool,claim,reconciliation=True))
        self.assertEqual(before,self.original())
        with self.pool.pool.connect() as con:self.assertEqual(con.execute("SELECT effective FROM candidate_results WHERE claim_id=?",(claim['claim_id'],)).fetchone()[0],0)

class ResearchQC(Research):
    def test_new_qc_and_later_old_qc_preserve_result_ownership(self):
        from webcollect.site_pool_sync import sync_candidate_qc
        before=self.original();claim=self.claim();new={**self.result,'sample_id':'research','task_key':'research','scope_id':'research'}
        with patch('webcollect.candidate_consumer.verified_saved',return_value=new),patch('webcollect.site_pool_sync.sync_candidate_qc'):
            finish_or_reconcile(self.pool,claim)
        report=exclusive(self.root/'controlled-qc.json',{'fixture':True})
        old_pass=False
        def snapshot(registry,scope):
            passed=scope=='research' or old_pass
            return {'tasks':[{'task_key':scope,'production_status':'reviewed_pass' if passed else 'collected_pending_review',
                              'qc':{'report':report,'status':'PASS'} if passed else None}]}
        with patch('webcollect.site_pool_sync._snapshot',side_effect=snapshot),patch('webcollect.runtime._bound_quality_report'):
            sync_candidate_qc(self.pool.path,self.result['registry'])
            self.assertEqual(before,self.original())
            with self.pool.pool.connect() as con:
                self.assertEqual(tuple(con.execute('SELECT effective,qc_state FROM candidate_results WHERE claim_id=?',(claim['claim_id'],)).fetchone()),(0,'accepted'))
            old_pass=True;sync_candidate_qc(self.pool.path,self.result['registry'])
            with self.pool.pool.connect() as con:
                self.assertEqual(tuple(con.execute('SELECT effective,qc_state FROM candidate_results WHERE claim_id=?',(self.old['claim_id'],)).fetchone()),(1,'accepted'))
                self.assertEqual(tuple(con.execute('SELECT effective,qc_state FROM candidate_results WHERE claim_id=?',(claim['claim_id'],)).fetchone()),(0,'accepted'))

class DirectReading(unittest.TestCase):
    def test_direct_article_requires_search_submission_title_and_body(self):
        from test_contracted_goal import ContractedGoal
        from webcollect.goal_evidence import progress
        f=ContractedGoal();f.setUp();self.addCleanup(f.doCleanups)
        button=('send','button','搜索',None,None)
        f.view('entry','entry',[('q','input','站内搜索','',None),button])
        f.view('typed','entry',[('q','input','站内搜索','河流',None),button])
        quote='水体流速减慢之后，原先搬运的物质会沉积在河床上。'
        f.view('land','article',[('h','h1','河流',None,None),('p','p',quote,None,None)])
        steps=[f.operation('type','type','entry','typed','q','河流'),f.operation('submit','click','typed','land','send')]
        session=f.session('land',steps)
        self.assertEqual(progress(session,'entry',f.reading)['status'],'PASSAGE_AVAILABLE')
        self.assertEqual(progress(session,'entry',f.reading)['opened_results'][0]['source'],'verified_search_submission_direct_article')
        passage=progress(session,'entry',f.reading)['passages'][0]
        session.answer_citation=exclusive(f.root/'cite.json',{'kind':'plan-branch','boundary':f.binding,
            'response':{'choice':'cite:p','attempt_id':'a','observation_id':'land'},'provider_reply':{'choice':'cite:p'},'options':[{'choice':'cite:p','passage':passage}]})
        session.task={'fragment':{'action_stability_protocol':'webcollect-search-submit-link-stability-3','plan_protocol':'webcollect-banded-conditional-plan-8',
            'session_objective':{'objective':{'description':'检索河流并往下阅读'}}}}
        self.assertEqual(progress(session,'entry',f.reading)['status'],'READING_REQUIRED')
        session.task['fragment']['session_objective']['objective']['description']='检索河流并阅读首屏'
        self.assertEqual(progress(session,'entry',f.reading)['status'],'VERIFIED')
        session.task['fragment']['session_objective']['objective']['description']='检索河流并往下阅读'
        f.view('lower','article',[('p2','p','流速改变会影响水体中细颗粒的沉积过程，继续阅读正文。',None,None)],y=400)
        session.trajectory.append(f.operation('scroll','scroll','land','lower'))
        session.current=f.obs['lower']
        self.assertEqual(progress(session,'entry',f.reading)['status'],'VERIFIED')
        session.trajectory[1]['target']['control_id']='wrong'
        self.assertEqual(progress(session,'entry',f.reading)['status'],'UNVERIFIED')

class FollowupProof(unittest.TestCase):
    def test_link_scope_preserves_href_node_pixels_and_values(self):
        from webcollect.action_stability import followup_scope,pair
        from PIL import Image
        import io
        def png(local=False,outer=False):
            image=Image.new('RGB',(300,200),'white')
            if local:image.putpixel((30,30),(255,0,0))
            if outer:image.putpixel((250,180),(255,0,0))
            b=io.BytesIO();image.save(b,format='PNG');return b.getvalue()
        e={'element_id':'a','visible':True,'enabled':True,'clickable':True,'text':'实际文章','bbox':[20,20,150,50]}
        b={'element_id':'a','tag':'a','href':'https://test.invalid/article','selector':'a','index':0}
        state={'elements':[e],'capture_controls':[b],'geometry_witnesses':[{'element_id':'a','samples':[{'ancestor':True}]*9}],
               'screen_resolution':[300,200],'device_pixel_ratio':1,'document_identity':{'id':1},'url':'https://test.invalid/','scroll':[0,0],
               'values':[],'capture_readiness':{'document_ready':'complete','fonts_ready':True,'images_ready':True}}
        scope=followup_scope(state,'a','click');a=png()
        self.assertTrue(pair(state,state,a,png(outer=True),scope)['accepted'])
        self.assertFalse(pair(state,state,a,png(local=True),scope)['accepted'])
        for field,value in [('href','https://wrong.invalid/'),('selector','other')]:
            changed=deepcopy(state);changed['capture_controls'][0][field]=value
            self.assertFalse(pair(state,changed,a,a,scope)['accepted'])
        changed=deepcopy(state);changed['elements'][0]['element_id']='replacement'
        self.assertFalse(pair(state,changed,a,a,scope)['accepted'])
        from webcollect.action_stability import reading_scope
        state['elements'].append({'element_id':'main','native_role':'main','visible':True,'bbox':[0,0,200,150]})
        state['capture_controls'][0]['selector']='main > a'
        state['capture_controls'].append({'element_id':'main','selector':'main'})
        readscope=reading_scope(state)
        self.assertTrue(pair(state,state,a,png(outer=True),readscope)['accepted'])
        for mode in ('text','geometry','value','document'):
            changed=deepcopy(state)
            if mode=='text':changed['elements'][0]['text']='错误文章'
            if mode=='geometry':changed['elements'][0]['bbox']=[25,20,155,50]
            if mode=='value':changed['values']=[{'element_id':'q','value':'wrong'}]
            if mode=='document':changed['document_identity']={'id':2}
            self.assertFalse(pair(state,changed,a,a,readscope)['accepted'],mode)
        self.assertFalse(pair(state,state,a,png(local=True),readscope)['accepted'])


class ResearchV2(unittest.TestCase):
    """Failed fixed baseline + named comparison; original rows stay unchanged."""
    def setUp(self):
        Research.setUp(self)
        from webcollect.batch_core import BatchLedger
        from webcollect.current_chain import initialize_chain
        from webcollect.planning import canonical
        self.registry = self.root/'registry'
        self.manifest = self.root/'chain/manifest.json'
        self.scope = initialize_chain(self.manifest, self.registry, chain_id='local',
                                      current_result_roots=[self.root/'results'])
        config = json.loads((Path(__file__).resolve().parents[1]/'config/batch-no-model.json').read_text())
        self.ledger = BatchLedger(self.root/'ledger.sqlite3', config, initialize=True)
        self.receipt = exclusive(self.root/'results/old/saved_sample.json', {'sample_id':'old'})
        body = {'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry',
                'entry_url':'https://example.org/comparison','requested_goal':None}
        source = exclusive(self.root/'comparison-source.json', {'fixture':True})
        comparison_id = self.pool.put(body, {'origin':'codex_session','run_id':'comparison',
            'references':[source],'category_hint':'在线工具','application_hint':'本地'})
        self.comparison_claim = self.pool.claim_next('w','comparison',candidate_id=comparison_id,
                                                     protocols=('webcollect-data-candidate-2',))
        self.result = {**self.result, 'registry':str(self.registry), 'save_receipt':self.receipt,
                       'result_location':str(self.root/'results/samples/old')}
        old_binding = {'output':str(self.root),'registry':str(self.registry),
                       'history_set':str(self.manifest),'ledger':str(self.ledger.path)}
        with self.pool.transaction() as con:
            con.execute('DELETE FROM candidate_results WHERE claim_id=?',(self.old['claim_id'],))
            con.execute("UPDATE candidate_claims SET state='failed',binding=?,reason='known_failure' WHERE claim_id=?",
                        (canonical(old_binding), self.old['claim_id']))
            con.execute("UPDATE data_candidates SET state='failed' WHERE candidate_id=?",(self.cid,))
            con.execute("UPDATE candidate_claims SET state='succeeded',binding=? WHERE claim_id=?",
                        (canonical({'registry':str(self.registry)}),self.comparison_claim['claim_id']))
            con.execute("UPDATE data_candidates SET state='succeeded' WHERE candidate_id=?",(comparison_id,))
            con.execute("INSERT INTO candidate_results VALUES(?,?,?,?,?,NULL,1)",
                        (comparison_id,self.comparison_claim['claim_id'],'old',canonical(self.result),'pending_review'))
        self.comparisons = [{'role':'comparison','claim_id':self.comparison_claim['claim_id'],
                             'sample_id':'old','save_receipt':self.receipt}]
        self.auth = self.authorization(self.obj)

    def authorization(self, objective, comparisons=None, name='v2-authorization.json'):
        return exclusive(self.root/name, {'scope':'fixed-baseline-research-only','candidate_id':self.cid,
            'version':self.old['version'],'original_claim_id':self.old['claim_id'],'objective':objective,
            'pool':str(self.pool.path),'registry':str(self.registry),'production_counted':False,
            'comparisons':self.comparisons if comparisons is None else comparisons})

    def claim(self, **kwargs):
        values = dict(candidate_id=self.cid,version=self.old['version'],original_claim_id=self.old['claim_id'],
                      objective=self.obj,authorization=self.auth,comparisons=self.comparisons,
                      replay_version='candidate-research-replay-2')
        values.update(kwargs)
        return self.pool.claim_research('w','v2',**values)

    def original_rows(self):
        with self.pool.pool.connect() as con:
            return [tuple(con.execute('SELECT * FROM data_candidates WHERE candidate_id=?',(self.cid,)).fetchone()),
                    tuple(con.execute('SELECT * FROM candidate_claims WHERE claim_id=?',(self.old['claim_id'],)).fetchone()),
                    [tuple(row) for row in con.execute('SELECT * FROM candidate_results WHERE claim_id IN (?,?)',
                        (self.old['claim_id'],self.comparison_claim['claim_id']))]]

    def task(self, claim):
        from webcollect.candidate_contract import VERSION
        from webcollect.react_session import build_url_task
        task = build_url_task(url=claim['snapshot']['entry_url'],task_version='v2-fixture')
        task['fragment']['candidate_attempt'] = claim['claim_id']
        reference = exclusive(self.root/'chain/research-claim.json', {**claim,'pool':str(self.pool.path)})
        task['candidate_binding'] = {'schema_version':VERSION,'candidate_id':self.cid,'claim_id':claim['claim_id'],
            'version':claim['version'],'candidate':claim['snapshot'],'claim_reference':reference}
        return task

    def test_failed_source_and_comparison_save_keep_effective_zero_and_original_rows(self):
        from webcollect.candidate_contract import research_duplicate_basis, research_overlap_sample_ids
        before = self.original_rows(); claim = self.claim()
        self.assertEqual(claim,self.claim())
        basis = research_duplicate_basis(self.task(claim),self.registry)
        self.assertEqual(research_overlap_sample_ids(basis), {'old'})
        self.assertNotIn('original_sample_id',basis)  # comparison is not a same-target success
        new = {**self.result,'sample_id':'research','scope_id':'research','task_key':'research'}
        with patch('webcollect.candidate_consumer.verified_saved',return_value=new), \
             patch('webcollect.site_pool_sync.sync_candidate_qc'):
            result = finish_or_reconcile(self.pool,claim)
            self.assertEqual(result,finish_or_reconcile(self.pool,claim,reconciliation=True))
        self.assertFalse(result['result']['production_counted'])
        self.assertEqual(before,self.original_rows())
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT effective FROM candidate_results WHERE claim_id=?',
                                        (claim['claim_id'],)).fetchone()[0],0)
        from webcollect.site_pool_sync import sync_candidate_qc
        report = exclusive(self.root/'explicit-review.json', {'fixture':True})
        # Projection reads explicit QC facts; it neither dispatches review nor
        # promotes the research result into the production effective set.
        def snapshot(registry,scope):
            return {'tasks':[{'task_key':scope,'production_status':'collected_pending_review',
                             'qc':{'report':report,'status':'PASS'} if scope=='research' else None}]}
        with patch('webcollect.site_pool_sync._snapshot',side_effect=snapshot), \
             patch('webcollect.runtime._bound_quality_report'):
            sync_candidate_qc(self.pool.path,self.registry)
        with self.pool.pool.connect() as con:
            self.assertEqual(tuple(con.execute('SELECT effective,qc_state FROM candidate_results WHERE claim_id=?',
                (claim['claim_id'],)).fetchone()),(0,'accepted'))
        self.assertEqual(before,self.original_rows())

    def test_objective_bytes_authorization_and_unknown_are_not_bypassed(self):
        from webcollect.batch_core import file_sha, OutcomeUnknown
        changed = self.root/'same-json-different-bytes.json'
        changed.write_bytes(Path(self.obj['path']).read_bytes()+b'\n')
        ref = {'path':str(changed),'sha256':file_sha(changed)}
        with self.assertRaisesRegex(ValueError,'objective bytes'):
            self.claim(objective=ref,authorization=self.authorization(ref,name='changed-auth.json'))
        with self.assertRaisesRegex(ValueError,'authorization'):
            self.claim(comparisons=[])
        with self.ledger.connect() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,request_json) "
                        "VALUES('unresolved','old-job','fixture',1,'unknown',0,0,0,'{}')")
            con.commit()
        with self.assertRaises(OutcomeUnknown):
            self.claim()
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM candidate_claims WHERE request_id='v2'").fetchone()[0],0)

    def runtime_commit_fixture(self, third=False):
        from m4_runtime_fixtures import NOW, make_plan
        from webcollect.runtime import RuntimeStore
        from webcollect.production_quality import sha, ExactImageIndex
        from webcollect.candidate_contract import research_duplicate_basis, research_overlap_sample_ids
        from webcollect.planning import canonical
        claim = self.claim(); task = self.task(claim)
        store = RuntimeStore(self.registry,'research')
        store.initialize({'campaign_id':'local','attempt_cap':10,'target_total':1000},now=NOW)
        plan, publication = make_plan(self.root/'runtime-plan',1)
        # make_plan is a legacy synthetic admission fixture, not a current-chain
        # page-identity fixture. Isolate that unrelated enqueue prerequisite;
        # the real v2 binding and exact-image commit below remain unmocked.
        with patch('webcollect.current_chain.require_plan',return_value=False):
            store.enqueue_plan(plan,publication,now=NOW)
        row = store.claim_next('runtime-worker',request_id='runtime',now=NOW+1)
        store.start_attempt(row['attempt_id'],'runtime-worker',row['lease_token'],now=NOW+1)
        with store._transaction() as con:
            con.execute('UPDATE m4_tasks SET task_json=? WHERE task_key=?',(canonical(task),row['task_key']))
        def image(sid):
            path = self.root/'results/samples'/sid/'images/step_001.png'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'controlled-identical-image')
            return path
        old = image('old'); originals = {str(old):sha(old)}
        if third:
            other=image('third');originals[str(other)]=sha(other)
        store.register_exact_baseline(originals,now=NOW+1)
        current = image(row['sample_id'])
        conflicts = ExactImageIndex([self.root/'results']).conflicts(current.parent.parent)
        overlaps = research_overlap_sample_ids(research_duplicate_basis(task,self.registry))
        blocked = [c for c in conflicts if Path(c['other_sample']).name not in overlaps]
        self.assertEqual({Path(c['other_sample']).name for c in blocked}, {'third'} if third else set())
        return store,row,{str(current):sha(current)}

    def test_runtime_commit_records_named_overlap_without_production_acceptance(self):
        from m4_runtime_fixtures import NOW
        store,row,images = self.runtime_commit_fixture()
        evidence = exclusive(self.root/'runtime-proof.json',{'fixture':True})
        with patch('webcollect.production_identity.verify_saved'):
            saved = store.finish_attempt(row['attempt_id'],'runtime-worker',row['lease_token'],
                'collected_pending_review',evidence=[evidence],exact_images=images,now=NOW+2)
        self.assertEqual(saved['status'],'collected_pending_review')
        overlaps = [e for e in store.snapshot()['events'] if e['event_type']=='research_original_image_overlap']
        self.assertEqual(len(overlaps),1)
        self.assertEqual(len(overlaps[0]['payload']['exact_conflicts']),1)
        self.assertFalse(overlaps[0]['payload']['basis']['production_duplicate_acceptance'])

    def test_runtime_third_sample_blocks_even_with_authorized_comparison(self):
        from m4_runtime_fixtures import NOW
        from webcollect.runtime import ImageCommitConflict
        store,row,images = self.runtime_commit_fixture(third=True)
        evidence = exclusive(self.root/'runtime-proof.json',{'fixture':True})
        with patch('webcollect.production_identity.verify_saved'), self.assertRaises(ImageCommitConflict):
            store.finish_attempt(row['attempt_id'],'runtime-worker',row['lease_token'],
                'collected_pending_review',evidence=[evidence],exact_images=images,now=NOW+2)
        self.assertEqual(store.snapshot()['attempts'][0]['status'],'running')


class ResearchV3(unittest.TestCase):
    """Reuse V2's claim/result paths; only saved research is newly eligible."""
    def setUp(self):
        f=ResearchV2('test_failed_source_and_comparison_save_keep_effective_zero_and_original_rows')
        f.setUp();self.addCleanup(f.doCleanups);self.f=f
        source=f.claim()
        output=f.root/'settled-research';output.mkdir()
        (output/'session-objective.json').write_bytes(Path(f.obj['path']).read_bytes())
        f.pool.stage(source,'execution',{'output':str(output)})
        self.receipt=exclusive(output/'saved_sample.json',{'sample_id':'research-source'})
        saved={**f.result,'sample_id':'research-source','scope_id':'research-source','task_key':'research-source',
               'save_receipt':self.receipt,'result_location':str(output/'samples/research-source')}
        with patch('webcollect.candidate_consumer.verified_saved',return_value=saved), \
             patch('webcollect.site_pool_sync.sync_candidate_qc'):
            finish_or_reconcile(f.pool,source)
        self.source=f.pool.get_claim(source['claim_id'])
        self.comparisons=[*f.comparisons,{'role':'comparison','claim_id':source['claim_id'],
            'sample_id':'research-source','save_receipt':self.receipt}]
        self.auth=exclusive(f.root/'v3-authorization.json',{'scope':'fixed-baseline-research-only',
            'candidate_id':f.cid,'version':f.old['version'],'original_claim_id':source['claim_id'],
            'objective':f.obj,'pool':str(f.pool.path),'registry':str(f.registry),
            'comparisons':self.comparisons,'production_counted':False})

    def claim(self, version='candidate-research-replay-3'):
        f=self.f
        return f.pool.claim_research('w','next-research',candidate_id=f.cid,version=f.old['version'],
            original_claim_id=self.source['claim_id'],objective=f.obj,authorization=self.auth,
            comparisons=self.comparisons,replay_version=version)

    def test_saved_research_replay_keeps_named_overlaps_and_nonproduction_projection(self):
        from webcollect.candidate_contract import research_duplicate_basis, research_overlap_sample_ids
        from webcollect.site_pool_sync import sync_candidate_qc
        f=self.f;before=f.original_rows();source_before=f.pool.get_claim(self.source['claim_id'])
        with f.pool.pool.connect() as con:
            result_before=tuple(con.execute('SELECT * FROM candidate_results WHERE claim_id=?',
                                            (self.source['claim_id'],)).fetchone())
        with self.assertRaisesRegex(ValueError,'settled failed'):
            self.claim('candidate-research-replay-2')
        # V2 also retains its effective=1-only comparison rule.
        v2_auth=f.authorization(f.obj,comparisons=self.comparisons,name='v2-research-comparison-auth.json')
        with self.assertRaisesRegex(ValueError,'historical save'):
            f.pool.claim_research('w','v2-with-research-comparison',candidate_id=f.cid,version=f.old['version'],
                original_claim_id=f.old['claim_id'],objective=f.obj,authorization=v2_auth,
                comparisons=self.comparisons,replay_version='candidate-research-replay-2')
        claim=self.claim();self.assertEqual(claim,self.claim())
        basis=research_duplicate_basis(f.task(claim),f.registry)
        self.assertEqual(basis['schema_version'],'candidate-research-duplicate-2')
        self.assertEqual(research_overlap_sample_ids(basis),{'old','research-source'})
        self.assertNotIn('third',research_overlap_sample_ids(basis))
        new={**f.result,'sample_id':'research-next','scope_id':'research-next','task_key':'research-next'}
        with patch('webcollect.candidate_consumer.verified_saved',return_value=new), \
             patch('webcollect.site_pool_sync.sync_candidate_qc'):
            saved=finish_or_reconcile(f.pool,claim)
        self.assertFalse(saved['result']['production_counted'])
        self.assertEqual(saved['result']['research_replay']['schema_version'],'candidate-research-replay-3')
        def snapshot(registry,scope):
            return {'tasks':[{'task_key':scope,'production_status':'collected_pending_review','qc':None}]}
        with patch('webcollect.site_pool_sync._snapshot',side_effect=snapshot) as read:
            sync_candidate_qc(f.pool.path,f.registry)
            read.assert_any_call(str(f.registry),'research-next')
        with f.pool.pool.connect() as con:
            self.assertEqual(tuple(con.execute('SELECT effective,qc_state FROM candidate_results WHERE claim_id=?',
                (claim['claim_id'],)).fetchone()),(0,'pending_review'))
            self.assertEqual(tuple(con.execute('SELECT * FROM candidate_results WHERE claim_id=?',
                (self.source['claim_id'],)).fetchone()),result_before)
        self.assertEqual(f.original_rows(),before)
        self.assertEqual(f.pool.get_claim(self.source['claim_id']),source_before)

    def test_unknown_and_reconcile_source_do_not_create_research_claim(self):
        from webcollect.batch_core import OutcomeUnknown
        f=self.f
        with f.ledger.connect() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,request_json) "
                        "VALUES('unresolved','source-job','fixture',1,'unknown',0,0,0,'{}')")
            con.commit()
        with self.assertRaises(OutcomeUnknown):self.claim()
        with f.pool.transaction() as con:
            con.execute("UPDATE candidate_claims SET state='reconcile' WHERE claim_id=?",(self.source['claim_id'],))
        with self.assertRaisesRegex(ValueError,'settled'):self.claim()
        with f.pool.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM candidate_claims WHERE request_id='next-research'").fetchone()[0],0)
        with f.ledger.connect() as con:
            self.assertEqual(con.execute("SELECT state FROM model_requests WHERE id='unresolved'").fetchone()[0],'unknown')
