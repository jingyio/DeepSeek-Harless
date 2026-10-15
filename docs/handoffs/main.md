# 主线当前交接

## 最新本地状态：2026-10-15持久化/批量/恢复

- 已完成用户指定三项，`feature/rsi-research-agent`，HEAD仍`fcdcc48`；无新提交/推送。Python编译/认证、TypeScript在线继续沿用。
- 日常入口 `npm run web -- --scenario file-management --real-model --mode execute` 不必传库配置；真实/模拟分别固定`daily-files-real-v2`/`daily-files-mock-v2`。原凭证由环境变量提供，不写入公共文件。
- 第5版4个v2图；真实6/6新任务机械交付、12/12认证材料交付，163HTTP/USD0.097170133、40次验证跳过。报告缺口与一次工具失败完整保留，未做人工盲评/完整净收益对照。系列代理估费USD8.348467365，账单未核实。
- 浏览器已多选双文件提交/看实际产物、服务重启/恢复原请求4→11、原摘要确认；SDK发布后中断也原请求6→15、一计划两效果。真实默认入口恢复原库和3完成任务，0新增模型调用；认证已封存材料采用原记录0重复费用。
- 新旧源码阶段和全部失败见`.local/persistent-rsi-development-20261015-5f4d87ee`，付费冻结协议/材料在`.local/file-management/fm-persistent-rsi-20261015-a648d606`及`fm-persistent-web-20261015-004257ff`。旧最终集/论文不学习不覆盖。
- 新接口：[详细变更](../changes/persistent-rsi-integration.md)，[实验](../experiments/persistent-rsi-20261015.md)。REST `resume` 仅原中断任务＋原确认摘要；预算与版本变化拒绝。v1旧失败/证书保留，v2独立认证重新学库。
- GitHub旧CI `38392885619`已被`01ce885`修复；最新已推送`fcdcc48`的`38548225640`成功。本次只检查旧失败，不重新推送。
- 最终检查：639 Python/216 Node通过（3可选跳过）、18免费smoke及SDK/Web/认证恢复通过；逐文件旧数据保留核验见开发档案。
- 当前边界：一个已登记文件MCP、17工具、2–8节点顺序图、非空唯一数组≤40；不支持并发图/任意循环/任意其它MCP。预算耗尽停止；未知费用或未核实轨迹拒绝训练。后续扩场景须单独适配，不能降低质量标准。

## 当前接手状态（2026-10-15，Codex）

- 目标/范围：用户要求先扩文件管理、再接默认前端；通用MCP算子契约、有界参数图学习、原生来源、独立认证/激活/回退与Web队列已实现，仅本地，暂不推送。
- 分支/版本：feature/rsi-research-agent，HEAD fcdcc48；本轮和先前脏工作均未提交，不能把本机新能力当GitHub已同步。旧发布库/许可证/证书原字节保留。
- 当前实现/接口：[通用MCP操作图实施记录](../changes/generic-mcp-operation-rsi.md)，Python离线发现/认证、TS在线执行；新schema为mcp-learning-contract和operation-graph。真实适配器为file_operations_v1，其它MCP需登记权限/材料/验收；不是任意流程全部学会。
- 验证：632Python、211Node通过，3可选跳过，18smoke；免费真实CLI/SDK/MCP与Web API及取消结算通过；真实严格文件流6/6普通交付、两代2→5节点图和3节点后缀独立激活；真实Web5/5，验证17次请求跳过。[全部结果/负面证据](../experiments/generic-mcp-operation-rsi-20261015.md)。
- 入口：`npm run web -- --scenario file-management --budget-usd 5 --request-limit 96`免费；`web:real`才真实，原/tasks预览确认不变。服务器可传--rsi-config/--files-dir，客户端只能选择已登记文件目标。当前私有配置`.local/file-management/fm-operation-rsi-20261015-a3adca6c/rsi.json`；库与来源指针`.local/rsi/operation-current.json`，旧只读指针不改。新克隆没有本机库，从空库普通运行学习。
- 数据/完整成本：本轮59真实执行/470HTTP/USD0.237622092，含第一轮worker缺审计失败、失败调用屏障修订及2个保守拒绝候选。全系列1084尝试/10888HTTP/USD8.251297232，原USD1000余991.748702768（代理估计，非账单）。净收益只记录，开发人工/语义质量未核实，最终留出禁止学习。
- 权限/预算：仅testpdf有标记的新副本；每原任务≤USD5/96步与HTTP/4000输出/2次验收修复，学习池≤USD25且计入系列。502/503同任务最多2次重试，每次记费，未知usage不训练。取消及在途结算保留原预留；本次23个当前版本预留全部结算。
- 失败/版本：旧bfd735a4长图因省略失败调用的采集缺陷事后明确停用；原证书/失败/费不改。a3adca6c严格来源审计通过。额外pin/read候选因隔离认证要求恰好一次完成而保守拒绝，未改标准重签。
- 保全/回退：`.local/general-rsi-development-20261015-244a9c2b`含before/after/diff/完整日志/final保全；267609个旧私有文件无删除覆盖，仅1日志追加原SHA前缀。移除--rsi-config回普通CLI；Web baseline关闭图执行，可observe停止自动学习。任务冻结原库版本，旧版本不重签。
- 未完成/接手下一步：其它真实MCP适配器及业务验收；重复图/多产物认证与新操作服务跨进程恢复；浏览器视觉/真实办公质量/长周期完整成本观察。现有默认UI已加文件目标表单，但本轮端到端验证为真实HTTP任务API，不冒充浏览器视觉验收或公网产品上线。

## 此前版本记录

下面状态是历史快照，若与上面的当前状态冲突，以当前状态为准；旧证据和失败保持。

2026-10-15已接通首版普通CLI持续Motif学习：任务封存后自动发现/编译、新副本独立认证、版本发布与后续复用；真实新任务流完成两版升级、6/6普通交付。最新并发队列/证据修订服务621 Python/199 Node通过，最终云端复验遇503，未完整重现两代，已停止付费诊断。首版仅只读文件报告及两类有界图，默认SDK/Web未接；净收益仅观测。30真实执行/146HTTP/估费上界USD0.176759772，5次503和全部失败/费用保留，最终留出不学习，暂不推送GitHub。[实验与边界](../experiments/continuous-motif-rsi-20261015.md)、[接口与入口](../changes/continuous-rsi-integration.md)。


此前[工作流结构报告与新RSI验证](../experiments/file-management-report-delivery-20261014.md)完成102次新执行：task_result身份/快照/真实回执由当前MCP状态生成，模型填写摘要/缺口；原实际字节与权限验收不变。新诊断H/回退各6/6；两轮当前版本经验学习/独立认证/自动激活后均在下一任务零HTTP执行。日常H5/6、S/F/R各6/6，最终正常H/S/R各8/8、F7/8，8版本安全停止。R完整API USD1.325444比F1.390140低约4.65%，但F未全部合格，预定同质量净收益门槛仍未满足；普通回退备份仍需修复。603 Python/185 Node及smoke通过，系列估费USD7.836915368；失败/排除/轨迹/费用与旧最终留出保留，仅本地、默认SDK/Web未启用、暂不推送GitHub。[共享契约](../changes/file-management-report-delivery.md)。


此前[回退修复与持续学习验证](../../docs/experiments/file-management-fallback-rsi-20261014.md)完成142次真实运行：跨计划重复SHA写入在执行前拒绝，提交时检查原始字节组完整覆盖。第二版新诊断H/回退均6/6；新两轮经验自动认证激活并在后续实际执行。最终正常H7/8、S8/8、F8/8、R7/8，8版本安全停止；R完整API USD1.149742低于F1.207199约4.76%，但最终质量较低，不支持同质量净收益。未知目标失败的文件正确但缺实际报告，原失败/费用留存，最终不学习。599 Python/185 Node通过，系列估费USD7.197809948。本轮仅本地，暂不推送GitHub、默认SDK/Web未启用。[共享接口](../../docs/changes/file-management-fallback-guard.md)。


## 最新 有界自动RSI验证完成 2026年10月14日

- 本地统一经验库/真实事实检索、机会触发普通探索、结构归纳、独立认证、两轮自动激活及失效普通回退已验证。新代码未提交/推送，之前Motif库分发仍在feature/rsi-research-agent；默认SDK/Web关闭。
- [完整结果](../experiments/file-management-auto-rsi-20261014.md)：51主研究+15同操作流控制，共66运行/633HTTP/代理USD0.477517296，系列751尝试/7303HTTP/USD5.893675700。H/S/F正常留出7/7、R6/7；8V停止。完整API H/S/F/R=0.137249172/0/0.491204188/0.520633648，尚无RSI质量/净收益证明。
- 第一轮空候选/失败探索、补充探索、两轮4份新独立认证、一次操作普通修复及未知目标最终失败保留。新库实际参与第二轮任务，0HTTP；最终留出禁止学习。此前暂不推送约束仅对新开发仍保留，最近授权上传库不扩为自动上传新代码。
- [契约](../changes/file-management-auto-rsi.md)/Schema、TS dsh_experience、Python经验库和auto_rsi、免费SDK与两独立审计是新入口。588Python/185Node通过、3可选跳过、18smoke；47,626旧私有文件SHA不变。
- 接手：先改善未知目标普通回退/真实语义质量，用新非留出材料；再做更长周期冻结库/持续更新的同成本对照。不能用本次最终留出修库，不能称通用自改代码RSI或上线。原1000美元估费余额994.106324300，实付未知。

库提交 `02bcc21` 已推送到 `feature/rsi-research-agent`，GitHub分支引用和全部18个分发文件的blob哈希已核对；其余本地开发改动仍未提交。

## 最新 文件管理 Motif 库分发 2026年10月14日

- 用户已恢复此次库分发的GitHub推送授权，目标 `feature/rsi-research-agent`；此前暂停推送记录不适用于本次明确授权。范围仅已学习Motif库、索引、检查与说明；其他本地运行时/脚本实验开发保留未提交。
- [公开库](../../examples/motif-library/file-management-v1/README.md)：9库/策略、3manifest、3认证/冻结摘要，原字节/摘要与重复副本索引保留。`.local`继续忽略，私人资料、密钥、原轨迹、费用和失败不上传且不删除。
- 本地与无 `.local` 的 HEAD+分发副本加载检查通过；6项发布回归通过，源码不匹配的两组严格检查按预期拒绝。0云请求/费用0；没有重做付费学习或认证。
- G4库依赖的部分MCP/任务源码尚未发布，公开索引报告版本差异；不可只凭库JSON执行G4流程，也未新增自动RSI。前端接入须另行发布兼容源码与新任务权限/预算绑定。[契约](../changes/file-management-library-publication.md)。

## 最新 脚本规则/目录变化与第二版完成（2026年10月14日）

- 目标/授权：原testpdf副本、既有DeepSeek、1000USD系列预算，验证规则/目录失效、原普通修复、新普通学习/认证及新留出；不提交/推送。feature/rsi-research-agent / dfe4fcc未变，历史未提交改动保留。
- 完成：独立TS dsh_learned_script_v2、script_adaptation_study/learning、受控草稿probe、SDK与独立audit；v1和六MCP服务依赖不变。四个受限关系模板从8干净普通见证推导；另2轨迹排除但计费。无任意代码/新Web kind；[接口](../changes/file-management-script-adaptation.md)。
- 认证/质量：8新实际L2认证均0HTTP合格；认证后40新五组留出，H/S/L2各6/6、M5/6、L1 4/6，10版本边界停止未交付。原修复控制5项中4项最终成功，1原失败保留；L1回退不保证修好，新留出仍有两项两轮修复失败。报告明确自然失败、受控草稿和受控版本中断。
- 版本：另2实际SDK/MCP陈旧execute拒绝，永久停用、0后续自动派发，模拟普通Provider各3HTTP/2轮修复后未完成，未知字节保持；0云费用，不训练。初诊断和公开helper复验原事件分别留存。
- 成本：65实际运行/790HTTP/USD0.715712544；L2新维护USD0.274608132，加首版准备为USD0.374614224，执行0HTTP。S API仍最低，不证明完整经济成本为0；人工金额不折算/维护工时与盲评/账单未知。系列685attempts/6670HTTP/USD5.416158404，原1000预算估费余994.583841596。
- 验证：573Python/173Node通过、3可选Docker跳过，18题smoke；16免费MCP探针、8零模型SDK及原草稿SDK修复通过。65费用/权限/字节及原事件/角色/停用审计通过，6857旧文件/PDF原字节保持；17真实验收修复全计费。
- 数据/复现：script-adaptation-current指向8872b28c，275e4518原14次只读导入，旧L1/G4/G5指针不变。协议/候选/证书/新留出锁、frozen-source、所有原事件/费用/每轮验收、失败和副本保留；开发快照/差异在.local/script-adaptation-development-20261014-f2caa1ac。[完整结果与命令](../experiments/file-management-script-adaptation-20261014.md)。SDK/Web默认关闭新模板。
- 未完成/下一步：只有两复制流程、已知容器和生成新路径/文本/规则的机审，不是40项完成/通用学习或上线验收。选择产品显式模板/权限与版本流程，再冻结真实业务材料和独立总成本评审；当前用户授权的本轮已完成，无后台付费任务或GitHub推送。


## 先前 学习脚本复用首批完成（2026年10月14日）

- 更新/交接人：2026-10-14，Codex；用户授权新普通探索、脚本提炼/独立认证和H/S/M/L新留出，原testpdf副本权限/1000USD系列预算保持，不提交/推送。feature/rsi-research-agent / HEAD dfe4fcc未变，本地新增代码和记录。[结果](../experiments/file-management-script-reuse-20261014.md)。
- 完成：script_reuse_study/learning、TS dsh_learned_script、真实SDK免费检查、独立audit及3Python/3Node新回归。受限指令从实际成功普通操作推导哈希组代表、目录前缀复制和实际备份产物输入；显式私有patch，无新工具/公共CLI/HTTP kind/任意代码。原六服务依赖、G4库、旧三组留出和三PDFSHA保持。[逐项接口](../changes/file-management-script-reuse.md)。
- 来源/失败：8792969c四普通探索全交付，FM05-E额外语义读取使编译拒绝；ef863a4d原SHA导入并补一个新元数据探索，原失败不追改。5原普通任务中4份学习，两模板不同数量见证；普通/免费/认证/自动/留出角色严格隔离，Runtime不训练。初始免费冻结拒绝和事后schema别名检查错误及修正均保留。
- 认证/新留出：候选锁先于8认证（4独立条件×H/L）且全部合格，L4次0HTTP；证书冻结后新生成6条件×4组24次轮换。正常/边界四组4/4，8V停止均未交付；总37含13准备/24留出，29交付、8未交付，不改旧留出或用新留出修库。
- 费用：准备136HTTP/USD0.100006092；留出H/S/M/L 77/0/61/0HTTP，USD0.057222300/0/0.045803244/0。L完整API为0.100006092，M加原全库准备为0.281582008（原库范围更广），本批L对H/S无完整API成本优势。4共同合格条件59/0/47/0HTTP，L与S相同0API。FM17的M是普通回退，其差异不能算学习收益。
- 失败/修复：49工具错误原请求和纠正费用计入；没有真实验收修复消息，L自然修复API0，不宣称已验证新的真实DeepSeek脚本失败修复。免费真实SDK/MCP模拟Provider一次失配、一次失败验收和同会话普通修复后通过，10mockHTTP/0云费用；另两零模型程序与5反事实守卫检查通过。原权限、预算和两轮修复不重置。
- 验证：当前及前版各6免费MCP探针通过，37完整独立字节/协议/来源/证书/四组/原HTTP与缓存usage/费用审计通过，无未知usage；568Python/170Node通过、3可选Docker跳过、18smoke通过。代码/默认接口仍实验边界，机械验收非人类质量或真实办公前瞻证据。
- 数据：script-reuse-current指向ef863a4d，8792969c原事件/源码仍原地保存并SHA引用；protocol/candidate-lock/certificate/holdout-lock、frozen-source、全部实际工作副本/每轮验收/原模型消息及HTTP账本/summary/独立审计/guardchecks/排除原因全留存。开发改前/差异/日志在.local/script-reuse-development-20261014-9c915457。
- 预算：本轮37执行（21有真实API、16零模型）/274HTTP/USD0.203031636；系列620执行/5880HTTP/USD4.700445860，估费余额USD995.299554140。实付/人工盲评/维护工时未知；人类金额按用户要求不折算。
- 接手：1 新规则与目录变化后的匹配失效/重提炼/独立认证与维护成本，2 语义选择后复用脚本的混合流程，再新的留出；已有留出不训练。不要声称通用代码学习、自动维护或完整成本优于预写程序；动态前端/SDK产品加载仍未接。回退移除新私有patch/env即普通原CLI；GitHub等待用户明确恢复。

## 此前 第五阶段六流程新留出三组完成 2026年10月14日

- 更新/交接人：2026-10-14，Codex；用户授权新留出比较、人工金额不折算，仍只testpdf实验副本，不提交/推送。feature/rsi-research-agent / HEAD dfe4fcc未变，本地开发未提交。
- 完成：workflow_holdout冻结18新probe/18新holdout、54个H/S/M运行并轮换顺序；H原循环，S三个语义流程同Model批量读/三个固定流程0Model，M仅旧认证读取/计划图、FM17普通回退。新TS dsh_workflow_experiment只经私有patch加载，注入相同版本/真实成功或崩溃冷边界；不新增工具，不改旧服务/IR/library/任务预算。公开入口默认预览。[接口](../changes/file-management-workflow-holdout.md)。
- 质量：正常/边界H11/12、S12/12、M12/12；18V全部停止，仍保留未完成。原H整理全局编号错误，两修复/三检查仍失败，35HTTP费用保留，未重跑同留出。54中35交付、19失败/停止；155工具错误完整保留。[结果](../experiments/file-management-workflow-holdout-20261014.md)。
- 费用：三组全部执行代理USD0.194854178 / 0.086595528 / 0.144017954，292/116/193HTTP。M加USD0.235778764探索/认证/在线验证为0.379796718，高于H/S；11共同合格三元配对176/72/132HTTP、M/H估费−16.53%、M/S+76.71%。本批脚本总体最低，无学习来源的因果/全成本优势结论；FM17两组普通循环差异不能算Motif作用。
- 恢复：FM38 H/M在成功/真实进程75后均新Session整Harness冷启同job；N幂等重复、E占1原repair后原token回滚/2验收通过，原费用/请求/权限不清零；M修复后停用。S用实际MCP重连同授权，0Model。V未知外部足迹拒绝恢复，三job.failed。无自动restore图。
- 验证：原与最终18MCP探针、9普通脚本、4真实SDK本地模拟冷启动全通过，0云费用；565Python/167Node、3Docker跳过与18smoke通过。独立54项完整字节/配对/原限额/版本/原HTTP使用量和费用审计通过，无未知usage；原54模板/oracle/pristine、三PDF、七实现和29旧库SHA不变。
- 数据：workflow-holdout-current指向427b924b；protocol-lock/frozen-source/private模板、library-lock引用、逐arm数据/配置/工具schema、原Model/HTTP、control-marker/job/计划/备份/恢复/每轮验收/最终副本、independent-audit/summary均保留。88f86de1和0fae7c42免费版本/源差异保留；开发归档workflow-holdout-development-20261014-a0046390。新留出没有训练或改变旧库。
- 预算：本批601HTTP/USD0.425467660，全系列583尝试/5606HTTP/USD4.497414224，98未通过交付结果保留（本批19含18受控V），原1000USD估费余额995.502585776；账单未知。人工金额按用户要求不折算，人类语义盲评/真实办公泛化/维护工时未确认。
- 接手下一步：优先将固定规则交普通程序，选真实语义较多用户流程做前瞻质量/维护验证；同语义决定和同调度的反事实对照再判断学习增益。不要从这54留出修库、承诺规模摊销收益或上线；默认SDK/Web/动态前端保持边界，GitHub待用户恢复。
- 回退：新实验control patch退出即原公开CLI；未改变G4库/服务版本或已发布HTTP任务契约。源码、权限、版本或模板变化必须新实验/绑定，不能覆盖旧结果或重置job。

## 最新 首批六流程普通探索完成 2026年10月14日

- G3新增14次普通DeepSeek尝试、12机器验收通过，首轮2恢复越界读取失败保留；修复读取前守卫后两份新文本通过。真实中断MCP重连并用原授权回滚，原任务预算不重置。共206HTTP/USD0.123931013，59工具错误和SDK旧Session免费失败均保留。[完整结果](../experiments/file-management-workflow-exploration-20261014.md)。
- 增加持久化恢复状态事实包、固定故障边界restart_required、同job/新传输Session冷启动和job归档；普通旧入口保留，默认Web无新接入。新14/15工具无新Motif证书，旧七工具和旧库不改。[共享接口](../changes/file-management-workflow-runtime.md)、[场景交接](file-management.md)。
- 归档源码重放审计通过，统一14图/343节点、12合格普通轨迹按版本/schema分两组；失败保留不训练，免费/模拟/留出排除，0自动Runtime节点。原54pristine/题面/oracle和三PDF不变。565Python/146Node、33免费MCP、模拟Provider冷启动和18smoke通过，3Docker跳过。
- 系列509尝试/4799HTTP/USD3.960098813、76模型失败保留，实付未知；原USD1000预算及仅testpdf副本授权保持。当前feature/rsi-research-agent、HEAD dfe4fcc，本地未提交/推送，用户暂停GitHub同步仍有效。
- 下一步G4实际版本分组学习并独立认证，之后G5新留出H/S/M；没有新流程节省、普通脚本增量优势或人工业务质量结论。完整格式恢复、动态前端、并发和跨平台仍待后续。

## 最新：六流程副本、验收与免费恢复整合完成（2026-10-13）

- 当前本地未提交/推送，公开基线仍dfe4fcc。用户本轮只推进准备与免费验证，0新增云API/真实模型费用；原495/4593/USD3.836167800和74失败保留。
- fm-workflow-free-20261013-de2f6604：54模板（probe18/explore12/certify6/holdout18）、独立WorkflowScene/验收与TS持久化job。33免费MCP检查通过；12业务字节后置合格、6外部变化保持停止，7守卫/8容量探针通过。真实MCP退出75后同授权回滚；非零预留/请求/步骤/修复计数不重置。另SDK9本地HTTP/1修复/2验收通过；模拟计价不计系列费用。
- 全仓565Python/145Node通过、3Docker跳过，最后版本校验26项定向通过、旧18smoke通过；早期CLI None兼容回归2失败日志保留并修复。共享scenario/停止守卫/CLI/预算桥/验收变化详见[记录](../changes/file-management-workflow-runtime.md)，[免费结果](../experiments/file-management-workflow-free-20261013.md)。
- 新恢复仅rename/自身rollback、15工具、原限额普通baseline；新图/写入/恢复组合没有Motif证书，不直接套旧库。旧七个文件工具/契约和原三PDF不改，前端动态目录入口仍未接。
- 下一步冻结最新协议与预算预览，在新explore副本跑普通Harness，再汇集原始轨迹学习/独立认证，之后新holdout做H/S/M；免费probe/SDK轨迹排除学习，留出保持未触碰。暂不推送继续有效。

## 最新：40项文件流程覆盖与六流程设计（2026-10-13）

- 用户同意先扩展覆盖规划。已完成[40项清单](../../scenarios/file-management/workflow-discovery.md)和[首批六流程方案](../../scenarios/file-management/workflow-evaluation-plan.md)，各有规划JSON；18项现有工具可组合、20项需工具、2项需运行整合。所有完整新流程留出均未完成，不能计为40项已实现。
- 六项为下载整理、目录合并、版本比较、普通文件字节备份/隔离恢复演练、ZIP资料包交付和任务中断恢复。设计包括18组条件、H/S/M候选54次对照、必读/可选范围、字节/范围/缺口验收及失败停止口径；54次尚未启动，负例探针通过不把未完成业务重标成功。
- 下一步先补前五项新材料和固定验收，做免费实际MCP探针；FM38须先组合TaskScene、PlanScene、预算/步骤/修复次数持久化和取消，再认证。新流程不是现有TaskContract允许的三种kind；不能拼接旧工具集或证书直接启用。
- 本轮只改文档和规划数据，未改共享运行接口，未生成实物实验副本，0新增真实API/费用；系列仍495尝试/4593HTTP/代理USD3.836167800，实付未知。工作先留本地，未提交/推送；dfe4fcc仍为公开基线，原失败、费用和版本保留。

## 最新协作要求：先本地完成，再推送（2026-10-13）

- 用户明确暂停后续GitHub推送；dfe4fcc是此前已推送基线。后续修改/测试与交接先留本地，直到用户明确恢复推送。原失败、轨迹、费用和接口版本继续保留。
- 下一步优先把当前TaskScene与已单独验证的计划授权/持久化恢复链路组合：确认绑定任务/计划/权限/来源版本，验证取消、执行中断、重启续接、外部文件变化、重复执行与恢复，预算和修复次数跨恢复不重置。读取图或守卫变化时重新认证库。
- 然后接本地前端动态任务：用户输入→服务端形成契约与副本范围→预览确认→执行→验收/有界修复→审阅结果；当前FM_TASK_FILE预配置入口不等于已完成动态任务入口。
- 组合后用新的跨流程留出，对比普通Harness、普通批量脚本与Motif，并计入失败/恢复/学习认证费用；再补真实材料的人审和可安装分发。仍只在原testpdf副本、既有DeepSeek和系列1000USD范围内。
- 本次仅核对现状、记录推送约束和下一步顺序，没有启动新的付费实验或修改运行实现。

## 最新：普通文件任务质量修复与新留出完成（2026-10-13）

TaskScene新契约修复全局重命名、明确转换原件/产物读取，以及空文本实际读取/无写操作交付；逐项接口/Schema/前端口径已记录。最终新12条件×H/L2为24/24，首轮4失败保留；本轮48任务/513HTTP/USD0.338547576，全文件系列495/4593/USD3.836167800。独立审计每个阶段、原输入/源码/库、实际HTTP/token/费用和最终字节，原三PDF不变。最终561Python/139Node通过、3Docker跳过，18smoke及三类免费真实Harness/MCP恢复检查通过。原读取图/L2证书不改，新效果验收另记版本，没有用留出学习；L2总体费用仅−1.43%，不支持普遍收益/生产或科学质量结论。见[完整记录](../experiments/file-management-task-quality-20261013.md)、[接口变化](../changes/file-management-task-contract.md)、[场景交接](file-management.md)。分支feature/rsi-research-agent，最终同步状态以本轮提交为准；旧commit/未提交记录为历史。

## 最新：验收失败后的普通Harness修复已验证并推送（2026-10-13）

- 用户已恢复推送授权：要求原权限/预算内补最多2轮修复，真实验证后北京时间20:00前推项目分支。源码提交47d9218已于北京时间19:46推送feature/rsi-research-agent，远端SHA已核对；main未改。当前交接补记另随分支提交同步。
- 同Session TypeScript停止钩子+固定Python程序验收；每轮不可覆盖证据，原预算/96步/MCP状态不变。失败后全部Motif禁用，普通DeepSeek修复并复验；不能用重置或放宽任务通过。
- 真实两版本共8任务：6成功/2预期权限不足失败，108HTTP/USD0.098112864；15验收含9失败阶段、7修复通知及15工具拒绝全部留存。两次重命名闭环、新L2索引失败后普通模型补齐真实通过。独立审计证明修复后无自动工具、原权限不增、预算不重置；原22基准失败仍保留。
- 最终550Python/139Node通过、3可选Docker跳过；实际免费三类恢复检查、18smoke/13Web HTTP通过。文件系列447任务/4080HTTP/峰值估费USD3.497620224，实付未知。
- 前端入口docs/handoffs/frontend.md，接口与逐项改动docs/changes/acceptance-repair.md，完整结果docs/experiments/acceptance-repair-20261013.md；Web暴露修复次数，仅最终验收通过才completed。文件管理仍显式副本场景，新库默认Web不全启；2项依赖high/多用户/跨启动/科学质量限制保持。
- 密钥、私有库/PDF、原轨迹及所有费用/失败保留.local/testpdf且不推送；当前公开代码内容审查通过。以下暂停推送与旧实验记录均为历史，被本次用户授权更新。

## 最新：暂停GitHub推送，完成基础可用性核验（2026-10-13）

- 用户最新要求先确认现有功能正常使用，暂不推送；当前feature/rsi-research-agent与origin同为2368235。没有暂存/提交/推送；公开开发改动及全部私有记录保留。后续推送须等用户恢复该动作。
- 494公开文件按SHA复制到不含密钥/旧运行/私人论文的干净副本，全仓540Python/132Node通过、3可选Docker跳过；独立npm ci及Python requirements安装成功。同一macOS arm64、Node22.22.2/Python3.12.13、主机已有Poppler，未声称全新系统或新跨平台验收。
- 换用全新安装依赖后18题MCP烟测、13组真实Harness HTTP/MCP联调通过（mock模型），含预览/提交、请求幂等、附件、预算拒绝、取消和库失配回退。五类新生成文件77次实际MCP调用、7预期拒绝，检查8文件/检索4命中，5副本计划覆盖复制/移动/三类转换/归档/隔离，均幂等且逐字节恢复。文献Web两题完成及取消，15项缺口显式保留，未证明科学质量。
- 0新增真实付费API请求；已有真实模型基准22失败仍未修，新文件库默认Web关闭/只在副本CLI实验。npm audit另报2项high（@modelcontextprotocol/sdk、sharp），尚未处理，锁/运行版本保持。当前只确认限定环境内后端/工具可运行，不宣称全部任务稳定或公网可用。
- 本机核验报告.local/github-frontend-handoff-20261013/usability-verification.md/json，clean-validation日志/新生成输入/逐MCP结果/fresh-install安装与audit全部保留。下一步先修已知编号/读取验收及依赖告警，再明确前端需要的场景HTTP接入；用户确认推送后同步项目分支。

## 最新：多窗口读取学习/认证与真实对照（2026-10-13）

- 仅新文献窗口场景/实验/测试/文档及场景收集器可选参数，复用原edge compiler/sss-online-motif/批量Runtime/SDK/预算；共享核心/旧库/上游/Web默认不改。窗口四个参数用规范字符串，转换调用原PDF工具，两组相同；模型仍选择范围/解释，不称新算法。
- 两普通问题9/10参数边，第三独立6边认证，manifest1e1f378…ec14b，正式.local/window-continuation-20261012-0bc4ddc5/learned。初始39请求同会话题面认证拒绝及16步pilot M未结束都留费，不放宽检查；最后双方32SDK步完整对照。
- 两题各3轮，三篇H/M调用均10.33但M费+44.41%；两篇H12.33/M10，输出−2.88%/费−3.76%；12完整结束/来源机械合格，阅读包不同、科学支持未验。19读取批次/36结果非19净省，H68/M61净7且总体M费+17.47%。37参数类型/4发布错误保留，暂不反复小修。
- 同真实模型选定窗口组件6包严格一致：H6/6/6、M5/5/4，3读取请求实际省去，平均费−5.09%；多出1差为模型合并独立调用，不全归于Motif。全部开发26真实run/266HTTP200/$0.287990820去重含失败/学习/pilot/18对照，实付/维护未知。不默认推广，不称科学质量/Code Mode优势。
- 487Python/98Node、24专项及实际免费MCP/SDK正负通过，3Docker跳过；共享SHA/原PDF/密钥/旧工作保持、服务未停，未commit/push/PR。接口/README同步，GitHub说明docs/changes/pdf-window-continuation.md，完整证据docs/experiments/window-continuation-20261012-0bc4ddc5.md，场景HANDOFF有复现/私有数据/预算。下一步引用工作数组/资源条件分支，保持核心改动先记录。

## 最新：扩大文献任务流程探索（2026-10-12）

- 按用户优先级暂缓细小字段修补，场景workflow-discovery.md列40个消费任务/5结构候选族；新增主题检索、真实笔记引用定位、论文资源3类原生小探针，共享核心/预算/上游/正式Web不改。脚本缓存/批量工具能力单列，不称Motif新增收益。
- workflow-discovery-20261012-eec15558首轮6次+db1e78ae偏移修复2次，56HTTP200/代理USD0.063332112含所有错误/重试；首轮引用5误报为新探针绝对/相对偏移错误，修后9引用当前，旧结果保留。40任务并非全部实现/实验，0新认证库/0自动跳过/无H-M效率对照。主题/资源科学质量未验。
- 从真实原生轨迹观察13个pin→read参数链、引用/资源遍历候选；普通Harness已会批量搜索，不能略过词/资源选择。优先跨任务多窗口续接与现有foreach机制迁移；如改共享核心先列字段/生命周期/回退。当前不继续标题/长度小修、不扩UI。
- npm test477Python/98Node通过，3Docker跳过，修后14专项+三类实际免费MCP通过/API0。场景入口explore-workflows.py预览再--call-model，用户API使用已授权。完整结果docs/experiments/workflow-discovery-20261012-eec15558.md；私有全部.local，场景HANDOFF有命令/版本/预算；feature/2368235未commit/push/PR，原服务/PDF/密钥/改动保留。

## 最新：目录日期/作者修补与重认证（2026-10-12）

- 只改变目录场景：日期候选类型/选择（行政日期拒作出版年、唯一年份程序投影）、author_coverage候选词元覆盖及真实partial缺口、submission/投影来源；共享核心/预算/上游不改。候选有限，完整作者/身份不认证，旧catalog/策略失效，新原生重认证，旧实验保留。实施前docs/changes/catalog-metadata-guards.md。
- catalog-guards-20261012-066ad241训练/认证15请求/$0.01665555，新policy f1b912390ce4e1dac61f66bf3403652e704348badaf7256d9ab287a3f78efe8c。12真实对照所有作者名单/日期与已查原文一致，但一次M标题缺口。新增1篇M费+11.31%/输出+16.18%；新增2篇费−13.00%/输出−19.83%，不证明普遍降本，默认不全启。
- 原生前沿12请求→0，12核验批次；后语义15→18，全任务27→18净少9，不能按批次数报净收益。全部源/保留记录及配对plan/packet一致。所有60HTTP200/代理USD0.06146788含学习与45评测/重试，实付维护未知；463Python/98Node/34专项通过，3可选Docker跳过，实际MCP/SDK mock正负/未变0API。结果docs/experiments/catalog-guards-20261012-066ad241.md。
- 原PDF/Key/旧脏工作保留，feature/2368235未commit/push/PR；服务未停，无新服务器/跨平台/思考模式验证。下一步原文区间/句柄减少逐字重抄（两组共有，不算Motif），再另一个真实任务前沿，避免扩人工审阅/UI。CLI已完成，Web未接目录任务；其他接口见场景HANDOFF。


## 最新：文献目录任务与工作清单 Motif（2026-10-12）

- 新普通PDF目录创建/增量更新场景：read_catalog_plan→work成员首页读取→原Harness元数据判断→类型/原文/版本/完整集合核验→私有JSON/Markdown/BibTeX。新增CLI/学习/检查及19回归，本轮无共享核心/预算/上游变化；复用原incremental IR/TS插件，旧库不改，独立工具重新认证。
- catalog-work-20261012-f44dece1：3/2文件普通训练+第三1文件认证，12请求/$0.01215073。新policy08cc0f802a36d3eb0238a9e72cc865ee42e8f6877269468dec6a0ae2c8a0594b仅私有实验、默认关闭/Web未接；实施前docs/changes/pdf-catalog-motif.md、结果docs/experiments/catalog-work-20261012-f44dece1.md。
- 12对照全任务H28/M19请求；新增1篇费−25.36%但M作者缺口1；新增2篇费−14.32%，必填均3/3但有Accepted日期当出版年问题。H真实前沿12请求/915输出→M0，累计12核验批次；后语义H16/M19，不能把批次数/全差当因果收益。所有源/保留字段重放一致，完整质量不等价。
- 本轮91HTTP200/代理USD0.10926764含32失败/.05574344、12学习/.01215073、47评测/.04137347；0模型环境阻止/免费检查错误保留。末轮448Python/98Node、3Docker跳过、真实SDK/MCP mock正负API0、未变普通程序0API、diff check。密钥/PDF/旧脏工作保留，feature/2368235未commit/push/PR，服务8765/3080未停，无新服务器/思考模式验证。
- 下一步有界日期类型/可见作者缺口自动处理，变化后新认证并保留负面；再扩任务或新来源，默认不全启，不扩人工审阅/UI。其他接口与权限见场景HANDOFF。


## 最新：文献收据后终止 Motif（2026-10-12）

- 新terminal_compiler/terminal_receipt_policy认证正常收据→最后模型文字/stop关系，固定dsh_entry_motif/SDK新配对terminal参数与独立计数，原预算/上游/entry不改。状态模板手写受限复制，不称自动学任意总结或优于脚本。当前claim-repair/preview，needs_review未认证回模型。
- 私有terminal-receipt-20261012-34cfce1d库db7c1941f3d149369124d975549a9d93432272de1b67d79d992ea89c7f650db3；1/2目标训练+第三1目标原生认证，15请求/.01749130，源/引用/Schema回放一致。12留出方法组请求4→2.67/估费−32.08%，两组3/3无机械缺口；评测组M更多请求/估费+0.56%且2缺口，只有1末尾触发。共4跳过，全任务差异不可都归因末尾，科学质量未验。
- 所有15新产物/未选字段/引用/范围机械核源一致；本轮63HTTP200/代理估费USD0.09794229包含全部学习/48评测/重试，实付维护未知。429Python/98Node+场景29通过，3可选Docker跳过；免费实际SDK/MCP正负/API0、烟测与diff check通过。篡改产物旧SHA0跳过、SDK error，免费错误断言记录保留。
- repair-pdf --terminal-policy、agent.ts --claim-terminal-policy第一support_audit显式可用，默认SDK/Web关闭，HTTP拒路径、组合旧库拒绝。入口/agent改变使旧缓存正常按workflow失效，不改旧索引。共享实施前/GitHub记录docs/changes/terminal-receipt-motif.md、结果docs/experiments/terminal-receipt-20261012-34cfce1d.md。
- 本地feature/2368235未commit/push/PR，旧脏工作/PDF/Key保持，服务8765/3080未停；无新跨平台/思考模式/服务器验证。下一步另一文献任务的更大结构前沿（建索引/引用目录），已有缓存/脚本0调用不计新Motif；needs_review分支先独立训练/认证，不手扩状态。


## 上轮：文献增量工作清单 Motif（2026-10-12）

- 已最小修复支持复核题面/条件必填Schema，证据/版本/科学支持规则保留。真实单事实3请求/0工具错误/首提交带anchor成功，不代表所有论文理解问题已解决。
- 第三Motif独立协议sss-entry-incremental-v1：当前完整update-plan→work数组参数绑定→只prepare受影响PDF→语义交接。改动entry_compiler/inventory_entry_policy/entry_read_policy及PROVENANCE；旧协议保持，原固定插件/SDK/预算/上游不改。实施前接口与GitHub正文docs/changes/incremental-work-motif.md。
- 首版51请求/$0.10004980两个混合prepare/list前沿被拒，原事件/费用保留。两组共同明确纯准备阶段后，新训练/独立认证45请求/$0.08795057，实际源与导航逐项回放一致。派生基线来自已有模型事实，机械源绑定而非科学审批；0模型创建，不计Motif收益。
- 12次真实新增1/2篇对照：一篇M请求−29.41%/输出−18.83%/估费−5.17%，两组3/3收据且无机械缺口；两篇M输出+29.55%/估费+12.79%且缺口更多。总体请求H90/M78但总费用M+7.95%。支持局部结构/一个已知任务效率，不支持默认全启或科学质量等价。6M共12入口核验批次，失败/重试计入；详见docs/experiments/incremental-work-motif-20261012-a55cdbd9.md。
- 本轮267HTTP/$0.55989722含全部探索/学习/评测/3请求公共契约probe，实付/维护未知。419Python/84Node+场景28通过，3可选Docker跳过，末轮48相关Python、SDK真实MCP/mock/fixture smoke API0。原PDF未改/Key未写/.local不提交。
- 新run-incremental --entry-policy与agent.ts --incremental-entry-policy显式CLI，HTTP不接策略路径、默认关闭；旧claim库须新认证，不自动组合。HEAD2368235/feature分支脏工作保留，未commit/push/PR，服务8765/3080未停。
- 下一步成功收据→状态/结束结构及其他文献流程的更大前沿；提交引用与无收据早停保留为窄修补，尚未加增量completion_guard，不扩质量框架。当前仅已知三PDF，本机macOS，无泛化/思考模式/新服务器验收。


## 上轮：文献清单准备 Motif 与完整任务对照（2026-10-12）

- 后续只读诊断（无新模型费用）：36入口批次与绑定正常；9个不合格中2个阶段失败、7个仅1字段缺口。确认pdf-repair-task前面要求supported带support_anchor，后面/例子却给不含anchor的三字段简写，80/120字示例也混用；实际submit schema元素是宽泛dict。385重复验证问题中缺anchor100/字段限制50/字段结构23，格式错误同样消耗当轮3次额度。此缺陷影响全部组，不能独自解释Motif质量差异。细目见原实验追加章节及.local/.../followup-diagnosis.json。
- 用户询问是否可继续其他任务流程。建议最小统一提交协议，保持科研支持/版本检查；优先增量受影响论文准备、已验证收据后的纯状态结束。现有0调用缓存/目录diff/支持原句复制不应再计Motif省调用；修完不能改写旧实验，也不声称模板能解决所有证据缺口。


- feature/rsi-research-agent/HEAD2368235，未commit/push/PR，原工作区改动保留。第二入口Motif学习原生PDF清单→全部选中文件准备；3/2训练、1篇不同问题认证，实际源重放一致，仅cache_stats排除导航摘要。新guarded协议不放松旧replay契约，公共接口先列明后实施，见`docs/changes/inventory-prepare-motif.md`与`docs/interfaces.md`。
- 新`sss-entry-inventory-v1`在线TypeScript/离线Python，复用旧固定Harness插件/预算/认证库；SDK全工具允许集校验。run-pdf/agent程序与CLI显式开启，Web/HTTP默认不启用并拒绝客户端策略路径；不改上游/旧manifest/依赖/前端。
- 18完整任务/65native子运行/446HTTP200/$1.313175240；加新认证共458/$1.328307816。两篇题目双Motif3/3自动合格、请求30→25.33、输出−9.73%、费+0.52%；三篇题目双0/3合格、输出更多。H各2/3、单各1/3；不支持整Agent稳定降本或默认启用。失败/续接保留，36入口核验批次不是36净省请求，专家质量未认证。原始资料.local，公开实验`docs/experiments/inventory-motif-20261012-9af4e5f0.md`。
- 413Python/79Node+场景27Node通过，3可选Docker跳过，免费Harness与smoke API0，原PDF与18run代码未改。8765/3080服务保留。下一步阅读-only消融和语义交接/分批提交结构诊断，不继续盲目堆入口Motif或扩大UI。

## 最新：多任务入口读取 Motif（2026-10-12）

- 用户当前以相对普通Harness减少调用/输出为主，不要求先胜过脚本；应用闭环降优先级。已有原生84消息中选出冻结目标数组的入口读取前沿，15/10目标学习、5目标独立任务认证；只接管调度，保留语义模型。
- 共享变化先写docs/changes/task-entry-motif.md：新的离线entry_compiler、TypeScript entry_read_policy及公开dsh_entry_motif插件；SDK --entry-policy/--entry-task、prepare_scenario可选entry_motif，默认关闭。现有manifest版本、计价、上游Harness、Web默认不改；接口同步docs/interfaces.md。
- 18真实run/89请求/USD0.145160004，两种已有证据复核观察到节省：H7.33→M3.67和H6→M2.67；单缺口H4→M6且M一次未填出，所有费用/反例保留。不是全Agent同质量/泛化或所有Harness模式结论。学习复用既有21请求/USD0.077256972，本轮新学习API0。
- 所有原文包相同、非目标字段不变、9个真实入口批次已核验；402Python/71Node、免费真实Harness/MCP检查及smoke通过，3可选Docker跳过。原PDF未变，不要求人工审批，无embedding/A100。
- 当前分支/HEAD不变，未commit/push/PR，原服务和工作区保留。公开结果docs/experiments/multitask-motif-20261012-4ba53478.md，完整场景交接scenarios/literature-notes/HANDOFF.md；新策略仍为显式CLI实验，不默认接管生产任务。

## 最新：文献 Agent 第一阶段三任务（2026-10-12）

- 场景内完成首次三篇比较、受控单字段缺口修复、两篇新增第三篇及无变化控制，复用既有 Harness/MCP/预算，新增私有来源反馈与指定字段复核 CLI；没有共享 Runtime/Motif/预算或上游接口变化。
- 初轮68请求/USD0.186649992；原文核对发现自动复核漏检，两次有界定向修订16/USD0.017195688保留负面结果。完整84HTTP200/USD0.203845680，5工具错误/2坏JSON恢复费均保留，0 learned Motif/embedding。原PDF不变，无人工审批；来源核对非专家真值/完整语义质量证明。
- 实际自动依赖图保留旧10字段、处理新5字段并更新综合；初轮及最终修订后无变化控制0模型/0费用。此前全复核说明属于遗留图或旧描述，已修正文档并保留原实验冻结版本。
- 全仓392Python+67共享Node，额外26场景Node/81相关Python通过；3可选Docker跳过。当前分支/HEAD仍feature/rsi-research-agent/2368235，未commit/push/PR，main bc1ecd5及已有服务/工作区保留。
- 公开实验与提交说明：`docs/experiments/phase-one-20261012-8a865a78.md`、`docs/changes/literature-phase-one.md`；完整场景交接见 `scenarios/literature-notes/HANDOFF.md`。下一步先建立缺口执行分支的强基线，再学习/认证Motif，不能按跳过计数宣称收益。

## 最新：Harness / 真正Code Mode / 脚本 / Motif对照（2026-10-12）

- 用户明确要包含Harness；发现此前文献入口没有原生Code Mode，补SDK可选native/ptc、相同MCP权限守卫、Docker部署的上游WorkerThreadCodeRuntime、原生PTC收据分析投影；未改上游/计价/原PDF，生产Web仍native/off。共享变化先登记docs/changes/literature-harness-comparison.md。
- 真实harness-strong-20261012-5da6ab9f：2train+1certify32请求/USD0.055282932，独立评测选页8/USD0.012848964，真实正常native学习1条3节点链，manifest ac8d3f33…。known三论文/一个冻结三窗决定，非整Agent科学或跨语料验收。
- 对照：首阶段d94d87e3四组16次/84请求/0.060794004全部packet相同，但CodeMode逐工具生成程序；记录amendment后全部组同加局部批量说明，强阶段b8a2c8a9四组16次/71请求/0.060951672，包/plan/prompt/source一致。实际请求均值H6.25/C3.5/S4/M4，USD均值0.004437882/0.003663846/0.003463803/0.003672387，Harness秒10.458/11.354/7.951/8.086，Motif每次skip2/embedding0。脚本最便宜/最快，Motif对脚本+6.02%，没有增量收益，不凭skip证明RSI。
- 完整开发36run/195HTTP200/$0.189877572，含首阶段2外层工具失败后纠正、无429/坏JSON/PTC失败子调用；累计PDF代理$3.152304460，实付/维护未知。显式同问题/计划/源缓存4次0模型/0费用，重放0.185秒/含入口0.456，不是learned RSI。私有protocol/amendment/source冻结/final-audit/cache及所有原事件/账本保留，未抹去负面结果。
- 回归：386 Python+67共享Node通过；额外3真实Docker绑定/隔离/取消测试通过。免费真实Harness PTC5子调用/2模拟请求、packet相同。最后统一prompt46相关测试并全仓/smoke复核。仅macOS arm64与Docker内Node22.22.2验收，服务器/Windows未新增验证，无A100使用。
- 接手：默认保留已有批量脚本/核源缓存，固定verify/build Motif仍实验性；先从资料变更/证据缺口的原生轨迹找有可验证前提的分支，再比强脚本/实际CodeMode。新Web全语义质量对照/思考模式/CodeMode+Motif组合仍未做；PTC分析不作原始模型训练见证。
- Git/运行：feature/rsi-research-agent/HEAD2368235，未commit/push/PR，main仍bc1ecd5同origin。Docker为显式PTC可选，普通SDK/Web无需；--tool-presentation ptc或npm run code:check需Desktop和固定镜像，无unsafe宿主回退。最新3080文献Web与8765保留，Docker无sss-ptc残留容器。公开结果docs/experiments/harness-strong-20261012-5da6ab9f.md，完整接口提交说明见上。


## 最新：文献官方Web逐Session接入（2026-10-12）

- 已完成：npm run web:literature，固定服务端PDF目录与独立任务preset/MCP；同Session阅读→自动claim复核最多两轮→完整表综合→真实收据交付。原生聊天/任意路径/通用附件拒绝，预算/记录/单槽仍原Web；原SDK/8765/自研最终前端路线保留。
- 修复：第二轮传原始证据历史及拒绝原因，复核阶段不能通过普通读取绕claim额度；启动包装器转发退出信号，防端口残留。共享变更先登记在docs/changes/literature-web-binding.md，无上游/Motif核心/原PDF修改。
- 验收：378 Python+66共享Node，免费最终51ad10a4两个任务各43模拟请求/15显式缺口，加取消0请求；真实aaf962ec两题各15字段0程序缺口/17和16引文，22/21请求，0.100008924/0.076882584美元。首版8d701dd9的4/1缺口及49请求费用、启动6b82834e失败0请求保留；开发合计92请求/USD0.358430952，累计PDF代理USD2.962426888，实付/维护未知。0程序缺口不是科学认证，本轮verified skip0/没有新learned Motif。
- 数据：私有web-binding-20261012-*/protocol/real-audit/outcome与.local/web/runs；公开docs/experiments/literature-web-binding-20261012.md，后续公平对照协议literature-web-comparison-protocol.md待运行。界面仅预览/取消0付费，问题和论文显示替代内部提示词。最终共享UI元信息修正后免费/回归核验，不重跑付费。
- 限制/下一步：Web仍off，旧工作台缓存/增量更新未迁入；无大PDF浏览器上传、任意子集或跨启动HTTP历史加载。每任务独立preset的长期内存未测。先冻结质量和强脚本基线，从真实轨迹选独立认证候选，再运行相同质量成本对照；不能强用旧web未认证库或宣称现已降本。
- Git/回退：feature/rsi-research-agent/HEAD2368235保留既有未提交工作，main与origin/main仍bc1ecd5，未merge/commit/push/PR。回退到SDK/8765或通用Web profile，不删除历史/PDF/Key。最新文献Web真实服务3080，通过私有access-url认证；8765旧工作台未停。


## 最新场景与main同步：完成收据/单引用（2026-10-12）

本地main已建立、跟踪origin/main并同为bc1ecd5；当前开发工作目录仍feature/rsi-research-agent/HEAD2368235，main Web入口/预算文件按来源合入开发目录，保留场景未提交修改，未完整Git merge/commit/push。SDK入口保留、npm run web通用官方Web动态任务可用。共享新接口completion_guard及固定TypeScript插件使用公开停止钩子，最多2次同Session续接、仍同预算、产物SHA收据才算完成；文献单citation_id解析保留旧格式/权限，不称learned Motif。

371 Python+64 Node、SDK/Web模拟故障诊断通过；真实2380b87f…15字段/18引文/0程序缺口，28HTTP200/0.075927552美元，含全部纠正（6工具失败、3坏JSON、19复核拒绝诊断），未实际触发续接。333ac7f2…同配置缓存0请求，原PDF/Key保持。代理累计2.603995936，未核账单。GitHub记录docs/changes/literature-receipt-guard.md、实验docs/experiments/receipt-fix-20261012-9c6d79d9.md。最终自研前端、暂用官方Web；论文目录/问题与官方/tasks逐Session绑定未接完，SDK/Web固定off、思考模式对照未做，下一步先接绑定再比较。科学正确/净降本未认证，原生记录留私有区。

## 最新场景：阅读归一化与决策记录（2026-10-11）

文献场景完成按实际页尾/重叠范围计预算、保持已选原文的确定性执行；引用权限、失败额度、低文本与源版本守卫保留。新增场景TypeScript决策诊断绑定原生事件/费用，自动交付无Human审批。不修改共享Harness/Motif/预算接口，也不把缓存/批量算RSI。351 Python+44共享Node通过，场景Node23包含在Python包装；日志时间戳小修后23场景Node再通过。

真实开发任务最终15字段/24引文/0程序缺口，同配置核源缓存0请求。包含首次3缺口/未完成续修、新语义补3缺口及开发者复核轮次选错引发全量任务：10唯一run、65HTTP200、USD0.177344580，失败和误触发费用完整保留。原12字段在补证据中不变，原3PDF未改，科学理解/净降本未认证。旧实际超限3例仍拒绝，默认脚本/缓存不变；更新的Evidence执行版本需重新认证旧库。记录docs/experiments/plan-efficiency-20261011-4ebe9910.md，GitHub接口/回退说明docs/changes/literature-plan-efficiency.md，详细当前交接scenarios/literature-notes/HANDOFF.md。下一步优先引用ID选择与未提交便结束，基于原生轨迹再决定有条件Motif；未commit/push/PR。

## 上轮场景：Motif重新学习与脚本强基线（2026-10-11）

新增场景免费机械review CLI/两个原生测试，复用现有Harness/MCP/预算、Python学习认证、v2 manifest和TypeScript在线规则；无本轮新增共享接口。当前profile3下两真实训练/一不同问题认证得到1个既有三节点机械Motif，新默认问题选计划后做同包三轮9任务。6/4/4请求，Motif各2成功原生验证skip，源/参数/许可及callId配对通过；只认证证据准备，既有15字段科研稿和原PDF未改。

结果：Motif平均费用比脚本高1.68%，含启动10.809/10.870秒几乎相同，学习USD0.04752未摊平；同输入缓存0调用。保留显式实验库，工作台默认批量/缓存/模型支持审查路线不切换。没有完整科研质量等价、稳定费用/时延或泛化证明。三次正常计划超12000字符拒后恢复，费用计入，候选不跨失败。

本轮82真实请求/13唯一run/USD0.104601444，HTTP200逐账本核对；累计PDF代理估费USD2.350723804未核账单。344 Python+44共享Node通过（内含21场景Node），实际PDF/新库免费模拟协议另列；Key/原稿/论文不变，本地未提交/推送/PR。当前服务PID50879/8765不需重启。

[完整实验与反例](../experiments/motif-renew-20261011-14c3fc42.md)、[本轮无共享变更的提交说明](../changes/literature-evidence-renewal.md)、[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)。下一步聚焦本次发现的选窗预算、重复补读和来源变化恢复，先对普通脚本/缓存验收增量价值，不继续包装同一固定链。

## 最新场景：批量读计划与最终引用支持（2026-10-11）

已新增来源前后守卫的普通批量读、同论断额度/凭证隔离、最终连续原文anchor/真实句末检查、保守双栏修复及bbox异常保留普通文本。继续复用Harness/MCP/预算，无Human审批。唯一本轮新增共享入口是官方Pro模型ID/旧别名归一与requested_model预览；Flash默认、共享价格/预算/Harness/Motif核心不改，此前共享续接修改保留。

三原论文最终真实修复job39d912a2-f6f0-49a3-8805-3b1888b18782直接交付15字段/19引文/0技术缺口，逐源重放通过；先前0缺口仍有否定截断，最终实际补完整引文。开发源比对不等于专家盲评/科研真值/泛化。相同来源显式同配置重放0新增调用。原PDF/Key未改，原失败稿/费用保留。

真实模型已选同一5窗的四轮暖机MCP对照：普通并行10调用8.994ms、批量1调用3.322ms，上下文完全一样；首版批量更慢反例保留。没有新增learned Motif或verified skip，不能当整Agent收益。本轮252请求/42唯一原生run/USD0.705697132含失败与修复，HTTP200账本核对；累计PDF代理估费USD2.246122360未核账单。342 Python+44共享Node通过（内含21场景Node），工作区未commit/push/PR。

[场景交接](../../scenarios/literature-notes/HANDOFF.md)、[GitHub接口/逐项变更](../changes/literature-read-plan.md)、[实验/质量反例/全部费用](../experiments/read-plan-20261011.md)。下一步固定当前门槛，学习并独立认证新候选Motif，与普通脚本和缓存强基线比较同质量全成本。

## 最新场景：实际PDF来源变化对照（2026-10-11）

普通PDF在独立私有版本中真实新增、同名替换、删除，复用既有Harness/MCP/预算和场景Runtime；无新增共享核心修改。补齐增量超长参数的字段/实际长度诊断，保持120字符上限；删除0变化字段时也重新读取整份当前表做全局综合。场景对照入口默认预览，不另建模型循环。

两协议235实际请求/USD0.391720872含首轮32步失败与重新建库；累计PDF代理估费USD1.540425228未核账单。第二协议新增full/inc 21/39请求、78.901/88.969秒、0/2缺口；替换26/31、95.392/83.698秒、均1缺口；删除17/8、60.334/23.808秒、均0技术缺口。增/换仅处理5字段并原样保留15，删除保留15且重做综合；旧句柄隔离/源重放通过。同源普通缓存0调用，不计新Motif收益。

新增增量更慢且有缺口；独立开发检查仍发现陈述超出选中引文/综合扩大事实，未证明同质量降本或科研质量可靠。接手优先论断覆盖/条件/栏位，再优化新论文读取计划与脚本/Code Mode/Motif对照。全仓329 Python+44共享Node通过，原PDF/Key不改。服务PID8104/8765，当前浏览器显示删除增量8请求；最新缓存job3bb6eed9-f09e-41ca-9b35-9ad0c637c391。

工作区未提交/推送；此前共享接口改动保留在下节，不能当成本輪新增。[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)、[本轮GitHub说明](../changes/literature-source-changes.md)、[实验与反例/完整费用](../experiments/source-changes-20261011.md)。

## 历史场景：普通PDF局部续修与自动依赖更新（2026-10-10）

已把4项技术/引用缺口逐项补读修复；续修只处理缺口，局部更新后自动重写全组综合假设，字段原样保留。自动稿无需Human审批建立Runtime来源绑定图，改/增PDF只重做对应字段，删除重综合，问题/版本/提示变化失效；旧人工图兼容。手写图和普通缓存不称learned Motif，科学质量未认证。

本輪17请求/USD0.017576004，含全局综合收据回收错误；累计PDF代理估费USD1.148704356。全局收据由真实原生工具提交0新请求回收，原成本保留。最终job2caa0f22-44bc-4b32-be27-8145811bd963直接交付15字段/0结构缺口，无变化更新0模型请求/$0；剩余11项未完整独立语义验收，不是净收益或泛化证明。

本次只改场景/测试/文档，没有新增共享核心接口、预算或上游修改，未提交/推送；此前共享变更在下一节单列。[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)、[本次接口/提交说明](../changes/literature-auto-incremental.md)、[实验含失败与费用](../experiments/targeted-repair-20261010.md)。下一步在私有副本做真实变化更新，再比较Harness、脚本、缓存与学习/认证后的Motif总成本。

## feature/rsi-research-agent 的共享接口更新（2026-10-10，本地未提交）

- 用户明确授权修改共享接口并详细记录。新增批准计划续接契约、训练/留出许可检查、manifest v2 与 TypeScript 在线许可守卫；保留上游 Harness、预算算法及 v1 无许可行为。逐文件/GitHub正文见 [变更记录](../changes/approved-plan-continuation.md)，协议见 [interfaces](../interfaces.md)。本段不表示已经合入或推送 main。
- 实验 `approved-continuation-20261010-94934aab`：正常真实模型两训练/一留出重新认证，新问题实测6次真实请求、2次原生验证跳过、0 embedding，3窗原文包逐字重放通过。本轮37请求、代理估费$0.047486532，含一次计划超限恢复；原始轨迹/凭证及PDF保留。科学质量、跨语料和超越普通脚本的净费用未验证，详见 [实验](../experiments/approved-continuation-20261010-94934aab.md)。
- 后续同计划真实三轮 `frozen-evidence-20261010-997d9e47` 完成：每组6/4/4请求，相同包；Motif每次跳过2、embedding0，均值6.636秒/脚本7.803秒，费用均值较脚本仅低1.8%且第三轮反向。42真实请求/$0.031742316，累计PDF代理估费$0.885055476；学习与未知人工成本单列，不支持稳定净收益。[新记录](../experiments/frozen-evidence-20261010-997d9e47.md)。
- 最新全仓284 Python+44 Node通过；实际MCP/Harness固定批准计划免费三组6/4/4模拟请求，包一致。新增场景内固定计划对照与结果缓存入口，未再修改共享核心/schema；完全相同显式请求缓存核验0模型请求。TypeScript生成桥接一致性纳入测试，不新增TS运行loader。新功能本机macOS/Node22已验证，其他平台待CI。
- 场景当前交接保持在 [既有 HANDOFF](../../scenarios/literature-notes/HANDOFF.md)，未再复制第二份。接口之外的其余科研场景工作仍在该分支工作区；`.local/`及`testpdf/`均忽略，不能提交私人PDF/凭证。本轮没有commit/push/PR，后续需审阅工作区并提交允许范围。
- 下一步：按 [分层验收方案](../experiments/literature-evaluation-protocol.md) 留出新论文/研究问题，先验收科学支持与失效回退，再对照缓存/脚本/Harness/Motif的同质量总成本。三篇已知论文及同计划重复仅是机制证据；优先现有有效结果缓存，不靠请求跳过数宣称RSI净收益。

## 此前 main 的交接（历史同步状态）

- **更新时间与交接人**：2026-10-09，Codex 根据项目负责人的要求整理；后续主线负责人由课题组确定。
- **目标与本次范围**：提供三位同学可共同使用的 Motif / DeepSeek Harness / 自定义 MCP 底座。本次补齐随仓库分发的历史 Motif 库、公开证据、免费重编译及 Harness 验收入口，按用户要求提交和推送最新主线。
- **分支与版本**：`main`，运行底座提交为 `9388ed0`；本次提交见 `git log -1`。远端为 `origin`（`jingyio/DeepSeek-Harless`），用户已授权推送当前最新 main；实际同步状态按 `git status -sb` 与远端提交核验。归档分支为本地 `archive`（`810edf4`）与 `archive-pre-cleanup-20261009`（`1d7ec26`），本次不单独推送归档分支。
- **已完成**：通用场景入口 `scripts/run-scenario.py`、场景配置适配 `src/adapters/scenario.py`、SDK 启动边界 `src/adapters/harness_runtime.py`、工具白名单与在线 Motif 插件；保留 Motif 核心及许可来源、18 项冻结科研夹具。入口见 `README.md`，协议见 `docs/interfaces.md`，合作方式见 `docs/collaboration.md`。
- **已验证**：此前在 macOS 及不含历史 `.local` 数据的临时目录执行 `npm test`，通过 133 项 Python、24 项 Node 测试；`npm run smoke` 通过 18 题、读取 83 个来源对象。另有本机模拟 Provider 的真实 SDK/MCP/预算代理闭环。以上属于离线协议与回归检查。本次纯文档修改检查 diff 和路径一致性，未重复运行模型或整套测试。
- **最近复核（2026-10-09）**：回答项目结构与连通性问题时，在当前本机重新执行 `npm test` 和 `npm run smoke`，仍通过 133 项 Python、24 项 Node 及全部 18 题工具检查；包含真实 Harness 对本机模拟 Provider 的三次请求、两次 MCP 调用。没有付费云调用或新的科研效果结论。当前在线路径为场景配置 → Python SDK → Node Harness → 可选 JS Motif 插件 → MCP；Python controller 为独立结构执行路径。新场景接入 Harness 后，要另行收集轨迹、编译认证 library 并配置任务/embedding 才能启用 Motif。现有 `docs/collaboration.md` 未提交修改属于用户工作，本次保留。
- **后续技术路线（2026-10-09，用户明确）**：Python 负责离线学习、编译和科研实验；新增 Harness 在线逻辑用 TypeScript，逐步迁移现有 JS 插件。生产在线 Runtime 以 TS 为权威，Python controller 用于参考/离线验证；不实施之前讨论的 Python 在线桥接方案。SSS 已通过 npm 安装并启动本地 Harness，已有原生插件，但独立插件分发、共享 Schema/类型及无额外 Python 的已有 library 执行尚未完成。当前纯代码节点和实验预算代理仍依赖 Python。本次仅核对代码和更新文档，没有重构、重跑付费实验或重复全套测试；用户在协作文档和 `dsh_client.py` 中的未提交修改保留。
- **首发历史库（2026-10-09）**：新增 `examples/motif-library/research-portfolio-v1/`，保留历史 4 个算子的认证摘要和 library 摘要。出处是真实 DeepSeek 调用、合成科研来源；两项训练/一项独立认证，共 26 次历史请求。公开 46 次工具证据均经 MCP 重放一致，未公开原日志；历史目录叫 v2，但题面哈希匹配 v1，已如实记录。新增 `npm run motif:check` 与 `motif:rebuild`，无须旧私有数据，重编译到 `.local/`，不修改在线核心或通用私有轨迹约束。136 项 Python、29 项 Node 通过，本机真实 Harness 四组协议验收通过：baseline/shadow/execute/旧版本请求为 14/14/7/14，四组工具调用均 13，取得相同对象/版本；结果验证跳过批次仅 execute 为 5。模拟 Provider 和固定 embedding 仅用于诊断，不是科研质量/成本结论；见 `docs/experiments/distributed-motif-example-v1.md`。库开发阶段保留用户的两份未提交文件；后续按用户的提交推送要求处理，范围见下文。
- **实验结论**：离线检查支持当前工具链和所覆盖的安全守卫可运行；没有本次真实研究交付的盲评或付费同题对照，不能据此宣称 Motif 降本或科研质量提升。清理与验证依据见 `docs/main-cleanup.md`；后续实验按 `AGENTS.md` 记录在 `docs/experiments/`。
- **配置与数据**：公开场景在 `scenarios/`，通用配置在 `config/`，依赖在 `package.json`、`package-lock.json` 和 `requirements.txt`。新入口默认 baseline、预览、`reasoning_effort="off"`，预算上限 0.25 美元、16 步、单请求输出上限 3000 token；实际实验以预览和配置快照为准。密钥使用本机 `DEEPSEEK_API_KEY` 或 Harness 凭证存储；MCP 认证用场景的 `from_env`。私人资料与历史原始记录在各自本机 `.local/`，不随 Git 分发。未在本记录中读取或记录任何密钥值。
- **未完成与限制**：Ubuntu/Windows 原生离线 CI 已通过（测试、18 题 MCP、Motif 本机模拟闭环）；真实 HTTP MCP 服务及外部应用场景尚未联调。三个实际场景及负责人尚未在仓库冻结。在线 JS runtime 是 Python 结构执行的子集，不是完整移植；embedding 和具体 MCP 服务的平台适配仍需场景验证。仓库定价表也需在付费实验前核对。
- **接手下一步**：
  1. 主线负责人确认团队共享仓库及同步范围，将需要的本地提交推送；验收是同学能取得相同版本并运行基础检查。
  2. 三位同学各开场景分支，复制 `scenarios/example/`，实现最小只读 MCP 链路；验收包括正常调用、版本/权限拒绝检查及各自场景交接记录。
  3. 选定真实独立研究决定，冻结任务、来源、基线、配置和质量标准；先预览预算，获得对应调用权限后再做付费对照。
- **干净分发复核与提交范围**：在临时干净副本（没有旧 `.local`，复用已安装依赖）通过完整 `motif:check`；重编译和场景 shadow 预览均通过。此前未提交的三位同学姓名分工按用户的“推送当前最新代码”要求纳入；语义客户端待提交改动绕过跨平台适配，推送前修正回 `create_harness` 统一边界，`reasoning_effort="off"` 仍由该边界设置。没有修改 SDK 上游核心。
- **权限与预算**：当前授权涵盖本地备份、主线整理、样例库开发及最新 main 提交和推送。此前整理和本次验收没有新增付费模型支出；团队后续总预算与剩余额度未知。没有授权本次发送邮件、写外部应用或开始新的付费实验。
- **Windows CI 修复（2026-10-09）**：用户提供首次 Windows CI 的 8 个失败，已定位为 LF/CRLF 原始字节哈希、cp1252 解码中文和不适用的 Unix 模式位断言；前两份哈希差已由换行转换精确复现。新增 `.gitattributes`、入口 UTF-8 配置、显式文本读写及平台限定的模式位检查；保留冻结哈希与所有非模式位安全验收。本机仍通过 136 项 Python、29 项 Node。推送后以对应平台 CI 为准；细节见 `docs/experiments/windows-ci-compatibility.md`。未调用付费模型。
- **回退与风险**：文档可按对应提交单独回退；完整历史可从两个归档分支查阅。不要直接把全部 archive 合回 main，也不要删除 `.local/`。通用入口的 `--call-model` 会启用付费调用；有副作用的 MCP 还需服务端权限、预览和确认。

- **Windows CI 验证结果**：修复提交 `c05127f` 的 [运行 37888988141](https://github.com/jingyio/DeepSeek-Harless/actions/runs/37888988141) 中，Ubuntu 与 Windows 均完成并通过 `npm ci`、环境安装、`npm test`、`npm run smoke`、`npm run motif:check`。本地 `core.autocrlf=true` 干净检出额外验证了 79 个冻结文件的原始哈希。当前已验证离线及模拟闭环，不能扩大为所有真实应用/MCP 或付费云实验的支持结论。
