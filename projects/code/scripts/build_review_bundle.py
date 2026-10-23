"""Build an offline review bundle from latest successful, unreplaced real tasks.

No human review is inferred. Images are copied byte for byte; exported decisions
are authored interactively by the reviewer, separately from machine checks.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from webcollect.evidence import audit_capture
from webcollect.validate import validate_sample


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(batches, output):
    if output.exists():
        raise FileExistsError('核验包目录已存在，拒绝覆盖')
    candidates = {}
    attempts = []
    for batch in batches:
        manifest = json.loads((batch / 'manifest.json').read_text())
        if manifest.get('sample_kind') != 'real' or manifest.get('collection_status') != 'finished_pending_review' or manifest.get('active_task'):
            raise ValueError('只允许已结束的真实批次')
        for attempt in manifest['attempts']:
            attempts.append({**attempt, 'batch_path': str(batch.resolve())})
            if attempt['status'] != 'collected_pending_review':
                continue
            sample_id = attempt['sample_id']
            evidence = batch / 'evidence' / sample_id
            review = evidence / 'agent_review.json'
            if review.exists() and json.loads(review.read_text()).get('status') == 'requires_recollection':
                continue
            sample = batch / 'samples' / sample_id
            report = validate_sample(sample, 'delivery', manifest)
            audited = audit_capture(batch, sample_id)
            if not report['structural_pass'] or not audited['capture_evidence_pass']:
                raise ValueError('候选未通过当前结构或证据检查：' + sample_id)
            annotation = json.loads((sample / 'annotation.json').read_text())
            candidates[attempt['task_id']] = {
                'sample_id': sample_id, 'task_id': attempt['task_id'],
                'batch_path': str(batch.resolve()), 'batch_id': manifest['batch_id'],
                'site': next(site for site in manifest['sites'] if site['site_id'] == attempt['site_id']),
                'program_version': manifest['program_version'], 'rule_version': manifest['rule_version'],
                'annotation': annotation, 'total_steps': report['total_steps'],
                'effective_steps': report['effective_steps'], 'structural_pass': True,
                'capture_evidence_pass': True, 'human_review': 'pending',
                'semantic_review': 'pending', 'delivery_ready': False,
            }
    if not candidates:
        raise ValueError('没有通过检查且未被替代的候选任务')
    output.mkdir(parents=True)
    rows = list(candidates.values())
    for row in rows:
        source = Path(row['batch_path']) / 'samples' / row['sample_id']
        destination = output / 'assets' / row['sample_id']
        shutil.copytree(source, destination)
        hashes = {str(path.relative_to(source)): sha(path) for path in sorted(source.rglob('*')) if path.is_file()}
        if any(sha(destination / relative) != digest for relative, digest in hashes.items()):
            raise ValueError('核验包复制校验失败')
        row['source_file_sha256'] = hashes
        row['annotation_sha256'] = hashes['annotation.json']
        row['asset_path'] = 'assets/' + row['sample_id']
    summary = {
        'created_at': datetime.now().astimezone().isoformat(),
        'candidate_samples': len(rows), 'site_count': len({row['site']['uri'] for row in rows}),
        'site_distribution': dict(Counter(row['site']['uri'] for row in rows)),
        'category_distribution': dict(Counter(row['site']['site_category'] for row in rows)),
        'attempts_in_input_batches': len(attempts),
        'rejected_attempts': sum(a['status'] == 'rejected' for a in attempts),
        'total_steps': sum(row['total_steps'] for row in rows),
        'effective_steps': sum(row['effective_steps'] for row in rows),
        'human_review': 'pending', 'qualified_samples': 0, 'delivery_ready': False,
        'note': '最新成功任务按 task_id 选入；重复试采、已标记重采和失败尝试不计入候选。分布为M2试采分布，不代表全集生产验收。',
    }
    document = {'summary': summary, 'samples': rows, 'attempts': attempts}
    (output / 'index.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    data = json.dumps(document, ensure_ascii=False).replace('<', '\\u003c')
    (output / 'index.html').write_text(HTML.replace('__REVIEW_DATA__', data))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>M2 逐条人工核验</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#142337;font:15px/1.6 system-ui}
header{background:#152b46;color:white;padding:16px 24px}h1{font-size:23px;margin:0}header p{margin:4px 0}
main{display:grid;grid-template-columns:280px 1fr;gap:18px;padding:18px}aside,article{background:white;border-radius:10px;padding:16px}
aside{align-self:start;position:sticky;top:10px;max-height:95vh;overflow:auto}button,select,input,textarea{font:inherit}
button,select,input{padding:7px;border:1px solid #b5c2d4;border-radius:5px}button{cursor:pointer;background:#edf3fa}
nav button{display:block;text-align:left;width:100%;margin:6px 0;font-size:12px}nav button.active{background:#cee5ff}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.stage{position:relative;width:100%;background:#ddd;margin:12px 0}
.stage img{display:block;width:100%;height:auto}.box{position:absolute;border:2px solid #f02727;pointer-events:none;display:none}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6fa;padding:10px;font-size:12px}label{display:block;margin:8px 0}
textarea{width:100%;min-height:70px;padding:8px}h2{font-size:18px}a{color:#145d9b}.status{color:#875900}fieldset{border:1px solid #d0dae7;border-radius:6px}
@media(max-width:900px){main{grid-template-columns:1fr}aside{position:static;max-height:250px}}
</style><header><h1>M2 逐条人工核验</h1><p id="summary"></p><p>结构与证据通过仍待人工核对。原图未经标注修改；红框仅为可切换的网页叠加层。</p></header>
<main><aside><label>核验人姓名 <input id="reviewer" placeholder="由实际核验人填写"></label>
<button id="export">导出本人核验记录</button><p class="status" id="progress"></p><nav id="samples"></nav></aside>
<article><h2 id="goal"></h2><p id="provenance"></p><div class="controls"><button id="prev">上一张</button><select id="steps"></select><button id="next">下一张</button>
<label><input type="checkbox" id="overlay">显示目标框</label><a id="original" target="_blank">打开原图</a><a id="annotation" target="_blank">标注JSON</a><a id="tree" target="_blank">同步界面树JSON</a></div>
<div class="stage"><img id="image" alt="原始操作前截图"><div class="box" id="box"></div></div>
<p id="visit"></p><pre id="step"></pre><fieldset><legend>由实际核验人填写本条结论</legend>
<label><input type="checkbox" id="alignment">逐张核对截图、树、文字、控件引用与坐标；没有缺步或隐式动作</label>
<label><input type="checkbox" id="semantics">任务、每步说明及终态一致，没有凑步、歧义或错误结果</label>
<label><input type="checkbox" id="language">简体中文、可见中文比例及页面真实性符合首批核验要求</label>
<label>本条结论 <select id="decision"><option value="pending">待核验</option><option value="pass">通过</option><option value="reject">退回修正</option></select></label>
<label>问题或备注 <textarea id="notes"></textarea></label></fieldset><p id="final"></p></article></main>
<script id="data" type="application/json">__REVIEW_DATA__</script><script>
const data=JSON.parse(document.querySelector('#data').textContent),rows=data.samples,$=id=>document.getElementById(id);
let current=0,step=0;const decisions=rows.map(()=>({visited:new Set(),alignment:false,semantics:false,language:false,decision:'pending',notes:''}));
$('summary').textContent=`${rows.length} 条候选，${data.summary.site_count} 个站点，${data.summary.total_steps} 张逐步原图；人工核验前正式合格数为 0。`;
function store(){let d=decisions[current];for(const k of ['alignment','semantics','language'])d[k]=$(k).checked;d.decision=$('decision').value;d.notes=$('notes').value;}
function render(){const r=rows[current],a=r.annotation,s=a.steps[step],d=decisions[current];d.visited.add(step);
$('goal').textContent=a.task_instruction;$('provenance').textContent=`${r.sample_id} · ${r.batch_id} · ${r.site.uri} · 程序 ${r.program_version.slice(0,12)} · ${r.effective_steps} 个有效步`;
$('steps').replaceChildren(...a.steps.map((s,i)=>new Option(`${i+1} / ${a.steps.length} · ${s.action.action_type}`,i)));$('steps').value=step;
const src=r.asset_path+'/'+s.image_path;$('image').src=src;$('original').href=src;$('annotation').href=r.asset_path+'/annotation.json';$('tree').href=r.asset_path+'/'+s.ui_tree_path;
$('step').textContent=JSON.stringify({step_id:s.step_id,page_name:s.page_name,user_goal:s.user_goal,action:s.action,tool_call:s.tool_call,next_step_rationale:s.next_step_rationale,step_result:s.step_result},null,2);
$('visit').textContent=`本条已打开 ${d.visited.size}/${a.steps.length} 张；打开图片不等于已核验。`;$('final').textContent=`终态说明：${a.final_result}；${a.completion_judgement}`;
for(const k of ['alignment','semantics','language'])$(k).checked=d[k];$('decision').value=d.decision;$('notes').value=d.notes;
const b=s.action.target_bbox,res=a.device_info.screen_resolution,box=$('box');box.style.display=b&&$('overlay').checked?'block':'none';
if(b){box.style.left=(b[0]/res[0]*100)+'%';box.style.top=(b[1]/res[1]*100)+'%';box.style.width=((b[2]-b[0])/res[0]*100)+'%';box.style.height=((b[3]-b[1])/res[1]*100)+'%';}
$('samples').replaceChildren(...rows.map((r,i)=>{const b=document.createElement('button');b.textContent=`${i+1}. ${r.task_id} [${decisions[i].decision}]`;b.className=i===current?'active':'';b.onclick=()=>{store();current=i;step=0;render()};return b}));
$('progress').textContent=`已填写结论 ${decisions.filter(d=>d.decision!=='pending').length}/${rows.length}；不自动修改批次验收状态。`;
}
$('steps').onchange=()=>{store();step=Number($('steps').value);render()};$('prev').onclick=()=>{store();step=Math.max(0,step-1);render()};$('next').onclick=()=>{store();step=Math.min(rows[current].annotation.steps.length-1,step+1);render()};$('overlay').onchange=()=>{store();render()};
for(const id of ['alignment','semantics','language','decision','notes'])$(id).onchange=store;
$('export').onclick=()=>{store();const reviewer=$('reviewer').value.trim();if(!reviewer){alert('请实际核验人填写姓名。');return;}
for(let i=0;i<rows.length;i++){let d=decisions[i];if(d.decision==='pass'&&(d.visited.size!==rows[i].annotation.steps.length||!d.alignment||!d.semantics||!d.language)){alert('通过结论需要逐张查看并完成三项核对：'+rows[i].sample_id);return;}}
const result={review_type:'human_authored',reviewer,reviewed_at:new Date().toISOString(),delivery_ready:false,records:rows.map((r,i)=>({...decisions[i],visited_steps:[...decisions[i].visited].sort((a,b)=>a-b).map(i=>i+1),visited:undefined,sample_id:r.sample_id,batch_id:r.batch_id,annotation_sha256:r.annotation_sha256,source_file_sha256:r.source_file_sha256}))};
const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='M2-human-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};render();
</script></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.batch, args.output)
