"""Independent paint-level negatives for the bounded blank grid/cell adapter.

All requests are fulfilled locally or aborted. Optional evidence is written to a
new directory only; production candidates and identifiers are never touched.
"""
import json
import os
from pathlib import Path
import unittest

from test_html_table_strategy import grid_html, editor_html
from webcollect.browser import observe, prepare_action
from webcollect.collect import assert_state
from webcollect.html_table_strategy import URI, TABLE_SELECTOR, EXPECTED_MATRIX, production_operations


class IndependentTablePaintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 720}, service_workers='block')
        self.requests = []
        async def local_only(route):
            self.requests.append(route.request.url)
            if route.request.is_navigation_request() and route.request.url == URI:
                await route.fulfill(status=200, content_type='text/html; charset=utf-8', body=grid_html())
            else:
                await route.abort()
        await self.context.route('**/*', local_only)
        self.page = await self.context.new_page()
        await self.page.goto(URI)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def record(self, name, state):
        root = os.environ.get('WEBCOLLECT_TABLE_INDEPENDENT_EVIDENCE')
        if not root:
            return
        directory = Path(root)
        directory.mkdir(parents=True, exist_ok=True)
        image = directory / (name + '.png')
        if image.exists():
            raise FileExistsError(image)
        await self.page.screenshot(path=str(image))
        with (directory / (name + '.json')).open('x') as stream:
            json.dump({'state': state, 'requests': self.requests, 'html': await self.page.content()}, stream,
                      ensure_ascii=False, indent=2)

    async def test_grid_positive_and_css_border_image_negative(self):
        operation = production_operations()[0]
        state = await observe(self.page, operation['selector'])
        prepare_action(state, operation)
        await self.record('grid-baseline', state)
        # border-image paints instead of border-color without changing its
        # computed palette, width or style. All tile edges disappear in pixels.
        await self.page.add_style_tag(content='.tg__cell{border-image:linear-gradient(#f7f7f9,#f7f7f9) 1 !important}')
        state = await observe(self.page, operation['selector'])
        await self.record('grid-border-image', state)
        with self.assertRaises(ValueError):
            prepare_action(state, operation)

    async def test_grid_mask_negative(self):
        operation = production_operations()[0]
        await self.page.add_style_tag(content='.tg__cells{mask-image:linear-gradient(transparent,transparent)}')
        state = await observe(self.page, operation['selector'])
        await self.record('grid-mask', state)
        with self.assertRaises(ValueError):
            prepare_action(state, operation)

    async def test_grid_pseudo_cover_negative(self):
        operation = production_operations()[0]
        await self.page.add_style_tag(content='.tg__cell{position:relative}.tg__cell::after{content:"";position:absolute;inset:-1px;background:#f7f7f9}')
        state = await observe(self.page, operation['selector'])
        await self.record('grid-pseudo-cover', state)
        with self.assertRaises(ValueError):
            prepare_action(state, operation)

    async def test_terminal_mask_negative(self):
        await self.page.set_content(editor_html())
        condition = {'selector': TABLE_SELECTOR, 'html_table_matrix': EXPECTED_MATRIX}
        state = await observe(self.page, assertions=[condition])
        await assert_state(None, [condition], state)
        await self.record('terminal-baseline', state)
        await self.page.add_style_tag(content='.tbl__area{mask-image:linear-gradient(transparent,transparent)}')
        state = await observe(self.page, assertions=[condition])
        await self.record('terminal-mask', state)
        with self.assertRaises(ValueError):
            await assert_state(None, [condition], state)

    async def test_terminal_pseudo_cover_negative(self):
        await self.page.set_content(editor_html())
        condition = {'selector': TABLE_SELECTOR, 'html_table_matrix': EXPECTED_MATRIX}
        await self.page.add_style_tag(content='.tbl__area{position:relative}.tbl__area::after{content:"";position:absolute;inset:0;background:#f7f7f9}')
        state = await observe(self.page, assertions=[condition])
        await self.record('terminal-pseudo-cover', state)
        with self.assertRaises(ValueError):
            await assert_state(None, [condition], state)


if __name__ == '__main__':
    unittest.main()
