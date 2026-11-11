# 生产者执行 Prompt：Muxtly / Wiki 各100页

以下整段交给执行Agent。范围已由用户确认：每站100页，共200页；每站10个生产者进程，共20进程。此处“页”指生产者真实判定并发布到Table2的有效、去重网页，不是搜索结果数、模型调用次数、消费者样本或QC通过数。

---

你在 `/Users/hemiao/projects/2610/WebCollect` 工作。请直接执行本次已授权的新生产者采集，不停留在方案：

- Muxtly：100个净新增有效中文网页。
- 中文Wiki：100个净新增有效网页。
- 两站各10个独立操作系统进程，同时运行共20个生产者进程；共用同一工程候选池和生产者请求账。
- 本次只启动生产者。消费者、独立AI QC、人工审核、导出发布不属于本次任务。
- 不重复已通过的无关测试、不新增版本、不边实采边改源码。若确有代码断点，先保存失败并停止受影响运行，再集中修复与最小复验，不用新账覆盖失败。

先读 `AGENTS.md`、`database/README.md`、`docs/策略2走查修复与数据库持久化-20261111.md` 以及当前生产者入口。用户已确认旧 `results/` 工程被删除；本轮明确创建新工程，不能声称恢复旧库、旧候选、旧费用或旧UNKNOWN。

### 1. 新工程与配置

采用工程ID `producer-muxtly-wiki-200-20261111-r01`。持久根：

```text
/Users/hemiao/projects/2610/WebCollect/database/sqllite/producer-muxtly-wiki-200-20261111-r01/
```

通过当前 `webcollect.candidate_project init` 初始化一次。默认持久根正是上述目录，五库、配置、scope、manifest、生产者来源证据必须保留在这里；运行报告放 `results/producer-muxtly-wiki-200-20261111-r01/`。

若根目录已存在，先查scope和原账，按同一工程续接，不能覆盖重建或另换工程逃避已有请求。若尚未初始化，配置模板先放 `database/launch-inputs/producer-muxtly-wiki-200-20261111-r01/`，不要预先创建init目标根目录。

运行统一使用：

```sh
PYTHONPATH=projects/code:projects/site-planner:projects/quality-inspector \
  projects/code/.venv/bin/python -B -u -m <当前模块>
```

使用真实GLM配置与现有凭据加载器；延续已确认的 `glm-5.3-flash` 配置并按当前校验器填写视觉与token字段，生产者的模型档位使用当前既定配置。配置缺失时依据当前支持字段建立新工程配置，不能拿example中的null占位或synthetic配置开始真实采集。已有token-only计量可以直接使用，不伪造价格或缺失usage。保证共享生产者调度允许20个进程工作，租约与请求超时使用当前已有机制。

密钥由程序从既有 `request/token.yaml` 加载，新模型会话按现有轮换机制选取，原会话及未决请求保持原绑定；不要人工读取、复制或输出任何密钥值。所有进程共用scope中的 `producer_db`、`pool`、`registry`、`history_set` 和 `site-facts.sqlite3`，不得每worker新建一套账。

### 2. 站点登记、真实取源与并发分配

使用当前 `site_planner.candidate_discovery produce-entries` 正常入口。新工程先按生产者正常流程建立Muxtly和中文Wiki的Table1身份，再进行站内expand。起始只接受真实第一方来源，例如Muxtly中文主页及中文Wiki页面；目录、列表和词条链接须实际获取后筛选，不凭语言模型猜URL或把同一网页改参数凑数。

Muxtly限制在实际确认的 `www.muxtly.com` / `muxtly.com` 中文功能页面，并保证这两个主机别名归属同一站点；Wiki限制在 `zh.wikipedia.org` 的真实百科正文/可延伸阅读页面。登录入口直接排除，不登录；公共人物百科可用，私人敏感内容排除。来源页面的资格、403/404、分类和用途按现有生产者规则处理，不能手工预填PASS。

为每站准备10份可追溯的第一方种子或互不重叠的任务范围，再分派10个worker。任务分配复用现有共享池短事务、唯一键、来源缓存及同请求并发控制；不要复制完全相同的一份冻结请求让10个进程重复派发。每worker使用唯一 `batch-key`、日志文件和进程标识，数据库及工程绑定保持共享。

每个生产者批次显式冻结 `--application-new-target 100`，按本工程该应用累计DISTINCT NEW计数，并沿用发布事务的最后容量检查。局部 `--target` 不能替代全站共享100页目标。使用 `--allowed-host`、`--site-expansion`、`--prefer-simplified-chinese` 和当前支持的选链参数；先用 `--help` 核对实际参数，不使用已删除的 `--model-protocol`、旧控制台脚本或历史协议选择项。

生产者原始来源、模型回包和HTTP证据使用默认的持久 `producer-evidence/`，不要将 `--output` 指向可清理的results/verify_results。DEBUG输入输出开关若该入口没有提供，不得伪造参数；保留原请求账、原响应引用及各worker的stdout/stderr即可。

### 3. 运行、停止与账本

完成配置、接线和种子冻结后，一次启动每站10进程，由当前会话持续跟踪到目标或明确无法继续，不创建定时任务，不运行无限自动补进程的生产服务。

每站达到100条净新增有效页面后，停止该站继续派发并让已发出的请求按原账收口；另一站继续至自己的100条。不能因为一站超额而抵扣另一站缺额。成功计数只认 `data_candidates`、`candidate_batch_rows.result=NEW` 及有效来源/发布收据；并发重复、登录/语言/内容拒收、UNKNOWN、已有页不计新增。

worker遇到未处理失败保留完整现场后退出，不自动重启失败进程重发请求；其他worker继续其独立任务。原UNKNOWN/未决请求不删除、不换job ID重发、不把缺失usage写0。只有已明确完成的批次才能使用新batch-key继续新的业务任务。若来源耗尽、账户不可用或其余进程不能完成目标，如实报告缺额和阻断，不伪造200条，也不扩大站点范围。

运行中只做只读分析，不修改源码。收到用户停止立即停止新派发，保留正在结算的事实和不确定状态。

### 4. 完成报告

写 `results/producer-muxtly-wiki-200-20261111-r01/report.md` 和结构化 `summary.json`，附最终scope绝对路径、20个worker的PID/批次/退出状态、源码摘要、起止时间及日志路径。

逐站报告：尝试网页数、成功观察数、内容资格通过数、Table2实际净新增数、重复数、排除原因、失败/UNKNOWN、模型请求数、实测tokens、耗时及距离100页的缺额；总计以200为分母。抽查候选引用能从SQLite追溯到持久来源文件。最后确认所有本轮worker已退出。

消费者采集、待审样本、独立AI QC、人工审核、发布分别写NOT_RUN；本轮生产者有效页面不是已交付轨迹。不要把测试或生产者模型判定称为人工审核或客户验收。

本次新工程创建及上述200页生产者真实采集已获授权，按范围直接执行。

