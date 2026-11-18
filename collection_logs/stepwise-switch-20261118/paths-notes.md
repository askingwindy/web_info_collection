# WP-B / WP-D / A7 与冻结入口修复回执

本轮只修改本地工程及隔离验证文件，没有运行真实模型、目标站、生产者、消费者或 QC，没有修改正式库或历史原账，没有 commit、push、上传或 PR。

## 已完成

- `workspace_json` 的 dump/dumps/load/loads 直接使用标准 json 函数；字符串不再编解码。
- `workspace_paths` 只保留 `logical()` 返回绝对路径；移除路径根 ContextVar、marker 识别、编解码和 bind/prepare/prepare_output。调用点一并移除；site_workers 由主 Agent 更新。`sqlite_connection` 保留连接、WAL 准备、busy_timeout、同步等级和 begin_immediate，删除 SQL 参数改写与 text_factory。旧 `workspace:/` 字符串保持原样。
- 删除授权的 16 个模块。`result_evidence` 及其解析依赖迁入 `goal_evidence`，`session_objective` 改从该模块读取；`fixed_cohort._path/_lock` 迁入 `candidate_batch`。每个模块删除前均执行 `rg -w`，包括 scripts/docs；删除后全仓 Python 代码引用为 0，见 `deletion-reference-audit.json`。
- 删除 QC 历史 tests 整目录：49 个磁盘文件（37 个 Python 文件，其中 33 个 test_ 文件；另有 1 个 JS、1 个 Markdown 夹具、10 个缓存文件）。完整清单见 `deleted-qc-tests.json`。同步离线验证脚本移除该目录；verify_table2_run 删除已退役历史排队锁用例并改用标准 JSON 原文断言。
- grounded_entries 清理 45 个常量分支/表达式，保留原业务结果；清理前后归一化 AST 一致，见 `grounded-cleanup-check.json`。按 gateway Agent 要求把内容拒绝读取改为兼读 unknown/failed，回执保留实际原状态。
- A7：sampling 的 verify/calibration 不比较实现摘要，prepare 作业身份不含实现摘要；delivery_pipeline 准备只检查输入完整性。duplicates 缓存身份按原 annotation/图片字节确定，源码/Pillow 摘要只保留顶层审计。没有取消样本文件、原件、合同和收据的完整性检查。
- 经主 Agent 授权补齐直接执行入口：四个 screenshot Session.run 与四个 screenshot_chooser 工厂最前抛 Strategy2Frozen，历史解析/导出函数未改；task_generation 默认 react-url，非 react-url 旧生成器在模型调用和输出写入前抛 Strategy1Forbidden，CLI 捕获后返回 2。原策略1 ReactSession/react_chooser 的同类接线由主 Agent 完成。
- QC README 标明已删除模块退役，不再保留其可执行 python -m 命令。根 README/工程说明/设计说明由主 Agent 同步。

## 验证

受影响核心：`test_candidate_storage_core.py` 2 项和 `QCSourceAuditContract` 1 项，**3 passed in 0.28s**；进程墙钟 0.465s，失败 0。命令、退出码见 `paths-focused-r01.json`，完整输出见 `paths-focused-r01.log`。

覆盖：双根交错读取不污染后续 JSON、SQL 中 path 与业务正文参数逐字保留、旧 workspace:/ 不解码、新初始化无 marker；源码变化时复用抽样作业和图片指纹缓存，数据变化仍使缓存失效/完整性拒绝。新增核心项 1 个，其余断言并入既有项；全工程最终数量由主 Agent 集中收集确认。

静态核验：13 个修改模块/测试 AST 解析成功，删除模块代码引用 0。没有把静态分析或离线夹具结果计作生产/QC/客户验收。

## 只读交叉审核与范围

- 确认普通策略3生成不再物化全历史 task/plan；select 已接在 execute/collect_m4 的浏览器和模型前。
- 发现并补齐直接策略2 Session/chooser、旧生成器及 CLI 异常退出漏点；主 Agent 已补直接策略1入口。
- 发现 C8 在 pilot_identity 路径仍经 verify_saved 于写事务中读全部文件；主 Agent 已据此把预校验前移并保留事务内身份核对。
- `document_text_qc` 不在 SSD A7 指定修改点。深入检查发现其历史源码摘要还间接进入 sample_qc 材料及语义请求身份；仅删顶层字段可能引入旧 UNKNOWN 新身份问题。按主 Agent 明确决定，已撤回该文件本轮扩展，保留原 CLI/原账语义，不增加兼容分支或新父账守卫；该文件最终与基线一致。
