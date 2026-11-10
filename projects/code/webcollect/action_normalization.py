"""Actual executed key delivery; explicit Windows helpers describe historical exports."""
from copy import deepcopy
import re

WINDOWS_KEYBOARD_NORMALIZATION_VERSION = 'delivery-windows-keys-2'
ACTUAL_KEYBOARD_VERSION = 'delivery-actual-keys-1'
SELECT_ALL_NORMALIZATION_VERSION = WINDOWS_KEYBOARD_NORMALIZATION_VERSION  # API compatibility
_MODIFIERS = ('ctrl', 'alt', 'shift', 'win')
_MODIFIER_ALIASES = {'control': 'ctrl', 'ctl': 'ctrl', 'windows': 'win', 'super': 'win'}
_COMMAND = {'meta', 'command', 'cmd', '⌘'}
_OPTION = {'option', 'opt', '⌥'}
_COMMAND_LETTERS = set('acvxzsfponwtlrdgbiuk')
_NAMED = {'enter', 'escape', 'tab', 'backspace', 'delete', 'insert', 'space',
          'home', 'end', 'pageup', 'pagedown', 'arrowleft', 'arrowright', 'arrowup',
          'arrowdown', 'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen', 'contextmenu'}
_ALIASES = {'return': 'enter', 'esc': 'escape', 'del': 'delete', 'ins': 'insert',
            'spacebar': 'space', 'pgup': 'pageup', 'pgdn': 'pagedown',
            'left': 'arrowleft', 'right': 'arrowright', 'up': 'arrowup', 'down': 'arrowdown'}
_DISPLAY = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift', 'win': 'Win',
            'enter': 'Enter', 'escape': 'Esc', 'tab': 'Tab', 'backspace': 'Backspace',
            'delete': 'Delete', 'insert': 'Insert', 'space': 'Space', 'home': 'Home', 'end': 'End',
            'pageup': 'PageUp', 'pagedown': 'PageDown', 'arrowleft': 'Left', 'arrowright': 'Right',
            'arrowup': 'Up', 'arrowdown': 'Down', 'capslock': 'CapsLock', 'numlock': 'NumLock',
            'scrolllock': 'ScrollLock', 'pause': 'Pause', 'printscreen': 'PrintScreen',
            'contextmenu': 'ContextMenu'}


def canonical_windows_keys(keys, source_os=None):
    """Canonicalize known Windows keys; map Mac Command only where declared."""
    def fail(reason):
        raise ValueError('WINDOWS_SHORTCUT_MAPPING_REQUIRED: ' + reason)
    if (not isinstance(keys, list) or not keys or
            any(not isinstance(k, str) or not k or k != k.strip() for k in keys)):
        fail('keys must be nonempty key names without surrounding whitespace')
    os_name = str(source_os or '').casefold()
    mac = os_name in {'macos', 'mac', 'darwin', 'mac os x'}
    windows = os_name.startswith('windows') or os_name in {'win32', 'win64'}
    modifiers = []; primary = []; command = False
    for key in keys:
        name = key.casefold()
        if name in _OPTION:
            fail('Option combinations need a functional Windows mapping')
        if name in _COMMAND:
            if mac:
                name = 'command'; command = True
            elif windows and name == 'meta':
                name = 'win'
            else:
                fail('native Meta/Command needs an explicit supported source OS')
        else:
            name = _MODIFIER_ALIASES.get(name, name)
        if name in _MODIFIERS or name == 'command':
            if primary or name in modifiers:
                fail('duplicate or misplaced modifier')
            modifiers.append(name)
            continue
        if primary:
            fail('only one non-modifier key is supported per chord')
        name = _ALIASES.get(name, name)
        if name in _NAMED or re.fullmatch(r'f(?:[1-9]|1[0-9]|2[0-4])', name):
            primary.append(name)
        elif len(key) == 1 and key.isprintable():
            primary.append(key.lower() if modifiers else key)
        else:
            fail('unknown Windows key name: ' + key)
    if command:
        if (not primary or 'ctrl' in modifiers or 'alt' in modifiers or 'win' in modifiers or
                not (primary[0] in _COMMAND_LETTERS or
                     (primary[0] in '123456789' and 'shift' not in modifiers))):
            fail('this Mac Command shortcut has no declared same-function Windows mapping')
        modifiers = ['ctrl' if key == 'command' else key for key in modifiers]
    if not primary:
        if len(modifiers) != 1:
            fail('a chord needs a main key')
        return modifiers
    return [key for key in _MODIFIERS if key in modifiers] + primary


def display_windows_keys(keys):
    return '+'.join(_DISPLAY.get(key, key.upper()) for key in keys)


def is_select_all(keys):
    """Compatibility predicate; normalization now covers every keyboard action."""
    try:
        return canonical_windows_keys(keys, 'macOS') == ['ctrl', 'a']
    except ValueError:
        return False


def normalize_delivery_arguments(tool_name, arguments, source_os=None):
    result = deepcopy(arguments)
    if tool_name == 'hotkey':
        if not isinstance(result, dict):
            raise ValueError('Actual hotkey arguments must be an object')
        keys = result.get('keys')
        if (not isinstance(keys, list) or not keys or
                any(not isinstance(key, str) or not key.strip() or key != key.strip() for key in keys)):
            raise ValueError('Actual hotkey requires nonempty executed key names')
        result['keys'] = list(keys)
    return result


def normalize_delivery_step(step, source_os=None):
    result = deepcopy(step)
    action = result.get('action', {}); call = result.get('tool_call', {})
    if action.get('action_type') == 'hotkey' and call.get('tool_name') == 'hotkey':
        call['arguments'] = normalize_delivery_arguments('hotkey', call.get('arguments'), source_os)
        keys = call['arguments']['keys']
        action['input_text'] = '+'.join(keys)
        action['target_text'] = display_actual_keys(keys)
    return result


def display_actual_keys(keys):
    labels = {**_DISPLAY, 'meta': 'Meta', 'command': 'Command', 'cmd': 'Cmd',
              'option': 'Option', 'opt': 'Opt', '⌘': '⌘', '⌥': '⌥'}
    return '+'.join(labels.get(key.casefold(), key.upper() if len(key) == 1 else key) for key in keys)
