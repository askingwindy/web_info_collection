"""Disposable template/real-host-tool contract checks; all external IO mocked."""
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock

from webcollect.consumer_templates import (calculator_goal, reading_goal, resolve_goal, article,
    result_quotes, section_body, Inapplicable, enabled, TemplateSession, CALCULATOR, READING)
from webcollect import react_session


def calc():
    return {'url':'https://example.test/calc','title':'计算器','screen_resolution':[1280,720],
        'visible_text':'收入计算器\n年收入\n计算', 'values':[{'element_id':'a','value':'0','readonly':False}],
        'elements':[{'element_id':'a','text':'年收入（元）','inputable':True,'enabled':True,'visible':True,'bbox':[20,80,200,120]},
                    {'element_id':'b','text':'计算','visible':True,'enabled':True,'bbox':[20,140,100,180]}],
        'capture_controls':[{'element_id':'a','tag':'input','input_type':'number','selector':'#income'},
                            {'element_id':'b','tag':'button','selector':'#calc'}]}


def wiki():
    return {'url':'https://zh.wikipedia.org/wiki/示例','title':'示例 - 维基百科，自由的百科全书',
        'visible_text':'简介\n发展\n正文','screen_resolution':[1280,720],'scroll':{'x':0,'y':0},
        'elements':[{'element_id':'m','native_role':'main','parent_id':'root'},
                    {'element_id':'h','native_role':'h2','parent_id':'m','text':'发展','visible':True,'bbox':[30,150,180,180]},
                    {'element_id':'p','native_role':'p','parent_id':'m','text':'正文','visible':True,'bbox':[20,20,800,130]}],
        'text_blocks':[{'element_id':'p','visible_text':'这是一段实际可见的词条正文，用于解释本条目的定义和主要内容，并作为本次定向阅读的简介证据。'}]}


class MatcherTests(unittest.TestCase):
    def test_calc_binds_actual_field_and_units(self):
        p=calculator_goal(calc());self.assertEqual(p['fields'][0]['value'],'50000')
        self.assertIn('年收入（元）=50000',p['description'])
        self.assertEqual(p['button_selector'],'#calc')

    def test_common_rule_independent_of_assignment(self):
        s=calc();self.assertEqual(resolve_goal(s,'calculator'),resolve_goal(deepcopy(s),'calculator'))

    def test_ambiguous_field_duplicate_and_non_numeric_fallback(self):
        for change in ('duplicate','date','hidden'):
            s=calc()
            if change=='duplicate':
                e=deepcopy(s['elements'][0]);e['element_id']='c';s['elements'].append(e)
                b=deepcopy(s['capture_controls'][0]);b['element_id']='c';s['capture_controls'].append(b)
            elif change=='date':s['capture_controls'][0]['input_type']='date'
            else:s['elements'][0]['bbox']=[20,800,200,840]
            with self.assertRaises(Inapplicable):calculator_goal(s)

    def test_explicit_goal_is_preserved_and_handed_to_original_agent(self):
        goal={'parameters':{'年收入':90000},'description':'核对税后金额'};old=deepcopy(goal)
        with self.assertRaisesRegex(Inapplicable,'EXPLICIT_GOAL'):resolve_goal(calc(),'calculator',goal)
        self.assertEqual(goal,old)

    def test_unknown_solver_never_fills_all_fields(self):
        s=calc();s['visible_text']+=' 留空表示要计算此项'
        with self.assertRaisesRegex(Inapplicable,'SOLVER_UNKNOWN'):calculator_goal(s)

    def test_wiki_article_body_vs_portal_index(self):
        s=wiki();self.assertEqual(reading_goal(s)['heading'],'发展')
        for url in ('https://zh.wikipedia.org/wiki/Portal:首页','https://zh.wikipedia.org/wiki/Wikipedia:分类索引'):
            s['url']=url;self.assertFalse(article(s))
            with self.assertRaises(Inapplicable):reading_goal(s)

    def test_directory_text_not_article_body(self):
        s=wiki();s['text_blocks']=[]
        with self.assertRaises(Inapplicable):reading_goal(s)

    def test_old_or_bare_input_numbers_do_not_prove_result(self):
        old=calc();new=deepcopy(old);new['visible_text']+='\n50000'
        self.assertEqual(result_quotes(new,old),[])
        new['visible_text']+='\n税后净收入：45000 元'
        self.assertEqual(result_quotes(new,old),[])  # Unbound text still cannot prove a result.

    def result_state(self,text):
        return {'screen_resolution':[1280,720],'elements':[{'element_id':'r','text':text,
            'native_role':'p','visible':True,'bbox':[20,100,400,140]}],
            'capture_controls':[{'element_id':'r','selector':'html:nth-of-type(1) > body:nth-of-type(1) > p:nth-of-type(1)'}]}

    def test_result_binds_visible_region_and_click_before_numbers(self):
        s=self.result_state('税后净收入：45000 元')
        html='<html><body><p id="result">税后净收入：45000 元</p></body></html>'
        before='<html><body><p id="result"></p></body></html>'
        self.assertEqual(result_quotes(s,{},html,before)[0]['after_numbers'],['45000'])
        self.assertEqual(result_quotes(s,{},html,html),[])  # Old offscreen result, newly scrolled into view.

    def test_input_echo_help_example_and_unbound_text_never_count_as_result(self):
        for attrs in ('','id="help"','id="example"','class="result example"'):
            old=f'<html><body><p {attrs}>年收入</p></body></html>'
            html=f'<html><body><p {attrs}>年收入 50000 元</p></body></html>'
            self.assertEqual(result_quotes(self.result_state('年收入 50000 元'),{},html,old),[])
        html='<html><body><p id="result"><input value="50000">年收入 50000 元</p></body></html>'
        self.assertEqual(result_quotes(self.result_state('年收入 50000 元'),{},html,'<html><body></body></html>'),[])
        html='<html><body><p id="result">年收入 50000 元</p></body></html>'
        self.assertEqual(result_quotes(self.result_state('年收入 50000 元'),{'values':[{'value':'50000'}]},html,
                                       '<html><body><p id="result"></p></body></html>'),[])

    def test_target_heading_at_bottom_does_not_claim_previous_section_paragraph(self):
        s=wiki();s['elements']=[{'element_id':'p','native_role':'p','parent_id':'m','text':'上一节正文',
            'visible':True,'bbox':[20,80,800,200]}, {'element_id':'h','native_role':'h2','text':'目标章节',
            'parent_id':'m','visible':True,'bbox':[20,650,800,690]}, {'element_id':'m','native_role':'main','parent_id':'root'}]
        s['text_blocks']=[{'element_id':'p','visible_text':'上一节可见的长正文。'*8}]
        self.assertEqual(section_body(s,'目标章节'),([],[]))
        s['elements'][0]['bbox']=[20,695,800,720]
        self.assertEqual(section_body(s,'目标章节')[0],['上一节可见的长正文。'*8])

    def test_sidebar_heading_and_sidebar_paragraph_are_not_article_evidence(self):
        s=wiki();s['elements'][:0]=[{'element_id':'n','native_role':'nav','parent_id':'root'},
            {'element_id':'nh','native_role':'h2','parent_id':'n','text':'工具','visible':True,'bbox':[900,10,1200,40]},
            {'element_id':'np','native_role':'p','parent_id':'n','text':'侧栏文字','visible':True,'bbox':[900,200,1200,300]}]
        s['text_blocks'].append({'element_id':'np','visible_text':'侧栏长文字不能算作目标章节的正文。'*5})
        self.assertEqual(reading_goal(s)['heading'],'发展')
        self.assertEqual(section_body(s,'发展')[0],[])

    def test_opt_in_restores_ordinary_session(self):
        old=react_session.ReactSession
        with enabled([{'candidate_id':'c','arm':'template','family':'calculator'}]):
            self.assertIs(react_session.ReactSession,TemplateSession)
        self.assertIs(react_session.ReactSession,old)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    def session(self,plan):
        s=object.__new__(TemplateSession);s.plan=plan;s.current={'observation_id':'obs','controls':{}}
        s.template_dispatches=0;s.template_tools=0;s.reactive_rounds=0;s.filled=set();s.calculated=False
        s.event=lambda *a,**k:{};s._tool_act=AsyncMock(return_value={'status':'ok'})
        s._observe=AsyncMock(return_value={'status':'ok'});s._native_finish=AsyncMock(return_value={'status':'ok'})
        s.actual_dispatches=0;return s

    async def test_executor_calls_real_host_act_instead_of_fake_model_response(self):
        s=self.session(calculator_goal(calc()))
        s.current['controls']={'a':{'binding':{'selector':'#income','element_id':'a'},
                                   'actions':{'set_value':{'status':'PROVEN'}}}}
        self.assertTrue(await s.act_control('#income','set_value','输入收入',value='50000'))
        args=s._tool_act.call_args.args[0]
        self.assertEqual(args['step']['value'],'50000');self.assertEqual(args['observation_id'],'obs')
        s._native_finish.assert_not_called()

    async def test_missing_probe_observes_without_dispatch(self):
        s=self.session(calculator_goal(calc()))
        s.current['controls']={'a':{'binding':{'selector':'#income','element_id':'a'},
                                   'actions':{'set_value':{'status':'INSUFFICIENT','reason':'MISSING_TARGET_PROBE'}}}}
        self.assertFalse(await s.act_control('#income','set_value','输入收入',value='50000'))
        s._tool_act.assert_not_called();s._observe.assert_awaited_once_with('a')

    async def test_host_rejection_falls_back_and_is_not_template_success(self):
        s=self.session(calculator_goal(calc()));s._tool_act.return_value={'status':'rejected','summary':'stale'}
        with self.assertRaisesRegex(Inapplicable,'HOST_TOOL'):await s.host_tool('act',{})

    async def test_dispatched_stop_is_still_counted_as_template_execution(self):
        from webcollect.react_session import ReactStop
        s=self.session(calculator_goal(calc()))
        async def stop_after_dispatch(arguments):
            s.actual_dispatches+=1
            raise ReactStop('blocked','Known stopped action; preserve original dispatch')
        s._tool_act=stop_after_dispatch
        with self.assertRaises(ReactStop):await s.host_tool('act',{})
        self.assertEqual(s.template_dispatches,1)

    async def test_changed_label_or_already_filled_parameter_never_reuses_selector(self):
        for changed_label in (True,False):
            s=self.session(calculator_goal(calc()));s.state_now=lambda:calc()
            s.current['controls']={'a':{'binding':{'selector':'#income','element_id':'a','input_type':'number'},
                'element':{'text':'另一字段' if changed_label else '年收入（元）'},
                'value':{'value':'50001'},'actions':{'set_value':{'status':'PROVEN'}}}}
            if not changed_label:s.filled={'#income'}
            with self.assertRaisesRegex(Inapplicable,'FIELD_IDENTITY_CHANGED|FILLED_PARAMETER_CHANGED'):
                await s.calculator_round()
            s._tool_act.assert_not_called()

    async def test_reading_uses_actual_scroll_tool_and_keeps_position(self):
        s=self.session(reading_goal(wiki()));s.read_positions=[];s.read_quotes=[];s.read_heading_seen=False;s.target_body_ids=set()
        s.state_now=lambda:wiki()
        await s.reading_round()
        self.assertEqual(s._tool_act.call_args.args[0]['step']['action'],'scroll')
        self.assertEqual(s.read_positions,[{'x':0,'y':0}])
        with self.assertRaisesRegex(Inapplicable,'POSITION_REPEATED'):await s.reading_round()
