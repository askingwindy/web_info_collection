"""Shared region equivalence: authored pixels/states, no transport or production IO."""
from copy import deepcopy
from io import BytesIO
import unittest
from PIL import Image,ImageDraw
from webcollect import dynamic_regions as dynamic
from webcollect.browser import stability_pair
from webcollect.reading_progress import same_view,lines
from webcollect.react_protocol import atomic_effect,RULE_VERSION,V3_EFFECT_RULE
from webcollect.action_stability import POST_VERSION,projection as input_projection


def state():
    s={'url':'https://example.test/article','title':'Article','document_identity':{'nonce':1},'scroll':[0,0],
       'screen_resolution':[80,60],'device_pixel_ratio':1,'values':[],
       'capture_readiness':{'schema_version':'webcollect-capture-readiness-1','document_ready':'complete','fonts_ready':True,'images_ready':True},
       'elements':[{'element_id':'main','native_role':'main','text':'','bbox':[0,0,80,60],'visible':True},
          {'element_id':'notice','parent_id':'main','native_role':'status','text':'Announcement one','bbox':[40,0,80,20],'visible':True},
          {'element_id':'go','parent_id':'main','native_role':'button','text':'Operate','bbox':[0,30,30,50],'visible':True,'enabled':True,'clickable':True,'state':'default'}],
       'visible_text':'Operate\nAnnouncement one','capture_controls':[{'element_id':'notice','selector':'div:nth-of-type(1)','tag':'div'}, {'element_id':'go','selector':'button','tag':'button','href':None}],
       'geometry_witnesses':[{'element_id':'go','bbox':[0,30,30,50],'samples':[{'ancestor':True}]*9}],
       'capture_images':[],'text_blocks':[],'paint_borders':[],'capture_media':[]}
    r={'schema_version':dynamic.VERSION,'category':'announcement','tag':'div','attributes':{'id':'notice','class':None,'role':'status','aria-label':None,'aria-roledescription':None,'title':None},
       'selector':'div:nth-of-type(1)','element_id':'notice','bbox':[40,0,80,20],'raw_bbox':[40,0,80,20],'clip_bbox':[0,0,80,60],
       'member_ids':['notice'],'member_selectors':['div:nth-of-type(1)'],'eligible':True,'reasons':[],'external_text_overlaps':[],'external_control_ids':[]}
    s['dynamic_region_contract']={'schema_version':dynamic.VERSION,'regions':[r],'visible_text_outside':'Operate','ancestor_text_outside':{}}
    return s


def png(color='red',outside=False):
    im=Image.new('RGB',(80,60),'white');d=ImageDraw.Draw(im);d.rectangle((40,0,79,19),fill=color)
    if outside:d.point((1,1),fill='blue')
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()


class DynamicRegions(unittest.TestCase):
    def test_main_notice_motion_is_not_new_reading_or_effect(self):
        a=state();b=deepcopy(a);b['elements'][1]['text']='Announcement two';b['visible_text']='Operate\nAnnouncement two'
        proof=stability_pair(a,b,png(),png('blue'));self.assertTrue(proof['accepted']);self.assertTrue(same_view(a,b));self.assertEqual(lines(a),lines(b))
        self.assertFalse(atomic_effect(a,b,'click',{},'go',rule_version=RULE_VERSION)['verified'])
        self.assertTrue(atomic_effect(a,b,'click',{},'go',rule_version=V3_EFFECT_RULE)['verified'])
        self.assertFalse(stability_pair(a,b,png(),png('blue',outside=True))['accepted'])
    def test_actual_business_result_is_not_an_allowed_announcement(self):
        a=state();b=deepcopy(a)
        for s in (a,b):s['dynamic_region_contract']['regions'][0].update(eligible=False,reasons=['business_result_semantics'])
        b['elements'][1]['text']='106.25';b['visible_text']='Operate\n106.25'
        for st in (a,b):st['dynamic_region_contract']['visible_text_outside']=st['visible_text']
        self.assertFalse(stability_pair(a,b,png(),png('blue'))['accepted'])
        self.assertTrue(atomic_effect(a,b,'click',{},'go',rule_version=RULE_VERSION)['verified'])
    def test_target_missing_or_occluded_and_wrong_document_rejected(self):
        a=state();b=deepcopy(a)
        a['target']=b['target']={'element_id':'missing','hit_valid':True}
        self.assertFalse(stability_pair(a,b,png(),png('blue'))['accepted'])
        a=state();b=deepcopy(a);a['target']={'element_id':'go','hit_valid':True};b['target']={'element_id':'go','hit_valid':False}
        self.assertFalse(stability_pair(a,b,png(),png('blue'))['accepted'])
        a=state();b=deepcopy(a);scope={'schema_version':POST_VERSION,'action':'observe','purpose':'post_primary_content','source_url':a['url'],'source_document':{'nonce':999},'allow_navigation':False}
        proof=stability_pair(a,b,png(),png('blue'),action_scope=scope);self.assertFalse(proof['accepted']);self.assertIn('document',proof['scope_error'])
    def test_equal_wrong_input_does_not_satisfy_dispatched_expected_value(self):
        a=state();e=a['elements'][2];e.update(native_role='input',inputable=True,clickable=True,text='Search')
        a['capture_controls'][1].update(tag='input',input_type='search',index=0)
        a['values']=[{'element_id':'go','value':'wrong','focused':True,'value_visible':True,'input_type':'search','readonly':False}]
        a['visible_text']='Search\nwrong\nAnnouncement one';a['dynamic_region_contract']['visible_text_outside']='Search\nwrong'
        source=input_projection(a,'go',action='type');scope={'schema_version':POST_VERSION,'action':'observe','purpose':'post_search_input','source':source,'expected_value':'wanted'}
        proof=stability_pair(a,deepcopy(a),png(),png('blue'),action_scope=scope);self.assertFalse(proof['accepted']);self.assertIn('expected value',proof['scope_error'])
    def test_labels_or_model_data_attributes_cannot_create_an_allowed_region(self):
        s=state();r=s['dynamic_region_contract']['regions'][0];r['attributes']['id']='plain';r['attributes']['role']=None
        self.assertEqual(dynamic.regions(s),[])
        r['attributes']['data-dynamic-region']='announcement';self.assertEqual(dynamic.regions(s),[])

    def test_ad_video_source_changes_use_shared_region_but_unclassified_video_does_not(self):
        from webcollect.media_preflight import summarize_preflight
        from test_media_preflight import probe,video,assessment
        v1=video(time=1,paused=False);v2=video(time=0,paused=False,source='next.webm')
        for v in (v1,v2):v['context']['explicit_ad_markers']=['advertisement']
        proof={'schema_version':dynamic.STABILITY,'accepted':True,'loading_complete':True,'allowed_dynamic_regions':[{'bbox':[20,100,460,260]}],'pixel_change':{'outside_allowed_pixels':0}}
        change={'changed_fraction':0.1,'bbox':[20,100,460,260],'related_stability':proof,'diagnostic_pair_stability':[proof,deepcopy(proof)]}
        probes=[probe(media=[v1]),probe(600,media=[v2])]
        self.assertEqual(summarize_preflight(probes,[assessment()],[change])['routing'],'NORMAL_M1')
        self.assertEqual(summarize_preflight(probes,[assessment()],[])['routing'],'REVIEW_REQUIRED')

    def test_empty_native_close_button_does_not_disqualify_notice_but_input_does(self):
        s=state();r=s['dynamic_region_contract']['regions'][0];r['member_ids'].append('go');r['member_selectors'].append('button')
        s['values']=[{'element_id':'go','input_type':'submit','value':'','value_visible':False,'focused':False}]
        self.assertEqual(len(dynamic.regions(s)),1)
        projected=dynamic.projection(s);self.assertTrue(any(e['element_id']=='go' for e in projected['elements']));self.assertEqual(projected['values'],s['values'])
        s['elements'][2].update(native_role='input',inputable=True);s['values'][0].update(input_type='text',value_visible=True)
        self.assertEqual(dynamic.regions(s),[])

    def test_agent_projection_carries_summary_from_full_original_state(self):
        import tempfile,json
        from pathlib import Path
        from webcollect.agent_observation import project
        from webcollect.batch_core import file_sha
        s=state()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'state.json').write_text(json.dumps(s));(root/'capture.json').write_text('{}');(root/'image.png').write_bytes(png())
            evidence={k:{'path':str(root/v),'sha256':file_sha(root/v)} for k,v in [('state','state.json'),('capture','capture.json'),('image','image.png')]}
            observed=project(s,evidence)
            self.assertNotIn('screen_resolution',observed)
            self.assertEqual(observed['dynamic_region_summary'],dynamic.summary(s))
            self.assertEqual(observed['dynamic_region_summary']['regions'][0]['eligible_for_change'],True)
            self.assertFalse(observed['capture_verified'])
