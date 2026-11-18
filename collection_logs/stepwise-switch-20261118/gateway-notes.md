# C10 / C13 / C14 实施与离线检查

本轮仅本地代码和隔离测试；真实模型、目标站、生产者实跑、消费者实采、QC 均未运行，正式库和历史原账未修改。

- C14：`ModelGateway` 收到任意 HTTP 4xx（含 408、429）后将原请求结算为 `failed`，`BatchLedger` 记 `cost=0`；未提供的 token 用量仍为 null。抛出的 `ProviderRejected` 保留 HTTP 状态、原 request ID 和脱敏诊断，`failure_class=model`。同一 job/purpose 再次调用读取原拒绝，不新增请求。HTTP 5xx 和已发出的传输超时继续保留 UNKNOWN。
- 账户冷却读取兼容原 unknown 与新 failed；429 无专属数字错误码时也按限流冷却，Retry-After 保留。授权挂起、1301 内容拒绝记录、按页面的用途挂起、生产者隔离均读取新 failed 原件；两个生产者模型适配器结束 job 为 failed，再读回保持确定失败。`grounded_entries` 的两处读取改动由 paths_cleanup 接入。
- C13：新增可选 `request_deadline` 仅在宿主上下文传递。stepwise 决策、回写、判定传会话硬截止；DNS 预检与派发前检查采用剩余预算，实际 HTTP socket timeout 被裁剪到硬截止剩余秒数，响应收据记录实际值。没有改变预算常量或新增传输框架；socket inactivity timeout 不是 trickle 响应总 wall time 的独立证明，宿主现有 hard watchdog 保留。
- C10：`_publish_entry` 找不到原渲染观察时提前返回 `HELD/rendered_observation_missing`，不再依靠 HTTP 检查发布候选。对应 core_contract 断言由主代理维护。
- 为 C16 保留可分类原因，已结算的模型拒答及无法继续压缩的 output_exhausted 直接保留 `ProviderFinishIncomplete`，不再替换为无分类的通用 ValueError；没有增加纠正请求。

测试按 D8 删除本文件中的 6 个策略2会话执行用例，保留 10 个共享日志/网关用例和可复用 fixture，新增 1 个 4xx 综合用例；本模块共 11 个独立执行项。

| 回合 | 检查 | 结果 | pytest 耗时 | 日志 |
|---|---|---|---|---|
| r01 | runlog 全 11 项 | 10 通过、1 失败 | 0.53 秒 | `gateway-core-r01.log` |
| r02 | 受影响的旧异常断言 1 项 | 1 通过 | 0.35 秒 | `gateway-core-r02.log` |

首轮唯一失败是旧测试精确匹配 `no lossless compact`；产品现保留 `ProviderFinishIncomplete/output_exhausted`。只更新该断言后复验通过。最新 11 个节点均通过，累计执行 12 次（11P/1F），pytest 累计 0.88 秒，失败日志保留。4xx 综合场景覆盖 400/401/403/408/429/499/500/503、重复调用零重发、费用和原始用量、授权/冷却/用途挂起，以及两个生产者 job 收口；既有超时用例补了 request_deadline 裁剪并保持 UNKNOWN 的断言。

只读交叉审核 stepwise 时发现后帧 SnapshotFault 被吞及已派发异常缺 terminal step 两个缺口，已反馈给实现代理；其补修后再次读取确认失败动作原件、终态引用、`unverified_actions` 和异常分类链贯通。本记录不替代主代理的最终全量测试及离线消费者全链报告。
