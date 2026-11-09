import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from site_planner.candidate_pool import CandidatePool
from site_planner.site_pool import SitePool
from webcollect.agent_controller import exclusive
from webcollect.candidate_contract import validate_task_binding
from webcollect.react_session import build_url_task
from webcollect.storage import allocate_in_transaction, ensure_registry_schema


class Table1DeliverySiteIDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        SitePool(self.root / 'pool.sqlite3', initialize=True)
        self.pool = CandidatePool(self.root / 'pool.sqlite3', install=True)
        with self.pool.pool.connect(write=True) as con:
            con.execute("INSERT INTO applications VALUES('app-muxtly','muxtly.com','Muxtly','在线工具',0)")
            con.execute("INSERT INTO applications VALUES('app-wiki','zh.wikipedia.org','维基','百科与文档',0)")
            con.execute("INSERT INTO data_candidates VALUES('candidate-muxtly','app-muxtly','muxtly',1,'{}',0,'pending')")
            con.execute("INSERT INTO data_candidates VALUES('candidate-wiki','app-wiki','wiki',1,'{}',0,'pending')")
            con.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def allocate(self, name, uri, required_site_id=None):
        path = self.root / name
        con = sqlite3.connect(path)
        try:
            ensure_registry_schema(con)
            con.execute('BEGIN IMMEDIATE')
            result = allocate_in_transaction(con, uri, '在线工具', 'real', '20261110',
                                             required_site_id=required_site_id)
            con.commit()
            return result
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def test_table1_rowid_defines_muxtly_and_wiki_site_ids(self):
        self.assertEqual(self.pool.delivery_site_id('candidate-muxtly'), 'S000001')
        self.assertEqual(self.pool.delivery_site_id('candidate-wiki'), 'S000002')
        with self.assertRaisesRegex(ValueError, 'Table1'):
            self.pool.delivery_site_id('missing')

    def test_independent_registries_keep_producer_site_ids_and_sample_format(self):
        muxtly_1 = self.allocate('server-a.sqlite3', 'https://www.muxtly.com/', 'S000001')
        muxtly_2 = self.allocate('server-a.sqlite3', 'https://www.muxtly.com/', 'S000001')
        wiki = self.allocate('server-b.sqlite3', 'https://zh.wikipedia.org/', 'S000002')
        self.assertEqual(muxtly_1['sample_id'], 'S000001_sample_000001')
        self.assertEqual(muxtly_2['sample_id'], 'S000001_sample_000002')
        self.assertEqual(wiki['sample_id'], 'S000002_sample_000001')
        self.assertEqual(len({muxtly_1['sample_id'], muxtly_2['sample_id'], wiki['sample_id']}), 3)

    def test_existing_registry_mapping_and_site_number_cannot_be_reassigned(self):
        self.allocate('occupied.sqlite3', 'https://www.muxtly.com/', 'S000001')
        with self.assertRaisesRegex(ValueError, '不一致'):
            self.allocate('occupied.sqlite3', 'https://www.muxtly.com/', 'S000002')
        with self.assertRaisesRegex(ValueError, '占用'):
            self.allocate('occupied.sqlite3', 'https://zh.wikipedia.org/', 'S000001')

    def test_legacy_tasks_retain_registry_local_allocation(self):
        result = self.allocate('legacy.sqlite3', 'https://legacy.example/')
        self.assertEqual(result['site_id'], 'S000001')
        self.assertEqual(result['sample_id'], 'S000001_sample_000001')

    def test_frozen_claim_and_task_must_carry_the_same_versioned_site_id(self):
        snapshot = {'schema_version': 'candidate-fixture', 'entry_url': 'https://www.muxtly.com/'}
        claim = {'candidate_id': 'candidate-muxtly', 'claim_id': 'claim-1', 'version': 1,
                 'snapshot': snapshot, 'site_id_version': 'table1-rowid-site-id-1', 'site_id': 'S000001'}
        reference = exclusive(self.root / 'claim.json', claim)
        task = build_url_task(url='https://www.muxtly.com/', task_version='fixture')
        task['fragment']['candidate_attempt'] = 'claim-1'
        task['candidate_binding'] = {
            'schema_version': 'webcollect-candidate-consumption-1',
            'candidate_id': 'candidate-muxtly', 'claim_id': 'claim-1', 'version': 1,
            'candidate': snapshot, 'claim_reference': reference,
            'site_id_version': 'table1-rowid-site-id-1', 'site_id': 'S000001'}
        self.assertEqual(validate_task_binding(task)['site_id'], 'S000001')
        task['candidate_binding']['site_id'] = 'S000002'
        with self.assertRaisesRegex(ValueError, 'site ID'):
            validate_task_binding(task)


if __name__ == '__main__':
    unittest.main()
