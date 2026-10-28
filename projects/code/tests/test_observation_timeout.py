import asyncio
import unittest
from unittest.mock import AsyncMock
from webcollect.browser import observe


class ObservationDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresponsive_page_has_a_bounded_observation(self):
        async def stalled(*args):await asyncio.Future()
        page=AsyncMock();page.evaluate.side_effect=stalled
        with self.assertRaisesRegex(TimeoutError,'页面同步观察超过'):
            await observe(page,timeout=0.01)

    async def test_successful_state_and_target_are_not_changed(self):
        page=AsyncMock();page.evaluate.return_value={'elements':[],'target':None}
        self.assertEqual(await observe(page,'#actual',2,timeout=0.1),{'elements':[],'target':None})
        self.assertEqual(page.evaluate.call_args.args[1],{'selector':'#actual','index':2})
