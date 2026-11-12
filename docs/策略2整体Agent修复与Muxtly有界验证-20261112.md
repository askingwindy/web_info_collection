# 策略2整体Agent修复与Muxtly有界验证

2026-11-12，用户授权基于最新代码使用 gpt-6.1-sol / low 子会话统一修复，再以同一 Muxtly URL 执行真实规划采集；失败时分析并修复，第一条最多五轮，成功后探测第二条 URL 并试跑。不重发旧 UNKNOWN，不覆盖原件与账目，不扩大为持续生产。

## 统一实现

- screenshot_plan：原目标与可调整核对方法分开；按需使用控件，先聚焦、可靠替换、实际值核验；统一可执行动作；决策专属字段；每个检查点可增量提交证据。数值核对区分逐字来源与推导结论，安全四则重算并绑定输入、页面公式和独立结果。此校验不等同自然语言公式语义的独立AI审核。
- screenshot_session：统一当前/历史输入、实际动作结果、页面目录、完整剩余计划、已核验及缺项投影；去重复与宿主私有来源字段；每轮先合并并重验累计证据，再作决策；滚动次数不再证明目标有进展。
- screenshot_execution/session_core/observation：编译和派发前共享焦点及可观测选区核验，保留真实原子动作，不自动聚焦或清空。数字框选择行为经本机离线Chrome核实，无需修改snapshot实现。
- postprocess：推导结论与逐字依据分开生成叙述；失败执行对账复用原子证据检查，仅不使用交付往返质量门禁，正常保存条件不变。
- model_gateway：协议纠错带原参数与准确路径；HTTP失败记录脱敏的provider说明、参数路径和请求结构。
- request_quarantine/runtime/consumer及关联门禁：原请求明确HTTP400/1210拒绝、全部网页派发可核验、原进程自然退出、取得本轮明确授权时，可追加新完整尝试许可。原UNKNOWN、费用、claim/attempt事实及原请求重发禁令保留，不泛化到超时或未知网页副作用。

## 已运行检查

受影响核心首轮执行31项，29通过、2夹具前提失败，6.98秒；修正两条夹具后仅复验失败项，2通过，0.24秒。共31个不同核心项、33次执行；维护总量50（collect-only 0.16秒）。首轮过滤表达式未匹配类名，额外执行的日志项均通过，后续不重复。未新增测试项。

旧封存轨迹只读审计最终通过：20个实际派发有完整证据，原请求费用仍UNKNOWN。此前审计暴露不存在的boundary字段假设、执行闭合与交付质量混用，已统一修正；不是旧样本转为成功。

## 真实验证

固定URL：https://www.muxtly.com/zh-CN/concrete-calculator/
固定原目标：使用页面上的混凝土计算器，计算一块12英尺×12英尺、厚6英寸的板所需混凝土体积及所需袋数，并核对结果。

本轮记录目录：[verify_results/muxtly-agent-loop-20261112-002523](../verify_results/muxtly-agent-loop-20261112-002523/)。第一条URL在第4轮完成原目标并正式保存；第二条已真实探测，但生产者资格请求HTTP429/1113后保留UNKNOWN，未进入消费者。全部真实进程已退出，无自动续跑。实际运行结果以逐轮原始日志、strategy-result和RuntimeStore保存收据为准。独立QC、人工、发布与客户验收分别报告，不将离线通过写成真实闭环通过。

## 第1轮结果与第2轮修复

第1轮真实执行433.702秒，16个有效动作（click5/hotkey3/type3/scroll5），10笔模型请求均succeeded，已知input168364/output14138 tokens。12/12/6首次输入均正确，阶段证据由4项增至5项。运行时原目标记VERIFIED，但仅体积由工程复算，袋数核对未纳入计算覆盖；该差异保留。正式保存0，派生第8步NARRATIVE_EVIDENCE_UNSUPPORTED。其他会话的site_workers.py、candidate_discovery.py、producer_query_plan.py运行中变化；本次消费者修复文件未漂移。

第2轮统一修复：固定目标由宿主绑定；多项calculations覆盖全部结果，computed_value由宿主计算；公式来源不接受尺寸行/结果卡，缺项精确反馈；按已核验选区事实生成叙述，避免引用裁切不可见数字；合法补证往返需首次新增且最终仍有效的事项证据；失败code/step/operation贯通保存日志。原件只读诊断16步叙述均可支持，未补存旧样本。仅复验受影响核心2项，0.38秒通过。第2轮即将按同一原目标真实启动。

## 第2轮结果与第3轮修复

第2轮231.995秒，11个有效动作，3笔请求（1 succeeded、2 invalid_response），input50215/output6835 tokens，无新增UNKNOWN，源码无漂移。首轮固定目标一次接纳、12/12/6首次正确；分支revise第二步click缺target，精确错误反馈后模型仍遗漏该字段，consumer_protocol_no_progress结束，正式保存0。

第3轮仅修协议字段纠错：对确定的叶字段错误，只提供单个repair_tool_arguments工具；补丁只能替换原schema指定字段，原有效兄弟字段冻结，合并后正常完整schema/normalizer复验。原provider回包、补丁、host合并与最终验证结果分别留证；保持既有tool_choice=auto；单次补丁失败立即结束，不无限重试。主要日志新增schema错误路径。更新现有核心1项，0.13秒通过，不新增测试项。准备同URL第3轮。

第3轮首次启动在explicit_retry阶段被第2轮review_required作业拦截，网页/模型派发均0，不计入真实采集轮数，原启动记录保留于round-03。统一修复执行闭合与模型格式待审混用：新增显式closed-execution授权，核验原自然退出、完整派发证据、全部请求已有确定结果、runtime原rejected且非unknown/interrupted后追加许可事件；旧job/request/失败及费用不改写。第2轮只读闭合审计1.79秒通过（11次派发，3个确定请求），内存模拟许可后公共guard放行。实际第3轮使用新目录round-03-live，沿用原账与原目标，不重发旧请求。

## 第3轮结果与第4轮修复

第3轮实际尝试34.554秒，正式attempt已建立，模型请求0、业务动作0、正式保存0，database is locked；源码无漂移。原错误误记为semantic且runtime根因只剩分类，此历史事实保留。collect_runtime已将SQLite OperationalError归program，并保留实际异常、root_cause与日志，最小内存检查0.065秒通过。

agent_feedback.site_context持活查询游标调用job_conflicts，再递归读取同一模型账。隔离复现“外层读游标→写事务等待提交→内层新读取”报锁，先fetchall结束游标后同场景通过；相关只读CandidatePool调用显式readonly。正式库authorizer禁止写SQL后，最新r3 guard_original_dispatch与site_context均通过，unresolved=0、写SQL=[]，20.756秒。原第3轮无堆栈及并发writer日志，因此已证实的是实际代码路径的锁序列风险，未捕获当时具体writer。证据见sqlite-read-lock-diagnosis.json及附带复现脚本。第4轮沿原账正常retry，不制造第3轮raw或闭合凭证。

## 第4轮成功与标准文件

第4轮482.902秒，15个有效业务动作（click5/hotkey3/type3/scroll4），annotation包含另1个complete终态，共16条记录。9笔真实模型请求，8 succeeded、1 invalid_response后纠正成功；input152615/output16721 tokens，无新增UNKNOWN、无源码漂移。原目标7项全部VERIFIED；页面输出72.00 cu ft、2.67 cu yd、120袋，页面“运作原理”提供除以12和0.6的依据，工程分别复算72与120并比对独立结果证据。RuntimeStore为collected_pending_review，正式保存1，sample_id=S000001_sample_000007，strategy-result与saved_sample收据一致。

正常package入口导出[delivery/202611120125](../delivery/202611120125/)，标准目录结构检查通过，16条annotation记录及原图树保留，包外索引为customer-package.evidence.json。独立AI QC、人工审核、发布均未进行，客户验收UNKNOWN；该包用于后续annotation核对，不代表已获客户验收。第二条URL的授权上限为探测生产一条、候选有效后消费一次；实际结果见下文，不开启持续批量。

## 第二条探测结果与最后收口

第二URL为真实第一方链接https://www.muxtly.com/zh-CN/paint-calculator/。原scope已有producer路径但model=null、账本不存在；备份配置后补齐模型引用与必要预算，在原绑定路径正常初始化，无旧账替换。正常生产GET3、模型2、search0；站点分类成功为“在线工具”，页面资格请求收到HTTP429/provider1113（本次所选账号余额/资源包不足），原request=93f71672a8154313a359d3e3a8f2a51d保留UNKNOWN。两笔请求账号不同，不能推断全部账号无额度。新候选0、第二页消费者尝试0、正式保存0。完整body/headers、provider请求ID与usage未留存，费用用量未知，未换账号重发或绕过隔离。

另一次directory JSONDecodeError来自本次来源准备把HTML放入实际要求JSONdocument的复用位置，独立于HTTP429。原输入保留、修正输入草稿另存。已统一修复application_discovery.reusable_source_document与grounded_entries目录、homepage来源复用：先验原hash；普通HTML/其他提示回到原受账取源；仅URI一致、正常GET原job已done且引用和raw_html哈希有效的JSON文档才复用，不凭hint制造页面事实。一轮最小离线复现3项通过（JSON复用、HTML取源、坏hash拒绝），0.0044秒；正常取源在夹具中stub，没有新增维护测试，修改后真实HTTP/GLM未再运行。

最终汇总见[完整报告](../verify_results/muxtly-agent-loop-20261112-002523/report.md)。本轮24笔真实模型请求为20 succeeded、3 invalid_response、1新UNKNOWN；已知input375812/output37774 tokens，未知费用不填0。原37笔请求、3条attempt、3条claim的选定事实哈希保持一致。第一条成功仍是待审保存，不等同第二条、所有站点或生产者全链已通过。
