# DeepSeek Harless 主线当前交接

## 2026-10-14：斜杠场景与成员边界（当前）

- 更新时间与交接人：2026-10-14，Codex；用户授权修复、真实受限测试、部署与提交 PR，继续不代替用户合并。
- 范围/版本：PR #11 的历史续聊与原生场景引用 `0fb57ad` 已合入 main `2ad349a`。新增分支 `codex/member-workspace-hardening`，实现 `a47f76e`/`0b5955c`；后续仅文档，具体 PR 状态以 GitHub 为准。
- 已完成：`harless_web_client/client.js` 原生前缀候选/蓝色引用与草稿保护；`dsh_web_tasks.ts` 工作区 ID 创建、冷会话恢复、场景锁定与同场景续聊；`dsh_member_workspace.ts`/`harless_member_file_scope.ts` 公开文件 Fetch/Lookup 边界；账号网关成员 profile 轮询、关闭浏览器连接和启动中后端。
- 已验证：最终 Linux 165 Python / 93 Node、smoke、motif:check 全通过。三组双账号各三轮真实对话，重启与隔离通过；PPT 浏览器两轮、截图对应的早期会话两轮；真实成员同名文件独立、6 类 API 越界拒绝、工作区与字节重启恢复。见 [本轮记录](../experiments/slash-member-recovery-20261014-v1.md)。
- 部署/数据：正式检出 `0b5955c`，owner 33102 / gateway 33101 保持；3080 原模型预算服务未重启。保留所有正式账号、Home、工作区、output 和迁移核验备份。原论文工作区没有覆盖；测试账户和凭证只在私有 `.local/`，结束清理测试后端，不清空历史日志。
- 权限/预算：有效 deepseek-flash、Origin、off、输出 1000；本轮 22 请求估费 0.004509264 美元。观测累计 46 请求/0.008586282 美元，上限 0.23 美元/250 请求保持，账单未核对；公共说明 `docs/harless-account-gateway.md` 与 `docs/interfaces.md` 已同步。
- 限制/下一步：未做大规模容量压测或 PPT 成品质量验收；Paper/Data 仍由部署可用性拒绝。迁入的锁定历史为文字兼容，新工具需新会话。审阅新 PR 后由用户合并；后续升级保持同 Home/output，并验证新增工具的账号文件边界。
- 回退：保留私有启动规格、policy 与访问 URL 文件；可回退 `2ad349a`，但会恢复较宽成员文件预览和旧连接退出行为。回退不删除用户文件、归属/任务索引，不重置预算，不改写私人原件。

## 2026-10-14：跨部署续聊恢复（历史，PR #11 已合并）

- 范围与版本：分支 `codex/persistent-chat-recovery` 基于 main `6ade286`；实现提交 `373eadd`（含 `5e1ecbe`），后续为文档。修复历史可见但升级后发送被拒绝，以及旧锁定 preset 无新版工具导致的二次失败。
- 接口：归属持久化至账号 `DSH_HOME`，按 Home/principal 隔离；私有 `ownership_legacy_outputs` 只导入同 Home 的明确旧目录，成员清空此配置。外部旧目录迁入的会话为文字续聊，`conversation_only:true`；附件及新版工具需新会话。正常重启不移除当前会话工具。
- 验证：Linux 全量 165 Python / 78 Node 通过；两临时账号并发各三轮真实模型对话，第三轮在网关与成员后端重启后完成，跨账号访问拒绝；实际报错旧会话两轮续聊通过；公网登录表单正常。详见 [实验记录](../experiments/chat-session-recovery-20261014-v1.md)。
- 部署与数据：正式隔离检出运行 `373eadd`；端口保持 owner 33102 / gateway 33101，原 3080 模型预算进程继续运行。保存旧启动配置与迁移前 policy；DSH Home、workspace、output 和三个生产账号保留，临时验收账号清理。原论文根工作区未重置，私有配置与日志未提交。
- 预算：有效 `deepseek-flash`、baseline、reasoning off、输出 cap 1000；本次新增 14 请求，代理估费 0.001674612 美元；当前运行累计 17 请求 / 0.002159760 美元，上限 0.23 美元 / 250 请求未重置，账单未核对。
- 后续与限制：PR 仅提交审阅，不合并。两个并发账号验证不代表容量压测；旧迁移会话为文字模式，新工具要新会话。临时 Cloudflare 隧道不在本修复范围。今后升级保留账号 Home、工作区及任务 output，回退不删除归属/任务数据、不重置预算。

## 2026-10-14：多场景前后端桥接

- 更新时间与交接人：2026-10-14，Codex。
- 目标与范围：原生 `/harless` 实际选择 Scene/Mode/RSI，统一已有 Runtime；未开发缺失的论文/数据业务后端。
- 分支/版本：`codex/scene-rsi-bridge` 最初基于 main `62ee46b`，已整合最新 `2a96552`（PR #7），已推送；[PR #8](https://github.com/jingyio/DeepSeek-Harless/pull/8) 已创建，未合并；最终提交以本分支历史为准。原论文/用户隔离工作区保持。
- 已完成：`harless_scenarios.py`登记；`harless_settings.ts/dsh_web_tasks.ts`真实选择及任务冻结；`harless_task_scope.ts`独立cwd/preset/上传/job；PPT现有19工具及通用文件MCP；生产Execute完整Schema/匹配服务准入，历史诊断分列。无新Agent循环或上游改动。
- 已验证：V100合并前154 Python/60 Node；合并后165 Python/75 Node通过；PPT53 Node；18题/83来源smoke；控制与新场景/动态协议。合并前后各两项合成来源真实模型任务，累计14请求/10MCP/0工具错误/0实际跳过，见`docs/experiments/harless-scenes-runtime-20261013-v1.md`。生产有库Execute、科研质量和浏览器操作未验收。
- 配置与数据：生产`config/harless-scenes.json`；诊断`config/harless-diagnostics.json`。私有轨迹/配置/失败保留隔离验收目录，真实runs `907266faee4d40d799eca6ae2fa2109d` / `47ac1c37b74b494391bff14b56ce6b13` 已同步本地`.local/integration/scene-rsi-results/`；密钥仅由既有环境提供，未提交。
- 未完成与接口依赖：论文/数据正式Scenario尚缺，明确拒绝；PPT生产Library缺，Execute拒绝。已保留PR #7的成员预算broker、Session持久化和连续对话；零工具成员不继承所有者MCP，PPT在成员沙箱尚未部署，明确拒绝。本次没有改变账号、密码或认证模块。PPT页数/模板/输出权限暂用任务API，默认只读。
- 接手下一步：1. 审阅并合并桥接PR，安装PPT依赖后`npm run web:scenes:check`。2. 用户负责人联合验收gateway隔离；场景负责人登记正式论文/数据MCP与Prompt。3. 用独立任务认证完整Schema/库/来源绑定后，按授权做真实Execute对照。
- 权限与预算：本次真实联调累计封顶0.06美元/24请求，已用代理估费0.00647472美元/14请求，账单未知，已停止。没有借论文uncapped权限扩大Web预算，无外部写/投稿。
- 回退与风险：按本分支提交回退；旧诊断明确使用`config/harless-diagnostics.json`。不覆盖共享服务器、不修改协作者工作区、不清理`.local`；单登录实例不能当作单进程多账号。


## 2026-10-13 多用户账号网关与连续对话（[PR #7](https://github.com/jingyio/DeepSeek-Harless/pull/7) 待审）

- 范围与代码：分支 `codex/multiuser-web-gateway` 基于 `main` 的 `62ee46b`；账号网关、邀请码、账户设置、成员独立 DSH Home/工作区、账号预算路由及同一会话逐轮任务在 `scripts/harless_gateway.mjs`、`scripts/web_budget_broker.mjs`、`src/adapters/dsh_web_tasks.ts`。保留主线原生 Harless 场景/模型选择；未纳入服务器论文实验或私有配置。
- 已验证：服务器独立 Linux worktree 中 `npm test` 为 164 Python、67 Node 全部通过。免费模拟 Web 带 `--public-origin` 启动，认证 303、首页和任务/设置 API 均 200。另用两个临时测试账号同时启动隔离 DSH 后端，双方就绪与首页均 200、进程端口不同；没有真实模型调用。旧检出的 host patch 在新检出上被拒绝，改用同一检出的 patch 后通过。Windows 本机全量测试另有符号链接权限和纯代码节点环境限制，Linux 全量通过。
- 配置与部署：公共说明见 `docs/harless-account-gateway.md`，账号、邀请码、模型密钥、运行日志和私有论文继续只在 `.local/`。本 PR 未切换正在运行的公网服务；生产切换前需要以最新主线重建私有 host patch，确认 `bubblewrap` 挂载、两个测试账号实际并发和 HTTPS 隧道稳定性。服务器原论文工作区的未提交改动没有改写。
- 后续：审阅 PR 后在隔离部署上完成双账号浏览器与真实模型预算验收，再安排生产切换。PR 暂不合并；回退为停止可选账号网关并继续使用现有单用户 Web 入口。

## 2026-10-13 原生二级菜单与输入框状态（已推送，PR 待创建）

- 范围：`/harless` 原生选择器改为 Scenes、Mode、RSI 二级菜单；Scenes 新增 New Scene，使用当前服务器运行时探索。PPT、Paper Proofreading、Research Data Analysis 仍只预览且阻止误用样例工具。Mode 显示 Origin/Shadow/Execute，协议 Origin 仍为 `baseline`；RSI 默认 On，切换模式不自动改变开关，Off 的下一任务按 Origin 执行。输入框加入加粗 Harless 状态标签。
- 分支与文件：`codex/harless-picker-ui`，从 `b330bb4` 起包含原生菜单、输入框状态、模型选择与 GLM 配置；已合入最新 `origin/main`（`856c02c`），提交 `fd06213`，当前完整 HEAD 为 merge commit。对应代码、文档和回归测试已提交并推送到同名远程分支。
- 已验证：合并后 `SSS_PYTHON=/Users/apple/Desktop/SSS/.venv312/bin/python npm test` 通过 153 项 Python、56 项 Node；纯离线与模拟控制服务，模型费用为零。3094 的本机预览运行 ID 为 `9b844f86fc6f4481bb36992dad328720`，认证地址留在 `.local/web/runs/<RUN_ID>/access-url.txt`。用户确认本功能完成；真实模型任务与场景运行时仍未接入。
- 下一步：创建面向 `main` 的 PR。三个正式场景的 MCP、权限与交付仍待接入，New Scene 当前复用服务器已配置运行时。此变更不扩大付费或外部写入授权；不要提交 `.local` 或认证地址。

## 2026-10-13 原生 Harless 选择菜单（当前）

- 目标与本次范围：用户要求像 Harness 原生模型选择框一样操作，界面用英文，只显示 PPT、Paper Proofreading、Research Data Analysis，不展示样例场景。按用户确认，这三项本次仅做可选界面，运行时接入后续完成。
- 分支与改动：`codex/harless-picker-ui`；新增 `src/adapters/harless_web_client/` 双端包，使用 Harness `commandUi.decorate({kind:'popupSelect'})` 装饰裸 `/harless`；移除注入 DOM 的旧悬浮菜单及输入框观察器。后台新增 `select_preview_scene` / `clear_preview_scene`，选中尚未接通的场景后以 `scene_not_connected` 阻止任务，避免误用样例工具。
- 已验证：本机 `npm test` 151 Python、52 Node 全部通过；本机免费模拟 Web 启动成功，认证 HTML 含原生客户端插件登记且不含旧菜单注入。未操作用户浏览器，真实点击与视觉效果由用户验证；未调用模型，费用为零。
- 配置与数据：真实运行时场景仍登记在 `config/harless-scenes.json`，三个界面预览标签在 Web 适配器中；私有启动产物留在 `.local/`。V100 3094 专用预览已部署 `c147400`，服务监听 `127.0.0.1:3094`；正式 3080 与原论文工作区不变。
- 未完成与下一步：用户测试 3094 的原生菜单与英文选项；之后分别接入三个场景的 MCP、权限、输入与交付。未接通前选择这三项会拒绝任务。多人账号与文件隔离、跨启动选择恢复仍未实现。
- 回退与风险：回退本分支的原生客户端包和服务器预览选择接口；不清理 `.local`。若原生菜单未加载，保留 `/harless` 参数命令作诊断入口。

## 2026-10-13 输入框菜单与页面清理（历史）

- 最新修复：用户反馈选中 `/harless` 后页面卡住。`52d245f` 曾直接编辑原生输入框，可能与 Harness 输入框更新互相触发；本次移除此编辑，仅观察命令状态并打开设置菜单，同一段输入最多触发一次。新增重复变更回归测试；Node 语法、新测试及 11 项 Web 定向测试通过。浏览器交互按用户要求由用户测试，当前仍未验证；`/harless` 文本可能留在输入框，需根据反馈继续完善。
- 当前预览：V100 专用 3094 实例将更新到本次修复提交；正式 3080 与原论文工作区不变。本次无模型调用及费用。

- 目标与范围：保留聊天输入框旁的 Harless 场景/RSI/模式选择；移除独立 `/tasks`、`/sss`、`/harless` 页面、悬浮入口及真实模式预算确认弹窗。原生聊天发送后直接执行，服务端预算约束保留。
- 分支 / commit / 工作区：`codex/harless-picker-ui`，基于合并后的 main `b330bb4`；选择菜单 `e45338f`、页面清理 `359d0bf`、直接发送 `cb7efb2`，尚未推送。原论文工作区未改动。
- 已完成：移除两个旧 HTML 面板和命令打开旧面板的轮询；旧页面地址返回 302 跳转聊天首页。裸 `/harless` 提示使用输入框旁菜单，具体场景/模式快捷命令保留。删除真实模式预算弹窗，原生消息发送时由服务端登记、激活预算并提交；显式任务 API 的预览/提交和全部兼容路由保留。
- 已验证：Node JS/TS 语法、Python 编译、diff 检查通过；本次在本机以现有 `.venv312` 运行 `npm test`，151 项 Python 与 50 项 Node 通过。真实模式原生发送的夹具检查了直接派发、预算只激活一次、重复请求不重跑，以及页面不再注入弹窗；这是模拟控制服务，不是付费或浏览器验收。本次零模型调用。
- 实验结论：此前 `harless-controls-20261013-v1` 真实运行记录未更改；本次仅前端入口与文档调整，不新增真实 API 测试或费用。
- 配置与数据：场景登记仍在 `config/harless-scenes.json`；V100 独立副本 `.local/validation/harless-picker-cb7efb2/` 已检出本提交并通过 11 项 Web 任务 Node 定向检查。专用 tmux `harless-controls-preview` / 3094 仍运行此前版本，尚未切换；不触碰正式 3080 或私有运行数据。
- 未完成与下一步：V100 主目录为他人正在修改的论文工作区，3094 原预览副本也有未提交改动；独立副本已就绪，3094 切换暂停，不能覆盖两处工作。浏览器确认直接发送、菜单和旧页面跳转仍待完成。多人账号与文件隔离、跨启动设置恢复仍未实现。
- 权限与预算：本次删除与 UI 检查不调用模型，预计真实 API 费用为零；真实调用继续遵循项目既有授权与预算。
- 回退与风险：本次是可逆 UI 路由/面板删除；不清理 `.local`。跨用户隔离尚未实现。

## 2026-10-09 至 10-10 历史交接（当时状态）

- 2026-10-10 本机连接修复：3086 手工隧道再次消失，改为专用受限 SSH 账号与用户 LaunchAgent 自动重连，并追加本地地址代理绕过。主动断开测试约 2 秒恢复，现有认证/任务页/API 均 HTTP 200；原服务器运行、预算和 3 请求/4 MCP 统计保留，本次零模型调用。浏览器刷新待用户确认；运维配置、回退及限制见 `docs/handoffs/harness-web.md`。此记录随 PR #2 更新，原论文工作区其他修改保留；尚未合入 main。

- 2026-10-09 官方真实聊天修复：见 `docs/experiments/native-chat-confirm-20261009-v1.md`。原 `session/prompt` 直接报错已改为待确认任务与原生预算弹窗；确认前/重试/取消均 0 模型调用，确认后真实 3 请求/4 MCP/来源核验通过。当前 3086 运行 `ebd724e8f4464b72b5cbc797210da350`，每任务/启动上限 0.247 美元，承接旧支出后累计估费约 0.003950 美元、账单未核对。146 Python、45 Node、13 组协议诊断通过；真实浏览器点击仍待负责人确认。原论文分支不切换，公共修复随 PR #2 发布。

- 2026-10-09 真实 Web 恢复与 API 验收：见 `docs/experiments/web-real-recovery-20261009-v1.md`。3086 运行 `9ea9d68a37a44627ad3ab1d545678c37` 已后台恢复，baseline/execute 两项真实任务各 3 请求/4 MCP/0 错误，来源核验通过、独立 Session，execute 无库回退；合计代理估费约 0.002485 美元（总上限 0.25，账单待核对）。旧运行零调用，记录保留。真实浏览器点击仍待负责人确认；认证 URL 换行修复避免复制进终端提示符。

- **更新时间与交接人**：2026-10-09，Codex 根据项目负责人的要求整理；后续主线负责人由课题组确定。
- **目标与本次范围**：提供四人共用的 Motif / DeepSeek Harness / 自定义 MCP 底座；用户兼任项目负责人及论文生成/投稿场景负责人。当前补齐前后端动态任务、三模式与独立统计，产品统一名为 DeepSeek Harless，保留已分发历史库和 SDK 入口；不替代论文场景开发。
- **当前分支与版本**：公共改动位于 `feature/web-task-api`，基于已合入冻结 Web 的 `origin/main`（`bdf934f`）；在线代码提交 `8168f83` 已推送，[PR #2](https://github.com/jingyio/DeepSeek-Harless/pull/2) 已创建，按负责人授权转为待审，尚未合入 main。后续交接提交以该分支 Git 历史为准。原本地与服务器的 `feature/paper-submission` 工作目录和未提交论文材料保留；实验发生时的旧 commit/dirty 配置仍以各实验快照为准。
- **公共 Web 当前新增状态**：默认 `npm run web` 动态入口，`--frozen` 兼容旧固定题面回归；产品页面 `/tasks`、API `/api/harless/tasks`，旧地址兼容。后端接收文字、JSON instruction/content/user messages、图片、官方文件 receipt 和服务器 resource_id；三模式逐任务固定，无有效认证库或输入不适配时回到普通 Harness。一个启动连续多任务，一任务一 Session、单活跃，记录独立。免费一键代码完成，真实模式仍预算预览与确认；goal/队列编辑不能绕过任务绑定。详见 `docs/handoffs/harness-web.md` 与 `docs/interfaces.md`。
- **公共 Web 最新验证与边界**：服务器 Node 22.23.3 / Python 3.10.8 通过 146 Python、44 Node、冻结 11 组、动态 HTTP/MCP 13 组、smoke 18 题/83 来源及 Motif 闭环，这些诊断无真实 API 费用。正式动态 3080 运行 `f91a53c78a524bbaa3fb935fd68c8b4f` 保持运行，浏览器认证进入 `/tasks`，产品标题/免费一键/三模式可见；同一运行无重启提交两项不同题面 `2057d2c5580d466d8efea9c385ad491a`、`ae83a4b3ad104fc7a4d0bf5760198de5`，各 completed/5 模拟请求/4 真实只读 MCP/实付 0、独立 Session、无额度表单或再次确认，刷新保留。私有截图 `.local/web-review/browser-live-multi-tasks.jpg`。同版本 3084 另已验证文字 baseline、JSON messages execute 缺库普通回退及另一聊天任务，截图 `.local/web-review/browser-free-one-click.jpg`；诊断 3084 与旧冻结 3080 均精确停止、资料保留。记录 `docs/experiments/dynamic-web-tasks-20261009-v1.md`；真实 Web、科研质量、费用收益、Windows Web 和多用户隔离未验证，预算/纯代码仍 Python。
- **后续测试执行与权限**：用户现已持续授权测试目的真实 DeepSeek API；涉及模型行为的端到端、场景和效果/成本验收默认使用服务器 `npm run web:real` / `npm run scenario:real`，不再用固定回复替代。单元、错误注入和无模型 smoke 仍为确定性诊断。运行前说明有效预算，先沿用既有 0.25 美元任务/整启动限额及实际请求上限做最小测试；超额、外部写操作和投稿另确认，不通过重启循环绕过限额。私有密钥不展示。正式 3080 仍是 mock，真实 SDK 结果不能当作真实 Web 验收。
- **真实 SDK/API/MCP 已验证**：`web:real` / `scenario:real` 显式入口已完成；服务器原变量为 `DEEPSEEK_APIKEY`，已在项目根私有 `.env` 补规范 `DEEPSEEK_API_KEY` 并设权限 `600`，未展示值。`scenario:real` 的 example/baseline、`reasoning_effort="off"`、0.25 美元上限、单请求输出 1000 token、8 步运行退出 0，耗时 9.729 秒；运行 `7929653e0d9d4828bf46e4ff49394abd`，Session `sss-105f45630d444789bccf467f3718006a`。3 次真实上游请求均 HTTP 200，4 次真实 MCP（2 pin/2 read）、0 工具错误；两个来源的 ID、SHA、读取正文和回答引用逐项一致。prompt 2712 token（缓存命中 1536/未命中 1176）、output 1043、total 3755，代理估费约 0.001614 美元，账单实付未核对。记录见 `docs/experiments/deepseek-real-api-smoke-20261009-v1.md`；原目录 `.local/runs/7929653e0d9d4828bf46e4ff49394abd/`，原始轨迹、答案与 `verification.json` 已同步两端 `.local/experiments/deepseek-real-api-smoke-20261009-v1/`。支持基本连通，任务仍用合成来源，质量未盲评，无收益结论；既有 3080 未重启。
- **当前接手优先级**：1. 项目负责人审阅公共改动，按可验收范围提交/PR，不混入私人材料和他人工作，再让同学同步。2. 各场景在服务器用真实 API 联调入口接自己的 MCP、真实输入；论文场景在独立 PR 推进，其交接不纳入本公共 PR。3. 固定质量标准、任务与配置，在已授权预算内执行最小真实验收并记录用量/人工修订；预算扩展另确认。不要再把模拟结果作为新增模型行为验收。

## 已有基础与历史验证

以下保留主线整理、分发、平台与服务器安装的历史依据；其中旧分支、测试数量、未实现前端等描述按发生时记录，当前状态以上述新增状态及 Web/论文交接为准。

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
- **历史阶段权限与预算**：此前授权涵盖本地备份、主线整理、样例库开发及最新 main 提交和推送，整理与模拟验收无新增付费支出，当时没有新增真实实验授权。当前测试目的真实 API 持续授权以顶部新约定为准；发送邮件、外部写操作、实际投稿及超额支出仍需另确认。
- **Windows CI 修复（2026-10-09）**：用户提供首次 Windows CI 的 8 个失败，已定位为 LF/CRLF 原始字节哈希、cp1252 解码中文和不适用的 Unix 模式位断言；前两份哈希差已由换行转换精确复现。新增 `.gitattributes`、入口 UTF-8 配置、显式文本读写及平台限定的模式位检查；保留冻结哈希与所有非模式位安全验收。本机仍通过 136 项 Python、29 项 Node。推送后以对应平台 CI 为准；细节见 `docs/experiments/windows-ci-compatibility.md`。未调用付费模型。
- **回退与风险**：文档可按对应提交单独回退；完整历史可从两个归档分支查阅。不要直接把全部 archive 合回 main，也不要删除 `.local/`。通用入口的 `--call-model` 会启用付费调用；有副作用的 MCP 还需服务端权限、预览和确认。

- **Windows CI 验证结果**：修复提交 `c05127f` 的 [运行 37888988141](https://github.com/jingyio/DeepSeek-Harless/actions/runs/37888988141) 中，Ubuntu 与 Windows 均完成并通过 `npm ci`、环境安装、`npm test`、`npm run smoke`、`npm run motif:check`。本地 `core.autocrlf=true` 干净检出额外验证了 79 个冻结文件的原始哈希。当前已验证离线及模拟闭环，不能扩大为所有真实应用/MCP 或付费云实验的支持结论。
- **远程开发源码同步（2026-10-09）**：按用户授权，将 `main` 的 `2368235f274329be6227a8393b850633cb943da4` 及完整主线 Git 历史恢复到指定服务器 `/root/autodl-tmp/jjy`，`origin` 指向原 GitHub 仓库；本条交接更新尚未提交，也随源码同步。未传输本机 `.local/`、密钥、虚拟环境、`node_modules` 或缓存；归档分支未单独迁移。远端为 Linux x86_64，现有 Conda Python 为 3.10.8，未找到 Node.js；开发依赖尚未安装，未运行远端测试或付费任务。接手先准备 Node.js 20+ 与 Python 3.12，再按 `README.md` 执行 `npm ci`、`npm run setup` 和免费检查。此次只授权源码同步，没有新增模型支出；SSH 凭证不写入仓库。
- **后续执行约定（2026-10-09，用户明确）**：用户负责论文生成与投稿场景，本地操作与审阅，后续 Agent 计算在服务器执行；运行前同步代码和输入，运行后同步交付与必要结果。已简短写入 `AGENTS.md`；本次仅更新文档，不安装环境或运行实验，文档改动未提交、未推送。
- **环境要求修正（2026-10-09）**：Python 3.12 是已有 CI/本机验收版本，不能据此推断 3.10 不兼容。`src/`、`scripts/`、`tests/` 通过 3.10 语法解析；已安装固定直接依赖的元数据允许 3.10。远端 Ubuntu 22.04、x86_64、内核 5.4、glibc 2.35 满足 Node.js 22 官方 Linux 二进制平台条件；尚未安装 Node 或完成 Python 3.10 依赖安装及运行回归；远端依赖 dry-run 解析未完成后已停止，不构成不兼容证据。已修正 `README.md`，下一步优先核验现有 Python 3.10 与 Node 22 的免费闭环。最终展示采用本地浏览器访问服务器任务接口；该前端/API 尚未实现。本次没有付费调用。
- **服务器免费闭环已完成（2026-10-09）**：更新上一条待验证状态。用户授权后在服务器安装项目隔离的 Node 22.23.3 / npm 10.9.9，沿用 Conda Python 3.10.8 创建 `.venv-sss`；依赖一致性检查、136 项 Python 与 29 项 Node 测试、18 题 / 83 对象 MCP smoke、4 个 Motif 重编译与 Harness baseline/shadow/execute/旧版本回退均通过，场景入口保持预览。没有为适配 3.10 修改源码；付费 API 请求为 0。记录见 `docs/experiments/server-python310-free-loop-20261009-v1.md`；配置与原始日志在两端 `.local/experiments/server-python310-free-loop-20261009-v1/`，启动先 `source .local/remote-env.sh`。安装中的慢速下载中止与缓存恢复已记录，不是功能失败。当前文档及验收记录未提交、未推送；用户 `reference/` 文件保留。下一步可在此环境接论文生成与投稿的最小 MCP 场景；尚未安装论文编译工具、联调真实论文或实现前端/API，付费任务及实际投稿仍需授权。
