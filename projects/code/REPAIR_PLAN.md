# 单次采集、三层质检与交付修复

2026-10-28，基线56e7f9f。先完成代码和全部离线验收，再单独申请一条真实验证。本次不恢复真实采集、模型服务、人工服务、定时任务或发布。正式合格仍为0。

最终流程：来源候选 → 任务规划 → 单次执行保存完整待审证据 → 全量机械检查 → 独立配置的AI/人工抽检（AI问题转人工、同样本合并） → 复用有效语义结果 → 交付格式/引用/跨包/版本校验 → final QC → ZIP。试点与交付共用入口，仅规模和配置不同。

| 阶段 | 改动范围 | 完成条件 |
| --- | --- | --- |
| R0 接口 | site_planner来源生产者；webcollect.qc_handoff；兼容adapter | 规范来源配置hash，保留内容hash；当前链保存收据和候选字节绑定；禁止旧库回退及来源不明trace晋升 |
| R1 单次采集 | production_identity、task_generation、collect_runtime及契约 | 移除pilot必须演练/独立准入的前置依赖；同execute→collect_m4→collect_one；每动作一次、resume不重做；完整PNG/tree/raw/attempt/收据输出pending，非QC PASS |
| R2 三层质检 | delivery_sampling、delivery_pipeline、handoff | 全量确定性检查；AI/人工独立显式比例和seed；按完整轨迹可复现抽样；AI失败/无效/UNKNOWN转人工、两来源去重；未选中不伪称语义PASS；真人结果真实导入 |
| R3 审核复用 | contract、reviews、reporting、ai_worker、sampling及相关模板 | 按chain/sample、原始证据、相关check规则及差异比较集合绑定；同证据同规则不重复AI；单样本或单规则变化按范围失效；无关源码/封包/路径变化不全量重审；UNKNOWN不重发 |
| R4 稳态 | browser、snapshot、evidence、task_admission；必要preflight/media逻辑 | 文档及相关资源加载完成；目标/标签/值/坐标/命中/遮挡/结果一致；仅允许可证明无关非交互图片动态；完整原图保留，不能全状态已变仍谎报dom_stable |
| R5 交付 | cumulative、client_reports、pipeline及薄版本/交付范围模块 | 同ID同版/异版及显式替代关系；不同ID继续四路去重；所有封包入口绑定有效集合、跨包PASS、final PASS；ZIP解压逐字节一致，不重AI |
| R6 总验收 | 离线fixture集成与绑定源码的验证报告 | 全链离线闭环及负向门禁通过，真实网络/付费模型/生产派发禁止；日志必须有结束状态和退出码 |

已有质检事实：delivery机械层全量检查；sampling支持ai_percent/human_percent、seed、batch/site分层，单位sample slot，向上取整；AI问题升级与独立人工抽中按sample合并。NOT_SELECTED只代表按策略准入，不代表看过图。默认没有sampling plan的check仍要求完整语义检查，所以新产品流程必须显式绑定计划。通用历史默认100%/0%及本地旧AI100%不等于已确认生产比例；改造暴露并传递参数，不擅选比例。

保留的政策问题：被AI选中但尚未尝试时，即使人工已PASS，现有策略仍AI_REQUIRED；不擅自改变该语义。已发生AI失败/UNKNOWN后的人工覆盖继续有效，旧失败不改写。人工FAIL要求替换，不能用再次AI投票掩盖。

硬性资格：三个程序契约通过；单次动作与完整证据通过；三层分流及复用通过；相关证据稳态正反例通过；当前空链、旧库排除、整站3次失败/UNKNOWN hold通过；跨包及所有归档入口门禁通过；当前代码完整选定离线回归和合成端到端都有结束状态、退出码及源码hash。缺一项不称整体完成。

之后一条真实验证须另获明确授权，使用新站、当前专链和experiment-one profile。可明确AI100%仅证明测试AI链路，不改生产默认；真人部分必须人实际完成，AI不得假扮。动作只执行一次，语义结果只按有效绑定复用；UNKNOWN停下核实不重试。试验包不代表正式一万包/二十万条数量、分布要求达标，不自动恢复批量生产或发布。

P0已知边界：首批handoff要求候选样本与提交保存结果字节相同；增量当前结果集合和转换后lineage须继续补契约，禁止靠同ID推断真实性。源码与测试样本都不计正式产量。
