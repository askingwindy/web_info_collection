"""Observed stopwatch controls and bounded functional-development workflow.

Initial observations establish controls only. The six-action proposal is not a
collector task: running/paused states, lap rendering, and synchronized capture
must be observed before a production compiler can bind their assertions.
"""
import re
from urllib.parse import urlsplit

ADAPTER_ID = 'lddgo-stopwatch-widget-1'
STRATEGY_ID = 'stopwatch-two-stage-laps-v1'
URI = 'https://www.lddgo.net/common/stopwatch'


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


def elapsed_milliseconds(text):
    """Parse the format documented on the observed page, without rounding."""
    if not isinstance(text, str):
        raise ValueError('Stopwatch elapsed text must be a string')
    match = re.fullmatch(r'(?:(\d{2,}):)?([0-5][0-9]):([0-5][0-9])\.([0-9]{3})', text)
    if not match:
        raise ValueError('Unsupported stopwatch elapsed format')
    hours, minutes, seconds, millis = match.groups()
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


STOPWATCH_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.lddgo.net/common/stopwatch')return empty;
 const id='lddgo-stopwatch-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=s=>document.querySelectorAll(s).length===1?document.querySelector(s):null;
 const visible=e=>{if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
  const r=e.getBoundingClientRect(),hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
  return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!hit&&(hit===e||e.contains(hit));};
 const group=one('[lay-filter="stopwatchForm"]'),clock=one('#countDownString'),ticks=one('#tickContainer'),last=one('#lastTick');
 if(!group||group.localName!=='div'||!clock||!ticks||!last||!group.contains(clock)||!group.contains(ticks)||!ticks.contains(last))
  return fail('Stopwatch grouping or display containers changed');
 if(document.title!=='在线秒表计时器'||!visible(clock)||clean(clock.innerText)!=='00:00.000'||clean(ticks.innerText)||ticks.children.length!==1)
  return fail('Stopwatch requires its visible pristine zero-time and empty lap state');
 const fields=[],expected=[['startStopwatch','开始'],['startCount','计次'],['startDownload','下载'],['startReset','重置']];
 const controls=[...group.querySelectorAll('input,textarea,select,button,[contenteditable=true]')];
 if(controls.length!==expected.length)return fail('Stopwatch control set changed');
 for(const [name,label] of expected){const el=one('#'+name);
  if(!el||!group.contains(el)||el.localName!=='button'||el.disabled||!visible(el)||clean(el.innerText)!==label)
   return fail('Stopwatch control role, label or viewport visibility changed');
  fields.push({selector:'#'+name,tag:'button',type:el.type,label,visible:true,enabled:true,value:''});}
 const startText=one('#startText');
 if(!startText||!one('#startStopwatch').contains(startText)||clean(startText.innerText)!=='开始')
  return fail('Stopwatch toggle label binding changed');
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'在线秒表计时器',fields,
  container_selector:'[lay-filter="stopwatchForm"]',display_selector:'#countDownString',display_text:'00:00.000',
  lap_container_selector:'#tickContainer',lap_container_text:'',lap_child_selectors:['#lastTick'],
  toggle_text_selector:'#startText',functional_validation:'NOT_RUN'}],
  result_targets:[{selector:'#countDownString',text:'00:00.000',visible:true,business_label:'秒表累计计时'},
   {selector:'#tickContainer',text:'',visible:false,business_label:'秒表计次记录'}],widget_rejections:[]};
}'''


def stopwatch_proposal(capability, page, widget, strategy_version):
    """Return necessary diagnostic actions; do not invent a production oracle."""
    if not all(matches_uri(uri) for uri in (capability['site_uri'], page['page_uri'], widget.get('page_uri', ''))):
        raise ValueError('Stopwatch requires its exact observed URI')
    if (page.get('title'), widget.get('kind'), widget.get('adapter_id'), widget.get('label')) != (
            '在线秒表计时器', 'non-form-widget', ADAPTER_ID, '在线秒表计时器'):
        raise ValueError('Stopwatch page and widget business context changed')
    expected = {'#startStopwatch':'开始', '#startCount':'计次', '#startDownload':'下载', '#startReset':'重置'}
    fields = widget.get('fields', [])
    if len(fields) != len(expected) or {x.get('selector') for x in fields} != set(expected):
        raise ValueError('Stopwatch requires exactly its four observed controls')
    for field in fields:
        if (field.get('tag'), field.get('label'), field.get('visible'), field.get('enabled')) != (
                'button', expected[field['selector']], True, True) or field.get('type') not in ('button', 'submit'):
            raise ValueError('Stopwatch control identity, role or visibility changed')
    for key, value in {'container_selector':'[lay-filter="stopwatchForm"]', 'display_selector':'#countDownString',
                       'display_text':'00:00.000', 'lap_container_selector':'#tickContainer',
                       'lap_container_text':'', 'lap_child_selectors':['#lastTick'],
                       'toggle_text_selector':'#startText'}.items():
        if widget.get(key) != value:
            raise ValueError('Stopwatch pristine-state binding changed: ' + key)
    results = page.get('result_targets', [])
    for selector, text, label in (('#countDownString','00:00.000','秒表累计计时'), ('#tickContainer','','秒表计次记录')):
        targets = [item for item in results if item.get('selector') == selector]
        if len(targets) != 1 or (targets[0].get('text'), targets[0].get('business_label')) != (text,label):
            raise ValueError('Stopwatch result target missing or ambiguous')
        if selector == '#countDownString' and targets[0].get('visible') is not True:
            raise ValueError('Stopwatch initial clock must be visibly zero')
    stages = [('start-first-stage','#startStopwatch','开始第一段计时'),
              ('record-first-stage','#startCount','结束并保留第一条分段计时'),
              ('pause-break','#startStopwatch','暂停计时以排除中场休息'),
              ('resume-second-stage','#startStopwatch','休息后继续第二段计时'),
              ('record-second-stage','#startCount','结束并保留第二条分段计时'),
              ('pause-final','#startStopwatch','暂停并核对总计时和已结束的两条分段记录')]
    return {'schema_version':'stopwatch-development-proposal',
        'status':'FUNCTIONAL_VALIDATION_REQUIRED', 'executable_production_task':False,
        'page_uri':URI, 'widget_adapter':ADAPTER_ID,
        'goal':'用在线秒表记录两段练习：第一段结束计次并暂停休息，休息后继续第二段，结束后再次计次并暂停，核对已结束的两条分段记录、当前段余量和总计时。',
        'operations':[{'operation_id':name,'action_type':'click','selector':selector,'goal':goal}
                      for name,selector,goal in stages],
        'effective_page_actions':6, 'waits_are_effective_actions':False,
        'required_functional_evidence':['Actual running and paused toggle labels',
            'Actual lap-row selectors, ordering, index and elapsed-time text',
            'Clock increases while running and remains unchanged during an observed pause',
            'Two completed positive lap records and current-segment remainder remain visible with final paused state',
            'Unmodified collector capture and verify_execution_state behavior while running and paused'],
        'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,
            'business_goal':'排除休息时间的两阶段秒表分段计次','observed_roles':['开始','计次','下载','重置'],
            'assurance':'Initial controls only; no functional success, production readiness, or quality acceptance inferred'}}
