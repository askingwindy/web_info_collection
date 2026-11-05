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
