# 静态多 worker 协议

这是本地、机器无关的数据协议和守卫，尚未部署多机，也不启动采集、模型、人工服务或定时任务。同一 shard 同时只能有一个执行者；复制同一 shard 给两台活跃机器不属于故障转移。

`webcollect.batch_protocol.plan_shards(catalog, run_id=..., target=..., worker_count=N)` 支持任意正整数 N，或显式非空唯一 `shard_ids`。每个规范化整站只有一个 `site_id` 和静态 owner，所有候选都保留在 manifest。`owned_site_ids` 包含全部归属站，`active_site_ids` 才是本轮可执行站；备用、未知容量、不可用站不会为了填满 worker 而启用。允许非整除和空 active 分片。规范化合并 scheme、默认端口、query、fragment、页面路径、www 别名；其他子域不猜测属于同一个应用。

容量必须来自显式正整数 `capacity` 和内容绑定 `capacity_ref`。收据采用 `webcollect-site-capacity-1`，包含对应 `site_uri`、`status=verified`、相同容量和非空支持证据文件 SHA256。缺少或未知容量保持 unknown，不默认每站20条。同站别名容量取已验证最大值，不相加。

工作端先显式 `initialize_chain(...)` 创建新链及 registry，再调用 `seed_registry(manifest, registry, shard_id)`；也可直接创建本协议的新 registry。全 catalog 的全局 S 编号在每台工作端一致。已兼容 registry 保留原 `next_sample`、allocations、current-chain meta；未知已有分配账本不被自动接管。库存 site 行不是已采集站数，已采集统计仍按实际样本和 metadata 计算。

任务在冻结前用 `global_task_id(run_id, site_id, local_task_id)` 创建全局任务编号，并声明 `batch_identity={run_id,shard_id,site_id,task_id}`。计划声明 `batch_shard={schema_version:webcollect-plan-shard-1,run_id,shard_id,manifest_sha256}`。首版要求 `task.site_uri` 逐字等于 manifest 的全站 canonical root，具体页仅放 `initial_url`。非 canonical 页面 URI、分片外站、缺少绑定均拒绝，守卫不改写已冻结任务或证据。

`verify_plan_shard` 在采集启动前只读核实；真实编号分配也调用 `guard_registry_site`。`verify_shard_policy` 强制同一 run 的本机 failure ledger，核对原始 immutable failure/UNKNOWN facts 的完整子集，不允许换账本或换片清零。原未分片入口保持原行为。

`freeze_result(registry, qc_report, dataset)` 只读验证实际已保存 capture 收据、完整原图树及样本字节、实际 allocation、独立最终 QC PASS 和 registry 中精确引用该报告的接受记录，再返回可搬运的内容绑定结果。`merge_qualified(manifest, inputs, facts=...)` 的每项输入包含 `result_ref`、`report_ref` 和搬运后本地 `dataset`；原报告无需改路径，完整文件、样本、校验和和格式必须一致。同 ID 同版副本只计一次，异版冲突拒绝。同轮同 shard 相同结果可幂等重传，异 body 拒绝；缺片明确列出。

合并重跑现有四路机械检查，输出确定性的无冲突样本引用子集，不修改任何原包或原审核。**`mechanical_unique_count` 不等于 `globally_qualified_count`**。来自不同原局部审核范围的多条样本，会把派生全局 `substantive_difference` 设为 `REVIEW_REQUIRED`，保留原审核不变，正式合格数暂不增加，`release_ready=false`。

待审可通过 `quality_inspector.global_difference.review_template(samples)` 生成空白模板后，显式导入已有实际人工独立比较记录：`merge_qualified(..., global_reviews=[{path,sha256},...])`。导入绑定完整有效总体摘要、每条原 annotation/图树字节、现代业务差异规则 ID 和实际审核来源，只消费第五项，不替换或重新调用原四项视觉审核。当前新增入口接受实际 human `qc-review-2`，空模板、裸 AI PASS、局部/旧总体、规则或字节变化均不能放行；真人身份仍遵循现有导入记录的声明边界。默认全量第五项须实际 PASS，FAIL/待审不计。原导入文件不变，明确选择新有效引用可完成待审，不能靠修改缓存状态。

可选 `merge_qualified(..., global_sampling_plan={path,sha256})` 只接显式冻结的既有 delivery sampling 计划，不默认选择比例。计划全部 slot ID 和原 annotation/evidence 必须匹配完整有效总体；原最终 QC 报告的升级事实也会绑定传入，人工升级、AI问题和替换项不能通过未抽中绕过。已抽中的第五项仍需实际独立结论；未抽中只按明确策略准入，显示 `NOT_SELECTED` 和 policy admission，不标成实际语义 PASS。`global_actual_fifth_pass_count` 与 `global_policy_admitted_count` 分开列出，原四项审核不重做。原报告、全局审核和抽样计划引用均会在下一轮重新核验。

`next_round(manifest, merged, new_catalog=...)` 重新核验合并及全部全局审核引用，并保留 `previous_global_reviews`；缺片或全局语义待审时拒绝继续补采，明确 FAIL 不当合格。条件完整时按 `target - globally_qualified_count` 的真实缺口启用尚未使用的备用站，也可显式增加新发现的整站。新站从全局最大编号后追加，旧 owner/编号不变。已用、unavailable、UNKNOWN hold 站不会自动回流；旧站换页面或参数不能取得新 ID。绑定的 portable facts 仅作失败/使用状态，不冒充本地或全局 QC PASS。

独立 QC 根报告还须带当前 `semantic_rule_ids`。finalize、archive、worker result freeze 和搬址合并共享缓存报告门：缺头或相关规则变化要求先确定性复验，并列出受影响项，不自动调用 AI；无关工程源码 hash 变化不会让未变语义审核过期。

本轮离线验证只使用临时 fixture 和本地 authority 文档；不代表真实多机生产或全局语义审核已完成。
