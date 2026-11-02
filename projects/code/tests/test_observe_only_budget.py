"""Historical ceilings, idempotent metering, and independent dispatch guards."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json, validate_config
from webcollect.model_gateway import ModelGateway

CONFIG = Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'
USAGE = {'input_tokens': 50, 'output_tokens': 10, 'cached_input_tokens': 0}


class ObserveOnlyBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.serial = 0

    def config(self, observe=True):
        value = load_json(CONFIG)
        value['budget'].update(max_model_requests=3, max_reserved_tokens=1000,
                               max_model_cost_micros=None if observe else 140,
                               currency='CONTROLLED_TEST_UNITS', max_concurrent_jobs=1)
        if observe:
            value['budget']['cost_control'] = 'observe_only'
        value['model'].update(reserve_input_tokens=100, max_completion_tokens=20, max_images=2,
                              timeout_seconds=1, reserve_cost_micros=140)
        value['model']['rates'] = {'version': 'TEST-NOT-PRICES', 'source': 'Controlled arithmetic fixture',
                                   'input': 1000000, 'cached_input': 500000, 'output': 2000000}
        return value

    def ledger(self, config=None):
        self.serial += 1
        ledger = BatchLedger(self.root / f'CONTROLLED-{self.serial}.sqlite3', config or self.config(), initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'controlled': True}))
        return ledger, job

    def settle(self, ledger, job, purpose):
        request = ledger.reserve_request(job, purpose, 0)
        ledger.settle_request(request['id'], state='succeeded', usage=USAGE, response={'result': {}})
        return request

    def test_legacy_representation_and_absent_or_null_ceilings(self):
        legacy = load_json(CONFIG)
        self.assertEqual(validate_config(legacy), legacy)
        self.assertNotIn('cost_control', validate_config(legacy)['budget'])
        for mode, amount in ((None, None), ('capped', None), ('observe_only', 0), ('observe_only', 140)):
            config = self.config()
            if mode is None: config['budget'].pop('cost_control')
            else: config['budget']['cost_control'] = mode
            config['budget']['max_model_cost_micros'] = amount
            with self.subTest(mode=mode, amount=amount): self.assertEqual(validate_config(config), config)
        config['budget']['cost_control']='invalid'
        with self.assertRaises(ValueError): validate_config(config)
        example = load_json(CONFIG.parent / 'batch-real.example.json')
        with self.assertRaises(ValueError): validate_config(example)
        example['budget']['cost_control'] = 'observe_only'
        with self.assertRaises(ValueError): validate_config(example)

    def test_real_observe_mode_still_requires_model_rates_currency_and_reservation(self):
        config = self.config()
        config['mode'] = 'real'; config['budget']['min_model_interval_seconds'] = 1
        config['model'].update(provider='chat-completions', endpoint='https://provider.invalid/chat/completions',
                               api_key_env='UNREAD_CONTROLLED_KEY', model='explicit-controlled-model')
        self.assertEqual(validate_config(config), config)
        for field in ('model', 'rates', 'currency', 'reservation'):
            changed = deepcopy(config)
            if field == 'model': changed['model']['model'] = None
            elif field == 'rates': changed['model']['rates']['input'] = 0
            elif field == 'currency': changed['budget']['currency'] = ''
            else: changed['model']['reserve_cost_micros'] = 0
            with self.subTest(field=field), self.assertRaises(ValueError): validate_config(changed)

    def test_amount_and_requests_continue_above_old_caps(self):
        ledger, job = self.ledger()
        for number in range(3): self.settle(ledger, job, f'purpose-{number}')
        summary = ledger.summary()
        self.assertEqual(summary['known_model_cost_micros'], 210)
        self.assertEqual(summary['model_cost_micros'], 210)
        self.assertEqual(summary['cost_control'], 'observe_only')
        self.assertEqual(summary['max_model_cost_micros'], 'NOT_APPLICABLE')
        self.assertFalse(summary['monetary_limit_applied'])
        self.settle(ledger, job, 'fourth')
        self.assertEqual(ledger.summary()['known_model_cost_micros'], 280)

    def test_default_and_explicit_historical_capped_configs_meter_actual_cost(self):
        for explicit in (False, True):
            config = self.config(False)
            if explicit: config['budget']['cost_control'] = 'capped'
            ledger, job = self.ledger(config); self.settle(ledger, job, 'one')
            with self.subTest(explicit=explicit):
                for n in ('two','three'): self.settle(ledger,job,n)
                self.assertEqual(ledger.summary()['known_model_cost_micros'],210)
                self.assertFalse(ledger.summary()['monetary_limit_applied'])

    def test_unknown_reservation_is_retained_and_same_identity_is_never_resent(self):
        ledger, job = self.ledger(); request = ledger.reserve_request(job, 'ambiguous', 0)
        ledger.settle_request(request['id'], state='unknown', error='TimeoutError')
        with self.assertRaises(OutcomeUnknown): ledger.reserve_request(job, 'ambiguous', 0)
        self.assertEqual(ledger.summary()['model_requests'], 1)
        self.assertEqual(ledger.summary()['model_cost_micros'], 'UNKNOWN')
        self.assertEqual(ledger.summary()['uncertain_reserved_cost_micros'], 140)
        ledger.reserve_request(job, 'different-independent-request', 0)
        self.assertEqual(ledger.summary()['uncertain_reserved_cost_micros'], 280)

    def test_old_token_and_time_limits_do_not_stop_jobs(self):
        config = self.config(); config['budget']['max_reserved_tokens'] = 120
        ledger, job = self.ledger(config); self.settle(ledger, job, 'one')
        self.assertEqual(ledger.reserve_request(job, 'two', 0)['state'], 'new')
        config = self.config(); config['budget']['max_run_seconds'] = 1
        ledger, job = self.ledger(config)
        self.assertEqual(ledger.reserve_request(job, 'after-window', 0)['state'], 'new')
        for field in ('max_model_requests', 'max_reserved_tokens', 'max_run_seconds'):
            config = self.config(); config['budget'][field] = None
            with self.subTest(field=field): self.assertEqual(validate_config(config),config)

    def test_only_monetary_overreservation_is_not_a_token_stop_in_observe_mode(self):
        for observe in (True, False):
            config = self.config(observe)
            if not observe: config['budget']['max_model_cost_micros'] = 10000
            ledger, job = self.ledger(config); request = self.settle(ledger, job, 'one')
            # Deliberately inconsistent cost fixture isolates the monetary guard;
            # no provider response or bill is claimed by this local test.
            with ledger.connect() as con:
                con.execute('UPDATE model_requests SET cost=500 WHERE id=?', (request['id'],)); con.commit()
            self.assertEqual(ledger.summary()['cost_reservation_exceeded_requests'], 1)
            self.assertEqual(ledger.summary()['known_model_cost_micros'], 500)
            self.assertEqual(ledger.reserve_request(job, 'two', 0)['state'], 'new')

    def test_token_overreservation_is_reported_and_next_request_can_dispatch(self):
        ledger, job = self.ledger(); request = ledger.reserve_request(job, 'one', 0)
        ledger.settle_request(request['id'], state='invalid_response', usage={**USAGE, 'input_tokens': 101}, error='SchemaMismatch')
        with ledger.connect() as con:
            actual = con.execute('SELECT state,error FROM model_requests WHERE id=?',(request['id'],)).fetchone()
        self.assertEqual(tuple(actual),('invalid_response','SchemaMismatch'))
        self.assertEqual(ledger.summary()['token_reservation_exceeded_requests'], 1)
        self.assertEqual(ledger.reserve_request(job, 'two', 0)['state'], 'new')

    def test_image_job_limits_and_old_ledger_configuration_remain_frozen(self):
        ledger, job = self.ledger()
        with self.assertRaisesRegex(ValueError, 'Image limit'):
            ModelGateway(ledger).call(job, 'images', 'JSON', {'type': 'object'}, images=[self.root / 'missing.png'] * 3)
        self.assertEqual(ledger.summary()['model_requests'], 0)
        with self.assertRaisesRegex(BudgetStop, 'max_concurrent_jobs'):
            ledger.claim('test', job_id=ledger.enqueue('test', {'second': True}))
        capped, _ = self.ledger(self.config(False)); before = hashlib.sha256(capped.path.read_bytes()).hexdigest()
        changed = self.config(False); changed['budget'].update(cost_control='observe_only', max_model_cost_micros=None)
        with self.assertRaisesRegex(ValueError, 'frozen'): BatchLedger(capped.path, changed)
        self.assertEqual(before, hashlib.sha256(capped.path.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
