# v3.1：明确统计续接授权，再从真实轨迹重新学习

本实验回答：LLM 批准统计方案之后，`03 run_analysis → 04 verify_analysis → 05 build_evidence` 能否由 Motif 连续发起？三个工具原本就是确定性操作；本次只把用户允许的统计续接范围写清楚，重新收集普通 DSH 轨迹并编译，不修改算法、DSH、插件守卫或旧版证据。**当前目录是新的实验入口，实际运行实现仍为 v3。** manifest 中 `benchmark_version=3` 是真实实现版本；本轮通过 `experiment_id=research-report-agent-v31-20261010` 和输入/政策哈希区分。

已完成的公开交付见 [报告与全部 19 次运行 PDF](results/20261010/README.md)，包括综合报告、逐次工具流程图和完整成品。仓库变更范围见 [发布审计](PUBLICATION_AUDIT.md)，实验结论见 [公开记录](../../docs/experiments/research-report-agent-v31-20261010.md)。PDF 保留原件，包括未通过科学文字评审的报告；自动交付成功不等于科研解释正确。

## 三步原来做什么

| 步骤 | 真实工作 | 是否需要 LLM 作新决定 |
|---|---|---|
| `run_analysis(plan_id)` | 读取已批准方案和 CSV，按方案完成缺失值处理、Welch 两组比较/配对检验/一元 OLS；产生效应、区间、p 值及诊断 | 否；方法已由 LLM 批准 |
| `verify_analysis(analysis_id)` | 从原始 CSV 重新构造数据，数值复算并与计算记录比较；保留明确容差 | 否；发现不一致须交回 LLM |
| `build_evidence(verified_id)` | 把已复核数字、单位与诊断整理为可供模型阅读的证据目录 | 否；它不选择图表或撰写科学解释 |

“独立复算”是实现中的重新计算与一致性检查，不等于独立科研验证或数学证明；部分诊断仍复用同一统计库。数值通过也不能证明研究设计或自由论述正确。

v3 final 的材料训练明确批准续接，而 ML 配对训练明确填写 `false`。因此三个统计候选仅有一个合格训练见证，虽然第三项认证见证存在，仍不够“两训练 + 独立认证”，没有入库。上轮真实库只有绘图的 2 条边和组装到交付的 5 条边。这不是统计工具缺少能力，也不能靠手工补库修复。

## 本轮唯一变化与不变的边界

[statistics_continuation_policy.txt](statistics_continuation_policy.txt) 是公开给两组、所有训练/认证/留出题完全相同的用户指令。它明确允许：在已经批准的方案、数据和工作区内，自动执行上述三个固定步骤。LLM 仍须在 `plan` 顶层亲自写 `allow_deterministic_continuation: true` 或 `false`；`false` 合法且始终保留，不由工具、准备脚本或插件改成 `true`。

这个授权范围和工具顺序是人工设计的。编译器学习的仍只是实际成功轨迹中的输出字段到后继唯一参数的绑定；没有预写可执行的 Motif 库，也没有提前选择统计方法、图形、正文或报告布局。用户提供的大纲/页数要求依旧保留。

三个语义关口都保留：先由 LLM 审核统计方案；实际证据形成后，由 LLM 选择图表、大纲、篇幅；图件检查后，由 LLM 撰写全文。`build_evidence` 的后继授权是空，不能跨过第二个关口。自动调用仍需逐步核对当前输入哈希、workspace、真实 receipt 字节摘要、完整工具 schema、唯一 ID 绑定及显式权限。失败和不一致按原插件规则回退。

## 复现

在已有 v3 依赖的 Linux 仓库根目录执行；环境安装说明见 [v1 依赖与离线验证](../research_report_agent_v1/README.md#5-环境与离线验证)。下文 Python 使用 `.venv-sss/bin/python`，可通过 `source .venv-sss/bin/activate` 激活同一虚拟环境。密钥使用环境变量或原 runner 的安全输入方式，不写进代码、参数或输出文件。新使用者需要自行设置预算并授权实际 API 调用，历史实验的授权不自动延续。

本轮 Linux 使用 Python 3.12.15、Node 22.23.3；统计诊断入口调用 `node:module.registerHooks`，请使用已验证的 Node 22.23.3 或更新兼容版本，不能仅依据仓库通用的 Node 20+ 要求运行它。Windows Python 3.13.5 / Node 24.16.0 的离线检查另见发布审计，不等于完整云模型环境复现。

先进行零 API 检查：

```sh
.venv-sss/bin/python -m unittest discover -s benchmarks/research_report_agent_v31/tests -v
.venv-sss/bin/python benchmarks/research_report_agent_v31/diagnose_statistics_chain.py \
  --output .local/v31-offline-diagnostic-linux
node --test benchmarks/research_report_agent_v3/test_motif_plugin.mjs
```

小诊断对三种统计设计各执行 `true/false` 两个 fixture，真实调用三个统计工具，共 18 次，产生真实回执，再通过**未改动的 v3 插件**重放回执，核对命令参数和语义边界。其测试库及 schema 是内存 fixture，不输出 learned library，不进行真实 DSH/MCP 网络传输，不是训练或性能证据。正式库必须来自下面的真实普通 DSH 运行。Windows 可额外传 `--node-deps-root <已有 node_modules 的仓库>`，不安装替代插件。

新输入必须放在空目录；不覆盖 v3/v3 final：

```sh
.venv-sss/bin/python benchmarks/research_report_agent_v31/prepare_experiment.py \
  --output .local/research-report-agent-v31-20261010 \
  --seed-offset 2000000 --experiment-id research-report-agent-v31-20261010
.venv-sss/bin/python benchmarks/research_report_agent_v31/run_matrix.py \
  --matrix .local/research-report-agent-v31-20261010/training-matrix.json \
  --data-root .local/research-report-agent-v31-20261010/data \
  --experiment .local/research-report-agent-v31-20261010 \
  --budget-ledger .local/research-report-agent/global-ledger.jsonl
```

最后命令默认只预览，无 API 调用。核对后加 `--call-model`，顺序运行两个普通 baseline 训练和第三个独立 baseline 认证；默认实验 ID 已是本轮 v3.1。共用原始 100 元预算账本，旧版开发/校准、训练及失败费用继续累计。三条达到交付门槛后：

```sh
.venv-sss/bin/python benchmarks/research_report_agent_v31/compile_motifs.py \
  --train .local/research-report-agent-v31-20261010/runs/v31_train_materials_baseline \
          .local/research-report-agent-v31-20261010/runs/v31_train_ml_baseline \
  --certify .local/research-report-agent-v31-20261010/runs/v31_cert_environment_baseline \
  --output .local/research-report-agent-v31-20261010/library.json
.venv-sss/bin/python benchmarks/research_report_agent_v31/run_matrix.py \
  --matrix .local/research-report-agent-v31-20261010/evaluation-matrix.json \
  --data-root .local/research-report-agent-v31-20261010/data \
  --experiment .local/research-report-agent-v31-20261010 \
  --budget-ledger .local/research-report-agent/global-ledger.jsonl \
  --call-model
```

若某条边仍缺真实见证，保留缺失，不能从诊断 fixture 补库。新种子统一加 `2000000`，7 项实际种子为 2910017、2920029、2930031、2940007、2950001、2960003、2970011。为兼容审计，case ID 保留 `v3_*`，运行名改为 `v31_*`。四项留出题各两组各两次，16 次均纳入分母；独立任务仍是 4 项。顺序交替、第二次重复反转先后，workers 固定 1。两组使用相同输入、公开工具 schema、模型和上限，自主选图、自主写全文。

## 证据、冻结和统计口径

准备脚本冻结公共授权政策、CSV/study/task/request 哈希、矩阵及 v3/v3.1 入口代码；每个真实 run 继续由原 v3 runner 保存 v1/v2/core/config/scripts 的完整依赖快照、原始模型 HTTP/SSE、MCP 工具事件、receipt、Motif 审计、PDF 和费用估算。旧实验文件全部保留。所有 `false`、失败、回退和重试需纳入解释与成本。

`tool_calls` 称为“DSH 工具调用尝试”，另数实际成功 MCP 执行、业务拒绝及 schema 错误。Motif 产生的工具命令已经包含在工具尝试中，不能重复相加；只有回执通过核验的绕过才计入 `verified_motif_bypasses`。模型请求数指向 LLM 的上游请求，和工具调用不是同一计数。无完整 usage 的请求保留保守估额，费用不是平台账单。

实测学习覆盖、成本、16 次交付与独立科研/视觉质量结果以本轮实际证据为准，本文件不预填结果。v3.1 证明的范围是“明确共享续接授权后能否重新学到已有确定性能力”，不是新统计算法，也不是任意科研任务自动识别。
