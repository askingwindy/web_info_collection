# WebCollect

WebCollect 是中文网页操作轨迹的采集、审核和交付工程。它用 Playwright 执行真实页面操作，保存原始截图、同步界面树、动作与终态证据，再由独立质检器检查实际交付文件，输出可追溯的客户数据包。

仓库包含三个 Python 程序：`site_planner` 负责来源发现与页面能力库存，`webcollect` 负责任务规划、采集和导出，`quality_inspector` 负责独立质检、AI/人工审核接入及交付门禁。

## 从哪里开始

| 阅读目的 | 入口 |
| --- | --- |
| 首次了解代码、环境、命令与测试 | [工程说明](docs/工程说明.md) |
| 理解数据流、状态机、恢复与审核设计 | [设计说明](docs/设计说明.md) |
| 后续 agent 快速接手 | [AGENTS.md](AGENTS.md) |
| 确认当前任务范围与停止状态 | [当前执行入口](projects/prd/三程序计划执行入口.md)、[试点执行说明](projects/prd/真实试点执行说明-20261028.md) |
| 查需求与交付合同 | [当前澄清](request/需求澄清记录.md)、[原需求书](request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md)、[字段附件](request/web操作采集需求/附件A-字段说明.md)、[动作附件](request/web操作采集需求/附件B-动作空间与坐标系.md) |

技术说明以 **2026-10-28 的源码提交 `34afaaa`** 为阅读基线。子程序 README 保留较多历史命令和批次记录；当前调用关系优先看本页和两份新说明，运行授权与需求仍以用户当前指令及需求文件为准。

## 当前状态与范围

当前试点为 `pilot1000-20261028-r01 / current-chain-r01`，目标 1000 条新增真实合格轨迹，先完成首条闭环，100 条为报告检查点。文档核对时，本地进度账为 `STOPPED_BY_USER`，新增采集、终审合格、待审均为 0。最新源码改造有离线验证记录，尚不能据此宣称真实链路或规模生产已通过。

当前代码采用**单次执行采集、独立后置质检**：仍有只读页面预检，但普通新任务不再必须先完整演练、独立准入后再重放。旧准入/观察轨迹入口继续兼容；不能把其旧流程说明当作新入口的必经步骤。参见[源码修复记录](projects/code/REPAIR_PLAN.md)。

本次文档整理不恢复采集或模型服务。实时事实入口仅在本机存在：

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

- 每个实际任务页面最多一条有效轨迹，当前任务要求 5–10 个必要操作，`wait` / `complete` 不计有效步数；终态必须有可见证据。
- 当前链审核、去重、验收和产量只使用绑定本轮 manifest 和专库的结果；候选、待审、合成测试及旧数据不计新增合格量。
- 同一整体应用累计三次真实失败即停止派发；换页、参数、目录或重启不清零。UNKNOWN 保持待核实，不自动重发或记为零费用。
- 原图、同步树、动作、编号、失败和审核证据保留；修订生成新版本与绑定，不能改签旧结论。源码、纯测试和当前说明入 Git，样本、请求、凭据、SQLite 与 ZIP 留本地。

细分命令与历史说明见[采集程序](projects/code/README.md)、[站点规划](projects/site-planner/README.md)、[独立质检](projects/quality-inspector/README.md)。
