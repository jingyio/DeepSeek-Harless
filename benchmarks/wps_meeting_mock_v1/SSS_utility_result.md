# WPS 组会 mock：SSS 效用诊断

2026-09-27。这里只评价[合成夹具](README.md)，不评价真实课题组任务质量或 MotifAgent 的一般效果。

## 实际执行

用 `run_mock.py` 分别运行 `base`、`duration_update`、`result_update`，三份 Quarto HTML 与 JSON 记录位于 `outputs/wps-meeting-mock-v1/reports/`。再运行 `tests/test_wps_meeting_mock.py`，3 项守卫测试通过。

| 场景 | 普通脚本结果 | 模型请求 | 守卫结果 |
| --- | --- | ---: | --- |
| 初始记录 | 基线 213/300、候选 237/300；生成待审简报 | 0 | 模拟已审阅表述与冻结依赖一致 |
| 仅耗时变化 | 候选总耗时 311.0 → 305.0 秒；正确率仍为 79.0% | 0 | 只沿用不受影响的正确率表述 |
| 正确数变化 | 候选 220/300，正确率 73.3% | 0 | 撤销旧表述，停在语义复核点 |

这条普通脚本基线已经在全部三例中完成数值和失效控制，模型请求数的下界是 **0**。本次没有测量人类修订时间、供应商账单或真实交付质量；`model_requests_executed: 0` 只表示该脚本未调用模型，不能解释为 SSS 节省了请求。

## SSS 的当前可执行性检查

1. 当前 `.local/online-motif-certified-library.json` 只有一个已认证工具集：`mcp__structured_research__pin_source → mcp__structured_research__inspect_records`。该清单没有 WPS 表格工具。
2. `src/mcp/structured_research_tools.py` 的批准来源扩展名是 `.json`、`.csv`、`.tsv`、`.svg`、`.txt`、`.md`、`.py`、`.pdf`；`experiment_log.xlsx` 不在其中。把它转换为 CSV 后执行现有本地 Motif，测到的也只是 CSV 读取，不是 WPS 工作流。
3. Motif 编译入口要求至少两个**不同研究决定**的见证轨迹，并以第三个不同决定留出验证。同一份表格的初始、耗时更新和正确数更新属于同一决定；`run_mock.py` 也没有产生 DSH/MCP Agent 调用轨迹。用相同 `research_decision_id` 调用现有 `require_distinct_decisions` 守卫，实际返回 `ValueError: training and held-out traces repeat one research decision`。因此不能从这三轮编译合规的 WPS Motif。

**原固定任务的结论：SSS 没有展示出相对于普通脚本的增益，且尚无可在 WPS `.xlsx` 输入上执行的认证 Motif。** 这是明确的负面开发诊断，不是“SSS 对科研任务无用”的结论。这个窄任务更适合保留为脚本／版本缓存基线。

根据用户反馈，已另加 [Agent 任务扩展](agent_task.md) 和跨模拟应用的只读 MCP。它要求结合旧主张、两篇虚构论文及数值选择下一步；普通脚本现在只负责数值片段。原生 Agent 两轮开发试跑见[试跑记录](agent_trial_result.md)：首轮读到隐藏评审包；第二轮关闭内置文件工具后仅通过 MCP 读取并直接交付可渲染报告。两轮都没有 Motif，也没有跨任务或公平的质量／费用对照。因此**不能把原固定任务的负面结果直接外推到新任务**。

对照新任务的[评审标准](agent_review.md)，旧脚本只覆盖第 1 项数值核算；它没有读取 Obsidian 目标和疑点、没有比较两篇论文的适用范围，也没有选择下一项研究行动。这是覆盖范围审计，不是盲评或模型质量成绩。模拟 MCP 的三类来源、`pin → read`、版本失效和统计调用已通过无模型测试；当前仍无法推断 SSS 相对自由 Agent 的收益。

## 若要检验 SSS 的独立价值

需要另找至少三个不同的真实研究决定，其中 WPS 实验记录与 Obsidian 主张、Zotero 证据或代码版本有实际交叉依赖；先做有授权范围和版本守卫的 WPS 只读入口，再从前两题普通 Agent 的真实轨迹挖局部算子、第三题留出。每题安排一类可安全复用的变化和一类必须打断旧主张的变化，**同题更新不算新任务**。优先挖掘“Agent 已决定核查结果后，按来源版本和参数依赖连续读取、复算、定位旧主张”的局部步骤；统计口径改变或出现反证时交回语义层。对照具备相同版本检查与缓存能力的普通脚本和自由 Harness：先盲评结论与组会材料是否合格，再比较完整模型请求、实际费用、人工修订和耗时。合成表格只继续用于字段校验和失效守卫回归。
