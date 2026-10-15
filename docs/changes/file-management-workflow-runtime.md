# 首批文件流程的验收与持久化任务接口

本轮把首批六流程的设计落实为新副本、固定验收和免费MCP验证。前五项使用独立WorkflowScene；FM38使用只覆盖重命名/自身计划撤销的RecoveryScene。旧File/Collection/Report/Task/Plan服务、读取图依赖和既有库不改。当前只本地开发，未推送。

## 新场景与验收契约

- `workflow_contract.py`定义`sss-file-workflow-v1`：workflow_id为FM01/05/13/17/21/38，source_paths、destination_prefixes、required_reads、allowed_reads、context_paths和recovery_goal。路径、集合上限和额外字段由Pydantic与跨字段检查共同验证；[公开Schema](../schemas/file-workflow-contract.schema.json)不是旧task kind扩展。
- `workflow_tools.py`继承ReportScene，保持14工具顺序，新增真实读取范围、目的路径/原件授权、先读发布说明再选版本、备份到恢复的实际来源映射，以及ZIP排除项守卫。`read_task`返回工作范围与执行摘要，不返回私有答案；报告添加workflow_contract_version及workflow_execution_version_sha256。
- 私有oracle有文件SHA，任务本身也固定其SHA。独立验收从实际目录、读取、日志和ZIP成员检查字节/路径/身份/缺口；对比真正执行版本。正常报告收据仍经原固定程序核验。由实际效果验收派生清单，模型没有新任意写文件能力。
- `validate-file-delivery.py`优先识别workflow_contract，再识别旧task/report契约；旧输入继续旧口径。FM38回滚目标由新workflow契约验收，不把“恢复原件”当成重命名完成。每轮任务/事件/收据/目录/报告/预算快照独立保留。

## 任务权限、预算与状态

`file_workflow_job.ts`是权威任务状态写入者。初始化绑定私有任务原始字节SHA、交付目录、执行版本和原预算/请求/步骤/输出/修复上限。序列事件不可覆盖且有摘要链；state.json是可重建视图，不能通过覆盖视图把计数归零。单写入序列冲突会拒绝；这不是多进程并发产品协议或密码学签名。

请求先以纳美元单位持久化上界和pending，再调用上游。使用完整成功usage才释放多余预留；未知或失败usage仍占原预算。请求、步骤和最多2轮修复跨重启保存。取消、撤销、完成、失败或耗尽状态不能静默恢复；显式pause只允许同执行版本resume。原任务/grant变化不接纳新请求。

`file_job_budget.py`是固定Python桥接，复用原保守价格计算和HTTP代理，持久化变更交给TS。不另造Agent循环，也不改原价格表。桥接保存逐请求账本；系列总费用仍由实验控制汇集，单个job不负责多个实验的全系列合并限额。

`recovery_tools.py`通过明确MRO组合TaskScene与PlanScene：全局重命名预览/读取规则→原计划授权→持久化效果/自身计划撤销。新服务15工具，execute_plan/restore_plan保持PlanScene的双参数授权标识；读取/版本和来源检查仍执行。每次写前检查任务状态与预算。当前只支持rename/rollback、有界普通文件、同文件系统与已记录日志边界；未支持任意转换/分类流程的通用恢复。

冻结的`recovery_crash_after_publish`用于明确标注的免费探针或真实恢复探索，在日志已记边界后让MCP子进程退出75。恢复使用原授权识别实际字节，不盲重放部分计划；未知外部状态仍拒绝。

## 共享入口的逐项改动

| 文件 | 新行为 | 旧路径与失效规则 |
| --- | --- | --- |
| scenario.py | acceptance_guard可显式添加durable_job=true；固定插件配置追加FM_JOB_FILE | 无此字段保持原配置；未知/false值拒绝 |
| dsh_acceptance_guard.ts | 可绑定job，持久化验收轮号、修复计数、成功/失败/取消 | 未绑定仍原同Session规则；任务/交付/修复上限不符拒绝 |
| run-scenario.py | 新--file-job读取已有任务，绑定同任务/目录；冷启动换传输Session，保守代理使用同持久化账本 | 不创建/重置job；须与durable_job配套、原预算/步数/输出精确一致；仅普通baseline，拒绝未认证Motif组合 |
| validate-file-delivery.py | 新流程分流、真实效果验收、派生清单及job视图快照 | 历史任务不追改；旧失败和旧证书保留 |
| project.mjs | npm test加入6项TS持久化回归 | 原测试继续执行 |

CLI的upstream_requests/budget_accounted_usd记录本次增量；durable_requests_total/durable_spent_usd_total/durable_repairs_total记录任务累计，避免重启后把累计估费重复计入系列。默认SDK/Web配置不自动切换服务；动态前端未接入本轮入口。

## 版本、回退与保留

当前实验`fm-workflow-free-20261013-de2f6604`保留完整frozen-source、工具schema、54模板/私有oracle、实际MCP/Harness事件、每轮验收、日志、任务事件账本和模拟HTTP记录；开发改前文件、源码差异和失败日志在`.local/file-workflow-development-20261013`。早期25/33项免费版本均保留，最终协议另冻，不把旧材料/成绩重写成新版本。

关闭新服务/--file-job，使用原TaskScene配置即可回旧入口。不要把恢复服务的15工具或新执行摘要塞进原14工具证书；本轮未学习、修改或认证新Motif。未来付费探索须重新核对源码/工具/模式/权限/系列剩余预算。

最终验证见[免费准备记录](../experiments/file-management-workflow-free-20261013.md)。当前565Python、145Node通过，3可选Docker跳过；最后版本校验定向26项通过，18题旧MCP烟测通过。真实API新增0、真实模型估费USD0，未做人工业务质量盲评或跨平台恢复认证。

## 真实探索后的接口修订 2026年10月14日

本次G3新增14次真实普通探索、12通过/2失败，逐项结果和费用见[真实探索记录](../experiments/file-management-workflow-exploration-20261014.md)。以下覆盖上面免费阶段关于传输Session的初版实现描述，旧源码和失败记录均保留。

| 文件 | 修订 | 权限和兼容规则 |
| --- | --- | --- |
| recovery_tools.py | read_task新增recovery_state，返回实际plan_id、唯一authorization_id、日志状态、原动作、可撤销状态和快照匹配；增加恢复/读取说明 | 只交付现有任务的持久化计划能力，不暴露私有账本或oracle，不生成新授权 |
| recovery_tools.py | pin_file在生成句柄前核对workflow.allowed_reads；空列表的rename/rollback只使用目录和哈希 | 第一版两次真实历史越界仍失败；新服务SHA改变，旧job不可按新版本续接，另做新任务验证 |
| validate-file-delivery.py | recorded_crash_restart仅识别已冻结FM38故障、完整状态SHA/输入/计划版本、executing日志及实际已记录inflight字节边界；返回restart_required | 未知外部变化不触发续接；不能以此放宽读取或覆盖权限 |
| dsh_acceptance_guard.ts | 原验收失败先保留证据并分配一次原限额repair；restart_required再抛TASK_RECOVERY_RESTART_REQUIRED给受限调度器 | 非restart保持原同Session修复；job计数和状态不重置，最多2修复；无job旧行为保留 |
| run-scenario.py / 停止守卫 | 每个冷启动生成新传输Session，验收归档改按同job路径SHA定位；CLI请求/费用记本段增量，durable_*仍是任务累计；错误消息进metrics | 固定SDK不能重开已有Session；使用新Session仍绑定原任务、交付、源码/限额，未修改上游Harness；无job仍原Session归档规则 |
| workflow_study.py | 新离线启动器冻结探索任务/源码/schema/配置、预览预算、顺序调用既有CLI；只有固定验收标识允许最多一次冷启动 | --call-model才付费；全系列USD1000和每任务USD5；已有outcome不覆写，待结算费用不自行归零；--workflows FM38另生成新文本副本 |
| audit-workflow-exploration.py | 读取归档源码核验原版本、真实字节、HTTP/token/费用；--pool汇集观测图并按版本/schema分组，保留失败但排除训练 | 无模型调用、无认证/执行权限；免费、模拟和留出不参与；当前只提取scalar参数边，不能声称已学得任意效果图 |
| check-file-workflows.py / check-file-workflow-sdk.py | 新增原件读取拒绝和整Harness冷启动检查；SDK模拟故障后的新Session仍用同job和预算 | 模拟12HTTP不计真实费用、不训练；原Session重复创建失败留存 |
| test_file_workflow_job.mjs | 新冷启动守卫回归，核验修复/验收跨Session累计与原job成功终态 | 原6项持久化测试继续运行，共7项；不改旧场景配置或默认Web策略 |

实际付费FM38-E由原MCP客户端重连后同Harness完成回滚，未使用外层CLI冷启动；整Harness冷启动当前只有真实SDK/MCP加本地模拟Provider的证据。二者分别记录，不能合称同一真实模型测试。

修订后565Python/146Node通过、3Docker跳过，33免费MCP及18旧smoke通过；第一版恢复两失败、新两任务、59次工具错误、原Session免费失败及费用全部留存。最新只本地，未新增证书、未启用动态前端、未提交/推送。运行后README/规划状态更新改变整目录冻结摘要；新付费任务应prepare新版本，旧验收审计使用自己的frozen-source。
