# 新资料题：Agent Workflow Memory 的工作流诱导与使用

> 2026-09-24，在本题任何模型调用前固定。来源是此前未用于本项目研究流程开发的 [Agent Workflow Memory](https://arxiv.org/abs/2409.07429)（Wang 等，2024），本地 PDF SHA-256 为 `ddc6f6fedec48c88ae743b43a464f7eb4aecaab05acd18c29cfb657ab445ebe4`，存于被忽略的 `.local/benchmarks/awm/reference/AWM.pdf`。为制定人工判分已读 PDF pp.3–4，因此这是**新来源开发验证**，不是严格盲评。

只据该 PDF 回答：**AWM 如何把任务轨迹抽象成可复用的工作流？离线与在线版本分别何时诱导、更新、使用记忆，在线轨迹有什么准入门槛？** 逐项给 PDF 物理页码。七项原子标准见[JSON 清单](AWM工作流记忆必答点.json)，人工以 pp.3–4 为主核对，特别注意在线版只有二元成功判别为 1 才把轨迹诱导入记忆。

固定两组：

- 普通检索脚本，人工检索词 `experience,workflow description,workflow trajectory,LM-based Workflow Induction,product-name,Offline Scenario,Online Scenario,successfully solves,agent memory`，一次综合，原有引文验证。
- 多步结构流程，使用同一份 PDF 和七项清单；最多一次规划、一次选页、一次综合。结论关联点 ID 和可定位引文；模型将是否影响必答项的“不确定”分开标记，结构守卫核查缺项。

两组均用 `deepseek-flash`、推理关闭、无模型工具调用，预览后各运行一次，不因结果调词或追加付费重试。模型输入格式、检索策略和单次输出限额不同，本题只能作诊断比较。质量以人工逐项核对为准；完整任务费用包含失败调用与人工准备，不能把程序状态单独当作合格答案。
