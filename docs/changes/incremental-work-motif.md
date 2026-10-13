# 增量工作清单 Motif 与提交契约修补（实施前记录）

2026-10-12，用户授权按诊断推进：先最小修复提交契约，再优先探索增量文献整理的Motif。旧实验/原始事件不变，保留科学支持、来源版本、引用和有界尝试检查，不以放宽门槛获得通过。完整组合/交付尾部Motif本轮不默认启用。

## 场景内修补

统一pdf-repair-task中的supported条件：支持复核需要support_anchor，普通模式原句/引文由Runtime复制。分别提供支持复核、普通复核、缺口及revised格式；80/120限制由packet确定。MCP提交工具暴露有字段、verdict和条件必填项的类型，而非list[dict]。HTTP/SDK名称和Runtime验证语义不变；格式错误仍有界，原3次额度暂不放宽。新Schema/题面属于所有组的公共接口优化，不计入Motif收益。

## 所需共享变化（先记录，再实施）

1. 原entry_compiler的受限清单前沿增加显式incremental变体：原生read_update_plan成功返回work对象数组，完整遍历work[].paper_id→prepare_pdf。逐调用/参数/结果配对，至少两个不同任务/不同目标数训练和另一个任务认证；当前计划全量重放、来源/解析器版本一致。不能用Runtime生成事件训练，不能学习“新事实仍正确”。原inventory变体保持原验证。
2. 原inventory_entry_policy的受限状态机增加独立sss-entry-incremental-v1协议分派：冻结完整计划返回摘要、plan_sha256、当前任务SHA、每个受影响PDF及解析版本。参数来自真实work结果；只准备受影响目标，不能把retained字段扩成处理对象。错误或计划/来源/schema/提示变化交回模型；0work未认证分支交普通路径，完全无变化仍是既有0调用缓存。
3. 原entry_read_policy增加此协议分派，复用固定dsh_entry_motif插件/原生工具/审计/预算；SDK不增加任意插件接口，原两个协议和旧manifest不变。run-incremental --entry-policy与agent程序/CLI incremental_entry_policy显式开启，默认关闭，HTTP不接受策略路径，旧manifest互斥。

## 实验边界

原资料不改；使用当前三篇已知PDF与已有模型事实生成可回源的派生基线缓存，明确记录seeded-baseline来源和机械源绑定，不伪造旧模型事件/专家审核。旧工作流版本变化会使旧缓存失效，新的派生缓存按当前版本重新核源索引，不覆盖原历史作业。学习/认证仅使用新普通原生增量轨迹。

测试新增2篇、增量新增1篇、独立另一选择新增1篇等不同更新任务，阅读窗口与新增事实判断仍是原Harness。冻结同一输入/计划、模型off、工具/题面、预算与输出限制，原生Harness/Motif串行交错，记录真实HTTP、缓存命中/未命中、输出、费用、耗时、失败和保留字段。来源/旧字段保留/完成收据为机械门槛，科学支持未专家验收；学习/认证成本单列。三个已知PDF足够机制开发，不支持新材料泛化。

共享修改后npm test和免费真实Harness/MCP smoke；实验前冻结有效代码/策略/输入，所有失败保留，不以替换不合格样本美化均值。实测后追加结果及GitHub提交接口说明。

## 已实现的兼容与记账细节

- supported显式携带原句/引文的旧调用继续支持，类型字段可省略；Runtime仍要求原值完全一致。gap题面与Schema只提供三字段。类型校验在进入场景提交前拒绝格式错误，因此不消耗论断语义尝试；真正进入原Runtime后仍按原3次计数。该层次变化两组相同。
- Python默认frontier='inventory'保持现有调用，新增值仅incremental；认证要求相应witness类型和source.work绑定，不能拿inventory认证代用。TypeScript三个入口分派复用已有状态机；旧两个格式不变。
- `run-incremental.py`的input-snapshot增加entry_policy_digest；真实upstream请求仍取原SDK账本。没有替换费用代理/模型循环，没有改上游Harness或预算接口。
- agent选项新增incremental_entry_policy/CLI --incremental-entry-policy，只有已有父图的增量阅读接受。普通阅读/续修拒绝；HTTP拒绝该路径。不会自动把claim策略用于增量事实判断。新策略默认关闭。
- 免费检查复用check-inventory，新增--incremental-run以启动原增量MCP。新learner独立入口learn-incremental；训练/认证失败不强制兼容。

## GitHub提交正文要点

增量文献整理此前仍需模型读取更新计划并生成受影响PDF的prepare参数。本次从独立原生轨迹认证该清单前沿，Runtime检查当前完整计划/文件/解析版本后执行，随后交回模型选择证据和产生新事实。已有旧字段缓存保持原确定性基线，未计为新增Motif收益。同步修正支持复核题面冲突并暴露条件必填字段，两组共用此改进。

共享改动限上述三个core文件；固定dsh_entry_motif插件、SDK参数/预算和上游Harness不变。新增协议显式开启，旧协议保持；旧claim schema绑定策略须重新认证。失败回退、来源变化、retained不重处理、原始事件配对和实测结果需要与提交一同审阅。取消新选项即可回到普通Harness增量路径，无需删除旧数据。

## 原生轨迹导致的公开流程修订

首版三次普通任务都完成并无机械缺口，但两个单work轨迹的第二请求把prepare_pdf与额外list_pdfs混合，不能按原“纯prepare”前沿认证；保留这些否定见证和全部费用，不删除额外事件或重复等待命中。改为在公共增量题面明确：read_update_plan已经给出成员，准备阶段先仅批量prepare全部work，再选择证据。该普通Harness流程优化两组一致使用，不计为Motif收益，也不声称候选自动发现。新自动workflow版本需要新派生缓存/训练/认证/对照，首版结果与新版本分开。

同时把gap题面中的规范文本写清为Runtime输出，提案仅三字段，避免与新明确Schema冲突。这也是两组公共修补，不放宽证据支持。

离线联调修正：新增pdf-incremental-contracts.json为现有read_update_plan登记只读但非replay-stable契约，和原pdf-contracts合并加载；原工具实现/Schema未变。执行版本包含该登记文件，避免后续静默换契约。首次编译因缺契约登记失败、策略不存在时的免费检查启动失败均为0付费调用，原日志保留。补登记后要求原计划及导航全量重放一致，不能强行升级不兼容轨迹；本次三条正常轨迹重放一致。公共workflow未因契约登记而变化，既有缓存不被追写。

## 验证与当前启用决定

已从新原生2/1工作量任务训练，另一个独立任务认证；policy_digest=f96c52f47623ff948df4a6ceadaa08c939ad0501ed60fb4ee21d5aab382c8a0d。实际SDK/MCP免费3工具/2批次、仅work准备；6个真实Motif任务各2批次核验且无deferred。十二次真实对照一篇M请求/输出/费用分别−29.41%/−18.83%/−5.17%，两组3/3收据且无机械缺口；两篇M费用+12.79%且失败/缺口，默认继续关闭，不按篇数自动选择。完整逐样本与全部费用见[实验记录](../experiments/incremental-work-motif-20261012-a55cdbd9.md)。

npm test419 Python、84 Node通过（3可选Docker跳过），场景另28 Node，末轮48相关Python与免费smoke通过。新明确Schema真实模型probe1事实3请求、首提交带145字符原文anchor、无错误；科学支持未全面验收。首版/编译/启动失败保留；本轮267HTTP/代理估费USD0.55989722，账单实付与维护未知。

本地未commit/push/PR，旧脏工作完整保留。新clone需自身正常原生轨迹/源重放后认证，未分发私人PDF/Key/日志/策略。已有完全无变化缓存、提交类型改进和公共准备阶段优化不算Motif收益。
