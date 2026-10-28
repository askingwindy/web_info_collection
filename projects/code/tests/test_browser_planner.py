"""Observation planner targets are actual DOM nodes, not model-made selectors."""
import tempfile
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, ValidationError
from webcollect.browser import capture, prepare_action, execute, verify_execution_state
from webcollect.browser_planner import (SCHEMA, operation_from_decision, planning_prompt,
                                        save_frame, scroll_coordinates)


class PlannerTargets(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p = await async_playwright().start()
        self.browser = await self.p.chromium.launch(channel='chrome', headless=True)
        self.page = await self.browser.new_page(viewport={'width': 1280, 'height': 720})
        await self.page.set_content('<label for="a">数量</label><input id="a"><button id="submit">计算</button><button id="delete">删除</button>')

    async def asyncTearDown(self):
        await self.browser.close(); await self.p.stop()

    def decision(self, eid, action='click'):
        return {'action_type': action, 'target_element_id': eid, 'arguments': {},
                'goal': '填写必要数量', 'rationale': '任务需要数量', 'expected': '数量框获得焦点'}

    async def test_model_element_must_exist_and_selector_is_from_dom(self):
        frame = await capture(self.page)
        field = next(e for e in frame['state']['elements'] if e['text'] == '数量' and e['element_type'] == 'input')
        op = await operation_from_decision(self.page, frame['state'], self.decision(field['element_id']))
        self.assertEqual(op['selector'], '#a')
        before = await capture(self.page, op['selector'])
        args, _ = prepare_action(before['state'], op)
        await execute(self.page, 'click', args)
        self.assertTrue(await self.page.locator('#a').evaluate('(e)=>e===document.activeElement'))
        with self.assertRaisesRegex(ValueError, 'current observed'):
            await operation_from_decision(self.page, frame['state'], self.decision('invented'))

    async def test_public_side_effect_controls_are_not_explored(self):
        frame = await capture(self.page)
        target = next(e for e in frame['state']['elements'] if e['text'] == '删除')
        with self.assertRaisesRegex(ValueError, 'side-effect'):
            await operation_from_decision(self.page, frame['state'], self.decision(target['element_id']))

    async def test_observation_frames_are_original_and_immutable(self):
        frame = await capture(self.page)
        with tempfile.TemporaryDirectory() as name:
            refs = save_frame(Path(name), 1, frame)
            self.assertEqual(Path(refs['image']['path']).read_bytes(), frame['png'])
            self.assertEqual(refs['image']['sha256'], frame['capture']['screenshot_sha256'])
            with self.assertRaises(FileExistsError):
                save_frame(Path(name), 1, frame)

    async def overflow(self):
        items=''.join(f'<div style="height:32px">单位选项{i}</div>' for i in range(20))
        await self.page.set_content('<style>body{height:2200px;margin:0}#menu{position:absolute;left:24px;top:80px;width:250px;height:120px;overflow:auto}iframe{position:absolute;left:500px;top:280px;width:400px;height:180px}</style>'
                                    f'<div id="menu">{items}</div><iframe title="本地不透明区域" srcdoc="本地框架"></iframe>')
        frame=await capture(self.page)
        menu=next(e for e in frame['state']['elements'] if e.get('scrollable') is True)
        return frame,menu

    async def test_actual_container_scroll_uses_original_hit_point_and_keeps_page_stationary(self):
        frame,menu=await self.overflow()
        decision=self.decision(menu['element_id'],'scroll');decision['arguments']={'direction':'down','distance':80}
        op=await operation_from_decision(self.page,frame['state'],decision)
        self.assertEqual(op['selector'],'#menu');self.assertEqual(op['execution'],{'distance':80})
        self.assertEqual(decision['arguments']['distance'],80) # original model decision remains immutable
        self.assertNotIn('distance',op['arguments'])
        before=await capture(self.page,op['selector'])
        self.assertEqual(before['state']['target']['element_id'],menu['element_id'])
        self.assertTrue(before['state']['target']['hit_valid'])
        op['arguments'].update(scroll_coordinates(before['state'],menu['element_id']))
        args,_=prepare_action(before['state'],op)
        self.assertEqual([args['x'],args['y']],before['state']['target']['coordinate'])
        await verify_execution_state(self.page,before['state'],op['selector'])
        await execute(self.page,'scroll',args,op['execution'])
        await self.page.wait_for_function('document.querySelector("#menu").scrollTop>0')
        after=await capture(self.page)
        self.assertGreater(await self.page.locator('#menu').evaluate('(e)=>e.scrollTop'),0)
        self.assertEqual(await self.page.evaluate('scrollY'),0)
        self.assertNotEqual(before['state']['visible_text'],after['state']['visible_text'])

    async def test_page_scroll_remains_unbound_and_embedded_frame_guard_is_preserved(self):
        frame,_=await self.overflow()
        decision=self.decision(None,'scroll');decision['arguments']={'direction':'down'}
        op=await operation_from_decision(self.page,frame['state'],decision)
        self.assertNotIn('selector',op);self.assertEqual(op['arguments'],{'direction':'down'})
        self.assertEqual(op['execution'],{'distance':360})
        before=await capture(self.page)
        self.assertIsNone(before['state']['target'])
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_FRAME'):prepare_action(before['state'],op)

    async def test_scroll_cannot_use_non_scrollable_or_invented_container(self):
        frame=await capture(self.page)
        field=next(e for e in frame['state']['elements'] if e['element_type']=='input')
        for eid in (field['element_id'],'invented',''):
            decision=self.decision(eid,'scroll');decision['arguments']={'direction':'down','distance':80}
            with self.subTest(eid=eid),self.assertRaisesRegex(ValueError,'current observed scrollable'):
                await operation_from_decision(self.page,frame['state'],decision)

    async def test_scroll_rechecks_live_scrollability_and_does_not_trust_stale_tree(self):
        frame,menu=await self.overflow()
        await self.page.locator('#menu').evaluate('(e)=>e.style.overflow="hidden"')
        decision=self.decision(menu['element_id'],'scroll');decision['arguments']={'direction':'down'}
        with self.assertRaisesRegex(ValueError,'current visible scrollable'):
            await operation_from_decision(self.page,frame['state'],decision)

    async def test_scroll_rebinds_coordinates_to_target_in_actual_before_capture(self):
        frame,menu=await self.overflow()
        decision=self.decision(menu['element_id'],'scroll');decision['arguments']={'direction':'down','distance':40}
        op=await operation_from_decision(self.page,frame['state'],decision)
        original=(op['arguments']['x'],op['arguments']['y'])
        await self.page.locator('#menu').evaluate('(e)=>e.style.left="150px"')
        before=await capture(self.page,op['selector'])
        op['arguments'].update(scroll_coordinates(before['state'],menu['element_id']))
        args,_=prepare_action(before['state'],op)
        self.assertNotEqual(original,(args['x'],args['y']))
        self.assertEqual([args['x'],args['y']],before['state']['target']['coordinate'])
        await verify_execution_state(self.page,before['state'],op['selector'])
        await execute(self.page,'scroll',args,op['execution'])
        await self.page.wait_for_function('document.querySelector("#menu").scrollTop>0')
        self.assertEqual(await self.page.evaluate('scrollY'),0)

    async def test_scroll_distance_schema_runtime_boundaries_and_no_other_action_option(self):
        frame=await capture(self.page)
        for distance in (40,480):
            decision=self.decision(None,'scroll');decision['arguments']={'direction':'down','distance':distance}
            full={**decision,'status':'act','reason':'必要滚动','final_assertions':[]}
            Draft202012Validator(SCHEMA).validate(full)
            op=await operation_from_decision(self.page,frame['state'],decision)
            self.assertEqual(op['execution']['distance'],distance)
            self.assertNotIn('distance',op['arguments'])
        for distance in (39,481,0,-1,True,480.0,'80',None):
            decision=self.decision(None,'scroll');decision['arguments']={'direction':'down','distance':distance}
            with self.subTest(distance=distance),self.assertRaisesRegex(ValueError,'40 to 480'):
                await operation_from_decision(self.page,frame['state'],decision)
        bad={**self.decision(None,'scroll'),'status':'act','reason':'测试','final_assertions':[],
             'arguments':{'direction':'down','distance':481}}
        with self.assertRaises(ValidationError):Draft202012Validator(SCHEMA).validate(bad)
        decision=self.decision(None,'hotkey');decision['arguments']={'keys':['enter'],'distance':80}
        with self.assertRaisesRegex(ValueError,'scroll only'):
            await operation_from_decision(self.page,frame['state'],decision)

    async def test_autofocused_empty_input_prompt_and_execution_need_no_click_or_select_all(self):
        await self.page.set_content('<label for="a">数量</label><input id="a" autofocus><button id="done">计算</button>')
        await self.page.wait_for_function('document.activeElement===document.querySelector("#a")')
        frame=await capture(self.page)
        field=next(e for e in frame['state']['elements'] if e['element_type']=='input')
        prompt=planning_prompt({'instruction':'填写数量'},[],frame['state'],[],0)
        hint=next(row for row in prompt['input_preparation'] if row['element_id']==field['element_id'])
        self.assertTrue(hint['focused']);self.assertFalse(hint['focus_click_needed'])
        self.assertFalse(hint['select_all_before_replacing'])
        self.assertIn('已聚焦就直接输入',prompt['instruction']);self.assertIn('空输入框直接输入，不做全选',prompt['instruction'])
        decision=self.decision(field['element_id'],'type');decision['arguments']={'text':'7'}
        op=await operation_from_decision(self.page,frame['state'],decision)
        before=await capture(self.page,op['selector']);args,_=prepare_action(before['state'],op)
        await execute(self.page,'type',args)
        self.assertEqual(await self.page.locator('#a').input_value(),'7')
        filled=await capture(self.page)
        filled_prompt=planning_prompt({},[],filled['state'],[],1)
        self.assertFalse(filled_prompt['input_preparation'][0]['focus_click_needed'])
        self.assertTrue(filled_prompt['input_preparation'][0]['select_all_before_replacing'])
        await self.page.locator('#done').click()
        blurred=await capture(self.page)
        self.assertTrue(planning_prompt({},[],blurred['state'],[],1)['input_preparation'][0]['focus_click_needed'])

    async def test_visible_label_guard_is_not_relaxed_by_new_focus_guidance(self):
        await self.page.set_content('<input id="a" aria-label="隐藏名称"><button>计算</button>')
        frame=await capture(self.page)
        field=next(e for e in frame['state']['elements'] if e['element_type']=='input')
        op=await operation_from_decision(self.page,frame['state'],self.decision(field['element_id']))
        before=await capture(self.page,op['selector'])
        with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):prepare_action(before['state'],op)
