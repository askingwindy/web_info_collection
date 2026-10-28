"""Independent local native-navigation cache contracts, never delivery samples."""
import json
from pathlib import Path
import tempfile
import unittest

from playwright.async_api import async_playwright
from webcollect.collect import collect_one
from webcollect.evidence import audit_capture

URL='https://preparation-document-cache.invalid/page'
PROSE=('这是一段独立手写的正文，用于确认页面重新载入后仍需核对当前内容是否真实可读。'
       '采集器应保存实际首帧、重新载入动作和新正文的阅读过程，而不能沿用先前文档的就绪状态直接跳过准备。'
       '每次结论都必须有当时截图和真实可见文字作为依据。')
STYLE='''<style>body{margin:0;font:20px/1.6 sans-serif}article{padding:24px;width:850px;box-sizing:border-box}
    #reload,#jump,#confirm,#result{position:fixed;right:20px;background:white;z-index:2}
    #reload,#jump{top:20px}#confirm{bottom:70px}#result{bottom:10px}</style>'''
CONFIRM='''<button id="confirm" onclick="document.querySelector('#result').textContent='确认完成'">确认阅读内容</button>
    <p id="result">等待确认</p>'''


def reload_case(banner_height):
    first='<title>第一份公开正文</title>'+STYLE+'<article><h1>第一份公开正文</h1><p>'+PROSE+'</p></article>'\
          '<button id="reload" onclick="location.reload()">重新载入</button>'
    second='<title>第二份公开正文</title>'+STYLE+f'<div style="height:{banner_height}px">新页面顶部横幅，正文位于下方。</div>'\
           '<article><h1>第二份公开正文</h1><p>'+PROSE+'</p></article>'+CONFIRM
    reload={'action_type':'click','selector':'#reload','arguments':{},'goal':'重新载入同地址的新文档',
            'rationale':'继续核对新的公开正文','expected':'第二份正文出现',
            'execution':{'wait_navigation':True,'settle_ms':100}}
    return [first,second],reload


class PreparationDocumentCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1)
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()
        self.temp.cleanup()

    async def collect_documents(self,documents,first_operation):
        self.document_loads=0
        async def route(route):
            source=documents[min(self.document_loads,len(documents)-1)]
            self.document_loads+=1
            await route.fulfill(content_type='text/html; charset=utf-8',body='<meta charset="utf-8">'+source)
        await self.context.route('https://preparation-document-cache.invalid/**',route)
        confirm={'action_type':'click','selector':'#confirm','arguments':{},'goal':'确认已经阅读正文',
                 'rationale':'依据实际可见内容确认','expected':'确认完成','execution':{'settle_ms':50}}
        task={'task_id':'document-cache-contract','app_name':'本地文档身份测试','initial_url':URL,
              'initial_settle_ms':0,'stop_when_final':False,'content_preparation':{'mode':'article'},
              'instruction':'这是本地原生导航契约测试，不可作为真实交付样本。','task_type':['数据查看'],
              'operations':[first_operation,confirm],'final_assertions':[{'visible_text':'确认完成'}],
              'final_result':'确认完成','completion_judgement':'实际末态控件显示确认完成'}
        sid='S000001_sample_000001'
        sample=self.root/'samples'/sid
        evidence=self.root/'evidence'/sid
        annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':sid})
        ledger=json.loads((evidence/'preparation_decisions.json').read_text())['decisions']
        raws=[json.loads((evidence/f'step_{index:03}.json').read_text())
              for index in range(1,len(annotation['steps'])+1)]
        self.assertTrue(audit_capture(self.root,sid)['capture_evidence_pass'])
        return annotation,ledger,raws

    async def test_native_reload_same_url_new_document_earns_readiness_again(self):
        # The new document begins below the fold, but its heading becomes
        # painted after the first necessary preparation scroll. Each resulting
        # frame must have real visible evidence for its narrative.
        documents,reload=reload_case(760)
        annotation,ledger,raws=await self.collect_documents(documents,reload)
        self.assertEqual(self.document_loads,2)
        self.assertTrue(ledger[0]['assessment']['body']['visible'])
        self.assertEqual(raws[0]['state']['title'],'第一份公开正文')
        self.assertEqual(raws[1]['state']['title'],'第二份公开正文')
        self.assertEqual(raws[1]['state']['scroll'],[0,0])
        first_identity=ledger[0]['assessment']['document_identity']
        new_identity=ledger[1]['assessment']['document_identity']
        self.assertEqual(first_identity['url_without_fragment'],new_identity['url_without_fragment'])
        self.assertNotEqual(first_identity['performance_time_origin'],new_identity['performance_time_origin'])
        self.assertFalse(ledger[1]['assessment']['next_target']['preserve_reading_position'])
        self.assertFalse(ledger[1]['assessment']['body']['visible'])
        self.assertEqual(ledger[1]['assessment']['decision']['action'],'scroll_to_content')
        preparation=[item for item in raws if item['operation_origin']=='preparation']
        self.assertGreater(len(preparation),0)
        self.assertTrue(all(item['operation']['action_type']=='scroll' for item in preparation))
        confirm_frame=next(item for item in raws if item['operation_origin']=='planned' and item['planned_operation_index']==1)
        self.assertGreater(confirm_frame['state']['scroll'][1],0)
        self.assertIn('采集器应保存实际首帧',confirm_frame['state']['visible_text'])
        self.assertEqual(annotation['steps'][-1]['action']['action_type'],'complete')

    async def test_native_reload_with_blank_intermediate_viewport_fails_closed(self):
        # Retain the original 1000px spacer: its first 240px preparation scroll
        # leaves only unchanged confirmation controls and no visible prose.
        documents,reload=reload_case(1000)
        with self.assertRaisesRegex(ValueError,'NARRATIVE_VISIBLE_EVIDENCE_MISSING'):
            await self.collect_documents(documents,reload)
        sid='S000001_sample_000001'
        evidence=self.root/'evidence'/sid
        failure=json.loads((evidence/'failure_after.json').read_text())
        self.assertEqual(failure['state']['scroll'],[0,240])
        self.assertEqual(failure['state']['visible_text'],'确认阅读内容\n等待确认')
        self.assertNotIn('第二份公开正文',failure['state']['visible_text'])
        self.assertFalse((self.root/'samples'/sid/'annotation.json').exists())
        self.assertTrue((self.root/'samples'/sid/'images'/'step_003.png').exists())

    async def test_native_fragment_keeps_same_document_reading_position(self):
        document='<title>同份公开正文</title>'+STYLE+'<article><h1>同份公开正文</h1><p>'+PROSE+'</p></article>'\
                 '<a id="jump" href="#later">前往阅读末尾</a><div style="height:1400px">正文后的连续阅读区域</div>'\
                 '<p id="later">这里是同一文档的阅读末尾，确认已经阅读。</p>'+CONFIRM
        jump={'action_type':'click','selector':'#jump','arguments':{},'goal':'前往同文档阅读末尾',
              'rationale':'原生锚点继续阅读同页内容','expected':'阅读末尾出现','execution':{'settle_ms':100}}
        annotation,ledger,raws=await self.collect_documents([document],jump)
        self.assertEqual(self.document_loads,1)
        self.assertEqual([item['action']['action_type'] for item in annotation['steps']],['click','click','complete'])
        self.assertEqual(ledger[0]['assessment']['document_identity'],ledger[1]['assessment']['document_identity'])
        self.assertTrue(raws[1]['state']['url'].endswith('#later'))
        self.assertGreater(raws[1]['state']['scroll'][1],0)
        self.assertFalse(ledger[1]['assessment']['body']['visible'])
        self.assertTrue(ledger[1]['assessment']['next_target']['preserve_reading_position'])
        self.assertEqual(ledger[1]['assessment']['decision']['action'],'not_applicable')
        self.assertTrue(all(item['operation_origin']=='planned' for item in raws))


if __name__=='__main__':unittest.main()
