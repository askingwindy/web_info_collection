# 策略3切换与工程链路减负实施报告

日期：2026-11-18（Asia/Shanghai）。结论：**本轮授权范围已完成本地修复与离线验证；真实采集未运行。** 对应[SSD](../../docs/无版本无SHA减负与必经缺陷修复SSD-20261118.md)。最终机器回执：[final-summary.json](final-summary.json)。

## 实施结果

- WP-S：缺省/唯一新采集策略为stepwise。旧react/screenshot_plan、旧别名、历史任务续跑，以及直接collect/preflight/scheduler与固定/普通worker计划入口，在领取或预留、浏览器、模型/账号探针之前拒绝，复用Strategy1Forbidden/global/CLI退出2。每attempt策略冻结不切换。历史strategy_id/enabled/save_eligibility、execution_entries、报表与QC读取保持原解释；策略2实现保留。
- WP-A：删除指定源码比较、执行前全部task/plan快照读取与排队锁；源摘要继续记录。固定cohort只比对业务身份/版本和真实收据，三项审计摘要不拦截。旧scheduler续跑整对象比较排除源码字段并沿用原审计记录，preflight结束不因源码变化拒绝。样本/原件完整性、候选独占和图片去重保留。
- WP-C：异常统一封存与分类，失败派发和后帧错误保留真实动作原件；select按本帧label/disabled预检；装饰几何剔除并留原因，目标/祖先不支持仍拒绝；ui_tree投影13字段。全部4xx含408/429为failed、cost=0、原请求不重发；5xx/超时UNKNOWN。冷却与五处挂起/隔离读取、两个生产者捕获点同步。无渲染观察一律HELD；图片/保存文件核验前移写事务外；请求timeout按硬截止剩余预算裁剪。
- WP-B/D：JSON原文直通、绝对路径，删除workspace路径ContextVar、SQL参数改写和marker创建。16个退役模块删除并迁出必要依赖，QC历史tests整目录删除，零碎不可达/常量分支清理。删除前逐模块全仓检索，删除后Python代码引用为0，见[删除审计](deletion-reference-audit.json)。
- 正常CLI导出的新任务规划说明修正为stepwise，保留实际系统提示。AGENTS、README、工程说明、设计说明和SSD已同步；原策略3SDD仅状态行追加链接，正文逐字核对不变。

本机起始HEAD已为5bf37d7且工作区干净，与用户指导中旧机器状态不同；没有fetch/reset或覆盖源码。根.venv已创建并安装公开依赖，已有projects/code/.venv与原离线脚本保留。测试与集成使用临时/独立verification工程，正式库与历史原账未操作。

## 核心测试

| 阶段 | 结果 | 时间 | 原件 |
|---|---|---|---|
| 原始基线 | 50 passed、3 subtests passed | 35.30秒 | [baseline-pytest.log](baseline-pytest.log) |
| 首次集中全量 | 39 passed | 2.80秒 | [final-core-r01.log](final-core-r01.log) |
| 最后两处门禁补修 | 2个既有项passed | 0.16秒 | [remaining-gates-core-r01.log](remaining-gates-core-r01.log) |
| 最终全量 | **39/39 passed** | **2.42秒**；进程2.638秒 | [final-core-r02.log](final-core-r02.log)、[命令回执](final-core-r02.json) |

按用户D8授权，删除9个策略2completion/save专属项和6个直接会话runlog项，新增4个核心项（异常收口、4xx、执行门禁、QC源码审计），其余关键覆盖并入原用例。总量50−15+4=39；视觉3项保留共享浏览器保护。没有新增参数化展开项或维护第二套隐藏测试。先前局部失败、夹具修复和复验日志均保留，见各子组记录；最终通过不抹去这些失败。

## 七种离线场景

复用原脚本，增加失败及select/几何场景。全部经正常消费者CLI、真实本地HTTP和Chrome；网关外部传输为离线替身。未加载真实凭据、未探测真实账号。网络案例在back导航接缝引向本地空响应服务，触发真实Playwright网络错误；这是明确的夹具注入边界。

最终覆盖为 **local-r03四条保存链85/85 + local-r02三条失败链51/51**，共136个检查。r03总墙钟 **29.593秒**；r02原七链总墙钟37.647秒，三条保留失败场景各自耗时见下表。不是一次最终源码的七链整轮重跑，也不把r02整轮改记PASS：其后只修改旧入口/预检门禁和新任务导出说明，失败出口实现未再变。

| 场景 | 回执 | 有效步 | 终态 | failure_class | 模型替身次数 | 场景秒 |
|---|---|---:|---|---|---:|---:|
| 操作 | local-r03 | 5 | 保存+CLI导出读回 | — | 8 | 6.740 |
| 阅读 | local-r03 | 5 | 保存+CLI导出读回 | — | 8 | 8.461 |
| select不存在→纠正 | local-r03 | 6 | 保存+CLI导出读回 | — | 10 | 7.275 |
| 装饰元素旋转 | local-r03 | 5 | 保存+CLI导出读回 | — | 8 | 6.498 |
| 短流程 | local-r02 | 0 | 失败封存；不保存 | collector | 3 | 3.334 |
| 协议失败 | local-r02 | 0 | 失败封存；不保存 | model | 2 | 2.010 |
| 本地网络失败 | local-r02 | 0 | 失败封存；不保存 | network | 1 | 2.081 |

四条保存链都通过领取→逐步执行→raw封存→回写→单独判定→annotation→RuntimeStore→verified_saved→候选回写→正常CLI客户导出→candidate-receipt及全部文件读回；导出为EXPORTED_FORMAT_VALID。三条失败链claim=failed、原始封存存在、不保存、不导出，协议/网络不计program。不存在选项不派发，下一轮纠正后6个真实有效动作。几何核心另覆盖旋转目标/祖先拒绝与禁用optgroup。

每条生成后注入变化的源码审计返回值，整个consumer CLI禁止调用registry_snapshot；A1/A9检查通过。各轮源码及driver前后摘要相等，自有driver/Chrome进程已退出。选定七场景模型替身共40次，真实模型HTTP/目标站请求/生产新增均0。模拟token不是生产费用证据。

回执：[r03检查](local-r03/report.json)、[r03逐链核账](local-r03/accounting.json)、[r02失败出口及原整轮检查](local-r02/report.json)、[r02逐链核账](local-r02/accounting.json)。

## 首轮失败与补修证据

1. integration-r01：107检查、104通过、3失败。select替身引文不在可见交付帧，正常拒收；driver无candidate_results时误索引None。另查到目录名integration触发现有导出隔离，driver后续手工导出掩盖正常CLI内部失败，因此本轮不作完整全链证明。保留所有原件；只修夹具引文/None处理，后续改用中性目录并强制验证CLI自身导出，不改保存资格。
2. local-r02：136检查、132通过。4条保存链的导出说明沿用ReAct文字，其余执行、保存、候选回写、CLI导出结构及读回正常。修正新任务production_facts.description后，只复验受影响4链，local-r03为85/85。三个失败出口继续引用r02，不重复无关链路。
3. 交叉走读发现并关闭直接collect/preflight旧入口、scheduler/cohort预留前拒绝、fixed resume父异常接线、plan.json缩进、cohort残留SHA、scheduler整对象SHA及preflight尾部门禁。C8的pilot verify_saved额外文件核验也前移到事务前，事务内仍重核身份与去重。

审核：[路径/入口交叉审核](independent-readonly-review.md)、[最终交叉审核](final-cross-review.md)。分组记录：[stepwise](stepwise-notes.md)、[gateway](gateway-notes.md)、[路径与删除](paths-notes.md)。本轮审核从实际调用链发现并修正问题，不以修复者自评代替验证。

## 静态核验与边界

270个工程Python文件AST解析通过；git diff --check通过；指定删除模块代码引用为0。最终239个产品源码文件与local-r03运行后摘要逐一相同。stepwise prompt/records/finalize与HEAD字节相同，未改提示词、schema、预算常量或保存资格。原策略3SDD状态行以外内容不变。新SSD为本地文件，未add；暂存区为空。

A7仅按指定sampling/delivery及关联缓存实施；document_text_qc独立CLI保持基线，历史语义请求身份中已有源码字段未扩改，避免另造身份触及UNKNOWN。保留原件完整性与旧策略内部同次运行检查，不宣称全仓所有SHA字段或所有历史快照工具均删除。C13裁剪socket超时，持续trickle响应仍依靠既有hard watchdog，不将socket inactivity timeout误称单独总墙钟保证。

D5本地commit、D6释放51个旧claim仍未决，因此均未执行；未push、PR或上传。旧claim、UNKNOWN、费用和失败原件保留。真实20页/100页需另行授权；QC/人审NOT_RUN、发布false、客户验收UNKNOWN。离线通过只证明本轮工程行为，不证明真实合格率或客户验收。
