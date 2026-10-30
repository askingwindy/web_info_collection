"""Read-only action projection shared by source inventory and workflow compiler."""

VERSION = 'observed-native-actions-1'
# This is the subset emitted by the semantic compiler and accepted by the
# existing executor. Select's argument is an observed, unique visible label.
EXECUTABLE = frozenset({'click', 'hotkey', 'type', 'select'})


def control_actions(element, binding, initial):
    if element.get('visible') is not True or element.get('enabled') is not True:
        return []
    actions = set()
    if element.get('clickable'):
        actions.add('click')
    tag = binding.get('tag')
    text_input = tag == 'textarea' or (tag == 'input' and binding.get('input_type', '') in
        ('', 'text', 'number', 'search', 'email', 'url', 'tel', 'password'))
    if (text_input and element.get('inputable')
            and initial.get('readonly') is False and isinstance(initial.get('value'), str)):
        actions.update(('click', 'hotkey', 'type'))
    if tag == 'select' and any(not o.get('disabled') and o.get('label') for o in binding.get('options', [])):
        actions.add('select')
    return sorted(actions)


def replacement_actions(initial, focused, control_id):
    """Cost and compilation use the same necessary replacement primitives."""
    return (['click'] if focused != control_id else []) + (['hotkey'] if initial else []) + ['type']
