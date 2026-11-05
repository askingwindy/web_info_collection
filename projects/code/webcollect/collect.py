"""M2 可审查的真实采集器：保留原始证据，结构通过也不自动通过人工验收。"""
import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time
from urllib.parse import urldefrag
from zoneinfo import ZoneInfo
from .browser import EvidenceStale, capture, execute, prepare_action, observe, verify_execution_state, CONTROL, POINTER, SNAPSHOT_JS
from .scaffold import program_version
from .storage import allocate, write_json, verify_existing_registry
from .validate import validate_sample, read_json, SCHEMAS, StrictValidator
from .content_preparation import assess_content, preparation_settings
from .task_instruction import validate_task_instruction
from .action_normalization import normalize_delivery_step


def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


async def capture_complete(page, evidence, selector=None, index=0, assertions=None, protected_selectors=None):
    """Refresh only a stale completion candidate; never replay an action.

    No formal frame/companion/narrative is published here. Every candidate
    keeps the complete capture and unchanged assertions/fingerprint checks.
    """
    protection={'protected_selectors':protected_selectors} if protected_selectors else {}
    started=time.monotonic()
    timing={'policy':'complete-full-refresh-1','started_at':now(),'attempt_limit':3,
            'timeout_seconds':12,'quiet_window_ms':1000,'retry_wait_ms':250,
            'natural_wait_requested_ms':0,'natural_wait_observed_ms':0.0,'attempts':[]}

    async def natural_wait(milliseconds):
        at=time.monotonic()
        timing['natural_wait_requested_ms']+=milliseconds
        try:await asyncio.sleep(milliseconds/1000)
        finally:timing['natural_wait_observed_ms']+=(time.monotonic()-at)*1000

    def reject_candidate(number, observation, attempt):
        folder=Path(evidence)/'terminal_candidates';folder.mkdir(exist_ok=True)
        image=folder/f'candidate_{number:03}.png';record=folder/f'candidate_{number:03}.json'
        with image.open('xb') as stream:stream.write(observation['png'])
        with record.open('x',encoding='utf-8') as stream:
            json.dump({'diagnostic_only':True,'accepted_as_formal_frame':False,
                'state':observation['state'],'capture':observation['capture'],'attempt':attempt,
                'rejection':attempt.get('rejection'),
                'natural_wait_requested_ms':timing['natural_wait_requested_ms'],
                'natural_wait_observed_ms':timing['natural_wait_observed_ms']},stream,ensure_ascii=False,indent=2)
            stream.write('\n')
        return {'path':str(record),'sha256':hashlib.sha256(record.read_bytes()).hexdigest(),
                'image_path':str(image),'image_sha256':hashlib.sha256(observation['png']).hexdigest()}

    async def refresh():
        for number in range(1,4):
            attempt={'attempt':number,'started_at':now()};timing['attempts'].append(attempt)
            try:
                observation=await capture(page,selector,index,assertions=assertions,**protection)
            except EvidenceStale as error:
                from .batch_core import save_json
                folder=Path(evidence)/'terminal_candidates';folder.mkdir(exist_ok=True)
                save_json(folder/('capture-rejection-'+str(number)+'.json'),{'diagnostic_only':True,
                    'action_executed':False,'capture':getattr(error,'capture',None)})
                if number==3:raise
                await natural_wait(250)
                continue
            attempt['screenshot_sha256']=observation['capture']['screenshot_sha256']
            try:
                attempt['assertions']=await assert_state(page,assertions or [],
                    captured_state=observation['state'],captured_png=observation['png'],**protection)
            except Exception as error:
                attempt.update(status='assertion_rejected',reason=str(error),finished_at=now())
                attempt['diagnostic']=reject_candidate(number,observation,attempt)
                raise
            await natural_wait(1000)
            try:
                preflight=await verify_execution_state(page,observation['state'],selector,index,assertions=assertions,**protection)
            except EvidenceStale as error:
                attempt.update(status='stale_rejected',reason=str(error),finished_at=now(),rejection=getattr(error,'capture',None))
                attempt['diagnostic']=reject_candidate(number,observation,attempt)
                if number==3:raise
                await natural_wait(250)
                continue
            attempt.update(status='accepted',state_preflight=preflight,finished_at=now())
            return observation

    try:
        observation=await asyncio.wait_for(refresh(),timeout=12)
    except Exception as error:
        timing.update(finished_at=now(),elapsed_seconds=time.monotonic()-started,accepted=False)
        error.terminal_refresh=timing
        raise
    timing.update(finished_at=now(),elapsed_seconds=time.monotonic()-started,accepted=True)
    observation['terminal_refresh']=timing
    return observation


async def capture_before_action(page, evidence, selector=None, index=0, **options):
    """One total caller-controlled deadline for capture and verification; no actions."""
    started=time.monotonic()
    budget=float(options.pop('timeout',12))
    if budget <= 0:raise ValueError('Action evidence timeout must be positive')
    timing={'timeout_seconds':budget,'stage':'capture','attempts':[],
            'action_executed':False,'started_at':time.time()}
    def remaining():return max(.001,budget-(time.monotonic()-started))
    async def bounded_refresh():
        for number in range(1,4):
            observation=None
            attempt={'attempt':number};timing['attempts'].append(attempt)
            try:
                timing['stage']='capture';phase=time.monotonic()
                try:observation=await capture(page,selector,index,timeout=remaining(),**options)
                finally:attempt['capture_seconds']=time.monotonic()-phase
                timing['stage']='verify_execution_state';phase=time.monotonic()
                try:observation['action_state_preflight']=await verify_execution_state(page,observation['state'],selector,index,timeout=remaining(),**options)
                finally:attempt['verification_seconds']=time.monotonic()-phase
                return observation
            except EvidenceStale as error:
                from .batch_core import save_json
                folder=Path(evidence)/'action_candidates';folder.mkdir(exist_ok=True)
                import uuid
                name=str(uuid.uuid4())
                save_json(folder/(name+'.json'),{'attempt':number,'diagnostic_only':True,
                    'action_executed':False,'rejection':getattr(error,'capture',None),
                    'capture':observation['capture'] if observation else None,
                    'state':observation['state'] if observation else None})
                if observation:
                    with (folder/(name+'.png')).open('xb') as stream:stream.write(observation['png'])
                if number==3:raise
                timing['stage']='stale_retry_wait'
                await asyncio.sleep(.25)
    try:
        observation=await asyncio.wait_for(bounded_refresh(),timeout=budget)
    except Exception as error:
        timing.update(elapsed_seconds=time.monotonic()-started,accepted=False,
                      error_type=type(error).__name__,error_message=str(error))
        error.action_refresh=timing
        raise
    timing.update(elapsed_seconds=time.monotonic()-started,accepted=True,stage='complete')
    observation['action_refresh']=timing
    observation['action_deadline_monotonic']=started+budget
    return observation


def chinese_ratio(text):
    letters=[character for character in text if character.isalpha()]
    han=sum(0x3400<=ord(character)<=0x9fff or 0xf900<=ord(character)<=0xfaff or
            0x20000<=ord(character)<=0x323af for character in letters)
    return han/len(letters) if letters else 0


def verify_public_url(url, allowed_hosts=None):
    from urllib.parse import urlsplit
    import ipaddress
    parsed=urlsplit(url)
    host=(parsed.hostname or '').lower()
    if parsed.scheme not in {'http','https'} or not host or parsed.username or parsed.password:
        raise ValueError('真实采集只接受不含账号信息的 HTTP(S) 网站地址')
    if host=='localhost' or host.endswith(('.localhost','.local','.invalid')):
        raise ValueError('本地或联调地址不能声明为真实公开站点')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:raise ValueError('私网或回环地址不能声明为真实公开站点')
    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValueError('实际页面跳转到了任务计划之外的站点：'+host)
    return host


def check_numbers(text, spec):
    import re
    from decimal import Decimal
    values=[Decimal(token) for token in re.findall(r'-?(?:\d+(?:\.\d*)?|\.\d+)',text)]
    return (len(values)==spec['count'] and
            all(Decimal(str(spec['minimum']))<=v<Decimal(str(spec['maximum_exclusive'])) for v in values) and
            (not spec.get('unique') or len(set(values))==len(values)) and
            (not spec.get('integer') or all(v==v.to_integral_value() for v in values)))


async def assert_state(page, conditions, captured_state=None, captured_png=None, protected_selectors=None):
    """Evaluate assertions against one observation, optionally the actual saved frame."""
    from .collect_runtime import CollectionFailure
    protection={'protected_selectors':protected_selectors} if protected_selectors else {}
    if any('visible_text' in condition and set(condition) != {'visible_text'} for condition in conditions):
        raise ValueError('Whole-page visible_text assertion cannot also bind a selector or another predicate')
    if captured_state is None and any('qr_png_payload' in condition or 'placeholder_png_text' in condition for condition in conditions):
        # QR completion cannot be inferred from DOM labels/statistics. Even the
        # early-completion check needs one synchronized, unmodified PNG.
        observation=await capture(page,assertions=conditions,**protection)
        captured_state=observation['state'];captured_png=observation['png']
    observed=captured_state if captured_state is not None else await observe(page,assertions=conditions,**protection)
    targets=observed.get('assertion_targets',[])
    if len(targets)!=len(conditions):raise ValueError('末态观察缺少同步断言目标，不能使用先前页面的结论')
    results=[]
    for index,condition in enumerate(conditions):
        pixel_oracle=None
        if 'visible_text' in condition:
            expected=condition['visible_text']
            if not isinstance(expected,str) or not expected.strip():raise ValueError('可见终态文字断言必须非空')
            actual=observed['visible_text'];passed=expected in actual
            at=actual.find(expected)
            actual=actual[max(0,at-60):at+len(expected)+60] if passed else actual[:160]
            if not passed:raise ValueError('目标文字未在实际视口内显示：'+expected)
        else:
            target=targets[index]
            if not target or target['selector']!=condition['selector'] or target['index']!=condition.get('index',0):
                raise ValueError('任务断言目标不在同步界面树观察中')
            if not target['visible']:raise CollectionFailure('任务断言目标未完整显示在截图视口或被其他元素遮挡','collector')
            displayed = target.get('display_value')
            if (target.get('value') is not None and not any(k in condition for k in ('checked','disabled'))
                    and target.get('value_visible') is False
                    and not ('value' in condition and target['value'] == condition['value']
                             and isinstance(displayed, str) and displayed == condition['value']
                             and displayed != target['value'])):
                # Only text rendered independently of the DOM value (a select's
                # option label differing from its value) can prove visible
                # rendering; an input/textarea display_value is the DOM value
                # itself, so equality with the expected value proves nothing.
                raise CollectionFailure('任务结果控件的完整值未在实际视口中可见，不能以后台值判定完成','collector')
            if 'qr_png_payload' in condition:
                from .qr_strategy import URI,SSID,PASSWORD,wifi_payload
                from .qr_pixel import verify_qr_png
                if (observed.get('url')!=URI or condition!={'selector':'#rnqr-qrCanvas','qr_png_payload':wifi_payload(SSID,PASSWORD)}):
                    raise ValueError('QR pixel oracle is limited to its exact observed page and synthetic WiFi payload')
                if captured_png is None:raise ValueError('QR completion requires the original synchronized PNG, not DOM-only state')
                try:
                    pixel_oracle=await asyncio.to_thread(verify_qr_png,captured_png,condition['qr_png_payload'],target['bbox'],
                                                        viewport=observed['screen_resolution'])
                except ValueError as error:
                    error.qr_png=captured_png;error.qr_state=observed
                    raise
                actual=pixel_oracle['decoded'][0]['payload'];passed=pixel_oracle['passed']
            elif 'placeholder_png_text' in condition:
                from .placeholder_strategy import URI,IMAGE_SELECTOR
                from .placeholder_pixel import verify_placeholder_png
                image=target.get('placeholder_image')
                if (observed.get('url')!=URI or condition!={'selector':IMAGE_SELECTOR,'placeholder_png_text':'预览图'} or
                    not isinstance(image,dict) or image.get('complete') is not True or
                    (image.get('natural_width'),image.get('natural_height'))!=(400,200)):
                    raise ValueError('Placeholder requires exact page, decoded 400x200 PNG and Chinese task text')
                if captured_png is None:raise ValueError('Placeholder completion requires original synchronized PNG pixels')
                try:
                    pixel_oracle=await asyncio.to_thread(verify_placeholder_png,captured_png,condition['placeholder_png_text'],
                                                        target['bbox'],image['src'],viewport=observed['screen_resolution'])
                except ValueError as error:
                    error.placeholder_png=captured_png;error.placeholder_state=observed
                    raise
                actual=pixel_oracle['recognized_text'];passed=pixel_oracle['passed']
            elif 'html_table_matrix' in condition:
                from .html_table_strategy import (URI, TABLE_SELECTOR, EXPECTED_MATRIX,
                                                   verify_synchronized_table_result)
                if (observed.get('url')!=URI or condition!={'selector':TABLE_SELECTOR,'html_table_matrix':EXPECTED_MATRIX}):
                    raise ValueError('HTML table oracle is limited to its exact observed page and requested matrix')
                evidence=target.get('html_table_evidence')
                actual=evidence.get('matrix') if isinstance(evidence,dict) else None
                passed=verify_synchronized_table_result(evidence)
            elif 'checked' in condition:
                actual=target['checked'];passed=actual is condition['checked'] and actual is not None
            elif 'disabled' in condition:
                actual=target['disabled'];passed=actual is condition['disabled']
            elif 'time_seconds' in condition:
                import re
                actual=target['text'].strip()
                match=re.fullmatch(r'(\d{2}):(\d{2}):(\d{2})',actual)
                seconds=sum(int(value)*factor for value,factor in zip(match.groups(),[3600,60,1])) if match else -1
                spec=condition['time_seconds']
                passed=bool(match) and int(match.group(2))<60 and int(match.group(3))<60 and spec['minimum']<=seconds<=spec['maximum']
            elif 'numbers' in condition:
                actual=target['value'] if target['value'] is not None else target['text']
                passed=check_numbers(actual,condition['numbers'])
            elif 'number' in condition:
                from decimal import Decimal,InvalidOperation
                actual=target['value'] if target['value'] is not None else target['text'].strip()
                try:passed=Decimal(actual)==Decimal(str(condition['number']))
                except InvalidOperation:passed=False
            elif 'value' in condition:
                actual=target['value'];passed=actual==condition['value']
            else:
                actual=target['value'] if target['value'] is not None else target['text']
                passed=condition['contains'] in actual
        row={'expected':condition,'actual':actual,'passed':passed,
             'evidence_source':'captured_frame_DOM_observation' if captured_state is not None else 'single_visible_DOM_observation'}
        if pixel_oracle is not None:
            row.update(evidence_source='original_saved_png_pixels',pixel_oracle=pixel_oracle)
        if 'selector' in condition:
            row['target_text']=targets[index]['target_text']
            display=targets[index]['display_value']
            if targets[index].get('value_visible') is True and isinstance(display,str) and display.strip():
                row['display_actual']=display
        results.append(row)
        if not passed:raise ValueError('任务结果断言未通过：'+json.dumps(row,ensure_ascii=False))
    return results


def visible_reference(text):
    if len(text)<=40:return '「'+text+'」'
    return '以「'+text[:12]+'」开头的文字'


def observed_excerpt(text):
    """Keep a complete observed sentence, or the complete available text block."""
    import re
    compact=re.sub(r'\s+',' ',text).strip()
    # Some source pages use 。 inside geographic/decimal numbers. Cutting
    # between numeric characters produces a false complete quotation.
    def boundary(value):
        for match in re.finditer(r'[。！？]',value):
            i=match.start()
            if (value[i]=='。' and value[:i].rstrip()[-1:].isdigit() and
                    value[i+1:].lstrip()[:1].isdigit()):
                continue
            return match.end()
        return None
    end=boundary(compact)
    if end is None:return compact
    first=compact[:end]
    # Closing punctuation belongs to the observed sentence, not the next one.
    while len(first)<len(compact) and compact[len(first)] in '”’」』）》】)':
        first+=compact[len(first)]
    # A short yes/no answer is meaningful only with its following explanation.
    if len(re.findall(r'[\u4e00-\u9fff]',first))<4:
        following=compact[len(first):];end=boundary(following)
        if end is not None:return first+following[:end]
    return first


def completion_from_assertions(assertions):
    """Describe verified terminal facts, never unexecuted plan history."""
    if not assertions or any(row.get('passed') is not True for row in assertions):
        raise ValueError('缺少全部通过的实际末态证据，不能生成完成判断')
    facts=[]
    for row in assertions:
        condition=row['expected'];actual=row['actual'];display=row.get('display_actual')
        # Older observations recorded HTMLButtonElement.value == '' as a
        # display string. Its actual visible text remains the grounded fact.
        if display is None or isinstance(display,str) and not display.strip():display=actual
        if 'visible_text' in condition and condition['visible_text'] in actual:
            facts.append('可见文字「'+condition['visible_text']+'」')
        elif 'contains' in condition and condition['contains'] in actual:
            facts.append('结果中可见「'+condition['contains']+'」' if condition['contains'] in str(display) else '结果显示「'+str(display)+'」')
        elif 'value' in condition and actual==condition['value']:
            facts.append('控件显示「'+str(display)+'」')
        elif 'checked' in condition:
            facts.append(('「'+row['target_text']+'」' if row.get('target_text') else '末态控件')+('已勾选' if actual else '未勾选'))
        elif 'disabled' in condition:
            facts.append(('「'+row['target_text']+'」' if row.get('target_text') else '末态控件')+('不可用' if actual else '可用'))
        elif any(key in condition for key in ('number','numbers','time_seconds')):
            if actual is None or not str(actual).strip():
                raise ValueError('实际数值证据为空，不能用计划期望补写完成判断')
            facts.append('末态'+('时间' if 'time_seconds' in condition else '数值')+'为「'+str(display)+'」')
        elif 'html_table_matrix' in condition:
            if actual!=condition['html_table_matrix'] or not isinstance(actual,list) or not actual or not actual[0]:
                raise ValueError('实际表格矩阵缺失或与通过断言不一致')
            rows=['第'+str(index+1)+'行为'+'、'.join('「'+value+'」' for value in values)
                  for index,values in enumerate(actual)]
            facts.append(str(len(actual))+'行'+str(len(actual[0]))+'列表格，'+'，'.join(rows))
        elif 'qr_png_payload' in condition:
            if actual!=condition['qr_png_payload'] or row.get('pixel_oracle',{}).get('passed') is not True:
                raise ValueError('二维码完成描述缺少原PNG独立解码证据')
            facts.append('原图二维码解码为「'+actual+'」')
        elif 'placeholder_png_text' in condition:
            oracle=row.get('pixel_oracle',{})
            if actual!=condition['placeholder_png_text'] or oracle.get('passed') is not True:
                raise ValueError('占位图完成描述缺少原PNG独立文字证据')
            facts.append('原图中'+str(oracle['image_width'])+'×'+str(oracle['image_height'])+'图片显示「'+actual+'」')
        else:
            raise ValueError('末态断言类型无法形成可核验的完成描述')
    return '最终视口已核对：'+'、'.join(dict.fromkeys(facts))+'。'


def visible_numeric_context(state):
    """Bind displayed results to their visible labels/columns, never input values."""
    import re
    lines=[text.strip() for text in state.get('visible_text','').splitlines() if text.strip()]
    elements=state.get('elements',[]);contexts=[]
    for at,label in enumerate(lines):
        if label=='结果':
            # Preserve numeric-only readouts when their visible heading supplies
            # context. Bare counters elsewhere are not calculation evidence.
            values=[]
            for item in lines[at+1:]:
                if not re.fullmatch(r'[-+]?\d+(?:\.\d+)?',item):break
                values.append(item)
            if 2<=len(values)<=8:
                contexts.append('「结果」之后显示数值'+ '、'.join('「'+value+'」' for value in values))
        if label in {'输出结果','计算结果'} and at+1<len(lines):
            result=lines[at+1]
            witnessed=any(e.get('text')==result and not e.get('clickable') and not e.get('inputable')
                and e.get('element_type')=='text' for e in elements)
            if witnessed and re.fullmatch(r'[-+\d.\s,，]+',result) and len(re.findall(r'-?\d+(?:\.\d+)?',result))>=2:
                contexts.append(f'{label}为「{result}」')
        if re.fullmatch(r'(?:当前.{0,8}值|.{1,8}范围)[：:]',label):
            values=[]
            for item in lines[at+1:]:
                if not re.fullmatch(r'[-+\d.]+|%|[A-Za-z]+',item):break
                values.append(item)
            if values and any(re.search(r'\d',item) for item in values):
                contexts.append(label+' '.join(values))
    # The synchronized tree supplies column geometry; every label and value
    # must also occur in this very frame's clipped visible text.
    headers=[e for e in elements if e.get('native_role')=='th' and e.get('text') in lines and e.get('bbox')]
    cells=[e for e in elements if e.get('native_role')=='td' and e.get('text') in lines and e.get('bbox')]
    groups={}
    for cell in cells:groups.setdefault(cell['bbox'][1],[]).append(cell)
    rows=[]
    for top,cells_in_row in sorted(groups.items()):
        preceding=[h for h in headers if h['bbox'][1]<top]
        if not preceding:continue
        header_top=max(h['bbox'][1] for h in preceding)
        row_headers=sorted([h for h in preceding if h['bbox'][1]==header_top],key=lambda h:h['bbox'][0])
        if len(row_headers)<2 or len(cells_in_row)!=len(row_headers):continue
        pairs=[]
        for head in row_headers:
            matches=[c for c in cells_in_row if abs(c['bbox'][0]-head['bbox'][0])<=2 and abs(c['bbox'][2]-head['bbox'][2])<=2]
            if len(matches)!=1:break
            pairs.append('「'+head['text']+'」='+'「'+matches[0]['text']+'」')
        if len(pairs)==len(row_headers):rows.append('，'.join(pairs))
    if rows:contexts.append('可见表格行包括'+ '；'.join(rows[:4]))
    return '；'.join(contexts)


def visible_paragraph_context(state, goal, before=None):
    """Select actual prose blocks; goals select evidence but supply no prose."""
    import re
    lines=[text.strip() for text in state.get('visible_text','').splitlines() if text.strip()]
    paragraphs=[]
    headings=[e for e in state.get('elements',[]) if e.get('native_role')=='h1' and e.get('bbox')]
    if not headings:
        stem=state.get('title','').split(' - ',1)[0]
        headings=[e for e in state.get('elements',[]) if e.get('native_role')=='span'
                  and e.get('text')==stem and stem in lines and e.get('bbox')
                  and e['bbox'][3]-e['bbox'][1]>=24]
    column_x=(headings[0]['bbox'][0]+headings[0]['bbox'][2])/2 if headings else None
    content_top=headings[0]['bbox'][3] if headings else None
    blocks={b.get('element_id'):b for b in state.get('text_blocks',[]) if isinstance(b,dict)}
    for element in state.get('elements',[]):
        text=element.get('text','')
        if element.get('native_role') not in {'p','li'} or len(re.findall(r'[\u4e00-\u9fff]',text))<8:continue
        box=element.get('bbox')
        if content_top is not None and box and box[3]<=content_top:continue
        if column_x is not None and box and not box[0]<=column_x<=box[2]:continue
        block=blocks.get(element.get('element_id'))
        if block and block.get('visible_text'):
            if 'complete_sentences' in block:
                complete=[sentence for sentence in block['complete_sentences']
                          if len(re.findall(r'[\u4e00-\u9fff]',sentence))>=8 and
                          not re.search(r'记者.{0,20}摄|图片来源|图源[：:]|资料图',sentence)]
                if complete:
                    paragraphs.extend(complete)
                    continue
            body=block['visible_text'].strip()
            if block.get('starts_visible') is False:
                boundary=re.search(r'[。！？]',body)
                if not boundary:continue
                body=body[boundary.end():].lstrip('”’」』）》】) \n')
            if len(re.findall(r'[\u4e00-\u9fff]',body))<8:continue
            if block.get('ends_visible') is False and not re.search(r'[。！？]',body):continue
            excerpt=observed_excerpt(body)
            if not re.search(r'记者.{0,20}摄|图片来源|图源[：:]|资料图',body):
                paragraphs.append(excerpt)
            continue
        # A p's own text omits inline links. Locate its observed opening and
        # closing in the separately captured reading-order text instead.
        prefix=text.split()[0][:24] if text.split() else ''
        starts=[i for i,line in enumerate(lines) if len(prefix)>=3 and line.startswith(prefix)]
        if len(starts)!=1:continue
        start=starts[0];suffix=text.split()[-1]
        ends=[i for i in range(start,len(lines)) if len(suffix)>=2 and lines[i].endswith(suffix)]
        if not ends:continue
        body=' '.join(lines[start:ends[0]+1])
        body=re.sub(r'\[\s*\d+\s*\]','',body)
        body=re.sub(r'\s+',' ',body).strip()
        paragraphs.append(body)
    # Some layouts render paragraph/list text in child spans while the block
    # container is not emitted as a separate tree element. The observer's
    # clipped text block remains useful only when its literal text also occurs
    # in this frame's independently captured visible reading order.
    known_ids={e.get('element_id') for e in state.get('elements',[])}
    observed=re.sub(r'\s+','',state.get('visible_text',''))
    for block in blocks.values():
        if block.get('element_id') in known_ids:continue
        complete=block.get('complete_sentences',[])
        candidates=complete or ([block.get('visible_text','')]
            if block.get('starts_visible') is True and block.get('ends_visible') is True else [])
        for body in candidates:
            if (len(re.findall(r'[\u4e00-\u9fff]',body))>=8
                    and re.sub(r'\s+','',body) in observed
                    and not re.search(r'记者.{0,20}摄|图片来源|图源[：:]|资料图',body)):
                paragraphs.append(body)
    paragraphs=list(dict.fromkeys(paragraphs))
    if re.search(r'末段|末尾|最后(?:一)?段',goal) and paragraphs:return paragraphs[-1]
    previous=re.sub(r'\s+','',(before or {}).get('visible_text',''))
    new=[body for body in paragraphs if re.sub(r'\s+','',body) not in previous]
    candidates=new or paragraphs
    compact_goal=re.sub(r'核对|查证|查阅|阅读|当前|页面|正文|指定|确认|所需|实际|内容|可见|任务|完成|返回|目录|选择|下一|章节','',goal)
    goal_words=set(re.findall(r'(?=([\u4e00-\u9fff]{2}))',compact_goal))
    scored=[(sum(word in body for word in goal_words),index,body) for index,body in enumerate(candidates)]
    if scored and max(row[0] for row in scored)>0:
        return max(scored,key=lambda row:(row[0],-row[1]))[2]
    return observed_excerpt((new or paragraphs)[0]) if paragraphs else None


def main_content_image(state):
    """Real image geometry only; never infer a subject or OCR from alt text."""
    headings=[e for e in state.get('elements',[]) if e.get('native_role')=='h1' and e.get('bbox')]
    if not headings:return None
    x=(headings[0]['bbox'][0]+headings[0]['bbox'][2])/2
    width,height=state.get('screen_resolution',[1280,720])
    candidates=[e for e in state.get('elements',[]) if e.get('native_role')=='img'
        and e.get('bbox') and e['bbox'][0]<=x<=e['bbox'][2]
        and (e['bbox'][2]-e['bbox'][0])*(e['bbox'][3]-e['bbox'][1])>=width*height*.12]
    return max(candidates,key=lambda e:(e['bbox'][2]-e['bbox'][0])*(e['bbox'][3]-e['bbox'][1])) if candidates else None


def visible_navigation_label(state):
    """A document title may select a painted label, never supply its text."""
    lines=[text.strip() for text in state.get('visible_text','').splitlines() if text.strip()]
    stem=state.get('title','').split(' - ',1)[0]
    if stem in lines:return stem
    for element in state.get('elements',[]):
        text=element.get('text','')
        if element.get('native_role')=='h1' and text in lines:return text
    return None


def visible_content_fragments(context, state):
    """Keep separately witnessed fragments instead of quoting a composed string."""
    import re
    observed=re.sub(r'\s+','',state.get('visible_text',''))
    result=[]
    for fragment in (context or '').split('；'):
        fragment=fragment.strip()
        if fragment and re.sub(r'\s+','',fragment) in observed and fragment not in result:
            result.append(fragment)
    return result


def quoted_visible_content(context, state, goal='', before=None):
    fragments=visible_content_fragments(context,state)
    if not fragments:
        paragraph=visible_paragraph_context(state,goal,before)
        fragments=visible_content_fragments(paragraph,state)
    return '；'.join('可见文字「'+fragment+'」' for fragment in fragments)


def visible_section_text(state, label):
    """Take a literal reading-order slice after a witnessed section heading."""
    import re
    lines=[text.strip() for text in state.get('visible_text','').splitlines() if text.strip()]
    positions=[i for i,text in enumerate(lines) if text==label]
    if len(positions)<2:return None
    window=lines[positions[-1]+1:]
    while window and window[0] in {'编辑','完善','隐藏','[',']'}:window=window[1:]
    if not window:return None
    candidate=observed_excerpt(' '.join(window))
    if len(re.findall(r'[\u4e00-\u9fff]',candidate))<8 or not re.search(r'[。！？]',candidate):return None
    return candidate


def observed_frame_description(state, goal='', before=None):
    label=visible_navigation_label(state)
    content=quoted_visible_content(None,state,goal,before)
    if not content:
        import re
        for line in state.get('visible_text','').splitlines():
            line=line.strip()
            if (len(re.findall(r'[\u4e00-\u9fff]',line))>=8 and re.search(r'[。！？]',line)
                    and not re.match(r'^[，。；：、）)]',line) and useful_added_text(line,state)):
                content='可见文字「'+observed_excerpt(line)+'」'
                break
    parts=(['当前可见「'+label+'」'] if label else [])+([content] if content else [])
    if parts:return '，'.join(parts)
    # Browsing fragments legitimately scroll onto viewports holding only formulas,
    # numbers or short labels; quoting those actually-rendered lines stays evidence-
    # bound. Only a viewport with no visible text at all lacks a describable state.
    short=[observed_excerpt(line.strip()) for line in state.get('visible_text','').splitlines()
           if line.strip() and len(line.strip())<=40]
    if short:
        return '可见文字「'+short[0]+'」'+('，另见「'+short[1]+'」' if len(short)>1 else '')
    # Do not turn missing observations into an exportable generic success.
    from .collect_runtime import CollectionFailure
    raise CollectionFailure('NARRATIVE_VISIBLE_EVIDENCE_MISSING: 当前视口没有可绑定的标题或正文，不能生成实际变化说明', 'collector')


def visible_goal_links(state, goal):
    """Use a goal only to select exact, currently visible navigation labels."""
    import re
    labels=re.findall(r'卷[一二三四五六七八九十百零〇\d]+|第[一二三四五六七八九十百零〇\d]+[回篇章]',goal)
    observed=re.sub(r'\s+','',state.get('visible_text',''))
    return list(dict.fromkeys(e['text'] for e in state.get('elements',[])
        if e.get('element_type')=='link' and e.get('text') in labels
        and re.sub(r'\s+','',e['text']) in observed))


def useful_added_text(text, state):
    """Exclude repeated clipped glyphs and search chrome from fallback prose."""
    import re
    han=''.join(re.findall(r'[\u4e00-\u9fff]',text))
    if len(han)>=3 and re.fullmatch(r'(.{1,3})\1{2,}',han):return False
    if text in {'搜索','登录','创建账号','编辑','隐藏','目录','添加列表项'}:return False
    if text.startswith('搜索') and len(text)<=24:return False
    return True


def visible_body_for_label(lines, label, metadata=False, elements=()):
    """A menu label alone is not section evidence; require nearby real prose."""
    import re
    candidates=[]
    positions=[at for at,line in enumerate(lines) if line==label]
    for at in positions if metadata else positions[-1:]:
        window=lines[at+1:]
        levels=[int(e['native_role'][1]) for e in elements
                if re.fullmatch(r'h[1-6]',e.get('native_role','')) and e.get('text')==label]
        level=min(levels) if levels and not metadata else 2
        headings={e['text'] for e in elements if re.fullmatch(r'h[1-6]',e.get('native_role',''))
                  and int(e['native_role'][1])<=level and e.get('text')}
        end=next((i for i,text in enumerate(window) if text in headings),len(window))
        window=window[:end] if not metadata else window[:14]
        prose=next((i for i,text in enumerate(window)
                    if len(re.findall(r'[\u4e00-\u9fff]',text))>=12 and re.search(r'[，。；：]',text)),None)
        if prose is None:continue
        # Short metadata and split inline text before the first substantial
        # paragraph are useful evidence; menu/edit/counter chrome is not.
        prefix=[text for text in window[:prose] if text not in {'编辑','完善','目录','隐藏','参见：','主条目：'}
                and not re.fullmatch(r'\d+条名句|\[|\]|\d+',text)]
        body=observed_excerpt(('；' if metadata else '').join(window[prose:]))
        score=(label in window[prose],len(re.findall(r'[\u4e00-\u9fff]',window[prose])))
        if metadata:
            context='；'.join(prefix[:6]+[body])
        else:
            # Respect the recorded heading/caption blocks, while retaining
            # inline links and references in reading order inside each block.
            boundaries={e['text'] for e in elements if e.get('native_role') in {'h1','h2','h3','h4','h5','h6','figcaption'} and e.get('text')}
            blocks=[];current=[]
            for text in window:
                if text in {'编辑','完善','目录','隐藏','参见：','主条目：'}:continue
                if text in boundaries and current:
                    blocks.append(' '.join(current));current=[]
                current.append(text)
            if current:blocks.append(' '.join(current))
            blocks=[re.sub(r'\[\s*\d+\s*\]','',text) for text in blocks]
            blocks=[text for text in blocks if len(re.findall(r'[\u4e00-\u9fff]',text))>=12]
            context='；'.join(observed_excerpt(text) for text in blocks[:2])
            if not context:continue
        candidates.append((score,context))
    return max(candidates,key=lambda row:row[0])[1] if candidates else None


def visible_result_description(state, before=None):
    """Quote an exposed dialog and its rendered rows, never a finish claim.

    Row boundaries come from the synchronous tree reading order. Only strings
    also present in the clipped visible-text inventory may be narrated.
    """
    elements = state.get('elements', [])
    visible = state.get('visible_text', '')
    old = {e['element_id'] for e in (before or {}).get('elements', [])}
    for dialog in elements:
        if dialog.get('native_role') not in ('dialog', 'alertdialog') or dialog['element_id'] in old:
            continue
        children = {dialog['element_id']}
        for _ in elements:
            added = {e['element_id'] for e in elements if e.get('parent_id') in children}
            if added <= children: break
            children |= added
        rows = [e for e in elements if e['element_id'] in children
                and e.get('text') and e['text'] in visible]
        titles = [e['text'] for e in rows if e.get('native_role') in ('h1', 'h2', 'h3')]
        title = next(iter(titles), dialog.get('text', ''))
        if not title or title not in visible: continue
        cells = [e['text'] for e in rows if e.get('native_role') in ('th', 'td')]
        # Keep every column and reading order, including direction/time pairs.
        detail = '；表格按原顺序可见' + '；'.join('「' + cell + '」' for cell in cells)[:1200] if cells else ''
        return title + '已展开' + detail
    return None


def describe_change(before, after, op, element):
    """Describe observed changes; accessible names are not visible text/value evidence."""
    import re
    action=op['action_type']
    if action=='complete':return '最终页面已确认，'+op['goal']
    # Planned postconditions choose which literal to describe, but only text
    # independently present in this saved frame may become an observation.
    witnessed=list(dict.fromkeys(condition['visible_text'] for condition in op.get('postconditions',[])
        if isinstance(condition,dict) and isinstance(condition.get('visible_text'),str)
        and condition['visible_text'].strip() and condition['visible_text'] in after.get('visible_text','')))
    if witnessed:
        prefix='操作后'
        if before.get('url')!=after.get('url'):
            label=visible_navigation_label(after)
            prefix='页面已切换'+('，当前可见「'+label+'」' if label else '')
        elif action=='scroll':
            prefix='向'+{'down':'下','up':'上','left':'左','right':'右'}[op['arguments']['direction']]+'滚动后'
        return prefix+'，'+ '；'.join('可见文字「'+text+'」' for text in witnessed[:3])
    if op.get('observation') and op.get('postconditions'):return op['observation']
    lines=[text.strip() for text in after.get('visible_text','').splitlines() if text.strip()]
    from urllib.parse import urldefrag,urlsplit
    before_url,before_fragment=urldefrag(before['url']);after_url,after_fragment=urldefrag(after['url'])
    before_parts,after_parts=urlsplit(before_url),urlsplit(after_url)
    paths=(before_parts.path,after_parts.path)
    # A documentation server may canonicalize an extensionless article to
    # .html while following its section link. Only that exact path pair, same
    # origin and unchanged query qualify; matching prose/title across other
    # URLs is never sufficient evidence of same-article navigation.
    html_path_pair=any(html==plain+'.html' and plain.rsplit('/',1)[-1]
        and '.' not in plain.rsplit('/',1)[-1] for plain,html in [paths,paths[::-1]])
    fragment_link=re.fullmatch(r'''a\[href=(["'])#([^"']+)\1\]''',op.get('selector') or '')
    clicked_fragment_link=(action=='click' and fragment_link is not None and fragment_link.group(2)==after_fragment)
    same_canonical_article=(before_parts.scheme in {'http','https'} and
        (before_parts.scheme,before_parts.netloc)==(after_parts.scheme,after_parts.netloc) and
        before_parts.query==after_parts.query and html_path_pair and clicked_fragment_link)
    if (before_url==after_url or same_canonical_article) and before['title']==after['title'] and before_fragment!=after_fragment:
        label=element.get('text','') if element else ''
        # The persistent table-of-contents link alone does not prove that its
        # corresponding heading/body has entered the viewport.
        body=visible_body_for_label(lines,label,elements=after['elements']) if label and lines.count(label)>1 else None
        if not body and len(label.rstrip('… .'))>=5:
            prefix=label.rstrip('… .')
            headings=list(dict.fromkeys(e.get('text','') for e in after['elements']
                if e.get('native_role') in {'h2','h3','h4','h5','h6'} and e.get('text') in lines and e.get('text','').startswith(prefix)))
            if len(headings)==1:
                actual_label=headings[0]
                body=visible_body_for_label(lines,actual_label,elements=after['elements'])
                if body:label=actual_label
        if body:
            section=visible_section_text(after,label)
            content=('可见正文「'+section+'」') if section else quoted_visible_content(body,after,op.get('goal',''),before)
            if content:return f'同一页面定位到「{label}」，'+content
        if label and label in lines:return f'页面链接已定位，当前可见目录项「{label}」'
        return observed_frame_description(after,op.get('goal',''),before)
    if before['title']!=after['title'] or before['url']!=after['url']:
        return '页面已切换，'+observed_frame_description(after,op.get('goal',''),before)

    result = visible_result_description(after, before)
    if result and action in ('click', 'double_click', 'hotkey'):
        return result

    # snapshot elements include accessible labels/title fallbacks. Only the
    # separately captured, clipped visible text may be called visible prose.
    old_text=set(before.get('visible_text','').splitlines())
    visible_added=list(dict.fromkeys(text.strip() for text in after.get('visible_text','').splitlines()
        if text.strip() and text.strip() not in old_text and (re.search(r'[\u4e00-\u9fff]',text) or re.search(r'\d',text))
        and not re.match(r'^w:',text.strip())))
    if action=='scroll':
        direction={'down':'下','up':'上','left':'左','right':'右'}[op['arguments']['direction']]
        links=visible_goal_links(after,op.get('goal',''))
        if links:return f'向{direction}滚动后，当前可见目录项'+ '、'.join('「'+label+'」' for label in links[:2])
        if before['scroll']!=after['scroll']:
            target=re.search(r'包含[「“]?(.+?)[」”]?的',op.get('goal',''))
            observed=re.sub(r'\s+','',after.get('visible_text',''))
            if target and target.group(1) in observed:
                phrase=target.group(1);at=observed.index(phrase)
                context=observed[max(0,at-12):at+len(phrase)+16]
                return f'页面向{direction}滚动，可见目标文字「{phrase}」，邻近正文为「{context}」'
            numeric=visible_numeric_context(after)
            if numeric:return f'页面向{direction}滚动，'+numeric
            # Select task entities only when the very same visible label and
            # substantial adjacent prose exist after scrolling. Goal/expected
            # strings choose evidence; they never supply observed content.
            generic={'作者','分类','体例','简介','信息','介绍','目录','文字','内容','正文','结果','目标','说明','页面','精度','输入','输出','计算','确认'}
            labels=list(dict.fromkeys(line for line in lines
                if 2<=len(line)<=18 and re.fullmatch(r'[\u4e00-\u9fff]+',line)
                and line not in generic and line in op.get('goal','')
                and not any(e.get('text')==line and e.get('element_type') in {'button','input','select'} for e in after['elements'])))
            if re.search(r'课程|公开课|教师|师资',op.get('goal','')):
                course_phrases=[]
                for text in visible_added:
                    phrase=re.split(r'[，。；]',text,1)[0].strip()
                    if (len(phrase)>=6 and not re.match(r'^[，。；：、）)]',phrase)
                            and re.search(r'课程|公开课|考研|托福|雅思|GRE|GMAT|直播|录播|一对一|体验营',phrase)
                            and not re.search(r'https?://|%[0-9a-fA-F]{2}',phrase)):
                        course_phrases.append(phrase)
                if course_phrases:
                    references=[]
                    for text in course_phrases:
                        if len(text)>18 or any(text.count(left)!=text.count(right) for left,right in [('（','）'),('(',')')]):
                            # A clipped course subtitle must not masquerade as
                            # a complete name. Cite an explicit visible prefix,
                            # before an open parenthesis or secondary clause.
                            prefix=re.split(r'[：:·（(，,]',text,1)[0].strip()
                            if len(prefix)>16:
                                prefix=prefix[:16]
                                if '直播' in prefix:prefix=prefix[:prefix.index('直播')+2]
                            prefix=prefix.rstrip(' /-')
                            references.append('以「'+prefix+'」开头的课程文字片段')
                        else:references.append('「'+text+'」')
                    return f'页面向{direction}滚动，课程区域可见'+ '和'.join(list(dict.fromkeys(references))[:2])
            contexts=[(label,visible_body_for_label(lines,label,metadata=True,elements=after['elements'])) for label in labels]
            contexts=[(label,body) for label,body in contexts if body and label in body]
            if contexts:
                observed_contexts=['可见「'+label+'」，'+quoted_visible_content(body,after,op.get('goal',''),before)
                                   for label,body in contexts[:2]]
                if any(observed_contexts):return f'页面向{direction}滚动，'+ '；'.join(text for text in observed_contexts if text)
            paragraph=visible_paragraph_context(after,op.get('goal',''),before)
            paragraph_fragments=visible_content_fragments(paragraph,after)
            if paragraph_fragments:return f'页面向{direction}滚动，'+ '；'.join('可见正文「'+text+'」' for text in paragraph_fragments[:2])
            if main_content_image(after):
                return f'页面向{direction}滚动，主内容区的图片进入当前视口'
            visible_added=[text for text in visible_added if useful_added_text(text,after)]
            long_added=[text for text in visible_added if len(re.findall(r'[\u4e00-\u9fff]',text))>=4]
            numeric_added=[text for text in visible_added if re.search(r'\d',text)
                and not re.fullmatch(r'[-+¥￥$]?\d+(?:\.\d+)?(?:%|元)?',text)
                and not re.search(r'https?://|%[0-9a-fA-F]{2}',text)]
            prose=[text for text in long_added if len(re.findall(r'[\u4e00-\u9fff]',text))>=8 and re.search(r'[，。；：]',text)]
            visible_added=list(dict.fromkeys(prose+long_added+numeric_added)) or [text for text in visible_added if len(re.findall(r'[\u4e00-\u9fff]',text))>=2]
            selected=visible_added[:2]
            return f'页面向{direction}滚动'+('，可见文字包括'+ '和'.join('「'+observed_excerpt(text)+'」' for text in selected[:4]) if selected else '，'+observed_frame_description(after,op.get('goal',''),before))

    def named_values(state):
        elements={e['element_id']:e for e in state['elements']}
        result={}
        for v in state['values']:
            e=elements[v['element_id']]
            if e['element_type'] not in {'input','select'} or v['value'] is None or not e['text']:
                continue
            if v.get('input_type') in {'range','color','file','password','hidden','checkbox','radio','button','submit','reset','image'}:
                continue
            if not v.get('value_visible',v.get('display_value',v['value']) in state.get('visible_text','')):
                continue
            # An editable search combobox is still an input. Its choice flag or
            # DOM identity can change on focus without a selection/value change.
            result[v['element_id']]=(e['text'],v.get('display_value',v['value']),bool(v.get('choice')) and not e['inputable'])
        return result
    old_values=named_values(before)
    new_values=named_values(after)
    focused=next((v for v in after['values'] if v['focused']),None)
    current=next((e for e in after['elements'] if focused and e['element_id']==focused['element_id']),None)
    if action=='click' and element and element['inputable'] and current and current['text']==element['text']:
        label=op.get('evidence',{}).get('target_label') or element.get('text','')
        # A filled input's placeholder is an accessible-name fallback, not
        # painted text. Focus is observed independently; quote only a label
        # actually present in the after frame.
        return f'「{label}」输入框获得焦点' if label and label in after.get('visible_text','') else '输入框获得焦点'

    changed=[]
    for eid,(name,value,choice) in new_values.items():
        previous=old_values.get(eid)
        if previous is None:previous=next((v for v in old_values.values() if v[0]==name),None)
        if previous is not None and previous[:2]==(name,value):continue
        if previous is None and value=='':continue
        label=('「'+name+'」') if name in after.get('visible_text','') else ('控件（可访问名称「'+name+'」）')
        if value=='':changed.append(f'{label}已清空')
        elif choice and previous is not None:changed.append(f'已选择「{value}」')
        else:changed.append(f'{label}显示「{value}」')
    if changed:
        values={value for name,value,choice in new_values.values()}
        controls={e['text'] for e in after['elements'] if e['element_type'] in {'button','input','select'}}
        prose=[text for text in visible_added if text not in controls and text not in values and not text.endswith((':','：'))]
        suffix=('；页面可见'+ '和'.join(visible_reference(text) for text in prose[:2])) if prose and action=='click' and element and element['element_type']=='button' else ''
        return '，'.join(dict.fromkeys(changed))+suffix
    if action in ('click', 'double_click') and element:
        from .react_protocol import control_state_transition
        transition = control_state_transition(before, after, element['element_id'])
        if transition:
            state_text = {'selected':'已选中','checked':'已勾选','unchecked':'已取消勾选',
                          'expanded':'已展开','collapsed':'已收起','focused':'获得焦点'}[transition['state']]
            return '「' + transition['target_text'] + '」所在控件' + state_text
    if action=='hotkey':
        if focused and focused.get('value') and focused.get('selection_start')==0 and focused.get('selection_end')==len(focused['value']):
            return '输入框中的原有内容已全部选中'
        keys=[str(key).lower() for key in op.get('arguments',{}).get('keys',[])]
        previous_focus=next((v for v in before['values'] if v.get('focused')),None)
        if (set(keys) in ({'ctrl','a'},{'meta','a'}) and len(keys)==2 and focused
                and focused.get('value') and previous_focus
                and focused['element_id']==previous_focus.get('element_id')
                and focused['value']==previous_focus.get('value') and current):
            label='「'+current['text']+'」输入框' if current.get('text') in after.get('visible_text','') and current.get('text') else '输入框'
            return f'已在{label}中执行全选快捷键，数值仍为「{focused["value"]}」，输入框保持焦点'
    if element:
        current_element=next((e for e in after['elements'] if e['element_id']==element['element_id']),None)
        states={'selected':'已选中','checked':'已勾选','unchecked':'已取消勾选','expanded':'已展开','collapsed':'已收起'}
        if current_element and current_element['state']!=element['state'] and current_element['state'] in states:
            return f'「{current_element["text"]}」'+states[current_element['state']]
    if action=='click' and element and not any(e['element_id']==element['element_id'] for e in after['elements']):
        return f'「{element["text"]}」已不在当前视口' if element['text'] else '目标控件已不在当前视口'
    numeric=visible_numeric_context(after)
    if action=='click' and numeric and numeric!=visible_numeric_context(before):return '页面显示'+numeric
    if visible_added:return '页面出现的文字包括'+'和'.join(visible_reference(text) for text in visible_added[:3])
    if op.get('observation'):return op['observation']
    if element and element['text'] and element['text'] in after.get('visible_text',''):
        return '页面仍显示「'+element['text']+'」控件'
    return observed_frame_description(after,op.get('goal',''),before)


def validate_plan(plan):
    if not isinstance(plan,dict) or not isinstance(plan.get('tasks'),list) or not plan['tasks']:
        raise ValueError('计划必须包含非空 tasks 数组')
    task_ids=[task.get('task_id') for task in plan['tasks'] if isinstance(task,dict)]
    if len(task_ids)!=len(set(task_ids)):raise ValueError('task_id 必须在计划中唯一')
    required=['task_id','site_uri','site_category','app_name','instruction','task_type','initial_url','operations','final_result','completion_judgement','final_assertions']
    task_type_schema=json.loads(SCHEMAS.joinpath('annotation.schema.json').read_text(encoding='utf-8'))['properties']['task_type']
    for task in plan['tasks']:
        from .react_session import is_react_task
        if is_react_task(task):
            from .react_session import validate_task as validate_react
            validate_react(task)
            validate_task_instruction(task['instruction'])
            type_errors=list(StrictValidator(task_type_schema).iter_errors(task['task_type']))
            if type_errors: raise ValueError('Invalid react task_type')
            verify_public_url(task['initial_url'], {verify_public_url(task['site_uri']), *task.get('allowed_hosts', [])})
            continue
        from .agent_controller import is_controlled, validate_task as validate_controlled
        if is_controlled(task):
            validate_controlled(task)
            validate_task_instruction(task['instruction'])
            type_errors=list(StrictValidator(task_type_schema).iter_errors(task['task_type']))
            if type_errors: raise ValueError('Invalid controlled task_type')
            verify_public_url(task['initial_url'], {verify_public_url(task['site_uri']), *task.get('allowed_hosts', [])})
            continue
        from .fragment_workflow import is_fragment
        if not isinstance(task,dict) or any(not task.get(k) for k in required if k!='final_assertions' or not is_fragment(task)):raise ValueError('任务计划缺少必要字段')
        type_errors=list(StrictValidator(task_type_schema).iter_errors(task['task_type']))
        if type_errors:
            raise ValueError('task_type 不符合合同枚举：'+str(task['task_id'])+'：'+type_errors[0].message)
        validate_task_instruction(task['instruction'])
        preparation_settings(task)
        site_host=verify_public_url(task['site_uri'])
        verify_public_url(task['initial_url'],{site_host,*task.get('allowed_hosts',[])})
        if not isinstance(task['operations'],list):raise ValueError('operations 必须为数组')
        for op in task['operations']:
            if not isinstance(op,dict) or not all(op.get(k) for k in ['action_type','goal','rationale','expected']):
                raise ValueError('每步必须包含动作、目标、依据、预期')
            if op['action_type'] in CONTROL and not op.get('selector'):raise ValueError('控件动作必须有原始定位依据')
        if sum(op['action_type'] not in ('wait','complete') for op in task['operations'])<5:
            raise ValueError('M2 任务至少规划 5 个显式有效操作，不允许通过等待凑步')
        if sum(op['action_type'] not in ('wait','complete') for op in task['operations'])>10:
            raise ValueError('采集任务最多规划 10 个必要有效操作；试点与交付共用 5-10 步口径')
        if any(op['action_type']=='complete' for op in task['operations']):raise ValueError('complete 由最终断言成功后添加，不得提前声明完成')
    from .task_contract import validate_m4_plan
    if any('task_admission' in task for task in plan['tasks']):
        from .task_contract import PLAN_SCHEMA
        if plan.get('schema_version') != PLAN_SCHEMA:
            raise ValueError('Reviewed task admission requires the versioned M4 plan contract')
    validate_m4_plan(plan)
    from .production_identity import validate_plan as validate_pilot_plan
    validate_pilot_plan(plan)


def task_protected_selectors(task):
    """Protect future result surfaces without evaluating their assertions early."""
    conditions = list(task.get('final_assertions', []))
    conditions += list(task.get('initial_preconditions', []))
    conditions += [condition for operation in task.get('operations', [])
                   for condition in operation.get('postconditions', [])]
    return sorted({condition['selector'] for condition in conditions
                   if isinstance(condition, dict) and isinstance(condition.get('selector'), str)
                   and condition['selector'].strip()})


async def collect_one(context, task, directory, evidence, ids, *, navigation=None, controller_factory=None):
    from .task_contract import (is_m4_task, validate_m4_task, completion_decision,
                                terminal_evidence, narrative_evidence, canonical_sha)
    m4=is_m4_task(task)
    if m4:validate_m4_task(task)
    protected_selectors=task_protected_selectors(task)
    protection={'protected_selectors':protected_selectors} if protected_selectors else {}
    directory=Path(directory);evidence=Path(evidence)
    (directory/'images').mkdir(parents=True)
    (directory/'ui_tree').mkdir()
    evidence.mkdir(parents=True)
    from .agent_controller import is_controlled
    controlled = is_controlled(task)
    controller = None
    if controlled:
        if controller_factory is None:
            raise ValueError('Controlled fragment requires original ledger controller factory')
        controller = controller_factory(task, evidence/'controller')
    page=await context.new_page()
    page.set_default_timeout(15000)
    dialogs=[]
    page.on('dialog',lambda dialog:dialogs.append({'type':dialog.type,'message':dialog.message}))
    operations=task['operations']+[{'action_type':'complete','arguments':{'status':'success'},
                'goal':'确认最终页面符合任务要求','rationale':task['completion_judgement'],'expected':task['final_result']}]
    steps=[];previous=None;raw_records=[];ground_truth=[];ratios=[]
    contract_result=None
    task_identity={'task_id':task.get('task_id'),'task_version':task.get('task_version'),
                   'task_sha256':canonical_sha({k:v for k,v in task.items() if not k.startswith('_')})} if m4 else None
    if m4:checkpoint_json(evidence/'task_contract.json',{'schema_version':'webcollect-task-contract-evidence-1',
            **task_identity,'machine_status':'IN_PROGRESS','semantic_status':'REVIEW_REQUIRED'})
    settings=preparation_settings(task)
    preparation={'schema_version':'content-preparation-v1',
                 'mode':'disabled' if settings['mode']=='off' else 'enabled',
                 'settings':settings,'decisions':[]}
    planned_index=0;preparation_actions=0;preparation_scrolls=0
    pending_preparation=None;attempted_preparation=set()
    prepared_locations=set()
    checkpoint_json(evidence/'preparation_decisions.json',preparation)
    try:
        if navigation is None:
            await page.goto(task['initial_url'],wait_until='domcontentloaded',timeout=30000)
        else:
            await navigation.goto(page, task['initial_url'], purpose='collection:' + ids['sample_id'])
        await page.wait_for_timeout(task.get('initial_settle_ms',1000))
        write_json(evidence/'initial_navigation.json',{'url':page.url,'timestamp':now(),'task_initial_state':True})
        from .workflow_normalization import assert_initial_state
        initial_proof = await assert_initial_state(page, task)
        if initial_proof is not None:
            write_json(evidence/'initial_preconditions.json',initial_proof)
        while controller is not None or planned_index<len(operations):
            i=len(steps)+1
            op=(await controller.next(page, assertions=raw_records[-1]['operation'].get('postconditions',[]) if raw_records else [])
                if controller else operations[planned_index])
            operation_origin='planned'
            completion_trigger='planned_final'
            if op['action_type']!='complete' and task.get('stop_when_final',True):
                try:
                    await assert_state(page,task['final_assertions'],**protection)
                except ValueError:
                    pass
                else:
                    if not m4 or completion_decision(task,raw_records,op)=='complete':
                        op=operations[-1]
                        completion_trigger='goal_already_satisfied'
            # Advice is read-only. The chosen action still goes through the
            # same capture, target truth, native execution and next-frame chain.
            location_key=None
            try:
                # Fragments share a reading position; a same-URL reload is a
                # new document and must earn readiness again. Read only.
                epoch=await asyncio.wait_for(page.evaluate('performance.timeOrigin'),timeout=15)
                location_key=(urldefrag(page.url)[0],epoch)
                assessment_operation={**op,'preserve_reading_position':location_key in prepared_locations}
                assessment=await assess_content(page,task,assessment_operation)
                assessment['document_identity']={'url_without_fragment':location_key[0],
                                                 'performance_time_origin':epoch}
            except Exception as assessment_error:
                # A failed observer must still retain the first available
                # pre-action frame, not click/scroll or lose the landing state.
                assessment={'schema_version':'content-preparation-assessment-1',
                    'page_url':page.url,'settings':settings,
                    'decision':{'action':'blocked','reason':'正文与广告判断失败：'+str(assessment_error)},
                    'observer_error':str(assessment_error)}
            decision=assessment['decision']
            if settings['mode']!='off' and decision['action'] in {'ready','not_applicable'} and not assessment.get('obstruction',{}).get('present'):
                prepared_locations.add(location_key)
            decision_id=f'D{len(preparation["decisions"])+1:04}'
            preparation_error=None
            same_planned_close=False
            planned_scroll_distance=(op.get('execution') or {}).get('distance',480)
            same_planned_scroll=(decision['action']=='scroll_to_content' and planned_index==0
                and op['action_type']=='scroll' and op.get('arguments',{}).get('direction')=='down'
                and type(planned_scroll_distance) is int
                and decision['distance']<=planned_scroll_distance<=480)
            if decision['action']=='close_overlay' and op['action_type']=='click' and op.get('selector'):
                same_planned_close=await page.evaluate('''({first,second,index})=>{
                    try{return document.querySelector(first)===document.querySelectorAll(second)[index||0];}
                    catch{return false;}
                }''',{'first':decision['selector'],'second':op['selector'],'index':op.get('index',0)})
            if op['action_type']!='complete' and decision['action'] in {'close_overlay','scroll_to_content'} and not (same_planned_close or same_planned_scroll):
                operation_origin='preparation'
                if decision['action']=='close_overlay':
                    op={'action_type':'click','selector':decision['selector'],'index':0,'arguments':{},
                        'goal':'关闭遮挡目标内容的可选推广层','rationale':'当前视口可见可正常关闭的推广遮罩，先关闭后继续原任务',
                        'expected':'推广遮罩关闭，原页面目标内容可见','execution':{'settle_ms':700}}
                else:
                    op={'action_type':'scroll','arguments':{'direction':'down'},
                        'goal':'向下定位当前页面的正文内容','rationale':'当前页面正文位于视口下方，分段滚动使正文进入视口',
                        'expected':'正文段落进入视口并可阅读',
                        'execution':{'distance':decision['distance'],'settle_ms':700}}
                signature=(assessment['page_url'],decision['action'],decision.get('selector'),
                           assessment.get('scroll_y',assessment.get('viewport',{}).get('scroll_y')))
                if decision['action']=='close_overlay' and signature in attempted_preparation:
                    preparation_error='同一推广关闭动作已经执行，遮挡仍在；停止重复点击'
                if preparation_actions>=settings['max_actions']:
                    preparation_error='页面准备动作达到上限，目标仍未就绪'
                if op['action_type']=='scroll' and preparation_scrolls>=settings['max_scrolls']:
                    preparation_error='正文定位滚动达到上限，目标仍未就绪'
                attempted_preparation.add(signature)
            elif op['action_type']!='complete' and decision['action']=='blocked':
                preparation_error='页面准备被阻断：'+decision['reason']
            is_final=op['action_type']=='complete'
            from .production_identity import before_action
            before_action(task, raw_records, op['action_type'])
            assertion=[]
            planned_completion=None
            if is_final:
                # Planned prose is audit input, never proof of navigation or
                # earlier reading. Every emitted final fact uses passed checks.
                planned_completion={'final_result':task['final_result'],
                    'completion_judgement':task['completion_judgement'],'operation':op}
            previous_conditions=(raw_records[-1]['operation'].get('postconditions',[])
                                 if m4 and raw_records else [])
            capture_conditions=previous_conditions+(task['final_assertions']
                if is_final or op.get('completion_view') else [])
            observation=await (capture_complete(page,evidence,op.get('selector'),op.get('index',0),
                                                assertions=capture_conditions or None,**protection) if is_final else
                               capture_before_action(page,evidence,op.get('selector'),op.get('index',0),assertions=capture_conditions or None,**protection))
            if controller and not is_final:
                op = controller.rebind(op, observation)
                if op is None: continue
            state=observation['state']
            if previous_conditions:
                previous_state={**state,'assertion_targets':state['assertion_targets'][:len(previous_conditions)]}
                postconditions=await assert_state(page,previous_conditions,captured_state=previous_state,
                    **({'captured_png':observation['png']} if any('qr_png_payload' in c or 'placeholder_png_text' in c for c in previous_conditions) else {}))
                raw_records[-1]['postconditions_saved_frame']={'assertions':postconditions,
                    'binding':{'image_path':f'images/step_{i:03}.png','ui_tree_path':f'ui_tree/step_{i:03}.json',
                               'screenshot_sha256':observation['capture']['screenshot_sha256']}}
                # The action record was already saved. Bind later-frame evidence
                # in an append-only companion instead of rewriting the original.
                previous_raw=evidence/f"step_{raw_records[-1]['step_id']:03}.json"
                write_json(evidence/f"step_{raw_records[-1]['step_id']:03}_postconditions.json",
                    {'source_step_id':raw_records[-1]['step_id'],
                     'source_raw_sha256':hashlib.sha256(previous_raw.read_bytes()).hexdigest(),
                     **raw_records[-1]['postconditions_saved_frame']})
            if is_final:
                final_assertion_state={**state,'assertion_targets':state.get('assertion_targets',[])[len(previous_conditions):]}
                assertion=await assert_state(page,task['final_assertions'],captured_state=final_assertion_state,
                    **({'captured_png':observation['png']} if any('qr_png_payload' in c or 'placeholder_png_text' in c for c in task['final_assertions']) else {}))
                from .fragment_workflow import is_fragment
                final_description=(observed_frame_description(state, task['instruction'])
                    if is_fragment(task) else completion_from_assertions(assertion))
                heading=next((e['text'] for e in state['elements'] if e.get('native_role')=='h1' and e.get('text')), '')
                final_goal=('确认本段结束页面' if is_fragment(task) else '确认最终页面')+('「'+heading+'」' if heading else '')+'，'+final_description
                op={**op,'goal':final_goal,'rationale':final_description,'expected':final_description}
            if i==1:
                (evidence/'initial_capture.png').write_bytes(observation['png'])
                write_json(evidence/'initial_capture.json',{'policy':'content-preparation-v1',
                    'state':state,'capture':observation['capture'],'first_step_id':1,'pre_action':True,
                    'settings':settings,'page_url':state['url']})
            if pending_preparation is not None:
                pending_preparation.update(after_step_id=i,after_image_sha256=observation['capture']['screenshot_sha256'])
                pending_preparation=None
            entry={'decision_id':decision_id,'before_step_id':i,
                   'before_image_sha256':observation['capture']['screenshot_sha256'],
                   'kind':decision['action'],'assessment':assessment,
                   'planned_operation_index':planned_index,'operation_origin':operation_origin,
                   'performed_by_planned_close':same_planned_close,
                   'performed_by_planned_scroll':same_planned_scroll}
            if operation_origin=='preparation':
                entry.update(intent_step_id=i,action_executed=False)
            preparation['decisions'].append(entry)
            checkpoint_json(evidence/'preparation_decisions.json',preparation)
            image_path=f'images/step_{i:03}.png'
            (directory/image_path).write_bytes(observation['png'])
            tree={'image_path':image_path,'screen_resolution':state['screen_resolution'],'elements':state['elements']}
            write_json(directory/f'ui_tree/step_{i:03}.json',tree)
            if task.get('require_public_origin'):
                verify_public_url(state['url'],{verify_public_url(task['site_uri']),*task.get('allowed_hosts',[])})
            from .production_quality import require_public_task_state
            require_public_task_state(state)
            ratios.append(chinese_ratio(state['visible_text']))
            if preparation_error:
                entry['blocked_reason']=preparation_error
                checkpoint_json(evidence/'preparation_decisions.json',preparation)
                write_json(evidence/'preparation_failure.json',{'policy':'content-preparation-v1','reason':preparation_error,
                    'step_id':i,'decision_id':decision_id,'action_executed':False,
                    'state':state,'capture':observation['capture'],
                    'screenshot_sha256':observation['capture']['screenshot_sha256']})
                raise ValueError(preparation_error)
            if assessment['page_url']!=state['url']:
                raise ValueError('正文判断后页面地址改变，停止使用过期准备判断')
            if op.get('completion_view'):
                from .task_admission import validate_live_completion_scroll
                completion_view_state={**state,
                    'assertion_targets':state.get('assertion_targets',[])[len(previous_conditions):]}
                completion_view_proof=validate_live_completion_scroll(task,op,completion_view_state)
                write_json(evidence/f'completion_view_{i:03}.json',{
                    **completion_view_proof,'screenshot_sha256':observation['capture']['screenshot_sha256'],
                    'image_path':image_path,'ui_tree_path':f'ui_tree/step_{i:03}.json'})
            if previous:
                previous['step_result']=describe_change(raw_records[-1]['state'],state,raw_records[-1]['operation'],raw_records[-1]['target_element'])
                if m4:
                    observed_result,narrative=narrative_evidence(previous['step_result'],raw_records[-1]['state'],state,raw_records[-1]['operation'])
                    narrative['after_frame']={'image_path':image_path,'screenshot_sha256':observation['capture']['screenshot_sha256']}
                    raw_records[-1]['narrative_evidence']=narrative
                    original=evidence/f"step_{raw_records[-1]['step_id']:03}.json"
                    write_json(evidence/f"step_{raw_records[-1]['step_id']:03}_narrative.json",
                        {'source_step_id':raw_records[-1]['step_id'],
                         'source_raw_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
                         **narrative})
                    if observed_result is None:
                        raise ValueError('NARRATIVE_EVIDENCE_UNSUPPORTED: 本步结果包含未绑定的引用或待审核占位文案，保留证据并停止保存成功样本')
                    previous['step_result']=observed_result
                previous['tool_result']['return_value']['screen_changed']=raw_records[-1]['capture']['screenshot_sha256']!=observation['capture']['screenshot_sha256']
            arguments,element=prepare_action(state,op)
            controller_dispatch = (controller.before_dispatch(op,state,
                {'path':str((directory/image_path).resolve()),'sha256':observation['capture']['screenshot_sha256']})
                if controller else None)
            from .production_identity import state_allowed
            state_allowed(task, state)
            action={'action_type':op['action_type'],'target_element_id':element['element_id'] if element else '',
                    'target_text':element['text'] if element else (op.get('key_name','+'.join({'meta':'Command','ctrl':'Ctrl','enter':'回车键'}.get(key,key.upper()) for key in arguments['keys'])) if op['action_type']=='hotkey' else ''),
                    'coordinate':[arguments['x'],arguments['y']] if op['action_type'] in POINTER else [],
                    'input_text':arguments['text'] if op['action_type']=='type' else '+'.join(arguments['keys']) if op['action_type']=='hotkey' else '',
                    'precondition':op.get('precondition',f'当前页面为「{state["title"]}」'+((f'，可见「{element["text"]}」控件' if element['text'] else '，可见目标控件') if element else '')),
                    'expected_result':op['expected']}
            if element and op.get('evidence',{}).get('observation_protocol')=='webcollect-trusted-observation-1':
                label=op['evidence']['target_label']
                action['precondition']=f'当前页面为「{state["title"]}」，可见「{label}」目标控件'
            if element:action.update(target_bbox=element['bbox'],target_control_type=element['element_type'])
            if op['action_type']=='drag':action['end_coordinate']=[arguments['end_x'],arguments['end_y']]
            step={'step_id':i,'image_path':image_path,'ui_tree_path':f'ui_tree/step_{i:03}.json','page_name':op.get('page_name','网页「'+state['title']+'」'),
                  'user_goal':op['goal'],'action':action,'tool_call':{'tool_name':op['action_type'],'call_id':f'{ids["sample_id"]}_{i:03}',
                    'arguments':arguments,'timestamp':now(),'context':'Web / '+task['app_name']},
                  'tool_result':{'status':'success','return_value':{},'error':''},
                  'next_step_rationale':op['rationale'],'step_result':op['expected'] if is_final else '', 'exception_evidence':[]}
            # Only the delivery annotation uses Windows names. Actual arguments,
            # operation and raw.executed_action below retain native key names.
            step=normalize_delivery_step(step, platform.system())
            raw={'step_id':i,'state':state,'capture':observation['capture'],'operation':op,'target_element':element,
                 'started_at':step['tool_call']['timestamp'],'final_assertions':assertion,
                 'executed_action':{'tool_name':op['action_type'],'arguments':arguments},'completion_trigger':completion_trigger if is_final else None,
                 'operation_origin':operation_origin,'planned_operation_index':planned_index if operation_origin=='planned' else None,
                 'preparation_decision_id':decision_id}
            if controller_dispatch is not None:
                raw['controller_dispatch'] = controller_dispatch
            if planned_completion is not None:
                raw['planned_completion']=planned_completion
                raw['completion_description_source']='passed_final_assertions'
                raw['terminal_refresh']=observation['terminal_refresh']
            if same_planned_close:
                raw['planned_close_preflight']={'matched':True,
                    'close_selector':decision['selector'],'planned_selector':op['selector'],
                    'planned_selector_index':op.get('index',0),
                    'element_id':element['element_id'],'bbox':element['bbox'],
                    'meaning':'Actual DOM nodes compared equal before capture; normal target preflight still required before click.'}
            if same_planned_scroll:
                raw['planned_scroll_preflight']={'matched':True,'direction':'down',
                    'planned_distance':planned_scroll_distance,'requested_preparation_distance':decision['distance'],
                    'decision_id':decision_id,'scroll_before':state['scroll'],
                    'meaning':'First existing planned scroll performs the bounded necessary movement; no duplicate preparation step inserted.'}
            if element:ground_truth.append({'step_id':i,'element_id':element['element_id'],'text':element['text'],'bbox':element['bbox']})
            pages_before=set(context.pages)
            try:
                preflight=await verify_execution_state(page,state,op.get('selector'),op.get('index',0),
                                                       assertions=capture_conditions or None,**protection)
                raw['state_preflight']={**preflight,'checked_at':now()}
                if element:raw['target_preflight']=raw['state_preflight']
                if is_final:
                    raw['final_assertions_binding']={'image_path':image_path,'ui_tree_path':step['ui_tree_path'],
                        'screenshot_sha256':observation['capture']['screenshot_sha256'],
                        'state_fingerprint':preflight['state_fingerprint']}
                    if m4:
                        contract_result=terminal_evidence(task,raw_records,assertion,raw['final_assertions_binding'])
                        raw['task_contract_terminal']={**task_identity,**contract_result}
                    from .production_identity import actual_proof
                    actual_proof(task, raw_records, final_state=state)
                execution=op.get('execution') or {}
                if 'wait_popup' in execution and type(execution['wait_popup']) is not bool:
                    raise ValueError('wait_popup 必须是显式布尔值')
                anchor=None
                if op['action_type']=='click':
                    # Read the real hit target before clicking. Do not use goto,
                    # rewrite target/href, or wait on every unrelated click.
                    anchor=await page.evaluate('''({x,y})=>{
                        const a=document.elementFromPoint(x,y)?.closest('a');
                        if(!a)return null;
                        return {href:a.href,target:a.target||document.querySelector('base[target]')?.target||''};
                    }''',arguments)
                expect_popup=execution.get('wait_popup') is True or bool(anchor and anchor['target'].lower()=='_blank')
                opened_page=None
                if expect_popup:
                    if op['action_type'] not in {'click','double_click','hotkey'}:
                        raise ValueError('该动作不能声明等待弹窗')
                    if execution.get('wait_navigation'):
                        raise ValueError('同一步不能同时声明等待原页面导航与新弹窗')
                    raw['popup_expectation']={'source':'live_anchor_target' if anchor and anchor['target'].lower()=='_blank' else 'plan.execution.wait_popup',
                                              'anchor':anchor,'timeout_ms':30000,'registered_before_action':True}
                    # A new target is not necessarily present in context.pages
                    # before its delayed initial response. Subscribe first.
                    async with page.expect_popup(timeout=30000) as popup:
                        await execute(page,op['action_type'],arguments,execution)
                    opened_page=await popup.value
                    await opened_page.wait_for_load_state('domcontentloaded',timeout=30000)
                else:
                    await execute(page,op['action_type'],arguments,execution)
                if dialogs:raise ValueError('发生未记录的浏览器原生弹窗：'+str(dialogs))
                new_pages=set(context.pages)-pages_before
                if len(new_pages)>1:raise ValueError('一次动作打开多个页面，需单独适配并记录')
                if opened_page is not None and opened_page not in new_pages:
                    raise ValueError('等待到的弹窗已关闭或不在本次真实新增页面中')
                if new_pages:
                    page=opened_page if opened_page is not None else next(iter(new_pages))
                    await page.wait_for_load_state('domcontentloaded')
                    raw['opened_page_url']=page.url
                if op.get('postconditions'):raw['postconditions']=await assert_state(page,op['postconditions'],**protection)
            except Exception as e:
                raw['execution_error']=str(e)
                write_json(evidence/f'step_{i:03}.json',raw)
                if controller:
                    try:
                        controller.result({'path':str((evidence/f'step_{i:03}.json').resolve()),
                            'sha256':hashlib.sha256((evidence/f'step_{i:03}.json').read_bytes()).hexdigest()}, error=str(e))
                    except Exception as stopped:
                        if getattr(e, 'capture', None): stopped.capture = e.capture
                        raise stopped from e
                raise
            if operation_origin=='preparation':
                entry.update(action_step_id=i,action_executed=True)
                checkpoint_json(evidence/'preparation_decisions.json',preparation)
            raw['ended_at']=now()
            write_json(evidence/f'step_{i:03}.json',raw)
            if controller and not is_final:
                controller.result({'path':str((evidence/f'step_{i:03}.json').resolve()),
                    'sha256':hashlib.sha256((evidence/f'step_{i:03}.json').read_bytes()).hexdigest()})
            raw_records.append(raw);steps.append(step);previous=step
            if operation_origin=='preparation':
                preparation_actions+=1
                if op['action_type']=='scroll':preparation_scrolls+=1
                pending_preparation=entry
            else:planned_index+=1
            if is_final:break
        annotation={'sample_id':ids['sample_id'],'task_instruction':task['instruction'],'task_type':task['task_type'],
             'terminal_type':'Web','device_info':{'device_model':'','os_name':'macOS' if platform.system()=='Darwin' else platform.system(),'os_version':(platform.mac_ver()[0] or platform.release()) if platform.system()=='Darwin' else platform.release(),'screen_resolution':state['screen_resolution']},
             'app_info':{'app_name':task['app_name'],'app_version':'','environment':'真实网站 / 隔离浏览器上下文','ui_language':'zh'},
             'risk_level':'normal','trajectory_source':{'source_type':'agent','data_type':'webcollect_agent_v1','action_space':'unified_gui_v4'},
             'steps':steps,'final_state_image':steps[-1]['image_path'],'final_result':final_description,
             'completion_status':'success','completion_judgement':final_description}
        write_json(directory/'annotation.json',annotation)
        if task.get('pilot_identity') is not None:
            from .production_identity import actual_proof
            write_json(evidence/'pilot_identity.json', {**actual_proof(task, raw_records),
                'annotation_sha256':hashlib.sha256((directory/'annotation.json').read_bytes()).hexdigest()})
        if m4:
            contract_result.update(task_identity)
            contract_result['review_binding']={'annotation_sha256':hashlib.sha256((directory/'annotation.json').read_bytes()).hexdigest(),
                'evidence_sha256':{p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                  for folder in ('images','ui_tree') for p in sorted((directory/folder).iterdir()) if p.is_file()}}
            contract_result['narrative_review_required_steps']=[r['step_id'] for r in raw_records
                if r.get('narrative_evidence',{}).get('machine_status')=='REVIEW_REQUIRED']
            checkpoint_json(evidence/'task_contract.json',contract_result)
        write_json(evidence/'ground_truth.json',ground_truth)
        write_json(evidence/'capture_summary.json',{'snapshot_source':'browser_dom','capture_count':len(steps),
              'minimum_chinese_character_ratio':min(ratios),'language_check_version':'page-control-language-consistency-1',
              'chinese_ratio_diagnostic_only':True,'language_review':'pending',
              'chinese_ratio_method':'Han / Unicode letters, deduplicated visible DOM text plus form values; image text needs human review',
              'human_review':'pending','agent_visual_review':'pending','task_id':task['task_id'],
              'preparation_policy':'content-preparation-v1','preparation_actions':preparation_actions,
              'preparation_scrolls':preparation_scrolls})
        return annotation
    except Exception as error:
        if controller and controller.state == 'running':
            controller.state = 'failed'
            controller.event('terminal', category='EXECUTION_FAILED', reason=str(error),
                evidence_preserved=True)
        if getattr(error,'terminal_refresh',None):
            write_json(evidence/'terminal_refresh_failure.json',{'diagnostic_only':True,
                'accepted_as_formal_frame':False,'error':str(error),'terminal_refresh':error.terminal_refresh})
        if getattr(error,'placeholder_png',None) is not None:
            rejected_png=error.placeholder_png
            (evidence/'placeholder_assertion_failure.png').write_bytes(rejected_png)
            write_json(evidence/'placeholder_assertion_failure.json',{'error':str(error),'state':error.placeholder_state,
                'screenshot_sha256':hashlib.sha256(rejected_png).hexdigest(),
                'accepted_as_formal_frame':False,'evidence_source':'rejected_original_synchronized_png'})
        if getattr(error,'qr_png',None) is not None:
            # Preserve the exact rejected pixels, before a later diagnostic
            # screenshot can see a different canvas render.
            rejected_png=error.qr_png
            (evidence/'qr_assertion_failure.png').write_bytes(rejected_png)
            write_json(evidence/'qr_assertion_failure.json',{'error':str(error),'state':error.qr_state,
                'screenshot_sha256':hashlib.sha256(rejected_png).hexdigest(),
                'accepted_as_formal_frame':False,'evidence_source':'rejected_original_synchronized_png'})
        if m4:
            checkpoint_json(evidence/'task_contract.json',{'schema_version':'webcollect-task-contract-evidence-1',
                **task_identity,'machine_status':'FAIL','semantic_status':'REVIEW_REQUIRED','reason':str(error),
                'executed_step_ids':[r['step_id'] for r in raw_records],
                'original_evidence_preserved':True})
        if getattr(error,'capture',None):
            write_json(evidence/'capture_failure.json',{'error':str(error),'capture':error.capture,
                         'diagnostic_only':True,'accepted_as_formal_frame':False})
        try:
            diagnostic=await asyncio.wait_for(capture(page,**protection),timeout=5)
            (evidence/'failure_after.png').write_bytes(diagnostic['png'])
            write_json(evidence/'failure_after.json',{'state':diagnostic['state'],'capture':diagnostic['capture'],'error':str(error)})
        except Exception as diagnostic_error:
            write_json(evidence/'diagnostic_error.json',{'error':str(diagnostic_error),
                         'capture':getattr(diagnostic_error,'capture',None)})
        raise
    finally:
        for at,p in enumerate(list(context.pages)):
            try:await asyncio.wait_for(p.close(),timeout=5)
            except Exception as cleanup_error:
                write_json(evidence/f'page_cleanup_error_{at}.json',{'error':str(cleanup_error),'not_business_success_evidence':True})


def checkpoint_json(path, value):
    import os
    import tempfile
    temporary=None
    try:
        path=Path(path)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.'+path.stem+'-',suffix='.tmp',delete=False) as file:
            temporary=Path(file.name)
            json.dump(value,file,ensure_ascii=False,indent=2,allow_nan=False)
            file.write('\n');file.flush();os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def checkpoint_manifest(output, manifest):
    checkpoint_json(Path(output)/'manifest.json',manifest)


def dynamic_controller_ledger(plan_path, config_path):
    """Open the exact original model ledger a dynamic (react/model) plan bound.

    Resume of a dynamic plan must reuse its original ledger/config: UNKNOWN
    model requests are retained there and never resent through a replacement.
    The plan carries the bound ledger path and config digest; the caller only
    supplies the original config file.
    """
    plan = read_json(Path(plan_path))
    expected = (plan.get('generation') or {}).get('controller_ledger') or {}
    if not expected.get('path'):
        raise ValueError('动态计划未绑定控制器账本路径；严格M4计划续跑无需 --config')
    from .agent_controller import verify_ledger_binding
    from .batch_core import BatchLedger
    ledger = BatchLedger(Path(expected['path']), read_json(Path(config_path)))
    verify_ledger_binding(plan, ledger)
    return ledger


async def collect_plan(plan_path, output, registry, channel='chrome', headless=True,
                       *, publication_path=None, policy_path=None, resume=False,
                       controller_ledger=None):
    from playwright.async_api import async_playwright
    plan=read_json(Path(plan_path));validate_plan(plan)
    if plan.get('schema_version') == 'webcollect-plan-m4-1':
        from .collect_runtime import collect_m4
        return await collect_m4(plan_path, output, registry, publication_path=publication_path,
                                policy_path=policy_path, resume=resume, channel=channel,
                                headless=headless,
                                **({'controller_ledger': controller_ledger} if controller_ledger is not None else {}))
    if publication_path or policy_path or resume:
        raise ValueError('发布收据、预算和恢复入口仅适用于严格M4计划；旧计划保留原采集行为')
    if 'media_preflight' in plan:
        from .preflight import validate_preflight_binding
        validate_preflight_binding(plan,plan_path)
    output=Path(output).resolve();registry=Path(registry).resolve()
    if output.exists():raise FileExistsError('输出批次已存在，拒绝覆盖')
    verify_existing_registry(registry,output.parent)
    output.mkdir(parents=True)
    write_json(output/'plan.json',plan)
    from .production_quality import contract_identity,sha
    repository=Path(__file__).resolve().parents[3]
    contract=contract_identity(repository)
    manifest={'contract_profile':contract,'plan_sha256':sha(plan_path),'preparation_policy':'content-preparation-v1','generator_files_sha256':{name:sha(Path(__file__).parent/name) for name in ['collect.py','browser.py','snapshot.js','production_quality.py','content_preparation.py','content_preparation.js','action_normalization.py']},'batch_id':None,'sample_kind':'real','program_version':program_version(),'rule_version':'1.0.0',
              'configuration':{'viewport':[1280,720],'device_scale_factor':1,'locale':'zh-CN','timezone':'Asia/Shanghai',
                               'channel':channel,'headless':headless,'default_settle_ms':500,'task_interval_seconds':1},
              'sites':[],'samples':[],'collection_status':'in_progress','human_review':'pending','created_at':now()}
    records=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel=channel,headless=headless)
        from importlib.metadata import version
        manifest['browser_version']=browser.version
        manifest['playwright_version']=version('playwright')
        try:
            for task in plan['tasks']:
                ids=allocate(registry,task['site_uri'],task['site_category'],'real',batch_id=manifest['batch_id'])
                manifest['batch_id']=ids['batch_id']
                site={'site_id':ids['site_id'],'uri':task['site_uri'],'site_category':task['site_category']}
                if site not in manifest['sites']:manifest['sites'].append(site)
                manifest['active_task']={**ids,'task_id':task['task_id']}
                manifest['attempts']=records
                checkpoint_manifest(output,manifest)
                sample=output/'samples'/ids['sample_id'];evidence=output/'evidence'/ids['sample_id']
                context=await browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1,locale='zh-CN',timezone_id='Asia/Shanghai')
                try:
                    await collect_one(context,{**task,'require_public_origin':True},sample,evidence,ids)
                    proposed={**manifest,'samples':manifest['samples']+[ids['sample_id']]}
                    report=validate_sample(sample,'delivery',proposed)
                    write_json(evidence/'structural_report.json',report)
                    if not report['structural_pass']:raise ValueError('结构检查不通过：'+str(report['issues']))
                    from .evidence import audit_capture
                    audited=audit_capture(output,ids['sample_id'])
                    write_json(evidence/'capture_audit.json',audited)
                    if not audited['capture_evidence_pass']:raise ValueError('采集证据核对不通过：'+str(audited['issues']))
                    from .production_quality import exact_conflicts
                    roots=[output.parent,*[Path(root) for root in plan.get('dedup_roots',[])]]
                    conflicts=exact_conflicts(sample,roots)
                    write_json(evidence/'producer_dedup.json',{'roots':[str(p) for p in roots],'exact_conflicts':conflicts,'other_routes':'independent_QC_required','not_qualified':True})
                    if conflicts:raise ValueError('跨样本截图重复，保留失败证据并需重新规划：'+str(conflicts))
                    manifest['samples'].append(ids['sample_id'])
                    records.append({**ids,'task_id':task['task_id'],'status':'collected_pending_review'})
                except Exception as e:
                    evidence.mkdir(parents=True,exist_ok=True)
                    write_json(evidence/'failure.json',{'error':str(e),'timestamp':now(),'task_id':task['task_id']})
                    if sample.exists():
                        destination=output/'rejected'/ids['sample_id'];destination.parent.mkdir(exist_ok=True)
                        shutil.move(str(sample),str(destination))
                    records.append({**ids,'task_id':task['task_id'],'status':'rejected','error':str(e)})
                finally:
                    try:await asyncio.wait_for(context.close(),timeout=10)
                    except Exception as cleanup_error:write_json(evidence/'context_cleanup_error.json',{'error':str(cleanup_error),'not_business_success_evidence':True})
                manifest['active_task']=None
                checkpoint_manifest(output,manifest)
                print(json.dumps(records[-1],ensure_ascii=False),flush=True)
                # A bounded pause respects site traffic; no concurrent website jobs.
                await asyncio.sleep(1)
        finally:
            try:await asyncio.wait_for(browser.close(),timeout=10)
            except Exception as cleanup_error:manifest['browser_cleanup_error']=str(cleanup_error)
    manifest['collection_status']='finished_pending_review';manifest['attempts']=records
    checkpoint_manifest(output,manifest)
    if manifest['samples']:
        from .metadata import export_metadata
        export_metadata(output,output/'metadata.csv')
    return {'batch_id':manifest['batch_id'],'collected':len(manifest['samples']),'rejected':len(records)-len(manifest['samples']),
            'qualified_samples':0,'human_review':'pending','output':str(output)}
