"""Independent delivery-contract QC with optional legacy engineering audits."""
import hashlib,json,re
from pathlib import Path
from collections import Counter
from .format_checks import run as format_run,sample_check,catalog,observations_from_examples,delivered_call_matches_capture
from .duplicates import analyze, analysis_error
from .checksums import verify_manifest
from .preparation_evidence import audit_preparation
from .layout import discover
from .external_evidence import load as load_external_evidence, context as capture_context
from .reviews import decision_note_valid

SEMANTIC=['visual_alignment','terminal_semantics','language','privacy','substantive_difference']
STATES={'PASS','FAIL','REVIEW_REQUIRED'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def aggregate(states):
    states=list(states)
    return 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if 'REVIEW_REQUIRED' in states or not states else 'PASS'
def baseline_load(config,samples_override=None):
    config=Path(config).resolve();c=read(config);repo=(config.parent/c['repository_root']).resolve();issues=[];sample_rows=[];relocations=[]
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
        # The requirement was moved intact into its original attachment folder.
        # Resolve only this known relocation, retaining the pinned original SHA
        # and the config bytes used to bind historical review records.
        if not p.is_file() and item['path']=='request/需求书-Web浏览器自动化操作轨迹数据集.md':
            moved=repo/'request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md'
            if moved.is_file() and sha(moved)==item['sha256']:
                relocations.append({'declared_path':str(p),'resolved_path':str(moved),'sha256':item['sha256']});p=moved
        if not p.is_file() or sha(p)!=item['sha256']:issues.append({'file':str(p),'reason':'supplemental authority changed; refresh profile explicitly, do not silently accept'})
    parent=Path(sample_rows[0]['path']).parent if sample_rows else None
    return {'status':'FAIL' if issues else 'REVIEW_REQUIRED','integrity':'FAIL' if issues else 'PASS','issues':issues,'authority_relocations':relocations,'config':c,'config_sha256':sha(config),'repository':str(repo),'samples':sample_rows,'reference_conventions_status':'FAIL' if issues or not sample_rows or any(row['reference_contract']['status']!='PASS' for row in sample_rows) else 'PASS','observed_fields':observations_from_examples([Path(row['path'])/'annotation.json' for row in sample_rows]),'known_limits':c['known_limits'],'note':'References are primary compatibility fixtures; known historical defects remain limits, never production requirements or source relabeling.'}

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
    if data.get('schema_version') not in ('qc-review', 'qc-review-1', 'qc-review-2'):return {},[{'reason':'unsupported review format'}]
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
            elif result['status'] in ['PASS','FAIL'] and not decision_note_valid(result,reviewer):why.append('FAIL and AI PASS need evidence reasoning; human PASS note must be a string '+name)
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

_NATIVE_EVIDENCE = object()

def capture_integrity(sample,a,evidence_dir=_NATIVE_EVIDENCE):
    path=Path(sample);missing=[];errors=[];checked=0
    if evidence_dir is _NATIVE_EVIDENCE:evidence_dir=path.parent.parent/'evidence'/path.name
    if evidence_dir is None:
        return {'status':'REVIEW_REQUIRED','checked_frames':0,'missing':['No bound external raw capture evidence'],
                'errors':[],'not_visual_semantic_acceptance':True}
    evidence_dir=Path(evidence_dir)
    for st in a.get('steps',[]):
        if not isinstance(st,dict) or not all(k in st for k in ['step_id','image_path','tool_call']):continue
        raw=evidence_dir/f'step_{st["step_id"]:03}.json'
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
            if executed and not delivered_call_matches_capture(executed,{'tool_name':st['tool_call']['tool_name'],'arguments':st['tool_call']['arguments']},a.get('device_info',{}).get('os_name')):errors.append({'step_id':st['step_id'],'raw':str(raw),'reason':'Executed action record differs from delivered tool call after the declared Windows shortcut mapping'})
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as e:errors.append({'step_id':st['step_id'],'raw':str(raw),'reason':str(e)})
    return {'status':'FAIL' if errors else 'REVIEW_REQUIRED' if missing else 'PASS','checked_frames':checked,'missing':missing,'errors':errors,'not_visual_semantic_acceptance':True}

def qc_rule(rule_id,status,location,sources,reason,suggestion,**extras):return {'rule_id':rule_id,'status':status,'location':location,'sources':sources,'reason':reason,'fix_suggestion':suggestion,**extras}

def inspect(config=None,dataset=None,reviews=None,ai_evidence=None,samples_override=None,profile=None,evidence=None,inspection_stage='final',delivery_sampling_plan=None,human_reviews=None,ai_failures=None):
    """Inspect delivered files; explicit pilot profiles retain the legacy audit."""
    from .profiles import DEFAULT_DELIVERY_PROFILE,load as profile_load
    selected=profile_load(profile or DEFAULT_DELIVERY_PROFILE) if profile or config is None else None
    if selected and selected['configuration']['scope']=='delivery':
        return _inspect_delivery(dataset,selected,reviews,config,evidence,samples_override,ai_evidence,inspection_stage,delivery_sampling_plan,human_reviews,ai_failures)
    if delivery_sampling_plan or human_reviews or ai_failures:raise ValueError('Delivery sampling is only available under the explicit delivery contract')
    if config is None:
        raise ValueError('A legacy pilot audit needs its explicit --baseline')
    return _inspect_legacy(config,dataset,reviews,ai_evidence,samples_override,profile,evidence)

def _inspect_legacy(config,dataset,reviews=None,ai_evidence=None,samples_override=None,profile=None,evidence=None):
    from .profiles import load as profile_load,apply as profile_apply,package_files
    local_profile=profile_load(profile) if profile else None
    dataset=Path(dataset).resolve();input_binding_errors=[]
    try:input_files=package_files(dataset)
    except (OSError,ValueError) as error:input_files={};input_binding_errors.append(str(error))
    base=baseline_load(config,samples_override);repo=Path(base['repository']);f=format_run(repo,dataset);layout=discover(dataset)
    external=load_external_evidence(evidence,layout);contexts={}
    for row in f['samples']:
        try:contexts[row.get('sample_id') or Path(row['sample_path']).name]=capture_context(layout,row['sample_path'],external)
        except (OSError,ValueError,TypeError,KeyError):pass
    try:dup=analyze(dataset,contexts)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as e:
        dup=analysis_error(e,sample_count=len(f['samples']),dataset_label=dataset)
        dup['status']='REVIEW_REQUIRED'
    rules={r['id']:r for r in catalog()};samples=f['samples'];accepted,review_errors=review_intake(reviews,samples,base['config_sha256']);partial=partial_ai(ai_evidence,samples);outputs=[]
    badpairs={sid for pair in dup['route1']['pairs'] for sid in pair['sample_ids']};badseq={sid for pair in dup['route2']['confirmed_pairs'] for sid in pair['sample_ids']};batchmap={Path(b['batch']):b for b in f['batches']}
    for s in samples:
        sid=s.get('sample_id') or Path(s['sample_path']).name;p=Path(s['sample_path']);checks=[];batch=batchmap[layout.batch_for(p)]
        context=contexts.get(sid,{'status':'REVIEW_REQUIRED','issues':['Unreadable customer sample'],'evidence_dir':None,'manifest_path':None})
        raw_directory=Path(context['evidence_dir']) if context.get('evidence_dir') else None
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
        checks.append(qc_rule('DUPLICATE_SEQUENCE','FAIL' if sid in badseq else 'REVIEW_REQUIRED' if dup.get('status')=='REVIEW_REQUIRED' else 'PASS',str(p),['request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md:101'],'Exact sequence comparison over all inspected pairs.','Review matching full action/page/control sequences; do not change words to evade duplicates.'))
        checks.append(qc_rule('NEAR_DUPLICATES','REVIEW_REQUIRED',str(p),['request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md:102-103'],'Explicit proxy algorithms executed; client implementation equivalence unknown.','Use supplied client algorithm/configuration or record an authorized adjudication.',proxy_image_candidates=[x for x in dup['route3']['candidates'] if sid in x['sample_ids']],proxy_text_candidates=[x for x in dup['route4']['candidates'] if sid in x['sample_ids']]))
        raw=raw_directory/f'step_{len(a.get("steps",[])):03}.json' if raw_directory else None;terminal=[];terminal_read_error=None
        if raw is not None and raw.is_file():
            try:rr=read(raw);terminal=rr.get('final_assertions',[])
            except (OSError,ValueError,TypeError,AttributeError) as error:terminal_read_error=str(error)
        terminal_good=isinstance(terminal,list) and bool(terminal) and all(isinstance(t,dict) and t.get('passed') is True for t in terminal)
        terminal_failed=terminal_read_error is not None or isinstance(terminal,list) and any(isinstance(t,dict) and t.get('passed') is False for t in terminal)
        checks.append(qc_rule('FINAL_MACHINE_EVIDENCE','FAIL' if terminal_failed else 'PASS' if terminal_good else 'REVIEW_REQUIRED',str(raw),['sample final image + explicit complete, archived requirement §6'],'Recorded final assertions all passed.' if terminal_good else 'No sufficient machine final assertions recorded; not assumed passed.','Inspect final image, objective and assertions; obtain review rather than fabricate completion.',assertions=terminal,not_visual_semantic_acceptance=True))
        integrity=capture_integrity(p,a,raw_directory)
        checks.append(qc_rule('CAPTURE_INTEGRITY',integrity['status'],str(p),['sample image + recorded capture/tool action evidence'],'Recorded capture/action integrity checked; absent optional raw evidence requires review.','Reconcile original image and actual action records, never forge hashes to match.',evidence=integrity))
        manifest_path=Path(context['manifest_path']) if context.get('manifest_path') else None
        try:manifest=read(manifest_path) if manifest_path else {}
        except (OSError,ValueError):manifest={}
        preparation=audit_preparation(raw_directory,p,
            expected_policy=manifest.get('preparation_policy'),
            expected_observer_sha256=manifest.get('generator_files_sha256',{}).get('snapshot.js')) if raw_directory else {
                'applicable':True,'status':'REVIEW_REQUIRED','issues':[{'reason':'No bound capture/manifest evidence; policy applicability is unknown'}],
                'visual_recognition_acceptance':'NOT_EVALUATED'}
        checks.append(qc_rule('PREPARATION_INTEGRITY',
            preparation['status'] if preparation['applicable'] else 'PASS',str(p),
            ['explicit page preparation actions + preserved original landing/capture evidence'],
            'New-policy first frame, inserted actions, bounded decisions and full-viewport language independently checked; legacy captures do not claim this new evidence.',
            'Retain actual first screen and all preparation actions; never remove overlays or discard disqualifying frames.',
            evidence=preparation,not_visual_semantic_acceptance=True))
        if layout.kind=='customer-flat' or evidence is not None:
            checks.append(qc_rule('EXTERNAL_CAPTURE_BINDING',context['status'] if context['status'] in STATES else 'PASS',str(evidence) if evidence else str(p),
                ['Customer annotation/image/tree hashes and optional webcollect-client-evidence-1 sidecar'],
                'Only complete validated source bindings permit external capture evidence.' if context['status']=='PASS' else '; '.join(str(v) for v in context['issues']),
                'Supply matching external evidence; do not copy raw logs into customer samples or fabricate missing capture evidence.',evidence=context))
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
        outputs.append({'sample_id':sid,'sample_path':str(p),'status':aggregate([c['status'] for c in checks]),'annotation_sha256':sha(p/'annotation.json') if (p/'annotation.json').is_file() else None,'evidence_sha256':evidence_files(p),'capture_evidence':context,'checks':checks,'partial_ai_evidence':partial.get('samples',{}).get(sid,[]),'steps':[{'step_id':st['step_id'],'image_path':str(p/st['image_path']),'tree_path':str(p/st['ui_tree_path']),'action':st['action'],'step_result':st['step_result']} for st in a.get('steps',[]) if isinstance(st,dict) and all(k in st for k in ['step_id','image_path','ui_tree_path','action','step_result'])]})
    dataset_checks=[]
    if evidence is not None:
        dataset_checks.append(qc_rule('EXTERNAL_EVIDENCE_INDEX',external['status'],str(evidence),
            ['webcollect-client-evidence-1 optional external evidence index'],
            'Validated customer-to-source sample and capture evidence bindings.',
            'Repair stale bindings or retain missing evidence as REVIEW_REQUIRED; never change customer files to fit a sidecar.',scope='batch',evidence=external))
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
    if layout.kind=='customer-flat':
        prompts=dataset/'动作空间与系统提示.md'
        prompt_text=prompts.read_text() if prompts.is_file() else ''
        for sample in samples:
            try:dtype=read(Path(sample['sample_path'])/'annotation.json')['trajectory_source']['data_type']
            except (OSError,ValueError,KeyError,TypeError):continue
            if not re.search(r'^#{1,6}\s+'+re.escape(dtype)+r'\s*$',prompt_text,re.M):
                mapping_status='REVIEW_REQUIRED'
                if sample.get('sample_id') not in unmapped:unmapped.append(sample.get('sample_id'))
    dataset_checks.append(qc_rule('U02',mapping_status,str(synthesis),mapping_rule['sources'],
        'Checks documented producer lineage mapping, not nonexistent external registration approval or authenticated identity.',
        'Supply a synthesis section named for each actual data_type and its action-space mapping; preserve truthful source.',scope='contract',mapped_samples=mapped,unmapped_samples=unmapped))
    status=aggregate([c['status'] for c in dataset_checks]+[s['status'] for s in outputs]+(['FAIL'] if base['integrity']=='FAIL' or review_errors or partial.get('errors') or f['package_errors'] else []))
    root_checksum=verify_manifest(dataset) if (dataset/'SHA256SUMS').exists() else {'pass':None,'status':'REVIEW_REQUIRED','reason':'No root manifest; per-batch checksum checks still apply.'}
    if root_checksum.get('pass') is False:status='FAIL'
    report={'program':'quality-inspector','status':status,'customer_actual_program_executed':False,'customer_actual_acceptance':'UNKNOWN','baseline':base,'dataset':str(dataset),'layout':layout.kind,'external_evidence':external,'sample_count':len(outputs),'sample_status_counts':dict(Counter(s['status'] for s in outputs)),'samples':outputs,'dataset_checks':dataset_checks,'local_sample_status':aggregate([s['status'] for s in outputs]),'rules':catalog()+[{'id':'BASELINE_SHAPE','certainty':'observed_and_documented','rule':'Reference field/type compatibility; no constants inferred from isolated values','sources':['config customer-samples.json, original two samples']},{'id':'DUPLICATE_SEQUENCE','certainty':'confirmed','rule':'Exact full action/control/page tuple sequence','sources':['request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md:101']},{'id':'NEAR_DUPLICATES','certainty':'proxy_requires_review','rule':'Execute configured dHash/SimHash proxies; client equivalence unknown','sources':['request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md:102-103']},{'id':'CAPTURE_INTEGRITY','certainty':'deterministic_evidence','rule':'Recorded screenshot hashes and executed actions agree; absent raw evidence requires review','sources':['supplied capture archives; archived requirement §1']},{'id':'FINAL_MACHINE_EVIDENCE','certainty':'recorded_assertions_only','rule':'Explicit failure is FAIL, absent evidence REVIEW_REQUIRED; not visual approval','sources':['final image, complete, supplied assertions; archived requirement §6']}]+[{'id':'REVIEW_'+name.upper(),'certainty':'evidence_bound_review','rule':name,'sources':['original sample evidence, archived requirement §1/4/5/6/7']} for name in SEMANTIC],'duplicates':dup,'format_layer_summary':{k:v for k,v in f.items() if k not in ['samples','batches','existing_internal_quality_layer']},'batch_results':f['batches'],'root_checksum':root_checksum,'review_import':{'accepted_count':len(accepted),'invalid_records':review_errors,'source':str(reviews) if reviews else None},'partial_ai_artifact':{k:v for k,v in partial.items() if k!='samples'},'baseline_compliance_is_not_customer_program_pass':True}
    report['rules'].append({
        'id':'PREPARATION_INTEGRITY','certainty':'new_production_evidence_contract',
        'rule':'For declared content-preparation-v1, missing original first-frame, decision or actual-action evidence is FAIL. Legacy NOT_APPLICABLE maps to compatibility PASS without claiming new-policy verification. Mechanical evidence consistency is not visual approval.',
        'sources':['用户2026-10-23要求：M1广告判断、正常关闭遮罩、按需滚动正文并保留完整证据',
                   'request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md: 连续截图与完整操作轨迹要求',
                   'projects/prd/M1-广告与正文准备对照方案-20261023.md'],
        'policy':'content-preparation-v1','new_policy_missing_evidence_status':'FAIL',
        'legacy_status':'NOT_APPLICABLE','legacy_compatibility_status':'PASS',
        'legacy_new_policy_verification_claimed':False,'not_visual_semantic_acceptance':True})
    report=profile_apply(report,local_profile,reviews) if local_profile else report
    try:
        if package_files(dataset)!=input_files:input_binding_errors.append('Inspected customer files changed while QC was running')
        if evidence is not None and load_external_evidence(evidence,layout)!=external:
            input_binding_errors.append('External evidence index or source capture files changed while QC was running')
    except (OSError,ValueError,TypeError) as error:input_binding_errors.append(str(error))
    report['input_files_sha256']=input_files
    report['input_integrity']={'status':'FAIL' if input_binding_errors else 'PASS','errors':input_binding_errors,
                               'checked_before_and_after':True,'not_visual_acceptance':True}
    if input_binding_errors:
        report['status']='FAIL'
        changed=qc_rule('INPUT_CHANGED_DURING_QC','FAIL',str(dataset),['Read-only QC input identity'],
            '; '.join(input_binding_errors),'Restore stable inputs and run QC into a separate output directory.',scope='batch')
        report['dataset_checks'].append(changed)
        if local_profile:
            report['local_acceptance_status']='FAIL'
            report['acceptance_scopes']['batch']['status']='FAIL'
            report['acceptance_scopes']['batch']['checks'].append(changed)
    return report


def _delivery_documents(dataset,profile,roles=None):
    """Check the contract's existing files, without consulting producer logs."""
    checks=[]
    required={
        '合成方式说明.md':['动作映射','坐标','界面变化判定','文字字段生成方式'],
        '来源与合规说明.md':['采集方式','访问频率策略','账号与脱敏','站点清单'],
    }
    for name,topics in required.items():
        role='synthesis' if name=='合成方式说明.md' else 'source'
        path=dataset/((roles or {}).get(role,{}).get('path') or name)
        content=path.read_text(encoding='utf-8') if path.is_file() else ''
        # Recorded model inputs are quotations, not current production declarations.
        # Exclude only explicitly labelled, closed text fences; ordinary text and
        # JSON/configuration fences still undergo the placeholder check. Quoted
        # prompts cannot supply missing documentary topics either.
        prompt_pattern=r'(?m)^实际提示词：[ \t]*\n(?:[ \t]*\n)*```text[ \t]*\n[\s\S]*?^```[ \t]*(?:\n|$)'
        quoted_prompts=re.findall(prompt_pattern,content) if name=='合成方式说明.md' else []
        prose=re.sub(prompt_pattern,'实际提示词（原文引用，真实性仍需资料审核）\n',content) if quoted_prompts else content
        missing=[topic for topic in topics if topic not in prose]
        placeholders=re.findall(r'UNKNOWN|NOT_RUN|待补充|待核验|待填写',prose)
        if name=='合成方式说明.md' and not any(word in prose for word in ('提示词','不使用模型','未使用模型')):
            missing.append('模型提示词或未使用模型的明确声明')
        checks.append(qc_rule('DELIVERY_DOCUMENT_CONTENT','FAIL' if missing or placeholders else 'PASS',str(path),
            ['需求书§3：合成方式说明、来源与合规说明'],
            'Missing required topics: '+', '.join(missing)+'; unresolved placeholders: '+', '.join(placeholders)
                if missing or placeholders else 'Required documentary topics are supplied in the delivered text.',
            'Complete the existing production document from actual records before release.',scope='batch',
            missing_topics=missing,unresolved_placeholders=placeholders,
            quoted_prompt_blocks=len(quoted_prompts),
            quoted_prompt_literal_markers=re.findall(r'UNKNOWN|NOT_RUN|待补充|待核验|待填写','\n'.join(quoted_prompts)),
            semantic_authenticity_not_proven_by_keywords=True))
    for name,digest in profile['configuration']['attachments'].items():
        path=dataset/name
        checks.append(qc_rule('DELIVERY_ATTACHMENT','PASS' if path.is_file() and sha(path)==digest else 'FAIL',str(path),
            ['Pinned original annex A/B contract'], 'Original attachment bytes must match the distributed contract.',
            'Supply the original attachment; put collection-specific explanations in the existing synthesis document.',scope='batch'))
    return checks


def _delivery_statistics(dataset,outputs,profile):
    import csv
    from collections import defaultdict
    from .category_coverage import parent_category
    rows=[];errors=[];sites=defaultdict(set);resolutions=set();short=0
    try:
        with (dataset/'metadata.csv').open(newline='',encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
    except (OSError,ValueError,csv.Error) as error:errors.append(str(error))
    try:
        listing=read(dataset/'site-list.json');declared={item['site_id']:item for item in listing['sites']}
        assignments={item['sample_id']:item['site_id'] for item in listing['samples']}
        ids={row['sample_id'] for row in outputs}
        if listing.get('schema_version') not in ('site-list','webcollect-site-list-1') or len(declared)!=len(listing['sites']) or len(assignments)!=len(listing['samples']) or set(assignments)!=ids:
            errors.append('Site list must cover the delivered samples exactly once.')
        from urllib.parse import urlsplit
        uri_owners={}
        for key,item in declared.items():
            uri=urlsplit(item['uri'])
            if uri.scheme not in ('http','https') or not uri.hostname or uri.username or uri.password:errors.append('Invalid source URI for '+key)
            if item['uri'] in uri_owners and uri_owners[item['uri']]!=key:errors.append('Source URI has multiple site IDs.')
            uri_owners[item['uri']]=key
            assigned={sid for sid,site in assignments.items() if site==key}
            if not isinstance(item.get('sample_ids'),list) or len(item['sample_ids'])!=len(set(item['sample_ids'])) or set(item['sample_ids'])!=assigned:
                errors.append('Site membership differs for '+key)
        for row in rows:
            site=declared.get(row.get('site_id'))
            if not site or site.get('site_category')!=row.get('site_category') or assignments.get(row.get('sample_id'))!=row.get('site_id'):
                errors.append('Site/category/sample mapping differs: '+str(row.get('sample_id')))
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:errors.append('Source attribution: '+str(error))
    for row in rows:sites[row.get('site_id','')].add(row.get('site_category',''))
    for sample in outputs:
        try:
            annotation=read(Path(sample['sample_path'])/'annotation.json')
            resolutions.add(tuple(annotation['device_info']['screen_resolution']))
            short+=int(annotation.get('short_flow') is True)
        except (OSError,ValueError,KeyError,TypeError):errors.append('Missing distribution facts: '+sample['sample_id'])
    count=len(outputs);categories=Counter(parent_category(row.get('site_category','')) for row in rows);targets=profile['configuration']['targets']
    maximum=max(categories.values(),default=0)/count if count else 0
    selection=None
    for document in ('来源与合规说明.md','README.md'):
        path=dataset/document
        if not path.is_file():continue
        for block in re.findall(r'```json\s*\n(.*?)\n```',path.read_text(encoding='utf-8'),re.S):
            try:value=json.loads(block)
            except (ValueError,TypeError):continue
            if isinstance(value,dict) and all(key in value for key in ('total_samples','selected_count','excluded_count','excluded_samples')):
                if selection is not None and selection!=value:errors.append('Delivered source population declarations disagree.')
                selection=value
    if selection is not None:
        excluded=selection.get('excluded_samples')
        if (any(type(selection.get(key)) is not int for key in ('total_samples','selected_count','excluded_count')) or
            selection.get('selected_count')!=count or selection.get('total_samples')!=selection.get('selected_count',0)+selection.get('excluded_count',0) or
            not isinstance(excluded,list) or len(excluded)!=selection.get('excluded_count') or
            any(not isinstance(row,dict) or not isinstance(row.get('sample_id'),str) or not row['sample_id'].strip()
                or not isinstance(row.get('reason'),str) or not row['reason'].strip() for row in excluded)):
            errors.append('Delivered selection population/reasons are incomplete or inconsistent.')
        elif len({row['sample_id'] for row in excluded}) != len(excluded):
            errors.append('Excluded sample IDs must be unique.')
        elif {row['sample_id'] for row in excluded} & {row['sample_id'] for row in outputs}:
            errors.append('Selected and excluded sample IDs must be disjoint.')
    task_types=Counter()
    for row in rows:
        try:
            tags=json.loads(row.get('task_type','[]'))
            if not isinstance(tags,list) or any(not isinstance(tag,str) for tag in tags):raise ValueError('task_type must encode an array of strings')
            task_types.update(tags)
        except (ValueError,TypeError):errors.append('Invalid metadata task_type: '+str(row.get('sample_id')))
    stats={'sample_count':count,'metadata_rows':len(rows),'site_count':len(sites),'categories':dict(categories),
        'site_sample_counts':dict(Counter(row.get('site_id','') for row in rows)),
        'step_counts':dict(Counter(row.get('steps','') for row in rows)),
        'task_types':dict(task_types),
        'viewport_specs':[list(value) for value in sorted(resolutions)],'short_flow_count':short,
        'maximum_category_share':maximum,'category_share_policy':targets['category_share'],
        'category_share_authority':profile['configuration']['authority'],'source_errors':errors,
        'source_population':selection if selection is not None else {'status':'NOT_DECLARED','scope':'No historical capture total is inferred from selected samples'}}
    checks=[qc_rule('DELIVERY_ACCOUNTING','FAIL' if errors or len(rows)!=count or not count else 'PASS',str(dataset),
        ['需求书§3、站点来源澄清'], 'Delivered metadata, site list and sample population reconcile.' if not errors else '; '.join(errors),
        'Correct delivered metadata/source declarations without discarding failed samples.',scope='batch',evidence=stats),
        qc_rule('DELIVERY_VIEWPORT_SPECS','PASS' if resolutions and len(resolutions)<=targets['max_viewport_specs'] else 'FAIL',str(dataset),
        ['需求书§2'], 'Whole delivered set has at most three viewport specifications.','Use the permitted viewport specifications.',scope='batch'),
        qc_rule('DELIVERY_SHORT_FLOW_SHARE','PASS' if count and short/count<=targets['max_short_flow_share'] else 'FAIL',str(dataset),
        ['需求书§2'], 'Declared short-flow share is checked over the unchanged delivered denominator.','Replace or repair short flows before release.',scope='batch')]
    expected=targets['expected_samples']
    if expected is not None:checks.append(qc_rule('DELIVERY_EXPECTED_SAMPLES','PASS' if count==expected else 'FAIL',str(dataset),
        [profile['configuration']['authority']],f'Expected {expected}; inspected {count}.','Supply the explicitly selected case population.',scope='batch'))
    expected_sites=targets.get('expected_sites')
    if expected_sites is not None:checks.append(qc_rule('DELIVERY_EXPECTED_SITES','PASS' if len(sites)==expected_sites else 'FAIL',str(dataset),
        [profile['configuration']['authority']],f'Expected {expected_sites} delivered site identities; inspected {len(sites)}.',
        'Supply the requested site population with truthful URI, category and sample attribution.',scope='batch'))
    if targets['category_share']=='enforced':checks.append(qc_rule('DELIVERY_CATEGORY_SHARE','PASS' if count and maximum<=targets['max_category_share'] else 'FAIL',str(dataset),
        ['需求书§5'], 'Single-category share must be at most 20%.','Correct collection coverage, never split labels to alter the ratio.',scope='batch',actual=maximum))
    return stats,checks


def _verify_delivery_qc_report(dataset,report):
    """Verify the producer summary against this independent final inspection.

    The binding excludes only qc_report.md and SHA256SUMS, breaking the report
    self-reference without excluding any sample, source or explanatory file.
    """
    path=dataset/'qc_report.md';errors=[]
    text=path.read_text(encoding='utf-8') if path.is_file() else ''
    declarations={}
    for line in text.splitlines():
        cells=[cell.strip() for cell in line.strip().strip('|').split('|')]
        if cells and cells[0].isdigit():
            state=next((cell for cell in cells[1:] if cell in STATES),None)
            if report.get('semantic_sampling') and '按抽检策略核验，实际覆盖见下表' in cells:
                state='按抽检策略核验，实际覆盖见下表'
            if state:declarations[int(cells[0])]=state
    mappings={1:['C01'],2:['C05','C06'],3:['C06'],4:['C06'],5:['C05'],6:['C11'],7:['C08'],8:['C07'],9:['C09'],
        10:['C10'],11:['C10'],12:['C03'],13:['REVIEW_LANGUAGE'],14:['C12'],15:['C12'],
        16:['REVIEW_VISUAL_ALIGNMENT','REVIEW_TERMINAL_SEMANTICS'],17:['REVIEW_PRIVACY']}
    for number,rules in mappings.items():
        expected=aggregate(check['status'] for sample in report['samples'] for check in sample['checks'] if check['rule_id'] in rules)
        if report.get('semantic_sampling') and any(rule.startswith('REVIEW_') for rule in rules):
            expected='按抽检策略核验，实际覆盖见下表'
        if declarations.get(number)!=expected:errors.append(f'Requirement {number} summary differs or is missing: expected {expected}.')
    summary=None
    for block in re.findall(r'```json\s*\n(.*?)\n```',text,re.S):
        try:value=json.loads(block)
        except (ValueError,TypeError):continue
        if isinstance(value,dict) and 'payload_sha256' in value:
            if summary is not None:errors.append('Multiple QC payload summary objects are ambiguous.')
            summary=value
    if summary is None:errors.append('Complete machine-readable QC summary and payload binding are missing.')
    else:
        for key in ('payload_sha256','payload_files_sha256'):
            if summary.get(key)!=report[key]:errors.append('QC summary '+key+' differs from the delivered payload.')
        distribution=summary.get('distribution',{})
        for key in ('sample_count','site_count','categories','task_types','step_counts'):
            if distribution.get(key)!=report['statistics'][key]:errors.append('QC distribution differs: '+key)
        expected_coverage={'human_complete_samples':0,'ai_complete_samples':0,'pending_or_missing_samples':0,'samples_in_this_output':report['sample_count']}
        for sample in report['samples']:
            checks=[check for check in sample['checks'] if check['rule_id'].startswith('REVIEW_')]
            kinds={(check.get('reviewer') or {}).get('kind') for check in checks}
            if len(checks)==len(SEMANTIC) and all(check['status'] in ('PASS','FAIL') for check in checks) and kinds=={'human'}:expected_coverage['human_complete_samples']+=1
            elif len(checks)==len(SEMANTIC) and all(check['status'] in ('PASS','FAIL') for check in checks) and kinds=={'ai'}:expected_coverage['ai_complete_samples']+=1
            else:expected_coverage['pending_or_missing_samples']+=1
        coverage=summary.get('review_coverage',{})
        for key,value in expected_coverage.items():
            if coverage.get(key)!=value:errors.append('QC actual review coverage differs: '+key)
        if report.get('semantic_sampling'):
            sampling=report['semantic_sampling']
            expected_sampling={key:sampling.get(key) for key in (
                'policy','plan_sha256','original_denominator','actual_ai_reviewed',
                'actual_human_reviewed','not_selected','human_pending_count','replacement_required_count')}
            if summary.get('semantic_sampling')!=expected_sampling:
                errors.append('QC frozen sampling policy or coverage summary differs.')
            for key in ('policy','original_denominator','actual_ai_reviewed','actual_human_reviewed',
                        'not_selected','human_pending_count','replacement_required_count'):
                if coverage.get(key)!=sampling.get(key):errors.append('QC sampling review coverage differs: '+key)
            if coverage.get('acceptance_basis')!='frozen_sampling_policy' or coverage.get('unselected_is_not_semantic_pass') is not True:
                errors.append('QC sampling summary must distinguish policy admission from actual semantic review.')
            if '全量检查与逐图复核' in text:
                errors.append('Sampling QC summary cannot claim universal visual review.')
        reviewers=Counter()
        for sample in report['samples']:
            checks=[check for check in sample['checks'] if check['rule_id'].startswith('REVIEW_')]
            if len(checks)!=len(SEMANTIC) or any(check['status'] not in ('PASS','FAIL') for check in checks):continue
            identities=[check.get('reviewer') or {} for check in checks]
            if any(identity.get('kind') not in ('ai','human') or not isinstance(identity.get('name'),str) or not identity['name'].strip() for identity in identities):continue
            names={(identity['kind'],identity['name']) for identity in identities}
            if len(names)==1:reviewers[next(iter(names))]+=1
        expected_sources=[{'kind':kind,'name':name,'samples':count} for (kind,name),count in sorted(reviewers.items())]
        if coverage.get('reviewer_sources')!=expected_sources:errors.append('QC actual review coverage differs: reviewer_sources')
        if summary.get('delivery_document_review')!=report['delivery_document_review']:
            errors.append('QC actual delivery_document_review differs or is missing.')
        duplicate=summary.get('four_route_duplicates',{})
        if duplicate.get('pair_comparisons')!=report['duplicates']['pair_comparisons']:errors.append('QC duplicate pair denominator differs.')
        for route in ('route1','route2','route3','route4'):
            expected=report['duplicates'][route].get('confirmed_pair_count' if route=='route1' else 'count')
            if duplicate.get(route)!=expected:errors.append('QC duplicate candidate count differs: '+route)
        resolution={key:value for key,value in report['duplicates'].get('summary',{}).items()
                    if key not in ('pair_adjudications','current_sample_ids','affected_current_sample_ids')}
        if duplicate.get('resolution')!=resolution:
            errors.append('QC duplicate union/rates/unadjudicated resolution differs or is missing.')
        selection=report['statistics']['source_population'];declared=summary.get('original_source_population',{})
        if 'total_samples' in selection:
            expected={key:selection[key] for key in ('total_samples','selected_count','excluded_count')}
            if declared.get('status')!='RECORDED' or declared.get('population')!=expected or declared.get('excluded_samples')!=selection['excluded_samples']:
                errors.append('QC original population or exclusion reasons differ from delivered source declaration.')
        elif not isinstance(declared,dict) or not declared.get('status'):errors.append('QC exclusion population status is missing.')
        if summary.get('delivery_scope')!=report['delivery_scope']:errors.append('QC delivery scope/explicit category policy differs.')
    return qc_rule('DELIVERY_QC_REPORT','FAIL' if errors else 'PASS',str(path),['需求书§7：本批17项、分布、去重、淘汰、实际抽检结论'],
        '; '.join(errors) if errors else 'Final QC summary independently matches the complete delivered payload, counts and actual review records.',
        'Generate the complete existing qc_report.md from the payload QC report, seal once, and inspect final read-only.',scope='batch',evidence=errors)


def _inspect_delivery(dataset,profile,reviews=None,baseline=None,evidence=None,samples_override=None,ai_evidence=None,inspection_stage='final',delivery_sampling_plan=None,human_reviews=None,ai_failures=None):
    """Contract checks use only delivered files plus installed rule resources.

    Historical baselines/raw logs are optional engineering diagnostics. Their
    absence, stale paths or failures never change the delivery conclusion.
    """
    from .contract import fingerprint as contract_fingerprint
    from .reviews import intake as delivery_review_intake
    from .profiles import package_files,delivery_document_review
    if inspection_stage not in ('payload','final'):raise ValueError('Inspection stage must be payload or final')
    dataset=Path(dataset).resolve();initial_errors=[]
    try:input_files=package_files(dataset)
    except (OSError,ValueError) as error:input_files={};initial_errors.append(str(error))
    # None deliberately prevents reads of repository reference documents.
    formats=format_run(None,dataset);layout=discover(dataset)
    contract,fingerprint=contract_fingerprint()
    if profile['configuration']['attachments']!=contract['attachments']:
        initial_errors.append('Profile attachments differ from the installed authority.')
    base={'status':'PASS','integrity':'PASS','config_sha256':fingerprint,'scope':'installed-delivery-contract',
          'samples':[],'known_limits':[],'note':'No external reference sample, baseline or raw log is required.'}
    semantic_sampling=None
    if delivery_sampling_plan:
        from .delivery_sampling import evaluate as evaluate_sampling
        human_paths=[human_reviews] if isinstance(human_reviews,(str,Path)) else list(human_reviews or [])
        failure_paths=[ai_failures] if isinstance(ai_failures,(str,Path)) else list(ai_failures or [])
        semantic_sampling,accepted=evaluate_sampling(delivery_sampling_plan,dataset,
            ai_reviews=[reviews] if reviews else [],human_reviews=human_paths,ai_failures=failure_paths)
        review_errors=[]
    else:
        if human_reviews or ai_failures:raise ValueError('Separate human/failure inputs require an explicit delivery sampling plan')
        accepted,review_errors,_=delivery_review_intake(reviews,formats['samples'],fingerprint)
    try:duplicates=analyze(dataset)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as error:
        duplicates=analysis_error(error,sample_count=len(formats['samples']),dataset_label=dataset)
    resolution=duplicates.get('summary',{})
    if resolution.get('analysis_status')!='COMPLETE' or resolution.get('unadjudicated_pair_count')!=0:
        initial_errors.append('Four-route evaluation or deterministic resolution is incomplete; unknown counts are not zero.')
    if duplicates.get('search',{}).get('exhaustive_verification',{}).get('status')=='FAIL':
        initial_errors.append('Duplicate index/cache disagrees with independent exhaustive validation.')
    outputs=[];byrule={row['id']:row for row in catalog()}
    for sample in formats['samples']:
        path=Path(sample['sample_path']);sid=sample.get('sample_id') or path.name;checks=[]
        try:annotation=read(path/'annotation.json')
        except (OSError,ValueError):annotation={}
        if not isinstance(annotation,dict):annotation={}
        for rid in [f'C{number:02}' for number in range(1,18)]:
            errors=[row for row in sample['errors'] if row['rule_id']==rid]
            if rid in ('C13','C14'):continue
            if rid=='C17' and any(sid in pair['sample_ids'] for pair in duplicates['route1']['pairs']):errors.append({'message':'Exact screenshot shared across delivered samples.'})
            checks.append(qc_rule(rid,'FAIL' if errors else 'REVIEW_REQUIRED' if sample.get('deep_checks') else 'PASS',str(path),byrule[rid]['sources'],
                '; '.join(row['message'] for row in errors) if errors else 'Independent deterministic contract check executed on delivered files.',
                'Repair the delivered sample from original evidence.',scope='sample',evidence=errors))
        if annotation.get('terminal_type')!='Web':checks.append(qc_rule('C02','FAIL',str(path),['Web dataset contract'],
            'This delivery contract requires terminal_type=Web.','Use Web trajectories.',scope='sample'))
        steps=annotation.get('steps',[])
        if isinstance(steps,list) and steps and isinstance(steps[-1],dict):
            goal=steps[-1].get('user_goal','');generic=re.sub(r'[\s，。！：、]','',goal) if isinstance(goal,str) else ''
            if generic in ('确认最终页面符合任务要求','确认任务完成','确认最终状态','完成任务'):
                checks.append(qc_rule('C10','FAIL',str(path/'annotation.json'),['需求书§6：user_goal写明确认最终页面'],
                    'Final user_goal is generic and does not name the actual final page/content.','Generate a concrete terminal confirmation from the delivered final state.',scope='sample'))
        # Unified duplicate verdict: exact/sequence pairs (routes 1/2) stay
        # per-sample hard failures (duplicate registration of the same data);
        # near-duplicate proxies (routes 3/4) are judged once against the
        # explicit effective set's near-duplicate sample rate (<=0.1%,
        # historical samples never dilute the denominator). All four-route
        # hit facts remain reported either way.
        rate=resolution.get('near_duplicate_sample_rate')
        rate_ok=resolution.get('sample_rate_within_requested_limit')
        for rid,route,key in [('DUPLICATE_SEQUENCE','route2','confirmed_pairs')]:
            hit=any(sid in row['sample_ids'] for row in duplicates[route][key])
            checks.append(qc_rule(rid,'FAIL' if hit else 'REVIEW_REQUIRED' if duplicates.get('error') else 'PASS',str(path),['需求书§6：四路去重'],
                'Exact duplicate sequence registration is a hard per-sample failure.','Resolve by repair/recollection, never by changing the denominator or labels.',scope='sample',route=route))
        for rid,route,key in [('NEAR_DUPLICATES','route3','candidates'),('NEAR_DUPLICATES','route4','candidates')]:
            hit=any(sid in row['sample_ids'] for row in duplicates[route][key])
            if hit and rate_ok is False:
                status='FAIL'
            elif hit or duplicates.get('error') or rate_ok is None:
                status='REVIEW_REQUIRED'
            else:
                status='PASS'
            checks.append(qc_rule(rid,status,str(path),['需求书§6：四路去重；近重复按显式有效集合比例≤0.1%判定'],
                'Near-duplicate proxies judged by the effective-set sample rate; hit facts retained verbatim.',
                'Resolve by repair/recollection, never by changing the denominator or labels.',scope='sample',route=route,
                near_duplicate_sample_rate=rate,rate_within_limit=rate_ok))
        sampling_row=next((row for row in semantic_sampling['rows'] if row['sample_id']==sid),None) if semantic_sampling else None
        semantic_names=SEMANTIC if sampling_row is None or sid in accepted else []
        for name in semantic_names:
            result=accepted.get(sid,{}).get('checks',{}).get(name)
            checks.append(qc_rule('REVIEW_'+name.upper(),result['status'] if result else 'REVIEW_REQUIRED',str(path),
                ['Delivered annotation, screenshots, actions and synchronized trees; 需求书§1/4/5/6/7'],
                result['note'] if result else 'Actual pixel/semantic inspection has not been supplied; not inferred from producer success.',
                'Inspect the actual delivered frames and import evidence-bound AI or human decisions.',scope='sample',
                reviewer=accepted.get(sid,{}).get('reviewer'),provenance=accepted.get(sid,{}).get('provenance'),
                semantic_reuse=accepted.get(sid,{}).get('semantic_reuse')))
        if sampling_row is not None:
            checks.append(qc_rule('SEMANTIC_SAMPLING_ADMISSION',sampling_row['admission_status'],str(path),
                ['Explicit versioned delivery sampling clarification'],
                'Frozen sampling decision: '+sampling_row['status']+'. NOT_SELECTED is not an AI/human semantic PASS.',
                'Complete actual human escalation/replacement inspection when required.',scope='sample',
                semantic_review_status=sampling_row['status'],sampling_plan_sha256=semantic_sampling['plan_sha256']))
        outputs.append({'sample_id':sid,'sample_path':str(path),'annotation_sha256':sha(path/'annotation.json') if (path/'annotation.json').is_file() else None,
            **({'semantic_sampling':sampling_row} if sampling_row is not None else {}),
            'evidence_sha256':evidence_files(path),'checks':checks,'local_checks':checks,'status':aggregate(row['status'] for row in checks),
            'local_acceptance_status':aggregate(row['status'] for row in checks),
            'steps':[{'step_id':row['step_id'],'image_path':str(path/row['image_path']),'tree_path':str(path/row['ui_tree_path']),
                      'action':row['action'],'step_result':row['step_result']} for row in steps if isinstance(row,dict) and all(key in row for key in ('step_id','image_path','ui_tree_path','action','step_result'))] if isinstance(steps,list) else []})
    batch=[]
    for row in formats['batches']:
        for rid in ('C13','C14'):
            errors=[item for item in row['errors'] if item['rule_id']==rid]
            batch.append(qc_rule(rid,'FAIL' if errors else 'PASS',row['batch'],byrule[rid]['sources'],
                '; '.join(item['message'] for item in errors) if errors else 'Delivered batch files and truth archives checked.',
                'Complete the actual delivered files.',scope='batch',evidence=errors))
    batch+=_delivery_documents(dataset,profile,formats['document_roles'])
    roles=formats['document_roles']
    batch.append(qc_rule('DELIVERY_DOCUMENT_ROLES',aggregate(row['status'] for row in roles.values()),str(dataset),
        ['需求书§3：README、字段、合成与来源资料'],
        'Every required document role must resolve to an actual nonempty delivered file; names may be explicitly mapped.',
        'Supply missing document roles or an accurate role mapping; presence is not semantic approval.',scope='batch',evidence=roles))
    stats,distribution_checks=_delivery_statistics(dataset,outputs,profile);batch+=distribution_checks
    batch.append(qc_rule('DELIVERY_NEAR_DUPLICATE_RATE',
        'FAIL' if resolution.get('sample_rate_within_requested_limit') is False
        else 'REVIEW_REQUIRED' if resolution.get('sample_rate_within_requested_limit') is None else 'PASS',
        str(dataset),['需求书§6：四路去重；近重复按显式有效集合样本比例≤0.1%（历史样本不稀释分母）'],
        'near_duplicate_sample_rate=' + str(resolution.get('near_duplicate_sample_rate')) +
        '; four-route hit facts retained in the duplicates block.',
        'Resolve by repair/recollection, never by changing the denominator, labels or exemption.',scope='batch'))
    checksum=verify_manifest(dataset)
    batch.append(qc_rule('ROOT_CHECKSUM','PASS' if checksum.get('pass') is True else 'FAIL',str(dataset/'SHA256SUMS'),
        ['需求书§3'], 'Complete delivered file manifest independently verified.','Seal the final unchanged package with a complete manifest.',scope='batch',evidence=checksum))
    if formats['package_errors'] or review_errors or initial_errors:
        batch.append(qc_rule('DELIVERY_INPUT','FAIL',str(dataset),['Contract input integrity'],
            'Invalid package or review bindings.','Correct the indicated input without suppressing failures.',scope='batch',
            evidence=formats['package_errors']+review_errors+initial_errors))
    sample_status=aggregate(row['status'] for row in outputs);batch_status=aggregate(row['status'] for row in batch)
    report={'program':'quality-inspector','scope':'delivery','dataset':str(dataset),'layout':layout.kind,
        'baseline':base,'local_profile':profile,'requirements_baseline':{'configuration':contract,'sha256':fingerprint},
        'sample_count':len(outputs),'samples':outputs,'statistics':stats,'duplicates':duplicates,'root_checksum':checksum,
        'dataset_checks':batch,'batch_results':formats['batches'],'format_layer_summary':{key:value for key,value in formats.items() if key not in ('samples','batches','existing_internal_quality_layer')},
        'review_import':{'accepted_count':len(accepted),'invalid_records':review_errors,'source':str(reviews) if reviews else None,
            'identity_authenticated':False,'actual_reading_authenticated':False},
        'rules':catalog()+[{'id':'REVIEW_'+name.upper(),'certainty':'evidence_bound_review','rule':name,'sources':['Delivered sample evidence']} for name in SEMANTIC]
            +([{'id':'SEMANTIC_SAMPLING_ADMISSION','certainty':'explicit_policy_admission','rule':'Frozen sampling selection and actual human escalation; NOT_SELECTED is not semantic PASS','sources':['2026-10-27 sampling clarification']}] if semantic_sampling else []),
        'package_files_sha256':input_files,'input_files_sha256':input_files,'partial_ai_artifact':{'status':'not_used_for_whole_trajectory_acceptance'},
        'external_evidence':{'status':'NOT_REQUIRED_FOR_DELIVERY'},'customer_actual_program_executed':False,'customer_actual_acceptance':'UNKNOWN',
        **({'semantic_sampling':semantic_sampling,'acceptance_basis':'explicit-frozen-sampling-policy'} if semantic_sampling else {}),
        'local_sample_status':sample_status,'sample_status_counts':dict(Counter(row['status'] for row in outputs)),
        'local_sample_status_counts':dict(Counter(row['status'] for row in outputs)),
        'package_review':{'status':batch_status,'method':'Delivered document content checks; no implied human sign-off'},
        'acceptance_scopes':{'sample':{'status':sample_status,'sample_count':len(outputs)},'batch':{'status':batch_status,'checks':batch},
            'pilot':{'status':'NOT_APPLICABLE','checks':[],'reason':'Delivery does not apply a pilot minimum.'},
            'corpus':{'status':'UNKNOWN'},'external':{'status':'UNKNOWN'}}}
    payload_files={key:value for key,value in input_files.items() if key not in ('qc_report.md','SHA256SUMS')}
    report['payload_files_sha256']=payload_files
    report['payload_sha256']=hashlib.sha256(json.dumps(payload_files,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    targets=profile['configuration']['targets']
    report['delivery_scope']={'scope':'delivery','expected_samples':targets['expected_samples'],
        'category_share':targets['category_share'],'max_category_share':targets['max_category_share'],
        'authority':profile['configuration']['authority'],'profile_id':profile['configuration']['profile_id']}
    if 'expected_sites' in targets:report['delivery_scope']['expected_sites']=targets['expected_sites']
    report['inspection_stage']=inspection_stage
    documents=delivery_document_review(reviews,report)
    report['delivery_document_review']=documents
    batch.append(qc_rule('DELIVERY_DOCUMENT_REVIEW',documents['status'],str(dataset),
        ['需求书§3/5/7：实际交付资料、来源分母、分布与真实审核结论'],
        documents['reason'] if 'reason' in documents else '; '.join(documents.get('errors',[])),
        'Actually read the delivered files and import the five payload-bound documentary decisions.',
        scope='batch',evidence=documents))
    report['acceptance_scopes']['batch']['status']=aggregate(row['status'] for row in batch)
    report['package_review'].update(status=report['acceptance_scopes']['batch']['status'],
        method='Delivered mechanical checks plus actual payload-bound delivery-document review; reviewer identity is explicit, not authenticated.')
    if inspection_stage=='final':
        final_summary=_verify_delivery_qc_report(dataset,report);batch.append(final_summary)
        report['acceptance_scopes']['batch']['status']=aggregate(row['status'] for row in batch)
        report['package_review']['status']=report['acceptance_scopes']['batch']['status']
    # These diagnostics are intentionally outside all contract aggregation.
    engineering={'excluded_from_delivery_gate':True,'baseline':{'status':'NOT_REQUESTED'},'capture':{'status':'NOT_REQUESTED'}}
    if baseline is not None:
        try:engineering['baseline']=baseline_load(baseline,samples_override)
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:engineering['baseline']={'status':'FAIL','error':str(error)}
    if evidence is not None:
        try:
            external=load_external_evidence(evidence,layout);engineering['capture']=external
            engineering['capture_integrity']=[{'sample_id':row['sample_id'],**capture_integrity(row['sample_path'],read(Path(row['sample_path'])/'annotation.json'),capture_context(layout,row['sample_path'],external).get('evidence_dir'))} for row in outputs]
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:engineering['capture']={'status':'FAIL','error':str(error)}
    report['engineering_audit']=engineering
    try:
        if package_files(dataset)!=input_files:initial_errors.append('Delivered files changed while QC was running.')
    except (OSError,ValueError) as error:initial_errors.append(str(error))
    report['input_integrity']={'status':'FAIL' if initial_errors else 'PASS','errors':initial_errors,'checked_before_and_after':True,'not_visual_acceptance':True}
    if initial_errors:
        changed=qc_rule('INPUT_CHANGED_DURING_QC','FAIL',str(dataset),['Read-only delivery QC'], '; '.join(initial_errors),'Inspect a stable final package.',scope='batch')
        batch.append(changed);report['acceptance_scopes']['batch']['status']='FAIL'
    if semantic_sampling:
        # Revalidate the immutable plan, every current sample and every actual
        # review at the exit boundary; no time-of-check/time-of-use acceptance.
        rechecked,_=evaluate_sampling(delivery_sampling_plan,dataset,ai_reviews=[reviews] if reviews else [],human_reviews=human_paths,ai_failures=failure_paths)
        if rechecked!=semantic_sampling:raise ValueError('Sampling evidence changed during delivery QC')
    report['status']=report['contract_status']=report['delivery_status']=report['local_acceptance_status']=aggregate([sample_status,report['acceptance_scopes']['batch']['status']])
    report['release_ready']=inspection_stage=='final' and report['delivery_status']=='PASS'
    return report
