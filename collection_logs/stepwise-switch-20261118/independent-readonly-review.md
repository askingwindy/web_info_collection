# 当前源码交叉审核与补修记录

日期：2026-11-18。范围：用户 SSD 的 WP-S / WP-A / WP-B / WP-D、C8；策略3会话与网关由主 Agent 和对应 Agent 另行交叉检查。

状态：**三个已确认缺口及续跑入口同源接线已修，针对性回归通过；主 Agent 已复核并认可 launch/startup/A8 三文件修改。当前审核范围内没有尚未处理的确定 P1/P2，集中集成结果待汇总。** 本记录不自授全工程独立审核全通过。审核从正常入口追到领取、启动、保存与历史读回，不只看 diff。最初审核只读；下列产品修改均在主 Agent 明确授权、集成退出后实施。当前仅写审核文档，产品已冻结。

## 确定发现、修复与验证

| ID | 等级与确定触发 | 修复 | 证据 |
|---|---|---|---|
| R1 | P1。直接传入旧策略2 fixed consumer plan，`collection_startup.check` 原先允许 screenshot_plan；`site_workers.launch` 可先执行账号探针，之后子 CLI 才拒绝旧策略，违反零模型前拒绝。worker 命令中的显式旧策略也未检查。 | `site_workers.launch` 最前检查 plan 标记与 worker 命令的 `--collection-strategy value` / `--collection-strategy=value`，复用 freeze/Strategy1Forbidden/Strategy2Frozen，在创建日志根目录、自检、probe、Popen 前拒绝。无字段、无参数补 stepwise；普通 consumer_plan 也显式生成 stepwise。collection_startup 的策略检查先于 scope IO，并保留原异常供 global 分类。CLI 捕获 Strategy1Forbidden，退出 2。 | 既有启动测试注入 react/screenshot_plan 与两种命令写法，确认异常为原类、disposition=global，目录未创建、check/probe/Popen 均零触达；CLI 退出 2。`site_workers.py:323`、`collection_startup.py:63`。 |
| R2 | P2。WP-B 删除 prepare_output 调用时，`write_json(root/'plan.json',plan)` 错留在 raise 之后，正常 consumer 启动没有 plan.json。 | 恢复成功 preflight 后的正常缩进；持久化补齐策略后的实际 worker 命令。 | mock worker 正常终态成功，读回 plan.json 为 stepwise，命令与实际 Popen 参数一致。`site_workers.py:365`。 |
| R3 | P2。claim_next 已取消候选 SHA 门禁，但 collection_startup 仍比较 producer response/body/sources 三摘要，preflight_cohort_sources 仍重算 sources_sha256，固定 cohort 在领取前依然被拦。 | startup 只比较 version/application_id/producer_batch/producer_row_id/entry_http；sources 摘要不再比较，也不作为选择原始 GET 检查的条件。存在 entry_http 或源材料声明原始 GET 时继续查验真实收据及其来源绑定。 | 三审计摘要改变后 startup=PASS；entry_http 绑定改变仍 COHORT_EVIDENCE_MISMATCH。真实临时收据在 sources 摘要过期或不存在时均通过，篡改收据文件后拒绝。`collection_startup.py:161`、`candidate_consumer.py:393`。 |

受影响测试命令：

```text
projects/code/.venv/bin/python -m pytest -q projects/code/tests/test_consumer_startup_core.py::ConsumerStartupCore::test_standalone_checks_scope_then_probes_once_and_stops_unavailable
```

结果：**1 passed in 0.15s**，进程墙钟 0.359s；日志 `startup-final-gaps-r01.log`，机器回执 `startup-final-gaps-r01.json`。新增断言并入既有节点，没有新增独立测试项。mock Popen/模型探针均不启动真实进程或请求。

续跑入口补修后同一节点最终复验：**1 passed in 0.14s**，进程墙钟 0.343s，`startup-final-gaps-r02.log` / `startup-final-gaps-r02.json`。主 Agent 已读最终 fixed_consumer_plan 修改及此回执并认可修复。补修与测试完成后产品再次冻结，交还主 Agent 执行集中验证。

## 入口与历史读回复核

- `collection_strategy` 新任务缺省 stepwise，旧策略执行由原 Strategy1Forbidden 家族拒绝；历史 `strategy_id`、`enabled`、`save_eligibility` 保留原解释。四个策略2 Session.run 与 chooser 工厂冻结，但 normalize、derive、validate_ending_marker 等读取函数仍可用。
- `client_package._execution_record` 的历史策略2路径进入 postprocess.session_record/effective_trajectory，不调用 Session.run/chooser/select；历史 completion 保存资格仍进入 closing_policy。collection_report 历史段读取模板 ending marker；qc_handoff.bind_delivery 通过统一 save_eligibility 读取历史 raw。未发现入口冻结误伤这些读取链。
- fixed_consumer_plan 保持同 scope/cohort/stepwise 前段约束，不释放或重写旧 claim，不读取 UNKNOWN 后自动重跑。
- 续跑入口同源接线也已按主 Agent 决定补齐：fixed_consumer_plan 读到 previous 后立即 freeze 检查；缺少历史标记视为冻结的 screenshot_plan，显式 screenshot_plan/react 分别抛原异常。策略、scope/cohort 和上一段全部退出检查都先于 mkdir/shard 写入。既有测试确认三种旧标记均为 global、无目录和分片写入；不释放或改写旧 claim。

## 减负、路径与删除复核

- `_generate_react_url` 是新 stepwise 正常生成入口；它不再调用 read_history 物化全部 m4 task/plan。旧非 react-url 生成器在 generate 最前拒绝。execute 的 check_live_m4_history 已移除；history_read_slot 及排队锁调用也移除。保留的 registry_snapshot 定义用于历史工具，不再处于新采集执行前比较路径。
- 同候选/目标领取及图片去重的现有数据库检查保留。current_chain 对已有保存结果材料的读取与已删除的全 task/plan 快照门禁不同，不把它误报为 A9 回归。
- 仓内 Python 检索 source_identity() !=、generation_source_identity() !=、history_read_slot、check_live_m4_history、generator_files_sha256 比较及 source_drift 无命中。
- workspace_paths 只有 logical 绝对路径；workspace_json 使用标准 json；raw_connect 无 SQL 包装或 text_factory。sqlite_connection 仍有 operation_deadline ContextVar，它只表示 SQLite 操作截止时间，不是路径根，不属于 WP-B 删除范围。
- 16 个删除模块在 projects 下所有 Python 产品、scripts、测试文件中全词检索均无引用。完整删除前逐模块审计及 docs 命令检查见 deletion-reference-audit.json；迁移后的 goal_evidence / candidate_batch 依赖可用。历史策略2实现保留。
- QC sampling/delivery 的实现摘要比较已删除；sampling enqueue 身份与 duplicate cache key 不使用源码摘要，原件/数据字节完整性仍检查。document_text_qc 超出指定 A7 修改点，按主 Agent 决定回退扩展，保持基线原 CLI/历史账语义，没有新增 UNKNOWN 兼容或重发逻辑。

## C8 事务范围复核

此前另发现 pilot_identity 的 verify_saved 仍会在写事务中读全部文件。主 Agent 已修复：RuntimeStore.finish_attempt 在开启事务前完成 exact PNG、saved_sample、annotation 和 verify_saved 校验；事务内重新核对原 task/sample 身份，保留 page_guard 与数据库去重。正常保存路径不会再在写事务里执行这些文件哈希。原 terminal 幂等返回仍保留，未改历史终态原账。依据 `runtime.py:823–881`。

本报告不把离线证据计作生产合格、QC、人审或客户验收，也不声称已经完成全工程独立审核。全量核心测试与本地七链集成的最终结果由主 Agent 汇总。
