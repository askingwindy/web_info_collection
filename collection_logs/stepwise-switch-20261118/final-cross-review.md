# C8 / WP-S / A1-A9 最终交叉复核

日期：2026-11-18。范围：当前源码的真实调用链；未读取正式库，未请求真实模型、目标网站或启动生产/QC。先只读复核，报告确定缺口后按主代理授权补修；以下两项补修后产品与测试已冻结。

结论：本范围发现的两类必修遗漏均已关闭。C8 普通新 attempt 保存路径、stepwise 主入口和 A1/A9 必经路径未发现其它确定必修遗漏。此结论不等于真实采集、QC 或客户验收通过。

## 发现与关闭

1. **WP-S，旧非 M4 collect/preflight 入口未拒绝冻结策略。** 原 `collect_plan` 只有 M4 分支进入 `collect_m4.select`；非 M4 计划以及直接 `preflight_plan` 都能先启动浏览器。现 `collect.py:1491-1495` 与 `preflight.py:347-351` 在读取计划后逐任务 `select`，早于验证、输出创建和 Playwright 启动。`__main__.py:189` 捕获父异常 `Strategy1Forbidden`，策略2子类沿用 CLI 退出2。`validate_plan` 保持纯历史验证能力。无标记的历史任务仍解释为 react 并拒绝执行，没有改写历史身份。

2. **WP-A A4，scheduler resume 隐式比较当前源码。** 原 `frozen` 包含本次 `source_identity()`，续跑把整份记录与它比较，删除派发前显式检查后仍会受源码变化阻断。现 `site_scheduler.py:144-150` 仅排除 `source_files_sha256` 后比较原业务/config/input绑定，之后 `frozen = recorded`。原 `schedule.json` 不改写，传入 `admission_cohort.reserve_schedule` 的也是原记录，避免其完整文件绑定和 cohort 确定性身份被本次源码摘要改变。该模块其它比较只有配置、输入文件、原 cohort 回执等非实现内容；没有其它当前源码比较。

## 调用链复核

- **C8：** `runtime.finish_attempt:835-862` 在只读连接取原 task/sample 后，先 `_checked_images` 逐PNG核对，再读取保存回执/annotation，最后调用 `production_identity.verify_saved`；写事务始于863。事务内881-882重核 task/sample 与预检一致，907-926执行 `m4_exact_images` 数据库冲突检查与写入。`verify_saved` 的文件读取/哈希没有再留在普通写事务内；终态幂等返回保持旧记录含义。历史显式 derivation recovery 仍按其原授权专用路径处理，不属于本次新 stepwise attempt 调整。
- **WP-S 主链：** `candidate_consumer.run:1029-1037` 与 `_consume` 在启动检查/领取前冻结；`task_generation._generate_react_url:785-786` 在生成前冻结；`execute:1363-1365` 在领取 collection job 前 `select`；`collect_m4:381-383` 在输出锁/registry/browser前 `select`；`_react_collection` 在 chooser/session/page 创建前拒绝策略2，保留 stepwise 分流。CLI只接受 stepwise。
- **固定消费者：** `site_workers.fixed_consumer_plan:253-259` 在新输出创建前拒绝旧段策略；`launch:330-349` 检查计划与各 worker 的显式 `--collection-strategy`（两种参数写法），缺省补 stepwise，早于 probe。旧策略子异常仍继承现有 global/program/CLI 接线。
- **建任务：** `session_core.build_candidate_task:276-285` 使用缺省 stepwise，标记在 task ID 哈希前冻结；另一个 capability 入口同样已接线。历史 `strategy_id/enabled/save_eligibility` 未被执行门禁污染。
- **其它执行入口：** 全代码检索 `collect_plan`、`preflight_plan`、`collect_m4`、`collect_one` 与 Playwright启动调用。`collect_one` 仅由已门禁的 `collect_plan`、`collect_m4` 内部调用，无独立 CLI；`site_scheduler` 的真实 runner 是 `collect_m4`。没有因此封禁历史回放、导出或纯验证工具。
- **A1/A9：** 新 `react-url`（保留名称）的生成分支不再物化全部历史 task/plan；`history=[]`，源码只写计划审计。`execute` 不再调用 `check_live_m4_history`，该函数及历史读排队锁已删除。现存 `read_history→registry_snapshot` 仅属于已冻结生成路径；新 stepwise 不带 `task_admission/workflow_admission`，因此不进入旧 admission registry快照比较。`guard_enqueue` 无旧workflow/cohort时在 `admission_cohort.py:267-269` 返回。客户已保存样本的原件完整性读取保留，未误删图片去重或候选/目标领取保护。

## 本次追加验证

没有新增独立测试项，断言合入既有核心测试：

| 节点 | 覆盖 | 结果 | 原件 |
|---|---|---|---|
| `StrategyResultContract::test_freeze_records_strategy_and_dispatch_follows` | 无标记/react/screenshot_plan 的 collect/preflight 直调与 CLI；拒绝前 Playwright、collect_one、validate、输出创建均未发生；CLI退出2 | 1 passed，0.15s | `strategy-entry-core-r01.log` |
| `StrategyResultContract::test_execute_allows_source_changes_without_registry_snapshot` | 原 A1/A9断言；实际 scheduler resume 流程遇新源码摘要放行，调用真实 reserve_schedule，原审计字节与传递绑定不变；业务配置改变仍拒绝 | 1 passed，0.11s | `scheduler-resume-core-r01.log` |

本次2个既有独立节点，各执行一次，2P/0F，pytest耗时合计0.26秒。上述 scheduler 测试只使用临时目录及离线 collector 替身；并未启动浏览器或生产采集。最终全量核心及本地浏览器全链由主代理统一安排，不能把本报告2项结果替代那些回执。

## 最后两处定点补修

上述交叉复核结束后，paths代理与主代理再次定点检查，指出两处仍需关闭；先前结论的覆盖不充分，以以下追加结果为准：

- **A5，preflight 尾部仍根据 `changed` 拒绝生成计划。** 已删除该拒绝，`preflight.py:427-433` 的 before/after 摘要及 `source_changed_during_run` 保留，445-447 正常输出计划并验证原件绑定。
- **WP-S，scheduler 的拒绝应先于 cohort 预留。** 虽然下游 `collect_m4` 能在浏览器前拒绝，原 scheduler 会先调用 `reserve_schedule`。现 `site_scheduler.py:86-90` 在读取每批计划后逐任务 `select`，早于注册库访问、输出创建及 cohort 预留；253-263 的 CLI 捕获原父异常并退出2。

断言仍合入上表两个既有独立项，没有增加测试项。新增 scheduler 直调/CLI 测试覆盖无标记、react、screenshot_plan，证明 registry/cohort/collector/output 均未触发。新增 preflight 测试以完全离线的 Playwright/页面观察替身走完整尾部，只模拟源码摘要前后不同，真实执行报告写入、`schedule_plan` 和 `validate_preflight_binding`，确认 changed 审计保留、probe_errors=0、原任务及 scheduled-plan 均有效。

最后回归原件：`remaining-gates-core-r01.log`，**2 passed，0.16秒**。本报告两轮补修累计4次执行、覆盖2个不同核心节点，4P/0F、合计0.42秒；不含主代理另行执行的全量和浏览器全链。产品与测试再次冻结，此后仅追加本说明，没有进一步扩展审计或修改源码。
