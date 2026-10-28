# 站点规划程序

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
