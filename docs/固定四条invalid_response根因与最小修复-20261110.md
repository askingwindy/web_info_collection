# 固定四条 invalid_response 根因与最小修复

2026-11-10。本次仅只读查证、原失败回包与原发送schema的字段对照及方案整理。没有重启、重试模型、浏览器动作、生产账写入、源码修改或重跑已通过检查。核对的 gateway/规划/执行源码哈希均与本轮启动冻结值相同。

## 明确结论

两笔都是完整的GLM `submit_plan` 工具回包，被本地JSON Schema校验拒绝，**不是停止截断了JSON，也不是达到8/10步上限**。有正确的tool_calls、完整可解析参数和provider usage，原账状态为invalid_response而非UNKNOWN。

但两次拒绝都发生在用户停止指令之后。停止时Muxtly两条正在等待第一次模型响应，Wiki两条尚无模型请求。用户停止造成四条attempt的interrupted/runner_cancelled与后续执行终止；返回参数中的协议问题独立存在，不能归咎于停止。原始状态不改写。

## 时间线（北京时间）

| 时间 | 原始事实 |
| --- | --- |
| 20:59:03–20:59:36 | 四条领取、首屏观察、本地任务生成并进入execution；这里的planned是本地任务生成，不是GLM已接受首轮计划 |
| 21:00:59.936 | w01导数计算器发出首轮模型请求 `3c59fb1f651242f2b62a31e30fd4d518` |
| 21:01:02.448 | w02德国面粉换算器发出首轮请求 `f6339992876d400491f89bacfbb5c835` |
| 21:01:12.871 | 用户“优雅停止”，向协调器发送SIGINT |
| 21:01:12.875–12.879 | 两个模型job已按取消进入review_required；四条attempt随后记录runner_cancelled |
| 21:01:42.577 | w02完整回包返回并结算invalid_response，比停止晚29.706秒 |
| 21:01:54.651 | w01完整回包返回并结算invalid_response，比停止晚41.780秒 |
| 21:01:54以后 | 四个worker退出，协调器收尾；四条均无已接受首轮计划和业务动作事件 |

HTTP请求在后台线程内进行，外层协程取消后，已发出的请求仍能返回并将原响应/usage记入原账；线程结束后进程退出。这解释了“attempt已取消，模型响应稍后才结算”，不是重新发起调用。按四个原attempt精确查原账，确实仅这两笔请求，Wiki两条没有模型请求。

停止前未记录这两笔响应校验失败，因此不能说“用户停止前两笔已报invalid_response”。运行前就存在的是接入契约/校验顺序缺口；它们由停止后返回的完整原响应暴露。也没有证据说明若不停止，后续格式纠正一定成功或一定失败。

## 原回包和拒绝字段

原账只记录 `failure_diagnostic={source:response_validation,error_type:ValidationError}`，没有保存字段路径。下面的具体字段是使用**原发送schema和原工具参数**只读对照定位的；未把重构诊断冒充原时刻已记录的详细错误。结构化证据、字段路径及原账内容哈希见[诊断报告](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/report.json)。完整provider_response为原账JSON副本，不是重新调用结果或网络原始字节。

### w01：导数计算器

- [原始工具参数](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w01-original-tool-arguments.json)、[完整原回包副本](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w01-provider-response.json)、[当时发送的schema](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w01-sent-schema.json)。
- 模型提出求多项式导数，返回 `click → type → click → wait → scroll` 五项，逐步rationale和expected_result均存在。
- **直接拒绝原因**：第4项wait和第5项scroll都额外带 `target:{text:"计算"}`；对应action schema不允许target，`additionalProperties:false`使两个步骤的oneOf校验失败。不是点击focused被禁，也不是缺expected_result。
- **独立业务问题**：五项中wait不计有效动作，首轮只有四个业务动作。即使整理两个冗余字段，仍不符合首轮至少五个必要业务动作，不能直接放行或凑第五步。应明确反馈“5项中1项wait、业务动作4”，无自然完整五步路径则结束并只留原始记录。
- 模型还把未来结果写成`9x`，属于尚未观察的结果谓词；这一项不是本次直接schema拒绝原因，但暴露首轮完成协议仍要求未来字面的问题。

### w02：德国面粉型号换算器

- [原始工具参数](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w02-original-tool-arguments.json)、[完整原回包副本](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w02-provider-response.json)、[当时发送的schema](../verify_results/consumer-unified-success-fixed4-20261110-r01/diagnosis-invalid-response-20261110-r01/w02-sent-schema.json)。
- 模型提出750克、来源405、目标812的换算，返回六个业务动作：click、hotkey、type、select、select、click。
- **直接拒绝原因**：六步全部缺少schema要求的expected_result；click额外带空value；hotkey额外带target及空value；type/select把实际期望值放在`expected.value`，但旧predicate schema仅允许kind/text/region。
- 例如原回包为 `expected:{kind:"value",text:"面粉用量（克）",value:"750"}`，执行器实际协议却把`expected.text`当作期望输入值。它包含可确定的标签/值分离信息，不能简单丢弃value，否则后续会拿控件标签核对输入值，制造新的零效果失败。
- 全选步骤用`selected`而不是输入文本的`text_selected`，完成条件又用输入型号`405`；这些是**尚未执行的语义风险**，不是已发生的页面失败或本次第一层schema错误。不能把输入型号可见当作换算完成。

## 集成为什么没有发现

集成确实验证了无累计上限、保存资格、RuntimeStore提交和收据一致，但对实际模型输出适配的覆盖不足：

| 当时通过的检查 | 没覆盖到的本次差异 |
| --- | --- |
| 完整CLI→真实Gateway→12步→正式收据 | HTTP边界返回的是人工构造的12个规范scroll，全部字段恰好符合schema；没有表单混合动作、冗余target/value或缺expected_result |
| 普通计算finish_result→封存回算→annotation | 使用直接注入的choose回包，未让这类表单首轮参数经过生产native tool入口的严格schema边界 |
| 首轮无8/10上限 | 未覆盖“5项里含wait，只有4个业务动作”的实际模型计划 |

因此，集成通过证明了**规范输入能走通**，没有证明GLM真实输出都能被正确接收。此前把这些通过项统称“Agent+工程完整对接已完成”，覆盖表述过宽；本次真实兼容性缺口仍存在。

代码层的明确断点是：`model_gateway.py`在通用JSON容器解码后立即严格校验；执行字段整理`executable_plan`只在reading/Wiki schema分支调用。Muxtly表单计划没有统一的、理解字段等价关系的入口整理。也不能直接照搬该函数：它目前会直接过滤掉`expected.value`，丢失实际期望值。

还有一个未收口的契约矛盾：两份实际发送的schema仍要求非Wiki首轮提供finish_when，且所选谓词要求text；同时system禁止预猜结果。虽然已经增加执行后的finish_result完成申请，首轮模型接口仍要求旧字面终点，因此模型仍返回`9x`、`405`这样的预猜/输入标签。此项是后续修复必须覆盖的同链问题，不应另开一轮才处理。

## 最小修复方案（本次未实施）

1. **统一计划接入整理，再做语义校验。** 在现有gateway规划入口复用一处整理函数，native tool与纯JSON、首轮与重规划同口径。仅处理有确定等价含义的字段：click等非输入动作的空value、wait/页面滚动的非执行上下文target、`expected.value`与`expected.text`的值/标签拆分。hotkey目标保留为焦点前提核验，不能丢掉意图或无条件改变作用对象；需要特定滚动容器或字段值冲突时给出具体反馈。原回包保留，并记录整理后的执行投影及字段变换依据。
2. **把缺信息和业务不足明确反馈给Agent。** expected_result缺失要求同一观察下补齐，不能删required或用purpose冒充原生预期结果。按真实业务动作口径反馈wait不计步；自然不足五步就结束，不补无用动作。全选的输入选择谓词与实际按键/当前输入值对齐，值检查用实际期望值，结果检查使用实际输出。
3. **收口新计算完成协议的首轮接口。** 对显式result-completion-1任务，首轮只列原目标事项，移除模型必须猜finish_when字面的要求，像现有Wiki路径一样由宿主补协议占位；执行后沿已实现finish_result逐项绑定本次结果。prompt、wire schema、绑定/校验、在线收尾和封存回算一起改。保留原目标success、至少5个有效动作、无累计上限及异常/短流程不正式保存。
4. **补拒绝原因和取消归因记录。** 在原request收据中记录校验阶段、action、精确字段路径、缺字段/冲突，不只写ValidationError；保留stop_requested_at、response_received/settled_at和attempt取消状态。这样后到回包错误不会被笼统归为停止前故障，也不会覆盖用户取消事实。

将来实施后的新增局部验收只用这两份冻结失败回包作为反例：w01整理后应明确得到“四个业务动作、不合格且无派发/正式文件”；w02应保留六步操作意图、正确映射750/405/812，精确指出缺少的六个expected_result，补齐后的规范投影才进入执行校验。另覆盖新计算首轮不要求预猜终点、取消后到回包不触发新派发。这些不是重跑已通过的12步保存、SQLite并发、拖拽或历史QC检查。

当前维持停止，不改原请求状态、不重派四条原候选、不启动真实复验。不能承诺仅放宽schema就能让这两条成功：w01还有明确的短路径问题，w02还有必须补齐的标注语义；此次给出的最小改动是把格式兼容、真实缺项与业务资格准确分开。
