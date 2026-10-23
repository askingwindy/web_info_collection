# WebCollect 独立质检器

依据客户原始样例、需求及明确的本地试点规则，检查候选文件、动作与图树、证据绑定、分布和四路重复候选。逐图语义审核使用单独记录导入，程序检查不能代替人工看图。

## 在仓库中运行

使用采集工程的Python环境安装质检依赖：

```sh
projects/code/.venv/bin/python -m pip install -r projects/quality-inspector/requirements.txt
projects/code/.venv/bin/python projects/quality-inspector/qc.py --help
```

质检器从仓库读取`config/`及`request/`，应保留完整目录关系。`config/customer-samples.json`绑定两份客户原始样例与需求文件的SHA；原始样例是格式依据，不表示其中所有字段都符合新生产要求。不要修改原件或把已知历史缺陷当作生产豁免。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --baseline projects/quality-inspector/config/customer-samples.json \
  --profile projects/quality-inspector/config/local-pilot-v1.json \
  --input /path/to/candidate --output verify_results/new-qc
```

检查报告必须位于输入包之外，使用新的输出目录。主要输出为`report.json`、`报告.md`、`review.html`及`review-template.json`，同时保存实际采用的规则与配置身份。

## 结果含义

- `PASS`：对应范围的实际检查和必要审核已通过。
- `FAIL`：有明确缺陷、绑定冲突或超过规则限制。
- `REVIEW_REQUIRED`：缺少审核、证据不足或仍待裁决。

启用本地profile后，命令退出码依据`local_acceptance_status`：PASS为0、FAIL为1、待审为2；执行错误为3。报告分别列出sample、batch、pilot、corpus和external作用域。总体`status`可以因客户或全集范围待核验而保持待审，不能将其误读为本地样本失败。客户实际程序及算法等价性未经执行时保持`UNKNOWN`。

本地试点配置要求至少20条、10站，单类不超过20%，视口规格不超过3种，短流程不超过2%。四路为截图SHA、完整动作序列哈希、首末帧dHash和任务SimHash；算法和阈值固定在profile。命中候选不能通过语义备注直接豁免。URI与站点编号及类目还须和实际来源对账，不能通过拆标签降低类目占比。

## 真实审核与重新检查

本机浏览器直接打开对应报告目录中的`review.html`，逐条查看原图、同步界面树、动作、步骤结果，并结合样本`annotation.json`核对任务和终态。选择真实审核来源，填写审核人/模型名和来源说明。每条五项为：

| 字段 | 核对内容 |
|---|---|
| `visual_alignment` | 图、树、控件、坐标和相邻动作是否对应 |
| `terminal_semantics` | 连续完成真实任务，无凑步或错误终态 |
| `language` | 简体中文叙述、控件原文和实际页面语言 |
| `privacy` | 实际来源及个人/账户内容是否符合需求声明 |
| `substantive_difference` | 与其他轨迹是否有实质差异 |

每项选择`PASS`、`FAIL`或`REVIEW_REQUIRED`；PASS/FAIL都须写具体样本、步骤和证据理由。不确定时保留待审。页面仅在内存中保存，刷新、关闭前导出`qc-review.json`备份。人工审核必须由实际审核人填写，不能将AI记录改名为人工。

导出模板还含`package_review`，其文档完整性及站点类目归属默认待审，需要实际阅读包内文档并填写绑定当前包的结论和依据。该对象没有页面编辑控件；按[人工核验SOP](../prd/M2-人工核验SOP.md)处理，不能盲目把默认值改为PASS。

```sh
projects/code/.venv/bin/python projects/quality-inspector/qc.py check \
  --baseline projects/quality-inspector/config/customer-samples.json \
  --profile projects/quality-inspector/config/local-pilot-v1.json \
  --input /path/to/candidate --reviews /path/to/qc-review.json \
  --output verify_results/new-qc-with-review
```

导入检查审核来源、annotation/evidence SHA及包内文件清单；样本或资料变更后旧记录不能自动沿用。报告中的已导入AI记录数不等于人工审核数。

## 核心模块

`engine.py`编排规则、作用域及审核绑定；`format_checks.py`独立解析格式；`checksums.py`核对完整文件清单；`duplicates.py`保留四路参数与候选；`profiles.py`计算本地验收；`preparation_evidence.py`审计正文准备的真实前后帧与动作；`reporting.py`生成报告和离线审核页。

正文准备审计核对初始完整截图、图/树/raw哈希、判断与实际动作、准备预算和失败记录。机械通过仍须逐图核对；失败尝试、历史兼容状态和未知边界分别保留。

`package`兼容入口调用采集工程的`webcollect.candidate`，需要同时保留采集核心。组包不执行网站采集，也不宣告验收通过。数据、测试和详细验证过程不纳入源码Git历史。
