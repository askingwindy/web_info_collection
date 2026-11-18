"""Append-only operational measurements; never a source of sample approval.

Network events retain hostnames and status/error codes only. They deliberately
omit URL paths, queries, headers, cookies, request/response bodies and credentials.
"""
from collections import Counter
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from webcollect import workspace_json as json
from pathlib import Path
import re
import os
import time
from urllib.parse import urlsplit
import uuid


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def append_event(path, event):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({'recorded_at': utc_now(), **event}, ensure_ascii=False, allow_nan=False) + '\n'
    # One append syscall prevents normal process termination from losing buffered
    # Python records. fsync is reserved for phase boundaries, not page scheduling.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        data = line.encode('utf-8')
        if os.write(fd, data) != len(data):
            raise OSError('Incomplete telemetry append')
        if event.get('event') != 'network':
            os.fsync(fd)
    finally:
        os.close(fd)


def start_phase(path, phase, *, scope=None):
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError('Phase needs a nonempty name')
    phase_id = str(uuid.uuid4())
    append_event(path, {'event': 'phase_started', 'phase_id': phase_id, 'phase': phase,
                        'scope': scope or {}, 'usage': 'UNKNOWN', 'cost': 'UNKNOWN'})
    return phase_id


def finish_phase(path, phase_id, *, outcome='completed', usage=None, usage_source=None):
    path = Path(path)
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    starts = [row for row in events if row.get('phase_id') == phase_id and row.get('event') == 'phase_started']
    if len(starts) != 1 or any(row.get('phase_id') == phase_id and row.get('event') == 'phase_finished' for row in events):
        raise ValueError('Phase must have one start and no prior finish; do not overwrite timing')
    if usage is not None and (not isinstance(usage, dict) or not isinstance(usage_source, str) or not usage_source.strip()):
        raise ValueError('Measured usage needs a source; unavailable billing remains UNKNOWN')
    start = datetime.fromisoformat(starts[0]['recorded_at'])
    append_event(path, {'event': 'phase_finished', 'phase_id': phase_id,
        'phase': starts[0]['phase'], 'scope': starts[0]['scope'], 'outcome': outcome,
        'elapsed_seconds': (datetime.now(timezone.utc) - start).total_seconds(),
        'usage': usage if usage is not None else 'UNKNOWN', 'usage_source': usage_source,
        'cost': 'UNKNOWN', 'timing_kind': 'wall_clock_not_active_human_attention'})


@contextmanager
def phase(path, name, *, scope=None):
    phase_id = start_phase(path, name, scope=scope)
    try:
        yield phase_id
    except BaseException as error:
        finish_phase(path, phase_id, outcome=type(error).__name__)
        raise
    else:
        finish_phase(path, phase_id)


@asynccontextmanager
async def worker_measurement(store, worker_id, output):
    store.worker_session(worker_id, output)
    ledger = Path(output) / 'metering' / 'phases.jsonl'
    phase_id = start_phase(ledger, 'collector_worker', scope={'worker_id': worker_id})
    outcome = 'completed'
    try:
        yield
    except BaseException as error:
        outcome = type(error).__name__
        raise
    finally:
        store.worker_session(worker_id, output, finished=True)
        finish_phase(ledger, phase_id, outcome=outcome)


class NetworkMeter:
    def __init__(self, context, directory, identity):
        self.context = context
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events = self.directory / 'network.jsonl'
        self.identity = identity
        self.counts = Counter()
        self.statuses = Counter()
        self.hosts = Counter()
        self.errors = Counter()
        self.measurement_error = None
        self.started = utc_now()
        self.monotonic_start = time.monotonic()
        self.listeners = [('request', self.request), ('response', self.response),
                          ('requestfailed', self.failed)]
        for event, callback in self.listeners:
            context.on(event, callback)
        append_event(self.events, {'event': 'meter_started', **identity,
            'retained_fields': ['host', 'event_type', 'status', 'transport_error_code'],
            'requests_are_not_actions': True})

    def record(self, kind, url, *, status=None, failure=None):
        try:
            host = (urlsplit(url).hostname or '').lower()
        except (TypeError, ValueError):
            host = 'UNKNOWN'
        host = host or 'NO_HOST'
        self.counts[kind] += 1
        if kind == 'request':
            self.hosts[host] += 1
        if status is not None:
            self.statuses[str(status)] += 1
        if failure is not None:
            match = re.search(r'net::ERR_[A-Z_]+', failure)
            failure = match.group() if match else 'TRANSPORT_ERROR'
            self.errors[failure] += 1
        try:
            append_event(self.events, {'event': 'network', **self.identity,
                'event_type': kind, 'host': host, 'status': status, 'transport_error_code': failure})
        except (OSError, ValueError) as error:
            # Playwright callbacks do not propagate reliably to the collector.
            # Remember loss and stop at the explicit collection/teardown boundary.
            self.measurement_error = type(error).__name__

    def ensure_recorded(self):
        if self.measurement_error:
            raise ValueError('网络计量记录失败，停止并保留现场：' + self.measurement_error)

    def request(self, request):
        self.record('request', request.url)

    def response(self, response):
        self.record('response', response.url, status=response.status)

    def failed(self, request):
        self.record('requestfailed', request.url, failure=request.failure or 'TRANSPORT_ERROR')

    def close(self, outcome):
        from .storage import write_json
        for event, callback in self.listeners:
            self.context.remove_listener(event, callback)
        summary = {'schema_version': 'webcollect-network-meter-1', **self.identity,
            'started_at': self.started, 'finished_at': utc_now(),
            'elapsed_seconds': time.monotonic() - self.monotonic_start,
            'counts': dict(self.counts), 'response_statuses': dict(self.statuses),
            'request_hosts': dict(self.hosts), 'transport_errors': dict(self.errors),
            'outcome_at_runner_exit': outcome, 'model_usage': 'UNKNOWN', 'model_cost': 'UNKNOWN',
            'measurement_status': 'FAIL' if self.measurement_error else 'PASS',
            'measurement_error': self.measurement_error,
            'limit': 'Counts include context teardown; aborted requests are not automatically website failures. Missing finish after process death is incomplete measurement, not zero usage.'}
        append_event(self.events, {'event': 'meter_finished', **self.identity, 'outcome': outcome})
        write_json(self.directory / 'network-summary.json', summary)
        return summary


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    start.add_argument('--ledger', type=Path, required=True)
    start.add_argument('--phase', required=True)
    start.add_argument('--scope', default='operator')
    end = sub.add_parser('finish')
    end.add_argument('--ledger', type=Path, required=True)
    end.add_argument('--phase-id', required=True)
    end.add_argument('--outcome', default='completed')
    args = parser.parse_args(argv)
    if args.command == 'start':
        print(json.dumps({'phase_id': start_phase(args.ledger, args.phase, scope={'name': args.scope})}))
    else:
        finish_phase(args.ledger, args.phase_id, outcome=args.outcome)
        print(json.dumps({'status': 'recorded', 'cost': 'UNKNOWN'}))


if __name__ == '__main__':
    main()


@contextmanager
def preparation_phase(path, name):
    """Best-effort monotonic timing; never change collection decisions or fail it."""
    started = time.monotonic()
    outcome = 'completed'
    try:
        yield
    except BaseException as error:
        outcome = type(error).__name__
        raise
    finally:
        # Outside capture/: its initial emptiness is part of bootstrap validation.
        try:
            line = json.dumps({'recorded_at': utc_now(), 'event': 'preparation_finished',
                'phase': name, 'elapsed_seconds': time.monotonic() - started,
                'outcome': outcome, 'usage': 'UNKNOWN', 'cost': 'UNKNOWN'}) + '\n'
            with Path(path).open('a', encoding='utf-8') as stream:
                stream.write(line)
        except OSError:
            pass
