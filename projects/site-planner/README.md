# 站点规划程序

2026-10-31 生产者 C0/C1 改造已实施并通过离线验证：同一共享池显式安装 `candidate-pool-2` 扩展后，`python -m site_planner.candidate_discovery produce-entries ...` 以 `candidate-producer-3` 逐条发布 `webcollect-data-candidate-2` 入口/目标候选——空目标入口为默认产物，`requested_goal` 只来自调用方 goals 文件，分类/建议留在来源上下文；模型网关只校验外层数组，逐行由程序判定 `NEW/DUPLICATE/REJECTED/OVER_LIMIT/HELD`，行身份=原session+批次+请求+原响应行号，中断只按原响应恢复。搜索词按 `producer-query-policy-1`（最少已完成方向优先、连续零新增停换、每方向上限、规范化去重）在会话级 checkpoint 上可复现地调整；UNKNOWN/401/403/整站 hold 按原作用域零新派发。旧 `webcollect-data-candidate-1`、`produce --strict`、旧 claim 语义不变，未声明新协议的领取端看不到新行。交接样例与验证记录见 `verify_results/producer-entry-offline-20261031-r01/`（36项PASS，仅离线，未恢复生产）。

2026-10-31 下一版生产者按[职责拆分与轻量化计划](../../docs/生产者消费者职责拆分与轻量化改造计划-20261031.md)改造：可信入口为默认库存，目标建议可选，文章类型作提示，逐条入库并报告缺额；来源归属、原账预算、UNKNOWN 和整站止损不放松。新协议须显式启用，旧严格模式保留。本次只更新规划，当前代码仍按下文原契约运行。

2026-10-31 新轻量生产者严格入口为 `python -m site_planner.candidate_discovery produce --strict --batch-key ROUND_ID ...`，共用原session冻结配置与模型/搜索预算，旧协议保留。本轮同版本连续3批各5条原始候选通过AI来源核对并入库，共15条；7/10次后停止，未运行消费者或轨迹QC。详见[严格生产者说明](../../docs/共享站点池与自主发现.md#轻量生产者)及[真实报告](../../verify_results/pilot1000-20261028-r01/producer-validation-20261031-r01/真实验证报告.md)。

2026-10-31 轻量生产者真实验证修复：拒绝泛网页空目标，支持显式correction-report及reconcile-response（原明确invalid_response且有usage）；flags只按版本规则归入parameters，原回答/请求状态不覆盖，UNKNOWN不复发。5条具体候选已形成，10次运行已停止；详见[真实报告](../../verify_results/pilot1000-20261028-r01/candidate-live-20261030-r01/真实验证报告.md)。

2026-10-30 新增轻量 `python -m site_planner.candidate_discovery {install,produce}`，以及 `discovery_agent.discover_candidates`：有限搜索/已有来源一次结构化AI分类并生成候选清单，分批写入共享池附加表，无页面浏览/资格审核。支持target=1000、原搜索缓存及BatchLedger预算/恢复；旧discover_ai冻结流程保留。见[共享池候选协议](../../docs/共享站点池与自主发现.md#候选库存协议-v12026-10-30工程与离线验证)。本轮只做模拟离线验证。

共享池的生产状态按页面/任务记录，不标记整站完成。绑定生产scope后自动保留尝试及QC结果；候选导出默认排除在途、待审、审核通过和同步未完成页面，发现身份和历史记录仍保留。同站其他功能页独立可用，详见[状态回写与防重](../../docs/共享站点池与自主发现.md#状态回写与防重)。

共享站点池、自主发现新入口：`python -m site_planner pool --help`、`python -m site_planner discover-ai --help`；命令、真实配置模板、恢复及计数边界见[共享站点池与自主发现](../../docs/共享站点池与自主发现.md)。

2026-10-29一致性修复将探测异常保存为独立 `webcollect-site-probe-failure-1` 记录，混合目录发布有效子集时继续保留失败原因为分母。来源/探测派发可绑定当前 `site_failure_guard`，失败按原执行ID累计；跨host仅使用证据别名。详见[有限修复计划](../../docs/需求一致性修复计划-20261028.md)。

同次只读访问现在同时保存 `page_anchor` 同步原帧，供当前链页面身份使用；原诊断帧仍保留其诊断性质，不能手工升级为正式证据。字体、视口图片和相关稳态仍须满足，后台document加载不要求所有网络请求结束。

当前源码导航：[工程说明](../../docs/工程说明.md)、[设计说明](../../docs/设计说明.md)、[agent 接手说明](../../AGENTS.md)。下文历史供给数量和策略覆盖只属于原运行范围；现有模块与当前单次采集交接流程见新说明。

当前执行范围为2026-10-28的 `current-chain-r01` 全新链路。统一入口为[真实试点执行说明](../prd/真实试点执行说明-20261028.md)，变更、进展与清理结果见[工程状态与清理记录](../prd/工程状态与清理记录-20261028.md)，实时事实以[本轮进度账](../../verify_results/pilot1000-20261028-r01/progress.json)及其原始账本为准。审核、去重、验收和产量仅使用绑定本轮manifest及专库的结果；旧运行、资格PASS和工程测试均不计本轮合格量。网站按整体应用管理，每个实际任务页面最多一条、5–10个必要操作，整站累计三次真实失败即停止。

Git仅提交有效源码、纯测试及当前工程/需求说明。样本、原图、过程报告、原始模型请求、账本、凭据和ZIP留在本地；历史原件及失败/费用证据保留，清理记录不改变其结论。下文旧批次实测和命令属于对应范围的兼容说明，执行本轮时以当前入口为准。

从种子 URI、公开目录链接或配置的搜索 URL 模板发现站点；保留来源、失败、规范化前分母和固定候选数。复用 `webcollect.preflight.inspect_page` 保存代表页原图、同步观察与风险线索，再做有预算的视觉筛选。不分配 sample_id，不作轨迹 QC 放行。

在项目根目录执行，无需安装新依赖：

```sh
projects/code/.venv/bin/python projects/site-planner/planner.py --help
projects/code/.venv/bin/python projects/site-planner/planner.py discover --help
projects/code/.venv/bin/python projects/site-planner/planner.py probe --help
```

纯离线发现示例（先用 `webcollect.batch init` 初始化独立作业账本）：

```sh
projects/code/.venv/bin/python projects/site-planner/planner.py discover \
  --config projects/code/config/batch-synthetic.json \
  --ledger verify_results/three-program-dev/operations.sqlite3 \
  --sources projects/site-planner/config/sources-synthetic.json \
  --output verify_results/three-program-dev/supply
```

真实来源配置使用 `webcollect-site-sources-1`，`sources` 中每项指定 `category`，并按来源选择：`kind=seed` + `uris`；`kind=directory` + `uri`；或 `kind=search-template` + `url_template`（包含 `{q}`）+ `query`。可加 `allowed_domains` 限定目录链接范围。只从真实返回的链接取得候选，不生成网址。外部搜索服务的费用不由模型费率表推算，未提供时总成本为 UNKNOWN。

S0 增加 `projects/code/config/batch-no-model.json`：`mode=real`、`model=null`，仅校验运行次数、页面数、时间、并发、每域间隔及租约，无需 API、费率或币种。初始化独立作业账本后可直接发现/探测；`probe` 在没有视觉复核证据时保存能力与原图并输出 `review_required`，不会把机械初筛记作 ready。启用模型时继续使用原模型配置和严格费用限额。生产采集次数/待审库存仍由原采集 runtime/policy 限制；新配置不扩大原 campaign。

每个来源可配置正整数 `max_candidates` 控制新入选 URI 数，避免第一个目录占满固定候选集。全局候选限额达到后仍输出 `candidates.json`，保存 `sources-frozen.json`、当前来源全部已解析链接计数、`deferred_links` 和 `unprocessed_sources`。未抓来源的链接分母为 `UNKNOWN`；该来源不计作访问失败，也不编造发现总数。候选上限是选集边界，页面/时间等运行限额仍触发持久暂停。重新启动使用原作业和候选选集，不重置预算。

`probe` 的 `--candidates` 使用实际生成的 `candidates.json`。当前精确页模式只检查候选URI，不再自动跟随首个同站导航；库存绑定实际落地URI，`capability_scope`限制发布任务只使用实际观察页，其他任务页须独立探测。HTML/控件库存只支持初筛；实际执行仍重新验证可见文字、焦点和遮挡。缓存绑定候选来源/页面库存/规则版本和实际证据；输入版本改变才建立新探测 job，证据被改则拒绝复用。到期能力不能直接交给任务执行，需提供更新后的来源/候选版本重新探测。无模型探测保持`review_required`，随后使用`prepare-review`生成空白包、`import-review`导入实际视觉复核；原图、URI、来源、库存、规则、身份及有效期绑定产生新能力版本。发布阶段再次检查，不能手改ready。

目前自动任务编译支持三种狭窄数值表单策略，以及已验证精确URI上的BMI原生控件策略。加速实施已完成BMI视觉能力导入、发布和1条正式采集，但新轨迹被累计去重拒收，不能靠换BMI参数补数。其他页面的能力与供给不足会如实保留。`unique_task_capacity_estimate`不是实测合格产能，不能由此推算每站10条或20条。运行证据位于`verify_results/three-program-acceleration-20261026/`，旧[自动交接与供给验证](../prd/三程序S1自动交接与供给验证-20261026.md)保留历史冻结事实。

独立模块`python -m site_planner.candidate_selection`可离线重选冻结来源中的工具页。`--supply`可重复，`--rules`冻结通用规则及`max_selected`、`max_selected_per_source`，`--output`使用新目录。保留全部链接出现、规范化URI、排除原因和失败分母；候选不授予ready。当前完整库存202条，独立排队清单20条、每来源最多10条，均未执行新探测。

合成浏览器探测仅由受控验证脚本运行；CLI 不提供把本地/合成站点声明为真实站点的参数。S1固定最多100候选的真实试验已实际执行，因4来源TLS失败仅冻结20候选，未补站；现策略命中0，未满足生产条件。实际命令、分层结果和证据见[S1运行记录](../prd/三程序S1运行记录-20261026.md)。旧[E0–E3记录](../prd/三程序E0-E3运行记录-20261026.md)保留当时结果。

S0 受影响验证：`PYTHONPATH=projects/code:projects/code/tests projects/code/.venv/bin/python -m unittest -v test_s0_runtime`。实际无 API 环境 CLI 记录及受控 Chrome 探测证据在 `verify_results/three-program-s0-20261026/runtime-r01/`；离线种子 URL 登记不算真实供给探测。

S1新增可选`budget.max_top_level_visits`：每次主动来源fetch/page.goto及失败重试都持久计数，缓存不计新访问；原`max_probe_pages`仍是job/page预留键数。实际派发逐次检查域间隔及剩余墙钟，redirect/子资源另列观察量。缺实际访问历史的旧账保持UNKNOWN，不能清零后启新限额。旧S1两页模式的部分成功与失败证据保留；当前精确页模式不再自动派发第二代表页。原S1冻结上限220、实用43，原身份完成后重入仍43；最新独立包为8/60访问，两者分账，不通过换run/目录补数量。
