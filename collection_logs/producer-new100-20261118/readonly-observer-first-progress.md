# 生产者首次进展只读观察

观察日期：2026-11-18。观察者仅检查进程、已有运行文件及正式数据库的只读连接；没有启动、停止、重试、修改源码或数据库。此文件是本轮唯一新增观察产物。

## 启动与进展

- `active-run.json` 为 RUNNING，controller PID **76663**，worker PID **76664**；两进程存活，worker 的 PPID 为76663。检查时运行约3分钟。
- 命令为正常 `site_planner.candidate_discovery produce-entries`，新批 `producer-new100-20261118-dpm-01`，`new-sites + site-expansion`，目标100、单worker、两故宫主机白名单、serial。没有消费者/QC进程由本轮启动的声明。
- 新站 Table1：`app-54680a484ea549505a7bd126`，host=`dpm.org.cn`，已 `confirmed`，`mining_state=running`。
- 首个首页真实 GET：visit `406355e095794e168d90f3e502c3189d`，`https://www.dpm.org.cn/`，HTTP200，succeeded，原GET job `891fee0567ef72712e494e42b50eba684d4aa70844d0c01515d12814e6043af7`。
- 首个站点分类模型请求 `7538de9a33a6472a90cd3b887e451bf3` 已 succeeded；usage为输入2966、输出74 token、cached输入0，返回模型 `glm-5.3-flash`。首次模型查询只见此1次新请求，没有新增模型UNKNOWN。
- `1794985371.435477` 时刻查询本轮 candidate_batch_rows 尚无NEW；pipeline仍在批量观察页面，不能把GET或站点分类成功计作100页目标完成。
- 针对已发现失败的原始诊断读取时，共看到16笔本轮取页：13 succeeded、1 failed、1 unknown、1在途。此为随后只读快照，与上一个模型/NEW查询不是原子联合快照。

## 已即时告知主代理的问题

1. **首页导航别名读取响应体失败。** URL `https://www.dpm.org.cn/Home.html`，visit `65da7e2b922d43d4bf6b4e78da6ae165`，job `f3a75813a880546d8749c943adb080bbe240c1dec16d01c885a3744208c8ca06`。原取页记录为failed，`error_type=Error`，原消息：

   ```text
   Response.body: Protocol error (Network.getResponseBody): No resource with given identifier found
   Response body is not available for a response that was navigated away from. Read response.body() before triggering any navigation.
   ```

   原job为review_required。只确认了原错误，不据此猜测跳转原因或替换请求。

2. **书画目录导航超时，页面结果UNKNOWN。** URL `https://www.dpm.org.cn/calligraphy_paint/index.html`，visit `a858e920e5a44a59965b9e3269c2e5fd`，job `e738a39c4381def157f8f6db441d06ab7131dfd9e2607d96e2e0a15196ddff16`。原取页记录为unknown，`error_type=OutcomeUnknown`，消息 `Original image-screen navigation unresolved: TimeoutError`；原job为review_required。这是页面访问UNKNOWN，不是新增模型UNKNOWN。

两项原件均保留，观察者没有重试或改判。控制器与worker在首次检查中仍存活，没有提前退出证据。主代理已收到问题及原visit/job ID，可纳入Git跟踪问题log；100页目标尚未达到，本报告只证明已发生首次真实请求与取页进展。
