"""Offline contract checks; no stopwatch function or production collection."""
from copy import deepcopy
import unittest

from webcollect.stopwatch_strategy import (ADAPTER_ID, STRATEGY_ID, URI, matches_uri,
                                          elapsed_milliseconds, stopwatch_proposal)


def fixture():
    widget = {'kind':'non-form-widget','adapter_id':ADAPTER_ID,'page_uri':URI,'label':'在线秒表计时器',
        'fields':[{'selector':selector,'tag':'button','type':'submit','label':label,
                   'visible':True,'enabled':True,'value':''} for selector,label in
                  [('#startStopwatch','开始'),('#startCount','计次'),('#startDownload','下载'),('#startReset','重置')]],
        'container_selector':'[lay-filter="stopwatchForm"]','display_selector':'#countDownString','display_text':'00:00.000',
        'lap_container_selector':'#tickContainer','lap_container_text':'','lap_child_selectors':['#lastTick'],
        'toggle_text_selector':'#startText','functional_validation':'NOT_RUN'}
    page = {'page_uri':URI,'title':'在线秒表计时器','widgets':[widget],
        'result_targets':[{'selector':'#countDownString','text':'00:00.000','visible':True,'business_label':'秒表累计计时'},
                          {'selector':'#tickContainer','text':'','visible':False,'business_label':'秒表计次记录'}]}
    return {'site_uri':URI}, page, widget


class StopwatchStrategyTests(unittest.TestCase):
    def test_elapsed_parser_preserves_millisecond_and_hour_boundaries(self):
        cases={'00:00.000':0,'00:00.001':1,'00:59.999':59999,'01:00.000':60000,
               '59:59.999':3599999,'01:00:00.000':3600000,'123:45:56.789':445556789}
        for value, expected in cases.items():
            with self.subTest(value=value):self.assertEqual(elapsed_milliseconds(value),expected)

    def test_elapsed_parser_rejects_other_numeric_or_countdown_formats(self):
        for value in ('0','1秒','00:00','00:00.01','00:60.000','60:00.000','-00:01.000',
                      '00:00.000 elapsed',' 00:00.000','NaN',1,None):
            with self.subTest(value=value),self.assertRaises(ValueError):elapsed_milliseconds(value)

    def test_exact_page_binding_excludes_countdown_and_redirect_aliases(self):
        self.assertTrue(matches_uri(URI))
        for uri in (URI+'/',URI+'?a=1',URI+'#clock',URI.replace('https:','http:'),
                    URI.replace('/stopwatch','/countdown'),URI.replace('www.lddgo.net','example.org')):
            with self.subTest(uri=uri):
                self.assertFalse(matches_uri(uri))
                capability,page,widget=fixture();page['page_uri']=uri
                with self.assertRaises(ValueError):stopwatch_proposal(capability,page,widget,'test')

    def test_six_necessary_actions_have_two_stages_and_no_step_padding(self):
        proposal=stopwatch_proposal(*fixture(),'test')
        self.assertEqual(proposal['deterministic_strategy']['id'],STRATEGY_ID)
        self.assertEqual([op['operation_id'] for op in proposal['operations']],
            ['start-first-stage','record-first-stage','pause-break','resume-second-stage','record-second-stage','pause-final'])
        self.assertEqual([op['selector'] for op in proposal['operations']],
            ['#startStopwatch','#startCount','#startStopwatch','#startStopwatch','#startCount','#startStopwatch'])
        self.assertEqual({op['action_type'] for op in proposal['operations']},{'click'})
        self.assertEqual(proposal['effective_page_actions'],6)
        self.assertFalse(proposal['waits_are_effective_actions'])

    def test_initial_controls_never_claim_functional_or_production_acceptance(self):
        proposal=stopwatch_proposal(*fixture(),'test')
        self.assertFalse(proposal['executable_production_task'])
        self.assertEqual(proposal['status'],'FUNCTIONAL_VALIDATION_REQUIRED')
        self.assertNotIn('final_assertions',proposal)
        self.assertTrue(any('capture' in requirement for requirement in proposal['required_functional_evidence']))

    def test_changed_role_hidden_disabled_missing_or_duplicate_control_rejects(self):
        for change in ('title','kind','label','type','hidden','disabled','missing','duplicate','extra'):
            capability,page,widget=fixture()
            if change=='title':page['title']='在线倒计时器'
            elif change=='kind':widget['kind']='form'
            elif change=='label':widget['fields'][0]['label']='暂停'
            elif change=='type':widget['fields'][0]['type']='reset'
            elif change=='hidden':widget['fields'][1]['visible']=False
            elif change=='disabled':widget['fields'][1]['enabled']=False
            elif change=='missing':widget['fields'].pop()
            elif change=='duplicate':widget['fields'][1]['selector']='#startStopwatch'
            else:widget['fields'].append(deepcopy(widget['fields'][0]))
            with self.subTest(change=change),self.assertRaises(ValueError):stopwatch_proposal(capability,page,widget,'test')

    def test_running_preexisting_or_ambiguous_lap_state_rejects(self):
        for key,value in [('display_text','00:01.200'),('lap_container_text','1 00:00.500'),
                          ('display_selector','#other'),('lap_child_selectors',['#lastTick','#extra']),
                          ('toggle_text_selector','#different')]:
            capability,page,widget=fixture();widget[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):stopwatch_proposal(capability,page,widget,'test')

    def test_result_targets_require_visible_zero_clock_and_empty_unique_laps(self):
        for change in ('hidden','value','business','missing','duplicate','existing_lap'):
            capability,page,widget=fixture()
            if change=='hidden':page['result_targets'][0]['visible']=False
            elif change=='value':page['result_targets'][0]['text']='00:00.001'
            elif change=='business':page['result_targets'][0]['business_label']='倒计时'
            elif change=='missing':page['result_targets'].pop()
            elif change=='duplicate':page['result_targets'].append(deepcopy(page['result_targets'][0]))
            else:page['result_targets'][1]['text']='1 00:01.000'
            with self.subTest(change=change),self.assertRaises(ValueError):stopwatch_proposal(capability,page,widget,'test')


if __name__=='__main__':
    unittest.main()
