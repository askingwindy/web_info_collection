"""合成联调样本，绝不代表真实网页采集。"""
from datetime import datetime
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw
from .storage import allocate, write_json
from .action_normalization import normalize_delivery_step


def program_version():
    root=Path(__file__).resolve().parents[3]
    try:
        result=subprocess.run(['git','-C',str(root),'rev-parse','--verify','HEAD'],capture_output=True,text=True,check=True)
        dirty=subprocess.run(['git','-C',str(root),'status','--porcelain'],capture_output=True,text=True,check=True)
        return result.stdout.strip()+('+dirty' if dirty.stdout.strip() else '')
    except (OSError,subprocess.CalledProcessError):
        return 'workspace+uncommitted'


def make_step(index, action_type, arguments, last=False):
    control=action_type in {'click','double_click','right_click','type','select','drag'}
    pointer=action_type in {'click','double_click','right_click','select','drag','scroll'}
    action={'action_type':action_type,'target_element_id':'e_1' if control else '',
            'target_text':'测试控件' if control else ('回车键' if action_type=='hotkey' else ''),
            'coordinate':[arguments['x'],arguments['y']] if pointer else [],
            'input_text':arguments['text'] if action_type=='type' else ('+'.join(arguments['keys']) if action_type=='hotkey' else ''),
            'precondition':'联调测试页面显示测试控件和当前序号',
            'expected_result':'联调页面显示下一状态' if not last else '确认联调页面最终状态'}
    if control: action.update(target_bbox=[100,100,400,200],target_control_type='input')
    if action_type=='drag': action['end_coordinate']=[arguments['end_x'],arguments['end_y']]
    step={'step_id':index,'image_path':f'images/step_{index:03}.png',
            'ui_tree_path':f'ui_tree/step_{index:03}.json','page_name':'联调测试页面',
            'user_goal':'确认最终页面状态' if last else '验证联调控件操作',
            'action':action,'tool_call':{'tool_name':action_type,'call_id':f'call_{index:03}',
                'arguments':arguments,'timestamp':'','context':'Web 联调环境'},
            'tool_result':{'status':'success','return_value':{} if last else {'screen_changed':True},'error':''},
            'next_step_rationale':'页面显示测试控件，执行联调验证' if not last else '最终页面显示联调完成状态，确认结束',
            'step_result':'联调页面显示下一状态' if not last else '联调结束，真实采集尚未开始',
            'exception_evidence':[]}
    return normalize_delivery_step(step, 'Windows')


def scaffold(output, registry=None):
    output=Path(output).absolute()
    output.parent.mkdir(parents=True,exist_ok=True)
    # mkdir(exist_ok=False) 是覆盖保护；后续失败保留现场和已分配编号。
    if output.exists() or output.is_symlink():
        raise FileExistsError('输出目录已存在，拒绝覆盖：'+str(output))
    registry=Path(registry) if registry else output.parent/'registry.sqlite3'
    if not registry.exists() and any(output.parent.glob('*/manifest.json')):
        raise ValueError('该目录已有批次但编号注册表缺失；请恢复原注册表，拒绝重新分配已有编号')
    output.mkdir()
    ids=allocate(registry,'https://example.invalid/integration','联调测试')
    sample=output/'samples'/ids['sample_id']
    (sample/'images').mkdir(parents=True)
    (sample/'ui_tree').mkdir()
    specs=[('click',{'x':200,'y':150}),('type',{'text':'联调输入'}),
           ('hotkey',{'keys':['enter']}),('scroll',{'x':600,'y':400,'direction':'down'}),
           ('select',{'x':200,'y':150,'option':'测试选项'}),('complete',{'status':'success'})]
    steps=[make_step(i,t,args,i==len(specs)) for i,(t,args) in enumerate(specs,1)]
    annotation={'sample_id':ids['sample_id'],'task_instruction':'联调测试：验证测试控件并确认最终页面；此数据不用于交付',
        'task_type':['填写表单'],'terminal_type':'Web',
        'device_info':{'device_model':'','os_name':'','os_version':'','screen_resolution':[1280,720]},
        'app_info':{'app_name':'联调测试页面','app_version':'','environment':'合成联调环境','ui_language':'zh'},
        'risk_level':'normal','trajectory_source':{'source_type':'agent','data_type':'webcollect_agent_v1','action_space':'unified_gui_v4'},
        'steps':steps,'final_state_image':steps[-1]['image_path'],'final_result':'联调测试结束，真实采集样本数仍为零',
        'completion_status':'success','completion_judgement':'此项仅验证结构，不能作为真实任务完成证据'}
    write_json(sample/'annotation.json',annotation)
    for s in steps:
        image=Image.new('RGB',(1280,720),(245,245,245))
        draw=ImageDraw.Draw(image)
        # 使用 Pillow 自带字体，跨环境无需下载字体；水印明确表示合成测试图。
        draw.text((30,25),'SYNTHETIC INTEGRATION FIXTURE - NOT REAL WEB DATA',fill='red',font_size=28)
        draw.rectangle((100,100,400,200),outline='blue',width=3)
        draw.text((130,130),'TEST CONTROL',fill='black',font_size=24)
        draw.text((30,300),f"STATE {s['step_id']:03} - NOT FOR DELIVERY",fill='red',font_size=32)
        image.save(sample/s['image_path'])
        tree={'image_path':s['image_path'],'screen_resolution':[1280,720],
            'elements':[{'element_id':'e_1','parent_id':'root','element_type':'input','native_role':'textbox',
                'text':'测试控件','bbox':[100,100,400,200],'clickable':True,'inputable':True,'scrollable':False,
                'visible':True,'enabled':True,'state':'default'}]}
        write_json(sample/s['ui_tree_path'],tree)
    manifest={**ids,'sample_kind':'integration','program_version':program_version(),'rule_version':'1.0.0',
              'schema_version':'1.0.0','created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'samples':[ids['sample_id']],
              'sites':[{'site_id':ids['site_id'],'uri':'https://example.invalid/integration','site_category':'联调测试'}],
              'notice':'全部截图及界面树为合成联调内容，真实合格样本数量为 0'}
    write_json(output/'manifest.json',manifest)
    from .metadata import export_metadata
    export_metadata(output,output/'metadata.csv')
    return manifest
