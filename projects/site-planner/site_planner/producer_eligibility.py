"""Entry-tools-14 checks over the original observation; no browser or model IO."""
import re
from webcollect.batch_core import load_json
from webcollect.collect import chinese_ratio

VERSION = 'producer-page-eligibility-2'


def normalize(text):
    return re.sub(r'\s+', '', text or '')


def assess(observation):
    from webcollect.consumer_page_policy import login_entry_exclusion
    login=login_entry_exclusion(observation)
    if login:return {'policy':VERSION,'status':'REJECTED','reason':login['reason'],'QC':'NOT_RUN'}
    text=observation.get('visible_text',observation.get('text','')) or ''
    # Code, addresses and numbers do not establish a page's natural language.
    prose=re.sub(r'```[\s\S]*?```|https?://\S+|\b[\w./:@-]+\([^\n]*?\)', '', text)
    han=len(re.findall(r'[\u3400-\u9fff]',prose));kana=len(re.findall(r'[\u3040-\u30ff]',prose))
    ratio=chinese_ratio(prose)
    reason=None
    if kana>=3 and kana/max(1,han+kana)>=0.12:reason='non_chinese_japanese_business_text'
    elif han and ratio<0.7:
        # Short product names/identifiers are not long foreign-language prose.
        paragraphs=[line for line in prose.splitlines() if len(line)>35 and re.search(r'[\u3400-\u9fff]',line)]
        if len(re.findall(r'[A-Za-z]{3,} [A-Za-z]{3,} [A-Za-z]{3,}',prose))>=3 and (not paragraphs or chinese_ratio('\n'.join(paragraphs))<0.7):reason='chinese_business_text_below_70_percent'
    elif not han:reason='chinese_business_text_not_evidenced'
    return {'policy':VERSION,'status':'REJECTED' if reason else 'UNKNOWN','reason':reason or 'chinese_prose_present_not_business_approval',
            'han_characters':han,'kana_characters':kana,'prose_chinese_ratio':ratio,'QC':'NOT_RUN'}


def visible_units(evidence):
    """DOM read after capture cannot supply business absent from the saved frame."""
    observation=load_json(evidence['observation']['path'])
    visible=normalize(observation.get('visible_text',observation.get('text','')))
    units=[]
    for unit in evidence['units']:
        text=(unit.get('text','') or '')[:900]
        witness=normalize(text)
        if witness and witness in visible:units.append({**unit,'text':text})
    return units,assess(observation)
