"""Read-only original 404 evidence -> isolated, network-forbidden cross-batch replay."""
import argparse
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from webcollect.batch_core import BatchLedger, load_json, save_json, file_sha
from site_planner.entry_access import check_entry
from webcollect.planning import verify_evidence


def replay(original, output):
    output=Path(output).absolute();output.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(Path(original).absolute().as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        rows=[dict(r) for r in con.execute("SELECT * FROM jobs WHERE kind='candidate-entry-http' AND "
            "(json_extract(payload,'$.batch') LIKE '%rule-08' OR json_extract(payload,'$.batch') LIKE '%topup-08')")]
    batches={name:{} for name in ('rule-08','topup-08')}
    for row in rows:
        payload=json.loads(row['payload'])
        if row['state']!='done':continue
        ref=json.loads(row['result']);verify_evidence([ref]);receipt=load_json(ref['path'])
        if receipt['http_status']==404:
            name=next(n for n in batches if payload['batch'].endswith(n))
            batches[name][payload['uri']]={'job':row,'reference':ref}
    assert len(batches['rule-08'])==8 and batches['rule-08'].keys()==batches['topup-08'].keys()
    hashes={i['reference']['path']:file_sha(i['reference']['path']) for b in batches.values() for i in b.values()}
    config={'schema_version':'webcollect-batch-config-1','run_id':'read-only-original-replay','mode':'synthetic','model':None,
        'budget':{'max_concurrent_jobs':1,'min_domain_interval_seconds':1,'lease_seconds':30,'max_job_attempts':1}}
    ledger=BatchLedger(output/'isolated.sqlite3',config,initialize=True)
    with ledger.transaction() as con:
        for item in batches['rule-08'].values():
            row=item['job'];columns=list(row)
            con.execute('INSERT INTO jobs('+','.join(columns)+') VALUES('+','.join('?' for c in columns)+')',tuple(row[c] for c in columns))
    outcomes=[]
    with patch('socket.create_connection',side_effect=AssertionError('network forbidden')),patch('site_planner.entry_access.fetch_status',side_effect=AssertionError('GET forbidden')) as fetch:
        for iteration in range(2):
            for uri,item in batches['rule-08'].items():
                record,ref=check_entry(BatchLedger(ledger.path,config),'replay-topup-08',uri,output)
                assert ref==item['reference'] and record['http_status']==404
                outcomes.append({'iteration':iteration,'uri':uri,'original':ref,'historical_duplicate':batches['topup-08'][uri]['reference']})
        assert fetch.call_count==0 and not ledger.visits()
    assert hashes=={path:file_sha(path) for path in hashes}
    report={'status':'PASS','original_ledger_read_only':str(Path(original).absolute()),'uris':8,
            'second_batch_original_receipt_references':8,'restart_original_receipt_references':8,
            'new_GET':0,'network_connections':0,'original_receipts_unchanged':True,'rows':outcomes}
    save_json(output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ledger',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();replay(args.ledger,args.output)
