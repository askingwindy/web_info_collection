# 三站策略3采集：run-03 收口

核账时间：2026-11-19T21:35:56+08:00；批次状态 `STOPPED_INCOMPLETE`；原生报告完整性 `FAILED`。

| 站点 | 固定页 | 已领 | 正式尝试 | 正式保存待审 |
|---|---:|---:|---:|---:|
| zh.wikipedia.org | 50 | 39 | 34 | 1 |
| muxtly.com | 50 | 38 | 37 | 2 |
| dpm.org.cn | 50 | 40 | 39 | 0 |

同时运行峰值 20；共领取 117/150，未领 33，正式保存待审 3。
消费者请求状态：`{'invalid_response': 41, 'succeeded': 898, 'failed': 4, 'unknown': 3}`；已证 HTTP 939，未证 3。已知输入/输出 token：2863233/186300，缺 usage 7 笔，费用 UNKNOWN。
调度问题记录 231 条，分类 `{'business': 42, 'transient': 168, 'page_program': 15, 'interrupted': 6}`。原生报告与独立账表都保留；缺原件或缺归因不作为通过。
历史保护字段有差异的行数：`{'pool': 0, 'registry': 0, 'consumer_db': 0, 'producer_db': 0}`；原未决消费者/生产者作业上新增请求数：0/0。

本批未启动自动导出、QC 或人审；数据集未发布，客户验收 UNKNOWN。

本段新增领取 57，正式尝试 53，正式保存待审 3。本段消费者用量和独立多图验证用量在 JSON 中分列。
