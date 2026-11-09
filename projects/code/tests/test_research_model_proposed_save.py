"""V1 research saves keep the first frozen goal without inventing an old goal."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import test_full_chain_repair as repair_fixture
from webcollect.agent_controller import exclusive
from webcollect.batch_core import file_sha
from webcollect.candidate_contract import VERSION, research_duplicate_basis, research_overlap_sample_ids
from webcollect.current_chain import initialize_chain
from webcollect.planning import canonical
from webcollect.react_session import REACT_VERSION
from webcollect.session_objective import bind


class ModelProposedResearchSaveTests(unittest.TestCase):
    def setUp(self):
        repair_fixture.Research.setUp(self)
        self.registry=self.root/'registry';self.manifest=self.root/'chain/manifest.json'
        initialize_chain(self.manifest,self.registry,chain_id='local',current_result_roots=[self.root/'results'])
        self.auth=exclusive(self.root/'scoped-authorization.json',{'scope':'original-two-baselines-only',
            'candidate_id':self.cid,'version':self.old['version'],'objective':self.obj,'production_counted':False})

    def task(self,original_objective=False):
        output=self.root/('original-with-objective' if original_objective else 'original-no-objective')
        output.mkdir(exist_ok=True)
        if original_objective:(output/'session-objective.json').write_bytes(Path(self.obj['path']).read_bytes())
        with self.pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',
                (canonical({'output':str(output),'registry':str(self.registry)}),self.old['claim_id']))
        claim=self.pool.claim_research('w','research',candidate_id=self.cid,version=self.old['version'],
            original_claim_id=self.old['claim_id'],objective=self.obj,authorization=self.auth)
        bound={**claim['binding'],'registry':str(self.registry),'history_set':str(self.manifest)}
        with self.pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',(canonical(bound),claim['claim_id']))
        claim=self.pool.get_claim(claim['claim_id']);frozen={**claim,'pool':str(self.pool.path)}
        ref=exclusive(self.root/'research-claim.json',frozen)
        objective=bind(self.obj,frozen)
        task={'candidate_binding':{'schema_version':VERSION,'candidate_id':self.cid,'claim_id':claim['claim_id'],
                'version':claim['version'],'candidate':claim['snapshot'],'claim_reference':ref},
            'fragment':{'schema_version':REACT_VERSION,'candidate_attempt':claim['claim_id'],'session_objective':objective},
            'workflow_proposal':{'spec':{'goal':{'structured':None},'session_objective':deepcopy(objective)}}}
        return task,claim

    def test_missing_original_objective_accepts_only_original_named_overlap(self):
        task,claim=self.task()
        self.assertEqual(claim['binding']['research_replay']['objective_origin'],'model-proposed-research')
        basis=research_duplicate_basis(task,self.registry)
        self.assertEqual(research_overlap_sample_ids(basis),{'old'})
        self.assertFalse(basis['production_counted'])
        self.assertFalse(basis['production_duplicate_acceptance'])

    def test_existing_original_goal_rejects_changed_content_or_bytes(self):
        task,claim=self.task(original_objective=True)
        original=self.root/'original-with-objective/session-objective.json'
        original.write_text(original.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'objective bytes'):research_duplicate_basis(task,self.registry)
        value=json.loads(original.read_text());value['objective']['description']='changed goal'
        original.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'objective bytes'):research_duplicate_basis(task,self.registry)

    def copied_objective(self,task):
        original=Path(self.obj['path'])
        copied=self.root/'copied-objective.json'
        copied.write_text(json.dumps(json.loads(original.read_text()),sort_keys=True,indent=2))
        reference={'path':str(copied),'sha256':file_sha(copied)}
        frozen=json.loads(Path(task['candidate_binding']['claim_reference']['path']).read_text())
        current=bind(reference,frozen)
        task['fragment']['session_objective']=current
        task['workflow_proposal']['spec']['session_objective']=deepcopy(current)

    def test_consumption_copy_with_identical_content_preserves_objective_binding(self):
        task,_=self.task();self.copied_objective(task)
        self.assertEqual(research_overlap_sample_ids(research_duplicate_basis(task,self.registry)),{'old'})

    def test_derived_fragment_uses_same_claim_sealed_original_objective(self):
        task,claim=self.task();self.copied_objective(task)
        output=self.root/'current-output'
        with self.pool.transaction() as con:
            live=self.pool.get_claim(claim['claim_id'])
            live['binding']['output']=str(output)
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',(canonical(live['binding']),claim['claim_id']))
        raw=output/'execution/capture/evidence/sample/raw';raw.mkdir(parents=True)
        boundary=exclusive(raw/'boundary.json',{'task':task})
        exclusive(raw/'raw-receipt.json',{'boundary':boundary,'files_sha256':{'boundary.json':boundary['sha256']}})
        del task['fragment']['session_objective']
        del task['workflow_proposal']['spec']['session_objective']
        self.assertEqual(research_overlap_sample_ids(research_duplicate_basis(task,self.registry)),{'old'})
        # A rewritten boundary cannot provide the removed execution objective.
        original=json.loads(Path(boundary['path']).read_text())
        original['task']['fragment']['session_objective']['objective']['description']='changed'
        Path(boundary['path']).write_text(json.dumps(original))
        with self.assertRaises(ValueError):research_duplicate_basis(task,self.registry)

    def test_missing_objective_without_sealed_original_rejected(self):
        task,_=self.task()
        del task['fragment']['session_objective']
        del task['workflow_proposal']['spec']['session_objective']
        with self.assertRaisesRegex(ValueError,'sealed original'):research_duplicate_basis(task,self.registry)

    def _rewrite_descriptor(self,task,claim,**updates):
        ref=task['candidate_binding']['claim_reference'];path=Path(ref['path']);frozen=json.loads(path.read_text())
        descriptor=frozen['binding']['research_replay'];descriptor.update(updates)
        with self.pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET binding=? WHERE claim_id=?',(canonical(frozen['binding']),claim['claim_id']))
            con.execute("UPDATE candidate_events SET record=? WHERE claim_id=? AND kind='research_claimed'",(canonical(descriptor),claim['claim_id']))
        path.write_text(json.dumps(frozen));ref['sha256']=file_sha(path)

    def test_wrong_origin_rejected_even_with_matching_live_event(self):
        task,claim=self.task();self._rewrite_descriptor(task,claim,objective_origin='original')
        with self.assertRaisesRegex(ValueError,'model-proposed objective binding'):research_duplicate_basis(task,self.registry)

    def test_missing_research_event_rejected(self):
        task,claim=self.task()
        with self.pool.transaction() as con:
            con.execute("DELETE FROM candidate_events WHERE claim_id=? AND kind='research_claimed'",(claim['claim_id'],))
        with self.assertRaisesRegex(ValueError,'authorization'):research_duplicate_basis(task,self.registry)

    def test_current_frozen_goal_must_match_descriptor(self):
        task,_=self.task();task['fragment']['session_objective']['objective']['description']='arbitrary model words'
        with self.assertRaisesRegex(ValueError,'model-proposed objective binding'):research_duplicate_basis(task,self.registry)
