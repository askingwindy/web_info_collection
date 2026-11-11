"""策略 2 观察投影：可绑定控件清单与可引用证据区域。

The prompt-facing projections of one trusted observation: which controls the
model may cite (with their real host ids, focus, value, action states and
really observed select options) and which substantive text regions it may
quote. Projections derive from the sealed state only; the original PNG and
tree stay intact and remain the authoritative evidence.
"""


def substantive_answer_text(value, *, field='', excluded_text=()):
    """Substantive visible answer text, without imposing a numeric-only rule."""
    from .numeric_result_evidence import normalized, weak_result_text
    text = normalized(value)
    label = normalized(field).rstrip(':：')
    excluded = {normalized(row) for row in excluded_text if normalized(row)}
    return bool(text and not weak_result_text(text) and not text.endswith((':', '：'))
                and text.rstrip(':：') != label and text not in excluded)


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
    if value.get('value') not in (None, ''):
        row['value'] = str(value.get('value'))[:60]
    if element.get('focused') is True or (control.get('probe') or {}).get('focused') is True:
        row['focused'] = True
    if (control.get('binding') or {}).get('tag') == 'select':
        options = [option for option in (control.get('binding') or {}).get('options') or []
                   if isinstance(option, dict)]
        if options:
            row['options'] = [{'value': str(option.get('value')),
                                'label': str(option.get('label')),
                                'disabled': bool(option.get('disabled'))}
                               for option in options[:20]]
            row['options_truncated'] = len(options) > 20
    return row


def _control_tier(control, allowed):
    element = control.get('element') or {}
    tag = (control.get('binding') or {}).get('tag')
    if element.get('inputable') or tag in ('input', 'select', 'textarea'):
        return 0
    if tag == 'button' or element.get('native_role') in ('button', 'checkbox', 'radio', 'slider'):
        return 1
    return 2


def controls_projection(observation, allowed_actions, limit=30):
    """Prompt-facing bindable controls of the current frame, with their real ids.

    The model cites `target.control` from this list; the host binds the id
    directly against the same observation, so a cited id is unique by
    construction. Business-interactive controls (inputs, selects, controls with
    proven actions) are projected before passive ones so a fixed cap is not
    filled by navigation chrome; inside a tier the document's own order is
    kept. Labels/values/options stay hints; the id is the identity, and no
    control that was not provided to the model is claimed as provided.
    """
    allowed = set(allowed_actions or ())
    tiers = ([], [], [])
    for cid, control in (observation.get('controls') or {}).items():
        element = control.get('element') or {}
        box = element.get('bbox') or []
        viewport = observation.get('viewport') or []
        if (element.get('visible') is not True or len(box) != 4 or len(viewport) != 2
                or not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1])):
            continue
        tiers[_control_tier(control, allowed)].append(_control_row(cid, control, allowed))
    rows = [row for tier in tiers for row in tier]
    rows = rows[:limit]
    for number, row in enumerate(rows, 1):
        row['number'] = number
    observation['provided_control_ids'] = [r['control'] for r in rows]
    return rows


_HEADING_ROLES = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')


def _region_tier(element, quote):
    role = element.get('native_role')
    if role in ('status', 'alert', 'output', 'dialog') or element.get('result_region_selector'):
        return 0
    if role in ('main', 'article', 'p', 'section', 'pre', 'table', 'td'):
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
            if e.get('native_role') in ('nav', 'navigation', 'header', 'banner', 'footer', 'contentinfo', 'aside', 'complementary'):
                return True
            e = tree.get(e.get('parent_id'))
        return False
    candidates = []
    for e in elements:
        quote = (e.get('text') or '').strip()
        if (e.get('visible') is not True or not e.get('bbox') or incidental(e)
                or e.get('native_role') in ('input', 'select', 'textarea', 'button', 'a')
                or not substantive_answer_text(quote)):
            continue
        # Leaf/specific readable blocks prevent body/main wrappers consuming slots.
        if any(child.get('parent_id') == e.get('element_id') and child.get('visible') is True
               and (child.get('text') or '').strip() and (child.get('text') or '').strip() in quote
               for child in elements):
            continue
        ranked = dict(e)
        if e.get('element_id') in result_ids:
            ranked['result_region_selector'] = True
        candidates.append((ranked, quote))
    candidates.sort(key=lambda row: (_region_tier(*row), -min(len(row[1]), 240)))
    rows, seen = [], set()
    for e, quote in candidates:
        if quote in seen:
            continue
        seen.add(quote)
        rows.append({'region_id': 'region_' + str(len(rows) + 1), 'bbox': e['bbox'], 'quote': quote[:240]})
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
    from .batch_core import load_json, file_sha
    root = Path(directory)
    oid = observation['observation_id']
    if observation.get('visual_evidence'):
        return observation['visual_evidence']
    source = observation['evidence']['image']
    image = Image.open(source['path']).convert('RGB')
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    mapping = []
    for number, cid in enumerate(observation.get('provided_control_ids', []), 1):
        box = observation['controls'][cid].get('element', {}).get('bbox')
        if not box:
            continue
        x, y = max(0, int(box[0])), max(0, int(box[1]) - 13)
        label = str(number)
        draw.rectangle((x, y, x + len(label)*7+5, y+13), fill='yellow', outline='black')
        draw.text((x+2, y), label, fill='black')
        mapping.append({'number': number, 'control': cid, 'bbox': deepcopy(box)})
    marked = root / ('visual-' + oid[:16] + '-viewport.png')
    with marked.open('xb') as stream:
        canvas.save(stream, format='PNG')
    viewport = {'ref': oid + '-viewport', 'observation_id': oid, 'scope': 'viewport',
                'path': str(marked.resolve()), 'sha256': file_sha(marked), 'source': deepcopy(source),
                'source_rect': [0, 0, image.width, image.height], 'scale': 1,
                'control_mapping': mapping, 'completion_evidence': True}
    visuals = [viewport]
    if first and page is not None:
        from .browser import observe
        state = load_json(observation['evidence']['state']['path'])
        before = await observe(page)
        dimensions = await page.evaluate('() => [Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),Math.max(document.documentElement.scrollHeight,document.body.scrollHeight)]')
        keys = ('url', 'document_identity', 'scroll', 'elements', 'values', 'visible_text')
        if dimensions[1] > image.height * 1.15 and all(before.get(k) == state.get(k) for k in keys):
            png = await page.screenshot(full_page=True, scale='css', timeout=15000)
            after = await observe(page)
            if all(before.get(k) == after.get(k) for k in keys):
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
    from .batch_core import file_sha
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
    from .planning import verify_evidence
    from .batch_core import load_json
    if not visuals or not any(v.get('scope') == 'viewport' for v in visuals):
        raise ValueError('MISSING_CLEAR_VIEWPORT_IMAGE')
    state = load_json(observation['evidence']['state']['path'])
    keys = ('url', 'document_identity', 'scroll', 'elements', 'values', 'visible_text')
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
