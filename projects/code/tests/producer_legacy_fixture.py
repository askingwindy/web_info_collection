"""Construct a pre-Table1 frozen job before exercising historical producer tests.

These suites assert the old UNKNOWN publishing and function-routing contracts.
Freeze the original policy without dispatch, then exercise normal recovery. New
batch policy and site evidence are covered by test_application_discovery.
"""
from unittest.mock import patch
from threading import RLock
from site_planner import candidate_discovery as discovery

_produce=discovery.produce_entries
_main=discovery.main
_freeze_lock=RLock()


class _FrozenOnly(Exception):
    pass


def produce_entries(*args, **kwargs):
    # The legacy fixture temporarily replaces module globals. Serialize this
    # fixture wrapper, so competing setup threads cannot restore a stale mock.
    # Actual new-policy publication races are tested without this wrapper.
    with _freeze_lock:
        with patch.object(discovery.site_tables,'POLICY',None), patch.object(discovery,'ModelGateway',side_effect=_FrozenOnly):
            try:
                _produce(*args,**kwargs)
            except _FrozenOnly:
                pass
        return _produce(*args,**kwargs)


def main(argv):
    with patch.object(discovery,'produce_entries',side_effect=produce_entries):
        return _main(argv)
