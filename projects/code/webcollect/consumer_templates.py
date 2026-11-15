"""Opt-in, same-session templates. No model responses or browser IO are simulated.

The experiment adapter replaces the session class only in its own process. All
actions still use ReactSession's four host tools, probes, raw journal, accounting,
range policy and formal postprocessor. The ordinary consumer imports none of this.
"""
from contextlib import contextmanager
from copy import deepcopy
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urlsplit

from .batch_core import load_json
from .react_session import ReactSession

GOAL_RULE = 'trusted-first-frame-common-goal'
CALCULATOR = 'calculator-fill'
READING = 'encyclopedia-directed-reading'


class Inapplicable(ValueError):
    pass


def shown(element, state):
    box = element.get('bbox', [])
    width, height = state.get('screen_resolution', [0, 0])
    return (element.get('visible') is True and len(box) == 4
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)


def article_element(element_id, state):
    """A visible control/paragraph must belong to the actual article landmark."""
    elements={e['element_id']:e for e in state.get('elements',[])}
    cursor=element_id;seen=set();main=False
    while cursor in elements and cursor not in seen:
        seen.add(cursor);e=elements[cursor];role=e.get('native_role')
        if role in ('nav','navigation','aside','complementary','header','footer','contentinfo'):return False
        if role in ('main','article'):main=True
        cursor=e.get('parent_id')
    binding=next((b for b in state.get('capture_controls',[]) if b['element_id']==element_id),{})
    selector=binding.get('selector','')
    if re.search(r'(?:^| > )(?:nav|aside|header|footer):',selector):return False
    return main or re.search(r'(?:^| > )(?:main|article):',selector) is not None


def article(state):
    url = urlsplit(state['url'])
    slug = unquote(url.path.split('/wiki/', 1)[-1])
    # Namespace pages, portals and indices are not article templates.
    return (url.hostname == 'zh.wikipedia.org' and '/wiki/' in url.path
            and ':' not in slug and any(article_element(b.get('element_id'),state) for b in state.get('text_blocks',[]))
            and re.search('维基百科|維基百科',state.get('title','')+' '+state.get('visible_text','')) is not None)


def label(element):
    return (element.get('text') or '').strip()


def numeric_value(name, old):
    # Deliberately small synthetic example inputs, not financial recommendations.
    if re.search('人数|成人|子女|份额|份數|份数', name): return '1'
    if re.search('月数|月份|月數|工作月', name): return '6'
    if re.search('年数|年數|年龄|年齡', name): return '30'
    if re.search('率|百分比', name): return '5'
    if re.search('收入|薪|金额|金額|遗产|遺產|价值|價值|财产|財產', name): return '50000'
    if old and re.fullmatch(r'\d+(?:\.\d+)?', str(old)):
        return str(float(old) + 1).removesuffix('.0')
    return '100'


def calculator_goal(state):
    if not re.search('计算|計算', state.get('visible_text', '')):
        raise Inapplicable('NO_VISIBLE_CALCULATOR')
    bindings = {b['element_id']: b for b in state.get('capture_controls', [])}
    values = {v['element_id']: v for v in state.get('values', [])}
    fields, choices = [], []
    for e in state.get('elements', []):
        b = bindings.get(e['element_id'], {}); v = values.get(e['element_id'], {})
        if not shown(e, state) or not e.get('enabled'): continue
        if b.get('tag') == 'select':
            display = v.get('display_value')
            if not label(e) or not display: raise Inapplicable('AMBIGUOUS_UNIT_OR_CHOICE')
            choices.append({'label':label(e), 'display':display, 'value':v.get('value'),
                            'selector':b['selector']})
        if e.get('inputable') and not v.get('readonly'):
            if b.get('input_type') != 'number' or not label(e):
                raise Inapplicable('NON_NUMERIC_OR_UNLABELLED_FIELD')
            fields.append({'label':label(e), 'selector':b['selector'],
                           'value':numeric_value(label(e), v.get('value')), 'old_value':v.get('value')})
    if not 1 <= len(fields) <= 4: raise Inapplicable('VISIBLE_NUMERIC_FIELD_COUNT')
    if len({f['label'] for f in fields}) != len(fields): raise Inapplicable('AMBIGUOUS_FIELD_LABEL')
    # Solvers with one deliberately empty unknown need an explicit target.
    if re.search('留空|任意两|任意兩|任意三|未知量', state.get('visible_text','')):
        raise Inapplicable('SOLVER_UNKNOWN_REQUIRES_EXPLICIT_GOAL')
    buttons = [e for e in state.get('elements', []) if shown(e,state)
               and bindings.get(e['element_id'],{}).get('tag') == 'button'
               and re.fullmatch(r'(?:开始|開始)?(?:计算|計算)(?:税额|稅額|奖金|獎金)?',label(e))]
    if len(buttons) != 1: raise Inapplicable('AMBIGUOUS_CALCULATE_BUTTON')
    desc = '在当前计算器使用演示参数：' + '；'.join(f"{f['label']}={f['value']}" for f in fields)
    if choices: desc += '；保留首帧选择：' + '；'.join(f"{c['label']}={c['display']}" for c in choices)
    desc += '。执行一次计算，核对可见结果数值及其单位/税额或奖金名称，不更换参数或计算任务。'
    return {'template':CALCULATOR, 'description':desc, 'fields':fields, 'choices':choices,
            'button_label':label(buttons[0]), 'button_selector':bindings[buttons[0]['element_id']]['selector']}


def reading_goal(state):
    if not article(state): raise Inapplicable('NOT_ENCYCLOPEDIA_ARTICLE_BODY')
    headings = [e for e in state.get('elements',[]) if shown(e,state)
                and article_element(e['element_id'],state)
                and e.get('native_role') in ('h2','h3') and label(e)
                and label(e) not in ('目录','目錄','参考资料','參考資料','外部链接','外部連結')]
    blocks = [b for b in state.get('text_blocks',[]) if len(b.get('visible_text','')) >= 30
              and article_element(b.get('element_id'),state)]
    if not blocks: raise Inapplicable('NO_VISIBLE_ARTICLE_PARAGRAPH')
    heading = label(headings[0]) if headings else None
    title = state.get('title','').split(' - ')[0]
    desc = f'在当前百科词条「{title}」内核对简介的定义和主要事实'
    if heading: desc += f'，定向阅读首帧章节「{heading}」的正文，至下一同级标题或文末'
    else: desc += '，沿当前简介正文向下定位首个章节标题，核对该标题与紧随的正文'
    desc += '。仅按可见正文取证，保留位置；目录链接文字不算正文，不跳去其他词条。'
    return {'template':READING,'description':desc,'heading':heading,
            'heading_role':headings[0]['native_role'] if headings else 'h2',
            'initial_quotes':[b['visible_text'][:200] for b in blocks[:2]],
            'initial_scroll':deepcopy(state.get('scroll'))}


def resolve_goal(state, family, requested_goal=None):
    if requested_goal:
        # An unconstrained natural-language target cannot safely be reinterpreted
        # as our URL-only demo parameters. Retain it and use the original agent.
        raise Inapplicable('EXPLICIT_GOAL_REQUIRES_ORIGINAL_REACT')
    return calculator_goal(state) if family == 'calculator' else reading_goal(state)


def bind_control(observation, selector):
    controls = [c for c in observation['controls'].values()
                if c['binding'].get('selector') == selector]
    if len(controls) != 1: raise Inapplicable('CONTROL_BINDING_CHANGED_OR_AMBIGUOUS')
    return controls[0]


class ResultRegions(HTMLParser):
    """Map synchronized DOM selectors to explicitly identified result regions.

    Full pre-click HTML is used only to reject old/offscreen results. Positive
    evidence still requires a visible tree node from the current synchronized PNG.
    """
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

    def __init__(self, html):
        super().__init__();self.stack=[];self.nodes={};self.top={};self.feed(html or '')

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);parent=self.stack[-1] if self.stack else None
        counts=parent['counts'] if parent else self.top;counts[tag]=counts.get(tag,0)+1
        path=(parent['path']+' > ' if parent else '')+f'{tag}:nth-of-type({counts[tag]})'
        tokens=set(re.split(r'[^a-z0-9_-]+',(attrs.get('id','')+' '+attrs.get('class','')).lower()))
        result=(tag=='output' or attrs.get('aria-live') in ('polite','assertive')
                or bool(tokens & {'result','results','output','calculation-result','calc-result'}))
        excluded=bool(tokens & {'help','example','examples','instruction','instructions','formula'}) or tag in ('label','script','style')
        node={'path':path,'tag':tag,'counts':{},'text':'','input':tag in ('input','select','textarea'),
              'result':result or bool(parent and parent['result']),
              'excluded':excluded or bool(parent and parent['excluded'])}
        self.nodes[path]=node
        if tag in ('input','select','textarea'):
            for old in self.stack:old['input']=True
        if tag not in self.VOID:self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]['tag']==tag:
                del self.stack[i:];break

    def handle_data(self,data):
        if self.stack and self.stack[-1]['tag'] not in ('script','style'):
            for node in self.stack:node['text']+=data


def result_quotes(state, baseline, html=None, before_html=None):
    if not html or not before_html:return []
    current=ResultRegions(html).nodes;previous=ResultRegions(before_html).nodes
    input_numbers={str(v.get('value')) for v in baseline.get('values',[])
                   if re.fullmatch(r'[-+]?\d+(?:\.\d+)?',str(v.get('value','')))}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    quotes=[]
    for element in state.get('elements',[]):
        selector=bindings.get(element['element_id'],{}).get('selector')
        node=current.get(selector);old=previous.get(selector)
        text=label(element)
        if (not node or not node['result'] or node['excluded'] or node['input']
                or not shown(element,state) or element.get('inputable')
                or element.get('native_role') in ('label','input','select','textarea') or not re.search(r'\d',text)):
            continue
        # Numeric output must change because of this click. A scroll exposing an
        # old result, a renamed heading, or a changed input echo cannot satisfy it.
        numbers=re.findall(r'[-+]?\d[\d,.]*(?:%|％)?',node['text'])
        old_numbers=re.findall(r'[-+]?\d[\d,.]*(?:%|％)?',old['text'] if old else '')
        if not numbers or numbers==old_numbers or set(numbers)<=input_numbers:continue
        quotes.append({'element_id':element['element_id'],'selector':selector,'visible_text':text,
                       'before_numbers':old_numbers,'after_numbers':numbers})
    return quotes


def section_body(state, heading_text):
    """Only visible paragraphs geometrically after the actual heading count."""
    elements={e['element_id']:e for e in state.get('elements',[])}
    headings=[e for e in elements.values() if shown(e,state)
              and article_element(e['element_id'],state)
              and e.get('native_role') in ('h2','h3') and label(e)==heading_text]
    if len(headings)!=1:return [],[]
    heading=headings[0]
    next_heads=[e for e in elements.values() if shown(e,state) and article_element(e['element_id'],state)
                and e.get('native_role')==heading['native_role']
                and e['bbox'][1]>=heading['bbox'][3] and e['element_id']!=heading['element_id']]
    bottom=min((e['bbox'][1] for e in next_heads),default=state['screen_resolution'][1])
    body=[b['visible_text'] for b in state.get('text_blocks',[]) if b.get('element_id') in elements
          and len(b.get('visible_text',''))>=30
          and article_element(b['element_id'],state)
          and shown(elements[b['element_id']],state)
          and elements[b['element_id']]['bbox'][1]>=heading['bbox'][3]
          and elements[b['element_id']]['bbox'][1]<bottom]
    return body,[label(e) for e in next_heads]


class TemplateSession(ReactSession):
    """A deterministic host controller; never impersonates an LLM tool call."""
    experiment_rows = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cid = (self.task.get('candidate_binding') or {}).get('candidate_id')
        self.experiment = deepcopy(self.experiment_rows.get(cid))
        if self.experiment is None: raise ValueError('Candidate absent from frozen template experiment')
        self.plan = None; self.template_disabled = False; self.reactive_rounds = 0
        self.template_dispatches = 0; self.template_tools = 0; self.goal_initialized = False
        self.filled = set(); self.calculated = False; self.baseline = None
        self.read_positions = []; self.read_quotes = []; self.read_heading_seen = False
        self.target_body_ids = set()
        self.event('template-experiment', goal_rule=GOAL_RULE,
                   assignment=self.experiment, model_calls_simulated=False)

    def state_now(self):
        return load_json(self.current['evidence']['state']['path'])

    def fallback(self, reason):
        self.template_disabled = True
        self.event('template-fallback', template=(self.plan or {}).get('template'), reason=reason,
                   actual_template_dispatches=self.template_dispatches, raw_preserved=True)

    async def _round_impl(self):
        if not self.goal_initialized:
            self.goal_initialized = True
            try:
                self.baseline = self.state_now()
                self.plan = resolve_goal(self.baseline,self.experiment['family'], self.requested_goal)
                self.working_goal = self.plan['description']
                update = {'description':self.working_goal,'basis_observation_id':self.current['observation_id'],
                          'reason':'两组共同的可信首帧规则 '+GOAL_RULE}
                self.goal_updates.append({**update,'applied_at_decision':0})
                self.event('common-first-frame-goal', rule=GOAL_RULE, plan=self.plan, update=update,
                           requested_goal_unchanged=True, model_http_requests=0)
            except Inapplicable as exc:
                self.fallback(str(exc))
        if self.experiment['arm'] == 'react' or self.template_disabled:
            self.reactive_rounds += 1
            return await super()._round_impl()
        self._check_request_budget()  # Includes original UNKNOWN and session caps.
        try:
            if self.template_tools >= 24: raise Inapplicable('TEMPLATE_TOOL_BOUND')
            self.template_tools += 1
            if self.plan['template'] == CALCULATOR: return await self.calculator_round()
            return await self.reading_round()
        except Inapplicable as exc:
            self.fallback(str(exc))

    async def host_tool(self, name, arguments):
        self.event('template-tool-intent', template=self.plan['template'], tool=name,
                   arguments=arguments, source='deterministic_host_controller', model_http_requests=0)
        self._last_model_intent = None
        self._last_decision = self.event('template-decision', tool=name, arguments=arguments)
        before = self.actual_dispatches
        try:
            if name == 'act': result = await self._tool_act(arguments)
            elif name == 'observe': result = await self._observe(arguments.get('focus_control_id'))
            else: result = await self._native_finish(arguments)
        finally:
            self.template_dispatches += self.actual_dispatches - before
        self.last_tool_result = result
        self.event('template-tool-result', template=self.plan['template'], result=result,
                   atomic_dispatches=self.actual_dispatches-before)
        if (result or {}).get('status') not in ('ok',):
            raise Inapplicable('HOST_TOOL_'+str((result or {}).get('summary')))
        return result

    async def act_control(self, selector, action, goal, **parameters):
        control = bind_control(self.current,selector)
        truth = control['actions'].get(action,{})
        cid = control['binding']['element_id']
        if truth.get('reason') == 'MISSING_TARGET_PROBE':
            await self.host_tool('observe',{'focus_control_id':cid})
            return False
        if truth.get('status') != 'PROVEN': raise Inapplicable('ACTION_NOT_PROVEN:'+str(truth))
        await self.host_tool('act',{'observation_id':self.current['observation_id'],
            'step':{'action':action,'control_id':cid,'goal':goal[:120],
                    'expected':('核对实际可见变化：'+goal)[:120],**parameters}})
        return True

    async def close_visible(self, summary, proof):
        self.event('template-verifier', template=self.plan['template'], status='VISIBLE_EVIDENCE',
                   proof=proof, observation_id=self.current['observation_id'], independent_qc='PENDING')
        oid=self.current['observation_id']
        return await self.host_tool('finish',{'observation_id':oid,'stop_reason':'ready',
            'summary':summary[:300],'evidence_refs':[oid]})

    async def calculator_round(self):
        state = self.state_now()
        for choice in self.plan['choices']:
            c=bind_control(self.current,choice['selector'])
            if label(c.get('element',{})) != choice['label']:
                raise Inapplicable('CHOICE_LABEL_CHANGED')
            if (c.get('value') or {}).get('value') != choice['value']:
                raise Inapplicable('UNIT_OR_CHOICE_CHANGED')
        for field in self.plan['fields']:
            c=bind_control(self.current,field['selector'])
            if label(c.get('element',{})) != field['label'] or c['binding'].get('input_type') != 'number':
                raise Inapplicable('FIELD_IDENTITY_CHANGED')
            if field['selector'] in self.filled:
                if str((c.get('value') or {}).get('value')) != field['value']:
                    raise Inapplicable('FILLED_PARAMETER_CHANGED')
                continue
            if str((c.get('value') or {}).get('value')) == field['value']:
                self.filled.add(field['selector']);continue
            if await self.act_control(field['selector'],'set_value',f"填写{field['label']}={field['value']}",value=field['value']):
                c=bind_control(self.current,field['selector'])
                if str((c.get('value') or {}).get('value')) != field['value']:
                    raise Inapplicable('FIELD_VALUE_NOT_CONFIRMED')
                self.filled.add(field['selector'])
            return
        if not self.calculated:
            button=bind_control(self.current,self.plan['button_selector'])
            if label(button.get('element',{})) != self.plan['button_label']:
                raise Inapplicable('CALCULATE_BUTTON_LABEL_CHANGED')
            self.calculation_before=state
            self.calculation_before_html=self.current['html']
            if await self.act_control(self.plan['button_selector'],'click','按本次参数执行计算'):
                self.calculated = True
            return
        quotes = result_quotes(state,self.calculation_before,self.current['html'],self.calculation_before_html)
        if quotes:
            return await self.close_visible('已按固定字段参数计算；末帧可见：'+'；'.join(q['visible_text'] for q in quotes[:3]),
                                             {'result_quotes':quotes,'fields':self.plan['fields'],'choices':self.plan['choices']})
        # One forward viewport can expose results below the form. No retry click.
        if not getattr(self,'result_scrolled',False) and 'scroll' in self.current['page_actions']:
            self.result_scrolled=True
            return await self.host_tool('act',{'observation_id':self.current['observation_id'],
                'step':{'action':'scroll','direction':'down','goal':'定位刚才计算的结果区','expected':'显示结果数值和名称单位'}})
        raise Inapplicable('CALCULATION_RESULT_NOT_VISIBLE')

    async def reading_round(self):
        state=self.state_now()
        if not article(state): raise Inapplicable('ARTICLE_BODY_OR_IDENTITY_LOST')
        pos=state.get('scroll')
        headings=[e for e in state.get('elements',[]) if shown(e,state)
                  and article_element(e['element_id'],state)
                  and e.get('native_role') in ('h2','h3') and label(e)]
        blocks=[b['visible_text'] for b in state.get('text_blocks',[]) if len(b.get('visible_text',''))>=30
                and article_element(b.get('element_id'),state)]
        new=[b for b in blocks if b not in self.read_quotes]
        self.read_quotes.extend(new)
        target=self.plan['heading'] or self.plan.get('located_heading')
        if target and any(label(h)==target for h in headings): self.read_heading_seen=True
        if not target and headings:
            target=label(headings[0]);self.plan['located_heading']=target;self.read_heading_seen=True
        target=target or self.plan.get('located_heading')
        target_body,boundary=section_body(state,target) if target else ([],[])
        elements={e['element_id']:e for e in state.get('elements',[])}
        current_ids={b['element_id'] for b in state.get('text_blocks',[]) if b.get('visible_text') in target_body}
        if target_body:self.target_body_ids.update(current_ids)
        # Continuation is accepted only for an actual previously bound paragraph,
        # before a newly visible boundary. Prose merely above a target is excluded.
        if not target_body and self.target_body_ids:
            boundaries=[h for h in headings if label(h)!=target and h.get('native_role')==self.plan['heading_role']]
            if boundaries:
                top=min(h['bbox'][1] for h in boundaries)
                target_body=[b['visible_text'] for b in state.get('text_blocks',[])
                    if b.get('element_id') in self.target_body_ids and b.get('element_id') in elements
                    and shown(elements[b['element_id']],state) and elements[b['element_id']]['bbox'][1]<top]
                if target_body:boundary=[label(h) for h in boundaries]
        self.event('template-reading-progress', position=pos, new_body_quotes=[b[:300] for b in new],
                   target_heading=target, bound_target_body_ids=sorted(self.target_body_ids),
                   target_body_quotes=[b[:300] for b in target_body],boundary_headings=boundary, displayed_only=True)
        if self.template_dispatches and self.read_heading_seen and target_body and (boundary or not self.plan['heading']):
            return await self.close_visible('已在当前词条内核对简介并定位目标章节正文；末帧正文：'+target_body[0][:150],
                {'position':pos,'target_heading':target,'boundary_headings':boundary,
                 'visible_body_quotes':[b[:300] for b in target_body[:2]],'positions':self.read_positions})
        if pos in self.read_positions: raise Inapplicable('READING_POSITION_REPEATED')
        if len(self.read_positions)>=6: raise Inapplicable('SECTION_NOT_REACHED_WITHIN_TEMPLATE_BOUND')
        if not new and self.read_positions: raise Inapplicable('NO_NEW_VISIBLE_BODY')
        self.read_positions.append(deepcopy(pos))
        return await self.host_tool('act',{'observation_id':self.current['observation_id'],
            'step':{'action':'scroll','direction':'down','goal':('继续定位本次词条目标章节 '+(target or '首个章节'))[:120],
                    'expected':'显示该章节的新正文或下一同级标题，保留阅读位置'}})

    def _close(self):
        if getattr(self,'experiment',None) and not getattr(self,'_template_closed',False):
            self._template_closed=True
            route=('mixed' if self.template_dispatches and self.reactive_rounds else
                   'template_direct' if self.template_dispatches else 'original_react')
            self.event('template-route-summary', route=route, template=(self.plan or {}).get('template'),
                       atomic_template_dispatches=self.template_dispatches, reactive_rounds=self.reactive_rounds,
                       fallback=self.template_disabled)
        return super()._close()


@contextmanager
def enabled(rows):
    """Process-local adapter; concurrent workers and ordinary imports unaffected."""
    # 策略1完全冻结：模板适配器（替换策略1会话）拒绝启用，纵深防御。
    from .collection_strategy import Strategy1Forbidden
    raise Strategy1Forbidden()
    from . import react_session
    old=react_session.ReactSession
    if old is not ReactSession: raise RuntimeError('A different session adapter is already active')
    TemplateSession.experiment_rows={r['candidate_id']:deepcopy(r) for r in rows}
    react_session.ReactSession=TemplateSession
    try: yield
    finally:
        react_session.ReactSession=old
        TemplateSession.experiment_rows={}
