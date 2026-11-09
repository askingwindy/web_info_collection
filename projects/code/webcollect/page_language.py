"""Evidence-only exclusion of readable non-Chinese pages; never a QC PASS."""
import re

VERSION = 'webcollect-chinese-page-exclusion-1'
_HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
_SELECTOR = re.compile(r'简体中文|簡體中文|繁体中文|繁體中文|中文（简体）|中文（繁體）|中文')


def assess(state, *, prior_states=()):
    text = state.get('visible_text', state.get('text', '')) or ''
    # A language-selector label cannot establish the business page's language.
    content = _SELECTOR.sub('', text)
    han = len(_HAN.findall(content))
    latin = len(re.findall(r'[A-Za-z]', content))
    identity = state.get('document_identity')
    prior_chinese = bool(identity) and any(
        old.get('document_identity') == identity and
        _HAN.search(_SELECTOR.sub('', old.get('visible_text', old.get('text', '')) or ''))
        for old in prior_states)
    excluded = not han and bool(latin) and not prior_chinese
    return {'policy': VERSION, 'excluded': excluded,
            'reason': 'same_document_chinese_observed' if prior_chinese and not han else
                      'rendered_chinese_not_evidenced' if excluded else
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
    states = {oid: load_json(o['state_path']) for oid,o in record['observations'].items()}
    prior=[]
    for oid,state in states.items():
        if oid not in selected:
            prior.append(state)
            continue
        if assess(state, prior_states=prior)['excluded']:
            raise ValueError('NON_CHINESE_SAVED_RANGE: ' + oid)
        prior.append(state)
