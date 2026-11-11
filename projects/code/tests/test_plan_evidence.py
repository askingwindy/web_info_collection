"""Local synthetic controls, facts, navigation and popup provenance."""
from copy import deepcopy
from types import SimpleNamespace
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock
from webcollect.plan_evidence import facts, expected_navigation, verify_popup
from webcollect.plan_protocol import PLAN_PROTOCOL as VERSION, ENDING_POLICY as END
from webcollect.banded_plan import bind_target, Controller
from webcollect.react_session import build_url_task, validate_task
from PIL import Image

class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.obs={}
    def observation(self,name,url,text,selector='main > h1',heading='简介'):
        node={'element_id':'e1','visible':True,'text':text,'bbox':[1,1,100,30],'native_role':'p'}
        state={'url':url,'document_identity':{'id':name},'screen_resolution':[1920,1080],
               'visible_text':text,'elements':[node,{'element_id':'h','visible':True,'text':heading,'native_role':'h1'}],
               'capture_controls':[{'element_id':'e1','selector':selector}]}
        p=self.root/(name+'.json');p.write_text(json.dumps(state))
        image=self.root/(name+'.png');Image.new('RGB',(1920,1080),'white').save(image)
        obs={'observation_id':name,'url':url,'document_identity':state['document_identity'],
             'capture_verified':True,'visible_text':text,'controls':{'e1':{'element':node,'binding':{'selector':selector},'readable_labels':[]}},
             'evidence':{'image':{'path':str(image)},'state':{'path':str(p)}}}
        self.obs[name]=obs;return obs
    def test_registered_page_check_uses_first_request_url_even_after_navigation(self):
        self.observation('home','https://a.test/home','矩形面积')
        current = self.observation('advert','https://a.test/ad','特价',heading='p0')
        session = SimpleNamespace(observation_records=self.obs, requested_goal=None,
                                  working_goal='核对面积', trajectory=[], current=current)
        checks = [{'field':'核对', 'page':page, 'region':region, 'visible_text':quote}
                  for page, region, quote in [('p0','正文','矩形面积'),('p1','正文','矩形面积'),
                                              ('p0','正文','特价'),('p0','左栏','矩形面积'),
                                              ('p99','正文','矩形面积')]]
        plan = {'checks':checks}
        original = deepcopy(plan)
        result = facts(session, plan, page_urls={'p0':'https://a.test/home','p1':'https://a.test/ad'})
        self.assertEqual([r['status'] for r in result['checks']], ['VERIFIED'] + ['UNVERIFIED'] * 4)
        self.assertEqual(result['checks'][0]['resolved_page'], 'https://a.test/home')
        self.assertEqual(result['checks'][0]['evidence'][0]['observation_id'], 'home')
        self.assertNotIn('resolved_page', result['checks'][-1])
        self.assertEqual(plan, original)

    async def test_home_year_not_accepted_as_intro_year(self):
        self.observation('home','https://a.test/home','Linux 1991 Linus',heading='教程')
        current=self.observation('intro','https://a.test/intro','创建者 Linus')
        s=SimpleNamespace(observation_records=self.obs,requested_goal=None,working_goal='章节核对',trajectory=[],current=current)
        p={'checks':[{'field':'年份','page':'https://a.test/intro','region':'正文','visible_text':'1991'},
                     {'field':'创建者','page':'简介','region':'正文','visible_text':'Linus'}]}
        result=facts(s,p)
        self.assertEqual(result['business_goal_status'],'PARTIAL')
        self.assertEqual(result['checks'][0]['evidence'],[])
        self.assertEqual(result['checks'][0]['seen_outside_allowed_source'][0]['observation_id'],'home')
        self.assertEqual(result['checks'][1]['evidence'][0]['quote'],'创建者 Linus')
    async def test_same_name_uses_region_href_and_ad_not_selected(self):
        obs=self.observation('a','https://a.test','安装','aside.sidebar > a',heading='教程')
        state=json.loads(Path(obs['evidence']['state']['path']).read_text())
        obs['controls']['e1']['binding']['href']='https://a.test/install'
        ad=deepcopy(obs['controls']['e1']);ad['element']['element_id']='ad';ad['element']['bbox']=[1700,1,1800,30]
        ad['binding']={'href':'https://ad.test','selector':'.ad > a'};obs['controls']['ad']=ad
        state['capture_controls'][0]['selector']='aside.sidebar > a'
        state['elements'].append(ad['element']);state['capture_controls'].append({'element_id':'ad',**ad['binding']})
        Path(obs['evidence']['state']['path']).write_text(json.dumps(state))
        self.assertEqual(bind_target(obs,{'text':'安装','region':'左栏菜单','href':'https://a.test/install'}),['e1'])
    async def test_expected_navigation_requires_href_landing_and_next_control(self):
        before=self.observation('a','https://a.test/home','安装')
        before['controls']['e1']['binding']['href']='https://a.test/install'
        after=self.observation('b','https://a.test/install','安装成功')
        row={'action':'click','target':{'control_id':'e1'},'operation_id':'op','before_observation_id':'a','after_observation_id':'b'}
        s=SimpleNamespace(trajectory=[row],observation_records=self.obs,current=after,page_urls=[])
        c=SimpleNamespace(last={},position=1,plan={'steps':[{'expected':{'kind':'visible_text','text':'安装成功'}},{'action':'click','target':{'text':'安装成功'}}]})
        c.targets=lambda session,target:bind_target(session.current,target)
        c.last={'operation':'op'}
        self.assertIsNotNone(expected_navigation(s,c))
        after['url']='https://ad.test';self.assertIsNone(expected_navigation(s,c))
    async def test_popup_exact_opener_landing_only(self):
        origin=object();opened=SimpleNamespace(opener=AsyncMock(return_value=origin),wait_for_load_state=AsyncMock(),url='https://a.test/next')
        op={'action_type':'click','evidence':{'anchor_element_id':'e'}}
        state={'url':'https://a.test','capture_controls':[{'element_id':'e','href':opened.url}]}
        self.assertEqual((await verify_popup(origin,opened,op,state))['atomic_actions'],1)
        opened.opener=AsyncMock(return_value=None)
        with self.assertRaisesRegex(ValueError,'SOURCE'):await verify_popup(origin,opened,op,state)
        opened.opener=AsyncMock(return_value=origin);opened.url='https://ad.test'
        with self.assertRaisesRegex(ValueError,'LANDING'):await verify_popup(origin,opened,op,state)
    async def test_original_only_current_observation_and_legacy_task_readable(self):
        a=self.observation('a','https://a.test','内容')
        s=SimpleNamespace(current=a,root=self.root,event=lambda *a,**k:None,task={'fragment':{'plan_protocol':VERSION,'allowed_actions':['scroll']}},
            attempt_id='x',used={'max_decisions':1},trajectory=[],actual_dispatches=0,context={},requested_goal=None,page_urls=[])
        c=Controller();c.request_original='a'
        p=c.prompt(s);self.assertTrue(p['observation']['image_ref'].endswith('.png'))
        s.current=self.observation('b','https://a.test/next','内容')
        self.assertTrue(c.prompt(s)['observation']['image_ref'].endswith('.jpg'))

class FormalFactsTests(unittest.IsolatedAsyncioTestCase):
    async def test_goal_evidence_survives_save_and_independent_qc_snapshot(self):
        from test_banded_plan import BandedSessionTests
        from webcollect.batch_core import load_json
        from quality_inspector.ai_worker import snapshot,verify_snapshot
        f=BandedSessionTests('test_first_plan_then_five_host_actions_finish_and_export_qc_input')
        f.setUp();self.addCleanup(f.doCleanups)
        s,e=f.recorded();original=s.choose
        async def choose(prompt):
            result=await original(prompt)
            text=next(e['text'] for e in f.surface.state['elements'] if e.get('text'))
            result['arguments']['checks']=[{'field':'可见字段','page':s.page.url,'region':text,'visible_text':text}]
            return result
        s.choose=choose
        result=await s.run();self.assertEqual(result['effective_steps'],5)
        terminal=load_json(e/'raw/terminal.json')
        self.assertEqual(terminal['goal_evidence']['business_goal_status'],'VERIFIED')
        destination,annotation=f.derive(e)
        proof=annotation['steps'][-1]['tool_result']['return_value']['goal_evidence']
        self.assertEqual(proof,terminal['goal_evidence'])
        self.assertEqual(load_json(e/'saved_sample.json')['raw_execution']['goal_evidence'],proof)
        verify_snapshot(snapshot(destination))

class ProtocolAlignmentTests(unittest.TestCase):
    def test_tool_schema_rejects_fields_and_endpoint_the_host_rejects(self):
        from jsonschema import Draft202012Validator
        from webcollect.banded_plan import tools
        from test_banded_plan import plan_for
        p=plan_for({'attempt_id':'a','observation':{'observation_id':'o'}})
        schema=tools()[0]['function']['parameters'];v=Draft202012Validator(schema)
        v.validate(p)
        p['steps'][0]['page_id']='p0'
        self.assertTrue(list(v.iter_errors(p)))
        del p['steps'][0]['page_id'];p['finish_when']={'kind':'scroll_changed','text':'移动'}
        self.assertTrue(list(v.iter_errors(p)))
    def test_real_canonical_selector_menu_group_and_ad_counterexample(self):
        from webcollect.plan_evidence import region_matches
        prefix='html:nth-of-type(1) > body:nth-of-type(1) > div:nth-of-type(3) > div:nth-of-type(1) > div:nth-of-type(2)'
        elements=[{'element_id':str(i),'text':text,'bbox':[15,100+i*40,207,139+i*40],'native_role':'a','visible':True} for i,text in enumerate(('教程','简介','安装'))]
        controls=[{'element_id':str(i),'selector':prefix+f' > a:nth-of-type({i+1})','href':f'https://a.test/section{i}'} for i in range(3)]
        state={'url':'https://a.test/home','elements':elements,'capture_controls':controls,'screen_resolution':[1280,720]}
        self.assertTrue(region_matches(state,'1','左栏菜单'))
        controls[2]['href']='https://ad.test';self.assertFalse(region_matches(state,'1','左栏菜单'))
    def test_v3_accepts_only_one_complete_json_fence_without_retry(self):
        from test_model_provider_protocols import ProviderProtocolTests
        f=ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens');f.setUp();self.addCleanup(f.doCleanups)
        ledger,job,g=f.gateway(f.config('glm'))
        f.opener.raw['choices']=[{'finish_reason':'stop','message':{'content':'```json\n{"choice":"stop"}\n```'}}]
        result=g.call_message(job,'v3','x',{'type':'object','required':['choice']},system='s',attempt_id='a',max_requests=25,content_envelope='single-json-fence-1')
        self.assertEqual(result,{'choice':'stop'});self.assertEqual(len(f.opener.calls),1)
        f.opener.raw['choices'][0]['message']['content']='```json\n{}\n```\n```json\n{}\n```'
        with self.assertRaises(ValueError):g.call_message(job,'multiple','x',{'type':'object'},system='s',attempt_id='a',max_requests=25,content_envelope='single-json-fence-1')
        self.assertEqual(len(f.opener.calls),2)

    def test_named_heading_region_uses_canonical_container_not_class_name(self):
        from webcollect.plan_evidence import region_matches
        parent='html:nth-of-type(1) > body:nth-of-type(1) > div:nth-of-type(1) > section:nth-of-type(1)'
        state={'url':'https://a.test/policy','screen_resolution':[1280,720],
          'elements':[{'element_id':'h','text':'政策文件','bbox':[100,100,900,160],'native_role':'h1','visible':True},
                      {'element_id':'department','text':'部门','bbox':[300,120,380,150],'native_role':'button','visible':True}],
          'capture_controls':[{'element_id':'h','selector':parent+' > h1:nth-of-type(1)'},
                              {'element_id':'department','selector':parent+' > button:nth-of-type(1)'}]}
        self.assertTrue(region_matches(state,'department','政策文件'))
        state['capture_controls'][1]['selector']='html > body > footer > button'
        self.assertFalse(region_matches(state,'department','政策文件'))
