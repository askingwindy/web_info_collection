"""策略 2 模板路由：选择、冻结与按任务解析模板包（只做路由，无业务代码）。

三个模板包（operation / long_reading / generic）各自独立拥有提示词、线协议
与决策循环；本模块只决定"用哪个模板"：
- ``template_module(name)`` 把已冻结的模板名（或历史任务的 None）解析成模块；
- ``task_template_name(task)`` 读取任务 fragment 上的冻结标记；
- ``freeze_template(task, name)`` 在生成期与策略冻结一起盖章；
- ``select_template(...)`` 由消费者在首帧之后、任何模型调用之前做确定性
  选择（目标方向 + 页面结构信号 + 已确认站点模板），不调用模型。

本模块不得在模块级 import 模板包或 session_core，避免环引用；也不承载
任何提示词、schema 或决策循环代码。历史封存记录（无模板标记）解析到
webcollect.screenshot_plan 单体实现，保证离线重放按原样只读。
"""
import re

TEMPLATE_NAMES = ('operation', 'long_reading', 'generic')
SPECIALIZED_TEMPLATE_NAMES = ('operation', 'long_reading')

# 目标方向关键词：只按明确动词/名词判向，不用域名或站点名单。
_OPERATION_GOAL = re.compile(
    r'计算|换算|转换|核算|求解|查询|单价|总额|合计|利率|'
    r'求(?=.{0,8}(?:值|和|结果))|生成(?=.{0,8}结果)|核对(?=.{0,6}(?:结果|表格))|'
    r'输入(?=.{0,12}(?:结果|输出))')
_READING_GOAL = re.compile(
    r'阅读|通读|翻阅|浏览|正文|章节|词条|文章|了解|学习|查证|读(?:完|取|到)')
_SEARCH_LIKE = re.compile(r'search|搜索|检索', re.I)


def template_module(name):
    """Resolve a frozen template name to its owning module (lazy import).

    ``None`` keeps the historical reading: sealed records without the template
    marker replay through the frozen monolith implementation.
    """
    if name is None:
        from . import screenshot_plan
        return screenshot_plan
    if name in TEMPLATE_NAMES:
        import importlib
        return importlib.import_module('webcollect.screenshot_templates.' + name)
    raise ValueError('Unknown screenshot template: ' + str(name))


def task_template_name(task):
    return ((task or {}).get('fragment') or {}).get('screenshot_template')


def freeze_template(task, name):
    """Stamp a new task's template next to the strategy freeze (idempotent)."""
    if name not in TEMPLATE_NAMES:
        raise ValueError('Unknown screenshot template: ' + str(name))
    fragment = task['fragment']
    current = fragment.get('screenshot_template')
    if current not in (None, name):
        raise ValueError('Screenshot template already frozen differently: ' + str(current))
    fragment['screenshot_template'] = name
    return task


def confirmed_templates(pool, application_id):
    """Tolerant read of registered per-site templates (missing table → none)."""
    if pool is None or not application_id:
        return []
    try:
        connect = getattr(pool, 'pool', None)
        if connect is None:
            return []
        with connect.connect() as con:
            rows = con.execute(
                'SELECT template_name FROM template_sites WHERE application_id=?',
                (application_id,)).fetchall()
    except Exception:
        # The registration table lives in candidate_pool's own DDL; consumers
        # only read it. A missing/busy table means no confirmed templates.
        return []
    names = []
    for row in rows or []:
        value = row.get('template_name') if isinstance(row, dict) else row[0]
        if value in TEMPLATE_NAMES:
            names.append(value)
    return sorted(set(names))


def _goal_text(goal):
    if goal is None:
        return None
    if isinstance(goal, str):
        return goal.strip() or None
    try:
        from .session_core import describe_goal
        return describe_goal(goal) or None
    except Exception:
        return None


def _direction_of(text):
    operation = _OPERATION_GOAL.search(text)
    reading = _READING_GOAL.search(text)
    if operation and reading:
        # 最终交付方向按出现位置靠后者判定（"搜索后阅读…"→阅读）。
        return 'operation' if operation.end() >= reading.end() else 'reading'
    if operation:
        return 'operation'
    if reading:
        return 'reading'
    return None


def _goal_direction(goal_text):
    text = str(goal_text or '').strip()
    if not text:
        return None
    # 最终交付物支配中间动作：优先看最后一个"后"之后的交付描述。
    deliverable = text.rsplit('后', 1)[-1] if '后' in text else ''
    for candidate in (deliverable if len(deliverable.strip()) >= 2 else '', text):
        direction = _direction_of(candidate)
        if direction:
            return direction
    return None


def _page_signals(state):
    """Deterministic structural signals from the captured entry state."""
    state = state if isinstance(state, dict) else {}
    elements = [row for row in state.get('elements', []) if isinstance(row, dict)]
    bindings = {row.get('element_id'): row for row in state.get('capture_controls', [])
                if isinstance(row, dict)}
    inputs = search_inputs = buttons = headings = links = 0
    for element in elements:
        if element.get('visible') is not True:
            continue
        role = element.get('native_role')
        if role in ('input', 'select', 'textarea') or element.get('inputable'):
            binding = bindings.get(element.get('element_id'), {})
            haystack = ' '.join(str(part or '') for part in (
                binding.get('selector'), binding.get('input_type'),
                element.get('text'), element.get('placeholder')))
            if _SEARCH_LIKE.search(haystack):
                search_inputs += 1
            else:
                inputs += 1
        elif role == 'button':
            buttons += 1
        elif role in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            headings += 1
        elif role == 'a':
            links += 1
    prose_blocks = sum(1 for block in state.get('text_blocks') or []
                       if isinstance(block, dict)
                       and len(str(block.get('visible_text') or '')) >= 50)
    return {'inputs': inputs, 'search_inputs': search_inputs, 'buttons': buttons,
            'headings': headings, 'links': links, 'prose_blocks': prose_blocks,
            'visible_text_len': len(str(state.get('visible_text') or ''))}


def _structural_choice(direction, signals):
    business_inputs = signals['inputs'] >= 1 or signals['buttons'] >= 3
    prose = (signals['prose_blocks'] >= 3 or signals['visible_text_len'] >= 800
             or signals['headings'] >= 3)
    search_entry = (signals['search_inputs'] >= 1 and signals['inputs'] == 0
                    and signals['links'] >= 5)
    if direction == 'operation' and business_inputs:
        return 'operation', '目标为输入→执行→核对输出且页面有业务输入控件'
    if direction == 'reading' and (prose or search_entry):
        return 'long_reading', '目标为阅读且页面呈正文/章节或词条检索结构'
    if direction is None:
        if business_inputs:
            # 工具页常带说明长文，输入控件是更强的操作信号；纯文章页几乎
            # 没有业务输入（站内搜索框已单独识别），落阅读。
            return 'operation', '未指定目标且页面有业务输入控件'
        if prose:
            return 'long_reading', '未指定目标且页面呈正文/章节结构'
    return 'generic', '目标与页面结构无专用模板信号，回退generic'


def select_template(*, pool=None, application_id=None, goal=None, state=None):
    """Deterministic template choice before any model call; returns (name, info)."""
    goal_text = _goal_text(goal)
    signals = _page_signals(state)
    direction = _goal_direction(goal_text)
    signals['goal_direction'] = direction
    confirmed = confirmed_templates(pool, application_id)
    structural, reason = _structural_choice(direction, signals)
    confirmed_specialized = [name for name in confirmed
                             if name in SPECIALIZED_TEMPLATE_NAMES]
    if structural in confirmed_specialized:
        return structural, {'source': 'confirmed_site',
                            'reason': '本站已确认该模板且匹配当前目标与页面：' + reason,
                            'signals': signals, 'confirmed': confirmed}
    if confirmed_specialized:
        return structural, {'source': 'confirmed_site_mismatch',
                            'reason': ('已确认模板{}与当前目标/页面不匹配，按结构规则选择{}；'
                                       .format('、'.join(confirmed_specialized), structural)) + reason,
                            'signals': signals, 'confirmed': confirmed}
    if structural == 'generic' and 'generic' in confirmed:
        return 'generic', {'source': 'confirmed_site',
                           'reason': '本站已确认generic模板且无专用结构信号',
                           'signals': signals, 'confirmed': confirmed}
    return structural, {'source': 'page_match' if structural != 'generic' else 'generic_fallback',
                        'reason': reason, 'signals': signals, 'confirmed': confirmed}
