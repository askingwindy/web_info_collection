"""Regression for the actual R02 branch outputs; no network or model requests."""
import json, unittest
from copy import deepcopy
from webcollect.model_gateway import (ModelGateway,parse_decision_content,normalize_branch,
    validate_branch,branch_wire_schema,schema_error_feedback)
from webcollect.banded_plan import choice_schema
from webcollect.direct_completion import schema,bind_answer
from jsonschema import ValidationError

class BranchWireContract(unittest.TestCase):
    def setUp(self):
        self.schema=schema(choice_schema(True,inherited=True))
        self.prompt={'options':[{'choice':'continue_plan'},{'choice':'replan'},{'choice':'finish_reading'}],
            'replan_contract':{'inherited_finish_when':{'kind':'goal_evidence'}},
            'reading_evidence_catalog':[{'observation_id':'o','node':'n','quote':'original text','operation_id':'op'}]}
    def test_wire_contains_schema_and_minimal_semantics(self):
        gateway=object.__new__(ModelGateway)
        gateway._call=lambda *args,**kw:kw['native_context']['system']
        sent=gateway.call_message({},'test',json.dumps(self.prompt),self.schema,system='base',attempt_id='a',grounded_choice=True)
        self.assertIn('"expected"',sent);self.assertIn('"reading_answer"',sent)
        self.assertIn('"choice"',sent);self.assertIn('current_step',sent)
        contract=branch_wire_schema(self.schema,self.prompt)
        self.assertEqual(list(contract['properties']['plan']['anyOf'][0]['properties']),['steps'])
    def test_ambiguous_action_is_not_silently_continued(self):
        with self.assertRaisesRegex(ValueError,'BRANCH_CHOICE_REQUIRED'):
            normalize_branch({'action':'click','options':['continue_plan'],'target':{'node':'n'}},self.prompt)
    def test_nodes_and_inherited_completion_marker_with_real_missing_expected(self):
        reply={'choice':'continue_plan','citations':[{'observation_id':'o','nodes':['n']}],
            'plan':{'steps':[{'action':'scroll','direction':'down','purpose':'read'},
                             {'action':'finish_reading','purpose':'answer'}]}}
        parsed,_=parse_decision_content(json.dumps(reply),'single-json-commentary-1')
        normal=normalize_branch(parsed,self.prompt)
        self.assertEqual(normal['choice'],'replan');self.assertEqual(normal['citations'][0]['quote'],'original text')
        self.assertEqual(len(normal['plan']['steps']),1)
        with self.assertRaises(ValidationError) as err:validate_branch(normal,self.schema)
        errors=schema_error_feedback(err.exception)
        self.assertTrue(any(e['field_path'][-1]=='expected' for e in errors),errors)
        self.assertFalse(any(e['field_path']==['choice'] for e in errors),errors)
        normal['plan']['steps'][0]['expected']={'kind':'scroll_changed'}
        validate_branch(normal,self.schema)
        self.assertEqual(normalize_branch(normal,self.prompt),normal)
        bound=bind_answer({'check_answers':[{'check_index':0,'passages':normal['citations']}]},
            {'goal':'read','checks':[{'evidence_kind':'reading'}]},self.prompt['reading_evidence_catalog'],[])
        self.assertEqual(bound['check_answers'][0]['operation_ids'],['op'])
    def test_wrong_or_ambiguous_source_rejected(self):
        for prompt in (dict(self.prompt,reading_evidence_catalog=[]),dict(self.prompt,reading_evidence_catalog=self.prompt['reading_evidence_catalog']*2)):
            with self.assertRaisesRegex(ValueError,'CITATION_SOURCE_NOT_UNIQUE'):
                normalize_branch({'choice':'continue_plan','citations':[{'nodes':['n'],'observation_id':'o'}]},prompt)

if __name__=='__main__':unittest.main()
