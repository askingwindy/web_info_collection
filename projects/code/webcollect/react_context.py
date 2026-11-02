"""Bounded wire projection only; archived requests and raw evidence stay intact."""
from copy import deepcopy
import json

LIMITS = {'system': 5000, 'tools': 24000, 'observation': 18000,
          'facts': 22000, 'history': 32000, 'query': 2000, 'requested_goal': 32000}
MAX_TEXT_TOKEN_ESTIMATE = 160000


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def project(prompt):
    result = deepcopy(prompt)
    history = result.pop('_history', [])
    # Window boundaries are complete assistant/tool pairs. user state from old
    # rounds is already represented by the current host state and raw archive.
    groups, group = [], []
    for message in history:
        group.append(message)
        if message.get('role') == 'tool':
            groups.append(group)
            group = []
    if group:
        raise ValueError('CONTEXT_PENDING_TOOL: cannot compact an unclosed tool round')
    closed = []
    for group in groups[-2:]:
        pair = []
        for message in group:
            if message['role'] == 'user':
                continue
            if message['role'] == 'tool':
                value = json.loads(message['content'])
                # Current observation is carried once in the new user message.
                if isinstance(value.get('data'), dict):
                    value['data'].pop('observation', None)
                message['content'] = encoded(value)
            pair.append(message)
        closed.append(pair)
    # Expensive completed reasoning is opaque. Drop complete older rounds
    # rather than truncating a provider message or stopping the next decision.
    kept = [message for pair in closed for message in pair]
    while closed and len(encoded(kept)) > LIMITS['history']:
        closed.pop(0)
        kept = [message for pair in closed for message in pair]
    if isinstance(result.get('last_tool_result'), dict):
        data = result['last_tool_result'].get('data')
        if isinstance(data, dict):
            data.pop('observation', None)
    sections = {'system': result['system'], 'tools': result['tools'],
                'observation': result['observation'], 'history': kept,
                'requested_goal': result['requested_goal'],
                'facts': {k:v for k,v in result.items() if k not in
                          ('system','tools','observation','requested_goal')}}
    chars = {name:len(encoded(value)) for name,value in sections.items()}
    for name,size in chars.items():
        if size > LIMITS[name]:
            raise ValueError('CONTEXT_CAPACITY: ' + name + ' exceeds its per-request bound; original retained')
    estimate = sum(len(encoded(value).encode('utf-8')) for value in sections.values()) + 1024
    if estimate > MAX_TEXT_TOKEN_ESTIMATE:
        raise ValueError('CONTEXT_CAPACITY: total text exceeds per-request projection capacity; originals retained')
    result['_history'] = kept
    result['context_metering'] = {'section_chars': chars,
        'text_tokens_upper_estimate': estimate, 'max_text_token_estimate': MAX_TEXT_TOKEN_ESTIMATE,
        'estimate_method': 'UTF-8 text bytes plus 1024 framing allowance as conservative token upper estimate; image bytes excluded',
        'images': 1, 'history_closed_rounds': len(closed),
        'history_rounds_omitted_for_size': min(len(groups),2)-len(closed), 'limits_chars': LIMITS}
    return result
