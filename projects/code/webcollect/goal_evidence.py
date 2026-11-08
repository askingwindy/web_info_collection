"""Observable answers to an explicitly contracted calculation or reading goal."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from .batch_core import load_json
from .plan_evidence import region_matches, same_url
from .planning import verify_evidence

LEGACY_VERSION = 'webcollect-goal-evidence-1'
VERSION = 'webcollect-goal-evidence-2'


def contract_for(task):
    from .react_session import struct_goal
    if task.get('fragment', {}).get('plan_protocol') not in ('webcollect-banded-conditional-plan-7','webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10','webcollect-banded-conditional-plan-11'):
        return None
    objective = task['fragment'].get('session_objective', {}).get('objective') or struct_goal(task)
    return objective.get('evidence_contract') if isinstance(objective, dict) else None


def norm(text):
    return ''.join(unicodedata.normalize('NFKC', str(text)).casefold().split())


def number(value):
    try:
        parsed = Decimal(norm(value).replace(',', ''))
        return parsed if parsed.is_finite() else None
    except InvalidOperation:
        return None


def validate_contract(contract):
    def text(value):
        return isinstance(value, str) and 0 < len(value.strip()) <= 120

    from .direct_article import VERSION as DIRECT_VERSION
    if isinstance(contract,dict) and contract.get('version')==DIRECT_VERSION:
        titles=contract.get('titles');entry=contract.get('entry_url')
        if (set(contract)!={'version','kind','entry_url','titles'} or contract.get('kind')!='reading'
                or not isinstance(entry,str) or urlsplit(entry).scheme not in ('http','https') or not urlsplit(entry).netloc
                or not isinstance(titles,list) or not 1<=len(titles)<=4 or not all(map(text,titles))
                or len({norm(t) for t in titles})!=len(titles)):
            raise ValueError('Invalid direct article identity contract')
        return
    if not isinstance(contract, dict) or contract.get('version') not in (LEGACY_VERSION, VERSION):
        raise ValueError('Unknown explicit goal evidence version')
    kind = contract.get('kind')
    if kind == 'reading':
        aspects = contract.get('aspects')
        required = {'version', 'kind', 'subject', 'aspects'}
        # v2 reading contracts may declare direct entry: the entry page itself is
        # the subject article and site search is not part of the objective.
        allowed = required | ({'direct_entry'} if contract.get('version') == VERSION else set())
        valid = (required <= set(contract) <= allowed and text(contract['subject'])
                 and contract.get('direct_entry') in (None, True)
                 and isinstance(aspects, list) and 2 <= len(aspects) <= 4 and all(map(text, aspects))
                 and len({norm(a) for a in aspects}) == len(aspects))
    elif kind == 'calculation':
        fields = contract.get('inputs')
        retained = contract.get('retain', [])
        valid = (set(contract) <= {'version', 'kind', 'inputs', 'retain', 'result_label', 'unit'}
                 and isinstance(fields, list) and 1 <= len(fields) <= 4 and isinstance(retained, list)
                 and len(retained) <= 4 and all(map(text, retained)) and text(contract.get('result_label'))
                 and text(contract.get('unit')) and all(isinstance(f, dict) and set(f) == {'label', 'value'}
                     and text(f['label']) and number(f['value']) is not None for f in fields))
        if valid:
            labels = [norm(f['label']) for f in fields] + [norm(label) for label in retained]
            valid = len(labels) == len(set(labels))
    else:
        valid = False
    if not valid:
        raise ValueError('Invalid explicit goal evidence fields')


def state(ob):
    return load_json(ob['evidence']['state']['path'])


def html(ob):
    if 'html' in ob:
        return ob['html']
    ref = ob.get('html_ref') or ob['evidence'].get('html')
    return Path(ref['path']).read_text() if ref else ''


def field_value(ob, label):
    """A unique, visibly labelled input or select on the synchronized frame."""
    matches = []
    for cid, c in ob['controls'].items():
        e, value = c['element'], c.get('value') or {}
        if not e.get('visible') or not value.get('value_visible') or not (
                e.get('inputable') or e.get('native_role') == 'select'):
            continue
        names = [e.get('text') or ''] + [r['text'] for r in c.get('readable_labels', [])]
        if any(norm(label) in norm(name) for name in names):
            matches.append((cid, value.get('value')))
    return matches[0] if len(matches) == 1 else (None, None)


def calc_evidence(s, start, contract):
    from .template_learning import result_evidence
    changed, retained = [], []
    for field in contract['inputs']:
        label, desired = field['label'], number(field['value'])
        first_id, first_value = field_value(start, label)
        latest_id, latest_value = field_value(s.current, label)
        if not first_id or number(first_value) == desired or (latest_id and number(latest_value) != desired):
            continue
        for index, step in reversed(list(enumerate(s.trajectory))):
            if step['action'] not in ('type', 'select'):
                continue
            before, after = (s.observation_records[step[k]] for k in ('before_observation_id', 'after_observation_id'))
            cid = (step.get('target') or {}).get('control_id')
            old_id, old = field_value(before, label)
            new_id, new = field_value(after, label)
            if (before.get('capture_verified') and after.get('capture_verified') and cid and cid == old_id == new_id
                    and number(old) != desired and number(new) == desired and after['document_identity'] == s.current['document_identity']):
                if latest_id != cid and (contract['version'] == VERSION or not latest_id):
                    # The earlier synchronized edit proves what was visible. After a scroll,
                    # the same bound field can corroborate the value outside the readable area.
                    current = s.current['controls'].get(cid) or {}
                    final_value = current.get('value') or {}
                    previous_binding = after['controls'][cid]['binding']
                    binding = current.get('binding') or {}
                    prior_scroll, final_scroll = state(after).get('scroll'), state(s.current).get('scroll')
                    if (contract['version'] != VERSION or latest_id or cid != first_id
                            or type(final_value.get('value_visible')) is not bool
                            or not previous_binding.get('selector') or binding.get('selector') != previous_binding['selector']
                            or binding.get('input_type') != previous_binding.get('input_type')
                            or number(final_value.get('value')) != desired
                            or prior_scroll is None or final_scroll is None or prior_scroll == final_scroll
                            or not any(later['action'] == 'scroll' for later in s.trajectory[index + 1:])):
                        continue
                changed.append({'label': label, 'before': old, 'after': new, 'operation_id': step['operation_id'],
                                'observation_id': after['observation_id'], 'node': cid,
                                **({'final_value_basis':'same_bound_field_after_scroll'} if not latest_id else {})})
                break
    for label in contract.get('retain', []):
        source, old = field_value(start, label)
        dest, new = field_value(s.current, label)
        if source and dest and old not in (None, '') and old == new:
            retained.append({'label': label, 'value': new})
    previous = start
    if contract['version'] == VERSION and changed:
        operations = {item['operation_id'] for item in changed}
        last_input = next(step for step in reversed(s.trajectory) if step['operation_id'] in operations)
        previous = s.observation_records[last_input['before_observation_id']]
    base, now = state(previous), state(s.current)
    base = {**base, 'values': base.get('values', []) + now.get('values', [])}
    card = {'card_labels':(contract['result_label'], contract['unit'])} if contract['version'] == VERSION else {}
    results = [p['quotes'] for p in result_evidence(now, base, html(s.current), html(previous), **card)
               if all(norm(x) in norm(' '.join(p['quotes'])) for x in (contract['result_label'], contract['unit']))]
    verified = (start['document_identity'] == s.current['document_identity'] and len(changed) == len(contract['inputs'])
                and len({c['node'] for c in changed}) == len(changed)
                and len(retained) == len(contract.get('retain', [])) and bool(results))
    return {'status': 'VERIFIED' if verified else 'UNVERIFIED', 'changed_fields': changed,
            'retained_fields': retained, 'result_quotes': results[:3]}


def suggestion_member_ids(ob):
    """Members of an eligible combobox suggestion popup on this frame.

    Suggestion rows are live overlay content: their appearance proves nothing
    about a submitted search, so they stay outside result/source evidence while
    remaining ordinary clickable inventory for the model.
    """
    from .dynamic_regions import regions as allowed_regions, SUGGESTION_CATEGORY
    try:
        return {x for r in allowed_regions(state(ob)) if r.get('category') == SUGGESTION_CATEGORY
                for x in r.get('member_ids', [])}
    except Exception:
        return set()


def result_links(ob, start, subject):
    """Expose current first-party result links, excluding navigation and pre-existing links."""
    old = {c['binding'].get('href') for c in start['controls'].values()}
    suggestions = suggestion_member_ids(ob)
    matches = {}
    for cid, c in ob['controls'].items():
        e, binding = c['element'], c['binding']
        name, href = e.get('text') or '', binding.get('href')
        if (not ob.get('capture_verified') or not href or href in old or not e.get('visible')
                or e.get('native_role') != 'a' or not name
                or urlsplit(href).hostname != urlsplit(ob['url']).hostname
                or re.search(r'(?:^| > )(?:nav|aside|footer|header):', binding.get('selector') or '')
                or cid in suggestions):
            continue
        if norm(subject) in norm(name + ' ' + unquote(href)):
            matches[cid] = {'node': cid, 'text': name, 'href': href}
    return matches


SEARCH_TERMS = ('搜索','搜尋','检索','檢索','查詢','查询','search')


def search_button(control):
    element = control.get('element', {})
    return (element.get('visible') and element.get('native_role') in ('button','input')
            and any(t in norm(element.get('text') or '') for t in SEARCH_TERMS))


def search_field(observation, cid):
    control = observation['controls'].get(cid, {})
    binding = control.get('binding', {})
    names = [control.get('element', {}).get('text') or ''] + [r['text'] for r in control.get('readable_labels', [])]
    if binding.get('input_type') == 'search' or any(t in norm(' '.join(names)) for t in SEARCH_TERMS):
        return True
    form = binding.get('form_index')
    if type(form) is not int or form < 0:
        return False
    siblings = {k:c for k,c in observation['controls'].items() if c['binding'].get('form_index') == form}
    fields = [k for k,c in siblings.items() if c['element'].get('visible') and c['element'].get('inputable')
              and c['binding'].get('input_type') in ('text','search')]
    return fields == [cid] and any(search_button(c) for c in siblings.values())


def search_focus_target(ob, *, allow_combobox=False):
    """Identify a single visible search input for a scoped first click."""
    if not ob.get('capture_verified'):
        return None
    matches = [(cid, c) for cid, c in ob['controls'].items()
               if c['element'].get('visible') and c['element'].get('inputable')
               and c['element'].get('native_role') in (('input','combobox') if allow_combobox else ('input',))
               and c['binding'].get('input_type') in ('text','search') and search_field(ob, cid)]
    if len(matches) != 1:
        return None
    cid, control = matches[0]
    element, binding = control['element'], control['binding']
    box = element.get('bbox')
    page = state(ob)
    viewport = page.get('screen_resolution') or []
    if (not box or len(box) != 4 or len(viewport) != 2 or page.get('device_pixel_ratio') != 1
            or not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1])
            or not binding.get('selector')):
        return None
    return {'node':cid, 'selector':binding['selector'], 'bbox':box, 'viewport':viewport,
            'document_identity':ob['document_identity'], 'url':ob['url'], 'label':element.get('text'),
            'value':(control.get('value') or {}).get('value')}


def search_focus_from_pair(before, after, proof):
    """A verified pair can support focusing a search field while other pixels move."""
    change = proof.get('pixel_change') or {}
    bounds = change.get('bbox') or []
    if (proof.get('loading_complete') is not True or len(bounds) != 4
            or not change.get('changed_pixels') or not (bounds[0] < bounds[2] and bounds[1] < bounds[3])):
        return None
    target = search_focus_target(before)
    if not target or target != search_focus_target(after):
        return None
    x1, y1, x2, y2 = target['bbox']
    if bounds[2] <= x1 or x2 <= bounds[0] or bounds[3] <= y1 or y2 <= bounds[1]:
        return target
    return None


def reading_evidence(s, start, contract):
    typed, sources, opened, passages = [], [], [], []
    # Sources carry (document_identity, url): a back-navigation revisits the
    # same result page under a new identity, and its result links stay sources.
    subject, aspects = contract['subject'], contract['aspects']
    landing_doc = None
    downward_reading=[]
    # A direct-entry contract opens the subject article itself: the initial
    # observation is the landing document, no search chain is required or
    # allowed, and passages/downward reading are collected on that article.
    direct_entry = contract.get('direct_entry') is True and contract['version'] == VERSION
    if direct_entry:
        initial = state(start)
        headings = [e for e in initial.get('elements', []) if e.get('visible') and e.get('native_role') == 'h1'
                    and norm(e.get('text', '')) == norm(subject)]
        body_ready = any(e.get('visible') and len((e.get('text') or '').strip()) >= 12
                         and e.get('native_role') not in ('a', 'input', 'button', 'h1', 'h2', 'h3')
                         and region_matches(initial, e['element_id'], '正文') for e in initial.get('elements', []))
        if len(headings) == 1 and body_ready:
            landing_doc = start['document_identity']
            opened.append({'text': headings[0]['text'], 'href': start['url'], 'landing': start['url'],
                           'operation_id': None, 'source': 'direct_entry_article'})
            for e in initial.get('elements', []):
                quote = e.get('text') or ''
                if (e.get('visible') and len(quote.strip()) >= 12 and all(norm(a) in norm(quote) for a in aspects)
                        and e.get('native_role') not in ('a', 'input', 'button', 'h1', 'h2', 'h3')
                        and region_matches(initial, e['element_id'], '正文')):
                    passages.append({'node': e['element_id'], 'quote': quote, 'url': start['url'],
                                     'observation_id': start['observation_id'], 'operation_id': None})
    def is_source_page(observation):
        return any(identity == observation['document_identity']
                   or same_url(url, observation['url']) and result_links(observation, start, subject)
                   for identity, url in sources)
    for step in s.trajectory:
        before, after = (s.observation_records[step[k]] for k in ('before_observation_id', 'after_observation_id'))
        if not (before.get('capture_verified') and after.get('capture_verified')):
            continue
        cid = (step.get('target') or {}).get('control_id')
        source_doc = is_source_page(before)
        if step['action'] == 'type':
            query = (step.get('arguments') or {}).get('text') or ''
            val = after['controls'].get(cid, {}).get('value') or {}
            if (norm(subject) in norm(query) and val.get('value_visible') and val.get('value') == query
                    and search_field(before, cid)):
                typed.append({'operation_id': step['operation_id'], 'query': query, 'field':cid,
                              'document_identity': after['document_identity']})
                sources, opened, passages, landing_doc = [], [], [], None
                downward_reading=[]
                if result_links(after, start, subject):
                    sources.append((after['document_identity'], after['url']))
        elif step['action'] in ('click','hotkey') and typed:
            entry = typed[-1]
            field = before['controls'].get(entry['field'], {}).get('value') or {}
            control = before['controls'].get(cid, {})
            keys = [str(k).lower() for k in (step.get('arguments') or {}).get('keys', [])]
            submit_key = step['action'] == 'hotkey' and keys in (['enter'],['return']) and field.get('focused')
            input_form = before['controls'].get(entry['field'], {}).get('binding', {}).get('form_index')
            submit_control = (step['action'] == 'click' and search_button(control) and
                              (input_form is None or control['binding'].get('form_index') == input_form))
            submitted=(before['document_identity'] == entry['document_identity'] and field.get('value') == entry['query']
                    and (submit_key or submit_control) and urlsplit(before['url']).netloc == urlsplit(after['url']).netloc)
            if submitted and result_links(after, start, subject) and all(
                    identity != after['document_identity'] for identity, _ in sources):
                sources.append((after['document_identity'], after['url']))
            article=state(after)
            headings=[e for e in article.get('elements',[]) if e.get('visible') and e.get('native_role')=='h1' and norm(e.get('text',''))==norm(subject)]
            if submitted and before['document_identity']!=after['document_identity'] and len(headings)==1 and any(
                    e.get('visible') and len((e.get('text') or '').strip())>=12 and e.get('native_role') not in ('a','input','button','h1','h2','h3')
                    and region_matches(article,e['element_id'],'正文') for e in article.get('elements',[])):
                landing_doc=after['document_identity'];passages=[]
                opened.append({'text':headings[0]['text'],'href':after['url'],'landing':after['url'],
                               'operation_id':step['operation_id'],'source':'verified_search_submission_direct_article'})
            # Delayed same-document suggestions can appear after the input capture.
            suggestions = (before['document_identity'] == entry['document_identity']
                           and field.get('value') == entry['query'] and bool(result_links(before,start,subject)))
            link = result_links(before, start, subject).get(cid)
            if (step['action'] == 'click' and (source_doc or suggestions) and link
                    and before['document_identity'] != after['document_identity'] and same_url(link['href'], after['url'])):
                landing_doc = after['document_identity']
                passages = []
                opened.append({**link, 'operation_id': step['operation_id'], 'landing': after['url']})
        elif (step['action'] == 'scroll' and landing_doc is not None
              and before['document_identity'] == after['document_identity'] == landing_doc):
            old, new = state(before), state(after)
            if not old.get('scroll') or old.get('scroll') == new.get('scroll'):
                continue
            seen = {e.get('text') for e in old.get('elements', []) if e.get('visible')}
            fresh_body=[e for e in new.get('elements',[]) if e.get('visible') and e.get('text') not in seen
                        and len((e.get('text') or '').strip())>=12 and e.get('native_role') not in ('a','input','button','h1','h2','h3')
                        and region_matches(new,e['element_id'],'正文')]
            if new.get('scroll',[0,0])[1]>old.get('scroll',[0,0])[1] and fresh_body:
                downward_reading.append({'operation_id':step['operation_id'],'observation_id':after['observation_id'],
                                         'visible_new_body':[{'node':e['element_id'],'quote':e['text']} for e in fresh_body]})
            for e in new.get('elements', []):
                quote = e.get('text') or ''
                if (e.get('visible') and quote not in seen and len(quote.strip()) >= 12
                        and all(norm(a) in norm(quote) for a in aspects)
                        and e.get('native_role') not in ('a','input','button','h1','h2','h3')
                        and region_matches(new, e['element_id'], '正文')):
                    passages.append({'node': e['element_id'], 'quote': quote, 'url': after['url'],
                                     'observation_id': after['observation_id'], 'operation_id': step['operation_id']})
        if landing_doc is not None and after['document_identity']==landing_doc and before['document_identity']!=landing_doc:
            page=state(after)
            for e in page.get('elements',[]):
                quote=e.get('text') or ''
                if (e.get('visible') and len(quote.strip())>=12 and all(norm(a) in norm(quote) for a in aspects)
                        and e.get('native_role') not in ('a','input','button','h1','h2','h3') and region_matches(page,e['element_id'],'正文')):
                    passages.append({'node':e['element_id'],'quote':quote,'url':after['url'],
                                     'observation_id':after['observation_id'],'operation_id':step['operation_id']})
    now = state(s.current)
    visible = {(e['element_id'], e.get('text')) for e in now.get('elements', []) if e.get('visible')}
    candidates = [p for p in passages if (p['node'], p['quote']) in visible and same_url(p['url'], s.current['url'])
                  and s.current['document_identity'] == landing_doc]
    selected = None
    ref = getattr(s, 'answer_citation', None)
    if ref:
        verify_evidence([ref])
        branch = load_json(ref['path'])
        reply = branch.get('response') or {}
        origin = s.observation_records.get(reply.get('observation_id'))
        if (branch.get('kind') == 'plan-branch' and branch.get('boundary') == s.binding and origin
                and (branch.get('provider_reply') or {}).get('choice') == reply.get('choice')
                and reply.get('attempt_id') == s.attempt_id and origin['document_identity'] == landing_doc):
            archived = []
            if getattr(s, 'task', {}).get('fragment', {}).get('plan_protocol') in ('webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10','webcollect-banded-conditional-plan-11'):
                # A selected passage remains evidence after useful reading in the
                # same opened document; it is never relabelled as current text.
                for passage in passages:
                    at=next((i for i,row in enumerate(s.trajectory) if row['operation_id']==passage['operation_id']),None)
                    later=s.trajectory[at+1:] if at is not None else []
                    if (later and all(row['action']=='scroll' and all(
                            s.observation_records[row[key]].get('capture_verified') and
                            s.observation_records[row[key]]['document_identity']==landing_doc
                            for key in ('before_observation_id','after_observation_id')) and
                            state(s.observation_records[row['before_observation_id']]).get('scroll') !=
                            state(s.observation_records[row['after_observation_id']]).get('scroll')
                            for row in later)
                            and same_url(passage['url'],s.current['url']) and s.current['document_identity']==landing_doc):
                        archived.append(passage)
            for candidate in candidates + archived:
                if any(option.get('choice') == reply.get('choice') == 'cite:' + candidate['node']
                       and option.get('passage') == candidate for option in branch.get('options', [])):
                    selected = candidate
                    break
    current_source = any(identity == s.current['document_identity'] for identity, _ in sources) or is_source_page(s.current)
    if typed and not current_source and s.current['document_identity'] == typed[-1]['document_identity']:
        field = s.current['controls'].get(typed[-1]['field'], {}).get('value') or {}
        current_source = bool(field.get('value') == typed[-1]['query'] and result_links(s.current,start,subject))
    fragment=getattr(s,'task',{}).get('fragment',{})
    objective_binding=fragment.get('session_objective',{})
    description=(objective_binding.get('objective') or {}).get('description','')
    if not description:
        requested_goal=getattr(s,'requested_goal',None)
        if isinstance(requested_goal,dict):
            description=requested_goal.get('description','')
    requested_scroll=re.search(r'(?:往下|向下)(?:滚动)?阅读|(?:往下|向下)滚动|scroll\s+down',description,re.I)
    # The requirement belongs to the contracted objective itself: a reading
    # contract whose frozen description demands downward reading must not be
    # silently waived because the task binds a different stability protocol
    # version (the raw-drive wwiki break left it false). Legacy sealed receipts
    # keep their original coupling.
    if contract['version']==VERSION and description:
        requires_reading=bool(requested_scroll)
    else:
        requires_reading=bool(fragment.get('action_stability_protocol') in ('webcollect-search-submit-link-stability-3','webcollect-post-action-observation-stability-4') and requested_scroll)
    reading_met=not requires_reading or bool(downward_reading)
    status=('VERIFIED' if reading_met else 'READING_REQUIRED') if selected else 'PASSAGE_AVAILABLE' if candidates else 'UNVERIFIED'
    if direct_entry:
        # The direct contract forbids site search: any search-input action keeps
        # the objective honestly unverified instead of re-labelling the trace.
        if typed and status=='VERIFIED':
            status='UNVERIFIED'
        if landing_doc is None and not opened:
            status='UNVERIFIED'
    return {'status': status,
            'required_downward_reading':requires_reading,'reading_requirement_basis':({'reference':objective_binding.get('reference'),'clause':requested_scroll.group(0),'start':requested_scroll.start()} if requires_reading else None),'downward_reading_satisfied':reading_met,'downward_reading':downward_reading,
            'direct_entry':direct_entry,'direct_entry_search_forbidden':[t['query'] for t in typed] if direct_entry and typed else [],
            'search_inputs': typed, 'opened_results': opened, 'passages': candidates,
            'result_page_current': current_source,
            'selected_passage': selected, 'citation_event': ref if selected else None}


def progress(s, initial_id, contract):
    start = s.observation_records.get(initial_id)
    base = {'kind': contract['kind'], 'required': True, 'is_AI_review': False, 'version': contract['version']}
    if not start or not start.get('capture_verified') or not s.current.get('capture_verified'):
        return {**base, 'status': 'UNVERIFIED'}
    from .direct_article import VERSION as DIRECT_VERSION, progress as direct_progress
    evaluate = direct_progress if contract['version']==DIRECT_VERSION else calc_evidence if contract['kind'] == 'calculation' else reading_evidence
    result = evaluate(s, start, contract)
    if contract['version'] == LEGACY_VERSION and contract['kind'] == 'reading':
        # Preserve the evidence shape of already sealed experimental receipts.
        result.pop('result_page_current')
        result['search_inputs'] = [{k:row[k] for k in ('operation_id','query')} for row in result['search_inputs']]
    return {**base, **result}
