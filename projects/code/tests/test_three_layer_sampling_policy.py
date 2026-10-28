"""Three-layer sampling contracts: synthetic bytes and authored decisions only.

These are protocol fixtures, never actual AI or human inspection. Network and
model construction are blocked throughout each test.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'),
                str(REPO / 'projects/quality-inspector/tests')]
from test_s0_sampling import controlled_reviews, multi_fixture
from quality_inspector import delivery_sampling as sampling
from quality_inspector.engine import inspect


class ThreeLayerSamplingPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for target in ('urllib.request.build_opener', 'socket.create_connection',
                       'quality_inspector.ai_worker.ModelGateway'):
            blocker = patch(target, side_effect=AssertionError('Offline protocol fixture: no service'))
            blocker.start(); self.addCleanup(blocker.stop)
        self.dataset = multi_fixture(self.root / 'CONTROLLED-fixture', count=4)
        self.plan_path = self.root / 'sampling-plan.json'

    def freeze(self, ai=25, human=50):
        return sampling.freeze(self.dataset, self.plan_path, ai_percent=ai,
                               human_percent=human, seed='THREE-LAYER-CONTROLLED')

    def authored_reviews(self, name, kind, ids, statuses=None):
        """Keep only explicitly supplied fixtures; no default human approvals."""
        path = self.root / (name + '.json')
        value = controlled_reviews(self.dataset, path, statuses)
        value = deepcopy(value)
        value['records'] = [record for record in value['records'] if record['sample_id'] in ids]
        for record in value['records']:
            record['reviewer'] = {'kind': kind,
                'name': 'CONTROLLED TEST AUTHOR; NOT ACTUAL ' + kind.upper() + ' SIGN-OFF'}
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path

    def test_partial_ai_and_independent_human_selection_are_frozen_per_sample(self):
        plan = self.freeze(ai=25, human=50)
        repeated = sampling.freeze(self.dataset, self.root / 'same-seed-plan.json',
            ai_percent=25, human_percent=50, seed='THREE-LAYER-CONTROLLED')
        self.assertEqual(plan, repeated)
        self.assertEqual(plan['original_denominator'], 4)
        self.assertEqual(sum(slot['ai_selected'] for slot in plan['slots']), 1)
        self.assertEqual(sum(slot['human_selected'] for slot in plan['slots']), 2)
        selected = {slot['current']['sample_id'] for slot in plan['slots'] if slot['ai_selected']}
        ai = self.authored_reviews('partial-ai', 'ai', selected)
        result, _ = sampling.evaluate(self.plan_path, self.dataset, ai_reviews=[ai])
        self.assertEqual(result['actual_ai_reviewed'], 1)
        self.assertEqual(result['ai_pending_count'], 0)
        self.assertEqual(set(result['human_queue']),
                         {slot['current']['sample_id'] for slot in plan['slots'] if slot['human_selected']})
        self.assertEqual(result['human_pending_count'], 2)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')

    def test_independent_human_and_ai_escalation_union_has_no_duplicate_task(self):
        plan = self.freeze()
        human_selected = {slot['current']['sample_id'] for slot in plan['slots'] if slot['human_selected']}
        overlap = sorted(human_selected)[0]
        escalated = next(slot['current']['sample_id'] for slot in plan['slots'] if not slot['human_selected'])
        ai_selected = {slot['current']['sample_id'] for slot in plan['slots'] if slot['ai_selected']}
        ai = self.authored_reviews('ai-findings', 'ai', ai_selected | {overlap, escalated},
            {overlap: {'privacy': 'FAIL'}, escalated: {'terminal_semantics': 'REVIEW_REQUIRED'}})
        original = ai.read_bytes()
        pending, _ = sampling.evaluate(self.plan_path, self.dataset, ai_reviews=[ai])
        expected = human_selected | {escalated}
        self.assertEqual(set(pending['human_queue']), expected)
        self.assertEqual(len(pending['human_queue']), len(expected))
        self.assertEqual(pending['human_pending_count'], len(expected))
        human = self.authored_reviews('actual-import-protocol-fixture', 'human', expected)
        resolved, effective = sampling.evaluate(self.plan_path, self.dataset,
                                               ai_reviews=[ai], human_reviews=[human])
        self.assertEqual(resolved['status'], 'PASS')
        self.assertEqual(resolved['human_pending_count'], 0)
        self.assertEqual(effective[overlap]['reviewer']['kind'], 'human')
        self.assertEqual(effective[escalated]['reviewer']['kind'], 'human')
        self.assertEqual(ai.read_bytes(), original)
        rows = {row['sample_id']: row for row in resolved['rows']}
        self.assertEqual(rows[overlap]['ai_status'], 'FAIL')
        self.assertEqual(rows[escalated]['ai_status'], 'REVIEW_REQUIRED')
        self.assertEqual(rows[overlap]['status'], 'HUMAN_PASS')

    def test_direct_human_random_sample_does_not_claim_unselected_ai_pass(self):
        plan = self.freeze(ai=0, human=25)
        selected = {slot['current']['sample_id'] for slot in plan['slots'] if slot['human_selected']}
        self.assertEqual(len(selected), 1)
        human = self.authored_reviews('direct-human', 'human', selected)
        state, effective = sampling.evaluate(self.plan_path, self.dataset, human_reviews=[human])
        self.assertEqual(state['status'], 'PASS')
        self.assertEqual(state['actual_ai_reviewed'], 0)
        self.assertEqual(state['actual_human_reviewed'], 1)
        self.assertEqual(state['not_selected'], 3)
        self.assertEqual(set(effective), selected)
        report = inspect(None, self.dataset, inspection_stage='payload',
                         delivery_sampling_plan=self.plan_path, human_reviews=[human])
        for sample in report['samples']:
            checks = [item for item in sample['checks'] if item['rule_id'].startswith('REVIEW_')]
            if sample['sample_id'] in selected:
                self.assertEqual(len(checks), 5)
                self.assertTrue(all(item['reviewer']['kind'] == 'human' for item in checks))
            else:
                self.assertEqual(checks, [])
                row = next(item for item in state['rows'] if item['sample_id'] == sample['sample_id'])
                self.assertEqual(row['status'], 'NOT_SELECTED')
                self.assertFalse(row['semantic_review_claimed'])
        self.assertFalse(report['release_ready'])  # Independent document/distribution gates still apply.

    def test_human_rejection_of_ai_issue_needs_replacement_not_ai_second_vote(self):
        plan = self.freeze(ai=25, human=0)
        selected = {slot['current']['sample_id'] for slot in plan['slots'] if slot['ai_selected']}
        sid = next(iter(selected))
        ai = self.authored_reviews('ai-issue', 'ai', selected, {sid: {'privacy': 'FAIL'}})
        human = self.authored_reviews('human-rejection', 'human', selected,
                                      {sid: {'terminal_semantics': 'FAIL'}})
        before = {path: path.read_bytes() for path in (ai, human)}
        rejected, effective = sampling.evaluate(self.plan_path, self.dataset,
                                                ai_reviews=[ai], human_reviews=[human])
        self.assertEqual(rejected['replacement_required_count'], 1)
        self.assertEqual(rejected['status'], 'FAIL')
        self.assertNotIn(sid, effective)
        self.assertEqual(next(row['status'] for row in rejected['rows']
                              if row['sample_id'] == sid), 'REPLACE_REQUIRED')
        # Evaluation is read-only and repeatable; it cannot request another AI vote.
        self.assertEqual(sampling.evaluate(self.plan_path, self.dataset,
            ai_reviews=[ai], human_reviews=[human])[0], rejected)
        self.assertTrue(all(path.read_bytes() == original for path, original in before.items()))

    def test_unknown_request_joins_human_sample_once_and_is_never_retried_or_qualified(self):
        plan = self.freeze(ai=0, human=50)
        slot = next(row for row in plan['slots'] if row['human_selected'])
        sample = slot['current']; sid = sample['sample_id']
        ledger = self.root / 'CONTROLLED-authored-unknown.sqlite3'
        with sqlite3.connect(ledger) as con:
            con.executescript('''CREATE TABLE batch_meta(id INTEGER PRIMARY KEY,config TEXT);
                CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,state TEXT,attempts INTEGER);
                CREATE TABLE model_requests(id TEXT PRIMARY KEY,job_id TEXT,state TEXT,started REAL,
                    finished REAL,request_json TEXT,error TEXT);''')
            con.execute('INSERT INTO batch_meta VALUES(1,?)', (json.dumps({'mode': 'real', 'model': {
                'provider': 'glm', 'model': 'CONTROLLED fixture; no actual model called'}}),))
            con.execute('INSERT INTO jobs VALUES(?,?,?,?,?)', ('CONTROLLED-job', 'ai-visual', json.dumps({
                'mode': 'real', 'contract_sha256': plan['contract_sha256'], 'candidate': {
                    'annotation_sha256': sample['annotation_sha256'],
                    'evidence_sha256': sample['evidence_sha256']}}), 'review_required', 1))
            con.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?)', ('CONTROLLED-request',
                'CONTROLLED-job', 'unknown', 1, 2,
                json.dumps({'CONTROLLED': 'authored fixture, never dispatched'}), 'TimeoutError'))
        failure = self.root / 'unknown-evidence.json'
        sampling.export_failures(self.plan_path, ledger, failure)
        before = hashlib.sha256(ledger.read_bytes()).hexdigest()
        state, effective = sampling.evaluate(self.plan_path, self.dataset, ai_failures=[failure])
        repeated, _ = sampling.evaluate(self.plan_path, self.dataset, ai_failures=[failure])
        self.assertEqual(state, repeated)
        self.assertEqual(state['human_queue'].count(sid), 1)
        self.assertEqual(state['human_pending_count'], 2)
        self.assertEqual(state['status'], 'REVIEW_REQUIRED')
        self.assertEqual(state['actual_ai_reviewed'], 0)
        self.assertNotIn(sid, effective)
        self.assertFalse(next(row['semantic_review_claimed'] for row in state['rows']
                              if row['sample_id'] == sid))
        self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(), before)
        with sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True) as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests').fetchall(), [('unknown',)])
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
