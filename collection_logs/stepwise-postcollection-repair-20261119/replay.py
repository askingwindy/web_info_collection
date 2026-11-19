"""从只读原账和原始帧重放最后 33 页的协议、状态变化与引用驳回。"""
import argparse
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from jsonschema import Draft202012Validator

from webcollect.stepwise import finalize, observation, prompt


def read(path):
    return json.loads(path.read_text())


def query(database, statement, params=()):
    with closing(sqlite3.connect(Path(database).as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(statement, params)]


def replay(root):
    archive = root / 'collection_logs/stepwise-three-sites-150-20261118'
    chosen = {p['candidate_id'] for p in read(archive/'run-04-selection.json')['pages']}
    plans = {}
    for segment in ('run-04', 'run-05'):
        plan = read(root/'results'/archive.name/segment/'prepared-plan.json')
        plans.update({p['worker_id']:plan['plan_id'] for p in plan['workers']})
    scope = read(root/'database/sqllite/prod/scope.json')
    claims = {c['claim_id']:c for c in query(scope['pool'], 'SELECT candidate_id,claim_id,worker_id FROM candidate_claims')
              if c['candidate_id'] in chosen and c['worker_id'] in plans}
    attempts = query(scope['registry'], """SELECT a.attempt_id,a.sample_id,a.status,
        json_extract(t.task_json,'$.candidate_binding.claim_id') AS claim_id
        FROM m4_tasks t JOIN m4_attempts a USING(task_key)""")
    evidence = {}
    changed = Counter()
    cite = Counter()
    hotkeys = Counter()
    cited_pages = set()
    for a in attempts:
        c = claims.get(a['claim_id'])
        if c is None:
            continue
        raw = Path(scope['output'])/plans[c['worker_id']]/c['worker_id']/c['claim_id']/'execution/capture/evidence'/a['sample_id']/'stepwise'
        evidence[a['attempt_id']] = raw
        for path in raw.glob('decision-rejection-*.json'):
            rejection = read(path)
            decision = read(raw/('decision-%03d.json' % rejection['round']))
            reason = rejection['reason'].partition(':')[0]
            if any(decision[k+'_before'] != decision[k+'_after'] for k in ('task_goal','note')):
                changed[reason] += 1
            args = decision['arguments']
            if args.get('action') == 'hotkey' and reason in ('HOTKEY_KEYS_NOT_ALLOWED','UNEXPECTED_ACTION_FIELDS'):
                frame = read(raw/('observation-'+rejection['frame_id'][1:]+'.json'))
                try:
                    operation, _ = observation.bind_action(frame, observation.actionable_rows(frame), args)
                    observation.require_action(frame, operation)
                except (ValueError, observation.ActionRejected):
                    hotkeys['still_rejected'] += 1
                else:
                    hotkeys['fully_valid'] += 1
                    if 'element' in args:
                        hotkeys['matching_focus_number'] += 1
            if reason != 'CURRENT_FRAME_CITATION':
                continue
            cited_pages.add(c['candidate_id'])
            state = read(raw/('observation-'+rejection['frame_id'][1:]+'.json'))
            fields = set(re.findall(r'(\w+) 引文「',rejection['reason']))
            problems = finalize.missing_quotes([(k,decision['arguments'][k]) for k in fields],state,'本帧')
            cite['still_unsupported' if problems else 'now_grounded'] += 1
    rows = query(scope['consumer_db'], """SELECT r.id,json_extract(r.request_json,'$.images[0].path') AS image,
        r.response,json_extract(j.payload,'$.attempt_id') AS attempt_id,json_extract(j.payload,'$.phase') AS phase
        FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE r.state='invalid_response'
        AND json_extract(j.payload,'$.attempt_id') IN (""" + ','.join('?' for _ in evidence) + ')',list(evidence))
    fields = Counter()
    host_names = []
    for row in rows:
        response = json.loads(row['response'])
        errors = response['failure_diagnostic']['schema_errors']
        paths = [e['field_path'][0] for e in errors]
        fields[row['phase']+'/'+','.join(paths)] += 1
        if paths != ['page_name']:
            continue
        img = Path(row['image'])
        assert img.parent == evidence[row['attempt_id']] and img.name.endswith('.numbered.png')
        state = read(img.with_suffix('').with_suffix('.json'))
        args = json.loads(response['provider_response']['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        name = prompt.frame_page_name(state)
        assert name and len(name) <= prompt.LIMIT_PAGE_NAME
        assert not finalize.missing_quotes([('page_name',name)], state, '本帧')
        assert Draft202012Validator(prompt.next_action_schema()).is_valid(args) is False
        Draft202012Validator(prompt.next_action_schema(frame_name=name)).validate(args)
        host_names.append({'attempt_id':row['attempt_id'], 'request_id':row['id'], 'frame':img.stem})
    return {'claimed':len(claims),'attempts':len(evidence),'invalid_responses':len(rows),
            'schema_errors_by_phase_fields':dict(fields),'title_responses_replayed':len(host_names),
            'title_affected_attempts':len({r['attempt_id'] for r in host_names}), 'title_receipts':host_names,
            'historic_rejected_decisions_changing_goal_or_note':dict(changed),
            'historical_hotkey_rejections_replayed':dict(hotkeys),
            'citation_rejections_by_latest_frame_check':dict(cite),'citation_affected_pages':len(cited_pages),
            'new_production_claims':0,'new_model_requests':0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    result = replay(Path(__file__).resolve().parents[2])
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
