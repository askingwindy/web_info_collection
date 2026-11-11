"""Disposable producer-image gates; never launches a browser or provider."""
from copy import deepcopy
from pathlib import Path
import json,unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import test_producer_business_v7 as business
from site_planner import page_consumption as policy,page_purpose_v5 as purpose
from site_planner.candidate_pool import CandidatePool,VERSION2,entry_identity
from site_planner.discovery_tools import reference
from site_planner.pipeline import reserve_visit
from site_planner.candidate_discovery import _publish_entry
from webcollect.batch_core import save_json,load_json,OutcomeUnknown
from webcollect.planning import object_sha256

class ImageScreen(unittest.TestCase):
 def setUp(self):
  self.b=business.Business('test_formal_business_selection_filters_legal_and_restart_zero_io');self.b.setUp();self.addCleanup(self.b.doCleanups)
  self.f=self.b.f;self.pool=self.f.pool;self.ledger=self.b.ledger;_,self.home=self.f.site(html='<main><a href="/poster">公开海报</a><a href="/article">正文条目</a></main>')
  self.uri='https://tools.example.org/poster';self.source={'origin':'codex_session','run_id':'fixture','references':[self.home['reference']]}
 def view(self,**updates):
  return {'schema_version':policy.OBSERVATION_VERSION,'url':self.uri,'title':'静态图片','screen_resolution':[100,100],
   'elements':[{'element_type':'image','visible':True,'bbox':[0,0,100,100]}],
   'inventory_complete':True,'reading_text':'','business_controls':[],'image_labels':[''],**updates}
 def result(self,uri=None,view=None,*,landed=None,after=None,status=200,version=None):
  uri=uri or self.uri;landed=landed or uri;view=view or self.view(url=landed)
  version=version or policy.VERSION
  jid=self.ledger.enqueue('site-discovery-page',{'uri':entry_identity(uri),'run_id':policy.SCREEN_RUN,'image_policy':version})
  old=self.ledger.get(jid)
  if old['state']=='done':return old['result']
  job=self.ledger.claim('site-discovery-page',job_id=jid);self.ledger.consume('probe_pages',jid);visit=reserve_visit(self.ledger,job,entry_identity(uri),'discovery-read')
  obs={'requested_uri':uri,'landed_uri':landed,'http_status':status,'navigation_error':None,'image_view':view,'image_view_after':after if after is not None else deepcopy(view)}
  path=self.f.root/(jid+'-observation.json');save_json(path,obs);png=path.with_suffix('.png');Image.new('RGB',tuple(view['screen_resolution']),'white').save(png)
  result={'uri':entry_identity(uri),'landed_uri':landed,'http_status':status,'same_application_host':True,'job_id':jid,'visit_id':visit['id'],'image_policy':version,'observation':reference(path),'image':reference(png)}
  self.ledger.settle_visit(visit,state='succeeded',response_status=status,landed_uri=landed,metrics={});self.ledger.finish(job,result=result);return result
 def entry(self,uri=None):return {'schema_version':VERSION2,'candidate_kind':'entry','entry_url':uri or self.uri,'requested_goal':None}
 def test_area_matches_consumer_without_semantic_exceptions(self):
  from webcollect.consumer_page_policy import full_image
  self.assertEqual(policy.assess(self.view())['status'],'NO_CONSUME')
  for changes in [dict(title='正在加载中'),dict(reading_text='有价值的正文内容。'*20),dict(business_controls=['CANVAS']),dict(title='地图查询'),dict(title='图表仪表盘'),dict(title='图片裁剪工具'),dict(image_labels=['这幅统计图说明多个年份的经济指标趋势'])]:
   with self.subTest(changes=changes):self.assertEqual(policy.assess(self.view(**changes))['status'],'NO_CONSUME')
  self.assertEqual(policy.assess(self.view(inventory_complete=False))['status'],'UNKNOWN')
  for width in (94,94.999,95,95.001,100):
   state=self.view(elements=[{'element_type':'image','visible':True,'bbox':[0,0,width,100]}])
   self.assertEqual(policy.assess(state)['status']=='NO_CONSUME',bool(full_image(state)))
  for boxes in [[0,0,94,100],[0,110,100,210]]:
   self.assertEqual(policy.assess(self.view(elements=[{'element_type':'image','visible':True,'bbox':boxes}]))['status'],'UNKNOWN')
  self.assertEqual(policy.assess(self.view(elements=[{'element_type':'image','visible':True,'bbox':[0,0,50,100]}]*3))['status'],'UNKNOWN')
 def test_pending_entry_blocked_without_rewriting_original_or_claim(self):
  cid=self.pool.put(self.entry(),self.source);before=self.pool.rows(protocols=(VERSION2,))[0]
  target={**self.entry(),'candidate_kind':'target','requested_goal':{'kind':'visual_compare','entity':'已指定目标','parameters':{'specific':True}}}
  target_id=self.pool.put(target,self.source)
  record=policy.register(self.pool,self.ledger,self.result());row=self.pool.rows(protocols=(VERSION2,))[0]
  self.assertFalse(row['consumption']['needs_consumption']);self.assertEqual(row['consumption']['label'],'无需消费')
  for key in ('candidate','version','state','sources'):self.assertEqual(row[key],before[key])
  self.assertEqual(self.pool.claim_next('w','no-consume',candidate_id=cid,protocols=(VERSION2,))['state'],'EMPTY')
  with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_claims').fetchone()[0],0)
  with self.assertRaisesRegex(ValueError,'NO_CONSUME'):self.pool.put(self.entry(self.uri+'?utm_source=again'),self.source)
  other=self.pool.put(self.entry('https://tools.example.org/other'),self.source)
  self.assertEqual(self.pool.claim_next('w','other',candidate_id=other,protocols=(VERSION2,))['state'],'consuming')
  self.assertEqual(self.pool.claim_next('w','specific',candidate_id=target_id,protocols=(VERSION2,))['state'],'EMPTY')
  with self.assertRaisesRegex(ValueError,'NO_CONSUME'):self.pool.put(target,self.source)
 def test_atomic_mark_is_shared_and_idempotent(self):
  result=self.result()
  def record(_):return policy.register(CandidatePool(self.pool.path),self.ledger,result)
  with ThreadPoolExecutor(2) as workers:a,b=list(workers.map(record,[1,2]))
  self.assertEqual(a,b);restarted=CandidatePool(self.pool.path,readonly=True);self.assertEqual(restarted.consumption(self.uri),a)
  with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM checkpoints WHERE run_id=?',(policy.RUN,)).fetchone()[0],1)
 def test_binding_instability_and_missing_proof_do_not_mark(self):
  result=self.result(after=self.view(reading_text='布局改变'))
  self.assertEqual(policy.register(self.pool,self.ledger,result)['status'],'UNKNOWN');self.assertIsNone(self.pool.consumption(self.uri))
  with self.assertRaises(ValueError):policy.register(self.pool,self.ledger,{**result,'uri':'https://tools.example.org/wrong'})
  with self.assertRaises(ValueError):policy.register(self.pool,self.ledger,{**result,'image_policy':'unsupported'})
 def test_changed_image_is_rejected_before_claim(self):
  result=self.result();policy.register(self.pool,self.ledger,result)
  Image.new('RGB',(100,100),'red').save(result['image']['path'])
  with self.assertRaises(ValueError):self.pool.consumption(self.uri)
 def test_http_failure_is_not_no_consume(self):
  with self.assertRaises(ValueError):policy.register(self.pool,self.ledger,self.result(status=403))
  self.assertIsNone(self.pool.consumption(self.uri))

 def test_original_http_404_holds_only_that_page_and_next_page_continues(self):
  result=self.result(status=404)
  rid,_=self.pool.pool.reserve_tool(policy.SCREEN_RUN,'browser',entry_identity(self.uri),{'uri':entry_identity(self.uri),'image_policy':policy.VERSION})
  self.pool.pool.settle_tool(rid,'succeeded',result)
  article='https://tools.example.org/article';probes=[]
  async def probe(pool,ledger,uri,root):
   probes.append(uri)
   return self.result(uri,view=self.view(url=uri,elements=[]))
  with patch.object(policy,'_probe',side_effect=probe):
   admitted,records=policy.screen(self.pool,self.ledger,[{'uri':self.uri},{'uri':article}],self.f.root)
  self.assertEqual(admitted,[{'uri':article}]);self.assertEqual(probes,[article])
  self.assertEqual(records[0]['decision']['status'],'HELD');self.assertEqual(records[0]['decision']['http_status'],404)
  self.assertIsNone(self.pool.consumption(self.uri));self.assertEqual(self.ledger.get(result['job_id'])['result'],result)
  with patch.object(policy,'_probe',side_effect=AssertionError('no 404 retry')):
   self.assertEqual(policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)[0],[])

 def test_screen_does_not_swallow_original_evidence_corruption(self):
  result=self.result(status=404)
  rid,_=self.pool.pool.reserve_tool(policy.SCREEN_RUN,'browser',entry_identity(self.uri),{'uri':entry_identity(self.uri),'image_policy':policy.VERSION})
  self.pool.pool.settle_tool(rid,'succeeded',result)
  Path(result['observation']['path']).write_text('{}')
  with self.assertRaises(ValueError):policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)

 def test_recorded_browser_library_failure_holds_page_and_does_not_retry(self):
  from playwright.async_api import TimeoutError as BrowserTimeout
  probes=[];article='https://tools.example.org/article'
  async def probe(pool,ledger,uri,root):
   probes.append(uri)
   if uri==self.uri:
    rid,_=self.pool.pool.reserve_tool(policy.SCREEN_RUN,'browser',entry_identity(uri),{'uri':entry_identity(uri),'image_policy':policy.VERSION})
    self.pool.pool.settle_tool(rid,'failed',{'error_type':'TimeoutError','phase':'screenshot'})
    raise BrowserTimeout('controlled screenshot font timeout')
   return self.result(uri,view=self.view(url=uri,elements=[]))
  with patch.object(policy,'_probe',side_effect=probe):
   admitted,records=policy.screen(self.pool,self.ledger,[{'uri':self.uri},{'uri':article}],self.f.root)
  self.assertEqual(admitted,[{'uri':article}]);self.assertEqual(records[0]['decision']['reason'],'original_image_probe_failed')
  self.assertEqual(records[0]['decision']['original_state'],'failed');self.assertEqual(probes,[self.uri,article])
  with patch.object(policy,'_probe',side_effect=AssertionError('no repeat screenshot')):
   self.assertEqual(policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)[0],[])
  with patch.object(policy,'_probe',side_effect=BrowserTimeout('unrecorded host failure')):
   with self.assertRaises(BrowserTimeout):policy.screen(self.pool,self.ledger,[{'uri':'https://tools.example.org/unrecorded'}],self.f.root)
 def test_redirect_aliases_share_flag_but_business_queries_do_not(self):
  landed='https://tools.example.org/image-view';result=self.result(landed=landed)
  policy.register(self.pool,self.ledger,result)
  self.assertIsNotNone(self.pool.consumption(landed));self.assertIsNone(self.pool.consumption(landed+'?mode=edit'))
 def test_old_probe_failure_is_retained_without_browser_retry(self):
  rid,_=self.pool.pool.reserve_tool(policy.SCREEN_RUN,'browser',entry_identity(self.uri),{'uri':entry_identity(self.uri),'image_policy':policy.LEGACY_VERSION})
  self.pool.pool.settle_tool(rid,'unknown',{'original':'UNKNOWN'})
  with patch.object(policy,'_probe',side_effect=AssertionError('no resend')):
   admitted,records=policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)
   self.assertEqual(admitted,[]);self.assertEqual(records[0]['decision']['status'],'HELD')
  with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT state FROM tool_requests WHERE id=?',(rid,)).fetchone()[0],'unknown')

 def test_original_successful_probe_is_reassessed_without_new_visit(self):
  result=self.result(view=self.view(schema_version=policy.LEGACY_VERSION,title='地图查询',business_controls=['CANVAS']),version=policy.LEGACY_VERSION)
  rid,_=self.pool.pool.reserve_tool(policy.SCREEN_RUN,'browser',entry_identity(self.uri),{'uri':entry_identity(self.uri),'image_policy':policy.LEGACY_VERSION})
  self.pool.pool.settle_tool(rid,'succeeded',result)
  with patch.object(policy,'_probe',side_effect=AssertionError('no replacement visit')):
   admitted,records=policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)
  self.assertEqual(admitted,[]);self.assertTrue(records[0]['reused'])
  self.assertEqual(records[0]['decision']['policy'],policy.VERSION)
  self.assertEqual(self.ledger.get(result['job_id'])['result'],result)
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)

 def test_legacy_entry_only_mark_is_read_without_rewriting_or_scope_expansion(self):
  result=self.result()
  legacy={**policy.assess(self.view()),'policy':policy.LEGACY_VERSION,'scope':'entry_without_requested_goal',
   'uri':self.uri,'entry_identities':[entry_identity(self.uri)],'references':[result['observation'],result['image']],
   'job_id':result['job_id'],'visit_id':result['visit_id']}
  self.pool.pool.checkpoint(policy.RUN,policy.key(self.uri),legacy)
  self.assertEqual(self.pool.consumption(self.uri),legacy)
  self.assertIsNone(self.pool.consumption(self.uri,kind='target'))
  self.assertEqual(policy.register(self.pool,self.ledger,result),legacy)

 def test_publication_gate_precedes_http_and_preserves_old_row_replay(self):
  header={'row_id':'old','run_id':'fixture','batch':0,'request_id':'controlled','response_sha256':'original','raw_index':0}
  old=self.pool.publish_row(header,self.entry(),self.source)
  policy.register(self.pool,self.ledger,self.result())
  self.assertEqual(self.pool.publish_row(header,self.entry(),self.source),old)
  with patch('site_planner.candidate_discovery.check_entry',side_effect=AssertionError('no entry GET')):
   rejected=_publish_entry(self.pool,self.ledger,'fixture',self.f.root,{**header,'row_id':'new'},self.entry(),self.source,{'kind':'original'})
  self.assertEqual(rejected['result'],'REJECTED');self.assertIn('NO_CONSUME',rejected['reason'])
 def test_formal_v9_excludes_image_before_model_and_cross_batch_reuse(self):
  self.b.target_html={};self.b.inputs=[];self.b.inspect=[];self.b.plain=False;probes=[]
  async def probe(pool,ledger,uri,root):
   probes.append(uri);width=94 if uri.endswith('/article') else 100
   return self.result(uri,view=self.view(url=uri,elements=[{'element_type':'image','visible':True,'bbox':[0,0,width,100]}]))
  with patch.object(policy,'_probe',side_effect=probe),patch.object(purpose,'homepage_document',side_effect=self.b.get),patch.object(self.f.f.provider.opener,'open',side_effect=self.b.provider):
   report=self.f.run_new(self.home,key='image-v9',target=2,max_batches=1,batch_size=2,sources=[{**self.home,'context_only':True}])
   other=self.f.run_new(self.home,key='image-v9-next',target=1,max_batches=1,batch_size=2,sources=[{**self.home,'context_only':True}])
  self.assertEqual(report['listed_unique_candidates'],1,report)
  self.assertEqual(other['listed_unique_candidates'],0,other);self.assertEqual(other['new_dispatches'],{'model':0,'GET':0,'search':0})
  self.assertEqual(len(probes),2);self.assertEqual(len(self.b.inputs),1)
  self.assertNotIn(self.uri,self.b.inputs[0]['source_uris'])
  self.assertEqual(self.pool.rows(protocols=(VERSION2,))[0]['candidate']['entry_url'],'https://tools.example.org/article')

 def test_formal_v9_screens_explicit_targets_before_purpose_model(self):
  self.b.target_html={};self.b.inputs=[];self.b.inspect=[];self.b.plain=False
  goals=self.f.root/'caller-goals.json'
  uri=self.home['uri']
  save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[{'uri':uri,'requested_goal':{'kind':'visual_compare','entity':'地图','parameters':{'specific':True}}}]})
  async def probe(pool,ledger,uri,root):return self.result(uri,view=self.view(url=uri,title='地图查询'))
  with patch.object(policy,'_probe',side_effect=probe),patch.object(purpose,'homepage_document',side_effect=self.b.get),patch.object(self.f.f.provider.opener,'open',side_effect=self.b.provider):
   report=self.f.run_new(self.home,key='image-v9-targets',target=1,max_batches=1,batch_size=2,goals_path=goals)
  self.assertEqual(report['listed_unique_candidates'],0,report)
  self.assertEqual(self.b.inputs,[]);self.assertEqual(self.pool.consumption(uri)['scope'],'entry_and_target')

 def test_route_scope_and_active_claim_are_preserved(self):
  uri='https://tools.example.org/#/poster';cid=self.pool.put(self.entry(uri),self.source)
  claim=self.pool.claim_next('w','active',candidate_id=cid,protocols=(VERSION2,))
  policy.register(self.pool,self.ledger,self.result(uri,view=self.view(url=uri)))
  self.assertEqual(self.pool.get_claim(claim['claim_id']),claim)
  self.assertIsNone(self.pool.consumption('https://tools.example.org/#/editor'))
  self.assertEqual(self.pool.claim_next('w','active',candidate_id=cid,protocols=(VERSION2,)),claim)

 def test_real_sensor_javascript_offline_with_rendered_dom_mocks(self):
  import subprocess
  script=Path(policy.__file__).with_name('image_screen.js')
  harness=r"""
const fs=require('fs');const sensor=eval('('+fs.readFileSync(process.argv[1],'utf8')+')');
global.innerWidth=100;global.innerHeight=100;global.location={href:'https://tools.example.org/poster'};global.NodeFilter={SHOW_TEXT:4};
const make=(extra={})=>Object.assign({tagName:'IMG',complete:true,naturalWidth:100,alt:'',title:'',tabIndex:-1,useMap:'',parentElement:null,
 getBoundingClientRect(){return {left:0,top:0,right:100,bottom:100,width:100,height:100}},closest(){return null},getAttribute(){return null}},extra);
let img=make(),overlay=false,controls=[],texts=[];global.getComputedStyle=e=>({visibility:'visible',display:'block',opacity:e.opacity||'1',cursor:e.cursor||'default'});
global.document={images:[img],body:make(),title:'静态图片',elementFromPoint(){return overlay?make():img},querySelectorAll(){return controls},
 createTreeWalker(){let i=0;return {currentNode:null,nextNode(){if(i>=texts.length)return false;this.currentNode={parentElement:make(),textContent:texts[i++]};return true}}}};
let results=[];results.push(sensor());overlay=true;results.push(sensor());overlay=false;img.naturalWidth=0;results.push(sensor());img.naturalWidth=100;
img.cursor='pointer';results.push(sensor());img.cursor='default';controls=[make({tagName:'BUTTON'})];results.push(sensor());controls=[];texts=['有用的正文内容。'.repeat(30)];results.push(sensor());
texts=[];controls=[make({tagName:'BUTTON',parentElement:make({getBoundingClientRect(){return {width:0,height:0}}})})];results.push(sensor());controls=[make({tagName:'BUTTON',parentElement:make({opacity:'0'})})];results.push(sensor());
console.log(JSON.stringify(results));
"""
  states=json.loads(subprocess.check_output(['node','-e',harness,str(script)],text=True))
  self.assertEqual(policy.assess(states[0])['status'],'NO_CONSUME')
  for state in states[1:3]:self.assertEqual(policy.assess(state)['status'],'UNKNOWN')
  for state in states[3:]:self.assertEqual(policy.assess(state)['status'],'NO_CONSUME')

 def test_producer_browser_image_capture_is_successful_even_without_text(self):
  import asyncio
  from site_planner.discovery_tools import DiscoveryBrowser
  owner=self
  class Page:
   async def route(self,*a):pass
   async def goto(self,*a,**kw):return type('Response',(),{'status':200})()
   def locator(self,*a):return self
   async def wait_for(self,**kw):pass
   async def wait_for_timeout(self,*a):pass
   async def evaluate(self,script):
    if 'const width=innerWidth' in script:return owner.view()
    return {'title':'静态图片','landed_uri':owner.uri,'text':'','links':[],'controls':[]}
   async def screenshot(self,path,**kw):Image.new('RGB',(100,100),'white').save(path)
   async def close(self):pass
  class Context:
   async def new_page(self):return Page()
  browser=DiscoveryBrowser(self.pool.pool,self.ledger,policy.SCREEN_RUN,self.f.root,image_screen=True);browser.context=Context()
  with patch('site_planner.discovery_tools.verify_public_url',return_value=None):result=asyncio.run(browser.read(self.uri))
  self.assertFalse(result['readable']);self.assertEqual(policy.register(self.pool,self.ledger,result)['status'],'NO_CONSUME')
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM top_level_visits WHERE id=?',(result['visit_id'],)).fetchone()[0],'succeeded')
  with patch.object(policy,'_probe',side_effect=AssertionError('no repeat browser')):
   self.assertEqual(policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)[0],[])

 def test_probe_navigation_timeout_is_unknown_and_does_not_become_no_consume(self):
  import asyncio
  from site_planner.discovery_tools import DiscoveryBrowser
  class Page:
   async def route(self,*a):pass
   async def goto(self,*a,**kw):raise TimeoutError('controlled')
   async def close(self):pass
  class Context:
   async def new_page(self):return Page()
  browser=DiscoveryBrowser(self.pool.pool,self.ledger,policy.SCREEN_RUN,self.f.root,image_screen=True);browser.context=Context()
  with self.assertRaises(OutcomeUnknown):asyncio.run(browser.read(self.uri))
  with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM top_level_visits').fetchone()[0],'unknown')
  with patch.object(policy,'_probe',side_effect=AssertionError('no retry')):
   admitted,records=policy.screen(self.pool,self.ledger,[{'uri':self.uri}],self.f.root)
  self.assertEqual(admitted,[]);self.assertEqual(records[0]['decision']['status'],'HELD');self.assertIsNone(self.pool.consumption(self.uri))

 def test_cli_inspection_is_read_only_and_live_probe_needs_original_scope(self):
  import io
  from contextlib import redirect_stdout,redirect_stderr
  output=io.StringIO()
  with redirect_stdout(output):policy.main(['--pool',str(self.pool.path),'--uri',self.uri])
  self.assertEqual(json.loads(output.getvalue())['status'],'UNKNOWN')
  policy.register(self.pool,self.ledger,self.result());output=io.StringIO()
  with redirect_stdout(output):policy.main(['--pool',str(self.pool.path),'--uri',self.uri])
  self.assertEqual(json.loads(output.getvalue())['status'],'NO_CONSUME')
  with patch.object(policy,'_probe',side_effect=AssertionError('no unsupplied real probe')),redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit) as error:policy.main(['--pool',str(self.pool.path),'--uri',self.uri,'--probe'])
  self.assertEqual(error.exception.code,2)

 def test_fixture_mode_cannot_launch_a_real_image_probe(self):
  import asyncio
  from types import SimpleNamespace
  with patch('site_planner.discovery_tools.DiscoveryBrowser.__aenter__',side_effect=AssertionError('no browser in fixture mode')):
   with self.assertRaisesRegex(ValueError,'mode=real'):asyncio.run(policy._probe(self.pool,SimpleNamespace(config={'mode':'fixture'}),self.uri,self.f.root))

if __name__=='__main__':unittest.main()
