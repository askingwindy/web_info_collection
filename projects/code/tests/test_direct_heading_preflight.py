"""Bounded pseudo paint and direct-article planning, real local Chromium only."""
from pathlib import Path
from copy import deepcopy
import io,unittest
from PIL import Image
from playwright.async_api import async_playwright
from webcollect.direct_article import VERSION,initial,planning_pair

SNAPSHOT=(Path(__file__).resolve().parents[1]/'webcollect/snapshot.js').read_text()
TITLE='受控气象文章'
BASE='''<style>body{margin:0;font:18px/28px Arial;color:#202122;background:white}main{position:absolute;left:260px;top:140px;width:740px}header{position:relative}h1{margin:0;font:28px/40px Arial}header::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:#a2a9b1}p{line-height:28px}</style>'''
HTML='<main><header><h1><span><span>'+TITLE+'</span></span><span>[<a href="?edit=1">编辑</a>]</span></h1></header><p>这是一段本地可见正文，实际内容通过原生截图树记录，不能由隐藏文本或旁栏内容代替。</p></main>'

class DirectHeadingPreflight(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':1280,'height':720});await self.page.route('**/*',lambda route:route.abort())
    async def asyncTearDown(self):await self.browser.close();await self.p.stop()
    async def snapshot(self,extra='',html=HTML):
        await self.page.set_content('<!doctype html><meta charset="utf-8"><title>'+TITLE+'</title>'+BASE+extra+html)
        before=await self.page.content();s=await self.page.evaluate(SNAPSHOT,{});self.assertEqual(await self.page.content(),before)
        return s
    def task(self,state):
        contract={'version':VERSION,'kind':'reading','entry_url':state['url'],'titles':[TITLE]}
        return {'initial_url':state['url'],'fragment':{'plan_protocol':'webcollect-banded-conditional-plan-8','session_objective':{'objective':{'evidence_contract':contract}}}},contract
    async def test_nested_visible_heading_and_disjoint_separator_keep_full_text_and_title_witness(self):
        s=await self.snapshot();h=next(e for e in s['elements'] if e['native_role']=='h1');self.assertIn(TITLE,h['text']);self.assertIn('编辑',h['text'])
        self.assertTrue(s['disjoint_pseudo_paint_proofs']);task,c=self.task(s);identity=initial(task,s,c)
        self.assertEqual(identity['heading'],TITLE);self.assertNotEqual(identity['heading_node'],identity['heading_label_node'])
        for extra in ('<style>h1>span:first-child{visibility:hidden}</style>', '<style>h1>span:first-child{opacity:0}</style>'):
            bad=await self.snapshot(extra)
            with self.assertRaises(ValueError):initial(task,bad,c)
    async def test_actual_top_middle_cover_and_unknown_pseudo_geometry_remain_rejected(self):
        for rule in ('top:0;bottom:auto;height:40px','top:15px;bottom:auto;height:15px','position:relative;height:30px','transform:translateY(-20px)','filter:blur(1px)','box-shadow:0 -20px 0 white'):
            s=await self.snapshot('<style>header::after{'+rule+'}</style>')
            self.assertNotIn(TITLE,s['visible_text'],rule)
    async def test_sticky_tail_bound_and_real_top_middle_occlusion(self):
        nav='''<aside id="scroller"><nav><a href="#part">目录章节定位</a><p>上部目录文字</p><p>中段目录文字</p></nav></aside>'''
        style='''<style>#scroller{position:fixed;left:20px;top:40px;width:200px;height:180px;overflow:auto}#scroller nav{display:block;margin:0;height:150px}#scroller p{margin:8px 0}#scroller::after{content:"";position:sticky;display:block;left:0;right:0;top:auto;bottom:0;height:16px;background:linear-gradient(transparent,white);pointer-events:none}</style>'''
        s=await self.snapshot(style,HTML+nav);self.assertIn('目录章节定位',s['visible_text']);self.assertIn('中段目录文字',s['visible_text'])
        self.assertTrue(any(p['kind']=='bottom-sticky-final-empty-block-envelope' for p in s['disjoint_pseudo_paint_proofs']))
        s=await self.snapshot(style+'<style>#scroller{height:100px}#scroller::after{height:100px;background:white}</style>',HTML+nav)
        self.assertNotIn('上部目录文字',s['visible_text']);self.assertNotIn('中段目录文字',s['visible_text'])
        for rule in ('padding-top:2px','border:1px solid black'):
            s=await self.snapshot(style+'<style>#scroller{'+rule+'}</style>',HTML+nav);self.assertNotIn('目录章节定位',s['visible_text'])
        for rule in ('margin-bottom:-10px','transform:translateY(10px)','scale:1.1'):
            s=await self.snapshot(style+'<style>#scroller nav{'+rule+'}</style>',HTML+nav);self.assertNotIn('目录章节定位',s['visible_text'])
        with self.assertRaisesRegex(Exception,'UNSUPPORTED_GEOMETRY'):
            await self.snapshot(style+'<style>#scroller nav{rotate:2deg}</style>',HTML+nav)
    async def test_planning_pair_preserves_body_and_directory_and_never_grants_dispatch(self):
        s=await self.snapshot('<nav style="position:fixed;left:20px;top:140px"><a href="#part">章节目录</a></nav>');task,c=self.task(s)
        # about:blank is sufficient for state-level checks; public URL is bound
        # explicitly for the same-page fragment projection.
        s['url']='https://example.org/wiki/Article';task['initial_url']=s['url'];c['entry_url']=s['url']
        for b in s['capture_controls']:
            if b.get('href','') and '#part' in b['href']:b['href']=s['url']+'#part'
        def png(point=None):
            im=Image.new('RGB',(1280,720),'white')
            if point:im.putpixel(point,(0,0,0))
            out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()
        good=planning_pair(task,s,deepcopy(s),png(),png((20,20)));self.assertTrue(good['accepted'],good);self.assertFalse(good['dispatch_permission'])
        for point in ((300,160),(30,150)):
            self.assertFalse(planning_pair(task,s,deepcopy(s),png(),png(point))['accepted'])
        for mode in ('title','body','directory'):
            after=deepcopy(s)
            if mode=='title':after['title']='wrong'
            elif mode=='body':next(e for e in after['elements'] if e['native_role']=='p')['text']='正文实际改变'
            else:next(e for e in after['elements'] if e.get('text')=='章节目录')['bbox'][0]+=2
            self.assertFalse(planning_pair(task,s,after,png(),png())['accepted'],mode)
