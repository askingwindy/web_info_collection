"""Bound navigation from observed links or actual action-triggered landings."""
from urllib.parse import urlsplit
from .candidate_contract import same_application

LEGACY_PAGE_LIMIT=64
NAV_ACTIONS={'click','double_click','hotkey','type','select','open_url','back'}


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
    from .react_protocol import NATIVE_VERSIONS
    fragment = task['fragment']
    if fragment.get('decision_protocol') in NATIVE_VERSIONS and None in fragment.get('budgets', {}).values():
        return True
    return len(urls) < LEGACY_PAGE_LIMIT


def extend(task, urls, state, previous=None):
    url=state['url']
    from .collect import verify_public_url
    if previous and excluded_article(task, url):
        raise ValueError('ARTICLE_OUTSIDE_RUN_SCOPE')
    verify_public_url(url)
    observed_navigation = task['fragment'].get('navigation_protocol') == 'observed-navigation-2'
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
        if (i and task['fragment'].get('navigation_protocol') == 'observed-navigation-2'
                and states[i-1]['url'] != state['url'] and (not operation or operation['action_type'] not in NAV_ACTIONS)):
            raise ValueError('Navigation URL changed without an actual triggering action')
        extend(task,urls,state,operation)
    return urls
