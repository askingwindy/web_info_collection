"""Read-only historical wire/PNG/DOM measurement. Never executes a trajectory.

Historical runtime/QC SQLite databases are opened only with mode=ro. Output must
be a new directory. No provider/browser/product entry point is called.
"""
import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import socket
import sqlite3
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'projects/code'),str(ROOT/'projects/site-planner'),str(ROOT/'projects/quality-inspector')]
from webcollect.batch_core import load_json,file_sha
from webcollect.planning import object_sha256
from webcollect.banded_plan import Controller,tools,bind_target,proves,region_evidence,distribution
from webcollect.inference_image import derive
from webcollect.agent_observation import project


def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)


def ref(path):return {'path':str(Path(path).resolve()),'sha256':file_sha(path)}


def size(value):return len(json.dumps(value,ensure_ascii=False,sort_keys=True))


def classify(p,result,ob):
    if result.get('state')=='unknown':return 'REFUSE_UNKNOWN','Original request UNKNOWN is retained; never replayed or assigned invented usage.'
    name=(result.get('result') or {}).get('name')
    args=(result.get('result') or {}).get('arguments') or {}
    if name=='finish':return 'HOST_FINISH_IF_ENDPOINT_PROVED','Actual trusted final state and the frozen endpoint must agree; archived finish is not a new receipt.'
    if name=='act':
        step=args.get('step') or {};cid=step.get('control_id');control=ob['controls'].get(cid,{})
        truth=control.get('actions',{}).get(step.get('action'),{})
        if not cid or truth.get('status')=='PROVEN':return 'HOST_DIRECT_IF_PLANNED','Recorded authorized action can use the existing dispatcher after fresh pre-dispatch verification.'
        if truth.get('reason')=='MISSING_TARGET_PROBE':return 'HOST_LOCATE_AND_PROBE_IF_UNIQUE','A fresh directed capture is still necessary; archived frames do not perform that capture.'
        return 'MODEL_REQUIRED','Current target is absent/ambiguous or its action is not proven.'
    if name=='inspect':
        if args.get('kind')=='search':return 'HOST_LOCATE_AND_PROBE_IF_UNIQUE','Host full-index semantic match plus directed probe; model decides only among ambiguous matches.'
        return 'HOST_STRUCTURE_THEN_MODEL_IF_VISUAL_GAP','Host can find the business container, but HTML alone does not prove visible rows or goal completion.'
    if name=='observe':
        if args.get('focus_control_id')=='null':return 'REFUSE_INVALID_READ','The new path does not request a provider tool; host observations use explicit null/known current node.'
        return 'HOST_DIRECTED_OBSERVATION','Read-only refresh/probe is hosted; no effective action is added.'
    return 'MODEL_REQUIRED','Business goal/branch has no deterministic owning proof.'


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--output',type=Path,required=True)
    a.add_argument('--cohort',type=Path,default=ROOT/'verify_results/consumer-agent-fifty-round2-parent-20261103-r01/user-stop/partial-cohort-audit.json')
    a.add_argument('--row3',type=Path,default=ROOT/'verify_results/consumer-row3-wire-audit-20261103-r01/metrics.json')
    args=a.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def no_network(*args,**kwargs):raise AssertionError('Read-only measurement forbids network')
    socket.socket.connect=no_network
    audit=load_json(args.cohort);metrics=load_json(args.row3);cohort=load_json(audit['cohort'])
    visited=[r for r in audit['rows'] if r['visits']]
    assert len(visited)==27
    base=Path(metrics['requests'][0]['image']['path']).parent.parents[5]
    for r in visited:
        if not r.get('raw') and r.get('claim_id'):
            paths=list((base/r['claim_id']/'execution/capture/evidence').glob('*/raw'))
            if len(paths)==1:r['raw']=str(paths[0])
    attempts={r['attempt_id']:r for r in visited if r.get('attempt_id')}
    originals={};original_hashes={};requests=[]
    db=Path(cohort['consumer_ledger']).resolve()
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as con:
        con.execute('PRAGMA query_only=ON');con.row_factory=sqlite3.Row
        sql="""SELECT r.id,r.state,r.request_json,r.response,r.usage,j.payload FROM model_requests r
               JOIN jobs j ON j.id=r.job_id WHERE json_extract(r.request_json,'$.http_dispatch')=1 ORDER BY r.started,r.id"""
        for row in con.execute(sql):
            req=json.loads(row['request_json']);attempt=req.get('dispatch_attempt_id')
            if attempt not in attempts:continue
            requests.append((dict(row),req,attempts[attempt]))
    for record,request,candidate in requests:
        if not candidate.get('raw') and request.get('images'):
            image=Path(request['images'][0]['path']).resolve()
            owner=Path(candidate.get('root') or base/candidate['claim_id']).resolve()
            if not image.is_relative_to(owner):raise ValueError('Original image belongs to another candidate root')
            candidate['raw']=str(image.parent)
    by_candidate={r['candidate_id']:[] for r in visited}
    summaries=[];observations={};all_assets=[];wire=[]
    for candidate in visited:
        raw=Path(candidate['raw']) if candidate.get('raw') else None
        obs={}
        if raw and raw.is_dir():
            for p in sorted(raw.glob('*-observation.json')):
                value=load_json(p);ob=project(load_json(value['evidence']['state']['path']),{k:value['evidence'][k] for k in ('image','state','capture')})
                if ob['observation_id']!=value['observation_id']:raise ValueError('Archived observation identity does not reproject exactly')
                obs[ob['observation_id']]=ob
                originals[str(p)]=ref(p)
        observations[candidate['candidate_id']]=obs
    first_seen=set()
    for record,request,candidate in requests:
        p=json.loads(request['text']);attempt=request['dispatch_attempt_id'];cid=candidate['candidate_id']
        if not candidate.get('raw'):
            by_candidate[cid].append({'request_id':record['id'],'classification':'NO_REPLAY_FRAME','reason':'No raw directory in stopped portion'});continue
        original=ref(Path(candidate['raw'])/'boundary.json');boundary=load_json(original['path'])
        ob=observations[cid].get(p['observation']['observation_id'])
        response=json.loads(record['response']) if record['response'] else {}
        result={'state':record['state'],'result':response.get('result') or {}}
        if not ob:
            by_candidate[cid].append({'request_id':record['id'],'classification':'NO_REPLAY_FRAME','reason':'No exact archived observation for this HTTP'});continue
        for r in ob['evidence'].values():originals[r['path']]=r
        event_assets=[]
        trace_path=Path(candidate['raw'])/'trajectory.jsonl'
        trace=[json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        originals[str(trace_path)]=ref(trace_path)
        effective=p['progress']['effective_steps'];prefix=trace[:effective]
        if len(prefix)!=effective:raise ValueError('Original progress is not supported by raw trajectory prefix')
        session=SimpleNamespace(current=ob,root=out/'derived'/cid,task=boundary['task'],attempt_id=attempt,
            context={'collection_facts':p.get('collection_facts') or {}},used={'max_decisions':p['progress']['decisions_used']},
            requested_goal=p.get('requested_goal'),actual_dispatches=p['progress']['actual_actions'],
            trajectory=prefix,page_urls=boundary['task']['fragment']['page_urls'],
            event=lambda kind,**kw:event_assets.append({'kind':kind,**kw}))
        # These are alternate payload projections of actual old observations.
        # There was no historical conditional plan; no future plan or state is invented.
        c=Controller();first=attempt not in first_seen;first_seen.add(attempt)
        if not first:
            c.submitted=True;c.plan={'steps':[],'finish_when':{'kind':'visible_text','text':'UNKNOWN'}}
            c.frozen_band='UNKNOWN';c.target_steps=8;c.last={'tool_result':p.get('last_tool_result') or {}}
        new=c.prompt(session,[{'choice':'replan','meaning':'原归档没有新协议条件路径，须真实规划'}, {'choice':'stop','meaning':'如实结束'}])
        new_user=deepcopy({k:v for k,v in new.items() if k not in ('system','tools','_images')})
        new_user['observation'].pop('image_ref',None)
        if not first:
            new_user['replan_contract']['remaining_effective_limit']='UNKNOWN: no conditional plan was recorded in the old protocol'
            new_user['historical_plan_status']='UNKNOWN; actual action progress is preserved from original raw prefix'
        assert new_user['progress']['effective_steps']==effective
        assert new_user['progress']['actual_dispatches']==p['progress']['actual_actions']
        mode,reason=classify(p,result,ob)
        if first and record['state']!='unknown':mode,reason='MODEL_REQUIRED_FIRST_PLAN','First business path/goal must be model-planned from the actual URL, panorama, rendered nodes and host band.'
        usage=json.loads(record['usage']) if record['usage'] else None
        entry={'request_id':record['id'],'attempt_id':attempt,'candidate_id':cid,
            'observation_id':ob['observation_id'],'old_tool':result['result'].get('name'),
            'classification':mode,'reason':reason,'historical_usage':usage,'new_usage':'NOT_MEASURED',
            'old':{'system_chars':len(request['system']),'tools_chars':size(request.get('tools',[])),
                   'user_chars':len(request['text']),'history_chars':size(request.get('history',[])),
                   'image_bytes':sum(Path(r['path']).stat().st_size for r in request.get('images',[]))},
            'new_projection':{'phase':new['phase'],'system_chars':len(new['system']),
                'tools_chars':size(new['tools']) if 'tools' in new else 0,'tool_choice_present':'tools' in new,
                'user_chars':size(new_user),'history_chars':0,'image_bytes':sum(e['asset']['bytes'] for e in event_assets),
                'payload':new_user,'tools':new.get('tools',[]),
                'limitations':'Projection of actual old frame; no historical conditional plan. Not a counterfactual execution or new receipt.'},
            'image_only_control':{'text_unchanged':True,'tools_unchanged':True,
                'bytes_after':event_assets[0]['asset']['bytes'],'quality':'UNVERIFIED','new_tokens':'UNKNOWN'},
            'would_avoid_model_roundtrip':mode.startswith('HOST_') or mode=='REFUSE_INVALID_READ',
            'avoidance_condition':reason}
        by_candidate[cid].append(entry);wire.append(entry);all_assets.extend(event_assets)
    assert len(requests)==129,(len(requests),len(attempts))
    for candidate in visited:
        records=by_candidate[candidate['candidate_id']]
        summary={k:candidate.get(k) for k in ('order','candidate_id','version','claim_id','attempt_id','entry_url','visits','requests','usage','atomic_dispatches','effective_steps','saved','claim_state','raw')}
        summary.update(replay_http=len(records),classes=dict(Counter(r['classification'] for r in records)),
            part='NO_MODEL_REQUEST_OR_REPLAY' if not records else 'STOPPED_PARTIAL' if candidate['order']==27 else 'OFFLINE_ARCHIVED_ONLY',
            original_stage=candidate.get('stage'),original_stop_reason=candidate.get('stop_reason'),
            original_root_cause=candidate.get('root_cause'),original_failure_class=candidate.get('failure_class'),
            no_replay_reason=None if records else 'No model HTTP for this visited candidate: retain original observation/preflight/routing rejection; no new state or model savings inferred',
            official_saved_receipt=candidate.get('save_receipt'),
            accepted_denominator='UNKNOWN',new_execution=False)
        summaries.append(summary)
    row3=[]
    for historical in metrics['requests']:
        new=next((r for r in wire if r['request_id']==historical['request']),None)
        row3.append({'http':historical['http'],'decision':historical['decision'],'request_id':historical['request'],
                     'historical':historical,'offline_replay':new,
                     'binding':'Original attempt/observation/request IDs retained; never replayed to website'})
    raw=Path(metrics['requests'][0]['image']['path']).parent
    regions=[];compress=[]
    for n in (3,6,10,13):
        state=load_json(raw/f'observation-{n:03}.json');ob=next(o for o in observations[metrics['candidate_id']].values() if o['evidence']['state']['path']==str(raw/f'observation-{n:03}.json'))
        matches=bind_target(ob,{'text':'部门'})
        regions.append({'frame':n,'state':ref(raw/f'observation-{n:03}.json'),'image':ref(raw/f'observation-{n:03}.png'),
            'department_matches':matches,'selected_proved':proves({'kind':'selected','text':'部门'},ob),
            'host_region':region_evidence(state,'政策文件'),
            'html_only':metrics['policy_list_dom'][str(n)],
            'offline_image_inspection':{'visible_policy_rows':0 if n in (3,6) else 5,
                'basis':'Original archived PNG visually inspected by implementation assistant; not independent QC or human review',
                'host_cannot_infer_from_html_or_blank_projection':True}})
    for h in metrics['requests']:
        source=h['image']['path'];variants={}
        for name,kw in [('jpeg1280_q85',{'size':(1280,720)}),('jpeg960_q85',{}),('original_full',{'original':True})]:
            variants[name]=derive(source,out/'compression',**kw)
        if h['http']>=5:
            variants['original_policy_roi']=derive(source,out/'compression',crop=(90,347,1170,720),original=True)
        state_path=Path(source).with_suffix('.json');state=load_json(state_path)
        tiny=[e for e in state['elements'] if e.get('visible') and e.get('text') and e.get('bbox') and e['bbox'][3]-e['bbox'][1]<=16]
        compress.append({'http':h['http'],'source':h['image'],'variants':variants,
            'small_text':{'original_boxes_height_le_16':len(tiny),'downscale':.75,'quality':'UNVERIFIED',
                          'boundary_examples':[{'node':e['element_id'],'bbox':e['bbox'],'text':e['text'][:80]} for e in tiny[:5]]}})
    # Confirm every archived file read as evidence is unchanged.
    unchanged=all(file_sha(r['path'])==r['sha256'] for r in originals.values())
    write(out/'cohort-27.json',summaries);write(out/'wire-129.json',wire);write(out/'row3-20.json',row3)
    write(out/'row3-regions.json',regions);write(out/'compression.json',compress)
    write(out/'sources.json',{'cohort':ref(args.cohort),'row3':ref(args.row3),'evidence':list(originals.values()),
                            'all_unchanged_after_read':unchanged,'sqlite_mode':'ro/query_only','network':'FORBIDDEN'})
    measured={'visited':len(visited),'historical_http':len(requests),'replayable_http':len(wire),
        'new_real_http':0,'new_real_tokens':None,'accepted':{'status':'UNKNOWN','denominator':None},
        'classes':dict(Counter(r['classification'] for r in wire)),
        'first':{'count':sum(r['new_projection']['phase']=='first' for r in wire)},
        'branch':{'count':sum(r['new_projection']['phase']=='branch' for r in wire)},
        'row3_image_bytes':{name:sum(r['variants'][name]['bytes'] for r in compress[1:]) for name in ('jpeg1280_q85','jpeg960_q85','original_full')},
        'scope':'Stopped evidence measurements only. Host eligibility is conditional, not a new execution or net savings claim.'}
    for phase in ('first','branch'):
        items=[r['new_projection'] for r in wire if r['new_projection']['phase']==phase]
        measured[phase].update(mean_user_chars=sum(r['user_chars'] for r in items)/len(items),max_user_chars=max(r['user_chars'] for r in items),
                              mean_tool_chars=sum(r['tools_chars'] for r in items)/len(items))
    write(out/'metrics.json',measured);print(json.dumps(measured,ensure_ascii=False))


if __name__=='__main__':main()
