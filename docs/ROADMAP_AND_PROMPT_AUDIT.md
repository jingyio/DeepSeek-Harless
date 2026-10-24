# GeneLoop｜共享 Roadmap 与 Vibe Coding Prompt 审计

> **建议仓库路径**：`docs/ROADMAP_AND_PROMPT_AUDIT.md`<br>
> **版本**：v1.2 整合候选（2026-10-24，v1.1 原稿＋会话补充）｜**维护者**：A（@jingyio）、B（@peilin6）两人<br>
> **定位**：面向 AI Agent 方法论文/预印本的研究—开发路线图，同时保留两人协作、产品迭代与 Prompt 审计。<br>
> **约束**：本文件为待评审的计划，不代表代码完成、实验通过、Issue 已创建或 Reviewer 已批准。以 `docs/research-contract.md`（F00）为研究主张的权威来源，本文件负责执行计划。
> **v1.1 调整**：对齐 F00 的 C1 代码级全链路 RSI、C2 开放代码 Operator 抽象、C3 LLM Work 消减；AppWorld 优先；Motif–Matcher 联合演化为论文最小研究闭环；`θ0→θ1→θ2` 仅在声明递归优化器时强制。

## 0. 十分钟使用说明

2026-10-24 F02 审核入口：先看[通俗结果与同例演示](rsi-protocol-v1.md)，再看[实际提示审计](prompt-audits/F02.md)和[实验记录](experiments/f02-protocol-local-20261024-v1.md)。#108–#113 已采用“拿到什么 → 同例 → 验收”的首页，原技术要求折叠保留；新任务可用仓库 Issue 模板。此为最小协议候选，不将后续学习或 Matcher 更新模板记为已执行。

**同时保留两种工具，职责不同：**

- **GitHub Issue + Project Board 管理「做什么」**：一个 Issue 是一个可独立交付的功能包（Feature Package），包含边界、Owner、依赖、验收条件。**不要为每个函数、每次 AI Prompt 创建 Issue。**
- **本文件管理「为什么、怎么做、怎么判断、AI 怎样被指挥」**：共享研究路线、跨功能协议、Benchmark 反馈、每次 Vibe Coding 的**完整脱敏 Prompt 原文**、结果证据与人工判断。
- **GitHub PR 管理「真实改了什么」**：代码 Diff、自动检查、交叉审核、回归和发布记录。Prompt 历史不能替代代码审查。

操作顺序：`选一个 Ready 功能包 → 领取 Issue → 在本文件记录本轮 Prompt → 交给编码 Agent → 运行开发集 Bench / Test → 记录完整反馈与下一条 Prompt → 功能自测通过 → 对方审核 PR → 合并 → 必要时部署 → 在 Board 关闭 Issue`。

每个人**同时最多负责一个 Doing 功能包**。一般无需频繁互相询问设计：只有**协议边界变更、权限/安全影响、准备发布，以及最终验收**需要对方介入。跨模块修改先提交兼容性 RFC，不能让两个 AI Agent 同时重写公共入口。

> **本轮落库说明（2026-10-24）**：已核对既有 [GeneLoop Development Board](https://github.com/users/jingyio/projects/1)，本轮复用该看板。连接器写入返回 403 后，经已登录的浏览器创建 F01/F02/F03/F05/F08、设置 Assignees 并加入 Board；实际 Issue 映射见 §11。本文及研究契约通过 PR 供审核，未合并前不算 G0 通过。未发送的 Prompt 模板仍保持原状态。

---

## 1. 我们的共同目标与非目标

### 1.1 研究问题与论文贡献

**研究定位：Efficiency-Oriented Self-Improving Agent Runtime via Structure–Semantic Separation.**

**核心问题**：能否让 Agent 从真实执行中持续获得可复用 Operator/Motif，**联合改进执行经验与处理经验的 Runtime 算法**，进而在质量可控的情况下减少后续任务的实际 LLM Work？

沿着 AutoTool（重复工具决策）→ MGGA（Runtime 结构接管）→ GeneLoop（执行结构与使用这些结构的算法共同演化）推进。首篇定位 **AI Agent 方法论文 / 可复现实验预印本**，不是完整产品架构论文。

| 核心假设                             | 本轮重点机制                                                 | 最重要的验证                                                 |
| ------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **C1 Full-Stack Runtime RSI**        | Motif、Matcher/Miner/Updater 以及必要的交接策略具有统一可演化接口；允许实际代码/逻辑修改，通过独立验证后联合发布 | **Joint RSI 优于 Motif-only、Matcher-only 和 Independent Module RSI**；至少一次真实 Matcher 算法/代码更新被后续任务使用 |
| **C2 Learned Operator Abstraction**  | 从 MCP、Bash、Python 的真实轨迹中恢复具有来源、依赖、接口和副作用约束的 Operator；无法验证的内部操作保持 opaque | 新 Operator 在未见输入/不同任务上有效复用，并优于合理 Script/Skill Cache 基线 |
| **C3 Efficiency-Oriented Evolution** | Runtime 依据当前执行证据推进已确定的工作，语义缺口才调用 LLM；以质量、真实请求、冷热 Token 和学习成本指导更新 | 时间顺序学习后，质量不退化，模型工作量和**包含学习/认证的累计成本**有可归因改善 |

**共同方法主张**：*GeneLoop jointly evolves executable experience and the runtime algorithms that use it, progressively shifting evidence-supported work away from LLMs.*

这里的“全”指**重要执行和学习模块的可演化覆盖**，不意味着所有模块必须在首篇同时演化，也不允许修改可信权限、独立评测器和原始计费。`θ0→θ1→θ2` 只有在论文声称优化器本身递归演化时才是强制条件。

### 1.2 与已有工作的研究边界

- **Skill-DisCo / NSI**：已有子目标程序、PFSM/符号分支、参数绑定和技能修订；我们的候选增量是自由代码 Operator、运行时跨片段证据匹配，以及**Motif 与 Matcher 算法本身的联合演化**。
- **ModularRSI / HarnessX / HarnessPro**：已有 Harness 组件的策略/代码级改进，不能声称对方“只改 Prompt”；我们以可执行经验及其**匹配、抽取和执行控制算法共同演化**为主要方法对象，以 LLM Work 而不是单一得分作核心评价。
- **Ledger / Script Cache**：已有任务状态与代码/结果/工作流复用；须检验跨任务学到的新能力及不断调整的 Runtime 控制相对于合理组合基线的额外价值。

具体证据、相关工作与引用以 `docs/research-contract.md` 为准，F07 中用实验验证差异；不把叙事差异直接等同于完成创新性验证。

### 1.3 产品目标（与首篇研究解耦）

Web/Desktop 共享可信 Runtime；Motif 可版本化、授权共享，用户文件、凭据、会话及环境隔离。先稳定服务少量真实用户，再考虑扩容。**F06/F09/F10 不应阻塞首篇预印本 F11**，除非明确需要它们检验某个论文主张。

### 1.4 暂时不做与独立守卫

- 不因为统一协议而重写全部可用代码。Python 保留离线学习/认证，TypeScript 承担权威在线执行；旧路径兼容迁移。
- 不把工具批处理、短 Prompt、简单缓存命中，直接算成 `verified_model_request_skipped`；区分真实 Provider 请求差与内部接管数。
- 不允许自修改候选改变独立测试、冻结测试集、账号权限、执行守卫或原始成本账本。
- 不要求所有 Harness、所有模块、万级部署、通用程序合成或优化器多代自改在首篇一次完成。

### 1.5 最小研究验收（研究 Gate，不是虚构的已有结果）

- **至少一个标准 Benchmark** 跑通任务轨迹→Operator/Motif 学习→执行→反馈→**真实 Matcher 逻辑/代码更新**→后续任务使用的闭环。
- 在同一模型/任务/预算/权限条件下，完成 Native、合理 Skill/Script Cache、Frozen、Motif-only、Matcher-only、Independent 与 Joint RSI 对照；必要时固定同一 Skill 比较 LLM 选择与 Runtime 决策。
- 记录任务成功/失败、Provider 请求、冷热输入和输出 Token、在线费用、进化/认证/回退成本；报告真正跨任务复用、错误执行及盲测泛化。
- AppWorld 优先提供核心结果；Terminal-Bench 2.0 是代码/终端外部验证目标，ToolSandbox/τ³-Bench 为可选状态变化场景。Benchmark 选型需通过 F03 的可行性审查。

---

## 2. 两人协作：按完整功能包而不是按小模块

|            | A：研究/Runtime 功能负责人                                | B：Benchmark/场景/产品功能负责人                             |
| ---------- | --------------------------------------------------------- | ------------------------------------------------------------ |
| 长期关注   | Operator/Motif、Matcher 代码演化、统一 RSI 协议、执行证据 | AppWorld/外部 Benchmark、Baseline、计量、现有场景兼容、产品运维 |
| 近期第一项 | **F00 定义研究边界与成功判据**                            | **F01 仓库基线与开发流程收敛**                               |
| 近期第二项 | F02 统一 RSI 引擎                                         | F03 统一 Bench Runner 与 Baseline                            |
| 可独立更改 | 自己功能包内代码、专有测试、设计与实验文档                | 自己功能包内代码、专有测试、设计与实验文档                   |
| 必须互审   | 修改共享协议、生产权限、外部发布、最终 Merge              | 同左                                                         |
| Reviewer   | B 审核 A 的最终功能 PR                                    | A 审核 B 的最终功能 PR                                       |

**功能 Owner 拥有端到端实现权**：可以自己编写 RFC、调用编码 Agent、生成子模块、写测试、调试和优化。审查人主要审核三个时间点：①影响另一条工作流的协议/边界冻结；②功能达标的 PR；③真实部署/论文主张。其他中间 Prompt 和代码迭代不要求实时批准。

**接口稳定策略**：F02 产出 RSI Protocol v1（包括 Fixture 和版本化 Schema）。B 首先以协议快照接入 AppWorld，兼顾已有 Paper/Data/PPT 的兼容性；A 可以继续演化引擎内部。破坏性契约变更先登记 RFC 和 Migration Plan；原则上新增版本兼容，不在另一人的活跃分支下直接改接口。

**Vibe Coding 作业规则**：一个 Issue 对应一个主工作区/分支，可以包含多次 Agent Prompt、若干小提交。Agent 可以自由探索自己的功能内部，但不得越界修改其他 Feature Owner 的协议、默认安全策略或真实数据。每次关键 Prompt、修订 Prompt、拒绝原因与验收证据都按 §6 记录。

---

## 3. GitHub Board：12 个功能包，而不是 32 个微任务

建议新建 **GeneLoop Research & Product** 项目，看板列为 `Backlog / Ready / Doing / Review / Blocked / Done`。字段：`Owner(A/B) / Track(Research, Product, Infra) / Gate / Priority / Evidence Link`。每个功能卡都以 `Fxx` 为稳定 ID，并填入真实 Issue URL。每人同一时刻最多一张 `Doing` 卡。不得以 AI 自动生成大量碎 Issue 替代任务拆解。

> **Owner** 表示主实现者；**Reviewer** 始终是另一人。编号不等于时间线上的完全串行：两个 Owner 可以各自独立推进一个完整功能包。

| ID      | 功能包（Issue 标题建议）                     | Owner | 前置依赖                            | 完成定义（摘要）                                             | Gate       |
| ------- | -------------------------------------------- | ----- | ----------------------------------- | ------------------------------------------------------------ | ---------- |
| **F00** | 精简研究契约：C1/C2/C3 与可验证差异          | A     | 无                                  | `docs/research-contract.md`；3 项候选贡献、最接近工作、主 Benchmark/核心消融；Reviewer 审核 | G0         |
| **F01** | 仓库基线、Vibe Coding 规约与分层 CI          | B     | 无                                  | 现有代码/实验归档、README/AGENTS、CI 和两人 PR 规则；不大规模改算法 | G0         |
| **F02** | 统一 RSI Protocol v1 + Operator/Runtime 接口 | A     | F00                                 | Execution Event、Operator/Motif、Evidence、Runtime Decision、RSI Update；Python/TS Fixture 与旧路径兼容 | G1         |
| **F03** | AppWorld Benchmark Runner + Baseline + 计量  | B     | F00、F01                            | AppWorld 轨迹采集/原生 Agent/评分/费用；split 冻结；缓存/Skill 强基线；评估 Terminal-Bench 可行性 | G1         |
| **F04** | Benchmark 与已有场景适配                     | B     | F02 ABI、F03                        | **优先 AppWorld** 的 API/Python Operator 执行端到端；保留 Paper/Data/PPT 原有能力和回归，后者不阻塞首篇 | G2         |
| **F05** | 在线 Operator/Motif 学习与证据更新           | A     | F02、F03                            | 新 Bash/Python/工具轨迹→抽取→独立认证→下任务使用；Positive/Negative 修订与失效 | G2         |
| **F06** | 共享 Motif Store、版本与并发一致性           | A     | F02                                 | 快照、原子发布/回滚、授权隔离；**产品/扩展性方向，可与论文并行，不是 F11 必需依赖** | G3-Product |
| **F07** | RSI 主实验、对照和消融流水线                 | B     | F03、F04、F05；F08 的候选结果       | 时间顺序在线学习；Frozen/Motif-only/Matcher-only/Independent/Joint；外部验证；质量与全成本归因 | G3/G4      |
| **F08** | Motif–Matcher 代码级联合自进化               | A     | F02、F05；使用 F03 Dev/Selection    | 匹配/学习实际算法变更、沙箱验证、版本加载及任务使用；Joint vs Independent；严格多代 optimizer RSI 可选 | G4         |
| **F09** | Web/Desktop 双端产品 MVP                     | B     | F04、F06                            | 共用产品 API、最小权限、任务恢复；不作为预印本前置条件       | G5-Product |
| **F10** | 服务发布、监控、隔离与规模测试               | B     | F06、F09                            | 灰度回滚、并发与压力、容量和运维；不作为预印本前置条件       | G6-Product |
| **F11** | ACL 类 AI 论文/预印本与复现包                | A     | F07 + F08 最小方法证据（若主张 C1） | 论文主张逐项对应真实结果、冻结测试、匿名复现和局限；**可先公开预印本** | G4         |

**初始看板状态**：`F00 → Ready (A)`、`F01 → Ready (B)`；其余先 Backlog。所有后续状态以真实 GitHub Board 为准。不要因为代码文件已经存在就自动把功能标记 Done。

**Issue 正文模板**（每个功能复制一份，不复制每轮 Agent Prompt）：

```markdown
## Why / 功能价值
要解决的用户或研究瓶颈；不做会有什么问题。
## Goal / 可观察结果
成功演示的输入、输出、指标或真实服务行为。
## Scope / 可改范围
允许修改的目录、协议版本、依赖、旧能力保留项。
## Non-goals / 明确不做
列出不可修改的模块、测试器、历史实验和生产状态。
## Dependencies / Gate
依赖哪些 Fxx、哪些已冻结的接口版本。
## Acceptance / 验收命令和质量门槛
至少一个实际场景测试 + 一个负例 + 一次回归 + Benchmark Dev 报告。
## Vibe Coding audit
本文件中的 `Prompt Log` 标识：P-...；完整脱敏 Prompt 原文在本文件。
## Deliverables
PR、代码版本、测试结果、Benchmark 报告、风险与回滚方式。
## Review
Owner、Reviewer、是否通过、待修改项及复验依据。
```

### 3.1 RSI 适配器归属与缺失机制（v1.2 补充整合）

本节依据用户 2026-10-24 后续会话补充整合到 v1.1；未取得独立的 v1.2 下载原件，不将本稿称为其逐字副本。以下是开发目标，当前代码能力须由功能 Owner 在固定 commit 上核验。

| 功能包 | 职责 | 最小新增能力与证据 |
| --- | --- | --- |
| F02 | 统一更新协议与动态匹配 ABI | Diagnosis、CandidatePatch、ValidationReport、PublicationReceipt、RollbackReceipt；diagnose/propose/validate/publish/rollback；结构签名、I/O 契约、语义描述与多阶段匹配接缝 |
| F05 | Motif 本身进化 | 真实反例归因、Positive/Negative 规则修订、必要的条件分裂、参数/历史证据重绑定、新旧分支分别认证、版本发布与后续任务使用 |
| F08 | 使用经验的算法进化 | Matcher 检索/结构评分/绑定的真实代码 patch、独立验证、兼容发布、实际加载及回滚；Miner/Updater 按同协议扩展 |
| F03/F07 | 任务反馈与因果对照 | 区分是否更新、是否采用更新、是否可靠迁移，固定库比较 Matcher，继而比较独立与联合演化 |
| F06 | 产品扩展 | 跨用户授权、共享版本、并发一致性和资源隔离，非当前论文前置 |

CandidatePatch 至少覆盖 `rule_revision`、`motif_split`、`matcher_code_patch`。共享的是版本、证据、独立验证与发布语义，不要求共用修改算法。候选不得修改可信执行准入、权限守卫、独立评测器、冻结 Test 或原始账本。

先 F02，再 F05 最小反例闭环，再 F08 真实代码更新；F03 的环境/计量可同步盘点。F08 可在少量固定 Dev/独立 Selection 上提前验证，不等待 F07 完整主实验。

### 3.2 跨任务动态迁移的可失败验收

本轮必须区分“同一路线换输入”与“不同完整任务共享局部执行结构”。至少覆盖局部结构重合、中间插入无关步骤、输入/依赖变化、执行中出现新反证、无适用 Motif 正确回退。若只做到完整脚本替换输入，应报告为脚本复用，不能声称已证明动态跨任务迁移。

Runtime 不必预知完整工具序列；每次新观察后可重匹配。检索/结构评分只提出候选，独立准入还必须核验当前任务需要该操作的义务或必要性、来源、输入状态、版本、权限和负向条件。证据不足交回 LLM；语义相似、代码相同或历史成功均不单独授权执行。

F03/F07 先固定同一 Motif 库测 Matcher，再做 Motif-only / Matcher-only / Independent / Joint；分别报告可复用机会、候选召回、绑定、准入拒绝、错误执行、实际 Provider 请求、匹配时延和学习/认证/恢复全成本。记录无复用任务和全部失败。

Library Scaling Study 可评估 100/1,000/10,000 的建议规模，须先按可用真实证据校准，区分可执行 Motif、相似干扰项和无复用任务；不能复制条目伪造规模收益。任意开放领域的类比推理或基础模型架构训练不作为当前论文必达目标。附件中的外部论文数值本轮未重新核验，不据此形成已验证结论。

### Board 状态规则

- `Ready`：目标、Scope、依赖、验收已明确；可交给编码 Agent。
- `Doing`：Owner 正在实现/反复 Vibe Coding，不要求对方逐条审 Prompt。
- `Review`：已自测，提交 PR 和证据，请对方做集成/语义/安全审核。
- `Blocked`：依赖缺失或安全问题，写清失败和解除条件。
- `Done`：验收证据 + 非作者批准 + 合并；若目标包括线上发布，还须部署/回滚记录。**实验假设失败且被严格验证，也可以关闭研究探索卡，但不应标记为“性能成功”。**

---

## 4. 共享推进节奏：按里程碑集成，而不是每天打断对方

| Gate                       | A 的交付                                    | B 的交付                                                     | 双方共同判定                                           |
| -------------------------- | ------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------ |
| **G0** 研究对齐            | F00 研究契约                                | F01 仓库/CI                                                  | C1–C3 主张、受保护边界、研究/产品分轨、成本口径        |
| **G1** 协议 + 计量         | F02 统一 Event/Operator/Evidence/RSI Update | F03 AppWorld Native + 账本                                   | 同一 Fixture 可被两端读取；真实模型请求/任务评分可复验 |
| **G2** 首个闭环            | F05 学习/认证/下任务使用                    | F04 AppWorld + 旧场景兼容                                    | 至少一条跨输入执行与失败回退，先证明机制，再测是否省费 |
| **G3** 联合 RSI            | F08 实际 Matcher/Runtime 代码或算法更新     | F07 Frozen/Motif-only/Matcher-only/Independent/Joint 开发集消融 | 联合演化是否优于独立模块，失败、额外计算和回退不能遗漏 |
| **G4** 论文证据            | F08 方法收敛与代码/版本证明                 | F07 外部 Benchmark/冻结测试                                  | 在明确质量约束下证明可归因收益，决定预印本主张与局限   |
| **G5/G6** 产品扩展（并行） | F06 共享库                                  | F09/F10 Web/Desktop/运维                                     | 不替代、不阻塞 G4 论文交付                             |

F08 可以在 F03 的冻结 Dev Fixture 上提前做 Matcher 代码更新，不必等 F07 全部完成；F07 则在获得 F08 候选后完成消融，**避免 F07↔F08 循环依赖**。F04 中 Paper/Data/PPT 的基础回归继续保留，但不要求在首篇论文前完成三场景全量产品验收。

---

## 5. Benchmark-in-the-loop：让评测直接指导 Vibe Coding

**我们当然可以结合 Benchmark 进行优化，而且应该这么做。** 需要隔离的是最终论文报告的数据，不是日常开发反馈。

### 5.1 三套角色分明的数据

| 数据集                   | 是否允许反复看失败             | 用途                                                  | 限制                                             |
| ------------------------ | ------------------------------ | ----------------------------------------------------- | ------------------------------------------------ |
| **Dev/Train**            | **允许**                       | 反复调 Prompt、Motif 抽取、优化器代码、错误恢复与协议 | 每次迭代留记录；不能拿开发集效果冒充泛化         |
| **Validation/Selection** | 允许受控选择，但须记录所有比较 | 选候选版本、质量阈值、上线决策                        | 反复适配后它也可能被过拟合；不能再当最终盲测     |
| **Frozen Test**          | **不允许用于开发反馈**         | 冻结实现后的一次正式论文评价                          | 若开封导致后续方法变更，另定新的独立测试集并披露 |

另外为 RSI 建立**时间顺序在线评测（prequential）**：给定任务序列 `T1,T2,…,Tn`，系统在完成 `Ti` 的评分后，才有权从它的运行轨迹中学习用于 `Ti+1`。每次任务都在**执行前**固定 Motif 和优化器版本，不许回头重新评分已见任务当作未见结果。

### 5.2 Benchmark 选择与最小对照矩阵

**首选 AppWorld**（明确 API+Python，可检验自由代码 Operator 与跨任务复用）。先用官方 Train/Dev 检查重复结构密度与可认证输入依赖，再决定扩大规模；Terminal-Bench 2.0 用于真实终端泛化，ToolSandbox/τ³-Bench 是可选可靠性场景。Paper/Data/PPT 保持真实应用价值，但不是首篇论文唯一核心 Benchmark。**此选型是研究计划，不代表 Adapter 已适配或模型结果已获得。**

| 组别     | 设置                                                         | 主要检验                                                    |
| -------- | ------------------------------------------------------------ | ----------------------------------------------------------- |
| **B0**   | Native Agent（完整 Bash/代码/原生工具）                      | 基础成功率和实际 LLM Work；允许强 Baseline 一次生成完整程序 |
| **B1**   | Native + 合理 Script/Skill/Workflow Cache                    | 简单程序复用是否足够；不可剥夺参数化/验证能力               |
| **B2**   | Frozen Certified Motif + Frozen Matcher                      | 固定结构执行的收益                                          |
| **B3**   | Motif-only RSI（固定 Matcher）                               | 仅持续学习与修订经验是否有效                                |
| **B4**   | Matcher-only RSI（冻结 Motif）                               | 仅修改匹配代码是否有效                                      |
| **B5**   | Independent Module RSI（独立优化并整合）                     | 排除模块分别优化即可得到同样收益                            |
| **B6**   | **GeneLoop Joint Motif–Matcher RSI**                         | 联合代码级演化的独立贡献                                    |
| **补充** | 同一份 Skill：LLM 选择 vs Runtime 绑定执行；可复现 Harness RSI / Skill-DisCo 基线 | 分离技能质量和 Runtime 控制贡献，检查相关工作的真实竞争力   |

**三项核心实验**：①跨任务 Operator 能否优于简单脚本缓存；②固定 Skill 后，Runtime 接管能否减少模型工作；③同样进化预算下 Joint RSI 是否优于 Motif-only、Matcher-only 和 Independent RSI。主报告包含完整费用（LLM/缓存/学习/认证/失败/回退）与成功率。不可把 `verified_skip` 数量直接当成净少请求数。

**阶段化**：G1 在 AppWorld 小型 Dev 上确认工具/代码轨迹可观测与评分可复验；G2 建立真实学习复用闭环；G3/G4 再扩大到在线任务序列和外部冻结测试。任何官方 Test 的泄漏都必须隔离并披露。

### 5.3 每个功能包都附带最小 Benchmark 反馈

每次 Agent 修改完成后记录一张测量卡：

| 指标         | 最小记录口径                                                 |
| ------------ | ------------------------------------------------------------ |
| 成功/质量    | 任务成功、内容/数值/文件质量，失败保持可见                   |
| 真正跳过模型 | `verified_skip` 与真实上游 LLM 请求数分开                    |
| 复用         | 命中、尝试、执行成功、回退、无命中原因分开                   |
| Token/费用   | uncached input、cached input、output；主任务、辅助模型、学习认证、回退与重试分开 |
| 时间         | end-to-end latency、学习时延、匹配开销及可用时的 p95         |
| 净成本       | 对照同质量成本；学习成本摊销不能在首次部署后消失             |
| 可迁移性     | 未见数据/任务族、更换输入、跨用户（有共享授权时）和重启后复验 |

**优化循环**：Dev 轨迹→定位是 Operator/Motif 缺失、Matcher 错误、参数来源问题或语义交接问题→提出 Motif 与/或 Matcher 代码候选→独立验证候选与旧能力→用 Selection 选择版本→发布供后续任务使用。每轮保存**实际代码 Diff、被拒绝候选、运行成本、任务结果和版本关系**，不能只保留成功版本。

**不可作弊边界**：不能改 Benchmark 官方测试、冻结样本、任务要求、合法工具能力或异常处理来人为提高通过率；不能清空历史费用、隐去重试；不得要求 Agent 针对 Test ID、最终答案或隐藏评分器写特例。

---

## 6. Prompt Audit：每一次实际下发给编码 Agent 的 Prompt 都可追溯

### 6.1 记录约定

每个完整功能包可以有多轮 Prompt。**每次实际发送给编码 Agent 的关键 Prompt、Follow-up Prompt、修订 Prompt 逐条记一份完整脱敏原文**，不只记录一个“我让 AI 修复 Bug”的摘要。紧贴这一条记录实际生成的提交/结果和验证。复用先前 Prompt 时也登记调用 ID。

推荐编号 `P-F02-001`、`P-F02-002`。若一个 Agent 子会话自动派生子 Agent，至少记录主控 Prompt、所用代理配置/工具及子任务概要；能导出的子代理 Prompt 另记录 ID。不同模型/版本会产生不同结果，务必注明模型与配置。

**两人同时记日志的冲突控制**：不同 Owner 只在自己的 `Fxx` 条目末尾追加，不覆盖对方条目；合并 PR 前先同步 main，遇到同一文档冲突时保留双方已记录的 Prompt 和索引，不采用“整文件以我为准”。功能日志增长后可将完整历史按 `docs/prompt-audits/Fxx.md` 无损拆分，本文件继续保留统一索引及不可变记录链接；拆分需双方审核，不能省略任何 Prompt。

**隐私处理**：只向公开 Git 提交可以公开的完整 Prompt。绝不提交 API Key、Cookie、学校/用户私有文件原文、真实个人数据、私有服务器地址或支付资料。对于必须脱敏的 Prompt，用 `[REDACTED: 秘密类型]` 明确替代，并保存原文 SHA-256 或私有审计引用（若确有必要），说明这已不是逐字公开复现版。不可用假原文冒充完整日志。

### 6.2 Prompt 索引（随每次下发同步更新）

> v1.1 仅修改**未发送的 Prompt 模板**并新增 P-F03-001 模板；下表为上传文件中的原始占位状态，不表示检查过远端 Issue、真实审计或本轮下发。若任何模板实际上已经发送，必须保留原文并另发新的 Prompt ID。

| Prompt ID | 功能卡 | Owner | 类型              | 基础 Commit | Agent/模型 | Outcome              | 证据 | 审阅 |
| --------- | ------ | ----- | ----------------- | ----------- | ---------- | -------------------- | ---- | ---- |
| P-F00-001 | F00    | A     | 初始设计          | 待填写      | 待填写     | **模板，未下发**     | —    | —    |
| P-F01-001 | F01    | B     | 仓库审计          | 待填写      | 待填写     | **模板，未下发**     | —    | —    |
| P-F02-001 | F02    | A     | 核心 ABI 设计     | 待填写      | 待填写     | **模板，未下发**     | —    | —    |
| P-F03-001 | F03    | B     | AppWorld 评测设计 | 待填写      | 待填写     | **新增模板，未下发** | —    | —    |

### 6.3 每条 Prompt 的追加式审计模板（复制，不覆盖旧版）

```markdown
### [P-Fxx-00n] YYYY-MM-DD HH:mm｜功能 Fxx｜初始/修订/Debug/Benchmark
- 发起人：A / B
- Issue：链接（未创建时保留 Fxx）
- 编码 Agent / 模型 / 模式：
- 代码起点：分支 / commit SHA / 依赖 Protocol 版本
- 目标：一句话说明为什么要下发这一轮 Prompt
- 允许改动：具体目录/文件
- 禁止改动：受保护契约、生产配置、测试器、历史证据等
- 预先冻结的 Benchmark：数据 split、case IDs、基线版本、模型与工具配置
- 是否包含脱敏字段：否 / 是（说明类型）

**实际发送的 Prompt 原文（完整，必要时脱敏）**
> 在这里逐字粘贴下发内容，包括修改后的完整 Follow-up Prompt。不要只写一句概括。

**Agent 返回摘要和交付**
- 修改文件、Commit/PR、关键设计选择
- 执行命令和结果（通过 / 失败 / 未执行）
- Benchmark Dev 指标（与哪一固定 baseline 比较）：
- 是否更改研究假设或协议：否 / 是（对应 Decision ID）
- 剩余风险、未证实主张、下一步

**人的判断与处理**
- Owner 判定：接受 / 打回 / 继续下一轮
- Reviewer 判定（仅 ABI/功能 Gate/上线必填）：批准 / 修改 / 未审
- 打回原因：具体错误与复验命令
- 下一 Prompt ID：P-Fxx-00(n+1) / 无
```

### 6.4 关键决策日志（必要时建立）

| Decision ID               | 日期       | 争议/问题                      | 备选方案                                        | 决定和原因                                                   | 影响的 Fxx                      | 复核/回滚条件                                                |
| ------------------------- | ---------- | ------------------------------ | ----------------------------------------------- | ------------------------------------------------------------ | ------------------------------- | ------------------------------------------------------------ |
| D-0001                    | 2026-10-23 | Vibe Coding 与任务管理如何结合 | 微任务 Issues / 功能包 Issues                   | 功能包 Issue + 本文件逐次 Prompt + PR 证据                   | 全部                            | 当团队规模变化时重评                                         |
| D-0002                    | 2026-10-23 | 能否用 Benchmark 调算法        | 禁止反馈 / 开发集驱动                           | 允许 Dev 迭代；Validation 受控选型；Frozen Test 隔离         | F03/F07/F08/F11                 | 发现泄漏则重置独立盲测                                       |
| D-0003（**待 A/B 评审**） | 2026-10-24 | F00 创新点与论文/产品优先级    | 优化器完整递归必需 / Motif–Matcher 联合演化优先 | **建议** C1/C2/C3；AppWorld 主 Bench；代码级 Matcher 更新是 C1 最小证据；多代 optimizer 与大规模产品非首篇硬门槛 | F00/F02/F03/F04/F05/F07/F08/F11 | 若 G1 不具备真实代码轨迹复用条件或 G3 联合更新无额外收益，则调整范围 |

---

## 7. 首批可复制的 Vibe Coding Prompt（**模板，未实际发送**）

> 使用方式：先把模板复制到 §6 中新的 `P-...` 记录，再按当次 commit 和需求修改并记录，然后发送给编码 Agent。**不要直接把模板在审计索引中标为已执行。**

### P-F00-001 模板｜A：研究契约，不动生产代码

```text
你负责 GeneLoop F00。先阅读 docs/research-contract.md 的 G0 评审稿、README.md、AGENTS.md、docs/interfaces.md 与已有实验。不得将待验证贡献写成现有事实。

目标：将 F00 统一为 AI Agent 方法研究契约，以 C1 Full-Stack Runtime RSI（重点为 Motif 与 Matcher 算法/代码联合演化）、C2 Learned Operator Abstraction（MCP/Bash/Python）、C3 Efficiency-Oriented Evolution（减少真实 LLM Work）为候选贡献。相近研究中 ModularRSI 已涉及 Harness 代码修改，Skill-DisCo/NSI 已包含参数化技能与分支；须说明我们的待验证增量，不以“他们只改 Prompt”或“他们无 Runtime”作为差异。

交付：只调整 docs/research-contract.md（如已满足则只列审阅意见），短文明确 3 个假设、最近工作区别、AppWorld→Terminal-Bench 2.0 的优先顺序、最小 Frozen/Motif-only/Matcher-only/Independent/Joint 基线和同质量 LLM Work 计量。

F00 只冻结研究问题与评估逻辑，不冻结匹配算法；不要求现在完成实验、θ0→θ1→θ2、全模块自改、多用户产品，也不改生产代码。将未决问题与相应 F02/F03 任务列出，留给 Reviewer 做 G0 决定。
```

### P-F01-001 模板｜B：仓库与 CI 基线，不大规模改算法

```text
你负责 GeneLoop 功能包 F01。目标是让两个人可以安全地通过 Vibe Coding 持续开发和复验，不是重做算法。

请盘点 main 当前的 README.md、AGENTS.md、docs/collaboration.md、config/harless-scenes.json、motif-libraries/、.github/workflows/test.yml、package.json、主要测试与启动命令。区分：源码已存在、测试已证实、生产实际运行、尚在私有实验、历史归档。

优先交付最小改动：
1. 更新 README 首页（C1/C2/C3 研究主张、功能现状、快速启动、AppWorld/Benchmark 链接）；把冗长历史移动到文档索引，保留来源，不能直接丢弃。
2. 将 AGENTS.md 收敛为长期稳定的编码边界与准确入口；删减/移动过时的时间性记录，不失去权限、预算、隐私和部署守卫。
3. 将旧多人按场景协作规范替换为 A/B 两人、功能包 Owner、交叉 Gate Review、Prompt Audit 和 PR 规范。
4. 检查已有 Ubuntu/Windows CI，先分出快速离线 Gate 与可选完整/真实验收。禁止普通 PR 隐式调用付费模型。
5. 给后续大规模重构提供模块地图与逐步迁移方案，但本次不要移动大量核心文件。

验收：运行 npm test、npm run smoke、npm run motif:check，记录实际命令/机器/结果。测试因环境缺失而未执行要说明，不准删测试掩盖失败。严禁读取/提交凭证、私有用户任务和生产账本。给出 Diff、测试、兼容性、回滚和剩余问题。
```

### P-F02-001 模板｜A：统一协议与 Runtime

```text
功能包 F02：在已有 TypeScript 在线 Runtime + Python 离线认证基础上建立 RSI Protocol v1，不另造 Agent Loop、不大规模删除旧实现。

先核查 docs/research-contract.md、docs/interfaces.md、src/motif_core/online_skill_runtime.mjs、src/motif_core/offline/、src/adapters/script_execution_frontier.ts、src/adapters/artifact_motif_compiler.py 以及实际 Schema 和测试。交付一个短 RFC、版本化 Execution Event / Operator+Motif / Evidence / Runtime Decision / RSI Update 合约，以及 2–3 个真实 Tool、Bash、Python 的跨语言 Fixtures。

至少将 Motif 和 Matcher 定义为可独立版本化并参与 RSI 的对象，明确真实匹配代码/规则版本、修改范围、审查与回滚接口；为未来 Miner/Updater/Context/Cost Policy 的更新保留兼容扩展位。不要求 F02 直接实现代码自改，那是 F08 的算法实验。分清语义相似匹配与直接执行资格；模型候选不能跳过证据/权限/来源/版本校验。

验收：旧库回归、Fixtures Node/Python 一致、一条新输入的认证执行、一个来源/版本负例和一个工具错误负例，所有真实调用有回执。给 B 明确的 AppWorld Adapter 与计量所需 ABI；不凭内部跳过标记宣称端到端降本。
```

### P-F03-001 新增模板｜B：AppWorld Benchmark Runner（未下发）

```text
功能包 F03：优先让 AppWorld 原生 Agent 跑通一小批官方 Train/Dev 任务并保留真实轨迹、评分、模型请求及缓存/输出 Token 计量。先调研并固定官方任务定义、环境与评分入口；不要碰官方 Test，也不要为了让 GeneLoop 胜出削弱 Native 的 Bash/代码能力。

交付最小 Runner：任务/环境快照、固定模型与工具参数、成功与失败的可复查结果、Provider 请求账本、基线复现命令；在 Dev 上评估跨任务 API/Python 可复用片段是否存在，不能假定所有任务天然可迁移。先实现 Native 与合理 Script/Skill Cache，再以 F02 ABI 接入 Frozen Motif，后续支持 Motif-only/Matcher-only/Independent/Joint 消融。

外部 Terminal-Bench 2.0 先给可行性/成本说明，不要求 F03 全量适配。输出准备投入、未验证假设、全部失败和总花费；不宣称未运行过的结果。
```

### P-F05-001 模板｜反例驱动的规则修订与 Motif 分裂（未下发）

```text
功能包 F05。先核验固定 commit 的既有 Negative/Description/Conditional Learning 与 Experience Registry；复用现有能力，不将局部实现称为通用闭环。
依据 F02 冻结协议和 F03 Dev/Selection，从一个真实反例完成诊断、rule_revision、必要的 motif_split、新旧分支独立认证、证据适用范围重绑定、不可变版本发布和后续任务实际加载。条件不明或来源/权限/版本失效须拒绝/交接。
不修改 Matcher 代码、独立评测器、冻结 Test、权限或账本。记录实际 Prompt、候选/拒绝、diff、配置、失败、质量及学习/认证/恢复成本；先完成最小真实闭环，再扩大。提交 PR 交另一位合作者审核。
```

### P-F08-001 模板｜Matcher 代码更新与动态迁移（未下发）

```text
功能包 F08。使用 F02 协议、F05 候选与 F03 固定 Dev/独立 Selection。先固定同一 Motif 库，诊断漏召回/结构评分/绑定问题，提出真实 matcher_code_patch，独立回归、版本兼容发布、后续任务加载及回滚；不能只改描述或阈值冒充代码 RSI。
验证不同完整任务的局部复用、中间无关步骤、新反证失效、无适用能力回退及语义近似却不应执行的负例。候选匹配不得授权执行；独立准入核验当前任务操作义务、来源/状态/版本/权限。
分别记录所有候选、拒绝、质量、真实请求、冷热 Token 与更新/认证/匹配/恢复成本，再比较 Motif-only、Matcher-only、Independent、Joint。Scaling 规模先校准，不靠复制条目。不可修改独立评测器、冻结 Test、权限或账本；提交 PR 交叉审核。
```

### Prompt 改进的推荐句式

当 Bench 失败时，**优先给 Agent 一个可复现反例，而不是直接要求“提升准确率、再试一次”**：

```text
功能包 Fxx，追加 Prompt P-Fxx-00n。固定起点为 commit <SHA>，Protocol 为 <VERSION>。
开发集 case <ID> 的失败：<最小复现命令>；期望 <...>，观察到 <...>。
已排除因素：<...>；待验证假设：<...>。本轮只允许修改 <文件/组件>，不得改评分脚本、冻结数据、公共接口或放宽拒绝守卫。
请先写出失败路径、关键变量和两个候选修法的影响；选择最小可逆方案，增补负例测试，运行同一 Dev case、相关回归和对应 Baseline。输出请求数、实际 verified skip、成本、质量变化，以及仍失败的 case。不能只返回“优化成功”。
```

---

## 8. 每次集成/论文主张的人工审核清单

- [ ] 实际代码 Diff 与 Issue Scope 一致，不存在越权改其他功能包。
- [ ] 完整关键 Prompt 已记录（含被打回的 Prompt），公开版本无凭证与私有内容。
- [ ] 使用已冻结的协议与 Benchmark 配置，非同质对照明确标注。
- [ ] 单元/集成测试、实际负例、恢复/撤销测试的证据真实存在。
- [ ] 质量与总成本并列，完整计入学习认证、错误重试、辅助模型与回退。
- [ ] 显示真实上游模型跳过与未跳过的具体原因；Matcher 代码更新要有 Diff、版本、对照与独立回归。
- [ ] 主要 Benchmark 结论不来自已经反复调过的最终测试集。
- [ ] Reviewer 根据 PR/证据批准或打回，附可复验理由。
- [ ] 生产部署另有灰度与回滚依据；未经许可不直接触碰正式服务。

---

## 9. 共享会议与每周同步的极简格式

每次同步不要逐行 review 代码，而只写一个短段落：

`本期 Owner A：Fxx，完成……，失败……，需要 B 决策的接口只有……；Owner B：Fyy，Benchmark ……，主阻塞……；共同确认的 Decision：D-...；下一期目标是达到 Gate G...。`

只对以下事项开联合审查：研究定义变化、协议破坏、成本/质量主张变化、生产安全边界、正式对外发布。其余由对应 Owner 使用自己的 Vibe Coding 会话闭环开发。

## 10. 当前起点 / 下一个动作

- [ ] A/B 审核 `docs/research-contract.md` 的 C1/C2/C3，并审议本文件 **D-0003（待评审）**；先更新真实 Issue 描述，再改变 Board 状态。
- [ ] B 将本更新稿拟提交到 `docs/ROADMAP_AND_PROMPT_AUDIT.md`；如仓库已有更晚记录，应按 Diff 合并，**不得覆盖真实 Prompt 审计历史、Issue/PR 链接或新的状态**。
- [ ] B 启动 F03：核查 AppWorld 官方环境/评测/轨迹并跑一个小型 Dev Native；A 完成 F02 RFC/Fixture，重点保留 Matcher 代码可版本化接口。
- [ ] G1 后优先打通真实代码轨迹 Operator 和 Motif→Matcher 联合更新（F05/F08），B 持续建设 F07 消融；Terminal-Bench 作为后续外部验证。
- [ ] 准备 F11 预印本时，以实际 C1–C3 证据决定主张范围；共享存储、双端与规模化可继续并行，但不阻塞研究稿件。

**维护原则**：功能状态与分派，以 GitHub Board 为准；技术决策与完整 Prompt 审计，以本文件为准；运行结果以真实实验报告/账本为准；实现以 Git Commit/PR 为准。四者通过 Fxx、P-Fxx-00n、Commit SHA 相互链接，避免出现四份互相矛盾的“真相”。


## 11. 2026-10-24 发布批次与当前交接

A = @jingyio，B = @peilin6；按功能分工、交叉审核。Issue 提出者与负责人可以不同。

| 功能 | 实际 Issue | Owner | Reviewer | 发布时核对状态 |
| --- | --- | --- | --- | --- |
| F00 | [#108](https://github.com/jingyio/GeneLoop/issues/108) | @jingyio（正文约定） | @peilin6，待审核 | Open；契约提交 PR 不等于 G0 通过 |
| F01 | [#109](https://github.com/jingyio/GeneLoop/issues/109) | @peilin6，已分配 | @jingyio | Open，已加入 Board |
| F02 | [#110](https://github.com/jingyio/GeneLoop/issues/110) | @jingyio，已分配 | @peilin6 | Open，已加入 Board；F00 依赖待解除 |
| F03 | [#111](https://github.com/jingyio/GeneLoop/issues/111) | @peilin6，已分配 | @jingyio | Open，已加入 Board；依赖 F00/F01，Frozen 接入还需 F02 ABI |
| F05 | [#112](https://github.com/jingyio/GeneLoop/issues/112) | @jingyio，已分配 | @peilin6 | Open，已加入 Board；依赖 F02/F03 |
| F08 | [#113](https://github.com/jingyio/GeneLoop/issues/113) | @jingyio，已分配 | @peilin6 | Open，已加入 Board；依赖 F02/F05 与 F03 Dev/Selection |

现有 [GeneLoop Development](https://github.com/users/jingyio/projects/1) 为 Todo / In Progress / Done。发布快照六张卡均为未开始，本次复用已有 Board，未改成六列。§3 的六列及 Ready/Backlog 是配置建议，不是已生效状态；后续以 Board 为准，本表保留发布快照。

本批在 F01–F03 后，根据用户 v1.2 与动态迁移补充，追加 F05/F08；F04/F06/F07/F09/F10/F11 暂留 Roadmap、未创建。先 F00 审核/F01 基线，再 F02、F05、F08；F03 可同步进行不受依赖影响的环境/计量盘点。每人最多一个 Doing，认领多项不代表同时开工。

- 代码起点：远端 main `ec72908755ea6df1771ec962b40e3b27be381ebb`；本轮不包含本机旧检出的未提交代码。
- 已完成：候选契约、v1.1 与本轮 v1.2/动态迁移补充的整合 Roadmap、本批 Issue；发布/审计边界见 [F00 审计](prompt-audits/F00.md)。
- 已验证：文档/引用检查、Issue/Assignee/Project 网页回读；未进行算法、Benchmark 或付费模型验收。
- 未完成：另一位合作者的 G0 审核、PR 合并、各功能实现；未重新核验附件中的相关论文数字，不据此声称成果。
- 接手下一步：①审核契约和 D-0003；②B 推进 F01、A 准备 F02 RFC；③F03 固定环境/计量后，以真实反例和固定库对照推进 F05/F08。
- 权限与费用：用户授权本批 Issue/PR 发布；本次无付费模型或生产发布，新增实验费用 0；后续沿用实际授权与原累计账本。
- 回退：本次仅文档分支，未合并可修订/关闭 PR；未更改 main 或正式服务。
