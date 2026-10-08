# 上下文插件与 SSS 创新边界核查

> 2026-09-25。只读核对公开仓库固定提交和 SSS 本地源码；未替第三方复跑付费实验。这里的“未见”只针对所查版本，不代表整个开源生态不存在。

## 结论

“压缩 Agent 历史”“可恢复的工具结果裁剪”“按反馈学习保留哪些上下文”“跨会话经验进化”“执行 DAG”都已有开源先例。SSS 不能把其中任何一项单独作为首创。更准确的研究主张是：**从历史工具轨迹编译可执行 Motif，用证据和参数依赖把步骤划为结构性、半结构性和开放语义操作；运行时直接执行第一类、将第二类交给有界决策器、只让第三类使用开放式生成模型，并依据后续任务结果修订这条边界**。Jev 是半结构决策器的一种实现，不是 SSS 的必要条件。它与上下文压缩可以叠加；收益必须包括报告质量、人工修正、真实总费用和进化成本。

当前 SSS 尚未完成上述组合。初版核查时，`dsh_trajectory.py` 与 `motif_miner.py` 只产生连续片段候选；此后已加入显式参数来源认证、只读 Motif 图执行、缺参恢复与失败守卫的候选／复核流程。它们尚未统一接管报告规划、证据选择、综合及写操作；失败反馈也未证明能在后续不同研究任务上改善合格交付与总成本。[当前源码状态](SSS核心与Harness集成.md)、[进化记录](EvoGraph启发的MotifSkill进化.md)、[盲评协议](同题调研盲评与总成本协议.md)。

## 三类操作与模型边界

这一划分在 MotifAgent 的结构—语义分离基础上，明确了[用户原有的半结构定义](/Users/apple/Desktop/ATC-MotifAgent/camera-ready/Jev帖子)：

| 操作 | 运行条件 | 执行者与模型调用 | 科研工作流示例 |
|---|---|---|---|
| **结构性** | 节点、参数来源、依赖和守卫都有当前任务证据支持；失败可检测。 | SSS 运行时直接调用工具或推进状态；**不发生成模型请求**。 | 按来源哈希识别未变文献、复用已核查的出处定位、只使受影响的问题失效。 |
| **半结构性** | 工作流和合法候选已确定，只剩一个或少数局部语义选择；允许“未知/升级”。 | Jev、Laya、受限生成模型或人工完成有界判断；SSS 校验返回候选、证据签名和权限后重入。 | 对几段已检索证据选择哪段与必答点相关，或判断两段是否冲突。 |
| **开放语义** | 当前没有可信结构或候选空间，需新查询、解释、规划或撰写。 | DeepSeek Harness 及其他生成式模型处理；产物仍经来源和质量检查。 | 发现资料缺口后设计新检索方向、综合多篇论文写正文。 |

这三类不是按工具名称永久划定。例如同一 `read` 工具，可由已验证的参数链直接调用，也可因文件名歧义先要有界判断；新任务完全没有适用 Motif 时要重新规划。经验积累可使“开放语义→半结构→结构”；来源漂移、守卫失败和留出质量下降也必须允许反向退级。分类标签本身不产生收益；只有实际少发了模型请求、减少重复执行且交付仍合格，才构成方法结果。

**Jev 接口的亮点在控制边界。** 请求应带候选 ID、局部证据、输入版本、可拒答选项、预算与回退条件；响应仅提供 `Choice`／`Score`／`Noul` 一类有界结果，运行时验证后才授权后续步骤。Jev 的[官方接口](https://docs.typesafe.ai/models)支持在同一 `state` 下评估多个问题，但 Jev 判断不是事实证明，也不能替代写入确认或引文核验。已有 [JevGraph](https://github.com/danielgshea/jev-graph) 和 [dsh-jev](https://github.com/buberlo/dsh-jev) 表明“接 Jev”以及“图＋Jev”各自已有先例。SSS 需要证明**轨迹编译出的执行结构控制何时完全跳过模型、何时仅调用 Jev，以及何时回退开放推理**，并证明这比相同模型/工具条件下的 Jev Agent 与固定图更有用。[现有 Jev 对照设计](Jev相近项目调研与对照设计.md)。

## 逐项对照

| 项目 | 已有机制 | 与 SSS 的重叠 | 源码核查边界 |
|---|---|---|---|
| [DeepSeek Harness 原生压缩](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-basic/README.md) | 上下文压力下以额外模型调用总结旧会话；可在触发后裁剪大工具结果。 | 通用历史管理与上下文成本基线。 | 不从任务轨迹编译 Motif。 |
| [dsh-context-compression-selector，`149f523`](https://github.com/WilliamShi666/dsh-context-compression-selector/tree/149f5236ced03eb7e25e3c340dfa908df73bdce0) | 首次展示前压缩工具结果、清理旧结果、按缓存与 token 成本选策略；[Adaptive 是成本不等式](https://github.com/WilliamShi666/dsh-context-compression-selector/blob/149f5236ced03eb7e25e3c340dfa908df73bdce0/packages/runtime/src/adaptive-cost.ts#L124-L185)。 | 强上下文成本对照。 | 没有跨任务学习；压缩器按[工具和内容规则](https://github.com/WilliamShi666/dsh-context-compression-selector/blob/149f5236ced03eb7e25e3c340dfa908df73bdce0/packages/runtime/src/reducers.ts#L38-L63)选取。 |
| [dsh-context-gc，`5c2d527`](https://github.com/Hexc01/dsh-context-gc/tree/5c2d52793f7d18cf87afd5001dac241968e32a94) | 按日志证据识别重复读文件、搜索及冗长测试输出；原文可找回，[默认仅预览](https://github.com/Hexc01/dsh-context-gc/blob/5c2d52793f7d18cf87afd5001dac241968e32a94/README.md#L3-L20)。 | 冗余工具结果清理对照。 | [计划器](https://github.com/Hexc01/dsh-context-gc/blob/5c2d52793f7d18cf87afd5001dac241968e32a94/src/plan.ts#L24-L103)是确定性规则，不更新工作流。 |
| [Distil，`10ff2ef`](https://github.com/dshakes/distil/tree/10ff2efa442121bbe133a06fdd6241e7745492ff) | 可恢复压缩、按历史展开请求学习保留策略、决策等价与任务级对照。 | **最强上下文自改进基线**；质量门与恢复设计值得认真对照。 | 学习的是保留哪些内容，不是 Motif 节点/参数/守卫；“按整项任务成败自动学习”模块存在，但实际运行链尚未接通。 |
| [dsh-rule-evolve，`d95d670`](https://github.com/zoahdev/dsh-rule-evolve/tree/d95d6705f62857edb68ce4dce364d8d1a77f9f54) | 从失败经验生成跨会话 `AGENTS.md` 文本规则，记录版本与使用次数。 | 经验进化基线。 | [插件验证路径](https://github.com/zoahdev/dsh-rule-evolve/blob/d95d6705f62857edb68ce4dce364d8d1a77f9f54/plugin/lib/index.js#L130-L230)用一个检查命令判整库通过，使用计数需显式记录；不是逐条规则的后续任务收益，也非可执行 Motif。 |
| [dsh-engram，`edfd704`](https://github.com/kenz1117/dsh-engram/tree/edfd704cbeaff4190f1f9abbef9472a9374f7bfb) | 跨会话记忆，辅助模型将同主题记录蒸馏为文本 fact/skill，并按报告的成功或失败调整召回。 | 更接近跨会话反馈学习。 | [蒸馏产物](https://github.com/kenz1117/dsh-engram/blob/edfd704cbeaff4190f1f9abbef9472a9374f7bfb/src/flywheel/distill.ts#L61-L130)仍是记忆/文本 skill；所查源码未显示轨迹到可执行参数 DAG。 |
| [DSH-DAG，`e53e235`](https://github.com/HEO-Club/DSH-DAG/tree/e53e235a9d9e3ba2ee2309b63bba1217d80e8c6b) | 模型提交 JSON 任务图，运行时校验依赖并调度子 Agent。 | 图执行不是 SSS 独有。 | [图由当前模型提交](https://github.com/HEO-Club/DSH-DAG/blob/e53e235a9d9e3ba2ee2309b63bba1217d80e8c6b/README.md)，不是从历史工具轨迹挖掘并验证的 Motif。 |

## Distil：确实有学习，但学习对象不是执行流程

1. 它不是“大模型摘要”。其压缩核心包含程序化裁剪、可恢复引用、缓存约束与反馈学习。[`learn.py`](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/learn.py#L78-L150) 汇总内容类型与长度区间的压缩和找回事件；同一类内容反复被找回后，后续可改为原样保留。查询相关性模型也有留出集门槛后才启用的路径：[`query_flywheel.py`](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/query_flywheel.py#L194-L257)、[`query_train.py`](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/query_train.py#L100-L146)。这已经覆盖“根据使用反馈优化上下文保留”，不能称 SSS 独有。
2. 它定义了按成对任务成败调整保留策略的 [`OutcomeStats`](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/compress/guideline.py#L35-L129)，但仓库的[自检源码](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/doctor.py#L696-L717)明确报告 `record_trajectory_outcome` 没有实际调用者；`certify-trajectories` 是读取用户提供的成对结果并出证书，不会自动把任务结果送进运行时学习。因此，目前可确认的在线学习主要来自找回行为和弱标签，不能说已形成“真实任务成败→运行策略持续改进”的完整闭环。
3. Distil 所称的 `trajectory` 是模型上下文块序列，不是工具执行图；找回操作按 handle 取回原始文本，不会按来源变化自动重验任务依赖。[trajectory 数据结构](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/distil/trajectory.py#L1-L133)。这与 SSS 拟做的可执行 Motif 属于不同控制层，可做组合实验。
4. 仓库提交了 SWE-bench Verified 500 题结果目录，报告中压缩组 210/500、全上下文 196/500；其论文描述为自建 30 步 ReAct Agent 配合官方判分，尚非本次独立复跑。另有 200 题 DeepSeek 结果目录，最终配置为 111/200、全上下文 120/200，先前配置出现大量运行错误。它们提醒我们：迁移到 DeepSeek 不能预设保真或收益。仓库的离线确定性门、真实模型测试、任务级结果需要分开引用；这些数字也不能迁移为 SSS 的预计成绩。[论文与方法](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/docs/PAPER.md)、[500 题结果目录](https://github.com/dshakes/distil/tree/10ff2efa442121bbe133a06fdd6241e7745492ff/docs/paper/results/swe_e2e_longhorizon/reports)、[DeepSeek 结果目录](https://github.com/dshakes/distil/tree/10ff2efa442121bbe133a06fdd6241e7745492ff/docs/paper/results/swe_e2e_longhorizon_deepseek/scores)。

## 值得借鉴的工程做法

| 优先级 | 来源 | 在 SSS 中的具体落点 |
|---|---|---|
| 高 | Distil 的[成对质量门和任务级验收](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/docs/PAPER.md#L214-L229) | 每项 Motif 修订同时跑固定版与候选版，分别记录最终报告合格、错误引用、人工修订、真实成本；提案、验证、启用和后续使用分开记。Distil 的“下一步决策相同”只适合检验上下文裁剪保真；SSS 可能有意改变执行路径，应以最终交付与守卫不变量验收。 |
| 高 | Distil 的[原文可恢复引用](https://github.com/dshakes/distil/blob/10ff2efa442121bbe133a06fdd6241e7745492ff/docs/PAPER.md#L218-L225)与 context-gc 的[可回放裁剪](https://github.com/Hexc01/dsh-context-gc/blob/5c2d52793f7d18cf87afd5001dac241968e32a94/README.md#L3-L20) | Motif 状态只给语义端口必要的证据片段；运行记录保留原文哈希、来源位置和找回入口。若证据无法找回或签名不符，停止结构复用并重验，不能让摘要代替引文。 |
| 高 | selector 的[首次展示前压缩与缓存成本判断](https://github.com/WilliamShi666/dsh-context-compression-selector/blob/149f5236ced03eb7e25e3c340dfa908df73bdce0/packages/runtime/src/adaptive-cost.ts#L124-L185) | 在 DSH 适配器构造 handoff 时就控制片段大小；同时统计缓存命中/失效、额外摘要调用和总费用。只减可见 token 可能破坏缓存，不能直接算作省钱。 |
| 中 | rule-evolve 的[来源、版本、使用次数与退役记录](https://github.com/zoahdev/dsh-rule-evolve/blob/d95d6705f62857edb68ce4dce364d8d1a77f9f54/README.md)；engram 的[记忆替代链](https://github.com/kenz1117/dsh-engram/blob/edfd704cbeaff4190f1f9abbef9472a9374f7bfb/src/flywheel/distill.ts#L61-L130) | 为每个 Motif 版本记来源轨迹、结构差异、验证集、实际命中、失败和回退。启用门要逐版本、逐守卫、跨不同任务验收；一次整库检查成功或“被调用次数增加”不足以证明收益。 |
| 中 | DSH-DAG 的[图校验、节点状态和有界重试](https://github.com/HEO-Club/DSH-DAG/blob/e53e235a9d9e3ba2ee2309b63bba1217d80e8c6b/README.md) | Motif 编译产物入库前校验环、缺参数、未声明依赖和写入效果；执行时显式记录阻塞、失败、重入。图来源仍须是审核过的历史轨迹，不以模型临时写出的 JSON 图替代。 |

先落实前三项作为**SSS 的评测与恢复基础设施**，再扩大 Motif 的自动进化范围。它们本身不构成 SSS 的结构方法贡献，但能避免质量下降、证据丢失与成本错算。

## 建议的可证伪对照

第一组固定同一 DeepSeek 模型、资料快照、工具权限与预算：原生 DSH、DSH＋上下文插件、固定 Motif＋DSH、进化 Motif＋DSH；若可接入，再测 Motif＋上下文插件，判断两者是否正交。`Distil` 的接入若只能走代理，应先用无模型回放核对请求/恢复语义，不能把未接通的配置算一个实验组。半结构决策另做相同 Motif 下的“受限 DeepSeek／Jev／Laya／无决策器”对照，记录低置信升级和错误自动接受。代码迁移题另用原仓库测试与人工复核，研究题按[盲评与总成本协议](同题调研盲评与总成本协议.md)。

进化提案只用训练任务；冻结的**不同**留出任务评价后续实际使用。主指标是合格交付率、每份合格交付总费用、人工修正分钟与端到端时间；同时列出按三类操作分解的实际生成模型请求数、Jev 调用数、结构执行步骤、进化训练与验证、失败回退和压缩恢复成本。对未合格交付不报告“省钱”。最关键的消融是固定结构与进化结构、仅缩上下文与真实跳过调用、用生成模型处理半结构缺口与用 Jev 处理同一缺口。
