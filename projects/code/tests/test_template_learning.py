"""Disposable contracts for project template learning and same-session routing."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock
from webcollect.template_learning import (DOM, VERSION, match, result_evidence,
    TemplateLibrary, LearningSession, Inapplicable, enabled, derive_program, validate_program)
from webcollect import react_session


def frame():
    path='html:nth-of-type(1) > body:nth-of-type(1) > input:nth-of-type(1)'
    return {'url':'https://example.test/calculator','screen_resolution':[1280,720],
      'visible_text':'Income (€) Calculate 12345','document_identity':{'id':'doc'},
      'elements':[{'element_id':'i','text':'Income (€)','inputable':True,'enabled':True,'visible':True,'bbox':[20,30,220,60]}],
      'values':[{'element_id':'i','value':'','readonly':False}],
      'capture_controls':[{'element_id':'i','selector':path,'tag':'input','input_type':'text'}]}

HTML='<html><body><input type="text" inputmode="decimal" placeholder="12345"><button>Calculate</button><div id="x-result"></div></body></html>'
PROGRAM=[{'op':'fill_numeric','source_input_kinds':[['text','decimal']],'repeat':'current_visible_compatible_numeric_roles'},
         {'op':'submit_compute','mechanism':'click','max_submissions':1,'button_locate_scroll_limit':1},
         {'op':'scroll_result','limit':1,'skip_if_result_visible':True},
         {'op':'verify_result','shape':'aligned_cells','exact_quotes':True,'changed_since':'before_submission'}]
T={'program':PROGRAM,'template_id':'learned-demo','version':VERSION,'application_id':'app','site_host':'example.test','state':'trial'}

class MatchTests(unittest.TestCase):
    def test_parameter_from_current_page_not_seed(self):
        plan=match(T,'app',frame(),HTML)
        self.assertEqual(plan['fields'][0]['value'],'12345')
        self.assertIsNone(plan['button_selector'])  # locating is a later real step
        self.assertNotIn('france',json.dumps(plan))

    def test_negative_contracts(self):
        for change in ('old','draft','app','unit','explicit','date','unknown_parameter'):
            t=deepcopy(T);s=frame();html=HTML;aid='app';goal=None
            if change=='old':t['version']='old'
            if change=='draft':t['state']='draft'
            if change=='app':aid='else'
            if change=='unit':s['elements'][0]['text']='Input'
            if change=='explicit':goal={'description':'fixed original goal'}
            if change=='date':s['capture_controls'][0]['input_type']='date'
            if change=='unknown_parameter':html=HTML.replace('placeholder="12345"','')
            with self.subTest(change=change),self.assertRaises(Inapplicable):match(t,aid,s,html,goal)

    def test_uncertain_select_display_falls_back(self):
        s=frame();s['elements'].append({'element_id':'s','text':'Currency','enabled':True,'visible':True,'bbox':[20,70,200,90]})
        s['capture_controls'].append({'element_id':'s','tag':'select','selector':'#s'})
        s['values'].append({'element_id':'s','value':'eur','display_value':'','value_visible':True})
        self.assertEqual(match(T,'app',s,HTML)['match_status'],'GREY_NEEDS_CHOICE_OBSERVATION')

    def test_project_bound_restart_and_idempotent_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);manifest=p/'manifest.json';manifest.write_text('{}');pool=p/'pool.sqlite3'
            a=TemplateLibrary(p/'templates.sqlite3',manifest,pool)
            self.assertEqual(a.snapshot(),TemplateLibrary(a.path,manifest,pool).snapshot())
            with self.assertRaisesRegex(ValueError,'another project'):TemplateLibrary(a.path,manifest,p/'other.sqlite3')

    def test_opt_in_restores_original(self):
        class Library:
            def snapshot(self):return {'templates':[]}
        old=react_session.ReactSession
        with enabled(Library()):self.assertIs(react_session.ReactSession,LearningSession)
        self.assertIs(react_session.ReactSession,old)

    def test_program_is_derived_from_source_order_and_scroll(self):
        ops=[{'action_type':'type','selector':'#x'},{'action_type':'click'},{'action_type':'scroll'}]
        fields=[{'input_type':'text','inputmode':'decimal','selector':'#x'}]
        proof=[{'nodes':[{},{}]}]
        a=derive_program(ops,fields,1,proof);b=derive_program(ops[:2],fields,1,proof)
        self.assertEqual([s['op'] for s in a],['fill_numeric','submit_compute','scroll_result','verify_result'])
        self.assertEqual([s['op'] for s in b],['fill_numeric','submit_compute','verify_result'])
        self.assertNotEqual(a,b)
        for bad in (None,a[:-1],[{'op':'invented'}]+a[1:]):
            with self.assertRaises(Inapplicable):validate_program(bad)


class ResultTests(unittest.TestCase):
    def state(self, texts):
        s={'visible_text':'\n'.join(texts),'screen_resolution':[1280,720],'elements':[],'capture_controls':[]}
        for i,text in enumerate(texts,1):
            s['elements'].append({'element_id':str(i),'text':text,'native_role':'td','visible':True,
                                 'bbox':[20+(i-1)*200,80,200+(i-1)*200,110]})
            s['capture_controls'].append({'element_id':str(i),'selector':f'html:nth-of-type(1) > body:nth-of-type(1) > div:nth-of-type(1) > table:nth-of-type(1) > tr:nth-of-type(1) > td:nth-of-type({i})'})
        return s

    def html(self,a,b,attrs='id="x-result"'):
        return f'<html><body><div {attrs}><table><tr><td>{a}</td><td>{b}</td></tr></table></div></body></html>'

    def test_separate_cells_prove_submitted_result_after_scroll(self):
        s=self.state(['Annual tax','3,904 €'])
        proof=result_evidence(s,{},self.html('Annual tax','3,904 €'),self.html('',''))
        self.assertEqual(proof[0]['quotes'],['Annual tax','3,904 €'])
        self.assertNotIn('Income',s['visible_text'])  # original form is offscreen

    def test_unsubmitted_old_result_or_echo_never_pass(self):
        s=self.state(['Annual tax','3,904 €']);html=self.html('Annual tax','3,904 €')
        self.assertEqual(result_evidence(s,{},html,html),[])
        self.assertEqual(result_evidence(s,{},self.html('Annual tax','3,904 €','id="help"'),self.html('','')),[])
        echo=self.html('Annual tax','<input value="3904">3,904 €')
        self.assertEqual(result_evidence(s,{},echo,self.html('','')),[])

    def test_hidden_change_cannot_recertify_unchanged_visible_value(self):
        s=self.state(['Annual tax','3,904 €'])
        before=self.html('Annual tax','3,904 €').replace('</div>','<span hidden>1</span></div>')
        after=before.replace('hidden>1','hidden>2')
        self.assertEqual(result_evidence(s,s,after,before),[])
        nested_before=self.html('Annual tax','3,904 €<span hidden>1</span>')
        nested_after=nested_before.replace('hidden>1','hidden>2')
        self.assertEqual(result_evidence(s,s,nested_after,nested_before),[])

    def test_old_offscreen_result_is_not_new_but_explicit_hidden_result_showing_is(self):
        s=self.state(['Annual tax','3,904 €']);html=self.html('Annual tax','3,904 €')
        self.assertEqual(result_evidence(s,{},html,html),[])
        hidden_before=html.replace('id="x-result"','id="x-result" style="display:none"')
        self.assertTrue(result_evidence(s,{},html,hidden_before))

    def test_plain_text_parameter_echo_in_new_result_is_not_computed_output(self):
        s=self.state(['Annual income','50,000 €']);baseline={'values':[{'value':'50000'}]}
        self.assertEqual(result_evidence(s,baseline,self.html('Annual income','50,000 €'),self.html('','')),[])

    def test_vertical_named_result_requires_same_card_changed_number_and_matching_unit(self):
        parts=['总体积','78.25','立方米']
        s=self.state(parts)
        for i,(el,control) in enumerate(zip(s['elements'],s['capture_controls']),1):
            el.update(native_role='div',bbox=[20,i*32,200,i*32+32])
            control['selector']=f'html:nth-of-type(1) > body:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type({i})'
        def card(number):
            return f'<html><body><div id="x-result"><div>总体积</div><div>{number}</div><div>立方米</div></div></body></html>'
        new,old=card('78.25'),card('--')
        options={'card_labels':('体积','立方米')}
        self.assertEqual(result_evidence(s,{},new,old,**options)[0]['quotes'],parts)
        self.assertFalse(result_evidence(s,{},new,old))
        self.assertFalse(result_evidence(s,{},new,new,**options))
        self.assertFalse(result_evidence(s,{'values':[{'value':'78.25'}]},new,old,**options))
        self.assertFalse(result_evidence(s,{},new,old,card_labels=('体积','升')))
        s['elements'][-1]['visible']=False
        self.assertFalse(result_evidence(s,{},new,old,**options))


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_form_offscreen_after_submit_does_not_rebind_or_resubmit(self):
        s=object.__new__(LearningSession);s.plan={'template':'t','fields':[],'choices':[{'selector':'missing'}]}
        s.program_index=2;s.result_scrolls=0;s.plan['program']=deepcopy(PROGRAM)
        s.calculated=True;s.calculation_before={};s.calculation_before_html='<html><body></body></html>'
        s.current={'html':'<html><body></body></html>'};s.state_now=lambda:{'elements':[]}
        s.scroll_to=AsyncMock();s.close_visible=AsyncMock();s.act_control=AsyncMock()
        await s.calculator_round();s.scroll_to.assert_awaited_once();s.act_control.assert_not_called()
        with self.assertRaisesRegex(Inapplicable,'SUBMITTED_RESULT'):await s.calculator_round()
        s.act_control.assert_not_called()

    async def test_unknown_stop_propagates_without_react_replay(self):
        from webcollect.react_session import ReactStop
        s=object.__new__(LearningSession);s.lookup_done=True;s.template_disabled=False;s.template_tools=0
        s._check_request_budget=lambda:None
        s.calculator_round=AsyncMock(side_effect=ReactStop('blocked','UNKNOWN',unknown=True))
        with self.assertRaises(ReactStop):await s._round_impl()
        self.assertFalse(s.template_disabled)

if __name__=='__main__':unittest.main()

class OfficialEntryTests(unittest.TestCase):
    def test_qc_wrapper_never_reclaims_attempted_or_unknown(self):
        from webcollect.template_learning_experiment import SelectedJobs
        class Ledger:
            def get(self,jid):return {'state':'queued' if jid!='unknown' else 'unknown','attempts':0 if jid=='new' else 1}
            def claim(self,kind,job_id):return job_id
        worker=SelectedJobs(Ledger(),{'ai-visual':['old','unknown','new']})
        self.assertEqual(worker.claim('ai-visual'),'new')
        self.assertIsNone(worker.claim('ai-visual'))

    def test_non_native_http_is_counted_from_bound_provider_receipt(self):
        import sqlite3
        from webcollect.template_learning_experiment import request_costs
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'jobs.sqlite3'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE model_requests(id,job_id,state,usage,started,finished,request_json,response)')
                usage={'source':'provider_response','provider_request_id':'controlled-receipt','input_tokens':12,'output_tokens':3}
                c.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?)',('r','j','succeeded',json.dumps(usage),0,1,'{}',json.dumps({'provider_response':{}})))
            result=request_costs(path,job_ids=['j'])
            self.assertEqual(result['http'],1);self.assertEqual(result['tokens']['input_tokens'],12)
            self.assertEqual(result['unconfirmed_http'],0)

class WiringTests(unittest.TestCase):
    def test_explicit_adapter_builds_original_four_tools_before_task_hash(self):
        from webcollect.banded_plan import VERSION as PLAN
        from webcollect.closing_policy import VERSION as CLOSE
        from webcollect.react_session import validate_task
        class Library:
            def snapshot(self):return {'templates':[]}
        original=react_session.build_url_task
        with enabled(Library()):
            task=react_session.build_url_task(url='https://example.test/calc',task_version='fixture',ending_policy=CLOSE,plan_protocol=PLAN)
            self.assertNotIn('plan_protocol',task['fragment'])
            self.assertNotIn('plan_protocol',task['workflow_proposal']['spec'])
            validate_task(task)
        self.assertIs(react_session.build_url_task,original)
        ordinary=original(url='https://example.test/calc',task_version='fixture',ending_policy=CLOSE,plan_protocol=PLAN)
        self.assertEqual(ordinary['fragment']['plan_protocol'],PLAN)

class RealQCOnlyTests(unittest.TestCase):
    def test_synthetic_independent_result_cannot_promote_library(self):
        import sqlite3
        from webcollect.template_learning import qc_binding
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'ledger.sqlite3'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE batch_meta(id,config)')
                c.execute('INSERT INTO batch_meta VALUES(1,?)',(json.dumps({'mode':'synthetic'}),))
            for name in ['report','review','queue']:(root/(name+'.json')).write_text('{}')
            class Ledger:pass
            ledger=Ledger();ledger.path=path
            with self.assertRaisesRegex(ValueError,'Only original real independent QC'):
                qc_binding(root/'report.json',root/'review.json',root/'queue.json',ledger)

class RealProviderReceiptTests(unittest.TestCase):
    def test_real_ledger_with_handwritten_ai_labels_and_no_http_cannot_promote(self):
        import sqlite3
        from webcollect.template_learning import qc_binding, REQUIRED
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dataset=root/'dataset';dataset.mkdir();path=root/'ledger.sqlite3'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE batch_meta(id,config)');c.execute('INSERT INTO batch_meta VALUES(1,?)',(json.dumps({'mode':'real'}),))
                c.execute('CREATE TABLE model_requests(job_id,usage,response,request_json,state)')
            sample={'sample_id':'s','annotation_sha256':'a','evidence_sha256':'b','steps':[{'step_id':1}],'status':'PASS'}
            review={**{k:sample[k] for k in ['sample_id','annotation_sha256','evidence_sha256']},'reviewer':{'kind':'ai'},
                    'provenance':{'visual_job':'v','difference_job':'d','frames_viewed':[1]},'step_observations':[{'step_id':1}],
                    'checks':{k:{'status':'PASS'} for k in REQUIRED}}
            payloads={'report':{'samples':[sample],'status':'PASS'},'review':{'records':[review]},
                      'queue':{'dataset':str(dataset),'candidate_package_sha256':{},'jobs':[{'sample_id':'s','visual_job':'v','difference_job':'d'}]}}
            for name,value in payloads.items():(root/(name+'.json')).write_text(json.dumps(value))
            class Ledger:
                def get(self,jid):return {'state':'done','payload':{}}
            ledger=Ledger();ledger.path=path
            with self.assertRaisesRegex(ValueError,'no actual independent provider request'):
                qc_binding(root/'report.json',root/'review.json',root/'queue.json',ledger)


class ProgramConstraintTests(unittest.TestCase):
    def test_missing_interpreter_constraints_reject_before_browser_execution(self):
        for index,key in [(0,'repeat'),(1,'button_locate_scroll_limit'),(2,'skip_if_result_visible')]:
            program=deepcopy(PROGRAM);del program[index][key]
            with self.subTest(key=key),self.assertRaises(Inapplicable):validate_program(program)

class CrossPageStateTests(unittest.TestCase):
    def test_revalidation_requires_actual_direct_reuse_of_this_template_on_another_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=root/'manifest.json';manifest.write_text('{}')
            lib=TemplateLibrary(root/'library.sqlite3',manifest,root/'pool.sqlite3')
            def source(receipt,derived,url,route='original_react',reused=None):
                value={'template_id':derived,'entry_url':url,'route':route,'reused_template_id':reused,'save_receipt':{'sha256':receipt,'path':'SYNTHETIC_FIXTURE_ONLY'}}
                with lib.connect() as c:
                    c.execute('INSERT INTO sources VALUES(?,?,?)',(receipt,derived,json.dumps(value)))
                    c.execute('INSERT INTO qc VALUES(?,?,?)',(receipt,'fixture',json.dumps({'receipt_sha':receipt,'all_five_pass':True})))
            with lib.connect() as c:c.execute('INSERT INTO templates VALUES(?,?)',('x',json.dumps({'template_id':'x'})))
            source('a','x','https://example.test/a')
            source('b','x','https://example.test/b')
            source('c','x','https://example.test/a','template_direct','x')
            self.assertEqual(lib.snapshot()['templates'][0]['state'],'trial')
            # A successful reused program may abstract into a new derived version;
            # validation must still credit the program actually executed.
            source('d','new-derived-version','https://example.test/c','template_direct','x')
            t=lib.snapshot()['templates'][0];self.assertEqual(t['state'],'same_site_revalidated')
            self.assertEqual([r['sha256'] for r in t['cross_page_validation_receipts']],['d'])
            with lib.connect() as c:c.execute('INSERT INTO qc VALUES(?,?,?)',('d','later-fixture',json.dumps({'receipt_sha':'d','all_five_pass':False})))
            self.assertEqual(lib.snapshot()['templates'][0]['state'],'trial')
