# WebCollect 采集核心

按计划执行真实网页操作，保存原始截图、同步界面树、动作记录与断言。先按客户样例导出实际交付文件，再由独立质检器读取该输出；采集成功、格式通过、人工审核、本地试点和客户验收分别记录。

## 正式交付流程

正式流程为：真实`collect` → 从实际清单生成`production_facts` → `package --layout client --facts ...`生成候选文件 → 独立QC的`check --stage payload`检查实际文件与真实审核记录 → `finalize-client`附入已绑定且PASS的摘要 → 独立QC的`check --stage final`只读核对完整封包 → `archive-client`生成对客ZIP与校验文件。`package`输出即使结构通过也只是候选；只有最后三个发布步骤全部通过后才能作为对客交付。历史baseline/pilot命令用于工程兼容审计，不是默认交付门槛。

`package`新增可选参数`--facts`和`--revisions`。facts包含实际采集方式、频率策略、账号与脱敏、变化判定、文字生成方式和本批筛选统计，用于填写原需求要求的说明文件；没有依据的事实不能编造。叙述修订计划绑定原annotation及引用图树的SHA256，仅允许修改任务和步骤叙述，禁止改变原图、同步树、真实动作、目标真值或步骤顺序。修订后的样本必须取得新的质检记录，不能沿用旧annotation签署。

2026-10-26用户将快捷键规则从仅全选扩展为全部Windows表达：例如粘贴为 `keys=["ctrl","v"]`、`input_text=ctrl+v`、`target_text=Ctrl+V`，单键统一显示Enter、Tab、Home等。采集器仅规范交付标注，实际操作与原始证据保留原生按键；按source_os区分macOS Command与Windows Win，并只执行已声明同功能映射，未定义的Mac特殊组合报WINDOWS_SHORTCUT_MAPPING_REQUIRED。`package`采用相同幂等规则，PNG、界面树、目标真值及原来源不改写。发生归一化时生成独立 `webcollect-action-normalization-provenance-1` 包外清单，记录原/新annotation哈希、逐步映射及 `delivery-windows-keys-2` 版本，`capture_binding=false`；不能当原样采集索引传给旧external-evidence入口。归一化与旧审核同时输入会被拒绝，须对新版重新检查；历史正式包和人工记录不原地改写。

步骤结果只描述动作后真实可见的变化。导航说明使用画面中的标题与正文，不能把浏览器后台title当成可见标题；多个可见片段分别引用，避免拼成一个无法绑定的引文。目标卷次和后置条件只能帮助选择已经可见的事实，不把规划预期当成结果。引用无法绑定时保留叙述诊断及失败现场，报`NARRATIVE_EVIDENCE_UNSUPPORTED`，不再用“具体可见变化待独立审核”替代实际观察后保存成功样本。现有问题文字可通过`--revisions`绑定原annotation及图树SHA离线修订，不能改动作或代签旧审核。

本批18条的原始输入固定在`results/baselines/approved18-20261024`；`scripts/prepare_client18_inputs.py`生成可复用的facts与修订输入，再交正式package执行。用户仅对此批授权类目占比只统计不考核；运行独立QC时显式使用`delivery-approved18-20261024.json`。默认交付规则仍考核20%上限，且不强制20条试点数量。

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
  --output results/new-batch --registry /path/to/existing-active-production-ledger.sqlite3
```

旧版计划保留直接传给`collect`的兼容入口。新M4计划使用下述严格发布与恢复入口。账本参数必须指向已有生产活动账本，不能为了本批新建空账本。原始封存ledger不可修改；从保留账本派生生产活动副本一次，此后同一生产线所有批次始终复用该副本。注册表应随数据备份，已有批次而注册表缺失时须先恢复。站点按完整`site_uri`登记，同 URI 跨批复用站点编号；`initial_url`只表示任务起始页。同域不同 URI 仍需有实质不同的任务并通过去重。

预检在新浏览器上下文保存完整初始诊断图，执行只读观察，保存逐 URI 风险和包含全部任务的调度计划。`--preserve-order`保留任务顺序；默认可按风险安排顺序。`samples`允许2至5，`interval-ms`允许100至2000。风险组为`NORMAL_M1`、`PREPARE_RECHECK`、`DYNAMIC_CONTENT_TRACK`、`REVIEW_REQUIRED`；分组不授予质检通过。

正式采集校验预检报告、计划、证据清单及源码身份，使用新上下文重新保留首帧。预检图不能拼入正式轨迹，源码漂移时不能继续沿用旧交接计划。

输出目录、报告和导出文件应使用新路径；程序拒绝覆盖已有产物。失败和拒收保留原因、原图及可获得的诊断，不能计入交付量。

### M4计划发布与恢复

程序结构、采集证据或精确索引检查出现 `program` 失败时，采集器保留该真实拒收 attempt 并立即暂停 scope，下一任务不再分配编号。普通站点语义失败不触发此程序级暂停。

已暂停且全部实际 attempt 都终结为 `rejected`、无成功和在途预留的批次，可使用 `runtime-close-replan --output /path/to/old-batch --registry /path/to/active.sqlite3 --reason "实际故障及重新规划原因" --evidence /path/to/evidence-list.json` 永久关闭。证据参数是含绝对 `path` 和 `sha256` 的列表。命令只新增 `replanning/closure.json`，完整绑定原文件 SHA、原 attempt、未开始任务和数据库前态，释放任务配额并记录数据库关闭事件；原 manifest、计划、快照、编号及真实失败分母不改写。关闭后的 scope 为 `closed_replanned`，不能 `runtime-resume`；新版本任务进入同 campaign 的新批次，继续共用原尝试预算。相同原因和证据可幂等核验；事务提交前仅写 `.prepared.json`，提交成功后才原子公开 `closure.json`。数据库未提交的中断保留孤儿 prepared 文件等待核账，不自动采用；数据库已提交但公开前中断，可用相同命令按关闭事件 SHA 恢复公开。

`schema_version: webcollect-plan-m4-1`要求任务版本、子目标、必做动作、实际可见完成依据、站点能力版本、任务族，以及采前的分阶段`production_facts.prompt_stages`。控件任务需要实际目标标签证据。机器断言通过后仍为`semantic_status: REVIEW_REQUIRED`，不能代替看图、真人审核或客户验收。图标/复杂几何等尚未验证能力应先登记为待审，不属于合同新增禁令。

能力目录记录`webcollect-site-capability-1`版本、URI/类目、实测及失效时间、支持动作、任务族、状态与绝对路径/SHA证据。`plan-publish`同时重验现有preflight交接，拒绝过期能力及未处理预检失败；它不分配任何样本编号。下列路径均为操作示例，不是已经获准采集的真实计划：

```sh
projects/code/.venv/bin/python -m webcollect plan-publish \
  --plan /path/to/scheduled-m4-plan.json --capabilities /path/to/capabilities.json \
  --output /path/to/publication.json

projects/code/.venv/bin/python -m webcollect collect \
  --plan /path/to/scheduled-m4-plan.json --publication /path/to/publication.json \
  --policy /path/to/wave-policy.json --output /path/to/new-batch \
  --registry /path/to/existing-active-production-ledger.sqlite3

projects/code/.venv/bin/python -m webcollect runtime-status \
  --output /path/to/new-batch --registry /path/to/existing-active-production-ledger.sqlite3

projects/code/.venv/bin/python -m webcollect collect \
  --plan /path/to/scheduled-m4-plan.json --publication /path/to/publication.json \
  --output /path/to/new-batch --registry /path/to/existing-active-production-ledger.sqlite3 --resume
```

首次运行必须显式提供预算及`baseline_category_counts`；旧200可沿用数未核实时不能默认忽略它们。一个campaign共享尝试、待审库存、类目预留和并发预算；改变批次目录不重置预算。预算调整使用`runtime-policy --updates /path/to/updates.json --reason "实际调整依据"`，同样指定`--output`和`--registry`，保留原策略和原因。新campaign代表独立生产范围，不能用于绕过本阶段上限。

编号预留、attempt关联和事件在同一SQLite事务提交。已预留未开始的编号单列，永久保留；实际开始后失败/中断均计入真实尝试分母。租约过期后封存半轨迹，再用新编号重试；提交完成的样本须匹配保存收据才能跳过。相同任务版本不能跨目录重复登记；同目录续跑要求计划、发布收据、源码和账本一致。需修改任务或程序时保留旧批次并生成新版本，不拼接旧轨迹。

`RuntimeStore.record_review`仅登记带证据的导出选择及配额/待审库存释放，返回`raw_retained: true`；它不改变已保存attempt的采集结果，也不认证审核者身份。证据必须包含一份实际`quality-inspector`报告，复用客户封包绑定校验核对当前完整客户目录及每条样本SHA；`pass`须对应该样本`PASS`，`reject`须对应`FAIL/REVIEW_REQUIRED`，任意文件SHA不能释放待审库存。`record_publication`另要求同样完整绑定的`final`报告且`delivery_status: PASS`、`release_ready: true`，所有发布编号在报告中通过并已登记审核通过；客户验收仍为`UNKNOWN`。

审核拒收后仍须保留原始采集批次中的样本及保存收据，合格集合由导出步骤单独选择。不能用会移动原始样本的旧拒收脚本处理需要续跑的M4批次；若原始文件已被移动或修改，续跑应停止并核账，后续任务使用新批次/版本，不能自动补号掩盖缺失。

生产端精确图片索引在每次运行从实际文件建立，增量添加已保存样本，结束时全量重哈希。预算/待审限制触发时保留`paused_pending_resume`；索引完整性未通过不能导出M4完成事实。独立QC另对实际客户目录做累计四路检查，生产端索引不授予交付合格。

首波策略可显式增加`min_free_disk_bytes`、`max_output_bytes`、`max_worker_seconds`和绝对路径`resource_root`。存储按固定campaign输出根的实际文件计算，worker时间累计同campaign所有scope；退出前未记结束的会话按持续到当前检查时刻的上界计量，不以重启清零。每次`claim_next`前检查资源，超限暂停且不分配新编号、不删除证据。调整预算仍须`runtime-policy --reason`；核实后用`runtime-resume --registry ... --output ... --reason ...`恢复范围，下次运行仍执行资源检查。检查保证下一attempt前停止，不声称能在一个超长attempt内瞬时切断。

M4采集在`metering/`保留append-only阶段与请求事件及每attempt结束摘要。网络只保留host、状态码和传输错误码，不写URL路径/查询、请求体、响应体、cookie或凭据；context关闭引起的中止不自动解释成网站失败。回调写入失败会在采集或关闭边界停止并保留真实attempt结果。模型用量/费用没有可核对来源时为`UNKNOWN`。规划、AI审核和修订等采集器外阶段可用`python -m webcollect.telemetry start --ledger ... --phase ... --scope ...`记录真实开始，随后用`finish --ledger ... --phase-id ... --outcome completed`记录结束；禁止倒填尚未测量的历史阶段。阶段墙钟不是人工注意力时长，也不代表已产生合格样本。

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

## 客户输出与质检顺序

真实采集计划需在顶层保存`production_facts`声明，再开始采集。账号与隐私声明必须与实际执行方式一致；下例仅适用于确实无登录、无支付的公开页任务，不能照抄到其他账号或业务流程。模型提示词须原样保存本次实际发送的指令，不能事后编写一个提示词冒充历史输入。

```json
{
  "production_facts": {
    "accounts_and_privacy": "本次只浏览公开页面，每个任务新建浏览器上下文，不导入持久登录状态；不输入账号密码，不执行支付、下单或交易。导出复制原图与同步树，不离线改写；页面与输入是否含个人信息仍须实际逐图核对。",
    "narrative_mode": "mixed",
    "narrative_generation": "任务指令、子目标与预期依据由模型根据所附实际指令规划；步骤结果与终态描述由采集器按同步观察和通过的断言生成。",
    "prompt": "此处必须原样保存本次真正发送给模型的完整任务规划及标注指令；此格式示例不是实际提示词。"
  }
}
```

`narrative_mode`为`template`、`model`或`mixed`；后两者必须附真实`prompt`。仅模板模式也必须如实说明模板的输入和生成范围。也可用`--declarations /path/to/actual-declarations.json`提供实际声明，文件直接含上述四个声明字段；其SHA会写进facts。没有真实账号、隐私或文字生成声明时工具拒绝生成完整资料，不能以猜测或UNKNOWN充数。

```sh
projects/code/.venv/bin/python -m webcollect.production_facts \
  --source /path/to/finished-source-batches \
  --output verify_results/customer-batch/production-facts.json

projects/code/.venv/bin/python -m webcollect package \
  --source /path/to/finished-source-batches \
  --facts verify_results/customer-batch/production-facts.json \
  --output results/customer-batch-candidate \
  --evidence-output verify_results/customer-batch/source-index.json

projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --input results/customer-batch-candidate --stage payload \
  --reviews /path/to/actual-evidence-bound-reviews.json \
  --output verify_results/customer-batch/qc-payload
```

事实工具只接受真实、已结束的采集批次，检查全部计划任务与attempts逐一对应、无遗漏或重复；按实际配置生成频率说明，保留拒收尝试、原始分母和具体原因。它不代表采集成功或语义通过。全部受控测试使用临时目录，不能放进真实交付样本或数量统计。

首次尚无审核记录时，先省略`--reviews`生成审核台与模板，再由实际审核者逐图作出结论；缺失审核会保持待审，不能直接封包。取得真正绑定当前annotation和图树的审核记录后，用上面的payload命令检查，并把结果写入新的报告目录。默认交付profile执行单类目≤20%、最多3种视口和短流程≤2%，不采用旧18条的类目豁免，也不应用20条pilot门槛。

delivery模式还要求实际阅读交付资料的`delivery_document_review`，与样本审核一同存入`--reviews` JSON。五项资料结论绑定全部payload文件哈希；缺失或陈旧时禁止发布。`qc_report.md`如实列出图像审核者身份与样本覆盖数，以及独立资料审核者、具体证据和结论。最终只读QC独立核对这些内容；报告及校验和排除自身绑定，避免循环回填。

本次10站、200条范围已配置为`projects/quality-inspector/config/delivery-200-10sites-20261024.json`，明确要求`targets.expected_samples=200`、`targets.expected_sites=10`、`targets.category_share=enforced`，保留全部去重算法及附件SHA。payload和final两次QC均显式传入`--profile projects/quality-inspector/config/delivery-200-10sites-20261024.json`，并核对逐站样本分布；不能复用`delivery-approved18-20261024.json`。此配置只定义本次判定范围，不表示已有200条真实样本或其质检通过。


`validate`只报告结构与可机械核对的项目。有效步数排除`wait`和`complete`；通常至少5个真实页面操作，合法短流程须声明并服从全集比例限制。控件名称、边框、触点、动作和相邻截图还须独立核验。

`package`默认生成客户目录，直接采用原始sample的结构：

```text
customer-batch/
  samples/<sample_id>/
    annotation.json
    images/step_NNN.png
    ui_tree/step_NNN.json
  metadata.csv
  qc_report.md
  SHA256SUMS
  附件A-字段说明.md
  附件B-动作空间与坐标系.md
  动作空间与系统提示.md
  合成方式说明.md
  来源与合规说明.md
  README.md
  site-list.json
  ground_truth/<sample_id>.json
```

样本中的三个条目、连续文件名、必填字段、控件引用、参数与坐标按附件A/B检查；不能夹带额外空目录或内部采集文件。样本文件从源件原样复制并逐文件校验，不为贴近示例改写真实采集来源，也不照抄示例中已声明的空任务标签缺陷。`data_type`配套同名系统提示章节随客户资料输出。

原始动作、捕获日志、内部清单和完整审核记录留在客户包外。`--evidence-output`生成来源索引；未修订时绑定客户文件与原始证据SHA，叙述修订后分别记录源标注和新标注SHA并明确不能当作捕获绑定。默认交付QC只读客户包和实际审核记录，旧baseline、raw及来源索引属于可选工程审计，不影响合同结论，也不替代看图。

需要按已完成的五项人工审核筛选时，使用`--reviews /path/to/qc-human-review.json --approved-only`；程序核对审核与实际样本绑定，仅选入明确通过项，并在包外保留完整原始分母和排除原因。筛选后的审核记录仍保持原对象，不改签署人或结论；新客户包的资料审核不能套用旧包的`package_review`。

新版`qc-review-2`使用已完成独立QC的实际客户候选目录作为`--source`，另提供`--selection-report /path/to/current-payload-report.json`。生产导出复用独立QC当前合同及覆盖检查，核对报告的完整客户文件绑定、原审核五项结论与实际样本机械状态。`--approved-only`仅选择当前样本QC为PASS且真人五项PASS者；有真实FAIL的总体报告可以用于筛选，但未验证/过期报告不能放行。原v2记录原样保留，不转换成v1；所选新包仍需重新资料审核及payload/final QC。提供facts时，selected_count必须对应本次选集，原尝试分母及排除原因继续保留。

同ID字段修订按“原初判包外冻结 → 新目录修订 → 当前版本实际重审与QC → 最终runtime选择”执行。不要把暂时的初判FAIL先写成不可变的runtime最终选择；真实重采仍使用新编号。选集不会移动或删除原始成功/失败attempt，也不会替代最终发布或客户验收。

导出只表示文件准备完成。初次导出时`qc_report.md`如实保持未运行状态，实际质检报告写入包外的新目录，不回写正在被检查的客户输入。需要把已执行质检结果带入交付资料时，使用正式命令生成新输出并再次质检：

```sh
projects/code/.venv/bin/python -m webcollect finalize-client \
  --source results/customer-batch-candidate \
  --qc-report verify_results/customer-batch/qc-payload/report.json \
  --output results/customer-batch-final

projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --input results/customer-batch-final --stage final \
  --reviews /path/to/actual-evidence-bound-reviews.json \
  --output verify_results/customer-batch/qc-final

projects/code/.venv/bin/python -m webcollect archive-client \
  --source results/customer-batch-final \
  --qc-report verify_results/customer-batch/qc-final/report.json \
  --output results/customer-batch-final.zip
```

`finalize-client`核对来源报告的实际客户路径、完整文件SHA、全部样本及图树SHA后，仅向新目录附入真实质检摘要。原包和报告保持不变，客户摘要不混入内部工作路径和raw。由于样本字节不变，原样本证据与审核记录仍可按内容绑定使用；新包的文件清单及资料审核必须重新核对。需要导入人工审核时，上述两次`check`均可增加同一份所选样本的`--reviews`，不能套用旧包级审核。程序不手改报告或校验和使输入自称通过。

历史内部候选格式可显式选择`package --layout candidate`。`scripts/finalize_candidate_reports.py`保留历史多批候选的回填能力；其输入不能替代本流程的实际客户输出。

独立质检入口与配置见[quality-inspector](../quality-inspector/README.md)。需求来源在`request/`；规则、检查清单和人工审核方法在`projects/prd/`。

## 人工审核

独立质检生成`review.html`、`review-template.json`和`report.json`。审核台按单人使用配置，无需重复填写姓名或选择来源；任务目标和完成标准常驻显示。逐步对照动作前后图，用目标红框和触点辅助检查，每步选择正常、有问题或看不清，再回答图文、终态、中文、隐私、任务差异五个中文问题。

进度自动保存到当前浏览器；右上角可导出带时间的`qc-human-review-*.json`备份，并用“恢复备份”继续。换浏览器或清理本地数据前应先导出，自动保存失败时页面会提示。浏览图片或保存草稿不会自动判通过，实际判断由本人确认。

“最后核对交付资料”提供独立文档/站点类目审核页，和样本结论一起导出，不需手改JSON。导出后通过独立QC的`--reviews`重新检查绑定。完整操作见[人工核验SOP](../prd/M2-人工核验SOP.md)。当前界面更新不签署实际人工记录，不改变候选与报告的既有状态。

`scripts/build_review_bundle.py`及`python -m webcollect.review`保留历史M2三项核验包生成/对账能力，其格式与当前独立QC五项记录不同，不能混用。当前流程以对应输入包生成的审核台和模板为准。

## 源码与数据边界

Git保留核心源码、JS/Schema资源、通用脚本、运行依赖配置和需求规范。测试、批次计划、联调样本、过程报告、`results/`及`verify_results/`留在本地，不纳入Git。客户提供的原始样例属于需求附件，是独立质检基准的必要输入。

正式样本、共享注册表和失败证据应独立备份，不能用源码仓库代替数据存储。程序不会因为采集或导出成功就自动设置正式交付通过。

## 三程序接口与任务生成（2026-10-26）

新增独立命令 `python -m webcollect.batch` 和 `python -m webcollect.task_generation`（仓库运行设置 `PYTHONPATH=projects/code`）。前者管理冻结的运行配置、job/租约、请求前费用预留、限额及用量；后者从站点库存生成表单任务规格，编译为现有M4计划，并调用原预检/发布、collect_m4、facts及客户导出。安装后入口为 `webcollect-batch`、`webcollect-tasks`。

真实 `generate` 现要求同时提供 `--history-registry` 和 `--history-set`；后者为冻结的 `qc-cumulative-set-1` 客户包集合，必须包含本仓库 `results/delivery/LATEST.md` 指向的正式包并保持全部文件SHA。原标注中已知同业务会拒绝，未识别的同源历史比较保持待定；`execute` 在预检/采集前重新检查客户包与实时M4历史。该复查尚非跨进程原子语义锁。旧仅查询M4任务库的计划不能直接执行，实际命令及220条历史拦截证据见 `verify_results/three-program-acceleration-20261026/history-r01/commands.json` 与 `result-summary.json`。

作业账本独立于生产编号账本；不能创建空生产账本或新campaign绕过已有待审/attempt上限。`config/batch-no-model.json` 是 `mode=real, model=null` 的显式无模型配置，不需要API、费率、币种或模型金额预算；保留发现/页面/时间/并发/域间隔/租约及有界job尝试，原采集attempt和待审库存仍由原runtime控制。模型对象存在时维持严格预算和费率验证，`model:null` 无法预留或发送模型请求。合成配置仅供开发。

`generate` 默认 `--generator deterministic`，现支持购物合计、行程速度、矩形面积三种明确业务策略；未知表单保留拒绝，不臆造结果。结构签名忽略参数，同origin同策略跨路径/换控件也不能多产一条；无效范围、无变化输入和结果歧义在编号前拒绝。`review_required` 能力只产待复核提案，发布/执行门禁保留。数值断言不等于视觉、单位和业务终态已通过独立审核。显式 `--generator model` 保留旧模型路径，启用时才依赖模型配置。

当前命令、验证与边界见[S0运行记录](../prd/三程序S0运行记录-20261026.md)及[执行入口](../prd/三程序计划执行入口.md)。定向复验：`projects/code/.venv/bin/python projects/code/scripts/verify_s0.py --output <新目录>`；可用 `--components runtime tasks qc compat` 选择受影响范围，`--browser` 另启本地受控Chrome。统一无浏览器路径与各受控浏览器用例已分别实跑，组合 `--browser` 命令尚未单独运行。旧[E0–E3记录](../prd/三程序E0-E3运行记录-20261026.md)继续保留。测试/报告按既有规则留在本地。

## DeepSeek / GLM 辅助判断接口（2026-10-27）

模型配置支持显式 `provider=deepseek` 或 `provider=glm`，分别使用厂商 Chat Completions 协议。[DeepSeek配置示例](config/batch-deepseek.example.json)和[GLM配置示例](config/batch-glm.example.json)保留未填写的型号、费率和预算，不能直接发送请求。启用前一次性补齐：确切模型版本与端点、凭据环境变量、币种及有来源和版本的输入/缓存/输出费率、请求/Token/时长上限和金额控制方式，以及视觉能力和每张图片的保守Token预留。金额控制默认要求硬上限；显式只统计模式见下文。原 `model:null`、`synthetic`、`chat-completions` 配置继续沿用原表示，既有账本不能通过更改配置扩容。

新厂商配置必须显式填写 `supports_vision`、`image_tokens_per_image`、`request_overhead_tokens`。纯文本模型在图片请求预留和派发前即被拒绝；视觉模型的文本、完整Schema、系统消息、消息开销和逐张图片预留合计超限也在请求前拒绝。视觉审核仍传原PNG，不以树文字、OCR文本或拼图替代全帧证据。是否具备视觉能力应按所选版本核验，不能仅从厂商名称推断。

DeepSeek 和 GLM 文本模型使用 `max_tokens` 与 `json_object`，完整Schema写入系统指令，返回结果仍经本地JSON Schema验证。GLM视觉模型按官方限制不发送 `response_format`，同样必须返回满足本地Schema的JSON；不会在一次失败后自动换协议或换模型重发。缓存用量接受 `prompt_tokens_details.cached_tokens`，DeepSeek同时支持其 `prompt_cache_hit_tokens`；缺失、冲突或非法用量继续记为 `UNKNOWN` 并保留预留，不把未知计为0。

同一AI worker运行账仍绑定一个确切模型；文本资料判断和原图判断若选择不同模型，应使用各自冻结的配置与独立账本，不能修改旧账模型或借文本结果填满视觉审核。DeepSeek兼容验证仍为离线HTTP夹具。GLM已完成下述首条真实验证，真实总体误判率仍未校准。人工审核、正式放行与客户验收继续单独记录。

协议依据（2026-10-27核对）：[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/)、[GLM对话补全](https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E5%AF%B9%E8%AF%9D%E8%A1%A5%E5%85%A8)、[GLM-4.6V图像输入](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.6v)。厂商能力和参数仍以未来实际选用版本及小样本校准为准。

2026-10-27已按用户指定的[GLM-5.3-Flash文档](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash)实跑首站首条。该型号使用显式`image_encoding=data_url`；旧GLM不填时保留raw base64表示。可选`reasoning_effort=low/high/max`仅供GLM/DeepSeek，GLM显式启用thinking；本轮使用high。GLM完整单一JSON代码围栏可规范化解析，前后解释、多块、非法JSON或Schema错误仍拒绝，原始响应不改写，完整系统指令继续绑定缓存身份。

本轮GLM完成站点图像筛选、11原帧五语义审核、3个近邻完整轨迹比较和资料审核。9次真实请求折算费用0.200977元；单条PASS、资料分布项FAIL，整包及GLM内部批次FAIL，未正式放行。资料通用worker原先只传Markdown/CSV，本次运行脚本另提供真实站点/标注JSON、文件库存、采集普查及修订sidecar，并对最终引用施加路径/SHA成对Schema约束；这些补证均有新请求身份和原失败记录，尚未将该补证流程泛化为通用无人值守能力。实际证据在`verify_results/production-day-20261027/glm-first-run-r01/`。

## 按数据审计 AI 请求、Token 与费用（2026-10-27）

`python -m webcollect.model_audit`只读现有运行账，不读取凭据、不调用模型，也不修改生产注册表、原账或原审核结果。先冻结账本逻辑指纹，再把实际 job 与样本、精确页面或批次绑定：

```sh
PYTHONPATH=projects/code projects/code/.venv/bin/python -m webcollect.model_audit fingerprint \
  --ledger /path/to/finished-run/operations.sqlite3

PYTHONPATH=projects/code projects/code/.venv/bin/python -m webcollect.model_audit export \
  --ledger /path/to/finished-run/operations.sqlite3 \
  --attribution /path/to/attribution.json \
  --output /path/to/new-audit-directory
```

`attribution.json`使用`schema_version=webcollect-model-attribution-1`，`ledger_binding`填写指纹命令返回的`logical_sha256`和`config_sha256`，`jobs`按实际 job ID 映射，例如：

```json
{
  "schema_version": "webcollect-model-attribution-1",
  "ledger_binding": {"logical_sha256": "<实际指纹>", "config_sha256": "<实际配置指纹>"},
  "jobs": {
    "<样本视觉审核job_id>": {"scope": "sample", "scope_id": "<sample_id>", "classification": "production"},
    "<站点筛选job_id>": {
      "scope": "site", "scope_id": "<精确页面URI>", "classification": "production",
      "related_sample_ids": ["<sample_id>"],
      "allocation": {"method": "equal_weight", "sample_ids": ["<sample_id>"]}
    }
  }
}
```

`scope`支持`sample/site/batch/engineering`。只有显式提供`allocation`才把站点或批次共享费用等权分摊；`related_sample_ids`仅说明关联。分摊金额与Token按排序后的样本ID分配整数余数，合计严格守恒，并标明它们是估算分摊、不是厂商逐样本实测。未绑定的请求留在`UNATTRIBUTED`，失败/重试、修补请求和工程开销不会自动删除。可选`request_classifications`仅覆盖请求的`classification/note`，不能改金额、归属或原结论。

输出`audit.json`、`summary.json`及`requests.csv`、`sample-summary.csv`、`stages.csv`、`scopes.csv`。逐请求保留厂商请求ID、模型、阶段、时间、attempt、请求状态和job状态、输入/输出/缓存/图片/推理Token、厂商总Token、冻结费率和费用复算，以及提示、Schema、原图记录的哈希；不导出提示、响应正文、图片内容或凭据。推理Token是输出的子集，不重复计费；厂商总Token需与输入+输出核对，缺失或不一致仍UNKNOWN。图片哈希是原请求所记录的值，导出不重新检查原图字节。

异常类型采用已知类型集合；未知异常文本仅保留哈希。厂商模型/请求ID采用有界单行标识符，purpose仅显示已知阶段标签并保留原值哈希。费率来源及归属清单的scope/备注仍是显式审计声明，按其实际内容保留；导出不是对任意恶意声明文本的通用敏感信息识别器。CSV另中和公式形式的文本，JSON保留声明原值。

逐样本区分直接请求数、分摊共享请求引用数与共享请求等价量；共享引用数不可跨样本相加当作新API调用。账中已预留但未确认返回的请求保持不确定状态；现有账未单独记录本地缓存命中事件，不能据此宣称缓存节省了多少调用。图片Token未单列、缓存用量缺失、实际扣费或端到端成本缺失时如实保留`UNKNOWN`和未决预留；已知费用只是冻结费率下的估算，不是账单。费率复算不一致、绑定漂移或已有输出目录会拒绝导出。

首条实际审计在`verify_results/production-day-20261027/glm-first-run-r01/model-audit-r02/`：样本直接4次，站点共享2次，批次资料共享3次；由于本轮仅此一条，显式等权分摊后共9次、输入193708、输出16431（含推理5390）、厂商总计210139、缓存0、估算0.200977元。原始失败、资料补证和站点首次重试均保留，整体交付仍FAIL。r01导出继续保留；r02绑定异常类型脱敏收紧后的源码，原账和对账总数不变。

离线查询不需要原数据库或凭据，也不调用模型。`query`先从请求行复算费率与全部归属/阶段/共享分摊视图，拒绝不一致的导出，再输出实际费用；`--compact`提供便于查看的摘要，省略`--sample-id`可查整批：

```sh
PYTHONPATH=projects/code projects/code/.venv/bin/python -m webcollect.model_audit query \
  --audit verify_results/production-day-20261027/glm-first-run-r01/model-audit-r02/audit.json \
  --sample-id S000030_sample_000001 --compact
```

完整查询仍保留全部细节。查询只核对导出内的schema、算术与守恒，返回审计文件SHA；它不重新认证生产现场或厂商账单。单样本的共享引用不可跨样本当新调用累加，推理/缓存/图片Token均是原总量中的子集。费用应分别看直接、共享分摊、工程/未归属池及UNKNOWN预留，不把“每条分摊费用”和“全批共享费用”再相加。

2026-10-27用户明确选择“不设定上限，直接统计”。新的工程配置只有同时设置`budget.cost_control="observe_only"`和`budget.max_model_cost_micros=null`才表示不设金额硬限；缺少模式的null仍是未配置并拒绝，不会误变成无限预算。默认或显式`capped`继续要求正整数金额上限。只统计模式保留实际Token、费用、失败和UNKNOWN预留，审计显示`observe_only`及金额上限`NOT_APPLICABLE`；请求数、Token、时长、并发、图像和生产准入限制仍按冻结范围执行。旧首条账仍保持原12请求/3元配置，不能改旧配置或时钟续用。

## 可配置跨站并发与共享提交（2026-10-27）

`python -m webcollect.site_scheduler`调度已经生成并发布的M4计划，不自行发现站点、创建生产账本、增加预算或授予质检通过。[配置示例](config/site-schedule.example.json)保留占位路径，须替换为真实计划、发布收据、原活动生产账本及新输出路径后使用：

```sh
PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector \
projects/code/.venv/bin/python -m webcollect.site_scheduler \
  --config /absolute/path/to/site-schedule.json \
  --output /absolute/path/to/new-schedule-evidence
```

配置的`sites`按稳定的`site_key`分组，每组`batches`依次执行；同一应用的不同URI应放在同一组。不同站点可并行运行，每条轨迹使用独立浏览器上下文，各批使用独立输出目录。`max_parallel_sites`指定全局站点并发上限；当前每站只有一个执行worker，因此它必须与共享policy的`max_workers`相等，配置不一致在派发前拒绝，不能悄悄退成串行。全部站点必须共享完整一致的campaign policy及同一个原生产账本；修改并发限额需先在原campaign记录明确的policy调整原因，不能换账本或目录重置尝试及待审预算。

同域和子域继续共享`max_domain_workers`、域间隔及原子编号/尝试/配额约束，不因URI不同获得额外并发额度。待审积压、尝试上限和资源检查会阻止继续派发。`max_schedule_seconds`限定本次调度的总运行时间；取消或超时关闭当前浏览器工作并保留已启动失败、半轨迹和编号，不能将半条轨迹拼成成功。

生产端新增共享精确图片索引：历史原图重新计算SHA登记，正在采集或已失败的目录不作为已接纳历史。精确截图声明与`collected_pending_review`在同一SQLite事务提交，两个并发样本命中同图时最多接纳一个；浏览器执行期间不持有全局串行锁。运行边界重新核对图片及登记状态，检测文件漂移。该保护只覆盖生产端精确截图路线，客户目录仍须执行完整四路去重和最终QC。

调度证据保留冻结配置、输入文件SHA、采集及调度实现SHA、追加事件和每次运行独立报告。续跑显式增加`--resume`，输入或代码漂移时拒绝沿用旧范围；已提交且证据完整的成功任务不会重采，中断重试使用新编号。报告中的`COLLECTED_PENDING_REVIEW`只表示计划样本已保存，`qualified_samples`保持0，最终合格及交付状态由独立QC和发布流程决定。

新`observed_workflow`准入任务并发时，调度器先逐条验证独立准入及共同冻结历史，再在原账本中一次性预留整个cohort的scope、计划、发布收据、任务全文和参数无关语义/结构签名。预留不会提前写入`m4_tasks`或分配站点、批次、样本编号。运行中只允许精确绑定在该cohort中的peer新增历史行；批次外新增任务、peer全文/范围改变、原历史缺失及冻结调度证据漂移都会停止。入队、领取编号、开始、心跳和成功提交都在各自短事务内复查，不把浏览器执行串行化。失败和取消不会自动释放预留，换scope不能重用其语义；原范围可显式续跑。旧任务独立调度保持原路，新workflow与旧任务/普通form混合调度暂时明确拒绝。`admission-cohort.json`中的`ENGINEERING_SIGNATURE_GUARDS_ONLY`只代表工程签名保护，不能计作peer间AI语义比较；独立QC仍比较本批和全部累计数据。

客户历史完整文件SHA校验在入队、领取、开始和成功提交的SQLite写事务之前进行；内容身份由完整历史上下文及校验前后文件元数据绑定，写事务只复核小型manifest/正式入口引用、文件身份和精确队列关系。心跳不重复读取全部客户图片SHA。校验后文件变动使本次proof失效；没有仅按时间复用的缓存。该校验仍有实际I/O成本，受控测试不证明大客户历史目录上的吞吐。

本实现已用受控双站及两个调度实例验证并发上限、同域限制、独立上下文、同图竞争、积压反压、取消和恢复；这些测试不代表真实站点吞吐或多机长期稳定性。生产并发数须根据实际任务、质检积压、资源和访问限制测量选择。
