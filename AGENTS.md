# Agent 接手说明

本文件是当前代码的导航与维护约定。先理解用户本次范围，再选择所需模块；无需为普通代码阅读、文档修改或临时夹具测试重新进行历史生产审计。

WebCollect 在单机运行，按需使用同机多进程。优先用现有 Python 调用、本地 SQLite 和文件解决问题。候选独占领取复用已有短事务和唯一约束。只有明确需求或可复现的问题才引入额外机制，避免为假设的多机部署或故障重复设防。

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
| 导出、最终封包、跨包版本 | `client_package.py`、`client_reports.py`；QC 的 `delivery_pipeline.py`、`delivery_scope.py`、`cumulative.py`、`version_compare.py` |
| 跨站并发/静态分片 | `site_scheduler.py`、`batch_protocol.py`、[分片协议](projects/code/docs/static-batch-protocol.md) |

以上简写文件名均相对 `projects/code/webcollect/`，除非另注明。三个包相互通过 Python 模块与文件契约协作，没有独立 HTTP 后端。

## 修改与验证

- 根据生产者结果讨论“消费优化”时，计划和复盘分为工程代码优化、站点挖掘 Agent 优化（goal、prompt、tool）两部分。工具的宿主实现和模型看到的协议分别说明，每部分各给问题证据和验收口径。
- 优化规划采集 Agent 时，只从当前工程的生产者 Table2（`data_candidates`）选取已发布的有效网页作真实基准。固定候选和目标，按原失败证据修复，再以该目标的可见结果和正式保存收据验收。找站、分类和补库存由生产者负责。[生产表基准与复验](docs/消费者Agent整体研发与单条真实验收实施方案-20261101.md#后续优化的生产表基准)
- 修改前运行 `git status --short`，保留已有用户改动。文档任务只修改文档。
- 首选 `rg` 定位函数与对应 `test_*.py`。三个包共同使用 `projects/code/.venv/bin/python`；未安装包时设置 `PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector`。
- 使用 [README 的选定离线验证命令](README.md#离线验证)，按改动更换 `--module`。验证目录必须是新目录。测试日志、源码摘要与失败保留，不把夹具 PASS 写成真实生产 PASS。
- 默认只跑修改模块及直接受影响调用链的用例，不做全量回归；公共契约变更、失败或未解决问题需要扩大时，先说明具体原因。仅提交已验证代码时不重复跑未受影响测试。
- 不默认运行历史全量测试、浏览器集成脚本、`model-smoke`、worker `run`、scheduler 或生产 CLI。先确认任务范围和 I/O；`--help` 可用于核对命令。
- 文档、路径或封包改变不应自动重做 AI 审核；使用现有证据/规则绑定判断失效范围。语义检查意义改变时更新 `semantic.py` 对应规则版本，并测试局部失效。
- 同时维护相关 README、工程说明和设计说明，避免复制易过期的运行统计。

## 必须保持的工程边界

- 当前生产状态为 `STOPPED_BY_USER`；没有用户明确恢复指令时，不启动采集、真实模型请求、人工服务或定时任务。普通源码/文档维护不代表恢复授权。
- 新候选工程使用 `candidate-project-2` 的 manifest、专库、候选池及结果目录。同一工程跨进程、批次和重启共用这些绑定。R02/R03 等旧试点限定在原 `current-chain-r01` 上复盘。
- 新任务走单次执行保存待审证据，不增加完整演练/独立准入的强制前置。旧任务带有准入收据时仍核验其原绑定，不能删除字段绕过。
- 采集成功最多到 `collected_pending_review`；`reviewed_pass`、`published`、客户验收各自有证据。不能手写审核、预填人工 PASS 或把 `NOT_SELECTED` 写成已看图。
- 编号预留不回收；中断轨迹不拼接；原始 PNG、树、动作、失败、费用和审核记录不覆盖。UNKNOWN 请求先核对原账，不能靠新作业或新账重发。
- 新工程按任务独占，允许同页不同目标，站点失败按次记账，三次失败后仍可派发。旧试点保留原页面占用与三次停止规则。当前工程的未决执行、原请求对账、资源计量和样本去重仍依原账处理。批次累计用量只记账。单次规划采集会话最多派发 25 次真实 GLM 调用，到限时记录原 attempt 与原因。[额度限制清单](docs/额度限制清单与取消说明-20261101.md)[切换依据](docs/历史门禁审查与新工程切换-20261101.md)
- `BatchLedger` 作业/模型账与生产 `RuntimeStore` 编号/尝试账各有职责，不能互相替代。当前链 manifest 不是可随意重建的配置。
- QC 输出、审核收据和缓存写在被检查数据包之外；finalize/archive 必须绑定显式有效集合和跨包报告。
- 不读取或输出凭据。不提交 `results/`、`verify_results/`、真实投影夹具、原始请求、SQLite、ZIP 和登录状态。历史原件及收据引用目录保留，退役清理脚本不是删除授权。

完成时说明实际改动、已运行检查及未验证边界；涉及进度时分别报告尝试、采集、待审、终审合格、发布和缺额，不把代码能力折算为产量。
