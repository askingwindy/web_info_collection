"""Controlled, network-blocked HTML-table adapter and independent oracle tests."""
from copy import deepcopy
import unittest

from webcollect.html_table_strategy import (URI, ADAPTER_ID, GRID_SELECTOR, TABLE_SELECTOR,
    HTML_TABLE_INVENTORY_JS, HTML_TABLE_RESULT_JS, EXPECTED_MATRIX,
    validate_observation, parse_table_matrix, verify_table_result, development_operations, cell_selector)

STYLE='''<style>*{box-sizing:border-box}body{margin:0;font:16px Arial;background:#f7f7f9;color:#343a40}
.tg__container{margin:80px 100px;width:350px}.tg__title,.tg__size{margin:5px}
.tg__cells{display:grid;grid-template-columns:repeat(10,20px);gap:10px;width:290px}
.tg__cell{width:20px;height:20px;border:1px solid #cfcfcf;cursor:pointer}
.tg__cell_selected{background:#bde2ff;border-color:#91cfff}.tbl__container{margin:100px;width:900px}
table{border-collapse:collapse;width:900px}td{border:1px solid #cfcfcf;padding:0}
.tbl__area{min-width:430px;height:46px;padding:8px}.tbl__resizer{width:1px}</style>'''
HELPERS='''<div class="cm hidden"></div><div class="toolbar__horizontal-line hidden"></div><div class="toolbar__vertical-line hidden"></div><div class="cm__open-btn hidden"><svg class="feather feather-chevron-down" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"></polyline></svg></div><div class="toolbar toolbar_v hidden"></div><div class="toolbar toolbar_h hidden"></div>'''
STYLE=STYLE.replace('</style>','.hidden{display:none}.tbl__container{position:relative}.cm__open-btn{position:absolute;width:25px;height:25px;background:#eee;border-radius:50%}.cm__open-btn svg{width:25px;height:25px}</style>')


def grid_html():
    tiles=''.join(f'<div class="tg__cell{ " tg__cell_selected" if i==0 else ""}" row="{i//10+1}" col="{i%10+1}"></div>' for i in range(100))
    return '<!doctype html><meta charset="utf-8">'+STYLE+'<div id="content"><div class="tg__container"><h3 class="tg__title">选择表格大小</h3><div class="tg__size"><p>1 x 1</p></div><div class="tg__cells">'+tiles+'</div></div></div>'


def table_html(matrix=EXPECTED_MATRIX):
    rows=''.join('<tr>'+''.join('<td><div class="tbl__area" contenteditable="true">'+value+'</div></td>' for value in row)+'</tr>' for row in matrix)
    return '<table class="tbl"><tbody>'+rows+'</tbody><colgroup><col><col></colgroup></table>'


def editor_html(matrix=EXPECTED_MATRIX):
    return '<!doctype html><meta charset="utf-8">'+STYLE+'<div id="content"><div class="tbl__container">'+table_html(matrix)+HELPERS+'</div></div>'


class TableParserTests(unittest.TestCase):
    def test_independent_structure_and_order(self):
        self.assertEqual(parse_table_matrix(table_html()),EXPECTED_MATRIX)
        self.assertEqual(parse_table_matrix('<table><tr><td>A &amp; B</td><td>3</td></tr></table>'),[['A & B','3']])
        self.assertNotEqual(parse_table_matrix(table_html([['项目','苹果'],['数量','3']])),EXPECTED_MATRIX)

    def test_reject_non_rectangular_nested_spanning_hidden_or_malformed(self):
        for html in ('', '<div>2 rows x 2 columns 项目 数量 苹果 3</div>',
                     '<table><tr><td>A</td></tr><tr><td>B</td><td>C</td></tr></table>',
                     '<table><tr><td rowspan="2">A</td></tr></table>',
                     '<table><tr><td colspan="2">A</td></tr></table>',
                     '<table><tr><td><table><tr><td>A</td></tr></table></td></tr></table>',
                     '<table><tr><td hidden>A</td></tr></table>',
                     '<table><tr><td><script>A</script></td></tr></table>',
                     '<table><tr><td>A</tr></table>',table_html()+table_html()):
            with self.subTest(html=html), self.assertRaises(ValueError):parse_table_matrix(html)

    def test_development_operations_are_necessary_explicit_page_actions(self):
        operations=development_operations()
        self.assertEqual([row['action_type'] for row in operations],['click','click','type','click','type','click','type','click','type'])
        self.assertEqual([row['arguments']['text'] for row in operations if row['action_type']=='type'],['项目','数量','苹果','3'])
        self.assertTrue(all('evidence' not in row for row in operations))
        for row,column in [(0,1),(3,1),(True,1),(1,'2')]:
            with self.assertRaises(ValueError):cell_selector(row,column)


class TableInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block')
        async def local_only(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=grid_html())
            else:await route.abort()
        await self.context.route('**/*',local_only);self.page=await self.context.new_page();await self.page.goto(URI)

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def test_read_only_initial_grid_records_true_blank_identity(self):
        before=await self.page.content();inventory=await self.page.evaluate(HTML_TABLE_INVENTORY_JS)
        self.assertEqual(before,await self.page.content());self.assertEqual(inventory['widget_rejections'],[])
        widget=inventory['widgets'][0];page={'page_uri':URI,**inventory}
        self.assertEqual(validate_observation({'site_uri':URI},page,widget),development_operations())
        self.assertEqual(widget['tiles'][11]['row'],2);self.assertEqual(widget['tiles'][11]['column'],2)
        self.assertEqual(widget['tiles'][11]['text'],'');self.assertEqual(widget['production_visual_support'],'review-required')

    async def test_scope_ambiguous_roles_geometry_occlusion_and_missing_tiles_reject(self):
        for mutation in [
            "document.querySelector('.tg__title').textContent='未知网格'",
            "document.querySelector('.tg__size p').textContent='2 x 2'",
            "document.querySelector('.tg__cell').remove()",
            "document.querySelectorAll('.tg__cell')[11].setAttribute('row','1')",
            "document.querySelectorAll('.tg__cell')[11].style.transform='translateX(40px)'",
            "document.querySelectorAll('.tg__cell')[11].textContent='X'",
            "document.querySelector('.tg__cells').style.opacity='0.5'",
            "document.querySelector('.tg__container').style.marginTop='500px'",
            "document.querySelector('#content').insertAdjacentHTML('beforeend','<input>')",
            "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:99\"></div>')"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(grid_html());await self.page.evaluate(mutation)
                value=await self.page.evaluate(HTML_TABLE_INVENTORY_JS)
                self.assertEqual(value['widgets'],[]);self.assertTrue(value['widget_rejections'])
        await self.page.goto(URI+'?different=1')
        self.assertEqual(await self.page.evaluate(HTML_TABLE_INVENTORY_JS),{'widgets':[],'result_targets':[],'widget_rejections':[]})

    async def test_observation_mutations_reject(self):
        inventory=await self.page.evaluate(HTML_TABLE_INVENTORY_JS)
        for change in ('order','rect','count','ready','uri','result'):
            with self.subTest(change=change):
                page={'page_uri':URI,**deepcopy(inventory)};widget=page['widgets'][0]
                if change=='order':widget['tiles'][11]['column']=3
                elif change=='rect':widget['tiles'][11]['rect'][0]+=30
                elif change=='count':widget['tiles'].pop()
                elif change=='ready':widget['production_visual_support']='approved'
                elif change=='uri':widget['page_uri']=URI+'/'
                else:page['result_targets']=[{'text':'existing'}]
                with self.assertRaises(ValueError):validate_observation({'site_uri':URI},page,widget)

    async def test_visible_matrix_agrees_with_independent_html_and_rejects_mutations(self):
        await self.page.set_content(editor_html());inventory=await self.page.evaluate(HTML_TABLE_RESULT_JS)
        self.assertEqual(inventory['widget_rejections'],[]);result=inventory['result_targets'][0]
        self.assertTrue(verify_table_result(result))
        for change in ('matrix','html','visibility','cell','dimension'):
            value=deepcopy(result)
            if change=='matrix':value['matrix'][1][1]='4'
            elif change=='html':value['html']=value['html'].replace('苹果','梨')
            elif change=='visibility':value['visible']=False
            elif change=='cell':value['cells'][2]['row']=1
            else:value['rows']=3
            self.assertFalse(verify_table_result(value),change)
        for mutation in ["document.querySelector('td').rowSpan=2",
                         "document.querySelector('.tbl__area').contentEditable='false'",
                         "document.querySelector('tr').insertAdjacentHTML('beforeend','<td><div class=tbl__area contenteditable=true>extra</div></td>')",
                         "document.querySelector('table').style.marginTop='700px'",
                         "document.querySelector('.tbl__area').style.opacity='0'",
                         "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:99\"></div>')"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(editor_html());await self.page.evaluate(mutation)
                value=await self.page.evaluate(HTML_TABLE_RESULT_JS)
                self.assertEqual(value['result_targets'],[]);self.assertTrue(value['widget_rejections'])

    async def compiled_task(self):
        from webcollect.html_table_strategy import html_table_spec,compile_html_table
        inventory=await self.page.evaluate(HTML_TABLE_INVENTORY_JS)
        page={'page_uri':URI,'title':'HTML 表格生成器',**inventory}
        capability={'site_uri':URI,'capability_id':'controlled-table','version':'test-1','site_category':'工具','status':'ready','capabilities':[page]}
        spec=html_table_spec(capability,page,page['widgets'][0],'test-1')
        return compile_html_table(capability,spec)

    async def show_cell_menu(self,row=1,column=1):
        await self.page.evaluate('''({row,column})=>{
          const area=document.querySelector(`table.tbl > tbody > tr:nth-child(${row}) > td:nth-child(${column}) > .tbl__area`);
          area.focus();area.classList.add('tbl__area_selected');
          const parent=area.closest('.tbl__container'),menu=parent.querySelector(':scope > .cm__open-btn');
          const a=area.getBoundingClientRect(),p=parent.getBoundingClientRect();
          menu.classList.remove('hidden');menu.style.left=(a.right-p.left-30)+'px';menu.style.top=((a.top+a.bottom)/2-p.top-12.5)+'px';
        }''',{'row':row,'column':column})

    async def test_compiler_contract_and_runtime_use_real_visual_evidence(self):
        from webcollect.browser import observe,prepare_action,execute
        from webcollect.task_contract import validate_m4_task
        from webcollect.html_table_strategy import production_operations
        task=await self.compiled_task();validate_m4_task(task)
        self.assertEqual(len(task['operations']),9)
        self.assertTrue(all('target_label' not in op['evidence'] for op in task['operations']))
        state=await observe(self.page,task['operations'][0]['selector'])
        self.assertEqual(state['target']['visual_target_evidence']['row'],2)
        prepare_action(state,task['operations'][0])
        await self.page.set_content(editor_html([['',''],['','']]))
        for operation in task['operations'][1:]:
            state=await observe(self.page,operation['selector'])
            args,_=prepare_action(state,operation)
            await execute(self.page,operation['action_type'],args,{'settle_ms':0})
            if operation['action_type']=='click':
                # Reproduce the saved site's known selected-cell helper only.
                await self.page.evaluate("document.querySelectorAll('.tbl__area_selected').forEach(e=>e.classList.remove('tbl__area_selected'))")
                await self.show_cell_menu(operation['evidence']['row'],operation['evidence']['column'])
        final=await self.page.evaluate(HTML_TABLE_RESULT_JS)
        self.assertTrue(verify_table_result(final['result_targets'][0]))
        from webcollect.collect import assert_state
        self.assertEqual(len(await assert_state(self.page,task['final_assertions'])),1)
        for change in ('label','uri','business','kind','row','matrix','selector','arguments'):
            altered=deepcopy(task);operation=altered['operations'][2]
            if change=='label':operation['evidence']['target_label']='第1格'
            elif change=='uri':altered['initial_url']=URI+'?bad=1'
            elif change=='business':altered['deterministic_strategy']['id']='other'
            elif change=='kind':operation['evidence']['target_visual_kind']='icon'
            elif change=='row':operation['evidence']['row']=2
            elif change=='matrix':operation['evidence']['expected_matrix'][0][1]='unexpected'
            elif change=='selector':operation['selector']=cell_selector(1,2)
            else:operation['arguments']['text']='OTHER'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_m4_task(altered)

    async def test_size_visual_adapter_rejects_border_clip_overlay_and_grid_reordering(self):
        from webcollect.browser import observe,prepare_action
        from webcollect.html_table_strategy import production_operations
        operation=production_operations()[0]
        for mutation in ["document.querySelectorAll('.tg__cell')[11].style.border='none'",
                         "document.querySelectorAll('.tg__cell')[11].style.borderColor='#f7f7f9'",
                         "document.querySelectorAll('.tg__cell')[11].style.borderColor='rgba(207,207,207,.01)'",
                         "document.querySelector('.tg__cells').style.background='#cfcfcf'",
                         "document.querySelector('.tg__cells').style.backgroundImage='linear-gradient(white,white)'",
                         "document.querySelector('.tg__cells').style.clipPath='inset(10px)'",
                         "document.querySelectorAll('.tg__cell')[11].style.transform='translateX(1px)'",
                         "document.querySelectorAll('.tg__cell')[11].setAttribute('col','3')",
                         "document.querySelector('.tg__title').style.opacity='.5'",
                         "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:99\"></div>')"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(grid_html());await self.page.evaluate(mutation)
                state=await observe(self.page,operation['selector'])
                with self.assertRaises(ValueError):prepare_action(state,operation)

    async def test_cell_visual_adapter_rejects_unknown_or_changed_menu_and_stale_matrix(self):
        from webcollect.browser import observe,prepare_action
        from webcollect.html_table_strategy import production_operations
        operation=production_operations()[2]
        mutations=[
          "document.querySelector('.cm__open-btn').style.left='10px'",
          "document.querySelector('.cm__open-btn').style.left='80px'",
          "document.querySelector('.cm__open-btn').style.width='40px'",
          "document.querySelector('.cm__open-btn').insertAdjacentHTML('afterend',document.querySelector('.cm__open-btn').outerHTML)",
          "document.body.append(document.querySelector('.cm__open-btn'))",
          "document.querySelector('.cm__open-btn').innerHTML='<span>unknown</span>'",
          "document.querySelector('.cm__open-btn polyline').setAttribute('points','1 1 5 5')",
          "document.querySelector('.cm').classList.remove('hidden')",
          "document.querySelectorAll('.tbl__area')[1].focus()",
          "document.querySelectorAll('.tbl__area')[3].textContent='unexpected'",
          "document.querySelector('.tbl__area').style.clipPath='inset(5px)'",
          "document.querySelector('.tbl__container').style.opacity='.5'",
          "document.querySelector('td').colSpan=2",
          "document.querySelector('td').style.borderColor='#f7f7f9'",
          "document.querySelector('.tbl__area').insertAdjacentHTML('beforeend','<div class=cm__open-btn style=\"position:absolute;inset:0\"></div>')"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                await self.page.set_content(editor_html([['',''],['','']]))
                await self.show_cell_menu();await self.page.evaluate(mutation)
                state=await observe(self.page,operation['selector'])
                with self.assertRaises(ValueError):prepare_action(state,operation)
        await self.page.set_content(editor_html([['',''],['','']]))
        await self.show_cell_menu();state=await observe(self.page,operation['selector'])
        self.assertEqual(state['target']['visible_label_evidence'],[])
        self.assertIsNotNone(state['target']['visual_target_evidence']['known_menu_rect'])
        prepare_action(state,operation)

    async def test_text_glyphs_and_menu_do_not_allow_hidden_existing_cell_content(self):
        from webcollect.browser import observe,prepare_action
        from webcollect.html_table_strategy import production_operations
        # Stage after first cell is filled and before the next cell is clicked.
        operation=production_operations()[3]
        for mutation in ["document.querySelector('.tbl__area').style.color='#f7f7f9'",
                         "document.querySelector('.tbl__area').style.webkitTextFillColor='rgba(0,0,0,.01)'",
                         "document.querySelector('.tbl__area').style.fontSize='1px'",
                         "document.querySelector('.tbl__area').style.textIndent='420px'",
                         "document.querySelector('.tbl__area').style.letterSpacing='420px'",
                         "document.querySelector('.tbl__area').style.opacity='.01'"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(editor_html([['项目',''],['','']]))
                await self.show_cell_menu();await self.page.evaluate(mutation)
                state=await observe(self.page,operation['selector'])
                with self.assertRaises(ValueError):prepare_action(state,operation)

    async def test_text_target_gate_still_rejects_invented_visible_label(self):
        from webcollect.browser import observe,prepare_action
        await self.page.set_content(editor_html([['',''],['','']]))
        state=await observe(self.page,cell_selector(1,1))
        with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state,{'action_type':'click','evidence':{'target_label':'虚构文字'}})

    async def test_production_terminal_oracle_rejects_substrings_extra_sections_spans_and_hidden_text(self):
        from webcollect.collect import assert_state
        from webcollect.browser import observe
        condition={'selector':TABLE_SELECTOR,'html_table_matrix':deepcopy(EXPECTED_MATRIX)}
        await self.page.set_content(editor_html());state=await observe(self.page,assertions=[condition])
        self.assertEqual((await assert_state(None,[condition],state))[0]['actual'],EXPECTED_MATRIX)
        evidence=state['assertion_targets'][0]['html_table_evidence']
        self.assertEqual(parse_table_matrix(evidence['html']),EXPECTED_MATRIX)
        for mutation in ["document.querySelectorAll('.tbl__area')[3].textContent='13'",
                         "document.querySelectorAll('.tbl__area')[2].textContent='苹果附加'",
                         "document.querySelector('table').insertAdjacentHTML('afterbegin','<thead><tr><td>额外</td><td>行</td></tr></thead>')",
                         "document.querySelector('table').insertAdjacentHTML('beforeend','<tfoot><tr><td>额外</td><td>行</td></tr></tfoot>')",
                         "document.querySelector('td').rowSpan=2",
                         "document.querySelector('td').colSpan=2",
                         "document.querySelector('col').span=2",
                         "document.querySelectorAll('.tbl__area')[3].style.color='#f7f7f9'",
                         "document.querySelectorAll('.tbl__area')[3].style.textIndent='900px'",
                         "document.querySelector('table').style.marginTop='700px'"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(editor_html());await self.page.evaluate(mutation)
                with self.assertRaises(ValueError):await assert_state(self.page,[condition])
        for change in ('geometry','html','matrix','uri'):
            forged=deepcopy(state)
            if change=='geometry':forged['assertion_targets'][0]['html_table_evidence']['geometry']=[]
            elif change=='html':forged['assertion_targets'][0]['html_table_evidence']['html']=table_html([['项目','数量'],['苹果','13']])
            elif change=='matrix':forged['assertion_targets'][0]['html_table_evidence']['matrix'][1][1]='13'
            else:forged['url']=URI+'?different=1'
            with self.assertRaises(ValueError):await assert_state(None,[condition],forged)


if __name__=='__main__':unittest.main()
