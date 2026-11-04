"""Synthetic parameter/output evidence, not a hardcoded calculator executor."""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import json,tempfile,unittest
from webcollect.session_objective import progress
from webcollect.banded_plan import Controller,proves,execution_keys

class ObjectiveEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.obs={}
        self.html='<html><body><main><div id="result"></div></main></body></html>'
        self.task={'fragment':{'session_objective':{'objective':{'kind':'mortgage_calculation','parameters':{'principal':300000,'annual_percent':4.2}}}}}
    def observation(self,name,p=5000000,r=2.5,result=None):
        elements=[{'element_id':'p','text':'本金','visible':True,'inputable':True,'native_role':'input','bbox':[1,1,100,30]},
                  {'element_id':'r','text':'年利率','visible':True,'inputable':True,'native_role':'input','bbox':[1,40,100,70]},
                  {'element_id':'help','text':'每月还款说明','visible':True,'native_role':'p','bbox':[1,80,400,100]}]
        bindings=[]
        html=self.html
        if result:
            elements.append({'element_id':'out','text':result,'visible':True,'native_role':'p','bbox':[1,200,400,240]})
            bindings=[{'element_id':'out','selector':'html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) > div:nth-of-type(1) > p:nth-of-type(1)'}]
            html=self.html.replace('<div id="result"></div>','<div id="result"><p>'+result+'</p></div>')
        st={'url':'https://fixture.invalid/calculator','screen_resolution':[1280,720],'elements':elements,'capture_controls':bindings,'visible_text':'\n'.join(e['text'] for e in elements),
            'values':[{'element_id':'p','value':str(p),'value_visible':True,'display_value':str(p)},{'element_id':'r','value':str(r),'value_visible':True,'display_value':str(r)}]}
        path=self.root/(name+'.json');path.write_text(json.dumps(st))
        ob={'observation_id':name,'url':st['url'],'document_identity':{'id':'same'},'capture_verified':True,'evidence':{'state':{'path':str(path)},'image':{'path':'fixture','sha256':'fixture'}},'controls':{},'html':html}
        self.obs[name]=ob;return ob
    def session(self,result):
        initial=self.observation('initial');one=self.observation('one',300000);two=self.observation('two',300000,4.2);now=self.observation('now',300000,4.2,result)
        trace=[{'action':'type','operation_id':'a','target':{'control_id':'p'},'before_observation_id':'initial','after_observation_id':'one'},
               {'action':'type','operation_id':'b','target':{'control_id':'r'},'before_observation_id':'one','after_observation_id':'two'}]
        return SimpleNamespace(task=self.task,trajectory=trace,observation_records=self.obs,current=now)
    def test_old_help_label_and_focus_do_not_establish_calculation(self):
        initial=self.observation('initial');s=SimpleNamespace(task=self.task,trajectory=[],observation_records=self.obs,current=initial)
        self.assertTrue(proves({'kind':'visible_text','text':'每月还款'},initial))
        self.assertEqual(progress(s,'initial')['status'],'UNVERIFIED')
        c=Controller();c.plan={'observation_id':'initial','finish_when':{'kind':'visible_text','text':'每月还款'}}
        self.assertFalse(c.proved(c.plan['finish_when'],s))
    def test_two_real_changes_and_new_named_result_required(self):
        s=self.session('每月还款 1467.05');result=progress(s,'initial')
        self.assertEqual(result['status'],'VERIFIED',result);self.assertEqual(len(result['parameter_changes']),2)
    def test_new_input_echo_is_not_new_result(self):
        s=self.session('本金300000 年利率4.2');self.assertEqual(progress(s,'initial')['status'],'UNVERIFIED')
    def test_logical_select_all_and_observed_text_selection(self):
        self.assertEqual(execution_keys(['Control','a'],'darwin'),['meta','a'])
        self.assertEqual(execution_keys(['Control','a'],'win32'),['ctrl','a'])
        ob=self.observation('selected');ob['controls']={'p':{'value':{'focused':True,'value':'5000000','all_text_selected':True}}}
        self.assertTrue(proves({'kind':'text_selected','text':'5000000'},ob))
        ob['controls']['p']['value']['all_text_selected']=False
        self.assertFalse(proves({'kind':'text_selected','text':'5000000'},ob))

class SearchReadingEvidence(unittest.TestCase):
    def test_typed_query_visible_suggestion_click_and_later_new_body_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);obs={};query='相关知识 查询';initial_url='https://fixture.invalid/wiki/start';landing='https://fixture.invalid/wiki/article'
            def make(oid,url,doc,paragraph,query_value='',result_link=False,scroll=0):
                elements=[{'element_id':'p','text':paragraph,'visible':True,'native_role':'p','bbox':[10,100,500,200]}]
                state={'url':url,'title':'相关条目','screen_resolution':[1280,720],'scroll':[0,scroll],'elements':elements,'values':[{'element_id':'query','value':query_value}],
                    'capture_controls':[{'element_id':'p','selector':'main > p'}],'visible_text':paragraph}
                path=root/(oid+'.json');path.write_text(json.dumps(state))
                controls={'result':{'element':{'native_role':'a','text':'相关条目','visible':True},'binding':{'href':landing}}} if result_link else {}
                ob={'observation_id':oid,'url':url,'document_identity':{'id':doc},'capture_verified':True,'controls':controls,'evidence':{'state':{'path':str(path)}}};obs[oid]=ob;return ob
            make('initial',initial_url,'d0','原入口正文')
            make('typed',initial_url,'d0','可见搜索建议',query,True)
            make('article',landing,'d1','条目开头正文')
            current=make('scrolled',landing,'d1','这是在搜索并打开相关条目后真实滚动才新出现的一整段正文，用于证明本次阅读末态。',scroll=500)
            actions=[{'action':'type','operation_id':'type','arguments':{'text':query},'target':{'control_id':'query'},'before_observation_id':'initial','after_observation_id':'typed'},
                     {'action':'click','operation_id':'open','target':{'control_id':'result'},'before_observation_id':'typed','after_observation_id':'article'},
                     {'action':'scroll','operation_id':'scroll','before_observation_id':'article','after_observation_id':'scrolled'}]
            s=SimpleNamespace(task={'fragment':{'session_objective':{'objective':{'kind':'site_search_reading','parameters':{'query':query}}}}},trajectory=actions,observation_records=obs,current=current)
            self.assertEqual(progress(s,'initial')['status'],'VERIFIED')
            s.trajectory=[actions[0],actions[2],actions[1]]
            self.assertEqual(progress(s,'initial')['status'],'UNVERIFIED')
            s.trajectory=actions;actions[0]['arguments']['text']='别的查询'
            self.assertEqual(progress(s,'initial')['status'],'UNVERIFIED')
