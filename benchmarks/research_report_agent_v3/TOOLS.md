# v3 工具与结果字段说明

14 个工具由真实 stdio MCP 服务 `research_report` 提供。DSH 中的全名为 `mcp__research_report__<工具名>`，下表省略该前缀。两组 Agent 看到完全相同的工具和 schema；本说明只描述能力，实际 Motif 库必须从普通 DSH 的成功轨迹编译，不能把下表直接当作已学到的流程。

“参数”是调用时送给工具的数据；“结果字段”是工具执行后返回对象中的一个名字。例如 `approve_analysis` 返回 `plan_id`，下一步把这个字段的值填到 `run_analysis` 的参数 `plan_id`。ID 指向本次工作区内有内容哈希的记录，不能随意用字符串替代或拿别题的 ID 混用。

日志 `tool_calls` 表示 DSH 工具调用尝试，包含被拒绝的请求，不能等同于成功执行数。final 中 269 次尝试对应 224 次成功 MCP 工具执行和 45 次失败（40 业务拒绝、5 schema 错误）。两组各成功执行 112 次；56 条 Motif 命令是这些尝试中的一部分，不是额外再执行 56 次。原始坏 JSON 1 次有服务端 Pydantic 拒绝记录，不能称作未抵达 MCP。

## 工具清单与三个停点

| 工具 | 主要参数 | 新结果字段 | 执行内容与边界 |
|---|---|---|---|
| `inspect_study` | 无 | 输入摘要 | 读取当前范围真实 CSV、研究背景、用户请求；先决定统计设计 |
| `approve_analysis` | `study_id, plan` | `plan_id` | **LLM 决策一**：统计方案及设计依据；禁止夹带图或报告方案 |
| `run_analysis` | `plan_id` | `analysis_id` | 真正计算所批准的统计量 |
| `verify_analysis` | `analysis_id` | `verified_id` | 从 CSV 独立复算统计量和辅助诊断 |
| `build_evidence` | `verified_id` | `evidence_id` | 返回真实结果、诊断、可用图型和数值目录；**不授权后继，必须回到 LLM** |
| `approve_presentation` | `evidence_id, presentation` | `presentation_id` | **LLM 决策二**：看到结果后选择图/表/大纲/篇幅并说明理由 |
| `render_figures` | `presentation_id` | `figure_bundle_id` | 按该方案实际输出 PNG/SVG/PDF 图 |
| `verify_figures` | `figure_bundle_id` | `packet_id` | 检查图文件和数值，返回真实图说明与正文合同；**不授权后继，必须回到 LLM** |
| `submit_report_text` | `packet_id, report_text` | `text_id` | **LLM 决策三**：提交每节完整正文和所需的研究选择比较 |
| `compose_report` | `text_id` | `draft_id` | 组装批准正文、图和选定数值表，不另写标准段落 |
| `layout_report` | `draft_id` | `layout_id` | 真实 PDF 渲染、测量与有界排版修复；同稿同版本幂等复用 |
| `audit_layout` | `layout_id` | `report_id` | 重开 PDF 检查内容、版面和哈希 |
| `verify_report` | `report_id` | `verification_id` | 核验文稿来自批准正文、来源未变、产物通过检查 |
| `deliver_report` | `verification_id` | `delivery_id` | 返回已验证 PDF 路径、页数、摘要和评审限制；运行完成条件 |

三段最多提供 3、2、5 条确定性转移候选。这个上限来自人工划分的工具粒度，不是实验结果；实际入库数量及实际跳过请求数必须读取 library 和 audit。每条自动工具仍单独由 DSH 调用 MCP，不是在一个隐藏工具里运行整条链。

final 实际训练/认证只录入 7 条边：绘图段 2 条、正文批准后组装至交付 5 条。统计段缺少第二项训练的合格见证，没有录入，正式运行时仍由 LLM 逐步发起。本表中“确定性工具”的性质不意味着它自动成为 Motif。

## 决策一：只批准统计方法

`plan` 必须只有 `analysis` 和 `allow_deterministic_continuation`。支持的 `analysis.design` 为：

| 值 | 方法 | 关键字段 |
|---|---|---|
| `independent_groups` | 双侧 Welch 两独立组比较 | `outcome_column, group_column, reference_group, comparison_group` |
| `paired` | 按实验单元对齐的双侧配对 t 检验 | 上述分组字段及 `subject_column` |
| `regression` | 带截距的一元 OLS 回归 | `outcome_column, predictor_column` |

公共字段还有 `missing_policy:"complete_case"`、`confidence:0.95`、`hypothesis` 和 `design_evidence:{source,quote}`。`source` 只能为 `user_request` 或 `study_description`，`quote` 必须是其中实际存在的设计说明；从列名猜测独立性不能通过此检查。配对缺失处理删除不完整配对，报告需区分原始行与有效配对数。方法范围不包含混合模型、时间序列、多重比较或其他任意科研分析。

`allow_deterministic_continuation` 必须是显式 JSON 布尔值。批准 `true` 后，权限随本段记录逐步传递，至 `build_evidence` 归零。它没有授权模型尚未做出的图表或文字决定。

## 决策二：根据实际统计选展示方式

`presentation` 的结构为：

```json
{
  "figures": [
    {"kind": "scatter_fit", "reason": "用本次散点和拟合展示已观察到的关系及观测离散"}
  ],
  "tables": [
    {"kind": "key_metrics", "metrics": ["estimate", "ci_low", "ci_high", "p_value", "n"],
     "reason": "便于核对本次斜率、不确定性和有效观测数"}
  ],
  "report": {
    "title": "研究结果报告",
    "outline": [
      {"heading": "方法", "roles": ["methods"]},
      {"heading": "结果与诊断", "roles": ["results", "diagnostics"]},
      {"heading": "局限与下一步", "roles": ["limitations", "next_steps"]}
    ],
    "style": "technical", "page_mode": "auto"
  },
  "reason": "结合本次实际效应、诊断与用户用途安排图表和正文",
  "allow_deterministic_continuation": true
}
```

这是字段示例，不是预填给主实验模型的答案；图型与理由需由模型根据本题实际结果生成。`figures` 选 1–3 种互不重复且兼容的图，必须有原始观测/分布图。可省略英文图标题，工具使用准确的默认标题；自行提供时必须为 ASCII，且不能声称图中存在实际没有画出的元素。

| 分析 | 可用图型 | 至少包含 |
|---|---|---|
| 独立两组 | `distribution_ci, group_ecdf, effect_interval` | `distribution_ci` 或 `group_ecdf` |
| 配对 | `paired_change, change_distribution, effect_interval` | `paired_change` 或 `change_distribution` |
| 回归 | `scatter_fit, residuals, effect_interval` | `scatter_fit` |

`tables` 必须明确为 `[]` 或一个 `key_metrics` 表，选择 1–12 个实际存在的数值字段。大纲角色可用 `summary, methods, results, diagnostics, limitations, next_steps, provenance`；每种角色最多出现一次，必须覆盖方法、结果、诊断、局限，可在一个标题下合并。用户提供的标题和顺序必须原样保留。

`style` 为 `brief|technical|paper`；`page_mode` 为 `auto|max|exact`。`max/exact` 要求 `pages` 为 1–6；`auto` 不硬定页数。当前单页配置最多一图、四个标题；冲突应返回修订或澄清，不能暗删用户要求。`true` 仅授权绘图及图检查，`verify_figures` 再次清空权限。

## 决策三：自由正文与数值标记

`report_text` 通过强 `ReportText` schema 向模型公开结构，禁止额外字段且权限为无默认值的严格布尔类型；可选字段不自动补进原始批准实参。它包含按批准标题顺序排列的 `sections`，每节有 `heading`、`paragraphs`，必须有 `figure_indices`（本节无图时用 `[]`）。图索引从 0 开始，每幅批准图恰好放一次。每节 1–12 个非空段落，每字段最多 2000 字符，总正文最多 18000 字符；单页另做真实排版容量预检。

例如模型可以自己写：

> 本次采用 {{method_name}}，有效样本为 {{n}} 个{{sample_unit}}。估计的效应为 {{estimate}} {{effect_unit}}，{{confidence_pct}}% 置信区间为 [{{ci_low}}, {{ci_high}}]；双侧 p 为 {{p_value}}。本分析排除 {{excluded_rows}} 行缺失记录，缺失机制未知，因此结论仅适用于当前完整记录。

这里只是解释标记用法，不是工具自动生成的标准正文。`{{estimate}}` 像“请把已复算效应填到这里”的空位：模型决定句子和论述，工具只绑定数值。全篇必须使用 `estimate, ci_low, ci_high, p_value, n, excluded_rows`，其他标记来自当前证据目录。置信度用 `{{confidence_pct}}%`；解释变量每原始单位可用 `{{unit_increment}}`；单位可用 `{{effect_unit}}`。不能夹带手写科学数字、未知标记或计算表达式。指向实际存在图件的图号（如 `图1`、`Figure 1`）和合法连续列表编号属于排版引用，按严格规则豁免并记录在 `formatting_references`，不会把正文中的任意数字放行。符号检查能发现数值未绑定，但不能证明自然语言对数字的解释正确。

需要比较后续研究选择时，模型另写 `research_options:[{name,rationale,tradeoff}]` 和 `comparison_summary`。这些文字在标记绑定后机械加入已批准的 `next_steps` 或 `limitations` 节，原文和插入差异都保存；工具不替模型编造研究建议。标题、图注、表头、来源标识属于布局/证据标签，与模型自由正文分别记录。

`report_text.allow_deterministic_continuation=true` 授权后续组装、排版、核验、交付。字段错误、硬数字、遗漏核心证据、缺少合成数据声明、缺少非因果边界或单页容纳不下，会返回 `ok:false` 和明确错误位置。应该修订同一 `packet_id` 的正文，不重做有效统计。关键词检查仅是约束检查，不是科学正确性证明。

## Receipt、权限与可追踪记录

成功结果包含本段 ID、`source_version` 和 `_provenance`。其核心字段如下：

| 字段 | 含义 |
|---|---|
| `workspace_id` | 绑定当前运行工作区，不能跨 run 混用 |
| `data_sha256` | 真实 CSV 字节摘要 |
| `study_sha256` / `source_version` | 绑定 CSV、研究说明、任务文本的共同版本 |
| `record_path` / `record_sha256` | 当前范围内真实 JSON 记录及其字节摘要 |
| `authorized_tools` | 这张记录允许插件继续调用的工具；空列表即不授权 |

记录的 ID 由内容寻址产生，工具读取记录时核对来源、工作区和内容。三个语义记录保存 `payload.semantic_approval={tool,arguments}` 的原始完整输入；正文记录还保存 `submitted_report_text`、`rendered_sections`、`bindings` 、`transformations` 和 `formatting_references`。它们让评审者从真实模型 tool call 一直追到最终文稿，而不是只看到一份模板报告。

学习器只接受模型正常运行中相邻成功调用的精确唯一 ID 传递，不能从这个表或工具说明自行构造 library。运行时通过完整工具 schema、来源和权限守卫才能尝试省掉一次模型请求。`ok:false`、`passed:false`、`quality_passed:false` 或不合格的 receipt 都不能计入“已验证跳过”。

## 完成与质量含义

`deliver_report` 必须基于仍有效、通过验证的 PDF。完成结果含 `delivered:true`、`quality_passed:true`，同时仍保留 `scientific_prose_verified:false`。数值、结构和版面自动核验并不覆盖“区间被解释成什么”“相关是否被写成因果”“建议是否有量纲问题”“图标题是否误导”等全部科学问题。

本轮应另外审阅每份正文和实际图/PDF页面，将重大科研问题、格式问题、修订和失败纳入质量与成本结果；通过工具检查不能直接宣传为论文级正确性。工具本身不调用 LLM，也不请求模型替它自动改写报告。
