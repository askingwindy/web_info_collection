"""Section provenance from the archived rendered DOM, without retrieving a page."""
from html.parser import HTMLParser
from pathlib import Path
import re

BLOCKS={'p','li','dd','dt','td','th','blockquote','pre'}
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


def norm(text):
    return re.sub(r'\s+','',text).removesuffix('[编辑]').removesuffix('编辑')


class Sections(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.counts={};self.rows=[];self.headings=[]

    def handle_starttag(self,tag,attrs):
        parent=self.stack[-1] if self.stack else None
        counts=parent['counts'] if parent else self.counts
        counts[tag]=counts.get(tag,0)+1
        selector=(parent['selector']+' > ' if parent else '')+f'{tag}:nth-of-type({counts[tag]})'
        attrs=dict(attrs)
        node={'tag':tag,'selector':selector,'text':'','counts':{},'sections':list(self.headings),
              'main':bool(parent and parent['main']) or tag in ('main','article') or attrs.get('role')=='main',
              'excluded':bool(parent and parent['excluded']) or tag in ('nav','aside','header','footer','form','script','style'),
              'block_child':False}
        if parent and tag in BLOCKS:parent['block_child']=True
        if tag not in VOID:self.stack.append(node)

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_data(self,text):
        for node in self.stack:node['text']+=text

    def handle_endtag(self,tag):
        index=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i]['tag']==tag),None)
        if index is None:return
        for node in reversed(self.stack[index:]):
            if re.fullmatch('h[1-6]',node['tag']) and node['main'] and not node['excluded']:
                level=int(node['tag'][1]);self.headings=[h for h in self.headings if h[0]<level]
                self.headings.append((level,norm(node['text'])))
            elif node['tag'] in BLOCKS and node['main'] and not node['excluded'] and not node['block_child'] and norm(node['text']):
                self.rows.append(node)
        self.stack=self.stack[:index]


def archived_rows(observation):
    """Read only the archived rendered document; callers never fetch HTML."""
    ref=observation.get('html_ref') or observation.get('evidence',{}).get('html')
    if ref:
        from .planning import verify_evidence
        verify_evidence([ref])
        html=Path(ref['path']).read_text()
    else:
        html=observation.get('html')
    if html is None:return []
    parser=Sections();parser.feed(html)
    return parser.rows


def section_rows(observation, section):
    label=norm(section)
    return [r for r in archived_rows(observation) if label in [title for _,title in r['sections']]]


def section_titles(observation,state,node):
    selector=next((b.get('selector') for b in state.get('capture_controls',[]) if b['element_id']==node),None)
    matches=[r for r in archived_rows(observation) if r['selector']==selector]
    return [title for _,title in matches[0]['sections']] if len(matches)==1 else []


def section_contains(observation,state,node,section):
    selector=next((b.get('selector') for b in state.get('capture_controls',[]) if b['element_id']==node),None)
    return bool(selector and any(r['selector']==selector for r in section_rows(observation,section)))
