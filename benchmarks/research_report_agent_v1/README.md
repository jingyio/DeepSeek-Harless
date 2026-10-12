# 科研数据分析与报告 Agent：真实执行 benchmark

这个 benchmark 研究一个具体问题：**LLM 已经决定了分析方案、图型或报告内容之后，能否把确定性的文件传递、计算、绘图、导出和检查交给可验证的模体，减少反复询问 LLM 的次数，同时保留报告质量？**

数据是明确标注的合成观测；DSH、DeepSeek Flash 云端请求、MCP 通信、统计软件、绘图库、文件写入与 PDF 检查均使用真实实现。本实验不把模拟业务后端或固定模型响应当作真实 Agent 成绩，也不把合成数据结果当作真实科研发现。

本文件描述实现与复现方法。2026-10-10 的真实运行汇总见 [RESULTS.json](RESULTS.json)，实测依赖见 [ENVIRONMENT.json](ENVIRONMENT.json)。逐次运行原始证据保存在忽略的 `.local/` 中；完整交付包含它们的副本，不随源码提交。

### 本次观察到的结果（单次运行，不是稳定收益保证）

| 留出任务 | 普通 DSH 的 LLM 请求 | Motif 的 LLM 请求 | 普通 / Motif 高峰估费（元） | 两组自动数值/产物 QA |
| --- | ---: | ---: | ---: | --- |
| 生物量独立两组 | 11 | 10 | 0.040780 / 0.064931 | 通过 / 通过 |
| 教育成绩配对 | 13 | 8 | 0.054194 / 0.046649 | 通过 / 通过 |
| 设备负载与能耗回归 | 12 | 7 | 0.048586 / 0.035804 | 通过 / 通过 |

三组共 36 → 25 次真实 LLM 请求（减少 30.6%），但估费合计 0.143560 → 0.147383 元（增加 2.7%）。每个执行组有 4 次经结果验证的模体接管；模型在报告语义节点的修正及输出长度变化抵消了一部分收益。输入缓存也影响费用，不能用请求次数直接代替成本。仅有三个单次配对，没有重复运行方差或普遍收益保证。

2 个正式训练任务及 1 个独立认证任务从真实轨迹中认证了 4 条边，覆盖分析和绘图两段。报告导出候选没有入库：部分训练/认证报告计划未显式授权确定性续步。它们仍由 LLM 调度，没有为凑足候选数量放宽授权或改写轨迹。

共保留 14 次运行：9 次正式运行及 5 次开发试跑；其中两次启动失败无 API 请求，两次早期报告失败，另一次旧检查器漏过了占位符。全部 137 次实际 API 请求都有 usage，按高峰价格保守记账 0.612349 元，离峰估计 0.306174 元，均不是供应商账单。未修改 DSH 或现有 Motif 核心。

**自动 QA 通过不等于科研文字全部合格。**逐份审阅还发现模型无依据推断随机化情况、普通教育报告误述配对独立性、未经过功效分析却断言功效不足等问题。原始报告与性能指标保留；交付中的审阅修订演示 PDF 单独标注，其编辑不计为原始 Agent 成绩。详细意见、原文替换和哈希见交付的审阅记录。本次不能宣称已证明两组的科学文字质量相等。

## 1. 六个任务与独立划分

| 案例 | 阶段 | 场景与统计设计 | PDF 页数 | 不同图型数量 |
| --- | --- | --- | ---: | ---: |
| `train_materials` | 训练 | 热处理与材料拉伸强度；两个独立组，Welch t 检验 | 2 | 2 |
| `train_ml` | 训练 | 相同数据划分下的算法比较；按实验单元配对 | 3 | 3 |
| `cert_environment` | 独立认证 | 温度与水质氧含量；带截距的一元线性回归 | 3 | 2 |
| `eval_biology` | 留出评测 | 营养处理与生物量；两个独立组 | 4 | 3 |
| `eval_education` | 留出评测 | 同一学习者训练前后成绩；配对分析 | 2 | 2 |
| `eval_energy` | 留出评测 | 设备负载与能耗；一元线性回归 | 4 | 3 |

每个案例使用独立随机种子。每题含少量缺失值，要求 LLM 显式选择并解释 `complete_case` 处理：独立组/回归删除所需字段缺失的观测；配对设计剔除不完整的整对观测。不能用零填充或悄悄插补。

生成目录分开保存代理可见材料和评审真值：

```text
DATA_ROOT/
  dataset_manifest.json
  cases/<case_id>/
    data.csv                 实际分析的 CSV 文件
    study.json               研究问题、字段、实验单元、页数和图数要求
    task.txt                 用户任务题面
  oracles/<case_id>.json      生成种子、总体效应、缺失注入位置；MCP 不读取
```

总体效应不等于这个有限样本实际估计的效应。数值验收依赖重新读取 CSV 并独立复算，而不是要求样本结果恰好等于生成器的总体参数。

## 2. 哪些部分真实，哪些人为生成

| 组件 | 实现与范围 |
| --- | --- |
| 输入数据 | 脚本生成的合成实验观测；包含真实存在的 CSV 字节与研究元数据 |
| LLM | `deepseek-flash` 真实云端接口；非固定回复；关闭 thinking/reasoning |
| Harness | 仓库现有 Python SDK 启动实际 DSH Node runtime，执行原生 Agent 循环 |
| 工具通信 | DSH 的 MCP 客户端与本 benchmark 的 stdio MCP 服务真实通信 |
| 统计 | pandas 读表；scipy 执行 Welch/配对检验；statsmodels 执行 OLS |
| 数值复核 | 独立 `csv` 读取、Python `statistics` 与显式统计公式；仅 t 分布函数共用 scipy |
| 绘图 | matplotlib 实际生成 PNG、SVG、PDF；无预制结果图 |
| 报告 | ReportLab 实际排版中文 PDF；PyMuPDF 打开成品检查页数、文字、图片与边界 |
| 模体 | 从真实普通组工具轨迹学习，再用独立任务认证；运行时检查文件、授权和参数绑定 |
| 外部应用 | 本题直接处理实验文件，不连接或假装连接 Zotero、论文数据库、电子表格云服务 |

生成器只负责数据，不负责产生 LLM 的分析选择、报告结论或最终交付。Agent 使用的工具代码是预先实现的、有边界的统计与排版工具；实验不要求 LLM 每次临时编写 Python 代码。

## 3. LLM 与模体各自做什么

以下是工具职责图，不是强制写入 Harness 的路由表。普通组由 LLM 自行发出工具调用；执行组只可采用已在轨迹中观察到、认证通过且当前授权成立的续步。

```text
用户任务 → DSH → LLM → inspect_study
                      ↓
              LLM 选择统计设计、列、缺失政策、置信水平及假设
                      ↓
                 plan_analysis
                      ↓ 可学习的确定性续步
                 run_analysis → verify_analysis
                      ↓ 返回 LLM
              LLM 解释结果，选择合适图型和标题
                      ↓
                 plan_figures
                      ↓ 可学习的确定性续步
                 render_figures → verify_figures
                      ↓ 返回 LLM
              LLM 写解释/局限/下一步，确认报告类型与页数
                      ↓
                 plan_report
                      ↓ 可学习的确定性续步
                 export_report → verify_report
                      ↓ 返回 LLM
              交付 PDF、图件、位置和必要限制
```

例如，`plan_analysis` 返回 `plan_id`。普通组需要模型再决定调用 `run_analysis(plan_id)`。认证模体若证据和权限齐备，可以从前一步结果字段取得该 ID，直接向 DSH 返回相同的工具指令。DSH 仍按正常 MCP 路径执行真实统计工具，插件再检查工具结果。**被省略的是询问模型的一次请求，不是统计计算或工具执行。**

这里的 receipt 指“有来源和权限的执行凭证”：一个绑定实际文件的内容寻址记录。它包含批准的计划、来源版本、工作区和获准续步工具。LLM 必须在计划中设置 `allow_deterministic_continuation=true` 才产生续步授权，默认不授权。分析验证、绘图验证、报告验证之后不再授予新语义计划，必须回到 LLM。

本版本不使用固定 embedding 向量，也不宣称解决了任意请求的语义分类。LLM 负责理解新任务；插件根据**当前已批准计划、实际工具结果、唯一参数来源与认证续步**作出机械匹配。无法唯一匹配、来源变化、授权缺失或检查失败时继续普通 LLM 路径。

## 4. 学习、认证、权限与非侵入边界

所有新增实现集中在本目录。DSH 核心与已有 Motif 核心保持原样，通过现有公开插件挂点和 MCP 接口加载。`motif_plugin.ts` 使用 JavaScript 兼容的 TypeScript 写法，对应 `.mjs` 运行文件。

原有样例主要覆盖只读工具；本 benchmark 增加局限于当前运行目录的幂等文件产物续步，因此使用本目录的窄范围编译器与插件。不能把这项局部扩展写成“旧 Motif 内核已原生支持任意写操作”。

`compile_motifs.py` 从普通组原始工具事件挖掘相邻、成功且存在实际参数依赖的调用：后一步唯一必需参数必须恰好等于前一步的一个 ID 字段，前一步凭证必须授权该工具。并行发出的调用不被误认作已经观察到的依赖。只有在至少两个独立训练任务中出现，并在另一个独立认证任务中再次出现的边才进入库。留出题不能作为训练或认证题再次用于执行组评测。

工具功能及允许执行的范围需要人工定义，这是实验的能力边界；具体续步证据来自轨迹。这里没有把手写全流程 DAG 或“按这个顺序做”的提示词包装成新的自动发现算法。它验证的是一种狭窄、可审计的结构复用机制。

审查与回归检查关注以下边界，最终是否通过以实际测试日志为准：

- 来源 CSV/研究元数据、题面、会话、工作区及记录文件版本；跨题、跨目录和陈旧记录拒绝。
- 显式计划授权；参数只从认证字段提取；新科学解释、图型选择与叙述不自动生成。
- 真实训练/认证时的工具输入 schema 与运行时一致；库摘要及认证证据完整。
- 工具传输成功与业务质量成功分开检查；`quality_passed=false` 不能作为成功接管证据。
- 工具失败、参数歧义和版本不匹配回退；失败尝试保留，不为展示成绩删除。

## 5. 环境与离线验证

以下示例为 Linux Bash，从仓库根目录执行。先按仓库主说明安装固定 DSH/SDK 依赖，例如 `npm ci`、`npm run setup`。使用同一个包含 `deepseek_harness`、MCP 的 Python 环境安装本目录的统计与报告依赖；推荐 Python 3.12。中文 PDF 优先使用系统中文字库，例如文泉驿微米黑。

```bash
PYTHON=.venv-sss/bin/python
BENCH=benchmarks/research_report_agent_v1
DATA=.local/research-report-data
EXPERIMENT=.local/research-report-experiment

"$PYTHON" -m pip install -r "$BENCH/requirements.txt"
"$PYTHON" "$BENCH/generate_data.py" --output "$DATA"

"$PYTHON" -m unittest discover -s "$BENCH/tests" -p 'test_*.py' -v
"$PYTHON" -m unittest discover -s "$BENCH" -p test_runner.py -v
node --test "$BENCH/test_motif_plugin.mjs"
```

`--seed-offset N` 可生成另一套数据，但这会改变来源哈希。不要覆盖已有实验的数据；使用新数据目录和实验 ID，重新记录配置。离线测试验证计算、导出和守卫，不等同于真实 LLM 端到端成功。

## 6. 预览与真实调用

每个运行目录须是新目录，不能覆盖已有事件或结果。`--call-model` 缺省时仅预览，不发出付费请求：

```bash
"$PYTHON" "$BENCH/runner.py" \
  --data-root "$DATA" --case train_materials \
  --out "$EXPERIMENT/preview_train_materials" \
  --budget-ledger "$EXPERIMENT/shared-budget.jsonl"
```

真实运行前通过受保护环境注入 `DEEPSEEK_API_KEY=<YOUR_DEEPSEEK_KEY>`，不要把实际密钥写入代码、配置、报告或版本控制。父进程保留云 API 密钥，DSH 使用本机预算代理的临时凭证。

本次授权的 **100 元人民币是全部开发与对照实验共享的总上限，不是每题各 100 元**。以下所有运行必须使用同一个 `shared-budget.jsonl`；不要删除账本或通过更换账本重置余额。

先获取两个训练任务和一个认证任务的普通 DSH 轨迹：

```bash
for CASE in train_materials train_ml cert_environment; do
  "$PYTHON" "$BENCH/runner.py" \
    --data-root "$DATA" --case "$CASE" --mode baseline \
    --out "$EXPERIMENT/${CASE}-baseline" \
    --budget-cny 100 --budget-ledger "$EXPERIMENT/shared-budget.jsonl" \
    --max-output 4096 --max-requests 30 --call-model
done
```

先查看每个 `metrics.json` 的结束状态与 `report_quality_passed`，并审阅实际成品。模型说“完成”不等于合格 PDF 已生成。失败时保留旧目录和已记成本，采用新运行目录修复或重跑；必要的工具改动会改变配置，应说明原因并保持对照条件一致。

从这些实际轨迹编译认证库：

```bash
"$PYTHON" "$BENCH/compile_motifs.py" \
  --train "$EXPERIMENT/train_materials-baseline" "$EXPERIMENT/train_ml-baseline" \
  --certify "$EXPERIMENT/cert_environment-baseline" \
  --contracts "$BENCH/tool_contracts.json" \
  --output "$EXPERIMENT/receipt-library.json"
```

如果没有得到足够的真实证据，编译应失败；不能手工补造成功轨迹或强制指定续步来获得“通过”。

留出题的一组对照示例：

```bash
"$PYTHON" "$BENCH/runner.py" \
  --data-root "$DATA" --case eval_biology --mode baseline \
  --out "$EXPERIMENT/eval_biology-baseline" \
  --budget-cny 100 --budget-ledger "$EXPERIMENT/shared-budget.jsonl" \
  --max-output 4096 --max-requests 30 --call-model

"$PYTHON" "$BENCH/runner.py" \
  --data-root "$DATA" --case eval_biology --mode execute \
  --library "$EXPERIMENT/receipt-library.json" \
  --out "$EXPERIMENT/eval_biology-execute" \
  --budget-cny 100 --budget-ledger "$EXPERIMENT/shared-budget.jsonl" \
  --max-output 4096 --max-requests 30 --call-model
```

对 `eval_education` 与 `eval_energy` 使用相同方法。建议交错运行顺序，例如 biology 普通组先、education 执行组先、energy 普通组先，并记录实际顺序。共享服务缓存会影响费用，应分别报告缓存命中与未命中 token，不把热缓存优势全部归因于模体。可用 `--mode shadow` 观察候选而不接管；它也使用真实模型，费用同样进入总账本。

## 7. 从请求到报告、评审和成本的完整证据

运行链路是：

```text
task.txt → 真实 DSH → 原生 llm/stream 插件挂点
                    ├─ 需语义判断 → 本机预算代理 → DeepSeek Flash
                    └─ 唯一认证续步 → 结构生成工具指令
                      ↓
                   DSH MCP 客户端 → server.py → 实际统计/绘图/PDF 文件
                      ↓
                   验证结果 → DSH 工具事件 → 下一次判断或最终答复
                      ↓
                   自动质量检查 + 独立数值复算 + 可见成品人工审阅
                      ↓
                   合格任务对照、逐请求 usage、成本与时间统计
```

每个 `--out` 目录保存：

| 路径 | 用于回答什么问题 |
| --- | --- |
| `manifest.json` | 题面/来源/代码/库哈希、模型、模式、工具顺序、限额、平台与版本是什么？ |
| `scenario.json`、`runtime.patch.yml` | 哪个真实 MCP 服务被加载？两组的基础 runtime 设置是否一致？ |
| `motif-task.json`、`motif.patch.yml` | 执行组绑定哪个会话、目录、来源及插件？ |
| `agent-events.jsonl` | DSH 每一步实际调用了哪个工具、传什么参数、收到什么结果？ |
| `model-requests/*.request.json` | 实际发给云模型的消息、工具 schema 和参数是什么？ |
| `model-requests/*.response.txt` | 云端原始响应/流、工具指令、usage 或错误是什么？ |
| `motif-audit.jsonl` | 哪次接管、采用哪个认证模体、为什么回退、结果是否验证？普通组无此文件。 |
| `cost-ledger.jsonl` | 每次上游尝试的状态、usage、缓存 token、耗时、预留额与估费 |
| `metrics.json` | 本次请求数、工具数、已验证接管数、自动质量结果、时间及估费摘要 |
| `answer.md` | LLM 的最终答复；它本身不证明实际文件存在或质量合格 |
| `workspace/records/*.json` | 计划、分析、图集、报告、检查结果及内容寻址证据 |
| `workspace/artifacts/*/` | 真正生成的 PNG/SVG/PDF 图件、报告 PDF 与叙述/数值绑定文件 |

实验共享的 `shared-budget.jsonl` 保存跨运行预留和结算。每次请求发送前按峰值价格及保守输入/输出上限预留；完整可信 usage 到达才释放差额。失败、超时或缺少 usage 时保留预留额，不能把未知成本写成零。实际供应商账单与代码估费需要区分。

`model_request_skipped_verified` 是“某次确定性工具续步成功并完成凭证核验”，不是报告整体通过的同义词，也不是大模型内部思维链。系统关闭模型 thinking，不声称记录了不可见的模型内部推理。

完成实际运行后，可离线生成机器可读汇总和科研风格的比较图：

```bash
"$PYTHON" "$BENCH/summarize.py" \
  --runs-root "$EXPERIMENT" --library "$EXPERIMENT/receipt-library.json" \
  --output "$EXPERIMENT/RESULTS.json"
```

汇总器按最终库中证据的 `run_id` 标记正式训练/认证；同题其他早期尝试归为 `development_pilot`，不混入正式认证。所有失败和费用仍保留。留出题有多个合格重复时不会自动挑选最好的结果；没有匹配配置、真实日志和合格产物时，不生成节省主张。`RESULTS.json` 与旁边的 `comparison_figures/` 是真实运行文件的汇总，不替代人工审阅。

本次九份实际报告还保存了可复现的独立数值复核与人工阅读式 AI 审查快照：

```bash
"$PYTHON" "$BENCH/review_observed_results.py" \
  --experiment-root "$EXPERIMENT" \
  --output-dir "$EXPERIMENT/review-reproduced"
```

实验根目录须包含原始 `data/`、`runs/` 和 `library.json`。脚本从 CSV 独立复算数值，不调用 benchmark 原统计函数；只在指定目录生成两个新的审查 JSON，不修改报告、日志或输入数据。省略 `--output-dir` 时默认输出到实验根目录的 `review/`，但已有文件一律拒绝覆盖。

**`MANUAL` 与 `EXECUTE_REVISIONS` 是本次实际阅读的固定快照，不是自动科学质量分类器。**脚本同时校验原报告 ID、实际 PDF 哈希、报告计划内容摘要及唯一原文片段；新报告或修改后的报告不能复用这些旧评语。本次评语是 AI 非盲审，不是人类专家背书。未来实验需要重新阅读并形成新的审查记录，而不能把脚本的预存意见作为新实验的自动审评结果。

## 8. 如何比较结果

普通组与执行组应采用同一题面、数据、工具集与顺序、模型、输出限制、统计代码、图件和报告质量规则。普通组保持 DSH 原生多工具调用能力，不能为了放大收益限制其批量调用或故意增加请求。执行组唯一预期区别是加载认证模体插件。

先判断报告合格，再比较消耗。至少检查：

1. 研究设计是否识别正确；配对是否按实验单元对齐；缺失样本量是否解释。
2. 效应方向、数值、置信区间、p 值和样本量是否通过独立复算；叙述是否正确理解这些量。
3. 图是否展示实际数据与不确定性，图型是否适合设计，轴和单位是否明确，无误导性因果结论。
4. PDF 页数与图数是否满足题面，中文可读，内容不越界，必要段落和数值完整。
5. 请求/响应、工具失败、修订、重试、缓存命中/未命中和最终文件是否均可追溯。

自动检查不替代视觉审阅和科研判断。报告文字由真实模型生成，可能出现不合理的解释，即使所有数值都正确。人工审阅应使用预先明确的标准，尽量不让审阅者先知道报告属于哪个组，并记录修订及其耗时。

费用应至少分列：训练轨迹、独立认证、留出普通组、留出执行组、失败/修订、额外质量评审。训练和认证不是免费收益；只有足够多后续任务能摊销这部分成本。小样本单次结果不能保证稳定节省或普遍胜过其他系统。

## 9. 当前适用范围与尚未比较的方案

- 仅支持两个独立组的 Welch t 检验、两条件配对 t 检验、带截距的一元 OLS 回归；不是通用统计专家系统。
- 仅支持显式 `complete_case` 缺失处理；没有多重插补、复杂缺失机制建模、混合效应、多重比较或稳健回归。
- 报告为中文 PDF，页数限定 2–4 页；当前不承诺 DOCX 输出、任意模板或任意长度自动排版。
- 图为有限的预实现图型：独立组散点/区间/经验分布，配对连线/差值分布/效应区间，回归散点拟合/残差/斜率区间。图标签使用英文，避免跨平台中文字体问题。
- 任务与工具集合被限定，权限来自明确计划；没有任意文件访问、通用代码执行或自动连接外部数据平台。
- 不使用语义 embedding 分类，也不证明在开放世界中能自主发现任意研究工作流。
- **尚未完成一般参数化脚本/固定自动化流水线的收益对照。**这类成熟工具可能同样省掉调度调用；本实验不能据此宣称模体是唯一或最优方案。
- 代理记录的是按固定价格表计算的估费与预算占用；它不是供应商发票，亦不包含人工开发、维护和审阅成本。

需要加入新学科或新统计方法时，应先增加真实工具及质量标准，再采集普通轨迹、独立认证和留出对照；不能把既有模体频率当作新方法的科学适用性证据。
