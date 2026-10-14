## 当前：多窗口读取已学习/认证并在线对照（2026-10-13）

[新读取续接记录](../../docs/experiments/window-continuation-20261012-0bc4ddc5.md)：复用旧edge compiler和批量Runtime，无共享核心变化。两个真实训练9/10边、独立问题6边认证；模型仍选词/页窗/科学解释，Runtime只读已发source_id。独立场景使用有界十进制字符串位置，H/M相同接口，旧探针保持。`window-study.py`先预览，train --call-model→learn→免费check-window正负→evaluate --call-model；默认不启正式Agent/Web。

两个问题各3轮完整任务：三篇比较请求不变、M估费+44.41%；两篇效率证据请求−18.92%、估费−3.76%，科学质量未验。同一实际窗口计划6原文包严格一致，H6/6/6请求、M5/5/4，读取明确省3次，均值估费−5.09%。全部开发/认证拒绝/失败pilot/18对照去重26run/266HTTP200/USD0.287990820；原PDF/密钥/旧资料保持，SDK/Web不默认启用，不宣称优于Code Mode/脚本或整Agent泛化。

## 当前：扩大任务流程探索（2026-10-12）

[40个文献与知识管理流程](workflow-discovery.md)已按消费者任务、参数来源、语义边界、现有能力与材料缺口整理；不是40个已实现Motif。新增主题检索、旧笔记引用定位、代码/数据资源三类探针，各两种问题/范围，复用原Harness/SDK/MCP/预算，不改共享核心/正式Web工具集。入口`explore-workflows.py --evidence <真实私有笔记>`先预览，再用返回的`--experiment <目录> --call-model`；不需要用户新增答案或人工审批。

[真实探索记录](../../docs/experiments/workflow-discovery-20261012-eec15558.md)：6首轮+2引用偏移修复补跑，56请求/代理估费USD0.063332112，13条pin→read真实参数传递与引用/资源遍历候选；0新Motif认证/0在线跳过，不能宣称已提速。首轮引用误报和10次长度提交错误/费用保留，其他细小修补暂缓。优先验证多窗口读取续接和工作数组机制迁移；检索词/资源选择仍需模型，普通Harness已经可以批量调用。

## 当前对照结果：包括 Harness 与真正 Code Mode（2026-10-12）

[真实四组组件对照](../../docs/experiments/harness-strong-20261012-5da6ab9f.md)已完成：普通Harness、Harness Code Mode、Harness+脚本、Harness+Motif，四轮同计划/同源/同packet。强阶段请求均值6.25/3.5/4/4，脚本费用/时延均值最低；Motif虽然每次验证skip2，费用较脚本均值高6.02%。本轮195真实请求/USD0.189877572含学习/认证/独立计划/两轮对照全部纠正；实付未核，不代表完整科研理解或新语料RSI收益。

Code Mode使用真正的run_code/上游生成SDK与WorkerThreadCodeRuntime，模型自行写程序；可选Docker仅隔离部署，不替换解释器或Agent循环。`docker pull node:22.22.2-bookworm-slim`后启动Docker Desktop，`npm run code:check`免费诊断；比较 `compare-evidence.py --include-code-mode --repeats 4` 默认预览，--call-model才付费。需要独立真实批准plan-run和当前认证manifest，不能复用未知来源证据。SDK一般--tool-presentation ptc为显式选择；默认native和现有Web/8765不依赖Docker、不强开旧库。

暂不把固定verify/build链加入Web来增加开销。下一步先寻找资料更新/缺口恢复中的可验证重复分支，再以强脚本/真正Code Mode和同质量任务检验。接口/兼容/回退见[提交说明](../../docs/changes/literature-harness-comparison.md)。

## 官方 Web 文献任务（2026-10-12）

```sh
# 默认免费协议模型，实际费用0，不理解论文
npm run web:literature -- --papers-dir ./testpdf
# 真实DeepSeek；Key复用.local/deepseek.env或环境变量
npm run web:literature -- --real-model --papers-dir ./testpdf
```

从启动日志中的私有输出目录读取access-url.txt并打开认证地址，再访问同源/tasks。研究问题直接填写；默认选择服务端目录的全部1–20篇PDF，客户端不能传本地路径。每任务预算默认3美元/90请求，启动合计6美元/180请求，同时执行一个任务；上限不是预计费用，可用--budget-usd/--run-budget-usd/--request-limit/--run-request-limit覆盖。确认预算后自动阅读、逐论断复核、有界补缺、完整表综合并交付，不需人工科研审阅。来源变更拒绝旧任务，创建新预览。

最终两不同问题各15字段/0程序缺口，共43请求/USD0.176891508；包含首版失败与纠正的开发总费USD0.358430952。自动检查不保证科研真值，没有新Motif收益/思考模式对照。输入/预算/收据/原生轨迹独立保留；旧agent.ts/8765的缓存与增量更新未移入此配置。免费复现 `node scripts/project.mjs python scenarios/literature-notes/check-web-pdf.py`，加--call-model会产生API费用。详情见[共享变更](../../docs/changes/literature-web-binding.md)、[验收记录](../../docs/experiments/literature-web-binding-20261012.md)。

# 科研文献场景：普通 PDF 证据与笔记

当前开发主线是普通 PDF，不要求 Zotero 或 Obsidian。第一版任务：围绕明确研究问题，读取选定目录中的论文，整理研究目标、方法、评价、发现、限制五类证据，生成可追溯的证据表和阅读笔记草稿。旧的合成批注场景保留为 Motif 协议回归。

2026-10-12修复：quote_spans/claim packet新增单citation_id，preview_research_notes/submit_claim_repair可直接引用该ID，Runtime解析成旧source/quote结构；未知、未读、跨论文/论断或源变化拒绝。阅读与修复场景启用成功产物收据守卫：最多2次同Session续接，不重置预算，不把“接下来读取”当交付。耗尽明确失败，仍可合法交付证据缺口。一次真实三论文任务15字段/18引文/0程序缺口，28请求/$0.07593；不保证科学正确或以后不会生成错误参数。[验证与失败](../../docs/experiments/receipt-fix-20261012-9c6d79d9.md)。

main官方Web入口已同步，当前开发目录保留在feature分支，本地main与origin/main一致。最终前端由本项目实现，暂时可复用Harness Web；普通PDF的动态问题/资料与Web每Session绑定尚未接完。当前SDK/Web思考模式固定off，尚未比较high。不要把界面选择或模拟诊断当真实模型验收。[接口/GitHub记录](../../docs/changes/literature-receipt-guard.md)。

## 直接使用：本地文献工作台

新增统一入口 `agent.ts`，需要 Node **22.18+**、现有 Python 环境与 Poppler。在仓库根目录启动：

```sh
node scenarios/literature-notes/agent.ts serve --port 8765
```

打开 <http://127.0.0.1:8765>，填写普通 PDF 文件夹和研究问题。默认不调用模型；勾选启用模型后，使用已经配置的 `DEEPSEEK_API_KEY` / `.local/deepseek.env`，经过现有 Harness 完成阅读和自动审阅。网页不收集或显示 Key。本次授权下默认总技术上限100美元，可以在表单降低；它不是预计费用。全部输入快照、原生轨迹、失败费用和交付文件留在 `.local`，原PDF不修改。

默认先逐论断核对当前句与最终所选引文（support_audit）：最多80字符，supported/revised须提交被最终连续引文覆盖的原文support_anchor；相邻内容必须正式补引用，不能只在推理时读过。每条最多2次同篇字面检索、3次6000字符补读，可一次按计划读取。仍无支持时明确撤回/留缺口。正常运行默认至多2轮：首轮支持复核，第二轮仅补未解决字段，已通过字段保持不变；无缺口时第二轮0模型调用。缺口续修仍默认1轮。不等待人工审阅；默认模型仍为Flash，更多审阅、补读、重试都有费用，没有整链降本证据。--audit-all保留旧盲重提取与120字符规则；它不是默认支持复核。

工作台直接交付五字段比较表、综合分析与Markdown笔记，自动执行来源核验和模型审阅，**不要求人工勾选、审阅或批准**。引文与物理页码、模型意见放在可展开区域。证据不足时标出缺口并交付已有结果；来源失效或费用记录不完整仍返回失败；额外修复未完成且账本完整时，明确警示并交付上一份来源核验稿，不能标为已修复。

完成状态为`delivered`或`delivered_with_gaps`，质量标签不表示科学结论已认证。完整结果可重放来源后缓存复用；自动交付后也建立逐字段来源依赖，无需Human审批。改动/新增PDF只重做对应字段，删除论文重新综合，问题、解析器、契约或工作流变化使相关字段失效；保留字段重放原文，不重复调用模型审阅。局部修复后读取当前整份证据表，只重写全局项目假设，避免综合分析只围绕最后一条论断。普通缓存和手写依赖图均不是learned Motif。旧`approve/revise`接口仅作兼容。

`repair --job <ID>`默认只修缺口；`--audit-all`显式全量重提取；`--audit-support`核对全部既有事实及最终连续原文依据；`repair --synthesis-only`只重新综合，字段全部保留。既有交付可用`index --job <ID>`免费来源重放并建立新版本依赖索引，随后`update --job <ID>`；付费动作仍需`--call-model`。本次接口/提交说明见[自动局部更新记录](../../docs/changes/literature-auto-incremental.md)，真实结果与限制见[实验记录](../../docs/experiments/targeted-repair-20261010.md)。

增量原生收据对应的`incremental_audit.synthesis_requires_review`现在明确传至工作台：资料删除即使没有新字段，默认自动审阅仍读取当前完整表重新综合；不以“修复字段数为0”保留旧全局判断。它只改变场景审计与协调，不是共享Motif接口。

真实内容变化对照入口`compare-source-changes.ts`复用`runWorkflow`，不另建模型循环。先在私有目录复制原论文，准备“新增实际论文→同名文件替换为另一篇实际论文→删除该条目”的四个不可覆盖语料版本。默认准备/预览不调用模型；同名替换不是作者修订版，也不能代替反证处理实验。研究问题去掉固定篇数，两个路线使用相同问题、模型及一轮字段审阅；全量重做和普通依赖缓存分别运行，不把手写缓存计作learned Motif。

```sh
# 生成新的私有实验和冻结协议；参数是你提供的两篇实际PDF的路径。
node scenarios/literature-notes/compare-source-changes.ts --addition /path/to/add.pdf --replacement /path/to/replace.pdf
# 查看上一步返回的实验目录；仍为0模型调用。
node scenarios/literature-notes/compare-source-changes.ts --experiment .local/literature-notes/source-change-<id>
# 已授权真实实验时执行；拒绝悄悄覆盖已开始的实验。
node scenarios/literature-notes/compare-source-changes.ts --experiment .local/literature-notes/source-change-<id> --call-model
```

记录原生job、全部阶段账本、端到端协调耗时、源重放、原样保留字段、旧来源句柄隔离及删除条目。质量等价不由这些机械检查自动签发；缺口和失败同样计入结果。

```sh
# CLI配置预览，无模型调用
node scenarios/literature-notes/agent.ts run
# 真实阅读 → 自动审阅 → 直接交付
node scenarios/literature-notes/agent.ts run --call-model --budget-usd 100
# 指定论文文件夹、问题（可以使用绝对路径）
node scenarios/literature-notes/agent.ts run --papers-dir testpdf --question "这些论文的方法与证据有何差异？" --call-model
# 按已有任务更新；不带call-model时仅预览
node scenarios/literature-notes/agent.ts update --job <任务UUID> --call-model
# 针对已有稿自动补证据/修复；保留旧任务及费用
node scenarios/literature-notes/agent.ts repair --job <任务UUID> --repair-rounds 2 --call-model
# 模型最后只给出完整JSON、没有提交时，离线验证提案；0新模型请求
node scenarios/literature-notes/agent.ts recover --job <任务UUID>
# 关闭新增修复轮用于对照；默认1轮，最多2轮
node scenarios/literature-notes/agent.ts run --repair-rounds 0 --call-model
# 禁用结果缓存，明确重新生成；或者只阅读而暂不自动审阅
node scenarios/literature-notes/agent.ts run --refresh --call-model
node scenarios/literature-notes/agent.ts run --no-model-review --call-model
node scenarios/literature-notes/agent.ts status --job <任务UUID>
# 旧版完整结果重新核验来源后按新策略交付；保留旧任务，0新模型请求
node scenarios/literature-notes/agent.ts deliver --job <旧任务UUID>
```

高级 `--manifest` 接入现有 **PDF pin→read** 库，模型仍由原 Harness 执行，计数只接受成功原生结果。该库与 `literature_evidence` 的提取→核验→组包库不同，不能互换；工作台默认 baseline，因为现有试验没有稳定的 Motif 净成本优势。做机制对照须加 `--refresh`，不能把缓存的0请求算Motif收益。

单次读取第一层1–20篇PDF，每篇最多64MiB/500页；扫描版只报告低文本缺口，尚无OCR。当前是本机开发版，不包含联网文献发现、批注写回、知识库同步或自主科研判断验收。仅在本机地址监听；POST校验Host、Origin和页面会话令牌，不提供公网部署/多用户鉴权。Node原生TypeScript提示不会阻止运行；没有引入新的npm依赖或改变共享启动脚本。

[真实三论文工作台验证与质量边界](../../docs/experiments/agent-workbench-20261010-c2d37352.md)，[本次场景接口与GitHub提交说明](../../docs/changes/literature-workbench.md)。

参考如何落地、哪些仍待学习与最简单基线见 [参考设计](reference-design.md)。新增工具/配置与GitHub记录见 [逐论断修复变更](../../docs/changes/literature-claim-repair.md)。

## 总体流程与第一条证据准备链

[总体流程与候选 Motif 契约](workflow-and-motifs.md) 对齐了现有代码、模型判断边界、三个候选续接与未来接口缺口。第一条新链为：模型选择并批准阅读窗口 → 提取 → 重放校验 → 组装原文证据包 → 交回模型。它不会替代论断支持审阅。

`pdf_evidence_tools.py` 复用现有 PDF 解析和来源窗口实现；每个步骤使用本次服务签发的专属凭证，绑定任务、所有选定 PDF、解析器 profile、工具实现及契约。模型先register_reading_plan登记批准的长计划，取得短plan_id，再用它作为extract_evidence_windows的plan参数。最多6窗、每窗6000字符、总12000字符。未批准、越界、来源变化或低文本不能取得下一阶段成功凭证。只是机械文本质量检查，不代表解析语义、相关性或科学解释正确。

```sh
# 预览，无密钥、无模型请求
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py
# 真实三篇 PDF / MCP / Harness / 预算代理免费验收，模拟 Provider
node scripts/project.mjs python scenarios/literature-notes/check-evidence.py
# 正常真实模型轨迹；依旧复用已有密钥和预算入口
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --call-model --budget-usd 100
# 普通程序合并对照；内部执行完全相同的三步检查
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --script-chain --call-model --budget-usd 100
# 从两条正常训练轨迹及一条不同决定的认证轨迹学习三节点链
node scripts/project.mjs python scenarios/literature-notes/learn-evidence.py --split .local/<实验>/split.json --output .local/<新学习目录>
# 新 v2 库：原生插件在线免 embedding 续接核验与组装
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --mode execute --manifest .local/<学习目录>/online-manifest.json --call-model --budget-usd 100
node scripts/project.mjs python -m pytest tests/test_literature_pdf_evidence.py -q
```

上述100美元是用户此前授权下沿用的技术上限，不是预期费用；每轮真实请求、失败和回退保留账本。普通入口默认预览、0.25美元默认保护。三节点学习复用共享编译器，训练目录必须为 `.local/runs/` 中真实 baseline、非脚本轨迹；`evidence-structural-review.json` 绑定 packet 和事件摘要并明确 `structural_chain_safe=true`。审阅仅验证机械来源，可学习参数传递，不能认证论文理解。独立问题仍可能来自同一已知语料，不宣称跨语料泛化。

现在可免费生成该机械review：`node scripts/project.mjs python scenarios/literature-notes/review-evidence.py --run .local/runs/<真实baseline>`。它重放当前来源，检查实际连续成功许可及参数，拒绝模拟/脚本/Motif训练、旧包版本和不同已有review；不要求Human审批，不审阅论文结论。随后按原入口从两训练/一独立问题认证轨迹学习，不能给旧轨迹补造许可或把错误版本强制升级。

上轮执行版本/profile v3下重新学习/认证已完成，实际三轮每组6/4/4请求、包逐字相同、Motif每次2验证skip。Motif均值比脚本贵约1.68%，含启动均值10.809/10.870秒几乎相同，学习费尚未摊平；工作台默认不切换为Motif。详见[重新认证及负面结果](../../docs/experiments/motif-renew-20261011-14c3fc42.md)和[提交说明](../../docs/changes/literature-evidence-renewal.md)。本轮阅读归一化更新了执行版本，旧库不能直接认作当前认证，须重新验证/认证。这是证据准备组件对照，不能认证整份论文理解或完整Agent净收益。

阅读计划现在按实际页尾和重复/重叠范围归一化，保持全部选定原文；真正超限仍拒绝。`read_pdf_evidence_plan.normalization.requested_to_contexts`对应原窗口与归一化上下文，不能猜引用ID或假设返回数量不变。会话内原文缓存仍先检查源版本。它们是普通程序优化，verified skip=0。

工作台任务结束自动生成私有 `decision-log.json`，关联原生选页、失败、usage和费用；没有明说的理由不推测，不可把派生诊断当Motif训练轨迹。免费重建：`node scenarios/literature-notes/agent.ts decisions --job <UUID>`。相同配置的核源复用已验证0模型调用；复核轮数不同可能触发付费全量任务。真实失败和误触发费用均保留，见[开发验证](../../docs/experiments/plan-efficiency-20261011-4ebe9910.md)、[接口与GitHub提交说明](../../docs/changes/literature-plan-efficiency.md)。

在线续接已实现：共享 Runtime 增加独立 `approved_plan_continuation` 守卫，绑定当前用户任务、已注册计划、完整 schema、版本和真实工具许可链；成功结果复核后才计入跳过。新库用 manifest v2，旧库保持 v1。没有扩大 `read_pinned` 特例、改名工具或伪造 embedding。具体共享字段、兼容与 GitHub 正文见 [变更记录](../../docs/changes/approved-plan-continuation.md)，权威接口见 [interfaces](../../docs/interfaces.md)。

当前学习产物在 `.local/literature-notes/approved-continuation-20261010-94934aab/learned/`：两条真实训练 + 一条不同问题留出认证。新问题真实在线交付3窗证据包，6次模型请求、2次验证跳过、0 embedding；[实验记录](../../docs/experiments/approved-continuation-20261010-94934aab.md) 保留全部请求、失败和边界。此前 `evidence-chain-20261010-ab70695f` 的无许可轨迹/库及回退记录保留为历史，不给旧记录补许可。

```sh
# 此路径是本机实验产物，不随 Git 分发；其他机器先按 split 收集并学习自己的库。
node scripts/project.mjs python scenarios/literature-notes/check-evidence.py --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --mode execute --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json --call-model --budget-usd 100
```

同一固定计划的免费三组实际 Harness/MCP 检查为9/7/7模拟请求，三个包逐字一致，Motif验证跳过2次。普通脚本也合并了两步；**尚无超越普通脚本的成本证据**，不把协议测试算科学质量或真实费用收益。公共 CLI 仍要求本机 embedding 配置，场景用拒绝请求的诊断端点；新许可路径实测不请求它。

交付目录含 `evidence-input-snapshot.json`、`evidence-packet.json`、`evidence-packet-receipt.json`、`evidence-delivery.json`，并保留共享 Runner 的 manifest、events、metrics 和 ledger。快照新增共享代码/策略/manifest摘要。正常模型最终回复不能替代成功工具收据；收据回收再次逐窗口重查来源。`--script-chain` 是普通程序基线，尚未实测 Code Mode 自主生成程序。共享许可接口已按用户授权修改；预算算法、上游 Harness、依赖版本和用户 PDF 未修改。legacy 内联计划可手动执行但无自动许可。

## 普通 PDF 入口

### 同计划对照与结果缓存

新增 `compare-evidence.py` 从真实原生成功运行提取模型批准的计划，固定相同任务/提示/工具/窗口，在独立会话轮换 Harness、普通脚本、Motif 三组。默认3轮、只预览；追加 `--call-model` 才付费。每个失败费用保留，记账缺失立即停止，不做未登记的整轮重试。原始来源和学习库仍为私有输入。

```sh
# 本机实例；默认无模型调用。其他机器换成自己的成功运行和认证库。
node scripts/project.mjs python scenarios/literature-notes/compare-evidence.py --plan-run .local/runs/8aab1d0e52ef4e6cb222c1e5ffafa0a6 --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json --budget-usd 100
# 固定批准计划的单次预览；已有 .local/<实验>/frozen-plan.json。
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --question '计划绑定的同一研究问题' --frozen-plan .local/<实验>/frozen-plan.json
# 完全相同请求的结果缓存基线：无模型入口，不读取 Key；核验不通过则拒绝复用。
node scripts/project.mjs python scenarios/literature-notes/reuse-evidence.py --plan-run .local/runs/<成功运行ID> --question '该计划的研究问题' --frozen-plan .local/<实验>/frozen-plan.json
```

`--frozen-plan` 只接受 `.local` 中私有常规 JSON 文件，绑定当前问题/来源，必须明确允许机械续接；collector 拒绝输出另一个计划。普通入口不传此参数时仍由模型选页。`--training-cost-usd` 与 `--training-cost-source` 可在对照中记录历史训练开销，不挤入本轮执行费用或隐去摊销。

真实三轮对照已完成：每组证据包一致，Harness/script/Motif 每次6/4/4请求，均值运行8.791/7.803/6.636秒；Motif费用较脚本只低约1.8%，第三轮更贵，不能宣称稳定降费。完全相同任务的缓存基线0请求；新问题/计划/来源不复用。详见 [全部运行、费用与限制](../../docs/experiments/frozen-evidence-20261010-997d9e47.md)。当前只有三篇已知论文、一个固定计划，科学支持仍未认证；[扩展验收方案](../../docs/experiments/literature-evaluation-protocol.md) 规定先分层验收、按整篇/项目留出，再比较同质量总成本。

默认读取项目根目录 `testpdf/`；支持中文文件名和大小写 PDF 后缀，范围是目录第一层的 1–20 个 PDF，每个最多 64 MiB、500 页。原始论文仅被读取；缓存、快照和结果放在 Git 忽略的 `.local/literature-notes/` 或 `.local/runs/`。不要提交 `testpdf/` 中的用户论文。

复用现有 Python/Node 环境和 Harness。外部解析工具需要 Poppler 的 `pdfinfo`、`pdftotext`；本机已安装，其他平台需自行安装 Poppler。新增回归生成公开的微型 PDF，不依赖三篇用户论文；无 Poppler 的环境明确跳过解析测试。

在仓库根目录执行：

```sh
# 预览真实 PDF 任务、工具和预算，不读取 Key、不调用模型
node scripts/project.mjs python scenarios/literature-notes/run-pdf.py

# 免费验收：真实 PDF + MCP + Harness + 预算代理，Provider 为本机模拟
node scripts/project.mjs python scenarios/literature-notes/check-pdf.py

# 场景回归
node scripts/project.mjs python -m pytest tests/test_literature_pdf.py -q

# 显式启用真实 DeepSeek，预算上限 0.25 美元、32 步、8000 输出 token
node scripts/project.mjs python scenarios/literature-notes/run-pdf.py --call-model
```

默认问题：这三篇论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？可以使用 `--papers-dir /path/to/pdfs --question '你的研究问题'`。`--budget-usd`、`--max-steps`、`--max-output` 会传给现有受预算代理保护的运行入口，默认 reasoning effort 为 off、无压缩。Key 继续使用 `.local/deepseek.env` 或 `DEEPSEEK_API_KEY`，解析逻辑复用原 `run-live.py`，值不进入命令参数或快照。

真实模型运行结果在 `.local/runs/<id>/`，包括原有 answer、metrics、cost-ledger、agent-events，加上 `pdf-input-snapshot.json`、`pdf-delivery.json`。模型成功调用预览工具后还生成 `evidence.json` 和 `research-notes.md`；若没有校验成功的工具结果，入口以 `missing_preview` 报告并返回非零，不能只因模型宣称完成就通过。存在未提取字段时交付状态为 `needs_review`，引文位置检查通过也不证明观点支持关系或科研质量。

## PDF 工具与复用边界

- `list_pdfs`：提供冻结选择、真实文件哈希、用户研究问题；不根据文件名筛选相关性。
- `prepare_pdf`：解析全部物理页并提供索引；缓存键含 PDF 内容摘要与实际解析器版本。`--cache-policy off` 禁用跨进程磁盘复用，`reuse` 启用；两者都保留本次执行内的材料复用。它是解析缓存基线，不是学习得到的 RSI。
- `search_pdf_text`：跨页面字面检索，提供定位片段；没有匹配不等于论文没有报告某概念。
- `pin_pdf_context` / `read_pinned_pdf_context`：固定明确选择的页和字符窗口，句柄绑定 PDF、页面文本、解析器版本；长页返回继续读取的偏移，旧来源拒绝。
- `preview_research_notes`：核验每条引文是否属于该论文、是否来自本次实际读取窗口，再渲染证据表与逐篇笔记。保留明确缺口；不判断语义支持、不写回用户文件。

低文本页面标记为待检查，不能直接当作空白页或扫描页。第一版未接 OCR、图像/复杂表格理解、论文 DOI 核验及原笔记增量合并。文件哈希标识文件版本，不识别同一论文的不同学术版本；当前 paper_id 绑定所选目录中的文件名。

`pin_pdf_context` 的 MCP `page` 参数为正整数十进制字符串（如 `"2"`），适配现有在线 IR 的字符串定位接口。来源句柄仍绑定确切的页、字符窗口、文件内容和解析器版本。在线守卫使用文档版本摘要，服务内再检查窗口摘要，不能用文档版本替代精确来源绑定。

`pdf-contracts.json` 与 `pdf-version-fields.json` 连接现有离线编译和在线插件。`learn-pdf.py` 从两条不同研究问题的原始 baseline 轨迹挖掘 pin → read 参数边，再以第三条不同问题轨迹认证，导出 library/manifest 并用权威 Node Runtime 校验。2026-10-10 已学习 1 个真实 PDF 只读 Motif，后续三篇论文对照中验证跳过 2 次模型请求。认证只覆盖参数依赖和只读版本守卫，不认证科研陈述，也不是完整递归自我改进。

默认窗口可由 Runtime 自动续读；显式自定义窗口仍会回退模型。页面选择、关联性和论断支持关系保持语义判断。未知句柄、文件/解析器变化、未读来源、错误引文 ID 均拒绝。引文可用 `{source_id, quote_id}` 引用服务签发的连续片段，服务复制原文；片段连续匹配不代表支持陈述。大草稿写入私有工件，工具返回哈希收据，入口检查位置、哈希与任务绑定，避免完整 JSON 被 Harness 大输出截断。

## 真实学习与三组对照

所有调用复用原 Harness、预算代理、MCP 和在线插件，未修改共享核心。先审阅 baseline，在原运行目录保存绑定 evidence/events 摘要的 `quality-review.json`。划分文件是私有 JSON：两个 `train` 和一个 `certify`，每条有 `run`、`decision_id`。科研草稿不合格时，可以认证已经核对安全的只读参数边，但不能据此声称科研质量或合格总成本通过。

```sh
node scripts/project.mjs python scenarios/literature-notes/learn-pdf.py \
  --split .local/literature-notes/pdf-motif-final-20261010/split.json \
  --output .local/literature-notes/new-pdf-library

node scripts/project.mjs python scenarios/literature-notes/compare-pdf.py \
  --manifest .local/literature-notes/new-pdf-library/online-manifest.json \
  --budget-usd 100 --max-output 5000 --max-steps 48 \
  --question '科研 PDF 内容或工具版本变化后，哪些阅读笔记和执行步骤可以复用，哪些必须重新验证？依据三篇论文给出保守的增量更新与来源追溯策略。'
```

学习输出目录必须尚不存在；重复实验创建新目录，保留原始记录。`compare-pdf.py` 顺序运行 baseline、Motif execute 和普通脚本模式（pin 直接返回 read 结果），三组都启用同样的解析缓存。固定同一问题、提示、六工具 schema、模型和步数/输出额度；端到端启动耗时包括预检和执行，不包含离线学习与审阅。闭合来源读取不使用 embedding，实际调用会被实验端点拒绝并统计请求数。

用户已撤回此前自设的本轮 0.25 美元上限；本机后续实验显式使用共享入口现有的 100 美元技术上限，实际费用仍逐次记账。`run-pdf.py` 默认仍是预览，默认 0.25 美元保护可通过 `--budget-usd 100` 调整。API Key 本身不能取消服务商并发限制。此前的后续 429 来自本地预算预留拒绝；已区分账本记录的服务端 429 与本地拒绝，只对确认的服务端 429 做有界整轮重试，失败/恢复费用全部保留，不能靠等待解决本地预算不足。

当前结论见 `quality-experiment.md`：三组均完成结构/来源预览，但原始科研草稿仍需修订；普通脚本在这次对照中请求最少、耗时最短，Motif 费用略高于 Harness。没有人类专家盲评或质量等价证据，不能宣称 Motif 比普通脚本更划算。

## 免费验收的含义

`check-pdf.py` 创建独立新缓存，比较冷解析与新进程读缓存的页面一致性，核验实际 stdio schema，使用真实 Harness 和三篇 PDF 走完引文/草稿协议。模拟 Provider 只选择首页片段，其字段和输出明确写为协议检查；不是论文分析，不作为科研交付。模拟 usage 只检查预算链路，不用于真实费用或端到端提速结论。

## 保留的合成批注场景

最小任务：固定一个明确选择的批注变化，读取论文页与指定笔记，核对引文位置，然后生成证据区的更新差异。只使用公开合成快照，不访问 Zotero、Obsidian 或用户论文，不写用户文件。论文页已经提取为文本，尚未接入 PDF 解析。

## 免费运行

在仓库根目录、完成现有依赖安装后：

```sh
# 普通入口只预览配置，不调用模型
npm run scenario -- --scenario scenarios/literature-notes/scenario.json --case eval_leakage

# 真实本地 Harness + stdio MCP + Motif + 预算代理；上游仅为回环模拟服务
node scripts/project.mjs python scenarios/literature-notes/check.py

# 场景守卫和完整协议回归
node scripts/project.mjs python -m pytest tests/test_literature_notes.py -q
```

验收输出写入新的 `.local/literature-notes/<run-id>/`。末尾 JSON 给出更新预览 `preview.diff` 和运行配置 `runtime-snapshot.json` 的路径。目录另含 library、online manifest、学习来源锁，以及每次运行的题面/来源摘要、Harness 原始事件、结果、预算账本、Motif 审计和指标。原始日志不提交。

`check.py` 只连接它创建的回环模拟服务，使用独立 DSH_HOME 和假凭证，不读取云模型密钥。模拟 usage 验证预算计数和缓存字段传递，不能用于推断真实费用。不要为本验收添加 `--call-model`；通用入口的该参数会启用实际云模型。

## 填写 Key 后进行真实模型联调

本机私有文件 `.local/deepseek.env` 已准备好，填写其中的空引号即可：

```sh
export DEEPSEEK_API_KEY=''
```

该文件被 Git 忽略，权限设为 0600。新的场景入口把它作为数据读取，不执行文件内容；也支持已有的 `DEEPSEEK_API_KEY` 环境变量，环境变量优先。无需手动 source，Key 不进入命令参数和配置预览。

在仓库根目录运行：

```sh
# 无 Key 也可以预览；不调用模型
node scripts/project.mjs python scenarios/literature-notes/run-live.py

# 填写后，离线检查配置；不显示 Key，不验证远端鉴权
node scripts/project.mjs python scenarios/literature-notes/run-live.py --check-key

# 明确启用真实 DeepSeek；每次上限 0.25 美元记账预算、8 步、2000 输出 token
node scripts/project.mjs python scenarios/literature-notes/run-live.py --call-model
```

首次真实联调使用 baseline 和同一个合成只读任务，继续复用仓库现有 Harness、工具白名单、预算代理和日志入口。结果位于 `.local/runs/<run-id>/`。Key 未填写会在创建 Harness 和联网之前停止。

这个入口不自动启动付费实验，也不把模拟轨迹学到的 Motif 当成真实模型收益证据。它仍用于旧合成场景；Zotero/Obsidian 未接入，普通 PDF 解析和真实模型实验使用本页开头的 `run-pdf.py`。

## 现有接口复用

- 配置与工具白名单：`prepare_scenario` 和现有场景守卫。
- Agent 循环与派发：`create_harness` 和安装的 DeepSeek Harness。
- 预算：`NativeBudgetGuard`、`deepseek_cost_gate.State/create_server`，每组上限 0.25 美元记账预算、8 步、2000 输出 token。全部调用是本地模拟，实际支出为零。
- 学习：原始 Harness 工具事件 → 参数来源推断 → witnessed-edge 挖掘/编译 → 独立合成案例认证 → library → online manifest。
- 在线执行：原生 `dsh_online_motif.mjs` 插件。没有修改共享核心、上游 Harness、预算代码或依赖。

## 工具与结构边界

| 工具 | 责任 | Motif 资格 |
| --- | --- | --- |
| `pin_annotation_change(change_id)` | 仅固定任务明确选择的变化，返回整个依赖快照的句柄与版本 | 认证边的起点 |
| `read_pinned_annotation_context(source_id)` | 读取该句柄的批注、页面和笔记；检查所有依赖版本 | 学到的唯一只读延续 |
| `preview_note_update(source_id)` | 核对引文、保留用户内容、生成归因引文预览或明确缺口 | 本次不授权 Motif 接管 |

句柄由服务签发，并绑定批注、论文页、笔记、任务与对象选择的完整快照。缓存命中仍先校验版本。这里的 `paper_sha256` 是合成页面快照摘要，不是原始 PDF 文件摘要。

Motif 只跳过一次读取上下文前的模型请求，不选择论文、不决定论断支持关系、不自动更新笔记。`preview_note_update` 是手写确定性工具，不能算成 RSI 学到的代码。它在契约中标记 `replay_stable: false`，不进入在线认证工具集；本次没有为它提供可挖掘的参数来源边。

定位错误、笔记未明确选择、证据区缺失/重复、已有同 ID 批注需要更新时，返回 `needs_review` 和 `gap`，不产生补丁。不把重复批注当作已经正确同步。当前只完成机械引文定位，不评估引文是否支持某个科研论断。

## 学习与验收

`train_seed`、`train_protocol` 是两项合成训练案例；`certify_cost` 单独认证；`eval_leakage` 是后续协议验收案例。案例身份由显式配置定义，并冻结题面与事件摘要。这是独立的合成输入划分，不是经人工审阅的真实研究决定。

图边来自三次实际 SDK/MCP 执行轨迹，不预写 DAG，也不替换历史库工具名。模拟 Provider 的固定动作序列只用于走通协议，不代表模型自行发现了科研结构。

验收要求四组获得完全一致的预览与来源，均执行三次工具调用：

| 模式 | 本地模拟模型请求 | 验证后的跳过 |
| --- | ---: | ---: |
| baseline | 4 | 0 |
| shadow | 4 | 0 |
| execute | 3 | 1 |
| execute / 旧版本 | 4 | 0 |

闭合的来源读取不需要 embedding 请求；配置保留现有插件要求的本地 endpoint，若实际调用该 endpoint，验收失败。每组完成后耗尽记账额度，额外请求必须被现有代理以 429 拒绝，且不得到达模拟上游。

这些结果只支持协议、参数来源、版本回退和预算链路可用。不支持真实费用下降、科研质量提升、完整递归自我改进或跨应用场景已完成。

## 下一步与共享接口

普通 PDF 主线下一步优先增加论断支持审阅和增量依赖失效测试，再验证更长的可执行路径是否比普通脚本更有价值。写入知识库仍需补丁预览和业务授权；真实应用版本、附件内容哈希和任务依赖不能用旧合成快照规则替代。

本次所需共享接口变化：**无**。若后续要让 Motif 自动选择跨对象后继、执行更新预览或写入，须先列出在线契约、版本关系和授权协议的具体变化，再修改共享核心。

## 独立论断支持审阅

对已有普通 PDF 草稿进行审阅，复用现有 Harness 和预算入口，不重跑原始文献分析：

```sh
# 仓库根目录；先配置预览，无付费调用
node scripts/project.mjs python scenarios/literature-notes/review-pdf.py --run .local/runs/<原始运行ID>

# 已授权真实模型时，启用语义审阅；沿用私有 Key 加载
node scripts/project.mjs python scenarios/literature-notes/review-pdf.py --run .local/runs/<原始运行ID> --call-model

node scripts/project.mjs python -m pytest tests/test_literature_pdf_review.py -q
```

三个审阅工具分别读取原始陈述与精确引文、补读同篇冻结来源、提交逐字段审阅与项目假设。补读可选原始 source_id，或显式 page 字符串与 start，两者互斥。支持关系由模型审阅，Runtime 只验证来源、版本、已读权限与结构；数字字面检查不是语义证明。新记录在私有 `claim-reviews/<ID>/`，原始 evidence 与事件不覆盖。

只有原始 Harness 事件中真实 submit 收据、路径/哈希/任务一致及当前来源未变，才回收修订笔记；单独存在的输出文件或模型最后声称成功都不算。启动前验证收据提取契约，离线回收故障不需要重新调用模型。模型稿标记 `model_reviewed_human_unverified`，不能作为领域专家盲评或质量等价验收。

本次三组已另存 Codex 来源核对稿和原始/自动/最终陈述的对照审阅；查看 `.local/literature-notes/claim-reviews/source-checked-index.md`。每组 15 字段、18 精确引文，项目复用策略仍是未验证假设。新增补读 API 与提示做了免费验收，最新版本未额外付费评测；当前三次付费审阅仍漏检若干语义问题。具体费用、质量边界和复现记录见 `quality-experiment.md` 的最后追加节。

## 普通 PDF 的增量更新入口

当前已跑通：已有来源审阅 → 编译依赖 → 输入变化 → 只重做受影响字段 → 独立来源审阅 → 再次复用。仍只输出私有预览，不写用户 PDF 或知识库。

`pdf_dependencies.py` 离线编译 PDF→解析→精确引文→论断→笔记→综合分析。`pdf-incremental-policy.ts` 是场景内 TypeScript 守卫，判断版本与审阅撤回；Python MCP 调用它，不新增 Python Agent 循环。已在 Node 22.22.2 / Python 3.12 / macOS arm64 验证；Node 20 不支持此直接执行方式，其他平台尚未验证本新增场景。

此段为遗留独立来源审阅图入口：只有明确的 Codex 来源核对稿及逐字段记录可以编译；普通模型稿和仅通过引文定位的草稿拒绝。审阅文件是受信任本机输入，不提供评审者身份鉴别或专家质量认证。依赖图须在基线文件仍可核对时冻结；之后即使原始目录被修改，仍能识别变化。新版本、新问题、新语料选择、新解析器或工具契约、审阅撤回使相应路径失效；该遗留路线在语料选择变化时保守复核全部既有论断。当前 `agent.ts` 的自动来源绑定图另有策略：逐篇事实绑定各自来源，新增论文保留来源未变的旧字段、重做新论文及跨论文综合，不继承科研真值认证；不实现新反证对旧解释的语义影响自动判断。

2026-10-12 第一阶段已运行首次比较、单字段缺口修复和两篇到三篇的资料更新。`node scenarios/literature-notes/run-phase-one.ts` 默认准备私有协议，显式 `--experiment .local/<目录> --call-model` 执行；原始结果存在时拒绝覆盖。定向支持修订可用 `repair-selected.ts`，来源意见经 `repair-pdf.py --source-feedback` 绑定当前稿和目标集合。两条语义反例与追加修复费用保留；无人工审批。见 [任务协议](phase-one-protocol.md)、[真实实验](../../docs/experiments/phase-one-20261012-8a865a78.md)、[提交说明](../../docs/changes/literature-phase-one.md)。这些入口复用既有 Harness/脚本，不是新 learned Motif。

在仓库根目录执行：

```sh
# REVIEW 含 source-checked-evidence.json 和 source-check.json；RUN 含 pdf-input-snapshot.json。
node scripts/project.mjs python scenarios/literature-notes/compile-pdf-dependencies.py --review .local/<REVIEW> --run .local/<RUN> --output .local/<新图>.json

# 只查看计划，不加载 Key 或付费。
node scripts/project.mjs python scenarios/literature-notes/run-incremental.py --dependencies .local/<图>.json --papers-dir testpdf

# 授权交付：无变化走确定性来源复核，有变化才调用原 Harness / 预算入口。
node scripts/project.mjs python scenarios/literature-notes/run-incremental.py --dependencies .local/<图>.json --papers-dir testpdf --call-model

# 撤回文件恰好为 {"revoked_claim_ids":["claim:<paper_id>:<field>"]}。
node scripts/project.mjs python scenarios/literature-notes/run-incremental.py --dependencies .local/<图>.json --papers-dir testpdf --revoked-claims .local/<撤回>.json

node scripts/project.mjs python -m pytest tests/test_literature_pdf_incremental.py -q
```

新内容必须在本次会话读取当前 PDF 后引用；模型不能覆盖保留字段或遗漏失效字段。服务端原样合并保留内容，并重新核对精确引文。发布前及回收时重查任务、来源、契约、撤回状态与收据，防止执行中变更。新模型内容保留 `model_draft_pending_independent_support_review` 状态；`preview` 不代表语义验收完成。再次编译须用独立核对后的派生稿，不能把模型自称 supported 当成既有审阅。场景代码/清单改变契约后须重新核对并编译，不覆盖旧图。

新增手写依赖规则与字段缓存不称为已学习的 RSI。现有已认证 pin→read Motif 可选叠加：使用 `--mode execute --manifest <已认证manifest> --embedding-endpoint <本地/v1/embeddings> --embedding-model <配置名>`。闭合读取实际不请求 embedding，接口参数依旧保留。`compare-incremental.py` 执行小规模对照；计划、变动副本与原始费用全部在 `.local/`。普通增量默认不加载 Motif，因为本次普通增量更便宜。

## 精选科研 skills 与工具复用

复用 K-Dense-AI/scientific-agent-skills 固定 commit `92ace75ac21efe19a620434e0ca4e356081fe807` 的 literature-review、citation-management、scientific-critical-thinking。三份原说明仅作来源归档（`UPSTREAM.md`），不是自动启用的全套技能；`research-checklist.md` 是本地 PDF 的最小改写清单，拼接到普通和增量提示，不引入搜索、临床评分、绘图 API 或新数据库。

MIT 许可证、原文件哈希和路径保存在 `vendor/scientific-skills/`。`preview_bibliography(bibtex)` 复用标准库解析和格式化代码，预览嵌套花括号、DOI 规范化、疑似重复和缺失元数据；不自动合并冲突条目、不覆盖输入、不认证学术身份或观点支持。上游会跳过部分不支持/损坏语法，因此保留未解析余项和警告，只供预览。当前没有从 PDF 自动推断 DOI。

## 固定审阅校准与撤回验收

`pdf_acceptance.py` 是离线验收器，不新增 Agent 循环或模型自动认证。先从绑定原始草稿的独立来源审阅冻结案例，再运行现有 `review-pdf.py`；参考答案不拼入提示。`revised` 仅说明答案发生改变，不能算已发现或已修复语义错误。独立逐字段判断和综合分析核对都通过、且无交付缺口，才给出来源核对层面的质量通过；仍不是专家盲评。

```sh
node scripts/project.mjs python scenarios/literature-notes/pdf_acceptance.py prepare-review --run .local/runs/<原始ID> --reference .local/<来源审阅>/source-check.json --output .local/<新实验>/calibration.json
node scripts/project.mjs python scenarios/literature-notes/review-pdf.py --run .local/runs/<原始ID> --call-model
node scripts/project.mjs python scenarios/literature-notes/pdf_acceptance.py score-review --calibration .local/<实验>/calibration.json --review .local/literature-notes/claim-reviews/<新ID> --output .local/<实验>/verdicts.json
# 独立核对须绑定 calibration、claim-review 和 revised-evidence 的摘要，逐条给出理由，并核对 synthesis。
node scripts/project.mjs python scenarios/literature-notes/pdf_acceptance.py score-review --calibration .local/<实验>/calibration.json --review .local/literature-notes/claim-reviews/<新ID> --adjudication .local/<实验>/source-comparison.json --output .local/<实验>/quality.json
node scripts/project.mjs python scenarios/literature-notes/pdf_acceptance.py check-revocation --dependencies .local/<旧图>.json --revoked .local/<撤回>.json --run .local/literature-notes/incremental-runs/<ID> --output .local/<实验>/revocation-check.json
node scripts/project.mjs python -m pytest tests/test_literature_pdf_acceptance.py tests/test_literature_pdf_review.py -q
```

撤回的是旧审批资格，不是自动断言论断为假。验收要求失效集合恰为指定字段及其下游，其他字段与引文原样保留；新字段由当前证据重处理，语义质量单独评审。当前用 11 条已知问题与 4 条对照校准，非独立留出测评。实际撤回 1 条后 14 条保留，模型新句仍漏主体引文，另存 Codex 补引文稿；不能说模型一次合格。

最新私有实验在 `.local/literature-notes/acceptance-20261010/`；当前来源核对图为 `revocation-dependencies-current.json`。用该图在 `testpdf/` 无变化运行，15 字段可零调用复用。`pdf_dependencies.py` 已将数值检查实现 `pdf_review_tools.py` 纳入契约摘要；旧图应因契约变化复核，历史图与输出保留。数值检查识别常见中文小数，防止“三点七”绕过，但不能认证数值单位、范围、主体或科学真值。

保持 Poppler；Docling/OCR 和 PaperQA 尚未安装或验证。它们是后续按需组件与独立基线，选型建议不等于已接入功能。此前增量/审阅实现没有改共享接口；本轮证据准备续接的共享变化见前述变更记录。


## 2026-10-11：批量证据读取与双栏修复

`prepare_pdf`现在返回字面章节导航。模型选择物理页窗口后，可用`read_pdf_evidence_plan(paper_id,document_version_sha256,windows)`一次实际读取：最多8窗/36000请求字符、每窗最多12000。修复工具`read_claim_evidence_plan`同篇、同论断、至多3个6000字符窗口，共用原读额度。Runtime检查版本、范围和已读凭证；不决定科研相关性。这是普通脚本执行基线，不是新增learned Motif。

解析profile升级v3，保守修复明确宽幅双栏散文块的行交错；修复页使用bbox词元，旧plain-text偏移不可继承。数字表格、窄栏、跨栏歧义不强行修复，不做OCR/通用布局认证。旧源句柄、依赖和对应旧Motif认证需重新取得，不能强制命中。

可选几何提取器异常时保留已成功的普通文本，显式返回布局未验证状态；普通解析或页数不对仍拒绝。批量读取先验证整计划，内部内存读取复用请求隔离的来源快照，返回前重新检查PDF，不免除变更检测。

support_audit的anchor必须来自最后选中的连续原文，且到真实句末标点。不能给截断原文补句号；需实际补相邻引文、换更短完整事实或留缺口。标点只作边界检查，仍不认证科研支持。当前三论文结果和首版批量慢的反例均见下方实验记录。

`node scripts/project.mjs python scenarios/literature-notes/check-read-plan.py --job <UUID>`可免费比较某个实际运行的多窗计划：普通并行pin/read与批量MCP交替四轮，要求逐字相同上下文。仅测暖机MCP开销，不能当作模型理解、整任务降本或learned Motif收益；版本变化时拒绝复用旧计划。

支持复核默认Flash。`repair-pdf.py --run <冻结输入> --model deepseek-v4-pro --call-model`可显式试Pro，但已观察截断和更高费用，不能预设更可靠。共享入口`--model deepseek-pro`旧别名现映射到官方`deepseek-v4-pro`；预览记录requested_model与实际model，已有预算表不改。

[GitHub提交说明](../../docs/changes/literature-read-plan.md)包含共享入口、场景契约、失效与回退；[真实实验与费用](../../docs/experiments/read-plan-20261011.md)保留所有失败和质量反例。0技术缺口、原文anchor和数字/技术名匹配都不认证中文推断、单位、条件或科研真值。

## 增量工作清单入口 Motif（显式实验）

已有依赖图决定哪些旧字段可按来源复用，原Harness决定新增事实。新候选只学习“读当前计划→准备所有受影响PDF→交回模型”，不学习结论、选页或科学支持。原首次阅读入口不能加载到这条路径。用两个不同工作量的普通原生增量任务训练，另一个任务独立认证：

```bash
node scripts/project.mjs python scenarios/literature-notes/learn-incremental.py --split .local/<实验>/split.json --output .local/<实验>/learned
node scripts/project.mjs python scenarios/literature-notes/check-inventory.py --task .local/literature-notes/incremental-runs/<原生ID>/task.json --incremental-run .local/literature-notes/incremental-runs/<原生ID> --policy .local/<实验>/learned/entry-policy.json
node scripts/project.mjs python scenarios/literature-notes/run-incremental.py --dependencies .local/<父任务>/automatic-dependencies.json --papers-dir ./testpdf --entry-policy .local/<实验>/learned/entry-policy.json
# 上一条默认只预览；实际运行加 --call-model --budget-usd 1。
node scenarios/literature-notes/agent.ts update --job <父任务UUID> --incremental-entry-policy .local/<实验>/learned/entry-policy.json --refresh --call-model --budget-usd 1
```

split包含training_runs两个增量输出目录、certification_run另一个增量输出目录；不是SDK子run ID。学习会重放全部更新计划和prepare结果，仅允许cache_stats变化。只处理work论文，已有完全无变化0调用仍是普通缓存。首次阅读、增量和claim策略分别显式选择；HTTP不接受策略路径。接口、失效和GitHub说明见[变更记录](../../docs/changes/incremental-work-motif.md)。

## 收据后结束 Motif（显式实验）

只替代“有效收据后，模型再生成结束文字”的末尾请求，正文与证据仍由原Harness/MCP生成。新库当前仅认证preview；needs_review、失败和pending仍交模型。状态JSON有Runtime来源标记，不新增论文事实、不宣称科学理解正确；普通手写停机规则也可做同一件事，未声称Motif更快。

```bash
node scripts/project.mjs python scenarios/literature-notes/learn-terminal.py --split .local/<实验>/split.json --output .local/<实验>/learned
node scripts/project.mjs python scenarios/literature-notes/repair-pdf.py --run .local/<冻结复核输入> --terminal-policy .local/<实验>/learned/entry-policy.json
# 上一条默认预览；调用模型加 --call-model --budget-usd 1
node scenarios/literature-notes/agent.ts run --claim-terminal-policy .local/<实验>/learned/entry-policy.json --refresh --call-model --budget-usd 1
```

split.training_runs为两个原生claim-repairs输出目录，certification_run为第三目录；无entry/terminal/PTC/manifest及恢复造出的轨迹才可学习，绑定当前生产代码与Schema并逐引用核源。不要与旧库一起开启。相关[接口记录](../../docs/changes/terminal-receipt-motif.md)与实验结论供提交审阅。


## 普通 PDF 文献索引与 BibTeX 引用目录

这是独立任务入口，复用 Harness、MCP、预算及现有引用格式检查。默认预览，显式调用模型后直接交付私有 JSON、Markdown 和 BibTeX；原 PDF 不变。只从首页原文抄录元数据，无法辨认的标题/作者保留缺口，出版年份/标识缺失留 null；首页中的接收/接受日期不能自动当出版日期，图片或数学字形可能未被文本解析保留，完整学术身份与作者表尚未认证。

```sh
# 预览，不收费
node scripts/project.mjs python scenarios/literature-notes/run-catalog.py --papers-dir ./testpdf
# 初次建立目录，使用已经配置的 API key
node scripts/project.mjs python scenarios/literature-notes/run-catalog.py --papers-dir ./testpdf --call-model
# 将上一条输出 receipt.artifact 作为 previous；只交给模型新/变化的文件
node scripts/project.mjs python scenarios/literature-notes/run-catalog.py --papers-dir ./testpdf --previous <私有catalog.json> --call-model
```

现有文件来源和执行版本都未变时，普通程序重新核源并保留旧记录，模型调用为零。这不计 Motif 学习收益。文件删除时只移除对应目录记录，精确重复文件始终保留，未自动合并学术身份。

可选 `--entry-policy <私有认证策略>` 免模型执行实际工作数组的全部首页读取，然后交回模型判断标题/作者等；需先用本场景真实普通原生轨迹重新学习及独立认证。`learn-catalog.py` 的 split 包含 training_runs 两个目录和 certification_run 一个不同目录。旧任务策略不能靠替换工具名迁用，完全未变时不执行 Motif。`check-catalog.py --task <私有task.json> [--previous <私有catalog.json>] [--policy <私有策略>] [--stale-plan]` 使用真实 MCP/SDK、本机模拟 Provider 验证，真实 API 为零；模拟轨迹不能学习。共享核心无变化，详情见 [实施前接口记录](../../docs/changes/pdf-catalog-motif.md)。


目录的日期与作者结构守卫已更新：模型year只传当前候选id或null，唯一明确出版/预印本年份由程序填入；Received/Accepted/版权不能用作出版年份。作者仍由模型抄录，author_coverage检查可见候选署名区域的词元覆盖，无法解释时partial明确保留缺口。覆盖不是完整作者表认证，日期候选也不是线上出版记录认证。新增候选探测仅支持部分Latin署名格式及显式日期，不从文件名推断。

新版本使旧catalog与旧entry-policy失效，更新时全量重建，重新学习认证后才能加载策略。旧实验结果原样保留。两组共用日期投影和作者反馈，不算Motif的收益；详见 [场景契约变更](../../docs/changes/catalog-metadata-guards.md)。
