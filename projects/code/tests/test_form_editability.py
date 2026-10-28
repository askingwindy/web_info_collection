"""An observed readonly output cannot be counted as a necessary input."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from test_s0_task_generation import capability
from webcollect.task_generation import compile_form, deterministic_specs


class FormEditability(unittest.TestCase):
    def test_readonly_or_disabled_inputs_are_not_compiled(self):
        with tempfile.TemporaryDirectory() as name:
            record = capability(Path(name))
            specs = deterministic_specs(record)
            self.assertTrue(specs)
            for key in ('editable', 'enabled'):
                changed = deepcopy(record)
                changed['capabilities'][0]['forms'][0]['fields'][0][key] = False
                with self.assertRaisesRegex(ValueError, 'Unsupported/unobserved'):
                    compile_form(changed, specs['tasks'][0])

    def test_disabled_submit_is_not_compiled(self):
        with tempfile.TemporaryDirectory() as name:
            record = capability(Path(name)); specs = deterministic_specs(record)
            record['capabilities'][0]['forms'][0]['fields'][-1]['enabled'] = False
            with self.assertRaisesRegex(ValueError, 'Submit target'):
                compile_form(record, specs['tasks'][0])
