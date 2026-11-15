"""策略 2 · operation 模板观察投影：可绑定控件清单与可引用证据区域（独立模板包拷贝）。

The prompt-facing projections of one trusted observation: which controls the
model may cite (with their real host ids, focus, value, action states and
really observed select options) and which substantive text regions it may
quote. Projections derive from the sealed state only; the original PNG and
tree stay intact and remain the authoritative evidence.
"""


from copy import deepcopy

def substantive_answer_text(value, *, field='', excluded_text=()):
    """Substantive visible answer text, without imposing a numeric-only rule."""
    from webcollect.numeric_result_evidence import normalized, weak_result_text
    text = normalized(value)
    label = normalized(field).rstrip(':：')
    excluded = {normalized(row) for row in excluded_text if normalized(row)}
    stem = text.rstrip(':：')
    # Prose legitimately ends with a colon before the content it introduces;
    # only a label-like fragment is rejected for ending there.
    return bool(text and not weak_result_text(text)
                and (not text.endswith((':', '：')) or (len(stem) >= 8 and not weak_result_text(stem)))
                and stem != label and text not in excluded)


def _control_row(cid, control, allowed):
    """One prompt-facing control record; ids and facts stay real, never guessed."""
    element = control.get('element') or {}
    labels = [str(row.get('text') or '') for row in (control.get('readable_labels') or [])][:4]
    value = control.get('value') or {}
    actions = control.get('actions') or {}
    proven = sorted(action for action, truth in actions.items()
                    if action in allowed and (truth or {}).get('status') == 'PROVEN')
    row = {'control': cid, 'role': element.get('native_role'),
           'tag': (control.get('binding') or {}).get('tag'),
           'labels': labels, 'proven_actions': proven,
           'action_states': {action: (actions[action] or {}).get('status')
                             for action in sorted(allowed) if action in actions}}
    text = (element.get('text') or '').strip()
    if text:
        row['text'] = text[:60]
    for key in ('value', 'input_type', 'focused', 'selection_start', 'selection_end', 'all_text_selected', 'checked', 'value_visible', 'readonly'):
        if key in value and value[key] is not None and (key != 'value' or value.get('value_visible') is True):
            row[key] = str(value[key])[:60] if key == 'value' else value[key]
    if (control.get('binding') or {}).get('tag') == 'select' and value.get('value_visible') is True:
        row['display_value'] = str(value.get('display_value') or '')[:60]
    if element.get('state') == 'focused' or element.get('focused') is True or (control.get('probe') or {}).get('focused') is True:
        row['focused'] = True
    for key in ('enabled', 'state'):
        if key in element:
            row[key] = element[key]
    if (control.get('binding') or {}).get('tag') == 'select':
        options = [option for option in (control.get('binding') or {}).get('options') or []
                   if isinstance(option, dict)]
        if options:
            row['options'] = [{'value': str(option.get('value')),
                                'label': str(option.get('label')),
                                'disabled': bool(option.get('disabled'))}
                               for option in options[:20]]
            row['options_truncated'] = len(options) > 20
    if (control.get('binding') or {}).get('scroll_container'):
        row['scroll_container'] = deepcopy(control['binding']['scroll_container'])
    return row


_CHROME_ROLES = ('nav', 'navigation', 'header', 'banner', 'footer',
                 'contentinfo', 'aside', 'complementary')
_CONTENT_ROLES = ('main', 'article')


def body_element_ids(state):
    """Ids outside site chrome, so article links outrank navigation links.

    The sealed tree carries only roles and parent links, so this walks ancestors
    and lets the nearest chrome/content role decide. A search field inside a
    header stays a business control because form tiers are ranked first anyway.
    """
    tree = {e.get('element_id'): e for e in (state or {}).get('elements', [])}
    verdict = {}

    def chrome(element_id):
        chain, node = [], element_id
        while node in tree and node not in verdict:
            chain.append(node)
            node = tree[node].get('parent_id')
        inside = verdict.get(node, False)
        for eid in reversed(chain):
            role = tree[eid].get('native_role')
            if role in _CHROME_ROLES:
                inside = True
            elif role in _CONTENT_ROLES:
                inside = False
            verdict[eid] = inside
        return verdict.get(element_id, False)

    return {eid for eid in tree if not chrome(eid)}


def _control_tier(control, allowed, body_ids=None):
    element = control.get('element') or {}
    tag = (control.get('binding') or {}).get('tag')
    if element.get('inputable') or tag in ('input', 'select', 'textarea'):
        return 0
    if tag == 'button' or element.get('native_role') in ('button', 'checkbox', 'radio', 'slider'):
        return 1
    if body_ids is None or element.get('element_id') in body_ids:
        return 2
    return 3


def controls_projection(observation, allowed_actions, limit=60, body_ids=None):
    """Prompt-facing bindable controls of the current frame, with their real ids.

    The model cites `target.control` from this list; the host binds the id
    directly against the same observation, so a cited id is unique by
    construction. Only dispatchable rows are projected: inputs and selects, then
    buttons, then clickable controls inside the page body, then clickable chrome
    last, so a long-reading page's article links are not crowded out by its
    navigation. Inside a tier the document's own order is kept. Labels/values/
    options stay hints; the id is the identity, and no control that was not
    provided to the model is claimed as provided.
    """
    allowed = set(allowed_actions or ())
    tiers = ([], [], [], [])
    for cid, control in (observation.get('controls') or {}).items():
        element = control.get('element') or {}
        box = element.get('bbox') or []
        viewport = observation.get('viewport') or []
        if (element.get('visible') is not True or len(box) != 4 or len(viewport) != 2
                or not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1])):
            continue
        tier = _control_tier(control, allowed, body_ids)
        # Passive wrappers (nav/form/div/p/heading) can never be dispatched; only
        # the form and button tiers keep rows the page did not mark clickable.
        if tier > 1 and element.get('clickable') is not True and not (
                'scroll' in allowed and (control.get('binding') or {}).get('scroll_container')):
            continue
        tiers[tier].append(_control_row(cid, control, allowed))
    rows = [row for tier in tiers for row in tier]
    rows = rows[:limit]
    for number, row in enumerate(rows, 1):
        row['number'] = number
    observation['provided_control_ids'] = [r['control'] for r in rows]
    observation['provided_control_numbers'] = {str(r['number']): r['control'] for r in rows}
    return rows


_HEADING_ROLES = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')


_AFFORDANCE_ORDER = ('input', 'select', 'button', 'body_link', 'chrome_link', 'other')


def _affordance_kind(row, body_ids):
    tag = row.get('tag')
    if tag in ('input', 'textarea'):
        return 'input'
    if tag == 'select':
        return 'select'
    if tag == 'button' or row.get('role') in ('button', 'checkbox', 'radio', 'slider'):
        return 'button'
    if tag == 'a':
        return 'chrome_link' if (body_ids is not None and row['control'] not in body_ids) else 'body_link'
    return 'other'


def interaction_affordances(rows, body_ids=None, limit=4):
    """The interaction forms this frame really offers, summarised from its rows.

    A long-reading page without this summary is what produced a six-scroll plan:
    the article body's clickable links were crowded out of the control list, so
    the only remaining shape was a linear read. Counts and examples come solely
    from rows actually projected to the model, never from page text.
    """
    groups = {}
    for row in rows:
        group = groups.setdefault(_affordance_kind(row, body_ids), {'count': 0, 'examples': []})
        group['count'] += 1
        label = (row.get('text') or ' '.join(row.get('labels') or [])).strip()
        if label and len(group['examples']) < limit:
            group['examples'].append(label[:30])
    ranked = [{'kind': kind, **groups[kind]} for kind in _AFFORDANCE_ORDER if kind in groups]
    return {'projected_controls': len(rows), 'kinds': [row['kind'] for row in ranked],
            'groups': ranked,
            'not_observed_kinds': [kind for kind in _AFFORDANCE_ORDER if kind not in groups],
            'scope': '当前已投影控件；未观察到的交互不等于页面或后续页面不支持',
            'dispatch_status_source': 'controls.action_states；PROVEN已证明当前可派发，UNAVAILABLE明确当前不满足条件',
            'unproven_actions': 'INSUFFICIENT或缺失状态表示尚未证明当前可派发；不代表宿主不支持，也不许可直接派发'}


def _region_tier(element, quote):
    role = element.get('native_role')
    if role in ('status', 'alert', 'output', 'dialog') or element.get('result_region_selector'):
        return 0
    if role in ('main', 'article', 'p', 'section', 'pre', 'table', 'tr', 'li', 'td', 'th'):
        return 1
    if role in _HEADING_ROLES:
        return 2
    return 3


def region_registry(state, limit=12):
    """Prefer specific result/body text; suppress duplicate ancestor wrappers."""
    elements = state.get('elements', [])
    tree = {e.get('element_id'): e for e in elements}
    result_ids = {b['element_id'] for b in state.get('capture_controls', []) if b.get('result_region_selector')}
    def incidental(e):
        seen = set()
        while e and e.get('element_id') not in seen:
            seen.add(e.get('element_id'))
            if e.get('native_role') in _CHROME_ROLES:
                return True
            e = tree.get(e.get('parent_id'))
        return False
    candidates = []
    block_ids = set()
    for block in state.get('text_blocks') or []:
        quote = str(block.get('visible_text') or '').strip()
        box = block.get('bbox') or []
        if not quote or len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]:
            continue
        owner = tree.get(block.get('element_id'), {})
        if incidental(owner):
            continue
        block_ids.add(block.get('element_id'))
        # Keep a whole visible row/sentence, never chop a person's name at the
        # schema boundary. Long blocks remain raw evidence; expose their intact
        # visible sentences or cells as individually citable regions.
        pieces = [quote] if len(quote) <= 400 else [
            q for q in block.get('complete_sentences') or [] if len(q) <= 400]
        if not pieces and block.get('cells'):
            pieces = [c['visible_text'] for c in block['cells'] if 0 < len(c.get('visible_text', '')) <= 400]
        for piece in pieces:
            row = {key: deepcopy(block[key]) for key in
                   ('element_id', 'bbox', 'tag', 'member_ids', 'member_selectors', 'cells', 'headers') if key in block}
            row.update(quote=piece, source='text_block')
            ranked = dict(owner, native_role=block.get('tag') or owner.get('native_role'))
            candidates.append((ranked, row))
    for e in elements:
        quote = (e.get('visible_text') if 'visible_text' in e else e.get('text') or '').strip()
        if (e.get('element_id') in block_ids or e.get('visible') is not True or not e.get('bbox') or incidental(e)
                or e.get('native_role') in ('input', 'select', 'textarea', 'button')
                or not quote or len(quote) > 400):
            continue
        if e.get('native_role') != 'a' and not substantive_answer_text(quote):
            continue
        if any(child.get('parent_id') == e.get('element_id') and child.get('visible') is True
               and (child.get('text') or '').strip() and (child.get('text') or '').strip() in quote
               for child in elements):
            continue
        ranked = dict(e)
        if e.get('element_id') in result_ids:
            ranked['result_region_selector'] = True
        candidates.append((ranked, {'element_id': e.get('element_id'), 'bbox': e['bbox'], 'quote': quote,
                                    'member_ids': [e.get('element_id')], 'source': 'element'}))
    candidates.sort(key=lambda row: (_region_tier(row[0], row[1]['quote']),
                                    -min(len(row[1]['quote']), 240)))
    rows, seen = [], set()
    for e, row in candidates:
        identity = (row.get('element_id'), row['quote'])
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({'region_id': 'region_' + str(len(rows) + 1), **row})
        if len(rows) >= limit:
            break
    return rows


async def prepare_visuals(observation, directory, page=None, *, first=False):
    """Create marked viewport and optional real full-page overview, preserving originals.

    Only the viewport's controls/regions are executable evidence. The overview
    is contextual and explicitly carries its own capture interval and scale.
    """
    from pathlib import Path
    from io import BytesIO
    from copy import deepcopy
    from PIL import Image, ImageDraw
    from webcollect.batch_core import load_json, file_sha
    root = Path(directory)
    oid = observation['observation_id']
    if observation.get('visual_evidence'):
        return observation['visual_evidence']
    source = observation['evidence']['image']
    image = Image.open(source['path']).convert('RGB')
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    mapping, placed = [], []
    for number, cid in enumerate(observation.get('provided_control_ids', []), 1):
        box = observation['controls'][cid].get('element', {}).get('bbox')
        if not box:
            continue
        label = str(number)
        width, height = len(label) * 7 + 5, 13
        left, top = max(0, int(box[0])), max(0, int(box[1]))
        right, bottom = min(image.width, int(box[2])), min(image.height, int(box[3]))
        fits = lambda x, y: 0 <= x and 0 <= y and x + width <= image.width and y + height <= image.height  # noqa: E731
        # Every number must stay readable: a badge may move, never disappear.
        free = lambda x, y: not any(x < rect[2] and rect[0] < x + width  # noqa: E731
                                    and y < rect[3] and rect[1] < y + height for rect in placed)
        anchors = [(left, top - height), (right - width, top - height), (left, top),
                   (right - width, top), (left, bottom - height), (right - width, bottom - height)]
        x, y = next(((cx, cy) for cx, cy in anchors if fits(cx, cy) and free(cx, cy)),
                    next(((cx, cy) for cx, cy in anchors if fits(cx, cy)), (left, max(0, top - height))))
        draw.rectangle((x, y, x + width, y + height), fill='yellow', outline='black')
        draw.text((x + 2, y), label, fill='black')
        placed.append((x, y, x + width, y + height))
        mapping.append({'number': number, 'control': cid, 'bbox': deepcopy(box),
                        'badge': [x, y, x + width, y + height]})
    marked = root / ('visual-' + oid[:16] + '-viewport.png')
    with marked.open('xb') as stream:
        canvas.save(stream, format='PNG')
    viewport = {'ref': oid + '-viewport', 'observation_id': oid, 'scope': 'viewport',
                'path': str(marked.resolve()), 'sha256': file_sha(marked), 'source': deepcopy(source),
                'source_rect': [0, 0, image.width, image.height], 'scale': 1,
                'control_mapping': mapping, 'completion_evidence': True}
    visuals = [viewport]
    if first and page is not None:
        import asyncio
        from webcollect.browser import observe
        from playwright.async_api import TimeoutError as ScreenshotTimeoutError, Error as BrowserError
        state = load_json(observation['evidence']['state']['path'])
        keys = ('url', 'document_identity', 'scroll', 'elements', 'values', 'visible_text', 'text_blocks', 'scroll_containers')
        png = None
        stage = 'before_observe'
        try:
            before = await observe(page)
            stage = 'dimensions'
            dimensions = await asyncio.wait_for(page.evaluate('() => [Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),Math.max(document.documentElement.scrollHeight,document.body.scrollHeight)]'), timeout=15)
            if dimensions[1] > image.height * 1.15 and all(before.get(k) == state.get(k) for k in keys):
                stage = 'screenshot'
                png = await page.screenshot(full_page=True, scale='css', timeout=15000)
                stage = 'after_observe'
                after = await observe(page)
        except (TimeoutError, ScreenshotTimeoutError) as error:
            # Every read in this optional locator chain may time out. The
            # already synchronized viewport remains the executable evidence.
            viewport['overview_unavailable'] = {'reason': stage + '_timeout', 'error': str(error)}
            observation['visual_evidence'] = visuals
            return visuals
        except BrowserError as error:
            # This optional locator has no authority over the already verified
            # viewport. Keep unsupported geometry local to the unused overview;
            # formal capture/target proofs and other engineering errors stay strict.
            if 'UNSUPPORTED_GEOMETRY:' not in str(error):
                raise
            viewport['overview_unavailable'] = {'reason': stage + '_unsupported_geometry', 'error': str(error)}
            observation['visual_evidence'] = visuals
            return visuals
        if png is not None and all(before.get(k) == after.get(k) for k in keys):
            full = root / ('visual-' + oid[:16] + '-full-original.png')
            with full.open('xb') as stream:
                stream.write(png)
            full_image = Image.open(BytesIO(png)).convert('RGB')
            # Long pages remain an overview; the viewport remains pixel-clear.
            ratio = min(1, 2400 / max(full_image.size))
            overview = full_image.resize((max(1, round(full_image.width*ratio)), max(1, round(full_image.height*ratio))))
            path = root / ('visual-' + oid[:16] + '-overview.png')
            with path.open('xb') as stream:
                overview.save(stream, format='PNG')
            import json
            def exclusive(path, data):
                with path.open('x', encoding='utf-8') as stream:
                    json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
                return {'path': str(path.resolve()), 'sha256': file_sha(path)}
            before_ref = exclusive(root / ('visual-' + oid[:16] + '-full-before.json'), before)
            after_ref = exclusive(root / ('visual-' + oid[:16] + '-full-after.json'), after)
            visuals.insert(0, {'ref': oid + '-overview', 'observation_id': oid,
                'scope': 'full_page_overview', 'path': str(path.resolve()), 'sha256': file_sha(path),
                'source': {'path': str(full.resolve()), 'sha256': file_sha(full)},
                'source_rect': [0, 0, full_image.width, full_image.height], 'scale': ratio,
                'document_identity': before.get('document_identity'),
                'before_state': before_ref, 'after_state': after_ref,
                'completion_evidence': False, 'note': '整体定位图；细节和完成引用使用当前清晰图或有来源的清晰裁图'})
    observation['visual_evidence'] = visuals
    return visuals


def crop_visual(observation, directory, rect, image_ref=None):
    """Detail from an already supplied original image; never a browser action."""
    from pathlib import Path
    from copy import deepcopy
    from PIL import Image
    from webcollect.batch_core import file_sha
    visuals = observation.get('visual_evidence') or []
    source_visual = next((v for v in visuals if v.get('ref') == image_ref), None) if image_ref else next((v for v in visuals if v['scope'] == 'full_page_overview'), None)
    if not source_visual or source_visual.get('scope') not in ('viewport', 'full_page_overview'):
        raise ValueError('IMAGE_REF_NOT_PROVIDED_OR_NOT_ORIGINAL_VIEW')
    image = Image.open(source_visual['source']['path'])
    if (len(rect) != 4 or any(not isinstance(x, int) or isinstance(x, bool) for x in rect)
            or not (0 <= rect[0] < rect[2] <= image.width and 0 <= rect[1] < rect[3] <= image.height)):
        raise ValueError('CROP_OUTSIDE_SOURCE')
    path = Path(directory) / ('visual-' + observation['observation_id'][:16] + '-' + source_visual['scope'] + '-crop-' + '-'.join(map(str,rect)) + '.png')
    cropped = image.crop(rect)
    if path.exists():
        with Image.open(path) as existing:
            if existing.size != cropped.size or existing.convert('RGB').tobytes() != cropped.convert('RGB').tobytes():
                raise ValueError('EXISTING_CROP_SOURCE_MISMATCH')
    else:
        with path.open('xb') as stream:
            cropped.save(stream, format='PNG')
    return {'ref': path.stem, 'observation_id': observation['observation_id'], 'scope': 'image_crop',
            'parent_ref': source_visual['ref'], 'parent_visual': deepcopy(source_visual), 'path': str(path.resolve()), 'sha256': file_sha(path),
            'source': source_visual['source'], 'source_rect': list(rect), 'scale': 1,
            'completion_evidence': False,
            'note': '已提供原图的清晰补图，不代表新观察或业务动作；完成引用仍绑定原观察的区域'}


def verify_visuals(observation, visuals):
    """Validate the exact host-generated image list in live calls and sealed replay."""
    from PIL import Image
    from webcollect.planning import verify_evidence
    from webcollect.batch_core import load_json
    if not visuals or not any(v.get('scope') == 'viewport' for v in visuals):
        raise ValueError('MISSING_CLEAR_VIEWPORT_IMAGE')
    state = load_json(observation['evidence']['state']['path'])
    keys = ('url', 'document_identity', 'scroll', 'elements', 'values', 'visible_text', 'text_blocks', 'scroll_containers')
    for visual in visuals:
        if visual.get('observation_id') != observation['observation_id']:
            raise ValueError('VISUAL_OBSERVATION_MISMATCH')
        verify_evidence([{'path': visual['path'], 'sha256': visual['sha256']}, visual['source']])
        scope = visual.get('scope')
        with Image.open(visual['source']['path']) as image:
            width, height = image.size
        rect = visual.get('source_rect') or []
        if len(rect) != 4 or not (0 <= rect[0] < rect[2] <= width and 0 <= rect[1] < rect[3] <= height):
            raise ValueError('VISUAL_SOURCE_RANGE_MISMATCH')
        if scope == 'viewport':
            if visual['source'] != observation['evidence']['image'] or rect != [0, 0, width, height]:
                raise ValueError('VIEWPORT_SOURCE_MISMATCH')
            for row in visual.get('control_mapping', []):
                c = observation['controls'].get(row['control']) or {}
                if row.get('bbox') != c.get('element', {}).get('bbox'):
                    raise ValueError('VISUAL_CONTROL_MAPPING_MISMATCH')
        elif scope == 'full_page_overview':
            verify_evidence([visual['before_state'], visual['after_state']])
            before, after = load_json(visual['before_state']['path']), load_json(visual['after_state']['path'])
            if not all(before.get(k) == after.get(k) == state.get(k) for k in keys):
                raise ValueError('FULL_PAGE_CAPTURE_STATE_DRIFT')
            if visual.get('completion_evidence') is not False:
                raise ValueError('OVERVIEW_IS_CONTEXT_ONLY')
        elif scope == 'image_crop':
            parent = visual.get('parent_visual') or {}
            if (parent.get('ref') != visual.get('parent_ref') or parent.get('source') != visual['source']
                    or parent.get('scope') not in ('viewport', 'full_page_overview')
                    or visual.get('completion_evidence') is not False):
                raise ValueError('CROP_REQUIRES_SAME_CAPTURE_SOURCE')
            viewport = next(v for v in visuals if v.get('scope') == 'viewport')
            verify_visuals(observation, [viewport, parent] if parent['scope'] != 'viewport' else [parent])
        else:
            raise ValueError('UNKNOWN_VISUAL_SCOPE')
    return [v['path'] for v in visuals]
