"""从正式漏斗已归属的 HTTP 请求核验两项补修、各阶段图数和运行事件。"""
import json
from collections import Counter, defaultdict

from validate import ARCHIVE, RUN, campaign
from progress import read, records, select, write


def main():
    account = read(ARCHIVE / 'accounting.json')
    scope = read(campaign.SCOPE)
    request_pages = {}
    for page in account['pages']:
        for phase in ('decision', 'writeback', 'judgement'):
            for rid in page['phases'].get(phase + '_http', []):
                assert rid not in request_pages
                request_pages[rid] = (page, phase)
    baseline = read(RUN / 'before.json')['consumer_db']['last_request_rowid']
    rows = select(scope['consumer_db'], """
        SELECT id, state, json_extract(request_json,'$.image_count') images,
          instr(json_extract(request_json,'$.text'),'[当前值为空；占位示例未填入]')>0 empty_shown,
          instr(json_extract(request_json,'$.text'),'[当前输入值：')>0 value_shown,
          json_extract(request_json,'$.field_repair.allowed_paths') paths,
          json_extract(request_json,'$.field_repair.source_request_id') source,
          json_extract(response,'$.result.argument_repair.base_arguments') original_args,
          json_extract(response,'$.result.argument_repair.validated_arguments') final_args,
          json_extract(response,'$.provider_error.http_status') http_status,
          json_extract(response,'$.provider_error.provider_code') provider_code
        FROM model_requests WHERE rowid>? ORDER BY rowid""", (baseline,))
    images = defaultdict(Counter)
    inputs = defaultdict(lambda: {'empty': [], 'filled': []})
    repairs, provider_errors = [], []
    for row in rows:
        if row['id'] not in request_pages:
            continue
        page, phase = request_pages[row['id']]
        images[phase][row['images']] += 1
        if phase == 'decision':
            for marker, key in [('empty_shown', 'empty'), ('value_shown', 'filled')]:
                if row[marker]:
                    inputs[page['site']][key].append(page['candidate_id'])
        if row['paths']:
            paths = json.loads(row['paths'])
            result = dict(candidate_id=page['candidate_id'], site=page['site'], phase=phase,
                          request_id=row['id'], source_request_id=row['source'],
                          source_is_same_page_and_phase=request_pages.get(row['source']) == (page, phase),
                          allowed_paths=paths, state=row['state'])
            if paths == [['status']] and row['original_args'] and row['final_args']:
                original, final = json.loads(row['original_args']), json.loads(row['final_args'])
                status = final.pop('status', None)
                result.update(original_action=original.get('action'), supplied_status=status,
                              only_missing_status_changed=('status' not in original and original == final))
            repairs.append(result)
        if row['http_status']:
            provider_errors.append(dict(candidate_id=page['candidate_id'], request_id=row['id'],
                                        http_status=row['http_status'], provider_code=row['provider_code']))
    assert sum(sum(counts.values()) for counts in images.values()) == len(request_pages) == account['usage']['dispatch']['dispatched']
    input_counts = {site: {key: {'requests': len(ids), 'pages': len(set(ids))} for key, ids in group.items()}
                    for site, group in inputs.items()}
    summaries = []
    for directory in sorted(RUN.glob('run-??')):
        summary = read(directory / 'summary.json')
        observations = list(records(directory / 'worker-observations.jsonl'))
        summaries.append({'start': read(directory / 'controller-start.json'),
                          'elapsed_seconds': summary['elapsed_seconds'],
                          'unlaunched': summary['unlaunched'], 'startup_probes': len(read(directory / 'startup-probes.json')['probes']),
                          'worker_concurrency': [{k: r[k] for k in ('at', 'live', 'peak')} for r in observations]})
    events = account['failure_events']
    write(ARCHIVE / 'observations.json', dict(segments=summaries, phase_image_counts=images,
          current_value_markers=input_counts, field_repairs=repairs, provider_errors=provider_errors,
          sqlite_lock_retries=dict(Counter(r['sqlite_operation'] for r in events if r['reason'] == 'database is locked')),
          core_tests=(ARCHIVE.parents[1] / 'verify_results' / ARCHIVE.name / 'core.log').read_text().splitlines()[-1]))
    timeline = []
    for point in records(RUN / 'timeline.jsonl'):
        by_site = point['per_site']
        timeline.append(dict(at=point['at'], claimed=sum(x['claimed'] for x in by_site.values()),
                             formal=sum(x['formal'] for x in by_site.values()),
                             saved={site: x['saved'] for site, x in by_site.items()},
                             request_states=point['new_request_states']))
    write(ARCHIVE / 'timeline.json', timeline)


if __name__ == '__main__':
    main()
