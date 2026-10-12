# 科研报告 Agent v2：自然请求、真实工具、可复用执行

本 benchmark 接受一段自然语言请求和 CSV，研究说明与报告大纲均可选。它使用仓库已有的 DeepSeek Harness 启动边界和真实 MCP 服务；模型依据用户请求确定整体方案，工具校验通过并记录范围授权，确定的工作区步骤才有机会由经过轨迹见证的 Motif 续接。`approve_workflow` 是模型提交方案的工具调用，不是要求用户逐次人工审批的界面。未知的研究设计、单位、独立性或配对关系不由文件名或 case ID 推断；信息不足时应停下并说明需要什么背景。

所有新增代码位于本目录。不修改 v1、Motif 核心或上游 DSH。已有 v1 的预算代理与日志工具以显式 import 复用，未另外实现 Agent 循环。当前仍是 benchmark 局部扩展，不是适用于任意工具的通用插件产品。

当前完成能力限定为三种统计设计：Welch 独立两组比较、按实验单元匹配的配对 t 检验、带截距的一元线性回归；图型为这些设计适用的有限集合。报告大纲标题可以保留，但内容必须能映射到摘要、方法、结果、诊断、局限、后续工作、来源这七类角色。标准模式使用明确设计的科学规则和已验证数值生成有限范围的段落；它不能替代任意领域的自由学术写作。需要基于结果的新解释或研究判断时，模型须选择 custom 模式，后续文字单独标为模型解释。

## 用户数据入口

在仓库根目录执行，Python 环境需包含仓库与 v1 科研统计/绘图/PDF 依赖。

```sh
python benchmarks/research_report_agent_v2/runner.py \
  --data /path/to/measurements.csv \
  --request-file /path/to/request.txt \
  --study-json /path/to/study.json \
  --outline-file /path/to/outline.txt \
  --out .local/research-report-agent-v2/runs/my-study \
  --budget-ledger .local/research-report-agent/global-ledger.jsonl
```

`--study-json` 和 `--outline-file` 可以省略。文件必须是 UTF-8。研究说明可以提供字段含义、单位、实验单元、是否配对、研究设计描述和数据是否合成；缺失说明不等于可以假定随机化或因果。大纲作为用户材料原样保留，不能执行其中的代码。报告篇幅和图型由模型在用户约束内选择。

默认只预览。用户已授权本轮真实 DeepSeek Flash 实验的总预算上限为人民币 100 元；同一账本累计 v1/v2、训练、认证、试跑、失败与重试。真实调用时在父进程环境配置 `DEEPSEEK_API_KEY`，上述命令加 `--call-model`。密钥不写入研究数据、模型日志或仓库。统计开销是按 token 计算的估费，不能当作平台账单。

每个运行目录只可执行一次，预览后可以在同一目录执行；已存在结果时必须换新目录。输入被复制到运行内的 `sources/cases/<id>/`，原始用户文件保持不变。`--out` 必须在本仓库忽略的 `.local/` 中。

## 生成与运行 benchmark

```sh
python benchmarks/research_report_agent_v2/generate_cases.py \
  --output .local/research-report-agent-v2/data

python benchmarks/research_report_agent_v2/runner.py \
  --data-root .local/research-report-agent-v2/data \
  --case v2_train_materials \
  --out .local/research-report-agent-v2/runs/train-materials \
  --budget-ledger .local/research-report-agent/global-ledger.jsonl
```

生成器复用 v1 的数值分布代码，使用七个新的独立随机种子，并重写自然语言请求；不在用户请求里指定工具链顺序。观察值都是合成数据，工具调用、CSV 读取、数值运算、图像和 PDF 文件均实际执行。

| 案例 | 用途 | 用户要求 |
|---|---|---|
| `v2_train_materials` | 训练观测 | 两组材料强度比较，组织与篇幅自定 |
| `v2_train_ml` | 训练观测 | 同一数据划分上的算法配对比较 |
| `v2_cert_environment` | 独立确认 | 温度与溶解氧关联及模型诊断 |
| `v2_eval_auto` | 留出评测 | 生物量分析，无大纲、篇幅自定 |
| `v2_eval_outline` | 留出评测 | 学习者成绩，用户大纲、最多三页 |
| `v2_eval_brief` | 留出评测 | 设备能耗，恰好一页摘要 |
| `v2_eval_technical` | 留出评测 | 看到统计结果后定制技术讨论 |

重复运行同一评测题只估计模型运行的波动，不算新的独立研究任务。评测轨迹不能用于本轮训练或确认。

初始真实训练中，模型在算法和环境题上选择了需要额外解释的 custom 路径，因此标准执行链缺少足够共同见证。这个观察保留为开发证据，不能把未走过的边补进库。后续增加三份不同数据的标准统计报告任务，题面只限定报告意图，不提供工具名、执行顺序或内部模式字段：

```sh
python benchmarks/research_report_agent_v2/generate_cases.py \
  --output .local/research-report-agent-v2/data_final_training --final-training
```

新组分别为 `v2_final_train_materials`（seed 410017）、`v2_final_train_ml`（420029）、`v2_final_cert_environment`（430031）。前两题用于训练，第三题独立确认；它们与原四个留出题的数据和题面分开保存。此命令不改变原来的 `CASES` 七题。默认 `--seed-offset 0`；设置偏移时，manifest 和 oracle 记录实际使用的种子。调整训练任务分布的事实必须随结果报告，不能宣称标准长链是没有场景设计就自然发现的。

## 从普通 DSH 轨迹形成 Motif

先用 `baseline --call-model` 完成新组的两项训练和不同数据的独立确认任务，再执行（以下运行目录名为示例，必须对应实际保留的完整轨迹）：

```sh
python benchmarks/research_report_agent_v2/compile_motifs.py \
  --train .local/research-report-agent-v2/runs/final-train-materials \
          .local/research-report-agent-v2/runs/final-train-ml \
  --certify .local/research-report-agent-v2/runs/final-cert-environment \
  --output .local/research-report-agent-v2/library.json
```

留出任务使用相同 runner，添加 `--mode execute --library .local/research-report-agent-v2/library.json`。普通对照不加这两个参数。两组沿用同一模型、工具集合、预算代理和输入，均关闭自动模型重试与压缩；工具拒绝后的模型自行修正会真实计费并保留。

相同的是输入、模型和工具条件；模型自由生成的分析/展示方案、报告篇幅与解释文字可能不同。这是两种 Agent 运行方式的实际交付对照，不能当作强制相同写作内容条件下的因果质量差异实验。对成本和质量的解释必须结合各次实际方案、重试与交付内容。

**人工先设计的是工具、语义/确定执行边界和后继授权。编译器收集的是实际出现的参数流。** 它要求相邻成功调用的返回字段精确成为下一步唯一参数，且该后继得到明确授权；至少两项不同训练任务以及第三项不同任务均有见证才入库。同一 CSV 换名字不算独立任务。这里的“独立确认”是观察到成功轨迹并检查约束，不是形式化证明。

`observed_authorized_edge_coverage` 列出实际观测候选的训练覆盖数和独立见证状态，缺证据就不录入。只有三次普通运行共同走到十条合格的参数传递边，才可能得到十步确定续接；代码和离线十边测试不构成真实采集成功的证据。

`learned_chains` 由已经入库的边自动连接生成，仅供说明；执行器仍每一步都核对来源文件、请求、工作区、记录摘要、工具 schema 和权限，通过后生成一条真实 MCP 工具指令。长链不是把完整流程藏进一个工具，再声称跳过很多次请求。自定义解释等新的语义决定必须回到 LLM。

如果插件自动发出的工具调用失败或结果无法核验，本会话后续保守交还 LLM；当前实现没有声称能对任意失败自动修复并重新进入所有长链。

## 记录与完成标准

- `intake.json`、`manifest.json`：输入字节摘要、请求、环境、预算、代码和工具版本。
- `model-requests/`、`cost-ledger.jsonl`：每一次真实云请求、响应、usage 和估费；含失败。
- `agent-events.jsonl`：真实 DSH 的每一条工具调用和结果。
- `motif-audit.jsonl`：跳过尝试、结果复核、回退理由。
- `metrics.json`：真实 API/MCP 次数、已验证接管、失败、完整 `delivery` 结果与累计账本。
- `workspace/`：有来源绑定的记录、图像及最终 PDF。

仅模型回答“完成”不算完成。最后一次报告验证和 `deliver_report` 必须通过，且返回 `delivered=true`、`quality_passed=true`，运行才标为 `done`。自动通过仍不等于完整科研质量获专家认可；实际文字、统计解释及版面需独立审查。节费与质量结论只能来自真实对照结果，不能从链长或离线测试推断。

## 离线检查

```sh
python -m unittest discover -s benchmarks/research_report_agent_v2/tests -v
node --test benchmarks/research_report_agent_v2/test_motif_plugin.mjs
```

在线 TypeScript 使用 JavaScript 兼容子集，`motif_plugin.mjs` 与 `.ts` 字节相同，作为部署文件；未修改 DSH 或既有核心模块。

## v2.2：减少排版返工与同内容对照

本轮修改仅在此 benchmark 目录内。普通 DSH 和 Motif 共用以下规则：

- 跨页正文按其排版块拼接后检查，页脚不会插入段落导致“缺字”误报；真实缺字仍拒绝。
- 正文超出计划边框不超过 3 pt（约 1.06 毫米），且没有裁切、结构重叠及其他硬错误时，保留为软提示。页数限制、文件/来源哈希、漏图、文字完整性仍是硬条件。
- 同稿同引擎复用排版回执；重新核验来源图、PDF、清单、审计及候选文件哈希。成功与失败都不会因为相同调用而重新绘制。真正失败要求说明限制或重新作出语义决定，不能循环重排同一稿件。
- custom 正文从任意的 1–3 段限制调整为 1–8 段，并保留总量与真实页高检查；单位增量 `{{unit_increment}}` 明确代表一个原始解释变量单位。科学数值绑定、授权与设计证据不放松。

`prepare_matched_experiment.py` 创建新的实验目录：三份独立训练/确认数据、四类任务的同内容对照和另外的自然请求诊断。固定方案来自历史真实方案并作明确记录的展示调整；技术讨论采用经过审阅的谨慎共同模板。`benchmark_frozen_decisions` 是公开给两组的实验输入，真实 LLM 仍需提交方案/解释，工具拒绝偏离或无效内容，绝不替换模型输出。无此输入时仍为自然请求流程。

```sh
python benchmarks/research_report_agent_v2/prepare_matched_experiment.py \
  --experiment .local/research-report-agent-v22-20261010 \
  --historical .local/research-report-agent-v2-20261010
```

这项受控实验回答“相同内容下减少多少调度请求”，不检验模型自由规划或科研写作能力。训练、独立确认、受控评测、自然请求、离线旧稿回放与开发预检必须分开记录；不能使用评测轨迹补入当前 Motif 库。`review/review_matched_runs.py` 核对最终交付所绑定的输入、方案、正文、图件、PDF和工具轨迹；不一致与失败保留原费用并明确标注。审计脚本独立于运行时，在冻结的真实实验完成后随本目录交付。

2026-10-10 的 Linux 实测记录位于忽略目录 `.local/research-report-agent-v22-20261010/`，旧实验完全保留。DSH 为 0.1.5-rc.3，真实模型为 DeepSeek Flash，数据为新的合成随机种子。48 项 Python 与 32 项 Node 检查通过。

| 同内容任务 | 普通 DSH 的 LLM 请求 | Motif 的 LLM 请求 | 每组 MCP 调用 | 每组 PDF 页数 |
| --- | ---: | ---: | ---: | ---: |
| 生物量常规分析 | 13 | 3 | 12 | 2 |
| 按大纲的配对成绩分析 | 13 | 3 | 12 | 2 |
| 恰好一页能耗简报 | 13 | 3 | 12 | 1 |
| 冻结讨论模板的技术报告 | 14 | 5 | 13 | 3 |

四组内容、图件、工具顺序相同，均无工具失败/Agent 排版重试；每次排版仍真实评估四个内部候选。受控总请求 53→14（-73.58%），MCP 49→49；按实际 token 的峰值估费 ¥0.23407624→¥0.18320480（-21.73%），不含三次训练/确认的 ¥0.15465096，也不含人工与研发。采集和确认依赖三项独立普通 DSH 轨迹，编译得到十条有见证的参数传递边。

另两次自然技术请求均交付，但内容不同：普通组 14 次模型请求，Motif 6 次；后者一次无效 JSON 被拒后由模型完整重提，没有排版返工。其估费 ¥0.07061344 略高于普通组 ¥0.07030544，不能据请求数减少推断费用必然下降。全轮十三次运行共 126 次真实 HTTP 请求、161 次 MCP 调用，估费 ¥0.71285088；此前与本轮累计 ¥4.00756520（不是提供商实际账单）。这些小样本和控制模板结果不代表任意科研报告的能力或平均节费。

独立复算：受控 148/148、自然 34/34 数值通过。十份 PDF 共 22 页的版面已检查，四对受控报告逐页渲染像素相同；技术报告仍有约 41% 的末页留白。自然生成的两份科研讨论各有局部推断需要修订（无明确精度目标便评价扩样收益、未定义温度差便比较斜率与残差标准差等），详见 `review/scientific-review-natural-v22.json`。排版门槛调整没有把这些科学问题判为通过，也没有改写原始报告。

```sh
python benchmarks/research_report_agent_v2/review/review_matched_runs.py \
  --repo . --experiment .local/research-report-agent-v22-20261010 \
  --output .local/research-report-agent-v22-20261010/review/matched-summary.json
```
