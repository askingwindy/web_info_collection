# Table2 策略2：100次采集日志

本轮使用固定100个Table2候选、策略2、最多20个并发消费者进程。100个候选均已发起消费尝试，全部进程已退出；正式保存0条。此目录按用户授权独立纳入Git，不属于 `delivery/`、`results/` 或 `verify_results/`。

执行代码最后提交为 `6fa9c93c820771461e6486d38452152f841e6696`。工程修复、验证和完整经过见[运行记录](../../docs/Table2策略2百次采集运行记录-20261118.md)。

## 最终结果

| 项目 | 结果 |
|---|---:|
| 唯一候选 / 唯一claim | 100 / 100，跨43站 |
| 并发峰值 / 历次worker实例 | 20 / 80 |
| 最终claim状态 | 43 failed、57 reconcile、0 consuming |
| 完成首帧 / 已选模板 | 70 / 69 |
| 正式attempt | 29，全部rejected |
| 发出模型HTTP的候选 / 初始计划通过 | 28 / 13 |
| 至少5个有效步骤 | 4 |
| 原目标完成证明 / 正式保存 / 导出 | 0 / 0 / 0 |
| 本轮消费者模型HTTP | 103：83 succeeded、20 invalid_response |
| 本轮模型UNKNOWN / reserved | 0 / 0 |
| 输入 / 输出tokens | 2,062,007 / 76,226 |
| 费用 | UNKNOWN |
| 证据完整性 | FAILED：unsettled_claims |
| QC / 人工审核 / 验收 | NOT_RUN / NOT_RUN / UNKNOWN |

采集策略准确度未调整。模型HTTP全部结算不代表动作结果全部已知；动作UNKNOWN、失败及未闭合证据保持原结论。无样本发布。

## 从哪里读

- [final-accounting.json](final-accounting.json)：最终100条状态、模型用量和汇总漏斗。
- [candidate-results.jsonl](candidate-results.jsonl)：每候选一行，共100行；包含站点、入口、最终claim状态、原生漏斗状态和消费者请求用量。最终claim来自精确限定本轮80个worker的只读查询，其余字段投影自冻结名单与原生报告；未知值不补零。
- [run-05/funnel.md](run-05/funnel.md) / [funnel.json](run-05/funnel.json)：跨run-02至run-05的原生自动报告，含逐候选证据路径与行号。
- 各 `run-*/w*.log`：80个真实worker的标准输出及错误日志；`runtime/*/runtime.jsonl`、`model-calls.jsonl`：会话事件与不含请求正文的模型调用记录。
- 各 `failure-events.jsonl`、`controller-exit.json`、`summary.json`：故障处置、停止与进程退出。`run-01`预检没有启动worker，其控制器退出记录保留在根目录。
- [protected-final.json](protected-final.json)、[run-04/historical-attempt-transitions.json](run-04/historical-attempt-transitions.json)、[historical-task-changes.json](run-04/historical-task-changes.json)、[historical-recovery-events.json](run-04/historical-recovery-events.json)：历史账发生变更的审计；[final-no-further-drift.json](final-no-further-drift.json)是修复后未继续漂移的核查。
- [final-reconciliation/receipt.json](final-reconciliation/receipt.json)与[claim-state-changes.json](final-reconciliation/claim-state-changes.json)：最后一条过期claim定向核账回执，无新请求或重放。
- [final-process-exit.json](final-process-exit.json)：426个已观察到的自有进程PID退出核查。`run-04`、`run-05`另有进程采样与运行前后源码提交记录。
- [archive-manifest.json](archive-manifest.json)：270份原样日志副本与3份明确标注的字段投影的来源、大小和未上传范围；[archive-check.json](archive-check.json)：本次归档核验结果。

## 运行段与故障

| 运行段 | 首次领取 | worker数 | 结束原因 |
|---|---:|---:|---|
| run-01 | 0 | 0 | 预检发现共享源码变动，迁入独立工作区 |
| run-02 | 20 | 20 | 几何能力拒绝误归工程故障；停止后修分类和报表开销 |
| run-03 | 27 | 20 | 截图同步拒绝、锁等待、历史读取开销；停止后修工程链路 |
| run-04 | 31 | 20 | DNS子进程崩溃；停止后改spawn并收窄历史恢复范围 |
| run-05 | 22 | 20 | 剩余分片耗尽，20个worker均正常退出 |

各段共用同一固定100名单，重启跳过已领取项，没有补位或重发旧UNKNOWN。run-02自动报表中断的失败收据原样保留，修复后另生成 `funnel-rebuilt.*`。

## 核账边界

最终自动漏斗读取早于最后一次claim核账，可能仍含1条consuming；最终状态以 `final-accounting.json` 与 `candidate-results.jsonl` 的43 failed、57 reconcile为准。原自动报告不改写，`integrity=FAILED`保留。

原生漏斗的总来源请求420笔，包含317笔Table2来源的历史producer请求和本轮103笔consumer请求。历史producer中的1笔reserved保留，不能把420笔写成本轮新增调用。

run-04曾将8条旧reserved attempt改为abandoned，关联8条历史任务也改变。因此原保护核查为FAIL；修复后未继续变化的PASS仅针对后续漂移，不抵消原异常。没有回写旧状态，也没有重新执行这些历史项。旧807条claim、消费者43条UNKNOWN、生产者19条UNKNOWN及2条reserved保持原账。

## 归档说明

原件根目录为 `/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/`。270份日志保持原字节，原绝对路径和错误原件引用保留；对应当前运行根下的路径可按相同相对路径在本目录查找。指向截图、模型请求正文、数据库或其它历史目录的路径仍依赖本地原件，Git日志不是完整证据包。

历史任务的完整大行仅投影实际变更字段；最后一条claim的前后行仅投影身份与状态，省略完整来源和过期租约token。3份投影均在清单中单独标注，不冒充原始行。完整来源、重复cohort、原始请求、截图、数据库及约23GB数据库备份不纳入此归档。凭据和浏览器登录状态不上传。

本次只归档与推送既有运行事实，不新增采集、模型请求或数据库写入。其它工作区未提交的策略3改动不包含在此归档中。
