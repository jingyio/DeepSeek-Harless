# 多任务 Motif：冻结目标集合的入口读取（实施前接口记录）

已实施并实测，原实施前设计保留。结果：两种已有证据复核节省调用/输出，单缺口补读出现反例；默认产品入口不开启。见[实验记录](../experiments/multitask-motif-20261012-4ba53478.md)。

2026-10-12。用户将研究主目标明确为相对普通 Harness 减少调用/输出 token；脚本和 Code Mode 为辅助对照，不是否决条件。不再新增应用功能或把完整专家质量验收作为机制实验的启动门槛。保留机械来源/版本/输出门槛，语义结论范围单独报告。

## 已发现的候选与选择

原始三任务事件显示：首次比较的支持复核读取15条冻结目标，两篇基线读取10条，新论文复核读取5条；在任何语义操作之前，模型只生成这些已知目标的读取参数。选择“入口目标集合→逐项目读取→结果逐一校验→语义交接”，不是旧 extract→verify→build 链的重命名。

离线从两条正常基线轨迹学习 all_targets 选择前沿，第三条任务认证。实际工具结果再从当前 PDF 重放核对。受控缺口、带独立反馈的追加修订和运行时生成调用不参与训练。相同论文但不同任务/语料/目标集合是开发认证，不称独立新论文泛化。

## 所需共享接口变化（先记录，再实现）

1. 新离线 `src/motif_core/offline/entry_compiler.py`：复用现有 artifact_signature、contract_signature、library_from_certified；验证原始模型入口读取前缀完整覆盖被冻结目标，不接收手写调用序列或旧分析投影作为见证。产物为现有认证库中的一种入口前沿 artifact，独立协议 `sss-entry-read-v1`，不是强行放进只支持工具后续边的 v1/v2 在线 manifest。
2. 新在线 TypeScript `src/motif_core/entry_read_policy.ts`：解释唯一受限节点 `foreach target in task.target_ids -> read_only_tool({scalar_param:target})`；目标来自宿主冻结输入，数量1–100、唯一、逐项核验。空集/不支持集合/版本变更/工具失败交回原模型。不执行科研选择或任意代码。
3. 新公开 Harness 插件 `src/adapters/dsh_entry_motif.ts`：在可信原始任务的首个模型请求前执行学习前沿，复用既有 syntheticToolStreamBatch 与原生工具调度/结果回调。每批最多8；只有实际成功结果的ID/版本/参数都匹配才记验证绕过。原事件保留运行时标记，不能冒充模型训练见证。多批绕过计数与真实HTTP请求节省分开报告。
4. `prepare_scenario(..., entry_motif=False)` 与 SDK `--entry-policy`、`--entry-task`：只加载固定上述插件，不能由场景/HTTP传任意模块。默认关闭，和旧Motif/PTC模式暂互斥；没有改变原v1/v2规则。`run-scenario.py` 将生成的真实Session、完整提示SHA绑定入口任务，保留原预算代理和模型参数。新审计种类追加到既有私有审计路径，指标区分 runtime entry bypass 与旧续接。

场景 `repair-pdf.py` 新增可选入口策略文件，生成当前来源绑定的目标 task；两组使用相同提示/工具集合/输入及读额度。机器来源校验值须由可信输入重新计算，不采用模型自报 supported。生成的task、策略、模型轨迹和账本仍在 `.local/`。不修改上游 Harness、计价、原 PDF、Web 默认或前端，不启用 embedding。

已实现的协议产物复用原 `certified_read_library`，新在线策略格式`sss-entry-read-v1`；原manifest版本不变。SDK新计数`entry_model_requests_bypassed_verified`和旧`model_requests_skipped_verified`分开，净节省以真实HTTP对照为准。`scripts/project.mjs`只添加新Node回归入口。工具实际输出、失败和Runtime标记均保留，不重写为原始模型训练事件。

## 认证与比较口径

候选来自正常原事件；学习与认证用不同完整任务，后续评测目标与输入另行冻结。模型首批调用和 Runtime 结果的内容要求一致、未选字段不变；不要求模型自然语言随机输出逐字相同，也不冒称科研语义质量等价已获专家认证。首次模型读取请求与其输出 token 为可审计的直接节省，完整任务费用/输出及失败分别比较。学习所依赖的既有轨迹费用单列，不隐去。

验证包括空目标、遗漏/重复/扩展目标、原始事件篡改、认证复用、摘要/工具schema/来源版本变化、读失败、非Agent模型请求、Session/提示变更、批次上限和预算失败。共享改动后运行 npm test 与相关免费 Harness 检查。实测前冻结预算/模型/顺序/新任务，保留所有不合格结果，不因净费用更高停止记录或夸大成功。
