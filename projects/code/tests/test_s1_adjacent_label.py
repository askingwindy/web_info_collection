"""Local Chrome checks for narrowly scoped, actually visible input-group labels.

Set WEBCOLLECT_ADJACENT_LABEL_ARTIFACTS to preserve every HTML/state/PNG,
including failed assertions. No fixture loads a remote resource.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

from playwright.async_api import async_playwright
from webcollect.browser import prepare_action


SNAPSHOT_PATH = Path(os.environ.get(
    "WEBCOLLECT_SNAPSHOT_UNDER_TEST",
    str(Path(__file__).resolve().parents[1] / "webcollect/snapshot.js"),
))
SNAPSHOT = SNAPSHOT_PATH.read_text()
KIND = "rendered_adjacent_input_group_label"
CSS = """
body { margin: 24px; font: 16px/24px Arial, sans-serif; color: #333; }
.input-group { display: flex; position: relative; width: 440px; margin-bottom: 20px; }
.input-group-prepend, .input-group-append { display: flex; }
.input-group-text { display: flex; align-items: center; padding: 6px 12px;
  border: 1px solid #aaa; white-space: nowrap; background: #eee; }
input { width: 240px; min-width: 0; padding: 6px 12px; border: 1px solid #aaa;
  font: inherit; background: white; }
"""
LABEL = '<span class="input-group-text" id="addon">身高 (cm)</span>'
INPUT = '<input type="number" id="target" value="170" placeholder="填写数值">'


def group(label=LABEL, control=INPUT, before="", after="", attrs=""):
    return (f'<div class="input-group" {attrs}>{before}'
            f'<div class="input-group-prepend">{label}</div>{control}{after}</div>')


class AdjacentLabelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(channel="chrome", headless=True)
        self.page = await self.browser.new_page(viewport={"width": 800, "height": 600})
        self.requests = []

        async def deny_network(route):
            self.requests.append(route.request.url)
            await route.abort()

        await self.page.route("**/*", deny_network)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def observe(self, html, case="case", extra_css=""):
        await self.page.set_content(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            f'<style>{CSS}{extra_css}</style><body>{html}</body></html>'
        )
        before = await self.page.content()
        result = await self.page.evaluate(SNAPSHOT, {"selector": "#target"})
        after = await self.page.content()
        evidence_dir = os.environ.get("WEBCOLLECT_ADJACENT_LABEL_ARTIFACTS")
        if evidence_dir:
            folder = Path(evidence_dir) / self._testMethodName / case
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "fixture.html").write_text(before)
            (folder / "state.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            (folder / "observation.json").write_text(json.dumps({
                "observer_sha256": hashlib.sha256(SNAPSHOT.encode()).hexdigest(),
                "chrome_version": self.browser.version,
                "dom_unchanged": before == after,
                "network_requests": self.requests,
                "fixture_kind": "controlled_local_html",
            }, ensure_ascii=False, indent=2))
            await self.page.screenshot(path=str(folder / "frame.png"))
        self.assertEqual(after, before, "Observer must not mutate DOM, attributes or styles")
        self.assertEqual(self.requests, [], "Controlled fixtures must never request remote resources")
        return result

    def assert_label(self, state, expected):
        target = state["target"]
        self.assertIsNotNone(target)
        self.assertEqual([row for row in target["visible_label_evidence"] if row["kind"] == KIND],
                         [{"kind": KIND, "text": expected}])
        prepare_action(state, {"action_type": "click", "evidence": {"target_label": expected}})

    def assert_rejected(self, state, expected="身高 (cm)"):
        self.assertFalse(any(row["kind"] == KIND for row in
                            (state["target"] or {}).get("visible_label_evidence", [])))
        with self.assertRaises(ValueError):
            prepare_action(state, {"action_type": "click", "evidence": {"target_label": expected}})

    async def test_real_shape_prepend_label_supports_runtime_click(self):
        self.assert_label(await self.observe(group()), "身高 (cm)")

    async def test_bootstrap_shared_border_keeps_label_but_not_wider_overlap(self):
        with self.subTest(case="prepend_shared_border"):
            self.assert_label(await self.observe(group(), "prepend_shared_border",
                              '.input-group-prepend { margin-right: -1px; }'), "身高 (cm)")
        appended = f'<div class="input-group">{INPUT}<div class="input-group-append">{LABEL}</div></div>'
        with self.subTest(case="append_shared_border"):
            self.assert_label(await self.observe(appended, "append_shared_border",
                              '.input-group-append { margin-left: -1px; }'), "身高 (cm)")
        self.assert_rejected(await self.observe(group(), "overlap_beyond_border",
                             '.input-group-prepend { margin-right: -2px; }'))
        overlay = '<div style="position:absolute;left:40px;top:24px;width:30px;height:38px;background:white;z-index:9">挡</div>'
        self.assert_rejected(await self.observe(group() + overlay, "shared_border_label_text_covered",
                             '.input-group-prepend { margin-right: -1px; }'))

    async def test_append_and_direct_leaf_labels(self):
        label = LABEL.replace("身高 (cm)", "体重 (kg)")
        control = INPUT.replace('value="170"', 'value="70"')
        for case, html in {
            "append": f'<div class="input-group">{control}<div class="input-group-append">{label}</div></div>',
            "direct": f'<div class="input-group">{label}{control}</div>',
        }.items():
            with self.subTest(case=case):
                self.assert_label(await self.observe(html, case), "体重 (kg)")

    async def test_multiple_controls_or_ambiguous_label_structures_reject(self):
        cases = {
            "two_inputs": group(control=INPUT + '<input value="70">'),
            "hidden_second_input": group(control=INPUT + '<input type="hidden">'),
            "readonly_second_input": group(control=INPUT + '<input readonly value="70">'),
            "nested_editable": group(label=LABEL.replace('</span>', '<b contenteditable="true">其他</b></span>')),
            "two_labels": group(label=LABEL + '<span class="input-group-text">体重 (kg)</span>'),
            "hidden_second_label": group(label=LABEL + '<span class="input-group-text" hidden>体重 (kg)</span>'),
            "unmarked_ambiguous_span": group(label=LABEL + '<span>体重 (kg)</span>'),
            "wrapper_own_text": group(label='体重 (kg)' + LABEL),
            "group_own_text": group(before='体重 (kg)'),
            "nested_group": group(label=f'<div class="input-group">{LABEL}</div>'),
            "nested_label_text": group(label=LABEL.replace('身高 (cm)', '身高 <span>(cm)</span>')),
            "unrelated_group_class": group().replace('class="input-group"', 'class="form-group"'),
            "unrelated_wrapper_class": group().replace('class="input-group-prepend"', 'class="description"'),
            "outside_group": LABEL + '<div class="input-group">' + INPUT + '</div>',
        }
        for case, html in cases.items():
            with self.subTest(case=case):
                self.assert_rejected(await self.observe(html, case))

    async def test_hidden_clipped_occluded_or_distant_labels_reject(self):
        cases = {
            "display_none": '#addon { display: none; }',
            "visibility_hidden": '#addon { visibility: hidden; }',
            "opacity_zero": '#addon { opacity: 0; }',
            "opacity_faint": '#addon { opacity: 0.1; }',
            "transparent_text": '#addon { color: transparent; }',
            "transparent_fill": '#addon { -webkit-text-fill-color: transparent; }',
            "tiny_text": '#addon { font-size: 1px; }',
            "partial_ancestor_clip": '.input-group-prepend { width: 36px; overflow: hidden; } #addon { flex-shrink: 0; }',
            "partial_self_clip": '#addon { width: 24px; overflow: hidden; }',
            "partial_viewport_clip": '.input-group { margin-left: -45px; }',
            "above_viewport": '#addon { position: relative; top: -60px; }',
            "distant_horizontal": '.input-group { gap: 48px; width: 600px; }',
            "distant_vertical": '#addon { position: relative; top: 80px; }',
            "stacked": '.input-group { flex-direction: column; }',
            "pseudo_extra_text": '#addon::after { content: "体重"; }',
            "filtered_label": '#addon { filter: blur(4px); }',
        }
        for case, css in cases.items():
            with self.subTest(case=case):
                self.assert_rejected(await self.observe(group(), case, css))
        overlay = '<div style="position:absolute;left:24px;top:24px;width:42px;height:40px;background:white;z-index:9">挡</div>'
        self.assert_rejected(await self.observe(group() + overlay, "covered_label"))

    async def test_partly_clipped_or_occluded_target_rejects_adjacent_evidence(self):
        self.assert_rejected(await self.observe(group(), "target_clipped", '.input-group { width: 170px; overflow: hidden; } input { flex-shrink: 0; }'))
        overlay = '<div style="position:absolute;left:330px;top:24px;width:40px;height:40px;background:white;z-index:9">挡</div>'
        self.assert_rejected(await self.observe(group() + overlay, "target_covered"))

    async def test_noneditable_controls_never_gain_adjacent_label(self):
        for case, control in {
            "readonly": INPUT.replace('id="target"', 'id="target" readonly'),
            "disabled": INPUT.replace('id="target"', 'id="target" disabled'),
            "range": INPUT.replace('type="number"', 'type="range"'),
            "checkbox": INPUT.replace('type="number"', 'type="checkbox"'),
        }.items():
            with self.subTest(case=case):
                self.assert_rejected(await self.observe(group(control=control), case))

    async def test_aria_placeholder_and_existing_association_keep_distinct_provenance(self):
        state = await self.observe(INPUT.replace('id="target"', 'id="target" aria-label="身高 (cm)"'), "aria_only")
        self.assert_rejected(state)
        state = await self.observe(INPUT.replace('value="170"', 'value=""').replace('填写数值', '身高 (cm)'), "placeholder")
        evidence = state['target']['visible_label_evidence']
        self.assertIn({'kind': 'visible_placeholder', 'text': '身高 (cm)'}, evidence)
        self.assertFalse(any(row['kind'] == KIND for row in evidence))
        state = await self.observe('<label for="target">身高 (cm)</label>' + INPUT, "associated")
        self.assertIn({'kind': 'rendered_associated_label', 'text': '身高 (cm)'}, state['target']['visible_label_evidence'])
        self.assertFalse(any(row['kind'] == KIND for row in state['target']['visible_label_evidence']))
        prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': '身高 (cm)'}})


if __name__ == "__main__":
    unittest.main()
