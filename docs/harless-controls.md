# Harless 场景、模式与 RSI

登录 Harness Web，在 `/harless` 原生菜单选择 Scene、Mode、RSI，或在输入开头使用 `/ppt`、`/paper`、`/data`、`/chat`。每次输入字符都按前缀筛选场景；选择后在原生编辑器中显示蓝色场景标识，输入框底部保留当前场景。目录来自服务端，未部署项说明原因并拒绝选择，不保存假选择。选择本身不注册任务、不调用模型。原生聊天仍直接发送，任务 API 保留 preview / submit。

| Scene ID | 实际绑定 | 当前能力 |
| --- | --- | --- |
| `ppt` | `scenarios/research_ppt/web-scenario.json` | 现有 TS 交付 Adapter + Python PPTService，19 个 MCP 工具；独立 Session job、批准 PDF/PPTX 来源、读取/生成/修订/验收/交付 |
| `paper-proofreading` | 未绑定替代实现 | main 尚无论文正式后端；任务返回 `scene_not_connected` / `paper_backend_not_published_on_main` |
| `research-data-analysis` | 未绑定替代实现 | main 尚无数据分析后端；任务返回 `scene_not_connected` / `data_analysis_backend_not_implemented` |
| `new-scene` | `scenarios/general/scenario.json` | 普通 Harness Agent Loop，受限通用 `list_files/read_file`；只访问所属 Session 已上传文件，无样例资料、shell 或任意服务器路径 |

PPT 未构建或缺 Python 依赖时目录返回 `ppt_adapter_not_built` / `ppt_python_dependencies_missing`。安装复用 [PPT README](../scenarios/research_ppt/README.md)。空 Session 只读初始化，不能借空来源开启输出。三个正式场景目前均没有随 main 分发的生产认证 Library；已有 PPT 私有实验库不会自动装进 Web，也不会套用 portfolio 库。

| 所选 Mode | RSI | 当前任务实际策略 |
| --- | --- | --- |
| Origin (`baseline`) | On / Off | 普通 Harness，不创建 Motif interceptor |
| Shadow | On | 认证绑定适用时匹配/审计，LLM 继续执行；否则记录回退 |
| Execute | On | 启动缺 Library、完整认证 Schema 或匹配服务时拒绝；局部输入、参数来源、版本、执行/结果守卫不合格时回退并记录 |
| Shadow / Execute | Off | 保留选择，实际 `baseline`；再次 On 重新核验 Execute 准入 |

`selected_mode` 是选择，响应中的 `mode` 是实际模式；RSI 是独立布尔值。生产 Execute 必须有完整的认证工具 Schema 快照；文件更改或实际 schema（含描述、参数类型）不一致会拒绝。匹配服务在 Execute 任务准入时实际探测，不用固定向量冒充生产服务。只有实际工具结果通过共享 Runtime 的验证才增加 `verified_skips`。

## 服务端登记与配置冻结

`config/harless-scenes.json` 是生产目录；`config/harless-diagnostics.json` 独立保存历史 example/portfolio 诊断，不出现在默认产品菜单。后者 `diagnostic:true` 保留旧契约校验及旧模拟闭环，不能当作生产认证或真实收益证据。

登记表顶层是 `schema_version:1`、`scenes`。可运行项包含 `id/label/scenario`，可选 `case/instructions/adapter/rsi`；缺失项只包含 `id/label/unavailable_reason`，不能同时登记替代 Scenario。Adapter 仅支持已实现的 `ppt/workspace`。`rsi` 是 `{manifest, task, tool_schemas?}`，路径由服务器管理员维护。生产 Execute 的 `tool_schemas` 必须来自独立认证时记录的完整、有序 Harness schema；不能从当前任务临时生成来补认证。历史 Library 仅有有限契约时，使用 Shadow 回退或显式历史诊断目录。

场景沿用 `prepare_scenario` 严格 MCP 校验、`from_env` 引用和白名单；PPT/通用模板的 `${SESSION_WORKSPACE}` 仅由服务端替换。任务复用 `dsh_web_tasks.ts` 和同一个 `createOnlineInterceptor` / `online_skill_runtime.mjs`，没有另一套 Agent 或 RSI。MCP 工具真实执行仍归 Harness。

每项任务冻结 Scene/Scenario SHA/版本、所选和实际模式、RSI、指令及摘要、实际完整有序工具 Schema、权限、Library/Manifest/任务绑定摘要、Provider/模型/输出 cap、任务及启动预算、用户/Session/Task、上传文件与 job 摘要。确认后文件/库/Schema 更改拒绝；切菜单不修改任务。预算代理沿用原有累计结算和错误恢复。

## API 与上传

`GET/POST /api/harless/settings` 仍由 Harness Connection 认证，`selection:{scene,mode,rsi}` 仅接受登记 ID 和协议值。GET 返回 `available/unavailable_reason/execute_available/execute_unavailable_reason`，不返回 MCP 命令、凭证或服务器路径。旧 `select_preview_scene` / `clear_preview_scene` 作为真实选择的兼容别名，不保存独立预览状态。

GET 另返回 `conversation_only:boolean`：经管理员从其他旧运行目录迁入的历史会话为 `true`，允许保留上下文的文字续聊，继续使用逐轮预算，但不加载新版场景工具或修改已锁定的旧 preset。向此类会话提交附件返回 `409 new_session_required`；文件任务或新版工具需要新会话。普通会话及当前目录内正常重启的会话为 `false`。

GET 中的场景行含 `shortcut`，另返回 `scene_locked`。设置首次访问允许认领该 Home 下、使用已登记 preset 且没有历史/来源继承的普通空会话；未知历史继续返回 404。已绑定会话切换场景返回 `409 scene_requires_new_session`，在保存或改工具之前拒绝，不让界面假选择影响普通续聊。Mode/RSI 的修改只用于后续任务，不改变正在执行的配置。

`new_session` 可带可选 `selection:{scene,mode,rsi}` 和 `inherit_session`，验证归属后创建新会话并继承所属工作区。浏览器选择新场景时，如果原会话已锁定，会创建对应场景会话并转移未被改写的草稿及附件；原聊天保留，发生编辑竞争则保留原输入而不覆盖。界面使用原生 span/revision 守卫和 reference chip，不修改上游编辑器。迟到的设置请求不会覆盖刚保存的选择。

网关模式下，原生 `workspaceId` 由同一账号的 Harness 注册表验证，并只以该 ID 创建会话，不再同时传入 `cwd`。独立非网关模式仍拒绝客户端位置字段。未指定工作区时登记服务器分配的位置；场景 MCP 输入与 job 继续在服务器分配的 Session 私有目录中。有逐轮预算 broker 时，通用和 PPT 对话可在相同场景、相同已批准输入与权限下连续多轮。新增文件或改变 PPT `scene_options` 要求新 Session，不能借后续文字提高输出权限。

完整前导 `/ppt` 等别名在发送时由服务端核验并去除控制词，再用所属场景处理剩余文字；只有控制词时不调用模型。路径（如 `/ppt/file`）和普通文字不当作场景指令。已有会话直接输入另一个场景并发送仍会明确要求新会话；从候选中选择会完成上述新建和草稿交接。

任务 API 新增可选 `request.scene_options`，只接受 PPT `{slides:1..30, template:"academic"|"lab", allow_output:boolean}`；默认 6 页、academic、只读。输出开启须先有已批准 PDF/PPTX，通过预览后明确 submit。原生聊天当前未提供页数、模板和输出权限编辑界面；需要生成交付的用户先用任务 API 设置这些字段，不能通过自然语言默提高 job 权限。

附件继续通过官方 `fileUploads.resolve(agent, receipt)` 与 `attachments.readFileStream` 核验所属 Session，再复制到私有 inputs。最多 8 个文件、每文件 20 MiB；任务 API 简易上传入口沿用 256 KiB 限制。PPT 仅 PDF/PPTX；通用读取 UTF-8 文本最多 256 KiB，拒绝路径穿越、符号链接和版本变化。上传改变预览摘要，需要新确认。

## 用户隔离与验证

2026-10-14 main 已合入 PR #7 多用户网关。每个 Harness Connection 仍是单登录实例，网关为成员隔离启动、DSH Home和工作区，预算 broker 沿用主线。`--user-id` 是可信服务器启动参数，不是浏览器自报身份；认证负责人应为每个用户分配独立启动/DSH_HOME/预算实例并传入该 ID。两个独立用户进程已验证配置、cwd、Session、任务、收据和轨迹隔离；本次没有修改认证/账户模块，也未宣称单进程多账号已实现。本轮合并保留其会话恢复与连续对话测试。成员现有零工具沙箱策略派生为 New Scene 普通对话；PPT等场景返回 `scene_not_deployed_in_member_sandbox`，不会继承所有者 MCP/库/输入。网关账号、密码和认证模块未改动；扩大沙箱挂载仍需负责人另行部署验收。

```sh
npm test
npm run smoke
npm run web:controls:check
npm run web:scenes:check
npm run web:tasks:check
npm run web:check
# V100 隔离目录；先加载项目环境。按持续测试授权，真实费用封顶0.06美元：
npm run web:scenes:check -- --real-model
```

真实结果与负例见 [场景集成验收](experiments/harless-scenes-runtime-20261013-v1.md)。科研质量、PPT生成交付和浏览器点击未在本轮验收；真实 Execute 降本也未验证。
