from pathlib import Path
import os,sys,json,time,subprocess,traceback,hashlib
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
plan=json.loads((ROOT/'launch-plan.json').read_text());scope=json.loads(Path(plan['scope']).read_text())
command=[str(REPO/'.venv/bin/python'),'-B','-u','-m','site_planner.candidate_discovery','produce-entries','--config',scope['producer_config'],'--ledger',scope['producer_db'],'--pool',scope['pool'],'--history-set',scope['history_set'],'--sources',plan['sources'],'--discovery-mode','new-sites','--site-expansion','--allowed-host','www.dpm.org.cn','--allowed-host','dpm.org.cn','--target','100','--application-new-target','100','--application-pending-cap','100','--batch-key',plan['batch_key'],'--producer-pipeline','serial','--batch-size','25','--max-batches','100','--max-searches','1']
env={**os.environ,'PYTHONPATH':os.pathsep.join(str(REPO/p) for p in ('projects/code','projects/site-planner','projects/quality-inspector')),'PYTHONDONTWRITEBYTECODE':'1','WEBCOLLECT_PRODUCER_STOP_FILE':plan['stop_file']}
started=time.time(); code=None
try:
 with (ROOT/'producer.log').open('x') as log:
  process=subprocess.Popen(command,cwd=REPO,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  active={**plan,'status':'RUNNING','started_at':started,'controller_pid':os.getpid(),'worker_pid':process.pid,'command':command}
  (ROOT/'active-run.json').write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n')
  code=process.wait()
except BaseException as error:
 with (ROOT/'issues.jsonl').open('a') as stream:stream.write(json.dumps({'at':time.time(),'stage':'controller','type':type(error).__name__,'error':str(error)},ensure_ascii=False)+'\n')
 raise
finally:
 after={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ('projects/code/webcollect','projects/site-planner/site_planner','projects/quality-inspector/quality_inspector') for p in (REPO/base).rglob('*') if p.is_file() and p.suffix in ('.py','.js','.json')}
 before=json.loads((ROOT/'source-before.json').read_text())
 (ROOT/'source-after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'controller-exit.json').write_text(json.dumps({'finished_at':time.time(),'seconds':time.time()-started,'returncode':code,'source_unchanged':before==after,'worker_exited':code is not None,'target_reached':code==0},ensure_ascii=False,indent=2)+'\n')
