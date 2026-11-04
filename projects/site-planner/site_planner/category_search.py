"""Public search receipts used when the independent BigModel search service is held."""
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from webcollect.batch_core import OutcomeUnknown, save_json
from webcollect.planning import verify_evidence
from .discovery_tools import reference
from .site_pool import page_uri


class OrganicResults(HTMLParser):
    """360 marks the original destination on an organic result title."""
    def __init__(self, engine='360-public'):
        super().__init__()
        self.engine=engine
        self.rows = []
        self.title = False
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h3':
            self.title = 'res-title' in attrs.get('class','').split()
        if self.engine=='ddg-html' and tag=='a' and 'result__a' in attrs.get('class','').split():
            href=attrs.get('href','')
            redirect=urlsplit(href)
            if redirect.path in ('/l/','/l') and redirect.hostname in (None,'duckduckgo.com','www.duckduckgo.com'):
                href=parse_qs(redirect.query).get('uddg',[''])[0]
            self.link={'link':href,'title':''}
        elif self.engine=='360-public' and self.title and tag == 'a' and attrs.get('data-mdurl'):
            self.link = {'link':attrs['data-mdurl'],'title':''}

    def handle_data(self, data):
        if self.link is not None:
            self.link['title'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.link is not None:
            self.rows.append(self.link)
            self.link = None
        if tag == 'h3':
            self.title = False


PUBLIC_ENGINES=('360-public','ddg-html','bing-rss')


def public_engine(pool, unit):
    # A verification redirect, rate limit or unreadable result page is a reason to rest that index.
    with pool.connect() as con:
        blocked={r[0] for r in con.execute("SELECT DISTINCT json_extract(payload,'$.search_engine') FROM tool_requests "
            "WHERE kind='search' AND state='unknown' AND finished>=?",(time.time()-1800,))}
    available=[e for e in PUBLIC_ENGINES if e not in blocked]
    if not available:
        raise OutcomeUnknown('Public search indexes are cooling down. Retain original receipts.')
    return available[unit % len(available)]


def public_search(pool, session, query, root, *, engine, maximum, batch_scope, count):
    if engine not in PUBLIC_ENGINES or not 1 <= len(query) <= 70 or not 1 <= count <= 50:
        raise ValueError('Invalid public search parameters')
    payload = {'search_engine':engine,'search_query':query,'count':count}
    rid, old = pool.reserve_tool(session,'search',query,payload,maximum=maximum,batch_scope=batch_scope)
    if old is not None:
        verify_evidence([old['raw_response'],old['reference']])
        return old
    endpoint={'360-public':'https://www.so.com/s?', 'ddg-html':'https://html.duckduckgo.com/html/?',
              'bing-rss':'https://cn.bing.com/search?format=rss&'}[engine]
    url=endpoint+urlencode({'q':query,**({'kl':'cn-zh'} if engine=='ddg-html' else {})})
    class SearchRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urlsplit(newurl).scheme != 'https' or urlsplit(newurl).hostname != urlsplit(url).hostname:
                raise ValueError('Public search left its original provider')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    raw_ref = None
    status = None
    try:
        with build_opener(SearchRedirect).open(Request(url,headers={'User-Agent':'WebCollectSitePlanner/0.1'}),timeout=25) as response:
            status=getattr(response,'status',None)
            raw = response.read(2_000_001)
        path = Path(root)/('search-'+rid+('.xml' if engine=='bing-rss' else '.html'))
        with path.open('xb') as stream:
            stream.write(raw)
        raw_ref = reference(path)
        if len(raw)>2_000_000:
            raise ValueError('Public search response exceeds byte bound')
        if engine != 'bing-rss':
            parser = OrganicResults(engine)
            parser.feed(raw.decode('utf-8',errors='replace'))
            rows = parser.rows
            if not rows:
                raise ValueError('No verifiable organic result markup in public search response')
        else:
            feed = ET.fromstring(raw)
            if feed.tag != 'rss' or feed.find('channel') is None:
                raise ValueError('Expected public RSS results')
            rows = [{'link':item.findtext('link'),'title':item.findtext('title') or '',
                     'content':item.findtext('description') or ''} for item in feed.findall('./channel/item')]
        parsed = []
        for row in rows:
            try:
                page_uri(row['link'])
            except (ValueError,TypeError,AttributeError):
                continue
            parsed.append(row)
            if len(parsed)>=count:
                break
        path = Path(root)/('search-'+rid+'.json')
        save_json(path,{'engine':engine,'query':query,'raw_response':raw_ref,'search_result':parsed})
        ref = reference(path)
        hits = [{**row,'index':i,'uri':page_uri(row['link']),'reference':ref} for i,row in enumerate(parsed)]
        result = {'engine':engine,'request_id':rid,'query':query,'results':hits,'raw_result_count':len(rows),
                  'reference':ref,'raw_response':raw_ref,'usage':None}
        pool.settle_tool(rid,'succeeded',result)
        return result
    except Exception as error:
        pool.settle_tool(rid,'unknown',{'engine':engine,'error_type':type(error).__name__,
                         'http_status':getattr(error,'code',status),'raw_response':raw_ref,
                         'reason':str(error)[:200] if isinstance(error,ValueError) else type(error).__name__})
        raise OutcomeUnknown('Public search unavailable; original request retained: '+rid) from error
