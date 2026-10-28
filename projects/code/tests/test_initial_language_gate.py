import unittest
from site_planner.pipeline import inventory_language_ratio

class InitialLanguageGateTests(unittest.TestCase):
    def test_prepared_chinese_view_does_not_hide_failing_initial_view(self):
        self.assertLess(inventory_language_ratio({'visible_text':'中文界面正文','initial_visible_text':'English initial screen 中文'}),0.7)
    def test_current_view_still_must_pass(self):
        self.assertLess(inventory_language_ratio({'initial_visible_text':'中文界面正文','visible_text':'English current screen 中文'}),0.7)
    def test_ordinary_inventory_and_two_passing_views(self):
        self.assertEqual(inventory_language_ratio({'visible_text':'中文界面正文'}),1.0)
        self.assertEqual(inventory_language_ratio({'initial_visible_text':'中文界面','visible_text':'中文正文'}),1.0)
