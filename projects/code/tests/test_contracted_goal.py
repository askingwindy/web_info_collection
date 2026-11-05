"""A plan's shape, grounded business evidence and review are separate gates."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from jsonschema import Draft202012Validator
from webcollect.agent_controller import exclusive
from webcollect.banded_plan import bind_reply_scope, choice_schema, plan_schema
from webcollect.goal_evidence import VERSION, progress, validate_contract


class ContractedGoal(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.reading = dict(version=VERSION, kind='reading', subject='河流', aspects=['流速','沉积'])
        self.calc = dict(version=VERSION, kind='calculation', inputs=[dict(label='甲',value='11'),
            dict(label='乙',value='7')], retain=['档位'], result_label='总量', unit='升')
        self.obs = {}
        self.binding = exclusive(self.root/'boundary.json', {'attempt_id':'a'})

    def view(self, key, doc, items, y=0):
        controls, elements, values = {}, [], []
        for id_, role, label, value, href in items:
            e = dict(element_id=id_, text=label, visible=True, native_role=role,
                     inputable=role=='input', bbox=[1,1,200,30])
            b = dict(element_id=id_, href=href, selector='main:nth-of-type(1) > '+role+':nth-of-type(1)')
            v = dict(element_id=id_, value=value, value_visible=value is not None)
            controls[id_] = {'element':e, 'binding':b, 'value':v, 'readable_labels':[]}
            elements.append(e)
            values.append(v)
        data = dict(elements=elements, values=values, capture_controls=[c['binding'] for c in controls.values()],
                    url='https://test.invalid/'+doc, scroll=[0,y], visible_text=' '.join(e['text'] for e in elements))
        ob = dict(observation_id=key, capture_verified=True, document_identity={'document':doc}, url=data['url'],
                  controls=controls, html='<main></main>', evidence={'state':exclusive(self.root/(key+'.json'),data)})
        self.obs[key] = ob
        return ob

    def operation(self, key, name, before, after, node=None, text=''):
        return dict(operation_id=key, action=name, before_observation_id=before, after_observation_id=after,
                    target={'control_id':node}, arguments={'text':text})

    def session(self, key, steps):
        return SimpleNamespace(current=self.obs[key], trajectory=steps, observation_records=self.obs,
                               attempt_id='a', binding=self.binding)

    def calculation(self, numbers, retained='3'):
        return [(k,'input',label,v,None) for k,label,v in zip('abc',['甲','乙','档位'],[*numbers,retained])]

    def test_calculation_binds_each_field_final_value_and_named_output(self):
        start=self.view('start','form',self.calculation(['2','5']))
        self.view('changed','form',self.calculation(['11','5']))
        self.view('final','form',self.calculation(['11','7']))
        steps=[self.operation('o1','type','start','changed','a'), self.operation('o2','type','changed','final','b')]
        s=self.session('final',steps)
        with patch('webcollect.template_learning.result_evidence',return_value=[{'quotes':['本次总量 18 升']}]):
            self.assertEqual(progress(s,'start',self.calc)['status'],'VERIFIED')
            swapped=deepcopy(self.calc)
            swapped['inputs'][0]['value'],swapped['inputs'][1]['value']='7','11'
            self.assertEqual(progress(s,'start',swapped)['status'],'UNVERIFIED')
            s.current=self.view('reset','form',self.calculation(['11','7'],'6'))
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
            s.current=self.obs['final']
        with patch('webcollect.template_learning.result_evidence',return_value=[{'quotes':['温度 18 度']}]):
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
        self.obs['changed']['html'] = '<output>尚未更新的中间结果</output>'
        def stale_intermediate(now, previous, html, previous_html, **options):
            return [] if '中间结果' in previous_html else [{'quotes':['本次总量 18 升']}]
        with patch('webcollect.template_learning.result_evidence',side_effect=stale_intermediate):
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
        start['capture_verified']=False
        self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')

    def test_scroll_can_hide_a_proven_input_while_its_bound_value_must_still_match(self):
        self.view('start','form',self.calculation(['2','5']))
        self.view('edit1','form',self.calculation(['11','5']))
        self.view('edit2','form',self.calculation(['11','7']))
        final=self.view('scrolled','form',self.calculation(['11','7']),y=360)
        final['controls']['a']['value']['value_visible']=False
        edits=[self.operation('o1','type','start','edit1','a'),self.operation('o2','type','edit1','edit2','b')]
        s=self.session('scrolled',edits+[self.operation('o3','scroll','edit2','scrolled')])
        with patch('webcollect.template_learning.result_evidence',return_value=[{'quotes':['本次总量 18 升']}]):
            self.assertEqual(progress(s,'start',self.calc)['status'],'VERIFIED')
            s.trajectory=edits
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
            s.trajectory=edits+[self.operation('o3','scroll','edit2','scrolled')]
            final['controls']['a']['value']['value']='99'
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
            final['controls']['a']['value']['value']='11'
            final['controls']['a']['binding']['selector']='main > a-different-input'
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')

    def test_scroll_can_hide_only_label_while_original_input_value_remains_visible(self):
        self.view('start','form',self.calculation(['2','5']))
        self.view('edit1','form',self.calculation(['11','5']))
        self.view('edit2','form',self.calculation(['11','7']))
        final=self.view('scrolled','form',self.calculation(['11','7']),y=360)
        final['controls']['a']['element']['text']=''
        steps=[self.operation('o1','type','start','edit1','a'),self.operation('o2','type','edit1','edit2','b'),
               self.operation('o3','scroll','edit2','scrolled')]
        s=self.session('scrolled',steps)
        with patch('webcollect.template_learning.result_evidence',return_value=[{'quotes':['本次总量 18 升']}]):
            self.assertEqual(progress(s,'start',self.calc)['status'],'VERIFIED')
            final['controls']['a']['binding']['selector']='replacement'
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')
        final['controls']['a']['binding']['selector']='main:nth-of-type(1) > input:nth-of-type(1)'
        with patch('webcollect.template_learning.result_evidence',return_value=[]):
            self.assertEqual(progress(s,'start',self.calc)['status'],'UNVERIFIED')

    def test_reading_requires_result_lineage_new_passage_and_bound_model_selection(self):
        form=('q','input','站内搜索','',None)
        button=('send','button','搜索',None,None)
        self.view('entry','entry',[form,button])
        self.view('typed','entry',[('q','input','站内搜索','河流',None),button])
        self.view('results','search',[('go','a','河流的搬运能力',None,'https://test.invalid/article'),
                                      ('ad','a','购买旅行票',None,'https://test.invalid/else')])
        heading=('h','h1','河流的搬运能力',None,None)
        self.view('land','article',[heading])
        quote='水体流速减慢后，原先搬运的物质更容易沉积在河床上。'
        self.view('new','article',[('p','p',quote,None,None)],y=400)
        steps=[self.operation('o1','type','entry','typed','q','河流'),
               self.operation('submit','click','typed','results','send'),
               self.operation('o2','click','results','land','go'),
               self.operation('o3','scroll','land','new')]
        s=self.session('new',steps)
        result=progress(s,'entry',self.reading)
        self.assertEqual(result['status'],'PASSAGE_AVAILABLE')
        p=result['passages'][0]
        s.answer_citation=exclusive(self.root/'decision.json',dict(kind='plan-branch',boundary=self.binding,
            response=dict(choice='cite:p',attempt_id='a',observation_id='new'),
            provider_reply={'choice':'cite:p'},options=[dict(choice='cite:p',passage=p)]))
        self.assertEqual(progress(s,'entry',self.reading)['selected_passage']['quote'],quote)
        s.attempt_id='other'
        self.assertEqual(progress(s,'entry',self.reading)['status'],'PASSAGE_AVAILABLE')
        s.attempt_id='a'
        s.trajectory[1]['target']['control_id']='unrelated'
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')
        s.trajectory[1]['target']['control_id']='send'
        s.trajectory[2]['target']['control_id']='ad'
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')
        s.trajectory[2]['target']['control_id']='go'
        s.current=self.view('away','else',[('p','p',quote,None,None)],y=400)
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')

    def test_derived_ids_never_override_stale_or_unseen_references(self):
        prompt={'attempt_id':'a','observation':{'observation_id':'o','rendered_dom':[{'node':'e'}]}}
        raw={'steps':[{'action':'click','target':{'node':'e','text':'打开'}}]}
        result=bind_reply_scope(raw,prompt)
        self.assertEqual(result['steps'][0]['target']['observation_id'],'o')
        self.assertNotIn('observation_id',raw)
        for altered in ({**raw,'attempt_id':'wrong'}, {'steps':[{'target':{'node':'omitted'}}]},
                        {'steps':[{'target':{'node':'e','observation_id':'stale'}}]}):
            with self.assertRaises(ValueError):
                bind_reply_scope(altered,prompt)
        for schema in (plan_schema(True,wire=True),choice_schema(True)):
            Draft202012Validator.check_schema(schema)
        self.assertIn('observation_id',plan_schema()['required'])
        self.assertNotIn('observation_id',plan_schema(True,wire=True)['required'])
        self.assertTrue(list(Draft202012Validator(choice_schema(True)).iter_errors({'steps':[]})))
        chooser=Draft202012Validator(choice_schema(True))
        self.assertTrue(chooser.is_valid({'choice':'cite:e_13','plan':None}))
        self.assertFalse(chooser.is_valid({'choice':'replan','plan':None}))
        self.assertFalse(chooser.is_valid({'choice':'cite:e_13','plan':{}}))
        for contract in (self.calc,self.reading):
            validate_contract(contract)
        with self.assertRaises(ValueError):
            validate_contract({**self.reading,'aspects':['重复','重复']})

    def test_only_disjoint_pixels_support_the_same_unique_search_input(self):
        from webcollect.goal_evidence import search_focus_from_pair
        items = [('q','input','站内搜索','',None),('send','button','搜索',None,None)]
        before, after = [self.view(key,'entry',items) for key in ('a','b')]
        for ob in (before, after):
            ob['controls']['q']['binding']['input_type'] = 'search'
        proof = {'loading_complete':True,'pixel_change':{'bbox':[20,80,280,100],'changed_pixels':12}}
        page = {'screen_resolution':[400,240],'device_pixel_ratio':1}
        with patch('webcollect.goal_evidence.state', return_value=page):
            self.assertEqual(search_focus_from_pair(before,after,proof)['node'], 'q')
            overlap = {**proof,'pixel_change':{'bbox':[20,15,90,36],'changed_pixels':1}}
            self.assertIsNone(search_focus_from_pair(before,after,overlap))
            self.assertIsNone(search_focus_from_pair(before,after,{**proof,'loading_complete':False}))
            for stale in ({**after,'document_identity':{'document':'new'}}, {**after,'capture_verified':False}):
                self.assertIsNone(search_focus_from_pair(before,stale,proof))
            after['controls']['q']['element']['bbox'] = [2,1,201,30]
            self.assertIsNone(search_focus_from_pair(before,after,proof))
            after['controls']['q']['element']['bbox'] = [1,1,200,30]
            after['controls']['duplicate'] = deepcopy(after['controls']['q'])
            self.assertIsNone(search_focus_from_pair(before,after,proof))

    def test_generic_query_field_needs_a_unique_input_and_search_button_in_the_same_form(self):
        from webcollect.goal_evidence import search_field
        ob=self.view('query','form',[('q','input','资料关键词','',None),('go','button','检索资料',None,None),
                                     ('other','input','姓名','',None)])
        for cid,form in [('q',0),('go',0),('other',1)]:
            ob['controls'][cid]['binding'].update(form_index=form,input_type='submit' if cid=='go' else 'text')
        self.assertTrue(search_field(ob,'q'))
        self.assertFalse(search_field(ob,'other'))
        ob['controls']['other']['binding']['form_index']=0
        self.assertFalse(search_field(ob,'q'))


class GroundedRound(unittest.IsolatedAsyncioTestCase):
    async def test_verified_citation_finishes_without_dispatching_remaining_step(self):
        from webcollect.banded_plan import Controller
        controller = Controller.__new__(Controller)
        controller.plan = {'finish_when':{'kind':'goal_evidence'}}
        controller.frozen_plan = {'observation_id':'first'}
        controller.exit_boundary = AsyncMock(return_value=False)
        controller.proved = Mock(return_value=True)
        controller.finish = AsyncMock()
        session = SimpleNamespace(task={}, choose=lambda:None)
        with patch('webcollect.banded_plan.contract_for',return_value={'version':VERSION}), \
                patch('webcollect.goal_evidence.progress',return_value={'status':'VERIFIED'}):
            await controller.round(session)
        controller.finish.assert_awaited_once()

    async def test_first_plan_keeps_lease_and_unknown_single_dispatch_branch_uses_config_timeout(self):
        import json
        import time
        from webcollect.batch_core import OutcomeUnknown
        from webcollect.react_session import build_url_task, react_chooser
        from webcollect.banded_plan import VERSION as PLAN_VERSION, tools
        from test_model_provider_protocols import ProviderProtocolTests
        fixture=ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cfg=fixture.config('glm',vision=True)
        cfg['budget']['lease_seconds']=300
        cfg['model']['timeout_seconds']=180
        ledger, setup_job, _=fixture.gateway(cfg)
        ledger.finish(setup_job)
        task=build_url_task(url='https://example.org/',task_version='wait',plan_protocol=PLAN_VERSION)
        task['fragment']['session_objective']={'objective':{'evidence_contract':{'version':VERSION}}}
        choose=react_chooser(ledger,task,'t')
        prompt={'protocol':PLAN_VERSION,'phase':'branch','system':'fixture','attempt_id':'t',
                'progress':{'decisions_used':1},'tools':tools(True),
                'observation':{'observation_id':'o','image_ref':str(fixture.image)}}
        from test_banded_plan import plan_for
        raw=plan_for(prompt)
        raw.pop('observation_id')
        fixture.opener.raw['choices']=[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]
        calls=[]
        def open_request(request,timeout):
            import io
            calls.append(timeout)
            if timeout==600:
                with ledger.connect() as con:
                    lease=con.execute("SELECT lease FROM jobs WHERE kind='react-native-decision' AND state='running'").fetchone()[0]
                self.assertGreater(lease-time.time(),625)
                raise TimeoutError('no headers')
            return io.BytesIO(json.dumps(fixture.opener.raw).encode())
        with patch.object(fixture.opener,'open',side_effect=open_request):
            self.assertEqual(await choose(prompt),raw)
            prompt.update(phase='first',progress={'decisions_used':2})
            with self.assertRaises(OutcomeUnknown):
                await choose(prompt)
            with self.assertRaises(OutcomeUnknown):
                await choose(prompt)
        self.assertEqual(calls,[180,600])
        with ledger.connect() as con:
            self.assertEqual([r[0] for r in con.execute('SELECT state FROM model_requests ORDER BY started')],['succeeded','unknown'])
