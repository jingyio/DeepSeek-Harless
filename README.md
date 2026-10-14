# DeepSeek Harless：Motif × DeepSeek Harness × 自定义 MCP

四场景研究代码的分支整合与兼容验收见 [当前整合记录](docs/experiments/four-scenario-main-integration-20261014-v1.md)。论文生成工具/轨迹 RSI 的显式实验入口在 [论文场景](scenarios/paper-submission/README.md)，文献处理在 [文献场景](scenarios/literature-notes/README.md)。研究 CLI 与统一 Web 的工具契约不同，分支合并不会自动赋予旧实验库产品 Execute 权限；文献的任务级 Web 绑定和双栏评分仍需单独验收。

Web 场景快捷入口支持 `/ppt`、`/paper`、`/data`、`/chat`，输入前缀即可选择并显示有色标识；`/harless` 同时列出场景、模式和 RSI。可用性由当前账号的实际部署决定。已有会话切换场景会新建对应会话并保留原聊天与未改写的草稿；同一场景的文字续聊保留上下文。详见 [场景与账号控制](docs/harless-controls.md)。

DeepSeek Harless 是本项目统一的产品名称；当前仓库是供场景开发使用的最小主线。MotifAgent 的迁移内核负责有证据支持的结构执行；DeepSeek Harness（DSH）负责 Agent 循环、语义判断、工具派发和会话。场景通过 MCP 扩展。历史环境变量、协议标识和目录保持兼容，不因产品更名修改其含义。

既有论文/DeepSeek 对照继续使用真实 DeepSeek API；共享 Web 现在可按服务器配置选择 GLM。服务器先加载 `.local/remote-env.sh`，在私有 `.env` 配置所需模型密钥（SDK 场景仍需 `DEEPSEEK_API_KEY`）；Web 用 `npm run web:real`，SDK 场景用 `npm run scenario:real -- --scenario scenarios/example/scenario.json --budget-usd 0.25`。Web 每任务与整次启动均默认上限 0.25 美元；SDK 每次运行默认上限 0.25 美元，运行前核对预览与有效配置，超出既有上限另行确认。已完成一次 SDK/Harness/MCP 的真实 API 闭环：3 次 HTTP 200、4 次工具、来源引用一致，见[最小真实调用记录](docs/experiments/deepseek-real-api-smoke-20261009-v1.md)。3080 的历史服务为模拟模式；3086 真实 Web 后端两项任务已通过，浏览器点击体验仍待确认，见[连接恢复与真实 Web 验收](docs/experiments/web-real-recovery-20261009-v1.md)。

`npm test`、无模型 `smoke`、故障注入及旧模拟回归继续检查协议、权限和失败恢复。它们仅是开发诊断；不能作为模型回答、科研交付或真实降本的验收依据。真实 API 失败时记录失败，不切回固定模拟回复来报告通过。

旧试验、报告、应用专用启动器和失败试跑均在 `archive` / `archive-pre-cleanup-20261009` 分支。本机 `.local/` 是私有运行区，仍保留且不提交。清理范围与恢复方式见 [清理记录](docs/main-cleanup.md)。

## 十分钟启动

当前 SDK 场景入口使用 `import.meta.main`，需要 Node.js 22.18+；安装清单的宽松 engine 范围不能代替实际启动验证。Python 3.10.8 与 3.12 均已通过主线免费运行验收；科研 PPT 场景在服务器使用 Python 3.12，额外渲染依赖按场景说明安装。服务器 3.10.8 的主线验收见[验收记录](docs/experiments/server-python310-free-loop-20261009-v1.md)。先安装固定依赖，再跑不付费的检查：

```sh
npm ci
npm run setup
npm test
npm run smoke
npm run motif:check
npm run scenario
```

最后一条只输出场景、工具、提示哈希、预算和 `reasoning_effort="off"` 的预览。不会启动付费任务。Windows 的入口相同；Python 命令需要在 PATH 中，或设置 `SSS_PYTHON` 为解释器路径。已验证 macOS 本机，以及 Ubuntu / Windows CI 的 Python/Node 测试、18 题 MCP 检查与 Motif 样例闭环（Node 22、Python 3.12）；云模型和真实应用场景仍需各自联调。自定义 MCP 自身的平台依赖仍由场景负责人处理。

本次已配置的远程开发环境使用项目内隔离的 Node 与 Python 环境。在服务器项目目录先执行 `source .local/remote-env.sh`，再使用上述 `npm` 入口；该脚本是服务器私有配置，不随 Git 分发。

仓库文本统一 UTF-8/LF，由 `.gitattributes` 固定检出换行符；统一入口也为 Python 设置 UTF-8。冻结夹具和 Motif 证据按原始字节校验，不能因 Windows 换行符变化而更新锁中的哈希。Windows 已有旧检出副本时，保存自己的改动后重新克隆最新 main 最容易确保规则生效。Unix 的 `0600` 模式检查只在相应平台运行；Windows 文件访问由 ACL 管理，不能用该数字替代 ACL 验证。

明确决定付费运行后，先在本机环境或 Harness 的 `.local/dsh` 凭证存储配置密钥，再显式执行：

```sh
npm run scenario:real -- --budget-usd 0.25 --max-steps 16
```

每次请求经过本机预算代理；模型输出、轨迹、预算账本与 Motif 审计只写入 `.local/`。费用表是仓库固定配置，运行付费实验前应核对；预算记账不等于真实账单。`--max-steps` 限制 Agent 步数，代理账本才记录实际上游请求。默认不开上下文压缩。

## 官方 Harness Web 与动态任务入口

SDK 的 `npm run scenario` 继续保留。`npm run web` 默认启动官方 Web 与 DeepSeek Harless 任务接口：任务从官方聊天提交，`/harless` 使用 Harness 原生命令菜单选择场景、RSI 和执行模式。每项任务有独立 Session、模式、预算和记录，同一时刻只执行一个任务；不再提供独立任务工作台页面或悬浮入口。服务器已验证 Node 22.23.3、Python 3.10.8；TypeScript 插件需要支持原生类型剥离的 Node，其他平台的 Web 尚未验证。

在服务器项目目录启动，本地建立端口转发：

```sh
# 服务器
source .local/remote-env.sh
npm run web
# 本地另一个终端
ssh -N -L 3080:127.0.0.1:3080 -p SSH_PORT USER@SERVER
```

默认动态运行时使用 `scenarios/general/`（New Scene），免费模拟模型、Shadow（RSI On），监听 `127.0.0.1:3080`。从本次 `.local/web/runs/<RUN_ID>/access-url.txt` 复制官方认证地址到本地浏览器，打开聊天首页即可。认证地址/token 为私有数据。原生 `/harless` 菜单的 PPT、Paper Proofreading、Research Data Analysis、Files 和 New Scene 分别加载服务器登记的 MCP、白名单与 Prompt：PPT 使用既有19工具；论文提供PDF/文本与静态LaTeX检查；数据提供CSV/TSV描述统计与Pearson相关；Files 盘点、读取、查重和索引任务上传文件，可显式授权整理副本；New Scene读取本Session上传文本。模式和RSI独立，菜单不调用模型，选择影响下一任务。PPT菜单可设置页数、模板及生成新副本权限；Files 菜单可设置只读或整理任务副本。免费和真实任务从聊天直接发送，服务端保留费用、请求上限与工具权限；旧页面跳回聊天，任务 API 保留。

PPT先安装 `scenarios/research_ppt/requirements.txt`，在该目录 `npm ci && npm run build`；需要兼容的LibreOffice、中文字体与静态Fontconfig才能输出。仅部署论文PDF读取时安装 `scenarios/paper_proofreading/requirements.txt`，纯文本校对/数据CSV分析不需渲染依赖。管理员在私有环境设置 `HARLESS_PPT_RENDERER_ROOT/HARLESS_PPT_FONT_ROOT`，缺失时只读可用、输出明确拒绝。`HARLESS_PPT_RUNTIME_BUNDLE` 指向已认证且代码锁有效的五文件包，当前仅接管闭合pin/read；没有库的场景可用Origin/Shadow，Execute On拒绝。部署成员能力只增加网关 `memberSceneDeployment` 只读挂载，输入、Session、产物和预算继续隔离。完整配置、范围与诊断见 [控制协议](docs/harless-controls.md)、[账号网关](docs/harless-account-gateway.md) 和 [上线准备记录](docs/experiments/harless-launch-readiness-20261014-v1.md)。V100 Ubuntu18/Node22.23.3/Python3.10.21已验证；完整模型自主PPT生成与科研质量未在本轮验收。

原生模型选择可切换服务器已启用的 DeepSeek Flash 与 GLM；默认免费模拟仍使用 DeepSeek。真实 Web 可在服务器私有 `.env` 配置 GLM 模型、密钥和价格。选定模型会绑定任务和预算账本；GLM 当前只接文字输入，真实 GLM 请求仍待验收。Codex 登录入口已撤销，当前不提供 GPT 登录。

文字字符串、`instruction`、`content`、仅含 user 的 `messages` 统一规范化为一次任务输入；结构化对象中的后三项必须三选一。`mode` 支持 baseline/shadow/execute。任务 API 可接收官方格式的图片 base64 或同 Session 已上传文件的 receipt，单文件上限 256 KiB；模型不支持图片时任务明确失败且不发起模型请求，不能据此宣称已支持图片理解。资料引用使用已由服务器登记的 `resource_id`，不接受浏览器本地路径。请求和响应详见[接口文档](docs/interfaces.md)。

`--scenario` 接受场景名或场景配置路径，用来选择初始运行时；`config/harless-scenes.json` 登记已接通的后台场景，每个场景使用独立的 MCP preset，当前诊断样例不在前端选项中。动态题面不再固定在场景文件中。资料登记为服务器私有 JSON，例如 `.local/inputs/resources.json`：

```json
{"paper-notes": {"text_file": "notes.md"}}
```

```sh
npm run web -- --scenario scenarios/example/scenario.json --resources .local/inputs/resources.json
npm run web -- --scenario portfolio-v1 --mode execute
```

`text_file` 相对登记文件，启动时读取 UTF-8 内容并冻结字节 SHA-256；前端用 `inputs: [{"resource_id":"paper-notes"}]` 引用，后端核验可选期望版本后将带来源标识的文本追加给模型。修改原文件不会自动刷新本轮快照。当前登记器处理文本快照，不代表已接通 Zotero 等真实应用。

三种模式由后端保存和执行。example 没有认证库，shadow 会记录原因并回到正常 Harness，execute 不可选；portfolio 的精确冻结样例可使用首发库。新题面、附件或资料版本不能沿用旧任务的认证绑定。模拟诊断中的 execute 已观察到 7 次请求、5 个结果验证通过的接管批次，不能当成真实质量或费用收益。

主要通过原生 `/harless` 选择菜单操作。具体参数命令仍可用于诊断；裸命令在不支持浏览器装饰的客户端会提示使用菜单。支持：

```text
/harless list
/harless mode shadow
/harless rsi off
/harless status
```

Mode 菜单显示 Origin、Shadow、Execute；Origin 在协议中仍为 `baseline`。RSI 默认 On，切换模式不改变开关；Off 保留所选模式，但下一任务按 Origin 执行。没有认证库或本地匹配服务时 Execute 会被服务端拒绝；Shadow 可以运行并明确记录普通 Harness 回退。菜单选择本身不调用模型，默认用于之后创建的会话。一个 Session 仍只绑定一个 Task，不复用旧预算或证据。

目前登记 `example`、`portfolio-v1`、`portfolio-v2` 三个合成资料场景；新增场景由服务器维护登记表和 MCP 配置。PPT MCP 与自动持续学习发布尚未实现。可选的 Linux 账号网关提供邀请码注册、独立 Harness Home/工作区及按账号隔离的预算路由；它需要单独配置并通过反向代理公开，直接运行 `npm run web` 仍是单用户开发入口。配置与限制见[账号网关部署说明](docs/harless-account-gateway.md)，任务接口见 [Harless 控制接口](docs/harless-controls.md)。

后台保留双层预算：每任务默认 0.25 美元/24 次，全启动默认 0.25 美元/256 次，每请求最多 1000 输出 token；新任务不重置全局限制。任务上限用 `--budget-usd/--request-limit` 配置，全启动用 `--run-budget-usd/--run-request-limit` 配置。固定 `reasoning_effort="off"`，默认关闭压缩；请求、缓存输入/输出 token、费用和 verified skips 仍完整记录，代理估值需与账单核对。免费模拟不展示额度表单，实际支出为零。

真实连接在服务器根目录的私有 `.env` 填写 `DEEPSEEK_API_KEY` 或 `HARLESS_GLM_API_KEY`；GLM 还要配置 `HARLESS_GLM_MODEL`、官方 `HARLESS_GLM_BASE_URL` 和两项保守的美元/百万 token 价格，字段见 `.env.example`。密钥只由服务器读取；浏览器 API 仅收到模型名称和可用状态，不读取 `.env`。不要提交或发送密钥。统一 npm 入口通过 Node `loadEnvFile` 读取它（要求 Node 20.12+），已有环境变量优先。填写密钥不会自动调用付费模型：

```sh
npm run web:real
```

这个显式入口只开放真实连接。官方聊天发送后立即登记并执行任务，不显示预算确认页面；任务 API 仍保留显式预览和提交操作。发送前可在输入框旁选择场景、RSI 与模式，服务端继续限制每任务及全启动费用和请求数。此前的[确认流程验收](docs/experiments/native-chat-confirm-20261009-v1.md)记录的是旧界面；SDK 的真实 API 基本连通已通过，真实 Web 后端最小闭环已通过；当前直接发送的浏览器体验和科研交付质量仍待验收。

GLM 请求通过本地预算代理绑定已提交任务；`HARLESS_GLM_BASE_URL` 仅接受智谱官方 HTTPS API 根地址。价格由管理员按所用模型与账户填写，代理估值不等于账单实付。当前 GLM 已完成假密钥启动、模型目录与任务预览验证，真实 GLM 请求和工具调用仍待配置有效密钥后验收。

免费复验、旧入口与停止：

```sh
npm run web:tasks:check
npm run web:controls:check # 免费原生命令与多场景协议诊断（真实验收加 --real-model）
npm run web:check
npm test
npm run smoke
npm run motif:check
# 旧固定题面/单任务入口，保留回归用途：
npm run web -- --frozen --scenario portfolio-v1 --mode execute
# 前台用 Ctrl+C；后台仅停止指定 RUN_ID，保留结果：
node scripts/project.mjs python scripts/stop-harness-web.py RUN_ID
```

服务器已通过 146 项 Python、44 项 Node、13 组动态 HTTP/MCP、11 组冻结协议诊断，以及 18 题/83 来源 smoke；Motif 样例闭环也已通过。实际付费为零，详见[动态任务验收](docs/experiments/dynamic-web-tasks-20261009-v1.md)与[Web 交接](docs/handoffs/harness-web.md)。HTTP 诊断不代替浏览器体验和真实质量评审。每个动态任务的数据独立位于 `.local/web/runs/<RUN_ID>/tasks/<TASK_ID>/`，含输入/配置快照、会话事件、答案、ledger 和 Motif 审计；启动目录另保留全局预算账本。goal 续轮、队列编辑、fork 或 steer 不能绕过既有任务绑定，改变要求需创建新任务。

当前适用于同一获授权操作人的服务器联调，没有多人账号隔离、跨启动任务恢复或论文工具闭环；官方文件浏览能力也不是多人文件沙箱。具体实现与限制见[接口文档](docs/interfaces.md)、[Web 交接](docs/handoffs/harness-web.md)及[冻结入口验收](docs/experiments/harness-web-v1-20261009.md)。

## 代码从哪里读

| 目录 | 责任 |
| --- | --- |
| `scenarios/` | 各同学的 MCP 配置、题面、服务、工具契约 |
| `src/adapters/scenario.py` | 校验场景并生成私有 DSH 插件配置；支持 stdio / streamable-http |
| `src/adapters/harness_runtime.py` | Python SDK → Node Harness 的唯一启动边界 |
| `src/adapters/dsh_scenario_guard.mjs` | 限定场景工具集合，阻止绕过 MCP 读仓库或执行 shell |
| `src/adapters/dsh_online_motif.mjs` | DSH 原生插件；在模型请求前匹配认证 Motif，在工具结果后复核 |
| `src/adapters/dsh_trajectory.py` | Harness 原始工具事件 → 带参数来源的轨迹 |
| `src/motif_core/offline/` | 轨迹挖掘、DAG/参数流编译、独立留出认证与 library 产物 |
| `src/motif_core/controller.py`、`read_executor.py` | Python 结构控制、依赖/证据守卫、handoff/reentry |
| `src/motif_core/online_skill_runtime.mjs` | DSH 插件使用的在线执行子集，含受限纯代码参数转换 |
| `tests/` | 结构核心、接口、版本失效、权限拒绝与安全回退回归 |
| `benchmarks/research_decision_portfolio_v{1,2}/` | 18 项冻结的合成科研决定，仅供开发诊断 |

先读 [接口契约](docs/interfaces.md)，再复制 `scenarios/example/` 接一个新场景。`src/motif_core/LICENSE` 和 [来源及迁移记录](src/motif_core/PROVENANCE.md) 必须保留。

科研 PPT 场景的安装与最短入口见 [research_ppt](scenarios/research_ppt/README.md)：接收 PDF/PPTX、生成可编辑 PPTX，并在 Linux 服务器通过 LibreOffice 输出真实预览。其渲染、字体和场景依赖需另外安装；PPT 场景的真实 Windows 运行尚未验证。来源读取 Motif 与普通组合生成脚本的边界见接口契约，不把脚本执行计为 Motif 收益。

科研 PPT 试用统一使用 `npm run ppt -- --input .local/inputs/paper.pdf --slides 6 --template lab --allow-output`：默认准备普通 DSH／组合优化两路预览，双路总上限 $3、每路 $1.50，不调用模型。确认预览后用 `npm run ppt -- --trial <实际trial.json> --call-model` 执行；完整命令、评审与费用范围见[双路试用](scenarios/research_ppt/trial.md)。朴素 `lab` 保留科研原图与可编辑数据，不强迫填满卡片；原生模板实验服务仍属历史隔离试用，不是此默认入口。

部署反馈与离线学习见[使用说明](scenarios/research_ppt/feedback-learning.md)。仅显式授权时收集，质量未审阅不进入训练；独立认证生成候选，后续真实任务验证收益后才可受控晋级。`--use-active-learning` 显式继承当前有效版本，没有已晋级版本时走普通流程并记录原因。不能仅因工具生成或测试通过宣称自进化收益。

## 随仓库分发的 Motif 库

[首发样例](examples/motif-library/research-portfolio-v1/README.md) 包含此前真实 DeepSeek 调用轨迹编译出的 4 个 Motif、在线 manifest、公开证据夹具和版本锁。任务资料为合成科研模拟；历史认证摘要保持不变，没有分发原始私有日志。

`npm run motif:check` 无需密钥，用真实 Harness/MCP 和本机模拟 Provider 检查重编译一致性、执行、shadow 及旧版本回退；`npm run motif:rebuild` 只重编译到 `.local/`。新克隆无需旧 `.local` 数据。它是调试验收起点，不代表真实科研质量或费用收益。加载命令和适用范围见样例说明。

## 18 题怎么跑

```sh
npm run scenario -- --scenario scenarios/portfolio-v1/scenario.json --case l_state_update
npm run scenario -- --scenario scenarios/portfolio-v2/scenario.json --case a_model_rsi_figure
```

默认均为预览。`npm run smoke` 会经真实 stdio MCP 客户端遍历全部 18 题，验证冻结哈希、对象句柄、版本和八种只读工具，并初始化 Harness SDK；不调用付费模型。这能证明工具链可用，不能证明 Agent 会答对题或 Motif 已降低科研成本。付费普通组/结构组和盲评需要另外运行并记录。

Motif 模式的入口与普通组相同，增加 `--mode shadow` 或 `--mode execute`、`--manifest`、`--task`、`--embedding-endpoint`、`--embedding-model`。只能使用轨迹编译且认证通过的 library；完整数据契约与命令见接口文档。

## 两天协作约定

每人一个场景分支，例如 `codex/scene-literature`、`codex/scene-results`、`codex/scene-collaboration`，主要改自己的 `scenarios/<name>/` 和对应测试。你负责公共接口和合并；核心变更先协调。每个小改动提交一次，通过 `npm test` 后发 PR，尽早合回 main。合入别人的工作后，各自同步最新 main。具体操作见 [协作说明](docs/collaboration.md)。

## 科研 PPT 历轮报告与恢复交付

历轮 PDF 的文件身份和结论见 [报告索引](docs/experiments/research-ppt-reports/README.md)；PDF 本体保留在团队私有归档，不进入 main，历史失败和勘误仍可按索引追溯；原始论文、运行日志、凭证仍只保存在私有区域。报告版本数量不等于独立实验数量。

V7/V8 的同任务 MCP 重启恢复及 TypeScript 有限交付入口见 [恢复与交付说明](scenarios/research_ppt/delivery.md)。新增入口仍使用 Python 场景工具后端；未实现无 Python 插件产品。最新两题对照的 Motif 组请求、token 和代理估费均增加，且未达到统一人工质量门槛，不支持整体降本。详见 [V7](docs/experiments/research-ppt-v7-delivery-rsi-20261011.md)、[V8](docs/experiments/research-ppt-v8-cost-quality-rsi-20261011.md)。科研 PPT 为场景 pilot，不能代替主线跨应用科研决定验收。

后续工程结果见 [V10](docs/experiments/research-ppt-v10-product-20261012.md) 与 [V11](docs/experiments/research-ppt-v11-scientific-design-20261012.md)：V10 在两份相同明确标题编辑任务中由普通入口省去模型；V11 增加科研原图、结果、方法页型并交付三组同内容对照和一份真实新稿。两者都不称新增 RSI。原始轨迹、来源及 PPT 仅保存在私有区，独立科学/视觉人评与完整生成净成本仍未证明。

### Harless 多场景 Web

`npm run web` / `web:real` 默认打开 `new-scene` 普通 Harness + Session 文件工具；`/harless` 的场景菜单直接选择服务端登记配置。PPT 连接现有19工具交付后端（需按 `scenarios/research_ppt/README.md` 安装依赖并构建），论文校对5工具、数据分析4工具及通用场景2工具均有正式后端。当前仅PPT的冻结只读来源链有生产认证库；其他场景 Shadow 记录无库回退，Execute On 明确拒绝。RSI Off 保留模式选择并实际采用 Origin。PPT 代码或Prompt变化会使旧部署包的版本锁失效，须重新认证后才可恢复 Execute。

任务与用户启动实例分别隔离；菜单不调用模型，已确认任务不随菜单变化。PPT 默认只读，生成页数/模板/输出权限经任务 API 设置后确认；原生聊天尚无该参数编辑界面。完整配置、用户入口依赖和验收见 [Harless 控制协议](docs/harless-controls.md)。`npm run web:scenes:check` 检查实际 Harness/MCP 与两用户实例隔离；`-- --real-model` 明确启用最多0.06美元的只读模型验收。历史样例工具只用 `--scene-registry config/harless-diagnostics.json --scenario example` 等显式诊断配置，默认产品菜单不映射样例。

`feature/rsi-research-agent` 的文献与文件管理实验入口和 `feature/research-ppt-agent` 的 V16/V17 场景代码已在独立后续集成分支整合。它们不自动成为四个产品菜单场景；PPT 旧双路主聊天不继承 Mode/RSI，故未注册到默认 Web 任务入口。集成状态与尚需的固定字体复验见[主线交接](docs/handoffs/main.md)。
