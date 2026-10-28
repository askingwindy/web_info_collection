"""Native local captures must not turn planned history into observed final facts."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from playwright.async_api import async_playwright
from webcollect.browser import SNAPSHOT_JS
from webcollect.collect import collect_one,completion_from_assertions
from webcollect.evidence import audit_capture

QC_ROOT=Path(__file__).resolve().parents[2]/'quality-inspector'
sys.path.insert(0,str(QC_ROOT))
from quality_inspector import preparation_evidence as QC
URL='https://completion-evidence.invalid/article'
PROSE=('这里是独立手写的本地公开阅读测试正文，用来核对实际操作和最终画面的证据。'
       '页面只提供当前五个段落的核对按钮，没有网站首页、职责或者服务概览等导航。'
       '最终描述应根据当前已经显示的文字形成，不应把计划中的历史话术当成已发生的事情。')
FINAL='核对完成：电话询问与互联网提供文字及声音版本。'
POISON_RESULT='未经执行的历史：此前从首页导航进入职责和服务概览，再阅读多个外部页面。'
POISON_JUDGEMENT='未经执行的历史：已经通过官网首页链接查阅职责，完成全部导航和注册。'


def fixture(early=False):
    buttons=[]
    for i in range(1,6):
        result=FINAL if i==5 or (early and i==1) else f'已核对第{i}段，继续阅读。'
        buttons.append(f'<button id="b{i}" onclick="document.querySelector(\'#result\').textContent=\'{result}\'">核对第{i}段</button>')
    return '<!doctype html><meta charset="utf-8"><title>本地末态事实核对</title>'\
        '<style>body{margin:0;font:20px/1.6 sans-serif}article{padding:24px;width:850px}button{font:inherit;margin:4px}</style>'\
        '<article><h1>实际末态证据测试</h1><p>'+PROSE+'</p><p>'+PROSE+'</p>'+''.join(buttons)+'<p id="result">等待核对。</p></article>'


def task(poisoned=False,early=False):
    operations=[{'action_type':'click','selector':f'#b{i}','arguments':{},'goal':f'核对当前第{i}段',
        'rationale':'根据可见段落进行当前内容核对','expected':f'第{i}段核对状态显示',
        'execution':{'settle_ms':30}} for i in range(1,6)]
    return {'task_id':'local-completion-facts','app_name':'本地末态证据测试','site_uri':URL,'initial_url':URL,
        'initial_settle_ms':0,'stop_when_final':early,'content_preparation':{'mode':'auto'},
        'instruction':'逐项核对本地五个段落，最终确认显示文字及声音版本；合成测试，不得计为交付样本。',
        'task_type':['数据查看'],'operations':operations,
        'final_assertions':[{'visible_text':'核对完成'},{'selector':'#result','contains':'文字及声音版本'}],
        'final_result':POISON_RESULT if poisoned else '计划核对当前末态。',
        'completion_judgement':POISON_JUDGEMENT if poisoned else '计划检查当前页面的末态文字。'}


class CompletionEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.temp=None
        artifacts=os.environ.get('WEBCOLLECT_COMPLETION_TEST_ARTIFACTS')
        if artifacts:
            self.root=Path(artifacts)/self._testMethodName;self.root.mkdir(parents=True,exist_ok=False)
        else:
            self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    async def asyncTearDown(self):
        await self.browser.close();await self.runtime.stop()
        if self.temp:self.temp.cleanup()

    async def collect_case(self,name,poisoned=False,early=False):
        context=await self.browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1)
        try:
            html=fixture(early)
            await context.route(URL,lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=html))
            plan=task(poisoned,early);original=deepcopy(plan)
            case=self.root/name;case.mkdir()
            (case/'scope.json').write_text(json.dumps({'synthetic_only':True,'formal_sample_count':0,
                'fixture_sha256':sha256(html.encode()).hexdigest(),'actual_native_browser_test':True},indent=2))
            (case/'task.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
            sid='S000001_sample_000001';sample=case/'samples'/sid;evidence=case/'evidence'/sid
            annotation=await collect_one(context,plan,sample,evidence,{'sample_id':sid})
            self.assertEqual(plan,original,'Producer must not rewrite the original task plan')
            raws=[json.loads(p.read_text()) for p in sorted(evidence.glob('step_*.json'))]
            captures=audit_capture(case,sid)
            self.assertTrue(captures['capture_evidence_pass'],captures)
            preparation=QC.audit_preparation(evidence,sample,expected_policy='content-preparation-v1',
                expected_observer_sha256=sha256(SNAPSHOT_JS.encode()).hexdigest())
            self.assertEqual(preparation['status'],'PASS',preparation)
            (case/'integrity-audits.json').write_text(json.dumps({'capture':captures,'preparation':preparation},ensure_ascii=False,indent=2))
            return annotation,raws,sample,plan
        finally:await context.close()

    def assert_actual_completion(self,annotation,raws,plan):
        last=annotation['steps'][-1];raw=raws[-1]
        actual=completion_from_assertions(raw['final_assertions'])
        self.assertIn('核对完成',actual);self.assertIn('文字及声音版本',actual)
        for value in [annotation['final_result'],annotation['completion_judgement'],last['step_result'],
                      last['action']['expected_result'],last['next_step_rationale'],
                      raw['operation']['expected'],raw['operation']['rationale']]:
            self.assertEqual(value,actual)
            self.assertNotIn('未经执行的历史',value)
        self.assertNotIn('未经执行的历史',json.dumps(annotation,ensure_ascii=False))
        planned=raw['planned_completion']
        self.assertEqual(planned['final_result'],plan['final_result'])
        self.assertEqual(planned['completion_judgement'],plan['completion_judgement'])
        self.assertEqual(planned['operation']['expected'],plan['final_result'])
        self.assertEqual(planned['operation']['rationale'],plan['completion_judgement'])
        self.assertEqual(raw['completion_description_source'],'passed_final_assertions')
        self.assertTrue(all(item['passed'] for item in raw['final_assertions']))
        self.assertEqual(raw['executed_action'],{'tool_name':'complete','arguments':{'status':'success'}})

    async def test_unexecuted_plan_history_never_changes_complete_facts_or_capture_chain(self):
        control,control_raw,control_sample,control_plan=await self.collect_case('control')
        poisoned,poison_raw,poison_sample,poison_plan=await self.collect_case('poisoned',poisoned=True)
        self.assert_actual_completion(control,control_raw,control_plan)
        self.assert_actual_completion(poisoned,poison_raw,poison_plan)
        self.assertEqual(len(poison_raw),6)
        self.assertEqual([x['planned_operation_index'] for x in poison_raw],list(range(6)))
        self.assertTrue(all(x['operation_origin']=='planned' for x in poison_raw))
        self.assertEqual([x['state'] for x in control_raw],[x['state'] for x in poison_raw])
        self.assertEqual([x['executed_action'] for x in control_raw],[x['executed_action'] for x in poison_raw])
        for a,b in zip(control['steps'],poisoned['steps']):
            self.assertEqual((control_sample/a['image_path']).read_bytes(),(poison_sample/b['image_path']).read_bytes())
        for index,raw in enumerate(poison_raw[:-1]):self.assertEqual(raw['operation'],poison_plan['operations'][index])

    async def test_goal_already_satisfied_keeps_original_plan_text_only_in_raw_audit_field(self):
        annotation,raws,_,plan=await self.collect_case('early',poisoned=True,early=True)
        self.assert_actual_completion(annotation,raws,plan)
        self.assertEqual([r['operation']['action_type'] for r in raws],['click','complete'])
        self.assertEqual([r['planned_operation_index'] for r in raws],[0,1])
        self.assertEqual(raws[-1]['completion_trigger'],'goal_already_satisfied')


if __name__=='__main__':unittest.main()
