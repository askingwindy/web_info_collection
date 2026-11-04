"""Disposable structure/quote/observation regressions; no real provider or browser."""
import json,time,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import test_producer_image_screen as fixture
from site_planner import purpose_structure as structure,page_purpose_v6 as purpose,producer_observation as observed,page_consumption as images
from site_planner.discovery_tools import reference
from site_planner.pipeline import reserve_visit
from webcollect.batch_core import save_json,load_json,OutcomeUnknown
from webcollect.planning import object_sha256

class ProducerV10(unittest.TestCase):
 def setUp(self):
  self.f=fixture.ImageScreen('test_area_matches_consumer_without_semantic_exceptions');self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.pool=self.f.pool;self.ledger=self.f.ledger;self.root=self.f.f.root
 def link(self,uri=None):
  return {'uri':uri or self.f.uri,'link_id':'first','evidence_id':'source-fixed','anchor':'公开业务条目','heading':'中文栏目','reference':self.f.home['reference'],
   'application_id':'fixture','site_category':'知识文库','site_decision_id':'fixed'}
 def ev(self,html):
  raw=self.root/('struct-'+object_sha256(html)+'.html');raw.write_text(html)
  doc={'uri':self.f.uri,'raw_html':reference(raw),'encoding':'utf-8'};path=raw.with_suffix('.json');save_json(path,doc)
  ev=purpose.material({**doc,'reference':reference(path)});purpose.prepare(self.link(),ev,self.ledger.config.get('model'));return ev
 def observation(self,uri,html):
  uri=images.entry_identity(uri);payload={'uri':uri,'image_policy':images.VERSION,'document_policy':observed.VERSION,'access':'fresh_context_no_login_get_only'}
  rid,old=self.pool.pool.reserve_tool(images.SCREEN_RUN,'browser',uri,payload)
  if old:return old
  jid=self.ledger.enqueue('site-discovery-page',{**payload,'run_id':images.SCREEN_RUN});job=self.ledger.claim('site-discovery-page',job_id=jid)
  self.ledger.consume('probe_pages',jid);visit=reserve_visit(self.ledger,job,uri,'discovery-read')
  folder=self.root/rid;folder.mkdir();raw=folder/'response.bin';raw.write_bytes(html.encode());dom=folder/'dom.html';dom.write_text(html)
  png=folder/'view.png';Image.new('RGB',(100,100),'white').save(png)
  doc={'document_policy':observed.VERSION,'uri':uri,'landed_uri':uri,'raw_html':reference(raw),'rendered_dom':reference(dom),'encoding':'utf-8',
   'job_id':jid,'visit_id':visit['id'],'method':'GET','response_uri':uri,'http_status':200,'anonymous_context':True,'initial_cookies':0,'login_performed':False}
  dpath=folder/'document.json';save_json(dpath,doc);view=self.f.view(url=uri,elements=[])
  obs={'requested_uri':uri,'landed_uri':uri,'http_status':200,'navigation_error':None,'observed_at':time.time(),
   'image_view':view,'image_view_after':view,'document':reference(dpath),'document_policy':observed.VERSION,'text':html}
  opath=folder/'observation.json';save_json(opath,obs)
  result={'uri':uri,'landed_uri':uri,'http_status':200,'same_application_host':True,'job_id':jid,'visit_id':visit['id'],
   'image_policy':images.VERSION,'document_policy':observed.VERSION,'document':reference(dpath),'observation':reference(opath),'image':reference(png)}
  self.ledger.settle_visit(visit,state='succeeded',response_status=200,landed_uri=uri,metrics={});self.ledger.finish(job,result=result);self.pool.pool.settle_tool(rid,'succeeded',result)
  return result
 def provider(self,request,timeout):
  import io
  body=json.loads(request.data);ctx=json.loads(body['messages'][1]['content'][0]['text']);decisions={}
  for page in ctx['pages']:
   facts=page['structures'];first=next((key for key,f in facts.items() if f['primary_eligible']),None)
   typ={'narrative':'内容详情','collection':'检索或列表','tool':'功能页','download':'第三方介绍或下载'}[facts[first]['kind']] if first else 'UNKNOWN'
   qs=list(page['evidence'])[:2]
   decisions[page['page_key']]={'page_type':typ,'business':'public_business','select':True,'quote_ids':qs,'business_quote_ids':qs,'structure_ids':[first] if first else [],'reason':'本页原件主区证据'}
  raw=deepcopy(self.f.b.f.f.provider.opener.raw)
  raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[{'id':'v10','type':'function','function':{'name':'submit_page_assessments','arguments':json.dumps({'decisions':decisions})}}]}}]
  return io.BytesIO(json.dumps(raw).encode())
 def test_div_cards_with_heading_anchors_are_a_collection(self):
  ev=self.ev('<main><h1>文章栏目</h1>'+''.join('<div class="card"><h3><a href="/p'+str(i)+'">条目'+str(i)+'</a></h3><p>条目说明</p></div>' for i in range(4))+'</main>')
  groups=[k for k,v in ev['structures'].items() if v['kind']=='collection'];self.assertTrue(groups)
  title=next(k for k,u in ev['menu'].items() if u['tag']=='h1')
  self.assertEqual(structure.accepts('检索或列表',[title],[groups[0]],ev),(True,None))
 def test_direct_anchor_directory_is_supported(self):
  ev=self.ev('<div class="catalog"><h1>课程目录</h1>'+''.join('<a href="/lesson'+str(i)+'">课程'+str(i)+'</a>' for i in range(4))+'</div>')
  self.assertTrue(purpose.supports('检索或列表',ev['units']))
 def test_inline_article_references_are_not_a_collection(self):
  ev=self.ev('<main><h1>完整教程</h1>'+''.join('<p>'+('本文详细说明具体原理。'*15)+'<a href="/ref'+str(i)+'">引用'+str(i)+'</a></p>' for i in range(4))+'</main>')
  self.assertTrue(purpose.supports('内容详情',ev['units']));self.assertFalse(purpose.supports('检索或列表',ev['units']))
 def test_article_related_cards_do_not_override_narrative(self):
  ev=self.ev('<main><h1>单篇文章</h1><p>'+('本文正文。'*180)+'</p>'+''.join('<div><a href="/ref'+str(i)+'">相关条目'+str(i)+'</a></div>' for i in range(3))+'</main>')
  self.assertFalse(purpose.supports('检索或列表',ev['units']))
 def test_api_document_global_search_does_not_prove_tool(self):
  ev=self.ev('<main><h1>地理编码 API 文档</h1><input name="search" placeholder="搜索"><button>搜索</button><p>'+('接口参数和返回结果说明。'*20)+'</p></main>')
  self.assertFalse(purpose.supports('功能页',ev['units']));self.assertTrue(purpose.supports('内容详情',ev['units']))
 def test_named_calculator_form_is_a_tool(self):
  ev=self.ev('<main><h1>面积计算器</h1><form><label>长度<input name="length"></label><label>宽度<input name="width"></label><button>计算</button><output>结果</output></form></main>')
  self.assertTrue(purpose.supports('功能页',ev['units']))
 def test_tool_explanation_length_alone_does_not_remove_real_inputs(self):
  ev=self.ev('<html><title>面积计算器</title><main><h1>面积计算器</h1><input name="length"><input name="width"><button>计算</button>'+''.join('<p>'+('计算步骤说明。'*60)+'</p>' for _ in range(4))+'</main></html>')
  self.assertTrue(purpose.supports('功能页',ev['units']))
 def test_nested_layout_keeps_main_scope_and_excludes_chrome(self):
  ev=self.ev('<nav><a href="/private">登录</a></nav><main><div class="content"><h1>正文</h1><div class="article-body"><p>'+('独立正文。'*40)+'</p></div></div></main><footer><input name="ad"></footer>')
  self.assertEqual(len({u['region'] for u in ev['units']}),1);self.assertFalse(any(u['kind']=='control' for u in ev['units']))
 def test_wrong_page_quote_or_structure_never_passes(self):
  ev=self.ev('<main><h1>正文</h1><p>'+('完整正文。'*30)+'</p></main>');q=next(iter(ev['menu']));s=next(iter(ev['structures']))
  self.assertFalse(structure.accepts('内容详情',['other-u0'],[s],ev)[0]);self.assertFalse(structure.accepts('内容详情',[q],['other-g0'],ev)[0])
 def test_same_observation_supplies_dom_and_publication_without_get(self):
  link=self.link();result=self.observation(link['uri'],'<main><h1>文章</h1><p>'+('完整业务正文。'*30)+'</p></main>')
  with patch.object(purpose,'homepage_document',side_effect=AssertionError('no second target GET')):
   ev=purpose.evidence_for(self.pool,self.ledger,link,self.root)
  self.assertEqual(ev['observation'],result['observation']);self.assertEqual(ev['material_source'],'shared_anonymous_rendered_dom')
  access,ref=observed.entry_receipt(self.pool,self.ledger,link['uri'],self.root)
  self.assertTrue(access['reused_original_browser_GET']);self.assertEqual(access['job_id'],result['job_id'])
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)
 def test_corrupt_document_or_job_proof_does_not_fall_back_to_new_get(self):
  link=self.link();result=self.observation(link['uri'],'<main><p>正文</p></main>');Path(result['document']['path']).write_text('{}')
  with patch.object(purpose,'homepage_document',side_effect=AssertionError('no replacement request')):
   with self.assertRaises(ValueError):purpose.evidence_for(self.pool,self.ledger,link,self.root)
 def test_cached_screen_does_not_start_chrome(self):
  link=self.link();self.observation(link['uri'],'<main><p>正文</p></main>')
  with patch('site_planner.producer_observation.DiscoveryBrowser.__aenter__',side_effect=AssertionError('no browser for cache')):
   admitted,records=observed.screen(self.pool,self.ledger,[link],self.root)
  self.assertEqual(admitted,[link]);self.assertTrue(records[0]['reused'])
 def test_formal_v10_uses_one_get_and_same_batch_replay_zero_dispatch(self):
  home=self.f.home;provider=self.f.b.f.f.provider.opener
  def screen(pool,ledger,links,root):
   for link in links:self.observation(link['uri'],'<main><h1>文章正文</h1><p>'+('具体业务完整正文。'*30)+'</p></main>')
   return images.screen(pool,ledger,links,root)
  sources=[{**home,'context_only':True,'excluded_entry_identities':['https://tools.example.org/already-seen']}]
  with patch.object(observed,'screen',side_effect=screen),patch.object(purpose,'homepage_document',side_effect=AssertionError('no target GET')),patch('site_planner.candidate_discovery.check_entry',side_effect=AssertionError('no publication GET')),patch('site_planner.entry_access.check_entry',side_effect=AssertionError('no historical landing GET')),patch.object(provider,'open',side_effect=self.provider):
   report=self.f.b.f.run_new(home,key='v10',target=1,sources=sources,model_protocol='entry-tools-10',batch_size=1)
   replay=self.f.b.f.run_new(home,key='v10',target=1,sources=sources,model_protocol='entry-tools-10',batch_size=1)
  self.assertEqual(report['listed_unique_candidates'],1,report);self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)
  row=self.pool.rows(protocols=('webcollect-data-candidate-2',))[0]
  self.assertEqual(set(row['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
  self.assertEqual(load_json(row['sources'][0]['entry_http']['path'])['policy'],'producer-entry-observed-get-2')
 def test_exact_purpose_cache_reuses_paid_reply_in_different_chunk(self):
  link=self.link();self.observation(link['uri'],'<main><h1>文章正文</h1><p>'+('具体业务完整正文。'*30)+'</p></main>')
  provider=self.f.b.f.f.provider.opener
  with patch.object(provider,'open',side_effect=self.provider):first,receipt=purpose.classify(self.ledger,[link],'first',self.root,pool=self.pool)
  with patch.object(provider,'open',side_effect=AssertionError('no repeated model')):second,reused=purpose.classify(self.ledger,[{**link,'link_id':'second'}],'second',self.root,pool=self.pool)
  self.assertEqual(second[0]['link_id'],'second');self.assertEqual(reused['calls'],[]);self.assertTrue(reused['records'][0]['model_calls'][0]['reused'])

 def test_shared_batch_opens_one_browser_and_keeps_page_contexts_fresh(self):
  owner=self;events=[]
  class Browser:
   def __init__(self,*a,**kw):events.append(('create',kw));self.closed=False
   async def __aenter__(self):events.append(('enter',));return self
   async def read(self,uri):events.append(('read',uri));return owner.observation(uri,'<main><p>原始正文</p></main>')
   async def __aexit__(self,*a):events.append(('exit',))
  links=[self.link(),self.link('https://tools.example.org/second')]
  with patch.dict(self.ledger.config,{'mode':'real'}),patch.object(observed,'DiscoveryBrowser',Browser):
   admitted,records=observed.screen(self.pool,self.ledger,links,self.root)
  self.assertEqual(len(admitted),2);self.assertEqual([e[0] for e in events],['create','enter','read','read','exit'])
  self.assertTrue(events[0][1]['fresh_pages']);self.assertTrue(events[0][1]['capture_document'])

 def test_browser_capture_keeps_response_and_dom_in_one_original_visit(self):
  import asyncio
  from site_planner.discovery_tools import DiscoveryBrowser
  owner=self;contexts=[];uri=self.f.uri
  class Response:
   status=200;headers={'content-type':'text/html; charset=utf-8'}
   request=type('Request',(),{'method':'GET'})();url=uri
   async def body(self):return b'<html><body>Original response</body></html>'
  class Page:
   url=uri
   async def route(self,*a):pass
   async def goto(self,url,**kw):
    self.url=url;response=Response();response.url=url;return response
   def locator(self,*a):return self
   async def wait_for(self,**kw):pass
   async def wait_for_timeout(self,*a):pass
   async def evaluate(self,script):
    if script=='document.characterSet':return 'UTF-8'
    if 'const width=innerWidth' in script:return owner.f.view(url=self.url,elements=[])
    return {'title':'正文','landed_uri':self.url,'text':'完整正文','links':[],'controls':[]}
   async def screenshot(self,path,**kw):Image.new('RGB',(100,100),'white').save(path)
   async def content(self):return '<main><h1>渲染正文</h1><p>'+('浏览器已渲染内容。'*20)+'</p></main>'
   async def close(self):pass
  class Context:
   async def new_page(self):return Page()
   async def close(self):self.closed=True
  class Engine:
   async def new_context(self,**kw):c=Context();c.closed=False;contexts.append(c);return c
  browser=DiscoveryBrowser(self.pool.pool,self.ledger,images.SCREEN_RUN,self.root,image_screen=True,capture_document=True,fresh_pages=True);browser.browser=Engine()
  async def run():
   result=await browser.read(uri)
   await browser.read('https://tools.example.org/other-capture')
   return result
  with patch('site_planner.discovery_tools.verify_public_url',return_value=None):result=asyncio.run(run())
  self.assertEqual(len(contexts),2);self.assertTrue(all(c.closed for c in contexts))
  doc,stored=observed.from_pool(self.pool,self.ledger,uri)
  self.assertEqual(Path(doc['raw_html']['path']).read_bytes(),b'<html><body>Original response</body></html>')
  self.assertIn('渲染正文',Path(doc['rendered_dom']['path']).read_text());self.assertEqual(stored,result)
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],2)

if __name__=='__main__':unittest.main()
