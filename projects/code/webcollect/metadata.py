"""按需求列序生成 metadata.csv；不将结构通过宣称为合格交付。"""
import csv
from webcollect import workspace_json as json
from pathlib import Path
from .validate import read_json, validate_sample, StrictValidator, SCHEMAS

COLUMNS=['sample_id','site_id','site_category','app_name','task_type','task_instruction',
         'steps','screen_resolution','completion_status','actions','bytes']
ARRAY_COLUMNS=['task_type','screen_resolution','actions']


def assert_output_outside_samples(output, batch):
    output=Path(output).resolve()
    samples=(Path(batch)/'samples').resolve()
    if output.is_relative_to(samples):
        raise ValueError('报告和 metadata 必须位于 samples 之外')


def export_metadata(batch, output):
    batch=Path(batch).resolve()
    output=Path(output)
    assert_output_outside_samples(output,batch)
    manifest=read_json(batch/'manifest.json')
    if not isinstance(manifest,dict) or manifest.get('sample_kind') not in ('real','integration'):
        raise ValueError('批次清单 sample_kind 无效')
    if not isinstance(manifest.get('samples'),list) or not manifest['samples']:
        raise ValueError('批次清单 samples 必须为非空数组')
    if len(manifest['samples'])!=len(set(manifest['samples'])):
        raise ValueError('批次清单中存在重复样本编号')
    sites=manifest.get('sites')
    if not isinstance(sites,list) or any(not isinstance(s,dict) for s in sites):
        raise ValueError('站点映射必须为对象数组')
    site_map={s.get('site_id'):s for s in sites}
    if len(site_map)!=len(sites): raise ValueError('站点编号重复')
    samples=batch/'samples'
    actual={p.name for p in samples.iterdir()}
    if actual!=set(manifest['samples']): raise ValueError('批次样本清单与实际目录不一致')
    rows=[]
    schema=json.loads(SCHEMAS.joinpath('metadata-row.schema.json').read_text())
    for sample_id in manifest['samples']:
        if not isinstance(sample_id,str) or '/' in sample_id or '\\' in sample_id:
            raise ValueError('样本编号必须为无路径分隔符的字符串')
        sample=samples/sample_id
        if sample.is_symlink() or not sample.is_dir(): raise ValueError('样本必须为实体目录')
        result=validate_sample(sample,manifest['sample_kind'] if manifest['sample_kind']=='integration' else 'delivery',manifest)
        if not result['structural_pass']: raise ValueError(f'{sample_id} 结构未通过：{result["issues"][0]}')
        data=read_json(sample/'annotation.json')
        site_id=sample_id.split('_sample_')[0]
        if site_id not in site_map: raise ValueError('缺少站点映射')
        row={'sample_id':sample_id,'site_id':site_id,'site_category':site_map[site_id].get('site_category',''),
             'app_name':data['app_info']['app_name'],'task_instruction':data['task_instruction'],
             'steps':len(data['steps']),'completion_status':data['completion_status'],
             'task_type':json.dumps(data['task_type'],ensure_ascii=False),
             'screen_resolution':json.dumps(data['device_info']['screen_resolution']),
             'actions':json.dumps([s['action']['action_type'] for s in data['steps']],ensure_ascii=False),
             'bytes':sum(p.stat().st_size for p in sample.rglob('*') if p.is_file())}
        errors=list(StrictValidator(schema).iter_errors(row))
        if errors: raise ValueError('metadata 字段无效：'+errors[0].message)
        rows.append(row)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    return rows
