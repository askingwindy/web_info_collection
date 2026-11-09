"""V5 ready-to-prefix eligibility and immutable delivery length boundaries."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from webcollect.postprocess import (_derive_verified, process, ready_requires_prefix,
                                    required_result_checks, terminal_outcome,
                                    validate_effective_limit)

V5='webcollect-five-ten-effective-ending-5'
V4='webcollect-continuous-attempt-ending-4'


def task(policy=V5):
    return {'fragment':{'ending_policy':policy},'instruction':'修改收入并核对实际税后结果'}


def terminal(checks, stop='ready'):
    return {'stop_reason':stop,'goal_evidence':{'checks':deepcopy(checks)}}


class FiveTenDeliveryTests(unittest.TestCase):
    def test_ready_missing_result_requests_prefix_only_for_v5(self):
        original=terminal([{'field':'实际税后收入','status':'UNVERIFIED'}])
        snapshot=deepcopy(original)
        self.assertTrue(ready_requires_prefix(task(),original))
        self.assertFalse(ready_requires_prefix(task(V4),original))
        self.assertEqual(original,snapshot)
        pending=terminal([{'field':'补充说明','status':'PENDING'}])
        self.assertEqual(required_result_checks(pending),[])
        self.assertFalse(ready_requires_prefix(task(),pending))

    def test_ready_cannot_claim_success_but_verified_prefix_can_be_pending_sample(self):
        raw_terminal=terminal([{'field':'实际税后收入','status':'UNVERIFIED'}])
        state={'visible_text':'收入计算器\n当前输入 1000','title':'收入计算器','values':[]}
        record={'terminal':raw_terminal}
        status,description=terminal_outcome(task(),record,state)
        self.assertEqual(status,'failed')
        self.assertIn('未核验',description)
        projected={'terminal':{'stop_reason':'ready'},'trusted_prefix':{'original_goal_completed':False}}
        status,description=terminal_outcome(task(),projected,state)
        self.assertEqual(status,'success')  # saved fragment, not original goal success
        self.assertIn('完整原目标未确认完成',description)
        self.assertEqual(raw_terminal,record['terminal'])

    def test_normal_derivation_rejects_eleven_effective_actions(self):
        with TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'ten effective'):
                _derive_verified(task(),{},[{}]*11,Path(td),{}, {})
        validate_effective_limit(task(),10)
        validate_effective_limit(task(V4),11)  # frozen continuous policy

    def test_prefix_process_cannot_bypass_v5_effective_cap(self):
        source={'task':task(),'terminal':{'stop_reason':'ready'},'trajectory':[{}]*11}
        verified=SimpleNamespace(record=lambda root:source)
        with TemporaryDirectory() as td, patch('webcollect.trusted_prefix.project_prefix',return_value=source):
            with self.assertRaisesRegex(ValueError,'ten effective'):
                process(Path(td),Path(td)/'delivery',{}, {},prefix_end_step=11,_verified=verified)

    def test_annotation_schema_accepts_v5_without_removing_historical_versions(self):
        path=Path(__file__).parents[1]/'webcollect/schemas/annotation.schema.json'
        schema=json.loads(path.read_text())
        enums=[]
        def walk(node):
            if isinstance(node,dict):
                if 'enum' in node:enums.append(node['enum'])
                for value in node.values():walk(value)
            elif isinstance(node,list):
                for value in node:walk(value)
        walk(schema)
        self.assertTrue(any(V5 in values and V4 in values for values in enums))
