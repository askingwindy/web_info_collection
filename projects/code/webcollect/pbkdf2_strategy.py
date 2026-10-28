"""Observed PBKDF2 form and independent UTF-8 password-key derivation oracle.

The saved crypto workbench passes explicit iterations and a key size measured
in 32-bit words, but leaves the PRF to the loaded CryptoJS default. Callers must
therefore supply a separately observed hash name instead of assuming a library
version. Parameter changes retain one password-key-derivation business identity.
Public fixture text uses the ordinary textarea, not the unrelated masked input.
"""
import hashlib
from urllib.parse import urlsplit

ADAPTER_ID = 'jyshare-pbkdf2-widget-1'
EXECUTION_ID = 'observed-form-result-v1'
EXECUTION_VERSION = 'observed-form-result-1'
BUSINESS_ID = 'password-key-derivation-v1'
STRATEGY_ID = BUSINESS_ID
URI = 'https://www.jyshare.com/crypto/pbkdf2/'
TITLE = 'PBKDF2 在线加密工具 | 菜鸟工具'
PASSWORD = ('公开演示口令素材：社区档案室正在开展旧书整理，参加者先登记书名与数量，再按分类摆放书籍。'
            '请在周六上午到阅读室集合，活动结束时核对清单并归还借阅卡。本段文字只用于演示密钥派生，'
            '不对应任何真实账号或密码。')
SALT = '社区档案公开派生测试盐'
ITERATIONS = 1000
KEY_SIZE_WORDS = 4
HASH_NAME = 'sha256'
LIBRARY_SHA256 = '769a555de553babc35a3338f344dd7aa16260c93cea2c7db290707c90484e7cc'


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


def pbkdf2_hex(password, salt, iterations, key_size_words, *, hash_name):
    """Compute a bounded UTF-8 fixture key without consulting page output.

    ``hash_name`` must come from the actual loaded PBKDF2 implementation. Its
    supported values describe the oracle's arithmetic, not registered variants
    of the workflow. The GUI's key-size values 4/8/16 mean 16/32/64 bytes.
    """
    if (not isinstance(password, str) or not isinstance(salt, str)
            or not password.strip() or not salt.strip()
            or len(password) > 4096 or len(salt) > 128
            or '\x00' in password + salt):
        raise ValueError('PBKDF2 oracle requires bounded nonempty UTF-8 public fixture inputs')
    if type(iterations) is not int or not 1 <= iterations <= 1_000_000:
        raise ValueError('PBKDF2 iterations must be a bounded positive integer')
    if type(key_size_words) is not int or key_size_words not in (4, 8, 16):
        raise ValueError('PBKDF2 key size must be an observed 128/256/512-bit option')
    if hash_name not in ('sha1', 'sha256'):
        raise ValueError('PBKDF2 requires an explicitly observed supported PRF hash')
    return hashlib.pbkdf2_hmac(hash_name, password.encode('utf-8'), salt.encode('utf-8'),
                               iterations, dklen=key_size_words * 4).hex()


PBKDF2_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/crypto/pbkdf2/')return empty;
 const id='jyshare-pbkdf2-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
 const shown=e=>!!e&&e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
 const visible=e=>{if(!shown(e))return false;const r=e.getBoundingClientRect();
  if(r.width<=0||r.height<=0||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)return false;
  const hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);return !!hit&&(hit===e||e.contains(hit));};
 const salt=one('#salt'),message=one('#message_source'),iterations=one('#iterations'),size=one('#key_size');
 const submit=one('#btn-encrypt'),result=one('#hash_result'),hiddenKey=one('#pwd'),params=one('#pbkdf_fields');
 const root=message?.closest('.form-row'),card=root?.closest('.card'),heading=card&&one('.card-header h4',card);
 const badge=card&&one('.card-header .algorithm-badge',card),saltCaption=salt?.closest('.input-group')?.querySelector('.input-group-prepend .input-group-text');
 const iterCaption=iterations?.closest('.input-group')?.querySelector('.input-group-prepend .input-group-text');
 const sizeCaption=size?.closest('.form-group')?.querySelector('label'),paramsCaption=params&&one('h6',params);
 if(document.title!=='PBKDF2 在线加密工具 | 菜鸟工具'||!root||!card||!heading||!badge||
    clean(heading.innerText)!=='PBKDF2 在线加密工具'||clean(badge.innerText)!=='密钥派生'||!visible(heading)||!visible(badge)||
    ![salt,message,iterations,size,submit,result,params].every(e=>!!e&&root.contains(e)))return fail('PBKDF2 exact heading, algorithm and original grouped controls changed');
 const crypto=window.CryptoJS,cfg=crypto?.algo?.PBKDF2?.cfg;
 if(typeof crypto?.PBKDF2!=='function'||!crypto?.algo?.SHA256||!cfg||cfg.hasher!==crypto.algo.SHA256||
    cfg.keySize!==4||cfg.iterations!==250000)return fail('PBKDF2 loaded PRF or implementation defaults are unknown or changed');
 if(!hiddenKey||shown(hiddenKey)||!visible(params)||!visible(paramsCaption)||clean(paramsCaption.innerText)!=='密钥派生参数')
    return fail('PBKDF2 parameter grouping or unrelated hidden masked key control changed');
 if(salt.localName!=='input'||salt.type!=='text'||salt.placeholder!=='请输入盐值'||salt.value!==''||salt.disabled||salt.readOnly||
    !visible(salt)||!visible(saltCaption)||clean(saltCaption.innerText)!=='盐（salt）')return fail('PBKDF2 original empty salt or adjacent visible label changed');
 if(message.localName!=='textarea'||message.placeholder!=='请输入需要加密的字符串'||message.value!==''||message.disabled||message.readOnly||
    message.rows!==6||!visible(message))return fail('PBKDF2 original empty visible password-material textarea changed');
 if(iterations.localName!=='input'||iterations.type!=='number'||iterations.value!=='1000'||iterations.min!=='1'||iterations.disabled||iterations.readOnly||
    !visible(iterations)||!visible(iterCaption)||clean(iterCaption.innerText)!=='迭代次数')return fail('PBKDF2 explicit fixed iteration setting changed');
 const options=[...size.options].map(o=>({value:o.value,label:clean(o.textContent)}));
 if(size.localName!=='select'||size.disabled||size.value!=='4'||!visible(size)||!visible(sizeCaption)||clean(sizeCaption.innerText)!=='密钥长度'||
    JSON.stringify(options)!==JSON.stringify([{value:'4',label:'128 位'},{value:'8',label:'256 位'},{value:'16',label:'512 位'}]))
    return fail('PBKDF2 original 128-bit key length and selectable options changed');
 if(submit.localName!=='button'||submit.type!=='button'||submit.disabled||!visible(submit)||clean(submit.innerText)!=='加密'||
    submit.getAttribute('onclick')!=="CryptoTool.hash('pbkdf2')"||typeof window.CryptoTool?.hash!=='function')return fail('PBKDF2 actual generate control or handler changed');
 const resultCard=result?.closest('.result-card'),captionRow=resultCard?.previousElementSibling;
 const resultCaption=captionRow&&one(':scope > span',captionRow);
 if(!resultCard||!resultCaption||!root.contains(resultCaption)||!visible(resultCaption)||clean(resultCaption.innerText)!=='加密结果')
    return fail('PBKDF2 result must have its original adjacent visible result header');
 const upper=one('#upperText'),info=one('#result-info'),timing=one('#result-time');
 if(!upper||upper.type!=='checkbox'||upper.checked||upper.disabled||!visible(upper)||!info||!timing||
    !root.contains(upper)||!root.contains(info)||!root.contains(timing)||result.localName!=='div'||!visible(result)||
    clean(result.innerText)!=='等待输入…'||result.className!=='placeholder-text'||clean(info.innerText)!=='—'||clean(timing.innerText)!=='')
    return fail('PBKDF2 initial visible result, status or output case changed');
 const editable=[...root.querySelectorAll('input,textarea,select,[contenteditable=true]')].filter(shown);
 if(editable.length!==5||editable.some(e=>![salt,iterations,size,message,upper].includes(e)))return fail('PBKDF2 additional editable settings require a separate registered workflow');
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'PBKDF2 在线加密工具',algorithm:'pbkdf2-hmac-sha256',
  loaded_implementation:{prf:'sha256',default_iterations:250000,default_key_size_words:4},
  fields:[{selector:'#salt',tag:'input',type:'text',label:'请输入盐值',adjacent_label:'盐（salt）',value:'',visible:true,enabled:true,
           value_visible:true,label_source:'visible-placeholder-and-adjacent-salt-label'},
          {selector:'#message_source',tag:'textarea',type:'textarea',label:'请输入需要加密的字符串',value:'',visible:true,enabled:true,
           value_visible:true,label_source:'visible-placeholder'}],
  settings:[{selector:'#iterations',tag:'input',type:'number',label:'迭代次数',value:'1000',min:'1',visible:true,enabled:true,
             label_source:'visible-adjacent-iteration-label'},
            {selector:'#key_size',tag:'select',type:'select-one',label:'密钥长度',value:'4',visible:true,enabled:true,
             label_source:'visible-sibling-key-length-label',options}],
  submit:{selector:'#btn-encrypt',tag:'button',type:'button',label:'加密',visible:true,enabled:true,handler:"CryptoTool.hash('pbkdf2')"},
  output_case:'lowercase',viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY}],
  result_targets:[{selector:'#hash_result',tag:'div',kind:'pbkdf2-result',label:clean(resultCaption.innerText),text:'等待输入…',visible:true}],widget_rejections:[]};
}'''


def _fields():
    return [{'selector': '#salt', 'tag': 'input', 'type': 'text', 'label': '请输入盐值',
             'adjacent_label': '盐（salt）', 'value': '', 'visible': True, 'enabled': True,
             'value_visible': True, 'label_source': 'visible-placeholder-and-adjacent-salt-label'},
            {'selector': '#message_source', 'tag': 'textarea', 'type': 'textarea',
             'label': '请输入需要加密的字符串', 'value': '', 'visible': True, 'enabled': True,
             'value_visible': True, 'label_source': 'visible-placeholder'}]


def _settings():
    return [{'selector': '#iterations', 'tag': 'input', 'type': 'number', 'label': '迭代次数',
             'value': '1000', 'min': '1', 'visible': True, 'enabled': True,
             'label_source': 'visible-adjacent-iteration-label'},
            {'selector': '#key_size', 'tag': 'select', 'type': 'select-one', 'label': '密钥长度',
             'value': '4', 'visible': True, 'enabled': True, 'label_source': 'visible-sibling-key-length-label',
             'options': [{'value': '4', 'label': '128 位'}, {'value': '8', 'label': '256 位'},
                         {'value': '16', 'label': '512 位'}]}]


def validate_observation(capability, page, widget):
    if (not all(matches_uri(uri) for uri in (capability.get('site_uri', ''), page.get('page_uri', ''), widget.get('page_uri', '')))
            or page.get('title') != TITLE or widget.get('kind') != 'non-form-widget'
            or widget.get('adapter_id') != ADAPTER_ID or widget.get('label') != 'PBKDF2 在线加密工具'
            or widget.get('algorithm') != 'pbkdf2-hmac-sha256' or widget.get('viewport') != [1280, 720]
            or widget.get('observed_scroll_y') != 0 or widget.get('output_case') != 'lowercase'
            or widget.get('loaded_implementation') != {'prf': 'sha256', 'default_iterations': 250000, 'default_key_size_words': 4}):
        raise ValueError('PBKDF2 requires exact observed route, initial settings and loaded SHA256 PRF')
    submit = {'selector': '#btn-encrypt', 'tag': 'button', 'type': 'button', 'label': '加密',
              'visible': True, 'enabled': True, 'handler': "CryptoTool.hash('pbkdf2')"}
    result = {'selector': '#hash_result', 'tag': 'div', 'kind': 'pbkdf2-result', 'label': '加密结果', 'text': '等待输入…', 'visible': True}
    targets = [target for target in page.get('result_targets', []) if target.get('selector') == '#hash_result']
    if widget.get('fields') != _fields() or widget.get('settings') != _settings() or widget.get('submit') != submit or targets != [result]:
        raise ValueError('PBKDF2 original visible roles, fixed settings, handler or empty result changed')
    return widget


def _assertions(password, salt):
    return [{'selector': '#hash_result', 'contains': pbkdf2_hex(password, salt, ITERATIONS, KEY_SIZE_WORDS, hash_name=HASH_NAME)},
            {'selector': '#message_source', 'value': password}, {'selector': '#salt', 'value': salt},
            {'selector': '#iterations', 'value': str(ITERATIONS)},
            {'selector': '#key_size', 'value': str(KEY_SIZE_WORDS)}]


def production_operations(password=PASSWORD, salt=SALT):
    assertions = _assertions(password, salt)
    return [
        {'operation_id': 'salt-focus', 'subgoal_id': 'salt', 'action_type': 'click', 'selector': '#salt',
         'evidence': {'target_label': '请输入盐值'}, 'goal': '选中「请输入盐值」输入框',
         'rationale': '定位公开测试盐的必要输入位置', 'expected': '盐值输入框获得焦点'},
        {'operation_id': 'salt-type', 'subgoal_id': 'salt', 'action_type': 'type', 'selector': '#salt',
         'evidence': {'target_label': '请输入盐值'}, 'arguments': {'text': salt}, 'goal': '填写任务给定的公开测试盐',
         'rationale': '密钥派生需要盐值与公开演示口令素材两个输入', 'expected': '盐值输入框完整显示公开测试盐',
         'postconditions': [{'selector': '#salt', 'value': salt}]},
        {'operation_id': 'password-focus', 'subgoal_id': 'password', 'action_type': 'click', 'selector': '#message_source',
         'evidence': {'target_label': '请输入需要加密的字符串'}, 'goal': '选中「请输入需要加密的字符串」输入框',
         'rationale': '定位公开演示口令素材的必要输入位置', 'expected': '公开演示口令素材输入框获得焦点'},
        {'operation_id': 'password-type', 'subgoal_id': 'password', 'action_type': 'type', 'selector': '#message_source',
         'evidence': {'target_label': '请输入需要加密的字符串'}, 'arguments': {'text': password},
         'goal': '填写任务中的完整公开演示口令素材', 'rationale': '公开演示文本是需要派生密钥的密码素材',
         'expected': '普通文本框完整显示任务给定的公开演示素材',
         'postconditions': [{'selector': '#message_source', 'value': password}]},
        {'operation_id': 'generate', 'subgoal_id': 'result', 'action_type': 'click', 'selector': '#btn-encrypt',
         'evidence': {'target_label': '加密'}, 'goal': '点击「加密」并核对「加密结果」',
         'rationale': '用公开演示素材和盐在既定迭代与长度下派生密钥',
         'expected': '加密结果完整显示128位派生密钥的32位十六进制文本',
         'postconditions': assertions, 'execution': {'settle_ms': 3500}}]


def _subgoals():
    return [{'id': 'salt', 'description': '填写公开测试盐', 'evidence': [{'operation_id': 'salt-type', 'postcondition_index': 0}]},
            {'id': 'password', 'description': '填写完整公开演示口令素材', 'evidence': [{'operation_id': 'password-type', 'postcondition_index': 0}]},
            {'id': 'result', 'description': '核对完整可见派生密钥与独立复算', 'evidence': [{'final_assertion_index': 0}]}]


def _business_identity(task):
    return {'schema_version': 'webcollect-business-identity-1', 'business_id': BUSINESS_ID, 'execution_capability_id': EXECUTION_ID,
            'definition': {'business_goal': '从公开演示口令素材与盐派生固定长度密钥',
                           'necessary_input_roles': ['public-password-material', 'public-salt'],
                           'state_path': ['empty-form', 'salt-visible', 'password-material-visible', 'derived-key-visible'],
                           'completion_criterion': 'visible PBKDF2 key equals independent UTF-8 Python oracle'},
            'observation_binding': {'capability_id': task['capability_id'], 'capability_version': task['capability_version']}}


def _instruction(password, salt):
    return ('在「PBKDF2 在线加密工具」中，将公开测试盐填写为「' + salt + '」，将公开演示口令素材填写为「'
            + password + '」，保持迭代次数1000、密钥长度128位，点击「加密」并核对「加密结果」中的完整派生密钥。')


def pbkdf2_spec(capability, page, widget, strategy_version):
    validate_observation(capability, page, widget)
    return {'page_uri': URI, 'widget_adapter': ADAPTER_ID, 'form_label': widget['label'], 'goal': _instruction(PASSWORD, SALT),
            'inputs': [{'selector': '#salt', 'label': '请输入盐值', 'value': SALT},
                       {'selector': '#message_source', 'label': '请输入需要加密的字符串', 'value': PASSWORD}],
            'completion': _assertions(PASSWORD, SALT)[0],
            'deterministic_strategy': {'id': EXECUTION_ID, 'version': strategy_version, 'business_id': BUSINESS_ID,
                                       'business_goal': '从公开演示口令素材与盐派生固定长度密钥',
                                       'operator': 'Python hashlib.pbkdf2_hmac(sha256, password_utf8, salt_utf8, 1000, dklen=16).hex()',
                                       'algorithm': 'pbkdf2-hmac-sha256', 'iterations': ITERATIONS, 'key_size_words': KEY_SIZE_WORDS}}


def validated_business_identity(task):
    if (not all(matches_uri(task.get(k, '')) for k in ('initial_url', 'site_uri'))
            or any(not isinstance(task.get(k), str) or not task[k].strip() for k in ('capability_id', 'capability_version'))
            or task.get('execution_capability') != {'id': EXECUTION_ID, 'version': EXECUTION_VERSION}
            or task.get('business_identity') != _business_identity(task)):
        raise ValueError('PBKDF2 business identity is not bound to its registered observed form')
    try:
        operations = task['operations']
        password, salt = operations[3]['arguments']['text'], operations[1]['arguments']['text']
        assertions = _assertions(password, salt)
        if (operations != production_operations(password, salt) or task.get('final_assertions') != assertions
                or task.get('required_actions') != [op['operation_id'] for op in operations]
                or task.get('subgoals') != _subgoals() or task.get('stop_when_final') is not True
                or task.get('instruction') != _instruction(password, salt)
                or task.get('final_result') != '加密结果区域显示128位派生密钥「' + assertions[0]['contains'] + '」'):
            raise ValueError('PBKDF2 necessary inputs, actions or independent visible result evidence changed')
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError('PBKDF2 operations or terminal evidence are malformed') from error
    strategy = task.get('deterministic_strategy', {})
    if (strategy.get('id') != EXECUTION_ID or strategy.get('business_id') != BUSINESS_ID
            or strategy.get('algorithm') != 'pbkdf2-hmac-sha256' or strategy.get('iterations') != ITERATIONS
            or strategy.get('key_size_words') != KEY_SIZE_WORDS):
        raise ValueError('PBKDF2 execution capability differs from its registered business meaning or fixed settings')
    return task['business_identity']


def compile_pbkdf2(capability, spec, task_version='observed-pbkdf2-compiler-1'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages = [page for page in capability['capabilities'] if page['page_uri'] == URI]
    if len(pages) != 1:
        raise ValueError('PBKDF2 must bind one exact observed page')
    page = pages[0];widgets = [widget for widget in page.get('widgets', []) if widget.get('adapter_id') == ADAPTER_ID]
    if len(widgets) != 1 or pbkdf2_spec(capability, page, widgets[0], spec['deterministic_strategy']['version']) != spec:
        raise ValueError('PBKDF2 specification differs from its observed controls, explicit settings and inputs')
    assertions = _assertions(PASSWORD, SALT);operations = production_operations()
    task = {'task_id': 'pbkdf2-' + object_sha256({'capability': capability['capability_id'], 'spec': spec})[:24],
            'task_version': task_version, 'capability_id': capability['capability_id'], 'capability_version': capability['version'],
            'task_family': 'form-workflow', 'site_uri': URI, 'site_category': capability['site_category'], 'initial_url': URI,
            'app_name': page['title'], 'instruction': spec['goal'], 'task_type': ['填写表单'], 'stop_when_final': True,
            'content_preparation': False, 'operations': operations, 'subgoals': _subgoals(),
            'required_actions': [op['operation_id'] for op in operations], 'final_assertions': assertions,
            'final_result': '加密结果区域显示128位派生密钥「' + assertions[0]['contains'] + '」',
            'completion_judgement': '核对原始末帧中的完整派生密钥与公开演示素材，结果须与独立计算一致。',
            'deterministic_strategy': spec['deterministic_strategy'],
            'execution_capability': {'id': EXECUTION_ID, 'version': EXECUTION_VERSION},
            'capability_screen_status': capability['status'], 'capability_review_required': capability['status'] != 'ready'}
    task['business_identity'] = _business_identity(task)
    validated_business_identity(task);validate_task_instruction(task['instruction']);validate_plan({'tasks': [task]});validate_m4_task(task)
    return task
