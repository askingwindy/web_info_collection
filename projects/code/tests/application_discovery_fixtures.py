"""Explicit first-party site documents; disposable fixtures only."""
from pathlib import Path
from urllib.parse import urlsplit
from site_planner.application_discovery import Discovery
from site_planner.discovery_tools import reference
from site_planner.qualification import CATEGORY_TAXONOMY_VERSION
from site_planner.entry_selection import VERSION
from webcollect.batch_core import save_json
from webcollect.planning import object_sha256


def document(root, uri, category='在线工具', text='本站提供中文在线计算与单位转换服务'):
    body={'uri':uri,'title':'中文首页','content':text,'chinese':True,'site_evidence':'homepage'}
    path=Path(root)/('homepage-'+object_sha256(body)+'.json');save_json(path,body)
    return {**body,'reference':reference(path)}


def seed(pool, root, uri, category='在线工具', text='本站提供中文在线计算与单位转换服务'):
    p=urlsplit(uri); home=document(root,f'{p.scheme}://{p.netloc}/',category,text)
    aid=pool.pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session',
        'run_id':'OFFLINE-site-fixture','event_id':object_sha256(home),'uri':home['uri'],'name':'受控中文站点',
        'category_hint':'UNKNOWN','source_refs':[home['reference']]})['application_id']
    sites=Discovery(pool,install=True)
    old=sites.get(aid)
    if old: return aid,home
    decision={'version':VERSION,'taxonomy_version':CATEGORY_TAXONOMY_VERSION,'parent_category':category,
              'status':'EVIDENCE_BOUND_AI','references':[home['reference']],
              'evidence':[{'role':'function','uri':home['uri'],'quote':text,'reference':home['reference']}]}
    sites.decide(aid,decision,home)
    return aid,home
