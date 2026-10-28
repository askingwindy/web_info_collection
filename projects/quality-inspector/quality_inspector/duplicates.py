"""Read-only exact four-route predicates with explicit population/rate accounting."""
import argparse,json,re,hashlib,itertools
from collections import Counter,defaultdict
from pathlib import Path
from PIL import Image
from .layout import discover

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def dhash(p):
    with Image.open(p) as im:
        small=im.convert('L').resize((9,8),Image.Resampling.LANCZOS);values=[small.getpixel((x,y)) for y in range(8) for x in range(9)]
    h=0
    for y in range(8):
        for x in range(8):h=(h<<1)|int(values[y*9+x]>values[y*9+x+1])
    return h

def simhash(text):
    tokens=[]
    for m in re.finditer(r'[\u4e00-\u9fff]+|[a-zA-Z0-9_]+',text.lower()):
        t=m.group();tokens.extend([t[i:i+2] for i in range(len(t)-1)] if re.fullmatch(r'[\u4e00-\u9fff]+',t) and len(t)>1 else [t])
    vector=[0]*64
    for t,weight in Counter(tokens).items():
        h=int.from_bytes(hashlib.sha256(t.encode()).digest()[:8],'big')
        for bit in range(64):vector[bit]+=weight if h&(1<<bit) else -weight
    return sum(1<<i for i,v in enumerate(vector) if v>0)
def distance(a,b):return (a^b).bit_count()


def summarize(result, current_sample_ids=None):
    """OR every route; semantic DISTINCT cannot clear a deterministic hit.

    A batch rate uses only the explicit current population. Historical-only
    matches stay visible in diagnostics but do not enter the batch numerator.
    """
    ids=[row['sample_id'] for row in result['rows']]
    if len(ids)!=len(set(ids)):raise ValueError('Repeated duplicate-summary population')
    all_ids=set(ids)
    current=all_ids if current_sample_ids is None else set(current_sample_ids)
    if not current<=all_ids:raise ValueError('Current duplicate-summary IDs are outside the inspected population')
    routes={};route_keys=(('route1','confirmed_pair_count','pairs'),('route2','count','confirmed_pairs'),
                         ('route3','count','candidates'),('route4','count','candidates'))
    for route,count_key,rows_key in route_keys:
        pairs=set()
        for row in result[route][rows_key]:
            pair=row.get('sample_ids')
            if (not isinstance(pair,list) or len(pair)!=2 or len(set(pair))!=2
                    or any(not isinstance(sid,str) or sid not in all_ids for sid in pair)):
                raise ValueError('Invalid four-route pair identity: '+route)
            pairs.add(tuple(sorted(pair)))
        if len(pairs)!=len(result[route][rows_key]) or result[route][count_key]!=len(pairs):
            raise ValueError('Four-route count/pair records disagree: '+route)
        routes[route]=pairs
    pairs=set().union(*routes.values())
    adjudications=[{'sample_ids':list(pair),'matched_routes':[route for route,values in routes.items() if pair in values],
        'status':'RESOLVED','classification':'NEAR_DUPLICATE','semantic_exemption_allowed':False}
        for pair in sorted(pairs)]
    unresolved=[row for row in adjudications if row['status']!='RESOLVED']
    batch_pairs=[row for row in adjudications if set(row['sample_ids'])&current]
    historical=[row for row in adjudications if not set(row['sample_ids'])&current]
    affected=sorted({sid for row in batch_pairs for sid in row['sample_ids'] if sid in current})
    count=len(current);history_count=len(all_ids-current)
    pair_domain=count*history_count+count*(count-1)//2
    sample_rate=len(affected)/count if count else None
    pair_rate=len(batch_pairs)/pair_domain if pair_domain else (0.0 if count else None)
    return {'schema_version':'qc-four-route-resolution-1','analysis_status':'COMPLETE' if count else 'PENDING',
        'population_scope':'all-inspected-samples' if current_sample_ids is None else 'explicit-current-batch-plus-history',
        'current_sample_ids':sorted(current),'current_sample_count':count,'history_sample_count':history_count,
        'all_inspected_sample_count':len(all_ids),'all_inspected_pair_domain':len(all_ids)*(len(all_ids)-1)//2,
        'current_involved_pair_domain':pair_domain,
        'route_pair_counts':{route:len(values) for route,values in routes.items()},
        'current_route_pair_counts':{route:sum(bool(set(pair)&current) for pair in values) for route,values in routes.items()},
        'historical_only_route_pair_counts':{route:sum(not bool(set(pair)&current) for pair in values) for route,values in routes.items()},
        'all_inspected_union_pair_count':len(adjudications),'current_union_pair_count':len(batch_pairs),
        'historical_only_union_pair_count':len(historical),'pair_adjudications':adjudications,
        'unadjudicated_pair_count':len(unresolved) if count else None,
        'affected_current_sample_ids':affected,'affected_current_sample_count':len(affected),
        'near_duplicate_sample_rate':sample_rate,
        'sample_rate_definition':'unique current samples involved in any four-route hit / current_sample_count; historical samples never dilute this denominator',
        'near_duplicate_pair_rate':pair_rate,
        'pair_rate_definition':'unique current-involved hit pairs / (current*history + current*(current-1)/2)',
        'maximum_near_duplicate_sample_rate':0.001,
        'sample_rate_within_requested_limit':sample_rate<=0.001 if sample_rate is not None else None,
        'strict_zero_hit_gate':'FAIL' if batch_pairs else 'PASS' if count and not unresolved else 'PENDING',
        'decision_policy':'Any configured route hit is a near duplicate. No semantic/AI/human DISTINCT exemption. Existing zero-hit gate remains stricter than the requested rate cap.'}


def analysis_error(error, *, sample_count=None, dataset_label='unreadable-input-set'):
    """A failed scan has unknown counts, never a fabricated four-route zero."""
    return {'dataset':str(dataset_label),'sample_count':sample_count,'pair_comparisons':None,'error':str(error),
        'analysis_status':'FAILED','route1':{'groups':[],'pairs':[],'confirmed_pair_count':None},
        'route2':{'confirmed_pairs':[],'count':None},'route3':{'candidates':[],'count':None},
        'route4':{'candidates':[],'count':None},
        'summary':{'schema_version':'qc-four-route-resolution-1','analysis_status':'FAILED',
            'current_sample_count':sample_count,'current_union_pair_count':None,
            'unadjudicated_pair_count':None,'unadjudicated_status':'UNKNOWN_CHECK_FAILED',
            'near_duplicate_sample_rate':None,'near_duplicate_pair_rate':None,
            'strict_zero_hit_gate':'PENDING','reason':'Four-route evaluation did not complete; unknown is not zero or PASS.'}}
def minimum_removal_sets(pairs):
    vertices=sorted({v for p in pairs for v in p})
    if len(vertices)>16:
        # Exact vertex-cover enumeration is only explanatory diagnostics. It
        # must never prevent a large duplicate batch from being rejected.
        edges={tuple(sorted(pair)) for pair in pairs};used=set();lower=0
        for first,second in sorted(edges):
            if first not in used and second not in used:
                used.update((first,second));lower+=1
        remaining=set(edges);proposal=[]
        while remaining:
            degrees=Counter(vertex for pair in remaining for vertex in pair)
            vertex=min(degrees,key=lambda value:(-degrees[value],value));proposal.append(vertex)
            remaining={pair for pair in remaining if vertex not in pair}
        return {'minimum_count':None,'all_minimal_size_options':[],
                'exact_minimum_computed':False,'lower_bound':lower,'upper_bound':len(proposal),
                'one_cover_proposal':sorted(proposal),'proposal_only_no_selection_applied':True,
                'reason':'Above 16 vertices, return honest matching/cover bounds instead of exponential subset enumeration. All duplicate pairs remain failures.'}
    for n in range(len(vertices)+1):
        candidates=[list(c) for c in itertools.combinations(vertices,n) if all(set(c)&set(p) for p in pairs)]
        if candidates:return {'minimum_count':n,'all_minimal_size_options':candidates,'proposal_only_no_selection_applied':True}

def hamming_candidates(values, radius):
    """Exact-recall pigeonhole index: <=r changed bits leave one of r+1 blocks equal."""
    if type(radius) is not int or not 0 <= radius < 64:
        raise ValueError('Hamming radius must be an integer in [0, 63]')
    candidates=set(); buckets=defaultdict(list)
    for index,value in enumerate(values):
        if type(value) is not int or not 0 <= value < 2**64:
            raise ValueError('Index values must be unsigned 64-bit integers')
        for block in range(radius+1):
            start=64*block//(radius+1); end=64*(block+1)//(radius+1)
            key=(block,(value>>start)&((1<<(end-start))-1))
            candidates.update((other,index) for other in buckets[key]); buckets[key].append(index)
    return candidates


def indexed_routes(rows):
    sequence=defaultdict(list)
    for index,row in enumerate(rows):sequence[canonical(row['sequence'])].append(index)
    route2={pair for group in sequence.values() for pair in itertools.combinations(group,2)}
    image_candidates=hamming_candidates([r['first_dhash'] for r in rows],4)&hamming_candidates([r['last_dhash'] for r in rows],4)
    text_candidates=hamming_candidates([r['instruction_simhash'] for r in rows],3)
    route3={(a,b) for a,b in image_candidates if max(distance(rows[a]['first_dhash'],rows[b]['first_dhash']),distance(rows[a]['last_dhash'],rows[b]['last_dhash']))<=4}
    route4={(a,b) for a,b in text_candidates if distance(rows[a]['instruction_simhash'],rows[b]['instruction_simhash'])<=3}
    return {'route2':route2,'route3':route3,'route4':route4}, {'route3_candidate_comparisons':len(image_candidates),'route4_candidate_comparisons':len(text_candidates)}


def exhaustive_routes(rows):
    routes={'route2':set(),'route3':set(),'route4':set()}
    for i,j in itertools.combinations(range(len(rows)),2):
        a,b=rows[i],rows[j]
        if a['sequence']==b['sequence']:routes['route2'].add((i,j))
        if max(distance(a['first_dhash'],b['first_dhash']),distance(a['last_dhash'],b['last_dhash']))<=4:routes['route3'].add((i,j))
        if distance(a['instruction_simhash'],b['instruction_simhash'])<=3:routes['route4'].add((i,j))
    return routes


CACHE_VERSION='qc-fingerprints-1'


def analyze_inputs(annotation_paths, evidence_contexts=None, *, cache=None, verify_exhaustive=False,
                   dataset_label='explicit-input-set', current_sample_ids=None):
    """Read-only samples; optional cache is outside all samples and never acceptance evidence.

    Final validation can force raw recomputation and compare the exact-recall
    indexed results with the independent exhaustive loop. No approximate recall.
    """
    paths=sorted(Path(p).resolve() for p in annotation_paths)
    if len(paths)!=len(set(paths)):raise ValueError('Duplicate annotation input path')
    if cache and any(Path(cache).resolve().is_relative_to(p.parent) for p in paths):
        raise ValueError('Fingerprint cache must be outside inspected samples')
    # A source/runtime change invalidates acceleration facts independently of
    # review migration. The cache never supplies image SHA or release evidence.
    import PIL
    implementation=hashlib.sha256((sha(__file__)+'|Pillow='+PIL.__version__).encode()).hexdigest()
    cached={}; hits=0; mismatches=[]
    if cache and Path(cache).is_file():
        value=json.loads(Path(cache).read_text())
        if isinstance(value,dict) and value.get('schema_version')==CACHE_VERSION and value.get('implementation_sha256')==implementation and isinstance(value.get('records'),dict):cached=value['records']
    updated={};rows=[];hashes=defaultdict(list);seen=set()
    for p in paths:
        a=json.loads(p.read_text());sid=a['sample_id']
        if not isinstance(sid,str) or not sid:raise ValueError('Missing or malformed sample ID')
        if sid in seen:raise ValueError('Duplicate sample ID in inspected set: '+sid)
        seen.add(sid)
        seq=[(s['action']['action_type'],s['action']['target_text'],s['page_name']) for s in a['steps']];images=[]
        for st in a['steps']:
            relative=st['image_path'];im=p.parent/relative
            if Path(relative).is_absolute() or not im.resolve().is_relative_to(p.parent) or im.is_symlink():raise ValueError('Unsafe image reference')
            h=sha(im);images.append(h)
            context=(evidence_contexts or {}).get(sid,{})
            directory=Path(context['evidence_dir']) if context.get('evidence_dir') else None
            raw=directory/f'step_{st["step_id"]:03}.json' if directory else None;rr=json.loads(raw.read_text()) if raw and raw.is_file() else {}
            hashes[h].append({'sample_id':sid,'step':st['step_id'],'image_path':str(im),'tree_path':str(p.parent/st['ui_tree_path']),'raw_evidence':str(raw),'page_name':st['page_name'],'url':rr.get('state',{}).get('url',''),'action':st['action'],'visible_text':rr.get('state',{}).get('visible_text',''),'focused_values':[v for v in rr.get('state',{}).get('values',[]) if v.get('focused')]})
        annotation_sha=sha(p)
        key=hashlib.sha256(canonical({'version':CACHE_VERSION,'implementation':implementation,'annotation':annotation_sha,'images':images}).encode()).hexdigest()
        value=cached.get(key)
        valid=isinstance(value,dict) and set(value)=={'first_dhash','last_dhash','instruction_simhash'} and all(type(v)is int and 0<=v<2**64 for v in value.values())
        if not valid or verify_exhaustive:
            actual={'first_dhash':dhash(p.parent/a['steps'][0]['image_path']),'last_dhash':dhash(p.parent/a['steps'][-1]['image_path']),'instruction_simhash':simhash(a['task_instruction'])}
            if valid and value!=actual:mismatches.append(sid)
            value=actual
        else:hits+=1
        updated[key]=value
        rows.append({'sample_id':sid,'annotation':a,'annotation_sha256':annotation_sha,'task_instruction':a['task_instruction'],'sequence':seq,'sequence_sha256':hashlib.sha256(canonical(seq).encode()).hexdigest(),'frame_sha256':images,**value})
    indexed,candidate_stats=indexed_routes(rows)
    comparison={'executed':verify_exhaustive,'status':'NOT_RUN','pair_count':0,'cache_fingerprint_mismatches':mismatches}
    if verify_exhaustive:
        expected=exhaustive_routes(rows)
        comparison.update(status='PASS' if indexed==expected and not mismatches else 'FAIL',pair_count=len(rows)*(len(rows)-1)//2,
                          route_differences={route:{'missing':sorted(expected[route]-indexed[route]),'extra':sorted(indexed[route]-expected[route])} for route in expected})
    exact=[{'sha256':h,'occurrences':v,'classification':'confirmed_contract_violation','observed_state':'Identical image bytes across distinct samples.','source':'requirement §6 route 1','whole_trajectory_duplicate_not_implied':True} for h,v in hashes.items() if len({o['sample_id'] for o in v})>1]
    shared_steps=defaultdict(list)
    for group in exact:
        for first,second in itertools.combinations(group['occurrences'],2):
            if first['sample_id']==second['sample_id']:continue
            if first['sample_id']>second['sample_id']:first,second=second,first
            shared_steps[(first['sample_id'],second['sample_id'])].append([first['step'],second['step']])
    byid={r['sample_id']:r for r in rows};exact_pairs=sorted(shared_steps);pair_records=[]
    for first,second in exact_pairs:
        a,b=byid[first],byid[second]
        pair_records.append({'sample_ids':[first,second],'shared_steps':shared_steps[(first,second)],'task_instructions':[a['task_instruction'],b['task_instruction']],'steps':[len(a['annotation']['steps']),len(b['annotation']['steps'])],'final_results':[a['annotation']['final_result'],b['annotation']['final_result']],'final_image_sha256':[a['frame_sha256'][-1],b['frame_sha256'][-1]],'final_images_equal':a['frame_sha256'][-1]==b['frame_sha256'][-1],'action_sequence_equal':a['sequence']==b['sequence'],'all_image_sequence_equal':a['frame_sha256']==b['frame_sha256'],'same_action_type_skeleton':[x[0] for x in a['sequence']]==[x[0] for x in b['sequence']],'classification':'confirmed_route1_violation_even_if_only_common_initial_state'})
    sequence_pairs=[{'sample_ids':[rows[i]['sample_id'],rows[j]['sample_id']],'sequence_sha256':rows[i]['sequence_sha256']} for i,j in sorted(indexed['route2'])]
    near_image=[{'sample_ids':[rows[i]['sample_id'],rows[j]['sample_id']],'first_hamming':distance(rows[i]['first_dhash'],rows[j]['first_dhash']),'last_hamming':distance(rows[i]['last_dhash'],rows[j]['last_dhash']),'classification':'confirmed_route3_threshold_hit'} for i,j in sorted(indexed['route3'])]
    near_text=[{'sample_ids':[rows[i]['sample_id'],rows[j]['sample_id']],'hamming':distance(rows[i]['instruction_simhash'],rows[j]['instruction_simhash']),'classification':'confirmed_route4_threshold_hit'} for i,j in sorted(indexed['route4'])]
    if cache:
        import os,tempfile
        target=Path(cache);target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,delete=False,encoding='utf-8') as stream:
            json.dump({'schema_version':CACHE_VERSION,'implementation_sha256':implementation,'records':updated},stream,ensure_ascii=False);temporary=stream.name
        os.replace(temporary,target)
    result={'dataset':str(dataset_label),'sample_count':len(rows),'pair_comparisons':len(rows)*(len(rows)-1)//2,
            'pair_comparisons_meaning':'complete logical unordered-pair domain, not physical index comparisons',
            'search':{'method':'exact-recall Hamming partition index with exact threshold filtering','recall_guarantee':'r+1 disjoint blocks: <=r bit differences share at least one complete block',**candidate_stats,'exhaustive_verification':comparison,'cache_hits':hits,'cache_is_not_review_evidence':True},
            'route1':{'groups':exact,'confirmed_pair_count':len(exact_pairs),'pairs':pair_records},
            'route2':{'confirmed_pairs':sequence_pairs,'count':len(sequence_pairs),'comparison':'exact full sequence tuples'},
            'route3':{'candidates':near_image,'count':len(near_image),'threshold':'both first and last Hamming <=4','algorithm':'64-bit horizontal dHash; grayscale; Pillow LANCZOS 9x8; left>right','customer_algorithm_equivalence':'UNKNOWN'},
            'route4':{'candidates':near_text,'count':len(near_text),'threshold':'SimHash Hamming <=3','algorithm':'64-bit CJK bigrams and lowercase Latin/alphanumeric; TF weights; first8 SHA256; ties zero','customer_algorithm_equivalence':'UNKNOWN'},
            'confirmed_violations':{'route1_pairs':len(exact_pairs),'route2_pairs':len(sequence_pairs)},
            'accepted_shared_states':{'count':0,'reason':'No cross-sample shared-state exemption'},
            'insufficient_rules':['Local hashes do not prove customer algorithm equivalence.','Substantive differences require actual review.'],
            'minimum_removal_for_route1_only':minimum_removal_sets(exact_pairs),'not_removed_or_recaptured':True,
            'rows':[{'sample_id':x['sample_id'],'task_instruction':x['task_instruction'],'sequence_sha256':x['sequence_sha256'],'first_sha256':x['frame_sha256'][0],'last_sha256':x['frame_sha256'][-1]} for x in rows]}
    result['summary']=summarize(result,current_sample_ids)
    if comparison['status']=='FAIL':
        result['summary'].update(analysis_status='FAILED',strict_zero_hit_gate='PENDING',
            unadjudicated_pair_count=None,unadjudicated_status='UNKNOWN_INDEX_OR_CACHE_DISAGREEMENT',
            near_duplicate_sample_rate=None,near_duplicate_pair_rate=None,sample_rate_within_requested_limit=None)
    return result


def analyze(dataset,evidence_contexts=None,*,cache=None,verify_exhaustive=True):
    dataset=Path(dataset);layout=discover(dataset)
    if layout.errors:raise ValueError('; '.join(layout.errors))
    if evidence_contexts is None:
        evidence_contexts={}
        for path in layout.annotations:
            directory=layout.native_evidence(path.parent)
            if directory:evidence_contexts[json.loads(path.read_text())['sample_id']]={'evidence_dir':str(directory)}
    return analyze_inputs(layout.annotations,evidence_contexts,cache=cache,verify_exhaustive=verify_exhaustive,dataset_label=dataset)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=analyze(a.dataset)
    with a.output.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'samples':d['sample_count'],'pairs':d['pair_comparisons'],'route1_pairs':d['route1']['confirmed_pair_count'],'route2_pairs':d['route2']['count'],'route3_proxy_pairs':d['route3']['count'],'route4_proxy_pairs':d['route4']['count'],'minimum_removal_route1_only':d['minimum_removal_for_route1_only']['minimum_count']},ensure_ascii=False))
if __name__=='__main__':main()
