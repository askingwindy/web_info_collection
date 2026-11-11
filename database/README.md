# WebCollect 持久工程存储

2026-11-11 起，新工程的默认持久根是 `database/sqllite/<project_id>/`（目录拼写按用户指定的 `sqllite`）。运行输出不再承载候选池和角色账本。

```text
database/sqllite/<project_id>/
  scope.json
  candidate-pool.sqlite3          # Table1 applications / Table2 data_candidates
  producer-jobs.sqlite3           # 生产者请求、用量与 UNKNOWN
  consumer-jobs.sqlite3           # 消费者请求、用量与 UNKNOWN
  production-registry.sqlite3    # 编号、任务、attempt、保存状态
  site-facts.sqlite3              # 工程站点事实
  producer-config.json
  consumer-config.json
  policy.json
  chain/manifest.json
  producer-evidence/              # Table2 引用的原始来源证据
results/<project_id>/collections/ # 消费者采集输出
```

两份角色作业库由角色首次启动时按原有入口初始化；初始化 scope 已冻结其路径。所有角色依 scope、manifest 的绝对路径读取同一工程，不能只凭文件名寻找替代库。生产者默认来源证据目录由 manifest 的持久根派生，不放进可清理的运行报告目录。

`.gitignore` 忽略 `database/` 中的本地数据库、配置、证据及 SQLite 辅助文件，只有本文提交源码。原目录一旦缺失，不根据旧路径创建空库冒充恢复，不把数据库快照或旧 UNKNOWN 迁入新工程重发。

初始化：

```sh
PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector \
  projects/code/.venv/bin/python -B -m webcollect.candidate_project init \
  --project-id "$PROJECT_ID" \
  --policy-template "$POLICY" \
  --producer-config "$PRODUCER_CONFIG" \
  --consumer-config "$CONSUMER_CONFIG"
```

默认持久根如上；`--root` 可显式指定其他持久根，不能处于 `results` 或 `verify_results` 内。`--output-root` 控制采集输出，不能包含持久根。初始化目标必须尚未存在，配置模板应先放在目标之外，如 `database/launch-inputs/<project_id>/`。

删除输出目录不会删除 Table2、角色原账、manifest 和生产者来源证据；已经保存的消费者原始样本仍属于其原始证据，删除它们不会由数据库自动恢复。

当前用户已确认此前位于 `results/` 的原工程被清理。本轮只修改存储和读取接线，未恢复旧数据库、未初始化新生产工程。新生产者执行范围见 [Muxtly/Wiki 各100页 Prompt](../docs/生产者Muxtly-Wiki各100页执行Prompt-20261111.md)。

