# 新Agent执行Prompt：第2步两条Muxtly固定目标回归

你在 `/Users/hemiao/projects/2610/WebCollect` 工作，使用 `gpt-6.1-sol / low`。用户将本Prompt作为执行任务交给你时，授权以下一次固定两条真实回归；不需要重新请求已列明的常规启动许可。原编写会话只修代码，没有启动该任务。

## 唯一目标与边界

验证当前代码能否重新完成两个历史成功的Muxtly固定目标，经正常消费者执行、RuntimeStore保存、候选回写和隔离导出。不是20进程100页采集，也不是跨站扩批。

- 固定两条，顺序执行，同时最多1个消费者；每条最多一次正式执行，不补位、不换目标、不自动修复重跑。正常模型/页面失败如实记录；新工程故障停后续派发。
- 真实模型沿现有GLM配置，first-plan/branch均high；按现有token.yaml账户轮换机制选择本轮可用账号，不打印密钥、不改变旧请求绑定。
- 不运行单元/集成测试、独立AI QC或人工审核；正常保存链内置的真实性与格式校验必须执行。QC、人工NOT_RUN，发布false，客户验收UNKNOWN。
- 不改生产源码、默认配置、历史claim、原始证据、费用或UNKNOWN；不清理任何目录。运行期间源码与新执行驱动保持不变。
- 不重发UNKNOWN，不换Key/任务身份规避旧请求隔离。所有结果使用新的验证身份，不向prod发布新增候选或成功计数。

## 先读与只读核验

1. 当前AGENTS.md及 `docs/工程阻断修复与基线代码准备-20261113.md`。
2. `verify_results/stage12-code-optimization-20261113-r01/root-review-final.json`、`baseline-selection.json`。
3. `database/sqllite/baseline/baseline-success-20261112.sqlite3`，只读打开；它不是采集工程库。
4. 核实当前源码、这两条原始计划和保存引用仍与准备记录一致。历史五条当前sealed replay未通过；不能将旧包完整性PASS写成当前成功回归。

解释器固定 `projects/code/.venv/bin/python`，设置 `PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector`。不安装新环境。

## 固定任务

以`baseline-selection.json`中的原路径、SHA与goal字段为权威，以下文本应逐字一致：

1. 历史样本 `S000001_sample_000036`，原候选 `candidate-9a86e690-9ba8-4285-bb18-294f68cb8d24`。
   URL：`https://www.muxtly.com/zh-CN/australia-luxury-car-tax-calculator/`
   目标：`在澳洲奢侈车税计算器中输入车辆价值 95000 澳元（普通车，不勾选节能车），点击计算得出奢侈车税结果，并展开「运作原理」核对该结果所依据的税率与门槛说明。`
2. 历史样本 `S000001_sample_000033`，原候选 `candidate-9beb607d-598f-48f6-91f5-f7861a9bdd3f`。
   URL：`https://www.muxtly.com/zh-CN/australia-negative-gearing-calculator/`
   目标：`在澳洲负扣税计算器中输入年租金收入30000、年租金支出40000、其他应税收入90000并点击计算，核验页面输出的租金亏损、可抵减的应税收入与节省的税款。`

原claim分别为`cb99d986-ca11-40ba-bb35-78277aa5295d`、`9769ce19-6b0f-4135-802f-8806cea3ae97`。历史原件只读作为目标来源，不重用历史答案/图证证明新执行。原计划和有效步分别5/5、5/8；本次仍须自然首轮至少5个必要动作、实际至少5个有效动作、原目标完成，不照抄旧动作链、不凑步。

## 准备新的隔离输入，不启动生产者

- 创建唯一run ID及新的`database/sqllite/verification/<run>/`持久根、`results/<run>/collections/`输出、`verify_results/<run>/`回执。先确认不存在，禁止覆盖。用已有`candidate_project.initialize()`或`candidate_project init --root`正常建立新scope和五库；必要的BatchLedger初始化使用现有入口，不直接拷贝prod五库。
- 从当前prod配置读取有效模板，由initialize重新绑定新project、run、guard、manifest、registry；不得继续使用prod scope/ledger路径。可用`numbering_from`只读继承旧编号高水位。建立新输入时逐项核对输出与持久库都属于新工程。
- 通过已有CandidatePool.put发布恰好两个`candidate_kind=entry`、`requested_goal=null`候选。来源明确`origin=baseline_import`，记录原候选/样本、原始目标、基线文件和本Prompt授权的引用，不伪造新模型生产者响应。
- 站点分类与来源来自原真实candidate_sources及其有效证据，不猜类别、不填UNKNOWN凑过。必要来源原字节复制到新工程持久证据目录，记录原路径、原SHA和新路径；不改历史源文件，不搬旧claim/tasks/results。新来源使用新的引用绑定；遇当前项目/分类合同不满足则报告具体阻塞，不能删校验字段绕过。
- 为每个新候选单独建立session objective文件：当前`SESSION_OBJECTIVE_PROTOCOL`值、新candidate_id/version、相同entry_url、requested_goal=null，objective.description取上述原goal，minimum_effective_steps=5、preferred_band=five。不添加额外业务目标或新的结果类型。
- 为每条生成仅含该新候选的合法固定cohort，复用`candidate_consumer._cohort_rows`现有格式核对pool/registry/身份，防止两条目标文件错配候选。保存计划、完整argv、源码摘要、输入摘要和名单后再启动。

## 正常执行入口

使用当前已接通的 `python -m webcollect.candidate_consumer --pool <新pool> run`，每条argv必须包含新scope对应的`--config`、`--ledger`、`--output`、`--registry`、`--policy`、`--history-set`、独立`--worker-id`与`--request-prefix`，以及：

```text
--limit 1
--cohort <本条固定cohort文件>
--session-objective <本条objective文件>
--collection-strategy screenshot_plan
--first-plan-effort high
--branch-effort high
```

上面的尖括号是说明，先用新scope实际绝对路径生成argv再执行。CLI会读取objective文件并传path/SHA给既有bind链；不能把字符串goal塞进requested_goal，也不能绕过正常claim/候选独占。

首条结账并审查后才启动第二条。正常已知页面/模型失败可以继续第二个固定任务；出现程序故障、SQLite错误、身份/保存链不一致则停止后续派发并记录未尝试数量。UNKNOWN保留且不重发，第二条是否可执行服从原隔离规则。

禁止直接执行旧`run_verification.py`或100页驱动：它们硬绑旧prod、站点数量、并发或停止逻辑。不要启动连续consumer_campaign main来替代两条固定执行。

## 保存、隔离导出与收口

- 每条必须经原正常RuntimeStore提交及candidate_results回写，用`verified_saved()`读回；保存失败不手工构造saved_sample、success或导出收据。
- 对真实合格保存，复用consumer_campaign.deliver/publish_pending或现有同等正常打包入口，在本轮隔离回执中排队导出到新的`results/<run>/verification-export/`。这不是prod新增或客户发布；保留source_receipt、文件SHA和原始采集目录。不导出异常、short_flow或未完成样本。
- 导出状态如需要campaign文件，只在新工程创建正确的新状态，由既有API维护；不能复制旧campaign并删字段。该状态用于导出，不启动持续调度。
- 源码运行期间若发生外部改动，停后续派发并如实记录，不把不同源码结果混成同一基线。
- 等全部本轮进程退出、在途模型请求按原边界结账；原UNKNOWN保留，禁止为了收口伪造状态。产物不自动清理。

最终逐条给出：新旧身份对应、固定目标一致性、claim/attempt、首轮和有效步数、目标核验、正式保存、候选回写、导出/哈希、失败阶段与原始原因、模型请求/invalid/UNKNOWN/已知用量/未知费用、源码前后摘要、PID退出情况。

只有两条新执行分别通过原目标、有效步、正常保存及隔离导出，才可称“两条采集保存链回归通过”；QC未运行，不能称QC或客户验收通过。若失败，明确是入口、计划、动作、完成证据、保存还是导出，不继续修复或扩批；回到主会话分析。无论结果如何，不自行进入跨站阶段或20并发。
