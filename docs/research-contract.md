# GeneLoop Research Contract（F00）

> **状态**：G0 评审稿<br>
> **Owner**：@jingyio｜**Reviewer**：第二位合作者<br>
> **仓库路径**：`docs/research-contract.md`<br>
> **论文定位**：AI Agent 方法研究，以可复现的效率收益和自进化行为为核心，不以完成通用产品为前提。

## 1. 研究定位与问题

**Efficiency-Oriented Self-Improving Agent Runtime via Structure–Semantic Separation**

**核心问题：** Agent 能否从持续执行中自动形成可复用的结构化能力，并**共同改进这些能力与使用它们的 Runtime 算法**，使后续任务在保持质量的前提下，需要越来越少的 LLM Work？

AutoTool 从工具调用惯性出发，MGGA 将有证据支持的局部执行交给 Runtime。**GeneLoop 的新一步不是再提出 Motif，而是让 Motif 及其发现、匹配、执行和更新机制共同自进化。**

## 2. 三项核心创新假设

### C1｜广覆盖、代码级的 Runtime 自进化（Full-Stack Runtime RSI）

**演化的不仅是经验，还包括处理经验的算法。**

将 Motif、Matcher、Miner、Updater、参数绑定、语义交接和成本策略纳入统一 RSI 协议。允许基于轨迹反馈修改**真实匹配/学习逻辑及代码**，而非局限于 Prompt、阈值或新增 Skill。

通过依赖检查、独立验证、版本发布和回滚，使多个模块的更新能够协同生效。

**验证：** 比较 Frozen、Motif-only RSI、Matcher-only RSI、Independent Module RSI 和 Joint RSI，证明联合更新带来额外的任务质量或效率收益。

“全”指执行与学习关键链路的可演化覆盖，不包含允许修改可信评测器或权限边界。

### C2｜从开放式代码轨迹涌现可执行工具（Learned Operator Abstraction）

传统 Motif 依赖可观测的工具结构；Coding Agent 往往只暴露 Bash/Python 调用。

GeneLoop 从真实命令、代码及执行回执中识别可复用操作，学习带输入输出、参数来源、依赖、副作用和适用条件的 **Operator**，通过认证后进入 Motif Library。

无法可靠拆解的代码保留为不透明单元，不虚构依赖。

**验证：** 在未见输入及不同任务上比较自动 Operator、完整脚本缓存和已有 Skill 编译方法的有效覆盖、错误执行与学习成本，证明收益不只是重复运行同一脚本。

### C3｜面向 LLM Work 消减的自进化执行控制（Efficiency-Oriented Evolution）

GeneLoop 不以 Skill 数量或命中率为最终目标，而是让 Runtime 根据当前证据，**直接执行已确定的操作，并只为未解决的参数、冲突或语义判断请求 LLM**。

质量、失败、实际模型请求及冷热 Token 成本反过来驱动 Motif 与 Runtime 策略更新，持续调整模型和结构执行之间的计算边界。

**验证：** 在时间顺序到来的后续任务上，证明真实 Provider 请求、Token 或累计成本下降，且任务质量不退化；完整计入学习、认证、匹配、回退和恢复成本。

`verified_skip` 不等于相对 Baseline 净少的请求数。

**统一论文主张：**

*GeneLoop jointly evolves executable experience and the runtime algorithms that use it, progressively shifting evidence-supported work away from LLMs.*

## 3. 与最接近工作的实质区别

| 工作 | 已解决什么 | GeneLoop 要推进什么 |
|---|---|---|
| **AutoTool / MGGA（自身基础）** | 惯性工具选择；有证据的局部结构接管与语义交接 | 从固定执行架构推进到 Motif 与 Runtime 学习/匹配算法的**联合在线演化** |
| **Skill-DisCo / NSI** | 从轨迹归纳具有分支、循环和动态绑定的参数化技能；部分技能内部由程序解释执行 | 不以完整子目标程序为唯一单元；从自由代码形成局部 Operator，由 Runtime 在新证据下**跨片段匹配、直接执行并缩小 LLM 介入** |
| **ModularRSI / HarnessX / HarnessPro** | 已能修改 Harness 组件、代码或策略，也涉及效率优化 | 将自改进聚焦到**可执行结构及其匹配/执行算法的协同演化**，用实际减少 LLM Work 而非仅提升 Harness 得分检验价值 |
| **Ledger / Script Cache** | 管理单任务执行状态，或复用代码、结果、流程 | 结合**跨任务新学到的 Operator、当前证据和持续演化的 Runtime 策略**，减少未来模型决策，而非只避免重复运行 |

**关键差异不是“我们也能改代码”或“我们也有图”，而是：执行经验和使用经验的算法能否一起改进，并使未来必要的模型计算持续减少。**

这些差异是待实验证明的研究假设，不预设已有工作无此能力。

## 4. 最小 Benchmark 与对照

**首选场景：**

- **AppWorld**：主实验，验证 API/Python 执行、跨任务结构复用与 RSI。
- **Terminal-Bench 2.0**：验证自由 Bash/代码环境下的泛化能力。
- **ToolSandbox / τ³-Bench**：补充验证状态变化与错误匹配，不阻塞第一轮交付。

**主要 Baseline：**

Native Agent、Script/Skill Cache、Frozen Motif、Motif-only RSI、Matcher-only RSI、Independent Module RSI、**Joint GeneLoop**。在相同任务条件下尽可能加入可复现的技能学习或 Harness RSI 强基线。

**必须回答三个问题：**

1. 新 Operator 能否跨任务可靠复用？
2. 同一份 Skill 下，Runtime 主动匹配和绑定是否比 LLM 选择减少额外计算？
3. 同一预算下，Motif 与 Matcher 联合演化是否优于独立演化？

采用 **Train/Dev → Validation → Frozen Test**，并设置时间顺序 RSI：任务 `T_i` 完成后产生的经验只能用于后续任务。

报告成功率、错误执行、实际 LLM 请求、冷热输入/输出 Token、在线费用、进化/认证费用与累计净成本。

允许 Dev 迭代，不用 Test 反向修改方法。

## 5. 本轮范围与 G0 验收

**本轮论文优先证明：** C1–C3 构成真实闭环，先在一个标准 Benchmark 上取得可归因的质量—效率收益，再用第二个任务环境考察泛化。可先发布明确标注实验范围的预印本。

**暂不要求：** 所有模块同时自改、优化器 `θ₀ → θ₁ → θ₂` 的完整递归、自主修改安全守卫、多用户并发产品或大规模部署。

若宣称优化器自身递归改进，须另证下一代优化器参与产生再下一代更新。

F00 只冻结**研究问题、创新假设、最接近工作的差异和评价口径**，不冻结具体 Matcher 算法或要求立即完成实验。

**G0 通过条件：**

- A/B 能统一解释三项创新及其联系。
- 每项创新有一个可反驳的实验。
- F02 据此定义 RSI/Operator/Runtime 协议。
- F03 据此建设主 Benchmark 与 Baseline。
- Reviewer 审核后合并至 `main`。
