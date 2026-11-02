# WebCollect 独立质检器

独立 QC 的模型账持续记录请求、token、费用和未决结果。默认处理完收据绑定的可执行作业。[额度限制清单](../../docs/额度限制清单与取消说明-20261101.md)

V2 消费者通过启动范围中的 `qc_policy` 冻结本次 `execution/qc-inputs/` 下的收据、采样计划、有效集合和收集检查。独立 QC 可以据此将同一样本送入逐帧视觉与差异检查队列。入队时仍为 `QC_NOT_RUN`，实际 AI、人工审核与发布各自计数。[启动与交接说明](../../docs/工程说明.md#本机有界批次启动) · [离线同一样本交接记录](../../verify_results/producer-consumer-react-qc-offline-20261101-094824-1251/联测报告.md)

`delivery_pipeline prepare --production-handoff /absolute/qc-inputs/receipt.json` 可绑定原当前链采集交接；run/status生成独立报告后核对原件与样本集合，自动登记待审/审核通过/失败并同步已绑定共享池。`single_record.qc` 自动传递该收据，已保存结果恢复只回写、不重审。受控模式不能绑定生产回写；真人、发布和客户验收仍独立记录。见[状态回写与防重](../../docs/共享站点池与自主发现.md#状态回写与防重)。

2026-10-29一致性修复为累计集合profile增加显式 `release.kind/version`。`formal` 要求200000有效样本、20包每包10000、总体分布执行且无重复/被替代副本；`experiment` 仅声明局部实验范围。旧profile的局部PASS不补签正式发行。审核复用和当前链门禁继续独立执行，见[有限修复计划](../../docs/需求一致性修复计划-20261028.md)。

当前源码导航：[工程说明](../../docs/工程说明.md)、[设计说明](../../docs/设计说明.md)、[agent 接手说明](../../AGENTS.md)。`34afaaa` 新增当前链 QC 交接、逐项语义审核复用及所有封包入口的有效集合/跨包绑定。下文含历史批次和兼容流程，最新参数以新说明及 CLI `--help` 为准。

当前执行范围为2026-10-28的 `current-chain-r01` 全新链路。统一入口为[真实试点执行说明](../prd/真实试点执行说明-20261028.md)，变更、进展与清理结果见[工程状态与清理记录](../prd/工程状态与清理记录-20261028.md)，实时事实以[本轮进度账](../../verify_results/pilot1000-20261028-r01/progress.json)及其原始账本为准。审核、去重、验收和产量仅使用绑定本轮manifest及专库的结果；旧运行、资格PASS和工程测试均不计本轮合格量。网站按整体应用管理，每个实际任务页面最多一条、5–10个必要操作，整站累计三次真实失败即停止。

Git仅提交有效源码、纯测试及当前工程/需求说明。样本、原图、过程报告、原始模型请求、账本、凭据和ZIP留在本地；历史原件及失败/费用证据保留，清理记录不改变其结论。下文旧批次实测和命令属于对应范围的兼容说明，执行本轮时以当前入口为准。

2026-10-28认证恢复：新增独立`python -m quality_inspector.document_auth_recovery`，只为已持久记录的资料HTTP401/provider1000提供一次明确有界的恢复增量，不改原请求、UNKNOWN费用、原预算和冻结源码。`prepare`需要绑定原资料receipt/原request ID的单次授权JSON及独立同模型/同一请求预算配置；只生成control receipt，不生成可直接派发的资料receipt。`run`还必须接收`--auth-proof`：`webcollect-model-authentication-evidence-1`的`ledger`、`config:{path,sha256}`、`request_id`，程序从原SQLite重核同服务、同模型的一次真实成功认证诊断及其原响应/usage，不能用手写PASS或凭据重发声明替代。凭据是否改变不作推定，仍401时不能重发完整资料。

该入口的`prepare --original-receipt ... --authorization ... --config ... --ledger ... --initialize-ledger --output ...`、`run --receipt ... --auth-proof ... --output ...`、`status --receipt ... --output ...`和`finalize --receipt ... --status ... --output ... [--archive ...]`复用原资料run/status/finalizer。相同失败request只有一个恢复scope；复制原receipt、换输出/ledger/授权文本不能增加请求。prepare中断可在原scope完成；已激活但尚未派发时可追加新的成功诊断证据，保留旧证据，仍只允许一次资料请求。请求已持久成功而job写入中断时，过期租约后的`run/status`可严格重验原响应/usage/资料引用并恢复结果，不发新请求、不重置尝试数；活租约不抢占。新输出的`recovery-accounting.json`分别列原pipeline、原401资料请求、恢复请求及认证诊断账本，UNKNOWN预留始终保留，实际扣费仍为UNKNOWN。资料人工始终0，原样本人审和正式分布门禁继续核验；底层原件改变会阻止后续状态/封包。

2026-10-28资料政策更新：新流程使用`python -m quality_inspector.document_text_qc`。资料按完整文本做工程对比与专用AI核对，资料AI比例100%、资料人工比例0%；样本仍执行原冻结计划中的AI/人工比例、AI失败转人工、真人失败重采替换及复检。资料FAIL进入`REVISE_DOCUMENTS_REQUIRED`，缺证/未知进入`AI_REVIEW_REQUIRED`，均不得自动通过或生成真人审核记录。新lane的`human_document_pending_count`恒0。

已有receipt通过`prepare --parent-receipt ... --parent-status ...`接续，旧receipt、旧软件哈希、原模型jobs/费用、原AI FAIL与真人历史全部保留。父status必须为原账实际发行、仍匹配当前真人历史且能按现有工程重算；手写status不能作为事实。新ledger必须单独有界、与父账追加的policy-amendment关联，不能重置父账预算。相同文本/事实/政策/模型在换输出目录或刷新父status后复用同一job；换ledger重复派费会被拒绝。未知请求留原账，不自动重试。

资料完整输入包含全部交付MD/CSV及非UI-tree的JSON、完整文件SHA清单、原始运行资料、已完成样本QC、原AI记录、真人原导出与冻结抽检计划。图片/UI树仅按路径、SHA、字节数列册；专用资料AI不重新裁决样本视觉或任务语义。README明确结构化统计先与实际包、annotation和format检查实算比对，矛盾会在模型派费前拦截。原始提示词中的规划示例不作为实际统计。包内历史导出stub与包外后续QC分阶段核对，不要求回写原包或形成资料审核自引用。

新生产入口先执行`run-samples`，只派发旧receipt中的visual/difference，不派发旧documents job，并追加superseded事件保留该旧job及已产生费用。随后创建新有界资料scope，顺序运行：

```sh
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.document_text_qc run-samples \
  --parent-receipt /path/to/pipeline-receipt.json --output /path/to/new-sample-qc
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.document_text_qc prepare \
  --parent-receipt /path/to/pipeline-receipt.json --parent-status /path/to/new-sample-qc/status.json \
  --config /path/to/bounded-document-config.json --ledger /path/to/document-scope.sqlite3 \
  --initialize-ledger --supporting-file /path/to/actual-facts.json --output /path/to/new-document-prepare
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.document_text_qc run \
  --receipt /path/to/new-document-prepare/document-text-receipt.json --output /path/to/new-document-qc
```

已完成旧visual/difference及真人审核的批次直接从`prepare`接续；旧documents已完成的结果与费用保留为历史，不覆盖。`status`只重算报告不派发模型。`text_consistency`与`formal_blockers`分别报告：如实说明单站类目100%可以文本一致，但原类目≤20%门禁仍FAIL，正式放行仍为false。新`finalize --receipt ... --status ... --output ... [--archive ...]`先验证新lane发行记录，再交由未改动的原finalizer重新检查全部资料、样本、分布、当前真人历史、文件哈希和最终包；离线正例可封包，类目超限反例不能封包。受控/模拟协议测试不证明真实模型审核或生产交付。

2026-10-26新增独立订阅适配入口`python -m quality_inspector.codex_subscription preflight/run`，使用现有ChatGPT登录、完整原帧和既有审核schema，独立持久请求账限制1次exec及最长120秒，未知结果不自动重试，禁止API回退。它尚未接通现有批量worker：25项离线定向测试通过，但首次真实冒烟因CLI内置provider配置覆盖被拒，修复后未补发，真实传输与usage仍未验证。单包视觉结果强制保留实质差异待定；受控传输输出不能导入为正式审核。结果见`verify_results/three-program-acceleration-20261026/subscription-r01/result-summary.json`，不要直接对生产批量调用。

依据需求书、附件A/B及已确认的澄清，直接读取程序已经导出的完整客户文件，检查目录、字段、动作与图树、分布和四路重复。实际像素与任务语义接受绑定当前交付文件的AI或真人审核，来源类型保持原样；未检查不推定通过。

## 在仓库中运行

使用采集工程的Python环境安装质检依赖：

```sh
projects/code/.venv/bin/python -m pip install -r projects/quality-inspector/requirements.txt
projects/code/.venv/bin/python projects/quality-inspector/qc.py --help
```

默认入口只需交付目录和报告目录，不读取旧采集目录、raw、历史审核导出或客户参考样例。合同schema、动作空间及附件原件哈希随程序安装；`delivery.json`默认不设试点最小样本数，仍考核类目≤20%、视口≤3种、短流程≤2%。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --input /path/to/customer-batch --output verify_results/new-final-qc
```

本次固定18条且类目只统计的用户例外单独保存在`config/delivery-approved18-20261024.json`；必须显式传`--profile`，不会改变全局默认。先检查不可变payload，再附入正式摘要并最终封包：

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --input /path/to/customer-export --stage payload \
  --profile projects/quality-inspector/config/delivery-approved18-20261024.json \
  --reviews /path/to/actual-current-ai-or-human-review.json \
  --output verify_results/new-payload-qc
```

`payload`允许尚未附入最终摘要的qc_report正文，但仍核对该文件存在和全部其他交付内容；`delivery_status=PASS`不等于可发布，`release_ready`仍为false。正式finalize附入摘要后，使用默认`--stage final`检查新包；最终报告核对17项、完整payload哈希、真实审核类型与覆盖、分布、四路候选数、源总体及排除原因，全部通过后`release_ready=true`。最终QC只读，报告始终存包外。

`payload_files_sha256`覆盖除根`qc_report.md`和`SHA256SUMS`之外的全部文件；`payload_sha256`是此字典按UTF-8、ensure_ascii=False、sort_keys=True及紧凑JSON序列化后的SHA256。最终SHA256SUMS包含qc_report，排除自身。如此不会产生报告自引用，也不能遗漏样本或说明文件。

`review-template.json`中的`baseline_sha256`现在绑定内置合同摘要，可从`report.baseline.config_sha256`取得。只有实际看过交付图像的审核者才能填写；部分旧AI字段证据不视为整条轨迹已审核。

delivery模式还要求同一`--reviews`文件顶层的`delivery_document_review`实际资料审核。生成的空模板包含`qc-delivery-document-review-1`结构，绑定内置合同、profile与完整`payload_files_sha256`。五项为交付文件与字段、来源与合规、分布及站点归属、淘汰总体与来源记录、真实审核覆盖与结论。每项明确判断须有具体`note`和非空`evidence`（包内payload相对`path`、对应`sha256`、实际阅读的`detail`），并注明真实AI/真人身份及来源。缺审核保持REVIEW_REQUIRED，错误绑定或不完整的通过记录为FAIL，均进入整批门禁；样本全PASS不能代替资料审核。旧`package_review`仍仅按原pilot规则使用，不能替代这五项。新 delivery 审核台使用这五项资料表单，导出时保留包内路径和 SHA；旧 pilot 的两项资料表单不能替代这五项。

资料审核绑定排除根`qc_report.md`与`SHA256SUMS`，同一实际记录可用于payload与final及完整隔离副本；最终报告17项、分布、覆盖、去重与来源统计仍由final独立核对。其他任何资料或样本变化都会使旧资料审核失效。程序只能核验声明及证据绑定，不能代替实际阅读或认证审核人身份。

正式`qc_report.md`还须在`review_coverage.reviewer_sources`列明实际审核者`kind/name/samples`，仅计五项结论均明确且为同一有效身份的样本；摘要的`delivery_document_review`须完整保留实际资料审核身份、来源和五项证据结论。final从导入记录独立重算并比对，计数相同而改写审核者名称、资料结论或证据仍会失败。

需求§6的任务标题格式通过C12单独核对：`task_instruction`中位于「」引用深度之外的《作品名》拒收，题名应使用「作品名」。已有「整段原文《法规名》」内的书名号保留；客户实际样例使用书名号的一般步骤叙述，以及须严格匹配同步树原文的`target_text`，不套用这个任务字段专门规则。该机械门禁不会推断所有专有名词或代替文字语义审核。

200条、10站点的新采集批次使用独立配置`config/delivery-200-10sites-20261024.json`。它要求恰好200条和10个实际交付站点身份，类目上限20%照常考核，不继承旧18条豁免。站点身份仍须通过metadata与包内URI/类目/样本归属对账；每站条数按真实分布统计，不强制把同一任务改关键词复制20次。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --input /path/to/new200-export --stage payload \
  --profile projects/quality-inspector/config/delivery-200-10sites-20261024.json \
  --reviews /path/to/actual-new200-review.json --output verify_results/new200-payload-qc
```

200条执行19,900对四路比较。任一路命中均失败，共用同一静态首页截图也不例外；不修改阈值、不自动删样本。大重复图仅给移除诊断的上下界及建议，不穷举200个顶点的最小集合，不宣称算得精确最优，也不应用建议。每条至少5个显式操作，wait/complete不计；200条最多4条短流程。批次至少需要5个真实类目才能满足20%上限，不能靠拆标签降低比例。

真实新采集还须由生产过程及真实来源声明支持；只读QC不会凭字段完整就认证实际访问过网站。新200条的语言、遮挡/可读性、图树与动作连续性、终态、隐私及任务实质差异必须针对新交付文件做实际审核，记录AI/真人身份和每条hash；旧18条审核不能复制到新样本。无实际语义记录仍为REVIEW_REQUIRED。生产自检、AI检查、人工抽检、客户验收分别计数；客户验收方式中的2%随机人工抽检在200条中对应4条，未运行时客户验收保持UNKNOWN。生产自检若另有人工抽查，比例和结论按实际记录，AI审核不能计入人工覆盖。

旧试点保持兼容，须显式使用pilot配置和参考baseline：

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --baseline projects/quality-inspector/config/customer-samples.json \
  --profile projects/quality-inspector/config/local-pilot-v1.json \
  --input /path/to/customer-batch \
  --evidence /path/to/outside-customer-batch/evidence.json \
  --output verify_results/new-qc
```

检查报告必须位于输入包之外，使用新的输出目录。主要输出为`report.json`、`报告.md`、`review.html`及`review-template.json`，同时保存实际采用的规则与配置身份。

当前客户格式为根目录` samples/<sample_id>/{annotation.json, images/, ui_tree/}`，不要求内部批次包、采集manifest或raw日志混入客户目录。根`metadata.csv`、附件、合成说明、来源说明、`site-list.json`和样本外`ground_truth/<sample_id>.json`直接作为实际输入核查。旧`<batch>/samples/`格式仍兼容；两种格式混用、漏标注的样本目录、多余空目录或文件不能被静默跳过。

流程固定为“采集工作区 → 采集程序`package`导出客户文件 → 本质检器`check --input 客户目录`”。目录树、字段与动作的检查目标始终是客户文件，不能只检查另一份内部副本后宣告交付格式通过。

delivery模式的`--baseline`和`--evidence`仅启用`engineering_audit`，诊断结果不进入交付结论；缺失旧文件也不造成合同待审。显式pilot模式仍保留原来的原样例、捕获manifest/raw哈希和预处理审计规则。工程审计不能替代对交付内容的独立检查。

## 结果含义

- `PASS`：对应范围的实际检查和必要审核已通过。
- `FAIL`：有明确缺陷、绑定冲突或超过规则限制。
- `REVIEW_REQUIRED`：缺少审核、证据不足或仍待裁决。

命令退出码依据`local_acceptance_status`：PASS为0、FAIL为1、待审为2；执行错误为3。delivery的`status/contract_status/delivery_status`只汇总已检查的样本和批次，pilot标记NOT_APPLICABLE；客户及全集验收保持独立UNKNOWN。显式pilot保留历史作用域与汇总行为。

本地试点配置要求至少20条、10站，单类不超过20%，视口规格不超过3种，短流程不超过2%。四路为截图SHA、完整动作序列哈希、首末帧dHash和任务SimHash；算法和阈值固定在profile。命中候选不能通过语义备注直接豁免。URI与站点编号及类目还须和实际来源对账，不能通过拆标签降低类目占比。

## 真实审核与重新检查

本机浏览器打开报告目录中的`review.html`，进入“人工审核台”。单人身份由页面配置，无需每次填写姓名或选择人工来源。上方保留任务目标及完成标准；逐步对照动作前后截图，点击图片放大，按需打开同步树和工具参数。目标红框与触点只辅助定位，不代替实际看图。

每步选择“这一步正确，继续”“发现问题”或“看不清 / 不确定”；正确时直接保存并继续，无需填写额外信息；问题和不确定项写一句具体说明。看完后回答五个中文问题：

| 记录字段 | 页面问题 |
|---|---|
| `visual_alignment` | 图、控件和动作是否对应？ |
| `terminal_semantics` | 最后真的完成任务了吗？ |
| `language` | 控件语言是否与页面一致，叙述是否为简体中文、控件引用是否保留原文？技术名词可保留英文，不按中文字符比例拒收。 |
| `privacy` | 是否符合来源和隐私要求？ |
| `substantive_difference` | 与其他任务有实质区别吗？ |

“符合”“有问题”“不确定 / 待核对”分别映射`PASS/FAIL/REVIEW_REQUIRED`。真人明确选择“符合”即可，无需填写原因，也不自动生成理由；问题项须定位实际证据。打开图片、程序已有AI PASS及导出成功都不会替本人给出结论；未完成项保持待审。导出发起下载后，应在浏览器下载列表确认文件；生成下载失败会显示错误，并保留当前判断。

逐步判断、答案、备注和位置自动保存在当前浏览器，保存状态显示在右上角。导出的`qc-human-review-<时间>.json`同时是备份，“恢复备份”可校验同包、同单人配置及图树/标注身份后续审。换浏览器、清理网站数据或自动保存失败前请导出；AI或旧版本记录不能改名套成人工。

左下角“最后核对交付资料”打开独立页面，提供包内文档链接。delivery 模式要求上述五项资料判断；兼容 pilot 保留文档完整性、站点类目归属两项。实际读完资料后在页面回答；仅打开链接不能视作通过，资料未完成仍保留待审。详见[人工核验SOP](../prd/M2-人工核验SOP.md)。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --baseline projects/quality-inspector/config/customer-samples.json \
  --profile projects/quality-inspector/config/local-pilot-v1.json \
  --input /path/to/customer-batch \
  --evidence /path/to/outside-customer-batch/evidence.json \
  --reviews /path/to/qc-human-review.json \
  --output verify_results/new-qc-with-review
```

delivery 新审核使用 `qc-review-2`，兼容 pilot 保留 `qc-review-1`/`qc-package-review-1`。导入检查审核来源、逐帧观察、五项结论、annotation/evidence SHA及包内文件清单；旧 delivery 记录须按下述显式迁移规则处理。候选或资料变更后旧记录不能自动沿用。页面进度不是合格数，AI导入数不等于人工审核数；本次界面更新未签署实际人工记录，候选与既有报告结论不变。

### 首轮真人盲审

需要独立初判时，使用单独的 `review --blind` 入口。普通 `check` 生成的审核页包含程序检查详情及包内资料，不能直接当作盲审。先冻结实际客户候选和当前delivery报告，再依据真实采集事实准备仅含 `source_statement`、`input_statement` 两个非空字符串的JSON；它们向审核者说明中性来源及测试输入，不放入AI判断、拒收或修订史。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py review \
  --report /path/to/current-delivery-qc/report.json \
  --blind --context /path/to/neutral-source-input.json \
  --output /path/to/new-blind-workspace \
  --receipt /path/to/outside-workspace/blind-receipt.json \
  --reviewer hemiao
```

该目录只包含审核页面、空白 `qc-review-2` 模板及白名单内的原始标注/截图/同步树副本。复制前后逐文件SHA必须一致，源码包、报告和旧审核不改写。报告结论、包内文档、旧记录及统计不会嵌入页面；操作收据保存在目录之外。额外未知字段会阻止盲审副本生成，需要明确审查展示范围；这属于盲审隔离规则，不改变客户合同是否允许额外字段。

目录内资源使用相对路径，可本地打开或仅把这个目录作为本机HTTP服务根目录。不要将整个项目、QC报告目录或交付包作为盲审服务根目录。每份盲审以证据、审核者和中性说明形成独立草稿空间，只能恢复同一盲审入口的备份；普通审核、AI记录或带资料结论的备份不能导入。

真人逐帧明确选择“正常”后直接保存并继续，无需填写依据；导出保留decision=ok，允许note为空，不自动编写事实。逐步选择“有问题”或“不确定”时仍需说明；AI逐帧观察仍要求非空。五项轨迹结论及资料结论选择“符合”也无需原因；选择“有问题”须写明原因，“待核对”可保留未决。保存、导出、恢复和QC导入均允许真人PASS的note为空字符串，AI的PASS/FAIL仍须非空理由。可以导出未完成备份，但只有完整、绑定正确的实际记录才能进入后续QC。原始初判导出并冻结SHA后，再展示AI结论、核对同版本分歧并安排资料审核。盲审页面不代替资料审核，也不认证身份或证明实际看图。

## 核心模块

2026-10-26用户将规则扩展为所有 `hotkey` 统一Windows表达：例如粘贴参数 `["ctrl","v"]`、文本ctrl+v、显示Ctrl+V；Enter、Tab、Home等单键也统一名称。独立QC逐项校验键名、修饰键顺序、连接文本及显示名称，并依据source_os核对真实按键到Windows的明确映射；Windows Meta表示Win，不当成Ctrl。无明确定义的Mac Command/Option组合拒绝交付，其他动作及额外参数仍须严格一致。历史文件生成新版后检查，旧审核及原始证据保留；完整词表和映射见[需求澄清](../../request/需求澄清记录.md)。

C12另依据附件A的`step_result`实际观察要求，拦截已确认的待审核占位、纯执行回执泛句及重复数字导航噪声。正常界面状态、具体数值和原文引用不因此被判错。此门禁不证明目标事实、步骤必要性和全文语义都已通过，仍需对照截图审核；修改后的标注不能自动沿用旧审核哈希。

`engine.py`编排规则、作用域及审核绑定；`format_checks.py`独立解析格式；`checksums.py`核对完整文件清单；`duplicates.py`保留四路参数与候选；`profiles.py`计算本地验收；`preparation_evidence.py`审计正文准备的真实前后帧与动作；`reporting.py`生成报告和离线审核页。

正文准备审计核对初始完整截图、图/树/raw哈希、判断与实际动作、准备预算和失败记录。机械通过仍须逐图核对；失败尝试、历史兼容状态和未知边界分别保留。

`layout.py`统一发现客户平铺目录和历史多批目录；`external_evidence.py`处理包外捕获证据绑定。字段、去重、作用域和审核台均使用实际客户文件路径。

历史`package`兼容入口保留内部候选组包；常规客户导出使用采集工程`python -m webcollect package`。组包不执行网站采集，也不宣告验收通过。纯测试可纳入源码Git；样本、原始模型请求、账本、ZIP及详细验证过程留在本地。


## M4 累计集合与审核版本边界（0.5.0）

正式 5,000 条质量批次在原累计清单上增加 `set-manifest --quality-batch-ids <本批ID数组.json>`，随后照常运行 `check-set`。程序按绑定的本批 ID 和全部有效历史分别核验短流程、四路重复、站点类目和视口。报告的 `statistics.quality_batch` 列出本批数量、近重复受影响的当前样本以及任务类型、动作和步数分布。精确帧和全动作序列要求零命中，近重复分母是当前 5,000 条，一条样本命中多个历史邻居只算一次。该质量批次独立于物理交付分包。

小规模试跑使用 `python -m quality_inspector.ai_worker prepare --trial-sample <sample_id> --effective-set <试跑清单>`，另按 `--help` 提供配置、原账、数据和输出目录。可重复传 `--trial-sample`。试跑队列和审核件与正式用途分开，report 逐条区分实审结果、机械阻断和待审，小样本比例用于诊断。正式流水线继续要求有效的跨包报告和绑定的审核证据。

`contract.py` 的 `webcollect-delivery-contract-2` 指纹包含需求书、澄清记录、附件 A/B 四份安装原文及 SHA，字段和动作规则、五类审核与逐帧策略、参与判定的代码 SHA。安装资源在 `quality_inspector/authority/`，运行不依赖仓库内历史目录。规则变化会产生新指纹，不能把旧审核的 `baseline_sha256` 改写后当作新审核。

新 `qc-review-2` 的明确结论要求：五类检查齐全；`provenance.frames_viewed` 和 `step_observations` 对实际步骤恰好覆盖一次；每步有实际判断，真人明确选择ok时允许空备注，其他逐步观察仍须非空；各项 PASS/FAIL 的 `evidence_steps` 引用有效步骤。真人PASS无需书面原因，FAIL及AI明确结论仍须理由。可选逐步文件引用还要属于该步且 SHA 相符，真人资料PASS允许空note/detail但仍须有效文件引用。缺帧、重复代替缺帧、陈旧证据和缺失结论均不可发布。这是内部证据记录协议，不新增客户要求的审核文件格式；也无法认证填写者身份或证明其实际看过图像。

旧审核兼容采用独立迁移文件：

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py migration-plan \
  --input /path/to/unchanged-customer-package \
  --source-reviews /path/to/immutable-old-review.json \
  --output /path/to/new-outside-package/migration-pending.json
```

命令只生成 `REVIEW_REQUIRED` 评估模板。字段/图像/同步树全部未变只是可迁移资格事实；必须另有实际规则影响评估，明确原记录 SHA、原规则 SHA、当前规则 SHA、原审核文件 SHA、评估来源和理由，才能把该条标为 `inherit_unchanged`。导入仍保留原 AI/真人身份、原判断、原指纹和完整逐帧观察，不创造新看图量。任何标注或图树改变均不能用此机制继承。五类语义规则不足以直接继承或缺少全帧观察时须真实复核。资料审核绑定合同/profile/完整 payload，本次机制只迁移样本记录，旧资料结论不能自动迁移；正式 qc_report 的旧规则指纹也不能伪装成新检查。

完成真实评估后才可在 `check` 加 `--review-migration /path/to/assessment.json`；原文件必须原封不动通过 `--reviews` 传入。缺迁移评估、待审评估或陈旧绑定导致 FAIL/待审，`release_ready=false`。系统不自动签署这些评估。

累计集合显式列出每个生效版本的客户目录，避免把原样本与修订副本同时计入：

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py set-manifest \
  --input /path/to/old200 --input /path/to/new-wave \
  --output /path/to/new-qc/set.json
projects/code/.venv/bin/python projects/quality-inspector/qc.py check-set \
  --manifest /path/to/new-qc/set.json \
  --profile /path/to/explicit-cumulative-count-profile.json \
  --cache /path/to/new-qc/fingerprints.json --verify-exhaustive \
  --output /path/to/new-qc/cumulative-result
```

`set-manifest` 只冻结全部实际文件 SHA，不批准样本。`check-set` 在检查前后核对清单；检查全局样本 ID、metadata 一一覆盖（同总数但重复替代仍失败）、站点/URI/类目一致性、累计类目/视口/短流程及四路去重。API 为 `build_set_manifest(package_paths)` 与 `inspect_set(manifest, profile, cache=None, verify_exhaustive=False)`。输入集合和 profile 不修改；新报告、缓存必须位于输入包之外。内部候选目录不完整时应先导出可检查的客户目录。

截图 SHA 倒排和完整序列索引保留精确命中；Hamming 半径 r 采用 r+1 个互不重叠 bit 分块，保证阈值内候选不漏召回，再精算距离。`--verify-exhaustive` 另从实际图像重算指纹，并与全部 n(n−1)/2 对的朴素穷举比较；差异或缓存事实不一致均 FAIL。缓存键绑定实际 annotation、全部截图 SHA、算法代码及 Pillow 版本。`pair_comparisons` 表示完整逻辑比较域，真实索引候选量另列。该优化不证明本地 dHash/SimHash 等价于客户算法，外部结果仍 UNKNOWN。

`check-set` 的机械 PASS 退出码为 0，但 **始终 `release_ready=false`、语义/资料审核 NOT_EVALUATED、客户验收 UNKNOWN**。最终统一客户目录仍必须执行带真实审核的 `check --stage final`。`config/delivery-m4-1000-20261025.json` 的累计目标为 1000 条；其中 20 URI、任务族、非滚动占比、各波和真人抽样属于 `internal_targets` 信息，不进入客户合同硬门槛。中间波须使用明确累计样本数的 profile，不能用 1000 配置的 FAIL 假称当前波通过。内部 G4/G5、真人首 20 及后续抽样、客户 2% 验收都由执行规划分别管理，任何本地 PASS 不等于 M4 完成或客户验收。

2026-10-26按用户要求调整正常步骤的真人输入格式（whole-trajectory-review-3）。现有盲审入口只更新界面模板，嵌入证据、原baseline与data_id保持不变，已存草稿按同一键恢复。reviews.py变化使后续QC实现指纹改变；原版导出通过已有显式审核迁移机制接入新版，需核对原记录/图树与规则影响，不覆盖原记录。此改动不改变样本合同标准、不增加真人审核量。

同日按用户补充要求，`whole-trajectory-review-4`进一步允许真人“符合”结论不填原因，覆盖保存、完成计数、导出、恢复及后端样本/资料校验；不预填任何通过理由。原有文字、判断和证据绑定保留，当前盲审data_id及原baseline不改写。原版导出接入新版QC仍须已有显式迁移流程。此调整不替用户提交草稿，也不增加已完成人审数量。

## 独立批量AI worker（2026-10-26）

`projects/code/.venv/bin/python projects/quality-inspector/ai_worker.py --help` 提供 `prepare/run/documents/report`。使用共享的独立作业/预算账，先从实际客户目录及显式有效累计集合执行机械/占位/四路重复拦截，再创建全帧视觉、近邻实质差异和资料任务。分段有相邻重叠，原图不缩为拼图；遗漏观察或无依据不能PASS，超时未知费用保留预留并转待定。

视觉缓存绑定全部图树/文字、模型/提示/协议/合同；近邻比较独立绑定比较版本，资料独立绑定实际payload。真实结果导出沿用`qc-review-2`并交给原`engine.inspect`；合成结果使用不兼容schema及synthetic身份，不作为AI或真人放行。worker只读取客户证据，不读生产者自评或旧AI结论，不写现有真人台。

仓库启动器自动引用`projects/code`；安装CLI `webcollect-ai-qc`时同时安装webcollect（可用本地`ai` extra）。真实凭据/试验金额/费率未配置，真实正反例检出率与usage尚未验证。具体命令和证据见[三程序运行记录](../prd/三程序E0-E3运行记录-20261026.md)。

2026-10-27新增DeepSeek/GLM厂商协议适配，字段、未配置模板及用量边界见[采集程序接入说明](../code/README.md#deepseek--glm-辅助判断接口2026-10-27)。`ai-visual`与近邻原图比较必须使用已明确配置视觉能力的模型；纯文本模型可承担资料/文本辅助判断，不能代替原图审核。同一worker账只绑定一个模型，使用不同模型时分别冻结配置和账本。GLM视觉请求省略其不支持的`response_format`，输出仍须通过本地Schema和证据绑定；接口兼容的离线通过不增加真实AI审核数。

日期视觉验收器的`vision_ocr.swift`已纳入安装包资源。对保留原帧运行安装包时，原固定0.9置信度门槛继续生效；安装可用不表示日期限定验收器已完成真实校准或可自动PASS。

同日GLM首条真实运行已完成：模型`glm-5.3-flash`对`S000030_sample_000001`全部11原帧及3个历史近邻作真实判断，五语义PASS，资料4PASS/分布项FAIL。最终导入引用均匹配实际payload，单条PASS；整包仍FAIL。独立会话复核的资料分布项PASS与GLM的FAIL并存于`cross-review-comparison.json`，保守保留整包FAIL，不用一个来源覆盖另一个。首次资料输入不足及后续引用到非payload绑定的QC存根被拒收也保留；补证及白名单Schema由本次`run_phase.py`明确实现，后续通用worker仍应完善实际JSON/来源证明输入与引用约束。真实运行不增加人工审核数。

2026-10-27后续工程已将上述文档补证机制加入通用worker，资料提示版本为`independent-documentary-full-payload-2`：完整传入实际MD/CSV及文档JSON（站点、标注、ground truth等），原图和UI树只列路径/SHA/字节库存，不能据此宣称看图通过。`qc_report.md`、`SHA256SUMS`作为当前导出状态旁证，排除出可签署引用；共享`$defs/$ref`仅允许真实payload路径与SHA配对，五项原判据和类目门槛不变。

实际facts、采集manifest和修订sidecar须显式提供，完整内容与SHA进入job身份；缺失的普查、人工判断或客户验收不猜测、不补成0。命令模板如下：

```sh
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python \
  projects/quality-inspector/ai_worker.py documents \
  --config <本次冻结模型配置> --ledger <本次独立工程账> \
  --input <实际客户候选> --profile projects/quality-inspector/quality_inspector/delivery.json \
  --output <包外新目录> \
  --supporting-file <实际facts.json> \
  --supporting-file <实际采集manifest.json> \
  --supporting-file <实际修订sidecar.json>
```

没有某项真实支持文件时省略该参数，不能编造文件或指向不相关批次。材料及支持文件在准备、派发前和返回后复核哈希。完整输入超单文件字节或模型输入预留时，在API前拒绝；不截断材料、不自动分片或称部分内容为整批审核。正常文档job最多发1次请求；模型无效响应保留待定，不自动补发。旧文档job不因本次代码更新获得更完整的证据，须以新材料身份重新准备。此工程验证不增加真实AI、人审或合格产量，实际节费仍待有界实测。

### 三近邻完整原帧合并实验（2026-10-27）

独立`quality_inspector.difference_batch`用于成本对照，未改正式`ai_worker.do_difference`。相同本条11帧与三个邻居8/6/11帧共36张原PNG全部发送，本条不再在三个请求里重复；原图、图树和标注逐文件SHA绑定，每对有独立身份、完整step覆盖及必要证据。超限停止，不缩图、不删帧或少比较对象。输入文字复用原worker的精简动作/结果/目标树上下文，不声称传输了全部UI树JSON。

实验v1未明确定义状态极性，真实回执理由均说有实质差异却返回三个FAIL；原回执及0.051042元费用保留。v2明确PASS=实质不同、FAIL=同业务/仅参数变体、REVIEW_REQUIRED=不确定，并用独立关系枚举与状态的Schema配对拒绝矛盾，不解析理由替模型改签。42项定向及独立13项/极性矩阵通过，随后另作唯一一次v2真实请求，三个结论与原逐对基线一致。

v2同材料结果：3→1请求、总Token88569→60944（少31.2%）、估算费用0.072651→0.050466元（少30.5%），完整36原帧保留。两轮工程合计新增0.101508元，账本分别在`verify_results/production-day-20261027/near-neighbor-batching-calibration-r01/`与`verify_results/production-day-20261027/near-neighbor-batching-calibration-r02/`，各有配置、不可覆盖scope/freeze、原请求/响应、audit、对照统计及凭据清理检查。只测一个正例与三个邻居，不能证明总体误判率；提示、Schema和输出结构也变了，不能把节省完全归因于图片共享。

该模块输出独立calibration schema，显式`QC_approval=false`、`production_review_import_allowed=false`，不能导入正式review records或增加合格产量。当前正式生产仍用原审核路径；推广前还需更多独立正反例及当前实际候选验证。

### S0 全量自动检查与分层/风险抽检

`PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.sampling --help` 提供 `prepare/enqueue/report/expand/calibrate`。`prepare` 支持 `mode=real, model=null` 的真实无模型作业配置，无需凭据或费率，仍使用原预算账的时长、并发、租约和恢复限制。它运行现有全量交付QC和当前候选＋显式有效集合的四路检查，冻结候选分母、文件摘要、合同/采集/抽检实现指纹、profile、种子、分层和风险原因。它不发模型请求。

默认内部策略为每个「站点＋任务族」层随机20%、至少1条，另加风险必审；全量兼容选项为policy中的`mode=full`。比例是待真实校准的内部默认值。新站点/能力、相关采集或抽检代码变更、敏感/未知风险、短流程、受控异常/动作异常必审。没有稳定历史时首批可能全部入选。稳定历史只能由`calibrate --input <历史包> --reviews <有效qc-review-2> --output <校准文件>`从摘要绑定、全帧完整、五项PASS的实际审核证据导出；不能手填已知站点名单消除风险。身份/实际阅读仍不由本地JSON认证。

```sh
# 先按 webcollect.batch init 建立独立无模型作业账；下列为CLI模板，具体实跑路径见S0验证记录。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.sampling prepare --config <无模型配置> --ledger <独立运行账> --input <客户候选> --effective-set <冻结有效集合> --output <包外目录>
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.sampling report --plan <sampling-plan.json> --output <包外report.json>
# 启用独立模型worker时，使用另行授权且有有效费率/费用预算的模型账，不修改无模型账配置。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.sampling enqueue --config <模型配置> --ledger <模型运行账> --plan <sampling-plan.json> --output <包外队列目录>
# 然后复用原 ai_worker run/report；此支路真实接入未因S0受控验证而自动获得验证或授权。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.sampling expand --plan <sampling-plan.json> --reviews <有效审核记录> --output <包外后继plan.json>
```

`expand`只读取现有审核协议验证过的实际记录：每层发现1条FAIL/未决即全层扩检；隐私或终态FAIL立即停止，其他FAIL累计2条停止。扩检/停止以不可覆盖后继清单和持久superseded收据留痕，旧计划及已排队worker派发会拒绝，不通过重开命令绕过。策略阈值同样需要S1校准。新候选集合、profile、规则、相关代码或比较证据变化使冻结计划失效。

未抽中保留`ai_status=NOT_REVIEWED`；自动检查不能证明的必要项保持`REVIEW_REQUIRED`，不会因抽检通过补成AI PASS。清单内`coverage_map`逐条列出需求§7的17项、中文/导航、任务终态/差异/四路、附件/澄清及资料检查的证据和边界。当前语言、相邻帧动作解释、隐私和自然完成仍依赖实际审核证据，故没有这些证据的未抽中样本不能放行；20%不意味着其余80%已合格。`report`单列抽中/风险/实际AI/未审核/缺失证据、审核来源和停止状态，且只产生payload阶段结果。正式放行仍由原最终密封交付QC决定，客户验收保持`UNKNOWN`。受控fixture和手写协议正反例不构成真实AI质量证据。

无模型会话审核包用 `python -m quality_inspector.sampling_packet --config <无模型配置> --ledger <同运行账> --plan <冻结plan> --output <包外新目录>`。它复用E3队列及`compact_trajectory`，导出全部选中原帧的路径/摘要、实际动作和近邻全帧比较，以及空白`review-template.json`；不预填观察、身份或通过结论。复制模板另存实际审核记录，如实填写会话来源，再交原`sampling report --reviews`/`expand`验证。新实际审核数及模型请求数均为0；该命令已在2条受控浏览器样本上运行并复跑，12个焦点原帧全部保留。程序化模型和会话审核仍须分别记账。


## 显式交付抽检、人工转审及替换复检（2026-10-27）

旧 `quality_inspector.sampling` 保留风险抽样及逐条证据门禁。用户新确认的交付抽检通过独立的 `delivery_sampling` 显式启用；默认 `check` 行为不变。全量机械、四路去重、分布及整包资料门禁均保持，抽检仅控制逐样本语义检查覆盖。

```sh
# 冻结样本位置、原始分母、比例、种子及标注/原图/树字节。0%不抽，正比例ceil，100%全量。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.delivery_sampling freeze --input <实际客户候选目录> --output <包外sampling-plan.json> --ai-percent 50 --human-percent 0 --seed <固定种子> --stratify site
# --reviews为实际AI样本/资料记录；人工独立记录使用可重复的--human-reviews。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector check --input <实际客户候选目录> --stage payload --delivery-sampling-plan <sampling-plan.json> --reviews <实际AI记录.json> --human-reviews <实际人工记录.json> --output <包外新报告目录>
# 仅为待人工样本建立空白、隔离的审核台；中性context只含source_statement/input_statement。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.delivery_sampling human-workspace --report <实际report.json> --output <新人工目录> --context <中性说明.json> --receipt <包外新收据.json> --reviewer <实际审核人>
# 原样本实际人工FAIL后，用新采集/新sample_id关联替换；原件、原人工决定和父计划保持。
PYTHONPATH=projects/code:projects/quality-inspector projects/code/.venv/bin/python -m quality_inspector.delivery_sampling replace --plan <原sampling-plan.json> --sample-id <被否决ID> --replacement <新采集样本目录> --human-reviews <实际人工FAIL记录.json> --reason <实际原因> --output <包外后继sampling-plan.json>
```

默认按整个批次抽样；`--stratify site`按站点分别ceil，例如100站各20条、50%时每站10条共1000条。AI比例、人工随机比例不包括强制转审及替换复检；这些可能使实际人工覆盖率高于配置比例。抽中的是完整轨迹，不是截图或API请求次数。

AI FAIL、未决、无效或缺失回复全部转人工；有效人工PASS可以裁决AI语义分歧，原AI失败仍保留。人工FAIL输出 `REPLACE_REQUIRED`；替换使用新编号、继承原位置AI选择，并强制人工复检，不能通过重新抽签逃检。未抽中输出 `NOT_SELECTED`，只产生 `SEMANTIC_SAMPLING_ADMISSION`，不生成伪造的 `REVIEW_* PASS`。报告 `semantic_sampling` 单列原始分母、比例、实际AI/人工覆盖、未抽中、人工待审、替换缺额和来源SHA。

封包继续使用payload检查→`finalize-client`新目录→final检查→归档；两次检查均需显式使用同一绑定抽检计划及实际审核输入。最终摘要必须写明按策略验收和真实覆盖，冒称全量逐图或篡改覆盖计数会拒绝。说明资料仍按包检查，抽样通过不能证明所有未抽中样本已经逐条语义验证。该模块不发送模型请求、不认证审核者身份或实际阅读，受控协议夹具不构成真实AI/人工判断。


尚未调用/尚无完整AI记录的选中样本输出 `AI_REQUIRED`，单列 `ai_pending_count`，不虚增人工积压，人工PASS也不能冒充未执行的AI检查。实际模型调用的网络未知/非法回复可通过只读 `delivery_sampling export-ai-failures --plan <计划> --ledger <原模型SQLite> --output <新失败收据>` 导出。收据逐条绑定原real模型账的job、request ID、已结算失败状态、请求行SHA、合同及样本哈希，`check --ai-failures <收据>`/`status --ai-failures <收据>`会回查原账再转人工；手写布尔或不绑定原账的错误声明不能替代。未知费用保持原预留，不由转人工触发自动重发。原账终结请求、合同、计划或样本改变会使该收据失效。


有效交付集合现按应用累计检查 500 条上限，并另报去重应用的类目分布。`set-manifest --application-registry <冻结站点库>` 绑定同工程的应用／别名身份；旧 manifest 无此字段时仍按规范主机统计。每批和累计的类目、重复、短流程检查与审核状态保持独立。[接口与边界](../../docs/工程说明.md#生产者站点表与有效交付容量)

2026-11-02 需求方确认页面／控件语言一致性口径后，仅升级 language 语义规则。旧审核语言项局部失效，其他四项按原证据继续复用；不覆盖原收据或自动重做 AI 审核。准备证据中的字符比例保留为诊断，不能代替独立原图语言审核。
