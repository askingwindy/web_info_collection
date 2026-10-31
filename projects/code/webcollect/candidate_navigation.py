"""Bound navigation from observed links or actual action-triggered landings."""
from .candidate_contract import same_application

MAX_PAGES=64
NAV_ACTIONS={'click','double_click','hotkey','type','select','open_url','back'}


def extend(task, urls, state, previous=None):
    url=state['url']
    if not same_application(task,url): raise ValueError('Candidate navigation left evidence-backed application')
    if url not in urls:
        if not previous or previous['action_type'] not in NAV_ACTIONS:
            raise ValueError('Unobserved navigation has no actual triggering action')
        if previous['action_type']=='open_url' and previous['arguments']['url'] not in urls:
            raise ValueError('Navigation URL was never observed')
        if len(urls)>=MAX_PAGES: raise ValueError('Candidate page scope limit reached')
        urls.append(url)
    for control in state.get('capture_controls',[]):
        href=control.get('href')
        if not href or href in urls or len(urls)>=MAX_PAGES: continue
        try:
            if same_application(task,href): urls.append(href)
        except ValueError: pass
    return urls


def verify_path(task, states, operations):
    urls=list(task['fragment']['page_urls'])
    for i,state in enumerate(states):
        extend(task,urls,state,operations[i-1] if i else None)
    return urls
