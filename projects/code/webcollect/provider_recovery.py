"""Append-only authorization recovery; never clears or reissues unknown requests."""
import json
from .planning import object_sha256, verify_evidence

KIND='model-authorization-probe'
TEXT='Authorization-only diagnostic. Return {"ok":true}.'
SCHEMA={'type':'object','properties':{'ok':{'const':True}},'required':['ok'],'additionalProperties':False}


def originals(con):
    return {row['id']:object_sha256(dict(row)) for row in con.execute(
        "SELECT * FROM model_requests WHERE state='unknown' AND error IN ('HTTPError:401','HTTPError:403') ORDER BY id")}


def _probe(con, job_id):
    job=con.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not job or job['kind']!=KIND:raise ValueError('Bound authorization probe required')
    payload=json.loads(job['payload']);verify_evidence(payload['authorization_evidence'])
    return job,payload


def _successful(con, job_id):
    job,payload=_probe(con,job_id)
    requests=list(con.execute('SELECT * FROM model_requests WHERE job_id=?',(job_id,)))
    if job['state']!='done' or len(requests)!=1 or requests[0]['state']!='succeeded':
        raise ValueError('Exactly one successful original authorization diagnostic required')
    request=requests[0];material=json.loads(request['request_json'])
    if (material.get('text')!=TEXT or material.get('schema')!=SCHEMA or material.get('images')!=[]
            or json.loads(request['response']).get('result')!={'ok':True} or not request['usage']):
        raise ValueError('Authorization diagnostic content/response differs')
    return payload,request


def holds(con):
    pending=originals(con);covered={}
    for event in con.execute("SELECT detail FROM batch_events WHERE event='provider_authorization_recovered' ORDER BY seq"):
        proof=json.loads(event[0]);payload,request=_successful(con,proof['probe_job_id'])
        if (request['id']!=proof['diagnostic_request_id'] or payload['original_auth_errors']!=proof['original_auth_errors']
                or object_sha256(dict(request))!=proof['diagnostic_request_sha256']):
            raise ValueError('Original authorization recovery evidence changed')
        covered.update(proof['original_auth_errors'])
    return {key:value for key,value in pending.items() if covered.get(key)!=value}


def permits_probe(con, job_id, request_json, attempt):
    job=con.execute('SELECT kind FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not job or job[0]!=KIND:return False
    _,payload=_probe(con,job_id)
    return (attempt==0 and payload['original_auth_errors']==holds(con)
        and request_json is not None and request_json.get('text')==TEXT
        and request_json.get('schema')==SCHEMA and request_json.get('images')==[]
        and not con.execute('SELECT 1 FROM model_requests WHERE job_id=?',(job_id,)).fetchone())


def prepare(ledger, evidence):
    verify_evidence(evidence)
    with ledger.connect() as con:pending=holds(con)
    if not pending:raise ValueError('No original authorization hold to reconcile')
    return ledger.enqueue(KIND,{'original_auth_errors':pending,'authorization_evidence':evidence,
        'scope':'One new diagnostic; old request state/usage/cost remain unchanged'})


def complete(ledger, job_id):
    with ledger.transaction() as con:
        payload,request=_successful(con,job_id)
        raw=originals(con)
        if any(raw.get(k)!=v for k,v in payload['original_auth_errors'].items()):
            raise ValueError('Original unknown request changed; recovery rejected')
        proof={'probe_job_id':job_id,'diagnostic_request_id':request['id'],
            'diagnostic_request_sha256':object_sha256(dict(request)),
            'original_auth_errors':payload['original_auth_errors'],
            'original_usage_and_cost':'UNKNOWN; retained reservations',
            'old_request_replay_authorized':False}
        saved=list(con.execute("SELECT detail FROM batch_events WHERE event='provider_authorization_recovered'"))
        if not any(json.loads(row[0])==proof for row in saved):ledger.event(con,'provider_authorization_recovered',proof)
        return proof
