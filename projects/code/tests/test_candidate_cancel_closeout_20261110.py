"""Cancellation closes only local proven facts with the original owner fence."""
from contextlib import contextmanager
import pytest
from webcollect import candidate_consumer as consumer


class Pool:
    def __init__(self, stage='claimed', fenced=True):
        self.current = {'claim_id':'claim', 'candidate_id':'candidate', 'state':'consuming', 'stage':stage}
        self.fenced = fenced
        self.finishes = []

    def get_claim(self, identity):
        return dict(self.current)

    @contextmanager
    def transaction(self):
        yield None

    def _fence(self, con, claim):
        if not self.fenced:raise ValueError('lost lease')

    def finish(self, claim, **kwargs):
        self._fence(None, claim)
        self.finishes.append(kwargs)
        self.current.update(state=kwargs['state'])


def test_claimed_cancel_before_dispatch_fails_without_replay(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(consumer, 'finish_or_reconcile', lambda *a: {'saved':False})
    monkeypatch.setattr(consumer, '_original_attempts', lambda *a: [])
    result = consumer.settle_cancelled_claim(pool, pool.current)
    assert result['state'] == 'failed'
    assert pool.finishes[0]['stage'] == 'claimed'


def test_execution_cancel_without_complete_save_preserves_reconcile(monkeypatch):
    pool = Pool('save_reconciliation')
    monkeypatch.setattr(consumer, 'finish_or_reconcile', lambda *a: {'saved':False})
    result = consumer.settle_cancelled_claim(pool, pool.current)
    assert result['state'] == 'reconcile'
    assert 'no resend' in pool.finishes[0]['reason']


def test_committed_save_reuses_normal_receipt_path(monkeypatch):
    pool = Pool('execution')
    monkeypatch.setattr(consumer, 'finish_or_reconcile', lambda *a: {'saved':True, 'state':'succeeded'})
    assert consumer.settle_cancelled_claim(pool, pool.current)['saved']
    assert not pool.finishes


def test_lost_lease_does_not_reconcile_or_finish(monkeypatch):
    pool = Pool(fenced=False)
    def forbidden(*args):raise AssertionError('Receipt commit must remain fenced')
    monkeypatch.setattr(consumer, 'finish_or_reconcile', forbidden)
    with pytest.raises(ValueError, match='lost lease'):
        consumer.settle_cancelled_claim(pool, pool.current)
    assert not pool.finishes


def test_already_settled_cancel_is_noop(monkeypatch):
    pool = Pool();pool.current['state'] = 'reconcile'
    def forbidden(*args):raise AssertionError('No duplicate closeout')
    monkeypatch.setattr(consumer, 'finish_or_reconcile', forbidden)
    assert consumer.settle_cancelled_claim(pool, pool.current)['state'] == 'reconcile'
    assert not pool.finishes
