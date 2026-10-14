# 文献任务与官方 Web 的 Session 绑定

2026-10-12。用户授权接入并验证两项不同问题。修改前登记的共享接口如下；验收结果在完成后补录。

- `scripts/harness-web.py`：新增服务端 `literature-pdf` 场景别名及 `--papers-dir` 登记目录；仅此场景加载固定的文献绑定模块，不能从请求指定模块、目录、环境变量或命令。通用 example/portfolio 与 SDK 保留。
- `src/adapters/dsh_web_tasks.ts`：可选服务端 `task_binding`，在 Session 创建前生成任务独有的 preset，冻结问题与资料，提交前检查来源；停止后回收并核对场景交付，而非以 Agent idle 判断文献任务成功。预算仍由原代理和 TaskBudgetRegistry 管理；同一启动进程只执行一个任务。
- 绑定模块位于场景目录，以现有 Python PDF/修复实现做来源与产物重放；在线任务调度用 TypeScript，复用公开 Controller/preset/MCP/停止钩子，不修改上游 Harness，不新增模型循环。
- 任务详情可返回场景的 Markdown/质量/缺口/收据摘要；临时 `/tasks` 展示这些交付。文献场景拒绝通用图片/receipt 附件，PDF 来自服务端登记目录；原生聊天尚不承担问题绑定，请从任务工作台提交。
- 场景工具复用 PdfScene 和 RepairScene，在同一个 Session 先阅读、后逐论断自动复核、有界补缺并交付。无人工科研审阅要求；自动检查不认证科学正确性，缺口可以交付但必须显示。

接口只是任务隔离与现有确定性流程，不是学习所得 Motif；没有可用认证库时显式普通流程回退。保留旧 8765 工作台和 SDK，不删除历史产物/费用/论文。最终自研前端通过同源任务 API 接入。

## 已实现与验收

- 场景新增web-scenario.json/web-task.md、web-binding.ts/web-binding.py、web_pdf_tools.py、run-web.py、check-web-pdf.py/web-fixture.py。共享只扩展已有Web适配器/启动器/面板及npm入口；不改变预算计价、上游或Motif核心。动态preset用公开发现/挂载，每个任务独有MCP状态，不能从原生聊天绕过绑定。
- `task_binding`为服务端配置 `{module,config}`；本启动器仅literature-pdf映射到固定场景模块。prepare(request,output)返回preset_id/content/sources/papers/allowed_tools/binding_digest；逐工具集合相同才允许创建。check在submit前核PDF与task摘要，collect在idle后核真正成功的native工具收据、来源、引文、完整自动复核与最后综合。原回答保留answer.md，场景权威交付另存research-notes.md。
- HTTP请求协议不新增客户端路径、模块、插件或shell字段；inputs空数组使用登记全部PDF，可指定pdf:library及其期望版本。文献仅单文本研究问题、1–20篇，通用图像/receipt上传拒绝；其他profile附件契约不变。
- native create仍只公开sss-task，新文献独立preset只能由服务端内部调用原Controller创建。已绑定Session禁止第二任务/steer/queue改写/fork；原生聊天返回scene_requires_workbench。每任务/全启动预算与单槽继续原实现，阶段/引用失败计入原工具事件与真实费用。
- 后端阶段reading→review(全字段)→review(仅缺口，最多2轮)→synthesis→delivered。引用历史先重放、按claim授权；旧拒绝提案只导航，不能变支持结论。原阅读工具仅reading开放，其他阶段走claim读取额度。收据守卫最多2次同Session续接，消息来源task-completion-guard，Web统计completion_continuations，真实本轮0；不计Motif skip。
- 包装器转发SIGTERM/SIGINT并等待真实Web启动器退出；仅停止本次自己创建的进程，不按端口盲杀其他服务。
- 378 Python+66 Node回归通过，最终两问题免费协议以及两问题真实API验证见[验收记录](../experiments/literature-web-binding-20261012.md)。真实最终43请求/0.176891508美元/每题15字段0程序缺口；首版缺口、54条最终pending拒绝诊断、一次阶段错误及启动失败均保留。0程序缺口不认证科学支持。

## 兼容、风险与回退

`npm run scenario`、原8765工作台与旧场景保留；新增 `npm run web:literature`，真实模型加--real-model并复用原私有Key。不混用旧认证library、不自动开启Motif，无思考模式比较。旧工作台的缓存/增量更新尚未迁入此Web配置；资料通过服务端目录登记，暂无浏览器大PDF上传、任意论文子集选择或跨启动HTTP历史加载。

每任务新preset的站立挂载/MCP生命周期由Harness持有至启动进程结束；本轮只验证少量连续任务，不承诺长期无限任务的内存占用。原始记录持续保留，启动总预算/请求上限不随任务重置。场景源文件与解析器变化要求重核版本/认证。

回退Web profile到example或portfolio-v1即可保留通用Web，文献仍可走旧agent.ts；删除可选task_binding桥接前先停其启动器。不要删除.local历史/Key/testpdf。当前feature/rsi-research-agent保留所有既有未提交工作，main仍bc1ecd5，与origin/main一致；本轮未merge/commit/push/PR。
