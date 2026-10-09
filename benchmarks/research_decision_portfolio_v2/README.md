# 科研决定任务集 v2：新增三类九题

v2 是独立冻结的**合成开发任务**；不修改 v1 已付费实验的任务和来源。它检验从 v1 正常 Agent 轨迹编译的局部 Motif 能否迁移到不同科研决定。所有邮件、日历、论文、表格、Quarto 和代码对象均为模拟，只通过当前题的只读 MCP 返回；`review.json` 不向 Agent 暴露。

| 新类型 | 三项独立决定 | 起点与关键语义问题 |
| --- | --- | --- |
| 交付物来源链与归档 | `a_model_rsi_figure`、`a_mutation_supplement`、`a_imaging_caption` | 从 Quarto 图卡／附录追到表格、脚本、批注和旧主张；图题能否发布须重新判断 |
| 复现结项条件 | `p_seed_stability`、`p_dataset_shift`、`p_control_registration` | 从运行清单或预登记清单追到数据与方法；种子不足、过滤规则变化或缺负对照应中断结项 |
| 证据缺口下选择下一实验 | `e_state_vs_retrieval`、`e_mutation_transfer`、`e_assay_initial_attempt` | 从 Obsidian 假设追到方法、试点与资源窗口；需要模型选能区分假设的最小实验 |

每题的事件 ID、任务文本、来源对象和隐藏评审标准固定在 `cases/<id>/`，哈希在 `fixtures.lock.json`。任务之间有相同的“事件返回对象 → 固定版本 → 读取已授权关联对象”等参数链，但科研判断、证据缺口和需要打断的旧结论不同。这些相似边只是 Motif 迁移的候选，不能把整题写成固定工作流。

运行前先验证：

```sh
npm test
npm run smoke
npm run scenario -- --scenario scenarios/portfolio-v2/scenario.json --case a_model_rsi_figure
```

MCP 仍提供八个通用只读工具；DSH 配置由 `scenarios/portfolio-v2/scenario.json` 生成。普通 Harness 和 Motif 应使用相同工具集合、提示和 Flash 非思考模式。每题先核交付质量，再比较真实请求、缓存计价费用、端到端时间和人工修订；这些合成题的成绩不能充当真实课题组收益。临时编写的穷尽式收集脚本不列为主对照，因为开发与维护成本没有计入。
