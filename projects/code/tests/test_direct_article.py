from copy import deepcopy
import unittest
from webcollect.direct_article import VERSION,initial,body,before_action,transition
from webcollect.goal_evidence import validate_contract
from webcollect.banded_plan import system_for

class DirectArticle(unittest.TestCase):
    def setUp(self):
        self.url='https://example.org/wiki/Ivan'
        self.contract={'version':VERSION,'kind':'reading','entry_url':self.url,'titles':['飓风伊万的气象历史','颶風伊萬的氣象歷史']}
        self.task={'initial_url':self.url,'fragment':{'plan_protocol':'webcollect-banded-conditional-plan-8','session_objective':{'objective':{'evidence_contract':self.contract}}}}
        self.state={'url':self.url,'title':'飓风伊万的气象历史 - 百科','document_identity':{'nonce':'one'},'scroll':[0,0],
            'elements':[{'element_id':'main','native_role':'main','visible':True,'text':'','bbox':[0,0,900,700]},
                {'element_id':'h','native_role':'h1','visible':True,'text':self.contract['titles'][0],'parent_id':'main'},
                {'element_id':'p','native_role':'p','visible':True,'text':'这是受控的正文段落，说明本地页面所展示的气象发展过程，不预设真实词条内容与答案。','parent_id':'main'},
                {'element_id':'link','native_role':'a','visible':True,'text':'热带气旋','parent_id':'main'},
                {'element_id':'toc','native_role':'a','visible':True,'text':'章节','parent_id':'nav'}],
            'capture_controls':[{'element_id':'main','selector':'main:1'}, {'element_id':'h','selector':'main:1 > h1:1'},
                {'element_id':'p','selector':'main:1 > p:1'}, {'element_id':'link','selector':'main:1 > a:1','href':'https://example.org/wiki/Cyclone'},
                {'element_id':'toc','selector':'nav:1 > a:1','href':self.url+'#later'}], 'values':[]}
    def test_explicit_contract_identity_and_no_invented_semantic_keywords(self):
        validate_contract(self.contract);self.assertTrue(initial(self.task,self.state,self.contract))
        prompt=system_for(self.task);self.assertIn('不提供浏览器原生Ctrl/Cmd+F',prompt)
        self.assertNotIn('搜索后用expected.kind=search_results',prompt)
        for field,value in [('url','https://example.org/wiki/Other'),('url',self.url+'?search=x')]:
            wrong=deepcopy(self.state);wrong[field]=value
            with self.assertRaises(ValueError):initial(self.task,wrong,self.contract)
        wrong=deepcopy(self.state);wrong['elements'][1]['text']='另一篇文章'
        with self.assertRaises(ValueError):initial(self.task,wrong,self.contract)
        titleonly=deepcopy(self.state);titleonly['elements']=titleonly['elements'][:2]
        with self.assertRaises(ValueError):initial(self.task,titleonly,self.contract)
        variant=deepcopy(self.state);variant['elements'][1]['text']=self.contract['titles'][1]
        self.assertTrue(initial(self.task,variant,self.contract))
    def test_nested_navigation_aside_and_link_text_are_not_body(self):
        for role in ('nav','aside','navigation','complementary','header','footer','form'):
            state=deepcopy(self.state);state['elements'].append({'element_id':'nested','native_role':role,'parent_id':'main'})
            state['elements'][2]['parent_id']='nested';state['capture_controls'][2]['selector']='main:1 > '+('div' if role in ('navigation','complementary') else role)+':1 > p:1'
            self.assertEqual(body(state),[],role)
        state=deepcopy(self.state);state['elements'][2]['native_role']='a';self.assertEqual(body(state),[])
    def test_paragraph_bold_and_wiki_footnote_are_body_but_nested_navigation_is_not(self):
        # Real snapshot shape: p with a direct b and ordinary linked children;
        # Wiki footnotes add sup > a. Text must remain the paragraph's own quote.
        state=deepcopy(self.state)
        state['text_blocks']=[{'element_id':'p','visible_text':state['elements'][2]['text']}]
        state['elements'] += [{'element_id':'bold','native_role':'b','parent_id':'p','visible':True,'text':'受控主体'},
            {'element_id':'footnote','native_role':'sup','parent_id':'p','visible':True,'text':'[1]'},
            {'element_id':'reference','native_role':'a','parent_id':'footnote','visible':True,'text':'[1]'}]
        self.assertIn({'node':'p','quote':state['elements'][2]['text']},body(state))
        for role in ('i','sub','em','strong','span','small','abbr','cite','code','br'):
            state['elements'][-3]['native_role']=role
            self.assertIn({'node':'p','quote':state['elements'][2]['text']},body(state),role)
        own=deepcopy(state);own['elements'][2]['text']='自身文本会丢失链接或加粗内容'
        self.assertIn({'node':'p','quote':state['elements'][2]['text']},body(own))
        missing=deepcopy(state);missing.pop('text_blocks')
        self.assertNotIn('p',[p['node'] for p in body(missing)])
        for role in ('b','small','sup','span'):
            inline=deepcopy(self.state);inline['elements'][2]['native_role']=role
            self.assertEqual(body(inline),[],role)
        for role in ('nav','aside','form','section','div'):
            state['elements'][-3]['native_role']=role
            self.assertNotIn('p',[p['node'] for p in body(state)],role)

    def test_immediate_back_and_deep_return_anchor_not_initial_h1(self):
        deep=deepcopy(self.state);deep['scroll']=[0,700];deep['elements'][1]['visible']=False
        away=deepcopy(deep);away['url']='https://example.org/wiki/Cyclone';away['title']='关联页';away['document_identity']={'nonce':'away'}
        pending,returned=transition(self.task,deep,away,'click',{},'link');self.assertTrue(pending);self.assertFalse(returned)
        for action,args in [('click',{}),('scroll',{'direction':'down'}),('hotkey',{'keys':['enter']})]:
            with self.assertRaises(ValueError):before_action(self.task,away,action,args,'link',pending=pending)
        back=deepcopy(deep);back['document_identity']={'nonce':'reloaded'}
        self.assertEqual(transition(self.task,away,back,'back',{},pending=pending),(None,True))
        for mode in ('wrongurl','wrongtitle','wrongbody'):
            wrong=deepcopy(back)
            if mode=='wrongurl':wrong['url']=self.url+'?different=1'
            if mode=='wrongtitle':wrong['title']='Wrong'
            if mode=='wrongbody':wrong['elements'][2]['text']='这是完全不同页面的正文，不能仅用相同网址继承原词条的主体身份和已有引文。'
            with self.assertRaises(ValueError):transition(self.task,away,wrong,'back',{},pending=pending)
    def test_fragment_is_same_page_but_query_and_path_leave(self):
        after=deepcopy(self.state);after['url']+='#later';after['scroll']=[0,800]
        self.assertEqual(transition(self.task,self.state,after,'click',{},'toc'),(None,False))
        for suffix in ('?variant=other','/other'):
            state=deepcopy(self.state);state['capture_controls'][3]['href']=self.url+suffix
            after=deepcopy(state);after['url']=self.url+suffix
            self.assertIsNotNone(transition(self.task,state,after,'click',{},'link')[0])
    def test_search_and_submit_and_native_find_refused(self):
        state=deepcopy(self.state);state['elements'].append({'element_id':'q','native_role':'input','visible':True,'inputable':True,'text':'搜索'})
        state['capture_controls'].append({'element_id':'q','input_type':'search'})
        for action,args,cid in [('click',{},'q'),('type',{'text':'月食'},'q'),('hotkey',{'keys':['enter']},None),('hotkey',{'keys':['ctrl','f']},None),('hotkey',{'keys':['meta','f']},None)]:
            with self.assertRaises(ValueError):before_action(self.task,state,action,args,cid)
        state['elements'].append({'element_id':'button','native_role':'button','text':'搜索','visible':True});state['capture_controls'].append({'element_id':'button'})
        with self.assertRaises(ValueError):before_action(self.task,state,'click',{},'button')
        before_action(self.task,state,'hotkey',{'keys':['pagedown']})
        state['capture_controls'][3]['href']='https://example.org/w/index.php?title=Special:Search'
        with self.assertRaises(ValueError):before_action(self.task,state,'click',{},'link')

    def test_return_keeps_original_reading_and_rebinds_citation_without_extra_scroll(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from webcollect.agent_controller import exclusive
        from webcollect.direct_article import progress
        with TemporaryDirectory() as d:
            root=Path(d);observations={}
            def ob(name,state):
                observations[name]={'observation_id':name,'capture_verified':True,'url':state['url'],'document_identity':state['document_identity'],'evidence':{'state':exclusive(root/(name+'.json'),state)}}
                return observations[name]
            start=ob('start',self.state);deep=deepcopy(self.state);deep['scroll']=[0,700];deep['elements'][1]['visible']=False
            deep['elements'][2]['text']='下读后新出现的原词条正文，记录受控章节的进一步变化与阅读事实，关联页面不得替代这段实际可见原文。'
            ob('deep',deep);away=deepcopy(deep);away.update(url='https://example.org/wiki/Cyclone',title='关联词条',document_identity={'nonce':'away'})
            away['elements'][2]['text']='关联页正文可以显示，但不属于原词条，不能获得原词条正文引用资格。';ob('away',away)
            returned=deepcopy(deep);returned['document_identity']={'nonce':'returned'};returned['elements'][2]['element_id']='newp';returned['capture_controls'][2]['element_id']='newp';ob('returned',returned)
            steps=[{'action':'scroll','arguments':{'direction':'down'},'operation_id':'read','before_observation_id':'start','after_observation_id':'deep'},
                {'action':'click','arguments':{},'target':{'control_id':'link'},'operation_id':'visit','before_observation_id':'deep','after_observation_id':'away'},
                {'action':'back','arguments':{},'operation_id':'back','before_observation_id':'away','after_observation_id':'returned'}]
            session=SimpleNamespace(task=self.task,plan_controller=SimpleNamespace(frozen_plan={'observation_id':'start'}),trajectory=steps,observation_records=observations,current=observations['returned'],binding={'controlled':'boundary'},attempt_id='local',answer_citation=None)
            result=progress(session,start,self.contract);self.assertEqual(result['status'],'PASSAGE_AVAILABLE');passage=result['passages'][0]
            self.assertEqual((passage['read_observation_id'],passage['observation_id'],passage['node']),('deep','returned','newp'))
            branch={'kind':'plan-branch','boundary':session.binding,'response':{'attempt_id':'local','observation_id':'returned','choice':'cite:newp'},'provider_reply':{'choice':'cite:newp'},'options':[{'choice':'cite:newp','passage':passage}]}
            session.answer_citation=exclusive(root/'cite.json',branch)
            fresh=deepcopy(returned);fresh['elements'][2]['element_id']='freshp';fresh['capture_controls'][2]['element_id']='freshp';session.current=ob('fresh',fresh)
            self.assertEqual(progress(session,start,self.contract)['status'],'VERIFIED')
            session.current=observations['away'];self.assertEqual(progress(session,start,self.contract)['status'],'UNVERIFIED')
            wrong=deepcopy(fresh);wrong['document_identity']={'nonce':'unexplained'};session.current=ob('sameurl_other',wrong)
            self.assertEqual(progress(session,start,self.contract)['status'],'UNVERIFIED')
            session.trajectory=steps[:2];session.current=observations['away']
            self.assertTrue(progress(session,start,self.contract)['return_required'])

    def test_ordinary_research_article_link_is_not_site_search(self):
        state=deepcopy(self.state);state['capture_controls'][3]['href']='https://example.org/wiki/Research'
        before_action(self.task,state,'click',{},'link')

    def test_direct_first_and_branch_schema_share_capabilities_without_dangling_source(self):
        from jsonschema import Draft202012Validator
        from webcollect.direct_article import protocol_schema
        from webcollect.banded_plan import tools,choice_schema
        import json
        first=protocol_schema(tools(True,pending_checks=True),self.contract)[0]['function']['parameters']
        branch=protocol_schema(choice_schema(True,inherited=True),self.contract)
        for schema in (first,branch):
            Draft202012Validator.check_schema(schema)
            self.assertNotIn('search_results',json.dumps(schema))
            def check(v):
                if isinstance(v,dict):
                    if v.get('additionalProperties') is False:self.assertTrue(set(v.get('required',[]))<=set(v.get('properties',{})))
                    for item in v.values():check(item)
                elif isinstance(v,list):
                    for item in v:check(item)
            check(schema)
        prompt=system_for(self.task)
        self.assertNotIn('网站快捷键可聚焦真实站内搜索框',prompt)
        self.assertNotIn('必要时包含真正触发计算',prompt)
