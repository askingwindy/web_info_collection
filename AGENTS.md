# Agent 接手说明

2026-11-13 用户授权重启双站真实验证并消费prod 400条，已完成并按用户授权清理非成功数据。阶段1（SSD第2次执行，baseline库已读、回执r02/baseline-read.json）：muxtly 2/8合格导出、站点闸门达标，wiki 0/10；阶段2（prod池400条、10进程、不分站点、按创建序跨48站）：400全部派发，21条合格导出（全部muxtly，5–16步）。交付 `delivery/202611122359/`（52 SHA全OK）与 `delivery/202611130023/`（448 SHA全OK），23条verified_saved读回一致；模型账：阶段1 82请求（70/10/2 unknown）、阶段2 1493请求（1284/186/23 unknown，均保留未重发）、token 合计约21.7M入/2.3M出。启动前修复目录迁移打断的消费链：7处绑定重绑（config↔batch_meta、registry链绑定、m4_campaigns、池checkpoint、stop_meta，先备份+回执）+ `current_chain.py` same_chain物理身份/冻结证据引用物理解析两处修正，核心50测试全绿，6次单条试跑贯通。**主要发现**：e6cd793"冻结原目标"prompt与prod池requested_goal全null冲突——wiki 0/134、dushu/syztt/taixing/chelaile 0/132 模型拒收（UNSUITABLE无目标），仅muxtly计算器页可冻结可验证目标（21/134、另37条导航超时）；恢复阅读型站点合格率需producer供给目标或放宽null-goal自提，待用户决策。2026-11-13 用户授权删除昨晚非成功数据：427个claim证据目录（20.68G）+重绑安全备份/试跑目录/失败worker产物（2.1G），共释放约22.8G（磁盘可用34Gi），五库原账行、23条成功样本证据与两交付包不动（`verify_results/prod400-10w-20261112-r01/deletion-manifest.json`）。遗留：producer-jobs续跑会撞producer_concurrency事件旧真实路径校验（下次生产者轮需同样重绑）；QC/人工NOT_RUN、发布false、验收UNKNOWN。

2026-11-12 Wiki阅读与连续执行优化已按用户授权集中实施（3个gpt-6.1-sol/low子Agent）：首次路线逐步取证连续执行；真实偏差一次补齐尾部；重复请求发送前去重；完整正文／表格、历史补图、弹层容器滚动、内部schema、首次标注及末帧核验贯通。受影响19个不同核心用例最新全部通过，维护总量仍50；含局部复验累计35次执行（28通过、7失败）、pytest 5.549秒，未全量重跑。一次离线集成工作集两条链最终32/32检查通过：计算7步、2次intent、0revise；弹层阅读5步、3次intent、1revise；均经正常RuntimeStore、candidate_results和隔离导出。局部失败原件保留，真实本地HTML专项通过。原151个intent的后续facts字符中位/P95减少53.1%/60.7%，仅字符代理。历史delivery/202611121809/的114个SHA256全一致。真实模型／网页采集／生产新增0，独立QC与人工NOT_RUN、发布false、验收UNKNOWN；不启动采集。详见[方案及当前结果](docs/策略2Wiki阅读与证据标注Token优化方案-20261112.md)与[实施证据](verify_results/strategy2-wiki-plan-implementation-20261112-r01/report.md)。

2026-11-12 用户澄清拼写并追授收尾轮已完成（[回执](verify_results/db-cleanup-20261112-r01/report.md)）：`database/sqlite/baselin/` 的成功样本基线库迁至 `database/sqllite/baseline/`（SHA256 一致），空目录 `database/sqlite/`、`sqllite/.offline-fixtures/` 及全仓无引用的 `.delivery-locks/`（13 个空锁）已删除；database/ 仅余 README、launch-inputs（配置模板）与 `sqllite/{prod,verification,baseline}` + 4 个符号链接。**results/ 与 verify_results/ 使用内容核验结论：无安全可删项**——collections/consumer 87 个会话目录（6.4G）经 strings 扫描确认 87/87 全部被 prod 五库原账引用，muxtly-single-plan（286M）被 SSD 文档与 11 份回执引用 75 处，verify_results 42 项含当前工作集回执（sites15-discovery 为暂停轮续传锚点）；仅 ~15M 纯被取代中间迭代未删（收益可忽略且损害证据链）。如需进一步释放：验证轮 results ~316M 或结束轮 attempt 证据 ~5-6G，均需显式授权并接受原账/文档引用断裂（回执第三节列明代价）。本轮未启动真实采集。

2026-11-12 用户确认数据库目录格局约定并已完成迁移（[回执](verify_results/db-layout-prod-20261112-r01/report.md)）：正式生产工程固定 `database/sqllite/prod/`（`candidate_project init` 默认根同步改为此值），验证工程放 `database/sqllite/verification/`（显式 `--root`，轮次结束不自动删除、清理须逐次授权），成功样本基线库在 `database/sqllite/baseline/`。旧正式工程 `producer-muxtly-wiki-200-20261111-r01/` 已整目录迁至 `prod/`（配置 JSON 内 14 处路径改写，五库与 producer-evidence 字节不变，SHA256/行数 264/1915 迁移前后一致，`site_inventory` 以新旧两条路径回读输出一致）；三个策略2验证工程迁至 `verification/`。**原路径留有同名符号链接桥接**：五库内嵌旧绝对路径（约 34 万处原账数据，不改写）与历史收据仍依赖它们解析，不能当冗余项删除。受影响核心测试 15 passed（0.81 秒，含 1 条旧默认根断言按新布局更新）；未启动真实采集。后续运行一律以 `prod/` 为正式工程锚点。

2026-11-12 SSD新授权双站验证首次走通完整真实交付链：Muxtly／Wiki 每站10条、每站5进程、本站合格保存并导出即停，执行1次即双站达标（剩余4次授权未用）。16条正式执行，**5条合格保存并导出**（muxtly 4/6、wiki 1/10），客户目录 `delivery/202611121809/`，114个打包文件SHA256SUMS全OK；5条经 `verified_saved` 读回、哈希、候选回写、导出收据全部一致。模型请求195次（148成功、47 invalid、**0 unknown**），16 worker全部退出码0，无源码漂移（源码＝保存链收口轮快照），零源码修改、零修复重跑、零离线重测。muxtly-07..10按闸门未派发保持pending未领取；失败11条全为已知模型行为类（无新工程断点），各有界结束证据保留。独立AI QC／人工NOT_RUN、发布false、客户验收UNKNOWN；wiki合格率10%（短流程与无进展仍是主因）。逐条账与核对明细见[本轮报告](docs/策略2双站各十条验证与首次合格交付-20261112.md)与 `verify_results/strategy2-dual-10x5-20261112-r01/accounting.json`。成功样本 Table2 行与逐条结果已按用户指定落库 `database/sqlite/baselin/baseline-success-20261112.sqlite3`（新目录，与 `database/sqllite/` 工程库根并存；data_candidates 5 行＋round_results 20 行＋round_summary，报告含结构与哈希）。

2026-11-12 门禁走读修复与保存链离线收口已完成（[证据与边界](verify_results/strategy2-save-chain-20261112-r01/report.md)）：首帧只判断首步确定输入冗余，不从引用命中推断滚动多余或正文／结果目标完成；结束修复按当前展示控件、同文档锚点及已核验前页导航事实许可，拒绝编辑／重置／焦点按键时返回具体缺项和定位建议。新增隔离计算8步、纯阅读5步，经正常 `_react_collection`、派生、RuntimeStore提交、候选回写及隔离导出，sample ID与哈希一致；加工失败保持 `program/save_failed/eligible`，integration批次导出仍拒绝。汇总44/44、反馈专项及失败分支5/5通过；受影响核心5个不同用例最新均通过，累计6次执行（5通过、1次旧断言失败后局部复验通过）、pytest共1.05秒，维护总量仍50，未全量重跑。仅合成离线夹具（导出使用生产形状测试），真实模型／网页／生产新增均0，QC／人工NOT_RUN、发布false、客户验收UNKNOWN；不启动采集。


2026-11-12 三轮后整体计划复核仅更新文档，未修改实现、未启动新采集。当前待实施顺序与验收见[SSD文首](docs/策略2观察反馈与完成收尾优化SSD-20261112.md)：首轮自然五步资格；末帧缺项／必要定位／停滞统一；完整标注；正常RuntimeStore提交与消费者回写集成。原25项集成只到派生文件，不能作为正式保存链证明；旧双站五次Prompt已标为历史授权。下述“已修复”按各自时间点理解，不覆盖本次新发现的缺口。

2026-11-12 三轮固定采集复核已结束：新授权 Muxtly／Wiki 每轮各5条，共3轮、30个唯一新候选及30个正式attempt，进程全部退出；每轮源码摘要一致，三份campaign均停止。宿主完成证据接受9条，正式保存／客户导出／内容复核合格均0，未新建客户样本包；claim failed 28、reconcile 2，新增模型UNKNOWN 2笔保留不重发。修复稳定目标事实停滞核算、语义全目标反馈、当前控件唯一别名正规化、正文路线与补图、结果完整叙述及无版本恢复引用；最后查实并修复goal_ready抢先拦截必要结束定位。维护核心总数仍50，受影响16个不同用例分批累计82次执行（80通过、2失败后局部复验通过），pytest累计4.30秒；最终离线集成25/25通过、必要定位专项通过，未全量重跑50条。**第3轮后最后改动仅离线覆盖，不增加第4轮，不宣称真实交付达标。** 独立AI QC、人工审核NOT_RUN，发布false，客户验收UNKNOWN。三轮明细、12步失败样本原恢复合同阻断及剩余规划／短流程问题见[本轮报告](docs/策略2三轮采集修复与交付复核-20261112.md)。

2026-11-12 策略2协议修复及双站固定采集已收口：`model_gateway.schema_errors_feedback()` 合并全部独立校验错误，`field_repair_plan()` 一次覆盖全部可修复叶字段；`screenshot_plan` 支持明确的“A 与 B”双输出原子事项、错放 `requirement.source_type` 的无损归位，条件 schema 改 `not/anyOf` 以返回精确字段错误。50 条核心测试全过（9.267 秒）、离线集成 25／25 PASS、三笔真实原始响应只读复算通过，证据 `verify_results/strategy2-protocol-atomic-20261112-r07/`。r04 固定十条为 5 rejected、3 interrupted、1 running、1 历史导出；导出样本 `S000001_sample_000009` 复核漏总成本 `$46958.76`，不计完整合格交付，原件未改。r05 从 Table2 对 Muxtly／Wiki 各取 5 条并真实执行，结果 4 rejected、2 interrupted、4 原账 running（实际进程均已终止），保存、导出、复核合格均 0；campaign 已停止，未重派或清理原账。重复 complete 但持续缺证据的路径仍会循环到外层时限，是尚未解决的真实缺陷；独立 AI QC、人工审核均 NOT_RUN，发布 false。逐条结果见[客户交付汇总](verify_results/strategy2-two-sites-five-20261112-r05/client-delivery-summary.md)与 `r05-closure.json`。

2026-11-12 策略2观察反馈与完成收尾优化已实施完成并离线验证：路线驱动检查点（observation_steps→执行检查点+revise重锚）、candidate_results 候选层、按需历史关键帧补图（历史控件不可派发当前动作）、goal_ready 不执行无用尾部、`DERIVATION_OBLIGATION` 义务分离（"核对结果"=页面输出确认，显式验算仍强制 derived_check）、complete 步标注分工、结果区完整叙述；并修复 `DECISION_FIELDS_INVALID` 绕过停滞核算的真实缺陷（离线复现 58k 事件无限循环）。核心测试 **50 条（上限内）全绿**、离线集成 25/25 PASS，证据 `verify_results/strategy2-observation-feedback-20261112-r01/`（[报告](verify_results/strategy2-observation-feedback-20261112-r01/report.md)）。双站真实尝试按最多五次授权停在阻塞：**Muxtly 0/5**——历史 reconcile claim 的隔离许可钉死在已耗尽的旧 request id，`claim_research` 合同阻断（[muxtly-blocked](verify_results/strategy2-observation-feedback-20261112-r01/muxtly-blocked.json)）；**Wiki 3/5**——三轮均零模型请求/零业务动作，第三次 claim+首屏后冻结目标字节被 `validate_task_instruction`（《辐射平衡》须写「辐射平衡」）确定性拒绝，research 合同禁止改字节，按"开始后不得换候选/换目标"停站（[attempt-summary](verify_results/strategy2-observation-feedback-20261112-r01/wiki-run/attempt-summary.json)）。**两站验收四条件均未达成，本轮无真实验证通过结论；不据此启动采集。**解除阻塞需新授权（Wiki 换候选+「」目标，或 Muxtly 显式 UNKNOWN 处置）。

2026-11-12 用户授权三个工作区统一到主目录 `main` 并清理附属分支；保留主目录最新修复，选择性整合 Wiki 与 ZCode 独有功能。后续在同一 main 研发。只执行受影响离线核心检查，不启动真实采集；合并取舍、测试和外部备份见[记录](docs/工作区改动合并与main收口-20261112.md)。

2026-11-12 生产启动器 `--sources` 接线已修复：`site_workers.launch()` 在启动前把每 worker 的来源 JSON 写为 `results/site-workers/<plan_id>/wNNN-sources.json`，命令改传文件路径，`plan.json` 保存最终路径。首次真实启动 `20261112000811-0933deae` 因 JSON 字符串被当文件路径而 20 进程全部退出 1、零新增；修复后同一离线集成扩为 5 项 PASS（0.458 秒，含 20 个轻量子进程及长中文来源回读），证据 `verify_results/site-workers-sources-20261112-r01/`，本轮未重跑 50 条核心测试。随后授权真实补采 `20261112001538-22ced6ea` 共 20 进程、两站各 10，全部退出 0 且已退出，但业务报告为 17 PARTIAL、3 TARGET_REACHED：Muxtly 45→45、Wiki 0→60，累计缺 155／140；Muxtly 10 个均受原模型 UNKNOWN 阻塞，Wiki 7 个 PARTIAL 另报并发分类变化，未自动重启、换批重发或清理旧账。消费者、QC、人工审核和导出均 NOT_RUN，退出码 0 不等于达标。

2026-11-11 策略2 动作多样性与控件投影统一优化已落地，详见[实施结果](docs/策略2动作多样性与控件投影统一优化草稿-20261111.md#实施结果2026-11-11-落地)。起因是一次真实 wiki「月食」首轮：模型看到 11 种步动作却提交 6 步连续 scroll，根因不是动作缺失，而是 `controls_projection` 固定取前 30 条且第 2 层保持文档原序，30 个名额里 15 个是 nav/form/div/span/img/h2 等不可派发容器，9 条目录链接只投影到 2 条、正文链接 0 条；同时 `requested_goal` 为空时 `session_core.py:165` 的通用指令过泛（需求书 §6 明确禁止"浏览一下这个网站"式目标），模型自提了纯线性通读目标。三层改动：解阻塞（区域型 scroll 目标无 text 时 `KeyError: 'text'` 崩溃、`_bind_target` 异常未被有界检查点包住、RAW_PENDING 结算丢弃会话自己的 failureClass）；控件投影（只投影可派发行、正文可点控件排在站点导航之前、上限 30→60、每观察归档一次 `screenshot-controls` 事件）；prompt 与记账（补全 11 种步动作及参数形状、禁止纯线性通读、首轮下发 `interaction_affordances` 事实清单、`first_plan_admission` 记 `action_histogram`）。月食首帧离线复算：正文可点链接 0→29，不可动作容器行 15→0，导航链接全部后移。**设计草稿的 2b（登录/注册文本正则硬排除）未实施**，2c/2a 的判定信号按真实状态字段重写（元素无 `id`/`class`；动作状态全为 `INSUFFICIENT`，原判据一条都过滤不掉）。全工程仍 **50 条核心测试**，只扩展现有用例断言未新增执行项，`50 passed`、7.68 秒；三包 207 模块 import 0 失败、38 个 `__main__` 入口 `--help` 全通过。**一处行为变化**：program 类 RAW_PENDING 现在会 `set_scope_paused(True, ...)`（`collect_runtime.py:475`），与其余 program 路径一致。真实 GLM、真实网页采集、独立 QC、人工验收全部 NOT_RUN；策略2 至今无任何 success 基线，6 步 scroll 是否消除、prompt 增量是否可接受只能由一次真实重跑确认，需用户单独授权。

2026-11-11 按站点统计与生产／消费启动器已完成：新增 `webcollect.site_inventory` 和 `webcollect.site_workers`，共享 `database/sqllite/` 候选库与 Table1／Table2 结构不变，按 `applications.id` 分站点派发。生产者支持多站每站累计 NEW 目标与总进程均分，消费者支持单站或多站跨全部生产批次领取当前 pending；`candidate_consumer run --stop-when-empty` 空库存返回 `candidates_exhausted`，原持续轮询缺省不变。默认只输出计划，显式 `--launch` 才前台启动并等待，日志在 `results/site-workers/<plan_id>/`。全工程仍 **50 条核心测试**，unittest `50 passed`、7.785 秒；独立离线集成 4 项 PASS，证据 `verify_results/site-workers-20261111-r01/`。真实 GLM、网页采集、消费者业务执行、真实多进程及 QC 全部 NOT_RUN；使用方法见 README 顶部，不因启动器完成自动启动采集。

2026-11-11 固定持久根与生产者并发接线已完成：新工程默认直接使用 `database/sqllite/`，不再按运行时间、版本或 `project_id` 建数据库子目录；`project_id` 仍用于 run/chain/输出身份。固定根可保留旧工程子目录，但直属 scope、manifest、配置、策略或数据库文件存在时拒绝初始化，不覆盖、不自动迁移。Table1 `applications` 与 Table2 `data_candidates` 继续共用 `candidate-pool.sqlite3`，候选四字段和消费者 claim/snapshot 契约不变。每站 NEW/pending 上限已在 `CandidatePool._put_v2()` 的 `BEGIN IMMEDIATE` 发布事务内复核，并发超额写 `OVER_LIMIT`。全工程仍为 **50 条核心测试**，unittest 全量 `50 passed`、7.878 秒；独立生产发布→消费领取离线集成 5 项 PASS（`verify_results/fixed-producer-storage-20261111-r01/`）。真实 GLM、真实网页采集、真实消费者执行、QC 和 100 进程实跑均 NOT_RUN；下方旧路径与旧轮次说明保留历史含义。

2026-11-11 交付口径追加修复（同日后续轮，用户讨论“策略2作为模式能否达标”后直接授权改代码）已完成，详见[报告追加节](docs/策略2走查修复与数据库持久化-20261111.md#交付口径追加修复同日后续轮)。六项修复均只改当前实现，无新增版本或兼容分支：`describe_change` 焦点态转移改为兜底（提交类点击按实际渲染的结果区/数值/新可见文字叙述）；controls 角标数字经 `provided_control_numbers` 绑定为 `target.control` 并在 `_source` 留 mark_number；`observed_result` 逐字口径写进 prompt/规则并新增 `OBSERVED_RESULT_NOT_VERBATIM` 缺项；`narrative_grounding_gaps` 在首轮与 revise 接受前机械核对 `rationale` 的「」引文是否落在当前帧（复用既有有界纠正，不新增模型调用）；下一步 `_source` 属于已变化文档时 choices 与工具 enum 同步去掉 `continue`；`planned_terminal_narrative` 两分支按“末帧仍可见/末帧前已观察到”分列依据。维护核心测试由 43 条增至 **50 条（当前总量 50，仍在 ≤50 上限内）**，全量 `50 passed`、pytest 7.73 秒；叙述文本另用一次性离线夹具核对，未新增常驻用例。真实 GLM、采集、QC、人工验收仍全部 NOT_RUN，不据此启动采集或宣称达标。

2026-11-11 本轮走查、策略2补缺及持久存储修改已完成，详见[报告](docs/策略2走查修复与数据库持久化-20261111.md)。用户确认原 `results/` 工程被删除；新工程默认使用 `database/sqllite/<project_id>/`，五库、scope、配置、manifest 和生产者来源证据均持久保留，采集输出单独绑定，数据库不提交Git。`candidate_project init --root` 可省略，支持 `--output-root`，禁止把 results/verify_results 当持久根。不自动重建旧库或重发UNKNOWN。本轮43条维护核心均有相关通过结果（首轮40过3失败，修复后受影响10条全过）；默认pytest只发现当前核心目录，历史QC套件保留但未默认维护/运行。真实GLM、采集、QC均NOT_RUN。用户已将后续改为准备[新生产者Prompt](docs/生产者Muxtly-Wiki各100页执行Prompt-20261111.md)：Muxtly/Wiki每站100页、每站10进程；此Prompt本轮尚未执行，原消费者20页计划未启动。

2026-11-11 无版本改造收尾轮已按用户三阶段指令完成：阶段一源码收口（六套关键回归全部通过的修复链：chooser NameError、分支回包 attempt/observation 宿主绑定、result-completion 稳定名两处旧字面、substantive_result_text 非数值模式、content_effect 结果区绑定、manifest schema 版本分叉删除、candidate_discovery produce/reconcile-response 死子命令删除、band_budget/candidate_binding 常量统一）+ 残留收敛 + 三包 201 模块 import 0 失败 + 14 入口 --help 全通过 + DB 对照报告（五库备份↔正式库一致，正式库未改、无需结构变更，见 verify_results/noversion-switch-20261111-r01/switch-report.md）。阶段二按用户新指示：**原 260 个测试文件（3225 条）连同 fixtures/helper 全部删除**，重写 projects/code/tests/test_core_contract.py（13 条核心契约全绿），后续按需增量补充；离线集成 4/4 通过（verify_results/noversion-offline-integration-20261111-r02/report.json）。阶段三文档同步完成。真实 GLM 采集、生产者固定页、消费者候选、AI QC 全部 NOT_RUN，不据此启动采集；本轮无真实验证结论。

## 后续开发统一约定（2026-11-11 用户确认）

- **核心测试简单、只覆盖核心代码，全工程维护总量不超过50条**：只新增和维护能直接验证关键业务行为、关键数据与状态一致性及少量重要失败路径的用例；短小、清楚、快速，不扩展非核心、重复或仅映射实现细节的测试，不为覆盖率堆积用例。50条是全工程核心测试总量上限，不是每个模块的额度；参数化展开按实际独立执行项计数，不把大量场景塞进一个大用例规避上限。每次变更只更新并运行受影响的核心用例，报告实际用例数与耗时；不默认维护或运行历史全量测试。本次记录约定，不自动批量删除既有测试。
- **后续开发统一采用无版本模式**：直接修改当前实现，不新增实现、协议或规则的代际版本，不增加旧实现兼容分支；不因代码无版本而改写历史原件、费用、UNKNOWN、claim或审核事实。
- **实施顺序**：先完成全部代码、数据库、配置、依赖与接线变更，使整体功能具备运行条件；再更新并运行本次修改相关的核心测试用例；最后同步文档。**不做真实验证**，不自动安排真实GLM、真实网页采集基线或真实对照试跑。

上述约定优先于下方相冲突的历史研发、版本维护及真实验证要求。

2026-11-11 无版本改造已按[执行 Prompt](docs/无版本改造执行Prompt-20261111.md)集中实施到当前工作区：稳定业务名统一收敛到 `projects/code/webcollect/plan_protocol.py`（`conditional-plan`、`goal-completion-ending`、策略 `react`/`screenshot_plan` 等），删除 V1–V13/ending-2..6 代际常量与分派、legacy_v5 5–10 步上限、action_stability focus 系列（仅剩 action-scoped evidence）、生产者 entry-content/entry-tools 多协议路径与 `--model-protocol`、候选协议筛选、QC RULE_VERSIONS/跨包 supersedes 链与 `--version-policy`、三个包的内部版本号与控制台脚本（改 PYTHONPATH + `python -m` 启动）。strategy_result 经 `finalize_strategy_result` 与 RuntimeStore 实际保存收据收口；task_key 改 `sha256([campaign_id, task_id])` 无版本盐，m4_tasks 列保留并写稳定值。五库已取全量一致备份（`verify_results/noversion-switch-20261111-r01/*.bak`），切换脚本 `projects/code/scripts/switch_noversion_db_20261111.py` 在工作副本验证通过，正式运行库未修改。**一次相关集成与真实 GLM 基线均未运行**，测试残留与逐组状态见[改造清单实施结果](docs/无版本运行改造清单与方案-20261111.md#2026-11-11-实施结果)；不据此启动采集。

2026-11-11（实施前状态）用户确定后续维护原则：所有代码更新直接修复当前工作区实现，不新增实现/协议/规则版本或旧版兼容分支；本地运行直接使用当前源码，运行期间只能分析、不能修改源码，由人工保证。[改造清单与方案](docs/无版本运行改造清单与方案-20261111.md)已对照最新未提交缺陷修复重新审核，补充保留检查、旧 V5 上限删除、最终保存状态收口及数据库约束处理；[逐文件索引](docs/版本维护代码索引-20261111.md)和[执行 Prompt](docs/无版本改造执行Prompt-20261111.md)同步更新。去版本源码和数据库切换当时尚未实施。下文旧“升级协议/冻结旧实现/版本兼容”要求仅解释历史，不作为后续新增版本的依据；旧原件、费用、UNKNOWN、claim 和审核事实仍保留。

2026-11-10 停止后已只读查清固定四条的两笔invalid_response：均为Muxtly完整首轮工具回包，在用户停止后才返回并被gateway schema拒绝；w01是wait/scroll冗余target，另只有4个业务动作；w02是6步缺expected_result及target/value/expected.value结构不兼容。集成规范回包覆盖不足，计算新完成协议的首轮仍强制finish_when字面也未收口。详见[诊断与最小方案](docs/固定四条invalid_response根因与最小修复-20261110.md)。本次未改源码、重启或重跑已通过检查，仍全部停止，不据文档自行采集。

2026-11-10 统一方案集中修复及相关集成已完成，固定四条真实验证随后按用户“优雅停止”结束：协调器与4个worker全部退出，不补位、不重启。领取4、正式attempt4均interrupted；原目标success/annotation/正式保存/导出均0。Muxtly两条终态有效步0，Wiki两条无终态计步不填0；145条旧未决记录未变，源码无漂移。全部子Agent `gpt-6.1-sol / low`，采集high/high。新执行无累计8/10步上限，异常/短流程禁止正式保存；独立QC/人工/发布未运行，不能称真实闭环通过。见[本轮记录](docs/统一方案集中实施与固定四条验证-20261110.md)。本轮授权已结束，旧claim/UNKNOWN/原件不改写，不自动续跑。

2026-11-10 5–8步优先规划及固定20条授权已执行并停止：V6 prompt/schema/保存/导出已改，首轮至少5步、优先5–8步但无资格上限；正式保存须原目标success且有效步≥5，异常和短流程不正式保存。按用户要求未跑测试。真实启动20进程、领取20条并完成首屏；协调器在300秒前台窗口收到SIGTERM，20子进程均-15退出，正式attempt/模型请求/业务动作/保存/导出均0，不能评价prompt效果。20个claim保留`consuming/execution`，不重置或重派；145条旧UNKNOWN不变。采集后检出banded_plan.py源码漂移。详见[执行记录](docs/客户反馈更新实施与固定基线验证-20261110.md)及固定目录`final-evidence-summary.json`。下文旧限制仅解释历史。

2026-11-10 固定40条真实验证已结束：两站各20条，20进程各固定2条，GLM high/high，不重复已通过检查。实际领取38、正式attempt22；正常多步success保存0，内部controlled_exception保存6，导出0。w06/w09零效果循环经用户明确授权终止，全部本轮进程已退出，不补位或重启。Wiki一条目标检查VERIFIED但终态no_path/异常的差异保留，未改标。原四条阻塞记录、原账与未决请求均保留，详见[本轮结果](docs/消费者固定40条真实验证-20261110.md)。

2026-11-10 续接收口：drag.end_coordinate 与 V13 已核验目标的独立完成依据已修，封存 raw 的局部后加工检查通过，合成隔离拒绝保留。固定四条启动前发现全部已被 `delivery-rate-fixed20-20261110-r01` 领取，本轮零真实派发，保持不补位、不重派；`launch-once.json` 已存在，不能按旧交接再次启动。见[执行记录](docs/客户反馈更新实施与固定基线验证-20261110.md)。另一轮结果不计入本轮，未停止或修改其运行。

2026-11-10 后续澄清：本轮唯一目标是提高原目标 success 下的多步交互。至少五步要求放首轮自然完整规划，工程负责执行到真实成功；新交付不要小于五步或 controlled_exception，旧 short_flow ≤2% 例外不再适用。十二种动作尽量自然多样、不强制全覆盖。标注重点修视觉规划到 annotation.json 的首次生成链；历史订正工具保留但本轮不自动调用。进展见[执行记录](docs/客户反馈更新实施与固定基线验证-20261110.md)。

2026-11-10 新授权：按客户反馈计划并发集中实施（全部子 Agent `gpt-6.1-sol / low`），随后一次相关集成和固定四条真实基线（两站各二、一人一条、不补位）。历史标注采用工程可选后置接口，确定字段才订正，零新增模型/浏览器动作、不重判完成状态。当前进入集成，尚未启动该真实基线；范围与结果见[执行记录](docs/客户反馈更新实施与固定基线验证-20261110.md)。下方上一轮十条记录保持历史含义。

2026-11-10 最新一轮协议对齐修复与固定十消费者真实验证已完成并停止。按用户指令全部子会话 `gpt-6.1-sol / low`，未重跑测试；固定十人各一条，无替换补位。最终规划接受7/10、普通完成候选1/10，仍有派生字段冲突和来源绑定缺口；不自动继续采集。详见[本轮结果](docs/消费者协议对齐修复与十消费者验证-20261110.md)。

2026-11-10 本轮新授权覆盖上一轮已结束的十条范围：梳理协议与工程失败，全部子会话 `gpt-6.1-sol / low` 集中修复；不运行单测、集成或回放，直接一次十消费者真实验证。Muxtly/Wiki 各五人，每人一条新生产候选；普通首次计划≥5，实际普通5–10且原目标完成，异常不交付、不补位，结束即停。详见[协议对齐记录](docs/消费者协议对齐修复与十消费者验证-20261110.md)。

本文件是当前代码的导航与维护约定。先理解用户本次范围，再选择所需模块；无需为普通代码阅读、文档修改或临时夹具测试重新进行历史生产审计。

WebCollect 在单机运行，按需使用同机多进程。优先用现有 Python 调用、本地 SQLite 和文件解决问题。候选独占领取复用已有短事务和唯一约束。只有明确需求或可复现的问题才引入额外机制，避免为假设的多机部署或故障重复设防。

## 近两日约定与当前实施范围（2026-11-10）

- 本轮集中实现、一次独立集成和十条固定真实验证已经结束并停止。代码采用 V12/Wiki2/完成交付新策略，但集成未完成全链，真实十条首轮协议未跑通、零业务动作和保存；没有修复重跑。新一次实施/采集不能沿用已结束的十条授权。结果见[执行记录](docs/消费者完成口径改造与十条固定验证-20261110.md)。
- 用户本轮授权按[最新方案](docs/消费者规划完成率与异常收尾优化方案-20261110.md)实施，并确认普通首次规划至少 5 步，普通候选实际 5–10 步且原目标完成，异常不交付、不补数。集中改完后新会话一次集成，Muxtly/Wiki 各 5 个消费者每人仅一条固定生产候选，结束即停，不补位、不反复修复、不恢复持续批量；全部子会话 `gpt-6.1-sol / low`。这次有界授权已执行完毕，下列“仅文档/仍在讨论”保留其较早阶段含义。
- 用户最新明确需求方拒绝 `controlled_exception`；后续客户交付与达标计数不能纳入它。异常、可信未完成片段及 UNKNOWN 继续内部留证，不删账或改标 success。旧批次允许片段的计数、旧格式检查和旧 QC PASS 不授予新交付资格；原需求原件、旧包及收据不改写。当前代码已加入新筛选，但完整真实闭环未通过，详见[需求澄清](request/需求澄清记录.md)。
- 用户已确认普通首次完整规划至少 5 步，当前预计 5–10 个必要有效动作；执行后另核实实际长度与原目标完成。剩余计划不补满五步，实际 1–4 步仍如实标 short_flow、不补普通目标，交付集合原比例上限 ≤2% 保留。新代码的接口检查已覆盖部分条件，不能将零真实产出的验证写成规划优化成功。
- 当前消费者已停止，本次有界实施和验证结束。子会话使用 `gpt-6.1-sol / low`，真实采集 GLM 保持冻结的 high/high；早先特定轮次的 sol/high、免集成或启动指令不自动延续。下一次实施仍按当次新授权范围执行。
- Wiki 允许上下滚动、目录/正文链接点击、返回与续读自由组合；不固定四次章节点击、点击比例或一律跨页立即返回。滚动后核对当前控件，必要时只重规划剩余问题，固定目标不改写。同站规划思路可复用，具体动作链不能照搬；类型序列相同只作为诊断，不替代既定重复判定。
- 总交付目标 20 万条、站点与单站容量灵活；100 站×2000 是示例，旧单应用 500 上限不恢复。客户目录逐条输出，原证据与包外日志保留。公开人物百科资料允许，真实隐私排除；登录入口仍直接排除。

聊天来源和旧新约定的覆盖关系见[近两日回顾](docs/近两日采集约定回顾-20261110.md)；当前问题、工程与 Agent 方案见[规划完成率与异常收尾优化](docs/消费者规划完成率与异常收尾优化方案-20261110.md)。上述最新需求与待实施方案分开记录，不将文档视为重启授权。

## 三角色独立接线与运行（2026-11-09）

- 生产者、消费者、QC 可以独立开发、测试、启动、停止和恢复。跨角色只通过版本化数据库契约与持久化证据交接，不依赖其他进程的内存对象、一次性函数返回值或固定启动顺序；各角色内部的 Agent goal、prompt、tool 和宿主实现可独立演进，但不得静默改变接线契约。
- 生产者读取工程 manifest、scope 和原账，可真实访问网页、调用模型，新增 Table1、Table2 与来源证据。消费者只从数据库原子领取符合条件的已有候选，写自己的 attempt、原始执行、待审样本和候选结果。QC 只审核明确指定的已保存待审样本或有效集合，审核输出和缓存写在被检查数据包之外。
- 独立启动不等于跳过业务数据前提：没有 pending 候选时消费者报告空库存，没有合格输入时 QC 为 NOT_RUN，均不得制造数据或预填 PASS。三者可单独运行，也可共用同一工程账本并行运行；测试使用隔离工程、临时数据库和独立输出，不污染正式账。
- 接线协议包括 schema 版本、candidate/claim/attempt/sample 引用、状态机与可消费条件、证据路径和哈希、manifest 绑定、UNKNOWN 与恢复规则及输出所有权，不只是 Table2 字段。上述契约变化必须显式版本化并做兼容验收；契约不变时，单一角色升级不要求另外两者同步修改。
- 保留原候选、原样本和原审核记录。消费者不改生产者原候选，QC 不改消费者原样本；原始 PNG、树、动作、失败、费用、UNKNOWN 和审核收据仍不可覆盖。

## 最短阅读路径

1. [README](README.md)：用途、环境、主流程、当前停止状态。
2. [工程说明](docs/工程说明.md)：入口、模块定位、配置、测试和故障排查。
3. [设计说明](docs/设计说明.md)：数据契约、状态机、证据绑定和交付门禁。
4. 任务涉及生产范围时，再读[当前执行入口](projects/prd/三程序计划执行入口.md)、[当前需求澄清](request/需求澄清记录.md)及其本地账本引用。

源码阅读基线是 `34afaaa`（2026-10-28）。后续提交应以实际代码为准；版本号、文档快照、旧 PASS 和旧命令不能代替当前运行证据。子程序 README 保留历史流程，单次执行的新调用链见两份工程文档。发现需求与实现不一致时如实列出，不自行降低标准。

## 先定位再改动

| 任务 | 先看 |
| --- | --- |
| 来源、页面能力、资格 | `projects/site-planner/site_planner/{pipeline,qualification,reviews}.py` |
| 任务生成、参数变体、业务身份 | `projects/code/webcollect/task_generation.py`、`task_contract.py`、对应 `*_strategy.py` |
| 动作、截图、可见终态、标签/遮挡 | `collect.py`、`browser.py`、`snapshot.js`、`media_preflight.py` |
| 编号、恢复、预算、整站停止 | `runtime.py`、`collect_runtime.py`、`storage.py`、`site_failure_stop.py` |
| 当前链、QC交接 | `current_chain.py`、`qc_handoff.py` |
| 格式、审核、抽检、审核复用 | `projects/quality-inspector/quality_inspector/{engine,format_checks,reviews,delivery_sampling,semantic,semantic_runtime}.py` |
| 导出、最终封包、跨包样本集合 | `client_package.py`、`client_reports.py`；QC 的 `delivery_pipeline.py`、`delivery_scope.py`、`cumulative.py`、`version_compare.py` |
| 跨站并发/静态分片 | `site_scheduler.py`、`batch_protocol.py`、[分片协议](projects/code/docs/static-batch-protocol.md) |

以上简写文件名均相对 `projects/code/webcollect/`，除非另注明。三个包相互通过 Python 模块与文件契约协作，没有独立 HTTP 后端。

## 修改与验证

- 新需求、方案或范围变化先讨论合理性、更简单的替代方案和取舍，再按共识规划设计；明确授权的日常实现细节无需反复确认。
- 2026-11-05 用户确定后续研发以快速实现功能、快速上线为核心：先写清必要的工程设计，再集中完成本轮所有代码更新，随后进行一次集成测试，并用稳定基线试跑。不要每改一处就反复单测、冻结或重复验收。
- 涉及 Agent 的 goal、prompt、tool 或宿主接入修改时，完成修改和集成测试后进行真实 GLM 调用，检验固定基线样本是否通过；模拟响应和单测不能作为 Agent 修改的最终验收。真实基线验证属于已授权研发范围时直接继续，不重复申请同一范围授权。
- Agent 协议/实际输出与工程文件不一致时，优先按 Agent 实际输出修复工程接入。输出字段、结构或含义改变时，prompt/tool/schema、gateway 解析、宿主校验、引用回算和保存须作为同一项改动同步更新；不能只改 Agent 后让旧校验继续拒绝。可确定等价的格式、字段别名、可选缺省和编号顺序统一整理；目标、来源与实际动作仍凭证据核对，业务歧义不静默猜测。功能正确性以原目标的实际结果和保存收据判断。
- 不允许过度设计、过度防御编程；优先复用现有模块并直接实现功能，只针对当前需求和已出现的问题修复，不为假设场景堆叠框架、兼容层或前置门禁。
- 2026-11-05 用户进一步要求：能由执行事实确定的字段由工程生成。短流程按最终有效业务动作数标记，1–4 步为 short_flow，≥5 步为普通流程，0 步不成样本；不依赖 Agent 声明、原因或计划长度。目标完成、保存与 QC 另行判断，不为长度补动作。当前先形成[复盘与实施规划](docs/长对话修复复盘与短流程工程化标记规划-20261105.md)，尚未完成全部入口的代码统一，不将规划写成已实现。
- 生产者 Table2 入口页本身确认 403 时，直接标记该页面废弃并停止派发；从可用页面跳转后遇到 403 时，优先真实返回并继续原目标，不因此废弃原可用页。保留原页面记录、失败与用量，不把单页问题扩大为整站禁用。
- 根据生产者结果讨论“消费优化”时，计划和复盘分为工程代码优化、站点挖掘 Agent 优化（goal、prompt、tool）两部分。工具的宿主实现和模型看到的协议分别说明，每部分各给问题证据和验收口径。
- 优化规划采集 Agent 时，只从当前工程的生产者 Table2（`data_candidates`）选取已发布的有效网页作真实基准。固定候选和目标，按原失败证据修复，再以该目标的可见结果和正式保存收据验收。找站、分类和补库存由生产者负责。[生产表基准与复验](docs/消费者Agent整体研发与单条真实验收实施方案-20261101.md#后续优化的生产表基准)
- 修改前运行 `git status --short`，保留已有用户改动。文档任务只修改文档。
- 首选 `rg` 定位函数与对应 `test_*.py`。三个包共同使用 `projects/code/.venv/bin/python`，2026-11-11 起统一以 `PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector` 从当前源码导入（不再安装内部发行包和控制台脚本）。
- 一次集成测试通过后进入稳定基线试跑；失败时修复实际断点，只复验相关链路，不反复跑已通过且未受影响的单测。只有定位具体问题确有需要时，才使用 [README 的选定离线验证命令](README.md#离线验证)运行最小相关用例；不默认做历史全量回归。
- 验证目录必须是新目录，测试日志、源码摘要与失败保留，不把夹具 PASS 写成真实生产 PASS。按既有正常入口完成集成和基线验证，调用前核对命令的任务范围和 I/O；`--help` 可用于核对命令，不另设与本次功能无关的前置检查。
- 文档、路径或封包改变不应自动重做 AI 审核；使用现有证据/规则绑定判断失效范围。语义检查含义改变时直接更新 `semantic.py` 当前检查实现（稳定检查名，无规则版本），并测试局部失效。
- 同时维护相关 README、工程说明和设计说明，避免复制易过期的运行统计。

## 必须保持的工程边界

- 批量生产默认状态为 `STOPPED_BY_USER`；已明确授权的集成与真实 GLM 基线验证按其范围执行，不因该历史默认状态重复请示。普通文档维护不启动真实调用；有界研发试跑不自动扩大为批量生产、人工服务或定时任务。
- 新候选工程使用 `candidate-project-2` 的 manifest、专库、候选池及结果目录。同一工程跨进程、批次和重启共用这些绑定。R02/R03 等旧试点限定在原 `current-chain-r01` 上复盘。
- 新任务走单次执行保存待审证据，不增加完整演练/独立准入的强制前置。旧任务带有准入收据时仍核验其原绑定，不能删除字段绕过。
- 采集成功最多到 `collected_pending_review`；`reviewed_pass`、`published`、客户验收各自有证据。不能手写审核、预填人工 PASS 或把 `NOT_SELECTED` 写成已看图。
- 编号预留不回收；中断轨迹不拼接；原始 PNG、树、动作、失败、费用和审核记录不覆盖。UNKNOWN 请求先核对原账，不能靠新作业或新账重发。
- 新工程按任务独占，允许同页不同目标，站点失败按次记账，三次失败后仍可派发。旧试点保留原页面占用与三次停止规则。当前工程的未决执行、原请求对账、资源计量和样本去重仍依原账处理。批次累计用量只记账。2026-11-09 用户取消当前消费者全部旧配额，当时采用 continuous ending V4；2026-11-10 新任务另采用 `webcollect-five-ten-effective-ending-5`，累计最多 10 个有效动作，属于后来明确的单轨迹工程策略。调用次数、会话总时长、固定节流和跨候选账户占位等旧配额仍不恢复；旧任务按原版本解释，原 UNKNOWN 不重发。获授权启动后按当次显式范围和目标结束，用户停止立即生效；客户输出为 `delivery/yyyyMMddHHmm/`，准入按上述最新澄清。[额度限制清单](docs/额度限制清单与取消说明-20261101.md)[切换依据](docs/历史门禁审查与新工程切换-20261101.md)
- `BatchLedger` 作业/模型账与生产 `RuntimeStore` 编号/尝试账各有职责，不能互相替代。当前链 manifest 不是可随意重建的配置。
- QC 输出、审核收据和缓存写在被检查数据包之外；finalize/archive 必须绑定显式有效集合和跨包报告。
- 不读取或输出凭据。不提交 `results/`、`verify_results/`、真实投影夹具、原始请求、SQLite、ZIP 和登录状态。历史原件及收据引用目录保留，退役清理脚本不是删除授权。

完成时说明实际改动、已运行检查及未验证边界；涉及进度时分别报告尝试、采集、待审、终审合格、发布和缺额，不把代码能力折算为产量。

- 2026-11-09 用户确认：登录页面直接排除，不作为可消费入口。生产者在用途模型前及发布前拒绝；消费者首帧确认登录页时直接 abandon，不继续规划、模型调用或正式 attempt。登录页上有公开链接不构成放行理由；保留原页、原观察、claim、失败及费用。
