# SSS 图决策智能体研究环境

**当前导师汇报入口：**[合成科研任务中的 Motif 结构执行阶段性调研报告](reports/导师汇报_合成科研任务中的Motif结构执行_2026-09-29.html)（[可编辑原稿](reports/导师汇报_合成科研任务中的Motif结构执行_2026-09-29.md)）。不进入主线的开发试跑和负结果见[实验资料归档索引](reports/archive/实验资料归档索引.md)。

本目录以[需求与初步方案](source/导师讨论需求与初步实施方案.md)、[底座选型修订](智能体底座选型修订.md)和[结构—语义分离实施依据](experiments/结构语义分离实施依据.md)为依据。当前已部署 Agent 运行环境、文献整理流程和首个结构运行时原型；正式产品功能尚未完成。

**当前产品方向：**从冻结的 MotifAgent 实现迁移轨迹编译、可执行 motif、匹配、结构推进与显式语义交接；DSH 是第一种语义执行器。现有场景脚本尚未构成该主控链。边界及迁移检查见 [SSS 核心与 Harness 集成边界](experiments/SSS核心与Harness集成.md)。

**原生 Harness 接入试验：**`scripts/prepare-sss-runtime.py` 会为固定资料目录和已认证只读 Motif 生成一个独立的 DSH 补丁，写入 `.local/sss-runtime/harness.patch.yml`。该补丁把原生 Agent 可见的工具限定为 SSS 的资料收集、分段读取、增量刷新和逐项检索交接／恢复；后端由迁移的 MotifController 执行并核验资料版本。它已覆盖读取与检索两个结构片段，尚未让同一个 SSS 状态机主控规划、证据选择、报告生成和写入。详细边界与复现方式见 [原生 Harness 接入切片](experiments/原生Harness与SSS运行时接入切片.md)。

## 启动

需要 Node.js 20 或更新版本。在本目录运行：

```bash
npm install
npm run structure:setup
npm run dev
```

启动命令会打印带临时访问令牌的完整本地网址，**请打开该网址**；单独访问 `http://127.0.0.1:8765` 会被拒绝，这是正常的本地访问保护。进入后先选择 SSS 作为 workspace。首次发起任务前，在 Settings → Models 中配置自己的模型 API 凭证；配置和会话保存在本目录的 `.local/dsh/`，不会进入 Git。当前环境不会自动发起付费模型调用。

若需要在另一个终端查看当前访问地址，运行 `npm run local:url`。带令牌的网址只供本人访问，不要公开分享。

停止服务：在运行终端按 `Ctrl+C`。检查安装版本：`npm run harness:version`。

## 当前边界

- 这是开发和小组试用环境，不是公开网络服务；监听地址固定为 `127.0.0.1`。
- `node_modules/` 与 `.local/` 不提交。升级 Harness 前先记录版本并验证现有任务，因为当前上游仍是开发者预览版。
- 不要把订阅账号当作产品 API 凭证。DeepSeek Harness 的模型设置使用独立 API 凭证；Codex 的直接使用另作为基线。

## 下一步

**MotifAgent 内核迁移的首个可运行切片已接通。** `src/motif_core/` 复制了冻结 artifact 的 frame／证据／确定性依赖求解模块，办公科研适配器在 A→B 两阶段合成任务上运行归档、引文绑定、暂停恢复和失效传播。2026-09-25 本机运行中，A/B 的结构评分与事件核对均通过；B 复用 5 份原资料，读取 2 份新增资料，只有 `MF-24` 的旧结论失效。复现命令见[合成任务说明](benchmarks/office_research_v0/README.md)。这证明机制路径运行，不代表真实报告质量或节省费用。

已将 [mu 与本地 Laya](experiments/mu对照与本地Laya接入.md)列为重点对照。Laya 0.3.20 已在独立本地环境部署，可用 `npm run laya:start` 启动 `127.0.0.1:8766` 服务；真实中文推理及 DR³-Eval 资料 shadow 扫描已完成。初扫出现高概率的来源角色误判，因此当前只记录 Laya 判断，不允许它自动删资料。mu 的判断内核已覆盖通用 Agent 的很多低成本决策点；SSS 需证明 Motif 的跨步骤证据状态和增量恢复对 mu 有额外帮助。

[KnoxChat](experiments/KnoxChat强基线与评测入口.md)已加入代码迁移与实际试用基线；已核查发布页和实际源码，尚未得到它在 SSS 同题任务上的实时模型成绩。

当前首要工作是继续补全 [MotifAgent 式结构核心及 DSH 交接](experiments/SSS核心与Harness集成.md)。`src/motif_core/` 现有跨任务轨迹挖掘、留出任务认证、只读 motif 库、输出目标匹配、参数流执行、受限语义交接与恢复、节点级证据版本以及经复核才启用的失败守卫。DSH 原始工具事件可加可核验的参数来源旁证后离线入库。科研资料读取与逐项检索已走该主控；写操作、开放式规划和整个调研报告的顶层顺序仍未由通用 MotifExecutor 接管。G-Agent 与 AutoTool 的局部机制按实测收益取舍，Jev 可通过有界语义回调接入。

多候选 Motif 的交接点现有 [embedding、本地 Laya 和 Jev API 三种可替换建议接口](experiments/Motif候选轻语义路由.md)。Qwen3-Embedding-0.6B 权重已下载并通过 SHA-256 核对，本机推理可用 `npm run embedding:start` 启动；三种建议都不能直接授权运行。Jev 付费请求默认关闭，目前没有真实 Jev 密钥或实测结果。没有 TF-IDF 路径。

[AutoTool 三组同题对照](experiments/AutoTool三组对照结果.md)已加入原生 DeepSeek Harness Agent 基线，并与普通检索脚本、多步结构流程比较。三组均未完成本题全部验收点；原始 token 与逐项缺口已保存，当前不能宣称合格任务的节省比例。

复跑原生 Agent 基线可先预览 `npm run research:native -- '具体问题' --source /path/to/paper.pdf`，确认单份来源与提示后加 `--call-model`。该命令允许 Harness 使用本地工具并发起多次模型请求；复制工作目录不提供操作系统文件隔离，请仅用公开、可信 PDF。原始事件与用量保存在被忽略的 `.local/native-baselines/`。

原生 Agent 现也可用 `--source-dir /path/to/sources --answer-points /path/to/points.json` 预览最多 20 份 PDF／文本来源的同题输入；公开 DR³-Eval 题已验证 16 份文件被逐一复制并核对哈希。付费运行必须显式加 `--max-model-requests N`，事件守卫会在下一步开始前阻止超出请求数，并在已观察输入 token 超限后停止；已发生的用量及停止原因会保存。**这不是服务端账单硬上限**，原生 Agent 的单次输入规模仍可能变化，应单独确认预算。两条有结论 JSON 的研究流程可用 `scripts/prepare-research-review.py` 生成同格式、隐藏方法名的人工评审包；评审先检查引文是否支持结论和必答项是否完整，再比较费用。

[同题盲评与总成本协议](experiments/同题调研盲评与总成本协议.md)现已把普通脚本、Motif 逐项调研和原生 Agent 的题目、必答项、来源哈希统一记录。`scripts/prepare-research-review.py --brief-only` 为不同形式的报告生成同一评审格式；`scripts/score-research-trial.py` 核对同题输入、人工合格判定和实际费用证据。公开题三条无模型预览的 16 份来源哈希一致；真实合格报告和费用对照尚未完成。

[下一轮结构—语义分离实验设计](experiments/下一轮结构语义分离实验设计.md)列出与普通脚本、原生 Agent、提示词流程的等条件对照和消融标准。

[论文摘要与归档](office/papers/README.md)已经作为环境试跑打通，不能代替主实验。运行 `npm run usage:latest` 可查看最新 Harness 会话的模型请求与 token 用量；报告只统计用量，价格应按执行时的官方价另行核算。

`npm run usage:latest` 需要系统安装 `zstdcat`；当前这台 Mac 已具备。

## DSH 中的工具

`npm run structure:setup` 后运行 `npm run dev`，DSH 默认接入 `local_research_tools`（本地 Python／Quarto 适配器）和只读文献发现 MCP，并在已准备好时接入 Zotero、Obsidian、Google 日历与 Gmail。旧调研 MCP 原型已删除；MCP 只负责工具接入，MotifAgent 主控内核尚在迁移。连接和验证状态见 [科研工具 MCP 接入](src/mcp/connectors.md)，正式架构见 [SSS 核心与 Harness 集成边界](experiments/SSS核心与Harness集成.md)。

下一轮主线与对照口径见 [结构化工具科研场景执行决议](experiments/结构化工具科研场景执行决议.md)：本地图表／JSON 核查只保留为开发诊断；主线选择真实跨应用科研决定，区分自由 Harness 基线与受限 MCP 诊断。

三类真实数据核查已实际调用结构化 MCP，并留下版本与参数传递轨迹；由其中两类轨迹编译的三节点候选已在独立数据任务上执行，也完成一次真实 DeepSeek 语义交接。在三个已明确统计参数的数据切片上，它与普通版本化缓存都将第二轮工具调用从 3 次降到 1 次，尚未显示额外收益。它未通过完整科研交付的质量与成本门槛，未注册为产品 Motif。失败案例、token 与费用代理记录见 [结构化 MCP 三类真实数据核查记录](experiments/结构化MCP三类真实数据核查记录.md)。

## 结构运行时首个样例

`src/graph/runtime.py` 持有可执行节点、依赖、已核验证据与语义缺口；不是要求模型照着 Skill 自行执行。代码迁移样例处理 Python 3.10 起已移除的 `collections.Mapping`、`MutableMapping`、`MutableSet`、`MutableSequence` 和 `Callable`：支持单项导入、全部成员均可核验的同一行 ABC 导入，以及能核验顶层 `collections` 绑定的属性用法，并产生预览：

```bash
npm run migration:preview -- /path/to/python/repository
```

预览的 diff、来源哈希和待人工判断的位置写入被忽略的 `.local/migration/`；**不会修改目标仓库，也不会调用付费模型**。ABC 与非 ABC 的混合导入、重名或来源不明的 `collections` 绑定停在语义边界。可重复使用 `--include jinja2` 这样的相对路径参数，只扫描指定包或文件；验证时仍复制完整仓库以便运行测试。这个窄样例用于验证运行时契约，不能视作完整代码迁移产品或成本增益证据。运行 `npm run test:structure` 检查关键边界。

预览报告还包含每个改动点执行的子图轨迹 `site_runs`：先核对来源与绑定，再产出候选改动。它提供逐点审计证据，但与普通 AST 脚本相比的额外收益仍待对照实验。

若仓库有可运行测试，可在复制出的仓库里验证预览补丁：

```bash
npm run migration:verify -- /path/to/python/repository --test-command '/absolute/path/to/python -m pytest -q'
```

命令会在 `.local/migration-sandboxes/` 中复制仓库、应用预览并运行指定测试，保留差异和测试结果；原仓库不会被改动。这里的“隔离”只指复制目录，**不是操作系统安全沙箱**，因此只对可信仓库运行其测试。若测试失败，运行时停止并留下 `tests_failed` 缺口。

测试失败后，可预览局部语义调解：

```bash
npm run migration:mediate -- /path/to/python/repository --test-command '/absolute/path/to/python -m pytest -q'
```

此命令先在复制仓库中重现失败，列出静态核验过、但尚未纳入自动规则的 `collections.abc` 候选。加 `--call-model` 才会发起一次 DeepSeek 调用（最多 500 输出 token）：模型只能选候选编号，结构层生成差异并在另一份复制仓库中重测。若没有安全候选、模型回答无效或测试仍失败，流程停止并保存报告；原仓库始终不变。这仅覆盖 Python `collections` ABC 迁移，不是通用代码修复器。

第二类迁移规则处理旧版 Jinja2 的 `native_concat` 单值非文本返回问题，先核对精确 AST 形态和来源哈希，再在复制仓库中比较改动前后测试；不调用模型：

```bash
npm run migration:native-value -- /path/to/prepared/repository --file jinja2/nativetypes.py --test-command '/absolute/path/to/python -m pytest -q tests'
```

仅当 `native_concat` 的导入、单值分支、文本拼接分支和 `literal_eval(out)` 形态均匹配时才生成补丁；其他代码停在 `unsupported_shape` 等语义缺口。程序保存预览差异、前后测试、逐节点轨迹于 `.local/native-value-runs/`，不修改输入仓库。测试在目录复制中运行，仍只适合可信源码。真实 Jinja2 2.10.1 的 Python 3.12 验证见[任务记录](experiments/Jinja原生值迁移任务登记.md)；该旧版另有独立的 traceback 格式测试失败，此规则不处理它。

研究场景已有同一运行时驱动的本地证据准备流程：

```bash
npm run research:prepare -- '你的具体研究问题' --source-dir reference --terms 'motif,parameter,fragment'
```

它提取 PDF/文本、去重、筛选并核验来源页码，随后停在“综合结论”的语义缺口。输出在 `.local/research-runs/`，不会调用付费模型。

如需完成一次有界语义回答，先运行 `npm run structure:setup` 安装 Python 3.10+ 环境，再运行：

```bash
npm run research:answer -- '你的具体研究问题' --source-dir reference --terms 'motif,parameter,fragment' --call-model
```

不加 `--call-model` 只预览证据与预算。模型配置使用本机 Harness 已保存的 DeepSeek 凭证，回答限制为一次无工具调用、每次最多 1,200 输出 token；每条保留结论要有能在来源文本中核对的短引文。模型输出和用量留在被忽略的 `.local/`。目前仅支持本地参考文献，不包含网页检索；[同题首轮成本记录](experiments/首轮同题成本对照.md)说明了已有结果及限制。

需要分解为多个子问题时，可试验三步的本地 Deep Research：

```bash
npm run research:deep -- '你的具体研究问题' --source-dir reference
```

默认只预览规划提示；加 `--call-model` 才会调用模型，最多三次（规划、从已核验页中选证据、综合），各步失败即停。`--plan-only` 可只生成计划；`--plan-file` 和 `--selection-file` 可复用已保存的计划/选页结果来控制调用成本。结果保存在 `.local/deep-research-runs/`。本流程仍只读取本地 PDF/文本，不包含网络检索；当前同题对照显示它尚未比普通检索脚本更省，见[多步研究同题对照](experiments/多步研究同题对照.md)。

有预先确定的必答原文证据时，可加 `--evidence-contract /path/to/contract.json`。契约是最多 12 个 `{id, source, page, anchors}` 条目，`anchors` 为该页中必须出现在最终 750 字符摘录内的短语。同一页多个锚点相距较远时，结构层会提供由省略标记分隔的多个连续原文片段；引文必须完整落在其中一个片段。运行时先核对来源与短语，再检查模型选中的页；若必需页被漏选、短语不在原文或摘录超预算，会停止在类型化缺口，**不会发起最终综合调用**。综合后还会检查每个必答锚点是否出现在已核验结论的引文里；缺失则保存答案和用量，但返回 `incomplete_answer`。全部命中时标为 `contract_covered`，仅表示指定引文覆盖，**不是整题质量通过**。有契约的综合最多 1,800 输出 token，无契约时最多 1,200。示例见[样例证据契约](experiments/样例证据契约.json)与[七锚点事后诊断契约](experiments/六点证据契约-事后诊断.json)；它们都不是先前留出实验的预注册设置。开放式问题可以不提供契约；契约守卫也不能替代人工判断“引文是否支持整句结论”。

第二道预先登记的留出题与 Jinja2 迁移结果见[留出任务结果](experiments/留出任务结果.md)。两道研究题都表明目前多步流程尚未在“合格答案成本”上胜过普通脚本，后续需要改善证据选择和缺口覆盖，再做更多任务的等条件评测。

尚不知道答案所在页时，可在调用前写一份**原子必答项**清单，再加 `--answer-points /path/to/points.json`。格式为 1–8 个 `{id, requirement}`，每项尽量只包含一个可独立判定的条件。综合结论须标明 `point_id` 并附可定位引文；不确定项也须标明 ID，并用 `blocks_requirement` 区分是否影响题目要求本身。缺少引文结论或存在 `blocks_requirement=true` 的缺口会返回 `incomplete_answer`。全部建立引文关联时状态为 `point_links_present`，**只表示关联存在，不表示每项已完整回答或引文蕴含结论**。这项清单可以与来源锚点契约同时使用；两项守卫都通过仍需人工质量评估。提供清单时综合步骤最多 1,800 输出 token。[G-Agent 诊断](experiments/G-Agent检索复用守卫结果.md)展示复合条目造成的误报；[AutoTool 原子清单](experiments/AutoTool惯性安全边界必答点.json)与[运行记录](experiments/AutoTool安全边界守卫结果.md)展示旧版真实调用如何停在三项未回答的缺口。

对已保存的 `incomplete_answer`，可先预览一次局部修复：

```bash
npm run research:repair -- /path/to/saved-run --source-dir /path/to/same-reference-directory
```

确认缺项和调用上限后加 `--call-model`，最多新增 2 次模型请求。结构层会重验原 PDF 哈希、为缺项重检索、核对短引文、替换该项旧结论并重新检查完成状态；源文档不被修改。结果在 `.local/research-repairs/`，包含父任务与新增及累计用量。[AutoTool 事后修复记录](experiments/AutoTool局部修复诊断.md)显示一次检索窗口错误及一次“不确定范围”假阴性；当前仍需人工判断引文是否真正支持结论，修复成功率尚未验证。

[AWM 新资料对照](experiments/AWM新资料对照结果.md)使用此前未参与流程开发的论文测试相同接口。普通检索与结构流程都未答全；结构流程第一次综合因 9 条结论超过旧 8 条上限而失败，现已把清单任务上限调整为 12，并对保存的响应做无模型回放。旧流程的选页仍遗漏在线成功门槛。

新增逐项证据流程，适用于问题已有 1–8 项可独立核对的要求时：

```bash
npm run research:points -- '你的具体研究问题' --source-dir /path/to/local-papers --answer-points /path/to/points.json
```

默认只预览来源、页数与三次调用上限；加 `--call-model` 才依次规划、选核验证据、综合。`--plan-file /path/to/saved-plan.json` 可复用已验证的逐项检索计划，省去规划调用，并预览剩余两次调用的预算。模型选页后，结构层重验来源，并在字符预算内把选中页拆为多个可引用片段；同一页给多个必答项复用。每项结论仅能引用分配给该项的证据，跨项引用会被拒绝。结果保存在 `.local/point-research-runs/`。这仍是开发试验：已读 AWM 的[首次逐项诊断](experiments/AWM逐项证据诊断.md)与[多片段事后诊断](experiments/AWM多片段事后诊断.md)显示证据选择改善，但整题未通过，质量和成本优势均未确立。引文存在只证明可定位，必须人工判断是否支持完整结论。

这条逐项流程的来源读取和去重现使用迁移的 Motif 状态与哈希绑定证据。首轮输出 `motif-source-state.json`；随后可加 `--previous-source-state /path/to/previous/motif-source-state.json`，核对文件哈希后只重读变化来源，并记录失效事件。`planning-handoff.json` 记录结构层交给查询规划模型的输入范围与预算。[DR³-Eval 中文任务 003](benchmarks/dr3_zh003/README.md)的无模型预览已验证 16 份来源第二次全数复用。下游检索和报告仍由旧 SSS 图运行时执行，完整 Motif 主控迁移及真实报告质量对照尚未完成。

比较型必答点可在清单中设置 `min_sources: 2`。选页阶段允许每项选 1–2 处证据，并在两来源要求下保留不同资料的候选；结构层在综合前核对来源文件、页码、哈希和原文片段。`--plan-file` 配合 `--selection-file` 可完全不调用模型地预览综合输入。选择文件须填写本轮 `selection-bundle-template.json` 中的候选指纹和每项的 `evidence_ids`；资料或候选变更后旧选择会被拒绝。该预览用于检查证据与预算，不能替代报告质量评价。

为报告中每个问题挑选的原文证据写入 `motif-selection-state.json`；后续可加 `--previous-selection-state /path/to/previous/motif-selection-state.json` 复用。MotifFrame 会逐个问题比较候选片段和问题要求；一份资料变化时，受影响的问题重新挑选，其他问题可以沿用已核验的选择。此接口仍需要相同的逐项检索计划才能重建候选池。公开题的无模型诊断已复用 4 项选择，并在后续资料变化时只使相关问题失效；真实模型报告和用户操作体验仍未测试。

[EvoGraph 启发的 Motif skill 进化切片](experiments/EvoGraph启发的MotifSkill进化.md)把上述依赖范围做成可版本化的结构策略：来源运行触发候选修订，训练及留出扰动检查安全复用，启用后记录下一次实际使用。可用 `scripts/evolve-motif-selection.py` 初始化和评估本地账本，再用 `research-points.py --selection-skill-registry /path/to/registry.json` 在流程中执行其当前版本。现阶段只验证内部证据选择的重用，尚未证明报告质量或总费用优势。

如果已有一份本流程生成的报告，可在下一次运行加 `--previous-report-run /path/to/previous/run` 生成增量草稿。程序重验旧引文与当前资料，保留可定位的结论供人工复核，只为失效的问题准备新的综合输入；输出 `change-log.md` 说明资料和逐项要求的变化。即使旧引文仍可定位，新资料也可能与旧结论冲突，所以沿用部分标为待审阅。无模型[公开题机制检查](experiments/公开调研增量报告切片.md)已走通，真实报告质量和合格任务总成本尚未验证。

比较项的最终覆盖门还要求被接受的结论实际引用两份不同资料，未满足则标为 `insufficient_sources`。`answer.md` 现在是按必答点列结论、未知项和来源索引的待审阅简报。结构检查不判断两种方法的语义比较是否充分，人工评审仍是质量门。

有真实模型用量的运行结束后，可用 `.venv312/bin/python scripts/report-research-cost.py /path/to/run` 查看按[当前 DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)估算的峰时／空闲时段 API 费用范围。它分别计算未缓存输入、缓存输入和输出 token；人工修订、本地计算及未写入日志的请求需另外记录。首个公开题的[真实模型实验预览](experiments/DR3-zh003真实模型实验预览.md)列明请求上限和质量验收。

相同必答项的一次调用检索脚本可作为较简单的对照：`npm run research:simple -- '问题' --source-dir /path/to/papers --answer-points /path/to/points.json --terms '事先固定的英文词,另一词' --per-source-limit 8`。默认预览；加 `--call-model` 才发起一次综合调用。该脚本仍使用相同来源核验与短引文检查，但没有逐项规划或选页。[SWE-agent 新来源对照](experiments/SWE-agent新来源对照结果.md)显示两个方案都未完成固定任务，且记录了逐项流程在跨组候选 ID 上安全停止的情况。

[Agentless 新来源对照](experiments/Agentless新来源对照结果.md)进一步显示：多条件答案原先被“三段引文”格式上限大量误拒，扩大到四段后用保存响应离线回放，结构覆盖虽通过，人工仍发现一项只答了部分要求；原始运行的质量和费用照旧记录。当前主要瓶颈已从“能否找出原文”转到“引文是否完整支持必答条件”，应在新题上继续验证后再讨论省钱或产品化。
