# DeepSeek Harless Web 当前交接

## 2026-10-19：统一服务启动、发布与回退入口

`npm run service -- <start|status|check|restart|rollback>` 是正式 owner/gateway 的统一入口，私有计划由 `GENELOOP_SERVICE_CONFIG` 指定。历史私有发布脚本只可参考配置准备，启动段退役。入口处理身份/配置/互斥检查、认证与令牌同步、活跃任务保护、失败回退及运行记录；保持预算进程/账本与用户数据。后续开发先读 [统一流程](../service-lifecycle.md)，验证与边界见[实施记录](../experiments/unified-service-lifecycle-20261019.md)。本地开发 `web`/`web:real` 不等于正式网站发布，Linux 管理验证不代表 Windows 托管。

## 2026-10-19：管理员内部令牌陈旧导致服务不可用

- 公开登录页/进程正常，所有者内部认证失败。直接重启 DSH 后漏写 `ownerTokenFile`；旧令牌 401、新令牌 303。已备份并原子同步当前有效令牌，网关热读取恢复，未重启、未调用模型、未改账号/数据/账本。
- `scripts/harless_owner_access.py` 提供认证后首页检查和原子同步；本次私有发布与回退脚本均接入并绑定启动日志偏移。6 项定向回归通过，生产 `--check` 返回认证后 200；已有成员刷新正常，新注册与管理员本人浏览器反馈未验。详见[故障记录](../experiments/owner-access-recovery-20261019.md)及[部署说明](../harless-account-gateway.md)。
- 所有者与成员令牌独立；后续发布不能只检查 TCP/公开登录页。代码发布与PR状态以本次提交/PR为准；线上运行代码未因此切换。

## 2026-10-19：生成文件只有文件名、不能点击

- 范围/分支：`codex/clickable-generated-files`，基于main `9f945a5` 的独立工作树，原本地工作区未改动。修复提交 `93e5309` 已推送，[PR #83](https://github.com/jingyio/GeneLoop/pull/83) 待审、未合并、未部署。
- 已完成：普通Chat命令产物快照/API/原生文件mentions/预览下载；双栏沙箱路径匹配；本轮暂存成品明确引用准入和旧报告排除；私有权限保持。新兼容库v13/v8仅重验原认证序列化IR，未重挖原始轨迹；旧库保留。
- 验证/结论：定向无模型回归已通过，最终全套/发布状态见[修复记录](../experiments/clickable-generated-files-20261019.md)。无真实API请求、新费用或收益结论；未部署线上。
- 入口/下一步：按接口重建成员policy并随PR发布，检查普通Chat和对照的文件名/卡片/下载、历史刷新及账号拒绝。`/api/harless/deliveries` 只认当前会话/任务文件ID。旧文件已覆盖且缺少快照时无法恢复。
- 回退/权限：回退PR与registry，不清理.local，不改600/700、不修改私人原件、不改变累计预算。

## 2026-10-18：Paper / Data benchmark 实际测试

用户已测 PPT，本次正式网页 Pro/Off 各做一次成对任务。Paper 两侧通过参考评分；Data Baseline 数值与原脚本重跑通过，Motif 将非法数错计为 10（应为 8）、脚本未进入下载交付，未通过。63 次请求、代理估费 $0.31953671，只有 Paper 有一次验证跳过。发现 Paper 发送后草稿残留；本次仅记录和测试，没有修复运行代码。详见[单次对照记录](../experiments/paper-data-benchmark-20261018.md)，不能泛化为稳定降本。

## 2026-10-18：双栏分别显示进度

用户最新要求覆盖下方“统一一个提示”的旧决定。Baseline/Motif 各自在回复下方显示 GeneLooping，各侧独立结束；双栏水合后不再重复显示原生全局提示，普通 Chat 继续使用原生即时反馈。隐藏无报告/文件和空回复占位，保留真实错误与已验证文件。当前 DeepSeek 两侧原本已并行，新增覆盖三个场景及预算隔离的回归，详情见[复核记录](../experiments/geneloop-paired-progress-20261018.md)。

## 2026-10-18：统一加载与场景后续聊状态

移除每侧GeneLooping，由原生聊天底部统一承接本地提交、普通执行、最新轮场景子任务及结束状态；保留后续聊天的私有上下文接线。加载遮罩绑定会话布局、隐藏全部历史/输入、修正图标溢出。附件显示同时覆盖user/steering及合并文本块。相关回归78项通过，详情见[生命周期修复](../experiments/geneloop-chat-lifecycle-20261018.md)，真实网页/发布状态见关联PR与私有验收。

## 2026-10-18：PPT 转换结构扩大复用与同模板网页对照

- 新 `ppt-master-v2` 从真实完整制作任务训练并通过独立留出，新增 pin→官方转换、转换回执→核验读取两条闭合边；实际网页验证 2 次跳过（上一版 1 次），未认证三节点链，不接管 Bash/页面制作/科研判断。Paper v8 仅兼容重编，旧库保留。
- 同一 AdaLoRA、官方 presentation_core/academic-research 模板、Pro Off：Baseline 87 请求/$1.17369790/1036.504s；Motif 80/$0.98129175/844.355s。单次估费低 16.39%，不能把 7 次请求差都归因于 2 次跳过。含失败采集共 694 请求/$7.70190830，账单未知、人工/CPU 未计价。
- 全部幻灯片均 GeneLoop 自制，未人工修订；两路六页、备注、PDF/PNG、网页预览和下载 SHA 完整。两版质量均未通过，Motif 排版更差，实际主题字体也未严格遵守指定字体；只称同模板输入，不称同样式成品或同质稳定降本。
- 运行代码冻结 `737c41f`；最终实现/守卫测试 `57e0ce4` CI 两平台 Python/Node、smoke/motif 检查通过（含明确跳过项）。共享 provider-length 原生续做仅诊断覆盖，本次未触发。详见[完整结果及测试](../experiments/ppt-master-structure-style-20261018.md)。
- 发布跟踪 [PR #73](https://github.com/jingyio/GeneLoop/pull/73)；原 PR #72 已合并并部署 `9a25a7d8`，原负向结果不改写。新部署保留数据、累计账本和回滚快照。私有原稿/报告在 `.local/deliverables/ppt-master-structure-style-20261018/`，正式回执与读取探针另存，不混入 PPT 评测费用。
- 后续优先提高共同流程的事实、公式与排版验收，再做重复盲评；本轮 `quality_cost_promoted=false`。扩大复用仅允许有真实轨迹和守卫证据的结构，不能把固定手写流水线算作学习。



## 2026-10-13 模型选择与 GLM 分支合并

- `codex/codex-login` 的模型选择、GLM 路由与预算绑定合入当前原生聊天分支；旧 `/tasks` 页面保持删除，Codex 登录原型仍为撤销状态。
- GLM 配置见 `.env.example`，凭证只保存在私有环境。已完成假密钥及免费协议诊断；真实 GLM 请求、工具调用与账单均未验收。
- 已验证：本机 `npm test` 为 153 项 Python、54 项 Node 全部通过；`npm run web:tasks:check` 免费 Harness HTTP 诊断通过，付费请求 0。新增原生模型选择到下一项聊天任务的模型与预算绑定测试。浏览器人工点击和 V100 部署仍待验收。
- 课题组共享入口仍缺独立身份、任务与文件隔离，不应向全组共享单个认证令牌。

## 2026-10-13 输入框菜单与页面清理（当前）

- 目标与范围：保留聊天输入框旁的 Harless 场景/RSI/模式选择；移除独立 `/tasks`、`/sss`、`/harless` 页面、悬浮入口及真实模式预算确认弹窗。原生聊天发送后直接执行，服务端预算约束保留。
- 分支 / commit / 工作区：`codex/harless-picker-ui`，基于合并后的 main `b330bb4`；选择菜单 `e45338f`、页面清理 `359d0bf`、直接发送 `cb7efb2`，尚未推送。
- 已完成：移除两个旧 HTML 面板和命令打开旧面板的轮询；旧页面地址返回 302 跳转聊天首页。裸 `/harless` 提示使用输入框旁菜单，具体场景/模式快捷命令保留。删除真实模式预算弹窗，原生消息发送时由服务端登记、激活预算并提交；显式任务 API 的预览/提交和全部兼容路由保留。
- 已验证：Node JS/TS 语法、Python 编译、diff 检查通过；本次在本机以现有 `.venv312` 运行 `npm test`，151 项 Python 与 50 项 Node 通过。真实模式原生发送的夹具检查了直接派发、预算只激活一次、重复请求不重跑，以及页面不再注入弹窗；这是模拟控制服务，不是付费或浏览器验收。本次零模型调用。
- 实验结论：此前 `harless-controls-20261013-v1` 真实运行记录未更改；本次仅前端入口与文档调整，不新增真实 API 测试或费用。
- 配置与数据：场景登记仍在 `config/harless-scenes.json`；V100 独立副本 `.local/validation/harless-picker-cb7efb2/` 已检出本提交并通过 11 项 Web 任务 Node 定向检查。专用 tmux `harless-controls-preview` / 3094 仍运行此前版本，尚未切换；不触碰正式 3080 或私有运行数据。
- 未完成与下一步：V100 主目录为他人正在修改的论文工作区，3094 原预览副本也有未提交改动；独立副本已就绪，3094 切换暂停，不能覆盖两处工作。浏览器确认直接发送、菜单和旧页面跳转仍待完成。多人账号与文件隔离、跨启动设置恢复仍未实现。
- 权限与预算：本次删除与 UI 检查不调用模型，预计真实 API 费用为零；真实调用继续遵循项目既有授权与预算。
- 回退与风险：本次是可逆 UI 路由/面板删除；不清理 `.local`。跨用户隔离尚未实现。

## 2026-10-09 至 10-10 历史交接（当时状态）

- 2026-10-10 访问恢复（二次故障）：用户再次出现 ERR_CONNECTION_REFUSED；本机 3086 监听和手工 SSH socket 已消失，服务器原 Web 仍响应，旧隧道退出原因未确定。改用用户级 LaunchAgent `com.jingyio.harless-web-tunnel` 自动重连，专用密钥在 `~/.ssh/harless-web-tunnel-3086`，日志在 `~/Library/Logs/DeepSeekHarless/`。服务器 `harless-tunnel` 账号仅允许公钥认证、本地转发至 127.0.0.1:3086，禁止 shell/远程转发/PTY；标记配置块 `HARLESS WEB TUNNEL 3086`，sshd 校验后重载。后台访问 Desktop 密钥曾被系统拒绝，移至 ~/.ssh 后成功；一次服务器断开被自动重试恢复。主动终止专用隧道后约 2 秒恢复，恢复后认证、/tasks、只读任务 API 均 HTTP 200。WT15/Wi-Fi 代理原绕过列表合成一个条目，追加独立 localhost/127.0.0.1/::1，原代理与规则保留。既有运行 `ebd724e8f4464b72b5cbc797210da350`、0.247 美元预算及 3 请求/4 MCP 统计不变，本次零模型调用。cookie 约 30 天，连接拒绝发生在认证前；浏览器实际刷新结果仍待用户确认。配置/代理回退快照及验证在本机 `.local/web-review/`，服务器 SSH 原配置备份在 `.local/web-review/sshd_config.before-tunnel`。回退先卸载专用 LaunchAgent，再仅移除该账号/标记配置块，校验并重载 SSH；代理按私有 snapshot 恢复，不能覆盖后来的 SSH 改动。私有运维配置未进入 Git；匿名化记录随 PR #2 更新，尚未合入 main。

- 2026-10-10 访问恢复（二次故障）：用户再次出现 ERR_CONNECTION_REFUSED；本机 3086 监听和手工 SSH socket 已消失，服务器原 Web 仍响应，旧隧道退出原因未确定。改用用户级 LaunchAgent `com.jingyio.harless-web-tunnel` 自动重连，专用密钥在 `~/.ssh/harless-web-tunnel-3086`，日志在 `~/Library/Logs/DeepSeekHarless/`。服务器 `harless-tunnel` 账号仅允许公钥认证、本地转发至 127.0.0.1:3086，禁止 shell/远程转发/PTY；标记配置块 `HARLESS WEB TUNNEL 3086`，sshd 校验后重载。后台访问 Desktop 密钥曾被系统拒绝，移至 ~/.ssh 后成功；一次服务器断开被自动重试恢复。主动终止专用隧道后约 2 秒恢复，恢复后认证、/tasks、只读任务 API 均 HTTP 200。WT15/Wi-Fi 代理原绕过列表合成一个条目，追加独立 localhost/127.0.0.1/::1，原代理与规则保留。既有运行 `ebd724e8f4464b72b5cbc797210da350`、0.247 美元预算及 3 请求/4 MCP 统计不变，本次零模型调用。cookie 约 30 天，连接拒绝发生在认证前；浏览器实际刷新结果仍待用户确认。配置/代理回退快照及验证在本机 `.local/web-review/`，服务器 SSH 原配置备份在 `.local/web-review/sshd_config.before-tunnel`。回退先卸载专用 LaunchAgent，再仅移除该账号/标记配置块，校验并重载 SSH；代理按私有 snapshot 恢复，不能覆盖后来的 SSH 改动。公共匿名记录已随 `f212141` 推送至正式待审 PR #2；私有配置未进入 Git，尚未合并 main。

- 2026-10-09 官方真实聊天修复：见 `docs/experiments/native-chat-confirm-20261009-v1.md`。原 `session/prompt` 直接报错已改为待确认任务与原生预算弹窗；确认前/重试/取消均 0 模型调用，确认后真实 3 请求/4 MCP/来源核验通过。当前 3086 运行 `ebd724e8f4464b72b5cbc797210da350`，每任务/启动上限 0.247 美元，承接旧支出后累计估费约 0.003950 美元、账单未核对。146 Python、45 Node、13 组协议诊断通过；真实浏览器点击仍待负责人确认。原论文分支不切换，公共修复随 PR #2 发布。

- 2026-10-09 真实 Web 恢复与 API 验收：见 `docs/experiments/web-real-recovery-20261009-v1.md`。3086 运行 `9ea9d68a37a44627ad3ab1d545678c37` 已后台恢复，baseline/execute 两项真实任务各 3 请求/4 MCP/0 错误，来源核验通过、独立 Session，execute 无库回退；合计代理估费约 0.002485 美元（总上限 0.25，账单待核对）。旧运行零调用，记录保留。真实浏览器点击仍待负责人确认；认证 URL 换行修复避免复制进终端提示符。

- 更新时间与交接人：2026-10-09，Codex。
- 目标与本次范围：统一前端与后端的动态任务入口；同一个官方 Harness Web 进程接收文字、结构化请求、附件和来源引用，保持 baseline/shadow/execute 与逐任务追踪。产品统一名为 DeepSeek Harless；SDK 和旧冻结入口保留，没有开发论文工具。
- 分支 / commit / 工作区未提交改动：公共实现位于 `feature/web-task-api`，基于 `origin/main` 的 `bdf934f`；在线代码提交 `8168f83` 已推送，[PR #2](https://github.com/jingyio/DeepSeek-Harless/pull/2) 已创建，按负责人授权转为待审，尚未合入 main。后续交接提交以分支 Git 历史为准。原两端 `feature/paper-submission`、论文场景、参考材料及私有运行区保留，不在本 PR 中。
- 已完成：`npm run web` 默认动态任务，`--frozen` 保留旧固定题面回归；新界面 `/tasks`、API `/api/harless/tasks`，旧 `/sss` 和 `/api/sss/tasks` 兼容。新增 `dsh_web_tasks.ts`、请求规范化、任务预算路由、工作台及 `web:tasks:check`。支持文字/JSON instruction/content/user messages、图片 base64、官方文件 receipt 和服务器登记的 resource_id；每任务独立 Session、模式和记录，当前单活跃。免费一键“开始免费联调”代码已完成，真实模式仍须预算预览/明确确认；官方队列编辑和 goal 续轮不能绕过任务绑定。
- 已验证：服务器 Ubuntu 22.04 / Node 22.23.3 / Python 3.10.8，146 项 Python、44 项 Node、18 题/83 来源 smoke、`motif:check`，冻结 Web 11 组及动态 HTTP/MCP 13 组均通过。动态 example 为 5 次代理请求/4 次 MCP；portfolio baseline/shadow/execute 为 14/14/7 次请求，三组各 13 次工具，execute 5 次 verified skip。无库或输入变化回退，图片不适配明确失败且请求数为零。以上模拟 Provider/embedding 验证协议与守卫，不验证科研答案。
- PR 精确提交复核：服务器独立工作树 `.local/pr-validation/web-task-api-dcdfdc9/` 对 `dcdfdc9352d5aaedc459863381aa0d17690659ca` 再次通过 146 Python、44 Node、smoke、动态 13 组和冻结 11 组。仅复用安装依赖，没有原工作区未跟踪资料或 `.env`；原服务保持运行，验证未新增真实 API 调用。私有摘要为该目录 `.local/validation/summary.json`，本地 `.local/pr-web-task-api/validation.json`。GitHub CI 状态以 PR 检查为准。

- 分支 / commit / 工作区未提交改动：两端均 `feature/paper-submission` / `2368235f274329be6227a8393b850633cb943da4`。本次新增入口、适配、测试和文档均未提交、未推送。原有 `AGENTS.md`、README、main 交接、服务器免费验收记录、论文交接及本地 `reference/` 工作保留；未切分支或迁移参考论文。
- 已完成：`npm run web` 默认动态任务，`--frozen` 保留旧固定题面回归；新界面 `/tasks`、API `/api/harless/tasks`，旧 `/sss` 和 `/api/sss/tasks` 兼容。新增 `dsh_web_tasks.ts`、请求规范化、任务预算路由、工作台及 `web:tasks:check`。支持文字/JSON instruction/content/user messages、图片 base64、官方文件 receipt 和服务器登记的 resource_id；每任务独立 Session、模式和记录，当前单活跃。免费一键“开始免费联调”代码已完成，真实模式仍须预算预览/明确确认；官方队列编辑和 goal 续轮不能绕过任务绑定。
- 已验证：服务器 Ubuntu 22.04 / Node 22.23.3 / Python 3.10.8，146 项 Python、44 项 Node、18 题/83 来源 smoke、`motif:check`，冻结 Web 11 组及动态 HTTP/MCP 13 组均通过。动态 example 为 5 次代理请求/4 次 MCP；portfolio baseline/shadow/execute 为 14/14/7 次请求，三组各 13 次工具，execute 5 次 verified skip。无库或输入变化回退，图片不适配明确失败且请求数为零。以上模拟 Provider/embedding 验证协议与守卫，不验证科研答案。
- 浏览器已验证：先前同一 3084 运行的两项不同文本任务各 5 次代理请求/4 次 MCP，刷新保留，截图 `.local/web-review/browser-multiple-tasks.jpg`。最新一键版本在 3084 运行 `b94e903d4a7c434dad86ee3b0e04be03` 已验：文字 baseline、JSON user messages execute 无额度表单、无第二次确认，各 completed/5 请求/4 MCP/真实支出 0，execute 明确 `no_certified_library` 普通回退，刷新保留；另一个聊天的浏览器也在该运行完成一项 5/4/0 任务。截图 `.local/web-review/browser-free-one-click.jpg`，任务/Session ID 详见动态实验记录。旧冻结入口的三模式和预算拒绝证据保留。
- 正式 3080 完整浏览器闭环已验证：动态运行 `f91a53c78a524bbaa3fb935fd68c8b4f` 保持运行，本地浏览器已认证进入 `/tasks`，DeepSeek Harless、免费一键与三模式可见。同一运行无重启提交两项不同题面，任务 `2057d2c5580d466d8efea9c385ad491a`、`ae83a4b3ad104fc7a4d0bf5760198de5` 各 completed/5 次模拟请求/4 次真实只读 MCP/实付 0，无预算输入、一键执行、独立 Session，刷新两项保留。截图 `.local/web-review/browser-live-multi-tasks.jpg`，具体 Session 见实验记录。旧冻结 3080 运行 `b1bce3882e5f470eb6f8ccc088e7a505` 与诊断 3084 `b94e903d4a7c434dad86ee3b0e04be03` 均按身份停止，资料保留。
- 实验结论：新增 `dynamic-web-tasks-20261009-v1`，见 `docs/experiments/dynamic-web-tasks-20261009-v1.md`；原冻结记录 `docs/experiments/harness-web-v1-20261009.md` 保留。支持动态输入、独立追踪和认证回退可运行，不支持真实语义质量或费用收益。旧模拟 Provider 累计 24 次的错误上限已修，失败记录保留，重验 13 组通过。
- 配置与数据：公共配置 `config/harness-web.json`，固定 DSH `0.1.5-rc.3`；运行先 `source .local/remote-env.sh`。`.env.example` 仅字段，统一 npm 入口加载服务器项目根私有 `.env`；原 `DEEPSEEK_APIKEY` 已补为规范 `DEEPSEEK_API_KEY`，文件权限 `600`，密钥值不记录。`--real-model` 显式开放真实连接，产品真实任务仍确认；SDK 已实际调用成功，现有 Web 仍为 mock。来源登记 `--resources` 的文本快照，版本为字节 SHA；尚无真实应用 resolver。Web 记录在 `.local/web/runs/<RUN_ID>/tasks/<TASK_ID>/`，含快照、原生事件、答案、ledger 和 Motif audit，全局账本另存启动目录。
- 后续模型验收约定：用户已持续授权测试目的真实 DeepSeek API。今后端到端、场景和效果/成本验收默认在服务器使用 `npm run web:real`（SDK 用 `npm run scenario:real`），不再用固定回复替代；单元、错误注入和无模型 smoke 保留为诊断。一般 `web` 与 CI 仍可默认 mock 避免暗中付费。当前正式 3080 仍为 mock，已记录结果不追改。
- 真实 SDK/API/MCP 已验证：example/baseline、`reasoning_effort="off"`、预算 0.25 美元、单请求输出 1000 token、8 步的 `scenario:real` 退出 0，耗时 9.729 秒；运行 `7929653e0d9d4828bf46e4ff49394abd`，Session `sss-105f45630d444789bccf467f3718006a`。3 次真实上游请求均 HTTP 200；4 次真实 MCP（2 pin/2 read）、0 工具错误，两个来源的 ID、SHA、读取正文和答案引用逐项一致。prompt 2712 token（缓存命中 1536/未命中 1176）、output 1043、total 3755，代理估费约 0.001614 美元，账单实付未核对。记录 `docs/experiments/deepseek-real-api-smoke-20261009-v1.md`；原目录 `.local/runs/7929653e0d9d4828bf46e4ff49394abd/`，原始轨迹、答案和 `verification.json` 已同步两端 `.local/experiments/deepseek-real-api-smoke-20261009-v1/`。仅支持 SDK 基本连通；合成来源，质量未盲评，无收益结论。现有 3080 未重启且仍为 mock，真实 Web 尚未验。
- 未完成与限制：真实 Web、语义 embedding、科研质量、费用收益、Windows Web、多用户隔离与跨启动恢复未验证；真实 SDK/API/MCP 基本连通已通过。一个启动只注册一个能力配置；256 KiB 文件上限，文件 receipt 通过不代表论文/PDF 内容理解。论文工具闭环未开发，认证文件浏览不是多人文件沙箱。预算、启动器和现有纯代码节点仍依赖 Python。
- 接手下一步：1. 负责人审阅工作区，分开提交公共 Web 改动与论文场景工作；未提交/推送状态不得当作团队已同步。2. 场景负责人用真实联调入口接自己的 MCP 与输入，先执行最小普通闭环，再冻结独立任务/认证 library。3. 按质量标准及真实用量评估收益，模拟诊断只验协议；真实模型测试在授权限额内推进，不重复询问同一授权。
- 权限与预算：测试目的真实 API 持续授权已生效，后续调用仍在服务器；运行前说明有效预算，Web 保持每任务/全启动 0.25 美元及 24/256 次默认限制。SDK 最小真实运行上限 0.25 美元，代理估费约 0.001614 美元、账单实付待核对；未知总额度不扩大支出，不重启循环规避限额。超额、外部写操作和实际投稿另确认。密钥不展示，产品真实任务仍保留预算预览/确认。

- 权限与预算：测试目的真实 API 持续授权已生效，后续调用仍在服务器；运行前说明有效预算，后续 Web 每任务/全启动默认上限改为 1 美元，保留 24/256 次限制；SDK 默认上限也为 1 美元。现有进程的有效配置不自动改变。SDK 最小真实运行上限 0.25 美元，代理估费约 0.001614 美元、账单实付待核对；未知总额度不扩大支出，不重启循环规避限额。超额、外部写操作和实际投稿另确认。密钥不展示，产品真实任务仍保留预算预览/确认。
- 回退与风险：撤回本次新增入口和小范围共享适配即可保留 SDK 基线；不修改上游包、不要删除 `.local/`。前台 Ctrl+C 或按 README 停止指定 RUN_ID；停止会保留数据。只停止本任务进程，不能扫描/终止共享服务器上的其他开发任务。
