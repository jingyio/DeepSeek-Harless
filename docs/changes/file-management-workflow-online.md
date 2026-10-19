# 持久化任务与认证计划Motif在线组合

2026-10-14，本地 `feature/rsi-research-agent` / `dfe4fcc` 后的未提交改动；用户继续授权原1000美元系列预算、testpdf实验副本、保留失败和费用，留出先不动、暂不推送。

## 共享接口

- `scripts/run-scenario.py` 新增 `--file-plan-binding <private.json>`。显式durable_job场景只允许普通baseline，或成对的 `--plan-policy/--plan-task` 加原 `--file-job` 和组合绑定。其余策略/PTC组合继续拒绝。预览核验组合是否eligible，但不激活任务；付费入口仍需 `--call-model`。原冻结budget/output/steps必须完全相同。
- 新 `src/adapters/dsh_job_plan_gate.ts` 解释 `sss-durable-plan-binding-v1`，不编写新计划图。绑定原job文件、任务原字节SHA、delivery、服务版本、原limits摘要、旧library-lock原字节SHA、计划policy原字节SHA、4个在线模块SHA。旧库的recovery15所有服务依赖与外层版本、计划组件版本均校验；不能仅用组件版本替代外层认证。
- `SSS_DURABLE_PLAN_BINDING` 只由显式入口传入。插件核对binding和MCP使用同一job；baseline清空继承变量。所有文件在项目.local，拒绝symlink和外部路径。
- 复用原 `FileJob.commit`，追加 `motif_activated` / `motif_disabled` 事件与状态 `motif_binding_sha256`。初次启用必须running且requests/steps/checks为0；不更改原权限、限额、任务、计划组件或原账本实现。冷启动只能继续同一激活绑定；停用后不能重新启用。原repair事件照旧把motif_disabled置true。
- `dsh_entry_motif.ts` 的 `createCollectionGate` 增加可选第五参数jobGuard；原四参数兼容。只对显式持久化计划启用；每次自动授权/执行前读取真实账本，检查状态、任务/权限、版本、原费用/请求/步骤限额、未决预留和repairs。控制器失败时持久化停用，实际工具失败不自动重试或恢复。
- 版本失效只使库停用；原任务和服务仍有效时交给普通Harness。原任务/权限或服务本身变化、撤权、暂停、取消、预算/步骤耗尽仍由原服务和代理拒绝。验收失败继续同job的普通Harness最多2轮修复，再验收；没有新授权、新预算或计数重置。

计划策略、图、training/validation references、摘要、G4 candidate-lock/library-lock不改写。`recovery_tools.py`、原FileJob/预算桥/验收守卫及13项服务依赖未改，因此外层仍c1b878a1…、组件仍ae4973ce…。4个新增组合执行模块另绑SHA。库真实性依赖可信本机原始证据和完整性摘要，不是签名或对恶意管理员的安全边界。

## 实验和回退

新增 `scenarios/file-management/workflow_online.py`：先冻结8个新开发条件及实际输入/工具顺序/源码/权限/预算，预检实际15工具；免费SDK/MCP用本地脚本Provider，真实任务复用公共SDK CLI。运行轨迹明确 `arm=M-plan-job`、`normal_harness_only=false`、不学习、不认证任意新图；角色限制为online_development。失败结果不可覆盖，最多一次已记录MCP边界冷启动沿用原job。原54个模板、oracle、pristine和留出不动。

撤权负例仅在私有实验目录生成固定测试插件，在实际authorize_plan成功回调后撤销同job、执行前检查停止。私有薄launcher只追加该测试patch并调用原run-scenario.main；没有公共撤权测试开关或模型工具。缺报告负例的冻结题面明确要求一次受控提前停止，不能算自然业务错误率或人工质量证据。实际进程退出75、partial_failure及原token恢复另行验证。

`scripts/audit-file-workflow-online.py` 独立复核原字节、原权限/限额、hash-chain状态、真实HTTP usage与峰值代理费用、自动调用身份、修复后无自动调用、零内容读取及留出保护。模拟HTTP/token的估价单列，云费用为0。保留开发初版、原测试断言失败和所有原日志。

初版9个真实条件完成后，收尾补强Schema/题面拒绝和验收修复消息分支的持久化停用；此前仅效果工具回调失败持久化停用。原9次输入/源码/绑定/结果不改，新模块SHA使旧绑定失效；新bcb96582副本重新冻结并作免费与真实4源件回归。原G4服务依赖/库不变，新增3条会话门拒绝后冷重建不能启用的回归；不把旧结果当成最终源码直接验证。

独立审计初版把budget_denied拒绝记录计入HTTP数量而拒绝；修订为逐项验证拒绝、只计算实际upstream usage，原审计失败日志保留。另原单测误把损坏binding的冷加载预期写成false，实际安全拒绝为throw；修订断言，未放宽守卫。两项均无新云费用。

## 使用边界

仅显式实验的FM38 rename/move及自身日志rollback组合；图在真实模型preview后只续接authorize/execute，最多6个受原grant约束的动作。此轮拓展到4源件的结果需以实验记录为准。自动restore、任意故障分支、其他效果/动态Web/多库组合/并发和任意断电/元数据恢复未认证。默认SDK/Web不启用新库；前端不能凭计划policy直接开启，必须提供完整原job和组合绑定，并显示实际后置验收状态。

结果、费用、失败和待验证内容见[本轮实验](../experiments/file-management-workflow-online-20261014.md)。
