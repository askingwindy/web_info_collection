"""Actual capture accounting and declared facts for generic customer exports."""
import copy
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

from test_client_package import fixture, write, REPO
from webcollect.client_package import build_client_package
from webcollect.production_facts import derive

DECLARATIONS={'accounts_and_privacy':'本受控测试仅操作本地合成页面，不使用账号或真实个人信息，不是正式采集数据。',
              'narrative_mode':'mixed','narrative_generation':'受控测试的计划文字按此实际指令编写，步骤结果使用采集器模板。',
              'prompt':'为本地合成页面编写测试目标，只引用界面可见内容。'}


def capture_batch(root,sid='Web_fixture_001',batch_id='B20261024_001'):
    sample=fixture(root,sid)
    manifest=json.loads((root/'manifest.json').read_text())
    manifest.update(batch_id=batch_id,collection_status='finished_pending_review',
        configuration={'viewport':[64,48],'device_scale_factor':1,'task_interval_seconds':2,'default_settle_ms':750})
    manifest['attempts'][0].update(task_id='task-'+sid,status='collected_pending_review')
    write(root/'manifest.json',manifest)
    write(root/'plan.json',{'tasks':[{'task_id':'task-'+sid}],'production_facts':copy.deepcopy(DECLARATIONS)})
    return sample


class ProductionFacts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.batch=self.root/'source';self.sample=capture_batch(self.batch)

    def test_actual_configuration_and_rejected_attempts_are_not_replaced_by_saved_count(self):
        manifest=json.loads((self.batch/'manifest.json').read_text())
        manifest['attempts'].append({'sample_id':'rejected-2','task_id':'failed-task','status':'rejected','error':'目标被遮挡'})
        plan=json.loads((self.batch/'plan.json').read_text());plan['tasks'].append({'task_id':'failed-task'})
        write(self.batch/'manifest.json',manifest);write(self.batch/'plan.json',plan)
        facts=derive(self.batch)
        self.assertEqual(facts['selection']['total_samples'],2)
        self.assertEqual(facts['selection']['selected_count'],1)
        self.assertEqual(facts['selection']['excluded_count'],1)
        self.assertEqual(facts['selection']['excluded_samples'][0]['reason'],'目标被遮挡')
        self.assertIn('"task_interval_seconds": 2',facts['frequency_policy'])
        self.assertIn('"default_settle_ms": 750',facts['frequency_policy'])
        self.assertEqual(facts['screenshot_configuration'],{'viewport':[64,48],'device_scale_factor':1})
        self.assertNotIn('category_share_authorization',facts)
        self.assertEqual(facts['prompt'],'批次「B20261024_001」实际标注提示词：\n'+DECLARATIONS['prompt'])

    def m4_source(self):
        from test_m4_task_contract import m4_task, declarations
        from webcollect.task_contract import PLAN_SCHEMA
        task=m4_task();task['task_id']='task-Web_fixture_001'
        write(self.batch/'plan.json',{'schema_version':PLAN_SCHEMA,'tasks':[task],
                                     'production_facts':declarations()})
        manifest=json.loads((self.batch/'manifest.json').read_text())
        manifest['producer_index_status']='PASS'
        manifest['attempts'][0].update(attempt_id='a-success',task_version='1',started_at='2026-10-25T10:00:00+08:00')
        return manifest

    def test_m4_finished_sample_cannot_bypass_unfinished_index_boundary(self):
        original=self.m4_source()
        for status in (None,'PENDING','FAIL'):
            manifest=copy.deepcopy(original)
            if status is None:manifest.pop('producer_index_status')
            else:manifest['producer_index_status']=status
            write(self.batch/'manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'producer_index_status PASS'):derive(self.batch)

    def test_m4_retry_denominator_excludes_unstarted_reserved_ids_without_erasing_them(self):
        manifest=self.m4_source();task_id=manifest['attempts'][0]['task_id']
        manifest['attempts'].insert(0,{'sample_id':'failed-previous','attempt_id':'a-failure',
            'task_id':task_id,'task_version':'1','started_at':'2026-10-25T09:00:00+08:00',
            'status':'rejected','error':'实际导航超时'})
        manifest['attempts'][1]['retry_of']='a-failure'
        manifest['reserved_attempts']=[{'sample_id':'reserved-gap','attempt_id':'a-reserved',
            'task_id':task_id,'task_version':'1','started_at':None,'status':'abandoned'}]
        write(self.batch/'manifest.json',manifest)
        facts=derive(self.batch)
        self.assertEqual(facts['selection']['total_samples'],2)
        self.assertEqual(facts['selection']['excluded_count'],1)
        self.assertEqual(facts['allocation_statistics']['reserved_unstarted_count'],1)
        self.assertEqual(facts['allocation_statistics']['reserved_unstarted_allocations'][0]['sample_id'],'reserved-gap')
        self.assertEqual(facts['prompt_stages'][0]['stages']['planning']['mode'],'model')
        self.assertEqual(facts['prompt_stages'][0]['stages']['narrative']['mode'],'template')

    def test_m4_attempt_identity_and_started_fact_are_required(self):
        original=self.m4_source()
        for mutate in (lambda m:m['attempts'][0].update(started_at=None),
                       lambda m:m['attempts'][0].update(task_version='invented-version'),
                       lambda m:m['attempts'][0].pop('attempt_id')):
            manifest=copy.deepcopy(original);mutate(manifest);write(self.batch/'manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'actual attempts'):derive(self.batch)

    def test_m4_revision_prompt_never_hides_planning_and_generation_facts(self):
        manifest=self.m4_source();write(self.batch/'manifest.json',manifest)
        facts=derive(self.batch);path=self.root/'facts-m4.json';write(path,facts)
        output=self.root/'client-m4';build_client_package(REPO,self.batch,output,facts=path)
        from webcollect.contract_documents import render
        records=[{'data':json.loads((self.sample/'annotation.json').read_text())}]
        render(output,records,facts,{'prompt':'只修正已核对字段，不重建原始提示词。','author':'受控测试'})
        synthesis=(output/'合成方式说明.md').read_text()
        self.assertIn('测试实际开始与暂停，不能仅设置后宣布完成。',synthesis)
        self.assertIn('m4-visible-evidence-1',synthesis)
        self.assertIn('只修正已核对字段，不重建原始提示词。',synthesis)

    def test_empty_rejected_batch_is_retained_in_combined_population(self):
        parent=self.root/'combined';parent.mkdir()
        self.batch.rename(parent/'first')
        second=parent/'second';sample=capture_batch(second,'Web_fixture_002','B20261024_002')
        shutil.rmtree(sample)
        manifest=json.loads((second/'manifest.json').read_text());manifest['samples']=[]
        manifest['attempts'][0].update(status='rejected',error='中文比例不足')
        write(second/'manifest.json',manifest)
        facts=derive(parent)
        self.assertEqual(facts['selection']['total_samples'],2)
        self.assertEqual(facts['selection']['excluded_count'],1)
        self.assertEqual(len(facts['capture_fact_sources']),2)

    def test_missing_declaration_or_model_prompt_is_a_blocker(self):
        plan=json.loads((self.batch/'plan.json').read_text());plan.pop('production_facts')
        write(self.batch/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'declarations'):derive(self.batch)
        plan['production_facts']=copy.deepcopy(DECLARATIONS);plan['production_facts'].pop('prompt')
        write(self.batch/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'actual prompt'):derive(self.batch)

    def test_finished_ledger_must_cover_every_planned_task_exactly_once(self):
        original_manifest=json.loads((self.batch/'manifest.json').read_text())
        original_plan=json.loads((self.batch/'plan.json').read_text())
        plan=copy.deepcopy(original_plan);plan['tasks'].append({'task_id':'omitted-task'})
        write(self.batch/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'omitted planned tasks'):derive(self.batch)
        plan=copy.deepcopy(original_plan);plan['tasks'].append(copy.deepcopy(plan['tasks'][0]))
        write(self.batch/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'duplicate task IDs'):derive(self.batch)
        write(self.batch/'plan.json',original_plan)
        manifest=copy.deepcopy(original_manifest)
        manifest['attempts'].append({**manifest['attempts'][0],'sample_id':'same-task-again','status':'rejected','error':'重复任务'})
        write(self.batch/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'duplicated in the attempt ledger'):derive(self.batch)

    def test_unfinished_ledger_or_unknown_configuration_is_a_blocker(self):
        original=json.loads((self.batch/'manifest.json').read_text())
        for mutate in [lambda m:m.update(collection_status='in_progress'),
                       lambda m:m['configuration'].pop('task_interval_seconds'),
                       lambda m:m['configuration'].update(viewport=[1280,720]),
                       lambda m:m['attempts'][0].update(status='rejected',error='真实失败')]:
            manifest=copy.deepcopy(original);mutate(manifest);write(self.batch/'manifest.json',manifest)
            self.assertRaises(ValueError,derive,self.batch)

    def test_explicit_declaration_is_bound_and_the_complete_customer_documents_are_generated(self):
        plan=json.loads((self.batch/'plan.json').read_text());plan.pop('production_facts');write(self.batch/'plan.json',plan)
        declaration_path=self.root/'declarations.json';write(declaration_path,DECLARATIONS)
        facts=derive(self.batch,declaration_path);self.assertIn('declarations_sha256',facts)
        path=self.root/'facts.json';write(path,facts)
        output=self.root/'client';build_client_package(REPO,self.batch,output,facts=path)
        synthesis=(output/'合成方式说明.md').read_text();source=(output/'来源与合规说明.md').read_text()
        for heading in ('动作映射','坐标','界面变化判定','文字字段生成方式','提示词'):self.assertIn(heading,synthesis)
        for heading in ('采集方式','访问频率策略','账号与脱敏','站点清单'):self.assertIn(heading,source)
        self.assertNotIn('UNKNOWN',synthesis+source)
        self.assertNotIn('原20条',source)
        self.assertNotIn('仅统计、不考核',(output/'README.md').read_text())
        self.assertIn('64×48',synthesis)

    def test_actual_rejection_population_survives_customer_qc_and_report_rendering(self):
        manifest=json.loads((self.batch/'manifest.json').read_text())
        manifest['attempts'].append({'sample_id':'rejected-2','task_id':'failed-task','status':'rejected','error':'实际加载失败'})
        plan=json.loads((self.batch/'plan.json').read_text());plan['tasks'].append({'task_id':'failed-task'})
        write(self.batch/'manifest.json',manifest);write(self.batch/'plan.json',plan)
        facts=derive(self.batch);facts_path=self.root/'facts.json';write(facts_path,facts)
        output=self.root/'client';build_client_package(REPO,self.batch,output,facts=facts_path)
        sys.path.insert(0,str(REPO/'projects/quality-inspector'))
        from quality_inspector.engine import inspect
        from webcollect.client_package import sha
        from webcollect.client_reports import _render_summary, finalize_client_package
        report=inspect(None,output,inspection_stage='payload')
        self.assertEqual(report['statistics']['source_population'],facts['selection'])
        # This synthetic one-case fixture has no semantic review and is not a
        # releasable corpus. Its FAIL must coexist with honest attempt counts.
        self.assertEqual(report['delivery_status'],'FAIL')
        report_path=self.root/'qc.json';write(report_path,report)
        files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
        text=_render_summary(output,report_path,report,files)
        summary=json.loads(re.search(r'```json\s*\n(.*?)\n```',text,re.S).group(1))
        self.assertEqual(summary['original_source_population']['population'],{'total_samples':2,'selected_count':1,'excluded_count':1})
        self.assertEqual(summary['original_source_population']['excluded_samples'],facts['selection']['excluded_samples'])
        self.assertEqual(summary['rejection_statistics_scope'],facts['selection']['scope'])
        for old_scope in ('原20条','固定输出18条','原18条'):self.assertNotIn(old_scope,text)
        with self.assertRaisesRegex(ValueError,'PASS delivery check'):
            finalize_client_package(REPO,output,report_path,self.root/'must-not-release')

    def closed_replan_combination(self):
        """Synthetic 5 failed + 15 unstarted, then 20 successes; never real evidence."""
        from test_m4_task_contract import m4_task, declarations
        from webcollect.task_contract import PLAN_SCHEMA, canonical_sha
        from webcollect.client_package import sha
        parent=self.root/'closed-combined';parent.mkdir();new=parent/'new';self.batch.rename(new)
        for i in range(2,21):fixture(new,f'Web_fixture_{i:03}')
        manifest=json.loads((new/'manifest.json').read_text());manifest['producer_index_status']='PASS'
        tasks=[]
        for i,row in enumerate(manifest['attempts']):
            task=m4_task();task.update(task_id='task-'+row['sample_id'],task_version='2');tasks.append(task)
            row.update(attempt_id=f'new-{i}',task_id=task['task_id'],task_version='2',
                       started_at='2026-10-25T10:00:00+08:00',status='collected_pending_review')
        write(new/'manifest.json',manifest);write(new/'plan.json',{'schema_version':PLAN_SCHEMA,'tasks':tasks,'production_facts':declarations()})
        old=parent/'old';(old/'samples').mkdir(parents=True);old_tasks=copy.deepcopy(tasks)
        for t in old_tasks:t.update(task_version='1',task_type=['信息检索','数据查看'])
        plan={'schema_version':PLAN_SCHEMA,'tasks':old_tasks,'production_facts':declarations()}
        failed=[];registry=[];registry_tasks=[];started='2026-10-25T09:00:00+08:00'
        for i,t in enumerate(old_tasks):
            registry_tasks.append({'task_key':f'key-{i}','task_id':t['task_id'],'task_version':'1',
                'task':t,'status':'needs_replan' if i<5 else 'queued'})
            if i<5:
                row={'attempt_id':f'old-{i}','sample_id':f'old-failed-{i}','task_id':t['task_id'],
                     'task_version':'1','started_at':started,'status':'rejected','error':'Synthetic metadata rejection'}
                failed.append(row);registry.append({**row,'started_at':datetime.fromisoformat(started).timestamp()})
                write(old/'evidence'/f'failure-{i}.json',{'synthetic_fixture':True,'attempt_id':row['attempt_id'],'error':row['error']})
        registry_path=(parent/'registry.sqlite3').resolve()
        paused={**manifest,'runtime_scope_id':'old-scope','registry_path':str(registry_path),'batch_id':'B20261024_002','samples':[],
                'attempts':failed,'collection_status':'paused_pending_resume','producer_index_status':'PENDING'}
        runtime={'scope':{'scope_id':'old-scope','campaign_id':'synthetic-campaign','state':'paused'},
                 'policy':{'synthetic_fixture':True},'tasks':registry_tasks,'attempts':registry}
        write(old/'manifest.json',paused);write(old/'plan.json',plan);write(old/'runtime-snapshot.json',runtime)
        closure={'schema_version':'webcollect-runtime-scope-closure-1','closure_id':'synthetic-closure',
            'scope_id':'old-scope','campaign_id':'synthetic-campaign','batch_id':'B20261024_002',
            'closed_at':'2026-10-25T09:30:00+08:00','reason':'Synthetic replan test only',
            'prior_scope_status':'paused','final_scope_status':'closed_replanned',
            'source_files':[{'role':{'manifest.json':'manifest','plan.json':'plan','runtime-snapshot.json':'runtime_snapshot'}.get(p.name,'evidence'),
                             'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(old.rglob('*')) if p.is_file()],
            'counts':{'planned_tasks':20,'actual_attempts':5,'rejected_attempts':5,'saved_attempts':0,
                      'inflight_attempts':0,'reserved_unstarted':0,'unstarted_tasks':15},
            'attempts':failed,'unstarted_tasks':[{'task_id':t['task_id'],'task_version':'1','plan_entry':t} for t in old_tasks[5:]],
            'planned_tasks':old_tasks,'registry_attempt_ledger':registry,'registry_attempt_ledger_sha256':canonical_sha(registry),
            'registry_tasks_before':registry_tasks,'registry_policy':runtime['policy'],'evidence_refs':[]}
        path=old/'replanning'/'closure.json';write(path,closure)
        with closing(sqlite3.connect(registry_path)) as con, con:
            con.execute('CREATE TABLE m4_scopes(scope_id TEXT PRIMARY KEY,campaign_id TEXT,state TEXT)')
            con.execute('CREATE TABLE m4_events(event_id INTEGER PRIMARY KEY,scope_id TEXT,event_type TEXT,payload_json TEXT)')
            con.execute('INSERT INTO m4_scopes VALUES(?,?,?)',('old-scope','synthetic-campaign','closed_replanned'))
            con.execute('INSERT INTO m4_events VALUES(?,?,?,?)',(1,'old-scope','scope_closed_replanned',
                        json.dumps({'closure_id':closure['closure_id'],'path':str(path.resolve()),'sha256':sha(path)})))
        return parent,old,path,closure

    def test_closed_replan_keeps_five_failures_plus_twenty_successes_not_fifteen_unstarted(self):
        parent,old,path,closure=self.closed_replan_combination()
        before={p:p.read_bytes() for p in old.rglob('*') if p.is_file()}
        facts=derive(parent)
        self.assertEqual({k:facts['selection'][k] for k in ('total_samples','selected_count','excluded_count')},
                         {'total_samples':25,'selected_count':20,'excluded_count':5})
        self.assertEqual(facts['planned_task_statistics']['unstarted_closed_task_count'],15)
        self.assertEqual(facts['closed_replanned_scopes'][0]['counts'],closure['counts'])
        self.assertEqual({r['sample_id'] for r in facts['selection']['excluded_samples']},{f'old-failed-{i}' for i in range(5)})
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_paused_failed_scope_without_explicit_closure_remains_blocked(self):
        parent,old,path,_=self.closed_replan_combination();path.unlink()
        with self.assertRaisesRegex(ValueError,'source file'):derive(parent)

    def test_closed_replan_rejects_forged_receipt_counts_omissions_and_invented_attempts(self):
        parent,old,path,original=self.closed_replan_combination()
        mutations=[
            lambda c:c['unstarted_tasks'].pop(),
            lambda c:c['planned_tasks'].pop(),
            lambda c:c['attempts'].pop(),
            lambda c:c['attempts'].append({'attempt_id':'invented','task_id':c['unstarted_tasks'][0]['task_id']}),
            lambda c:c['unstarted_tasks'][0].update(sample_id='invented-sample',started_at='invented'),
            lambda c:c['unstarted_tasks'][0].update(task_version='invented'),
            lambda c:c['counts'].update(actual_attempts=20),
            lambda c:c['counts'].update(saved_attempts=True),
            lambda c:c.update(final_scope_status='active'),
            lambda c:c.update(scope_id='other-scope'),
            lambda c:c.update(registry_attempt_ledger_sha256='0'*64),
            lambda c:c['registry_tasks_before'].pop(),
            lambda c:c['source_files'].pop(),
            lambda c:c['source_files'][0].update(sha256='0'*64),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(case=index):
                candidate=copy.deepcopy(original);mutate(candidate);write(path,candidate)
                with self.assertRaisesRegex(ValueError,'Closed replan receipt'):derive(parent)

    def test_closed_replan_detects_changed_original_manifest_plan_and_runtime(self):
        parent,old,path,closure=self.closed_replan_combination()
        for name in ('manifest.json','plan.json','runtime-snapshot.json','evidence/failure-0.json'):
            with self.subTest(file=name):
                target=old/name;original=target.read_bytes();target.write_bytes(original+b' ')
                with self.assertRaisesRegex(ValueError,'SHA or size'):derive(parent)
                target.write_bytes(original)

    def test_receipt_cannot_count_unstarted_task_as_attempt_with_rehashed_manifest(self):
        from webcollect.client_package import sha
        parent,old,path,closure=self.closed_replan_combination()
        manifest_path=old/'manifest.json';manifest=json.loads(manifest_path.read_text())
        task=closure['unstarted_tasks'].pop(0)
        fake={'attempt_id':'invented','sample_id':'invented','task_id':task['task_id'],'task_version':'1',
              'started_at':'2026-10-25T09:00:00+08:00','status':'rejected','error':'Invented failure'}
        manifest['attempts'].append(fake);write(manifest_path,manifest);closure['attempts']=manifest['attempts']
        closure['counts'].update(actual_attempts=6,rejected_attempts=6,unstarted_tasks=14)
        for entry in closure['source_files']:
            if entry['role']=='manifest':entry.update(sha256=sha(manifest_path),size_bytes=manifest_path.stat().st_size)
        write(path,closure)
        with self.assertRaisesRegex(ValueError,'attempt identity differs from registry'):derive(parent)

    def test_closed_replan_cannot_bypass_saved_sample_index_boundary(self):
        from webcollect.client_package import sha
        parent,old,path,closure=self.closed_replan_combination()
        manifest_path=old/'manifest.json';manifest=json.loads(manifest_path.read_text());manifest['samples']=['invented-saved']
        write(manifest_path,manifest)
        for entry in closure['source_files']:
            if entry['role']=='manifest':entry.update(sha256=sha(manifest_path),size_bytes=manifest_path.stat().st_size)
        write(path,closure)
        with self.assertRaisesRegex(ValueError,'failed-only manifest|Manifest sample list'):derive(parent)

    def test_closed_replan_requires_committed_event_not_only_a_valid_sidecar(self):
        parent,old,path,closure=self.closed_replan_combination();registry=parent/'registry.sqlite3'
        with closing(sqlite3.connect(registry)) as con, con:con.execute("UPDATE m4_scopes SET state='paused'")
        with self.assertRaisesRegex(ValueError,'committed registry closure'):derive(parent)
        with closing(sqlite3.connect(registry)) as con, con:
            con.execute("UPDATE m4_scopes SET state='closed_replanned'");con.execute('DELETE FROM m4_events')
        with self.assertRaisesRegex(ValueError,'committed registry closure'):derive(parent)

    def test_closed_replan_event_sha_binding_survives_later_campaign_database_writes(self):
        parent,old,path,closure=self.closed_replan_combination();registry=parent/'registry.sqlite3'
        before=registry.read_bytes()
        with closing(sqlite3.connect(registry)) as con, con:
            con.execute('INSERT INTO m4_scopes VALUES(?,?,?)',('later-scope','synthetic-campaign','active'))
        self.assertNotEqual(before,registry.read_bytes())
        self.assertEqual(derive(parent)['selection']['total_samples'],25)
        with closing(sqlite3.connect(registry)) as con, con:
            con.execute('UPDATE m4_events SET payload_json=?',(json.dumps({'closure_id':closure['closure_id'],
                        'path':str(path.resolve()),'sha256':'0'*64}),))
        with self.assertRaisesRegex(ValueError,'committed registry event'):derive(parent)

    def test_runtime_closure_api_receipt_is_accepted_without_rewriting_old_files(self):
        from test_runtime_closure import RuntimeClosureTests
        from webcollect.production_facts import _closed_replan
        case=RuntimeClosureTests();case.setUp()
        try:
            (case.output/'samples').mkdir()
            case.manifest.update(sample_kind='real',producer_index_status='PENDING',
                configuration={'viewport':[64,48],'device_scale_factor':1,'task_interval_seconds':2,'default_settle_ms':750})
            write(case.output/'manifest.json',case.manifest)
            case.close()
            result=_closed_replan(case.output,json.loads((case.output/'manifest.json').read_text()),
                                  json.loads((case.output/'plan.json').read_text()))
            self.assertEqual(result['counts']['actual_attempts'],5)
            self.assertEqual(result['counts']['unstarted_tasks'],15)
            self.assertIn('event_id',result['registry_commit_verification'])
            capture_batch(case.root/'new','Web_replan_new_001','B20261024_099')
            facts=derive(case.root)
            self.assertEqual(facts['selection']['total_samples'],6)
            self.assertEqual(facts['selection']['selected_count'],1)
            self.assertEqual(facts['selection']['excluded_count'],5)
            self.assertEqual(facts['planned_task_statistics']['unstarted_closed_task_count'],15)
        finally:case.doCleanups()


if __name__=='__main__':unittest.main()
