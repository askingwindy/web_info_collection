"""Build delivery declarations from actual finished capture ledgers and explicit facts.

Run after capture: python -m webcollect.production_facts --source BATCH_ROOT
--output facts.json. Account/privacy and narrative declarations come from each
saved plan's production_facts object or an explicitly supplied declarations file;
missing facts never become invented compliance assertions.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from collections import Counter
from datetime import datetime
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3

from .client_package import _discover, real_file, sha
from .validate import read_json


def _declaration(value):
    fields=('accounts_and_privacy','narrative_generation','narrative_mode')
    if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not value[k].strip() for k in fields):
        raise ValueError('Capture declarations require accounts_and_privacy, narrative_generation and narrative_mode')
    if value['narrative_mode'] not in ('template','model','mixed'):
        raise ValueError('narrative_mode must identify template, model or mixed generation')
    if value.get('prompt_stages') is not None:
        from .task_contract import validate_prompt_stages
        validate_prompt_stages(value)
    elif value['narrative_mode'] in ('model','mixed') and not (isinstance(value.get('prompt'),str) and value['prompt'].strip()):
        raise ValueError('Model-generated narrative requires its actual prompt')
    return value


def _closed_replan(root, manifest, plan):
    """Verify a failed scope's immutable closure, never infer missing attempts."""
    from .task_contract import canonical_sha
    path=real_file(root/'replanning'/'closure.json',root)
    closure=read_json(path)
    def require(condition, detail):
        if not condition:raise ValueError('Closed replan receipt '+detail)
    require(isinstance(closure,dict) and closure.get('schema_version')=='webcollect-runtime-scope-closure-1','schema is invalid')
    require(manifest.get('collection_status')=='paused_pending_resume' and not manifest.get('samples'),
            'requires the original paused failed-only manifest')
    require(closure.get('prior_scope_status')=='paused' and closure.get('final_scope_status')=='closed_replanned',
            'does not close a paused scope for replanning')
    for key in ('closure_id','scope_id','campaign_id','batch_id','closed_at','reason'):
        require(isinstance(closure.get(key),str) and bool(closure[key].strip()),'missing '+key)
    require(closure['scope_id']==manifest.get('runtime_scope_id') and closure['batch_id']==manifest.get('batch_id'),
            'scope or batch identity differs')
    try:closed_at=datetime.fromisoformat(closure['closed_at'].replace('Z','+00:00'))
    except (ValueError,TypeError):raise ValueError('Closed replan receipt closed_at is invalid')
    require(closed_at.tzinfo is not None,'closed_at requires timezone')
    files=closure.get('source_files');require(isinstance(files,list) and bool(files),'source files are missing')
    expected={str(p.resolve()) for p in root.rglob('*') if p.is_file() and p.relative_to(root).parts[0]!='replanning'}
    seen=set();roles={}
    for entry in files:
        require(isinstance(entry,dict) and isinstance(entry.get('path'),str),'source file entry is invalid')
        require(Path(entry['path']).is_absolute(),'source file path must be absolute')
        source=real_file(Path(entry['path']),root).resolve();name=str(source)
        require(name not in seen and name in expected,'source file is duplicate or outside original evidence')
        require(type(entry.get('size_bytes')) is int and entry['size_bytes']==source.stat().st_size and
                entry.get('sha256')==sha(source),'source file SHA or size differs')
        seen.add(name)
        if entry.get('role') in ('manifest','plan','runtime_snapshot'):
            require(entry['role'] not in roles,'source role is duplicated');roles[entry['role']]=source
    require(seen==expected,'source file inventory omits original evidence')
    for role,name in (('manifest','manifest.json'),('plan','plan.json'),('runtime_snapshot','runtime-snapshot.json')):
        require(roles.get(role)==root/name,'source binding is missing or wrong for '+role)
    runtime=read_json(roles['runtime_snapshot']);scope=runtime.get('scope',{})
    require(scope.get('scope_id')==closure['scope_id'] and scope.get('campaign_id')==closure['campaign_id'] and
            scope.get('state')=='paused','original runtime scope is not the same paused scope')
    require(closure.get('registry_policy')==runtime.get('policy'),'registry policy differs from original snapshot')
    require(closure.get('planned_tasks')==plan.get('tasks'),'planned task denominator differs')
    require(closure.get('attempts')==manifest.get('attempts'),'actual attempt ledger differs from original manifest')
    def indexed(rows,key,label):
        require(isinstance(rows,list),label+' must be a list');result={}
        for row in rows:
            require(isinstance(row,dict) and isinstance(row.get(key),str) and bool(row[key]) and row[key] not in result,
                    label+' contains missing or duplicate identities')
            result[row[key]]=row
        return result
    tasks=indexed(plan.get('tasks'),'task_id','planned tasks')
    registry=closure.get('registry_attempt_ledger')
    require(closure.get('registry_attempt_ledger_sha256')==canonical_sha(registry),'registry attempt digest differs')
    registry_rows=indexed(registry,'attempt_id','registry attempts')
    require(registry_rows==indexed(runtime.get('attempts'),'attempt_id','snapshot attempts'),
            'registry attempts differ from original runtime snapshot')
    before=indexed(closure.get('registry_tasks_before'),'task_key','registry tasks')
    require(before==indexed(runtime.get('tasks'),'task_key','snapshot tasks'),'registry tasks differ from original runtime snapshot')
    before_by_id=indexed(list(before.values()),'task_id','registry task IDs')
    require(set(before_by_id)==set(tasks),'registry task denominator differs')
    for tid,row in before_by_id.items():
        require(row.get('task_version')==tasks[tid].get('task_version') and row.get('task')==tasks[tid],
                'registry task content or version differs')
    actual=indexed(manifest['attempts'],'attempt_id','actual attempts');attempted=set()
    for aid,row in actual.items():
        db=registry_rows.get(aid,{})
        require(row.get('task_id') in tasks and row.get('status')=='rejected' and
                isinstance(row.get('error'),str) and bool(row['error'].strip()),'contains a non-rejected or unplanned attempt')
        require(all(db.get(k)==row.get(k) for k in ('sample_id','task_id','task_version','status')),
                'attempt identity differs from registry')
        try:started=datetime.fromisoformat(row['started_at'].replace('Z','+00:00'))
        except (KeyError,TypeError,AttributeError,ValueError):raise ValueError('Closed replan receipt actual attempt lacks started time')
        require(started.tzinfo is not None and type(db.get('started_at')) in (int,float) and
                abs(started.timestamp()-db['started_at'])<0.00001,'attempt started fact differs from registry')
        attempted.add(row['task_id'])
    require(set(actual)=={aid for aid,row in registry_rows.items() if row.get('started_at') is not None},
            'actual attempt denominator differs from registry')
    reserved=manifest.get('reserved_attempts',[])
    reserved_rows=indexed(reserved,'attempt_id','reserved attempts')
    require(set(reserved_rows)=={aid for aid,row in registry_rows.items() if row.get('started_at') is None},
            'unstarted reserved denominator differs')
    for aid,row in reserved_rows.items():
        require(row.get('started_at') is None and all(row.get(k)==registry_rows[aid].get(k)
                for k in ('sample_id','task_id','task_version','status')),'reserved allocation identity differs from registry')
    require(not any(row.get('status') in ('reserved','running') for row in registry_rows.values()),'still has inflight attempts')
    unstarted=indexed(closure.get('unstarted_tasks'),'task_id','unstarted tasks')
    require(set(unstarted)==set(tasks)-attempted,'unstarted task denominator differs or overlaps attempts')
    for tid,row in unstarted.items():
        require(set(row)=={'task_id','task_version','plan_entry'} and row['task_version']==tasks[tid].get('task_version') and
                row['plan_entry']==tasks[tid] and before_by_id[tid].get('status')=='queued',
                'unstarted task contains invented allocation or mismatched plan content')
    counts={'planned_tasks':len(tasks),'actual_attempts':len(actual),'rejected_attempts':len(actual),
            'saved_attempts':0,'inflight_attempts':0,'reserved_unstarted':len(reserved_rows),'unstarted_tasks':len(unstarted)}
    require(closure.get('counts')==counts and all(type(v) is int for v in closure['counts'].values()),'counts differ from complete evidence')
    # A prepared sidecar is not proof that its transaction committed. Read only
    # the durable scope/event identities; later campaign writes may change DB SHA.
    require(isinstance(manifest.get('registry_path'),str) and bool(manifest['registry_path']),
            'requires the original accessible registry for commit verification')
    registry_path=Path(manifest['registry_path'])
    require(registry_path.is_absolute(),'registry path must be absolute')
    registry_path=real_file(registry_path,registry_path.parent).resolve()
    try:
        con=workspace_connect(registry_path.as_uri()+'?mode=ro',uri=True)
        try:
            db_scope=con.execute('SELECT campaign_id,state FROM m4_scopes WHERE scope_id=?',(closure['scope_id'],)).fetchone()
            events=con.execute("SELECT event_id,payload_json FROM m4_events WHERE scope_id=? AND event_type='scope_closed_replanned'",
                               (closure['scope_id'],)).fetchall()
        finally:con.close()
    except sqlite3.Error as exc:raise ValueError('Closed replan receipt registry commit cannot be verified') from exc
    require(db_scope==(closure['campaign_id'],'closed_replanned') and len(events)==1,'has no unique committed registry closure')
    try:binding=json.loads(events[0][1])
    except (ValueError,TypeError):raise ValueError('Closed replan receipt registry event is invalid')
    require(isinstance(binding,dict) and binding.get('closure_id')==closure['closure_id'] and
            binding.get('path')==str(path) and binding.get('sha256')==sha(path),'differs from committed registry event')
    return {'path':str(path),'sha256':sha(path),'closure_id':closure['closure_id'],'scope_id':closure['scope_id'],
            'campaign_id':closure['campaign_id'],'counts':counts,'unstarted_tasks':list(unstarted.values()),
            'registry_commit_verification':{'registry_path':str(registry_path),'event_id':events[0][0],
                'mode':'read_only_scope_and_event_binding; active database file SHA is not frozen'}}


def derive(source, declarations=None):
    source=Path(source).resolve()
    records=_discover(source)
    if not records:raise ValueError('No collected samples to describe')
    roots=[source] if (source/'samples').is_dir() else sorted(p for p in source.iterdir() if p.is_dir() and (p/'manifest.json').is_file())
    explicit=_declaration(read_json(Path(declarations))) if declarations else None
    selected={r['sample_id'] for r in records}
    attempts={};batches=[];account_statements=[];narrative_statements=[];prompts=[];configurations=[];prompt_stages=[]
    m4_attempt_ids=set();reserved_allocations=[];reserved_sample_ids=set();closed_scopes=[];unstarted_tasks=[]
    for root in roots:
        manifest_path=real_file(root/'manifest.json',root);manifest=read_json(manifest_path)
        if manifest.get('sample_kind')!='real':
            raise ValueError('Production facts require finished real capture manifests, including rejected attempts')
        configuration=manifest.get('configuration')
        required=('viewport','device_scale_factor','task_interval_seconds','default_settle_ms')
        if not isinstance(configuration,dict) or any(k not in configuration for k in required):
            raise ValueError('Capture configuration is incomplete; do not infer frequency or viewport')
        if (not isinstance(configuration['viewport'],list) or len(configuration['viewport'])!=2 or
            any(type(v) is not int or v<=0 for v in configuration['viewport']) or
            type(configuration['device_scale_factor']) not in (int,float) or configuration['device_scale_factor']<=0 or
            any(type(configuration[k]) not in (int,float) or configuration[k]<0 for k in ('task_interval_seconds','default_settle_ms'))):
            raise ValueError('Invalid actual capture configuration')
        ledger=manifest.get('attempts')
        if not isinstance(ledger,list) or not ledger:raise ValueError('Capture attempt ledger is missing')
        batch_id=manifest.get('batch_id')
        if not isinstance(batch_id,str) or not batch_id.strip():raise ValueError('Capture batch_id is missing')
        plan_path=real_file(root/'plan.json',root);plan=read_json(plan_path)
        from .task_contract import PLAN_SCHEMA
        m4=plan.get('schema_version')==PLAN_SCHEMA
        closed=None
        if manifest.get('collection_status')!='finished_pending_review':
            if not m4 or manifest.get('collection_status')!='paused_pending_resume':
                raise ValueError('Production facts require finished real capture manifests, including rejected attempts')
            closed=_closed_replan(root,manifest,plan);closed_scopes.append({**closed,'source_batch':batch_id})
            unstarted_tasks.extend({**row,'source_batch':batch_id,'source_scope_id':closed['scope_id']}
                                   for row in closed['unstarted_tasks'])
        if m4 and not closed and manifest.get('producer_index_status')!='PASS':
            raise ValueError('M4 production facts require producer_index_status PASS after completed boundary verification')
        declaration=explicit or _declaration(plan.get('production_facts'))
        account_statements.append('批次「'+batch_id+'」：'+declaration['accounts_and_privacy'])
        narrative_statements.append('批次「'+batch_id+'」：'+declaration['narrative_generation'])
        if declaration.get('prompt_stages') is not None:
            from .task_contract import canonical_sha
            prompt_stages.append({'batch_id':batch_id,'stages':declaration['prompt_stages'],
                                  'declaration_sha256':canonical_sha(declaration)})
        elif declaration['narrative_mode']=='template':
            narrative_statements.append('该批计划声明叙述未使用模型，采用所说明的模板。')
        else:prompts.append('批次「'+batch_id+'」实际标注提示词：\n'+declaration['prompt'])
        accepted=set(manifest.get('samples',[]));ledger_accepted=set()
        tasks=plan.get('tasks')
        if not isinstance(tasks,list) or not tasks or any(not isinstance(task,dict) or not isinstance(task.get('task_id'),str) or not task['task_id'].strip() for task in tasks):
            raise ValueError('Saved plan requires all planned task IDs')
        planned_ids=[task['task_id'] for task in tasks];task_ids=set(planned_ids)
        if len(task_ids)!=len(planned_ids):raise ValueError('Saved plan has duplicate task IDs')
        attempted_task_ids=set()
        task_versions={task['task_id']:task.get('task_version') for task in tasks}
        if m4:
            from .task_contract import validate_m4_plan
            # Invalid original planning metadata can itself be the recorded cause
            # of a closed failed scope; it must not erase that historical population.
            if not closed:validate_m4_plan(plan)
            reserved=manifest.get('reserved_attempts',[])
            if not isinstance(reserved,list):raise ValueError('M4 reserved_attempts must be a list')
            for row in reserved:
                if (not isinstance(row,dict) or row.get('started_at') or not row.get('attempt_id') or not row.get('sample_id')
                        or row.get('task_id') not in task_ids or row.get('task_version')!=task_versions.get(row.get('task_id'))):
                    raise ValueError('M4 reserved allocation must be unstarted and bound to its actual task version')
                if row['attempt_id'] in m4_attempt_ids or row['sample_id'] in reserved_sample_ids or row['sample_id'] in attempts:
                    raise ValueError('M4 reserved allocation identity was reused')
                m4_attempt_ids.add(row['attempt_id']);reserved_sample_ids.add(row['sample_id'])
                reserved_allocations.append({**row,'source_batch':batch_id})
        for row in ledger:
            if not isinstance(row,dict) or not isinstance(row.get('sample_id'),str) or not row['sample_id']:
                raise ValueError('Capture attempt has no stable sample ID')
            sid=row['sample_id']
            if sid in attempts or sid in reserved_sample_ids:raise ValueError('Duplicate capture attempt sample ID: '+sid)
            if row.get('task_id') not in task_ids:raise ValueError('Capture attempt is not in its saved plan')
            if m4:
                if (not isinstance(row.get('attempt_id'),str) or not row['attempt_id'] or
                        not isinstance(row.get('started_at'),str) or not row['started_at'] or
                        row.get('task_version')!=task_versions[row['task_id']]):
                    raise ValueError('M4 actual attempts require attempt_id, started_at and matching task_version')
                if row['attempt_id'] in m4_attempt_ids:raise ValueError('Duplicate M4 attempt_id')
                m4_attempt_ids.add(row['attempt_id'])
            elif row['task_id'] in attempted_task_ids:raise ValueError('Capture task is duplicated in the attempt ledger')
            attempted_task_ids.add(row['task_id'])
            if row.get('status') not in ('collected_pending_review','rejected'):
                raise ValueError('Capture attempt has an unfinished or unsupported status')
            if row['status']=='collected_pending_review':ledger_accepted.add(sid)
            elif not isinstance(row.get('error'),str) or not row['error'].strip():
                raise ValueError('Rejected attempts require their actual recorded reason')
            attempts[sid]={**row,'source_batch':batch_id}
        if not closed and attempted_task_ids!=task_ids:raise ValueError('Finished capture ledger omitted planned tasks')
        if accepted!=ledger_accepted:raise ValueError('Capture ledger and saved sample population disagree')
        actual={r['sample_id'] for r in records if r['batch']==root}
        if accepted!=actual:raise ValueError('Source samples were dropped without a recorded selection decision')
        for record in records:
            if record['batch']==root and record['data']['device_info']['screen_resolution']!=configuration['viewport']:
                raise ValueError('Manifest viewport differs from actual delivered PNG dimensions')
        configurations.append({'batch_id':batch_id,'configuration':configuration})
        batches.append({'batch_id':batch_id,'manifest_sha256':sha(manifest_path),'plan_snapshot_sha256':sha(plan_path),
                        'declarations_source':'explicit file' if explicit else 'saved plan.production_facts',
                        'attempt_count':len(ledger),'saved_count':len(accepted),
                        **({'replanning_closure':closed,'original_collection_status':manifest['collection_status']} if closed else {})})
    if not selected<=attempts.keys():raise ValueError('Collected sample has no actual capture attempt')
    excluded=[{'sample_id':sid,'reason':row['error'],'source_batch':row['source_batch']}
              for sid,row in sorted(attempts.items()) if sid not in selected]
    action_counts=Counter(step['action']['action_type'] for r in records for step in r['data']['steps'])
    facts={'schema_version':'webcollect-production-facts-1',
        'collection_method':'按本批实际浏览器自动化采集清单'+('及已核验的重规划闭合收据' if closed_scopes else '')+'汇总'+str(len(batches))+'个批次、'+str(len(records))+
            '条已保存轨迹；每条保留动作前真实视口PNG、同步页面元素树、统一动作与目标真值。交付导出复制原始图树，不重新访问站点或补拍。实际动作统计：'+json.dumps(dict(action_counts),ensure_ascii=False)+'。',
        'frequency_policy':'以下为来源采集清单中实际记录的任务间隔、默认稳定等待、浏览器与视口配置。配置间隔不是完整网络请求速率日志；不得据此声称第三方资源请求速率已被完整测量。\n\n```json\n'+json.dumps(configurations,ensure_ascii=False,indent=2)+'\n```',
        'accounts_and_privacy':'以下为来源计划或显式事实文件记录的账号与隐私声明，不由导出器推断授权或账号性质；是否符合声明仍须核对实际轨迹与页面。\n\n'+'\n\n'.join(account_statements),
        'change_detection':'本生产线以观察页面状态、视口截图、再次观察的同步证据保存图树；相邻PNG的SHA-256变化记为screen_changed。文字、控件值与状态、滚动位置差异用于结果描述；哈希变化不替代动作解释、连续性和最终任务完成的独立逐图核对。',
        'narrative_generation':'以下为来源计划或显式事实文件记录的实际文字生成方式声明；叙述是否仅引用可见证据仍由独立质检核对。\n\n'+'\n\n'.join(narrative_statements),
        'selection':{'total_samples':len(attempts),'selected_count':len(selected),'excluded_count':len(excluded),
                     'excluded_samples':excluded,'scope':'本次所供完整采集批次的真实尝试总体；不把保存成功数当作最初尝试总数，也不推断其他历史批次'},
        'capture_fact_sources':batches,'category_share_policy':'enforced; no previous batch exception inherited'}
    if prompts:facts['prompt']='\n\n'.join(prompts)
    if prompt_stages:facts['prompt_stages']=prompt_stages
    if closed_scopes:
        facts['closed_replanned_scopes']=closed_scopes
        facts['planned_task_statistics']={'unstarted_closed_task_count':len(unstarted_tasks),
            'unstarted_closed_tasks':unstarted_tasks,
            'scope':'Original unstarted tasks remain in their closed planning denominator; they are not execution attempts or saved samples.'}
    if m4_attempt_ids:
        facts['allocation_statistics']={'reserved_unstarted_count':len(reserved_allocations),
            'reserved_unstarted_allocations':reserved_allocations,
            'scope':'Unstarted reserved IDs remain allocated but are excluded from the actual execution denominator.'}
    specs={(tuple(row['configuration']['viewport']),row['configuration']['device_scale_factor']) for row in configurations}
    if len(specs)==1:
        viewport,dpr=next(iter(specs));facts['screenshot_configuration']={'viewport':list(viewport),'device_scale_factor':dpr}
    if declarations:facts['declarations_sha256']=sha(Path(declarations))
    return facts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--declarations',type=Path,help='Explicit actual account/privacy and narrative declaration JSON; otherwise use the saved plan.production_facts')
    args=parser.parse_args()
    facts=derive(args.source,args.declarations)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(facts,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'output':str(args.output.resolve()),'selection':facts['selection']},ensure_ascii=False))


if __name__=='__main__':main()
