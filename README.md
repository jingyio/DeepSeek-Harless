# SSS：Motif × DeepSeek Harness × 自定义 MCP

2026-10-15已上传：持续RSI代码与4份原始v2策略见`feature/rsi-research-agent`提交`f397645`；新机器从自己的库学习，公开摘要不替代私有运行准入证明。GeneLoop main命令接入与Windows CI修复见[发布记录](docs/changes/rsi-publication-20261015.md)。

2026-10-15发布准备：用户已授权将完成的RSI代码、共享接口/实验文档与4个原始v2学习策略上传`feature/rsi-research-agent`。公开库见[operation-v2](examples/motif-library/file-management-operation-v2/README.md)，私有轨迹/任务/凭证保留；原运行准入证明不随公开摘要迁移。历史“暂不推送”记录对应当时阶段。GeneLoop主线的`/management`接入将以最新main为基准，避免覆盖现有注册与工作区能力。

2026-10-15 最新：日常文件管理默认固定持久库，v2支持同图顺序重复、1–40唯一字符串数组及多产物绑定，SDK/Web/认证恢复沿用原任务、权限、版本和预算。18次真实执行（6新任务＋12认证）/163HTTP/USD0.097170133，4图激活、第5版，合计40次验证跳过；转换的一次工具失败和报告缺口保留。完整浏览器提交/重启/恢复/真实状态验证通过。默认真实入口重启0新增模型请求。原最终集/失败/费用保留，暂不推送。见[接口](docs/changes/persistent-rsi-integration.md)和[实验](docs/experiments/persistent-rsi-20261015.md)。

日常启动：`npm run web -- --scenario file-management --real-model --mode execute`，通过原环境变量提供已有DeepSeek凭证，认证后访问`/tasks`。不传`--rsi-config`沿用`.local/rsi/daily-files-real-v2.json`；模拟库独立。预算达到原限额即停止，不靠重启清零。其它MCP仍须登记独立权限、材料和质量适配器。

2026-10-15最新：已接通工具名无关的 MCP 学习契约与2–8节点参数DAG，并扩展到原授权文件写操作；真实新流从两节点前缀学习并独立认证五节点图，3个新图激活，严格文件流6/6普通任务合格。既有默认 Harness Web 的 file-management profile 已接同一库、任务后封存与自动学习队列；真实Web5/5合格，17次结构续接经实际结果验证。632 Python/211 Node通过、3可选跳过、18smoke；本轮59真实执行/470HTTP/代理USD0.237622092，包含所有失败与认证，最终留出不学习、暂不推送GitHub。其它MCP仍须登记真实权限/材料/验收适配器，任意控制流及稳定完整净收益未验证。 [完整实验](docs/experiments/generic-mcp-operation-rsi-20261015.md)、[共享接口与入口](docs/changes/generic-mcp-operation-rsi.md)。

```sh
npm run web -- --scenario file-management --budget-usd 5 --request-limit 96
# 真实模型显式开启，预览后确认：npm run web:real -- --scenario file-management
```

以下为此前版本的历史记录；其中“默认Web未接”等表述仅对应当时版本。

2026-10-15已接通首版普通CLI持续Motif学习：任务封存后自动发现/编译、新副本独立认证、版本发布与后续复用；真实新任务流完成两版升级、6/6普通交付。最新并发队列/证据修订服务621 Python/199 Node通过，最终云端复验遇503，未完整重现两代，已停止付费诊断。首版仅只读文件报告及两类有界图，默认SDK/Web未接；净收益仅观测。30真实执行/146HTTP/估费上界USD0.176759772，5次503和全部失败/费用保留，最终留出不学习，暂不推送GitHub。[实验与边界](docs/experiments/continuous-motif-rsi-20261015.md)、[接口与入口](docs/changes/continuous-rsi-integration.md)。


此前[工作流结构报告与新RSI验证](docs/experiments/file-management-report-delivery-20261014.md)完成102次新执行：task_result身份/快照/真实回执由当前MCP状态生成，模型填写摘要/缺口；原实际字节与权限验收不变。新诊断H/回退各6/6；两轮当前版本经验学习/独立认证/自动激活后均在下一任务零HTTP执行。日常H5/6、S/F/R各6/6，最终正常H/S/R各8/8、F7/8，8版本安全停止。R完整API USD1.325444比F1.390140低约4.65%，但F未全部合格，预定同质量净收益门槛仍未满足；普通回退备份仍需修复。603 Python/185 Node及smoke通过，系列估费USD7.836915368；失败/排除/轨迹/费用与旧最终留出保留，仅本地、默认SDK/Web未启用、暂不推送GitHub。[共享契约](docs/changes/file-management-report-delivery.md)。


此前[回退修复与持续学习验证](docs/experiments/file-management-fallback-rsi-20261014.md)完成142次真实运行：跨计划重复SHA写入在执行前拒绝，提交时检查原始字节组完整覆盖。第二版新诊断H/回退均6/6；新两轮经验自动认证激活并在后续实际执行。最终正常H7/8、S8/8、F8/8、R7/8，8版本安全停止；R完整API USD1.149742低于F1.207199约4.76%，但最终质量较低，不支持同质量净收益。未知目标失败的文件正确但缺实际报告，原失败/费用留存，最终不学习。599 Python/185 Node通过，系列估费USD7.197809948。本轮仅本地，暂不推送GitHub、默认SDK/Web未启用。[共享接口](docs/changes/file-management-fallback-guard.md)。


[有界自动RSI](docs/experiments/file-management-auto-rsi-20261014.md)已完成两轮自动升级及66次真实运行：统一Motif/脚本版本库、无profile_id事实检索、重复成本触发普通探索、独立认证、自动激活/停用/回退。正常最终H/S/F各7/7、R6/7，8版本安全停止；RSI完整API USD0.520634，高于冻结库0.491204与H0.137249，S零模型，尚无净收益证明。此次633HTTP/USD0.477517296，系列USD5.893675700。失败/轨迹/费用原样保留，新代码仅本地、默认SDK/Web不启用。[共享接口](docs/changes/file-management-auto-rsi.md)。

[已学习的文件管理 Motif 库](examples/motif-library/file-management-v1/README.md)现以版本化分发目录保存：9个库/策略、3个在线 manifest 与3份原认证/冻结摘要，原始字节/签名保留；免费检查6项通过，公开副本无需 `.local` 即可校验。用户已授权将此次库分发推送 `feature/rsi-research-agent`；此前暂不推送的记录是历史状态。G4部分运行源码仍待发布，默认SDK/Web不自动激活，固定脚本库另存。[分发契约](docs/changes/file-management-library-publication.md)。

[脚本规则/目录变化与第二版](docs/experiments/file-management-script-adaptation-20261014.md)验证完成：4模板/8独立认证/40新H/S/M/L1/L2留出，正常H/S/L2各6/6、M5/6、L1 4/6，10版本负例停止未交付。L2执行0HTTP，含首版与新验证/修复/学习/认证USD0.374614224，未优于预写脚本完整API成本；65运行/790HTTP/USD0.715712544，系列USD5.416158404。原失败/轨迹/费用和旧版本保留，默认SDK/Web不启用，暂不推送。[共享变化](docs/changes/file-management-script-adaptation.md)。

[学习脚本复用首批](docs/experiments/file-management-script-reuse-20261014.md)已完成：5 次新普通探索（4 份用于提炼，1 份排除但计费）→2 复制模板→8 次独立认证→24 次 H/S/M/L 新留出。正常/边界四组各4/4，8版本停止保留；学习脚本与预写脚本执行均零模型，L加建库/认证为USD0.100006092，尚无相对预写脚本的完整API成本优势。37执行/274HTTP/代理USD0.203031636，系列USD4.700445860；默认SDK/Web不启用、暂不推送。[接口变动](docs/changes/file-management-script-reuse.md)。

六流程[第五阶段新留出H/S/M](docs/experiments/file-management-workflow-holdout-20261014.md)已完成54运行：正常/边界H11/12、S12/12、M12/12，18版本变化安全停止；原H全局编号失败和两轮修复保留。三组执行代理估费USD0.194854178/0.086595528/0.144017954，M加库准备/验证为USD0.379796718，本批普通脚本最低。共同合格11条件M/H执行费−16.53%，不能归为对脚本的学习增益；整Harness同job冷启动/原授权恢复与完整费用审计通过。601真实HTTP、本批USD0.425467660，全系列USD4.497414224，实付/人类质量未核实。默认SDK/Web关闭，暂不推送。[逐项接口](docs/changes/file-management-workflow-holdout.md)。


## 先前覆盖规划（历史）

普通文件管理的[40项覆盖规划](scenarios/file-management/workflow-discovery.md)仍为18项可组合、20项缺工具、2项需运行机制扩展；首批六项已完成G1/G2受限准备、G3探索、G4受限结构认证及持久化计划在线验证。G5新留出H/S/M54次初筛已完成，原留出保持不动，新留出不学习或改库；40项不能计为已实现。

前端开发请先阅读[当前分支接入说明](docs/handoffs/frontend.md)：已有任务HTTP契约、安装命令、模式/预算确认与新增有界验收修复。文件管理场景可显式启用acceptance_guard，原权限和总预算内最多2轮普通Harness修复，每轮失败证据保留；验证与限制见[实施记录](docs/changes/acceptance-repair.md)。

普通文件管理新增 [跨流程实验入口](scenarios/file-management/README.md)：以三篇真实 PDF 和生成的五类文件，在独立副本中运行盘点、索引、检索、分类、重命名、去重、冲突处理、转换、增量、归档恢复等十二类任务，统一采集原始 Harness 轨迹并进行独立 Motif 认证。共享核心保持，副本写操作另有计划/收据/恢复检查；实验与界限见 [记录](docs/experiments/file-management-discovery-20261013.md)，接口与 GitHub 提交依据见 [变化说明](docs/changes/file-management-discovery.md)。

普通文件读取的[在线配对阶段](docs/experiments/file-management-online-20261013.md)完成60次完整任务对照：首轮全12流程整体未省费；修正13来源历史保留后，3读取流程6对都通过、请求44→36、估费−11.68%，仍有单题费用上升。共享manifest新增显式`source_dereference`能力和TypeScript守卫，原库/认证摘要不变，详见[逐项接口记录](docs/changes/file-management-online.md)。`online-study.py`默认冻结预览，显式`--call-model`才运行；SDK/Web默认入口保持原设置。定向生成材料结果不代表真实办公泛化，写关系尚未认证。

[集合读取跨流程阶段](docs/experiments/file-management-collection-20261013.md)新增独立认证的`模型选定集合 → foreach(pin/read) → 完整gather` Motif：6次普通探索、4次认证、6对真实对照全部通过独立验收；相同14工具条件下请求54→39、估费−15.58%，其中一对费用+1.15%。实际选择和语义判断仍由模型完成，受限图语法由工程限定；尚未比较普通批量脚本，也未认证写操作或任意控制流。共享TS/离线编译/CLI/守卫与调度修订详见[接口实施记录](docs/changes/file-management-collection.md)。全文件系列124次运行、997请求、代理累计估费USD0.778423656，实际账单未知；失败和恢复全部保留。

[普通批量脚本与计划认证阶段](docs/experiments/file-management-batch-plan-20261013.md)已完成：读取三组18次均合格，H/S/M请求55/37/37，手写脚本最省费，未观察到Motif相对脚本的增量费用优势。新预授权计划链从3普通训练/2认证与实际字节重放认证，4对评测M4/4、H3/4；共同合格3对请求23→19、估费−3.55%，仍一题费用上涨，故障后由模型用同token恢复。原验收程序失败及H误恢复完整保留。共享权限/版本/持久化/恢复/TS/CLI详见[实施记录](docs/changes/file-management-batch-plan.md)。全文件系列156运行/1231请求/代理估费USD0.990767448，实付未知；新接口继续显式实验，默认SDK/Web不开。

最新[第五阶段两代库闭环](docs/experiments/file-management-rsi-cycle-20261013.md)已完成45次：冻结L1执行新任务，从5份真实模型残余图学习L2并独立认证，再跑36次新留出。L1/L2共同合格的6次盘点对照请求65→45、估费−15.29%；全体H10/12、L1 6/12、L2 7/12，内容检索质量不足，尚不支持整体质量等价降本。再次进入仅限原读取图在新模型选择后执行第二段，语法由工程限定，未证明通用图学习。完整接口/来源/回退见[实施记录](docs/changes/file-management-rsi-cycle.md)，失败与费用均保留。全系列201次/1693请求/峰值估费USD1.457616816，实付未知；第六阶段完整基准待执行，默认SDK/Web继续关闭新策略。

这是供场景开发使用的最小主线。MotifAgent 的迁移内核负责有证据支持的结构执行；DeepSeek Harness（DSH）负责 Agent 循环、语义判断、工具派发和会话。场景通过 MCP 扩展。

最新[报告契约修复与第六阶段完整基准](docs/experiments/file-management-report-benchmark-20261013.md)完成：区分完整检查成员、字面命中与当前效果结果，源阶段守卫和收据同时用于普通/库组；两失败修订保留，新版本重学/独立认证两代库。36新质量三组各12/12；144完整基准H60/72、L2 62/72，60共同合格配对610→401请求/估费−16.02%，22冻结验收失败完整保留，未证明整体完全合格或真实办公泛化。完整基准未触发第二段再入，其增量证据来自36两阶段对照；未比较本轮手写脚本。共享API/版本/回退见[实施记录](docs/changes/file-management-report-contract.md)。全系列439次/3972HTTP/峰值估费USD3.399507360，实付未知，默认SDK/Web不开新策略。

旧试验、报告、应用专用启动器和失败试跑均在 `archive` / `archive-pre-cleanup-20261009` 分支。本机 `.local/` 是私有运行区，仍保留且不提交。清理范围与恢复方式见 [清理记录](docs/main-cleanup.md)。

普通PDF文献场景已有本地工作台（Node22.18+）：`node scenarios/literature-notes/agent.ts serve --port 8765`，打开 <http://127.0.0.1:8765>。它串联现有Harness的阅读、自动审阅、直接交付、结果复用与资料更新；默认仅预览，不修改原PDF。无需人工批准即可交付；缺口显式保留，自动审阅不保证科学判断全部正确。使用与边界见 [场景说明](scenarios/literature-notes/README.md)，场景接口变更见 [提交说明](docs/changes/literature-workbench.md)。

已带入main bc1ecd5的官方Web与动态任务入口：`npm run scenario`继续保留；`npm run web`默认启动免费模拟的官方Web及同源`/tasks`，`npm run web:real`开放真实API后仍要求任务预算预览确认。同一进程可顺序运行不同题面，每任务独立Session/模式/预算/记录、同时一个任务，启动总预算不因新任务重置。Node22.18+用于TypeScript插件，本轮macOS本机验收；main报告的服务器Node22.23.3/Python3.10.8属于既有验收，其他平台Web未新增验证。具体入口/私有认证地址见[main Web交接](docs/handoffs/harness-web.md)。

最终产品使用自己的前端，官方Harness Web是临时入口。文献新增官方Web入口 `npm run web:literature -- --real-model --papers-dir ./testpdf`：每任务独立问题/PDF快照/Session，在同Session自动阅读、逐论断复核和直接交付；认证后访问 `/tasks`。旧8765工作台的结果缓存/增量更新保留在旧入口，此Web配置尚未迁入全套功能。两问题接入验证与真实费用见[验收记录](docs/experiments/literature-web-binding-20261012.md)，共享接口见[变更说明](docs/changes/literature-web-binding.md)。引用新增可复制单citation_id；阅读/修复可选收据守卫最多两次同Session续接，仍记真实请求费用。SDK/Web当前固定off，思考模式比较尚未运行。[共享变化及边界](docs/changes/literature-receipt-guard.md)、[真实开发验证](docs/experiments/receipt-fix-20261012-9c6d79d9.md)。

## 十分钟启动

需要 Node.js 20+、Python 3.12。先安装固定依赖，再跑不付费的检查：

```sh
npm ci
npm run setup
npm test
npm run smoke
npm run motif:check
npm run scenario
```

最后一条只输出场景、工具、提示哈希、预算和 `reasoning_effort="off"` 的预览。不会启动付费任务。Windows 的入口相同；Python 命令需要在 PATH 中，或设置 `SSS_PYTHON` 为解释器路径。已验证 macOS 本机，以及 Ubuntu / Windows CI 的 Python/Node 测试、18 题 MCP 检查与 Motif 样例闭环（Node 22、Python 3.12）；云模型和真实应用场景仍需各自联调。自定义 MCP 自身的平台依赖仍由场景负责人处理。

仓库文本统一 UTF-8/LF，由 `.gitattributes` 固定检出换行符；统一入口也为 Python 设置 UTF-8。冻结夹具和 Motif 证据按原始字节校验，不能因 Windows 换行符变化而更新锁中的哈希。Windows 已有旧检出副本时，保存自己的改动后重新克隆最新 main 最容易确保规则生效。Unix 的 `0600` 模式检查只在相应平台运行；Windows 文件访问由 ACL 管理，不能用该数字替代 ACL 验证。

明确决定付费运行后，先在本机环境或 Harness 的 `.local/dsh` 凭证存储配置密钥，再显式执行：

```sh
npm run scenario -- --budget-usd 0.25 --max-steps 16 --call-model
```

每次请求经过本机预算代理；模型输出、轨迹、预算账本与 Motif 审计只写入 `.local/`。费用表是仓库固定配置，运行付费实验前应核对；预算记账不等于真实账单。`--max-steps` 限制 Agent 步数，代理账本才记录实际上游请求。默认不开上下文压缩。

## 代码从哪里读

| 目录 | 责任 |
| --- | --- |
| `scenarios/` | 各同学的 MCP 配置、题面、服务、工具契约 |
| `src/adapters/scenario.py` | 校验场景并生成私有 DSH 插件配置；支持 stdio / streamable-http |
| `src/adapters/harness_runtime.py` | Python SDK → Node Harness 的唯一启动边界 |
| `src/adapters/dsh_scenario_guard.mjs` | 限定场景工具集合，阻止绕过 MCP 读仓库或执行 shell |
| `src/adapters/dsh_online_motif.mjs` | DSH 原生插件；在模型请求前匹配认证 Motif，在工具结果后复核 |
| `src/adapters/dsh_trajectory.py` | Harness 原始工具事件 → 带参数来源的轨迹 |
| `src/motif_core/offline/` | 轨迹挖掘、DAG/参数流编译、独立留出认证与 library 产物 |
| `src/motif_core/controller.py`、`read_executor.py` | Python 结构控制、依赖/证据守卫、handoff/reentry |
| `src/motif_core/online_skill_runtime.mjs` | DSH 插件使用的在线执行子集，含受限纯代码参数转换 |
| `tests/` | 结构核心、接口、版本失效、权限拒绝与安全回退回归 |
| `benchmarks/research_decision_portfolio_v{1,2}/` | 18 项冻结的合成科研决定，仅供开发诊断 |

先读 [接口契约](docs/interfaces.md)，再复制 `scenarios/example/` 接一个新场景。`src/motif_core/LICENSE` 和 [来源及迁移记录](src/motif_core/PROVENANCE.md) 必须保留。

科研文献证据准备新增已批准计划的在线续接：模型选定并注册窗口后，已认证 Motif 可免 embedding 执行机械核验与原文包组装；成功工具结果复核后才计入跳过。新接口使用 manifest v2，旧 v1 库保持原路径。共享变化和 GitHub 提交正文见 [变更记录](docs/changes/approved-plan-continuation.md)，真实验证与限制见 [实验记录](docs/experiments/approved-continuation-20261010-94934aab.md)，入口见 [场景说明](scenarios/literature-notes/README.md)。新在线规则用 TypeScript，随仓库提交生成 JavaScript；开发构建用 Node 22.18+ 的 `npm run build:continuation`，运行无需额外 TS loader。科学理解与论断支持未由此认证。

[重新认证后的同计划真实三轮对照](docs/experiments/motif-renew-20261011-14c3fc42.md) 已完成：Harness、脚本、Motif 每次6/4/4请求，证据包一致；Motif费用较脚本均值高约1.68%，没有增量费用优势。阅读计划随后增加保持选定原文的页尾/重叠归一化与完整决策诊断，见 [开发验证](docs/experiments/plan-efficiency-20261011-4ebe9910.md)。更新后的执行版本需重新认证旧证据链，默认继续使用普通程序和核源缓存。当前三篇已知论文只支持开发及机械机制试验，后续按 [分层验收方案](docs/experiments/literature-evaluation-protocol.md) 验证新语料、科学支持和包含学习/修订的总成本。

最新[四组真实组件对照](docs/experiments/harness-strong-20261012-5da6ab9f.md)包含普通Harness、真正Code Mode、普通脚本和learned Motif。统一效率说明后，每组4轮同一批准计划/同packet；请求均值6.25/3.5/4/4，普通脚本最便宜且最快，Motif比脚本估费均值高6.02%，没有增量优势。全部开发195请求/$0.189877572包含学习/两阶段恢复；只针对证据准备组件，不代表整Agent质量或泛化。Code Mode可选Docker隔离执行器，SDK `--tool-presentation ptc`、免费 `npm run code:check`，默认SDK/Web继续native且无需Docker。共享变化见[提交说明](docs/changes/literature-harness-comparison.md)。

普通PDF新增[文献索引与引用目录任务](docs/changes/pdf-catalog-motif.md)：`run-catalog.py`创建/增量更新私有JSON、Markdown、BibTeX，未变目录普通程序0模型。新任务复用原工作数组Motif机制、共享核心不改，策略默认关闭。[12次对照](docs/experiments/catalog-work-20261012-f44dece1.md)请求H28/M19，新增1/2篇估费−25.36%/−14.32%，但一轮作者遗漏且有日期语义问题，不证明完整质量等价；全部91请求/$0.10926764含失败和训练，Web未接。

目录新增[日期类型/作者覆盖守卫](docs/changes/catalog-metadata-guards.md)，共享核心不改、旧策略需重新认证。[新12次对照](docs/experiments/catalog-guards-20261012-066ad241.md)作者/年份均与已查原文一致，实际请求27→18；新增两篇估费−13.00%，新增一篇反而+11.31%且一次标题缺口，不能普遍启用。日期投影是两组共用程序，不计Motif收益；463Python/98Node通过，全部学习/评测60请求/$0.06146788。

文献场景新[40个任务流程清单](scenarios/literature-notes/workflow-discovery.md)按参数来源、语义边界、工具/材料缺口筛选结构；三类新探针复用现有Harness/SDK/MCP/预算，不改共享核心。主题检索、笔记引用定位、论文资源共8次真实运行/56请求/代理USD0.063332112（含引用偏移错误补跑），见[探索记录](docs/experiments/workflow-discovery-20261012-eec15558.md)。13条pin→read与工作数组重复结构只是候选，0新认证/0在线跳过，不宣称已提速；小字段修补暂缓。

新的[多窗口读取续接](docs/experiments/window-continuation-20261012-0bc4ddc5.md)已从普通轨迹学习/独立认证，复用原edge compiler/批量Runtime，无共享核心变化。两题完整任务一题请求−18.92%/估费−3.76%，另一题费用+44.41%；同计划6原文包完全一致，读取调度三轮明确省3次请求，均值估费−5.09%。全部开发26run/266HTTP200/USD0.287990820包含失败/重训，仍显式CLI实验、Web默认关闭，不宣称科研质量或普遍收益。入口window-study.py先预览/训练/认证/检查，再对照，接口见[提交说明](docs/changes/pdf-window-continuation.md)。

## 随仓库分发的 Motif 库

文献场景新增[多任务入口Motif实验](docs/experiments/multitask-motif-20261012-4ba53478.md)：学习冻结目标集合的逐项目读取前沿，语义复核仍由模型完成。两个已有证据复核范围相对普通Harness减少请求/输出；单缺口补读有一次未修好，不能全面启用。`repair-pdf.py --entry-policy <认证策略>`显式实验，默认SDK/Web关闭；新入口协议与旧manifest分开，预算不变。共享接口与GitHub说明见[变更记录](docs/changes/task-entry-motif.md)。

第二个[清单准备入口 Motif](docs/changes/inventory-prepare-motif.md)从原生轨迹学习 `list_pdfs → papers[].paper_id → prepare_pdf`，来源/解析版本一致后交回模型选择阅读窗口。`run-pdf.py --entry-policy <私有认证策略>`可单独加载；完整任务用 `agent.ts run --reading-entry-policy <策略> --claim-entry-policy <策略> --refresh --call-model` 显式组合。只有初次阅读和第一轮支持复核启用；缺口修复、综合、Web 默认继续原 Harness。训练/认证资料和策略在 `.local`，新克隆须有自己的原始轨迹再认证，不能把此开关当开箱可用的通用库。

第三个[增量工作清单 Motif](docs/changes/incremental-work-motif.md)学习 `read_update_plan → work[].paper_id → prepare_pdf`，完整计划/来源守卫通过后交回模型。`agent.ts update --incremental-entry-policy <私有策略>`显式使用，SDK/Web默认关闭。[十二次真实增量对照](docs/experiments/incremental-work-motif-20261012-a55cdbd9.md)：新增一篇请求−29.41%、输出−18.83%、估费−5.17%，两组均3/3收据且无机械缺口；新增两篇费用反而+12.79%且有失败，不支持默认全面启用或科学质量等价。

第四个[收据后结束 Motif](docs/changes/terminal-receipt-motif.md)只替代复核已发布后的末尾文字/stop，状态JSON标明Runtime来源；`agent.ts --claim-terminal-policy <私有策略>`仅第一支持复核显式开启，默认关闭/Web未开。[十二次对照](docs/experiments/terminal-receipt-20261012-34cfce1d.md)方法组估费−32.08%，评测设计组估费+0.56%且两次缺口回退，不能全面启用或称科学质量相同。新库只认证preview，未认证状态仍原模型。

[首发样例](examples/motif-library/research-portfolio-v1/README.md) 包含此前真实 DeepSeek 调用轨迹编译出的 4 个 Motif、在线 manifest、公开证据夹具和版本锁。任务资料为合成科研模拟；历史认证摘要保持不变，没有分发原始私有日志。

`npm run motif:check` 无需密钥，用真实 Harness/MCP 和本机模拟 Provider 检查重编译一致性、执行、shadow 及旧版本回退；`npm run motif:rebuild` 只重编译到 `.local/`。新克隆无需旧 `.local` 数据。它是调试验收起点，不代表真实科研质量或费用收益。加载命令和适用范围见样例说明。

## 18 题怎么跑

```sh
npm run scenario -- --scenario scenarios/portfolio-v1/scenario.json --case l_state_update
npm run scenario -- --scenario scenarios/portfolio-v2/scenario.json --case a_model_rsi_figure
```

默认均为预览。`npm run smoke` 会经真实 stdio MCP 客户端遍历全部 18 题，验证冻结哈希、对象句柄、版本和八种只读工具，并初始化 Harness SDK；不调用付费模型。这能证明工具链可用，不能证明 Agent 会答对题或 Motif 已降低科研成本。付费普通组/结构组和盲评需要另外运行并记录。

Motif 模式的入口与普通组相同，增加 `--mode shadow` 或 `--mode execute`、`--manifest`、`--task`、`--embedding-endpoint`、`--embedding-model`。只能使用轨迹编译且认证通过的 library；完整数据契约与命令见接口文档。

## 两天协作约定

每人一个场景分支，例如 `codex/scene-literature`、`codex/scene-results`、`codex/scene-collaboration`，主要改自己的 `scenarios/<name>/` 和对应测试。你负责公共接口和合并；核心变更先协调。每个小改动提交一次，通过 `npm test` 后发 PR，尽早合回 main。合入别人的工作后，各自同步最新 main。具体操作见 [协作说明](docs/collaboration.md)。

普通文件管理新增[全局重命名与读取范围契约](docs/changes/file-management-task-contract.md)：错误编号/分类路径在写前拒绝，转换产物按真实执行版本核验，空文本必须实际读取，无需写操作时直接交付。[新留出最终24/24通过](docs/experiments/file-management-task-quality-20261013.md)，首轮4失败及两版513HTTP/USD0.338547576全部保留；L2总体费用仅−1.43%，不支持普遍降本。前端新任务选task_tools.py与显式task_contract；旧工具和历史验收保留。
