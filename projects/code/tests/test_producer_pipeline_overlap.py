"""producer_pipeline=overlap-1 scheduling: preflight headroom + one-batch screen lookahead.

Focused tests for the 2026-11-09 producer throughput round. Serial keeps the
original observe->judge->publish behavior byte-for-byte; overlap-1 only moves
scheduling. No real provider or browser is launched here.
"""
from collections import Counter
import json
import re
import threading
import time
import unittest
from unittest.mock import patch

import test_producer_business_value as fixtures
import test_producer_task_value as task_fixtures
from site_planner import page_consumption as images, producer_observation as observed
from site_planner.candidate_pool import VERSION2, entry_identity
from webcollect.batch_core import BatchLedger, load_json
from webcollect.planning import canonical, object_sha256

FOUR_LINKS = ('<main><h1>本站中文栏目</h1><a href="/c1">栏目一</a><a href="/c2">栏目二</a>'
              '<a href="/c3">栏目三</a><a href="/c4">栏目四</a></main>')


class PipelineOverlap(unittest.TestCase):
    setUp = fixtures.BusinessValue.setUp
    original = task_fixtures.TaskValue.original
    provider = fixtures.BusinessValue.provider
    decision = fixtures.BusinessValue.decision

    def home(self, html=FOUR_LINKS):
        return self.f.f.f.site('https://pipeline.example.org/',html=html)[1]

    def settle_screen(self, pool, ledger, links, root, skip=()):
        """BusinessContent-style screen: settle original shared observations, then
        the real consumption screen reuses them without any browser."""
        for link in links:
            if link['uri'] not in skip:
                self.original(link['uri'])
        return images.screen(pool, ledger, links, root)

    def run_overlap(self, home, key='ov', **kwargs):
        args = dict(key=key, target=4, batch_size=2, max_batches=2, producer_pipeline='overlap-1',
                    sources=[{**home, 'context_only': True}], model_protocol='entry-tools-13')
        args.update(kwargs)
        return self.f.f.f.run_new(home, **args)

    def run_id(self, key):
        return self.f.f.f.f.cfg['run_id'] + '/entry-batch/' + key

    def frozen_config(self, run_id):
        with self.pool.pool.connect() as con:
            return json.loads(con.execute('SELECT config FROM runs WHERE id=?', (run_id,)).fetchone()[0])

    def rows(self, run_id):
        with self.pool.pool.connect() as con:
            out = []
            for r in con.execute('SELECT b.batch,b.raw_index,b.result,b.record,c.body FROM candidate_batch_rows b '
                                 'LEFT JOIN data_candidates c USING(candidate_id) WHERE b.run_id=? '
                                 'ORDER BY b.batch,b.raw_index', (run_id,)):
                row = dict(r)
                row['entry_url'] = json.loads(row.pop('body'))['entry_url'] if row['body'] else None
                out.append(row)
            return out

    def put_pending(self, home, uris):
        source = {'origin': 'codex_session', 'run_id': 'pipeline-fixture', 'references': [home['reference']]}
        for uri in uris:
            self.pool.put({'schema_version': VERSION2, 'candidate_kind': 'entry',
                           'entry_url': uri, 'requested_goal': None}, source)

    def pending_count(self, aid):
        with self.pool.pool.connect() as con:
            return con.execute("SELECT COUNT(*) FROM data_candidates WHERE application_id=? AND state='pending'",
                               (aid,)).fetchone()[0]

    def metrics(self, run_id):
        out = {}
        with self.pool.pool.connect() as con:
            for r in con.execute("SELECT key,value FROM checkpoints WHERE run_id=? AND key LIKE '%/pipeline-metrics'",
                                 (run_id,)):
                out[r['key']] = json.loads(r['value'])
        return out

    def test_overlap_runs_next_screen_behind_classify_and_serial_never_overlaps(self):
        home = self.home()
        lock = threading.Lock()
        events = []
        chunk1 = set()
        screen2_started = threading.Event()
        classify_first = threading.Event()

        def note(name, **kw):
            with lock:
                events.append({'event': name, 't': time.monotonic(), **kw})

        def screen(pool, ledger, links, root):
            uris = tuple(h['uri'] for h in links)
            note('screen_start', uris=uris)
            if not chunk1:
                chunk1.update(uris)
            elif not set(uris) <= chunk1:
                screen2_started.set()
            try:
                return self.settle_screen(pool, ledger, links, root)
            finally:
                note('screen_end', uris=uris)

        def provider(request, timeout):
            first = not classify_first.is_set()
            classify_first.set()
            note('classify_start', first=first)
            if first:
                # Deterministic overlap proof: chunk 2's screen must already be
                # running behind this classify; serial would time out here.
                if not screen2_started.wait(timeout=20):
                    note('classify_wait_timeout')
            response = self.provider(request, timeout)
            note('classify_end', first=first)
            return response

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=provider):
            report = self.run_overlap(home)
            replay = self.run_overlap(home)
        self.assertEqual(report['listed_unique_candidates'], 4, report)
        self.assertIsNone(report['stopped'], report)
        self.assertFalse(any(e['event'] == 'classify_wait_timeout' for e in events), events)
        starts = [e for e in events if e['event'] == 'screen_start']
        first_classify_end = next(e['t'] for e in events if e['event'] == 'classify_end' and e['first'])
        later = [e for e in starts if not set(e['uris']) <= chunk1]
        # The first later screen is the prefetch worker; the instant follow-up
        # reuse pass at the next chunk's turn is expected and not overlap proof.
        self.assertTrue(later and later[0]['t'] < first_classify_end, events)
        # Publish order and Table2 four fields stay on the original contract.
        rows = self.rows(self.run_id('ov'))
        self.assertEqual([r['result'] for r in rows], ['NEW'] * 4, rows)
        for row in self.pool.rows(protocols=(VERSION2,)):
            self.assertEqual(set(row['candidate']), {'schema_version', 'candidate_kind', 'entry_url', 'requested_goal'})
        # Restart: zero new dispatches, original receipts replayed untouched.
        self.assertEqual(replay['new_dispatches'], {'model': 0, 'GET': 0, 'search': 0}, replay)
        # Per-chunk metrics receipts exist and reconcile with the row ledger.
        metrics = self.metrics(self.run_id('ov'))
        self.assertEqual(len(metrics), 2, metrics)
        ordered = [metrics[k] for k in sorted(metrics)]
        for batch, record in enumerate(ordered):
            self.assertEqual(record['results'], dict(Counter(r['result'] for r in rows if r['batch'] == batch)),
                             (record, rows))
            self.assertIn('screen_seconds', record)
            self.assertIn('classify_seconds', record)
        # No prefetch worker survives the producer.
        self.assertFalse(any(t.name.startswith('producer-prefetch') for t in threading.enumerate()))
        self.assertEqual(report['producer_pipeline']['preflight_skipped_links'], 0)

    def test_serial_default_never_overlaps_and_keeps_report_shape(self):
        home = self.home()
        lock = threading.Lock()
        events = []
        classify_first = threading.Event()

        def note(name, **kw):
            with lock:
                events.append({'event': name, 't': time.monotonic(), **kw})

        def screen(pool, ledger, links, root):
            note('screen_start', uris=tuple(h['uri'] for h in links))
            try:
                return self.settle_screen(pool, ledger, links, root)
            finally:
                note('screen_end', uris=tuple(h['uri'] for h in links))

        def provider(request, timeout):
            first = not classify_first.is_set()
            classify_first.set()
            note('classify_start', first=first)
            response = self.provider(request, timeout)
            note('classify_end', first=first)
            return response

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=provider):
            report = self.run_overlap(home, key='ser', producer_pipeline='serial')
        self.assertEqual(report['listed_unique_candidates'], 4, report)
        self.assertNotIn('producer_pipeline', report)
        first_screen = next(e['t'] for e in events if e['event'] == 'screen_start')
        first_classify_end = next(e['t'] for e in events if e['event'] == 'classify_end' and e['first'])
        later_screens = [e['t'] for e in events if e['event'] == 'screen_start' and e['t'] > first_screen]
        self.assertTrue(all(t > first_classify_end for t in later_screens), events)
        self.assertEqual(self.frozen_config(self.run_id('ser'))['producer_pipeline'], 'serial')

    def test_overlap_payload_tools_and_publish_order_match_serial(self):
        home_self = self.home()
        # The offline provider patches urllib.build_opener globally; the newest
        # fixture owns the gateway opener, so both runs dispatch through it and
        # a closure switches which fixture answers.
        other = fixtures.BusinessValue('test_business_evidence_without_task_or_purpose_is_admitted')
        other.setUp()
        self.addCleanup(other.doCleanups)
        home_other = other.f.f.f.site('https://pipeline.example.org/', html=FOUR_LINKS)[1]
        current = {'provider': self.provider}

        def dispatcher(request, timeout):
            return current['provider'](request, timeout)

        common = dict(target=4, batch_size=2, max_batches=2, model_protocol='entry-tools-13')

        def settle_with(fixture):
            def screen(pool, ledger, links, root):
                for link in links:
                    fixture.original(link['uri'])
                return images.screen(pool, ledger, links, root)
            return screen

        opener_other = other.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=settle_with(self)), \
             patch.object(opener_other, 'open', side_effect=dispatcher):
            serial = self.f.f.f.run_new(home_self, key='cmp', producer_pipeline='serial',
                                        sources=[{**home_self, 'context_only': True}], **common)
            current['provider'] = other.provider
            with patch.object(observed, 'screen', side_effect=settle_with(other)):
                overlap = other.f.f.f.run_new(home_other, key='cmp', producer_pipeline='overlap-1',
                                              sources=[{**home_other, 'context_only': True}], **common)
        self.assertEqual(serial['listed_unique_candidates'], 4, serial)
        self.assertEqual(overlap['listed_unique_candidates'], 4, overlap)

        def purpose_jobs(ledger_path, config):
            with BatchLedger(ledger_path, config).connect() as con:
                return [json.loads(r['payload']) for r in con.execute(
                    "SELECT payload FROM jobs WHERE kind='ai-target-page-purpose-1' ORDER BY rowid")]

        serial_jobs = purpose_jobs(self.root / 'model.db', self.f.f.f.f.cfg)
        overlap_jobs = purpose_jobs(other.root / 'model.db', other.f.f.f.f.cfg)
        self.assertEqual(len(serial_jobs), len(overlap_jobs), (serial_jobs, overlap_jobs))

        def model_visible(jobs):
            # Evidence file identities are fixture-local by design; the model sees
            # scope, sources, page keys and the quoted material itself.
            # page_key and site_context embed fixture-local evidence digests;
            # compare by position with raw sha strings scrubbed.
            def scrub(value):
                if isinstance(value, str):
                    return re.sub(r'[0-9a-f]{64}', 'SHA', value)
                if isinstance(value, list):
                    return [scrub(v) for v in value]
                if isinstance(value, dict):
                    return {k: scrub(v) for k, v in value.items()}
                return value
            # Intra-chunk link order follows fixture-local frozen inputs (hash
            # randomization); compare the per-chunk page material as a set.
            def one(j):
                pages = sorted((scrub({'title': pg['title'], 'site_context': pg['site_context'],
                                       'evidence': pg['evidence'], 'omitted_units': pg['omitted_units']})
                                for pg in j['input']['pages']), key=canonical)
                return scrub({'scope': j['input']['scope'], 'source_uris': sorted(j['input']['source_uris']),
                              'pages': pages})
            return [one(j) for j in jobs]

        self.assertEqual(model_visible(serial_jobs), model_visible(overlap_jobs))
        def schema_visible(jobs):
            # Per-page schema properties are keyed by the fixture-local page_key;
            # compare the schema shape with those keys renamed by position.
            def one(tools):
                params = tools[0]['function']['parameters']
                pages = params['properties']['decisions']['properties']
                order = {k: i for i, k in enumerate(sorted(pages))}
                def walk(v, *, key=None):
                    if isinstance(v, dict):
                        return {renamed(k): walk(x, key=k) for k, x in v.items()}
                    if isinstance(v, list):
                        if key == 'required':
                            return sorted(order.get(e, -1) for e in v if isinstance(e, str))
                        return [walk(e) for e in v]
                    if isinstance(v, str):
                        return re.sub(r'[0-9a-f]{12,64}', 'SHA', v)
                    return v
                def renamed(k):
                    return 'p%d' % order[k] if k in order else k
                return {'name': tools[0]['function']['name'], 'schema': walk(params)}
            return [one(j['tools']) for j in jobs]

        self.assertEqual(schema_visible(serial_jobs), schema_visible(overlap_jobs))
        self.assertEqual([j['input']['version'] for j in serial_jobs],
                         [j['input']['version'] for j in overlap_jobs])
        self.assertEqual([j['system'] for j in serial_jobs], [j['system'] for j in overlap_jobs])
        # Cross-run order is fixture-local; each run must publish its own chunks
        # in sequence with the frozen Table2 contract instead.
        serial_rows = self.rows(self.run_id('cmp'))
        overlap_rows = PipelineOverlap.rows(other, other.f.f.f.f.cfg['run_id'] + '/entry-batch/cmp')
        self.assertEqual(sorted(r['entry_url'] for r in serial_rows),
                         sorted(r['entry_url'] for r in overlap_rows))
        for rows in (serial_rows, overlap_rows):
            self.assertEqual([(r['batch'], r['raw_index']) for r in rows],
                             [(0, 0), (0, 1), (1, 0), (1, 1)], rows)

    def test_pending_at_cap_skips_browser_and_model_without_fabricated_rows(self):
        aid, home = self.f.f.f.site('https://pipeline.example.org/',html=FOUR_LINKS)
        self.put_pending(home, ['https://pipeline.example.org/pad%d' % i for i in range(100)])
        self.assertEqual(self.pending_count(aid), 100)
        screen_calls = []

        def screen(pool, ledger, links, root):
            screen_calls.append([h['uri'] for h in links])
            return self.settle_screen(pool, ledger, links, root)

        def no_model(request, timeout):
            raise AssertionError('purpose model must not be dispatched at cap')

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=no_model):
            report = self.run_overlap(home, key='cap', target=4, batch_size=2, max_batches=2)
        self.assertEqual(report['listed_unique_candidates'], 0, report)
        self.assertIsNone(report['stopped'], report)
        self.assertEqual(screen_calls, [])
        self.assertEqual(self.rows(self.run_id('cap')), [])
        metrics = self.metrics(self.run_id('cap'))
        self.assertEqual(sum(m['preflight_skipped'] for m in metrics.values()), 4, metrics)
        receipts = sorted((self.root / 'output' / 'cap').glob('pipeline-preflight-*.json'))
        self.assertEqual(len(receipts), 2, receipts)
        record = load_json(receipts[0])
        self.assertEqual(record['reason'], 'APP_PENDING_CAP_PREFLIGHT')
        self.assertEqual(len(record['records'][0]['skipped_links']), 2)
        self.assertEqual((record['records'][0]['pending'], record['records'][0]['cap'],
                          record['records'][0]['remaining']), (100, 100, 0))
        with self.pool.pool.connect() as con:
            conclusions = [json.loads(r[0]) for r in con.execute(
                'SELECT i.conclusion FROM application_scope_items i WHERE i.conclusion IS NOT NULL')]
        self.assertEqual({c['stage'] for c in conclusions}, {'app_pending_cap_preflight'}, conclusions)
        self.assertTrue(all(c['result'] == 'NOT_SELECTED' for c in conclusions))
        self.assertEqual(self.pending_count(aid), 100)

    def test_partial_headroom_prepare_is_bounded_and_shortfall_stays_honest(self):
        aid, home = self.f.f.f.site('https://pipeline.example.org/',html=FOUR_LINKS)
        self.put_pending(home, ['https://pipeline.example.org/pad%d' % i for i in range(97)])
        seen = []

        def screen(pool, ledger, links, root):
            seen.append([h['uri'] for h in links])
            return self.settle_screen(pool, ledger, links, root)

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=self.provider):
            report = self.run_overlap(home, key='bound', target=4, batch_size=4, max_batches=1)
        self.assertEqual(report['listed_unique_candidates'], 3, report)
        self.assertEqual(report['deficit'], 1, report)
        self.assertEqual(len(seen[0]), 3, seen)
        metrics = self.metrics(self.run_id('bound'))
        self.assertEqual(sum(m['preflight_skipped'] for m in metrics.values()), 1, metrics)
        # In-flight reservations never became formal rows beyond the cap.
        self.assertEqual(self.pending_count(aid), 100, report)

    def test_race_filling_pending_after_preflight_still_rejected_at_publish(self):
        aid, home = self.f.f.f.site('https://pipeline.example.org/',html=FOUR_LINKS)
        self.put_pending(home, ['https://pipeline.example.org/pad%d' % i for i in range(98)])

        def provider(request, timeout):
            # Another writer fills the last headroom during classify.
            self.put_pending(home, ['https://pipeline.example.org/race1', 'https://pipeline.example.org/race2'])
            return self.provider(request, timeout)

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=self.settle_screen), patch.object(opener, 'open', side_effect=provider):
            report = self.run_overlap(home, key='race', target=4, batch_size=2, max_batches=1)
        self.assertEqual(report['listed_unique_candidates'], 0, report)
        self.assertEqual(report['row_results'].get('OVER_LIMIT'), 2, report)
        over = [json.loads(r['record']) for r in self.rows(self.run_id('race')) if r['result'] == 'OVER_LIMIT']
        self.assertEqual(len(over), 2)
        self.assertTrue(all('APP_PENDING_CAP' in (r['reason'] or '') for r in over), over)
        self.assertEqual(self.pending_count(aid), 100)

    def test_prefetch_host_failure_keeps_current_chunk_and_restart_resumes_cleanly(self):
        home = self.home()
        fail = {'on': True}

        def screen(pool, ledger, links, root):
            if fail['on'] and any(h['uri'].endswith(('/c3', '/c4')) for h in links):
                raise RuntimeError('prefetch host failure')
            return self.settle_screen(pool, ledger, links, root)

        opener = self.f.f.b.f.f.provider.opener
        run_id = self.run_id('pfail')
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=self.provider):
            first = self.run_overlap(home, key='pfail')
            self.assertEqual(first['listed_unique_candidates'], 2, first)
            self.assertEqual(first['stopped']['type'], 'RuntimeError', first)
            with self.pool.pool.connect() as con:
                saved = con.execute("SELECT COUNT(*) FROM checkpoints WHERE run_id=? AND key LIKE '%/selection'",
                                    (run_id,)).fetchone()[0]
            self.assertEqual(saved, 1)
            fail['on'] = False
            second = self.run_overlap(home, key='pfail')
        self.assertEqual(second['listed_unique_candidates'], 4, second)
        self.assertIsNone(second['stopped'], second)
        self.assertEqual(second['new_dispatches']['model'], 1, second)
        self.assertEqual(Counter(r['result'] for r in self.rows(run_id)), {'NEW': 4})

    def test_page_level_unknown_in_next_chunk_isolated_and_original_kept(self):
        home = self.home()
        unsettled = 'https://pipeline.example.org/c3'
        identity = object_sha256([images.SCREEN_RUN, 'browser', entry_identity(unsettled)])
        rid, old = self.pool.pool.reserve_tool(images.SCREEN_RUN, 'browser', entry_identity(unsettled),
                                               {'uri': entry_identity(unsettled), 'image_policy': images.VERSION})
        self.assertFalse(old)
        self.pool.pool.settle_tool(rid, 'unknown', {'reason': 'original unsettled probe'})

        def screen(pool, ledger, links, root):
            return self.settle_screen(pool, ledger, links, root, skip=(unsettled,))

        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=screen), patch.object(opener, 'open', side_effect=self.provider):
            report = self.run_overlap(home, key='unk')
        self.assertEqual(report['listed_unique_candidates'], 3, report)
        with self.pool.pool.connect() as con:
            state = con.execute('SELECT state FROM tool_requests WHERE id=?', (identity,)).fetchone()[0]
        self.assertEqual(state, 'unknown')
        self.assertEqual(Counter(r['result'] for r in self.rows(self.run_id('unk'))), {'NEW': 3})
        held = []
        for path in sorted((self.root / 'output' / 'unk').glob('entry-links-*.json')):
            held += [r for r in load_json(path)['page_consumption'] if r['uri'] == unsettled]
        self.assertEqual(held[0]['decision']['status'], 'HELD')

    def test_mode_is_frozen_and_cannot_switch_within_one_run(self):
        home = self.home()
        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=self.settle_screen), patch.object(opener, 'open', side_effect=self.provider):
            self.run_overlap(home, key='switch')
            with self.assertRaisesRegex(ValueError, 'switch pipeline mode'):
                self.run_overlap(home, key='switch', producer_pipeline='serial')
            replay = self.run_overlap(home, key='switch', producer_pipeline='overlap-1')
        self.assertEqual(self.frozen_config(self.run_id('switch'))['producer_pipeline'], 'overlap-1')
        self.assertEqual(replay['new_dispatches'], {'model': 0, 'GET': 0, 'search': 0}, replay)

    def test_overlap_requires_budget_concurrency_headroom(self):
        home = self.home()
        opener = self.f.f.b.f.f.provider.opener
        original = self.f.f.f.f.cfg['budget']['max_concurrent_jobs']
        self.f.f.f.f.cfg['budget']['max_concurrent_jobs'] = 1
        try:
            with patch.object(observed, 'screen', side_effect=self.settle_screen), \
                 patch.object(opener, 'open', side_effect=self.provider):
                # Fail fast before any probe can be poisoned as UNKNOWN.
                with self.assertRaisesRegex(ValueError, 'max_concurrent_jobs'):
                    self.run_overlap(home, key='budget')
        finally:
            self.f.f.f.f.cfg['budget']['max_concurrent_jobs'] = original

    def test_old_run_without_field_stays_serial_and_rejects_overlap(self):
        home = self.home()
        run_id = self.run_id('legacy')
        opener = self.f.f.b.f.f.provider.opener
        with patch.object(observed, 'screen', side_effect=self.settle_screen), patch.object(opener, 'open', side_effect=self.provider):
            self.run_overlap(home, key='legacy', producer_pipeline='serial')
        # Simulate a pre-2026-11-09 run: drop the new field from the frozen config.
        with self.pool.pool.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            config = json.loads(con.execute('SELECT config FROM runs WHERE id=?', (run_id,)).fetchone()[0])
            del config['producer_pipeline']
            con.execute('UPDATE runs SET config=? WHERE id=?', (canonical(config), run_id))
            con.commit()
        with self.assertRaisesRegex(ValueError, 'predates producer_pipeline'):
            self.run_overlap(home, key='legacy', producer_pipeline='overlap-1')


if __name__ == '__main__':
    unittest.main()
