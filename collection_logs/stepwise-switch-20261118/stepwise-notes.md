# 策略3必经缺陷与几何底座修复记录

2026-11-18。本轮只修改本地工作区；真实模型和目标网站请求为 0。

- C16：`StepwiseSession.run` 为模型协议/拒答、异常责任属性、Playwright 网络错误和未知程序错误提供统一分类并封存。`stepwise_caller` 将 `ProviderRejected` 子作业结算为 failed；回写/判定阶段同样保留模型/网络分类。派发和后帧异常先写失败动作收据，保留实际执行事实、异常类型与消息，再封存；UNKNOWN 不重发。
- C17：`EvidenceStale` 与 unsupported geometry 为 collector，其它 `SnapshotFault` 为 program。后帧捕获不再吞掉原异常。失败终态引用实际 failed-NNN.json，原有 `unverified_actions` 可以核对缺后帧。
- C11：select 非空检查移出不可达 elif；使用当前帧原生 select 的选项原文与禁用标记校验，缺失/禁用返回 `SELECT_OPTION_NOT_PRESENT`，派发前反馈。原生 optgroup 禁用也采入禁用标记。
- C12：交付 ui_tree 仅投影客户 schema 的 13 个字段，原始 state 保留。
- C15：不支持几何的子树从可操作控件、ui_tree 和可见文字证据剔除并在 `geometry_exclusions` 留原因；原始截图像素继续保留。显式目标或目标祖先不支持几何时仍拒绝。保持旧规则名，不新增版本。
- C13 接线：决策、回写、判定把既有 host 硬截止传入 gateway 的 request_deadline，不修改预算常量。

产品修改 5 个文件：stepwise/{session,collection,observation,annotation}.py 与 snapshot.js。未修改策略3提示词、schema、预算常量或保存资格。浏览器 Python 实现无需改动。

## 核心验证

本组维护 4 个 stepwise 核心项（按 D8 新增 1 项异常收口）及既有 visual 核心中的几何断言。

- `stepwise-affected-r01.log`：5 项执行，4 通过、1 失败，3.60 秒。失败由新测试错误传入 `capture(retries=0)` 引起；该参数是总尝试数，0 意味着没有进行捕获。
- 只修夹具为 `retries=1` 后，`stepwise-visual-r02.log`：1 项通过，1.35 秒。产品未改。
- 最新不同核心项 5/5；累计 6 次执行为 5 通过、1 失败，pytest 4.95 秒。失败原件保留。
- 异常核心覆盖协议纠正失败、no-progress、拒答、4xx、网络、EvidenceStale、普通/几何 SnapshotFault、KeyError，以及派发中和后帧故障的原始动作收口。
- 几何核心真实启动本地 Chrome，通过 set_content 和禁止外网路由验证装饰/无关按钮/变换祖先剔除、正常目标可观察、旋转目标与祖先拒绝、optgroup 禁用事实。

## 离线全链脚本

`stepwise_offline.py` 从此前原件复制后修改，原脚本未覆盖。包含 operation、reading、shortflow、protocol、network、select、rotated 七链，支持 --chain 定向复验。所有链经正常消费者 CLI，缺省策略参数省略。generation 完成后注入不同的源码审计值，consumer CLI 全程禁止调用大历史 registry_snapshot，以验证 A1/A9。网络链在 back 导航接缝注入真实本地 HTTP 空响应，报告明确该边界。所有模型传输为离线替身，数据库只在新的 verification 工程；来源摘要、脚本摘要、scope 引用及失败原件落在新输出目录。

全链执行和最终全量状态以主代理的本轮报告为准。

## 第一轮七链（integration-r01）

全部进程已退出，产品与 driver 在运行前后字节一致。结果 107 个检查、104 通过、3 失败，模型传输替身 40 次。操作/阅读/旋转链真实隔离保存各 1 条；短流程、协议和本地网络错误均正确失败、封存，claim=failed，未误分类 program。A1/A9 七链全部通过。

select 链先拒绝不存在选项、下一轮纠正后真实派发 6 个动作；结束加工因为替身 step_result 引文「元」不在下一交付帧被现有引文核对拒绝，正确不保存。driver 随后在没有 candidate_results 时仍索引 None，造成次生检查异常。现只修替身描述和 driver 断言，不改产品资格标准。

还发现输出目录名 integration-r01 触发已有 integration_data 出口拒绝：三个已保存链在 CLI 内部导出报程序处置，而 driver 第二次手工 build_client_package 的读回检查掩盖了这个中间错误。因此本轮不作为完整链路通过证明。下一轮使用中性 local-r02 输出目录，并直接检查 CLI 内部导出的 customer_export=EXPORTED_FORMAT_VALID、candidate-receipt 与对应全部文件摘要，不再二次手工导出。

## 第二轮七链（local-r02）

136 个检查，132 通过，37.647 秒；40 个模型传输替身请求（38 succeeded、2 invalid_response、0 UNKNOWN）。4 条成功链全部走正常消费者 CLI 自身保存、候选回写、导出并读回 candidate-receipt：操作/阅读/旋转各 5 个有效动作，select 先拒绝不存在选项、修正后 6 个有效动作并保存。短流程 collector、协议失败 model、本地网络失败 network 三条均封存 raw、不保存，claim=failed；未误计 program。

唯一 4 个失败为成功链导出的说明文字：CLI 传 facts 时由 contract_documents.render 重渲染说明，task_generation 为新 stepwise 任务仍生成“单一 ReAct 循环…observe/inspect/act/finish”陈旧描述。真实系统提示和 next_action、## stepwise 都在，故不是动作、封存、保存或导出结构失败。主代理将修正新任务的事实描述，仅定向复验受影响的 4 个成功导出链；本轮三条失败出口证据继续使用。

完整核账在 local-r02/accounting.json。产品及 driver 运行前后字节一致，驱动与本地 Chrome 均已退出。r02 不能标为全部通过。

## 最终定向复验（local-r03）

新任务事实描述修正后，仅复跑 operation、reading、select、rotated 四条受影响成功链：**85/85 检查通过，29.593 秒**。四条均通过正常消费者 CLI 保存、候选回写、`customer_export=EXPORTED_FORMAT_VALID` 和 candidate-receipt 全文件摘要读回；导出说明的 stepwise 章节通过。有效动作分别为 5、5、6、5，claim 均为 succeeded。模型传输替身共 34 次（8、8、10、8），全部 succeeded，0 UNKNOWN。

A1 执行时审计身份改变仍可执行、A9 全程禁止大历史快照两项均通过。运行前后源码与 driver 字节一致，驱动器退出 0；进程核对无遗留本轮 driver 或 Chrome。逐链核账、CLI 导出回执位置和进程结论见 `local-r03/accounting.json`，完整断言见 `local-r03/report.json`，stdout 原件为 `local-r03.log`。

最终七链证据由 **local-r03 四条成功链的 85/85** 与 **local-r02 三条失败出口的 51/51** 共同组成。三条失败出口分别为短流程 collector、模型协议 model、本地网络 network，均封存 raw、claim=failed、不保存、不误计 program。未重跑这三条，不把 local-r02 原始 136 项称为全过。所有输出为隔离离线工程；真实模型/目标网站/生产新增均为 0，QC 与人审未运行、未发布、客户验收 UNKNOWN。
