"""Controlled historical-source regressions; no model/browser/production writes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_task_admission as fixtures
from webcollect.batch_core import load_json, save_json
from webcollect.planning import object_sha256
from webcollect.task_admission import attach, reference, static_identity, verify_live
from webcollect.task_generation import compile_form, generation_source_identity, semantic_signature


class HistoricalObserverTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompletionViewTests('test_only_proven_necessary_scroll_is_appended_and_owns_full_terminal_evidence')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.h = self.fixture.helper; self.root = self.h.root
        self.cap, self.spec, self.flow_frames = self.fixture.flow('historical-flow')
        self.base = compile_form(self.cap, self.spec)
        self.packet, self.review = self.h.prepare('historical-approved', self.cap, self.spec, self.base, self.h.frames)
        self.admitted = attach(self.base, self.packet, self.review, self.h.ctx, mode='synthetic')

    def future_sources(self):
        value = generation_source_identity(); value['snapshot.js'] = '0' * 64
        return value

    def fork(self, mutate):
        packet = load_json(self.packet['path']); mutate(packet)
        path = self.root / ('packet-' + object_sha256(packet)[:20] + '.json'); save_json(path, packet)
        pref = reference(path); review = load_json(self.review['path']); review['packet_sha256'] = pref['sha256']
        rref = self.h.write_review(self.root / ('review-' + pref['sha256'][:20] + '.json'), review, pref)
        task = deepcopy(packet['task']); task['task_admission'] = deepcopy(self.admitted['task_admission'])
        task['task_admission'].update(packet=pref, review=rref)
        return task

    def fork_flow(self, mutate):
        def change(packet):
            flow = load_json(packet['spec']['completion_view']['record']['path']); mutate(flow)
            path = self.root / ('flow-' + object_sha256(flow)[:20] + '.json'); save_json(path, flow)
            view = {'schema_version': 'webcollect-bound-completion-view-1', 'record': reference(path)}
            packet['spec']['completion_view'] = view
            packet['task']['operations'][-1]['completion_view'] = deepcopy(view)
        return self.fork(change)

    def test_static_signature_survives_snapshot_upgrade_but_live_compile_and_attach_reject(self):
        expected = self.admitted['task_admission']['semantic_signature']
        with patch('webcollect.task_generation.generation_source_identity', return_value=self.future_sources()):
            self.assertEqual(static_identity(self.admitted), expected)
            self.assertEqual(semantic_signature(self.admitted), expected)
            with self.assertRaisesRegex(ValueError, 'observer/source drift'):
                compile_form(self.cap, self.spec)
            with self.assertRaisesRegex(ValueError, 'observer/source drift|source version changed'):
                verify_live(self.admitted, self.h.ctx, mode='synthetic')

    def test_unchanged_current_live_path_still_validates(self):
        self.assertEqual(verify_live(self.admitted, self.h.ctx, mode='synthetic'), static_identity(self.admitted))
        self.assertEqual(compile_form(self.cap, self.spec), self.base)

    def test_other_source_change_cannot_grant_new_dispatch(self):
        changed = generation_source_identity(); changed['task_admission.py'] = '1' * 64
        with patch('webcollect.task_generation.generation_source_identity', return_value=changed):
            self.assertEqual(static_identity(self.admitted), self.admitted['task_admission']['semantic_signature'])
            with self.assertRaisesRegex(ValueError, 'source version changed'):
                verify_live(self.admitted, self.h.ctx, mode='synthetic')

    def test_missing_malformed_or_different_packet_observer_rejects(self):
        for source in (None, {}, {'snapshot.js': 'not-a-sha'}, {'snapshot.js': '0' * 64}):
            with self.subTest(source=source):
                task = self.fork(lambda packet, value=source: packet.__setitem__('source_identity', value))
                with self.assertRaisesRegex(ValueError, 'observer'):
                    static_identity(task)

    def test_rehashed_functional_capture_observer_mismatch_still_rejects(self):
        def mutate(flow):
            frame = flow['frames'][0]; capture = load_json(frame['capture']['path'])
            capture['observer_sha256'] = '0' * 64
            path = self.root / 'changed-functional-capture.json'; save_json(path, capture)
            frame['capture'] = reference(path)
        task = self.fork_flow(mutate)
        with self.assertRaisesRegex(ValueError, 'observer/source drift'):
            static_identity(task)

    def test_rehashed_packet_frame_mismatch_rejects_even_without_completion_view(self):
        # This makes the frame internally hash-consistent, but its observer is
        # different from the packet source. Historical mode is not an exemption.
        task = self.h.admitted(); packet = load_json(self.h.packet['path'])
        capture = load_json(packet['frames'][0]['capture']['path']); capture['observer_sha256'] = '0' * 64
        path = self.root / 'changed-packet-frame-capture.json'; save_json(path, capture)
        packet['frames'][0]['capture'] = reference(path)
        ppath = self.root / 'plain-rehashed-packet.json'; save_json(ppath, packet); pref = reference(ppath)
        review = load_json(self.h.review['path']); review['packet_sha256'] = pref['sha256']
        rref = self.h.write_review(self.root / 'plain-rehashed-review.json', review, pref)
        task['task_admission'].update(packet=pref, review=rref)
        with self.assertRaisesRegex(ValueError, 'different frozen observer'):
            static_identity(task)

    def test_rehashed_action_parameters_and_order_are_not_waived(self):
        def mutate(flow):
            action = load_json(flow['action_refs'][1]['path'])
            action['operation']['arguments']['text'] = '999'
            path = self.root / 'changed-action.json'; save_json(path, action)
            flow['action_refs'][1] = reference(path)
        task = self.fork_flow(mutate)
        with self.assertRaisesRegex(ValueError, 'functional action/parameters/frame order mismatch'):
            static_identity(task)

    def test_raw_frame_tamper_and_unbound_semantic_value_reject(self):
        bad = deepcopy(self.admitted); bad['task_admission']['semantic_signature'] = '2' * 64
        with self.assertRaisesRegex(ValueError, 'semantic signature changed'):
            static_identity(bad)
        image = Path(self.flow_frames[-1]['image']['path']); image.write_bytes(image.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
            static_identity(self.admitted)

    def test_proposal_meaning_and_complete_history_coverage_still_required(self):
        changed = deepcopy(self.admitted); changed['instruction'] += '改变目标。'
        with self.assertRaisesRegex(ValueError, 'compiled proposal/roles/meaning changed'):
            static_identity(changed)
        review = load_json(self.review['path']); review['history_comparisons'] = []
        rref = self.h.write_review(self.root / 'missing-history-review.json', review, self.packet)
        changed = deepcopy(self.admitted); changed['task_admission']['review'] = rref
        with self.assertRaisesRegex(ValueError, 'whole frozen history comparison coverage missing'):
            static_identity(changed)


if __name__ == '__main__':
    unittest.main()
