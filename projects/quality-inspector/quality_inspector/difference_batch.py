"""Experimental three-neighbor comparison, never a production QC import.

Every original step remains an image presentation. Only the repeated focal
trajectory is shared across the three complete pair comparisons.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

from webcollect.batch_core import file_sha, load_json
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256
from . import ai_worker

VERSION='three-neighbor-original-frame-calibration-2'
JOB_KIND='ai-difference-batch-calibration'
PURPOSE='difference-three-neighbor-calibration-v2'
STATES=('PASS','FAIL','REVIEW_REQUIRED')
RELATIONSHIPS={'PASS':'SUBSTANTIVELY_DISTINCT','FAIL':'SAME_BUSINESS_OR_PARAMETER_ONLY',
               'REVIEW_REQUIRED':'UNCERTAIN'}


def _text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _sources():
    import webcollect.batch_core as batch_core
    import webcollect.model_gateway as model_gateway
    return {str(Path(path).resolve()):file_sha(path) for path in
            (__file__,ai_worker.__file__,batch_core.__file__,model_gateway.__file__)}


def _object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def _exact_integers(values):
    return {'type':'array','prefixItems':[{'const':v} for v in values],
            'items':False,'minItems':len(values),'maxItems':len(values)}


def _material(source_job):
    if (not isinstance(source_job,dict) or source_job.get('kind')!='ai-difference'
            or not isinstance(source_job.get('id'),str) or not source_job['id']
            or not isinstance(source_job.get('payload'),dict)):
        raise ValueError('An existing ai-difference job and its exact payload are required')
    payload=source_job['payload'];neighbors=payload.get('neighbors')
    if not isinstance(neighbors,list) or len(neighbors)!=3:
        raise ValueError('Exactly three full original neighbors are required')
    if payload.get('comparison_version')!=object_sha256(neighbors):
        raise ValueError('Original comparison version differs from the three neighbor snapshots')
    snapshots=[payload['candidate'],*neighbors]
    if any(not isinstance(value,dict) for value in snapshots):
        raise ValueError('Every trajectory must be an exact original snapshot')
    paths=[value.get('path') for value in snapshots]
    if len(paths)!=len(set(paths)):raise ValueError('Focal and neighbor roots must be distinct')
    trajectories=[];manifest=[];images=[];seen_ids=set()
    for ordinal,value in enumerate(snapshots):
        ai_worker.verify_snapshot(value)
        root=Path(value['path']);annotation=load_json(root/'annotation.json')
        sid=annotation['sample_id'];steps=annotation['steps'];role='focal' if not ordinal else 'neighbor_'+str(ordinal)
        if not isinstance(sid,str) or not sid or sid in seen_ids:
            raise ValueError('Focal and neighbor sample identities must be distinct')
        seen_ids.add(sid)
        step_ids=[step['step_id'] for step in steps]
        if (not step_ids or any(type(v) is not int for v in step_ids)
                or step_ids!=list(range(1,len(steps)+1))
                or annotation.get('completion_status')!='success'
                or steps[-1].get('action',{}).get('action_type')!='complete'):
            raise ValueError('Each complete original trajectory must retain every ordered step')
        for field in ('image_path','ui_tree_path'):
            if len({step[field] for step in steps})!=len(steps):
                raise ValueError('Each original step needs its own bound image and tree path')
        context,originals=ai_worker.compact_trajectory(value)
        dimensions=annotation['device_info']['screen_resolution'];indices=[]
        for step,path in zip(steps,originals):
            tree_path=root/step['ui_tree_path'];tree=load_json(tree_path)
            if tree.get('image_path')!=step['image_path'] or tree.get('screen_resolution')!=dimensions:
                raise ValueError('Original UI tree does not bind the corresponding full frame')
            with Image.open(path) as png:
                if png.format!='PNG' or list(png.size)!=dimensions:
                    raise ValueError('Original full-resolution PNG required; no thumbnails or composites')
                png.verify()
            index=len(images)+1;indices.append(index);images.append(str(path.resolve()))
            manifest.append({'image_index':index,'trajectory_key':role,'sample_id':sid,
                'step_id':step['step_id'],'image_path':str(path.resolve()),'image_sha256':file_sha(path),
                'ui_tree_path':str(tree_path.resolve()),'ui_tree_sha256':file_sha(tree_path),
                'annotation_sha256':value['annotation_sha256'],'resolution':dimensions})
        trajectories.append({'trajectory_key':role,'sample_id':sid,
            'annotation_sha256':value['annotation_sha256'],'image_indices':indices,
            'step_ids':step_ids,'trajectory':context})
        ai_worker.verify_snapshot(value)
    focal=len(trajectories[0]['step_ids']);other=[len(t['step_ids']) for t in trajectories[1:]]
    return {'source_job_id':source_job['id'],'source_payload_sha256':object_sha256(payload),
        'comparison_version':payload['comparison_version'],
        'comparison_scope':payload.get('comparison_scope','Explicit source job only'),
        'trajectories':trajectories,'image_manifest':manifest,'image_paths':images,
        'image_presentations':{'three_complete_pairs_without_chunk_repetition':3*focal+sum(other),
            'merged_complete_trajectories':focal+sum(other),'repeated_focal_presentations_removed':2*focal,
            'focal_frames':focal,'neighbor_frames':other,
            'basis':'Image presentation arithmetic, not API request counts or a measured fee reduction.'}}


def _request(material):
    focal=material['trajectories'][0];pairs=[]
    for index,neighbor in enumerate(material['trajectories'][1:]):
        pair=_object({'neighbor_index':{'const':index},
            'focal_sample_id':{'const':focal['sample_id']},
            'focal_annotation_sha256':{'const':focal['annotation_sha256']},
            'neighbor_sample_id':{'const':neighbor['sample_id']},
            'neighbor_annotation_sha256':{'const':neighbor['annotation_sha256']},
            'covered_focal_step_ids':_exact_integers(focal['step_ids']),
            'covered_neighbor_step_ids':_exact_integers(neighbor['step_ids']),
            'status':{'type':'string','enum':list(STATES)},
            'relationship':{'type':'string','enum':list(RELATIONSHIPS.values())},
            'note':{'type':'string','minLength':1},
            'evidence_steps':{'type':'array','items':{'type':'integer','enum':focal['step_ids']},
                              'minItems':1,'uniqueItems':True},
            'neighbor_evidence_steps':{'type':'array','items':{'type':'integer','enum':neighbor['step_ids']},
                                       'minItems':1,'uniqueItems':True}})
        pair['allOf']=[{'$ref':'#/$defs/relationship_status'}]
        pairs.append(pair)
    schema=_object({'pair_decisions':{'type':'array','minItems':3,'maxItems':3,
                                      'items':{'oneOf':pairs}}})
    schema['$defs']={'relationship_status':{'oneOf':[
        {'properties':{'status':{'const':status},'relationship':{'const':relationship}},
         'required':['status','relationship']} for status,relationship in RELATIONSHIPS.items()]}}
    mapping=[{k:row[k] for k in ('image_index','trajectory_key','sample_id','step_id','image_sha256')}
             for row in material['image_manifest']]
    text=json.dumps({'instruction':
        'EXPERIMENTAL CALIBRATION ONLY. Compare the focal trajectory independently with EACH of the three '
        'neighbors for substantive business/goal/action differences. Parameter/keyword-only changes do not '
        'qualify. The status is the qualification decision for substantive difference: '
        'PASS with relationship SUBSTANTIVELY_DISTINCT means the pair has substantively different business, '
        'goals or actions; FAIL with relationship SAME_BUSINESS_OR_PARAMETER_ONLY means the pair is the same '
        'business or differs only in parameters/keywords; REVIEW_REQUIRED with relationship UNCERTAIN means '
        'evidence is insufficient to determine the relationship. These are the only valid status/relationship '
        'combinations. A pair whose business is substantively different qualifies as PASS. '
        'All actions and EVERY original full frame are supplied; the focal images are shared once, '
        'not omitted from any pair. Image index 1 means the first image supplied after this text. '
        'Use the explicit global image-index mapping to associate every image with its trajectory and step. '
        'Inspect each complete pair including intermediate and terminal frames. Return exactly one decision '
        'for each neighbor identity with complete, ordered covered step IDs and valid focal/neighbor evidence. '
        'Keep reasons concise without omitting contradictions. Retain FAIL and REVIEW_REQUIRED per pair; '
        'uncertainty in one pair cannot be replaced by another pair PASS. This does not perform visual QC, '
        'approve a sample, authenticate actual reading, or authorize production.',
        'comparison_scope':material['comparison_scope'],
        'comparison_version':material['comparison_version'],
        'trajectories':material['trajectories'],'image_index_mapping':mapping,
        'complete_image_manifest_sha256':object_sha256(material['image_manifest'])},ensure_ascii=False,sort_keys=True)
    return text,schema,list(material['image_paths'])


def _budget(ledger,text,schema,images):
    model=ledger.config.get('model')
    if not model:raise ValueError('An explicitly configured image model is required')
    if len(images)>model['max_images']:
        raise ValueError('Complete merged originals exceed configured image limit; no frame was dropped')
    if not model.get('supports_vision',True):raise ValueError('Configured model has no image capability')
    bound=(len(text.encode())+len(json.dumps(schema).encode())+
           len(json.dumps(schema,ensure_ascii=False,sort_keys=True).encode())+4096+
           model.get('request_overhead_tokens',0)+len(images)*model.get('image_tokens_per_image',0))
    if bound>model['reserve_input_tokens']:
        raise ValueError('Complete merged text/schema/images exceed input reservation; no truncation or splitting')
    return bound


def prepare(ledger,source_job):
    """Enqueue one separate calibration job after complete evidence/budget checks."""
    sources=_sources();material=_material(source_job)
    if source_job['payload'].get('mode')!=ledger.config['mode']:
        raise ValueError('Source trajectory mode differs from the calibration mode')
    text,schema,images=_request(material)
    bound=_budget(ledger,text,schema,images)
    if _sources()!=sources:raise ValueError('Calibration implementation changed during preparation')
    value={'version':VERSION,'experimental':True,'calibration_only':True,
        'production_review_import_allowed':False,'source_job':{
            'id':source_job['id'],'kind':source_job['kind'],'payload':deepcopy(source_job['payload'])},
        'material':material,'material_sha256':object_sha256(material),'source_identity':sources,
        'model':deepcopy(ledger.config['model']),'mode':ledger.config['mode'],
        'request_text_sha256':_text_sha(text),'request_schema_sha256':object_sha256(schema),
        'complete_input_bound':bound}
    jid=ledger.enqueue(JOB_KIND,value)
    return {'job_id':jid,'material_sha256':value['material_sha256'],
            'image_presentations':material['image_presentations'],'complete_input_bound':bound,
            'calibration_only':True,'production_review_import_allowed':False}


def _verify(ledger,job):
    value=job['payload']
    if (job.get('kind')!=JOB_KIND or value.get('version')!=VERSION
            or value.get('experimental') is not True or value.get('calibration_only') is not True
            or value.get('production_review_import_allowed') is not False):
        raise ValueError('Only the separate experimental calibration job is accepted')
    if value['source_identity']!=_sources():raise ValueError('Calibration implementation changed')
    if value['model']!=ledger.config['model'] or value['mode']!=ledger.config['mode']:
        raise ValueError('Frozen calibration model/mode changed')
    material=_material(value['source_job'])
    if material!=value['material'] or object_sha256(material)!=value['material_sha256']:
        raise ValueError('Calibration source trajectories or manifest changed')
    text,schema,images=_request(material)
    if _text_sha(text)!=value['request_text_sha256'] or object_sha256(schema)!=value['request_schema_sha256']:
        raise ValueError('Calibration request identity changed')
    if _budget(ledger,text,schema,images)!=value['complete_input_bound']:
        raise ValueError('Calibration input bound changed')
    return material,text,schema,images


def _synthetic(material):
    focal=material['trajectories'][0]
    return {'pair_decisions':[{
        'neighbor_index':i,'focal_sample_id':focal['sample_id'],
        'focal_annotation_sha256':focal['annotation_sha256'],
        'neighbor_sample_id':other['sample_id'],'neighbor_annotation_sha256':other['annotation_sha256'],
        'covered_focal_step_ids':list(focal['step_ids']),'covered_neighbor_step_ids':list(other['step_ids']),
        'status':'REVIEW_REQUIRED','relationship':'UNCERTAIN',
        'note':'SYNTHETIC calibration protocol; no real model judgment.',
        'evidence_steps':[focal['step_ids'][-1]],'neighbor_evidence_steps':[other['step_ids'][-1]]}
        for i,other in enumerate(material['trajectories'][1:])]}


def do_comparison(ledger,gateway,job,*,synthetic_response=None):
    """One ModelGateway call; the caller owns claim/finish and error persistence."""
    material,text,schema,images=_verify(ledger,job)
    if synthetic_response is not None and ledger.config['mode']!='synthetic':
        raise ValueError('Controlled responses cannot be supplied to real calibration')
    result=gateway.call(job,PURPOSE,text,schema,images=images,attempts=1,
        synthetic_response=synthetic_response if synthetic_response is not None else _synthetic(material))
    _verify(ledger,job)
    Draft202012Validator(schema).validate(result)
    pairs=result['pair_decisions']
    if {p['neighbor_index'] for p in pairs}!={0,1,2}:
        raise ValueError('Three distinct, correctly bound neighbor decisions are required')
    if any(not p['note'].strip() for p in pairs):raise ValueError('Each pair needs a specific nonempty reason')
    pairs=sorted(pairs,key=lambda p:p['neighbor_index'])
    status='FAIL' if any(p['status']=='FAIL' for p in pairs) else 'REVIEW_REQUIRED' if any(p['status']=='REVIEW_REQUIRED' for p in pairs) else 'PASS'
    return {'schema_version':'webcollect-difference-batch-calibration-1','version':VERSION,
        'experimental':True,'calibration_only':True,'production_review_import_allowed':False,
        'QC_approval':False,'sample_ids_allocated':0,'status':status,'pair_decisions':pairs,
        'model_job_id':job['id'],'source_job_id':material['source_job_id'],
        'material_sha256':job['payload']['material_sha256'],'comparison_version':material['comparison_version'],
        'image_manifest':material['image_manifest'],'image_presentations':material['image_presentations'],
        'coverage_semantics':'All original frames were supplied and every pair declared complete step coverage; actual model reading is not authenticated.',
        'cost_semantics':'Only the ledger reports actual usage/estimated fees; fewer image presentations do not imply an equal fee reduction.'}
