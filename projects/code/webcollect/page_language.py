"""Evidence-only exclusion of readable non-Chinese pages; never a QC PASS."""
import re

VERSION = 'webcollect-chinese-page-exclusion-1'
_HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
_SELECTOR = re.compile(r'简体中文|簡體中文|繁体中文|繁體中文|中文（简体）|中文（繁體）|中文')


def assess(state):
    text = state.get('visible_text', state.get('text', '')) or ''
    # A language-selector label cannot establish the business page's language.
    content = _SELECTOR.sub('', text)
    han = len(_HAN.findall(content))
    latin = len(re.findall(r'[A-Za-z]', content))
    excluded = not han and bool(latin)
    return {'policy': VERSION, 'excluded': excluded,
            'reason': 'rendered_chinese_not_evidenced' if excluded else
                      'chinese_text_present_not_language_approval' if han else 'insufficient_readable_text',
            'han_characters': han, 'latin_characters': latin,
            'character_ratio_diagnostic_only': True, 'language_QC': 'NOT_RUN'}


def validate_range(record):
    """New executions only; examine selected action frames and ending, not raw tails."""
    marker = record.get('boundary', {}).get('language_exclusion_policy')
    if marker is None:
        return  # Original sealed executions retain their original contract.
    if marker != VERSION:
        raise ValueError('Unknown saved-range language exclusion policy')
    from .batch_core import load_json
    selected = {record['terminal'].get('final_observation_id')}
    for row in record['trajectory']:
        selected.update((row['before_observation_id'], row['after_observation_id']))
    for oid in selected - {None}:
        state = load_json(record['observations'][oid]['state_path'])
        if assess(state)['excluded']:
            raise ValueError('NON_CHINESE_SAVED_RANGE: ' + oid)
