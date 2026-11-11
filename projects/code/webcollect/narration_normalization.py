"""Simplify newly generated strategy-2 prose while preserving evidence literals."""
import re
from functools import lru_cache


@lru_cache(maxsize=1)
def _converter():
    from opencc import OpenCC
    return OpenCC('t2s')


def simplify(text, literals=()):
    if not isinstance(text, str):
        return text
    protected = sorted({s for s in literals if isinstance(s, str) and s}, key=len, reverse=True)
    if not protected:
        return _converter().convert(text)
    pattern = re.compile('|'.join(re.escape(s) for s in protected))
    result, end = [], 0
    for match in pattern.finditer(text):
        result.extend((_converter().convert(text[end:match.start()]), match.group()))
        end = match.end()
    result.append(_converter().convert(text[end:]))
    return ''.join(result)


def normalize_annotation(annotation, record):
    """Only prose fields; actual inputs, labels, quotes and evidence stay byte exact."""
    from .postprocess import _observation_state
    literals = []
    for observation_id in record['observations']:
        state = _observation_state(record, observation_id)
        literals.append(state.get('title'))
        literals.extend(e.get('text') for e in state.get('elements', []))
    for row in record['trajectory']:
        literals.extend(((row.get('target') or {}).get('label'), (row.get('arguments') or {}).get('text')))
    def quotes(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('quote', 'visible_text', 'observed_visible_text') and isinstance(child, str):
                    literals.append(child)
                else:
                    quotes(child)
        elif isinstance(value, list):
            for child in value:
                quotes(child)
    quotes(record['terminal'].get('goal_evidence') or {})
    for key in ('task_instruction', 'final_result', 'completion_judgement', 'short_flow_reason'):
        if key in annotation:
            annotation[key] = simplify(annotation[key], literals)
    for step in annotation['steps']:
        for key in ('user_goal', 'next_step_rationale', 'step_result'):
            step[key] = simplify(step[key], literals)
        for key in ('precondition', 'expected_result'):
            step['action'][key] = simplify(step['action'][key], literals)
    return annotation
