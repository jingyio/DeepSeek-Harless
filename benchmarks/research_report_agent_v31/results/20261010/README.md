# v3.1 综合报告与全部原始 PDF（2026-10-10）

本目录保留本轮 **19 次运行的最终原始 PDF**：2 次轨迹学习、1 次独立认证、16 次正式对照；另附 3 份汇总报告。所有 PDF 逐字节复制，保留全部页面与评审发现的缺陷，没有为发布而改写结果。历史版本开发运行、排版候选、原始模型/工具日志不在此目录。

## 先看这三份报告

| 文件 | 页数 | 内容 |
| --- | ---: | --- |
| [综合实验报告](reports/comprehensive_experiment_report.pdf) | 20 | 数据、模体、逐步真实工具、成本、质量与完整结果展示 |
| [16次正式运行的真实工具流程附录](reports/actual-execution-flows.pdf) | 4 | 全部16次正式运行，含实际工具、LLM/Motif来源、重试及最终回复 |
| [四种任务首次Motif运行的完整样例合辑](reports/complete_report_examples.pdf) | 10 | 封面1页 + 四种任务第一次Motif运行原件2/3/1/3页 |

完整样例合辑只是一份固定选择的阅读入口；下表提供全部原件，包含第二轮技术报告的完整 4 页，未只截取前两页。

## 如何理解数据、流程和成本

- 数据由实验脚本合成；DeepSeek Flash、DSH、stdio MCP 连接、统计计算、图形生成与 PDF 排版均实际执行。
- 工具与授权边界由人工设计；10 条可执行续接边来自两条正常 DSH 轨迹及一条独立认证，不是手工填写的学习结果。03–05 统计、复核和证据整理已连续执行，8 次 Motif 正式运行共验证这段绕过 24 次 LLM 请求。
- 统计方案、根据结果选择图表/结构、正文写作保留 LLM；确定性工具并没有被省略。两组成功执行工具均为 112 次。
- 科研质量为独立 AI 非盲评，不是人工领域专家认证；自动交付/排版通过不等于科研内容合格。三份重大缺陷原件仍在下表。

| 正式对照（各8次） | 普通 DSH | DSH + Motif |
| --- | ---: | ---: |
| 真实 LLM 请求 | 143 | 62 |
| 工具调用尝试（含失败） | 135 | 134 |
| 成功工具执行 | 112 | 112 |
| 工具失败 | 23 | 22 |
| 已验证 Motif 绕过 | 0 | 80 |
| 峰时模型费估算（元） | 0.72016560 | 0.61217400 |
| 自动 PDF 交付 | 8/8 | 8/8 |
| 科研评审合格 | 7/8 | 6/8 |

请求减少 **56.64%**，正式运行模型费估算减少 **15.00%**；但合格率不同，不能据此声称相同科研质量下已降本。准备的 3 次运行额外为 **50 次请求、0.23453344 元**，其作用是收集轨迹与认证，不是模型参数训练。本轮共 255 次请求、估算 1.56687304 元；连同历史开发累计 1419 次、估算 7.42098712 元。费用是代理估计而非平台账单，服务器、开发、人工作业和独立评审成本未计入。

## 全部正式运行 PDF

两次重复使用同一个任务/输入；独立正式任务为 4 个，不应把 16 次运行当成 16 个独立科研问题。`baseline` = 普通 DSH，`execute` = DSH + Motif。合格仍可能含需要修订的次要问题，详细项见清单。

| 任务 | 次数 | 组别与原件 | 页数 | 科研评审 |
| --- | ---: | --- | ---: | --- |
| 自主组织的生物学报告 | 1 | [v31_eval_auto_r1_baseline](runs/evaluation/v31_eval_auto_r1_baseline.pdf) | 3 | 不合格（原件保留） |
| 自主组织的生物学报告 | 1 | [v31_eval_auto_r1_execute](runs/evaluation/v31_eval_auto_r1_execute.pdf) | 2 | 合格 |
| 自主组织的生物学报告 | 2 | [v31_eval_auto_r2_baseline](runs/evaluation/v31_eval_auto_r2_baseline.pdf) | 2 | 合格 |
| 自主组织的生物学报告 | 2 | [v31_eval_auto_r2_execute](runs/evaluation/v31_eval_auto_r2_execute.pdf) | 3 | 合格 |
| 指定大纲的配对教学报告 | 1 | [v31_eval_outline_r1_baseline](runs/evaluation/v31_eval_outline_r1_baseline.pdf) | 3 | 合格 |
| 指定大纲的配对教学报告 | 1 | [v31_eval_outline_r1_execute](runs/evaluation/v31_eval_outline_r1_execute.pdf) | 3 | 合格 |
| 指定大纲的配对教学报告 | 2 | [v31_eval_outline_r2_baseline](runs/evaluation/v31_eval_outline_r2_baseline.pdf) | 3 | 合格 |
| 指定大纲的配对教学报告 | 2 | [v31_eval_outline_r2_execute](runs/evaluation/v31_eval_outline_r2_execute.pdf) | 3 | 合格 |
| 1页能耗简报 | 1 | [v31_eval_brief_r1_baseline](runs/evaluation/v31_eval_brief_r1_baseline.pdf) | 1 | 合格 |
| 1页能耗简报 | 1 | [v31_eval_brief_r1_execute](runs/evaluation/v31_eval_brief_r1_execute.pdf) | 1 | 合格 |
| 1页能耗简报 | 2 | [v31_eval_brief_r2_baseline](runs/evaluation/v31_eval_brief_r2_baseline.pdf) | 1 | 合格 |
| 1页能耗简报 | 2 | [v31_eval_brief_r2_execute](runs/evaluation/v31_eval_brief_r2_execute.pdf) | 1 | 合格 |
| 环境研究技术报告 | 1 | [v31_eval_technical_r1_baseline](runs/evaluation/v31_eval_technical_r1_baseline.pdf) | 3 | 合格 |
| 环境研究技术报告 | 1 | [v31_eval_technical_r1_execute](runs/evaluation/v31_eval_technical_r1_execute.pdf) | 3 | 不合格（原件保留） |
| 环境研究技术报告 | 2 | [v31_eval_technical_r2_baseline](runs/evaluation/v31_eval_technical_r2_baseline.pdf) | 4 | 合格 |
| 环境研究技术报告 | 2 | [v31_eval_technical_r2_execute](runs/evaluation/v31_eval_technical_r2_execute.pdf) | 4 | 不合格（原件保留） |

三份重大问题分别是：自动生物学报告 baseline r1 无依据比较检出能力与实际重要性；技术报告 execute r1 把不同量纲的斜率区间与残差标准差比较并据此排序后续研究；技术报告 execute r2 把未计算的精度收益判断写成直接受结果支持。详见 `artifact-manifest.json` 的逐份检查与问题。

## 准备阶段 PDF（不计入正式16次分母）

| 用途 | 原件 | 页数 | 科研评审 |
| --- | --- | ---: | --- |
| 材料学训练 | [v31_train_materials_baseline](runs/preparation/v31_train_materials_baseline.pdf) | 2 | 合格，保留次要问题 |
| 机器学习配对训练 | [v31_train_ml_baseline](runs/preparation/v31_train_ml_baseline.pdf) | 3 | 合格，保留次要问题 |
| 环境学独立认证 | [v31_cert_environment_baseline](runs/preparation/v31_cert_environment_baseline.pdf) | 2 | 合格，保留次要问题 |

## 校验与复现

[artifact-manifest.json](artifact-manifest.json) 记录每个文件的相对路径、SHA-256、字节数、页数、原始 run ID、评审状态及未修复问题。[metrics.json](metrics.json) 提供脱敏后的组间费用、usage、请求和工具计数。19 份原件共 47 页，其中正式 40 页、准备 7 页；每份均核对原件字节摘要、评审绑定摘要、页数与逐页文字可提取性。

复现入口和授权边界见 [benchmark README](../../README.md)。复现将重新调用模型，输出会随机变化，需自备凭证与预算；本目录 PDF 是这次已完成运行的固定记录。原始模型内容、工具日志与私有环境快照留在受保护实验区，不随 Git 发布。
