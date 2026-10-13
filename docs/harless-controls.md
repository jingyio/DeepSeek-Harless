# Harless 场景、模式与 RSI

## 使用

登录本次 Harness Web，使用聊天输入框旁的 Harless 菜单选择场景、RSI 和运行模式。独立 `/harless` 页面已移除；裸 `/harless` 命令会提示使用菜单，快捷设置、`list` 和 `status` 命令仍可用。

| 模式 | RSI | 行为 |
| --- | --- | --- |
| Baseline | Off | 普通 Harness，保留工具权限和预算 |
| Shadow | On | 记录结构候选，原模型继续执行 |
| Execute | On | 认证、输入、来源版本和工具守卫通过后才接管 |

Off 记住最后一次 Shadow/Execute；On 恢复该模式。首次恢复 Shadow。切到不支持 Execute 的场景时，界面先选择 Shadow；直接 API/命令请求非法 Execute 会拒绝，不隐藏失败。Execute 即使场景层可选，当前输入或来源不合格仍会回退并记录原因。真实模式没有配置匹配服务时不会用模拟 embedding 冒充。

菜单和设置 API 不启动 Agent turn、不注册付费任务、不调用模型。预览后任务的模式、工具快照、场景配置、指令和认证库文件摘要冻结；菜单选择用于之后创建的会话。新任务使用新的 Session，重新绑定输入、来源和预算；全局预算继续累计。

## 登记场景

`config/harless-scenes.json` 的顶层为 `schema_version: 1` 和 `scenes`。每项必需 `id`、`label`、`scenario`（仓库根目录相对路径）；可选 `case`、`instructions`（场景通用指令文件）、`rsi: {manifest, task}`（认证 library 和其任务/版本绑定）。不接受匹配器或未实现的运行时配置字段。浏览器不能提交路径、MCP 命令或库覆盖。

复用已有 `scenario.json` 的严格 MCP 校验和环境引用。启动器为每个场景生成私有独立 preset；默认场景使用 `sss-task`，其他使用 `sss-scene-<id>`。场景通用指令单独注册为 PromptSection，不把 `prompt.md` 的固定任务题面注入每项新任务。`prompt.md` 仍用于既有冻结样例的输入认证；当前库不能泛化到任意新任务。

`--scene-registry` 指定服务器维护的登记表，`--scenario` 选择初始场景。`--manifest/--task` 仅覆盖初始场景的认证绑定；其余从登记表读取。真实 embedding 通过已有本地 loopback 服务配置，未配置时 Shadow 普通回退、Execute 禁用。离线 Python 挖掘、编译和发布入口保持；本次没有增加自动学习器或重复 Agent 循环。

## 认证控制 API

所有路径使用 Harness Connection 的同源、Host 和登录认证。

- `GET /api/harless/settings[?session_id=...]`：选择、适用时点、当前任务、可用场景及 Execute 原因；不返回凭证、资料正文或服务器路径。
- `POST` 同路径：`{action:"select", session_id?, selection:{scene?, mode?, rsi?}}`。`rsi` 为布尔值，冲突字段拒绝。省略 Session 表示新会话默认。
- `{action:"new_session", inherit_session?}`：独立新 Session，不启动任务或模型。
- 任务预览保留 `/api/harless/tasks`，新增可选顶层 `session_id`，只接受本启动拥有且未绑定任务的 Session。任务 `capability_profile` 即登记场景 ID。

原生 `agentPresets.select` 也经同一选择验证；已经绑定任务的 Session 不能从原生 preset API 改当前组合。空会话使用 Harness 公开 `agentPresets.select`，工具限制的 disposer 随切换更新；新任务随后保存实际 schema 快照。上游核心未修改。

## 复现

```sh
npm test
npm run smoke
npm run web:controls:check
# V100，先 source .local/remote-env.sh；测试目的真实 API 持续授权内
npm run web:controls:check -- --real-model
```

控制协议验收累计 0.06 美元、单任务 0.03 美元，真实验收24/32请求（免费三场景协议诊断为24/64）、输出1000。产品默认额度仍由启动配置决定；原生聊天发送后直接执行，任务 API 保留显式预览和提交。一次启动不可通过切场景或新建会话重置预算。

单元和免费协议仅验证工程接缝。真实 API 验收见 `docs/experiments/harless-controls-20261013-v1.md`，不把 Shadow 候选说成实际节省。当前只在本机 macOS / V100 Linux 验证；没有多人账号隔离和跨启动状态恢复。
