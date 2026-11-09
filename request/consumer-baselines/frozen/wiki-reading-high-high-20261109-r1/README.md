# wiki-reading-high-high-20261109-r1

已冻结的消费者模型参数和Wiki固定对照目标。

- `freeze.json`：文件摘要、原始实跑及保存收据绑定，状态FROZEN_ENGINEERING_BASELINE。
- `model-profile.json`：glm-5.3-flash、high/high及实际运行参数；将`consume_kwargs`传入现有`candidate_consumer.consume/run`入口。此文件是会话参数快照，原BatchLedger配置保持不变。
- `session-objective.json`：成功实跑的原目标字节，保留原候选绑定。普通批量候选仍各用自己的目标。

未显式传`effort_profile`时，普通V11仍默认low/low。冻结不包含凭据，不更改旧账、UNKNOWN、原样本、QC或发布状态。以后修改配置或目标另建冻结编号，不覆盖本目录。

[完整说明及待优化项目](../../../../docs/消费者模型与Wiki基线冻结及待优化项目-20261109.md)
