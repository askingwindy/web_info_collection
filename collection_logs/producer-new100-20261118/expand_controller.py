from pathlib import Path
import os,json,time,subprocess,sqlite3,hashlib
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
plan=json.loads((ROOT/'launch-plan.json').read_text());scope=json.loads(Path(plan['scope']).read_text());active=json.loads((ROOT/'active-run.json').read_text())
evidence=Path(plan['sources']).parent
uris=['https://www.dpm.org.cn/explore/buildings.html','https://www.dpm.org.cn/explores/courts.html','https://www.dpm.org.cn/Research.html']
with sqlite3.connect(Path(scope['producer_db']).as_uri()+'?mode=ro',uri=True,timeout=90) as c:
 done={};excluded=[]
 for payload,state,result in c.execute("SELECT payload,state,result FROM jobs WHERE kind='site-discovery-page' AND created>=?",(active['started_at'],)):
  value=json.loads(payload);uri=value.get('uri');excluded.append(uri)
  if uri in uris and state=='done':done[uri]=json.loads(result)
assert set(done)==set(uris)
workers=[];children=[];logs=[]
env={**os.environ,'PYTHONPATH':os.pathsep.join(str(REPO/p) for p in ('projects/code','projects/site-planner','projects/quality-inspector')),'PYTHONDONTWRITEBYTECODE':'1','WEBCOLLECT_PRODUCER_STOP_FILE':plan['stop_file']}
for number,uri in enumerate(uris,2):
 data=done[uri];assert data['http_status']==200 and data['readable'] is True
 ref=data['document'];assert hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()==ref['sha256']
 source={'uri':uri,'title':data['title'],'content':'','reference':ref,'simplified_chinese_only':True,'excluded_entry_patterns':[r'^https?://(?:www\.)?dpm\.org\.cn/?(?:\?.*)?$'],'excluded_entry_identities':sorted(set(filter(None,excluded)))}
 source_path=evidence/f'expand-sources-{number:02d}.json';source_path.write_text(json.dumps([source],ensure_ascii=False,indent=2)+'\n')
 command=[str(REPO/'.venv/bin/python'),'-B','-u','-m','site_planner.candidate_discovery','produce-entries','--config',scope['producer_config'],'--ledger',scope['producer_db'],'--pool',scope['pool'],'--history-set',scope['history_set'],'--sources',str(source_path),'--discovery-mode','expand','--site-expansion','--allowed-host','www.dpm.org.cn','--allowed-host','dpm.org.cn','--target','100','--application-new-target','100','--application-pending-cap','100','--batch-key',f'producer-new100-20261118-dpm-{number:02d}','--producer-pipeline','serial','--batch-size','10','--max-batches','100','--max-searches','1']
 workers.append({'number':number,'seed_uri':uri,'source':str(source_path),'command':command})
expansion={'at':time.time(),'reason':'首页大批导航观察已完成；从本轮已真实获取且成功的建筑/宫廷/学术原件继续同一新站挖掘。原worker与冻结队列不改，新批排除已观察入口，不重发UNKNOWN。','total_workers_including_original':4,'shared_application_target':100,'shared_pending_cap':100,'workers':workers}
(ROOT/'expansion-plan.json').write_text(json.dumps(expansion,ensure_ascii=False,indent=2)+'\n')
try:
 for w in workers:
  log=(ROOT/f'producer-{w["number"]:02d}.log').open('x');logs.append(log)
  p=subprocess.Popen(w['command'],cwd=REPO,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  children.append(p);w['pid']=p.pid
 (ROOT/'expansion-active.json').write_text(json.dumps({**expansion,'controller_pid':os.getpid(),'workers':workers},ensure_ascii=False,indent=2)+'\n')
 while any(p.poll() is None for p in children):
  with sqlite3.connect(Path(scope['pool']).as_uri()+'?mode=ro',uri=True,timeout=90) as c:
   total=c.execute("SELECT COUNT(DISTINCT candidate_id) FROM candidate_batch_rows WHERE run_id LIKE ? AND result='NEW'",('%/entry-batch/producer-new100-20261118-dpm-%',)).fetchone()[0]
  if total>=100:Path(plan['stop_file']).touch(exist_ok=True)
  time.sleep(5)
finally:
 for p in children:
  if p.poll() is None:
   Path(plan['stop_file']).touch(exist_ok=True)
   p.wait()
 for log in logs:log.close()
 (ROOT/'expansion-exit.json').write_text(json.dumps({'finished_at':time.time(),'workers':[{'pid':p.pid,'returncode':p.returncode} for p in children],'all_children_exited':all(p.poll() is not None for p in children)},indent=2)+'\n')
