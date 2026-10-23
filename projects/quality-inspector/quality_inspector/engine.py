"""Independent baseline-driven QC orchestration and evidence review intake."""
import hashlib,json,re
from pathlib import Path
from collections import Counter
from . import __version__
from .format_checks import run as format_run,sample_check,catalog,observations_from_examples
from .duplicates import analyze
from .checksums import verify_manifest
from .preparation_evidence import audit_preparation

SEMANTIC=['visual_alignment','terminal_semantics','language','privacy','substantive_difference']
STATES={'PASS','FAIL','REVIEW_REQUIRED'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def aggregate(states):return 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in states or not states else 'PASS'
def baseline_load(config,samples_override=None):
    config=Path(config).resolve();c=read(config);repo=(config.parent/c['repository_root']).resolve();issues=[];sample_rows=[]
    for item in c['samples']:
        path=Path(samples_override)/Path(item['path']).name if samples_override else repo/item['path']
        for rel,digest in item['files'].items():
            p=path/rel
            if not p.is_file() or sha(p)!=digest:issues.append({'sample':str(path),'file':rel,'reason':'baseline file missing or hash changed'})
        original=sample_check(path)
        annotation=read(path/'annotation.json') if (path/'annotation.json').is_file() else {}
        documented=[]
        # Reference interpretation only, never production validation. Paths are
        # pinned by config above; no sample ID is an exemption selector.
        if isinstance(annotation,dict) and annotation.get('task_type')==[]:
            documented=[{'rule_id':'C03','field':'annotation/task_type','actual':[],
                'source':'request/web操作采集需求/samples/样例说明.md:21',
                'quote':'task_type 是空数组，需求书 §4 要求必填 1–3 个枚举值。',
                'production_waiver':False}]
        residual=[e for e in original['errors'] if not (documented and e['rule_id']=='C03' and e['path']=='annotation/task_type')]
        reference_contract={'status':'FAIL' if residual else 'PASS','scope':'field/type/source conventions with explicitly documented reference exception only',
            'documented_exceptions':documented,'unexplained_format_errors':residual,'semantic_acceptance':'NOT_CLAIMED'}
        sample_rows.append({'reference_contract':reference_contract,'path':str(path),'original_format_result':sample_check(path),'deep_historical_diagnostic':sample_check(path,True),'not_accepted_production_waiver':True})
    for item in c['supplemental_documents']:
        p=repo/item['path']
        if not p.is_file() or sha(p)!=item['sha256']:issues.append({'file':str(p),'reason':'supplemental authority changed; refresh profile explicitly, do not silently accept'})
    parent=Path(sample_rows[0]['path']).parent if sample_rows else None
    return {'status':'FAIL' if issues else 'REVIEW_REQUIRED','integrity':'FAIL' if issues else 'PASS','issues':issues,'config':c,'config_sha256':sha(config),'repository':str(repo),'samples':sample_rows,'reference_conventions_status':'FAIL' if issues or not sample_rows or any(row['reference_contract']['status']!='PASS' for row in sample_rows) else 'PASS','observed_fields':observations_from_examples([Path(row['path'])/'annotation.json' for row in sample_rows]),'known_limits':c['known_limits'],'note':'References are primary compatibility fixtures; known historical defects remain limits, never production requirements or source relabeling.'}

def compare_baseline_shape(annotation,sample,observations):
    expected={r['path']:set(r['types']) for r in observations};actual={}
    def walk(value,path):
        kind='boolean' if type(value)is bool else 'integer' if type(value)is int else 'number' if type(value)is float else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'null'
        actual.setdefault(path,set()).add(kind)
        if isinstance(value,dict):
            for key,v in value.items():walk(v,path+'/'+key)
        elif isinstance(value,list):
            for v in value:walk(v,path+'/*')
    walk(annotation,'annotation')
    for tree in sorted((Path(sample)/'ui_tree').glob('*.json')):
        try:walk(read(tree),'ui_tree')
        except (OSError,ValueError):pass
    mismatches=[{'field':path,'sample_types':sorted(expected[path]),'candidate_types':sorted(types),'certainty':'observed_type_difference_not_inferred_requiredness'} for path,types in actual.items() if path in expected and not types<=expected[path]]
    return {'baseline_paths_observed':len(expected),'matched_paths_compared':sum(p in expected for p in actual),'type_differences':mismatches,'new_paths_not_forbidden':sorted(p for p in actual if p not in expected),'values_not_used_as_constants':True,'absent_observed_paths_not_assumed_required':True}

def evidence_files(sample):
    p=Path(sample);files={}
    try:a=read(p/'annotation.json')
    except (OSError,ValueError):return files
    if not isinstance(a,dict) or not isinstance(a.get('steps'),list):return files
    for step in a.get('steps',[]):
        for key in ['image_path','ui_tree_path']:
            rel=step.get(key)
            if not isinstance(rel,str):continue
            path=p/rel
            if not Path(rel).is_absolute() and path.resolve().is_relative_to(p.resolve()) and path.is_file():files[rel]=sha(path)
    return files

def review_intake(path,samples,baseline_hash):
    records={};errors=[]
    if not path:return records,errors
    data=read(path)
    if not isinstance(data,dict):return {},[{'reason':'review document must be an object'}]
    if data.get('schema_version')!='qc-review-1':return {},[{'reason':'unsupported review format'}]
    byid={s['sample_id']:s for s in samples if s.get('sample_id')}
    if not isinstance(data.get('records'),list):return {},[{'reason':'records must be an array'}]
    for record in data.get('records',[]):
        if not isinstance(record,dict):errors.append({'reason':'record must be an object'});continue
        sid=record.get('sample_id');why=[]
        if sid not in byid:errors.append({'sample_id':sid,'reason':'unknown sample'});continue
        if not isinstance(record.get('reviewer'),dict) or not isinstance(record.get('checks'),dict) or not isinstance(record.get('provenance'),dict):
            errors.append({'sample_id':sid,'reason':'reviewer/checks/provenance must be objects'});continue
        sample=Path(byid[sid]['sample_path']);reviewer=record['reviewer']
        if sid in records:why.append('duplicate review records; cannot overwrite silently')
        if record.get('baseline_sha256')!=baseline_hash:why.append('different baseline')
        if record.get('annotation_sha256')!=sha(sample/'annotation.json'):why.append('stale/different annotation')
        if record.get('evidence_sha256')!=evidence_files(sample):why.append('incomplete/stale image or tree evidence')
        if reviewer.get('kind') not in ['ai','human'] or not isinstance(reviewer.get('name'),str) or not reviewer['name'].strip():why.append('reviewer kind/name required; identity not authenticated by this program')
        results=record.get('checks',{})
        if not results or set(results)-set(SEMANTIC):why.append('unknown/missing semantic checks')
        for name,result in results.items():
            if not isinstance(result,dict) or result.get('status') not in STATES:why.append('invalid status '+name)
            elif result['status'] in ['PASS','FAIL'] and (not isinstance(result.get('note'),str) or not result['note'].strip()):why.append('PASS/FAIL needs evidence reasoning '+name)
        if not isinstance(record['provenance'].get('description'),str) or not record['provenance']['description'].strip():why.append('review source/provenance description required')
        if why:errors.append({'sample_id':sid,'reason':'; '.join(why)});continue
        records[sid]=record
    return records,errors

def partial_ai(path,samples):
    if not path:return {'status':'not_supplied','not_visual_acceptance':True,'samples':{}}
    d=read(path);byid={s['sample_id']:s for s in samples if s.get('sample_id')};out={};errors=[]
    for record in d.get('current_v2_reviewed',[]):
        sid=record['sample_id']
        if sid not in byid:continue
        valid=True;p=Path(byid[sid]['sample_path'])
        for frame in record.get('frames',[]):
            image=p/'images'/f'step_{frame["frame"]:03}.png'
            if not image.is_file() or sha(image)!=frame['sha256']:valid=False
        if not valid:errors.append({'sample_id':sid,'reason':'AI partial-review frame hash mismatch'});continue
        out.setdefault(sid,[]).append({'field':record['path'],'finding':record['finding'],'review_source':record['review_source'],'evidence_frames':record['frames']})
    return {'artifact':str(Path(path).resolve()),'artifact_sha256':sha(path),'status':'partial_evidence_only','not_visual_acceptance':True,'samples':out,'errors':errors,'note':'Existing field review, with image hashes checked. Does NOT silently turn whole-trajectory visual/semantic rules PASS.'}

def capture_integrity(sample,a):
    path=Path(sample);missing=[];errors=[];checked=0
    for st in a.get('steps',[]):
        if not isinstance(st,dict) or not all(k in st for k in ['step_id','image_path','tool_call']):continue
        raw=path.parent.parent/'evidence'/path.name/f'step_{st["step_id"]:03}.json'
        if not raw.is_file():missing.append(str(raw));continue
        try:
            d=read(raw);recorded=d.get('capture',{}).get('screenshot_sha256');image=path/st['image_path']
            if not recorded:missing.append(str(raw)+'#capture.screenshot_sha256')
            elif not image.is_file() or sha(image)!=recorded:errors.append({'step_id':st['step_id'],'file':str(image),'raw':str(raw),'reason':'Screenshot bytes differ from recorded capture hash'})
            else:checked+=1
            state=d.get('state')
            tree_path=path/st.get('ui_tree_path','')
            if isinstance(state,dict) and 'elements' in state:
                tree=read(tree_path)
                if tree.get('elements')!=state['elements'] or tree.get('screen_resolution')!=state.get('screen_resolution'):
                    errors.append({'step_id':st['step_id'],'file':str(tree_path),'reason':'Delivered tree differs from raw capture state'})
            else:
                missing.append(str(raw)+'#state.elements')
            executed=d.get('executed_action')
            if executed and executed!={'tool_name':st['tool_call']['tool_name'],'arguments':st['tool_call']['arguments']}:errors.append({'step_id':st['step_id'],'raw':str(raw),'reason':'Executed action record differs from delivered tool call'})
        except (OSError,ValueError,TypeError,KeyError) as e:errors.append({'step_id':st['step_id'],'raw':str(raw),'reason':str(e)})
    return {'status':'FAIL' if errors else 'REVIEW_REQUIRED' if missing else 'PASS','checked_frames':checked,'missing':missing,'errors':errors,'not_visual_semantic_acceptance':True}

def qc_rule(rule_id,status,location,sources,reason,suggestion,**extras):return {'rule_id':rule_id,'status':status,'location':location,'sources':sources,'reason':reason,'fix_suggestion':suggestion,**extras}

def inspect(config,dataset,reviews=None,ai_evidence=None,samples_override=None,profile=None):
    from .profiles import load as profile_load,apply as profile_apply
    local_profile=profile_load(profile) if profile else None
    base=baseline_load(config,samples_override);repo=Path(base['repository']);dataset=Path(dataset).resolve();f=format_run(repo,dataset)
    try:dup=analyze(dataset)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as e:dup={'route1':{'pairs':[]},'route2':{'confirmed_pairs':[]},'route3':{'candidates':[]},'route4':{'candidates':[]},'status':'REVIEW_REQUIRED','error':str(e)}
    rules={r['id']:r for r in catalog()};samples=f['samples'];accepted,review_errors=review_intake(reviews,samples,base['config_sha256']);partial=partial_ai(ai_evidence,samples);outputs=[]
    badpairs={sid for pair in dup['route1']['pairs'] for sid in pair['sample_ids']};badseq={sid for pair in dup['route2']['confirmed_pairs'] for sid in pair['sample_ids']};batchmap={Path(b['batch']):b for b in f['batches']}
    for s in samples:
        sid=s.get('sample_id') or Path(s['sample_path']).name;p=Path(s['sample_path']);checks=[];batch=batchmap[p.parent.parent]
        try:a=read(p/'annotation.json')
        except (OSError,ValueError):a={}
        if not isinstance(a,dict):a={}
        if not isinstance(a.get('steps'),list):a['steps']=[]
        for rid in [f'C{i:02}' for i in range(1,18)]:
            errors=[e for e in s['errors'] if e['rule_id']==rid]
            if rid in ['C13','C14']:errors += [e for e in batch['errors'] if e['rule_id']==rid]
            errors += [e for e in f['package_errors'] if e['rule_id']==rid]
            if rid=='C17' and sid in badpairs:errors += [{'path':'cross-sample screenshots','message':'Exact screenshot reused in another trajectory; no shared-initial-state exemption in archived clause.'}]
            status='FAIL' if errors else 'REVIEW_REQUIRED' if s.get('deep_checks') and rid not in ['C13','C14','C15','C17'] else 'PASS'
            if rid=='C14' and not errors and any(row['status']=='REVIEW_REQUIRED' for row in f['document_roles'].values()):status='REVIEW_REQUIRED'
            if rid=='C17' and dup.get('status')=='REVIEW_REQUIRED' and status!='FAIL':status='REVIEW_REQUIRED'
            checks.append(qc_rule(rid,status,str(p),rules[rid]['sources'],'; '.join(e['message'] for e in errors) if errors else 'Implemented deterministic portion executed; language/visual checks are separate.', 'Correct the cited annotation/file from real evidence; preserve source provenance.' if rid not in ['C13','C17'] else 'Assemble honest qc/checksum documents.' if rid=='C13' else 'Resolve duplicate candidates or obtain explicit client rule clarification; do not alter images or silently delete.',evidence=errors,scope='deterministic_only'))
        observations=s.get('observations',[]);shape=compare_baseline_shape(a,p,base['observed_fields'])
        checks.append(qc_rule('BASELINE_SHAPE','REVIEW_REQUIRED' if observations or shape['type_differences'] else 'PASS',str(p/'annotation.json'),['customer sample baseline pinned by '+base['config_sha256']],'Field/type comparison uses two reference observations plus documented source variants; observed single values are not exclusive enums.','Review inferred/unknown conventions against actual client checker.',observations=observations,shape_comparison=shape,baseline_sample_paths=[x['path'] for x in base['samples']]))
        checks.append(qc_rule('DUPLICATE_SEQUENCE','FAIL' if sid in badseq else 'REVIEW_REQUIRED' if dup.get('status')=='REVIEW_REQUIRED' else 'PASS',str(p),['request/需求书-Web浏览器自动化操作轨迹数据集.md:103'],'Exact sequence comparison over all inspected pairs.','Review matching full action/page/control sequences; do not change words to evade duplicates.'))
        checks.append(qc_rule('NEAR_DUPLICATES','REVIEW_REQUIRED',str(p),['request/需求书-Web浏览器自动化操作轨迹数据集.md:104-105'],'Explicit proxy algorithms executed; client implementation equivalence unknown.','Use supplied client algorithm/configuration or record an authorized adjudication.',proxy_image_candidates=[x for x in dup['route3']['candidates'] if sid in x['sample_ids']],proxy_text_candidates=[x for x in dup['route4']['candidates'] if sid in x['sample_ids']]))
        raw=p.parent.parent/'evidence'/str(sid)/f'step_{len(a.get("steps",[])):03}.json';terminal=[]
        if raw.is_file():
            rr=read(raw);terminal=rr.get('final_assertions',[])
        terminal_good=isinstance(terminal,list) and bool(terminal) and all(isinstance(t,dict) and t.get('passed') is True for t in terminal)
        terminal_failed=isinstance(terminal,list) and any(isinstance(t,dict) and t.get('passed') is False for t in terminal)
        checks.append(qc_rule('FINAL_MACHINE_EVIDENCE','FAIL' if terminal_failed else 'PASS' if terminal_good else 'REVIEW_REQUIRED',str(raw),['sample final image + explicit complete, archived requirement §6'],'Recorded final assertions all passed.' if terminal_good else 'No sufficient machine final assertions recorded; not assumed passed.','Inspect final image, objective and assertions; obtain review rather than fabricate completion.',assertions=terminal,not_visual_semantic_acceptance=True))
        integrity=capture_integrity(p,a)
        checks.append(qc_rule('CAPTURE_INTEGRITY',integrity['status'],str(p),['sample image + recorded capture/tool action evidence'],'Recorded capture/action integrity checked; absent optional raw evidence requires review.','Reconcile original image and actual action records, never forge hashes to match.',evidence=integrity))
        manifest_path=p.parent.parent/'manifest.json'
        try:manifest=read(manifest_path)
        except (OSError,ValueError):manifest={}
        preparation=audit_preparation(p.parent.parent/'evidence'/str(sid),p,
            expected_policy=manifest.get('preparation_policy'),
            expected_observer_sha256=manifest.get('generator_files_sha256',{}).get('snapshot.js'))
        checks.append(qc_rule('PREPARATION_INTEGRITY',
            preparation['status'] if preparation['applicable'] else 'PASS',str(p),
            ['explicit page preparation actions + preserved original landing/capture evidence'],
            'New-policy first frame, inserted actions, bounded decisions and full-viewport language independently checked; legacy captures do not claim this new evidence.',
            'Retain actual first screen and all preparation actions; never remove overlays or discard disqualifying frames.',
            evidence=preparation,not_visual_semantic_acceptance=True))
        for name in SEMANTIC:
            result=accepted.get(sid,{}).get('checks',{}).get(name);status=result['status'] if result else 'REVIEW_REQUIRED'
            checks.append(qc_rule('REVIEW_'+name.upper(),status,str(p),['customer samples, archived requirement §1/4/5/6/7'],'No valid evidence-bound review imported.' if not result else result['note'],'Open review.html, inspect actual screenshots/trees/actions, then import evidence-bound AI or human result.',reviewer=accepted.get(sid,{}).get('reviewer'),provenance=accepted.get(sid,{}).get('provenance')))
        byrule={check['rule_id']:check for check in checks}
        dependencies={'U03':['REVIEW_LANGUAGE'],'U04':['REVIEW_VISUAL_ALIGNMENT','REVIEW_TERMINAL_SEMANTICS','REVIEW_PRIVACY','CAPTURE_INTEGRITY']}
        for rule in f['unknown_rules']:
            if rule['id'] not in dependencies:continue
            required=dependencies[rule['id']]
            resolved=aggregate([byrule[name]['status'] for name in required])
            checks.append(qc_rule(rule['id'],resolved,str(p),rule['sources'],
                'Evidence-dependent summary; no independent duplicate review request.',
                'Resolve the cited dependency, never infer approval from partial review.',scope='sample',depends_on=required))
        outputs.append({'sample_id':sid,'sample_path':str(p),'status':aggregate([c['status'] for c in checks]),'annotation_sha256':sha(p/'annotation.json'),'evidence_sha256':evidence_files(p),'checks':checks,'partial_ai_evidence':partial.get('samples',{}).get(sid,[]),'steps':[{'step_id':st['step_id'],'image_path':str(p/st['image_path']),'tree_path':str(p/st['ui_tree_path']),'action':st['action'],'step_result':st['step_result']} for st in a.get('steps',[]) if isinstance(st,dict) and all(k in st for k in ['step_id','image_path','ui_tree_path','action','step_result'])]})
    dataset_checks=[]
    for rule in f['unknown_rules']:
        if rule['id'] not in ['U01','U02','U05']:continue
        scope={'U01':'external','U02':'contract','U05':'corpus'}[rule['id']]
        dataset_checks.append(qc_rule(rule['id'],'REVIEW_REQUIRED',str(dataset),rule['sources'],rule['rule'],
            'Provide authoritative rule/configuration or actual external result; unknown is not PASS.',scope=scope))
    mapping_rule=next(rule for rule in catalog() if rule['id']=='U02')
    role=f['document_roles'].get('synthesis',{});mapped=[];unmapped=[]
    synthesis=dataset/(role.get('path') or '__missing__')
    document=synthesis.read_text() if role.get('status')=='PASS' and synthesis.resolve().is_relative_to(dataset.resolve()) else ''
    for sample in samples:
        try:lineage=read(Path(sample['sample_path'])/'annotation.json')['trajectory_source']
        except (OSError,ValueError,KeyError,TypeError):unmapped.append(sample.get('sample_id'));continue
        dtype=lineage.get('data_type');space=lineage.get('action_space')
        if isinstance(dtype,str) and isinstance(space,str) and re.search(r'^#{1,6}\s+'+re.escape(dtype)+r'\s*$',document,re.M) and space in document:mapped.append(sample.get('sample_id'))
        else:unmapped.append(sample.get('sample_id'))
    mapping_status='PASS' if samples and not unmapped else 'REVIEW_REQUIRED'
    dataset_checks.append(qc_rule('U02',mapping_status,str(synthesis),mapping_rule['sources'],
        'Checks documented producer lineage mapping, not nonexistent external registration approval or authenticated identity.',
        'Supply a synthesis section named for each actual data_type and its action-space mapping; preserve truthful source.',scope='contract',mapped_samples=mapped,unmapped_samples=unmapped))
    status=aggregate([c['status'] for c in dataset_checks]+[s['status'] for s in outputs]+(['FAIL'] if base['integrity']=='FAIL' or review_errors or partial.get('errors') or f['package_errors'] else []))
    root_checksum=verify_manifest(dataset) if (dataset/'SHA256SUMS').exists() else {'pass':None,'status':'REVIEW_REQUIRED','reason':'No root manifest; per-batch checksum checks still apply.'}
    if root_checksum.get('pass') is False:status='FAIL'
    report={'program':'quality-inspector','version':__version__,'status':status,'customer_actual_program_executed':False,'customer_actual_acceptance':'UNKNOWN','baseline':base,'dataset':str(dataset),'sample_count':len(outputs),'sample_status_counts':dict(Counter(s['status'] for s in outputs)),'samples':outputs,'dataset_checks':dataset_checks,'local_sample_status':aggregate([s['status'] for s in outputs]),'rules':catalog()+[{'id':'BASELINE_SHAPE','certainty':'observed_and_documented','rule':'Reference field/type compatibility; no constants inferred from isolated values','sources':['config customer-samples.json, original two samples']},{'id':'DUPLICATE_SEQUENCE','certainty':'confirmed','rule':'Exact full action/control/page tuple sequence','sources':['request/需求书-Web浏览器自动化操作轨迹数据集.md:103']},{'id':'NEAR_DUPLICATES','certainty':'proxy_requires_review','rule':'Execute configured dHash/SimHash proxies; client equivalence unknown','sources':['request/需求书-Web浏览器自动化操作轨迹数据集.md:104-105']},{'id':'CAPTURE_INTEGRITY','certainty':'deterministic_evidence','rule':'Recorded screenshot hashes and executed actions agree; absent raw evidence requires review','sources':['supplied capture archives; archived requirement §1']},{'id':'FINAL_MACHINE_EVIDENCE','certainty':'recorded_assertions_only','rule':'Explicit failure is FAIL, absent evidence REVIEW_REQUIRED; not visual approval','sources':['final image, complete, supplied assertions; archived requirement §6']}]+[{'id':'REVIEW_'+name.upper(),'certainty':'evidence_bound_review','rule':name,'sources':['original sample evidence, archived requirement §1/4/5/6/7']} for name in SEMANTIC],'duplicates':dup,'format_layer_summary':{k:v for k,v in f.items() if k not in ['samples','batches','existing_internal_quality_layer']},'batch_results':f['batches'],'root_checksum':root_checksum,'review_import':{'accepted_count':len(accepted),'invalid_records':review_errors,'source':str(reviews) if reviews else None},'partial_ai_artifact':{k:v for k,v in partial.items() if k!='samples'},'baseline_compliance_is_not_customer_program_pass':True}
    report['rules'].append({
        'id':'PREPARATION_INTEGRITY','certainty':'new_production_evidence_contract',
        'rule':'For declared content-preparation-v1, missing original first-frame, decision or actual-action evidence is FAIL. Legacy NOT_APPLICABLE maps to compatibility PASS without claiming new-policy verification. Mechanical evidence consistency is not visual approval.',
        'sources':['用户2026-10-23要求：M1广告判断、正常关闭遮罩、按需滚动正文并保留完整证据',
                   'request/需求书-Web浏览器自动化操作轨迹数据集.md: 连续截图与完整操作轨迹要求',
                   'projects/prd/M1-广告与正文准备对照方案-20261023.md'],
        'policy':'content-preparation-v1','new_policy_missing_evidence_status':'FAIL',
        'legacy_status':'NOT_APPLICABLE','legacy_compatibility_status':'PASS',
        'legacy_new_policy_verification_claimed':False,'not_visual_semantic_acceptance':True})
    return profile_apply(report,local_profile,reviews) if local_profile else report
