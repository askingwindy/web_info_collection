# WebCollect

2026-10-30 新增[规划采集 agent 闭环](docs/规划采集Agent闭环-20261030.md)：`agent-model` / `site_rolling --controlled` 使用可信三态观察、原执行/QC反馈及有预算的短计划控制循环；新片段协议直接采5–8实际有效动作，复用原账、采集和独立QC，成功仍仅待审。旧冻结协议与恢复门禁保留。本轮仅代码和离线验证，真实小批方案待范围明确后执行。下文同日较早的“仅文档”说明保留为历史状态。

2026-10-30最新QC方案采用[全量程序检查＋AI抽检与批次计数](docs/QC抽检与批次合格计数方案-20261030.md)：基础随机10%，启动前10条、新组前5条及风险样本必审；普通问题扩至30%，再发现问题或严重/系统性问题则全检相关范围。今日1000和最终20万按实际程序检查、累计指标与批次接纳后的有效片段计数；未抽中可按批次接纳，但不记为逐条AI审核。当前只更新文档，尚未实现新策略或启动运行。

2026-10-30今日目标是1000条有效片段，最终目标20万条，见[今日与最终目标共用的程序规划](docs/今日1000条与20万条量产程序规划-20261030.md)。主线为发现站点、站级规划/采集反馈循环、独立批次QC；今日先直接5–8步采集并形成小批流水，自动切段保持后续兼容。首条和10/50/100条只是检查点。当前仅更新规划文档，未据此改代码、调整原policy或启动运行。

2026-10-30最新[轨迹口径补充](request/轨迹采集口径补充-20261030.md)：动作直接按附件B定义，规划核心为动作合法、满足5步和重复度达标，不增加单页业务完整性或额外业务必要性门槛。连续浏览和多轮工具操作可采，主要按5–8实际动作形成片段，同页可多条，10动作可切2段；静态阅读不另计步，切段共享边界单独统计。已撤回“20万条至少需20万个任务页”的推算。[快采方案](docs/20万条快速采集量产方案-20261030.md)及[P0第11节](docs/P0快速闭环实施计划-20261030.md#11-最新轨迹口径对齐2026-10-30未实施)已对齐文档；代码与QC规则尚未因此同步，本次只改文档，不启动生产。

2026-10-30 当前讨论已整理为[20万条快速采集量产方案](docs/20万条快速采集量产方案-20261030.md)和[P0快速闭环实施计划](docs/P0快速闭环实施计划-20261030.md)。优先修能力登记、业务条件与动作的分离、规划诊断，先验证首条及5–10条小批；通用多页框架与规模平台后移。本轮按最新指令实施 P0-1 至 P0-3 及必要执行前断言，仅做离线验证；未启动真实采集或模型请求。实施结果与首条缺口见 P0 文档的实施记录；下文旧运行授权与快照保留为历史。

2026-10-30 网站规划修复与 GLM 交互新版见[实施与验收记录](docs/网站规划与GLM交互修复-20261030.md)。原三站的 SOURCE_FAILED 和 UNKNOWN 保留；旧 C01–C18 关闭结论须结合本次后继修正读取。工程、真实验证和规模适用性分别报告。


2026-10-29最新运行授权和阻塞以[同站双功能与20站最小执行](docs/同站双功能与20站最小执行-20261029.md)为准：最多40次正式尝试，沿用原账；双功能真实验证先于后续生产。当前GLM 401导致真实资格/QC受阻，20站观察规划草案不能当作已合格来源或新增产量。

共享站点池与仅给类目的GLM发现入口见[共享站点池与自主发现](docs/共享站点池与自主发现.md)。GLM和Codex发现共用入池/去重，程序2以 `webcollect site-pool` 只读读取；此支路不启动轨迹采集。

共享池现支持按页面/任务自动回写采集与独立QC状态：来源资格目录绑定原池，正式执行将生产账状态同步到池，QC消费原交接收据后登记结果。默认候选读取排除在途、待审和审核通过的页面，同站其他功能页可继续；失败及同步中断保留原记录。当前改造只做离线验证，不代表恢复生产，详见[状态回写与防重](docs/共享站点池与自主发现.md#状态回写与防重)。

模型双链路新增火山方舟 `provider=ark`：首选 [Ark GLM 配置](projects/code/config/batch-ark-glm.example.json)，备选 [Ark DeepSeek 配置](projects/code/config/batch-ark-deepseek.example.json)，原智谱 GLM 通道继续保留。接入及切换方式见[采集程序模型接口](projects/code/README.md#火山方舟-ark-双链路2026-10-29)。配置示例仅允许一次联通请求，不授权恢复生产或重发旧 UNKNOWN。

Ark当前首选 `glm-5-3-flash-260828`，备选已按用户指令切换为 `deepseek-v4-1-flash-economy-261017`，两者均已有原PNG输入、严格JSON、模型版本和usage的真实联通证据。现有 `request/token.yaml` 通过显式 `model.api_key_file` 读取 `ark1`，兼容严格YAML及顶层旧标签格式；不修改密钥文件。当前证据见[经济版与凭据格式复验](verify_results/ark-integration-20261029-live-r06-economy-format/复验报告.md)，GLM证据见[开通后复验](verify_results/ark-integration-20261029-live-r03/复验报告.md)，首次失败见[原接入报告](verify_results/ark-integration-20261029-live-r01/接入报告.md)。旧UNKNOWN原账保留，联通成功不代表恢复发现、采集或审核。

WebCollect 是中文网页操作轨迹的采集、审核和交付工程。它用 Playwright 执行真实页面操作，保存原始截图、同步界面树、动作与终态证据，再由独立质检器检查实际交付文件，输出可追溯的客户数据包。

仓库包含三个 Python 程序：`site_planner` 负责来源发现与页面能力库存，`webcollect` 负责任务规划、采集和导出，`quality_inspector` 负责独立质检、AI/人工审核接入及交付门禁。

## 从哪里开始

| 阅读目的 | 入口 |
| --- | --- |
| 首次了解代码、环境、命令与测试 | [工程说明](docs/工程说明.md) |
| 理解数据流、状态机、恢复与审核设计 | [设计说明](docs/设计说明.md) |
| 查看AI抽检比例、扩检及1000/20万合格计数 | [QC抽检与批次合格计数方案](docs/QC抽检与批次合格计数方案-20261030.md) |
| 查看20万条快采分工、最小P0与真实验收顺序 | [快速采集量产方案](docs/20万条快速采集量产方案-20261030.md)、[P0实施计划](docs/P0快速闭环实施计划-20261030.md)，含本轮实施记录 |
| 查看后续规划、稳定性修复和批次QC优化 | [统一优化方案](docs/WebCollect统一优化方案-20261029.md)，方案不代表实现或运行授权 |
| 后续 agent 快速接手 | [AGENTS.md](AGENTS.md) |
| 确认当前任务范围与停止状态 | [当前执行入口](projects/prd/三程序计划执行入口.md)、[试点执行说明](projects/prd/真实试点执行说明-20261028.md) |
| 查需求与交付合同 | [当前澄清](request/需求澄清记录.md)、[原需求书](request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md)、[字段附件](request/web操作采集需求/附件A-字段说明.md)、[动作附件](request/web操作采集需求/附件B-动作空间与坐标系.md) |

技术说明以 **2026-10-28 的源码提交 `34afaaa`** 为阅读基线。子程序 README 保留较多历史命令和批次记录；当前调用关系优先看本页和两份新说明，运行授权与需求仍以用户当前指令及需求文件为准。

## 当前状态与范围

最新授权已进入[今日单条真实闭环计划](docs/今日单条真实闭环计划-20261029.md)：设计实施后自主测试与修复，范围限1条真实采集和独立QC，复用原当前链与失败账；不扩到15条或批量生产。入口为 `python -m webcollect.single_record --help`。

该单条已完成真实采集及独立QC，运行证据、修复和费用见[本轮完成报告](verify_results/single-record-20261029-r01/完成报告.md)。后续不自动扩批或发布。

本轮（2026-10-29）的最新授权范围是共享站点池工程改造及真实GLM站点发现验证，不启动任务生成或轨迹采集。入口与边界见[共享站点池与自主发现](docs/共享站点池与自主发现.md)；以下此前端到端授权记录保留为历史，不作为本轮采集派发指令。

当前试点为 `pilot1000-20261028-r01 / current-chain-r01`，目标 1000 条新增真实合格轨迹，先完成首条闭环，100 条为报告检查点。文档核对时，本地进度账为 `STOPPED_BY_USER`，新增采集、终审合格、待审均为 0。最新源码改造有离线验证记录，尚不能据此宣称真实链路或规模生产已通过。

当前代码采用**单次执行采集、独立后置质检**：仍有只读页面预检，但普通新任务不再必须先完整演练、独立准入后再重放。旧准入/观察轨迹入口继续兼容；不能把其旧流程说明当作新入口的必经步骤。参见[源码修复记录](projects/code/REPAIR_PLAN.md)。

2026-10-29 本线程已授权有限一致性修复：先[逐项修复与核对](docs/需求一致性修复计划-20261028.md)和离线测试，满足后仅运行一条真实端到端，再五站各三条。此授权不扩至100/1000条，也不重建当前链或止损账。上述 `STOPPED_BY_USER` 是此前账本快照，具体阶段以本次验证记录为准。

上轮文档整理未恢复采集或模型服务，本次有限授权见上节。实时事实入口仅在本机存在：

- 进度：`verify_results/pilot1000-20261028-r01/progress.json`。
- 当前链 manifest：`verify_results/pilot1000-20261028-r01/current-chain-r01/manifest.json`。
- 生产专库：`results/pilot1000-20261028-r01/state/production-registry.sqlite3`。
- 整站失败账的实际路径：从冻结的 `policy.site_failure_guard` 及本轮进度引用读取。

这些目录不入 Git；新克隆不含生产证据，不能仅凭代码和本页快照恢复生产。

## 工程结构

```text
WebCollect/
├── AGENTS.md                         # agent 接手约定与代码导航
├── docs/                             # 工程说明、设计说明
├── request/                          # 需求、澄清、动作/字段合同
├── projects/
│   ├── code/
│   │   ├── webcollect/                # 采集核心、账本、任务策略、导出
│   │   ├── config/                    # 运行配置模板
│   │   ├── scripts/                   # 离线验证及历史兼容工具
│   │   └── tests/                     # unittest 回归
│   ├── site-planner/
│   │   └── site_planner/              # 发现、探测、能力审核
│   ├── quality-inspector/
│   │   └── quality_inspector/         # 独立QC、抽检、审核、发布校验
│   └── prd/                          # 当前执行入口及工程记录
├── results/                          # 本地产物、原图、生产账本；忽略
└── verify_results/                    # 本地验证、审核、失败/费用证据；忽略
```

## 安装与查看入口

在仓库根目录执行。三个包声明 Python ≥3.11；现有依赖锁定文件记录的是 Python 3.14.4/macOS 环境，其他平台需另验依赖兼容性。浏览器采集默认使用本机 Chrome，Playwright Chromium 也可由底层参数选择；只阅读代码或运行纯离线测试无需安装浏览器。

```sh
python3 -m venv projects/code/.venv
projects/code/.venv/bin/python -m pip install -r projects/code/requirements.lock
projects/code/.venv/bin/python -m pip install --no-deps \
  -e projects/code -e projects/site-planner -e projects/quality-inspector
```

安装后三个包共用同一虚拟环境。以下只显示帮助，不访问网站或模型：

```sh
projects/code/.venv/bin/python -m site_planner --help
projects/code/.venv/bin/python -m webcollect --help
projects/code/.venv/bin/python -m webcollect.task_generation execute --help
projects/code/.venv/bin/python -m webcollect.qc_handoff --help
projects/code/.venv/bin/python -m quality_inspector --help
projects/code/.venv/bin/python -m quality_inspector.delivery_pipeline --help
```

没有 editable 安装时，可在命令前加 `PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector`。生产命令所需计划、manifest、账本和审核记录必须来自实际绑定输入；配置模板不能直接充当运行授权。

## 主流程

```mermaid
flowchart LR
    A[来源发现与能力库存] --> B[任务生成与冻结]
    B --> C[只读预检与计划发布]
    C --> D[单次执行采集]
    D --> E[完整待审证据与候选包]
    E --> F[全量机械检查]
    F --> H[冻结有效集合与跨包检查]
    H --> G[显式AI和人工抽检]
    G --> I[payload检查与final封包复验]
    I --> J[ZIP及校验文件]
```

`webcollect.task_generation.execute()` 编排预检、发布、采集、候选导出；传入显式 `qc_policy` 时冻结后续 QC 输入。`quality_inspector.delivery_pipeline` 承接审核与封包。采集入口只保存 `collected_pending_review`；审核通过、正式发布和客户验收分别记录。默认 `quality_inspector check` 要求完整语义证据，抽检必须显式传入冻结计划。

`generate --workflow-specs` 可消费绑定原始PNG/树的显式DOM工作流提案，覆盖已观察控件的导航查询、非form工具与DOM交互；无需先执行完整流程。它与表单策略共用 `execute`，不支持的动态目标/画布游戏仍显式拒绝。终态滚动可用 `webcollect-live-completion-view-1` 在本次实际截断结果上核验必要性；旧准入绑定仍按原协议验证。两者均不授予质量通过。

## 离线验证

优先选择受影响测试，使用现有验证器生成源码绑定报告。以下命令只运行选定的临时夹具测试；输出目录必须尚不存在，复跑时换一个后缀：

```sh
PYTHONDONTWRITEBYTECODE=1 projects/code/.venv/bin/python -B \
  projects/code/scripts/verify_current_offline.py \
  --output verify_results/docs-offline-check-r01 \
  --module test_single_execution_path \
  --module test_qc_handoff \
  --module test_three_layer_sampling_policy \
  --module test_semantic_reuse
git diff --check
```

验证器输出 `tests.log`、`summary.json`，检查验证前后源码是否一致，并禁止读取旧样本、生产 `results/` 和凭据目录。它不替代网络隔离，所选测试本身也必须使用临时夹具及模拟外部 I/O。全仓库历史测试含本机证据依赖，不宜把全量 discovery 作为新克隆的默认验收命令。

## 数据与维护原则

- 最新需求以[轨迹口径补充](request/轨迹采集口径补充-20261030.md)为准：同页允许多轮操作和多个片段，主要按5–8个实际动作计步，10动作可切2段；静态阅读、wait/complete不另计步。记录真实片段末状态，不强制完整业务完成；切段共享边界单列。执行器与QC旧规则仍待对齐。
- 当前链审核、去重、验收和产量只使用绑定本轮 manifest 和专库的结果；候选、待审、合成测试及旧数据不计新增合格量。
- 同一整体应用累计三次真实失败即停止派发；换页、参数、目录或重启不清零。UNKNOWN 保持待核实，不自动重发或记为零费用。
- 原图、同步树、动作、编号、失败和审核证据保留；修订生成新版本与绑定，不能改签旧结论。源码、纯测试和当前说明入 Git，样本、请求、凭据、SQLite 与 ZIP 留本地。

细分命令与历史说明见[采集程序](projects/code/README.md)、[站点规划](projects/site-planner/README.md)、[独立质检](projects/quality-inspector/README.md)。


2026-10-29工程实施增补：见[统一优化实施记录](docs/统一优化实施记录-20261029.md)。新增通用模型规划与冻结队列、严格页面/多图协议、结构化重取证、版本化局部边框规则及显式批次QC准备；原single_record首关100%策略、旧FAIL、UNKNOWN、原账及停止事实保持。新增能力仅完成局部离线验证，真实链路及规模能力待新授权验证；历史规划快照不作为本次生产授权。


2026-10-29后续工程交付：[C01–C18关闭状态与验收](docs/C01-C18关闭状态-20261029.md)。补齐跨目录原件合批、受影响流程扩检、保存/索引及合批中断恢复、原生离线绘制反例；用户已授权提交本地main后执行3站新批次，沿用原manifest与生产库。旧停站先据证据追加复核，仅经本次显式运营授权应用工程更正，不删除旧失败或重发UNKNOWN。工程关闭与真实验证状态分别记录。
