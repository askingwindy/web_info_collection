"""Export selected all-frame evidence for session review, without model dispatch."""
import argparse
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3

from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.planning import object_sha256
from .ai_worker import compact_trajectory, prepare as worker_prepare
from .reporting import review_template
from .sampling import verify_plan, _destinations, _protected


def _export(ledger, plan_path, output, job):
    plan = verify_plan(load_json(plan_path))
    output = Path(output).resolve()
    _destinations([output, ledger.path], _protected(plan['dataset'],
        plan['effective_set']['path'] if plan.get('effective_set') else None,
        plan['calibration']['path'] if plan.get('calibration') else None))
    if plan.get('expansion', {}).get('stop'):
        raise ValueError('Sampling stop condition active; evidence remains on the stopped plan')
    before_requests = ledger.summary()['model_requests']
    selected = {row['sample_id'] for row in plan['rows'] if row['selected']}
    queued = worker_prepare(ledger, plan['dataset'], output / 'queue',
        effective_set=plan['effective_set']['path'] if plan.get('effective_set') else None,
        sample_ids=selected, sampling_binding={'path': str(Path(plan_path).resolve()), 'sha256': object_sha256(plan)})
    queue = load_json(queued['queue_file']); packets = []; samples = []

    def trajectory(bound):
        context, images = compact_trajectory(bound)
        return {'snapshot': bound, 'trajectory': context,
                'original_frames': [{'step_id': step['step_id'], 'path': str(path), 'sha256': file_sha(path)}
                                    for step, path in zip(context['steps'], images)]}

    for item in queue['jobs']:
        ledger.heartbeat(job)
        payload = ledger.get(item['difference_job'])['payload']
        bound = payload['candidate']
        packets.append({'sample_id': item['sample_id'], 'focal': trajectory(bound),
                        'neighbors': [trajectory(other) for other in payload['neighbors']],
                        'comparison_version': payload['comparison_version']})
        samples.append({'sample_id': item['sample_id'], 'annotation_sha256': bound['annotation_sha256'],
                        'evidence_sha256': bound['evidence_sha256']})
    if {item['sample_id'] for item in packets} != selected:
        raise ValueError('Selected evidence no longer fully available; freeze sampling again')
    verify_plan(plan)
    value = {'schema_version': 'webcollect-session-review-packet-1',
             'plan': {'path': str(Path(plan_path).resolve()), 'sha256': plan['plan_sha256']},
             'implementation_sha256': file_sha(__file__), 'packets': packets,
             'original_denominator': plan['original_denominator'], 'selected_count': len(packets),
             'actual_review_created': False, 'release_ready': False,
             'instruction': 'Inspect every original frame and necessary nearest-task comparisons. Record actual reviewer identity, session provenance, frames_viewed and observations in the blank template; no judgment is prefilled.'}
    template = review_template({'scope': 'delivery', 'baseline': {'config_sha256': plan['contract_sha256']}, 'samples': samples})
    save_json(output / 'packet.json', value)
    save_json(output / 'review-template.json', template)
    after_requests = ledger.summary()['model_requests']
    if after_requests != before_requests:
        raise ValueError('Unexpected model dispatch during evidence export')
    return {'packet_file': str(output / 'packet.json'), 'review_template': str(output / 'review-template.json'),
            'queue_file': queued['queue_file'], 'selected_samples': len(packets),
            'original_denominator': plan['original_denominator'], 'new_model_requests': after_requests - before_requests,
            'actual_reviews_created': 0, 'release_ready': False}


def export(ledger, plan_path, output):
    plan = verify_plan(load_json(plan_path))
    jid = ledger.enqueue('qc-session-packet', {'plan_sha256': plan['plan_sha256'],
        'implementation_sha256': file_sha(__file__), 'output': str(Path(output).resolve())})
    prior = ledger.get(jid)
    if prior['state'] == 'done':
        for path, digest in prior['result']['artifacts_sha256'].items():
            if file_sha(path) != digest:
                raise ValueError('Session packet artifact changed')
        return prior['result']
    job = ledger.claim('qc-session-packet', job_id=jid)
    if not job:
        raise ValueError('Session packet export already leased or requires recovery')
    try:
        result = _export(ledger, plan_path, output, job)
        result['artifacts_sha256'] = {result[key]: file_sha(result[key])
                                     for key in ('packet_file', 'review_template', 'queue_file')}
        ledger.finish(job, result=result)
        return result
    except Exception as error:
        ledger.finish(job, 'review_required', error=type(error).__name__)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'ledger', 'plan', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = export(BatchLedger(args.ledger, load_json(args.config)), args.plan, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
