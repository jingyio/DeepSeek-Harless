# 批量脚本对照与计划认证：共享接口记录

2026-10-13，授权范围见实验文档。与大量既有未提交工作共存，改前文件逐项归档在.local/file-management/interface-before-batch-plan-20261013；未改上游Harness或预算代理。

读取阶段新增collection_batch_script.ts：手写四角色、批次8、容量32、独立sss-collection-script-v1及script_digest，无artifact/认证伪装。collection_read_policy.ts仅把已有执行器拆出createGuardedCollectionExecutor，认证入口仍先严格验证旧policy；两组共享实际参数/版本/覆盖/提示守卫和调度。脚本审计用collection_script_*，批次指标collection_script_batches_verified，与Motif审计分开。

dsh_entry_motif.ts新增显式脚本配置/任务，复用后选择gate，可与所有Motif/PTC互斥。run-scenario.py新增--collection-script/--collection-script-task，私有路径/批准工具/权威Node校验、实际session/prompt绑定，普通入口清空脚本环境。环境SSS_COLLECTION_SCRIPT/SSS_COLLECTION_SCRIPT_TASK，preview记录script摘要和执行模式。experiment.run_one新增可选脚本文件/任务，默认行为不变，分别保存hash。

scripts/file-batch-study.py冻结新18三组任务，复用原普通执行、预算及验收，不造模型循环。源码另捕获新增共享模块，common.py保持原字节以维持旧MCP执行版本。check-file-collection.py新增--script免费实际SDK/MCP检查，不训练/不作真实费用证据。5项新Node检查覆盖无库加载/错误配置/独立审计；旧11项集合检查继续。

计划认证的协议、实现、测试、真实结果将随阶段追加；目前不把预定方案写成成果。

## 已实施的计划接口与边界

新scenarios/file-management/plan_tools.py独立继承FileScene，旧12工具与原认证库不改；新13工具在H/M一致。preview_actions(actions)沿用Action输入、限定copy/move/quarantine，返回preview_sha256、计划/输入/当前快照/执行版本/grant摘要及copy_only/permission_status。authorize_plan(plan_id)检查冻结task write_grant，返回唯一authorization_id、计划/preview/权限/快照/版本摘要、single_plan/operation_count和authorization_sha256，不是由模型决定授权范围。

execute_plan(plan_id,authorization_id)与restore_plan(plan_id,authorization_id)要求精确匹配capability，不兼容旧单参数签名，只在新服务使用。grant列明源路径、目标前缀、操作、最大6项、恢复许可；未知/异计划token、任务/版本变化、过期snapshot、已消耗/已恢复计划、冲突覆盖均拒。未改变原文件权限。

授权、计划、备份、逐动作边界、最终收据保存于每attempt delivery的plan-state/journals/backups；state/preview/token等均有版本化摘要。state为可信私有文件的完整性检查，不是对抗拥有本机文件写权限攻击者的密码学签名。字节私有staging完整写入、同一文件系统无覆盖hardlink发布，移动再删源，所有步骤保存预测/实际字节状态。部分失败禁止重执行effects；同token恢复只在日志after等于当前字节快照时允许，保留其他来源；后来计划/外部不同字节、失效版本、未知中断状态拒绝。重启识别已记录有限原子边界，成功执行/恢复重复返回原收据。仅一个服务串行工作、同文件系统；未认证跨进程并发、原文件权限/时间戳/目录属性保持、任意机器掉电或相同字节替换的inode身份检测。

新Python plan_compiler离线要求真实模型usage/原生call-result唯一时序、preview→authorize→execute实际参数关系、权限/快照/版本与效果收据一致，独立变动作数训练及另一个任务认证。受限三角色语法由工程限定，非任意控制流自动发现。Action.format缺省none仅按同一冻结schema规范化，不猜计划/授权ID。真实文件备份/效果重放另外核验。

新TS authorized_plan_policy解释独立sss-authorized-plan-v1，仅在当前模型实际preview后生成authorize/execute，核验实际token和效果收据后才计plan_model_requests_bypassed_verified。执行失败即停止自动续接、交回模型恢复，不自动猜测恢复/权限/语义分支。源动作、目标和报告仍模型选择；模型调用restore不是Runtime生成节点。

dsh_entry_motif复用现有会话/实际prompt/user envelope/gate/工具公开钩子，新增SSS_PLAN_MOTIF_POLICY/TASK，与所有旧Motif/脚本/PTC互斥。run-scenario新增--plan-policy/--plan-task、私有路径/准许工具/Node权威策略校验、session/prompt绑定、preview执行模式/摘要、正常入口清空新增环境；experiment.run_one可选计划文件及hash。budget代理和上游Harness未改，默认SDK/Web不开。

验收第一版在一次真实copy完成后错误重新构造初始FileScene，抛ValueError。保留fm-plan-20261013-596394ac首任务原stdout/收据/事件/账本/最终副本及验收失败，9HTTP/USD0.004298748补记，不追改失败。修正版scope只读冻结原快照；experiment.run_one现在捕获验收异常并写失败outcome/完整cost，防止已经消费的调用因验收抛错消失。新IDfm-plan-20261013-b2a877a4冻结后重新训练/认证，旧源完整归档。

13项实际权限/效果/重启/恢复Python回归，7项编译证据检查，11项TS权限/来源/版本/返回/失败交接检查；修正版全量523Python/127Node通过，3Docker跳过。3普通训练、2认证及5实际字节重放已认证1个新计划Motif，摘要847b59b0…5627f。SDK/真实评测/费用结果见实验文档；模拟Provider始终不参与训练或真实费用结论。

## 最终审计与轨迹归档

读取18次全部合格，H/S/M请求55/37/37，S最低费、M比S贵2.35%，无Motif相对手写批量增量费用证据。计划13次12合格，评测M4/4、H3/4，3对共同合格估费−3.55%，清理费用+5.08%；故障后的restore均为真实模型调用。全部失败/恢复保留，实付未知。

collect-file-management-graphs.py兼容无parent/previous的新协议，识别所有sss-节点及手写脚本，排除全部Runtime来源，不把旧数组/权限observer缺口写成完整参数发现。统一7实验150图/3733节点、701Runtime排除；旧标量候选与新learned数组/授权证据分别保存，不修改旧库或反训评测。辅助检查/审计/收集源码另存各私有analysis-source及SHA，源码和协议冻结不追改。
