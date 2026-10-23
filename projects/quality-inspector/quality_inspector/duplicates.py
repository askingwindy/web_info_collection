"""Read-only four-route diagnostics; near hashes are explicit proxies, not client algorithms."""
import argparse,json,re,hashlib,itertools
from collections import Counter,defaultdict
from pathlib import Path
from PIL import Image

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
def minimum_removal_sets(pairs):
    vertices=sorted({v for p in pairs for v in p})
    for n in range(len(vertices)+1):
        candidates=[list(c) for c in itertools.combinations(vertices,n) if all(set(c)&set(p) for p in pairs)]
        if candidates:return {'minimum_count':n,'all_minimal_size_options':candidates,'proposal_only_no_selection_applied':True}

def analyze(dataset):
    dataset=Path(dataset);rows=[];hashes=defaultdict(list)
    for p in sorted(dataset.glob('*/samples/*/annotation.json')):
        a=json.loads(p.read_text());sid=a['sample_id'];seq=[(s['action']['action_type'],s['action']['target_text'],s['page_name']) for s in a['steps']];images=[]
        for st in a['steps']:
            im=p.parent/st['image_path'];h=sha(im);images.append(h);raw=p.parent.parent.parent/'evidence'/sid/f'step_{st["step_id"]:03}.json';rr=json.loads(raw.read_text()) if raw.is_file() else {}
            hashes[h].append({'sample_id':sid,'step':st['step_id'],'image_path':str(im),'tree_path':str(p.parent/st['ui_tree_path']),'raw_evidence':str(raw),'page_name':st['page_name'],'url':rr.get('state',{}).get('url',''),'action':st['action'],'visible_text':rr.get('state',{}).get('visible_text',''),'focused_values':[v for v in rr.get('state',{}).get('values',[]) if v['focused']]})
        rows.append({'sample_id':sid,'annotation':a,'annotation_sha256':sha(p),'task_instruction':a['task_instruction'],'sequence':seq,'sequence_sha256':hashlib.sha256(canonical(seq).encode()).hexdigest(),'frame_sha256':images,'first_dhash':dhash(p.parent/a['steps'][0]['image_path']),'last_dhash':dhash(p.parent/a['steps'][-1]['image_path']),'instruction_simhash':simhash(a['task_instruction'])})
    exact=[{'sha256':h,'occurrences':v,'classification':'confirmed_contract_violation','observed_state':'Identical image bytes across distinct samples; actual page, step and action are recorded per occurrence.','source':'request/需求书-Web浏览器自动化操作轨迹数据集.md:102','whole_trajectory_duplicate_not_implied':True} for h,v in hashes.items() if len({o['sample_id'] for o in v})>1]
    exact_pairs=sorted({tuple(sorted((x['sample_id'],y['sample_id']))) for g in exact for x,y in itertools.combinations(g['occurrences'],2) if x['sample_id']!=y['sample_id']})
    pair_records=[];sequence_pairs=[];near_image=[];near_text=[]
    for a,b in itertools.combinations(rows,2):
        names=[a['sample_id'],b['sample_id']];dh=[distance(a['first_dhash'],b['first_dhash']),distance(a['last_dhash'],b['last_dhash'])];sh=distance(a['instruction_simhash'],b['instruction_simhash']);seq_equal=a['sequence']==b['sequence']
        if seq_equal:sequence_pairs.append({'sample_ids':names,'sequence_sha256':a['sequence_sha256'],'source':'request/需求书-Web浏览器自动化操作轨迹数据集.md:103'})
        if max(dh)<=4:near_image.append({'sample_ids':names,'first_hamming':dh[0],'last_hamming':dh[1],'classification':'proxy_algorithm_candidate_not_client_result'})
        if sh<=3:near_text.append({'sample_ids':names,'hamming':sh,'classification':'proxy_algorithm_candidate_not_client_result'})
        if tuple(sorted(names)) in exact_pairs:
            pair_records.append({'sample_ids':names,'shared_steps':[[x['step'],y['step']] for g in exact for x in g['occurrences'] for y in g['occurrences'] if x['sample_id']==names[0] and y['sample_id']==names[1]],'task_instructions':[a['task_instruction'],b['task_instruction']],'steps':[len(a['annotation']['steps']),len(b['annotation']['steps'])],'final_results':[a['annotation']['final_result'],b['annotation']['final_result']],'final_image_sha256':[a['frame_sha256'][-1],b['frame_sha256'][-1]],'final_images_equal':a['frame_sha256'][-1]==b['frame_sha256'][-1],'action_sequence_equal':seq_equal,'all_image_sequence_equal':a['frame_sha256']==b['frame_sha256'],'same_action_type_skeleton':[x[0] for x in a['sequence']]==[x[0] for x in b['sequence']],'classification':'confirmed_route1_violation_even_if_only_common_initial_state'})
    return {'dataset':str(dataset),'sample_count':len(rows),'pair_comparisons':len(rows)*(len(rows)-1)//2,'route1':{'groups':exact,'confirmed_pair_count':len(exact_pairs),'pairs':pair_records},'route2':{'confirmed_pairs':sequence_pairs,'count':len(sequence_pairs),'comparison':'exact list of (action_type,target_text,page_name); compare tuples directly, hash only a receipt','source':'request/需求书-Web浏览器自动化操作轨迹数据集.md:103'},'route3':{'candidates':near_image,'count':len(near_image),'threshold':'both first and last Hamming <=4','algorithm':'64-bit horizontal dHash, grayscale, Pillow LANCZOS resize 9x8, left>right comparison','customer_algorithm_equivalence':'UNKNOWN'},'route4':{'candidates':near_text,'count':len(near_text),'threshold':'SimHash Hamming <=3','algorithm':'64-bit SimHash; CJK bigrams + lowercased Latin/alphanumeric tokens; term frequency weights; first8 bytes SHA256; ties zero','customer_algorithm_equivalence':'UNKNOWN'},'confirmed_violations':{'route1_pairs':len(exact_pairs),'route2_pairs':len(sequence_pairs)},'accepted_shared_states':{'count':0,'reason':'Archived rule explicitly forbids any cross-trajectory static image reuse; no initial-state exemption found.'},'insufficient_rules':['Customer actual checker and near-hash implementation parameters unavailable; route3/4 proxies cannot prove client acceptance.','Whether the client will amend the no-common-initial-state rule is unknown; no exception applied.','Substantive task differences beyond the four deterministic comparisons require actual evidence review, not an invented similarity threshold.'],'minimum_removal_for_route1_only':minimum_removal_sets(exact_pairs),'not_removed_or_recaptured':True,'rows':[{'sample_id':x['sample_id'],'task_instruction':x['task_instruction'],'sequence_sha256':x['sequence_sha256'],'first_sha256':x['frame_sha256'][0],'last_sha256':x['frame_sha256'][-1]} for x in rows]}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=analyze(a.dataset)
    with a.output.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'samples':d['sample_count'],'pairs':d['pair_comparisons'],'route1_pairs':d['route1']['confirmed_pair_count'],'route2_pairs':d['route2']['count'],'route3_proxy_pairs':d['route3']['count'],'route4_proxy_pairs':d['route4']['count'],'minimum_removal_route1_only':d['minimum_removal_for_route1_only']['minimum_count']},ensure_ascii=False))
if __name__=='__main__':main()
