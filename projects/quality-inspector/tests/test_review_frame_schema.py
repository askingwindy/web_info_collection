"""Actual-frame constraints prevent invented final screenshots entering reviews."""
from copy import deepcopy
import unittest
from jsonschema import Draft202012Validator, ValidationError
from quality_inspector.ai_worker import (REVIEW_SCHEMA, bound_review_schema,
    bound_difference_schema, synthetic_review, validate_review)


class BoundFrameSchemaTests(unittest.TestCase):
    def test_phantom_extra_confirmation_frame_is_rejected(self):
        result=synthetic_review([1,2,3,4,5,6])
        result['step_observations'].append({'step_id':7,'note':'Invented extra final frame'})
        result['checks']['terminal_semantics']['evidence_steps']=[6,7]
        with self.assertRaises(ValidationError):
            Draft202012Validator(bound_review_schema([1,2,3,4,5,6])).validate(result)

    def test_duplicate_ids_with_different_notes_cannot_replace_missing_frame(self):
        result=synthetic_review([1,2,3]);result['step_observations'][1]={'step_id':1,'note':'Different note'}
        with self.assertRaises(ValidationError):
            Draft202012Validator(bound_review_schema([1,2,3])).validate(result)

    def test_exact_noncontiguous_frame_set_accepts_reordered_observations(self):
        result=synthetic_review([2,4,9]);result['step_observations'].reverse()
        Draft202012Validator(bound_review_schema([2,4,9])).validate(result)
        validate_review(result,[2,4,9])

    def test_segment_cannot_cite_frame_not_supplied_in_that_segment(self):
        result=synthetic_review([5,6]);result['checks']['privacy']['evidence_steps']=[1]
        with self.assertRaises(ValidationError):
            Draft202012Validator(bound_review_schema([5,6])).validate(result)

    def test_pending_visual_decision_can_preserve_missing_evidence(self):
        result=synthetic_review([1,2]);result['checks']['privacy'].update(status='REVIEW_REQUIRED',evidence_steps=[])
        Draft202012Validator(bound_review_schema([1,2])).validate(result)
        validate_review(result,[1,2])

    def test_difference_cannot_cite_neighbor_only_or_duplicate_ids(self):
        validator=Draft202012Validator(bound_difference_schema([1,2,3]))
        for evidence in ([1,4],[1,1],[]):
            with self.subTest(evidence=evidence),self.assertRaises(ValidationError):
                validator.validate({'status':'PASS','note':'Pair comparison','evidence_steps':evidence})
        validator.validate({'status':'PASS','note':'Bound focal comparison','evidence_steps':[1,3]})

    def test_binding_does_not_mutate_shared_schema_between_sample_lengths(self):
        before=deepcopy(REVIEW_SCHEMA)
        bound_review_schema([1,2]);nine=bound_review_schema(list(range(1,10)))
        self.assertEqual(REVIEW_SCHEMA,before)
        Draft202012Validator.check_schema(nine)
        Draft202012Validator(nine).validate(synthetic_review(list(range(1,10))))


if __name__=='__main__':unittest.main()
