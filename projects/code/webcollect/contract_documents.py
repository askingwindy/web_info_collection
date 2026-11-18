"""Render the requested customer documents from explicit production facts."""
from webcollect import workspace_json as json
from pathlib import Path


def load_facts(path):
    if path is None:
        return None
    facts = json.loads(Path(path).read_text(encoding='utf-8'))
    fields = ('collection_method', 'frequency_policy', 'accounts_and_privacy', 'change_detection', 'narrative_generation')
    if (facts.get('schema_version') not in ('production-facts', 'webcollect-production-facts-1') or
            not all(isinstance(facts.get(k), str) and facts[k].strip() for k in fields) or
            not isinstance(facts.get('selection'), dict)):
        raise ValueError('Production facts need actual collection, account, frequency and narrative declarations')
    return facts


def render(out, records, facts, revisions=None):
    out = Path(out)
    if facts is None:
        return
    chapters = []
    for dtype in sorted({r['data']['trajectory_source']['data_type'] for r in records}):
        spaces = sorted({r['data']['trajectory_source']['action_space'] for r in records if r['data']['trajectory_source']['data_type'] == dtype})
        chapters.append('## ' + dtype + '\n\n动作空间版本：' + '、'.join(spaces) + '。采用附件B的Web动作子集。')
    mapping = ('click/double_click/right_click→{x,y}；type→{text}；hotkey→{keys}；'
               'scroll→{x,y,direction}；drag→{x,y,end_x,end_y}；select→{x,y,option}；'
               'open_url→{url}；back/wait→{}；complete→{status}。\n\n'
               'type只作用于当前已聚焦输入框；hotkey保留实际执行keys及input_text，显示名来自同一键数组，不将Meta或Command替换为Ctrl。'
               'delivery-windows-keys-2只解释历史版本，不适用于新输出；本次采用delivery-actual-keys-1。'
               '实际参数、平台、逐步对应与原派发/执行哈希见actual-execution.json；UNAVAILABLE明确表示缺原派发依据，complete为宿主终态。'
               '原始日志和请求保留在包外，不将参数表达恢复冒称为新浏览器操作。'
               'scroll的down表示查看更下方内容；滚动距离不加入交付参数。'
               '每步只记录一个实际动作，等待和结束确认不计入有效操作。')
    synthesis = '# 合成方式说明\n\n' + '\n\n'.join(chapters)
    synthesis += '\n\n## 动作映射\n\n' + mapping
    resolutions = sorted({tuple(r['data']['device_info']['screen_resolution']) for r in records})
    sizes = '、'.join(str(w) + '×' + str(h) for w, h in resolutions)
    configuration = facts.get('screenshot_configuration', {})
    if configuration.get('viewport') is not None and tuple(configuration['viewport']) not in resolutions:
        raise ValueError('Declared capture viewport differs from delivered PNG dimensions')
    dpr = ('采集配置DPR=' + str(configuration['device_scale_factor']) + '。') if 'device_scale_factor' in configuration else ''
    synthesis += ('\n\n## 坐标\n\n本批截图规格为' + sizes + '的当前视口PNG。' + dpr +
                  '原点左上角，x向右、y向下，单位是截图整数像素。目标框来自页面真实元素的视口边界，'
                  '动作坐标、工具参数和同步树使用同一坐标；每张图为本步动作前界面，末图为最终状态。')
    synthesis += '\n\n## 界面变化判定\n\n' + facts['change_detection']
    synthesis += '\n\n## 文字字段生成方式\n\n' + facts['narrative_generation']
    if facts.get('prompt_stages'):
        names={'planning':'任务规划','narrative':'标注生成','revision':'历史文字修订'}
        synthesis+='\n\n## 分阶段生成事实与提示词\n\n以下按真实阶段分别保留，编辑指令不替代采集规划或生成指令。'
        for record in facts['prompt_stages']:
            synthesis+='\n\n### 批次「'+record['batch_id']+'」\n\n声明SHA-256：'+record['declaration_sha256']
            for stage_name,stage in record['stages'].items():
                synthesis+='\n\n#### '+names[stage_name]+'\n\n'+stage['description']
                if stage['mode']=='model':
                    synthesis+='\n\n实际提示词：\n\n```text\n'+stage['prompt']+'\n```'
                else:
                    synthesis+='\n\n实际模板版本：'+stage['template_version']+'。此阶段未声明模型生成。'
        if facts.get('prompt'):
            synthesis+='\n\n## 兼容来源的历史提示词\n\n```text\n'+facts['prompt']+'\n```'
        if revisions is not None:
            synthesis+='\n\n## 本轮文字修订提示词\n\n```text\n'+revisions['prompt']+'\n```\n\n执行者：'+revisions['author']+'。'
    elif revisions is not None:
        synthesis += ('\n\n## 本轮标注提示词\n\n以下为本轮标注整理的实际指令。\n\n```text\n' +
                      revisions['prompt'] + '\n```\n\n执行者：' + revisions['author'] + '。')
    elif facts.get('prompt'):
        synthesis += '\n\n## 标注提示词\n\n```text\n' + facts['prompt'] + '\n```'
    (out / '合成方式说明.md').write_text(synthesis + '\n', encoding='utf-8')
    annex = (out / '附件B-动作空间与坐标系.md').read_text(encoding='utf-8')
    (out / '动作空间与系统提示.md').write_text(annex + '\n\n' + '\n\n'.join(chapters) + '\n\n实际文字标注方式与提示词见《合成方式说明》。附件B第3节仅为参考系统提示，采集为计划驱动。\n', encoding='utf-8')
    source = ('# 来源与合规说明\n\n## 站点清单\n\n站点URI、类目、样本归属见site-list.json，索引见metadata.csv。'
              '\n\n## 采集方式\n\n' + facts['collection_method'] + '\n\n## 访问频率策略\n\n' + facts['frequency_policy'] +
              '\n\n## 账号与脱敏\n\n' + facts['accounts_and_privacy'] +
              '\n\n## 本批筛选统计\n\n```json\n' + json.dumps(facts['selection'], ensure_ascii=False, indent=2) + '\n```\n')
    (out / '来源与合规说明.md').write_text(source, encoding='utf-8')
    readme = (out / 'README.md').read_text(encoding='utf-8').replace('当前独立QC状态：NOT_RUN', '实际质检结果见qc_report.md')
    (out / 'README.md').write_text(readme, encoding='utf-8')
    with (out / 'README.md').open('a', encoding='utf-8') as stream:
        stream.write('\n## 本批范围与筛选\n\n```json\n' + json.dumps(facts['selection'], ensure_ascii=False, indent=2) + '\n```\n')
        if facts.get('category_share_authorization'):
            stream.write('\n本次类目占比：仅统计、不考核。授权：' + facts['category_share_authorization'] + '\n')
