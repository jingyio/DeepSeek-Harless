# 文件流程按版本学习和独立认证接口

本轮G4复用既有参数边、集合和预授权计划编译器，以及权威TypeScript执行器。新增的是场景离线学习、证据核验、版本清单和实际MCP重放入口；未修改共享Motif IR、编译器、TS在线规则、上游Harness、工具Schema或默认Web。用户文件仍只在testpdf实验副本内操作，GitHub同步继续暂停。

## 入口和证据范围

`workflow_learning.py`读取已冻结的普通探索来源，再制作补充训练及独立认证副本。实际调用仍由`workflow_study.run_task`交既有CLI完成；仅显式`--role explore/certify --call-model`付费，每题原USD5/96请求与步骤/4000输出/2修复上限。认证调用必须已有candidate-lock；已有结果拒绝覆盖。首次学习阶段只有3个新训练任务，分析修订版通过`--training-parent`引用其原始成功轨迹，不重复收费或修改旧结果。

| 文件 | 变化 | 守卫和兼容 |
| --- | --- | --- |
| workflow_study.py | outcome.role从固定explore改为原冻结case.role | 原探索仍explore；不重标旧轨迹。新的认证样本不会被汇总器误计训练 |
| workflow_learning.py | 学习只接纳explore，独立认证只接纳certify，均需H/普通来源、实际完成、当前收据及任务验收 | probe/holdout、失败业务任务、Runtime或投影调用拒绝；原事件、输入和源码SHA核验 |
| workflow_learning.py | 按WorkflowScene或RecoveryScene的实际执行摘要、相关源码依赖和完整Schema分组 | 不要求无关文档或离线脚本与历史执行快照一致；使用到的服务依赖必须逐项一致，旧失败版恢复轨迹排除 |
| workflow_learning.py | 编译前重放原读取字节/解析/版本；集合片段保留原seq、模型usage、调用/结果，边界从实际选择到同集合成功汇集 | 原编译器仍检查完整顺序、来源和所有中间调用；不删除失败来拼接成功路径；每个独立任务最多一个集合见证 |
| workflow_learning.py | 候选在首个付费认证前冻结，认证不能改写compiled目录；公开优先级决定独立见证选择 | candidate-lock绑定候选、训练报告、协议和学习源码；变化须新版本，认证材料不能回流训练 |
| workflow_learning.py | 实际MCP说明非空时按原绑定器核验；为空时用冻结基类方法文档补充离线描述 | 实际Schema/说明原值及SHA不变；描述是展示和匹配元数据，不是执行许可，未放宽共享Schema检查器 |
| replay-file-workflow-motif.py / .mjs | 独立认证轨迹的实际选择/预览在新副本上复放，交现有TS控制器提出后续调用，并经真实MCP执行 | 无模型Provider、0云费用；自动调用明确标为Runtime，不能训练；版本/Schema失效与撤销必须停在效果前 |

读取业务任务合格不必然提供集合图见证。先读后选择、未读集合汇集、选择后的失败调用或插入其他操作仍可能被编译器拒绝；拒绝原因和原轨迹保存。工程限定的集合/计划图语法未扩展，不声称学习任意控制流。

## 服务和计划组件的双层版本

14工具的集合/读取图绑定WorkflowScene执行版本`85390f91…`及相关读取/契约源码。15工具的组清单绑定RecoveryScene执行版本`c1b878a1…`，包括TaskScene、读取权限、任务账本、预算桥和验收守卫。

PlanScene的预览、授权、执行和持久化状态本身返回组件版本`ae4973ce…`，不是外层RecoveryScene版本。新计划策略按实际组件包认证；`library-lock.json`另绑定外层服务及其依赖。固定重放器调用前必须核对外层清单，MCP每次写入仍检查原job权限与预算。不能把组件版本相同当成任意恢复服务兼容，也不能脱离该清单宣称组合在线认证已完成。

当前计划认证范围仅既有全局重命名、move和本题不超过3个源文件。编译器通用图中的6动作与copy/quarantine语法上限，不代表这些扩展在RecoveryScene获新认证。计划控制器在执行失败时只停止并交还语义层，不自动重试或restore；回滚由普通模型或明确标注的免费重放程序使用原授权执行。

## 产物和激活

`compiled/candidates.json`和`candidate-lock.json`是训练决定；`libraries/workflow14`保存独立认证的读取产物，`libraries/recovery15`保存独立计划产物；`library-lock.json`记录组的服务/组件摘要、源码依赖、产物SHA及认证来源。失败、原事件、账本和逐轮验收继续存私有.local，不进入Git。

权威Node验证器核对产物结构，免费重放再验证实际MCP和现有TS控制器的来源、版本、字节与停止行为。普通DeepSeek的独立认证任务提供实际参数传递见证；免费重放不计模型收益，业务质量仍需人工评审。

新库未全局启用。尤其durable_job CLI继续只接受普通baseline，尚不允许计划策略组合；后续在线接入必须同时落实外层清单、原job权限/预算和停止守卫，再验证真实模型的库执行。默认SDK/Web、旧库和旧工具不切换。留出保持未运行，G5尚未开展。
