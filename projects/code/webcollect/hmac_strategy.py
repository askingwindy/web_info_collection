"""Observed HMAC form -> necessary actions -> independently computed visible result.

The exact route and original controls are registered; arbitrary crypto pages,
algorithms or parameter variants do not create independent business inventory.
The public example key is an authored task input, never an account credential.
A masked password value is not accepted as saved-frame completion evidence.
"""
import hashlib
import hmac
from urllib.parse import urlsplit

ADAPTER_ID = 'jyshare-hmac-widget-1'
EXECUTION_ID = 'observed-form-result-v1'
EXECUTION_VERSION = 'observed-form-result'
BUSINESS_ID = 'keyed-message-authentication-v1'
STRATEGY_ID = BUSINESS_ID
URI = 'https://www.jyshare.com/crypto/hmacsha256/'
TITLE = 'HMACSHA256 在线加密工具 | 菜鸟工具'
KEY = '社区阅读室公开示例密钥'
MESSAGE = ('请核对这段示例公告的消息认证码：本周六上午九点开始图书整理活动，请参与者携带借阅证到社区阅读室集合。'
           '活动结束后统一归还书籍，确认登记表上的书名和数量；如需调整安排，请以现场公布的说明为准。感谢各位居民配合。')
SOURCE_DOM_SHA256 = 'ce03f69f59225141ad62b325d501704758d84e53c0d9bd6f076e1c9b2dc82714'


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


def hmac_sha256(message, key):
    """Compute from UTF-8 task inputs without consulting page code or DOM output."""
    if (not isinstance(message, str) or not isinstance(key, str) or not message.strip() or not key.strip()
            or len(message) > 4096 or len(key) > 128 or '\x00' in message + key):
        raise ValueError('HMAC oracle requires bounded nonempty UTF-8 example inputs')
    return hmac.new(key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()


HMAC_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/crypto/hmacsha256/')return empty;
 const id='jyshare-hmac-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
 const shown=e=>!!e&&e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
 const visible=e=>{if(!shown(e))return false;const r=e.getBoundingClientRect();
  if(r.width<=0||r.height<=0||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)return false;
  const hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);return !!hit&&(hit===e||e.contains(hit));};
 const key=one('#pwd'),message=one('#message_source'),submit=one('#btn-encrypt'),result=one('#hash_result');
 const root=key?.closest('.form-row'),card=root?.closest('.card'),heading=card&&one('.card-header h4',card);
 const badge=card&&one('.card-header .algorithm-badge',card),caption=key?.closest('.input-group')?.querySelector('.input-group-prepend .input-group-text');
 if(document.title!=='HMACSHA256 在线加密工具 | 菜鸟工具'||!root||!card||!heading||!badge||
    clean(heading.innerText)!=='HMACSHA256 在线加密工具'||clean(badge.innerText)!=='HMAC'||!visible(heading)||!visible(badge)||
    ![key,message,submit,result].every(e=>!!e&&root.contains(e)))return fail('HMAC exact heading, algorithm and original grouped controls changed');
 if(key.localName!=='input'||key.type!=='password'||key.placeholder!=='请输入密钥'||key.value!==''||key.disabled||key.readOnly||
    key.autocomplete!=='new-password'||!visible(key)||!visible(caption)||clean(caption.innerText)!=='密钥')
    return fail('HMAC original masked empty key control or adjacent visible label changed');
 if(message.localName!=='textarea'||message.placeholder!=='请输入需要加密的字符串'||message.value!==''||message.disabled||message.readOnly||
    message.rows!==6||!visible(message))return fail('HMAC original empty message textarea changed');
 if(submit.localName!=='button'||submit.type!=='button'||submit.disabled||!visible(submit)||clean(submit.innerText)!=='加密'||
    submit.getAttribute('onclick')!=="CryptoTool.hash('hmacsha256')"||typeof window.CryptoTool?.hash!=='function'||
    typeof window.CryptoJS?.HmacSHA256!=='function')return fail('HMAC actual submit control, handler or loaded algorithm changed');
 const upper=one('#upperText'),info=one('#result-info'),timing=one('#result-time');
 if(!upper||upper.type!=='checkbox'||upper.checked||upper.disabled||!visible(upper)||!info||!timing||
    !root.contains(upper)||!root.contains(info)||!root.contains(timing)||result.localName!=='div'||!visible(result)||
    clean(result.innerText)!=='等待输入…'||result.className!=='placeholder-text'||clean(info.innerText)!=='—'||clean(timing.innerText)!=='')
    return fail('HMAC initial visible result, empty status or output-case setting changed');
 const editable=[...root.querySelectorAll('input,textarea,select,[contenteditable=true]')].filter(shown);
 if(editable.length!==3||editable.some(e=>![key,message,upper].includes(e)))return fail('HMAC additional visible editable settings require a separate registered workflow');
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'HMACSHA256 在线加密工具',algorithm:'hmac-sha256',
  fields:[{selector:'#pwd',tag:'input',type:'password',label:'请输入密钥',adjacent_label:'密钥',value:'',visible:true,enabled:true,
           value_visible:false,label_source:'visible-placeholder-and-adjacent-key-label'},
          {selector:'#message_source',tag:'textarea',type:'textarea',label:'请输入需要加密的字符串',value:'',visible:true,enabled:true,
           value_visible:true,label_source:'visible-placeholder'}],
  submit:{selector:'#btn-encrypt',tag:'button',type:'button',label:'加密',visible:true,enabled:true,handler:"CryptoTool.hash('hmacsha256')"},
  output_case:'lowercase',viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY}],
  result_targets:[{selector:'#hash_result',tag:'div',kind:'hmac-result',label:'加密结果',text:'等待输入…',visible:true}],widget_rejections:[]};
}'''


def validate_observation(capability, page, widget):
    if (not matches_uri(capability.get('site_uri', '')) or not matches_uri(page.get('page_uri', ''))
            or not matches_uri(widget.get('page_uri', '')) or page.get('title') != TITLE
            or widget.get('adapter_id') != ADAPTER_ID or widget.get('label') != 'HMACSHA256 在线加密工具'
            or widget.get('kind') != 'non-form-widget' or widget.get('algorithm') != 'hmac-sha256'
            or widget.get('viewport') != [1280, 720] or widget.get('observed_scroll_y') != 0
            or widget.get('output_case') != 'lowercase'):
        raise ValueError('HMAC requires its exact observed route, initial algorithm and viewport')
    expected_fields = [
        {'selector': '#pwd', 'tag': 'input', 'type': 'password', 'label': '请输入密钥', 'adjacent_label': '密钥',
         'value': '', 'visible': True, 'enabled': True, 'value_visible': False,
         'label_source': 'visible-placeholder-and-adjacent-key-label'},
        {'selector': '#message_source', 'tag': 'textarea', 'type': 'textarea', 'label': '请输入需要加密的字符串',
         'value': '', 'visible': True, 'enabled': True, 'value_visible': True, 'label_source': 'visible-placeholder'}]
    expected_submit = {'selector': '#btn-encrypt', 'tag': 'button', 'type': 'button', 'label': '加密',
                       'visible': True, 'enabled': True, 'handler': "CryptoTool.hash('hmacsha256')"}
    targets = [target for target in page.get('result_targets', []) if target.get('selector') == '#hash_result']
    expected_result = {'selector': '#hash_result', 'tag': 'div', 'kind': 'hmac-result',
                       'label': '加密结果', 'text': '等待输入…', 'visible': True}
    if widget.get('fields') != expected_fields or widget.get('submit') != expected_submit or targets != [expected_result]:
        raise ValueError('HMAC must bind the original visible labels, masked key, handler and empty visible result')
    return widget


def _assertions(message, key):
    return [{'selector': '#hash_result', 'contains': hmac_sha256(message, key)},
            {'selector': '#message_source', 'value': message}]


def production_operations(message=MESSAGE, key=KEY):
    assertions = _assertions(message, key)
    return [
        {'operation_id': 'key-focus', 'subgoal_id': 'key', 'action_type': 'click', 'selector': '#pwd',
         'evidence': {'target_label': '请输入密钥'}, 'goal': '选中「请输入密钥」输入框',
         'rationale': '定位填写公开示例密钥的必要输入位置', 'expected': '密钥输入框获得焦点'},
        {'operation_id': 'key-type', 'subgoal_id': 'key', 'action_type': 'type', 'selector': '#pwd',
         'evidence': {'target_label': '请输入密钥'}, 'arguments': {'text': key}, 'goal': '填写任务给定的公开示例密钥',
         'rationale': '消息认证码需要消息与示例密钥两个输入', 'expected': '密钥输入框以密码掩码保留输入',
         'postconditions': [{'visible_text': '密钥'}]},
        {'operation_id': 'message-focus', 'subgoal_id': 'message', 'action_type': 'click', 'selector': '#message_source',
         'evidence': {'target_label': '请输入需要加密的字符串'}, 'goal': '选中「请输入需要加密的字符串」输入框',
         'rationale': '定位需要生成认证码的公告输入位置', 'expected': '公告输入框获得焦点'},
        {'operation_id': 'message-type', 'subgoal_id': 'message', 'action_type': 'type', 'selector': '#message_source',
         'evidence': {'target_label': '请输入需要加密的字符串'}, 'arguments': {'text': message}, 'goal': '填写任务中的完整示例公告',
         'rationale': '公告原文是需要生成消息认证码的内容', 'expected': '公告输入框完整显示任务给定的公告',
         'postconditions': [{'selector': '#message_source', 'value': message}]},
        {'operation_id': 'generate', 'subgoal_id': 'result', 'action_type': 'click', 'selector': '#btn-encrypt',
         'evidence': {'target_label': '加密'}, 'goal': '点击「加密」并核对「加密结果」',
         'rationale': '以已填写的公告和示例密钥生成消息认证码', 'expected': '加密结果区域完整显示64位消息认证码',
         'postconditions': assertions, 'execution': {'settle_ms': 3500}}]


def _subgoals():
    return [{'id': 'key', 'description': '填写公开示例密钥并由最终认证码验证其参与计算',
             'evidence': [{'final_assertion_index': 0}]},
            {'id': 'message', 'description': '填写完整示例公告',
             'evidence': [{'operation_id': 'message-type', 'postcondition_index': 0}]},
            {'id': 'result', 'description': '核对原始末帧中的消息认证码',
             'evidence': [{'final_assertion_index': 0}]}]


def _business_identity(task):
    return {'schema_version': 'business-identity', 'business_id': BUSINESS_ID,
            'execution_capability_id': EXECUTION_ID,
            'definition': {'business_goal': '使用公开示例密钥为公告生成消息认证码',
                           'necessary_input_roles': ['public-example-key', 'message'],
                           'state_path': ['empty-form', 'key-entered-masked', 'message-visible', 'authentication-code-visible'],
                           'completion_criterion': 'visible HMAC-SHA256 equals independent UTF-8 Python oracle'},
            'observation_binding': {'capability_id': task['capability_id'],
                                    'capability_version': task['capability_version']}}


def hmac_spec(capability, page, widget, strategy_version):
    validate_observation(capability, page, widget)
    return {'page_uri': URI, 'widget_adapter': ADAPTER_ID, 'form_label': widget['label'],
            'goal': '在「HMACSHA256 在线加密工具」中，用公开示例密钥「' + KEY + '」为公告「' + MESSAGE
                    + '」生成消息认证码，点击「加密」并核对「加密结果」中的完整结果。',
            'inputs': [{'selector': '#pwd', 'label': '请输入密钥', 'value': KEY},
                       {'selector': '#message_source', 'label': '请输入需要加密的字符串', 'value': MESSAGE}],
            'completion': {'selector': '#hash_result', 'contains': hmac_sha256(MESSAGE, KEY)},
            'deterministic_strategy': {'id': EXECUTION_ID, 'version': strategy_version, 'business_id': BUSINESS_ID,
                                       'business_goal': '使用公开示例密钥为公告生成消息认证码',
                                       'operator': 'Python hmac.new(key_utf8, message_utf8, sha256).hexdigest()',
                                       'algorithm': 'hmac-sha256'}}


def validated_business_identity(task):
    """Reject unknown, padded, hidden-value or mismatched terminal claims."""
    if (not all(matches_uri(task.get(k, '')) for k in ('initial_url', 'site_uri'))
            or any(not isinstance(task.get(k), str) or not task[k].strip()
                   for k in ('capability_id', 'capability_version'))
            or task.get('execution_capability') != {'id': EXECUTION_ID, 'version': EXECUTION_VERSION}
            or task.get('business_identity') != _business_identity(task)):
        raise ValueError('HMAC business identity is not bound to its registered observed form')
    try:
        operations = task['operations']
        message, key = operations[3]['arguments']['text'], operations[1]['arguments']['text']
        assertions = _assertions(message, key)
        if (operations != production_operations(message, key) or task.get('final_assertions') != assertions
                or task.get('required_actions') != [op['operation_id'] for op in operations]
                or task.get('subgoals') != _subgoals() or task.get('stop_when_final') is not True):
            raise ValueError('HMAC necessary operations or independent visible result evidence changed')
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError('HMAC operations or terminal evidence are malformed') from error
    strategy = task.get('deterministic_strategy', {})
    if (strategy.get('business_id') != BUSINESS_ID or strategy.get('algorithm') != 'hmac-sha256'
            or strategy.get('id') != EXECUTION_ID):
        raise ValueError('HMAC execution capability is distinct from its registered business meaning')
    return task['business_identity']


def compile_hmac(capability, spec, task_version=ADAPTER_ID + '-compiler'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages = [page for page in capability['capabilities'] if page['page_uri'] == URI]
    if len(pages) != 1:
        raise ValueError('HMAC must bind one exact observed page')
    page = pages[0]
    widgets = [widget for widget in page.get('widgets', []) if widget.get('adapter_id') == ADAPTER_ID]
    if len(widgets) != 1 or hmac_spec(capability, page, widgets[0], spec['deterministic_strategy']['version']) != spec:
        raise ValueError('HMAC specification differs from the registered observed controls and inputs')
    assertions = _assertions(MESSAGE, KEY)
    operations = production_operations()
    task = {'task_id': 'hmac-' + object_sha256({'capability': capability['capability_id'], 'spec': spec})[:24],
            'task_version': task_version, 'capability_id': capability['capability_id'], 'capability_version': capability['version'],
            'task_family': 'form-workflow', 'site_uri': URI, 'site_category': capability['site_category'], 'initial_url': URI,
            'app_name': page['title'], 'instruction': spec['goal'], 'task_type': ['填写表单'], 'stop_when_final': True,
            'content_preparation': False, 'operations': operations, 'subgoals': _subgoals(),
            'required_actions': [op['operation_id'] for op in operations], 'final_assertions': assertions,
            'final_result': '加密结果区域显示消息认证码「' + hmac_sha256(MESSAGE, KEY) + '」',
            'completion_judgement': '核对原始末帧中的完整消息认证码与公告内容，结果须与独立计算一致。',
            'deterministic_strategy': spec['deterministic_strategy'],
            'execution_capability': {'id': EXECUTION_ID, 'version': EXECUTION_VERSION},
            'capability_screen_status': capability['status'], 'capability_review_required': capability['status'] != 'ready'}
    task['business_identity'] = _business_identity(task)
    validated_business_identity(task)
    validate_task_instruction(task['instruction'])
    validate_plan({'tasks': [task]})
    validate_m4_task(task)
    return task
