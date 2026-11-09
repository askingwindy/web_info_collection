# zcode：生产者等待、明确失败与 Agent 反馈实现提示词

```text
只在以下隔离工作区实现：
/Users/hemiao/.codex/worktrees/producer-observation-feedback-20261109/WebCollect
分支：codex/producer-observation-feedback-20261109

先读 AGENTS.md、README.md、docs/工程说明.md、docs/设计说明.md，以及：
docs/生产者固定等待优化与明确失败前置及Agent反馈实施方案-20261109.md

当前主工作区 /Users/hemiao/projects/2610/WebCollect 正在生产本批 1000 个有效 Table2 页面，必须继续。不要修改其源码、配置、manifest、候选、生产账、运行参数，不要杀进程、重启服务、切分支或合并代码。只读查看原账使用 SQLite mode=ro，输出全部写到本 worktree。原运行目录是主工程 verify_results/producer-live1000-20261109-r01/，服务与 PID 以实际查询为准。不要因历史 STOPPED_BY_USER 再次索要已授权研发的许可。

工作区基线为 702573a，另有上轮原账并发接续的必要继承改动，文件摘要见 verify_results/producer-observation-feedback-20261109-r01/bootstrap.json。先 git status --short，保留这些继承文件和其他已有改动。不要复制主工作区的消费者在研代码。

按顺序集中实现三项：
1. discovery_tools.DiscoveryBrowser._read 的第一段固定 1200ms 改为原窗口内有界就绪观察；正文/控件/首帧图片就绪并稳定后可提前结束，不稳定走原上限。完整首帧清单明确未达到图片排除条件时取消第二段 1200ms 延时，但仍进行第二次真实观察。可能达到图片排除条件时保留原延时和二次几何核验。不得降低 >=95% 图片排除标准、按正文长度拒绝页面，或复制第一帧冒充第二帧。
2. 确定 HTTP 4xx/5xx 时，保存绑定原 URI/响应/visit/job/tool request 的失败收据并提前收束，不继续等待/截图/完整 DOM/用途模型。没有确定响应的导航错误仍是 UNKNOWN。入口 403 页级废弃，其他页面可继续；失败原账不删除、不重发、不扩大为整站永久禁用。
3. 宿主从原角色账本汇总有界页面访问事实，按 host 给出成功、HTTP 失败、UNKNOWN、状态码和导航错误码，保存原行身份与摘要收据。将紧凑摘要接入找站拟词 Agent，指引换来源/表达；不自动禁站、不改已冻结 prepared 列表、不让模型生成候选或消费者任务。

兼容要求：
- 新功能显式 --producer-optimization observation-feedback-1，只用于新 entry-tools-13 批次；缺省和旧 run 保持原义，同 run 禁止切换。
- 内部读取策略 producer-readiness-1、失败收据 producer-http-failure-1、反馈 producer-page-feedback-1、拟词输入 producer-category-query-4 显式版本化并绑定恢复。
- Table2 四字段、业务 V13、candidate ID/去重、来源哈希、claim/attempt/sample 和消费者/QC 均不改。
- 原 URI 观察可复用；失败/UNKNOWN 不能因换策略生成新的观察身份重发。旧 query checkpoint 不能重算反馈覆盖。
- 不做两个浏览器并行、模型并发、reason 字段放宽、整站三次失败停止或历史清理。

工程实现和模型可见协议必须同时接线；不能只把反馈写日志却没传入真实模型请求。优先现有 Python/SQLite/文件，不新增框架或服务。

验证：集中完成后做一次聚焦集成，输出到本 worktree 全新目录，保留失败、命令和源码摘要。采用主工程现有 projects/code/.venv/bin/python，PYTHONPATH 只指本 worktree 三个包。用真实 Chromium 的本地受控夹具覆盖等待/图片/HTTP 失败/UNKNOWN/恢复；localhost 许可只留在测试夹具。
集成通过后直接完成计划约定的隔离、固定输入、最多 16 NEW/轮的真实 GLM 基线，并单独验证一次找站反馈真实 GLM 请求。production_counted=false，不启动消费者或 QC，不写正式账；当前 1000 页生产不中断。凭据仅由现有模块正常读取，不打印或复制 token。新会话沿既有轮换，旧会话绑定不变。UNKNOWN 不补位、不重发。

完成时同步本 worktree README/工程说明/设计说明/生产者 README，并报告改动、检查、真实 NEW 与失败、Agent 反馈是否实际进入模型、性能证据及未验证边界。保存可复查的代码 diff 和收据，不提交 results/verify_results/SQLite/截图/请求或凭据。不要自动合并、推送或部署到主工作区。实现中如已有部分完成，先核对原结果接续，不重做已通过且未受影响的验证。
```
