"""Generation cutover uses local disposable stores. No browser or network."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from site_planner.site_pool import SitePool
from webcollect.batch_core import load_json, save_json
from webcollect.batch_protocol import facts_state
from webcollect.candidate_project import initialize
from webcollect.current_chain import check_project_guard, check_project_pool, read_chain_scope
from webcollect.runtime import RuntimeStore
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
from webcollect.storage import allocate
from webcollect.task_admission import reference


class ProjectTests(unittest.TestCase):
    uri = 'https://example.org/tool'

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.cfg = load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')

    def project(self, name, **options):
        return load_json(initialize(self.root/name, name, {'max_worker_seconds':15},
                                    self.cfg, self.cfg, **options))

    def test_failed_visits_are_observations_in_new_project_including_shards(self):
        legacy = SiteFailureStore.initialize({'ledger':str(self.root/'legacy.sqlite3'),
                                              'campaign_id':'old','formal_since':1})
        scope = self.project('current')
        active = SiteFailureStore(load_json(scope['policy'])['site_failure_guard'])
        def record(store, number, state='failed'):
            return store.record(self.uri, 'visit-'+str(number), stage='probe', state=state,
                                reason='controlled result', real_execution=True,
                                evidence=[reference(scope['policy'])], usage_refs=[])
        for store in (legacy,active):
            for number in range(3):
                record(store, number)
        with self.assertRaises(SiteStopped):
            legacy.guard(self.uri)
        active.guard(self.uri)
        self.assertEqual(record(active, 4)['failure_count'], 4)
        for store, blocked in ((legacy,True),(active,False)):
            facts = store.export_facts()
            path = self.root/(facts['campaign_id']+'.json')
            save_json(path,facts)
            state = facts_state([reference(path)],facts['campaign_id'])
            self.assertEqual(bool(state['excluded_sites']),blocked)
            self.assertEqual(store.status(self.uri)['dispatch_blocked'],blocked)
        with self.assertRaises(ValueError):
            active.import_facts(legacy.export_facts())
        bad = active.export_facts()
        del bad['failure_limit']
        with self.assertRaises(ValueError):
            active.import_facts(bad)
        self.assertTrue(record(active, 5, 'unknown')['dispatch_blocked'])
        with self.assertRaises(SiteStopped):
            active.guard(self.uri)
        path = self.root/'hold.json'
        save_json(path, active.export_facts())
        self.assertTrue(facts_state([reference(path)],'current')['excluded_sites'])

    def test_mixed_pool_guard_and_job_ledgers_rejected(self):
        a, b = self.project('project-a'), self.project('project-b')
        owner = read_chain_scope(a['history_set'])
        self.assertTrue(check_project_pool(owner, SitePool(a['pool'])))
        for wrong in (read_chain_scope(b['history_set']), None):
            with self.assertRaisesRegex(ValueError, 'pool belongs'):
                check_project_pool(wrong, SitePool(a['pool']))
        guard = load_json(a['policy'])['site_failure_guard']
        for guard_arg, jobs in ((load_json(b['policy'])['site_failure_guard'],a['consumer_db']),
                                (guard,b['consumer_db']), (guard,a['registry']), (guard,a['producer_db'])):
            with self.assertRaises(ValueError):
                check_project_guard(owner, guard_arg, jobs, role='consumer')
        check_project_guard(owner, guard, a['consumer_db'], role='consumer')
        self.assertFalse(Path(a['consumer_db']).exists())
        self.assertFalse(Path(a['producer_db']).exists())
        with self.assertRaises(FileExistsError):
            self.project('project-a')
        self.assertEqual(read_chain_scope(a['history_set']),owner)

    def test_page_identity_binds_each_task_and_one_accepted_sample(self):
        import test_production_identity as fixture
        from webcollect.production_identity import reserve, guard, accept, validate_plan
        case = fixture.PilotIdentityTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        scope = self.project('tasks')
        other = deepcopy(case.task)
        other['task_id'] += '-second'
        plan = {'schema_version':'webcollect-plan-m4-1','tasks':[case.task,other],
                'generation':{'history_scope':read_chain_scope(scope['history_set'])}}
        self.assertTrue(validate_plan(plan,required=True))
        with self.assertRaisesRegex(ValueError,'same logical task'):
            validate_plan({**plan,'tasks':[case.task,case.task]},required=True)
        with closing(sqlite3.connect(scope['registry'])) as con:
            con.execute('BEGIN IMMEDIATE')
            for item in (case.task,other):
                key = item['task_id']
                reserve(con,key,item)
                guard(con,key,item)
                accept(con,key,item,'fixture-'+key)
                with self.assertRaisesRegex(ValueError,'another accepted'):
                    accept(con,key,item,'fixture-another-sample')
            self.assertEqual(con.execute('SELECT count(*) FROM m4_pilot_page_claims').fetchone()[0],2)

    def test_number_high_water_transfers_with_no_page_site_or_worker_history(self):
        old = self.project('older')
        old_id = allocate(old['registry'], self.uri, '在线工具', day='20261101')
        reserved = allocate(old['registry'], self.uri, '在线工具', day='20261101', batch_id='B20261101_017')
        prev = RuntimeStore(old['registry'],'project-setup')
        now = old['started_at']
        prev.worker_session('old-open',old['output'],now=now)
        metering = prev.resource_checkpoint(old['output'],now=now+40)
        self.assertEqual((metering['reasons'],metering['campaign_worker_seconds']),([],40))
        new = self.project('newer',numbering_from=[old['registry']])
        curr = RuntimeStore(new['registry'],'project-setup')
        checkpoint = curr.resource_checkpoint(new['output'],now=now+100)
        self.assertEqual((checkpoint['status'],checkpoint['campaign_worker_seconds'],checkpoint['open_sessions']),
                         ('PASS',0,[]))
        with closing(sqlite3.connect(new['registry'])) as con:
            for table in ('sites','allocations','m4_tasks','m4_attempts','current_chain_results'):
                self.assertEqual(con.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
        with self.assertRaisesRegex(ValueError,'上一代'):
            allocate(new['registry'],self.uri,'在线工具',batch_id=reserved['batch_id'])
        fresh = allocate(new['registry'],self.uri,'在线工具',day='20261101')
        self.assertGreater(fresh['site_id'],old_id['site_id'])
        self.assertEqual(fresh['batch_id'],'B20261101_018')
        self.assertEqual(prev.resource_checkpoint(old['output'],now=now+100)['open_sessions'], ['old-open'])
