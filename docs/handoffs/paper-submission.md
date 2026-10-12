# 论文生成与投稿场景当前交接

- 2026-10-12阶段保存：`52cb0f4`已推送origin/feature/paper-submission，当前V6及此前论文/公共适配代码已保存；其他同学场景/参考PDF未纳入。该快照Ubuntu CI通过、Windows收集因fcntl失败。新增统一跨平台锁与控制器导入/竞争测试，本地385 Python/213 Node通过；远端新CI待确认，见[修复记录](../experiments/windows-rsi-lock-20261012-v1.md)。完整论文优先：私有副本已免费编译成功，参考文献表34条、Bib315条；有重复标签与未解析nocite placeholder，尚无新付费调用，累计7.96362748/10美元不变。

## 当前：V6导出收据与费用优化完成（2026-10-12 08:48，Codex）

- 目标/范围：用户醒后继续优化两局部Motif费用，本地累计10美元；原权限/生成算法不变。仅同论文结构修订/合格报告复核/标识故障，不是完整论文。
- 分支/代码：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4，未提交/推送、未同步服务器，其他同学工作保留。
- 已完成：revision_export_receipt.ts成功投影为绑定完整检查的收据，失败/未知输出保持完整；patch-rsi-task-server.ts、Batch编译/Runtime显式绑定可选新协议；paper-rsi-receipt-task.py复用V5控制器/预算/守卫，同工具提示约束最终解释。完整检查/来源/原字段/前后快照仍在私有报告。投影/提示/宿主为工程，算法仍旧DeepSeek生成，新两图来自本轮正常轨迹。
- 已验证：两正常Session10请求冻结后，三Shadow15请求/严格4，三execute9请求/verified5/unverified0；六份完整结构/字段保留通过。免费364 Python/212 Node、18题/83来源smoke及新增协议切换专项通过，详细数量见实验记录。运行后注册代码hash一致，旧manifest没改。
- 实验结论：docs/experiments/paper-rsi-export-receipt-20261012-v6.md。同新版工具估费低12.75%，execute比V5低21.55%；不是纯Motif贡献。观测请求少40%，直接接管记录只有5次，第6次差是原生复核做额外无变化写入；该项严格Shadow0，执行前记录并单列路线诊断。一条Shadow最终文字混淆报告key与Bib键的重复范围；150中文字是软提示，execute-main未完全遵守。质量没有人工盲评、完整事实/PDF未做，学习未摊平。
- 配置/数据：.local/paper-reference/paper-rsi-receipt-task-20261012-v6/，含prospective-plan、prior-v5-cost-profile、全部正常/Shadow/execute事件/请求/ledger/报告/验收、pre-execute-gate、code-snapshot、cost-optimization-audit、comparison-summary/final-state。DeepSeek-flash/off/8192，无次数上限/压缩，内联200000。库a538afe9c916ad1cbc4ac70b4673b3eaa8df421a7065c014cbcf5fe54247ba6d；快照2b584b9c5e79bb534508734538b01d189508373c6c3600c21d5d3fdaf5412b58。
- 未完成/阻塞：初始提示/技术版本收据的冷输入仍主导；未做单项投影/提示消融、失败后的真实恢复、跨论文盲评、长事实与正式版本链。总费用下降包含正常路线变化，不能假装所有原生请求差都是准确预测。
- 接手下一步：1.新工作先核对累计账本/锁，不重复健康固定库追比例；2.减少版本收据/提示的重复冷输入时保留完整取证、同协议对照并冻结新epoch；3.接真实长取证/版本/PDF流程和独立论文，报告全部失败及学习摊销。
- 权限/预算：新增34真实请求，含预留估费0.016492596美元，累计7.96362748/10美元，余额上界2.03637252；实付账单未知。原paper-rsi-local-export-20261012-v1授权，只读+固定当前私有revision-report.md导出；不改原件、不投稿、不写外部应用、不重启Web。无活动付费任务，夜间automation仍暂停，公共默认1美元。
- 回退/风险：不加载V6入口可保留旧协议；旧实验按各自代码归档重放，不能更新旧hash。免费最短入口：node scripts/project.mjs python scripts/paper-rsi-receipt-task.py preview；既有结果用summarize-paper-rsi-patch.py加--experiment上述私有目录。本轮阶段完成，停止新增付费调用。

## 当前：连续输入Schema与状态守卫，夜间完成（2026-10-12 07:24，Codex）

- 目标/范围：本地RSI局部结构修订，累计10美元；补足上一轮输出作为新输入及不合格检查后的状态前提。完整事实/版本/PDF/跨论文及人工盲评未做。
- 分支/代码：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交/推送、未同步服务器；其他同学改动保留。旧库/manifest未改。
- 已完成：trace_rsi_schema_adaptation.py从真实合格字段交集只适配required，原DeepSeek AST不改；trace_rsi_effect_guards.py通用特征/合取学习；dsh_trace_rsi_effect_guard.ts叠加当前状态拒绝/原生回退；paper-rsi-effect-task.py复用原控制器/预算/题面，显式加载新工具及守卫。特征/搜索/Schema/宿主/排版是工程，算法及旧调用图有真实生成/轨迹证据。
- 已验证：7原状态输出一致、13分支检查与中立事实一致、6保留守卫诊断通过；免费364 Python/211 Node、18题/83来源smoke通过。新版两正常训练10请求冻结后，三项Shadow14/严格5，三execute9/verified5/unverified0，三完整结构/字段检查均通过；真实请求少35.71%、费用仅少3.56%。无需新增ID修订与上轮合格报告复核均通过。旧V4三项40%/13.24%仍仅自己的范围。
- 实验结论：docs/experiments/paper-rsi-effect-guards-20261012-v5.md；already-covered费用上升3.89%，失败保留。旧Runtime免费缺项诊断仍导出，新守卫免费诊断回原生，均不是模型恢复/节省。真实六项未触发失败检查，不能声称该分支模型恢复通过；学习未摊平。
- 配置/数据：effect-guards-20261012-v1保留7来源/归档验证、Schema、13分支、适配工具/守卫及原新诊断；effect-task-20261012-v5保留全部计划/事件/ledger/报告/验收/冻结批次/code-snapshot/final-state。DeepSeek-flash/off/8192，无次数上限/压缩，工具内联200000。V5preview免费，summarize加--experiment该私有目录；旧入口未自动升级。
- 未完成/阻塞：未做失败后真实模型恢复、跨论文或完整论文；守卫直接回退可能漏一次后续机会。新Schema仍保持原类型/闭合字段，不能任意接收其他论文的未知字段。没有净学习收益或人类盲评。
- 接手下一步：1.用户继续时先核对本地累计账本，做有真实意义的失败恢复对照而非重跑健康固定库；2.接长取证/正式版本/PDF流程，记录全部质量和费用；3.再提供独立论文盲评与学习摊销，避免把局部35.7%写成全流程。
- 权限/预算：V5新增33请求/估费0.02006504美元；历史7.94713490/10美元，余额上界2.05286510，账单未知。授权paper-rsi-local-export-20261012-v1；Runtime只读及当前固定私有revision-report.md导出，模型负责修订。不改原件、不投稿、不写外部应用、不改上游/重启Web；公共默认1美元。
- 回退/风险：停用V5显式入口可回旧原生/V4；新代码快照f0ad7c4e72eabaf51157bbdcc64ab519d20f2fa87a12d3c8780c10f8741047c1。无活动付费任务，预算锁空闲；固定计划完成且七小时窗口结束前停止跟进，不再新增调用。

## 前次：RSI局部计数/字段能力与恢复Shadow（2026-10-11，Codex）

- 目标/范围：将计数、重复数、字段保留及违规对象定位内化为模型生成工具，再从正常轨迹编译Motif；当前同论文结构修订子任务，不是完整论文真实性/PDF验收。用户仍要求Shadow优先、暂停新execute。
- 分支/代码：feature/paper-submission / 基底2368235f274329be6227a8393b850633cb943da4；本轮未提交/推送，保留其他同学改动。服务器最终代码快照和私有结果已回本地，新增文档/样例同步服务器。
- 已完成：revision_tool_evidence.py提供中立事实、生成表达式选取/组合/输入绑定；dsh_revision_rsi_learning.ts与revision_rsi_macros.ts接真实学习；paper-rsi-revision.py提供学习及免费局部编译；paper-rsi-revision-task.py复用原MCP/观察器/批次编译器。生成计数/比较算法未手改；解释器、守卫、选择与验收仍工程提供。公开程序见examples/rsi-tools/revision-{counts,fields}-v1/。
- 已验证：局部计数27新派生例、字段14开发/21原未见例，组合36诊断；导出违规对象重放原例不算新认证。两正常任务各5请求通过后冻结；三个已知反例恢复Shadow为1/5、2/7、1/5，合计4/17＝23.5%；结构通过两条单列2/10＝20%，实际跳过0。两端347 Python/192 Node免费回归、服务器无模型18题/83来源smoke及公开2＋3例通过。
- 实验结论：docs/experiments/paper-rsi-revision-counts-20261011-v1.md。恢复任务非未知范围/独立论文；subset-b一个原条目第4个source_urls内容仍被改，生成工具报错但模型未修复，失败保留。四次匹配请求只占三任务原生费用3.64%，没有实际降本/人类盲评/完整交付结论。
- 追加免费费用审计：同三任务完整报告写入4次/13,139输出token占49.1%费用，最终文字占11.7%，全部7次检查占34.7%；未被当前库覆盖的3次首次检查约占31.0%，主要未缓存输入。输出合计57.6%；不能只压最后总结。优先RSI生成字段级修订与程序化报告，再学习首次检查，尚未实现；逐请求证据见最终task-v6/output-cost-audit.json，新增模型请求/费用0。
- 配置/数据：SSS_TRACE_RSI_TASK_CONFIG；DeepSeek-flash/off/8192，无次数上限/压缩，Node22.23.3/Python3.10.8/Harness0.1.5-rc.3。私有revision-shadow-v1..v6、revision-counts-v1..v5、revision-task-shadow-v1..v6目录均位于.local/paper-reference/并含日期20261011；最终task-v6的final-state.json、code-snapshot.tar记录配置/哈希/结果。当前冻结工具counts-v5，Motif8881f95c…85d4d；公共样例不能直接加载成认证库。
- 未完成/反例：通用审计器学习525请求仍未整体认证，部分版本中止；完整失败不追改。字段修复仍失败1条；更长取证/修订链、未知论文、最终解释/科研判断和实际降本未验收。读取→检查仅1训练Session，本轮严格机会只由2 Session的写入→检查产生。
- 接手下一步：1.从正常修订轨迹生成按key/字段的局部修订工具，避免重写整份报告污染来源；2.接更长流程，预先固定真正新任务，记录质量及学习摊销，不再把恢复集当盲测；3.另定交付门槛与execute范围，当前继续暂停自动接管。免费入口 `node scripts/project.mjs python scripts/paper-rsi-revision-task.py preview`；已有结果用score，不覆盖标签/库。
- 权限/预算：本次所有学习/失败/任务641新请求，新增代理金额1.544031820美元；历史累计7.710643630/8美元，余额上界0.289356370，含未结算预留，账单未知。本轮付费已结束，无模型任务挂起；产品默认1美元不变。不改原件、不投稿、不写外部应用、不重启Web。
- 回退/风险：停用新生成工具/观察器可回原路径；各轮代码快照、失败、原始回答与账本保留，不清空.local。旧实验用各自快照复核；当前verify会拒绝代码变动，不应改旧manifest哈希绕过。

## 前次：完整请求批次与工具调度通道（2026-10-11，Codex）

- 目标/范围：生成工具→正常轨迹→整请求批次→冻结后Shadow，优先调用/费用并透明记录有限性能损失；当前仍是结构修订子任务，不是完整论文校验/PDF。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交/推送，保留其他同学改动。服务器执行，私有结果和最终代码已回本地。
- 已完成：trace_rsi_batch_compiler.py、dsh_trace_rsi_batch_shadow.ts、paper-rsi-batch-shadow.py、audit-trace-control-text.py及专属回归；原工具/旧提示保持不变，共享新协议分v1/v2。显式追加三个观察器版本，完整工具/参数/结果/派发顺序和当前来源守卫；固定工程去重与学习所得批次分列。
- 已验证：v1冻结Shadow仍0/5严格。v2两合格正常Session冻结后，预定三个Shadow各2/5，共6/15=40%；原字段保留通过两条为4/10，另一条失败保留。对应原生请求费用23.1%，不是省费；实际跳过0。两端335 Python/177 Node免费回归、服务器smoke通过；真实库仍只有两个单工具后继，多工具能力仅免费诊断。
- 实验结论：docs/experiments/paper-rsi-batch-shadow-20261011-v2.md。Agent初阅发现一条来源URL被改、三条最终说明计数/解释错误；不能把结构通过说成完整交付合格。所有失败/旧strict0保留，用户可容忍损失尚未量化，无人类盲评/跨论文认证。
- 配置/数据：私有paper-rsi-batch-training-20261011-v1和batch-shadow-v{1,2}含全部ledger/事件/报告/fixture/冻结库/配置/版本；v2 prospective-plan.json固定两训练/三范围，code-snapshot.tar和final-state.json可定位最终版本。DeepSeek-flash/off/8192，无次数上限/压缩，SSS_TRACE_RSI_TASK_CONFIG；新协议全部组相同。
- 未完成：计数与修订差异仍让模型重复解释，存在错误；未接更长真实性/正式版本/PDF/Web链，未得到两Session的真实多工具批次支持，实际降本未验证。
- 接手下一步：1.从新正常轨迹让RSI生成计数/修订差异/字段保留工具，独立测试后冻结，不手改科研判断；2.接长取证/恢复链，用固定新任务报告全分母与质量损失；3.完整交付验收后另定execute范围，不自动恢复接管。
- 权限/预算：本次所有失败/训练/评测51请求、新增估费0.091044美元，历史累计6.166612/8美元，余额上界1.833388，账单未知；无模型任务挂起。用户允许有限性能下降，但没有增加预算/解除暂停execute。不投稿、不写外部应用、不重启Web。
- 回退/风险：停用批次插件即可回原Shadow；旧控制器/库/日志保留，不清空.local。两端旧文档历史有差异，仅增量同步本轮内容，不覆盖团队历史。

## 前次：正常正反轨迹学习状态条件（2026-10-11，Codex）

- 目标/范围：拒绝已经检查过相同输入的重复续接，保留模型修订/总结职责；继续只做Shadow，不自动执行。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交/推送，其他同学改动保留；服务器执行，私有结果已同步本地。
- 已完成：trace_rsi_state_compiler.py、dsh_trace_rsi_state_shadow.ts、paper-rsi-state-shadow.py、replay-trace-state-shadow.mjs；原工具、提示与旧观察器字节不变，派生库显式增加观察器版本。状态特征工程提供，条件由原正常正反例学习。
- 已验证：两正常Session的2正/2负例学出prior_same_input_check==false；负例仅1Session。历史回放保留4正确预测、拒绝2结束误预测，零新增模型请求。三真实Shadow各5请求，全部结构/字段保留通过；完整调度5/15，严格0/15、实际跳过0。298 Python/162 Node两端回归及服务器无模型smoke通过。
- 实验结论：docs/experiments/paper-rsi-state-shadow-20261011-v1.md。状态拒绝效果仅在已看过的历史反例回放验证；新任务没有末尾单独重读，不能称前瞻结束认证。主稿请求4把检查+读取放在同一请求，单检查预测不覆盖整请求，计为不完整；6次预测5匹配，非收益证据。
- 配置/数据：私有.local/paper-reference/paper-rsi-state-shadow-20261011-v1/含原库/派生库、正反见证、逐请求、报告、评分、用量、回放；SSS_TRACE_RSI_TASK_CONFIG。公开摘要examples/motif-library/trace-rsi-state-shadow-v1/不可加载执行。DeepSeek-flash/off/8192，无次数上限/压缩，累计预算不重置；preview免费，已用paid标签和冻结库不覆盖。
- 未完成/边界：同论文故障注入，不是跨论文或语义验收；write→check无负例，仍未认证所有分支。文字未交接，严格请求替代0；不能把原生6→5算方案收益。
- 接手下一步：1.从正常轨迹学习完整多工具批次及参数/顺序依赖，预测必须覆盖整请求；2.保留科研判断，定义检查控制文字的有界交接并在新结束分支评测；3.更长真实任务及独立论文质量审阅后再考虑execute。
- 权限/预算：新增15真实请求/估费0.028743美元，历史累计6.075568/8美元，余额上界1.924432，账单未知；无模型任务挂起。不写外部应用、不投稿、不重启Web，继续暂停execute。
- 回退/风险：停用新状态插件即可回原Shadow；原库及完整反例保留，不清空.local。Windows模型运行、任意bash工具化、语义质量、实际降本均未验证。

## 前次：生成工具正常使用与局部图 Shadow（2026-10-11，Codex）

- 目标/范围：把上一轮模型生成工具接入正常修订，学习实际衔接，冻结后评测新范围。仍暂停execute，不改原件、不投稿。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交、未推送，其他同学改动保留。服务器运行，私有结果已同步本地。
- 已完成：scenarios/paper-submission/trace-rsi-task-server.ts；src/adapters/trace_rsi_motif_compiler.py、dsh_trace_rsi_shadow.ts；scripts/paper-rsi-generated-task.py、check-trace-rsi-task.mjs。动态算法未人工改写，当前收据绑定输入/报告/来源/目录/候选/Session，旧版本与伪造句柄拒绝。
- 已验证：v3主稿/摘要正常7/5请求；冻结库两个局部图，每图两个Session支持；新范围Shadow各6请求，各2次调用/参数/结果匹配，结构与既有字段保留均通过。最终292 Python/158 Node免费回归，服务器无模型smoke通过；语义未评审。
- 实验结论：docs/experiments/paper-rsi-generated-task-shadow-20261011-v3.md。局部4/12=33.3%，严格整请求0/12、实际跳过0；六次预测中两次结束阶段误预测，精确率66.7%。同论文范围变化/故障注入，非独立论文认证。公开阅读摘要在examples/motif-library/trace-rsi-shadow-v1/，不可加载为执行库。
- 配置/数据：私有.local/paper-reference/paper-rsi-generated-task-shadow-20261011-v{1,2,3}/含全部逐请求、报告、验收、图与费用；冻结生成工具仍来自paper-rsi-trace-tools-20261011-v3。SSS_TRACE_RSI_TASK_CONFIG绑定任务配置；DeepSeek-flash/off/8192，无次数上限或压缩。入口先运行preview；verify/score已有标签免费。已用paid标签禁止覆盖。
- 未完成/反例：v1改写既有字段导致质量门槛失败，保留并未训练；v2工具顺序启动错误零请求，修复后新建v3并重建见证。图不区分“新状态需检查”和“已验证应结束”；模型文字也未被安全交接，不能算跳过。
- 接手下一步：1.由成功与结束反例学习状态条件，并在新任务上验证误预测；2.保留科研判断，给纯检查旁白定义有界控制交接，严格统计与人工判断分列；3.扩展真实跨论文/更长任务后再讨论execute与净收益，不再只重复本范围诊断。
- 权限/预算：本轮所有失败与修复共40真实请求，新增估费约0.070375美元，历史累计6.046825/8美元，余额上界1.953175，实付未知。当前没有模型任务挂起。默认产品1美元不变；暂停新execute，不写外部应用，不重启Web。
- 回退/风险：只停用新任务插件/MCP即可回旧路径；v2旧代码快照与零请求失败保留。Windows模型运行、任意bash凝练、完整论文交付、跨论文认证与实际降本均未验证。

## 前次：真实轨迹驱动工具发现（2026-10-11，Codex）

- 目标/范围：先读正常轨迹，再由DeepSeek自主决定工具目标、输入输出并生成/修复程序，独立验收后保存动态MCP。继续暂停新execute；本轮没有新增正常论文任务或Shadow，不能声称新Motif或请求减少。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；本轮代码/文档未提交、未推送，其他同学工作保留。服务器模型学习，本地审阅；私有结果已同步。
- 已完成：paper-rsi-trace.py、trace_tool_evidence.py、dsh_trace_rsi_learning.ts、trace_rsi_program.ts、trace-rsi-server.ts、check-trace-rsi-tool/mcp.mjs；模型自主选出的triage_catalog_coverage提供覆盖/缺失/多余、arxiv_id差异和问题类型序列。通用基础设施仍人工实现，没有人工改写生成算法。
- 已验证：20条bash全部保留，仅2源脚本支持内存重放；模型生成最终程序后3开发、12未见源反例、12真实MCP通道调用通过；全部23有效源反例复核一致。两端265 Python/139 Node免费回归通过，含成功试用守卫；无模型smoke通过。公开合成两例仅供阅读诊断。
- 实验：docs/experiments/paper-rsi-trace-tools-20261011-v3.md；前两版失败保留，第三版162请求/57定义/36已安装版本后通过。本轮3版本共308请求、实际跳过0；只认证同源选中输出，非独立论文/科学事实质量/完整修订验收。
- 配置/数据：scenarios/paper-submission/trace-rsi-learning.prompt.md；私有.local/paper-reference/paper-rsi-trace-tools-20261011-v{1,2,3}/含来源、逐请求、预算、不可变候选、开发/留出/冻结/MCP验收。deepseek-flash/off/8192、无次数上限/压缩、同一累计预算。公开原程序及无私有数据的合成样例在examples/rsi-tools/trace-coverage-v1/，不是可直接加载的认证库。
- 未完成/限制：只有2源操作可认证，不是任意bash自动工具化；工具schema保留原目录字段，输入源/版本绑定需场景守卫。新工具尚未加入正常任务、挖掘新衔接或前瞻Shadow；学习host VM不是隔离边界。语义未评审，费用未核对实付。
- 接手下一步：1.给正常论文任务加载冻结工具，保持模型执行并采集输入来源/版本、成功及恢复见证；2.从正常使用轨迹编译动态工具局部边，不能用学习会话或手写DAG代替；3.冻结图后在新任务前瞻Shadow，报告严格整请求机会及全部学习摊销开销，仍不做新execute。
- 权限/预算：本轮新增代理0.274440美元，含历史累计5.976450/8美元，余额上界2.023550，账单未知。没有模型运行继续挂起；不重置预算、不改原件、不写外部应用、不投稿、不重启Web。产品默认仍1美元。
- 回退：新入口显式启用，停用新学习配置/MCP可回旧流程；源码v01/v02/v03私有存档及失败保留，不清空.local。Windows、独立插件分发、跨论文泛化及实际降本未验证。

## 前次：固定目标的 DeepSeek 自生成工具 RSI 最小闭环（2026-10-11，Codex）

- 目标/范围：原生Cordis让DeepSeek生成、测试、修复报告结构工具，独立验收后冻结成MCP，正常修订轨迹编译局部Motif，下一任务前瞻Shadow。继续暂停execute；不是完整论文修订、文献真实性或PDF验收。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；本轮未提交/未推送，其他同学改动保留。服务器学习/运行，本地审阅交付。
- 已完成：paper_rsi_program.ts有界解释器；dsh_paper_rsi_learning.ts原生学习接缝；rsi-server.ts TS MCP；dsh_paper_rsi_shadow.ts只读预测；paper-rsi-tool-learning.py / paper-rsi-program-check.mjs / check-paper-rsi-task.mjs / score-paper-rsi-shadow.py控制、认证和审计。MCP加载生成程序不需Python进程，实验控制/预算仍需Python。
- 已验证：DeepSeek真实生成，开发测试通过、工具真实调用，11/11未见结构样例通过；两个正常基线和一个留出各4请求，结构/来源通过。252 Python/113 Node免费回归；有真实MCP stdio诊断，模型验收不用mock。
- 实验：docs/experiments/paper-rsi-tool-learning-20261011-v1.md；学习92请求/31源码定义，2 Session编译1局部write→check候选。Shadow局部1匹配，含旁白，严格整请求0/4、实际跳过0，语义未评审、未证明降本。
- 配置/数据：scenarios/paper-submission/rsi-learning.prompt.md为公开契约；私有.local/paper-reference/paper-rsi-tool-learning-20261011-v1/保存冻结工具、定义/测试/轨迹/图/结果。模型deepseek-flash/off，输出8192，无次数限制/压缩，独立DSH_HOME，Node22。沿用夜间v1的authorized-budget.json，密钥仅服务器环境。
- 未完成/限制：工具目标、契约、安全解释器和样例仍人工提供，尚非任意bash自动工具化；初次启动注册顺序失败0请求已修复，重复检查有多轮模型调试；首次纯请求编译无见证，改为局部边后保留文本事实；学习VM不是安全边界，不能直接对不可信用户开放。生成工具只验结构。
- 接手下一步：1.审阅留出请求3旁白的内容职责，区分语义与调度，禁止直接删文本美化指标；2.接入更长真实修订中的缺证据/失败恢复，自动提出下一工具学习目标；3.新程序使用新版本/独立反例验收，统计含学习与人工修订的摊销成本。
- 权限/预算：累计8美元授权不重置，本轮104请求新增代理0.089141532，累计5.70201003，余额上界2.29798997，实付未知；无新execute、原件/外部应用/投稿写入授权。默认产品仍1美元。
- 回退：新入口显式启用，默认论文工具集未改；不加载新学习/MCP/Shadow配置即可回旧路径。保留旧数据和失败，不清空.local。Windows、独立插件产品分发和长期收益未验证。

## 前次：十任务三轮 Shadow 已结束（2026-10-11，Codex）

- 目标与本次范围：从正常轨迹扩展局部参数化 Motif，探索整请求 Shadow 替代空间；仅一篇论文十种范围/错误变体的活动引用和预印本分诊，不是十篇论文、完整修订或最终 PDF 验收。继续暂停新 execute。
- 分支 / commit / 未提交改动：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；论文代码、文档与私有结果两端同步，未提交/未推送。保留其他同学 Web/场景改动及两端文档差异，不代表 main 已更新。 原始私人论文ZIP保持原位置，已加入窄范围Git忽略规则，避免误提交。
- 已完成：paper-rsi-overnight.py、paper-rsi-recovery.py、paper-rsi-repair-shadow.py；Python 局部图编译与查询信封学习，TS 请求前只读预测与已完成节点守卫，来源绑定 Crossref/arXiv MCP、当前产物读取。最终9局部单步候选，查询库1 Crossref信封/1Session见证；没有DBLP成功协议。可读摘要见 examples/motif-library/paper-shadow-v1/，不是可安装执行库。
- 已验证：13 baseline+21 Shadow，共34运行/616真实模型请求；两端252 Python/109 Node免费回归。前三轮严格匹配24/112=21.4%、37/114=32.5%、45/164=27.4%；最佳单任务50%，实际跳过0。第三轮6/7有产物且结构通过，重复条目任务无 triage.json，虽然Harness completed仍判交付失败，保留11请求/费用；语义未盲评。
- 实验结论：docs/experiments/paper-rsi-overnight-20261011-v3.md 汇总，v1/v2记录保留。新增校验失败→读取候选只有1Session支持，本轮未触发，新增覆盖0；成功edit→check出现6次反例；事后分类第三轮51次纯来源读取、78次原生网页请求，后者仍缺可预测参数/分支，不能计跳过。最佳整组超过20%仅支持候选空间，不能证明安全执行、跨论文泛化、持续单调下降或实际节省。
- 配置与数据：服务器加载 .local/remote-env.sh；Node22.23.3/Python3.10.8/DSH0.1.5-rc.3/SDK0.1.5rc1；deepseek-flash/off/8192/无次数限额/无压缩/shadow/danger-full-access。私有根 .local/paper-reference/paper-rsi-overnight-20261011-v1、v2、v3；v3 final-summary.json/effective-config.json、代码版本存档及逐请求配置/账本可复核。最终库06ebe76573610d1f201a79993061f3666401ed99a7e843af026d854ef0c990b4；查询库35512689085d2803031957119b6d3e30a9e43dda509b993d131eeee219172c11。源码/工具/来源变化须按manifest重新训练；只允许已记录的编译器/观察器两文件迁移。
- 未完成与阻塞：Crossref未收录被误判DOI不存在、键名年份误判、无正式版证据P2、重复条目事实绑定错误，均未通过语义验收。需要独立论文盲评、真正批量查证/恢复正常轨迹、完整PDF和Web集成；不继续无变化付费重测。旧模拟/诊断结论不改成真实质量通过。
- 接手下一步：①同条件独立新论文Shadow+盲评来源/版本/交付；②将查询与失败表达为来源绑定类型结果，从正常轨迹学习分支与局部子图；③通过质量及冻结留出后才考虑受限execute和脚本/缓存对照。当前免费预览：node scripts/project.mjs python scripts/paper-rsi-repair-shadow.py --phase preview（需私有账本/训练目录，不覆盖既有运行）。
- 权限与预算：用户本轮累计上限8美元，今晚新增代理估费0.744562，含历史累计5.612869，剩余上界2.387131；账单未知，失败不扣除、预算不重置，默认产品仍1美元。本轮已结束，无自动续跑任务。私人副本/真实API测试授权有效，不改原件、不投稿、不写外部应用、不重启Web；没有新execute。
- 回退与风险：默认工具/入口保持，新增模块显式启用；不用flow/query配置即回既有路径。保留旧代码/库/训练摘要与失败；不能清空.local或将公开可读摘要加载为认证库。Shadow只观察模型原始路径，跳过后模型轨迹与缓存可能变化，需要后续真实验证。

## 前次：局部编译与逐请求 Shadow 回放

- 目标与本次范围：负责人要求先证明shadow整请求替代和动态局部复用，暂停新execute；本次从正常基线编译候选并回放历史留出，不运行模型或重新执行工具。仍仅覆盖活动引用/预印本分诊阶段，不是完整论文修订或参考文献PDF报告验收。
- 分支 / commit / 同步：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；本次7个新源码/协议/测试文件、私有候选库与审计双端同步，测试入口均追加新项；未提交/未推送，其他人的Web/场景改动及两端已有文档差异保留。
- 已完成：src/adapters/paper_shadow_compiler.py、paper_shadow_runtime.ts；schemas/paper-shadow-library.schema.json；scripts/compile-paper-shadow.py与audit-paper-shadow.mjs。从collect-manuscript/abstract挖掘write→check（2 Session/2见证）、edit→check（1 Session/1见证）。工程工具契约仍人工实现，边来自正常轨迹；只有shadow候选，不执行写/改或修复。
- 已验证：两端npm test为239 Python/107 Node，其中新增12 Python/5 Node。冻结库后回放evaluate-manuscript/abstract-shadow，5预测中3严格整请求、1含旁白局部匹配、1下一操作不一致；完整检查结果/来源/文件摘要一致才计候选。请求分类3整请求/10局部/4语义或恢复缺口，实际跳过0。
- 实验结论：docs/experiments/paper-shadow-compiler-audit-20261011-v1.md。严格仍3/17=17.6%，未增加此前统计；人工4/17=23.5%只保留在前次审计，不改自动口径。历史Session虽训练/评测分离，开发者此前看过评测，同论文不同稿件，不是前瞻盲测、独立论文认证或合格降本。主稿请求5是反例，不能固定每次编辑后强接长流程。
- 配置与数据：.local/paper-reference/paper-shadow-compiler-audit-20261011-v1/保留library.json、shadow-audit.json、effective-config.json及regression-server.txt；源码/环境配置为事后补录，库digest 1eb1bf41a27391eb9bd889eafca14481091e1b26f5ee25afe23aa4401866c060。旧原始轨迹/账本/分析不改，敏感材料不入Git。服务器Node22.23.3/Python3.10.8/DSH0.1.5-rc.3/SDK0.1.5rc1。
- 未完成与阻塞：复合取证内部步骤尚非独立学习节点，网页查询/失败恢复缺类型与来源绑定；主稿失败编辑后没有当前产物读取工具，误用file://网页请求。语义判断未盲评，新候选没有跨论文/自动执行认证，完整PDF/Web与持续自动工具生成仍未完成。
- 接手下一步：①补失败编辑后当前产物的只读取证与版本摘要；②为复合取证子步骤、正式版本线索和网页失败类型补契约，采集正常轨迹；③冻结下一版后在新论文前瞻shadow验证预测反例、整请求机会与语义质量，不重跑无变化的同库execute。
- 权限与预算：本次新增请求/费用0；用户此前追加1美元后的累计封顶5.84521046，累计代理4.86830662、剩余上界0.97690384，账单未知；原4.84521046记录及历史失败费用不重置。既有真实API授权有效，off/8192/无请求次数限额；当前没有模型运行，不改原件、不投稿、不重启Web。
- 回退与风险：新入口为独立只读离线诊断，未安装到Web/Harness执行路径；停用入口即可保留既有流程。当前检查器只验证结构/范围/版本，不认证文献真实性；HTTP200验证页、缺DOI、引用键中的年份均不自动构成出版结论。

## 此前阶段记录（当前状态以以上交接及对应实验为准）

- 2026-10-10 复合取证六次真实运行：主稿baseline/shadow/execute=8/9/7请求；短稿6/8/7。六次completed、集合/结构/来源守卫通过，语义未盲评。baseline与execute合计均14请求，execute估费高30.3%；工程Hook尚非新学习Motif。详见 docs/experiments/paper-composite-delivery-20261010-v2.md。此前新增0.09451318美元已经计入本次沿用累计预算，不能扣除重试/失败。
- 2026-10-10 先行审计：严格3/17；主稿请求3人工认为是纯调度旁白，另列候选4/17=23.5%，非自动认证/真实收益。citation库两局部边+同一完整链、参数库7原型归三族，多个查询无留出；见 docs/experiments/paper-shadow-reuse-audit-20261010-v1.md，旧统计不改。


- 2026-10-10 两次真实 shadow 复验：同一冻结库/同一论文，confirm-a/b 请求 40/17，选定结果 23/23、30/30 全通过，完整纯工具机会 2/40、3/17，合计 5/57=8.8%；实际跳过 0，20% 尚不稳定。两份阶段产物集合均 15/15，来源哈希未变，语义质量未盲评；新费用约 0.102378，累计代理约 4.295005/上限4.84521046，余额上界0.550205，账单未知。逐请求分析明确 7 次选择协议响应，以及未绑定集合和 bash 片段；这些不是认证跳过。当前未形成 RSI 自动学习/发布闭环，下一步从正常轨迹编译参数化查询/脚本与恢复节点、把选择协议并入必要判断，再冻结新库开展留出 shadow；不继续相同库付费重测，加入脚本/Code Mode 对照。专项 7 项本地/服务器免费诊断通过，新数据两端同步，代码未提交/未推送。详见 `docs/experiments/paper-shadow-confirmation-20261010-v1.md`，私有新运行与分析仍位于 continuation-v2 根，suffix 不是独立任务；当前入口固定原稿/阶段任务、未接完整 PDF/Web。前次 execute 动作类型已更正为 8 读取+3 查询（2 请求）。

- 2026-10-10 shadow 评测主线：负责人最新要求以 shadow 为主，`paper-reference-continuation.py` 默认模式已改 shadow（仍默认预览、付费须 --call-model；显式 execute 保留）。新增 `scripts/evaluate-shadow-continuation.py` 分析既有真实 root Session 的完整请求边界，不新跑模型。旧 v2 shadow 4 批/30 项全验证，3 次纯工具请求机会、1 次含文本需审阅；Codex 初阅后者仅调度说明，未改自动分类。实际跳过/直接跳过节省均 0、反事实费用未知，不能将候选数冒充收益。两端免费 177 Python/80 Node，本次新增费用 0，累计仍约 4.19263/冻结上限4.84521046。记录 `docs/experiments/paper-shadow-evaluation-20261010-v1.md`，私有派生 `shadow-evaluation-v2.json` 与 `shadow-text-review-v1.json`；原轨迹/账本/质量缺陷保留。代码未提交/未推送；下一步负责人独立评审风险等级，再新增真实输入配置开展 shadow，当前入口仍固定原稿，suffix 不是独立任务。


- 2026-10-10 连续接管真实阶段测试：`paper-reference-continuation-20261010-v2` 已完成，主稿 34 引用键中的 15 个 arXiv 条目由模型选批，三组最终均精确覆盖 15/15。baseline/shadow/execute 真实请求 50/15/25；shadow 4 批验证 30 项，execute 4 批中两批原生已到齐，另两批 8 次读取 + 3 次查询通过并实际跳过 2 请求（逐批复核更正，原始总数不变），无 unverified。6 次新运行（含 v1 范围/等级失败）新增估费约 0.31265，含历史累计约 4.19263，冻结封顶 4.84521046，余额上界 0.65258，账单未知；不重置费用。最终两端 172 Python/80 Node，本地无模型 smoke 18/83 通过。模型选择与目录协议是手工适配，结构原型仍从历史轨迹编译；未做跨论文认证，未接 Web/完整 PDF。输出集合通过但语义质量未盲评，存在 P1/版本证据判断差异；不能将 50→25 全归因于仅 2 次拦截或宣称合格降本。新增入口 `scripts/paper-reference-continuation.py` 默认预览，模型绑定 v2 schema、连续恢复/同批去重在 `dsh_parameter_motif.ts`，质检入口 `scripts/check-reference-continuation.py`。代码和公共小改动未提交/未推送，既有 Web 并行改动保留；实验详情见 `docs/experiments/paper-reference-continuation-20261010-v2.md`，私有轨迹/交付/代码历史位于同名 `.local/paper-reference/`。下一步：先锁定字段证据与风险判断质量，再做等条件对照、脚本节点及独立论文验证。


- 更新时间与交接人：2026-10-10，Codex。
- 最新局部证明：`parameter-motif-proof-20261010-v1` 已完成。新增 Python 参数原型编译器、TypeScript 参数绑定/并行汇合插件、服务器受限证明入口及输入 schema；不修改原 v5 库或精确编译器。读取原型有 2 训练/4 留出成功观察，查询有 17 训练观察和 5 并行批次、无成功留出。真实 API 两类局部任务 baseline/shadow/execute 均为 3/3/2 次，execute 各 verified skip 1、全部选定项到齐，无 unverified；严格网络守卫重测同样通过。基线已明确流程、输入由实验预选，不是完整论文自动匹配/脚本挖掘/跨任务认证。详见 `docs/experiments/parameter-motif-proof-20261010-v1.md`；新真实运行及代码历史在 `.local/paper-reference/parameter-motif-proof-20261010-v1/`。本机最终免费全量 170 Python/64 Node，服务器参数编译专项 16、Runtime 13 通过。新增代理估费约 0.03477，含历史累计约 3.87998；该轮增量额度冻结为 1 美元、累计封顶 4.84521046，总封顶 5，不重置旧费用，账单未知。全部本次代码未提交/未推送；下一步做模型输出显式绑定后连续多节点接管，保留原完整报告质量待验收状态。
- 最新候选审计：用户要求暂不谈效果，先解释候选结构。已只读还原 v5 全部 23 候选，分布 4/7/2/10/0，各只有一次出现；13 个仅训练、10 个仅留出，全部缺至少两条训练支持。原库只计数未存淘汰 body，完整结构与失败条件现存私有根的 `candidate-audit.md/json`，还原脚本为 `audit_candidates.py`。哈希分组绑定前置批次、具体路径/参数/输出和文件版本，尚无子目录/查询/脚本参数抽象；已观察到同字节主稿因路径及批次不同被拆组。896 个协议拒绝窗口发生在候选计数前；另 4 种后台读取候选仅在第五条留出出现，无训练支持。未修改编译/在线规则或阈值，未新增模型调用；详细匿名化依据已补入 v5 实验记录。
- 目标与本次范围：当前按用户统一题面执行完整参考文献/正文引用核验与 PDF 报告，计划五次原生 Harness 新会话采集，三训练/两留出编译同题诊断 Motif，再做两次 execute。v2 曾因输出 8000 截断，v4 输出 32768 后因原生子 Agent 并发预留触发预算 429。用户最新授权提高额度，v5 累计上限 5 美元、输出 32768：五次 baseline、两次 execute 均已结束并产出报告候选。编译得到 23 候选、0 认证 Motif，在线实际跳过为 0；质量未验收，范围差异阻止直接成本比较。旧六 MCP 的 shadow/execute 结论与 Native/PTC 记录保留；本轮原生工具不等同旧 MCP 对照，不投稿、不改原件。
- 分支 / commit / 工作区未提交改动：`feature/paper-submission`，基点 `2368235f274329be6227a8393b850633cb943da4`（已推送）。本次和此前论文环境/实验改动未提交、未推送；同目录另有 Web 并行改动，不一起提交或覆盖。
- 当前新增入口：`scripts/paper-reference-experiment.py`、统一 `reference-audit.prompt.md`、`native_motif_compiler.py`、`dsh_native_motif.ts`。共享 Harness 生命周期门复用；编译支持受限本地读取及实际后台句柄→结果读取，不能重放任意生成脚本。私有最新根为 `.local/paper-reference/paper-reference-five-native-two-motif-20261010-v5/`，v1/v2/v4 失败证据保留。
- 已完成（此前 MCP 实验）：`scenarios/paper-submission/checks.py/server.py` 六个只读 MCP；`scripts/paper-motif-experiment.py` 预览/准备/采集/编译/比较；`dsh_paper_motif.ts` 复用共享拦截器。manifest 增加可选诊断 scope、实际参数 schema 哈希，普通插件拒绝诊断库。两训练合成稿及另一留出稿的真实轨迹编译出三个 pin→read Motif；私人论文仅评测。两端同步私有证据与公开记录，保留实际执行代码历史。
- 当前验证：本机全量 169 Python / 51 Node、服务器编译与预算专项 23 项通过。七次真实模型运行 completed，但认证库为空，实际 verified skip 为 0；七份 PDF 质量仍未验收。原生事件会话隔离、Unicode JSONL 和持久预留恢复已投入本轮；实际执行代码历史保存于私有目录。
- 已验证（此前 MCP 实验）：真实模型采集 9 次请求，评测 baseline/shadow/execute 为 3/3/2 次；三组题面、schema 顺序和工具结果完全一致，各六个 MCP，无工具错误、无源变化。execute 三次读取组成一个 batch，逐结果通过后计一次 verified skip。本机修正后全量 153 Python / 48 Node 通过；服务器最终全量验证同为 153 Python / 48 Node。无模型 smoke 18 题/83 来源、既有四个 Motif 库重编译及 Harness/shadow/execute/旧版本回退通过。模拟检查不代表效果。
- 当前实验记录：`docs/experiments/paper-reference-five-native-two-motif-20261010-v5.md`，包含完整七次请求/费用/耗时/产物表、23 候选与 0 认证、空库回退审计、34/314/315 范围不一致和字体提取问题。旧 v1/v2/v4 失败保留，不追改为通过。
- 实验结论（此前）：`docs/experiments/paper-motif-shadow-execute-20261009-v1.md`。支持在该只读条件下跳过一次整请求；execute 估费 0.00343812 美元，比同工具基线 0.003314136 高约 3.7%，耗时 12.515 对 12.019 秒，未观察到降本。合成任务仅协议认证（`protocol_diagnostic`），非独立科研决定。三份回答质量未盲评；不能与前面 Native 85/PTC 128 次探索直接归因比较。前面两份报告误读与失败见各实验记录，未删除。
- 配置与数据：服务器 `/root/autodl-tmp/jjy`，先加载 `.local/remote-env.sh`，统一 Python 入口。Node 22.23.3、控制器 Python 3.10.8、Harness 0.1.5-rc.3。密钥仅服务器 `DEEPSEEK_API_KEY`。本实验两端 `.local/paper-motif/paper-motif-shadow-execute-20261009-v1/` 保存输入、真实请求/事件/ledger、各模式答案、库/manifest、快照、verification、codex-audit、实际执行代码；公共工具契约在控制器 `contracts()`。旧 Native/PTC 私有目录保留。详见场景 README 的复现与依赖边界。
- 未完成与阻塞：检查器事后修复了 ACM bibitem 注释导致渲染键漏读，以及未知 shell-escape 的布尔歧义；旧回答不改，离线重算恢复 34 个键，未知安全配置改 null，未再付费复验。检查器摘要变动使旧 task 版本失效，下一次需新快照。静态解析不等于完整 TeX，缺少真实编译动作/失败恢复、页面视觉、科研质量认证、脚本对照和独立论文泛化。实验入口依赖 Linux fcntl、五份旧账本及既有私人准备目录，未做通用化或 Windows 验收。新增 TS 入口尚复用 JS 核心，并非已完成全面 TS 迁移或独立插件打包；未接入 Web。原容器 bubblewrap/Landlock 阻塞仍存在。
- 接手下一步：用户现阶段要求先证明结构接管，暂不谈完整效果。①让模型在真实论文任务中输出一次显式目标/选定输入绑定，验证连续多个参数化节点接管及反例恢复；②从现有正常轨迹扩展有输入输出、版本和副作用契约的脚本节点、数据依赖与选择守卫，不能用手写场景 DAG 冒充挖掘；③完整效果评测前仍须解决 v5 原稿范围/编号/逐条来源/逐页视觉和跨运行污染问题。不要重复已经结束的五次采集，也不要覆盖本次局部证明的原始记录。
- 权限与预算：通用默认仍为 1 美元。本次参数局部证明增量最多 1 美元，起点累计 3.84521046，冻结累计封顶 4.84521046，另保留此前 5 美元总封顶；单次输出 4096、无请求次数上限、推理 off、压缩关闭。8 次局部真实运行已结束，新估费约 0.03477，含历史失败与未结算预留的累计代理金额约 3.87998；当前冻结额度余额上界约 0.96523，账单未知。此前完整 v5 输出 32768/5+2 记录不改。私人副本非沙箱实验授权持续有效；不投稿、不改原件、不写外部应用。
- 回退与风险：原件不改，上游不改，前端不重启；不要清空 `.local` 或覆盖预算历史。新诊断库只限 opt-in；不合适/失效时走原模型。保存工作区后再切分支，提交只纳入本人文件和审阅过的公共小改动。旧快照回放须用保存的实际代码，不能冒用当前修正版本。

本轮最终运行快照（2026-10-10）：服务器 `pipeline-status.json` 为 `model_runs_finished`，七次报告候选页数为 34/8/10/17/21/15/26。基线模型请求 240/157/215/319/1197，execute 207/153；后两次只是空库原生回退，没有 verified skip。本轮新增估费约 3.0526，含历史失败与一笔未结算保守预留的累计约 3.8452 美元，账单未知。服务器编译专项 23 项通过。采集与续跑已经结束，不要按早期“等待采集”指示重复启动。下一步先核对报告范围（34 与 314/315 混用、扩展摘要混入）、编号/权威证据/逐页排版，以及临时目录跨运行污染，再扩展脚本节点与参数绑定的轨迹编译；当前无可用的正式论文 Motif 库和降本结论。
