"""核对采集证据与交付文件；通过此检查仍不代表图文语义或人工验收通过。"""
from datetime import datetime
import hashlib
from pathlib import Path
from .browser import fingerprint
from .validate import read_json


def audit_capture(batch, sample_id):
    batch=Path(batch);sample=batch/'samples'/sample_id;evidence=batch/'evidence'/sample_id
    issues=[];checked=0;previous_end=None;expected_ground=[]
    def fail(step_id,message):issues.append({'step_id':step_id,'message':message})
    try:
        data=read_json(sample/'annotation.json')
        for step in data['steps']:
            number=step['step_id']
            try:
                raw=read_json(evidence/f'step_{number:03}.json')
                tree=read_json(sample/step['ui_tree_path'])
                capture=raw['capture'];state=raw['state'];attempt=capture['attempts'][-1]
                if capture['snapshot_source']!='browser_dom':fail(number,'界面树不是浏览器 DOM 来源')
                if tree['elements']!=state['elements'] or tree['screen_resolution']!=state['screen_resolution']:fail(number,'交付树与原始浏览器证据不一致')
                if hashlib.sha256((sample/step['image_path']).read_bytes()).hexdigest()!=capture['screenshot_sha256']:fail(number,'图片校验值与采集记录不一致')
                if not attempt['dom_stable'] or attempt['before_fingerprint']!=fingerprint(state) or attempt['after_fingerprint']!=fingerprint(state):fail(number,'无法证明截图前后的 DOM 一致')
                started=datetime.fromisoformat(raw['started_at']).timestamp()
                ended=datetime.fromisoformat(raw['ended_at']).timestamp()
                if not attempt['started_ns']<=attempt['ended_ns'] or attempt['ended_ns']/1e9>started+0.001 or started>ended:fail(number,'截图与动作的先后时间不一致')
                if previous_end and attempt['started_ns']/1e9<previous_end-0.001:fail(number,'本步截图早于上步动作结束')
                previous_end=ended
                if raw['executed_action']!={'tool_name':step['tool_call']['tool_name'],'arguments':step['tool_call']['arguments']}:fail(number,'动作标注与实际执行参数不一致')
                target=raw.get('target_element')
                if target:
                    expected_ground.append({'step_id':number,'element_id':target['element_id'],'text':target['text'],'bbox':target['bbox']})
                    action=step['action']
                    if (action['target_element_id'],action['target_text'],action['target_bbox'])!=(target['element_id'],target['text'],target['bbox']):fail(number,'目标标注与原始真值不一致')
                if step['action']['action_type']=='complete' and (not raw['final_assertions'] or not all(a['passed'] for a in raw['final_assertions'])):fail(number,'缺少最终页面断言的实际通过记录')
                checked+=1
            except (OSError,ValueError,KeyError,TypeError,IndexError) as e:fail(number,'证据不完整或格式错误：'+str(e))
        if read_json(evidence/'ground_truth.json')!=expected_ground:fail(None,'批次目标真值清单与逐步证据不一致')
    except (OSError,ValueError,KeyError,TypeError) as e:fail(None,str(e))
    return {'sample_id':sample_id,'capture_evidence_pass':not issues,'steps_checked':checked,'issues':issues,
            'human_review':'pending','semantic_review':'pending','delivery_ready':False}
