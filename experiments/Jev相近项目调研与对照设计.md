# Jev 相近项目调研与 SSS 对照设计

> 2026-09-24。公开资料调研与下一轮实验建议，不是 SSS 的 Jev 实测结果。此处的 Jev 指 TypeSafe 的 System One 决策模型；开源 Jev 类模型另列。

## 一、调研口径

在 GitHub 检索 `Jev`、`System One`、`agent`、`workflow`、`graph`、`coding`、`research`、`document`、`office`，优先阅读近期原始仓库的 README、关键源码、测试和评测记录。区分真实 TypeSafe API 调用、可运行代码、模拟调用、产品自述和独立实测。本次没有克隆或运行第三方项目，没有调用付费模型；下述数值均为仓库作者报告，需复现。GitHub 项目在快速更新，后续对照须固定提交 SHA。

SSS 的目标见[场景与成本目标补充](../source/场景与成本目标补充.md)和[结构—语义分离实施依据](结构语义分离实施依据.md)：代码迁移、范围明确的 deep research 优先；运行时持有节点依赖、参数流、证据守卫和回退。Jev 应处理有界语义判断，不能把图简化成给模型看的提示。

## 二、最值得跟踪的相近项目

| 项目 | 已核查的机制 | 当前证据与限制 | 对 SSS 的价值 |
| --- | --- | --- | --- |
| [stanley-code](https://github.com/devagrawal09/stanley-code) | 确定性条件先筛工作流，再由 Jev 选择；代码读取 diff/日志、按块判断相关性或风险，记录预算与证据。 | 主要是有界代码检查；代码生成交给 Pi Agent。没有执行型迁移图。 | 借鉴工作流注册、局部证据、预算与 `notChecked` 报告；作为代码检查局部基线。 |
| [CasaJev](https://github.com/8endit/CasaJev) | Jev 选择工具，保存已验证工具及历史数据流图；支持 `jev_only` 与图开关。 | [源码](https://github.com/8endit/CasaJev/blob/main/casajev/workflows.py)将图作为路由提示；类型可连接边不等于语义可执行边。[六个合成任务对照](https://github.com/8endit/CasaJev/blob/main/VERGLEICH.md)未证明图开关有收益。 | 最接近“Jev Agent + 图提示”基线；SSS 必须展示图真实控制依赖、参数和执行。 |
| [PiJev](https://github.com/tonyzdev/pijev) | Jev 选 skill、重排文件、归类工具失败；生成模型写代码。 | 作者在 20 个 django、13 个新仓库任务的成对运行中报告工具调用减少 16–25%，完成率 django 15/20→14/20、新仓库 4/13→4/13；Jev 增加费用，部分耗时上升。样本不足以判断完成率差异。 | 代码 Agent + Jev 强基线；检索更快未必让迁移更正确或更便宜。 |
| [jev-harness](https://github.com/TypeSafeAI/jev-harness) | 校验提案、四个 Jev 问题、确定性判决、绑定证据收据。 | 独立社区仓库，不是 TypeSafe 官方运行时；不应用补丁。25 项离线 `+Jev` 数字使用模拟回答，不能视为模型成绩。 | 借鉴变更前的任务匹配、引文/代码证据、无关改动与澄清守卫。 |
| [JevGraph](https://github.com/danielgshea/jev-graph) | LangGraph 控制路由；Jev 做请求分类、工具授权、检索评分和回答评估；生成模型负责开放式回答。 | 有真实 API 调用代码，但仓库未给出与传统 Agent 的端到端对照；图节点偏通用路由，未做任务级证据参数流。 | 直接说明“图 + Jev”已经有人做；SSS 的区别必须落在可验证的结构执行及真实任务增益。 |
| [jev-research-pipeline](https://github.com/shimo4228/jev-research-pipeline) | Python 固定研究监测循环，Jev 筛来源、原句和草稿，Qwen 写段落，保留预算与人工反馈。 | [pilot 记录](https://github.com/shimo4228/jev-research-pipeline/blob/main/docs/pilot-log.md)：作者自报 11 次个人运行，只有 2 次写入真实 vault；一次四主题运行 $0.297、601 秒，独立评审 1/3 篇可发表，仍有曲解来源问题。同一批 20 对来源与问题，批量和单项路由仅 11/20 一致，因此作者关闭跨主体批处理。 | 范围明确研究场景的强 Jev 基线；SSS 需解决必答点覆盖、逐句证据蕴含和失败时定界补证，并验证批处理是否改变判断。 |
| [PagePilot](https://github.com/thevibeworks/pagepilot) | Jev 对网页块做选择，程序形成可复用阅读规格；守卫检查覆盖与泄漏，必要时交给 LLM。 | 作者报告 3 个站点成功、3 个回退；仍为 alpha，扩展端到端浏览尚未充分验证。 | 借鉴结构抽取及回退；可比较跨网站研究时重复读取的成本。 |
| [jev-eval-agent](https://github.com/vinilana/jev-eval-agent) | 模拟日历、邮件、机票、报销等办公工具，对照传统 Agent 与 Jev 工具选择。 | 100 工具/6 个合成任务；部分对照的 reasoning 配置不同，模拟完成不等于真实办公任务。 | 借用工具混淆与错误工具指标，不能直接采信它的性能排序。 |
| [jev-document-classification](https://github.com/Charlyhno-eng/jev-document-classification) | 本地抽取文档、短文本批处理、Jev 分类、低置信人工复核、审计与撤销。 | 有实现和测试，未见独立真实任务质量基准。 | 办公文件归档基线；SSS 可测多文件依赖、冲突元数据与错误搬移恢复。 |
| [box-jev-incident-triage](https://github.com/box-community/box-jev-incident-triage) | PDF 转文本后调用 Jev 三个判断，固定策略写入 Box 元数据/搬移，可创建人工复核任务。 | 可运行演示；未提供准确率、人工修正和费用比较。 | 现实办公写操作的预览、人工复核与撤销设计参考。 |
| [GroundCheck](https://github.com/sharziki/groundcheck) | 用 Jev 判定答案中的主张是否受给定来源支持。 | 有[评测方法](https://github.com/sharziki/groundcheck/blob/main/bench/BENCHMARK.md)，但英语与特定来源设定限制泛化；只检查给定来源，无法发现检索时漏掉了关键来源。 | 逐条引用核验的局部基线；SSS 还须做来源覆盖与必答点检查。 |

补充反例：[jev-skill 成对实验](https://github.com/wuyoscar/jev-skill/blob/main/evals/RESULTS.md)的 12 对合成任务中，传统 Agent 完成 12/12，固定回合插入 Jev 建议完成 10/12；报告费用 $0.00507→$0.00911，平均 API 时间 6.33→12.57 秒。不能把“增加 Jev 判断”预设为增益。

## 三、SSS 的具体结合点

### 代码迁移

运行时按调用点维护 `定位 → 候选变换 → 应用到副本 → 语法/测试验证 → 接受或回退`，保存旧/新 API 版本、文件哈希、AST 绑定、补丁与测试证据。确定性规则可处理的点不调用 Jev；有两个以上合法迁移候选、失败原因需分类、或局部上下文有歧义时，Jev 只能从带证据的封闭候选中选择，必须允许 `未知/升级`。生成模型只处理无法由候选解决的缺口，产物仍经过相同守卫。若 Jev 提高错误自动接受率，改为仅建议或停用该判断点。

### 办公与 deep research

首个主任务继续用限定范围、多来源的研究问题：检索、去重、抽取、必答点到证据片段的绑定、逐条引文校验由运行时负责。Jev 可判断候选来源是否相关、两条证据是否冲突、缺口应补哪类来源；正文仍由生成模型写。低置信和证据不足不能变成“已回答”。办公文件归档作为第二任务：提取字段、重复检测、分类候选、预览、确认后移动、撤销；Jev 只在分类或异常分流上介入。

研究流程应单独测试“同一来源逐项调用”与“多个来源打包判断”的一致性、费用和时延，不能预设打包总是安全的；参见上述研究监测 pilot 的 11/20 一致结果。文档分类还要覆盖缺失置信度和 API 异常，默认进入复核，不能将缺失值解释为无需复核。

以上是待检验的设计推论，不是已经取得的性能结果。Jev 官方文档也说明其不写代码/正文，长而无关的状态、数字精度和复杂间接判断是弱点；中文任务要单独测。[模型说明](https://docs.typesafe.ai/models)、[已知弱点](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

## 四、能检验“结构 × Jev”额外价值的实验

同一任务快照、同一生成模型、reasoning、工具权限、候选信息、预算和验收器，预先固定以下组别：

1. 传统 Agent：生成模型决定流程与工具。
2. Agent + Jev：Jev 做路由/检索/守卫，没有可执行任务图；对应 PiJev、JevGraph 等。
3. 结构运行时 + 原生成模型：图执行相同节点，歧义交给生成模型。
4. **结构运行时 + Jev**：只将合适的有界歧义交给 Jev，其他缺口仍可回退生成模型。
5. 普通脚本 + 缓存：相同确定性迁移或检索能力，没有图状态/恢复；必要时再测“图仅作提示”。

首要判定是同一质量门槛下的**合格任务比例、每个合格任务总费用、人工修正时间和端到端耗时**。代码验收包括隐藏测试、目标调用点覆盖、错误/无关改动、原仓库未改；研究验收包括必答点、逐句证据支持、遗漏/错误、引用可追溯；归档验收包括分类、误移动、恢复。保存 Jev 问题与概率、图自动执行数、语义缺口、回退、实际模型请求、缓存命中/未命中 token、全部模型费用和失败重试。PiJev 的经验提醒：缓存输入可能非常便宜，减少 token 不一定降低现金支出。

最关键的消融是 ② 对 ④（图的额外价值）、③ 对 ④（Jev 的额外价值）、⑤ 对 ④（相对简单脚本的价值）。若只降低工具调用而不提高合格完成率或总成本，不能宣称方法更强。先在新仓库/新材料上冻结任务和评分，再运行；已用于设计的 Requests、Jinja、ATC/G-Agent/AutoTool 只用于开发诊断。对第三方结果与本地结果分开记录，失败样例原样保存到被忽略目录。
