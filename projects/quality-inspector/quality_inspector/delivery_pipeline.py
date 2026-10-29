"""Bound delivery-QC runner: sampled model jobs, human escalation and final QC.

This runner never collects trajectories, authors human decisions, or bypasses
distribution checks. Every operation uses the immutable outer receipt. Unlike
the legacy worker sampling_binding, its binding is part of each job identity.
"""
import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3

from . import ai_worker, delivery_sampling
from .engine import inspect
from .profiles import DEFAULT_DELIVERY_PROFILE, package_files
from .reporting import write_outputs
from webcollect.batch_core import BatchLedger

VERSION='delivery-qc-pipeline-1'
PIPELINE_RULES_VERSION='frozen-sample-slots-human-escalation-final-seal-1'
KINDS=('ai-visual','ai-difference','ai-documents')


def _read(path):return json.loads(Path(path).read_text())
def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _digest(value):return delivery_sampling.digest(value)


def _ref(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('An original existing input file is required')
    return {'path':str(path.resolve()),'sha256':_sha(path)}


def _check_ref(ref):
    if _ref(ref['path'])!=ref:raise ValueError('Bound pipeline input file changed')


def _implementation():
    import webcollect,webcollect.batch_core,webcollect.model_gateway
    paths=[Path(__file__),Path(ai_worker.__file__),Path(delivery_sampling.__file__),
           Path(__file__).with_name('engine.py'),Path(__file__).with_name('profiles.py'),
           Path(__file__).with_name('reviews.py'),Path(__file__).with_name('contract.py'),
           Path(webcollect.batch_core.__file__),Path(webcollect.model_gateway.__file__)]
    paths += [Path(webcollect.__file__).parent/name for name in ('site_progress.py','client_reports.py')
              if (Path(webcollect.__file__).parent/name).is_file()]
    return {str(path.resolve()):_sha(path) for path in paths}


def _mode(ledger,mode):
    model=ledger.config.get('model') or {}
    if mode=='real':
        supported = ((model.get('provider') == 'glm' and model.get('model') == 'glm-5.3-flash')
                     or (model.get('provider') == 'ark' and model.get('model') in
                         ('glm-5-3-flash-260828', 'deepseek-v4-1-flash-261017',
                          'deepseek-v4-1-flash-economy-261017')))
        if ledger.config.get('mode')!='real' or not supported or model.get('supports_vision') is not True:
            raise ValueError('Real delivery pipeline requires explicitly configured glm-5.3-flash or Ark vision model')
    elif mode=='controlled':
        if ledger.config.get('mode')!='synthetic' or model.get('provider')!='synthetic':
            raise ValueError('Controlled mode requires a synthetic ledger and cannot claim real review')
    else:raise ValueError('Explicit real or controlled execution mode is required')


def _external(output,roots,inputs=()):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new output path; preserve previous pipeline evidence')
    if any(output.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError('Pipeline output must be outside inspected candidate and historical packages')
    if any(output==Path(path).resolve() for path in inputs):raise ValueError('Pipeline output cannot replace an input')
    return output


def _roots(receipt):
    result=[Path(receipt['dataset']).resolve()]
    for item in _read(receipt['effective_set']['path'])['packages']:
        root=Path(item['path']);root=Path(receipt['effective_set']['path']).parent/root if not root.is_absolute() else root
        result.append(root.resolve())
    return result


@contextmanager
def _lock(receipt_path):
    receipt=_read(receipt_path)
    if receipt.get('schema_version')!=VERSION:raise ValueError('Expected a delivery pipeline receipt before acquiring its lock')
    lock=Path(receipt_path).resolve().with_name(Path(receipt_path).name+'.operation.lock')
    if any(lock.is_relative_to(root) for root in _roots(receipt)):
        raise ValueError('Pipeline receipt/lock cannot be inside inspected packages')
    if lock.is_symlink():raise ValueError('Pipeline operation lock cannot be a symlink')
    with lock.open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another operation owns this delivery pipeline') from None
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


@contextmanager
def _human_gate(ledger):
    path=ledger.path.with_name(ledger.path.name+'.human-finalization.lock')
    if path.is_symlink():raise ValueError('Human/finalization gate lock cannot be a symlink')
    with path.open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another human import/finalization owns this model-ledger gate') from None
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


class _BoundLedger:
    """Delegate charging/leases, but enqueue and dispatch only bound identities."""
    def __init__(self,ledger,binding,*,allowed=None,validate=None):
        self._base=ledger;self.binding=binding;self.allowed=allowed;self.validate=validate

    def __getattr__(self,name):return getattr(self._base,name)

    def enqueue(self,kind,payload):
        if kind in KINDS:payload={**payload,'delivery_pipeline_binding':self.binding}
        return self._base.enqueue(kind,payload)

    def claim(self,kind,*,job_id=None,**kwargs):
        if self.allowed is None:return self._base.claim(kind,job_id=job_id,**kwargs)
        if self.validate:self.validate()
        candidates=[job_id] if job_id else sorted(self.allowed)
        for identity in candidates:
            if identity not in self.allowed:raise ValueError('Unbound worker job cannot be dispatched')
            expected=self.allowed[identity];job=self._base.get(identity)
            if job['kind']!=kind:continue
            if _digest(job['payload'])!=expected['payload_sha256']:
                raise ValueError('Bound worker job payload changed before dispatch')
            result=self._base.claim(kind,job_id=identity,**kwargs)
            if result:return result
        return None

    def reserve_request(self,*args,**kwargs):
        if self.validate:self.validate()
        job=args[0]
        if self.allowed is not None and job['id'] not in self.allowed:
            raise ValueError('Unbound worker cannot reserve a model request')
        return self._base.reserve_request(*args,**kwargs)

    def finish(self,*args,**kwargs):
        result=self._base.finish(*args,**kwargs)
        if self.validate:self.validate()
        return result


def prepare(ledger,dataset,plan_path,effective_set,output,*,profile=DEFAULT_DELIVERY_PROFILE,
            mode='real',supporting_files=(),cross_package_report=None,collection_checks=None,document_review_mode='ai',
            sample_reviews=None,production_handoff=None):
    from .delivery_scope import verify_delivery_scope
    _mode(ledger,mode)
    if production_handoff is not None:
        if mode != 'real':raise ValueError('Controlled QC cannot update production/shared pool')
        from webcollect.site_pool_sync import validate_handoff
        validate_handoff(production_handoff,dataset)
    if document_review_mode not in ('ai','human'):raise ValueError('Explicit ai or human documentary review mode required')
    dataset=Path(dataset).resolve();plan_path=Path(plan_path).resolve()
    plan=delivery_sampling.verify(plan_path,dataset)
    scope=verify_delivery_scope(effective_set,cross_package_report,dataset=dataset,phase='payload')
    manifest=_read(effective_set)
    if manifest.get('schema_version')!='qc-cumulative-set-1':raise ValueError('An explicit frozen cumulative set is required')
    roots=[]
    for item in manifest['packages']:
        root=Path(item['path']);root=(Path(effective_set).resolve().parent/root).resolve() if not root.is_absolute() else root.resolve()
        if package_files(root)!=item['package_files_sha256']:raise ValueError('Effective cumulative package changed')
        roots.append(root)
    if dataset not in roots:raise ValueError('Cumulative set must include the actual candidate package')
    if ledger.path.is_relative_to(dataset):raise ValueError('Model ledger must be outside candidate samples')
    supporting_files=list(dict.fromkeys([*map(lambda p:str(Path(p).resolve()),supporting_files),
                                         *([str(Path(sample_reviews).resolve())] if sample_reviews else [])]))
    output=_external(output,roots,[plan_path,effective_set,profile,ledger.path,*supporting_files])
    output.mkdir(parents=True,exist_ok=False)
    implementation=_implementation();candidate=package_files(dataset)
    binding={'version':VERSION,'plan':_ref(plan_path),'plan_sha256':plan['plan_sha256'],
             'pipeline_rules_version':PIPELINE_RULES_VERSION,'mode':mode}
    proxy=_BoundLedger(ledger,binding)
    selected={slot['current']['sample_id'] for slot in plan['slots'] if slot['ai_selected']}
    try:
        queued=ai_worker.prepare(proxy,dataset,output/'worker',effective_set=effective_set,sample_ids=selected,
                                collection_checks=collection_checks)
        from .profiles import delivery_document_review_template
        document_template=delivery_document_review_template(inspect(None,dataset,profile=profile,inspection_stage='payload'))
        document_job=(ai_worker.documents_job(proxy,dataset,profile,output/'document-preparation',supporting_files=supporting_files,
                      sample_reviews=sample_reviews,delivery_sampling_plan=plan_path if sample_reviews else None)
                      if document_review_mode=='ai' else None)
        queue=_read(queued['queue_file'])
        job_ids={job for row in queue['jobs'] for job in (row['visual_job'],row['difference_job'])}
        if document_job:job_ids.add(document_job)
        jobs={jid:{'kind':ledger.get(jid)['kind'],'payload_sha256':_digest(ledger.get(jid)['payload'])} for jid in sorted(job_ids)}
        for jid in jobs:
            if ledger.get(jid)['payload'].get('delivery_pipeline_binding')!=binding:
                raise ValueError('Worker job is not bound to this exact delivery sampling plan')
        value={'schema_version':VERSION,'created_at_utc':datetime.now(timezone.utc).isoformat(),
               'mode':mode,'dataset':str(dataset),'candidate_files_sha256':candidate,
               'plan':binding['plan'],'plan_sha256':plan['plan_sha256'],'binding':binding,
               'ledger':str(ledger.path),'ledger_config_sha256':_digest(ledger.config),
               'effective_set':_ref(effective_set),'profile':_ref(profile),
               'cross_package_report':_ref(cross_package_report),'delivery_scope':scope,
               'collection_checks':queue.get('collection_checks'),
               **({'production_handoff':production_handoff} if production_handoff is not None else {}),
               'supporting_files':[_ref(path) for path in supporting_files],
               'implementation_sha256':implementation,'queue':_ref(queued['queue_file']),
               'pipeline_rules_version':PIPELINE_RULES_VERSION,
               'jobs':jobs,'document_job':document_job,'ai_selected_sample_ids':sorted(selected),
               'document_review_mode':document_review_mode,'document_template':document_template,
               'original_denominator':plan['original_denominator'],
               'mechanically_blocked':queue['mechanically_blocked'],
               'actual_human_reviews_created':0,'release_ready':False}
        value['receipt_sha256']=_digest(value)
        if package_files(dataset)!=candidate or implementation!=_implementation():raise ValueError('Inputs/code changed during pipeline preparation')
        delivery_sampling.verify(plan_path,dataset)
        receipt=output/'pipeline-receipt.json';delivery_sampling.write(receipt,value)
        verify(receipt,ledger)
        return {'receipt':str(receipt),'ai_selected_samples':len(selected),'bound_jobs':len(jobs),
                'model_requests_dispatched':0,'release_ready':False,'mode':mode}
    except Exception as error:
        delivery_sampling.write(output/'prepare-failure.json',{'status':'STOP','type':type(error).__name__,
                                'reason':str(error),'model_requests_dispatched':0,'release_ready':False})
        raise


def _verify_frozen_cross_scope(receipt):
    """Validate the already evaluated scope without rerunning global pair search.

    prepare/final/archive run the complete scope checker. During worker leases
    the exact frozen report, rules, profile and every package byte stay bound;
    a mutable PASS flag alone is never used as authority.
    """
    from .contract import fingerprint
    saved=receipt['delivery_scope'];manifest=_read(receipt['effective_set']['path'])
    report=_read(receipt['cross_package_report']['path'])
    if (saved.get('effective_set')!=receipt['effective_set']
            or saved.get('cross_package_report')!=receipt['cross_package_report']
            or saved.get('manifest_sha256')!=_digest(manifest)
            or report.get('manifest')!=manifest or report.get('manifest_sha256')!=saved['manifest_sha256']
            or report.get('contract_sha256')!=fingerprint()[1]
            or report.get('contract_sha256')!=saved.get('contract_sha256')
            or any(report.get(key)!='PASS' for key in ('status','mechanical_status','cross_package_status'))
            or saved.get('source_member')!=receipt['dataset']):
        raise ValueError('Frozen cross-package scope/report binding changed')
    selected=report.get('local_profile',{})
    _check_ref({'path':selected['path'],'sha256':selected['sha256']})
    snapshots={}
    for item in manifest['packages']:
        root=Path(item['path']);root=(Path(receipt['effective_set']['path']).parent/root).resolve() if not root.is_absolute() else root.resolve()
        if str(root) in snapshots:raise ValueError('Frozen scope has duplicate package roots')
        snapshots[str(root)]=item['package_files_sha256']
    if (snapshots!=report.get('input_files_sha256')
            or snapshots.get(receipt['dataset'])!=receipt['candidate_files_sha256']
            or {key:value for key,value in receipt['candidate_files_sha256'].items() if key not in ('qc_report.md','SHA256SUMS')}
                !=saved.get('payload_files_sha256')):
        raise ValueError('Frozen cross-package membership or complete file binding changed')


def verify(receipt_path,ledger=None):
    reference=_ref(receipt_path);receipt=_read(receipt_path)
    unsigned={key:value for key,value in receipt.items() if key!='receipt_sha256'}
    if receipt.get('schema_version')!=VERSION or receipt.get('receipt_sha256')!=_digest(unsigned):
        raise ValueError('Pipeline receipt was changed')
    if 'pipeline_rules_version' in receipt:
        if receipt['pipeline_rules_version']!=PIPELINE_RULES_VERSION:raise ValueError('Pipeline rules changed; prepare a new version')
    elif receipt['implementation_sha256']!=_implementation():
        raise ValueError('Legacy pipeline implementation changed; prepare a new version')
    for ref in [receipt['plan'],receipt['queue'],receipt['effective_set'],receipt['profile'],*receipt['supporting_files']]:_check_ref(ref)
    if receipt.get('cross_package_report'):
        _check_ref(receipt['cross_package_report'])
        _verify_frozen_cross_scope(receipt)
    else:raise ValueError('Pipeline requires the bound cross-package report')
    if receipt.get('collection_checks'):
        _check_ref(receipt['collection_checks'])
        ai_worker.collection_context(receipt['collection_checks'],{
            slot['current']['sample_id'] for slot in delivery_sampling.verify(receipt['plan']['path'])['slots']})
    if receipt.get('production_handoff'):
        from webcollect.site_pool_sync import validate_handoff
        validate_handoff(receipt['production_handoff'],receipt['dataset'])
    plan=delivery_sampling.verify(receipt['plan']['path'],receipt['dataset'])
    if plan['plan_sha256']!=receipt['plan_sha256']:raise ValueError('Bound delivery sampling plan identity changed')
    if package_files(receipt['dataset'])!=receipt['candidate_files_sha256']:raise ValueError('Pipeline candidate package changed')
    manifest=_read(receipt['effective_set']['path'])
    for item in manifest['packages']:
        root=Path(item['path']);root=Path(receipt['effective_set']['path']).parent/root if not root.is_absolute() else root
        if package_files(root)!=item['package_files_sha256']:raise ValueError('Pipeline cumulative history changed')
    if ledger is None:ledger=_ledger(receipt)
    if str(ledger.path)!=receipt['ledger'] or _digest(ledger.config)!=receipt['ledger_config_sha256']:
        raise ValueError('Pipeline cannot switch model ledger or frozen configuration')
    _mode(ledger,receipt['mode'])
    queue=_read(receipt['queue']['path'])
    expected={jid for row in queue['jobs'] for jid in (row['visual_job'],row['difference_job'])}
    if receipt['document_job']:expected.add(receipt['document_job'])
    if set(receipt['jobs'])!=expected:raise ValueError('Pipeline job population differs from frozen worker queue')
    for jid,expected in receipt['jobs'].items():
        job=ledger.get(jid)
        if (job['kind']!=expected['kind'] or _digest(job['payload'])!=expected['payload_sha256']
                or job['payload'].get('delivery_pipeline_binding')!=receipt['binding']):
            raise ValueError('Bound worker job identity/payload changed')
    if _ref(receipt_path)!=reference:raise ValueError('Pipeline receipt changed during verification')
    return receipt


def _ledger(receipt):
    path=Path(receipt['ledger']).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
        row=con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()
    if not row:raise ValueError('Existing model ledger configuration is missing')
    config=json.loads(row[0])
    if _digest(config)!=receipt['ledger_config_sha256']:raise ValueError('Model ledger configuration changed')
    return BatchLedger(path,config)


def _usage(ledger,receipt):
    with ledger.connect() as con:
        rows=[dict(row) for row in con.execute('SELECT * FROM model_requests ORDER BY started')
              if row['job_id'] in receipt['jobs']]
    usage=[json.loads(row['usage']) for row in rows if row['usage'] is not None]
    complete=len(usage)==len(rows)
    return {'scope':'only-job-ids-bound-to-this-pipeline','mode':receipt['mode'],'model_requests':len(rows),
            'external_model_requests':len(rows) if receipt['mode']=='real' else 0,
            'request_states':dict(Counter(row['state'] for row in rows)),
            'usage_covered_requests':len(usage),'usage_coverage_complete':complete,
            'input_tokens':sum(row['input_tokens'] for row in usage) if complete else 'UNKNOWN',
            'output_tokens':sum(row['output_tokens'] for row in usage) if complete else 'UNKNOWN',
            'cached_input_tokens':sum(row.get('cached_input_tokens',0) for row in usage) if complete else 'UNKNOWN',
            'known_model_cost_micros':sum(row['cost'] for row in rows if row['cost'] is not None),
            'uncertain_reserved_cost_micros':sum(row['reserved_cost'] for row in rows if row['cost'] is None),
            'currency':ledger.config['budget']['currency'],'actual_account_debit':'UNKNOWN'}


def _human_events(ledger,receipt,connection=None):
    if connection is None:
        with ledger.connect() as con:return _human_events(ledger,receipt,connection=con)
    plan=delivery_sampling.verify(receipt['plan']['path'])
    current={row['current']['sample_id']:row['current'] for row in plan['slots']}
    template=receipt['document_template']
    events=[]
    for row in connection.execute("SELECT seq,detail FROM batch_events WHERE event='delivery_pipeline_human_import' ORDER BY seq"):
        value=json.loads(row['detail']);saved=value.get('event_sha256')
        if saved!=_digest({k:v for k,v in value.items() if k!='event_sha256'}):
            raise ValueError('Persistent human inspection history changed')
        relevant=any(item['sample_id'] in current
                     and (item.get('decision')=='FAIL' or
                          item['annotation_sha256']==current[item['sample_id']]['annotation_sha256']
                          and item['evidence_sha256']==current[item['sample_id']]['evidence_sha256'])
                     for item in value.get('records',[]))
        document=value.get('document')
        relevant=relevant or bool(document and all(document.get(key)==template.get(key) for key in
                     ('baseline_sha256','profile_sha256','payload_files_sha256')))
        if relevant:
            _check_ref(value['source'])
            events.append({'sequence':row['seq'],**value})
    return events


def _human_history_hash(ledger,receipt,connection=None):
    return _digest([{'sequence':row['sequence'],'event_sha256':row['event_sha256']} for row in _human_events(ledger,receipt,connection=connection)])


def _human_materials(ledger,receipt,new_paths,output):
    """Select unchanged current records; keep prior FAIL sticky in the ledger."""
    from .reviews import intake,record_hash
    current={row['current']['sample_id']:row['current'] for row in delivery_sampling.verify(receipt['plan']['path'])['slots']}
    prior=_human_events(ledger,receipt)
    sources=[]
    for event in prior:
        if event['source'] not in sources:sources.append(event['source'])
    new_sources=[_ref(path) for path in new_paths]
    for source in new_sources:
        if source not in sources:sources.append(source)
    records={};record_sources={};document=None;document_source=None;imports=[]
    template=receipt['document_template']
    for source in sources:
        raw=_read(source['path'])
        if raw.get('schema_version')!='qc-review-2' or not isinstance(raw.get('records'),list):
            raise ValueError('Human import requires actual qc-review-2 records')
        imported=[]
        for record in raw['records']:
            if not isinstance(record,dict):raise ValueError('Malformed human record')
            sid=record.get('sample_id')
            if sid not in current:continue
            previous=records.get(sid)
            if previous is not None and previous!=record:
                statuses={row['status'] for row in previous['checks'].values()}
                new_fail=any(check.get('status')=='FAIL' for check in record.get('checks',{}).values())
                if 'FAIL' in statuses and not new_fail:
                    raise ValueError('Human-rejected sample bytes require a new capture identity; FAIL cannot be overwritten')
                # A pending human observation may be completed by a later
                # original export; the previous source remains in history.
            records[sid]=record;record_sources[sid]={'source':source,'record_sha256':record_hash(record)}
            imported.append({'sample_id':sid,'annotation_sha256':record.get('annotation_sha256'),
                             'evidence_sha256':record.get('evidence_sha256'),'record_sha256':record_hash(record),
                             'decision':'FAIL' if any(check.get('status')=='FAIL' for check in record.get('checks',{}).values()) else
                                        'PASS' if all(check.get('status')=='PASS' for check in record.get('checks',{}).values()) else 'REVIEW_REQUIRED'})
        candidate=raw.get('delivery_document_review')
        doc_binding=None
        if isinstance(candidate,dict) and all(candidate.get(key)==template.get(key) for key in
                     ('baseline_sha256','profile_sha256','payload_files_sha256')):
            if candidate.get('reviewer',{}).get('kind')!='human':raise ValueError('Human documentary import needs its actual human reviewer')
            if document is not None and document!=candidate:
                statuses={row.get('status') for row in document.get('checks',{}).values()}
                new_fail=any(row.get('status')=='FAIL' for row in candidate.get('checks',{}).values())
                if 'FAIL' in statuses and not new_fail:
                    raise ValueError('Human-rejected documentary bytes require a revised package, not overwritten PASS')
            document=candidate;document_source=source
            doc_binding={key:candidate[key] for key in ('baseline_sha256','profile_sha256','payload_files_sha256')}
            doc_binding['record_sha256']=record_hash(candidate)
        if source in new_sources and (imported or doc_binding):
            event={'schema_version':VERSION+'-human-import','source':source,'records':imported,'document':doc_binding}
            event['event_sha256']=_digest(event);imports.append(event)
        _check_ref(source)
    if new_sources and not imports:raise ValueError('Human import contains no current candidate or documentary decisions')
    paths=[]
    if records:
        selected=output/'current-human-reviews.json'
        delivery_sampling.write(selected,{'schema_version':'qc-review-2','records':list(records.values()),
            'selection_sources':[dict(sample_id=sid,**record_sources[sid]) for sid in sorted(records)],
            'actual_human_reviews_created':0})
        contexts=[{'sample_id':sid,'sample_path':str(Path(receipt['dataset'])/'samples'/sid)} for sid in current]
        accepted,errors,_=intake(selected,contexts,delivery_sampling.verify(receipt['plan']['path'])['contract_sha256'])
        if errors or any(row['reviewer']['kind']!='human' for row in accepted.values()):
            raise ValueError('Imported human records do not bind current original evidence: '+str(errors))
        paths=[selected]
    return paths,sources,imports,document,document_source


def _commit_humans(ledger,imports,receipt,expected_history):
    with _human_gate(ledger),ledger.transaction() as con:
        if _human_history_hash(ledger,receipt,connection=con)!=expected_history:
            raise ValueError('Human history changed during inspection; rerun status with current decisions')
        existing={json.loads(row['detail']).get('event_sha256') for row in
                  con.execute("SELECT detail FROM batch_events WHERE event='delivery_pipeline_human_import'")}
        for event in imports:
            if event['event_sha256'] not in existing:
                ledger.event(con,'delivery_pipeline_human_import',event);existing.add(event['event_sha256'])
        return _human_history_hash(ledger,receipt,connection=con)


def _issue_status(ledger,receipt_path,receipt,status_path,history):
    reference=_ref(status_path)
    with _human_gate(ledger),ledger.transaction() as con:
        if _human_history_hash(ledger,receipt,connection=con)!=history:
            raise ValueError('Human history changed before status publication; regenerate status')
        ledger.event(con,'delivery_pipeline_status_issued',{'schema_version':VERSION+'-status-issuance',
            'status':reference,'receipt':_ref(receipt_path),'human_history_sha256':history})
    return reference


def _verify_issued_status(ledger,receipt_path,status_reference,history):
    expected={'schema_version':VERSION+'-status-issuance','status':status_reference,
              'receipt':_ref(receipt_path),'human_history_sha256':history}
    with ledger.connect() as con:
        issued=[json.loads(row['detail']) for row in con.execute(
            "SELECT detail FROM batch_events WHERE event='delivery_pipeline_status_issued'")]
    if expected not in issued:raise ValueError('Status/report bindings were not issued by this pipeline; edited status cannot authorize finalization')


def _status(ledger,receipt_path,output,*,human_reviews=(),progress=None,request_id=None):
    receipt=verify(receipt_path,ledger)
    if progress is not None and receipt['mode']!='real':raise ValueError('Controlled QC must not update real site progress')
    output=_external(output,_roots(receipt),[receipt_path,*human_reviews]);output.mkdir(parents=True,exist_ok=False)
    worker=ai_worker.report(ledger,receipt['queue']['path'],output/'worker-report',document_job=receipt['document_job'])
    failure_paths=[]
    if receipt['mode']=='real':
        try:
            failed=delivery_sampling.export_failures(receipt['plan']['path'],ledger.path,output/'all-current-ledger-failures.json')
            from .semantic_runtime import failure_jobs
            failure_scope=failure_jobs(ledger,receipt['jobs'])
            failed['rows']=[row for row in failed['rows'] if row['job_id'] in failure_scope]
            if failed['rows']:
                delivery_sampling.write(output/'ai-failures.json',failed);failure_paths=[output/'ai-failures.json']
        except ValueError as error:
            if str(error)!='No actual failed model requests for the frozen current samples':raise
    # Synthetic worker exports keep their incompatible schema and cannot be
    # imported as actual AI approval; their job/results still exercise routing.
    reviews=worker['review_file'] if receipt['mode']=='real' else None
    history_before=_human_history_hash(ledger,receipt)
    human_paths,human_inputs,human_imports,human_document,human_document_source=_human_materials(ledger,receipt,human_reviews,output)
    if human_document is not None:
        exported=_read(worker['review_file']) if receipt['mode']=='real' else {'schema_version':'qc-review-2','records':[]}
        exported['delivery_document_review']=human_document
        exported['documentary_resolution']={'actual_human_source':human_document_source,
                                            'original_worker_export':_ref(worker['review_file']),
                                            'original_decisions_retained':True}
        reviews=output/'effective-reviews.json';delivery_sampling.write(reviews,exported)
    report=inspect(None,receipt['dataset'],profile=receipt['profile']['path'],reviews=reviews,
                   inspection_stage='payload',delivery_sampling_plan=receipt['plan']['path'],
                   human_reviews=human_paths,ai_failures=failure_paths)
    if receipt['mode']=='controlled':
        report['release_ready']=False;report['pipeline_execution_mode']='controlled'
    report_dir=output/'payload-qc';write_outputs(report,report_dir)
    if human_document is not None and report['delivery_document_review']['status']=='FAIL' and report['delivery_document_review'].get('errors'):
        raise ValueError('Actual human documentary review did not bind the current payload')
    committed_history=_commit_humans(ledger,human_imports,receipt,history_before)
    sampling=report['semantic_sampling']
    human_queue=[row for row in sampling['rows'] if row['status']=='HUMAN_REQUIRED']
    replacements=[row for row in sampling['rows'] if row['status']=='REPLACE_REQUIRED']
    document=report['delivery_document_review'];doc_job=ledger.get(receipt['document_job']) if receipt['document_job'] else None
    raw_document=_read(worker['review_file']).get('delivery_document_review')
    from .profiles import delivery_document_review
    original_document=delivery_document_review(worker['review_file'],report) if receipt['mode']=='real' and raw_document else None
    raw_states={row.get('status') for row in (raw_document or {}).get('checks',{}).values()}
    doc_ai=('INVALID_REVIEW' if original_document and original_document['status']=='FAIL' and original_document.get('errors') else
            'FAIL' if 'FAIL' in raw_states else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in raw_states else 'PASS' if raw_states=={'PASS'} else
            'CALL_FAILED' if doc_job and doc_job['state']=='review_required' else 'NOT_REVIEWED')
    doc_state=('REVISE_DOCUMENTS_REQUIRED' if human_document is not None and document['status']=='FAIL' else
               'HUMAN_PASS' if human_document is not None and document['status']=='PASS' else
               'HUMAN_REQUIRED' if receipt['document_review_mode']=='human' or human_document is not None or doc_ai in ('FAIL','REVIEW_REQUIRED','CALL_FAILED','INVALID_REVIEW') else
               'AI_PASS' if doc_ai=='PASS' and document['status']=='PASS' else 'AI_REQUIRED')
    document_queue={'schema_version':VERSION+'-document-human-queue','status':doc_state,
                    'actual_ai_status':doc_ai,'human_pending_count':int(doc_state=='HUMAN_REQUIRED'),
                    'original_documentary_validation':original_document,
                    'report':_ref(report_dir/'report.json'),'original_worker_review':_ref(worker['review_file']),
                    'actual_human_source':human_document_source,'actual_human_reviews_created':0}
    delivery_sampling.write(output/'document-human-queue.json',document_queue)
    delivery_sampling.write(output/'human-queue.json',{'schema_version':VERSION+'-human-queue',
        'report':_ref(report_dir/'report.json'),'rows':human_queue,'count':len(human_queue),'actual_human_reviews_created':0})
    delivery_sampling.write(output/'replacement-requests.json',{'schema_version':VERSION+'-replacement-requests',
        'report':_ref(report_dir/'report.json'),'rows':replacements,'count':len(replacements),
        'action':'site_progress must bind new capture attempts and mandatory replacement reinspection',
        'original_failures_retained':True})
    imported=None
    if progress is not None:
        if receipt['mode']!='real':raise ValueError('Controlled QC must not update real site progress')
        if not request_id:raise ValueError('Progress import needs an explicit idempotent request ID')
        imported=progress.import_qc(report_dir/'report.json',request_id=request_id)
    verify(receipt_path,ledger)
    if receipt.get('production_handoff'):
        from webcollect.site_pool_sync import apply_qc
        apply_qc(report_dir/'report.json',receipt['production_handoff'])
    for reference in human_inputs:_check_ref(reference)
    summary={'schema_version':VERSION+'-status','receipt':_ref(receipt_path),'mode':receipt['mode'],
             'dataset':receipt['dataset'],'original_denominator':receipt['original_denominator'],
             'payload_status':report['delivery_status'],'report':_ref(report_dir/'report.json'),
             'ai_pending_count':sampling['ai_pending_count'],'human_pending_count':sampling['human_pending_count'],
             'replacement_required_count':sampling['replacement_required_count'],
             'human_document_pending_count':document_queue['human_pending_count'],
             'document_review_status':doc_state,
             'actual_ai_reviewed':sampling['actual_ai_reviewed'],'actual_human_reviewed':sampling['actual_human_reviewed'],
             'review_file':_ref(reviews or worker['review_file']),'worker_review_file':_ref(worker['review_file']),
             'human_reviews':[_ref(path) for path in human_paths],
             'human_input_sources':human_inputs,
             'human_history_sha256':committed_history,
             'ai_failure_sources':sampling['ai_failure_sources'],'model_cost':ledger.summary(),
             'model_cost_scope':'entire-original-ledger; bound-job totals are in pipeline_model_usage',
             'pipeline_model_usage':_usage(ledger,receipt),
             'elapsed_since_prepare_seconds':(datetime.now(timezone.utc)-datetime.fromisoformat(receipt['created_at_utc'])).total_seconds(),
             'job_states':dict(Counter(ledger.get(jid)['state'] for jid in receipt['jobs'])),
             'progress_import':imported,'release_ready':False,'customer_acceptance':'UNKNOWN'}
    delivery_sampling.write(output/'status.json',summary)
    _issue_status(ledger,receipt_path,receipt,output/'status.json',committed_history)
    return summary


def status(receipt_path,output,*,human_reviews=(),progress=None,request_id=None):
    with _lock(receipt_path):
        receipt=verify(receipt_path);ledger=_ledger(receipt)
        _external(output,_roots(receipt),[receipt_path,*human_reviews])
        if progress is not None and receipt['mode']!='real':raise ValueError('Controlled QC must not update real site progress')
        return _status(ledger,receipt_path,output,human_reviews=human_reviews,progress=progress,request_id=request_id)


def run(receipt_path,output,*,max_jobs=100,human_reviews=(),progress=None,request_id=None):
    if type(max_jobs)is not int or max_jobs<1:raise ValueError('max_jobs must be positive')
    with _lock(receipt_path):
        receipt=verify(receipt_path);ledger=_ledger(receipt)
        _external(output,_roots(receipt),[receipt_path,*human_reviews])
        if progress is not None and receipt['mode']!='real':raise ValueError('Controlled QC must not update real site progress')
        proxy=_BoundLedger(ledger,receipt['binding'],allowed=receipt['jobs'],validate=lambda:verify(receipt_path,ledger))
        result=ai_worker.run(proxy,max_jobs=max_jobs)
        verify(receipt_path,ledger)
        summary=_status(ledger,receipt_path,output,human_reviews=human_reviews,progress=progress,request_id=request_id)
        delivery_sampling.write(Path(output)/'worker-run.json',result)
        return summary


def import_human(receipt_path,human_reviews,output,*,progress=None,request_id=None):
    if not human_reviews:raise ValueError('Actual human review files are required')
    return status(receipt_path,output,human_reviews=human_reviews,progress=progress,request_id=request_id)


def finalize(receipt_path,status_path,output,*,archive=None,progress=None,request_id=None):
    with _lock(receipt_path):
        receipt=verify(receipt_path);ledger=_ledger(receipt)
        with _human_gate(ledger):
            return _finalize_locked(ledger,receipt,receipt_path,status_path,output,
                                    archive=archive,progress=progress,request_id=request_id)


def _finalize_locked(ledger,receipt,receipt_path,status_path,output,*,archive=None,progress=None,request_id=None):
    from webcollect.client_reports import finalize_client_package,archive_client_package
    path=Path(status_path)
    if path.is_symlink() or not path.is_file():raise ValueError('Status must be an original existing file')
    raw=path.read_bytes();state=json.loads(raw)
    status_reference={'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest()}
    if receipt['mode']!='real':raise ValueError('Controlled pipelines cannot publish customer packages')
    _verify_issued_status(ledger,receipt_path,status_reference,state.get('human_history_sha256'))
    if state.get('receipt')!=_ref(receipt_path):raise ValueError('Status belongs to another pipeline receipt')
    if state.get('human_history_sha256')!=_human_history_hash(ledger,receipt):
        raise ValueError('Human inspection history changed after this status; regenerate status before finalization')
    for ref in [state['report'],state['review_file'],*state['human_reviews'],*state['ai_failure_sources']]:_check_ref(ref)
    current=inspect(None,receipt['dataset'],profile=receipt['profile']['path'],reviews=state['review_file']['path'],
        inspection_stage='payload',delivery_sampling_plan=receipt['plan']['path'],
        human_reviews=[r['path'] for r in state['human_reviews']],ai_failures=[r['path'] for r in state['ai_failure_sources']])
    if current['delivery_status']!='PASS' or state.get('payload_status')!='PASS':
        raise ValueError('Payload, distribution, documents or human/replacement issues remain unresolved; no finalization')
    saved=_read(state['report']['path'])
    if current['semantic_sampling']!=saved.get('semantic_sampling') or current['input_files_sha256']!=saved.get('input_files_sha256'):
        raise ValueError('Saved payload QC no longer reproduces')
    output=_external(output,_roots(receipt),[receipt_path,status_path])
    if archive:_external(archive,_roots(receipt),[receipt_path,status_path])
    if progress is not None and not request_id:raise ValueError('Final progress import needs an explicit request ID')
    output.mkdir(parents=True,exist_ok=False)
    scope_args={'effective_set':receipt['effective_set']['path'],
                'cross_package_report':receipt['cross_package_report']['path']}
    result=finalize_client_package(Path(__file__).resolve().parents[3],receipt['dataset'],state['report']['path'],output/'client-final',**scope_args)
    report=inspect(None,result['output'],profile=receipt['profile']['path'],reviews=state['review_file']['path'],
        inspection_stage='final',delivery_sampling_plan=receipt['plan']['path'],
        human_reviews=[r['path'] for r in state['human_reviews']],ai_failures=[r['path'] for r in state['ai_failure_sources']])
    write_outputs(report,output/'final-qc')
    verify(receipt_path,ledger)
    if state['human_history_sha256']!=_human_history_hash(ledger,receipt):raise ValueError('Human inspection history changed during finalization')
    imported=None
    if progress is not None and report['release_ready'] is True:
        imported=progress.import_qc(output/'final-qc/report.json',request_id=request_id)
    archived=None
    if archive:
        if report['delivery_status']!='PASS' or report['release_ready'] is not True:raise ValueError('Final package QC did not pass; archive refused')
        _check_ref(status_reference)
        archived=archive_client_package(result['output'],output/'final-qc/report.json',archive,**scope_args)
    summary={'schema_version':VERSION+'-final','receipt':_ref(receipt_path),
             'final_package':result['output'],'final_report':_ref(output/'final-qc/report.json'),
             'delivery_status':report['delivery_status'],'release_ready':report['release_ready'],
             'archive':archived,'progress_import':imported,'customer_acceptance':'UNKNOWN'}
    delivery_sampling.write(output/'final-status.json',summary);return summary

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--config',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--initialize-ledger',action='store_true');p.add_argument('--input',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--effective-set',type=Path,required=True)
    p.add_argument('--cross-package-report',type=Path,required=True)
    p.add_argument('--collection-checks',type=Path)
    p.add_argument('--production-handoff',type=Path,help='Original current-chain capture handoff for automatic shared pool QC writeback')
    p.add_argument('--document-review-mode',choices=('ai','human'),required=True)
    p.add_argument('--profile',type=Path,default=DEFAULT_DELIVERY_PROFILE);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('real','controlled'),required=True);p.add_argument('--supporting-file',type=Path,action='append',default=[])
    for name in ('run','status','import-human'):
        p=sub.add_parser(name);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
        p.add_argument('--human-reviews',type=Path,action='append',default=[])
        if name=='run':p.add_argument('--max-jobs',type=int,default=100)
        p.add_argument('--progress-state',type=Path);p.add_argument('--production-registry',type=Path);p.add_argument('--request-id')
    p=sub.add_parser('finalize');p.add_argument('--receipt',type=Path,required=True);p.add_argument('--status',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path)
    p.add_argument('--progress-state',type=Path);p.add_argument('--production-registry',type=Path);p.add_argument('--request-id')
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare':
            if args.initialize_ledger and args.ledger.exists():raise ValueError('Cannot initialize over an existing model ledger')
            if args.ledger.resolve().is_relative_to(args.input.resolve()):raise ValueError('Model ledger must be outside candidate samples')
            manifest=_read(args.effective_set)
            for item in manifest['packages']:
                root=Path(item['path']);root=Path(args.effective_set).resolve().parent/root if not root.is_absolute() else root
                if args.ledger.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Model ledger must be outside every historical inspected package before initialization')
            ledger=BatchLedger(args.ledger,_read(args.config),initialize=args.initialize_ledger)
            result=prepare(ledger,args.input,args.plan,args.effective_set,args.output,profile=args.profile,
                           mode=args.mode,supporting_files=args.supporting_file,
                           cross_package_report=args.cross_package_report,collection_checks=args.collection_checks,
                           document_review_mode=args.document_review_mode,
                           production_handoff=_ref(args.production_handoff) if args.production_handoff else None)
        elif args.command=='finalize':
            progress=None
            if args.progress_state or args.production_registry:
                if not args.progress_state or not args.production_registry:raise ValueError('Progress state and production registry must be supplied together')
                from webcollect.site_progress import SiteProgress
                progress=SiteProgress(args.production_registry,args.progress_state)
            result=finalize(args.receipt,args.status,args.output,archive=args.archive,progress=progress,request_id=args.request_id)
        else:
            progress=None
            if args.progress_state or args.production_registry:
                if not args.progress_state or not args.production_registry:raise ValueError('Progress state and production registry must be supplied together')
                from webcollect.site_progress import SiteProgress
                progress=SiteProgress(args.production_registry,args.progress_state)
            options={'human_reviews':args.human_reviews,'progress':progress,'request_id':args.request_id}
            if args.command=='run':result=run(args.receipt,args.output,max_jobs=args.max_jobs,**options)
            elif args.command=='import-human':result=import_human(args.receipt,args.human_reviews,args.output,progress=progress,request_id=args.request_id)
            else:result=status(args.receipt,args.output,**options)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if args.command=='finalize' and result.get('release_ready') is not True else 0
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        print(json.dumps({'status':'STOP','reason':str(error),'release_ready':False},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
