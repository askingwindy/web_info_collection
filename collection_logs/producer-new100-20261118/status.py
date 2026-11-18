from pathlib import Path
import json,sqlite3,time,hashlib,os
ROOT=Path(__file__).resolve().parent
plan=json.loads((ROOT/'launch-plan.json').read_text());scope=json.loads(Path(plan['scope']).read_text())
active=json.loads((ROOT/'active-run.json').read_text())
started=active['started_at']; needle='%producer-new100-20261118-dpm-%'
def connect(path):
 c=sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=90);c.row_factory=sqlite3.Row;return c
with connect(scope['producer_db']) as c:
 jobs=[dict(r) for r in c.execute('SELECT id,kind,state,error FROM jobs WHERE created>=? AND (payload LIKE ? OR payload LIKE ?)',(started,needle,'%dpm.org.cn%'))]
 ids=[j['id'] for j in jobs]
 models=[dict(r) for r in c.execute("SELECT r.id,r.state,r.usage,r.cost,r.error,r.started,r.finished,json_extract(r.response,'$.failure_diagnostic') AS diagnostic FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE j.created>=? AND (j.payload LIKE ? OR j.payload LIKE ?)",(started,needle,'%dpm.org.cn%'))]
 visits=[dict(r) for r in c.execute('SELECT v.id,v.state,v.target_uri,v.response_status,v.error_type,v.error_message FROM top_level_visits v JOIN jobs j ON j.id=v.job_id WHERE j.created>=? AND (j.payload LIKE ? OR j.payload LIKE ?)',(started,needle,'%dpm.org.cn%'))]
from collections import Counter
with connect(scope['pool']) as c:
 rows=[dict(r) for r in c.execute('SELECT result,reason,candidate_id,created FROM candidate_batch_rows WHERE run_id LIKE ?',(needle,))]
 new_ids={r['candidate_id'] for r in rows if r['result']=='NEW'}
base=json.loads((ROOT/'baseline.json').read_text())
protected=json.loads((ROOT/'protected-before.json').read_text());drift=[]
for role,tables in protected.items():
 with connect(scope[role+'_db']) as c:
  for table,records in tables.items():
   for rid,expected in records.items():
    row=c.execute('SELECT * FROM '+table+' WHERE id=?',(rid,)).fetchone()
    sha=hashlib.sha256(json.dumps(dict(row),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest() if row else None
    if sha!=expected['sha256']:drift.append({'role':role,'table':table,'id':rid,'old_state':expected['state'],'new_state':row['state'] if row else None})
tokens=Counter()
for m in models:
 if m['usage']:
  u=json.loads(m['usage'])
  for key in ('input_tokens','output_tokens','prompt_tokens','completion_tokens','total_tokens'):
   if isinstance(u.get(key),(int,float)):tokens[key]+=u[key]
failures=[v for v in visits if v['state'] in ('failed','unknown')]
summary={'at':time.time(),'elapsed_seconds':round(time.time()-started,1),'target':100,'net_new_unique':len(new_ids-set(base['candidate_ids'])),'candidate_rows':dict(Counter(r['result'] for r in rows)),'job_states':dict(Counter(j['state'] for j in jobs)),'model_states':dict(Counter(r['state'] for r in models)),'tokens':dict(tokens),'GET_states':dict(Counter(v['state'] for v in visits)),'protected_drift':drift,'worker_pid':active['worker_pid'],'finished':(ROOT/'controller-exit.json').exists() and (not (ROOT/'expansion-active.json').exists() or (ROOT/'expansion-exit.json').exists()),'page_failures':failures}
(ROOT/'status-latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
with (ROOT/'progress.jsonl').open('a') as log:log.write(json.dumps({k:v for k,v in summary.items() if k!='page_failures'},ensure_ascii=False)+'\n')
known=set()
for line in (ROOT/'issues.jsonl').read_text().splitlines():
 value=json.loads(line)
 if value.get('visit_id'):known.add(value['visit_id'])
with (ROOT/'issues.jsonl').open('a') as log:
 for v in failures:
  if v['id'] not in known:log.write(json.dumps({'at':time.time(),'stage':'producer_fetch','code':v['error_type'],'visit_id':v['id'],'uri':v['target_uri'],'state':v['state'],'error':v['error_message'],'action':'原失败/UNKNOWN保留；没有由本观察器重试。'},ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='page_failures'},ensure_ascii=False))

known_text=(ROOT/'issues.jsonl').read_text()
with (ROOT/'issues.jsonl').open('a') as log:
 for m in models:
  if m['state'] in ('failed','invalid_response','unknown') and m['id'] not in known_text:
   log.write(json.dumps({'at':time.time(),'stage':'producer_model','code':m['error'],'request_id':m['id'],'state':m['state'],'diagnostic':json.loads(m['diagnostic']) if m['diagnostic'] else None,'action':'原请求与费用保留，观察器不重试。'},ensure_ascii=False)+'\n')
