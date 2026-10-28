"""真实浏览器只读观察与显式动作执行；不使用 locator 自动滚动或 fill 隐式聚焦。"""
import asyncio
import base64
import hashlib
from importlib.resources import files
import json
import math
import time
import weakref
from pathlib import Path
from PIL import Image
from io import BytesIO

SNAPSHOT_JS=files('webcollect').joinpath('snapshot.js').read_text(encoding='utf-8')
POINTER={'click','double_click','right_click','drag','select','scroll'}
CONTROL={'click','double_click','right_click','drag','select','type'}
_SCREENSHOT_SESSIONS=weakref.WeakKeyDictionary()
_CAPTURE_RETRY_DELAYS=(0.1,0.25,0.5,1.0,1.5,2.0,2.5)
_CAPTURE_WAIT_BUDGET=8.0
_ANIMATION_OBSERVATION_JS=r'''() => {
  const encode=value=>{
    if(typeof value==='number'&&!Number.isFinite(value))return String(value);
    if(Array.isArray(value))return value.map(encode);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,encode(v)]));
    return value;
  };
  const visible=element=>{
    if(!(element instanceof Element))return false;
    if(element.checkVisibility&&!element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
    for(let n=element;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;}
    const r=element.getBoundingClientRect();return r.width>0&&r.height>0&&r.right>0&&r.bottom>0&&r.left<innerWidth&&r.top<innerHeight;
  };
  const animations=[];
  for(const animation of document.getAnimations()){
    const effect=animation.effect,target=effect?.target;if(!visible(target))continue;
    const r=target.getBoundingClientRect();
    animations.push(encode({kind:animation.constructor.name,play_state:animation.playState,pending:animation.pending,
      current_time:animation.currentTime,current_time_type:typeof animation.currentTime,playback_rate:animation.playbackRate,
      start_time:animation.startTime,timing:effect.getTiming(),computed_timing:effect.getComputedTiming(),
      composite:effect.composite,iteration_composite:effect.iterationComposite,pseudo_element:effect.pseudoElement||null,
      keyframes:effect.getKeyframes(),target:{tag:target.localName,id:target.id,rect:{x:r.x,y:r.y,width:r.width,height:r.height}}}));
  }
  return {observed_at_performance_ms:performance.now(),visible_animations:animations,
    read_only:true,occlusion_verified:false,
    scope:'Viewport-intersecting/style-visible native animation timing advice only; no occlusion or capture stability proof. Full-state fingerprint equality remains mandatory.'};
}'''


def _finite_number(value):
    return type(value) in (int,float) and math.isfinite(value)


def _merge_intervals(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if end<=start:continue
        if merged and start<=merged[-1][1]+1e-6:merged[-1][1]=max(merged[-1][1],end)
        else:merged.append([start,end])
    return merged


def _native_animation_window(observation,remaining_ms,required_ms=1000):
    """Prove a common native hold interval; this never certifies a capture."""
    guard=50.0
    horizon=remaining_ms+required_ms+guard*2
    common=[[0.0,horizon]];details=[];unsupported=[]
    for index,animation in enumerate(observation.get('visible_animations',[])):
        detail={'animation_index':index,'target':animation.get('target'),'intervals_relative_ms':[]}
        details.append(detail)
        if animation.get('play_state')!='running' and not animation.get('pending'):
            detail['status']='not_running_no_wait_needed';continue
        timing=animation.get('timing',{});current=animation.get('current_time');rate=animation.get('playback_rate')
        if (animation.get('pending') or animation.get('pseudo_element') or
            not _finite_number(current) or not _finite_number(rate) or rate<=0 or
            not _finite_number(animation.get('start_time'))):
            unsupported.append(index);detail.update(status='unsupported',reason='Pending/pseudo/non-numeric timeline or non-positive rate.');continue
        intervals=[]
        if animation.get('kind')=='CSSTransition':
            end=animation.get('computed_timing',{}).get('endTime')
            if _finite_number(end) and timing.get('direction')=='normal':
                intervals=[[max(0.0,(end-current)/rate),horizon]]
                detail['status']='finite_transition_natural_end'
            else:
                unsupported.append(index);detail.update(status='unsupported',reason='Transition end/direction is not provable.');continue
        else:
            duration=timing.get('duration');delay=timing.get('delay',0)
            if (timing.get('iterations')!='Infinity' or timing.get('direction')!='normal' or timing.get('easing')!='linear' or
                timing.get('iterationStart',0)!=0 or animation.get('composite') not in ['replace','auto'] or
                animation.get('iteration_composite') not in [None,'replace'] or
                not _finite_number(duration) or duration<=0 or not _finite_number(delay) or current<delay):
                unsupported.append(index);detail.update(status='unsupported',reason='Only normal linear replace infinite timing after delay is supported.');continue
            keyframes=animation.get('keyframes',[])
            properties=set().union(*(set(frame)-{'offset','computedOffset','easing','composite'} for frame in keyframes)) if keyframes else set()
            offsets=[frame.get('computedOffset') for frame in keyframes]
            valid=(len(keyframes)>=2 and bool(properties) and all(_finite_number(x) and 0<=x<=1 for x in offsets) and
                   offsets==sorted(offsets) and offsets[0]==0 and offsets[-1]==1 and
                   all(frame.get('composite') in ['auto','replace'] for frame in keyframes))
            if not valid:
                unsupported.append(index);detail.update(status='unsupported',reason='Complete replace keyframes with numeric offsets and actual properties required.');continue
            holds=[]
            for left,right in zip(keyframes,keyframes[1:]):
                if all(key in left and key in right and left[key]==right[key] for key in properties):
                    holds.append([left['computedOffset'],right['computedOffset']])
            holds=_merge_intervals(holds);detail['hold_offsets']=holds;detail['compared_properties']=sorted(properties)
            if not holds:
                unsupported.append(index);detail.update(status='unsupported',reason='No identical-property keyframe interval.');continue
            if holds==[[0,1]]:
                intervals=[[0.0,horizon]]
            else:
                # A short period cannot supply a long hold unless every frame
                # is constant (handled above). Avoid unbounded cycle expansion.
                if duration/rate<required_ms+guard*2:
                    unsupported.append(index);detail.update(status='unsupported',reason='No period is long enough for the required guarded hold.');continue
                cycle=math.floor((current-delay)/duration)
                for iteration in range(cycle-1,cycle+math.ceil(horizon*rate/duration)+3):
                    for start,end in holds:
                        a=(delay+(iteration+start)*duration-current)/rate
                        b=(delay+(iteration+end)*duration-current)/rate
                        if b>0 and a<horizon:intervals.append([a,min(b,horizon)])
                intervals=_merge_intervals(intervals)
                intervals=[[a,b] for a,b in intervals if b-max(0,a)>=required_ms+guard*2]
            if not intervals:
                detail.update(status='no_long_hold_in_current_horizon',reason='Known hold cannot satisfy the current horizon/budget.')
            else:detail['status']='infinite_identical_property_hold'
        # Both hold edges are guarded; a finite transition already ended needs
        # no extra delay. The window is advice only, not semantic acceptance.
        guarded=[[max(0,a+guard) if a>0 else 0,b-guard] for a,b in intervals if b-guard-max(0,a+guard if a>0 else 0)>=required_ms]
        detail['intervals_relative_ms']=guarded
        common=_merge_intervals([[max(a,c),min(b,d)] for a,b in common for c,d in guarded if min(b,d)-max(a,c)>=required_ms])
    if unsupported:
        return {'status':'unsupported','unsupported_animation_indices':unsupported,'details':details,'wait_ms':0,'prediction_is_not_capture_acceptance':True}
    choices=[(max(0,a),b) for a,b in common if b-max(0,a)>=required_ms and max(0,a)<=remaining_ms]
    if not choices:
        return {'status':'no_common_window_within_budget','details':details,'wait_ms':0,'prediction_is_not_capture_acceptance':True}
    start,end=min(choices)
    return {'status':'native_window_predicted' if details else 'no_running_native_animation_wait',
            'wait_ms':start,'common_window_relative_ms':[start,end],'required_hold_ms':required_ms,
            'details':details,'prediction_is_not_capture_acceptance':True}


async def _wait_for_native_window(page,remaining_ms,required_ms):
    result={'observations':[],'requested_wait_ms':0.0,'observed_wait_ms':0.0}
    # Recheck actual native timing after waiting. A prediction is never a
    # substitute for the unchanged before/PNG/after fingerprint comparison.
    for _ in range(2):
        try:observation=await asyncio.wait_for(page.evaluate(_ANIMATION_OBSERVATION_JS),timeout=3)
        except Exception as error:
            result['status']='native_reader_unavailable';result['reader_error']=str(error);return result
        plan=_native_animation_window(observation,max(0,remaining_ms-result['requested_wait_ms']),required_ms)
        result['observations'].append({'native':observation,'plan':plan})
        delay=plan['wait_ms']
        if delay<=0:
            result['status']=plan['status'];return result
        started=time.monotonic();await asyncio.sleep(delay/1000)
        result['observed_wait_ms']+=(time.monotonic()-started)*1000
        result['requested_wait_ms']+=delay
    result['status']='window_recheck_not_confirmed';return result


def fingerprint(state):
    return hashlib.sha256(json.dumps(state,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


async def observe(page, selector=None, index=0, timeout=15, assertions=None):
    """A stalled page must reject its task, never stall the entire batch."""
    try:
        options={'selector':selector,'index':index}
        if assertions:options['assertions']=assertions
        return await asyncio.wait_for(page.evaluate(SNAPSHOT_JS,options),timeout=timeout)
    except asyncio.TimeoutError as error:
        raise TimeoutError(f'页面同步观察超过{timeout}秒，停止该任务并保留检查点') from error


async def viewport_png(page):
    """Capture actual rendered pixels even if an optional web font never settles."""
    try:
        return await page.screenshot(full_page=False,scale='css',timeout=15000),{'method':'playwright_viewport'}
    except Exception as error:
        # Chrome already renders its fallback font while a remote font request
        # remains pending. CDP reads that real surface without editing the DOM,
        # changing font CSS, intercepting requests or fabricating image pixels.
        if 'waiting for fonts to load' not in str(error):raise
        # Keep the read-only session until page/context closure. Detaching an
        # auxiliary CDP session can reset Chrome target emulation/viewport.
        session=_SCREENSHOT_SESSIONS.get(page)
        if session is None:
            session=await page.context.new_cdp_session(page)
            _SCREENSHOT_SESSIONS[page]=session
        metrics=await page.evaluate('({width:innerWidth,height:innerHeight,deviceScaleFactor:devicePixelRatio,mobile:false})')
        # Auxiliary CDP sessions do not inherit Playwright's per-session device
        # metrics. Reassert the SAME observed configuration, never a crop/layout
        # chosen to improve language or quality scores.
        await session.send('Emulation.setDeviceMetricsOverride',metrics)
        viewport=await page.evaluate('({x:scrollX,y:scrollY,width:innerWidth,height:innerHeight,scale:1/devicePixelRatio})')
        result=await session.send('Page.captureScreenshot',{'format':'png','fromSurface':True,'captureBeyondViewport':False,'clip':viewport})
        return base64.b64decode(result['data'],validate=True),{'method':'chrome_rendered_viewport','font_wait_error':str(error),'device_metrics_reasserted':metrics,'font_rendering_policy':'actual browser fallback; no page content or resource modification'}


async def capture(page, selector=None, index=0, retries=8, assertions=None):
    """严格匹配前后 DOM；仅在错配后有界自然等待，不修改页面或暂停动画。

    retries remains the total number of attempts, including when explicitly
    supplied. The backoff requests at most eight seconds of sleep in total;
    screenshot/observation timeouts remain independent and unchanged.
    """
    attempts=[]
    delay_before=0.0
    requested_wait=0.0
    observed_wait=0.0
    recent_capture_ms=0.0
    for attempt_index in range(retries):
        if delay_before:
            wait_started=time.monotonic()
            await asyncio.sleep(delay_before)
            observed_wait+=time.monotonic()-wait_started
            requested_wait+=delay_before
        native_window=await _wait_for_native_window(page,max(0.0,(_CAPTURE_WAIT_BUDGET-requested_wait)*1000),
                                                   max(1000.0,recent_capture_ms+250.0))
        requested_wait+=native_window['requested_wait_ms']/1000
        observed_wait+=native_window['observed_wait_ms']/1000
        started=time.time_ns()
        before=await observe(page,selector,index,**({'assertions':assertions} if assertions else {}))
        try:png,screenshot_evidence=await asyncio.wait_for(viewport_png(page),timeout=25)
        except asyncio.TimeoutError as error:raise TimeoutError('视口截图超过25秒，停止该任务并保留检查点') from error
        after=await observe(page,selector,index,**({'assertions':assertions} if assertions else {}))
        ended=time.time_ns()
        recent_capture_ms=(ended-started)/1e6
        before_fingerprint=fingerprint(before)
        after_fingerprint=fingerprint(after)
        same=before_fingerprint==after_fingerprint
        next_delay=0.0
        if not same and attempt_index+1<retries:
            next_delay=min(_CAPTURE_RETRY_DELAYS[min(attempt_index,len(_CAPTURE_RETRY_DELAYS)-1)],
                           max(0.0,_CAPTURE_WAIT_BUDGET-requested_wait))
        attempts.append({'attempt':attempt_index+1,'started_ns':started,'ended_ns':ended,'dom_stable':same,
                         'delay_before_ms':round(delay_before*1000),'next_retry_delay_ms':round(next_delay*1000),
                         'native_window_wait_ms':round(native_window['requested_wait_ms'],3),
                         'native_window_evidence':native_window,
                         'mismatch_fields':[key for key in sorted(before.keys()|after.keys())
                                            if key not in before or key not in after or before[key]!=after[key]],
                         'before_fingerprint':before_fingerprint,'after_fingerprint':after_fingerprint})
        if same:
            with Image.open(BytesIO(png)) as im:
                if list(im.size)!=before['screen_resolution']:
                    raise ValueError('截图像素分辨率与 DOM 坐标系不一致')
            return {'state':before,'png':png,'capture':{'attempts':attempts,'screenshot_sha256':hashlib.sha256(png).hexdigest(),
                    'natural_wait_requested_ms':round(requested_wait*1000),
                    'natural_wait_observed_ms':round(observed_wait*1000),'natural_wait_budget_ms':8000,
                    'coordinate_space':'screenshot_css_pixels','snapshot_source':'browser_dom',
                    'screenshot':screenshot_evidence,
                    'observer_sha256':hashlib.sha256(SNAPSHOT_JS.encode()).hexdigest()}}
        delay_before=next_delay
    error=ValueError('截图前后页面结构持续变化，拒绝保存不同步界面树')
    # Rejected evidence remains rejected. Callers may preserve this diagnostic
    # alongside their failure checkpoint without treating any PNG as accepted.
    error.capture={'attempts':attempts,'natural_wait_requested_ms':round(requested_wait*1000),
                   'natural_wait_observed_ms':round(observed_wait*1000),'natural_wait_budget_ms':8000}
    raise error


async def verify_execution_state(page, state, selector=None, index=0, assertions=None):
    """Reject any changed captured state before dispatch, including non-control actions."""
    live=await observe(page,selector,index,assertions=assertions)
    if fingerprint(live)!=fingerprint(state):
        changed=[key for key in sorted(live.keys()|state.keys()) if live.get(key)!=state.get(key)]
        raise ValueError('截图后页面状态发生变化，拒绝用陈旧坐标或终态执行：'+','.join(changed))
    return {'matched':True,'state_fingerprint':fingerprint(live),'target':live.get('target')}


def prepare_action(state, operation):
    action=operation['action_type']
    target=state['target']
    parameters=dict(operation.get('arguments',{}))
    element=None
    if action in CONTROL:
        if not target:raise ValueError('目标未出现在当前视口界面树；必须先显式滚动')
        element=next(e for e in state['elements'] if e['element_id']==target['element_id'])
        if not element['enabled']:raise ValueError('目标控件不可用')
        visual_kind=(operation.get('evidence') or {}).get('target_visual_kind','text')
        if visual_kind!='text':
            from .html_table_strategy import validate_visual_target
            validate_visual_target(state,operation)
        expected_label=(operation.get('evidence') or {}).get('target_label')
        if expected_label:
            import re
            compact=lambda text:re.sub(r'\s+','',text)
            labels=target.get('visible_label_evidence',[])
            if not any(compact(expected_label) in compact(row.get('text','')) for row in labels):
                raise ValueError('M4_TARGET_LABEL_UNREADABLE: 目标文字未完整可读；可命中裁切框或无障碍名称不能代替可见标签')
        if action in POINTER:
            if not target['hit_valid']:raise ValueError('目标中心被其他元素遮挡')
            parameters.update(x=target['coordinate'][0],y=target['coordinate'][1])
        if action=='type' and (not target['focused'] or not element['inputable']):
            raise ValueError('type 仅对当前已聚焦的输入控件执行；请先显式点击')
        if action=='type':
            value=next((v for v in state.get('values',[]) if v['element_id']==element['element_id']),{})
            if value.get('input_type') in {'date','time','month','week','datetime-local'}:
                raise ValueError('原生日期时间控件不支持统一 type 的 insert_text 语义；请规划显式按键操作，不以 fill 替代')
    if action=='scroll':
        parameters.setdefault('x',state['screen_resolution'][0]//2)
        parameters.setdefault('y',state['screen_resolution'][1]//2)
    from .validate import StrictValidator, SCHEMAS
    schema=json.loads(SCHEMAS.joinpath('annotation.schema.json').read_text())['properties']['steps']['items']['properties']['tool_call']
    call={'tool_name':action,'call_id':'validation','arguments':parameters,'timestamp':'','context':'Web'}
    errors=list(StrictValidator(schema).iter_errors(call))
    if errors:raise ValueError('执行前统一动作参数不合法：'+errors[0].message)
    width,height=state['screen_resolution']
    for xkey,ykey in [('x','y'),('end_x','end_y')]:
        if xkey in parameters and not (0<=parameters[xkey]<width and 0<=parameters[ykey]<height):
            raise ValueError('执行前发现坐标越界')
        if xkey in parameters and any(frame['bbox'][0]<=parameters[xkey]<frame['bbox'][2] and
            frame['bbox'][1]<=parameters[ykey]<frame['bbox'][3] for frame in state.get('embedded_frames',[])):
            raise ValueError('UNSUPPORTED_FRAME: 动作坐标落在未读取子树的嵌入框内，拒绝执行')
    if action=='hotkey' and any(frame.get('focused') for frame in state.get('embedded_frames',[])):
        raise ValueError('UNSUPPORTED_FRAME: 当前焦点位于嵌入框内，不能向未知子树派发按键')
    return parameters,element


async def _execute_action(page, action, args, execution=None):
    execution=execution or {}
    if action in {'click','double_click','right_click'}:
        await page.mouse.click(args['x'],args['y'],click_count=2 if action=='double_click' else 1,
                               button='right' if action=='right_click' else 'left')
    elif action=='type':
        native_type=await page.evaluate('document.activeElement?.type')
        if native_type in {'date','time','month','week','datetime-local'}:
            raise ValueError('原生日期时间控件不支持统一 type 的 insert_text 语义，不以 fill 替代')
        else:await page.keyboard.insert_text(args['text'])
    elif action=='hotkey':
        keymap={'meta':'Meta','command':'Meta','cmd':'Meta','⌘':'Meta',
                'ctrl':'Control','control':'Control','ctl':'Control','alt':'Alt','option':'Alt','opt':'Alt','⌥':'Alt',
                'shift':'Shift','win':'Meta','windows':'Meta','super':'Meta','enter':'Enter','return':'Enter',
                'escape':'Escape','esc':'Escape','tab':'Tab','backspace':'Backspace','delete':'Delete','del':'Delete',
                'insert':'Insert','ins':'Insert','space':'Space','spacebar':'Space','home':'Home','end':'End',
                'pageup':'PageUp','pgup':'PageUp','pagedown':'PageDown','pgdn':'PageDown',
                'arrowdown':'ArrowDown','down':'ArrowDown','arrowup':'ArrowUp','up':'ArrowUp',
                'arrowleft':'ArrowLeft','left':'ArrowLeft','arrowright':'ArrowRight','right':'ArrowRight',
                'capslock':'CapsLock','numlock':'NumLock','scrolllock':'ScrollLock','pause':'Pause',
                'printscreen':'PrintScreen','contextmenu':'ContextMenu'}
        def native_key(key):
            if key.lower().startswith('f') and key[1:].isdigit() and 1<=int(key[1:])<=24:
                return 'F'+str(int(key[1:]))
            return keymap.get(key.lower(),key)
        await page.keyboard.press('+'.join(native_key(key) for key in args['keys']))
    elif action=='scroll':
        distance=execution.get('distance',480)
        if type(distance) is not int or distance<=0:raise ValueError('滚动距离须为正整数')
        dx,dy={'up':(0,-distance),'down':(0,distance),'left':(-distance,0),'right':(distance,0)}[args['direction']]
        await page.mouse.move(args['x'],args['y'])
        await page.mouse.wheel(dx,dy)
    elif action=='drag':
        await page.mouse.move(args['x'],args['y']);await page.mouse.down()
        await page.mouse.move(args['end_x'],args['end_y'],steps=execution.get('steps',10));await page.mouse.up()
    elif action=='select':
        handle=await page.evaluate_handle('({x,y})=>document.elementFromPoint(x,y)',args)
        element=handle.as_element()
        if not element or await element.evaluate('(node)=>node.tagName')!='SELECT':
            raise ValueError('select 只映射到当前坐标命中的可见原生 select')
        # Unified select is an atomic primitive. It emits real input/change events
        # on the observed native control without inventing an unobserved popup.
        await element.select_option(label=args['option'])
    elif action=='back':await page.go_back(wait_until='domcontentloaded')
    elif action=='open_url':await page.goto(args['url'],wait_until='domcontentloaded')
    elif action=='wait':await page.wait_for_timeout(execution.get('duration_ms',1000))
    elif action=='complete':return
    else:raise ValueError('不支持的 Web 动作 '+action)


async def execute(page, action, args, execution=None):
    execution=execution or {}
    if execution.get('wait_navigation'):
        # Mouse/keyboard APIs do not wait for document navigation. Register the
        # observer before dispatch so assertions never read the departing page.
        async with page.expect_navigation(wait_until='domcontentloaded',timeout=15000):
            await _execute_action(page,action,args,execution)
    else:
        await _execute_action(page,action,args,execution)
    if action!='complete':
        await page.wait_for_timeout(execution.get('settle_ms',500))
