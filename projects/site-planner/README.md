2026-11-06 [对照实验修复](../../docs/对照实验问题修复与八并发AB试跑计划-20261106.md)第一阶段已落地 R4：`site_planner/inventory_recheck.py` 的访问（GET）、导航、页面观察三类结果分离——GET 仅 DNS 失败为 dead_hard，SSL/拒绝连接/阻断/超时一律 strike；浏览器冒烟复用消费者上下文参数（1280×720、zh-CN、Asia/Shanghai、block service workers），导航期 404/410 dead_hard、浏览器确认入口 403 按既定规则废弃、观察/几何失败记 `browser_observe_failed` 只记录不剔除（冒烟覆盖导航+DOM 观察，不代表完整图树同步）；剔除在短事务内复核 pending 且无 claim；`--dry-run` 全路径零写入（含 smoke 与辅助表创建）。离线测试通过（`tests/test_inventory_recheck.py` 与 `tests/test_consumer_ab_repair.py` 的 R4 部分）；真实库存未做任何处置，生产者 Agent 协议与任务生成不变。

2026-11-06 后续[对照实验修复计划](../../docs/对照实验问题修复与八并发AB试跑计划-20261106.md)真实 A4/B4 消费实验在基础测试交接并重新打开原工程后触发。生产者 Agent 继续供给页面，entry 允许无目标；不增加任务生成或补库存。

2026-11-04 V9新Table1/Table2挖掘100页及质量/性能复盘已结束，当前停止；单页探针失败隔离、公开索引在付费规划前检查已修复，用途指标仍未通过。[结果与归因](../../docs/生产者V9新挖掘100页与性能归因-20261104.md)。本轮未启动消费者或轨迹QC。

2026-11-04 前一工程阶段的 `entry-tools-9` 图片预筛V2与消费者统一：首帧已曝光IMG覆盖率≥95%即“无需消费”，不设地图/图表/图片工具等语义例外；共享标记阻止后续领取/发布。新具名批次须显式选择，旧冻结记录不覆盖。[规则、CLI和验证边界](../../docs/生产者图片型入口无需消费规则-20261104.md)。该前一阶段仅离线实现。

2026-11-04 `entry-tools-8` 已完成本轮有界真实验证，须在新具名批次显式选择；最终用途规则为 `target-page-purpose-6`。匿名观察补证、原件/版本兼容及独立指标结果见[本轮记录](../../docs/生产者新版100网页真实验证与独立用途验收-20261104.md)；旧冻结批次继续按原协议恢复，不自动续产。

历史 `entry-tools-3` 的 P0/P1已接入正式 `produce-entries`：站点用 `submit_site_classification` 原文编号核定，页面从第一方HTML提取链接并使用规则或 `submit_entry_links`。该协议及原冻结批次保持兼容。当前新会话默认 `entry-tools-7`，本轮新版显式选择 `entry-tools-8`，实现及实际验收见上方记录。

2026-11-04 后续工程修复采用 `entry-tools-7`，分开业务选入与用途，修复正文误删和重复补证；Table2 沿用已有 `candidate_id` 主键及事务独占领取，并增加约束核验。仅离线验证，未启动新生产。[修复与并发说明](../../docs/生产者业务选链修复与Table2并发约束-20261104.md)。

2026-11-04 新 `entry-tools-6` 将来源选链与目标用途判别分开：规则先判，未命中必经有原账的模型兜底；缺证保留 UNKNOWN，主区/控件证据写生产者来源，Table2 四字段不变。旧协议显式恢复。本轮 100 网页实测已结束；后台业务及独立语义验收未通过，不自动续跑。开发与实测证据见 [本轮记录](../../docs/生产者用途兜底与100网页验证-20261104.md)。

来源记录分别保存 `site_origin`、`page_origin`、`selection_method`、`page_evidence` 和排序依据；Table2 正文仍是原四字段，入口 `requested_goal=null`，显式调用方目标和原领取参数不变。English/登录切换单列，通用文案不足以建立页面类型时保留 UNKNOWN。页面语言与可操作性仍需消费者首帧验证。

公共 GET 只在传输层编码 Unicode，保留原 URI 与已转义字节；`candidate_landings` 用唯一键在原发布短事务中拦截已结算的重复落地，不合并原入口或不同目标。搜索厂商码 1113 在同一池暂停该通道，保留原 UNKNOWN；未耗尽的已授权种子仍可扩页。新模型、真实网页和首帧效果没有在本轮补测。详细命令与验收见[工程说明](../../docs/工程说明.md#正式第一方扩页与两阶段选择2026-11-02)。

# 站点规划程序

新批次使用生产者站点扩展保存中文首页、整体主营类目与冻结挖掘进度。新入口必须同时满足 Table1 有据分类和最终 GET 2xx；原版消费者继续读取原 Table2 和来源字段。旧冻结批次保持原协议。详见[工程接口](../../docs/工程说明.md#生产者站点表与有效交付容量)。

可显式用 `classify_homepage` 对已核验的第一方中文首页单独判类：模型选原文编号，程序绑定精确引文，已确认决定直接复用。首页保留原 HTML 和实际解码方式；搜索 HTTP 错误保存原响应及厂商错误码，未决原账不自动重发。调用方 URI 清单的零选源 token 与真实站点分类 token 分开核算。

新发现批次默认按候选目标、输入范围和有无进展收尾。共享搜索和模型原账持续计量。[额度限制清单](../../docs/额度限制清单与取消说明-20261101.md)

使用[本机启动说明](../../docs/工程说明.md#本机有界批次启动)中的 `start_candidates.py --scope <范围文件> producer` 并传入搜索方向与数量上限。脚本将同一批次键与 manifest 传给 `produce-entries`，由生产者选择链内证据根。批次报告按实际 `NEW` 计数。

新批次对将要入库的入口执行有预算的公开 GET，仅最终 2xx 允许发布。403、404 等状态逐条留下拒绝收据，未取得响应也不产生可领取候选。模型提交的入口与显式 `--goals` 都经过检查，同批同 URL 只访问一次。[检查和日志](../../docs/工程说明.md#候选-v2-的两个-python-入口)

当前链的 `produce-entries` 使用与消费者相同的 `--history-set`。省略 `--output` 时，生产者按批次身份创建链内证据目录，实际路径见报告的 `evidence_output`。独立试验的运行日志可以放在另一目录。[证据目录与监视命令](../../docs/工程说明.md#候选-v2-的两个-python-入口)

2026-10-31 新的 GLM-5.3-Flash 生产会话默认使用原生工具协议 `entry-tools-1`。继续原会话时，程序读取池中已冻结的协议，早期无协议字段的记录沿用 `entry-content-1`。可用 `--model-protocol` 显式选择新作业的协议，原会话拒绝切换。新协议以简洁 goal 和有限来源上下文注册 `submit_candidates`，使用 `tool_choice=auto`、`thinking={type:enabled, clear_thinking:false}`、`reasoning_effort=low`。按智谱[函数调用](https://docs.bigmodel.cn/cn/guide/capabilities/function-calling)及[思考模式](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode)处理原生工具和不透明历史字段；每轮严格要求恰一个已声明函数、非空且未重复的 ID、合法 JSON 对象及对应 Schema。错名、多调用、缺 ID、纯内容等响应结算为协议失败，不触发入库。外层仅约束 candidates 数组，每行独立判定，非对象坏行不会丢弃其他合法行。

该协议为每批保存 `batch-NNNN-tool-call.json` 和 `batch-NNNN-tool-result.json`：前者只含工具名/ID、参数及原模型作业和请求 ID，后者是绑定同一个 `tool_call_id` 的真实逐行发布结论。候选来源同时引用搜索请求 ID、原命中序号、过滤后索引、模型请求 ID 和行身份；它们不相互替代。工具回执落本地后结束，无额外 completion 确认写库。可选建议仍不能生成 frozen goal；显式 goals 路径仍无需模型。费用及 UNKNOWN 保留原账，候选不是已采样本。

显式 `--goals` 的每项可附 `category_hint`，例如 `{"uri":"https://example.org/tool","requested_goal":{"kind":"edit","entity":"fields","parameters":{"quantity":20}},"category_hint":"在线工具"}`。该提示保存在冻结来源中，不进入 `requested_goal`；旧文件不提供时保持 UNKNOWN，消费者不会用显示回退类别占正式配额。

共享调用入口是 `ModelGateway.call_tool(job, purpose, text, tools, *, system, history=(), images=(), attempts=1, output_limit=None, reasoning_effort=None, attempt_id=None, max_requests=None, synthetic_response=None)`。返回 `name`、字典 `arguments`、`tool_call_id`、`assistant_message`、本轮实际 `user_message` 和原账 `request_id`。下一轮将原 user/assistant 和匹配 ID 的真实 `role=tool` 结果按序放入 history；system 只放一次，当前文字和原始 PNG 由网关构造。完整 history、图片和 Schema 纳入预留与请求身份，不截断或改写 reasoning_content；它仅留在受控账本/通信历史，不进入普通报告或候选来源。synthetic_response 显式传 assistant 消息对象（含 tool_calls），离线格式见 `test_model_provider_protocols.NativeToolProtocolTests`。

`attempt_id/max_requests` 在原 BatchLedger 短事务中共同冻结并限制实际 HTTP 派发：缓存及本地预检零发送不计，格式错误重试和 UNKNOWN 计，UNKNOWN 禁止同尝试换作业/目的重发。同账本以不含密钥的账户散列限制账户/模型在途数，沿用原派发间隔；新独立会话排除原账记录的 1113 账户 hold、1302 账户退避、1305 模型退避（优先 Retry-After，否则 60 秒），同尝试不可换号。未带账户身份的旧 UNKNOWN 无法据此归到某个 key，仍遵守旧冻结恢复门禁；此处不跨独立账本建立全局健康服务，也不清除历史 hold。

ReAct 接入复查：请求计数直接使用原模型请求 `request_json.dispatch_attempt_id` 与 `http_dispatch=true`，覆盖同尝试的全部工具请求；逻辑决策轮次与实际格式重试分别记录。入口导航前和每轮决策前先核对原尝试的 `reserved/unknown`，再判断剩余额度，最后一份额度为 UNKNOWN 时仍保持待核实。明确预算耗尽按宿主 budget 封存；旧决策零发送失败、已结算格式失败和未决请求保留各自分类，均不自动重发。取消等待后即使后台 HTTP 晚到并结算成功，原决策作业的 review_required 仍在同尝试预留事务中阻止新派发，原模型用量与费用照实保留。原缓存回读与未决拒绝路径不选择模型账户；需要新派发时才为该会话初始化共享网关。成功和宿主拒绝的工具结果均按原非空 ID 回传，原 assistant/reasoning 历史保持不透明。

共享网关与 ReAct 接入复查的最终证据为 `verify_results/parallel-producer-react-compat-20261031-r10/{tests.log,summary.json}`：8 个直接相关测试模块共 110 项通过，源码和测试文件在验证期间稳定。新增假 HTTP 接入夹具覆盖成功/宿主拒绝的工具历史、实际重试计数、缓存与零发送、额度耗尽、UNKNOWN 重启防重发，以及取消等待后晚到成功仍保持原尝试待核实。前几轮复现失败和并行源码变动报告均保留，仅为离线工程验证。

本轮最终离线证据为 `verify_results/parallel-producer-20261031-r05/{tests.log,summary.json}`：选定 6 个直接影响模块共 109 项通过，源码/测试文件在验证期间稳定。假 GLM 验证 24 次实际派发通过、第 25 次并发请求在原账事务中拒绝；混合批次 `NEW=2 / DUPLICATE=1 / REJECTED=2`，发布中断后按原工具响应恢复且新增 HTTP 为零。r01 保留新增搜索夹具字段错误及源码变动记录，r02–r04 测试零失败但源码变化门禁未过，不记最终 PASS。以上仅临时库与假网关，不代表真实采集、独立 QC、发布或客户验收。

2026-10-31 生产者 C0/C1 改造已实施并通过离线验证：同一共享池显式安装 `candidate-pool-2` 扩展后，`python -m site_planner.candidate_discovery produce-entries ...` 以 `candidate-producer-3` 逐条发布 `webcollect-data-candidate-2` 入口/目标候选——空目标入口为默认产物，`requested_goal` 只来自调用方 goals 文件，分类/建议留在来源上下文；模型网关只校验外层数组，逐行由程序判定 `NEW/DUPLICATE/REJECTED/OVER_LIMIT/HELD`，行身份=原session+批次+请求+原响应行号，中断只按原响应恢复。搜索词按 `producer-query-policy-1`（最少已完成方向优先、连续零新增停换、每方向上限、规范化去重）在会话级 checkpoint 上可复现地调整；UNKNOWN/401/403/整站 hold 按原作用域零新派发。旧 `webcollect-data-candidate-1`、`produce --strict`、旧 claim 语义不变，未声明新协议的领取端看不到新行。交接样例与验证记录见 `verify_results/producer-entry-offline-20261031-r01/`（36项PASS，仅离线，未恢复生产）。

2026-10-31 的[职责拆分与轻量化计划](../../docs/生产者消费者职责拆分与轻量化改造计划-20261031.md)记录了可信入口、可选目标建议、逐条入库及缺额的设计。当前 V2 批次使用本页开头的 `produce-entries` 入口，以下严格模式记录适用于其原协议。

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


2026-11-02 后继限定批次使用 `entry-tools-4`：同站最多继续读取四份目录，优先复用冻结的第一方文档；逐行校验并隔离错误行。模型选择合法页面类型与本行原文编号，宿主绑定 URI 和精确引文，操作证据允许空数组。可在来源中指定 `settled_selection_job_id`，只读取有 usage 的原响应，保留有效行并对错误行使用独立编号纠错请求；UNKNOWN 不进入此路径。新批次沿用原生产者会话和工程账本，旧协议冻结不变。`excluded_entry_identities` 随来源输入冻结，用于排除历史已入池及其落地身份；Table2 四字段和 Table1 主类入池门禁保持。实测证据与逐候选分账见 `verify_results/producer-continuation-20261102-real-r01/`，离线记录见 `verify_results/producer-continuation-20261102-r06/`；最终实际数量以本轮报告为准。

2026-11-02 本轮后继修正：编号工具的 `ops` 是可选证据，缺失安全解释为空数组，原 provider arguments 保留。已结算的整包协议错误可读取原响应逐行隔离，绝不重派 UNKNOWN。只读首帧在领取前检查原请求保护；成功后 `release_observation` 核验原观察作业、唯一已结算访问和同步图树收据，将 claim 追加为 observed、候选恢复 pending，正式消费者可新建独占 claim。未决观察仍按原规则隔离。历史未决主机/URI 仅作为负向派发约束，包含未入池入口，不能作为本轮页面或分类证据。

本轮限定实测及边界见 [结果报告](../../verify_results/producer-continuation-20261102-real-r01/结果报告.md)：200 条净新增、16 站；31 条固定首帧样本，29 条可判定、21 条可信可用。37 项定向检查见 `../../verify_results/producer-continuation-20261102-r12/summary.json`。保留 7 笔生产 GET UNKNOWN、1 笔 GLM UNKNOWN；早期回放误发 GET 的独立异常账也在报告中，不计离线 PASS 或生产 NEW。


生产者跨批页面检查与仅类目查询已接入正式 `produce-entries`；原作业/收据复用、定向复核条件、`--category` 的冻结输入输出、三类产出统计及禁网验收见[研发记录](../../docs/生产者跨批检查与类目查询研发-20261102.md)。生产继续 `STOPPED_BY_USER`，原 UNKNOWN 和搜索 1113 保留；离线入池不代表真实新应用产出。

2026-11-03 增加显式 `entry-tools-5` 生产者协议：站点核类使用单份编号材料，业务角色与模板签名影响选页排序，UNKNOWN 保留探索位；消费结果按候选 ID／版本及原保存收据冻结。旧协议、Table2 契约及原请求恢复保持。运行与证据边界见根目录 `docs/工程说明.md`、`docs/设计说明.md` 及 `verify_results/producer-opt2000-20261103-r01/`。


2026-11-04 本轮生产者显式 `entry-tools-10 / target-page-purpose-7` 增加主区结构事实、按页编号引用及同次匿名GET复用。浏览器进程按小批复用，每页仍用新匿名context；图片、原始响应、DOM、用途与发布绑定原job/visit。旧协议、默认入口及Table2主键/独占领取保持。工程与Agent goal/prompt/tool、真实新100页及独立用途验收分列于 [V10实施与复盘](../../docs/生产者V10结构引用修复与新100页复盘-20261104.md)；该100页有界验证已完成并停止，实际质量与成本见复盘，不自动扩大到下一批；消费者和轨迹QC未启动。


2026-11-04 最新生产者维护：显式 `entry-tools-11 / producer-business-task-1` 将业务价值与自然任务作为选入核心，page_type保留为可选辅助；用途UNKNOWN、缺字段或引用失败不触发补读/补问。原观察复用，已结算原判定跨小批缓存；任务提示不冻结requested_goal、不证明可执行或五步。原工程/原账、失败和UNKNOWN保持，默认入口及旧冻结协议不改。本轮仅离线验证，未启动真实生产、消费者或轨迹QC。[实现、Agent目标与验收](../../docs/生产者业务价值与自然任务优先-20261104.md)。


2026-11-04 显式entry-tools-11的新100页真实验证已完成并停止。独立业务与自然任务、参考完整度分别验收；业务达本轮工程门槛，整体独立验收尚未通过，失败/缺项/UNKNOWN按原件保留。原工程原账和旧标签不变，不自动续产，不启动消费者或轨迹QC。工程、Agent与token/耗时归因见 [V11真实验证与复盘](../../docs/生产者V11新100页业务与自然任务独立验收-20261104.md)。
