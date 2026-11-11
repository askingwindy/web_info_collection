"""Observed Jyshare grid/editor adapter and independent table-structure oracle.

Blank size tiles and editor cells use a separately scoped synchronous visual
adapter, never invented text labels. Development actions are not production
approval; every capture still requires its original-frame semantic review.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit

ADAPTER_ID = 'jyshare-html-table-widget-1'
STRATEGY_ID = 'html-table-construction-v1'
URI = 'https://www.jyshare.com/front-end/7688/'
GRID_SELECTOR = '#content > .tg__container > .tg__cells'
SIZE_SELECTOR = GRID_SELECTOR + ' > .tg__cell[row="2"][col="2"]'
TABLE_SELECTOR = '#content > .tbl__container > table.tbl'
EXPECTED_MATRIX = [['项目', '数量'], ['苹果', '3']]
SOURCE_DOM_SHA256 = 'f392d00c925b92c2d5d4030f70c99d2f2656db867ec57f6de8ee3577e73e2a07'
VISUAL_ADAPTER_ID = 'jyshare-html-table-visual-1'
VISUAL_KINDS = ('jyshare-table-size-cell', 'jyshare-table-editor-cell')


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


def cell_selector(row, column):
    if type(row) is not int or type(column) is not int or not 1 <= row <= 2 or not 1 <= column <= 2:
        raise ValueError('Only the bounded 2 by 2 editor is supported')
    return TABLE_SELECTOR + f' > tbody > tr:nth-child({row}) > td:nth-child({column}) > div.tbl__area[contenteditable="true"]'


# Full viewport/ancestor-opacity and multi-point hit checks bind geometry. They
# do not replace original-pixel review of the unlabeled grid or the cell glyphs.
_JS_COMMON = r'''
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/front-end/7688/')return empty;
 const id='jyshare-html-table-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const rect=e=>{const r=e.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom];};
 const visible=e=>{
  if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||e.closest('[inert],[aria-hidden=true]'))return false;
  for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.visibility!=='visible'||Number(s.opacity)<1)return false;}
  const r=e.getBoundingClientRect();
  if(!(r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight))return false;
  for(const fx of [.15,.5,.85])for(const fy of [.15,.5,.85]){
   const h=document.elementFromPoint(r.left+r.width*fx,r.top+r.height*fy);
   if(!h||!(h===e||e.contains(h)))return false;
  }
  return true;
 };
'''

HTML_TABLE_INVENTORY_JS = '() => {' + _JS_COMMON + r'''
 const root=one('#content'),container=one('#content > .tg__container');
 const title=container&&one(':scope > h3.tg__title',container),size=container&&one(':scope > .tg__size > p',container);
 const grid=container&&one(':scope > .tg__cells',container);
 if(!root||!container||root.children.length!==1||container.children.length!==3||!title||!size||!grid||
    !visible(title)||!visible(size)||clean(title.innerText)!=='选择表格大小'||clean(size.innerText)!=='1 x 1')
  return fail('Initial size-selector identity, title or visible default changed');
 const cells=[...grid.children];
 if(cells.length!==100||document.querySelector('table.tbl,.tbl__area'))return fail('Expected untouched 10 by 10 size grid');
 const observed=[];
 for(let i=0;i<cells.length;i++){
  const e=cells[i],row=Math.floor(i/10)+1,col=i%10+1;
  if(e.localName!=='div'||!e.classList.contains('tg__cell')||e.getAttribute('row')!==String(row)||
     e.getAttribute('col')!==String(col)||e.children.length||clean(e.textContent)||!visible(e)||
     e.classList.contains('tg__cell_selected')!==(i===0))return fail('Size tile order, identity, blank state or visibility changed');
  const r=rect(e);observed.push({row,column:col,rect:r,tag:'div',visible:true,text:''});
 }
 // Verify the visual grid rather than trusting row/col attributes alone.
 for(let i=0;i<observed.length;i++){
  const a=observed[i],rowStart=observed[Math.floor(i/10)*10],colStart=observed[i%10];
  if(Math.abs(a.rect[1]-rowStart.rect[1])>.5||Math.abs(a.rect[0]-colStart.rect[0])>.5||
     (i%10&&observed[i-1].rect[2]>=a.rect[0])||(i>=10&&observed[i-10].rect[3]>=a.rect[1]))
   return fail('Grid attribute ordering disagrees with visual geometry');
 }
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'HTML 表格生成器',
   state:'size-selection',selector:'#content > .tg__container > .tg__cells',title:'选择表格大小',size_text:'1 x 1',
   rows:10,columns:10,tiles:observed,fields:[],viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY,
   target_visual_kind:'unlabeled-size-grid',production_visual_support:'review-required'}],result_targets:[],widget_rejections:[]};
}'''

HTML_TABLE_RESULT_JS = '() => {' + _JS_COMMON + r'''
 const table=one('#content > .tbl__container > table.tbl');
 if(!table||document.querySelector('.tg__container')||table.querySelector('table'))return fail('Missing unique generated table');
 const bodies=[...table.children].filter(e=>e.localName==='tbody');
 if(bodies.length!==1||table.rows.length!==2||bodies[0].children.length!==2||!visible(table))return fail('Expected fully visible two-row table');
 const cells=[],matrix=[];
 for(let r=0;r<2;r++){
  const row=table.rows[r];if(row.parentElement!==bodies[0]||row.cells.length!==2||row.children.length!==2)return fail('Expected two direct cells per row');
  const values=[];
  for(let c=0;c<2;c++){
   const td=row.cells[c],area=one(':scope > div.tbl__area[contenteditable=true]',td);
   if(td.localName!=='td'||td.rowSpan!==1||td.colSpan!==1||!area||!area.isContentEditable||!visible(area)||
      td.querySelectorAll('[contenteditable=true]').length!==1)return fail('Cell role, span, editability or visibility changed');
   values.push(area.innerText);
   cells.push({row:r+1,column:c+1,tag:'div',contenteditable:true,visible:true,text:area.innerText,rect:rect(area),
      focused:document.activeElement===area});
  }
  matrix.push(values);
 }
 if(table.querySelectorAll('.tbl__area').length!==4)return fail('Unexpected editor cells');
 return {widgets:[],widget_rejections:[],result_targets:[{selector:'#content > .tbl__container > table.tbl',
  label:'HTML 表格',rows:2,columns:2,visible:true,matrix,cells,html:table.outerHTML,rect:rect(table),viewport:[innerWidth,innerHeight]}]};
}'''


def validate_observation(capability, page, widget):
    if not all(matches_uri(value) for value in (capability['site_uri'], page['page_uri'], widget.get('page_uri', ''))):
        raise ValueError('HTML table requires its exact observed URI')
    expected = {'kind':'non-form-widget', 'adapter_id':ADAPTER_ID, 'label':'HTML 表格生成器',
                'state':'size-selection', 'selector':GRID_SELECTOR, 'title':'选择表格大小', 'size_text':'1 x 1',
                'rows':10, 'columns':10, 'viewport':[1280,720], 'observed_scroll_y':0,
                'fields':[], 'target_visual_kind':'unlabeled-size-grid', 'production_visual_support':'review-required'}
    if any(widget.get(key) != value for key, value in expected.items()) or page.get('result_targets'):
        raise ValueError('HTML table initial state or viewport changed')
    tiles = widget.get('tiles', [])
    if len(tiles) != 100:
        raise ValueError('HTML table requires all 100 observed size tiles')
    import math
    for i, tile in enumerate(tiles):
        row, col = i // 10 + 1, i % 10 + 1
        if (tile.get('row'),tile.get('column'),tile.get('tag'),tile.get('visible'),tile.get('text')) != (row,col,'div',True,''):
            raise ValueError('HTML table tile identity changed')
        box = tile.get('rect', [])
        if (len(box) != 4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in box)
                or not (0 <= box[0] < box[2] <= 1280 and 0 <= box[1] < box[3] <= 720)):
            raise ValueError('HTML table tile geometry missing')
        if abs(box[1]-tiles[(i//10)*10]['rect'][1]) > .5 or abs(box[0]-tiles[i%10]['rect'][0]) > .5:
            raise ValueError('HTML table row/column geometry changed')
        if (i%10 and tiles[i-1]['rect'][2] >= box[0]) or (i>=10 and tiles[i-10]['rect'][3] >= box[1]):
            raise ValueError('HTML table tiles overlap or are reordered')
    return development_operations()


class _TableParser(HTMLParser):
    """Parse actual rows/cells; do not accept a text dump claiming dimensions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.rows=[];self.row=None;self.cell=None;self.tables=0;self.errors=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);parent=self.stack[-1] if self.stack else None
        if tag=='table':
            self.tables+=1
            if self.stack or self.tables!=1:self.errors.append('Nested or multiple table')
        elif not self.stack:
            self.errors.append('Content outside the table')
        if tag in ('script','style','template','iframe') or 'hidden' in attrs or attrs.get('aria-hidden')=='true':
            self.errors.append('Non-result or hidden content')
        if tag=='tr':
            if parent not in ('tbody','thead','tfoot','table') or self.row is not None:self.errors.append('Invalid row nesting')
            self.row=[]
        if tag in ('td','th'):
            if parent!='tr' or self.cell is not None or self.row is None:self.errors.append('Invalid cell nesting')
            if attrs.get('rowspan','1')!='1' or attrs.get('colspan','1')!='1':self.errors.append('Spanning cells unsupported')
            self.cell=[]
        if tag=='br' and self.cell is not None:self.cell.append('\n')
        if tag not in ('br','col','hr','img','input','meta','link'):self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1]!=tag:
            self.errors.append('Unbalanced table markup');return
        if tag in ('td','th'):
            if self.row is not None:self.row.append(''.join(self.cell or []).strip())
            self.cell=None
        if tag=='tr':
            self.rows.append(self.row or []);self.row=None
        self.stack.pop()

    def handle_data(self, data):
        if self.cell is not None:self.cell.append(data)
        elif data.strip():self.errors.append('Text outside a cell')


def parse_table_matrix(html):
    if not isinstance(html,str) or not html.strip():raise ValueError('Missing table HTML')
    parser=_TableParser();parser.feed(html);parser.close()
    if parser.errors or parser.stack or parser.tables!=1 or not parser.rows or not parser.rows[0] or len({len(r) for r in parser.rows})!=1:
        raise ValueError('Invalid rectangular table HTML: '+', '.join(parser.errors))
    return parser.rows


def verify_table_result(result):
    """Require independent structure parsing plus observed visible editor cells."""
    if not isinstance(result,dict) or result.get('selector')!=TABLE_SELECTOR or result.get('visible') is not True or result.get('viewport')!=[1280,720]:
        return False
    try:matrix=parse_table_matrix(result['html'])
    except (KeyError,ValueError):return False
    if matrix!=EXPECTED_MATRIX or result.get('matrix')!=EXPECTED_MATRIX or (result.get('rows'),result.get('columns'))!=(2,2):return False
    cells=result.get('cells',[])
    return len(cells)==4 and all((cell.get('row'),cell.get('column'),cell.get('tag'),cell.get('contenteditable'),
        cell.get('visible'),cell.get('text'))==(i//2+1,i%2+1,'div',True,True,EXPECTED_MATRIX[i//2][i%2]) for i,cell in enumerate(cells))


def verify_synchronized_table_result(evidence):
    """Production terminal oracle: exact matrix plus snapshot glyph/geometry proof."""
    if not isinstance(evidence,dict) or any(evidence.get(key)!=value for key,value in {
        'adapter_id':VISUAL_ADAPTER_ID,'kind':VISUAL_KINDS[1],'rows':2,'columns':2,
        'matrix':EXPECTED_MATRIX,'source':'synchronized_browser_dom_geometry',
        'full_viewport':True,'occlusion_checked':True,'row':1,'column':1}.items()):return False
    if not _valid_geometry(evidence.get('geometry'),2,2):return False
    try:return parse_table_matrix(evidence['html'])==EXPECTED_MATRIX
    except (KeyError,ValueError):return False


def _valid_geometry(geometry,rows,columns):
    import math
    if not isinstance(geometry,list) or len(geometry)!=rows*columns:return False
    for i,box in enumerate(geometry):
        if (not isinstance(box,list) or len(box)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in box)
                or not (0<=box[0]<box[2]<=1280 and 0<=box[1]<box[3]<=720)):return False
        row_first,col_first=geometry[i//columns*columns],geometry[i%columns]
        if (abs(box[1]-row_first[1])>.5 or abs(box[3]-row_first[3])>.5 or
                abs(box[0]-col_first[0])>.5 or abs(box[2]-col_first[2])>.5 or
                i%columns and geometry[i-1][2]>box[0]+.5 or i>=columns and geometry[i-columns][3]>box[1]+.5):return False
    return True


def validate_table_assertion_scope(task,condition):
    if condition!={'selector':TABLE_SELECTOR,'html_table_matrix':EXPECTED_MATRIX} or not all(
        matches_uri(task.get(key,'')) for key in ('initial_url','site_uri')) or task.get('deterministic_strategy',{}).get('id')!=STRATEGY_ID:
        raise ValueError('HTML table matrix assertion requires the exact observed URI, strategy and fixed matrix')


def development_operations():
    """Nine explicit necessary actions; NOT a valid M4 task until visual support."""
    actions=[{'operation_id':'choose-size','action_type':'click','selector':SIZE_SELECTOR,
              'goal':'选择尺寸网格的第2行第2列，创建2行2列空表'}]
    for row in range(1,3):
        for column in range(1,3):
            value=EXPECTED_MATRIX[row-1][column-1];selector=cell_selector(row,column)
            actions.extend([{'operation_id':f'cell-{row}-{column}-focus','action_type':'click','selector':selector,
                             'goal':f'聚焦第{row}行第{column}列空白单元格'},
                            {'operation_id':f'cell-{row}-{column}-type','action_type':'type','selector':selector,
                             'arguments':{'text':value},'goal':f'在第{row}行第{column}列填写「{value}」'}])
    return actions


def html_table_spec(capability,page,widget,strategy_version):
    validate_observation(capability,page,widget)
    return {'page_uri':URI,'form_label':widget['label'],'widget_adapter':ADAPTER_ID,
            'goal':'在「HTML 表格生成器」中创建2行2列的表格，第一行依次填写「项目」「数量」，第二行依次填写「苹果」「3」，查看完整表格。',
            'expected_matrix':[row[:] for row in EXPECTED_MATRIX],
            'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,'business_goal':'HTML表格结构与内容构建',
                'operator':'independent HTML row/cell parsing','expected_rows':2,'expected_columns':2,
                'assurance':'Requires original-frame review and a separately validated unlabeled grid/cell visual target adapter'},
            'production_status':'REQUIRES_SYNCHRONIZED_GRID_CELL_VISUAL_EVIDENCE'}


def production_operations():
    """The observed row-major editing sequence, with exact prior cell contents."""
    from copy import deepcopy
    operations=development_operations();matrix=[['',''],['','']]
    operations[0]['evidence']={'target_visual_kind':VISUAL_KINDS[0],'adapter_id':VISUAL_ADAPTER_ID,
                             'row':2,'column':2,'rows':10,'columns':10,'expected_matrix':None}
    for index,operation in enumerate(operations[1:]):
        row,column=index//4+1,(index//2)%2+1
        operation['evidence']={'target_visual_kind':VISUAL_KINDS[1],'adapter_id':VISUAL_ADAPTER_ID,
                              'row':row,'column':column,'rows':2,'columns':2,'expected_matrix':deepcopy(matrix)}
        if operation['action_type']=='type':matrix[row-1][column-1]=operation['arguments']['text']
    return operations


def validate_visual_operation(task,operation):
    """Narrow contract exception; ordinary text/icon rules remain unchanged."""
    if not all(matches_uri(task.get(key,'')) for key in ('initial_url','site_uri')) or task.get('deterministic_strategy',{}).get('id')!=STRATEGY_ID:
        raise ValueError('M4_CAPABILITY_REVIEW_REQUIRED: visual table targets require their exact URI and business')
    expected=next((row for row in production_operations() if row['operation_id']==operation.get('operation_id')),None)
    if expected is None or any(operation.get(key)!=expected.get(key) for key in ('action_type','selector','arguments','evidence')):
        raise ValueError('M4_CAPABILITY_REVIEW_REQUIRED: visual table operation identity or prior matrix changed')
    return True


def validate_visual_target(state,operation):
    """Match operation intent to the actual pre-action synchronized DOM frame."""
    expected=operation.get('evidence',{})
    visual=(state.get('target') or {}).get('visual_target_evidence')
    if not matches_uri(state.get('url','')) or state.get('screen_resolution')!=[1280,720] or not isinstance(visual,dict):
        raise ValueError('M4_VISUAL_TARGET_UNVERIFIED: missing table visual evidence')
    if expected.get('target_label') or expected.get('target_visual_kind') not in VISUAL_KINDS:
        raise ValueError('M4_VISUAL_TARGET_UNVERIFIED: unsupported visual identity or invented label')
    intent={'initial_url':URI,'site_uri':URI,'deterministic_strategy':{'id':STRATEGY_ID}}
    validate_visual_operation(intent,operation)
    checks={'adapter_id':VISUAL_ADAPTER_ID,'kind':expected['target_visual_kind'],
            'row':expected['row'],'column':expected['column'],'rows':expected['rows'],'columns':expected['columns'],
            'matrix':expected['expected_matrix'],'source':'synchronized_browser_dom_geometry',
            'full_viewport':True,'occlusion_checked':True}
    if any(visual.get(key)!=value for key,value in checks.items()):
        raise ValueError('M4_VISUAL_TARGET_UNVERIFIED: row/column, viewport or prior cell contents changed')
    geometry=visual.get('geometry',[])
    if not _valid_geometry(geometry,expected['rows'],expected['columns']):
        raise ValueError('M4_VISUAL_TARGET_UNVERIFIED: incomplete geometry')
    box=geometry[(expected['row']-1)*expected['columns']+expected['column']-1]
    target=state['target'];x,y=target['coordinate']
    if not target.get('hit_valid') or not (box[0]<=x<box[2] and box[1]<=y<box[3]) or any(
            abs(actual-intended)>1 for actual,intended in zip(target['bbox'],box)):
        raise ValueError('M4_VISUAL_TARGET_UNVERIFIED: target coordinates disagree with matrix geometry')
    return True


def compile_html_table(capability,spec,task_version=ADAPTER_ID + '-compiler'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages=[page for page in capability['capabilities'] if page['page_uri']==URI]
    if len(pages)!=1:raise ValueError('HTML table must bind one observed page')
    page=pages[0];widgets=[widget for widget in page.get('widgets',[]) if widget.get('adapter_id')==ADAPTER_ID]
    if len(widgets)!=1 or html_table_spec(capability,page,widgets[0],spec['deterministic_strategy']['version'])!=spec:
        raise ValueError('HTML table specification changed from the observed strategy')
    operations=production_operations();subgoals=[]
    # This terminal assertion runs the independent Python HTML parser against
    # the same saved-frame snapshot that proves complete visible cell glyphs.
    assertions=[{'selector':TABLE_SELECTOR,'html_table_matrix':[row[:] for row in EXPECTED_MATRIX]}]
    operations[0].update(subgoal_id='size',rationale='表格结构须先从尺寸网格创建',expected='出现2行2列的空表格')
    subgoals.append({'id':'size','description':'创建2行2列表格','evidence':[{'final_assertion_index':0}]})
    for index,operation in enumerate(operations[1:]):
        row,column=index//4+1,(index//2)%2+1;sid=f'cell-{row}-{column}'
        operation.update(subgoal_id=sid,rationale='每个单元格承载任务要求的独立内容',
                         expected='光标进入指定空白单元格' if operation['action_type']=='click' else '单元格显示「'+operation['arguments']['text']+'」')
        if operation['action_type']=='type':
            operation['postconditions']=[{'selector':cell_selector(row,column),'contains':EXPECTED_MATRIX[row-1][column-1]}]
            subgoals.append({'id':sid,'description':f'填写第{row}行第{column}列',
                            'evidence':[{'final_assertion_index':0}]})
    operations[-1]['postconditions']=assertions
    task={'task_id':'html-table-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
      'task_version':task_version,'capability_id':capability['capability_id'],'capability_version':capability['version'],
      'task_family':'form-workflow','site_uri':capability['site_uri'],'site_category':capability['site_category'],
      'initial_url':URI,'app_name':page['title'],'instruction':spec['goal'],'task_type':['填写表单'],
      'stop_when_final':True,'content_preparation':False,'operations':operations,'subgoals':subgoals,
      'required_actions':[operation['operation_id'] for operation in operations],'final_assertions':assertions,
      'final_result':'完整显示2行2列表格，第一行为项目、数量，第二行为苹果、3',
      'completion_judgement':'核对完整表格的行列与四个单元格内容，使用独立HTML矩阵解析并审查最终原图。',
      'deterministic_strategy':spec['deterministic_strategy'],'capability_screen_status':capability['status'],
      'capability_review_required':capability['status']!='ready'}
    validate_task_instruction(task['instruction']);validate_plan({'tasks':[task]});validate_m4_task(task)
    return task
