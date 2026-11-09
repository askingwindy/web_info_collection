"""Project band advice/reservations beside the existing runtime ledger.

Derived SQLite indexes are disposable. Original runtime/QC evidence owns status.
All filesystem/QC binding work happens outside the reservation write transaction.
Only new/changed runtime evidence is projected; repeated reservations are O(1).
"""
import json
from pathlib import Path
import sqlite3
import time
from .batch_core import load_json
from .planning import object_sha256, verify_evidence
from .banded_plan import distribution, VERSION, band_counts

EVENT='conditional_plan_band_reserved_1'
ACCEPTED='conditional_plan_accepted_set_1'


def _project(registry):
    from .current_chain import _meta, read_chain_scope
    binding=_meta(registry); scope=read_chain_scope(binding['manifest']['path'])
    if str(Path(registry).resolve())!=scope['registry']:raise ValueError('Band registry scope mismatch')
    return {'chain_id':scope['chain_id'],'manifest':scope['manifest'],
            'pool':scope.get('candidate_project',{}).get('pool'),'registry':scope['registry']}


def _schema(con):
    con.execute('CREATE TABLE IF NOT EXISTS m4_band_reservations(project_key TEXT NOT NULL,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,band TEXT NOT NULL,budget_json TEXT NOT NULL,locked_band TEXT,PRIMARY KEY(project_key,task_id))')
    if 'locked_band' not in {r[1] for r in con.execute('PRAGMA table_info(m4_band_reservations)')}:
        con.execute('ALTER TABLE m4_band_reservations ADD COLUMN locked_band TEXT')
    con.execute('CREATE INDEX IF NOT EXISTS m4_band_attempt ON m4_band_reservations(attempt_id)')
    con.execute('CREATE INDEX IF NOT EXISTS m4_band_event_type ON m4_events(event_type,event_id)')
    con.execute('CREATE INDEX IF NOT EXISTS m4_band_attempt_status ON m4_attempts(status,attempt_id)')
    con.execute('CREATE TABLE IF NOT EXISTS m4_band_state(project_key TEXT PRIMARY KEY,five_count INTEGER NOT NULL,long_count INTEGER NOT NULL,cursor INTEGER NOT NULL,metrics_json TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS m4_band_sample_cache(project_key TEXT NOT NULL,attempt_id TEXT NOT NULL,status TEXT NOT NULL,evidence_json TEXT NOT NULL,effective_steps INTEGER,source_json TEXT,PRIMARY KEY(project_key,attempt_id))')


def _actual_accepted(registry,reference):
    """Reuse actual QC admission + explicit cross-package effective membership.

    reviewed_pass (independent review) and batch_accepted (sampling-policy
    admission) stay labelled separately. Neither is human/customer acceptance.
    """
    from .runtime import _bound_quality_report
    report,_=_bound_quality_report([reference]); claimed=report.get('production_quality')
    if not claimed:raise ValueError('No explicit effective/cross-package admission set in QC report')
    from quality_inspector.production_sampling import quality_report
    actual=quality_report(report,claimed['effective_set'],claimed['cross_package_report'],claimed.get('production_handoff'))
    if actual!=claimed:raise ValueError('Original production admission differs from independently recomputed report')
    cross=load_json(claimed['cross_package_report']['path'])
    members=cross['version_comparison']['effective_samples']
    if (cross.get('duplicates',{}).get('summary',{}).get('analysis_status')!='COMPLETE'
            or cross['duplicates']['summary'].get('unadjudicated_pair_count')!=0):
        raise ValueError('Cross-package deduplication is not complete')
    from .current_chain import _meta,read_chain_scope,assert_current_result_path
    scope=read_chain_scope(_meta(registry)['manifest']['path'])
    rows=[];seen=set();sources={};stage_counts={'reviewed_pass':0,'batch_accepted':0,'published':0}
    with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for member in members:
            sid=member['sample_id']
            if sid in seen:raise ValueError('Duplicate effective sample identity')
            seen.add(sid)
            original=con.execute('SELECT a.evidence_json,t.status,r.annotation_sha256 FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key JOIN current_chain_results r ON r.sample_id=a.sample_id WHERE a.sample_id=?',(sid,)).fetchone()
            if not original:raise ValueError('Effective member is not owned by current project')
            if original['status'] not in stage_counts:continue
            annotation=assert_current_result_path(scope,Path(member['sample_path'])/'annotation.json')
            from .batch_core import file_sha
            if file_sha(annotation)!=original['annotation_sha256']:raise ValueError('Accepted original annotation changed')
            # Verify each member against its owning actual QC report, including
            # prior batches; current cumulative mechanical PASS is not semantic PASS.
            review=con.execute('SELECT decision,evidence_json FROM m4_reviews WHERE sample_id=?',(sid,)).fetchone()
            admission=con.execute('SELECT quality_status,report_json FROM m4_quality_admissions WHERE sample_id=?',(sid,)).fetchone() if 'm4_quality_admissions' in tables else None
            ref=json.loads(admission['report_json']) if admission and admission['quality_status']=='ACCEPTED_BY_BATCH_POLICY' else None
            if ref is None and review and review['decision']=='pass':
                refs=json.loads(review['evidence_json']);ref=next((r for r in refs if load_json(r['path']).get('program')=='quality-inspector'),None)
            if ref is None:raise ValueError('Accepted registry status lacks original admission/review receipt')
            key=object_sha256(ref)
            if key not in sources:
                bound,_=_bound_quality_report([ref]);prod=bound.get('production_quality')
                if prod:
                    checked=quality_report(bound,prod['effective_set'],prod['cross_package_report'],prod.get('production_handoff'))
                    if checked!=prod:raise ValueError('Member original batch admission changed')
                    sources[key]={r['sample_id'] for r in checked['rows'] if r['quality_admission']=='ACCEPTED_BY_BATCH_POLICY'}
                else:
                    sources[key]={r['sample_id'] for r in bound['samples'] if r['status']=='PASS'} if bound['status']=='PASS' else set()
            if sid not in sources[key]:raise ValueError('Sample no longer accepted by its original receipt')
            value=load_json(annotation)
            n=sum(s['action']['action_type'] not in ('wait','complete') for s in value['steps'])
            rows.append({'sample_id':sid,'effective_steps':n,'status':original['status'],'source':ref})
            stage_counts[original['status']]+=1
    result={'status':'KNOWN' if rows else 'UNKNOWN',**band_counts(rows),'source':reference,
            'effective_set':claimed['effective_set'],'cross_package_report':claimed['cross_package_report'],
            'stage_counts':stage_counts,'human_review_inferred':False,'customer_acceptance':'UNKNOWN'}
    return result


def _accepted(registry,reference):
    # Arithmetic fixture indexes are deliberately not production admissions.
    # Only the existing report/registry/effective-set binding gate may provide
    # the denominator used by the formal candidate entry.
    value=load_json(reference['path']);verify_evidence([reference])
    if value.get('program')!='quality-inspector':
        raise ValueError('Formal band advice requires an original quality-inspector admission report')
    return _actual_accepted(registry,reference)


def bind_accepted_set(registry,reference):
    facts=_accepted(registry,reference);project=_project(registry)
    with sqlite3.connect(Path(registry)) as con:
        con.execute('INSERT INTO m4_events(scope_id,campaign_id,event_type,task_key,attempt_id,at,payload_json) VALUES(?,?,?,?,?,?,?)',
                    ('band-budget','band-budget',ACCEPTED,None,None,time.time(),json.dumps({'project':project,'reference':reference},ensure_ascii=False)))
    return facts


def _refresh(registry,key,project):
    """Read changed evidence outside writer lock, apply only if cursor unchanged."""
    with sqlite3.connect(Path(registry)) as con:
        con.row_factory=sqlite3.Row;_schema(con)
        state=con.execute('SELECT * FROM m4_band_state WHERE project_key=?',(key,)).fetchone()
        cursor=state['cursor'] if state else 0
        events=list(con.execute('SELECT * FROM m4_events WHERE event_id>? ORDER BY event_id',(cursor,)))
        high=max([e['event_id'] for e in events] or [cursor])
        metrics=json.loads(state['metrics_json']) if state else distribution()
        relevant=[e for e in events if e['event_type'] in ('attempt_finished','review_recorded','batch_quality_recorded','pool_qc_result',ACCEPTED)]
        # First import and subsequent changed rows only. No original PNG hash or
        # broad pending-file scan happens on each candidate reservation.
        if not state:
            changed=list(con.execute('SELECT a.*,t.status task_status FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key'))
        else:
            ids={e['attempt_id'] for e in relevant if e['attempt_id']}
            ids.update(r[0] for e in relevant if e['task_key'] for r in con.execute('SELECT attempt_id FROM m4_attempts WHERE task_key=?',(e['task_key'],)))
            changed=[con.execute('SELECT a.*,t.status task_status FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.attempt_id=?',(i,)).fetchone() for i in ids]
        old={r['attempt_id']:con.execute('SELECT * FROM m4_band_sample_cache WHERE project_key=? AND attempt_id=?',(key,r['attempt_id'])).fetchone() for r in changed if r is not None}
        imported=con.execute('SELECT payload_json FROM m4_events WHERE event_type=? ORDER BY event_id DESC LIMIT 1',(ACCEPTED,)).fetchone()
        latest_qc=next((json.loads(e['payload_json']).get('report') for e in reversed(relevant) if e['event_type'] in ('pool_qc_result','batch_quality_recorded')),None)
        accepted_ref=json.loads(imported[0])['reference'] if imported else latest_qc
    updates=[]
    for row in changed:
        if row is None:continue
        prior=old.get(row['attempt_id'])
        status=row['task_status'] if row['task_status'] in ('reviewed_pass','batch_accepted','published') else row['status']
        if prior and prior['status']==status and prior['evidence_json']==row['evidence_json']:continue
        n=None;source=None
        if status=='collected_pending_review':
            for ref in json.loads(row['evidence_json']):
                try:
                    verify_evidence([ref]);value=load_json(ref['path']);terminal_ref=value.get('terminal')
                    if terminal_ref:
                        verify_evidence([terminal_ref]);terminal=load_json(terminal_ref['path'])
                        n=terminal['effective_steps'];source=terminal_ref;break
                except (OSError,ValueError,KeyError,TypeError):continue
        updates.append((key,row['attempt_id'],status,row['evidence_json'],n,json.dumps(source)))
    if accepted_ref and (not state or any(e['event_type'] in (ACCEPTED,'pool_qc_result','batch_quality_recorded','review_recorded') for e in relevant)):
        try:metrics['accepted']=_accepted(registry,accepted_ref)
        except (OSError,ValueError,KeyError,TypeError) as error:
            metrics['accepted']={'status':'UNKNOWN','denominator':None,'reason':str(error),'source':accepted_ref}
    with sqlite3.connect(Path(registry)) as con:
        con.row_factory=sqlite3.Row;con.execute('BEGIN IMMEDIATE')
        current=con.execute('SELECT cursor FROM m4_band_state WHERE project_key=?',(key,)).fetchone()
        if current and current['cursor']!=cursor:return False
        for update in updates:con.execute('INSERT OR REPLACE INTO m4_band_sample_cache VALUES(?,?,?,?,?,?)',update)
        if updates or not current:
            pending={'denominator':0,'counts':{'five':0,'long':0,'short':0,'outside':0},'unknown_count':0}
            for row in con.execute("SELECT effective_steps,COUNT(*) n FROM m4_band_sample_cache WHERE project_key=? AND status='collected_pending_review' GROUP BY effective_steps",(key,)):
                n=row['effective_steps'];count=row['n']
                if n is None:
                    pending['unknown_count']+=count;pending['denominator']+=count;continue
                pending['denominator']+=count;pending['counts']['five' if n==5 else 'long' if n>=6 else 'short' if 1<=n<5 else 'outside']+=count
            pending['distribution_status']='UNKNOWN' if pending['unknown_count'] else 'KNOWN' if pending['denominator'] else 'EMPTY'
            metrics['pending_review']=pending
        if current:con.execute('UPDATE m4_band_state SET cursor=?,metrics_json=? WHERE project_key=?',(high,json.dumps(metrics,ensure_ascii=False),key))
        else:con.execute('INSERT INTO m4_band_state VALUES(?,?,?,?,?)',(key,0,0,high,json.dumps(metrics,ensure_ascii=False)))
    return True


def reserve(registry,task,attempt):
    from .closing_policy import VERSION as CONTINUOUS
    if task.get('fragment',{}).get('ending_policy') == CONTINUOUS:
        return {'protocol':'continuous-consumer-1','assigned_band':None,'project':None,
                'assignment_basis':'natural goal; no band quotas'}
    project=_project(registry);key=object_sha256(project)
    with sqlite3.connect(Path(registry)) as con:
        _schema(con)
        prior=con.execute('SELECT budget_json FROM m4_band_reservations WHERE project_key=? AND task_id=?',(key,task['task_id'])).fetchone()
        if prior:return json.loads(prior[0])
    _refresh(registry,key,project)  # A newer competing snapshot already covers our cursor; reuse it under the short reservation transaction.
    with sqlite3.connect(Path(registry)) as con:
        con.row_factory=sqlite3.Row;con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT budget_json FROM m4_band_reservations WHERE project_key=? AND task_id=?',(key,task['task_id'])).fetchone()
        if prior:return json.loads(prior[0])
        state=con.execute('SELECT * FROM m4_band_state WHERE project_key=?',(key,)).fetchone();budget=json.loads(state['metrics_json'])
        five,long=state['five_count'],state['long_count'];ordinal=five+long+1
        inflight=list(con.execute("SELECT COALESCE(r.locked_band,r.band) band,COUNT(*) n FROM m4_band_reservations r JOIN m4_attempts a ON a.attempt_id=r.attempt_id WHERE r.project_key=? AND a.status IN ('reserved','running') GROUP BY COALESCE(r.locked_band,r.band)",(key,)))
        flight={r['band']:r['n'] for r in inflight}
        if budget['accepted']['status']=='KNOWN':
            accepted=budget['accepted'];n=accepted['denominator'];counts=accepted['counts']
            deficits={b:round((n+sum(flight.values())+1)*ratio-counts[b]-flight.get(b,0),4) for b,ratio in [('five',.8),('long',.19)]}
            band=max(('five','long'),key=lambda b:(deficits[b],b=='five'));budget['deficits']=deficits
            short=counts['short'];budget['short_reserve']={'status':'KNOWN','numerator':short,'denominator':n,
                'ratio':short/n,'limit':.01,'remaining_slots':max(0,int(n*.01)-short),
                'over_limit_count':max(0,short-int(n*.01)),'qc_external_limit_unchanged':.02}
            basis='explicit admitted effective-set deficit minus current in-flight reservations'
        else:
            band='long' if long<int(ordinal*19/99) else 'five'
            budget['short_reserve']={'status':'UNKNOWN','denominator':None,'limit':.01,'qc_external_limit_unchanged':.02}
            basis='accepted denominator UNKNOWN; persistent project planning cadence 80:19; short reserve only'
        objective=task.get('fragment',{}).get('session_objective',{}).get('objective',{})
        if objective.get('preferred_band') in ('five','long'):
            band=objective['preferred_band'];basis='explicit frozen user objective; '+basis
        budget.update(protocol=VERSION,project=project,reservation_ordinal=ordinal,assigned_band=band,
            assignment_basis=basis,planned={'denominator':five+long,'counts':{'five':five,'long':long,'short':0}},
            in_flight=flight,stage_meanings={'planned':'host reservations','pending_review':'official saved effective steps',
                                           'accepted':'existing reviewed_pass/batch_accepted receipts in deduplicated effective set'})
        payload={'project_key':key,'task_id':task['task_id'],'attempt_id':attempt['attempt_id'],'band':band,'budget':budget}
        encoded=json.dumps(budget,ensure_ascii=False)
        con.execute('INSERT INTO m4_band_reservations(project_key,task_id,attempt_id,band,budget_json) VALUES(?,?,?,?,?)',(key,task['task_id'],attempt['attempt_id'],band,encoded))
        con.execute('UPDATE m4_band_state SET five_count=five_count+?,long_count=long_count+? WHERE project_key=?',(int(band=='five'),int(band=='long'),key))
        con.execute('INSERT INTO m4_events(scope_id,campaign_id,event_type,task_key,attempt_id,at,payload_json) VALUES(?,?,?,?,?,?,?)',
                    (attempt['scope_id'],attempt['campaign_id'],EVENT,attempt['task_key'],attempt['attempt_id'],time.time(),json.dumps(payload,ensure_ascii=False)))
        return budget


def freeze(registry,task,attempt_id,band,reason):
    """Lock the grounded band before first business dispatch, preserving proposal."""
    if band not in ('five','long','short') or not reason:raise ValueError('Grounded band and reason required')
    project=_project(registry);key=object_sha256(project)
    with sqlite3.connect(Path(registry)) as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT attempt_id,band,locked_band FROM m4_band_reservations WHERE project_key=? AND task_id=?',(key,task['task_id'])).fetchone()
        if not row or row[0]!=attempt_id:raise ValueError('Original band reservation/attempt mismatch')
        if row[2] is not None:
            if row[2]!=band:raise ValueError('Frozen band cannot be changed')
            return
        if row[1]=='five' and band=='long':raise ValueError('Five cannot be raised to long')
        con.execute('UPDATE m4_band_reservations SET locked_band=? WHERE project_key=? AND task_id=?',(band,key,task['task_id']))
        con.execute('INSERT INTO m4_events(scope_id,campaign_id,event_type,task_key,attempt_id,at,payload_json) VALUES(?,?,?,?,?,?,?)',
            ('band-budget','band-budget','conditional_plan_band_frozen_1',task['task_id'],attempt_id,time.time(),json.dumps(
                {'proposed_band':row[1],'locked_band':band,'reason':reason,'long_deficit_retained':row[1]=='long' and band!='long'},ensure_ascii=False)))
