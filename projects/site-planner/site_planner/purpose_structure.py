"""Primary-region structure evidence, independent of a site's layout tag names."""
from html.parser import HTMLParser
from collections import defaultdict
import re
from .page_purpose_v5 import generic
from webcollect.planning import object_sha256

VERSION='producer-main-structure'
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
BLOCKS={'p','li','dt','dd','td','th','h1','h2','h3','h4','h5','h6','figcaption','label','output'}

class Regions(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes={};self.stack=[];self.units=[];self.acc={};self.title=[];self.lang=''
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);parent=self.stack[-1] if self.stack else None;serial=len(self.nodes)+1
        tokens=(' '.join(a.get(k,'') for k in ('id','class','role'))).lower().split()
        chrome=any(re.fullmatch(r'(?:vp)?(?:footer|header|nav|navbar|sidebar|menu|cookie|contact|search-box)(?:[-_](?:wrapper|container|panel|menu))?',t) for t in tokens)
        blocked=bool(parent and parent['blocked'] or tag in ('script','style','noscript','nav','header','footer','aside')
            or a.get('role') in ('navigation','search','banner','contentinfo') or 'hidden' in a or a.get('aria-hidden')=='true' or chrome)
        region=parent['region'] if parent else None
        main=tag in ('main','article') or a.get('role')=='main' or tag in ('div','section','form') and any(
            not t.startswith(('has-','with-','border-','bg-','text-','color-','font-','theme-')) and re.search(r'(?:^|[-_])(?:main|content|bodycontent|article|articlebody|trs_editor)(?:$|[-_])',t) for t in tokens)
        if main and region is None:region='main:'+str(serial)
        collection=parent['collection'] if parent else None;item=parent['item'] if parent else None
        if tag in ('ul','ol','dl','table'):collection=tag+':'+str(serial)
        if tag in ('li','dt','dd','tr'):item=tag+':'+str(serial)
        node={'id':serial,'tag':tag,'attrs':a,'parent':parent['id'] if parent else None,'children':[],
            'blocked':blocked,'region':region,'collection':collection,'item':item,
            'path':[n['id'] for n in self.stack]+[serial]}
        self.nodes[serial]=node
        if parent:parent['children'].append(serial)
        if tag not in VOID:self.stack.append(node)
        if not blocked and tag in ('input','textarea','select','button','canvas','output'):
            if tag=='input' and a.get('type','text') in ('hidden','submit','button'):return
            text=' '.join(a.get(k,'') for k in ('type','name','aria-label','placeholder','value')).strip()
            self.units.append(self.unit(node,'control',text or ('text' if tag=='input' else '')))
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]['tag']==tag:del self.stack[i:];break
    def unit(self,node,kind,text):
        return {'kind':kind,'tag':node['tag'],'node':node['id'],'path':node['path'],'region':node['region'],
            'collection':node['collection'],'item':node['item'],'text':text,
            **({'href':node['attrs'].get('href',''),'download':'download' in node['attrs']} if kind=='link' else {})}
    def add(self,node,kind,text):
        key=(node['id'],kind)
        if key not in self.acc:
            self.acc[key]=self.unit(node,kind,'');self.units.append(self.acc[key])
        self.acc[key]['text']+=text
    def handle_data(self,text):
        if not text or not self.stack or self.stack[-1]['blocked']:return
        if any(n['tag']=='title' for n in self.stack):self.title.append(text);return
        block=next((n for n in reversed(self.stack) if n['tag'] in BLOCKS),self.stack[-1])
        self.add(block,'heading' if re.fullmatch('h[1-6]',block['tag']) else 'body',text)
        anchor=next((n for n in reversed(self.stack) if n['tag']=='a'),None)
        if anchor:self.add(anchor,'link',text)
    def finish(self):
        units=[];seen=set()
        for unit in self.units:
            unit['text']=' '.join(unit['text'].split())[:1600]
            if not unit['text'] and unit['kind']!='control':continue
            key=object_sha256(unit)
            if key not in seen:units.append(unit);seen.add(key)
        if not any(u['region'] for u in units):
            roots={u['path'][0] for u in units if u['path']}
            if sum(len(u['text']) for u in units if u['kind']=='body')>=45 or sum(u['kind']=='link' for u in units)>=3:
                for u in units:u['region']='fallback:'+str(min(roots)) if roots else None
        # Repeated DIV/ARTICLE cards and direct anchor lists are structural
        # collections. Paragraph citations and globally repeated chrome are not.
        for parent in sorted(self.nodes.values(),key=lambda n:-len(n['path'])):
            if parent['blocked'] or parent['tag'] in ('p','span','label'):continue
            siblings=defaultdict(list)
            for child_id in parent['children']:
                child=self.nodes[child_id]
                if not child['blocked'] and child['tag'] in ('div','section','article','a'):siblings[child['tag']].append(child)
            for tag,children in siblings.items():
                if len(children)<3:continue
                items=[];hrefs=set()
                for child in children:
                    links=[u for u in units if u['kind']=='link' and child['id'] in u['path'] and not generic(u['text']) and u.get('href') and not u['href'].startswith(('#','javascript:'))]
                    if not 1<=len(links)<=6:continue
                    items.append(child);hrefs.update(u['href'] for u in links)
                if len(items)<3 or len(hrefs)<3:continue
                if tag=='a':
                    body=sum(len(u['text']) for u in units if u['kind']=='body' and parent['id'] in u['path'])
                    linked=sum(len(u['text']) for u in units if u['kind']=='link' and parent['id'] in u['path'])
                    if body>max(80,linked*1.7):continue
                for child in items:
                    for u in units:
                        if child['id'] in u['path'] and not u.get('collection'):
                            u['collection']='repeat:'+str(parent['id'])+':'+tag;u['item']='item:'+str(child['id'])
        for i,u in enumerate(units):u['unit_id']='u'+str(i)
        return units

def parse(text):
    parser=Regions();parser.feed(text);units=parser.finish()
    return {'units':units,'title':' '.join(''.join(parser.title).split()),'language':parser.lang,
        'main_region_found':any(u['region'] for u in units),'structure_version':VERSION}

def facts(evidence):
    main=[u for u in evidence['units'] if u.get('region')];out={}
    narrative=[u for u in main if u['kind']=='body' and not u.get('collection') and len(u['text'])>=45]
    narrative_chars=sum(len(u['text']) for u in narrative)
    groups=defaultdict(list)
    for u in main:
        if u.get('collection'):groups[u['collection']].append(u)
    collection_chars=0
    for group,us in groups.items():
        items={u['item'] for u in us if u.get('item') and u['kind'] in ('link','body')}
        links={u.get('href') for u in us if u['kind']=='link' and not generic(u['text'])}
        cells={u['item'] for u in us if u.get('item') and u['tag']=='td'}
        if len(items)<3 or len(links)<3 and len(cells)<3:continue
        chars=sum(len(u['text']) for u in us if u['kind'] in ('body','heading'));collection_chars+=chars
        out['g'+str(len(out))]={'kind':'collection','items':len(items),'body_chars':chars,'regions':sorted({u['region'] for u in us}),
            'unit_ids':[u['unit_id'] for u in us],'primary_eligible':not(narrative_chars>=600 and narrative_chars>chars*1.5)}
    if narrative:
        out['narrative']={'kind':'narrative','body_chars':narrative_chars,'paragraphs':len(narrative),
            'unit_ids':[u['unit_id'] for u in narrative],'regions':sorted({u['region'] for u in narrative}),
            'primary_eligible':not(collection_chars>narrative_chars*2 and len(groups)>=1)}
    editable=[]
    for u in main:
        if u['kind']!='control' or u['tag'] not in ('input','select','textarea'):continue
        if re.search(r'\b(?:search|query|keyword|wd|q|s)\b|搜索|检索|站内',u['text'],re.I):continue
        editable.append(u)
    commands=[u for u in main if u['tag'] in ('button','input') and re.search('计算|转换|生成|校验|提交|运行|发送|convert|calculate|submit',u['text'],re.I)]
    if editable and (len(editable)>=2 or commands):
        us=editable+commands
        document_title=bool(re.search(r'API|接口|开发文档|返回参数|请求示例',evidence.get('title',''),re.I))
        out['tool']={'kind':'tool','editable_controls':len(editable),'command_controls':len(commands),'regions':sorted({u['region'] for u in us}),
            'unit_ids':[u['unit_id'] for u in us],'primary_eligible':not(document_title and narrative_chars>=600)}
    downloads=[u for u in main if u['kind']=='link' and (u.get('download') or re.search(r'\.(?:exe|dmg|apk|msi|zip)(?:[?#]|$)',u.get('href',''),re.I))]
    if downloads and narrative_chars<1500:
        out['download']={'kind':'download','links':len(downloads),'regions':sorted({u['region'] for u in downloads}),
            'unit_ids':[u['unit_id'] for u in downloads],'primary_eligible':True}
    return out

def accepts(page,quote_ids,structure_ids,evidence):
    menu=evidence['menu'];structures=evidence['structures']
    if not quote_ids or not all(q in menu for q in quote_ids):return False,'invalid_or_missing_quote_ids'
    kinds={'功能页':'tool','检索或列表':'collection','内容详情':'narrative','第三方介绍或下载':'download'}
    if page not in kinds:return False,'UNKNOWN'
    if not structure_ids or not all(key in structures for key in structure_ids):return False,'invalid_or_missing_structure_ids'
    cited=[menu[q] for q in quote_ids]
    for key in structure_ids:
        fact=structures[key]
        if fact['kind']!=kinds[page] or not fact['primary_eligible']:continue
        if any(u['unit_id'] in fact['unit_ids'] or u['kind']=='heading' and u['region'] in fact['regions'] for u in cited):return True,None
    return False,'type_structure_or_citation_scope_not_proven'
