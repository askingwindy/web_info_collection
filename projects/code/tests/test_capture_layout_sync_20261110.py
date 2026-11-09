"""Read-only capture regression: layout drift and long offscreen article work."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

from test_dynamic_regions import state, png
from webcollect.action_stability import ACTION_SCOPED_V3, post_action_document_scope
from webcollect.browser import capture, stability_pair, validate_capture_receipt


class CaptureLayoutSyncTests(unittest.IsolatedAsyncioTestCase):
    def test_post_observation_rejects_layout_drift_with_identical_pixels(self):
        before = state()
        after = deepcopy(before)
        after['elements'][2]['bbox'] = [0, 36, 30, 56]
        proof = stability_pair(before, after, png(), png(),
                               action_scope=post_action_document_scope(before))
        self.assertFalse(proof['accepted'])
        self.assertFalse(proof['related_dom_stable'])
        self.assertFalse(proof['dispatch_permission'])

    def test_frozen_v3_still_replays_its_original_identity_only_proof(self):
        before = state()
        after = deepcopy(before)
        after['elements'][2]['bbox'] = [0, 36, 30, 56]
        proof = stability_pair(before, after, png(), png(), action_scope=
                               post_action_document_scope(before, version=ACTION_SCOPED_V3))
        self.assertTrue(proof['accepted'])

    def test_classified_announcement_changes_do_not_block_observation(self):
        before = state()
        after = deepcopy(before)
        after['elements'][1]['text'] = 'Announcement two'
        after['visible_text'] = 'Operate\nAnnouncement two'
        proof = stability_pair(before, after, png('red'), png('blue'),
                               action_scope=post_action_document_scope(before))
        self.assertTrue(proof['accepted'])
        self.assertFalse(proof['full_dom_stable'])

    def test_empty_decoration_and_incidental_hits_do_not_block_observation(self):
        before = state()
        after = deepcopy(before)
        # A content container resizes around an announcement; business text and
        # control positions remain fixed. A transparent painted ancestor also
        # changes incidental hit inventory, without moving the actual control.
        after['elements'][0]['bbox'] = [0, 0, 80, 58]
        after['elements'].append({'element_id': 'ornament', 'element_type': 'image',
                                  'text': '', 'bbox': [70, 50, 80, 60], 'visible': True})
        after['geometry_witnesses'][0]['samples'] = [{'ancestor': True, 'hit_tag': 'span'}] * 9
        proof = stability_pair(before, after, png(), png(),
                               action_scope=post_action_document_scope(before))
        self.assertTrue(proof['accepted'])

    def test_announcement_reflow_that_moves_business_target_still_rejects(self):
        before = state()
        after = deepcopy(before)
        after['elements'][1]['text'] = 'Announcement two'
        after['visible_text'] = 'Operate\nAnnouncement two'
        after['elements'][2]['bbox'] = [0, 36, 30, 56]
        proof = stability_pair(before, after, png(), png(),
                               action_scope=post_action_document_scope(before))
        self.assertFalse(proof['accepted'])

    async def test_capture_retries_layout_shift_before_retaining_first_tree(self):
        before = state()
        settled = deepcopy(before)
        settled['elements'][2]['bbox'] = [0, 36, 30, 56]
        image = png()
        # First PNG has the settled layout while the initial DOM is still old.
        # Identity-only proofs used to accept this first mismatched bracket.
        with patch('webcollect.browser.observe', AsyncMock(side_effect=[
                before, settled, settled, settled, settled, settled])), \
             patch('webcollect.browser.viewport_png', AsyncMock(return_value=(image, {}))), \
             patch('webcollect.browser.asyncio.sleep', AsyncMock()):
            class Page:
                pass
            page = Page()
            result = await capture(page, retries=2,
                                   action_scope=post_action_document_scope(before))
        self.assertEqual(result['state'], settled)
        self.assertEqual(len(result['capture']['attempts']), 2)
        self.assertFalse(result['capture']['attempts'][0]['stability']['accepted'])
        self.assertTrue(validate_capture_receipt(result['state'], result['capture'], image))


class SnapshotOffscreenWorkTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for isolated observer helper test')
    def test_offscreen_text_skips_ancestor_work_and_reuses_empty_result(self):
        # Execute the actual synchronous helper with DOM read counters. This
        # needs no browser and catches repeated whole-article offscreen work.
        source = (Path(__file__).parents[1] / 'webcollect/snapshot.js').read_text()
        helper = source[source.index('  const visibleText = node => {'):
                        source.index('  const frameworkColorCache=')]
        program = """
const Node={COMMENT_NODE:8,ELEMENT_NODE:1,TEXT_NODE:3};
const textCache=new WeakMap(),textEdges=new WeakMap();
const width=1280,height=720;
let rangeReads=0,clipReads=0;
const owner={checkVisibility:()=>true};
const node={nodeType:3,parentElement:owner,textContent:'离屏正文'};
const document={createRange:()=>({selectNodeContents(){},getClientRects(){
  rangeReads++;return [{left:0,right:100,top:1500,bottom:1520}];}})};
const clipFor=()=>{clipReads++;throw Error('Offscreen clip walk');};
""" + helper + """
for(let i=0;i<5;i++)if(visibleText(node)!=='')throw Error('Offscreen text leaked');
process.stdout.write(JSON.stringify({rangeReads,clipReads}));
"""
        completed = subprocess.run(['node', '-e', program], capture_output=True,
                                   text=True, check=True)
        self.assertEqual(json.loads(completed.stdout), {'rangeReads': 1, 'clipReads': 0})
