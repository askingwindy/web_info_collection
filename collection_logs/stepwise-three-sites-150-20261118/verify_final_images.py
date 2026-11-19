import argparse
import asyncio
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.collection_startup import check
from webcollect.planning import verify_evidence
from webcollect.stepwise import finalize, prompt
from webcollect.stepwise.image_capacity import authorize_final_images
from webcollect.stepwise.session import stepwise_caller

from launch_run import before
from select_pages import ROOT, RUN, SCOPE


DIRECTORY = RUN / 'image-repair-20261119' / 'live-validation'
SESSION = 'stepwise-final-images-20261119-tabs'


def material():
    fixture = ROOT / 'verify_results/stepwise-consumer-20261119/final-cli/tabs'
    scope = load_json(fixture / 'scope-reference.json')
    evidence, = fixture.rglob('stepwise/terminal.json')
    terminal = load_json(evidence)
    with closing(sqlite3.connect(Path(scope['consumer_db']).as_uri() + '?mode=ro', uri=True)) as con:
        inputs = {phase: json.loads(body) for phase, body in con.execute("""
            SELECT json_extract(j.payload,'$.phase'),r.request_json FROM model_requests r JOIN jobs j ON j.id=r.job_id
            WHERE json_extract(j.payload,'$.phase') IN ('writeback','judgement') AND r.state='succeeded' ORDER BY r.rowid""")}
    frames = {}
    for phase, count in [('writeback', 2), ('judgement', 3)]:
        refs = inputs[phase]['images']
        verify_evidence(refs)
        frames[phase] = [ref['path'] for ref in refs]
        if len(set(frames[phase])) != count or any(ref['kind'] != 'original_png' or Path(ref['path']).parent != evidence.parent for ref in refs):
            raise ValueError('Fixture must have distinct verified original PNG frames')
    if frames['writeback'] != [frames['judgement'][0], frames['judgement'][-1]]:
        raise ValueError('Start/terminal frames differ between phases')
    actions = re.findall(r'^\d+\. (\{.*\})$', inputs['writeback']['text'], re.MULTILINE)
    if terminal['mode'] != 'autonomous' or terminal['stop_reason'] != 'complete_success' or len(actions) != terminal['effective_steps']:
        raise ValueError('Complete fixture actions required')
    return terminal, frames, actions, load_json(Path(frames['writeback'][-1]).with_suffix('.json'))


async def exercise(ledger, terminal, frames, actions, final_state, outcome):
    call = stepwise_caller(ledger, {'task_id': SESSION, 'site_uri': final_state['url']}, SESSION)
    deadline = time.monotonic() + 600
    correction, prior = [], None
    for number in (1, 2):
        response = await call(phase='writeback', system='你是采集回写器。只依据所给材料输出 submit_writeback，不添加新信息。',
            tools=prompt.writeback_tools(), user_text=prompt.writeback_message(mode='autonomous', requested_goal_text=None,
                initial_task_goal=terminal['initial_goal'], task_goal=terminal['task_goal'], actions_summary=actions, site_tasks=[],
                correction_problems=correction, previous_writeback=prior),
            images=frames['writeback'], reasoning_effort='high', dispatch_deadline=deadline, request_deadline=deadline,
            round_index=number, tool_name='submit_writeback')
        prior = response['arguments']
        save_json(DIRECTORY / f'writeback-{number}.json', response)
        try:
            checked = finalize.validate_writeback(prior, mode='autonomous', app_name='fixture.example.org')
            correction = finalize.writeback_citations_check(checked, final_state)
        except finalize.FinalizationRejected as error:
            correction = [str(error)]
        if not correction:
            outcome['writeback_valid'] = True
            break
    else:
        raise ValueError('Two writeback mechanical checks failed')
    response = await call(phase='judgement', system='你是独立复核者。只依据截图与动作记录输出 submit_judgement。',
        tools=prompt.judgement_tools(), user_text=prompt.judgement_message(task_instruction=checked['model_instruction'],
            actions_summary=actions, final_result=checked['final_result'], completion_judgement=checked['completion_judgement']),
        images=frames['judgement'], reasoning_effort='high', dispatch_deadline=deadline, request_deadline=deadline,
        round_index=number + 1, tool_name='submit_judgement')
    save_json(DIRECTORY / 'judgement.json', response)
    judgement = finalize.validate_judgement(response['arguments'])
    outcome.update(judgement_valid=True, fixture_semantic_pass=finalize.judgement_passed(judgement))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorize-new-stepwise-images', action='store_true', required=True)
    parser.parse_args()
    terminal, frames, actions, final_state = material()
    DIRECTORY.mkdir(exist_ok=False)
    scope = load_json(SCOPE)
    baseline = before(scope)
    save_json(DIRECTORY / 'protected-before.json', baseline)
    ledger = BatchLedger(scope['consumer_db'], load_json(scope['consumer_config']))
    outcome = {'started': datetime.now().astimezone().isoformat(), 'session_id': SESSION, 'model': ledger.config['model']['model'],
               'material': 'saved local tabs fixture; new verification session; not a production claim', 'status': 'FAILED'}
    try:
        decision = authorize_final_images(ledger, '2026-11-19 用户授权按策略3规则本地修复并重新采集；新作业决策1张、回写2张、判定最多3张原图。')
        outcome['authorization'] = decision
        outcome['frozen_max_images'] = ledger.config['model']['max_images']
        validation = check(SCOPE, launch_role='consumer')
        save_json(DIRECTORY / 'preflight.json', validation)
        if validation['status'] != 'PASS':
            raise ValueError('Production consumer preflight did not pass')
        asyncio.run(exercise(ledger, terminal, frames, actions, final_state, outcome))
        outcome['status'] = 'PASS'
    except Exception as error:
        outcome['error'] = {'type': type(error).__name__, 'reason': str(error)[:350]}
    finally:
        with ledger.connect() as con:
            physical = [dict(row) for row in con.execute("""
                SELECT r.id AS request_id,r.state,json_extract(j.payload,'$.phase') AS phase,
                  json_extract(r.request_json,'$.image_count') AS images,json_extract(r.request_json,'$.stage_max_images') AS stage_limit,
                  json_extract(r.usage,'$.input_tokens') AS input_tokens,json_extract(r.usage,'$.output_tokens') AS output_tokens
                FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE json_extract(j.payload,'$.attempt_id')=?
                ORDER BY r.rowid""", (SESSION,))]
        outcome['physical_requests'] = physical
        if not all(any(row['phase'] == phase and row['images'] == count and row['state'] == 'succeeded' for row in physical)
                   for phase, count in [('writeback', 2), ('judgement', 3)]):
            outcome['status'] = 'FAILED'
        after = before(scope)
        outcome['prior_claims_attempts_and_unsettled_unchanged'] = (
            all(after[key] == baseline[key] for key in ('prior_claims', 'prior_attempts')) and
            all(after[role]['unsettled'] == baseline[role]['unsettled'] for role in ('consumer_db', 'producer_db')))
        if not outcome['prior_claims_attempts_and_unsettled_unchanged']:
            outcome['status'] = 'FAILED'
        outcome['finished'] = datetime.now().astimezone().isoformat()
        save_json(DIRECTORY / 'receipt.json', outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=2), flush=True)
    return 0 if outcome['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
