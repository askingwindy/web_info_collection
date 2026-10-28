import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from webcollect import observed_workflow as workflow


class EmptyReviewSchemaTest(unittest.TestCase):
    def test_empty_current_comparison_set_has_valid_strict_schema(self):
        packet = {'mode': 'real', 'trace': {'path': 'trace'},
                  'history_context': {'comparisons': []}, 'task': {},
                  'created_at': 0, 'capability': {'expires_at': 3600},
                  'producer_context_id': 'producer'}
        with patch.object(workflow, '_read', side_effect=lambda ref: ref['path']), \
                patch.object(workflow, 'load_json', side_effect=[packet, {'transitions': []}]):
            schema = workflow.review_schema({'path': 'packet', 'sha256': 'test'})
        Draft202012Validator.check_schema(schema)
        comparisons = schema['properties']['history_comparisons']
        self.assertNotIn('prefixItems', comparisons)
        self.assertTrue(Draft202012Validator(comparisons).is_valid([]))
        self.assertFalse(Draft202012Validator(comparisons).is_valid([{}]))


if __name__ == '__main__':
    unittest.main()
