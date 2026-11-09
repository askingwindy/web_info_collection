"""Effective dispatch ceiling and downstream schema compatibility."""
import unittest
from unittest.mock import AsyncMock, Mock, patch

from webcollect.closing_policy import EFFECTIVE_VERSION, VERSION
from webcollect.react_session import ReactSession
from quality_inspector.format_checks import ANNOTATION, Strict
import test_semantic_reuse as semantic_reuse_fixture


class FiveTenDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_tenth_effective_step_stops_next_primitive_without_dispatch(self):
        session = object.__new__(ReactSession)
        session.task = {'fragment': {'ending_policy': EFFECTIVE_VERSION}}
        session.trajectory = [{}] * 10
        session.business_attempt_refs = [{}] * 14
        session.plan_controller = None
        session._perform_primitive = AsyncMock()
        session._range_close = Mock()
        session._ok = Mock()
        session.stop_summary = 'ten effective steps'
        session.collection_ending = {}
        await session._execute_primitive({}, {}, {}, {}, {}, None, None, [], [])
        session._perform_primitive.assert_not_awaited()
        self.assertEqual(session._range_close.call_args.args[0], 'TEN_EFFECTIVE_STEP_LIMIT')

    async def test_attempt_count_does_not_consume_effective_allowance(self):
        for policy, effective in [(EFFECTIVE_VERSION, 9), (VERSION, 13)]:
            session = object.__new__(ReactSession)
            session.task = {'fragment': {'ending_policy': policy}}
            session.trajectory = [{}] * effective
            session.business_attempt_refs = [{}] * 15
            session.plan_controller = None
            session.actual_dispatches = 15
            session.state = 'recording'
            session._perform_primitive = AsyncMock(return_value='performed')
            session._record_business_attempt = Mock()
            result = await session._execute_primitive({'goal': 'read', 'expected': 'new passage'}, {},
                {'action_type': 'scroll'}, {}, {}, None, None, [], [])
            session._perform_primitive.assert_awaited_once()
            self.assertEqual(result, 'performed')

    def test_qc_recognizes_new_ending_and_preserves_old_versions(self):
        schema = ANNOTATION['properties']['steps']['items']['properties']['tool_result']['properties']['return_value']['properties']['collection_ending']
        for version in (VERSION, EFFECTIVE_VERSION):
            self.assertEqual(list(Strict(schema).iter_errors({'protocol': version})), [])


class FiveTenSemanticReuseTests(unittest.TestCase):
    setUp = semantic_reuse_fixture.SemanticReuseTests.setUp
    prepare_run = semantic_reuse_fixture.SemanticReuseTests.prepare_run

    def test_only_terminal_rule_is_invalidated(self):
        from quality_inspector import semantic
        with patch.dict(semantic.RULE_VERSIONS, {'terminal_semantics': 'truthful-fragment-continuous-ending-7'}):
            before = self.prepare_run('v4')
        after = self.prepare_run('v5')
        self.assertEqual(self.calls[-1][1]['properties']['checks']['required'], ['terminal_semantics'])
        current = self.ledger.get(after['jobs'][0]['visual_job'])
        for name in ('visual_alignment', 'language', 'privacy'):
            self.assertEqual(current['result']['semantic_check_sources'][name], before['jobs'][0]['visual_job'])
