"""Batch result accounting and evidence-bound recovery; no external transport."""
from webcollect import workspace_json as json
import re
from pathlib import Path

from .batch_core import load_json, BudgetStop, SessionGLMCallLimit
from .planning import verify_evidence

VERSION = 'candidate-batch-routing'


def batch_ids(pool, producer_batch):
    with pool.pool.connect() as con:
        return {r[0] for r in con.execute("SELECT candidate_id FROM candidate_batch_rows WHERE run_id=? AND result='NEW'", (producer_batch,))}


def report(pool, producer_batch, *, target=0, basis='saved'):
    """Read original saves/quality receipts; projections alone never grant credit."""
    from .candidate_consumer import _original_attempts, verified_saved
    from .site_pool_sync import _snapshot
    from .runtime import _bound_quality_report
    ids = batch_ids(pool, producer_batch)
    with pool.pool.connect() as con:
        claims = [pool._claim(r) for r in con.execute('SELECT * FROM candidate_claims ORDER BY created,rowid') if r['candidate_id'] in ids]
        effective = {r['candidate_id']: dict(r) for r in con.execute('SELECT * FROM candidate_results WHERE effective=1') if r['candidate_id'] in ids}
        dispositions = {cid: pool.disposition(con, cid) for cid in ids}
        states = {r['candidate_id']: r['state'] for r in con.execute('SELECT candidate_id,state FROM data_candidates') if r['candidate_id'] in ids}
    attempts, saved, qualified, published, reviewed, batch_accepted, failed, invalid = set(), set(), set(), set(), set(), set(), set(), []
    quality = []
    for claim in claims:
        for row, _ in _original_attempts(claim):
            attempts.add((claim['binding']['registry'], row['attempt_id']))
        result = effective.get(claim['candidate_id'])
        if not result or result['claim_id'] != claim['claim_id']:
            continue
        try:
            original = verified_saved(claim)
            if not original or original != json.loads(result['record']):
                raise ValueError('Effective result differs from verified original save')
            key = (original['registry'], original['sample_id'])
            saved.add(key)
            task = next(t for t in _snapshot(original['registry'], original['scope_id'])['tasks'] if t['task_key'] == original['task_key'])
            qc = task['qc']
            if qc:
                bound, _ = _bound_quality_report([qc['report']])
                if bound.get('production_quality'):
                    from quality_inspector.production_sampling import quality_report
                    claimed = bound['production_quality']
                    actual = quality_report(bound, claimed['effective_set'], claimed['cross_package_report'], claimed.get('production_handoff'))
                    if actual != claimed:
                        raise ValueError('Batch quality differs from recomputed evidence')
                    rows = [r for r in actual['rows'] if r['sample_id'] == original['sample_id']]
                    status = 'PASS' if rows and rows[0]['quality_admission'] == 'ACCEPTED_BY_BATCH_POLICY' else 'FAIL' if rows and rows[0]['quality_admission'] == 'REJECTED' else 'REVIEW_REQUIRED'
                else:
                    rows = [r for r in bound['samples'] if r['sample_id'] == original['sample_id']]
                    status = rows[0]['status'] if len(rows) == 1 else 'REVIEW_REQUIRED'
                    if status == 'PASS' and bound['status'] != 'PASS': status = 'REVIEW_REQUIRED'
                if len(rows) != 1 or status != qc['status']:
                    raise ValueError('Quality result differs from original bound receipt')
                if qc['status'] == 'PASS' and task['production_status'] in ('reviewed_pass', 'batch_accepted', 'published'):
                    qualified.add(key)
                    (batch_accepted if qc.get('quality_admission') == 'ACCEPTED_BY_BATCH_POLICY' else reviewed).add(key)
                    quality.append({'sample_id': original['sample_id'], 'report': qc['report'], 'status': task['production_status']})
                    if task['production_status'] == 'published':
                        published.add(key)
                elif qc['status'] == 'FAIL':
                    failed.add(key)
        except (ValueError, OSError, KeyError, StopIteration) as error:
            invalid.append({'candidate_id': claim['candidate_id'], 'reason': str(error)})
    counts = {d: sum(bool(v) and v['disposition'] == d and (d != 'recovery_ready' or states[cid] in ('pending','consuming')) for cid,v in dispositions.items())
              for d in ('optimize', 'reprocess', 'abandon', 'reconcile', 'paused', 'recovery_ready')}
    count = len(saved) if basis == 'saved' else len(qualified)
    return {'schema_version': VERSION, 'producer_batch': producer_batch, 'target': target, 'target_basis': basis,
            'inventory': len(ids), 'claimed_candidates': len({c['candidate_id'] for c in claims}),
            'consumption_claims': len(claims), 'formal_attempts': len(attempts),
            'saved_pending_or_reviewed': len(saved), 'pending_review': len(saved - qualified - failed), 'qc_failed':len(failed),
            'independently_reviewed_pass':len(reviewed), 'accepted_by_batch_policy':len(batch_accepted),
            'qualified': len(qualified), 'published': len(published), 'target_count': count,
            'shortfall': max(0, target - count), 'dispositions': counts, 'candidate_dispositions': dispositions,
            'states': {s: sum(v == s for v in states.values()) for s in set(states.values())},
            'invalid_receipts': invalid, 'quality_evidence': quality}


def recover(pool, producer_batch, *, reasons, fix_version, candidate_ids):
    """Explicit finite selection; retry performs the original ledger reconciliation."""
    from .candidate_consumer import retry
    if not fix_version or not reasons or not candidate_ids:
        raise ValueError('Recovery requires reasons, fix version and explicit original candidate set')
    eligible = batch_ids(pool, producer_batch)
    if not set(candidate_ids) <= eligible:
        raise ValueError('Recovery candidates must belong to the specified producer batch')
    results = []
    for cid in sorted(set(candidate_ids)):
        try:
            results.append(retry(pool, cid, reason='targeted repair: ' + ','.join(sorted(reasons)),
                                 recovery={'producer_batch': producer_batch, 'reasons': sorted(set(reasons)),
                                           'fix_version': fix_version, 'candidate_ids': sorted(set(candidate_ids))}))
        except (ValueError, BudgetStop) as error:
            results.append({'candidate_id': cid, 'state': 'paused' if isinstance(error, BudgetStop) else 'held', 'reason': str(error)})
    return {'producer_batch': producer_batch, 'fix_version': fix_version, 'results': results}


def english_quiz_reason(state):
    """Check question and answers independently, using rendered text only."""
    title=(state.get('title') or '').casefold()
    if not any(marker in title for marker in ('测验','试题','答题','题库','quiz')):
        return None
    text=state.get('visible_text') or ''
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    answers=[];first_choice=None
    for i,line in enumerate(lines):
        inline=re.match(r'^[A-D][.、:：)）\s]+(.+)$',line)
        answer=inline.group(1) if inline else lines[i+1] if line in ('A','B','C','D') and i+1<len(lines) else None
        if answer:
            answers.append(answer)
            if first_choice is None:first_choice=i
    def english_majority(value):
        letters=[c for c in value if c.isalpha()]
        return bool(letters) and sum(c.isascii() and c.isalpha() for c in letters)>len(letters)/2
    questions=[line for line in lines[:first_choice] if line.endswith(('?','？'))]
    if not questions and first_choice is not None:
        headings={e.get('text') for e in state.get('elements',[]) if e.get('native_role') in ('h2','h3','h4')}
        questions=[line for line in lines[:first_choice] if line in headings]
    if questions and english_majority(questions[-1]):
        return 'english_quiz_question'
    if len(answers)>=2 and english_majority(' '.join(answers)):
        return 'english_quiz_answers'
    return None


def first_frame_disposition(state):
    """Route direct first-frame facts; this does not certify later frames."""
    from .consumer_page_policy import full_image, boundary, login_entry_exclusion
    if (boundary(state) or {}).get('kind')=='http_403':
        return 'abandon','entry_http_403'
    login = login_entry_exclusion(state)
    if login:
        return 'abandon', login['reason']
    if full_image(state):
        return 'abandon', 'first_frame_image_fills_viewport'
    title = (state.get('title') or '').strip().casefold()
    text = (state.get('visible_text') or '').strip()
    if title in ('404', '404 not found', '页面不存在', '网页不存在') and any(
            phrase in text.casefold() for phrase in ('404', 'not found', '页面不存在', '网页不存在')):
        return 'abandon', 'page_absent'
    if title in ('access denied', '访问受限', '安全验证', '人机验证', '网站暂时无法访问'):
        return 'optimize', 'access_blocked'
    quiz_reason=english_quiz_reason(state)
    if quiz_reason:
        return 'abandon', quiz_reason
    from .page_language import assess
    if assess(state)['excluded']:
        return 'optimize', 'rendered_chinese_not_evidenced'
    # Letter ratios do not establish page/control language consistency.
    # The independent all-frame language review checks that visible relationship.
    return None


def record_outcome(pool, claim, result):
    """Route proved failures after original close-out, without inventing site policy."""
    current = pool.get_claim(claim['claim_id'])
    with pool.pool.connect() as con:
        prior = pool.disposition(con, claim['candidate_id'])
        if prior and (prior['disposition'] != 'recovery_ready' or prior['claim_id'] == claim['claim_id']):
            return
    if result.get('saved') or current['state'] not in ('failed', 'reconcile'):
        return
    binding = current.get('binding') or {}
    refs = [binding['claim_reference']] if binding.get('claim_reference') else []
    if not refs:
        return  # no evidence: original claim remains the reconciliation authority
    kind = 'paused' if result.get('resource_stop') else 'reconcile' if current['state'] == 'reconcile' else 'optimize'
    reason = 'resource_pause' if kind == 'paused' else 'original_account_unresolved' if kind == 'reconcile' else 'consumer_failure'
    if binding.get('output'):
        for terminal_path in sorted(Path(binding['output']).glob('execution/capture/evidence/*/raw/terminal.json')):
            from .batch_core import file_sha
            refs.append({'path':str(terminal_path), 'sha256':file_sha(terminal_path)})
            if kind == 'optimize' and load_json(terminal_path).get('stop_details', {}).get('code') == SessionGLMCallLimit.code:
                reason = SessionGLMCallLimit.code
                break
            for event_path in sorted(terminal_path.parent.glob('*-tool-result.json')):
                event = load_json(event_path)
                if event['result']['status'] in ('rejected','need_observation'):
                    refs.append({'path':str(event_path),'sha256':file_sha(event_path)})
                    if kind == 'optimize': reason = 'tool_evidence_gap'
                    break  # retain the first observed breakpoint
    pool.record_disposition(current, disposition=kind, reason=reason, stage=current['stage'],
                            evidence=refs, policy_version=VERSION)


def reprocess(pool, candidate_id, revision_root, *, reason, fix_version):
    from .candidate_consumer import verified_saved
    from .postprocess import revise
    with pool.pool.connect() as con:
        disposition = pool.disposition(con, candidate_id)
        if not disposition or disposition['disposition'] != 'reprocess':
            raise ValueError('Candidate must be explicitly routed to reprocessing')
        for row in con.execute("SELECT record FROM candidate_events WHERE candidate_id=? AND kind='revision'", (candidate_id,)):
            prior = json.loads(row[0])
            if prior['fix_version'] == fix_version:
                if prior['reason'] != reason: raise ValueError('Revision version already bound to a different reason')
                verify_evidence([prior['receipt']])
                return {**prior, 'repeated': True}
    claim = pool.get_claim(disposition['claim_id'])
    saved = verified_saved(claim)
    if not saved:
        raise ValueError('Complete original saved result required')
    evidence = Path(saved['save_receipt']['path']).parent
    destination = Path(revision_root).absolute()
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError('Revision destination cannot use symlinks')
    if destination.is_relative_to(evidence.parent.parent) or evidence.is_relative_to(destination):
        raise ValueError('Revision must be outside the original dataset')
    manifest = load_json(evidence.parent.parent / 'manifest.json')
    ids = {**saved, 'site_id': saved['sample_id'].split('_sample_')[0], 'batch_id': manifest['batch_id']}
    # The existing local file lock serializes version-idempotence as well as
    # receipt registration. It never locks a browser/model operation.
    from .fixed_cohort import _lock
    with _lock(Path(str(pool.path) + '.revision')):
        with pool.pool.connect() as con:
            for row in con.execute("SELECT record FROM candidate_events WHERE candidate_id=? AND kind='revision'", (candidate_id,)):
                prior = json.loads(row[0])
                if prior['fix_version'] == fix_version:
                    if prior['reason'] != reason: raise ValueError('Revision version already bound to a different reason')
                    verify_evidence([prior['receipt']])
                    return {**prior, 'repeated': True}
        receipt_path = Path(revision_root).absolute() / 'revision.json'
        if receipt_path.is_file():
            from .batch_core import file_sha
            result = load_json(receipt_path)
            if (result['fix_version'] != fix_version or result['reason'] != reason
                    or result['original_save_receipt'] != saved['save_receipt']
                    or result['sample_id'] != saved['sample_id']):
                raise ValueError('Existing revision belongs to a different original or repair')
            for name, digest in result['revision_files_sha256'].items():
                path = receipt_path.parent / name
                if Path(name).is_absolute() or not path.resolve().is_relative_to(receipt_path.parent) or path.is_symlink() or file_sha(path) != digest:
                    raise ValueError('Existing isolated revision changed')
            result['receipt'] = {'path':str(receipt_path),'sha256':file_sha(receipt_path)}
        else:
            result = revise(evidence, revision_root, ids, manifest, reason=reason, fix_version=fix_version)
        event = {'candidate_id': candidate_id, 'claim_id': claim['claim_id'], 'fix_version': fix_version,
                 'reason': reason, 'receipt': result['receipt'], 'status': result['status'],
                 'browser_calls': 0, 'model_calls': 0}
        with pool.transaction() as con:
            pool.event(con, candidate_id, claim['claim_id'], 'revision', event)
        return event


def usage_report(scope, producer_batch):
    """Reuse role accounting and separate explicitly diagnostic requests."""
    from .candidate_accounting import build_report, metering
    from .candidate_monitor import rows
    base = build_report(scope, batches=(producer_batch,))
    requests = rows(scope['consumer_db'], """SELECT m.id,m.job_id,m.state,m.usage,m.error,m.started,m.purpose,
        j.kind,json_extract(j.payload,'$.diagnostic_only') AS diagnostic_only FROM model_requests m LEFT JOIN jobs j ON j.id=m.job_id""")
    linked = {r for c in base['candidates'] for r in c['consumer_result']['request_ids']}
    buckets = {'formal_consumption':[], 'diagnostic':[], 'unattributed':[]}
    for r in requests:
        diagnostic = r['diagnostic_only'] or r['kind'] == 'react-feedback-comparison' or 'diagnostic' in (r['kind'] or '').lower() or 'diagnostic' in r['purpose'].lower()
        buckets['diagnostic' if diagnostic else 'formal_consumption' if r['id'] in linked else 'unattributed'].append(r)
    def measured(items):
        return {**metering(items), 'request_ids':[r['id'] for r in items]}
    base['consumer_request_classes'] = {kind:measured(items) for kind,items in buckets.items()}
    producer_requests = rows(scope['producer_db'], 'SELECT id,job_id,state,usage,error,started FROM model_requests')
    base['producer_project_usage'] = measured(producer_requests)
    base['accounting_note'] = 'Original request token usage; formal consumption, diagnostics and unattributed requests remain separate. Missing usage stays unknown; cache and reasoning are subsets, never added twice.'
    pool = __import__('site_planner.candidate_pool',fromlist=['CandidatePool']).CandidatePool(scope['pool'],readonly=True)
    with pool.pool.connect() as con:
        dispositions = {c['candidate_id']:pool.disposition(con,c['candidate_id']) for c in base['candidates']}
    groups = {}
    formal = {r['id']:r for r in buckets['formal_consumption']}
    for candidate in base['candidates']:
        cid = candidate['candidate_id']; d = dispositions[cid]
        candidate['disposition'] = d
        if not d: continue
        key = d['disposition'] + '/' + d['reason'] + '/' + d['policy_version']
        group = groups.setdefault(key,{'candidate_ids':[], 'requests':{}})
        group['candidate_ids'].append(cid)
        group['requests'].update((rid,formal[rid]) for rid in candidate['consumer_result']['request_ids'] if rid in formal)
    base['disposition_usage'] = {key:{'candidate_ids':g['candidate_ids'], **measured(list(g['requests'].values()))} for key,g in groups.items()}
    return base


def main(argv=None):
    import argparse
    from site_planner.candidate_pool import CandidatePool
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    stats = sub.add_parser('report')
    stats.add_argument('--producer-batch', required=True)
    stats.add_argument('--target', type=int, default=0)
    stats.add_argument('--target-basis', choices=('saved','qualified'), default='saved')
    stats.add_argument('--usage-scope', help='Read original discovery/consumer/diagnostic usage via candidate_accounting')
    repair = sub.add_parser('recover')
    repair.add_argument('--producer-batch', required=True)
    repair.add_argument('--reason', action='append', required=True)
    repair.add_argument('--candidate-id', action='append', required=True)
    repair.add_argument('--fix-version', required=True)
    route = sub.add_parser('disposition')
    route.add_argument('--claim-id', required=True)
    route.add_argument('--kind', choices=('optimize','reprocess','abandon','reconcile','paused'), required=True)
    route.add_argument('--reason', required=True)
    route.add_argument('--stage', required=True)
    route.add_argument('--evidence', required=True, help='JSON array of original path/sha256 references')
    route.add_argument('--policy-version', required=True)
    revision = sub.add_parser('reprocess')
    revision.add_argument('--candidate-id', required=True)
    revision.add_argument('--output', required=True)
    revision.add_argument('--reason', required=True)
    revision.add_argument('--fix-version', required=True)
    a = parser.parse_args(argv)
    pool = CandidatePool(a.pool, readonly=a.command == 'report')
    if a.command == 'report':
        result = report(pool, a.producer_batch, target=a.target, basis=a.target_basis)
        if a.usage_scope:
            result['usage'] = usage_report(load_json(a.usage_scope), a.producer_batch)
    elif a.command == 'recover':
        result = recover(pool, a.producer_batch, reasons=a.reason, fix_version=a.fix_version, candidate_ids=a.candidate_id)
    elif a.command == 'disposition':
        result = pool.record_disposition(pool.get_claim(a.claim_id), disposition=a.kind, reason=a.reason,
            stage=a.stage, evidence=load_json(a.evidence), policy_version=a.policy_version)
    else:
        result = reprocess(pool, a.candidate_id, a.output, reason=a.reason, fix_version=a.fix_version)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
