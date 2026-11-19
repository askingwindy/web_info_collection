"""策略 3 当前帧投影、动作绑定与视图比较（独立小实现，不调用旧合同）。

只做派发前必要检查：编号属于本帧可见可用元素、命中坐标在真实bbox与截图
内、type 只承接实际已聚焦输入框、同站范围与排除规则轻量检查。无证据区域
合同、覆盖率或依赖图。
"""
import re
from urllib.parse import unquote, urlsplit

from . import prompt

POINTER_ACTIONS = ('click', 'double_click', 'right_click', 'select', 'scroll')
CONTROL_ACTIONS = ('click', 'double_click', 'right_click', 'select', 'type')

# 登录/注册/支付/下载/隐私等排除词（URL 路径单词与页面标题关键词）。
_EXCLUDE_URL_PATTERNS = (
    'login', 'signin', 'sign-in', 'signup', 'sign-up', 'register', 'logout',
    'passport', 'account/login', 'pay', 'payment', 'checkout', 'cart',
    'download', 'privacy', 'agreement', 'license')
_EXCLUDE_TEXT_KEYWORDS = ('登录', '註冊', '注册', '立即登录', '请登录', '登录后',
                          '支付', '付款', '结算', '下载app', '下载app'.upper(),
                          '实名认证', '手机号验证')
# 允许的动作参数集合（与交付动作空间一致；首版无 drag/open_url）。
SUPPORTED_ACTIONS = frozenset(('click', 'double_click', 'right_click', 'type',
                               'hotkey', 'scroll', 'select', 'back', 'wait', 'complete'))


class ActionRejected(ValueError):
    """派发前拒绝：动作在本帧不可真实、安全执行。"""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def actionable_rows(state):
    """本帧可见、可用元素投影；业务控件与正文链接在前，站点导航在后。

    编号只在当前帧内有效；列表裁剪只影响模型输入，不裁宿主界面树。
    """
    width, height = state.get('screen_resolution') or [1280, 720]
    nav_band = min(160, height // 4)

    def candidates():
        for element in state.get('elements') or []:
            if not element.get('visible') or not element.get('enabled'):
                continue
            actionable = (element.get('clickable') or element.get('inputable')
                          or element.get('scrollable')
                          or (element.get('element_type') or '') in ('link', 'button')
                          or (element.get('native_role') or '') in ('link', 'button'))
            if not actionable:
                continue
            left, top, right, bottom = element.get('bbox') or [0, 0, 0, 0]
            if right <= left or bottom <= top or right < 0 or bottom < 0 or left >= width or top >= height:
                continue
            yield element

    elements = list(candidates())

    def is_navigation(element):
        kind = (element.get('element_type') or element.get('native_role') or '')
        text = (element.get('text') or '').strip()
        if re.fullmatch(r'(首页|登录|注册|搜索|帮助|关于|联系|更多|导航)', text):
            return True
        if kind not in ('link', 'a'):
            return False  # 顶部输入框/按钮是业务控件，不是站点导航
        left, top, right, bottom = element.get('bbox') or [0, 0, 0, 0]
        return top < nav_band

    business = [element for element in elements if not is_navigation(element)]
    navigation = [element for element in elements if is_navigation(element)]
    # 业务控件内可输入元素排在纯可点击元素（如伴随的 label）之前：label 与
    # 其输入框同现时，编号优先给输入框本身，避免 type 绑定到不可输入控件。
    business.sort(key=lambda element: 0 if element.get('inputable') else 1)
    ordered = (business + navigation)[:prompt.LIMIT_ELEMENT_ROWS]
    return [(index + 1, element) for index, element in enumerate(ordered)]


def _element_values(state, element_id):
    for value in state.get('values') or []:
        if value.get('element_id') == element_id:
            return value
    return {}


def _center(bbox):
    left, top, right, bottom = bbox
    return int((left + right) // 2), int((top + bottom) // 2)


def _hotkey_allowed(state, keys):
    if (not isinstance(keys, list) or not keys or len(keys) > 4
            or any(not isinstance(key, str) or not key or key.lower() not in prompt.ALLOWED_KEYS
                   for key in keys)):
        return False
    lowered = [key.lower() for key in keys]
    if 'a' not in lowered:
        return True
    # 新增字母键仅用于当前可编辑输入的全选，不能扩展成任意浏览器快捷键。
    if (len(lowered) != 2 or lowered[-1] != 'a'
            or lowered[0] not in ('ctrl', 'control', 'meta', 'command', 'cmd')):
        return False
    elements = {item.get('element_id'): item for item in state.get('elements') or []}
    return any(value.get('focused') is True and not value.get('readonly')
               and elements.get(value.get('element_id'), {}).get('inputable') is True
               and elements[value['element_id']].get('visible') is True
               and elements[value['element_id']].get('enabled') is True
               and value.get('input_type') not in prompt.NATIVE_PICKER_TYPES
               for value in state.get('values') or [])


def bind_action(state, rows, arguments):
    """把模型动作参数绑定为一次可派发的原子操作。失败抛 ActionRejected。"""
    action = arguments.get('action')
    if action not in SUPPORTED_ACTIONS:
        raise ActionRejected('UNSUPPORTED_ACTION:' + str(action))
    by_number = {number: element for number, element in rows}
    element = None
    number = arguments.get('element')
    width, height = state.get('screen_resolution') or [1280, 720]

    if action in ('click', 'double_click', 'right_click', 'select'):
        if type(number) is not int or number not in by_number:
            raise ActionRejected('ELEMENT_NOT_IN_FRAME:' + str(number))
        element = by_number[number]
        if not element.get('enabled'):
            raise ActionRejected('ELEMENT_DISABLED')
        x, y = _center(element['bbox'])
        if not (0 <= x < width and 0 <= y < height):
            raise ActionRejected('ELEMENT_OUTSIDE_VIEWPORT')
    elif action == 'type':
        if number is None:
            raise ActionRejected('TYPE_ELEMENT_REQUIRED: type 同时填写已聚焦输入框的 element 和 text')
        if type(number) is not int or number not in by_number:
            raise ActionRejected('ELEMENT_NOT_IN_FRAME:' + str(number))
        element = by_number[number]
        if not element.get('inputable'):
            raise ActionRejected('TYPE_TARGET_NOT_INPUTABLE')
        value = _element_values(state, element['element_id'])
        if not value.get('focused'):
            raise ActionRejected('TYPE_REQUIRES_FOCUSED_INPUT: 请先点击输入框')
        if value.get('readonly'):
            raise ActionRejected('TYPE_TARGET_READONLY')
        if value.get('input_type') in prompt.NATIVE_PICKER_TYPES:
            raise ActionRejected('NATIVE_DATE_INPUT_UNSUPPORTED: 此控件不支持 type 或全选，可选用其他可行操作')
        text = arguments.get('text')
        if not isinstance(text, str) or not text:
            raise ActionRejected('TYPE_TEXT_REQUIRED')
    elif action == 'hotkey':
        keys = arguments.get('keys')
        if isinstance(keys, list) and len(keys) == 1 and isinstance(keys[0], str):
            modifier, _, key = keys[0].lower().partition('+')
            if modifier in ('ctrl', 'control', 'meta', 'command', 'cmd') and key == 'a':
                keys = [modifier, key]
                arguments = {**arguments, 'keys': keys}
        if not _hotkey_allowed(state, keys):
            raise ActionRejected('HOTKEY_KEYS_NOT_ALLOWED:' + str(keys))
    elif action == 'scroll':
        if number is not None:
            if type(number) is not int or number not in by_number:
                raise ActionRejected('ELEMENT_NOT_IN_FRAME:' + str(number))
            element = by_number[number]
            if not element.get('scrollable'):
                raise ActionRejected('SCROLL_TARGET_NOT_SCROLLABLE')
            x, y = _center(element['bbox'])
        else:
            x, y = width // 2, height // 2
        if arguments.get('direction') not in ('up', 'down', 'left', 'right'):
            raise ActionRejected('SCROLL_DIRECTION_REQUIRED')
    elif action == 'wait':
        pass
    elif action == 'back':
        pass
    elif action == 'complete':
        if arguments.get('status') not in ('success', 'infeasible'):
            raise ActionRejected('COMPLETE_STATUS_REQUIRED')
    if action == 'select':
        option = arguments.get('option')
        if not isinstance(option, str) or not option:
            raise ActionRejected('SELECT_OPTION_REQUIRED')
        control = next((item for item in state.get('capture_controls') or []
                        if item.get('element_id') == element['element_id']), {})
        if (control.get('tag') != 'select'
                or not any(item.get('label') == option and not item.get('disabled')
                           for item in control.get('options') or [])):
            raise ActionRejected('SELECT_OPTION_NOT_PRESENT')
    # 未声明参数不得随动作携带（不同动作只允许自身需要的参数）。
    allowed = {'last_step_result', 'page_name', 'precondition', 'thought',
               'user_goal', 'expected_result', 'note', 'action', 'task_goal'}
    allowed |= {
        'click': {'element'}, 'double_click': {'element'}, 'right_click': {'element'},
        'type': {'element', 'text'}, 'hotkey': {'keys'}, 'scroll': {'element', 'direction'},
        'select': {'element', 'option'}, 'back': set(), 'wait': set(), 'complete': {'status'},
    }[action]
    extra = set(arguments) - allowed
    if extra:
        hint = '；hotkey 只加 keys，使用当前焦点' if action == 'hotkey' else ''
        raise ActionRejected('UNEXPECTED_ACTION_FIELDS:' + ','.join(sorted(map(str, extra))) + hint)

    operation = {'action_type': action,
                 'arguments': _native_arguments(action, element, arguments, state),
                 'evidence': {'collection_strategy': 'stepwise'}}
    if element is not None:
        operation['evidence']['element_id'] = element['element_id']
        operation['evidence']['element_text'] = (element.get('text') or '')[:200]
        operation['evidence']['element_bbox'] = list(element['bbox'])
        operation['evidence']['element_type'] = element.get('element_type')
        operation['evidence']['element_inputable'] = bool(element.get('inputable'))
        if action in ('click', 'double_click'):
            # 公共导航读回从此真实点击节点查找已捕获的链接/原生表单来源。
            operation['evidence']['anchor_element_id'] = element['element_id']
        elif action == 'type':
            operation['evidence']['focused_element_id'] = element['element_id']
    elif action == 'hotkey':
        focused = next((value.get('element_id') for value in state.get('values') or []
                        if value.get('focused')), None)
        if focused is not None:
            operation['evidence']['focused_element_id'] = focused
    return operation, element


def _native_arguments(action, element, arguments, state):
    """统一动作空间参数（交付与派发一致；坐标为截图像素整数）。"""
    native = {}
    if action in ('click', 'double_click', 'right_click'):
        x, y = _center(element['bbox'])
        native = {'x': x, 'y': y}
    elif action == 'type':
        native = {'text': arguments['text']}
    elif action == 'hotkey':
        native = {'keys': list(arguments['keys'])}
    elif action == 'scroll':
        if element is not None:
            x, y = _center(element['bbox'])
        else:
            width, height = state.get('screen_resolution') or [1280, 720]
            x, y = width // 2, height // 2
        native = {'x': x, 'y': y, 'direction': arguments['direction']}
    elif action == 'select':
        x, y = _center(element['bbox'])
        native = {'x': x, 'y': y, 'option': arguments['option']}
    elif action == 'complete':
        native = {'status': arguments['status']}
    return native


def require_action(state, operation):
    """browser.validate_action_observation 的策略 3 校验器（派发与离线审计共用）。"""
    evidence = operation.get('evidence') or {}
    if evidence.get('collection_strategy') != 'stepwise':
        raise ValueError('UNKNOWN_STEPWISE_OPERATION')
    action = operation.get('action_type')
    arguments = operation.get('arguments') or {}
    width, height = state.get('screen_resolution') or [1280, 720]
    if action not in SUPPORTED_ACTIONS:
        raise ValueError('UNSUPPORTED_ACTION:' + str(action))
    if action in ('click', 'double_click', 'right_click', 'select'):
        element_id = evidence.get('element_id')
        element = next((item for item in state.get('elements') or []
                        if item.get('element_id') == element_id), None)
        if element is None or not element.get('visible') or not element.get('enabled'):
            raise ValueError('ELEMENT_NOT_VISIBLE_OR_ENABLED')
        if list(element['bbox']) != list(evidence.get('element_bbox') or []):
            raise ValueError('ELEMENT_BBOX_CHANGED')
        x, y = arguments.get('x'), arguments.get('y')
        if (type(x) is not int or type(y) is not int or not (0 <= x < width and 0 <= y < height)
                or not (element['bbox'][0] <= x < element['bbox'][2]
                        and element['bbox'][1] <= y < element['bbox'][3])):
            raise ValueError('POINTER_OUTSIDE_TARGET_BBOX')
    elif action == 'type':
        element_id = evidence.get('element_id')
        element = next((item for item in state.get('elements') or []
                        if item.get('element_id') == element_id), None)
        if (element is None or not element.get('inputable')
                or not element.get('visible') or not element.get('enabled')):
            raise ValueError('TYPE_TARGET_NOT_INPUTABLE')
        value = _element_values(state, element_id)
        if not value.get('focused'):
            raise ValueError('TYPE_REQUIRES_FOCUSED_INPUT')
        if value.get('readonly'):
            raise ValueError('TYPE_TARGET_READONLY')
        if value.get('input_type') in prompt.NATIVE_PICKER_TYPES:
            raise ValueError('NATIVE_DATE_INPUT_UNSUPPORTED')
        if not isinstance(arguments.get('text'), str) or not arguments['text']:
            raise ValueError('TYPE_TEXT_REQUIRED')
    elif action == 'hotkey':
        keys = arguments.get('keys')
        if not _hotkey_allowed(state, keys):
            raise ValueError('HOTKEY_KEYS_NOT_ALLOWED')
    elif action == 'scroll':
        if arguments.get('direction') not in ('up', 'down', 'left', 'right'):
            raise ValueError('SCROLL_DIRECTION_REQUIRED')
        x, y = arguments.get('x'), arguments.get('y')
        if type(x) is not int or type(y) is not int or not (0 <= x < width and 0 <= y < height):
            raise ValueError('SCROLL_POINT_OUTSIDE_VIEWPORT')
    elif action in ('back', 'wait', 'complete'):
        if arguments:
            raise ValueError('ACTION_TAKES_NO_ARGUMENTS')
    return True


# ---------------------------------------------------------------- 视图比较与效果
def business_view(state):
    """比较原始可见事实，不使用提示词里已截断的文字或元素列表。

    文字结果、标签/展开状态、焦点、原生选择区和页内滚动都可能是动作的
    实际效果。像素变化由会话另行核对；光标闪烁本身不能成为有效动作。
    """
    clean = lambda text: re.sub(r'\s+', ' ', text or '').strip()
    values = []
    for value in state.get('values') or []:
        values.append({key: value.get(key) for key in (
            'element_id', 'value', 'display_value', 'value_visible', 'checked',
            'choice', 'focused', 'readonly', 'selection_start', 'selection_end',
            'all_text_selected')})
    visible_elements = [item for item in state.get('elements') or [] if item.get('visible')]
    controls = []
    for element in visible_elements:
        if (element.get('clickable') or element.get('inputable') or element.get('scrollable')
                or element.get('element_type') in ('link', 'button')
                or element.get('native_role') in ('link', 'button')):
            controls.append((clean(element.get('text')), clean(element.get('visible_text')),
                             element.get('element_type') or '', element.get('native_role') or '',
                             element.get('state') or '', bool(element.get('enabled')),
                             bool(element.get('inputable'))))
    return {
        'url': state.get('url'),
        'document_identity': state.get('document_identity'),
        'title': state.get('title'),
        'scroll': state.get('scroll'),
        'visible_text': clean(state.get('visible_text')),
        'controls': sorted(controls),
        'focused_elements': sorted(str(item.get('element_id')) for item in visible_elements
                                   if item.get('state') == 'focused'),
        'scroll_containers': sorted(({'element_id': item.get('element_id'),
                                     'scroll': item.get('scroll')}
                                    for item in state.get('scroll_containers') or []
                                    if item.get('visible') is not False),
                                   key=lambda item: str(item.get('element_id'))),
        # 图集可能只替换图片而没有新增文字；读取已捕获的图片来源即可识别。
        'images': sorted((item.get('src') or '', item.get('current_src') or '')
                         for item in state.get('capture_images') or []
                         if item.get('eligible') is not True),
        'values': sorted((item for item in values if item.get('value_visible')
                          or item.get('checked') is not None or item.get('choice')
                          or item.get('focused')),
                         key=lambda item: str(item.get('element_id'))),
    }


def view_equal(before, after):
    """业务视图等价：同文档且业务事实未变（广告轮换、光标闪烁不在此视图内）。"""
    return business_view(before) == business_view(after)


def document_changed(before, after):
    left = before.get('document_identity') or before.get('url')
    right = after.get('document_identity') or after.get('url')
    return left != right


def action_omittable(before, after, action_type):
    """无效果动作可否安全移出交付：同文档、业务视图等价且无未决副作用。

    判断只覆盖确定性场景；输入类动作改变值即不等价，不会被省略。
    """
    if document_changed(before, after):
        return False, 'document_changed'
    if not view_equal(before, after):
        return False, 'business_view_changed'
    if action_type in ('type', 'hotkey'):
        # 键入/组合键即使视图暂未变化也可能有未决副作用，保守保留。
        return False, 'input_side_effect_possible'
    return True, 'no_effect_confirmed'


# ---------------------------------------------------------------- 范围与排除
def allowed_hosts(task):
    def host(url):
        value = str(url or '')
        parsed = urlsplit(value if '://' in value or value.startswith('//') else '//' + value)
        return (parsed.hostname or '').lower().rstrip('.')
    hosts = {host(task.get('site_uri')), host(task.get('initial_url'))}
    hosts.update(host(url) for url in task.get('allowed_hosts') or [])
    reference = (task.get('candidate_binding') or {}).get('application_registry')
    if reference is None:
        reference = task.get('application_registry')
    if reference is not None:
        from ..application_identity import aliases
        mapping = aliases(reference)  # 同时核验登记文件及其第一方来源原件。
        canonical = {owner for uri, owner in mapping.items() if host(uri) in hosts}
        hosts.update(host(uri) for uri, owner in mapping.items() if owner in canonical)
    return {item for item in hosts if item}


def destination_allowed(url, hosts):
    """轻量同站检查：以候选已给出的 host 为准，不凭顶级域名相同扩大范围。"""
    if not url:
        return True
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    return (parsed.hostname or '').lower().rstrip('.') in hosts


def exclusion_issues(url, state):
    """登录/注册/支付/下载/隐私排除与纯英文页检查；返回 (issue|None)。"""
    target = unquote(urlsplit(url or '').path).lower()
    for pattern in _EXCLUDE_URL_PATTERNS:
        # In a calculator slug "pay" can mean wages. Separate payment path components still apply.
        path = ('/'.join(part for part in target.split('/') if not part.endswith('-pay-calculator'))
                if pattern == 'pay' else target)
        if re.search(r'(?<![a-z0-9])' + re.escape(pattern) + r'(?![a-z0-9])', path):
            return 'excluded_url_pattern:' + pattern
    title = (state.get('title') or '')
    visible = (state.get('visible_text') or '')
    for keyword in _EXCLUDE_TEXT_KEYWORDS:
        if keyword and keyword in title:
            return 'excluded_title_keyword:' + keyword
    text = visible.strip()
    if len(text) > 120:
        cjk = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        if cjk / len(text) < 0.05:
            return 'non_chinese_page'
    return None


def destination_hint(url):
    """可确定的链接目的地（同文档锚点/同host直链）；无法确定时返回 None。"""
    if not url:
        return None
    if url.startswith('#') or url.startswith('javascript:'):
        return 'same_document'
    if url.startswith(('http://', 'https://')):
        return url
    return None
