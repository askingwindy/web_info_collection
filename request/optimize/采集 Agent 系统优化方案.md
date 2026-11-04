先说清楚:你的地基是对的,要保留——生产者/消费者分层、t1/t2 拆分、分类≤20% 配额、消费者用"目标+tools 的 ReAct"驱动。这些都不用推翻。下面只讲增量。

一、根本差异(概念层面,不是工程细节)
维度	你的当前方案	升级方案	差异的本质
规划粒度	per-page(每页一次完整 ReAct 规划)	per-template(一份模板覆盖一类页面)	你把每页都当"新问题",升级把同类页当"同一题的不同实例"
规划与执行	耦合:ReAct 在线一步步跑,边规划边执行	解耦:规划产出可回放轨迹,执行无 LLM 纯并发	你 10min 里有规划又有执行;升级后 10min 只剩规划,执行降到秒级
失败处理	失败即放弃/阻塞该页	降级兜底 + 失败页进提升队列	你追求"规划成功才算数",升级追求"每页必有产物,质量分层"
知识积累	每次规划用完即弃,无沉淀	成功规划→沉淀模板→下次复用	你是"一次性"系统,升级是"越跑越省"的飞轮
冷启动	新站从 0 ReAct(易失败)	warm-start 用同 category 骨架模板起步	你让模型"白手起家",升级让模型"带着经验上岗"
一句话压缩: 你的系统是「线性消耗」的——每页 10min,跑完即丢;升级后是「指数摊薄」的——每模板 10min 一次,同结构页秒级复用,模板库越用越满、越用越快。

# 采集 Agent 系统优化方案

> 输入 URL → 规划操作路径 → 截图采集,最终目标 **采集 20w 条数据轨迹**。
> 本文档覆盖三大优化:① 总工程架构升级 ② 生产者 ③ 消费者。

---

## 一、背景与现状

### 1.1 系统现状
- **生产者(Producer)**:持续挖掘新网站 + 每个站下的可操作网页,写入数据库。
  - `t1` 表:站点信息(`site_type`=百科/站点操作/订票…,`category`=生物/操作/小游戏…)。
  - `t2` 表:页面信息(关联 `site_id`)。
  - **约束:每个分类占比 ≤ 20%。**
- **消费者(Consumer)**:对 DB 中已存在的网页做采集规划。
  - 当前用 **ReAct(设定目标 + tools)** 驱动。

### 1.2 核心痛点
| 痛点 | 现象 | 量化后果 |
|------|------|---------|
| 规划慢 | 每页完整规划 ≈ 10min | 20w × 10min ≈ 1388 天 ≈ 3.8 年(串行) |
| 新站失败 | ReAct 从 0 探索未知页 | 失败率高,页面卡死 |
| 配额风险 | naive 持续挖掘 | 撞 ≤20% 顶,合规违约 |
| 无沉淀 | 规划成果用后即弃 | 越跑越慢,无飞轮 |

### 1.3 关键判定:单靠加并发不够
```
20 并发 ReAct 仍需 ~70 天
```
**10min/规划 这个数本身必须降下来**——胜负手不是堆算力,而是让 10min 不再分摊到每个页面。

---

## 二、核心设计原则:三杠杆

| 杠杆 | 作用 | 预期收益 |
|------|------|---------|
| ① **模板化复用** | 同站点/同结构页面共享一份规划 | 规划量从 20w 降到 千~万级模板 |
| ② **规划/执行解耦** | 规划产物是可回放轨迹 JSON,执行无 LLM、纯并发 | 执行成本 10min → ~30s/页 |
| ③ **双队列并发** | Planner 队列与 Executor 队列独立扩缩 | 线性加速 |

**目标:把 ReAct 从"每页 10min 的 Executor"压成"每模板一次的 Planner",稳态执行全走秒级模板。**

---
## 三、第一部分:总工程架构升级

### 3.1 两层规划 × 两个方案矩阵
路径规划分为两层,各自选型:

```
输入: 站点入口 URL(+ site_type: content / tool)
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ 层 1:站点级发现 Agent(给出"采哪些页")               │
│   方案1 确定性: sitemap/爬链/搜索 → URL 清单+去重    │  ← Wiki 适用
│   方案1 变体:   直接给定页面清单                      │  ← 工具站(20 页)
├─────────────────────────────────────────────────────┤
│ 产出: 采集任务清单 [{url, page_type, seedHints}]     │
└───────────────┬─────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────┐
│ 层 2:页面级采集 Agent(给出"每页怎么走")             │
│   方案1 确定性编排: 模板步骤静态生成                   │  ← Wiki 主路径
│   方案2 ReAct 动态:  在线观测→决策→执行→校验          │  ← 工具站/Wiki 兜底
├─────────────────────────────────────────────────────┤
│ 共享内核: Planner / Executor / Perceiver / Memory     │
│           / Verifier / ScreenshotStore / SafetyHook   │
└───────────────┬─────────────────────────────────────┘
                ▼
采集产物: 轨迹序列 + 每步截图 + 页面结构摘要 + 采集报告
```

### 3.2 生产者 ↔ 消费者数据流与接缝

```
Producer 拥有(只读给下游):
  t1 site   { site_id, type, category, default_template_id?, quota_slot, homogeneity }
  t2 page   { page_id, site_id, url, page_type, structure_fingerprint, quality_flag }

Consumer 拥有(自己产生、自己用):
  template  { template_id, category, structure_fingerprint, steps[],
              reuse_count, success_rate, last_updated }
  trajectory{ page_id, template_id, shots[], status }
```

**关键接缝:生产者产"匹配键"(structure_fingerprint),消费者产"可复用计划"(template)。**

### 3.3 模板归属:消费侧正本,不是站点侧

> **结论**:模板正本放**消费侧**消费者 template 库;`structure_fingerprint` 由**生产侧**预产写入 `t2`;`t1` 可带 `default_template_id` 指针,仅作 warm-start 快路径。

**为什么正本在消费侧(3 条理由)**
1. **模板按"结构指纹"匹配,不按"站点身份"绑定**。跨站同结构页面要能共享模板——这是把复用率从"站内"放大到"类内"、把 10min 摊薄到天花板的关键。绑 site_id 会杀掉跨站复用。
2. **模板是规划产物,只有消费者会生成它**。让生产者持有模板就得反向调消费者生成,职责反向。
3. **模板生命周期(命中/成功率/失效/再生成)与站点存在与否无关**。站点下线模板仍按结构复用,归属跟着"谁用谁管"走。

**为什么"站点侧"是陷阱**
- 把模板和 site_id 锁死 → 杀掉跨站复用(吞吐命门 C1 重新存活);
- 让生产者承担不该有的规划职责;
- 站点下线/迁移时模板一起丢,知识归零。

**`t1.default_template_id` 的正确用法**:同站第一页规划成功后回写指针,同站后续页**先试站点默认模板**(零匹配成本、最高先验),不行再回退到结构指纹匹配。它是**指针/捷径**,模板正本仍在消费侧库。

### 3.4 预期账(假设平均复用比 1:30)
```
模板数 ≈ 20w / 30 ≈ 6,700 个
需 ReAct 规划 ≈ 6,700 × 10min ≈ 67,000 min
执行:    20w × 30s ≈ 100,000 min
Planner 并发 15 + Executor 并发 40:
  规划 ≈ 75 小时 ≈ 3 天
  执行 ≈ 42 小时 ≈ 1.7 天
  重叠流水(规划与执行并行)≈ 3-4 天 ✅
```
**目标:一周内 20w,真实可达。**

### 3.5 关键指标(决定能否交付)
1. **模板命中率 / 平均复用率** → 直接决定加速,低了工期崩盘
2. **分类占比实时表** → 配额闸门监控,接近 20% 自动止损+反向生产
3. **单位轨迹成本(元/有效轨迹)** → LLM token + 浏览器实例,决定 20w 预算

---

## 四、第二部分:生产者优化

### 4.1 当前问题
| # | 问题 | 影响 |
|---|------|------|
| P1 | **配额失控**:naive 持续挖掘撞 ≤20% 顶 | 类别比例违约(硬约束) |
| P2 | **噪声页混入**:登录墙/canvas SPA/404/无限滚动 | 下游规划失败,烧 token |
| P3 | **类别判定滞后**:深挖完才知类别 | 浪费爬虫配额在撞顶类别 |
| P4 | **fingerprint 未预计算**:留给消费者算 | 成本错位,活塞回瓶颈端 |
| P5 | **同质度不可见**:站点间结构同质度未知 | 跨站复用上限未知 |

### 4.2 优化方案
| # | 方案 | 解决 | 细节 |
|---|------|------|------|
| S1 | **配额主动调度** | P1 | 预占槽 + 反向生产(主动找欠配类别种)+ 待入库 buffer(超配页停车不丢) |
| S2 | **轻量预分类** | P3 | 深挖前用最小模型/规则判 type+category,决定投不投配额 |
| S3 | **页面质量过滤器** | P2 | 可操作面检测(有无可点/表单),拦截"伪可操作页" |
| S4 | **fingerprint 预计算** | P4 | 渲染时顺手算结构指纹,写入 `t2` |
| S5 | **同质度度量** | P5 | 产出打标,供消费者优先调度 |

### 4.3 核心定位
**生产者是给消费者喂干净、合规、带指纹原料的管线**。吞吐不是命门,**配额合规 + 质量 + 预产指纹** 才是。

### 4.4 配额 ≤20% 的关键实现
- 用**预占槽**而非事后统计:`t_quota: { category, capacity = 0.20 × N_total / 类别数, used }`
- 插入前查 `used/capacity`,接近上限则:
  - 候选页丢 `pending_hold` 队列等待;
  - 或触发**反向生产**:Crawler 优先挖欠配类别新站。
- 配额是"主动调度"出来的,避免浪费已挖内容。

### 4.5 站点内页面发现
确定性优先级:sitemap.xml → 分类页爬链 → 搜索接口兜底 → 人工种子清单。去重:URL 归一化(去 utm_/锚点/排序参数)+ 内容指纹。

---
## 五、第三部分:消费者优化

### 5.1 当前问题
| # | 问题 | 量化 |
|---|------|------|
| C1 | **per-page ReAct**:每页 10min 全规划 | 20w 不可达 |
| C2 | **规划与执行耦合**:在线边规划边执行,无回放 | 10min 含执行,无法摊薄 |
| C3 | **新站从 0 探索失败** | 失败率高 |
| C4 | **失败即阻塞**:无兜底 | 吞吐断流 |
| C5 | **路由不分**:模板/ReAct/hybrid 无判定 | 全走重路径 |
| C6 | **无知识沉淀**:用后即弃 | 越跑越慢 |

### 5.2 优化方案
| # | 方案 | 解决 |
|---|------|------|
| R1 | **模板库 + 指纹匹配**:命中复用,秒级执行 | C1, C6 |
| R2 | **规划/执行解耦**:规划产可回放轨迹,执行无 LLM 并发 | C1, C2 |
| R3 | **ReAct 降级为 Planner**:跑一次生成模板 | C1, C6 |
| R4 | **warm-start**:同 category 骨架起步 | C3 |
| R5 | **降级兜底**:超步/失败套最小采集模板 | C4 |
| R6 | **路由 dispatcher**:可预测性×可枚举性判定 | C5 |
| R7 | **双队列并发**:Planner M + Executor K 解耦 | 吞吐线性扩 |
| R8 | **模板族**:多路径页"一条路径一模板",枚举选择 | 应对路径多 |

### 5.3 ReAct 的两种用法(关键认知)
| 用法 | 干什么 | 频次 | 耗时 |
|------|--------|------|------|
| **ReAct as Planner(离线/生成器)** | 跑一次产出可回放模板存档 | 一页/一类一次 | 10min,只付一次 |
| **ReAct as Executor(在线/驱动器)** | 每步看页面决定下一步,跑完即丢 | 每次执行 | 每天 10min |

> 现状是 Executor → 20w × 10min。**升级的全部意义:把 ReAct 从 Executor 降级成 Planner。**

### 5.4 路由判据:可预测性 × 可枚举性(不是"路径多")

**重要纠正:"动作路径多" ≠ "只能用 ReAct"。** 多路径意味着存多个模板(一路径一模板),不是每条都现场 ReAct。ReAct 的理由是"可不可以提前脚本化",不是"数量"。

| 可预测性 | 可枚举性 | 走法 | 典型 |
|---------|---------|------|------|
| 可预测 | 可枚举 | **模板族**(多条模板逐条复用) | 工具站增删改查页 |
| 可预测 | 不可枚举 | **模板 + 启动枚举器**(一次性 ReAct 列路径,各变模板) | 同类工具页首次见 |
| 不可预测 | 可枚举 | **分段**:稳态段模板,动态分叉段 ReAct | 多步向导 |
| 不可预测 | 不可枚举 | **全程 ReAct 在线**+限步+兜底 | 全新异动态页 |

**一句话准则**:
> 模板负责"可预测的稳态路径",ReAct 负责"不可预测的探索与动态分叉"。能用模板绝不进 ReAct;被迫进 ReAct 的,跑完也要冻回模板。

### 5.5 fingerprint 的作用

**fingerprint = 把一页的"可操作结构"压成可比对小签名,回答"这页和我之前规划过的哪页结构像不像"。**

| 作用 | 说明 |
|------|------|
| 模板查找键 | 进模板库的索引 |
| 决定是否再规划 | 相似度 ≥ 阈值 → 复用;< 阈值 → ReAct。是路由判据输入 |
| 跨站复用基石 | 按结构算不按身份,wiki A 与 wiki B 能匹配 |
| 去重/同质度 | 同指纹簇 = 同模板可服务的页,簇大小 = 复用率预测 |

**关键取舍:fingerprint 只描述"操作面骨架",不描述"内容"。** 同模板 100 页正文千差万别但结构一致;把正文编进去就变成 100 个不同指纹,复用死。
- ✅ 编:可操作元素角色与拓扑(数量/位置/是否可折叠/表单字段类型序列)
- ❌ 不编:文本/标题/图片 URL/动态数据/用户态

**fingerprint 组成(不是单 hash,要支持相似度)**:
```
fingerprint = {
  skeleton: [ {role, depth, order, actionClass} ... ],   // 操作面骨架
  roleHistogram: { "nav-link":6, "collapsible":5, ... }, // 计数向量(快匹配)
  layout: "nav-top | main-content | toc-sidebar | footer",// 粗布局(分桶)
  lsh: "0xa3c4..."                                       // LSH hash(分桶键)
}
```
`actionClass`(submit/expand/navigate/filter)是关键加分项:从"有按钮"细到"有提交型按钮",大幅减少误匹配。

### 5.6 模板匹配:4 段流水线 + 三档阈值

```
新 page.fingerprint
   │
   ▼
[Stage 0] 站点默认快路径(零匹配成本,最高先验)
   拿 t1.default_template_id 直接试 → 高分命中即用,否则进 Stage 1
   ▼
[Stage 1] 粗分桶(快剪枝)
   用 lsh / layout / roleHistogram 把库缩到几十~几百候选 (O(1)~O(logN))
   ▼
[Stage 2] 精排打分
   对每个候选算相似度:
     - skeleton tree-edit distance(容忍元素小漂移)
     - roleHistogram 余弦(容忍数量差)
     - 或训练小 embedding 做余弦
   ▼
[Stage 3] 阈值裁决
   top score ┌─ ≥ Ts(高阈值)        → 复用,直接回放
            ├─ ∈ [Tw, Ts)(灰区)      → warm-start:拿该模板做 ReAct 增量调整
            └─ < Tw(低阈值)          → ReAct 从0规划 → 成功后冻成新模板入族
```

**三档阈值是匹配灵魂**:不止"匹配/不匹配"两态,中段灰区专门处理"页面像但不完全一样"(如 wiki 多了搜索框)——不全盘重规划,也不强行套用,拿相近模板微调。

### 5.7 运行示例(wiki 站)
- **首次见某 wiki 页 P1**:< Tw → ReAct 从0(~10min)→ 冻成 template T1 → 回写站点 `default_template_id`
- **P2~P100**(同站 99 页):Station 0 站点默认路径命中 T1,零匹配成本,秒级复用
- **wiki B 首页**(与 P1 近似,多搜索框):score 0.88 ∈ 灰区 → warm-start 几分钟 → 新模板 T2 入族(跨站复用飞轮转动)
- **全新工具后台页**:库无相似 → ReAct 从0 → 沉淀"CRUD 表单模板族"(增/删/改/查多条)

### 5.8 fingerprint 调参失败模式
| 模式 | 现象 | 后果 |
|------|------|------|
| 指纹过细 | 同模板页算成不同指纹 | 命中率低 → 退化全 ReAct |
| 指纹过粗 | 不同操作页撞同模板 | 复用命中但执行失败 |
| Ts 过高 | 只几乎完全一致算命中 | 灰区页被推去全 ReAct |
| Tw 过低 | 差异大也算匹配 | 套错模板,执行必败 |

**调参方法 = Step 0**:跑 30 页同站页,看指纹分布和步序列重合度,定 Tw/Ts 初始值。复用率指标是这套机制的健康度本身。

### 5.9 安全层(工具站必备)
工具站核心难题是"会不会改生产数据"。SafetyHook:
- `routeHandler` 拦截写操作(POST/PUT/DELETE)→ 返回 mock 200 成功体(白泽数据劫持思路反向用)
- 沙箱账号/测试环境隔离
- 不可逆操作黑名单(删除/发布/支付)直接拒,只截"确认页"留证
- dry-run:截到"确认框"即停,不点确认
- 不可预测段(如"填写直到校验通过")才交 ReAct 在线,稳态段仍模板

---
## 六、落地路线与里程碑

### 6.1 步骤(严格顺序)
```
Step 0(立即,半天):量一次真实复用率
  拿已有 ReAct 跑 2~3 个 wiki 站各 30 页
  记录每页操作步序列标签化 → 算站内步序列重复占比
  → 决定走"轻量模板化"(≥80%)还是"分层规划"(<50%)

Step 1(1~2 周):模板库最小闭环
  template 表 + structure_fingerprint + 规划前匹配 + 命中复用 + 成功沉淀
  验收:模板命中率 ≥80%

Step 2(半周):ReAct 改 warm-start
  system prompt 塞同 category 骨架模板作参考,任务改"在此模板上调整"

Step 3(半周):降级兜底
  超步熔断 + 失败套最小采集模板,t2 不再有长期堆积 failed 页

Step 4(压测后):双队列拆分 + 并发上调
  Step 1~3 跑顺后再上并发——否则更快烧 token 跑废轨迹
```

### 6.2 里程碑
| 里程碑 | 验证什么 | 关键指标 |
|--------|---------|---------|
| M1 模板库+指纹匹配 | 同站 100 页 → 1 规划 + 99 复用跑通 | 模板命中率 ≥85% |
| M2 降级兜底链路 | 异构页失败仍产出轨迹 | 失败页有产物率 100% |
| M3 双队列并发压测 | 5k 页吞吐曲线 | Planner/Executor QPS |
| M4 20w 全量 | 吞吐与配额平衡 | 复用率、分类占比、轨迹有效率 |

### 6.3 整体优先级(两命门并重)
```
并级命门1: 消费者 模板库+指纹复用(R1~R3)         ← 决定能否跑完
并级命门2: 生产者 配额主动调度+预分类(S1~S2)    ← 决定跑完是否合规
     ↓
第二批:   生产者 质量过滤+fingerprint 预计算(S3~S4)  ← 抬高消费者命中率上限
          消费者 warm-start+降级兜底+路由(R4~R6)     ← 抬高新站成功率
     ↓
最后:     双队列并发(R7)、模板族(R8)               ← 决定多快跑完
```

---

## 七、风险与对策

| 风险 | 场景 | 对策 |
|------|------|------|
| 采不全(lazy-load/折叠) | Wiki | scroll_loop 双停条件 + expand_all + 方案2 兜底 |
| 真提交改生产数据 | 工具站 | SafetyHook 拦截 mock 返回 + 黑名单 + 测试环境 |
| ReAct 跑偏/死循环 | 工具站 | Memory 轨迹栈 + 单页最大步数 + 状态哈希去重 |
| 100 页爬取被限流 | Wiki | 并发上限 + robots 尊重 + 退避重试 |
| 输入生成不合理 | 工具站 | 字段类型+约束推导,失败回退固定测试值集 |
| 页面结构变更致用例失效 | 通用 | anchor 三级 fallback(视觉>文本>结构) |
| 复用率不达标(致命) | 全局 | Step 0 先量,低于预期调整 fingerprint 粒度/分层规划 |

---
## 八、核心算法与伪代码

> 本节是唯一"理论顺但实现细节决定成败"的部分。阈值符号(`Ts/Tw/K/...`)均需 Step 0 数据标定,文档只给默认值与含义。

### 8.1 [消费者] fingerprint 计算

fingerprint 只描述"操作面骨架",不描述内容。核心是 `classifyRole` 的归一化粒度——过细则同模板被拆成多指纹,过粗则不同操作撞同模板。**这是整套机制最敏感的调参旋钮。**

```python
OPERABLE = "button, a[href], input, select, textarea, "
           "[role=tab], [aria-expanded], [role=button]"
DEPTH_CAP = 6          # 防止 DOM 深度炸开
ORDER_BUCKET = 10      # 位置量化,容忍微调
TOP_K = 32             # 控制指纹大小与匹配成本

def compute_fingerprint(page, dom):
    wait page.network_idle()
    elems = dom.select(OPERABLE)             # 文档序
    skeleton, hist = [], {}
    for i, el in enumerate(elems):
        role = classify_role(el)
        if role in SKIP: continue
        salience = viewport_visibility(el) * area(el)   # 可见×面积
        cell = {
            "role":        role,
            "depth":       min(el.depth, DEPTH_CAP),
            "orderQ":      i // ORDER_BUCKET,
            "actionClass": infer_action_class(el),       # submit/expand/navigate/query/filter
        }
        skeleton.append((cell, salience))
        hist[role] = hist.get(role, 0) + 1
    # 按显著性取 top-K,再按原文档序排回(保证可比对)
    skeleton = [c for c,_ in top_by_salience_then_reorder(skeleton, TOP_K)]
    layout  = coarse_layout(dom, page)        # nav-top|main|sidebar|footer 四分位
    role_seq = [c["role"]+":"+c["actionClass"] for c in skeleton]
    ngrams   = shingles(role_seq, n=3)
    lsh_sig  = minhash(ngrams, num_perm=128)  # 落同桶用
    return Fingerprint(skeleton, hist, layout, lsh_sig, role_seq)

def classify_role(el):
    # 归一化:只认结构性角色,不认文本/具体值
    if el.tag == "button" or el.role == "button":
        return "submit" if el.type=="submit" else "button"
    if el.tag == "a" and el.href:
        return "nav-link" if is_external(el.href) else "link"
    if el.tag == "input":     return "form-" + (el.type or "text")
    if el.tag == "select":    return "form-select"
    if el.tag == "textarea":  return "form-textarea"
    if "aria-expanded" in el.attrs or el.role=="tab": return "collapsible"
    return "other"

def infer_action_class(el):
    # 按结构性提示给类别,关键:用 hint 关键词集(提交/确认/搜索/展开/查看更多…)做映射
    # 不把具体文本编进指纹,只把"类型标签"编进去
    h = text_hint(el)  # 小写关键词集
    if "提交" in h or "submit" in h or "确认" in h: return "submit"
    if any(k in h for k in ["展开","更多","查看更多","expand"]): return "expand"
    if any(k in h for k in ["搜索","search","查询","query"]):  return "query"
    if el.tag=="a": return "navigate"
    return "default"
```
### 8.2 [消费者] 模板匹配(4 段流水线)

```python
Ts = 0.85   # 高阈值:直接复用(默认值,Step 0 标定)
Tw = 0.55   # 低阈值:低于此即视为不匹配

def match_template(page, fp, site):
    # Stage 0: 站点默认快路径(零匹配成本,最高先验)
    if site.default_template_id:
        cand = template_store.get(site.default_template_id)
        if similarity(fp, cand.fingerprint) >= Ts:
            return Reuse(template=cand)
    candidates = set()
    # Stage 1: 粗分桶(快剪枝,O(1)~O(logN))
    candidates |= lsh_index.query(fp.lsh_sig)            # MinHash 桶
    candidates |= layout_index[fp.layout].filter(..)     # 布局桶
    candidates = [template_store.get(id) for id in candidates]
    # Stage 2: 精排打分
    scored = [(similarity(fp, t.fingerprint), t) for t in candidates]
    top = max(scored, default=(0, None))
    # Stage 3: 三档阈值裁决
    if top.score >= Ts:      return Reuse(template=top.t)
    elif top.score >= Tw:    return WarmStart(seed=top.t)
    else:                    return PlanNew()

# ---- 相似度:结构 + 直方图 + 布局 加权 ----
def similarity(fpA, fpB):
    s_struct = skel_sim(fpA.skeleton, fpB.skeleton)      # 序列编辑距离归一化
    s_hist   = cosine(fpA.roleHistogram, fpB.roleHistogram)
    s_layout = 1.0 if fpA.layout==fpB.layout else 0.5
    return 0.5*s_struct + 0.3*s_hist + 0.2*s_layout

def skel_sim(skelA, skelB):
    # 把骨架线性化为文档序的角色序列,做序列编辑距离(TOP_K=32 时 O(n²)≈1k 次可接受)
    seqA = [c.role+":"+c.actionClass for c in skelA]
    seqB = [c.role+":"+c.actionClass for c in skelB]
    d = edit_distance(seqA, seqB, sub_cost=role_sub_cost)
    return 1 - d / max(len(seqA), len(seqB), 1)
# 注:需更强结构保真可用真 tree-edit(成本 ~5x);量大时可预训练 embedding 算余弦,O(1) 查

# ---- 大规模时的廉价兜底相似度 ----
def cheap_sim(fpA, fpB):
    return jaccard(shingles(fpA.role_seq,3), shingles(fpB.role_seq,3))
```

### 8.3 [消费者] 路由 dispatcher

**判据是"可预测性 × 可枚举性",不是"路径多"**。可枚举 → ReAct 一次性规划每条路径并各自冻成模板(模板族);不可枚举 → 全程在线 ReAct + 兜底。

```python
OP_COUNT_THRESHOLD = 40      # 可操作元素总数上限(超过视为开放操作面)
DISTINCT_ACTION_CAP = 8      # distinct actionClass 上限
MAX_STEPS = 15; MAX_TIME = 180   # 在线 ReAct 熔断

def route(page, fp, match_result):
    if isinstance(match_result, Reuse):
        return execute_template(match_result.template, page)              # 秒级
    if isinstance(match_result, WarmStart):
        return react_incremental(match_result.seed, page)                 # 增量,几分钟

    # PlanNew: 决定 ReAct 用 Planner(模板族) 还是 Executor(在线)
    if not is_enumerable(fp):
        # 不可枚举 → 全程在线 ReAct,带熔断 + 降级兜底
        return with_degradation(page,
                  lambda p: react_online(p, goal, MAX_STEPS, MAX_TIME))

    # 可枚举 → ReAct-as-Planner:一次性把所有操作路径列清并各自冻成模板
    family = []
    for op in enumerate_operations(page, fp):     # 增/删/改/查/导出...
        steps = react_plan(page, goal=op)         # 规划,不在线执行
        family.append(freeze_template(steps))     # 沉淀,供同族页复用
    template_store.add_family(fp.category, fp.layout, family)
    return execute_family(family, page)          # 秒级回放每条路径

def is_enumerable(fp):
    total = sum(fp.roleHistogram.values())
    distinct = len({c.actionClass for c in fp.skeleton})
    return total <= OP_COUNT_THRESHOLD and distinct <= DISTINCT_ACTION_CAP
```

### 8.4 [消费者] 执行层 anchor 三级兜底定位

抗页面重构:视觉优先(以图搜图)→ 文本(OCR)→ 结构(xpath)兜底。

```python
def locate(element, page):
    if element.visual_anchor:                   # 优先:以图搜图
        loc = find_by_image(element.visual_anchor, page.screenshot)
        if loc: return loc
    if element.text_anchor:                     # 次选:OCR 文本
        loc = find_by_ocr(element.text_anchor, page.screenshot)
        if loc: return loc
    if element.struct_anchor:                   # 兜底:xpath
        return find_by_xpath(element.struct_anchor, page.dom)
    raise LocateFailed
```

### 8.5 [消费者] warm-start 增量 + 降级兜底

```python
MINIMAL_CAPTURE = [                              # 降级模板:保证每页必有产物
    {"action":"goto","url":"$URL"},
    {"action":"scroll_loop","until":"networkIdleAndStable"},  # 双停条件触发 lazy-load
    {"action":"expand_all","targets":"折叠/tab/手风琴"},
    {"action":"screenshot","mode":"fullPage"},
    {"action":"extract","fields":["title","body_md","outbound_links"]},
]

def react_incremental(seed, page):
    # 不从 0 探索:用 seed 做骨架对照,只规划页面新增/差异部分
    delta = diff(seed.fingerprint.skeleton, page.fingerprint.skeleton)
    plan  = LLM(INCR_PROMPT(seed.steps, delta, goal))     # 在已规划路径上"补/改"
    return with_degradation(page, lambda p: finalize(plan, p))

def with_degradation(page, plan_fn):
    try:
        return plan_fn(page)                     # 超步/超时抛 Runaway
    except (Runaway, ReActFailed, Timeout):
        traj = execute_template(MINIMAL_CAPTURE, page)    # 最小采集
        t2.update(page, status=DEGRADED)
        return traj                              # 不丢页,质量分档
```

### 8.6 [生产者] 配额 ≤20% 主动调度

用**预占槽**而非事后统计。接近上限即触发反向生产(主动找欠配类别的种子),超配页进 buffer 停车不丢。

```python
MAX_CAT_SHARE = 0.20
# capacity 是每类硬上限;target 是计划量(≤capacity),可按运营策略分配
# capacity[cat] = floor(MAX_CAT_SHARE * N_total)

def admit_candidate(page):
    cat = light_classify(page)                  # S2 预分类(深挖前,要够轻)
    if cat is None: return REJECTED_NOCLASS
    # 预占槽:接近上限即停收
    if quota.used[cat] / quota.capacity[cat] >= 1.0:
        pending_hold.enqueue(page, cat)         # 停车不丢,等别类腾位再回放
        trigger_reverse_production(deficit_categories())
        return DEFERRED
    # 质量过滤(8.7)
    if not is_operable_surface_present(page):   # 登录墙/canvas/404
        return REJECTED_NOOPSURFACE
    quota.used[cat] += 1
    t2.insert(page, fingerprint=compute_fingerprint(page), qflag=OK)
    return ADMITTED

def on_released_slot(cat):
    # 某类额度释放(如页面被消费后降级剔除)→ 回放该类 buffer 里的待入库页
    if pending_hold.has(cat):
        page = pending_hold.dequeue(cat)
        admit_candidate(page)                   # 重新走流程
```
### 8.7 [生产者] 页面质量过滤

```python
def is_operable_surface_present(page):
    wait page.network_idle()
    ops = page.dom.select(OPERABLE)
    if count(ops, outside=FOOTER) == 0:  return False      # 没有可操作元素
    if is_login_wall(page):             return False        # 跳登录
    if is_404(page):                    return False
    if is_canvas_only(page) and not has_text_inputs(page): return False
    if is_infinite_scroll_trap(page, timeout=15):           # 15s 仍无稳定内容
        return False
    return True
```

### 8.8 关键阈值与 Step 0 标定表

| 符号 | 含义 | 默认 | 标定方法 |
|------|------|------|---------|
| `Ts` | 高阈值,直接复用 | 0.85 | 取 Step 0 中"应同模板页"的最低 ssim 分位数 |
| `Tw` | 低阈值,低于即视为不匹配 | 0.55 | 取"明确不同模板页"的最高分位数 |
| `TOP_K` | skeleton 保留元素数 | 32 | 体感:操作面平均元素数,过大拖慢 skel_sim |
| `DEPTH_CAP` | DOM 深度截断 | 6 | 防 DOM 深度噪声 |
| `OP_COUNT_THRESHOLD` | 可枚举上限 | 40 | Step 0:工具页操作面规模上界 |
| `DISTINCT_ACTION_CAP` | action 类上限 | 8 | Step 0:distinct actionClass 分布 |
| `MAX_STEPS/MAX_TIME` | 在线 ReAct 熔断 | 15/180s | 单页预算 × 复用比的产出速率约束 |

**Step 0 操作**:跑 30 页同站页 → 统计站内步序列重复占比 与 指纹两两相似度分布 → 看能不能把"同模板页"与"不同模板页"用 `Tw<Ts` 切开。切得开 → 走轻量模板化;切不开 → fingerprint 粒度需调整或下沉到分层规划。
---

## 十、核心结论速记

1. **吞吐胜负手是"摊薄 10min"**:模板化复用 + 规划/执行解耦,把 ReAct 从 per-page 10min 的 Executor 压成 per-template 一次的 Planner。
2. **fingerprint 是匹配的键**:只描述操作面骨架不描述内容,支撑跨站复用。
3. **模板正本在消费侧**:`structure_fingerprint` 生产侧预产,`t1.default_template_id` 只是指针。
4. **多路径 ≠ ReAct**:多路径是模板族一次枚举;ReAct 只在"不可预测/不可枚举"时用。
5. **两命门并重**:模板命中率(能否跑完)+ 配额 ≤20%(是否合规),缺一不可。
6. **先量复用率再铺量**:Step 0 不做就铺 20w 是赌博。