"""Page-local consumer decisions from synchronized visible evidence only."""
import math
import re
from urllib.parse import urlsplit

VERSION = 'webcollect-consumer-page-policy-1'
PLAN_PROTOCOL = 'webcollect-banded-conditional-plan-7'
EXIT_LABELS = {'取消', '返回', '关闭', '取消下载', '暂不登录', '稍后再说',
               'cancel', 'back', 'close', 'not now', 'cancel download'}


def enabled(task):
    return task.get('fragment', {}).get('plan_protocol') in (PLAN_PROTOCOL,'webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10')


def full_image(state):
    """A rendered image covers >=95% of the first viewport, not its DOM alt text.

    Use exposed image records, not capture_images (which may include occluded
    resources). Clip to the screenshot and compute union, avoiding double count.
    """
    size = state.get('screen_resolution') or []
    if len(size) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in size):
        return None
    width, height = size
    boxes = []
    for e in state.get('elements', []):
        b = e.get('bbox') or []
        if (e.get('element_type') != 'image' or e.get('visible') is not True or len(b) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in b)):
            continue
        x1,y1,x2,y2 = max(0,b[0]),max(0,b[1]),min(width,b[2]),min(height,b[3])
        if x1 < x2 and y1 < y2: boxes.append((x1,y1,x2,y2))
    area = 0
    edges = sorted({x for b in boxes for x in (b[0], b[2])})
    for left,right in zip(edges, edges[1:]):
        intervals = sorted((b[1],b[3]) for b in boxes if b[0] <= left and b[2] >= right)
        bottom = 0
        for top,end in intervals:
            area += (right-left)*max(0,end-max(top,bottom))
            bottom = max(bottom,end)
    ratio = area/(width*height)
    return {'policy':VERSION, 'image_viewport_ratio':ratio, 'threshold':.95,
            'image_boxes':[list(b) for b in boxes]} if ratio >= .95 else None


def boundary(state):
    """An observed access error, login/download destination or dialog."""
    elements = state.get('elements', [])
    visible = [e for e in elements if e.get('visible') is True]
    path = urlsplit(state.get('url', '')).path.lower()
    auth_url = bool(re.fullmatch(r'/(?:user/|account/|accounts/)?(?:login|signin|sign-in)(?:\.aspx|\.html|\.php|/)?', path))
    titles = [(state.get('title') or '').strip().casefold()]
    titles += [(e.get('text') or '').strip().casefold() for e in visible if e.get('native_role') == 'h1']
    text_visible=(state.get('visible_text') or '').strip().casefold()
    denied=('forbidden','access denied','禁止访问','拒绝访问','访问被拒绝','存取被拒')
    response=state.get('navigation_response') or {}
    if response.get('status')==403 and response.get('url','').split('#')[0]==state.get('url','').split('#')[0]:
        return {'kind':'http_403','policy':VERSION,'basis':'native_navigation_response_403','goal_completed':False}
    if any(re.fullmatch(r'(?:(?:http|error)\s*)?403(?:\s*[-:：]?\s*(?:forbidden|access denied|禁止访问|拒绝访问))?',t) for t in titles) and any(t in text_visible for t in denied):
        return {'kind':'http_403','policy':VERSION,'basis':'visible_403_status_page','goal_completed':False}
    dialogs = [e for e in visible if e.get('native_role') in ('dialog','alertdialog')]
    def dialog_text(root):
        ids = {root['element_id']}
        for _ in range(len(visible)):
            extra = {e['element_id'] for e in visible if e.get('parent_id') in ids}
            if extra <= ids: break
            ids |= extra
        return ' '.join(e.get('text','') for e in visible if e.get('element_id') in ids)
    text = ' '.join(dialog_text(e) for e in dialogs).casefold()
    ids = {e['element_id'] for e in visible}
    password = any(v.get('element_id') in ids and v.get('input_type') == 'password' for v in state.get('values', []))
    if auth_url or password or any(t in ('登录','用户登录','账号登录','login','sign in') for t in titles) or (
            dialogs and re.search(r'登录|登入|sign in|log in', text)):
        return {'kind':'login', 'policy':VERSION, 'basis':'observed_auth_destination_or_visible_dialog'}
    if any(t in ('下载','文件下载','下载文件','下载确认','确认下载','下载提示','download','download file','download confirmation') for t in titles) or (
            dialogs and re.search(r'下载|download', text)):
        return {'kind':'download', 'policy':VERSION, 'basis':'visible_download_destination_or_dialog'}
    return None


def exit_ids(state):
    return [e['element_id'] for e in state.get('elements', [])
            if e.get('visible') is True and e.get('clickable') is True
            and (e.get('text') or '').strip().casefold() in EXIT_LABELS]


def allowed_exit(state, action, control_id=None):
    if (boundary(state) or {}).get('kind')=='http_403':return action=='back'
    return action == 'back' or (action == 'click' and control_id in exit_ids(state))


def returned_pair(origin, middle, returned, entry, exit):
    """Recomputable two real operations: enter a boundary, then cancel/return."""
    if (entry.get('action') not in ('click','double_click','open_url') or boundary(origin)
            or not boundary(middle) or boundary(returned)):
        return None
    cid=(exit.get('target') or {}).get('control_id')
    if not allowed_exit(middle, exit.get('action'), cid): return None
    if origin.get('url') != returned.get('url'): return None
    return {'policy':VERSION, 'kind':boundary(middle)['kind'],
            'meaning':'boundary_observed_then_exited; no_login_or_download_completion_claim'}


def ending_evidence(task, rows, states, final_id):
    from .reading_progress import same_view
    if not enabled(task) or len(rows) < 2: return None
    entry, exit = rows[-2:]
    origin = states[entry['before_observation_id']]
    middle = states[exit['before_observation_id']]
    returned = states[exit['after_observation_id']]
    if not same_view(states[entry['after_observation_id']], middle): return None
    proof = returned_pair(origin, middle, returned, entry, exit)
    if proof and proof['kind']=='http_403':return None  # Recovery resumes the original goal.
    if not proof or not same_view(returned, states[final_id]): return None
    return {**proof, 'entry_operation_id':entry['operation_id'], 'exit_operation_id':exit['operation_id'],
            'origin_observation_id':entry['before_observation_id'],
            'boundary_observation_id':exit['before_observation_id'],
            'returned_observation_id':exit['after_observation_id'], 'final_observation_id':final_id}
