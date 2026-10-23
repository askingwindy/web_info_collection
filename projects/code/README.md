# WebCollect 采集核心

按计划执行真实网页操作，保存原始截图、同步界面树、动作记录与断言，生成待独立质检和人工核验的候选。采集成功、结构通过、本地试点通过和正式交付分别记录。

## 安装与运行

在仓库根目录执行，Python 需要 3.11 或更高版本：

```sh
python3 -m venv projects/code/.venv
projects/code/.venv/bin/python -m pip install -r projects/code/requirements.lock
projects/code/.venv/bin/python -m pip install --no-deps -e projects/code
projects/code/.venv/bin/python -m playwright install chromium
projects/code/.venv/bin/python -m webcollect --help
```

`config/example.json`给出规则及批次字段示例，不是实际采集计划。实际计划通过`--plan`传入，作为本地过程文件管理；不得在配置中提交凭据或登录状态。

## 采集与预检

```sh
projects/code/.venv/bin/python -m webcollect preflight \
  --plan /path/to/plan.json --output results/_work/new-preflight \
  --samples 3 --interval-ms 400

projects/code/.venv/bin/python -m webcollect collect \
  --plan results/_work/new-preflight/scheduled-plan.json \
  --output results/new-batch --registry results/_work/registry.sqlite3
```

也可直接把实际计划传给`collect`。同一生产线的所有批次必须共用编号注册表；注册表应随数据备份，已有批次而注册表缺失时须先恢复。站点按完整`site_uri`登记，同 URI 跨批复用站点编号；`initial_url`只表示任务起始页。同域不同 URI 仍需有实质不同的任务并通过去重。

预检在新浏览器上下文保存完整初始诊断图，执行只读观察，保存逐 URI 风险和包含全部任务的调度计划。`--preserve-order`保留任务顺序；默认可按风险安排顺序。`samples`允许2至5，`interval-ms`允许100至2000。风险组为`NORMAL_M1`、`PREPARE_RECHECK`、`DYNAMIC_CONTENT_TRACK`、`REVIEW_REQUIRED`；分组不授予质检通过。

正式采集校验预检报告、计划、证据清单及源码身份，使用新上下文重新保留首帧。预检图不能拼入正式轨迹，源码漂移时不能继续沿用旧交接计划。

输出目录、报告和导出文件应使用新路径；程序拒绝覆盖已有产物。失败和拒收保留原因、原图及可获得的诊断，不能计入交付量。

## 正文准备与图树一致性

计划可以设置以下配置，也可对单个任务配置：

```json
{
  "content_preparation": {
    "mode": "auto",
    "max_actions": 6,
    "max_scrolls": 4,
    "scroll_step_pixels": 240,
    "close_hints": []
  }
}
```

`auto`按真实页面处理遮挡和正文位置，`article`检查正文可读性，`off`或`false`关闭新增准备动作。准备仍须保留首次完整视口，新增真实点击及滚动逐步写入连续图、树、动作链。已就绪的同一文档保留原阅读位置；新遮罩重新检查，`complete`不插入准备动作。动作预算达到上限且仍未就绪时停止并留证。

`close_hints`仅用于实际看图核对过的关闭控件，必须提供`selector`、可选`index`和`evidence.path/sha256/description`。执行时继续检查当前可见性、命中关系和行为，不凭旧坐标或外观猜测关闭按钮。

每步截图须通过`observe → PNG → observe`严格一致检查。重试仅自然等待，不暂停动画、隐藏动态区域或改 DOM；原生动画时序只用于选择观察窗口，不能代替最终指纹检查。持续变化的页面仍拒收。同步树中的图像名称只取实际`alt/title`，不猜图片主题。

准备不会豁免70%可见中文初筛。DOM文字比例不能覆盖图片和画布内容，整体呈现仍由实际看图审核。正文、控件和完成描述必须依据真实可见内容及通过的断言生成，不从任务预期补造结果。

## 校验、索引与候选组包

```sh
projects/code/.venv/bin/python -m webcollect validate /path/to/sample \
  --mode delivery --manifest /path/to/batch/manifest.json \
  --report verify_results/new-structure.json

projects/code/.venv/bin/python -m webcollect metadata /path/to/batch \
  --output verify_results/new-metadata.csv

projects/code/.venv/bin/python -m webcollect package \
  --source /path/to/source-batches --output results/new-candidate
```

`validate`只报告结构与可机械核对的项目。有效步数排除`wait`和`complete`；通常至少5个真实页面操作，合法短流程须声明并服从全集比例限制。控件名称、边框、触点、动作和相邻截图还须独立核验。

`package`复制完整证据并生成待核验资料，不宣告合格。`scripts/finalize_candidate_reports.py`可依据绑定当前输入的独立QC报告回填候选报告，保留实际来源、审核比例、未执行项及未知项；查看其`--help`选择输入和新输出路径。

独立质检入口与配置见[quality-inspector](../quality-inspector/README.md)。需求来源在`request/`；规则、检查清单和人工审核方法在`projects/prd/`。

## 人工审核

独立质检生成`review.html`、`review-template.json`和`report.json`。审核台按单人使用配置，无需重复填写姓名或选择来源；任务目标和完成标准常驻显示。逐步对照动作前后图，用目标红框和触点辅助检查，每步选择正常、有问题或看不清，再回答图文、终态、中文、隐私、任务差异五个中文问题。

进度自动保存到当前浏览器；右上角可导出带时间的`qc-human-review-*.json`备份，并用“恢复备份”继续。换浏览器或清理本地数据前应先导出，自动保存失败时页面会提示。浏览图片或保存草稿不会自动判通过，实际判断由本人确认。

“最后核对交付资料”提供独立文档/站点类目审核页，和样本结论一起导出，不需手改JSON。导出后通过独立QC的`--reviews`重新检查绑定。完整操作见[人工核验SOP](../prd/M2-人工核验SOP.md)。当前界面更新不签署实际人工记录，不改变候选与报告的既有状态。

`scripts/build_review_bundle.py`及`python -m webcollect.review`保留历史M2三项核验包生成/对账能力，其格式与当前独立QC五项记录不同，不能混用。当前流程以对应输入包生成的审核台和模板为准。

## 源码与数据边界

Git保留核心源码、JS/Schema资源、通用脚本、运行依赖配置和需求规范。测试、批次计划、联调样本、过程报告、`results/`及`verify_results/`留在本地，不纳入Git。客户提供的原始样例属于需求附件，是独立质检基准的必要输入。

正式样本、共享注册表和失败证据应独立备份，不能用源码仓库代替数据存储。程序不会因为采集或导出成功就自动设置正式交付通过。
