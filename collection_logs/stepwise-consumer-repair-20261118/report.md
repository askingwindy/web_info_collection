# 策略3消费者启动前修复与离线验证

2026-11-18（Asia/Shanghai）。本轮按用户发送“结束”后的材料直接修当前实现。代码、受影响核心检查、本地正常消费者入口六链与交叉复审已完成；没有启动故宫/Muxtly 20页试采、真实模型或生产消费者。

## 实际结果

- 最终本地六链：6/6 正式保存为 collected_pending_review、6/6 候选回写、6/6 正常客户导出并逐文件摘要读回；146/146 检查通过，66.617秒。产品源码和驱动器在运行中均未改变。
- 受影响核心8个不同执行项最新全通过；累计14次执行，12P/2F，pytest合计1.65秒。两次失败为测试夹具适配，原日志保留。未跑全量核心。
- 维护47个测试方法；原有1个两场景subTest展开后共48项，仍≤50。collect-only不是全量测试通过证据。
- 真实GLM/远端页面请求/生产新增均0；QC/人工审核NOT_RUN，published=false，客户验收UNKNOWN。隔离夹具的模型传输替身走真实ModelGateway解析和账本，不能证明真实模型的任务质量或保存率。
- 正式池只读核对故宫本批100个候选：100个requested_goal为空、0个有指定目标、claim为空，均进入自主模式。见[只读回执](palace-goal-readonly.json)。没有领取或写回正式候选。

## 改动与对应问题

| 问题 | 当前实现与验证范围 |
|---|---|
| 页内点击效果遗漏 | business_view加入完整可见文字、可操作控件文字/状态、焦点/选区、页内滚动及图片来源；语义变化和解码截图像素变化同时成立才计有效。标签、展开、计算结果、输入焦点/全选有真实本地链；内滚动和图片来源由核心断言验证。 |
| 有效数与交付冲突 | annotation也使用像素比较，不能用PNG编码元数据变化当效果；保留但未证实可见效果的非wait动作在complete前按collector拒绝，不删除原件、不耗回写后再报program。 |
| 新标签与慢链接 | 点击前安装源页popup/主帧导航监听；新页切换、back回opener；已知href等5秒，无href额外短等1秒，back仅commit。已知链接有界等待仍未落地且视图未变时navigation_unconfirmed停止，不误记no_effect或重击。 |
| 跨页保存接线 | raw step.state改为真实动作前帧，后帧独立after_state；绑定真实anchor/focused元素，供现有导航证明读回。直链target=_blank与1秒延迟同页链接均经试点身份、RuntimeStore和导出正常保存。 |
| 站点与排除规则 | 从已核验application_registry扩展同application别名，不放开任意子域；URL按路径单词边界匹配，display/cartoon不误伤。已知越界/排除/非网页协议在派发前拒绝并反馈。 |
| 实际越界恢复 | 未预知的越界落地与宿主返回各有真实独立原件，返回后继续观察。无法证明安全省略的越界轨迹不保存；不把外部动作隐藏成正常交付。 |
| 请求预算与异常 | 调用账本requests_used计数，决策含终态最多34HTTP；used=33仅允许1笔，给两次回写与一次判定保留6笔，总限40不变。预算异常model、截图超时collector，显式用户取消interrupted不被覆盖；恢复后截图失败保留action_executed=True，不冒充未知派发。 |
| complete协议与B | 缺status按字段错误拒绝，可修正；修复原非法决策记录传不存在参数导致TypeError。自主success不足5最多驳回2次，第3次short_flow；infeasible先给1次改任务机会，共用总上限。指定目标不扩展。只在接受时写complete与时间。 |
| B进度与记录 | 派发上限20、有效5–12；提示优先5–8个自然操作，覆盖第1步起全部动作，不往返凑步。无效果反馈明确连续N/3；独立complete-rejection原件、初始/最新目标、修改次数进入终态和runlog。 |
| 回写和判定 | 回写含初始/最终任务、页面、本步目标、输入、方向、选项与按键；字段/末帧引文机械失败可基于同证据重写一次，两次原件都保留。历史动作叙述不改；判定只调用一次，冗余/不符必须空。 |
| 历史提示与扫描 | SQL先限同入口页，读已保存annotation/finalization真实指令；不读占位指令。不扫描全站历史证据，精确读取当前候选未决attempt及请求/作业，包括没有attempt_id的task-generation UNKNOWN/reserved。 |
| 失败图片引用 | 在raw与stepwise目录按截图摘要找真实原图；不覆盖已有不同摘要的样本图。反馈引用均指向存在且摘要匹配的文件。 |
| 输入与上下文 | 已聚焦、可见启用、可编辑普通输入允许Ctrl/Cmd+A，再type覆盖；不泛开字母快捷键。超限元素从尾部裁剪，保留靠前业务控件。 |

产品共9文件：stepwise/{session,observation,prompt,collection,finalize,records,annotation}.py，agent_feedback.py，browser.py。没有新增策略、模板或协议代际，没有修改生产数据库、释放历史claim、重发UNKNOWN、恢复旧任务。

## 最终本地全链

每条均使用独立新隔离工程、真实本地HTTP+Chrome、正常candidate_consumer命令。外部模型传输、账号可用性探针和DNS前检为明确离线替身；没有替换真实浏览器动作、保存、候选回写或导出。

| 场景 | 有效/派发 | 模拟HTTP | 保存/导出 | 秒 |
|---|---:|---:|---|---:|
| 五次页内标签切换 | 5/5 | 8 | 成功/成功 | 11.795 |
| 五次展开内容 | 5/5 | 8 | 成功/成功 | 11.453 |
| target=_blank→新页四项资料 | 5/5 | 8 | 成功/成功 | 10.746 |
| 1秒延迟链接→详情四项资料 | 5/5 | 8 | 成功/成功 | 10.790 |
| 自然3步→B扩展5步，回写引文纠正1次 | 5/5 | 10 | 成功/成功 | 11.550 |
| 默认100→全选覆盖50→计算→展开说明 | 5/5 | 8 | 成功/成功 | 9.495 |

B场景的封存终态记录complete_rejection_count=1、task_modifications=1，回写原件2份、判定原件1份，最终5个有效动作完整保存。已查看终态图片，确认popup已在藏品资料页；覆盖输入场景数量和计算结果均为50。

第一次local-r01保留：69.381秒、74项检查54P/20F，六条中5条保存、0条导出。五条导出被夹具的泛化末步user_goal合理拒绝；展开夹具第五按钮滚出视口导致离线替身AssertionError，隔离账本保留该笔UNKNOWN（没有重发）。仅修夹具文案/布局后用全新隔离候选复验；同时在全部退出后补修交叉审核发现的scheme/超窗导航/恢复超时问题。r01的原件、失败、UNKNOWN和已保存状态均保留，不能用r02覆盖或改判r01。

## 检查与复现

- [最终检查回执](local-r02/report.json)、[汇总](verification-summary.json)、[交叉复审](independent-review.md)。交叉审核明确区分自查与不同代理实现，不把自身实现称为全独立审核。
- 核心日志：core-observation-r01/r02/r03、core-session-r01/r02/r03、core-feedback-r01、core-browser-r01；47方法盘点见core-inventory.log。
- 驱动器[local_cli.py](local_cli.py)复用只读历史stepwise-switch驱动的工程初始化和正常CLI检查，新增本轮页面与模型替身；每轮各自source-before/source-after用于审计，不增加源码运行门禁。

```sh
projects/code/.venv/bin/python collection_logs/stepwise-consumer-repair-20261118/local_cli.py --output /绝对路径/一个尚不存在的新隔离目录
```

失败复验仅针对本轮未通过或修改影响的链路；没有重跑旧生产候选。工作开始已有生产者取证修复及文档改动，期间观察到这些改动已进入0490c04；本轮未执行commit/push，也未回退、覆盖它们。

## 尚未验证的边界

1. 真实模型能否自然扩展、是否会凑步、真实no_effect/short_flow/冗余判定比例及成本，必须由另行启动的试采提供事实。离线脚本化判定不代表独立QC或真实规划能力。
2. 原生date/time/month/week/datetime-local的统一type仍不支持；没有以fill或脚本改值替代真实键入。本轮修复普通输入覆盖，不宣称日期控件已支持。
3. 超出短等待窗口的无href异步popup、复杂重定向/JS来源证明、真实站点别名/导航和恢复质量未做远端实测。已知超窗链接安全留证停止；未知实际越界恢复后仍可能因unsafe_omissions拒保存。
4. 本轮只关闭当前策略3范围内核实的问题，不宣称历史S1–S6全部问题矩阵已关闭。核心上限保持，旧失败、历史请求与审核事实不改写。
