"""Scoped observation and unresolved-pair guards, disposable evidence only."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io,json,unittest
from PIL import Image
from webcollect.action_stability import post_observation_scope,pair
from webcollect.batch_core import BatchLedger,load_json
from quality_inspector.ai_worker import unresolved_pair_inputs

class PostObservation(unittest.TestCase):
    def state(self):
        return {'url':'https://example.org/','document_identity':{'id':1},'scroll':[0,0],
          'screen_resolution':[300,200],'device_pixel_ratio':1,
          'capture_readiness':{'document_ready':'complete','fonts_ready':True,'images_ready':True},
          'elements':[{'element_id':'q','native_role':'input','inputable':True,'visible':True,'enabled':True,'text':'搜索','bbox':[20,20,150,50]}],
          'capture_controls':[{'element_id':'q','tag':'input','input_type':'search','selector':'input','index':0}],
          'values':[{'element_id':'q','value':'','value_visible':True,'focused':False,'readonly':False}],
          'geometry_witnesses':[{'element_id':'q','samples':[{'ancestor':True} for _ in range(9)]}]}
    def png(self,point=None):
        image=Image.new('RGB',(300,200),'white')
        if point:image.putpixel(point,(255,0,0))
        b=io.BytesIO();image.save(b,format='PNG');return b.getvalue()
    def test_post_input_proof_rejects_value_focus_pixels_geometry_document_and_ambiguity(self):
        source=self.state();scope=post_observation_scope(source,{'action_type':'click','operation_id':'op','evidence':{'anchor_element_id':'q'}})
        after=deepcopy(source);after['values'][0]['focused']=True
        a=self.png();proof=pair(after,after,a,self.png((250,180)),scope)
        self.assertTrue(proof['accepted']);self.assertFalse(proof['dispatch_permission'])
        for mode in ('value','focus','document','geometry','ambiguity','pixels'):
            changed=deepcopy(after)
            if mode=='value':changed['values'][0]['value']='wrong'
            if mode=='focus':changed['values'][0]['focused']=False
            if mode=='document':changed['document_identity']={'id':2}
            if mode=='geometry':changed['geometry_witnesses'][0]['samples'][4]['ancestor']=False
            if mode=='ambiguity':changed['elements'].append({**changed['elements'][0],'element_id':'other'})
            try:result=pair(changed,changed,a,self.png((30,30)) if mode=='pixels' else a,scope)
            except ValueError:continue
            self.assertFalse(result['accepted'],mode)
        with self.assertRaises(ValueError):pair(after,after,a,a,{**scope,'action':'click'})
    def test_post_primary_keeps_rendered_body_and_values_strict(self):
        source=self.state();source['elements'].append({'element_id':'main','native_role':'main','visible':True,'bbox':[0,0,200,150]})
        source['capture_controls'][0]['selector']='main > input';source['capture_controls'].append({'element_id':'main','selector':'main'})
        scope=post_observation_scope(source,{'action_type':'scroll','operation_id':'read'})
        a=self.png();self.assertTrue(pair(source,source,a,self.png((250,180)),scope)['accepted'])
        for mode in ('body','value','geometry','document','pixels'):
            changed=deepcopy(source)
            if mode=='body':changed['elements'][0]['text']='different body'
            if mode=='value':changed['values'][0]['value']='wrong'
            if mode=='geometry':changed['elements'][0]['bbox']=[21,20,151,50]
            if mode=='document':changed['document_identity']={'id':2}
            try:result=pair(source,changed,a,self.png((30,30)) if mode=='pixels' else a,scope)
            except ValueError:continue
            self.assertFalse(result['accepted'],mode)

    def test_post_navigation_loading_is_rejected_and_readonly_observation_can_settle(self):
        source=self.state();source['elements'].append({'element_id':'main','native_role':'main','visible':True,'bbox':[0,0,200,150]})
        source['capture_controls'].append({'element_id':'main','selector':'main'})
        scope=post_observation_scope(source,{'action_type':'hotkey','operation_id':'submit'})
        after=deepcopy(source);after['url']='https://example.org/article';after['document_identity']={'id':2}
        png=self.png()
        for key,value in (('document_ready','loading'),('fonts_ready',False),('images_ready',False)):
            loading=deepcopy(after);loading['capture_readiness'][key]=value
            rejected=pair(loading,after,png,png,scope)
            self.assertFalse(rejected['accepted']);self.assertFalse(rejected['dispatch_permission'])
            self.assertEqual(rejected['reason'],'Reading region not fully loaded')
            self.assertIn('before_fingerprint',rejected);self.assertIn('png_after_sha256',rejected)
        self.assertTrue(pair(after,after,png,png,scope)['accepted'])

class UnknownPair(unittest.TestCase):
    def test_full_vectors_block_new_ids_prose_and_chunking_but_not_other_neighbor(self):
        with TemporaryDirectory() as d:
            root=Path(d);cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
            ledger=BatchLedger(root/'local.db',cfg,initialize=True)
            for name in ('f1','f2','n1','n2','different'):(root/name).write_text(name)
            payload={'candidate':{'sample_id':'old','images':['f1','f2']},'neighbors':[{'sample_id':'old-neighbor','images':['n1','n2']}]}
            jid=ledger.enqueue('ai-difference',payload)
            with ledger.connect() as con:columns=[r[1] for r in con.execute('pragma table_info(model_requests)')]
            with ledger.transaction() as con:
                con.execute("INSERT INTO model_requests(id,job_id,purpose,state,started,request_json,attempt,reserved_tokens,reserved_cost) VALUES(?,?,?,'unknown',0,'{}',1,0,0)",('original',jid,'difference-0-part-0:original-binding'))
            def compact(value):return {'sample_id':value['sample_id']},[root/n for n in value['images']]
            with patch('quality_inspector.ai_worker.compact_trajectory',side_effect=compact):
                focal={**payload['candidate'],'sample_id':'new','annotation':'changed prose'}
                other={**payload['neighbors'][0],'sample_id':'renamed'}
                self.assertEqual(unresolved_pair_inputs(ledger,focal,other)[0]['request_id'],'original')
                self.assertEqual(unresolved_pair_inputs(ledger,focal,{**other,'images':['different']}),[])
            with ledger.connect() as con:self.assertEqual(con.execute('select state from model_requests').fetchone()[0],'unknown')
