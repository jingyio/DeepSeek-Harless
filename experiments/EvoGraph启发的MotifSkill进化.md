# EvoGraph 启发的 Motif skill 进化：首个可运行切片

## 借鉴了什么

截至 2026-09-25 检查了 [EvoGraph-Agent `main` README 与最小核心](https://github.com/jingyio/EvoGraph-Agent/tree/322ca9a1f4d6b3f811284a6674e91bede4380812) 和 [完整 `develop` 实现](https://github.com/jingyio/EvoGraph-Agent/tree/39ca6578d3611ca2dfb0b9a79a611e6f855e3bbc)。它把正常任务轨迹中的可复用结构保存成版本；当前任务重新绑定自己的数据；图结构 `G` 与匹配描述 `M` 分开修订；创建或修订本身不等于收益，后续任务实际执行该版本才有复用证据。`main` 是可审查的机制核心，完整运行和候选实验在 `develop`。仓库报告的 12 个财务任务结果属于该候选范围，不能直接移作 SSS 的预期收益。

SSS 将这一思路用于 Motif 的**决策依赖结构**。首个 skill 是“为调研报告的每个问题选择证据”：版本说明选择决定依赖哪些候选片段。它不是给模型加提示词，也不保存旧论文的段落、答案或结论。源文件、问题和证据都在新任务中重新核对。

## 已接入的运行机制

`research-points.py` 的证据选择阶段现在能加载本地版本账本：

Motif **执行失败**也进入进化候选的来源，但不能据一次失败直接修改执行图。运行时先阻止当前步骤、留下失败算子、原因、输入版本以及 Motif／参数绑定签名；不把原文或参数值复制进可共享的 skill。再区分是来源损坏、工具接口变化、参数来源错误、守卫不足，还是语义判断错误。只有能复现失败、提出明确守卫或参数边修订，并在独立任务上验证质量与成本后，才允许启用新版；启用后仍须记录后续命中、再次失败和回退。负向 Motif 可以用于阻止已知坏路径，但不能被当作可执行计划。

失败进化目前完成了**凭据与候选核对**：迁移后的依赖求解器会在缓存命中前重验前置条件，研究资料读取节点失败时由 `research-points.py` 在被忽略的 `.local/` 运行目录保存 `motif-failure-witness.json`，并以零模型请求停止。每份凭据带执行 ID，但不含原文或错误详情。`src/motif_core/offline/failure_evolution.py` 可以从同一输入版本、参数绑定和错误类型的独立失败提出精确范围的负向守卫候选，再检查独立失败重放与成功对照。它**不自动启用**；单次失败、重复提交同一凭据、对照成功会被误阻断时都不能通过。尚未覆盖完整 MotifExecutor 的全部失败类型，也尚未完成跨任务报告质量与成本门。用损坏文本资料做过一次无模型端到端回放，得到 `dependency_tool_error`、0 次模型请求；它是恢复边界验证，不是正式效果分数。

1. 旧版本 `global-v0`：任何候选资料变化，所有问题的证据选择都失效。
2. 候选新版 `per_point`：每个问题只依赖本问题的候选片段和问题定义；资料变化时，仅相关问题重新选择。
3. 进化提案必须有来源运行、真实候选变化和“未变问题也被旧版失效”的事件；没有这些条件拒绝提案。
4. 版本不能只凭训练案例启用。独立留出案例必须通过“没有复用已变候选”“安全复用数不退化”检查，且至少观察到一次结构收益。
5. 版本启用后，后续运行记录实际处理的问题和版本 ID。创建、评估、启用、实际使用分别留痕。账本仅在显式指定 `--selection-skill-registry` 时写到本地文件；默认执行继续使用安全的逐问题依赖方式。

实现入口：[进化账本](../src/workflows/motif_skill_evolution.py)、[Motif 选择状态](../src/workflows/motif_point_selection.py)、[命令入口](../scripts/evolve-motif-selection.py)、[调研执行入口](../scripts/research-points.py)。当前提案器只认识一项白名单结构修订：全局候选依赖改为逐问题候选依赖。它尚不能自动发明任意 Motif 图节点或更新模型提示词。

## 本地机制实验记录

在 DR³-Eval 中文 003 的 16 份来源、4 个必答问题上，使用被忽略的 `.local/` 临时副本，未修改冻结资料，未调用模型：

| 运行 | 候选变化 | 旧版 `global-v0` 安全复用 | 新版逐问题安全复用 | 不安全复用 |
|---|---|---:|---:|---:|
| 训练扰动 | `web-06.txt` 内容变化，仅影响 `coarse` 候选 | 0/4 | 3/4 | 0 |
| 留出扰动 | `web-13.txt` 内容变化，影响 `fine` 和 `methods` 候选 | 0/4 | 2/4 | 0 |
| 后续实际运行 | 新版启用后再改 `web-09.txt`，影响 `methods`、`limits` | — | 2/4，另 2 项待重选 | 0 |

前两行是候选签名与决策复用的确定性评估；留出扰动是**同一道题的另一份资料变化**，不是独立研究问题。第三行来自实际命令预览，新版的运行记录中有 `selection_reused` 和 `selection_invalidated` 事件。进化账本在 `.local/motif-skill-demo/registry.json`，源运行和后续运行分别为 `.local/point-research-runs/20260925T014646Z-bd0675/` 与 `.local/point-research-runs/20260925T014757Z-b1c3ed/`；后一轮局部失效预览为 `.local/point-research-runs/20260925T014819Z-164c0b/`。这些原始记录不提交仓库，运行标识只是本机复查线索。

该实验没有测模型生成报告，因此不能声称报告质量、真实 token 或总费用改善。旧版 0/4、新版 3/4 和 2/4 指的是内部证据选择可复用数，**不是任务完成率**。节省多少模型请求还取决于之后是否按缺失问题单独调用语义模型；代码已经能只为缺失问题构造选择提示，但尚未进行付费实测。

## 复现与下一步验收

初始化版本账本：

```bash
.venv312/bin/python scripts/evolve-motif-selection.py --registry .local/my-motif-skill.json --init
```

用 `research-points.py --selection-skill-registry .local/my-motif-skill.json` 运行一条已验证的选择，再在同一资料目录修改**临时副本**中的一份资料，携带 `--previous-selection-state` 重跑。`--source-run` 指首次运行目录，`--changed-run` 指第二次运行目录。将训练和留出扰动各保存为 JSON 数组，每项包含 `id`、`points`、`before_candidates`、`after_candidates`、`selected_ids`；如果问题要求也发生变化，可额外放 `after_points`。然后执行：

```bash
.venv312/bin/python scripts/evolve-motif-selection.py \
  --registry .local/my-motif-skill.json \
  --source-run .local/point-research-runs/<first> \
  --changed-run .local/point-research-runs/<second> \
  --train-cases .local/train-cases.json \
  --validation-cases .local/validation-cases.json
```

下一道研究门槛是把“结构复用”扩展为真正的 Motif skill 演化：从通过审核的轨迹提出节点、依赖、参数槽和守卫修订；验证当前资料重新绑定、失败回退、报告质量和总成本；在冻结的**不同研究任务**上对照固定 Motif 与持续进化 Motif。匹配范围的修订要单独评估，避免把进化版误用于无关任务。还要累计冷启动、提案、验证、失败和人工复核成本。只有后续任务交付合格、总成本更低，才称为 SSS 的效果增益。
