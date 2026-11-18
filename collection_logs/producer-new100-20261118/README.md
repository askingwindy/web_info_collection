# 新站生产者：故宫 100 页运行归档

2026-11-18 用户授权使用修复后的代码挖掘新站点并把运行日志纳入 Git。本轮在故宫博物院官网 `www.dpm.org.cn` / `dpm.org.cn` 新增 1 个站点、100 个 Table2 候选；独立只读核账确认相对原 4,284 个候选净新增 100，100 个实际落地 URL 唯一，500 份引用文件核验通过。全部 4 个 worker 与 2 个控制器已退出，运行耗时 1,731.952 秒。

## 结果与边界

| 指标 | 实际结果 |
|---|---:|
| 本轮候选批次行 | 170 |
| NEW / REJECTED / DUPLICATE / OVER_LIMIT | 100 / 40 / 29 / 1 |
| 净新增候选 / 唯一实际落地 / 引用核验 | 100 / 100 / 500 |
| 模型 HTTP | 25：22 succeeded、3 invalid_response |
| 输入 / 输出 token | 232,243 / 17,214 |
| 模型费用 | UNKNOWN：25 笔均缺实际费用 |
| GET | 219：212 succeeded、5 failed、2 unknown |
| 旧保护行 / 239 个产品文件 | 均未改变 |
| 后续同 URI 请求 / 相关残留进程 | 0 / 0 |

费用字段 `known_cost_micros=0` 仅表示已知费用之和为 0，不能写成总费用为 0。2 个网页 GET UNKNOWN 保持原状态，没有随后对同 URI 再派发。此次是生产者候选供给结果，不代表消费者采集样本、QC、人审或交付通过；本轮没有启动消费者或 QC，human_review=NOT_RUN，published=false。

四个 worker 的 NEW 分别为 42、17、21、20。它们共用站点总目标 100；达到共享目标后，控制器写公共停止标记，因此每个 worker 都保留 PARTIAL、BudgetStop 和退出码 2。原 `controller-exit.json` 中 `target_reached=false` 只按该 worker 退出码计算，原件没有被改写。**整体 100 页完成由 final-audit.json 的独立核账证明，不能用四个 worker 的各自 deficit 相加判断本轮缺额。**

## 阅读入口

- [final-audit.json](final-audit.json)：最终只读核账 PASS、100 页计数、请求用量、旧保护行、源码与进程核对。
- [page-results.jsonl](page-results.jsonl)：100 个 NEW 候选的入口、实际落地、语言与 GET 证据、5 类引用；不含页面正文或原始请求正文。
- [candidate-batch-rows.jsonl](candidate-batch-rows.jsonl)：全部 170 行的元数据投影，包含 row_id、result、reason、entry_url、candidate_id、request_id 及原批次定位字段。40 个 REJECTED 保留 `simplified_chinese_not_evidenced`；1 个 OVER_LIMIT 保留共享上限原因；29 个 DUPLICATE 原 reason 为 null，保持 null。这里的 request_id 是原批次行保存的生产者 job 身份，不冒充模型请求 ID。
- [workers/producer-01.log](workers/producer-01.log)、[02](workers/producer-02.log)、[03](workers/producer-03.log)、[04](workers/producer-04.log)：明确标为 `explicit-field-projection` 的 worker 结果，保留各自范围、数量、状态和停止原因，以及原 stdout 路径、大小、SHA256。
- [launch-plan.json](launch-plan.json)、[active-run.json](active-run.json)、[expansion-plan.json](expansion-plan.json)、[expansion-active.json](expansion-active.json)：初始 1 worker 与之后扩到 4 worker 的原计划和启动事实。
- [controller-exit.json](controller-exit.json)、[expansion-exit.json](expansion-exit.json)、[final-process-check.json](final-process-check.json)：原退出状态和最终无残留进程核查。
- [unknown-followup-check.json](unknown-followup-check.json)：2 个 UNKNOWN 页及随后同 URI 派发为 0 的核查。
- [issues.jsonl](issues.jsonl)、[progress.jsonl](progress.jsonl)、[status-latest.json](status-latest.json)、[只读观察记录](readonly-observer-first-progress.md)：实际过程、问题与早期观察，保留各自时间含义。
- [baseline-counts.json](baseline-counts.json)、[protected-before.json](protected-before.json)、[source-before.json](source-before.json)、[source-after.json](source-after.json)：基线数量投影与原保护/源码摘要。没有上传 4,284 个旧候选 ID 清单。
- [archive-manifest.json](archive-manifest.json)、[archive-check.json](archive-check.json)：复制与投影白名单、来源和摘要、遗漏范围及归档核验结果。

## 审计脚本首轮错误保留

首次 smoke 审计把 `candidate_sources.source.run_id` 误当完整批次 run_id；实际字段保存工程 producer ID。该错误使审计读者找不到对应来源，原回执为 IN_PROGRESS、verified_pages=0，并列出 864 个衍生问题。修正的是审计脚本读取关系，未修改生产者或候选原账。

[r01 汇总投影](audit-smoke-r01/final-audit-summary.json)保留原状态和问题分类计数；[r02](audit-smoke-r02/final-audit-summary.json)校验当时的 76 页/380 引用；[r03](audit-smoke-r03/final-audit-summary.json)校验当时的 100 页/500 引用。两次后续 smoke 均无审计问题，但当时进程尚未全部退出，仍为 IN_PROGRESS。最终进程退出后的 PASS 以 final-audit.json 为准。各次重复 page-results 未再次复制。

## 归档方式

原件位于 `results/producer-new100-20261118-r01/`。本目录包含 26 份逐字节原样副本和 9 份明确标注的字段投影，合计 510,019 字节；另新增本说明、清单及核验回执。数据库投影以 `mode=ro` 读取严格限定本轮的 170 行；URL 来自冻结 selection 中与原 row_id/request_id 精确匹配的项目，不拷贝 source 正文。

原四份约 1.1 MB 的 stdout 含全局历史 query_decisions/model_metering，因此只上传白名单投影，不把历史量误计成本轮用量。原 stdout、完整基线 ID、重复审计逐页文件、数据库、页面与渲染原件、截图、模型请求/响应正文、凭据和浏览器状态继续留在本地。

[controller.py](controller.py)、[expand_controller.py](expand_controller.py)、[status.py](status.py)、[final_audit.py](final_audit.py)是原操作脚本副本，保留执行命令和绝对原件路径以便追溯。它们依赖本地原账及未上传的完整基线，归档不是可直接重启的完整运行包；尤其不能因运行脚本仍存在就重复派发本轮任务。

原计划、日志和报告中的绝对路径、失败状态、审计错误与时间值保持原样。摘要只用于核对归档是否损坏，不作为运行门禁。归档期间未修改产品、原件或数据库行，没有追加模型请求，也未执行 git add、commit 或 push。
