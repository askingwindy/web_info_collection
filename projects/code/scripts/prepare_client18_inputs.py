"""Prepare reproducible prose corrections and factual declarations for approved18.

Does not write source samples. The production package command applies the plan.
"""
import argparse
import hashlib
import json
from pathlib import Path


PROMPT = '''以指定的18条原始轨迹为依据整理交付标注。逐项对照原始截图、同步界面树和动作，所有叙述只引用可见证据。末步user_goal必须明确要确认的最终页面内容和结果，不使用“确认最终页面符合任务要求”的套话。登录对话框按“微信扫码快捷登录”的实际界面描述。界面专有名称用「」标示。只改有图树证据支持的叙述文字，不修改sample_id、图片、界面树、步骤顺序、真实动作、工具参数、目标真值，不新增或删除步骤，不缩减原任务以隐藏未完成部分。保持历史人工审核的原始身份和结论；本轮AI复核不能称为新增人工审核。'''

GOALS = {
 'S000002_sample_000007':'确认字数统计结果显示15个汉字、3个中文标点、3个段落和20个总字符',
 'S000003_sample_000010':'确认信息熵结果显示「2.0000 bit」及四个等概率项的分布表',
 'S000003_sample_000012':'确认排序输出完整显示10、7、2、-1，重复的7只保留一次',
 'S000004_sample_000006':'确认「出师表」正文中包含「鞠躬尽瘁」的段落可见',
 'S000004_sample_000007':'确认「滕王阁序」正文中包含「老当益壮」的段落可见',
 'S000005_sample_000001':'确认「JAMStack / SSG」章节显示单页和多页静态站点的适用场景说明',
 'S000005_sample_000002':'确认「取舍」小节显示组合式 API 代码组织及其接近普通 JavaScript 的说明',
 'S000007_sample_000018':'确认「地方示范」内容中可见北京示范区建设范围扩展至600平方公里的说明',
 'S000008_sample_000016':'确认调查报道中列举平台图片异常的段落可见「在京东平台」及「在拼多多」的分析',
 'S000009_sample_000016':'确认课程页面同时显示「GRE录播课」「GRE直播课」和「GRE一对一」',
 'S000010_sample_000015':'确认目录显示「孙子兵法」「子部兵家类」「黄帝内经」和「子部医家类」',
 'S000011_sample_000015':'确认「变体及类似食品」章节中「水晶虾饺」「调味猪肉馅」和「台湾水饺」内容可见',
 'S000012_sample_000015':'确认「學」条目当前视口可见「新字体」「旧字体」和「音读」内容',
 'S000013_sample_000015':'确认「一般天气服务」页面显示「电话询问」「互联网」及「文字及声音版本」说明',
 'S000014_sample_000015':'确认作品赏析显示「全词景中有情」和「首尾呼应作用」的结构总结',
 'S000015_sample_000015':'确认中文宣言的「准则 9」显示商业利益和公共利益平衡的要求',
 'S000018_sample_000001':'确认「20以内的进位加法」正文显示8加9等于17，并说明将9拆成2和7',
 'S000019_sample_000003':'确认第一篇「四季」教案显示四季色彩特征、作品赏析及学生介绍作品的活动说明',
}
NAMES = {
 'S000004_sample_000006':['维基文库','《出师表》','前出师表','后出师表'],
 'S000004_sample_000007':['维基文库','《滕王阁序》'],
 'S000005_sample_000001':['Vue','单页面应用','全栈服务端渲染','静态站点生成'],
 'S000005_sample_000002':['Vue','组合式 API 常见问答','取舍'],
 'S000007_sample_000018':['经济参考报'],
 'S000009_sample_000016':['新东方在线','GRE/GMAT'],
 'S000010_sample_000015':['史记','论语','庄子','增广贤文','资治通鉴','孙子兵法','黄帝内经'],
 'S000011_sample_000015':['中文维基百科','《饺子》','名称','传言','历史','制法','变体及类似食品'],
 'S000012_sample_000015':['维基词典'],
 'S000013_sample_000015':['香港天文台','一般天气服务'],
 'S000014_sample_000015':['《八声甘州·对潇潇暮雨洒江天》','柳永'],
 'S000015_sample_000015':['Mozilla','中文宣言'],
 'S000018_sample_000001':['维基教科书','小学数学一年级上册','认识钟表','20以内进位加法'],
 'S000019_sample_000003':['第一范文网','语文教案','《四季 教案（精选12篇）》'],
}
TASKS = {
 'S000005_sample_000001':'在「Vue」中文文档中关闭偏好提示，依次查看「单页面应用 (SPA)」「全栈 / SSR」及「JAMStack / SSG」，最后定位单页与多页静态站点适用场景的说明。',
 'S000018_sample_000001':'从「维基教科书」的「小学」课程目录打开「小学数学」的「一年级上册」，先查阅「认识钟表」的时针、分针说明，再阅读「20以内的进位加法」的凑十法及8加9的拆分示例。',
 'S000015_sample_000015':'阅读「Mozilla 宣言」的引言和目的，查阅有关互联网公共资源、安全隐私、用户自主、开源和社区治理的准则，最后定位商业化参与准则，核对其对商业利益与公共利益平衡的要求。',
}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    source=args.baseline/'client-original'; args.output.mkdir(parents=True,exist_ok=False)
    changes=[]
    for p in sorted(source.glob('samples/*/annotation.json')):
        a=json.loads(p.read_text());sid=a['sample_id'];n=len(a['steps']);edits=[]
        def edit(path,before,after,evidence):
            if before!=after:edits.append(dict(path=path,before=before,after=after,evidence=evidence))
        edit(f'steps/{n-1}/user_goal',a['steps'][-1]['user_goal'],GOALS[sid],[f'images/step_{n:03}.png',f'ui_tree/step_{n:03}.json'])
        task=a['task_instruction'].replace('组合式接口常见问答','组合式 API 常见问答')
        for name in NAMES.get(sid,[]):task=task.replace(name,'「'+name.strip('《》')+'」')
        task=TASKS.get(sid,task)
        edit('task_instruction',a['task_instruction'],task,[s[k] for s in a['steps'] for k in ('image_path','ui_tree_path')])
        if sid=='S000009_sample_000016':
            replacements={
                'user_goal':'关闭「微信扫码快捷登录」对话框以查看公开课程',
                'next_step_rationale':'当前页面显示「微信扫码快捷登录」对话框，点击右上角关闭按钮后继续查看公开课程',
                'step_result':'「微信扫码快捷登录」对话框关闭，公开课程首页可见，右侧客服浮层仍在页面上',
                'action/precondition':'当前首页中央显示「微信扫码快捷登录」对话框，右上角关闭按钮可见',
                'action/expected_result':'登录对话框关闭，返回可查看公开课程的首页视口'}
            for key,after in replacements.items():
                node=a['steps'][0]
                for part in key.split('/'):node=node[part]
                edit('steps/0/'+key,node,after,['images/step_001.png','images/step_002.png','ui_tree/step_001.json','ui_tree/step_002.json'])
        evidence_hashes={str(q.relative_to(p.parent)):hashlib.sha256(q.read_bytes()).hexdigest() for d in ('images','ui_tree') for q in sorted((p.parent/d).iterdir()) if q.is_file()}
        changes.append(dict(sample_id=sid,annotation_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),evidence_sha256=evidence_hashes,edits=edits))
    if {r['sample_id'] for r in changes}!=set(GOALS):raise ValueError('Source is not exactly the approved18 set')
    revision=dict(schema_version='webcollect-narrative-revisions-1',author='Codex AI标注整理，非人工审核',prompt=PROMPT,samples=changes)
    excluded=json.loads((args.baseline/'reviews/excluded-samples.json').read_text())
    exclusions=[]
    for r in excluded:
        bad={k:v for k,v in r.get('review',{}).get('checks',{}).items() if v.get('status')!='PASS'}
        exclusions.append(dict(sample_id=r['sample_id'],reason=r['reason'],non_pass_checks=bad))
    facts=dict(schema_version='webcollect-production-facts-1',screenshot_configuration={'viewport':[1280,720],'device_scale_factor':1},
      collection_method='本批沿用真实中文网站的浏览器自动化采集：计划驱动执行实际点击、输入、按键、滚动和返回；各任务使用隔离浏览器上下文。截图为动作前的真实视口，界面树来源于页面实际元素，未用视觉模型重建元素框。本次仅整理18条既有轨迹及叙述，不重新访问站点、不补拍或合成图片。',
      frequency_policy='已保存的8个来源批次配置均为任务间隔1秒、动作后的默认稳定等待500毫秒，视页面加载增加等待；每个采集进程顺序执行任务。任务失败停止该任务并留档，不以无限重试冲击站点。本说明声明采集配置及策略，不声称掌握第三方资源的完整请求速率日志。',
      accounts_and_privacy='18条任务为公开网页查询、阅读或在线工具测试，使用隔离且不导入持久会话的浏览器上下文；保留的执行记录没有输入账号密码、扫码登录、支付或交易提交。新东方任务关闭登录对话框后浏览公开内容，没有完成登录。输入内容为诗句、检索词或测试数字。公开网页中的作者、教师、报道人物姓名按原页面保留，不是采集者私人账号信息；本次不额外修改或脱敏原图与同步树。',
      change_detection='采集器采用观察页面状态、截图、再次观察的顺序，前后状态一致且PNG尺寸匹配才保存同步图树。相邻PNG文件SHA-256不同记录screen_changed=true，页面可见文字、输入值、焦点、选择状态和滚动位置差异形成step_result。文件变化本身不等于动作解释成立，动作与相邻视口、终态与任务的对应关系由独立质检逐图核对。',
      narrative_generation='原始标注输入包含任务计划文字、采集状态差异模板，以及历史离线修订，不能把全部历史文字笼统称为模板生成。本轮采用下列明示指令对整套叙述逐图审订：保留有证据支持的原文，按确定性修订清单替换末步子目标、专有名称引用和登录对话框描述。生产程序校验修订前值及原标注哈希，仅允许叙述字段变化；原图、同步树、真实动作及目标真值保持原样。本轮独立AI复核指令与实际覆盖另有真实记录，历史人工结论不改签。下列提示词记录本轮整理过程，不冒充无法恢复的历史模型提示词。',
      selection=dict(total_samples=20,selected_count=18,excluded_count=2,excluded_samples=exclusions,historical_human_pass=18,historical_human_total=20,scope='原20条人工核验池，本次固定输出其中18条；不等于全部历史试验捕获总体'),
      category_share_authorization='用户2026-10-24明确要求：以现有18条case为准，本次暂不考核类目占比。')
    for name,value in [('revisions.json',revision),('production-facts.json',facts)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'samples':len(changes),'edits':sum(len(r['edits']) for r in changes),'output':str(args.output)},ensure_ascii=False))


if __name__=='__main__':main()
