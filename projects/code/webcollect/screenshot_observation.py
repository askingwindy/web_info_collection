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
    """Interactive business controls first, so the cap is not nav-chrome-only."""
    element = control.get('element') or {}
    if (element.get('inputable') is True or element.get('native_role') in ('input', 'select', 'textarea')
            or any((control.get('actions') or {}).get(action, {}).get('status') == 'PROVEN'
                   for action in allowed)):
        return 0
    if element.get('clickable') is True:
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
        if element.get('visible') is not True:
            continue
        tiers[_control_tier(control, allowed)].append(_control_row(cid, control, allowed))
    rows = [row for tier in tiers for row in tier]
    return rows[:limit]


_HEADING_ROLES = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')


def _region_tier(element, quote):
    """Body/result blocks and headings are quotable before incidental fragments."""
    if len(quote) >= 80 or element.get('native_role') in _HEADING_ROLES:
        return 0
    return 1


def region_registry(state, limit=8):
    """Host-issued short ids for currently visible substantive evidence areas.

    Body and result blocks (long substantive text) and section headings come
    before incidental short fragments, so the registry is not just the first
    text nodes of the tree; within a tier document order is kept and ids are
    assigned after ranking, deterministically.
    """
    candidates = []
    for element in state.get('elements', []):
        quote = (element.get('text') or '').strip()
        if (element.get('visible') is not True or not element.get('bbox')
                or element.get('native_role') in ('input', 'select', 'textarea', 'button')
                or not substantive_answer_text(quote)):
            continue
        candidates.append((element, quote))
    candidates.sort(key=lambda row: _region_tier(row[0], row[1]))
    rows = []
    for element, quote in candidates:
        rows.append({'region_id': 'region_' + str(len(rows) + 1), 'bbox': element['bbox'],
                     'quote': quote[:80]})
        if len(rows) >= limit:
            break
    return rows
