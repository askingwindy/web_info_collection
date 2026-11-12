# WebCollect 持久工程存储

2026-11-12 起，工程持久根按目录格局约定分区（目录拼写沿用用户指定的 `sqllite`）：**正式生产工程固定 `database/sqllite/prod/`（初始化默认根）**，验证工程放 `database/sqllite/verification/`，成功样本基线库在 `database/sqllite/baseline/`（自 `database/sqlite/baselin/` 迁入，SHA256 一致）。运行输出不承载候选池和角色账本。

```text
database/sqllite/prod/               # 正式生产工程（默认持久根）
  scope.json
  candidate-pool.sqlite3             # Table1 applications / Table2 data_candidates
  producer-jobs.sqlite3              # 生产者请求、用量与 UNKNOWN
  consumer-jobs.sqlite3              # 消费者请求、用量与 UNKNOWN
  production-registry.sqlite3        # 编号、任务、attempt、保存状态
  site-facts.sqlite3                 # 工程站点事实
  producer-config.json / consumer-config.json / policy.json
  chain/manifest.json
  producer-evidence/                 # Table2 引用的原始来源证据
database/sqllite/verification/<name>/ # 验证工程归档区（显式 --root 初始化；轮次结束后仅按逐次授权清理）
database/sqllite/baseline/             # 成功样本基线库（自 database/sqlite/baselin/ 迁入）
results/<project_id>/collections/    # 消费者采集输出，仍按工程身份区分
```

Table1 与 Table2 是同一个 `candidate-pool.sqlite3` 中的逻辑业务表，不拆成 `table1/`、`table2/` 两个物理库。`data_candidates.application_id` 引用 `applications.id`，发布与领取还依赖同一 SQLite 事务；拆库会破坏现有外键和原子交接。所有 Table 数据及来源证据都直接位于上述固定根，不再增加工程 ID 目录层级。`project_id` 仍用于 run、chain、输出目录和业务身份。

两份角色作业库由角色首次启动时按原有入口初始化；初始化 scope 已冻结其路径。所有角色依 scope、manifest 的绝对路径读取同一工程，不能只凭文件名寻找替代库。生产者默认来源证据目录由 manifest 的持久根派生，不放进可清理的运行报告目录。

初始化：

```sh
PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector \
  projects/code/.venv/bin/python -B -m webcollect.candidate_project init \
  --project-id "$PROJECT_ID" \
  --policy-template "$POLICY" \
  --producer-config "$PRODUCER_CONFIG" \
  --consumer-config "$CONSUMER_CONFIG"
```

默认持久根如上（`database/sqllite/prod/`）；验证工程用显式 `--root database/sqllite/verification/<name>` 初始化，不能处于 `results` 或 `verify_results` 内。`--output-root` 控制采集输出，不能包含持久根。固定根可以已经存在并包含无关的旧工程子目录，但其直属 scope、manifest、配置、策略和数据库文件必须均不存在；已有完整或部分初始化文件时直接拒绝，不覆盖、不续建。配置模板应先放在目标之外，如 `database/launch-inputs/<project_id>/`。

删除输出目录不会删除 Table2、角色原账、manifest 和生产者来源证据；已经保存的消费者原始样本仍属于其原始证据，删除它们不会由数据库自动恢复。

`.gitignore` 忽略 `database/` 中的本地数据库、配置、证据及 SQLite 辅助文件，只有本文提交源码。2026-11-12 目录格局统一迁移：旧正式工程 `producer-muxtly-wiki-200-20261111-r01/` 已迁至 `prod/`，三个策略2验证工程已迁至 `verification/`；原路径留有同名符号链接桥接——五库内嵌旧绝对路径（原账不改写）与 `results/`、`verify_results/` 历史收据仍依赖它们解析，**不能当作冗余项删除**。验证工程轮次结束后不自动删除，清理须逐次明确授权并确认证据已在收据中留存。需要读取旧工程时仍显式使用其原 scope；原目录一旦缺失，不根据旧路径创建空库冒充恢复，不把数据库快照或旧 UNKNOWN 迁入新工程重发。

本轮离线验证：迁移前后五库 SHA256 一致、行数一致（applications 264、data_candidates 1915），`site_inventory` 以新旧两条路径回读输出一致；受影响核心测试 15 passed。证据在 `verify_results/db-layout-prod-20261112-r01/`。真实 GLM、真实网页采集、真实消费者执行和 QC 均为 NOT_RUN。
