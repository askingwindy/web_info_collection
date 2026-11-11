"""Bound navigation from observed links or actual action-triggered landings."""
from urllib.parse import urlsplit
from .candidate_contract import same_application
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


def extend(task, urls, state, previous=None):
    url=state['url']
    from .collect import verify_public_url
    if previous and excluded_article(task, url):
        raise ValueError('ARTICLE_OUTSIDE_RUN_SCOPE')
    verify_public_url(url)
    observed_navigation = task['fragment'].get('navigation_protocol') in SEALED_NAVIGATION_PROTOCOLS
    if not observed_navigation and not same_application(task,url): raise ValueError('Candidate navigation left evidence-backed application')
    if url not in urls:
        if not previous or previous['action_type'] not in NAV_ACTIONS:
            raise ValueError('Unobserved navigation has no actual triggering action')
        if previous['action_type']=='open_url' and previous['arguments']['url'] not in urls:
            raise ValueError('Navigation URL was never observed')
        if not has_page_capacity(task, urls): raise ValueError('Candidate page scope limit reached')
        urls.append(url)
    observed = set(urls)
    for control in state.get('capture_controls',[]):
        href=control.get('href')
        if not href or href in observed or excluded_article(task,href) or not has_page_capacity(task, urls): continue
        try:
            verify_public_url(href)
            if observed_navigation or same_application(task,href):
                urls.append(href)
                observed.add(href)
        except ValueError: pass
    return urls


def verify_path(task, states, operations):
    urls=list(task['fragment']['page_urls'])
    for i,state in enumerate(states):
        operation = operations[i-1] if i else None
        if (i and task['fragment'].get('navigation_protocol') in SEALED_NAVIGATION_PROTOCOLS
                and states[i-1]['url'] != state['url'] and (not operation or operation['action_type'] not in NAV_ACTIONS)):
            raise ValueError('Navigation URL changed without an actual triggering action')
        extend(task,urls,state,operation)
    return urls
