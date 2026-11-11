"""Producer-only anonymous DOM supplement, no network or consumer execution."""
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image
import test_producer_business_v7 as business
from site_planner import page_purpose_v5 as p
from site_planner.discovery_tools import reference
from site_planner.pipeline import reserve_visit
from webcollect.batch_core import load_json,save_json

class Observation(unittest.TestCase):
 def setUp(self):
  self.b=business.Business('test_formal_business_selection_filters_legal_and_restart_zero_io');self.b.setUp();self.addCleanup(self.b.doCleanups)
  self.f=self.b.f;self.ledger=self.b.ledger;self.uri='https://tools.example.org/a'
  self.b.target_html={self.uri:'<html><title>公开示例</title><div id="root"></div></html>'}
  self.doc,self.ref=self.b.get(self.ledger,'original',self.uri,self.f.root)
  self.link={'uri':self.uri,'link_id':'fixture-link','application_id':'a','site_category':'企业后台与开源演示站','site_decision_id':'decision'}
 def observation(self,**overrides):
  jid=self.ledger.enqueue('producer-anonymous-observation-1',{'uri':self.uri,'access':'fresh_context_no_login_get_only'})
  job=self.ledger.claim('producer-anonymous-observation-1',job_id=jid)
  self.ledger.consume('probe_pages',jid);visit=reserve_visit(self.ledger,job,self.uri,'producer-anonymous-observation-1')
  dom=self.f.t.docs/'rendered.html';dom.write_text('<main><h1>公开表格示例</h1><p>'+('数据展示的正文说明。'*10)+'</p><table><tr><td>记录</td></tr></table><select name="status"><option>全部</option></select></main>')
  png=self.f.t.docs/'observed.png';Image.new('RGB',(10,10),'white').save(png)
  record={'policy':'producer-anonymous-readonly-1','job_id':jid,'visit_id':visit['id'],'source_get':self.ref,'entry_uri':self.uri,'landed_uri':self.uri,'status':200,
    'anonymous_context':True,'login_performed':False,'initial_cookies':0,'requests':[{'method':'GET','url':self.uri,'resource_type':'document'}],
    'dom':reference(dom),'screenshot':reference(png),**overrides}
  path=self.f.t.docs/'observation.json';save_json(path,record)
  self.ledger.settle_visit(visit,state='succeeded',response_status=200,landed_uri=self.uri,metrics={});self.ledger.finish(job,result=reference(path))
  return record
 def test_rendering_adds_evidence_without_replacing_original_get(self):
  self.assertFalse(p.material({**self.doc,'reference':self.ref})['main_region_found'])
  record=self.observation();ev=p.observed_material(self.ledger,self.link,self.doc,self.ref)
  self.assertTrue(ev['main_region_found']);self.assertEqual(ev['document'],self.ref);self.assertEqual(ev['raw_html'],self.doc['raw_html'])
  self.assertEqual(ev['rendered_dom'],record['dom']);self.assertFalse(ev['anonymous_controls_proven'])
 def test_no_observation_uses_original_static_document(self):
  ev=p.observed_material(self.ledger,self.link,self.doc,self.ref);self.assertNotIn('observation',ev)
 def test_logged_in_or_mutating_observation_is_rejected(self):
  self.observation(login_performed=True)
  with self.assertRaisesRegex(ValueError,'conditions'):p.observed_material(self.ledger,self.link,self.doc,self.ref)
 def test_wrong_get_binding_is_rejected(self):
  self.observation(source_get={'path':'wrong','sha256':'wrong'})
  with self.assertRaisesRegex(ValueError,'conditions'):p.observed_material(self.ledger,self.link,self.doc,self.ref)
 def test_formal_v8_uses_anonymous_dom_and_preserves_four_field_body(self):
  self.observation();home=self.f.site(html='<main><a href="/a">公开示例正文</a></main>')[1]
  self.b.inputs=[];self.b.inspect=[];self.b.plain=False
  with patch.object(p,'homepage_document',side_effect=self.b.get),patch.object(self.f.f.provider.opener,'open',side_effect=self.b.provider):
   report=self.f.run_new(home,key='v8',target=1,sources=[{**home,'context_only':True}])
   repeat=self.f.run_new(home,key='v8',target=1,sources=[{**home,'context_only':True}])
  self.assertEqual(report['listed_unique_candidates'],1,report);self.assertEqual(repeat['new_dispatches'],{'model':0,'GET':0,'search':0})
  row=self.f.pool.rows(protocols=('webcollect-data-candidate-2',))[0]
  self.assertEqual(set(row['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
  ev=row['sources'][0]['purpose_evidence']['target_evidence'];self.assertEqual(ev['material_source'],'anonymous_rendered_dom')

 def test_paid_site_citation_cap_recovered_without_resend_or_mutation(self):
  import io,json
  from copy import deepcopy
  from site_planner.application_discovery import classify_homepage
  from site_planner.discovery_agent import SettledSelectionRejected
  aid,home=self.f.site(uri='https://demo.example.org/',html='<main>公开示例\n表单校验\n表格分页\n图表查询\n后台管理</main>',confirmed=False)
  content='公开示例\n表单校验\n表格分页\n图表查询\n后台管理'
  body={k:v for k,v in home.items() if k!='reference'};body['content']=content
  hp=self.f.t.docs/'site-recovery-source.json';save_json(hp,body);home={**body,'reference':reference(hp)}
  def provider(request,timeout):
   context=json.loads(json.loads(request.data)['messages'][1]['content'][0]['text'])
   from site_planner.producer_evidence import numbered_homepage
   ids=list(numbered_homepage(home,['公开示例','表单校验','表格分页','图表查询','后台管理']))
   args={'parent_category':'企业后台与开源演示站','quote_ids':ids[:4],'reason':'公开后台示例原文'}
   raw=deepcopy(self.f.f.provider.opener.raw);raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[{'id':'site','type':'function','function':{'name':'submit_site_classification','arguments':json.dumps(args)}}]}}]
   return io.BytesIO(json.dumps(raw).encode())
  with patch.object(self.f.f.provider.opener,'open',side_effect=provider):
   with self.assertRaises(ValueError):classify_homepage(self.f.pool,self.ledger,home,self.f.root,protocol='producer-site-classification-4')
  with self.ledger.connect() as con:before=[dict(r) for r in con.execute('SELECT * FROM model_requests')]
  with patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('no resend')):
   result=classify_homepage(self.f.pool,self.ledger,home,self.f.root,protocol='producer-site-classification-5')
  self.assertEqual(result['category'],'企业后台与开源演示站')
  with self.ledger.connect() as con:self.assertEqual(before,[dict(r) for r in con.execute('SELECT * FROM model_requests')])

 def test_demo_prerequisite_accepts_concrete_crud_and_chart_controls(self):
  for title in ('增删改查示例','图表示例'):
   doc=self.b.document('<main><h2>'+title+'</h2><input name="filter"><table><tr><td>数据</td></tr></table></main>')
   self.assertEqual(p.demo_proof(doc)['acceptance'],'STATIC_PREREQUISITE_ONLY')

 def test_unnamed_controls_need_semantic_scope_and_table_needs_three_data_rows(self):
  ev=p.material(self.b.document('<main><h2>表单校验</h2><input><button>提交</button><table><tr><th>ID</th></tr>'+''.join('<tr><td>'+str(i)+'</td></tr>' for i in range(3))+'</table></main>'))
  heading=next(u for u in ev['units'] if u['kind']=='heading');table=next(u for u in ev['units'] if u['tag']=='table')
  self.assertTrue(p.accepts('功能页',[heading],ev));self.assertTrue(p.accepts('检索或列表',[table],ev))
  self.assertFalse(p.accepts('检索或列表',[heading],ev))
  self.assertFalse(p.accepts('功能页',[],ev))
  menu={'q0':heading,'q1':table};proposal={'select':True,'business':'public_business','business_quotes':['q0','q1']}
  self.assertTrue(p.business_supported(proposal,menu,ev));proposal['business_quotes']=['q1'];self.assertFalse(p.business_supported(proposal,menu,ev))

 def test_legacy_site_receipt_recovery_keeps_original_bytes(self):
  import io,json
  from copy import deepcopy
  from site_planner.application_discovery import classify_homepage,Discovery
  _,home=self.f.site(uri='https://legacy.example.org/',confirmed=False)
  def provider(request,timeout):
   args={'parent_category':'在线工具','quote_ids':['q0'],'reason':'原始首页提供中文在线工具'}
   raw=deepcopy(self.f.f.provider.opener.raw);raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[{'id':'original','type':'function','function':{'name':'submit_site_classification','arguments':json.dumps(args)}}]}}]
   return io.BytesIO(json.dumps(raw).encode())
  with patch.object(self.f.f.provider.opener,'open',side_effect=provider),patch.object(Discovery,'decide',side_effect=RuntimeError('stopped after receipt before decide')):
   with self.assertRaises(RuntimeError):classify_homepage(self.f.pool,self.ledger,home,self.f.root,protocol='producer-site-classification-4')
  path=next(self.f.root.glob('site-classification-*.json'));original=load_json(path);original.pop('response_mode',None);path.write_text(json.dumps(original,ensure_ascii=False,indent=2,sort_keys=True)+'\n');before=path.read_bytes()
  with patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('no network on original paid recovery')):
   result=classify_homepage(self.f.pool,self.ledger,home,self.f.root,protocol='producer-site-classification-4')
  self.assertEqual(result['category'],'在线工具');self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
