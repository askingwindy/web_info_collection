"""Read the two fixed consumer cases and verify their original producer evidence."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from contextlib import closing

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / folder) for folder in
                ('projects/code', 'projects/site-planner', 'projects/quality-inspector')]

from webcollect.agent_feedback import reference
from webcollect.batch_core import load_json
from webcollect.candidate_cohort import ReadOnlyLedger, verify_get
from webcollect.goal_evidence import validate_contract
from webcollect.session_objective import bind


def require(match, message):
    if not match:
        raise ValueError(message)


def original_ref(record):
    actual = reference(ROOT / record['path'])
    require(actual['sha256'] == record['sha256'], f"Changed evidence: {record['path']}")
    return actual


def verify_case(path):
    case = load_json(path)
    cid, version, producer = case['candidate_id'], case['version'], case['producer']
    scope = load_json(original_ref(producer['scope'])['path'])
    with closing(sqlite3.connect(Path(scope['pool']).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('''SELECT c.application_id, v.body FROM candidate_versions v
            JOIN data_candidates c USING (candidate_id) WHERE v.candidate_id=? AND v.version=?''',
                         (cid, version)).fetchone()
        publication = producer['publication']
        published = db.execute('''SELECT run_id,row_id,result,response_sha256 FROM candidate_batch_rows
            WHERE candidate_id=? AND row_id=?''', (cid, publication['row_id'])).fetchone()
        src = db.execute('SELECT source FROM candidate_sources WHERE candidate_id=? AND source_key=?',
                         (cid, producer['source_key'])).fetchone()
    require(row and src and published, f"Missing original producer rows for {cid} v{version}")
    require(dict(published) == publication and published['result'] == 'NEW', 'Publication mismatch')
    body = json.loads(row['body'])
    require(body == producer['body'] and row['application_id'] == producer['application_id']
            and hashlib.sha256(row['body'].encode()).hexdigest() == producer['body_sha256'],
            'Table2 version, body or application mismatch')
    source = json.loads(src['source'])
    require((source['category_hint'], source['page_type']) == (producer['category'], producer['page_type']),
            'Producer classification mismatch')
    require((source.get('entry_source') or source['page_evidence']['reference'])
            == original_ref(producer['source_evidence']), 'Page source mismatch')
    receipt = producer['entry_get']
    require(source['entry_http'] == original_ref(receipt), 'Original GET reference mismatch')
    ledger = ReadOnlyLedger(scope['producer_db'], load_json(scope['producer_config']))
    access = verify_get(ledger, body['entry_url'], source['entry_http'])
    require((access['http_status'], access['job_id']) == (receipt['http_status'], receipt['job_id']),
            'Original GET status or job mismatch')
    goal = bind(reference(path), {'candidate_id':cid, 'version':version, 'snapshot':body})['objective']
    validate_contract(goal['evidence_contract'])
    return {'case':path.stem, 'candidate_id':cid, 'version':version, 'original_get':access['http_status'],
            'goal':goal['kind'], 'body_sha256':producer['body_sha256']}


if __name__ == '__main__':
    cases = ROOT / 'request/consumer-baselines'
    rows = [verify_case(cases / name) for name in ('muxtly-square-footage.json', 'zh-wikipedia-reading.json')]
    require(len({r['candidate_id'] for r in rows}) == 2 and [r['goal'] for r in rows] == ['calculation','reading'],
            'Expected separate action and reading baselines')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
