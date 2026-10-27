#!/usr/bin/env python3
"""Preserve immutable capture bytes while classifying reviewed quality failures.

Only manifest membership/status and regenerated metadata change. No registry is opened.
The supplied AI/human review is evidence, never an inferred approval of the remainder.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone

CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:sys.path.insert(0,str(CODE_ROOT))


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path,data):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def atomic_bytes(path,data):
    path=Path(path);temp=path.with_name('.'+path.name+'.quality-reject.tmp')
    with temp.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)


def inventory(batch):
    result={}
    for name in ['samples','evidence']:
        root=batch/name
        if not root.is_dir() or root.is_symlink():raise ValueError('Missing/nonphysical source directory: '+name)
        for path in sorted(root.rglob('*')):
            if path.is_symlink():raise ValueError('Source symlink is not allowed: '+str(path))
            if path.is_file():result[path.relative_to(batch).as_posix()]=sha(path)
    return result


REVIEW_CHECKS=('visual_alignment','terminal_semantics','language','privacy','substantive_difference')


def duplicate_failure(batch,decision,annotation,proof):
    """Bind a machine near-image exclusion to its real report and recomputed pixels.

    This is a conservative exclusion of a local proxy candidate, never an AI
    semantic failure or a claim about the unavailable customer hash algorithm.
    """
    source=decision.get('actual_qc_source',{});original=Path(source.get('path',''))
    if not original.is_file() or original.is_symlink() or sha(original)!=source.get('sha256'):
        raise ValueError('Actual duplicate QC report hash binding is missing or wrong')
    report=json.loads(original.read_text());pair=decision.get('duplicate_pair',[])
    if (decision.get('duplicate_route')!='route3' or len(pair)!=2 or len(set(pair))!=2
            or decision['sample_id'] not in pair):raise ValueError('Explicit route3 duplicate pair required')
    candidates=[r for r in report.get('duplicates',{}).get('route3',{}).get('candidates',[])
                if set(r.get('sample_ids',[]))==set(pair)]
    if len(candidates)!=1:raise ValueError('Duplicate pair is absent or nonunique in actual QC report')
    candidate=candidates[0];distances=[candidate.get('first_hamming'),candidate.get('last_hamming')]
    if any(type(n) is not int or not 0<=n<=4 for n in distances) or distances!=decision.get('duplicate_distances'):
        raise ValueError('Duplicate threshold or reported distances mismatch')
    dataset=Path(report.get('dataset','')).resolve();rows=report.get('samples',[]);annotations=[]
    for sid in pair:
        records=[r for r in rows if r.get('sample_id')==sid]
        if len(records)!=1:raise ValueError('Duplicate pair sample is absent in QC report')
        record=records[0];sample=Path(record.get('sample_path','')).resolve();path=sample/'annotation.json'
        if not sample.is_relative_to(dataset) or not path.is_file() or path.is_symlink():
            raise ValueError('Duplicate QC sample path is invalid')
        if sha(path)!=record.get('annotation_sha256'):raise ValueError('Duplicate QC annotation binding mismatch')
        data=json.loads(path.read_text());steps=data.get('steps',[])
        if data.get('sample_id')!=sid or not steps:raise ValueError('Duplicate QC sample identity mismatch')
        for step in steps:
            for field in ('image_path','ui_tree_path'):
                relative=step.get(field,'');file=sample/relative
                if (not relative or not file.resolve().is_relative_to(sample) or file.is_symlink()
                        or not file.is_file() or sha(file)!=record.get('evidence_sha256',{}).get(relative)):
                    raise ValueError('Duplicate QC image/tree binding mismatch')
        annotations.append((sample,data))
        if sid==decision['sample_id']:
            raw=batch/'samples'/sid
            if sha(raw/'annotation.json')!=sha(path):raise ValueError('Duplicate QC differs from original annotation')
            if decision.get('final_frame')!=len(steps):raise ValueError('Duplicate original frame count mismatch')
            required={f'samples/{sid}/annotation.json':sha(raw/'annotation.json')}
            required.update({f'samples/{sid}/{s[k]}':sha(raw/s[k]) for s in steps for k in ('image_path','ui_tree_path')})
            required.update({f'evidence/{sid}/step_{s["step_id"]:03}.json':sha(batch/'evidence'/sid/f'step_{s["step_id"]:03}.json') for s in steps})
            if any(proof.get(k)!=v for k,v in required.items()):raise ValueError('Every duplicate original frame must be bound')
    from PIL import Image
    def dhash(path):
        with Image.open(path) as im:
            values=list(im.convert('L').resize((9,8),Image.Resampling.LANCZOS).getdata())
        h=0
        for y in range(8):
            for x in range(8):h=(h<<1)|int(values[y*9+x]>values[y*9+x+1])
        return h
    observed=[]
    for index in (0,-1):
        hashes=[dhash(sample/data['steps'][index]['image_path']) for sample,data in annotations]
        observed.append((hashes[0]^hashes[1]).bit_count())
    if observed!=distances:raise ValueError('Duplicate distances disagree with actual image pixels')


def reviewed_failure(batch,decision,annotation,proof):
    """Validate an actual independent all-frame AI FAIL, without inventing goal timing."""
    source=decision.get('actual_review_source',{})
    original=Path(source.get('path',''));path=original.resolve()
    if not path.is_file() or original.is_symlink() or sha(path)!=source.get('sha256'):
        raise ValueError('Actual AI review source hash binding is missing or wrong')
    review=json.loads(path.read_text())
    if review.get('schema_version')!='qc-review-1':raise ValueError('Actual AI review source schema is invalid')
    records=[r for r in review.get('records',[]) if r.get('sample_id')==decision['sample_id']]
    if len(records)!=1:raise ValueError('Actual AI review sample must be unique')
    record=records[0];reviewer=record.get('reviewer',{})
    if reviewer.get('kind')!='ai' or not str(reviewer.get('name','')).strip():
        raise ValueError('Actual independent AI reviewer identity is required')
    steps=annotation.get('steps',[]);numbers=list(range(1,len(steps)+1))
    if not numbers or [s.get('step_id') for s in steps]!=numbers or decision.get('final_frame')!=len(steps):
        raise ValueError('Actual AI review final frame differs from original annotation')
    provenance=record.get('provenance',{})
    observations=record.get('step_observations',[])
    if (provenance.get('frames_viewed')!=numbers or not str(provenance.get('description','')).strip()
            or [r.get('step_id') for r in observations]!=numbers
            or any(not isinstance(r.get('note'),str) or not r['note'].strip() for r in observations)):
        raise ValueError('Actual AI review requires observations of every original frame')
    checks=record.get('checks',{})
    if set(checks)!=set(REVIEW_CHECKS) or any(
            not isinstance(checks[k],dict) or checks[k].get('status') not in ('PASS','FAIL')
            or not isinstance(checks[k].get('note'),str) or not checks[k]['note'].strip()
            for k in REVIEW_CHECKS):
        raise ValueError('Actual AI review requires five explicit judgments with reasons')
    failed=[k for k in REVIEW_CHECKS if checks[k]['status']=='FAIL']
    if not failed or decision.get('failed_checks')!=failed:
        raise ValueError('Actual AI FAIL source is empty or differs from rejection')
    actual_reason='；'.join(k+': '+checks[k]['note'] for k in failed)
    if decision.get('reason')!=actual_reason:raise ValueError('Rejection reason differs from actual AI FAIL source')
    sid=decision['sample_id'];sample=batch/'samples'/sid
    expected={}
    for step in steps:
        for field in ('image_path','ui_tree_path'):
            relative=step.get(field,'');candidate=sample/relative
            if (not relative or Path(relative).is_absolute() or not candidate.resolve().is_relative_to(sample)
                    or not candidate.is_file() or candidate.is_symlink()):
                raise ValueError('Actual AI review original image/tree is missing')
            expected[relative]=sha(candidate)
    if record.get('annotation_sha256')!=sha(sample/'annotation.json') or record.get('evidence_sha256')!=expected:
        raise ValueError('Actual AI review annotation/image/tree hash binding mismatch')
    required={f'samples/{sid}/annotation.json':sha(sample/'annotation.json')}
    required.update({f'samples/{sid}/{name}':digest for name,digest in expected.items()})
    required.update({f'evidence/{sid}/step_{n:03}.json':sha(batch/'evidence'/sid/f'step_{n:03}.json') for n in numbers})
    if any(proof.get(name)!=digest for name,digest in required.items()):
        raise ValueError('Every original annotation/image/tree/raw frame must be review-bound')


def preflight(batch,review_path,output):
    if output.exists():raise ValueError('Output already exists; repeated classification is refused')
    review=json.loads(review_path.read_text());manifest=json.loads((batch/'manifest.json').read_text())
    if review.get('schema_version')!='webcollect-quality-rejection-review-1':raise ValueError('Unknown review schema')
    if review.get('batch')!=str(batch):raise ValueError('Review is bound to a different batch')
    machine=all(d.get('failure_type')=='machine_duplicate_rejection' for d in review.get('decisions',[]))
    kind='machine_quality_rejection_not_human_approval' if machine else 'AI_quality_rejection_not_human_approval'
    if review.get('review_kind')!=kind:raise ValueError('Explicit review authorship is required')
    if manifest.get('collection_status')!='finished_pending_review' or manifest.get('active_task'):
        raise ValueError('Only finished immutable capture batches can be classified')
    if manifest.get('quality_classification') and any(d.get('failure_type') not in ('reviewed_quality_failure','machine_duplicate_rejection') for d in review.get('decisions',[])):
        raise ValueError('Batch was already quality classified; early-goal branch cannot repeat')
    for filename in ['manifest.json','metadata.csv','plan.json']:
        if not (batch/filename).is_file() or sha(batch/filename)!=review['input_files_sha256'].get(filename):
            raise ValueError('Review binding mismatch: '+filename)
    samples=manifest.get('samples',[])
    if samples!=review.get('original_samples') or len(samples)!=len(set(samples)):raise ValueError('Original sample membership changed')
    actual=sorted(path.name for path in (batch/'samples').iterdir())
    if actual!=sorted(samples):raise ValueError('Manifest/sample directories differ')
    current=inventory(batch)
    if current!=review.get('source_files_sha256'):raise ValueError('Source payload hash/inventory binding mismatch')
    decisions=review.get('decisions',[]);ids=[d.get('sample_id') for d in decisions]
    all_actual=all(d.get('failure_type') in ('reviewed_quality_failure','machine_duplicate_rejection') for d in decisions)
    if (not decisions or len(ids)!=len(set(ids)) or not set(ids)<=set(samples)
            or (not all_actual and not set(ids)<set(samples))):
        raise ValueError('Reject IDs must be unique existing members; early-goal branch must leave a pending remainder')
    attempts=manifest.get('attempts',[])
    for decision in decisions:
        sid=decision['sample_id']
        if not re.fullmatch(r'S\d{6}_sample_\d{6,}',sid):raise ValueError('Invalid sample ID')
        if decision.get('decision')!='QUALITY_REJECT' or not decision.get('reason'):raise ValueError('Explicit per-sample rejection is required')
        rows=[a for a in attempts if a.get('sample_id')==sid]
        if len(rows)!=1 or rows[0].get('status')!='collected_pending_review' or rows[0].get('task_id')!=decision.get('task_id'):
            raise ValueError('Attempt identity/status binding mismatch: '+sid)
        if (batch/'rejected'/sid).exists():raise ValueError('Rejected destination already exists: '+sid)
        proof=decision.get('evidence_files_sha256',{})
        if not proof:raise ValueError('Bound per-frame review evidence is required')
        annotation=json.loads((batch/'samples'/sid/'annotation.json').read_text())
        if annotation.get('task_instruction')!=decision.get('original_task_instruction'):raise ValueError('Review instruction differs from original sample')
        failure_type=decision.get('failure_type','early_goal_completion')
        if failure_type=='reviewed_quality_failure':
            reviewed_failure(batch,decision,annotation,proof)
        elif failure_type=='machine_duplicate_rejection':
            duplicate_failure(batch,decision,annotation,proof)
        elif failure_type=='early_goal_completion':
            if not (isinstance(decision.get('first_goal_frame'),int) and 1<=decision['first_goal_frame']<decision.get('final_frame',0)):
                raise ValueError('Early completion evidence is missing')
            literals=decision.get('terminal_visible_literals',[])
            if not literals or any(not isinstance(v,str) or not v.strip() for v in literals):raise ValueError('Terminal goal evidence is required')
            frames=[]
            for number in range(1,decision['final_frame']+1):
                relative=f'evidence/{sid}/step_{number:03}.json'
                if relative not in proof:raise ValueError('Every original frame must be review-bound')
                state=json.loads((batch/relative).read_text()).get('state',{})
                frames.append(all(literal in state.get('visible_text','') for literal in literals))
            first=next((i+1 for i,v in enumerate(frames) if v),None)
            if first!=decision['first_goal_frame'] or not frames[-1]:raise ValueError('Claimed early goal timing disagrees with bound raw frames')
        else:raise ValueError('Unknown quality failure type')
        for relative,digest in proof.items():
            path=batch/relative
            if path.resolve().is_relative_to(batch) is False or not path.is_file() or sha(path)!=digest:
                raise ValueError('Audit evidence binding mismatch: '+relative)
    return review,manifest,current


def classify(batch,review_path,output,metadata_exporter=None):
    batch=Path(batch).resolve();review_path=Path(review_path).resolve();output=Path(output).resolve()
    if output.is_relative_to(batch):raise ValueError('Audit output must be outside the source batch')
    review,manifest,source_hashes=preflight(batch,review_path,output)
    if metadata_exporter is None:
        from webcollect.metadata import export_metadata
        metadata_exporter=export_metadata
    output.mkdir(parents=True);before=output/'before';before.mkdir()
    for name in ['manifest.json','metadata.csv','plan.json']:shutil.copyfile(batch/name,before/name)
    shutil.copyfile(review_path,before/'quality_review.json')
    write_json(before/'source_files_sha256.json',source_hashes)
    evidence_dir=before/'reviewed_steps';evidence_dir.mkdir()
    for decision in review['decisions']:
        sid=decision['sample_id'];dest=evidence_dir/sid;dest.mkdir()
        for relative in decision['evidence_files_sha256']:
            path=batch/relative
            if path.suffix=='.json':
                target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        if decision.get('failure_type')=='reviewed_quality_failure':
            source=decision['actual_review_source'];target=before/'actual_ai_reviews'/(source['sha256']+'.json')
            target.parent.mkdir(exist_ok=True)
            if not target.exists():shutil.copyfile(source['path'],target)
            if sha(target)!=source['sha256']:raise ValueError('Actual AI review changed during sealing')
        elif decision.get('failure_type')=='machine_duplicate_rejection':
            source=decision['actual_qc_source'];target=before/'actual_machine_qc'/(source['sha256']+'.json')
            target.parent.mkdir(exist_ok=True)
            if not target.exists():shutil.copyfile(source['path'],target)
            if sha(target)!=source['sha256']:raise ValueError('Actual machine QC changed during sealing')
    before_hashes={p.relative_to(before).as_posix():sha(p) for p in sorted(before.rglob('*')) if p.is_file()}
    write_json(output/'before_files_sha256.json',before_hashes)
    # Recheck after sealing and before the first source mutation.
    if inventory(batch)!=source_hashes or any(sha(batch/n)!=review['input_files_sha256'][n] for n in ['manifest.json','metadata.csv','plan.json']):
        raise ValueError('Source changed during sealing; no source mutation performed')
    rejected={d['sample_id']:d for d in review['decisions']};moved=[];review_sha=sha(before/'quality_review.json')
    original_count=len(manifest['attempts']);original_samples=list(manifest['samples'])
    try:
        (batch/'rejected').mkdir(exist_ok=True)
        for sid in rejected:
            (batch/'samples'/sid).rename(batch/'rejected'/sid);moved.append(sid)
        manifest['samples']=[sid for sid in original_samples if sid not in rejected]
        for attempt in manifest['attempts']:
            if attempt['sample_id'] not in rejected:continue
            decision=rejected[attempt['sample_id']]
            attempt['capture_status_before_quality_review']=attempt['status'];attempt['status']='rejected'
            attempt['error']=decision['reason']
            rejection={'reason':decision['reason'],'review_sha256':review_sha,'review_path':str((before/'quality_review.json').resolve()),'review_kind':review['review_kind'],'failure_type':decision.get('failure_type','early_goal_completion'),'final_frame':decision['final_frame'],'raw_bytes_preserved':True}
            if rejection['failure_type']=='early_goal_completion':rejection['first_goal_frame']=decision['first_goal_frame']
            elif rejection['failure_type']=='reviewed_quality_failure':
                rejection['actual_review_source_sha256']=decision['actual_review_source']['sha256']
                rejection['failed_checks']=decision['failed_checks']
                rejection['actual_review_source_path']=str((before/'actual_ai_reviews'/(decision['actual_review_source']['sha256']+'.json')).resolve())
            else:
                rejection.update(actual_qc_source_sha256=decision['actual_qc_source']['sha256'],
                    actual_qc_source_path=str((before/'actual_machine_qc'/(decision['actual_qc_source']['sha256']+'.json')).resolve()),
                    duplicate_route=decision['duplicate_route'],duplicate_pair=decision['duplicate_pair'],
                    duplicate_distances=decision['duplicate_distances'],customer_algorithm_equivalence='UNKNOWN',
                    ai_semantic_failure_claimed=False)
            attempt['quality_rejection']=rejection
        if manifest.get('quality_classification'):
            manifest.setdefault('quality_classification_history',[]).append(manifest['quality_classification'])
        manifest['quality_classification']={'review_sha256':review_sha,'audit_directory':str(output),'rejected_samples':list(rejected),'original_sample_count':len(original_samples),'attempt_count_unchanged':original_count,'remaining_status':'pending_review','human_approval_claimed':False,'timestamp':datetime.now(timezone.utc).isoformat()}
        atomic_bytes(batch/'manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
        metadata_path=output/'metadata-regenerated.csv'
        if not manifest['samples']:
            # A completely rejected capture batch remains an audit population,
            # never an empty customer package. Keep the ordinary export gate strict.
            from webcollect.metadata import COLUMNS
            if any((batch/'samples').iterdir()):raise ValueError('Empty accepted membership differs from sample directories')
            with metadata_path.open('x',newline='',encoding='utf-8') as stream:
                csv.DictWriter(stream,fieldnames=COLUMNS).writeheader()
        else:metadata_exporter(batch,metadata_path)
        with (output/'metadata-regenerated.csv').open(newline='',encoding='utf-8') as stream:
            metadata_ids=[r['sample_id'] for r in csv.DictReader(stream)]
        if metadata_ids!=manifest['samples']:raise ValueError('Regenerated metadata membership mismatch')
        os.replace(output/'metadata-regenerated.csv',batch/'metadata.csv')
        mappings={}
        for relative,digest in source_hashes.items():
            parts=Path(relative).parts
            resolved=Path('rejected',*parts[1:]) if parts[0]=='samples' and parts[1] in rejected else Path(relative)
            if not (batch/resolved).is_file() or sha(batch/resolved)!=digest:raise ValueError('Preservation verification failed: '+relative)
            if resolved.as_posix()!=relative:mappings[relative]=resolved.as_posix()
        if len(manifest['attempts'])!=original_count:raise ValueError('Attempt denominator changed')
        write_json(output/'moved_files.json',mappings)
        receipt={'status':'PASS','operation':'preserving_quality_rejection','batch':str(batch),'review_sha256':review_sha,'before_index_sha256':sha(output/'before_files_sha256.json'),'original_sample_count':len(original_samples),'rejected_count':len(rejected),'remaining_pending_review':len(manifest['samples']),'attempt_count_before':original_count,'attempt_count_after':len(manifest['attempts']),'all_original_sample_and_evidence_file_hashes_preserved':True,'preserved_file_count':len(source_hashes),'manifest_sha256_after':sha(batch/'manifest.json'),'metadata_sha256_after':sha(batch/'metadata.csv'),'ledger_opened_or_modified_by_script':False,'remaining_qualified_or_approved_claimed':False}
        write_json(output/'receipt.json',receipt);return receipt
    except Exception as error:
        for sid in reversed(moved):
            if (batch/'rejected'/sid).exists() and not (batch/'samples'/sid).exists():(batch/'rejected'/sid).rename(batch/'samples'/sid)
        for name in ['manifest.json','metadata.csv']:atomic_bytes(batch/name,(before/name).read_bytes())
        write_json(output/'failure.json',{'status':'FAIL','error':str(error),'source_membership_and_manifest_rolled_back':True})
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    try:
        if not a.execute:
            review,manifest,files=preflight(a.batch.resolve(),a.review.resolve(),a.output.resolve());print(json.dumps({'status':'READY_NOT_EXECUTED','reject_count':len(review['decisions']),'original_samples':len(manifest['samples']),'bound_source_files':len(files)}));return
        print(json.dumps(classify(a.batch,a.review,a.output),ensure_ascii=False))
    except Exception as error:print(json.dumps({'status':'FAIL','error':str(error)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':main()
