"""Small offline controls/pixel guards; no live request or text proof invented."""
import base64
from copy import deepcopy
from io import BytesIO
import unittest
from PIL import Image,ImageDraw
from webcollect.placeholder_strategy import (URI,ADAPTER_ID,development_operations,inspect_placeholder_png,
    validate_observation,compile_placeholder)

def uri(image):
    stream=BytesIO();image.save(stream,format='PNG');return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()

class PlaceholderGuards(unittest.TestCase):
    def test_ten_necessary_actions_and_no_extra_select_scroll_or_download(self):
        operations=development_operations()
        self.assertEqual([op['action_type'] for op in operations],['click','hotkey','type']*3+['click'])
        self.assertEqual([op['arguments']['text'] for op in operations if op['action_type']=='type'],['400','200','预览图'])
        self.assertEqual(operations[-1]['selector'],'#generateBtn')

    def test_png_decoder_proves_dimensions_and_ink_but_not_text_semantics(self):
        image=Image.new('RGB',(400,200),(238,238,238));ImageDraw.Draw(image).rectangle((180,90,220,110),fill=(170,170,170))
        result=inspect_placeholder_png(uri(image))
        self.assertEqual([result['width'],result['height']],[400,200]);self.assertEqual(result['ink_bbox'],[180,90,221,111])
        self.assertEqual(result['text_semantics'],'REQUIRES_INDEPENDENT_PIXEL_REVIEW_OR_OCR')
        for bad in (Image.new('RGB',(400,200),(238,238,238)),Image.new('RGB',(300,300),'white'),Image.new('RGBA',(400,200),(238,238,238,0))):
            with self.assertRaises(ValueError):inspect_placeholder_png(uri(bad))
        with self.assertRaises(ValueError):inspect_placeholder_png('data:image/svg+xml,<svg/>')

    def test_initial_identity_defaults_and_result_are_required(self):
        fields=[{'selector':s,'tag':'input','type':t,'label':l,'value':v,'visible':True,'enabled':True,'label_source':'associated_label'}
                for s,t,l,v in [('#width','number','宽度','300'),('#height','number','高度','300'),('#customText','text','自定义文本','300X300')]]
        fields.append({'selector':'#generateBtn','tag':'button','label':'生成占位图','visible':True,'enabled':True})
        settings=[{'selector':s,'tag':t,'label':l,'value':v,'visible':True,'enabled':True} for s,t,l,v in
                  [('#fontSize','input','字体大小','24'),('#fontFamily','select','选择字体','Arial'),('#theme','select','选择主题','gray')]]
        widget={'adapter_id':ADAPTER_ID,'page_uri':URI,'label':'在线占位图生成工具','viewport':[1280,720],'observed_scroll_y':0,'fields':fields,'settings':settings}
        page={'page_uri':URI,'result_targets':[{'holder_source':'holder.js/300x300?size=24&theme=gray&text=300X300&font=Arial'}]}
        self.assertEqual(validate_observation({'site_uri':URI},page,widget),development_operations())
        for change in ('uri','value','label','type','theme','result'):
            w=deepcopy(widget);p=deepcopy(page)
            if change=='uri':w['page_uri']=URI+'?bad=1'
            elif change=='value':w['fields'][0]['value']='400'
            elif change=='label':w['fields'][0]['label']='其他'
            elif change=='type':w['fields'][0]['type']='range'
            elif change=='theme':w['settings'][-1]['value']='sky'
            else:p['result_targets']=[]
            with self.assertRaises(ValueError):validate_observation({'site_uri':URI},p,w)

if __name__=='__main__':unittest.main()
