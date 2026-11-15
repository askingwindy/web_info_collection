"""Bound navigation from observed links or actual action-triggered landings."""
from urllib.parse import urlsplit
from .plan_protocol import (DELAYED_NAVIGATION_PROTOCOL as DELAYED_PROTOCOL,
                            NAVIGATION_PROTOCOL, REACT_PROTOCOL)

LEGACY_PAGE_LIMIT=64
NAV_ACTIONS={'click','double_click','hotkey','type','select','open_url','back'}
# Sealed historical records keep their originally frozen names; new fragments
# only ever carry the stable names. Read-side dual acceptance.
SEALED_DELAYED_PROTOCOLS=(DELAYED_PROTOCOL,'webcollect-explicit-href-landing-1')
SEALED_NAVIGATION_PROTOCOLS=(NAVIGATION_PROTOCOL,'observed-navigation-2')
SEALED_DECISION_PROTOCOLS=(REACT_PROTOCOL,'webcollect-react-native-2','webcollect-react-native-3')


def delayed_landing(operation, source, current, landed, *, same_tab, no_other_action, no_new_tab):
    """Exact observed href only. This is attribution, never a replay/click."""
    if not (same_tab and no_other_action and no_new_tab and operation
            and operation.get('action_type') in ('click','double_click')
            and current.get('url') == source.get('url') and landed.get('url') != current.get('url')):
        return None
    cid=operation.get('evidence',{}).get('anchor_element_id')
    control=next((c for c in source.get('capture_controls',[]) if c.get('element_id')==cid),None)
    if not control or control.get('target') not in (None,'','_self') or control.get('href') != landed.get('url'):
        return None
    return {'rule_version':DELAYED_PROTOCOL,'operation_id':operation['operation_id'],
            'source_url':source['url'],'href':control['href'],'landed_url':landed['url'],
            'same_tab':True,'no_other_action':True,'no_new_tab':True,'control_id':cid}


def excluded_article(task, url):
    if not task['fragment'].get('skip_wechat_articles') or not url:
        return False
    try:
        link = urlsplit(url)
        return (link.scheme in ('http','https') and (link.hostname or '').rstrip('.') == 'mp.weixin.qq.com'
                and (link.path == '/s' or link.path.startswith('/s/')))
    except ValueError:
        return False


def has_page_capacity(task, urls):
    fragment = task['fragment']
    if fragment.get('decision_protocol') in SEALED_DECISION_PROTOCOLS and None in fragment.get('budgets', {}).values():
        return True
    return len(urls) < LEGACY_PAGE_LIMIT


def _source_binding(source, operation):
    if not source or not operation:return None
    evidence=operation.get('evidence', {})
    cid=evidence.get('anchor_element_id') or evidence.get('focused_element_id') or operation.get('control_id')
    controls=source.get('capture_controls', [])
    if not controls and isinstance(source.get('controls'),dict):
        controls=[dict(row.get('binding') or {},element_id=key) for key,row in source['controls'].items()]
    return next((row for row in controls if row.get('element_id')==cid),None)


def exact_destination(source, operation):
    """Only a bound href or the browser's frozen native form encoding."""
    from urllib.parse import urljoin
    if not source or not operation:return None
    binding=_source_binding(source,operation)
    action=operation.get('action_type') or operation.get('action')
    if action in ('click','double_click') and source.get('capture_controls'):
        from .screenshot_execution import navigation_carrier
        evidence=operation.get('evidence',{})
        cid=evidence.get('anchor_element_id') or operation.get('control_id')
        carrier=navigation_carrier(source,cid)
        if carrier:return urljoin(source['url'],carrier['href'])
    if not binding:return None
    if action in ('click','double_click') and binding.get('href'):
        return urljoin(source['url'],binding['href'])
    form=binding.get('form_submission')
    if not form:return None
    if action=='click':
        if (binding.get('tag') not in ('button','input') or binding.get('input_type')!='submit'
                or binding.get('selector')!=form.get('submitter_selector')):return None
    elif action=='hotkey':
        if [str(k).lower() for k in operation.get('arguments',operation).get('keys',[])]!=['enter']:return None
        if not any(v.get('element_id')==binding['element_id'] and v.get('focused') is True for v in source.get('values',[])):return None
    else:return None
    from .navigation import native_form_encoding
    try:return native_form_encoding(form,source['url'])[0]
    except (ValueError,KeyError,TypeError):return None


def destination_allowed(task, url, page_urls=None, *, source=None, operation=None, proof=None):
    """Frozen pages or exact action/source permission, never an observed host."""
    from .collect import verify_public_url
    try:
        verify_public_url(url)
        if excluded_article(task,url):return False
        registered=page_urls if page_urls is not None else task['fragment'].get('page_urls',[])
        if url in registered:return True
        if source and source.get('url') in registered and operation:
            expected = exact_destination(source,operation)
            chain = (proof or {}).get('http_navigation') if isinstance(proof,dict) else None
            if isinstance(proof,dict) and proof.get('kind')=='http_navigation':chain=proof
            if expected and chain:
                from .navigation import validate_http_chain
                validate_http_chain(chain,expected,url,source_url=source['url'],
                                    operation_id=operation.get('operation_id'))
                if (proof or {}).get('kind')=='native_form':
                    from .plan_evidence import validate_native_form_popup
                    validate_native_form_popup(proof,operation,source,url)
                else:
                    first=chain['requests'][0]
                    binding=_source_binding(source,operation) or {}
                    form=binding.get('form_submission')
                    if form and not binding.get('href'):
                        from .navigation import native_form_encoding
                        _,encoded=native_form_encoding(form,source['url'])
                        if first.get('method') != form['method'].upper():return False
                        if form['method']=='post' and (first.get('post_data') != encoded
                                or first.get('content_type','').split(';')[0].strip()!=form['enctype']):return False
                        if form['method']=='get' and first.get('post_data') not in (None,''):return False
                    elif first.get('method') != 'GET':return False
                return True
            if expected==url:
                if proof and proof.get('kind')=='native_form':
                    from .plan_evidence import validate_native_form_popup
                    validate_native_form_popup(proof,operation,source,url)
                return True
        if 'candidate_binding' in task:return False
        hosts={verify_public_url(task['site_uri']),verify_public_url(task['initial_url']),*task.get('allowed_hosts',[])}
        return verify_public_url(url,hosts) in hosts
    except (ValueError,KeyError,TypeError):
        return False


def check_url(task, url, allowed_hosts=None, page_urls=None):
    """Entry, dispatch and replay all use frozen or earned exact pages."""
    if 'candidate_binding' in task:
        from .candidate_contract import guard_claim
        guard_claim(task)
    if not destination_allowed(task,url,page_urls):
        raise ValueError('NAVIGATION_SOURCE_UNPROVEN: destination outside frozen or earned exact pages')


def admit_landing(task, page_urls, url, operation=None, *, source=None, proof=None):
    if not destination_allowed(task,url,page_urls,source=source,operation=operation,proof=proof):return 'out_of_scope'
    if url not in page_urls:
        if not has_page_capacity(task,page_urls):return 'capacity'
        page_urls.append(url)
    return 'allowed'


def extend(task, urls, state, previous=None, *, source=None, proof=None):
    """Register actual landings only; observing links never expands ownership."""
    outcome=admit_landing(task,urls,state['url'],previous,source=source,proof=proof)
    if outcome=='out_of_scope':raise ValueError('NAVIGATION_SOURCE_UNPROVEN: destination has no exact permission')
    if outcome=='capacity':raise ValueError('Candidate page scope limit reached')
    return urls


def verify_path(task, states, operations, proofs=None):
    urls=list(task['fragment']['page_urls'])
    for i,state in enumerate(states):
        operation=operations[i-1] if i else None
        source=states[i-1] if i else None
        if i and source['url']!=state['url'] and (not operation or operation.get('action_type') not in NAV_ACTIONS):
            raise ValueError('Navigation URL changed without an actual triggering action')
        extend(task,urls,state,operation,source=source,proof=(proofs[i-1] if proofs and i else None))
    return urls
