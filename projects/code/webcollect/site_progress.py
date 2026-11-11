"""Logical-site progress backed by the existing production runtime.

This sidecar owns targets, task-position assignments and immutable QC references.
It never allocates production IDs, changes a capture outcome, signs a review or
adds campaign budget. SQLite remains authoritative for every task and attempt.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlsplit

from .planning import canonical, object_sha256, verify_evidence

VERSION = 'site-progress'
LEGACY_VERSION = 'webcollect-site-progress-1'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ref(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('An existing absolute nonsymlink file is required')
    return {'path': str(path.resolve()), 'sha256': _sha(path)}


def _nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be nonempty')
    return value


def _state_hash(value):
    return object_sha256({k: v for k, v in value.items() if k != 'state_sha256'})


def _recheck_final_report(report, human_reference=None):
    """Recompute a claimed final PASS, rather than trusting edited report labels.

    This reads existing evidence only and never requests a model or signs a
    human record. Reviewer identity and actual reading remain unauthenticated.
    """
    from quality_inspector.engine import inspect
    profile = report.get('local_profile', {})
    reference = _ref(profile.get('path', ''))
    if reference['sha256'] != profile.get('sha256'):
        raise ValueError('Final report profile binding differs')
    sampling = report.get('semantic_sampling', {})
    plan = sampling.get('plan')
    if plan:
        verify_evidence([plan])
    human_paths = {row.get('human_source', {}).get('path') for row in sampling.get('rows', [])
                   if isinstance(row.get('human_source'), dict)} - {None}
    if human_reference:
        human_paths.add(human_reference['path'])
    ai_failures = sampling.get('ai_failure_sources', [])
    if ai_failures:
        verify_evidence(ai_failures)
    try:
        actual = inspect(dataset=report['dataset'], profile=reference['path'],
            reviews=report.get('review_import', {}).get('source'), inspection_stage='final',
            delivery_sampling_plan=plan['path'] if plan else None,
            human_reviews=sorted(human_paths) or None,
            ai_failures=[row['path'] for row in ai_failures] or None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('Claimed final PASS cannot be independently rechecked: ' + str(error)) from error
    if (actual.get('delivery_status') != 'PASS' or actual.get('release_ready') is not True
            or actual.get('input_integrity', {}).get('status') != 'PASS'
            or any(row.get('status') != 'PASS' for row in actual.get('samples', []))
            or {row['sample_id'] for row in actual.get('samples', [])}
               != {row['sample_id'] for row in report['samples']}):
        raise ValueError('Claimed final PASS does not reproduce under the actual current inspector')
    return {'status': 'PASS', 'contract_sha256': actual['baseline']['config_sha256'],
            'profile': reference, 'model_requests': 0, 'human_identity_authenticated': False}


class SiteProgress:
    """A resumable logical-site view of one existing production campaign.

    ``site_id`` here is a planning identity and may cover several observed URIs.
    Actual production site/sample IDs are read unchanged from the original DB.
    """
    def __init__(self, registry, state_path):
        self.registry = Path(registry).resolve()
        self.path = Path(state_path).absolute()
        if self.path.is_symlink() or self.path == self.registry:
            raise ValueError('Progress state must not replace the production registry')

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.registry.as_uri() + '?mode=ro', uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + '.lock')
        if lock.is_symlink():
            raise ValueError('Progress lock cannot be a symlink')
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _read(self):
        if self.path.is_symlink():
            raise ValueError('Progress state cannot be a symlink')
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if (state.get('schema_version') not in (VERSION, LEGACY_VERSION) or state.get('registry') != str(self.registry)
                or state.get('state_sha256') != _state_hash(state)):
            raise ValueError('Progress state integrity or registry identity differs')
        previous = state['spec_sha256']
        if previous != object_sha256(state['spec']):
            raise ValueError('Frozen progress specification differs')
        for number, event in enumerate(state['events'], 1):
            if (event.get('sequence') != number or event.get('previous_sha256') != previous
                    or event.get('event_sha256') != object_sha256(
                        {k: v for k, v in event.items() if k != 'event_sha256'})):
                raise ValueError('Progress event history integrity differs')
            previous = event['event_sha256']
        return state

    def _write(self, state):
        state['state_sha256'] = _state_hash(state)
        descriptor, name = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(canonical(state) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    @staticmethod
    def _event(state, kind, payload, request_id):
        _nonempty(request_id, 'request_id')
        for old in state['events']:
            if old['request_id'] == request_id:
                if (old['kind'], old['payload']) != (kind, payload):
                    raise ValueError('An idempotency key already binds a different progress event')
                return False
        event = {'sequence': len(state['events']) + 1, 'kind': kind, 'payload': deepcopy(payload),
                 'request_id': request_id, 'created_at': _now(),
                 'previous_sha256': state['events'][-1]['event_sha256'] if state['events'] else state['spec_sha256']}
        event['event_sha256'] = object_sha256(event)
        state['events'].append(event)
        return True

    def initialize(self, campaign_id, sites, *, max_attempts_per_slot=3):
        _nonempty(campaign_id, 'campaign_id')
        if type(max_attempts_per_slot) is not int or max_attempts_per_slot < 1:
            raise ValueError('max_attempts_per_slot must be a positive integer')
        if not isinstance(sites, list) or not sites:
            raise ValueError('A nonempty logical site target list is required')
        normalized = []
        seen = set()
        for row in sites:
            sid = _nonempty(row.get('site_id'), 'site_id')
            if sid in seen:
                raise ValueError('Repeated logical site_id')
            seen.add(sid)
            target = row.get('target_count', 20)
            if type(target) is not int or target < 1:
                raise ValueError('target_count must be a positive integer')
            uris = row.get('allowed_uris')
            if not isinstance(uris, list) or not uris or len(set(uris)) != len(uris):
                raise ValueError('Each site needs distinct observed allowed_uris')
            for uri in uris:
                parsed = urlsplit(uri)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError('Site URIs must be public HTTP(S) identities without credentials')
            normalized.append({'site_id': sid, 'app_name': _nonempty(row.get('app_name'), 'app_name'),
                               'target_count': target, 'allowed_uris': sorted(uris)})
        spec = {'campaign_id': campaign_id, 'sites': sorted(normalized, key=lambda r: r['site_id']),
                'max_attempts_per_slot': max_attempts_per_slot}
        with self._connect() as con:
            if not con.execute('SELECT 1 FROM m4_campaigns WHERE campaign_id=?', (campaign_id,)).fetchone():
                raise ValueError('Use an existing initialized production campaign; this module cannot create budget')
        with self._locked():
            if self.path.exists():
                state = self._read()
                if state['spec'] != spec:
                    raise ValueError('Cannot replace frozen site targets or campaign')
                return self._snapshot(state)
            state = {'schema_version': VERSION, 'registry': str(self.registry), 'spec': spec,
                     'spec_sha256': object_sha256(spec), 'created_at': _now(), 'events': []}
            self._write(state)
            return self._snapshot(state)

    def _task_binding(self, con, state, scope_id, assignment):
        sid = _nonempty(assignment.get('site_id'), 'site_id')
        sites = {row['site_id']: row for row in state['spec']['sites']}
        if sid not in sites:
            raise ValueError('Unknown logical site_id')
        task_id = _nonempty(assignment.get('task_id'), 'task_id')
        version = _nonempty(assignment.get('task_version'), 'task_version')
        row = con.execute('SELECT * FROM m4_tasks WHERE campaign_id=? AND scope_id=? AND task_id=? AND task_version=?',
                          (state['spec']['campaign_id'], scope_id, task_id, version)).fetchone()
        if not row:
            raise ValueError('Task must already exist in the same production campaign and scope')
        task = json.loads(row['task_json'])
        if task['site_uri'] not in sites[sid]['allowed_uris']:
            raise ValueError('Task URI is outside the logical site observed scope')
        if object_sha256(task) != row['task_sha256']:
            raise ValueError('Production task bytes differ from its registered identity')
        return {'site_id': sid, 'slot_id': _nonempty(assignment.get('slot_id'), 'slot_id'),
                'task_key': row['task_key'], 'task_id': task_id, 'task_version': version,
                'task_sha256': row['task_sha256'], 'scope_id': scope_id, 'site_uri': task['site_uri']}

    @staticmethod
    def _slots(state):
        slots = {}
        for event in state['events']:
            if event['kind'] == 'tasks_registered':
                for binding in event['payload']['bindings']:
                    slots[binding['slot_id']] = {'site_id': binding['site_id'], 'bindings': [binding]}
            elif event['kind'] == 'replacement_bound':
                binding = event['payload']['binding']
                slots[binding['slot_id']]['bindings'].append(binding)
        return slots

    def register_tasks(self, scope_id, assignments, *, request_id):
        if not isinstance(assignments, list) or not assignments:
            raise ValueError('Nonempty task-position assignments are required')
        with self._locked():
            state = self._read()
            self._validate(state)
            with self._connect() as con:
                bindings = [self._task_binding(con, state, scope_id, row) for row in assignments]
            if len({b['slot_id'] for b in bindings}) != len(bindings) or len({b['task_key'] for b in bindings}) != len(bindings):
                raise ValueError('Repeated task or task position')
            payload = {'bindings': sorted(bindings, key=lambda b: b['slot_id'])}
            if any(e['request_id'] == request_id for e in state['events']):
                self._event(state, 'tasks_registered', payload, request_id)
                return self._snapshot(state)
            slots = self._slots(state)
            known = {b['task_key'] for slot in slots.values() for b in slot['bindings']}
            if any(b['slot_id'] in slots or b['task_key'] in known for b in bindings):
                raise ValueError('Position/task is already bound; replacements need explicit linkage')
            for site in state['spec']['sites']:
                count = sum(slot['site_id'] == site['site_id'] for slot in slots.values())
                count += sum(b['site_id'] == site['site_id'] for b in bindings)
                if count > site['target_count']:
                    raise ValueError('Registered positions exceed the frozen logical site target')
            self._event(state, 'tasks_registered', payload, request_id)
            self._write(state)
            return self._snapshot(state)

    def _validate(self, state):
        with self._connect() as con:
            if not con.execute('SELECT 1 FROM m4_campaigns WHERE campaign_id=?', (state['spec']['campaign_id'],)).fetchone():
                raise ValueError('Original production campaign is missing')
            for slot in self._slots(state).values():
                for binding in slot['bindings']:
                    actual = self._task_binding(con, state, binding['scope_id'], binding)
                    if actual != binding:
                        raise ValueError('Frozen task assignment differs from original production registry')
        for event in state['events']:
            if event['kind'] == 'qc_imported':
                self._load_qc(event['payload']['report'], event['payload'].get('human_reviews'))

    @staticmethod
    def _load_qc(reference, human_reference=None):
        verify_evidence([reference] + ([human_reference] if human_reference else []))
        from .client_reports import _bound_report
        value = json.loads(Path(reference['path']).read_text())
        report, _ = _bound_report(Path(value['dataset']).resolve(), Path(reference['path']))
        records = {}
        sources = [human_reference] if human_reference else []
        if not human_reference:
            for row in report.get('semantic_sampling', {}).get('rows', []):
                source = row.get('human_source')
                if isinstance(source, dict) and source not in sources:
                    sources.append(source)
        for source in sources:
            verify_evidence([source])
            from quality_inspector.reviews import intake
            current, errors, _ = intake(source['path'], report['samples'], report['baseline']['config_sha256'])
            if errors or any(row['reviewer']['kind'] != 'human' for row in current.values()):
                raise ValueError('Only current evidence-bound explicit human reviews can close replacement problems: ' + str(errors))
            for sid, row in current.items():
                if sid in records and records[sid] != row:
                    raise ValueError('Conflicting human records need explicit resolution')
                records[sid] = row
            verify_evidence([source])
        verify_evidence([reference] + ([human_reference] if human_reference else []))
        return report, records

    @staticmethod
    def _human_status(record):
        if not record:
            return 'NOT_SUPPLIED'
        statuses = {row['status'] for row in record['checks'].values()}
        return 'FAIL' if 'FAIL' in statuses else 'PASS' if statuses == {'PASS'} else 'REVIEW_REQUIRED'

    def import_qc(self, report_path, *, human_reviews=None, request_id):
        reference = _ref(report_path)
        human_reference = _ref(human_reviews) if human_reviews else None
        report, records = self._load_qc(reference, human_reference)
        recheck = None
        if report.get('inspection_stage') == 'final' and report.get('release_ready') is True:
            recheck = _recheck_final_report(report, human_reference)
        dataset = Path(report['dataset']).resolve()
        if self.path == dataset or self.path.is_relative_to(dataset):
            raise ValueError('Progress state must remain outside the immutable customer dataset')
        with self._locked():
            state = self._read()
            self._validate(state)
            slots = self._slot_rows(state)
            known = {row['sample_id']: row for row in slots if row['sample_id']}
            rows = []
            for item in report['samples']:
                sid = item['sample_id']
                if sid not in known:
                    continue
                row = known[sid]
                human = self._human_status(records.get(sid))
                sampling = item.get('semantic_sampling', {})
                if not sampling:
                    sampling = next((r for r in report.get('semantic_sampling', {}).get('rows', [])
                                     if r.get('sample_id') == sid), {})
                # A later PASS cannot erase a human rejection of these same bytes.
                if row['human_rejected'] and (item.get('status') == 'PASS' or human == 'PASS'):
                    raise ValueError('A human-rejected sample needs a new capture identity, not a revised PASS')
                if row['replacement'] and item.get('status') == 'PASS' and human != 'PASS':
                    raise ValueError('Replacement requires explicit current human PASS')
                accepted = (report.get('inspection_stage') == 'final' and report.get('release_ready') is True
                            and report.get('delivery_status') == 'PASS' and item.get('status') == 'PASS'
                            and (not row['replacement'] or human == 'PASS'))
                rows.append({'slot_id': row['slot_id'], 'sample_id': sid, 'sample_status': item.get('status'),
                             'human_status': human, 'final_policy_accepted': accepted,
                             'sampling_status': sampling.get('status', 'LEGACY_REVIEW'),
                             'annotation_sha256': item['annotation_sha256'],
                             'evidence_sha256': item['evidence_sha256']})
            if not rows:
                raise ValueError('QC report contains no current successfully captured task positions')
            payload = {'report': reference, 'human_reviews': human_reference,
                       'rows': sorted(rows, key=lambda r: r['slot_id']),
                       'inspection_stage': report.get('inspection_stage'),
                       'independent_final_recheck': recheck,
                       'contract_sha256': report['baseline']['config_sha256']}
            if self._event(state, 'qc_imported', payload, request_id):
                self._write(state)
            return self._snapshot(state)

    def bind_replacement(self, slot_id, scope_id, assignment, *, replaces_sample_id, request_id):
        with self._locked():
            state = self._read()
            self._validate(state)
            rows = {row['slot_id']: row for row in self._slot_rows(state)}
            if slot_id not in rows:
                raise ValueError('Unknown replacement task position')
            current = rows[slot_id]
            existing = [e for e in state['events'] if e['request_id'] == request_id]
            if not existing and (current['sample_id'] != replaces_sample_id or not current['human_rejected']):
                raise ValueError('Replacement must bind the current explicit human-rejected sample')
            if not existing and current['attempted'] >= state['spec']['max_attempts_per_slot']:
                raise ValueError('Task-position attempt limit reached; keep the deficit pending')
            assignment = {**assignment, 'slot_id': slot_id, 'site_id': current['site_id']}
            with self._connect() as con:
                binding = self._task_binding(con, state, scope_id, assignment)
            payload = {'binding': binding, 'replaces_sample_id': replaces_sample_id,
                       'mandatory_human_recheck': True}
            if existing:
                self._event(state, 'replacement_bound', payload, request_id)
                return self._snapshot(state)
            previous = self._slots(state)[slot_id]['bindings']
            if binding['scope_id'] == previous[-1]['scope_id']:
                raise ValueError('A replacement version needs a new immutable output scope')
            if not existing and any(binding['task_key'] == b['task_key'] for slot in self._slots(state).values() for b in slot['bindings']):
                raise ValueError('Replacement cannot reuse a registered task/version')
            if self._event(state, 'replacement_bound', payload, request_id):
                self._write(state)
            return self._snapshot(state)

    def _slot_rows(self, state):
        slots = self._slots(state)
        qc = {}
        rejected = set()
        for event in state['events']:
            if event['kind'] == 'qc_imported':
                for row in event['payload']['rows']:
                    qc[row['sample_id']] = row
                    if row['human_status'] == 'FAIL':
                        rejected.add(row['sample_id'])
        with self._connect() as con:
            rows = []
            for slot_id, slot in sorted(slots.items()):
                bindings = slot['bindings']
                attempts = []
                for binding in bindings:
                    attempts += [dict(r) for r in con.execute('SELECT * FROM m4_attempts WHERE task_key=? ORDER BY created_at,rowid', (binding['task_key'],))]
                current = [a for a in attempts if a['task_key'] == bindings[-1]['task_key']]
                successful = [a for a in current if a['status'] == 'collected_pending_review']
                if len(successful) > 1:
                    raise ValueError('More than one committed success for a task/version')
                sample = successful[0] if successful else None
                if sample:
                    proof = json.loads(sample['evidence_json'])
                    if not proof:
                        raise ValueError('Committed capture has no actual saved evidence')
                    verify_evidence(proof)
                    allocation = con.execute('SELECT site_id,batch_id FROM allocations WHERE sample_id=?',
                                             (sample['sample_id'],)).fetchone()
                    if allocation is None or tuple(allocation) != (sample['site_id'], sample['batch_id']):
                        raise ValueError('Captured sample identity differs from original production allocation')
                sid = sample['sample_id'] if sample else None
                decision = qc.get(sid, {})
                published = False
                if sid and decision.get('final_policy_accepted'):
                    for release in con.execute('SELECT sample_ids_json FROM m4_publications WHERE campaign_id=?', (state['spec']['campaign_id'],)):
                        published = published or sid in json.loads(release[0])
                rows.append({'slot_id': slot_id, 'site_id': slot['site_id'], 'binding': bindings[-1],
                             'replacement': len(bindings) > 1, 'sample_id': sid,
                             'attempted': sum(a['started_at'] is not None for a in attempts),
                             'failed_attempts': sum(a['status'] in ('rejected', 'interrupted') for a in attempts),
                             'inflight': any(a['status'] in ('reserved', 'running') for a in current),
                             'captured': bool(sample), 'sample_checked': bool(decision),
                             'sample_status': decision.get('sample_status', 'NOT_CHECKED'),
                             'human_status': decision.get('human_status', 'NOT_SUPPLIED'),
                             'sampling_status': decision.get('sampling_status', 'NOT_CHECKED'),
                             'human_rejected': sid in rejected,
                             'final_policy_accepted': bool(decision.get('final_policy_accepted')) and sid not in rejected,
                             'released': published and sid not in rejected,
                             'attempt_ids': [a['attempt_id'] for a in attempts]})
        return rows

    def _snapshot(self, state):
        self._validate(state)
        rows = self._slot_rows(state)
        by_site = {}
        for site in state['spec']['sites']:
            selected = [row for row in rows if row['site_id'] == site['site_id']]
            accepted = sum(row['final_policy_accepted'] for row in selected)
            by_site[site['site_id']] = {'target_count': site['target_count'], 'planned': len(selected),
                'attempted': sum(row['attempted'] for row in selected),
                'failed_attempts': sum(row['failed_attempts'] for row in selected),
                'inflight': sum(row['inflight'] for row in selected),
                'captured_pending': sum(row['captured'] and not row['sample_checked'] for row in selected),
                'sample_checked': sum(row['sample_checked'] for row in selected),
                'sample_pass': sum(row['sample_status'] == 'PASS' and not row['human_rejected'] for row in selected),
                'not_selected': sum(row['sampling_status'] == 'NOT_SELECTED' for row in selected),
                'final_policy_accepted': accepted, 'released': sum(row['released'] for row in selected),
                'replacement_positions': sum(row['replacement'] for row in selected),
                'human_pending': sum((row['replacement'] and row['captured'] and row['human_status'] not in ('PASS', 'FAIL'))
                                     or row['sampling_status'] == 'HUMAN_REQUIRED' for row in selected),
                'remaining_gap': site['target_count'] - accepted}
        requests = []
        for row in rows:
            if row['human_rejected']:
                requests.append({'slot_id': row['slot_id'], 'site_id': row['site_id'],
                    'replaces_sample_id': row['sample_id'], 'previous_binding': row['binding'],
                    'mandatory_human_recheck': True,
                    'status': 'ATTEMPT_LIMIT_REACHED' if row['attempted'] >= state['spec']['max_attempts_per_slot'] else 'REPLAN_OR_RECOLLECT',
                    'next_action': 'Use the same production campaign, explicit available budget and a new task/version/output scope; never rewrite the rejected capture.'})
        return {'schema_version': VERSION + '-snapshot', 'campaign_id': state['spec']['campaign_id'],
                'state_sha256': state['state_sha256'], 'by_site': by_site,
                'target_count': sum(r['target_count'] for r in by_site.values()),
                'final_policy_accepted': sum(r['final_policy_accepted'] for r in by_site.values()),
                'remaining_gap': sum(r['remaining_gap'] for r in by_site.values()),
                'replacement_requests': requests, 'slots': rows,
                'production_identity_source': str(self.registry), 'allocates_production_ids': False,
                'reviewer_identity_authenticated': False, 'customer_acceptance': 'UNKNOWN'}

    def snapshot(self):
        with self._locked():
            return self._snapshot(self._read())

    def sync(self):
        """Read live production facts; no outcome is copied back into SQLite."""
        return self.snapshot()

    def replacement_requests(self):
        return self.snapshot()['replacement_requests']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--state', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('--spec', required=True)
    register = sub.add_parser('register'); register.add_argument('--scope', required=True)
    register.add_argument('--assignments', required=True); register.add_argument('--request-id', required=True)
    qc = sub.add_parser('import-qc'); qc.add_argument('--report', required=True)
    qc.add_argument('--human-reviews'); qc.add_argument('--request-id', required=True)
    replacement = sub.add_parser('replace'); replacement.add_argument('--slot', required=True)
    replacement.add_argument('--scope', required=True); replacement.add_argument('--assignment', required=True)
    replacement.add_argument('--replaces-sample-id', required=True); replacement.add_argument('--request-id', required=True)
    sub.add_parser('status'); sub.add_parser('replacement-requests')
    args = parser.parse_args(argv)
    progress = SiteProgress(args.registry, args.state)
    load = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    if args.command == 'init':
        spec = load(args.spec)
        result = progress.initialize(spec['campaign_id'], spec['sites'], max_attempts_per_slot=spec.get('max_attempts_per_slot', 3))
    elif args.command == 'register':
        result = progress.register_tasks(args.scope, load(args.assignments), request_id=args.request_id)
    elif args.command == 'import-qc':
        result = progress.import_qc(args.report, human_reviews=args.human_reviews, request_id=args.request_id)
    elif args.command == 'replace':
        result = progress.bind_replacement(args.slot, args.scope, load(args.assignment),
            replaces_sample_id=args.replaces_sample_id, request_id=args.request_id)
    else:
        result = progress.snapshot() if args.command == 'status' else progress.replacement_requests()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
