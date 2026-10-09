# DeepSeek Harless：Motif × DeepSeek Harness × 自定义 MCP

DeepSeek Harless 是本项目统一的产品名称；当前仓库是供场景开发使用的最小主线。MotifAgent 的迁移内核负责有证据支持的结构执行；DeepSeek Harness（DSH）负责 Agent 循环、语义判断、工具派发和会话。场景通过 MCP 扩展。历史环境变量、协议标识和目录保持兼容，不因产品更名修改其含义。

项目负责人已明确：后续模型联调、场景验收和质量/成本对照统一使用真实 DeepSeek API。服务器先加载 `.local/remote-env.sh`，在私有 `.env` 配置 `DEEPSEEK_API_KEY`；Web 用 `npm run web:real`，SDK 场景用 `npm run scenario:real -- --scenario scenarios/example/scenario.json --budget-usd 0.25`。Web 每任务与整次启动均默认上限 0.25 美元；SDK 每次运行默认上限 0.25 美元，运行前核对预览与有效配置，超出既有上限另行确认。已完成一次 SDK/Harness/MCP 的真实 API 闭环：3 次 HTTP 200、4 次工具、来源引用一致，见[最小真实调用记录](docs/experiments/deepseek-real-api-smoke-20261009-v1.md)。3080 的历史服务为模拟模式；3086 真实 Web 后端两项任务已通过，浏览器点击体验仍待确认，见[连接恢复与真实 Web 验收](docs/experiments/web-real-recovery-20261009-v1.md)。

`npm test`、无模型 `smoke`、故障注入及旧模拟回归继续检查协议、权限和失败恢复。它们仅是开发诊断；不能作为模型回答、科研交付或真实降本的验收依据。真实 API 失败时记录失败，不切回固定模拟回复来报告通过。

旧试验、报告、应用专用启动器和失败试跑均在 `archive` / `archive-pre-cleanup-20261009` 分支。本机 `.local/` 是私有运行区，仍保留且不提交。清理范围与恢复方式见 [清理记录](docs/main-cleanup.md)。

## 十分钟启动

项目要求 Node.js 20+，当前优先使用已验收的 Node.js 22。Python 3.10.8 与 3.12 均已通过免费运行验收；服务器 3.10.8 的安装、测试与模拟闭环见[验收记录](docs/experiments/server-python310-free-loop-20261009-v1.md)。先安装固定依赖，再跑不付费的检查：

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

SDK 的 `npm run scenario` 继续保留。`npm run web` 默认启动官方 Web 与 DeepSeek Harless 任务工作台：同一进程可连续处理不同任务，每个任务有独立 Session、模式、预算和记录，当前同时只执行一个任务。服务器已验证 Node 22.23.3、Python 3.10.8；TypeScript 插件需要支持原生类型剥离的 Node，其他平台的 Web 尚未验证。

在服务器项目目录启动，本地建立端口转发：

```sh
# 服务器
source .local/remote-env.sh
npm run web
# 本地另一个终端
ssh -N -L 3080:127.0.0.1:3080 -p SSH_PORT USER@SERVER
```

默认加载 `scenarios/example/`，使用免费模拟模型、baseline，监听 `127.0.0.1:3080`。从本次 `.local/web/runs/<RUN_ID>/access-url.txt` 复制官方认证地址到本地浏览器，再打开同源的 `/tasks` 工作台。认证地址/token 为私有数据；主机名和端口保持 `127.0.0.1:3080`。填写要求或 JSON、选择模式与附件后，点击“开始免费联调”即可执行，无需填写额度或再次确认；界面在后台完成规范化、预览、上传和提交。结束后可直接创建下一个任务，不需要重启。官方聊天在模拟模式也能接收新会话的任务，真实模式的官方聊天会弹出题面与预算确认框，确认前不调用模型；任务工作台也保留预览与确认。旧 `/sss` 保留为兼容别名。

文字字符串、`instruction`、`content`、仅含 user 的 `messages` 统一规范化为一次任务输入；结构化对象中的后三项必须三选一。`mode` 支持 baseline/shadow/execute。可在 `content` 中附带官方格式的图片 base64 或同 Session 已上传文件的 receipt。工作台文件上传上限为 256 KiB；模型不支持图片时任务明确失败且不发起模型请求，不能据此宣称已支持图片理解。资料引用使用已由服务器登记的 `resource_id`，不接受浏览器本地路径。请求和响应详见[接口文档](docs/interfaces.md)。

`--scenario` 接受场景名或场景配置路径，每次启动只注册一个能力配置；动态题面不再固定在场景文件中。资料登记为服务器私有 JSON，例如 `.local/inputs/resources.json`：

```json
{"paper-notes": {"text_file": "notes.md"}}
```

```sh
npm run web -- --scenario scenarios/example/scenario.json --resources .local/inputs/resources.json
npm run web -- --scenario portfolio-v1 --mode execute
```

`text_file` 相对登记文件，启动时读取 UTF-8 内容并冻结字节 SHA-256；前端用 `inputs: [{"resource_id":"paper-notes"}]` 引用，后端核验可选期望版本后将带来源标识的文本追加给模型。修改原文件不会自动刷新本轮快照。当前登记器处理文本快照，不代表已接通 Zotero 等真实应用。

三种模式由后端保存和执行。example 没有认证库，shadow/execute 会记录原因并回到正常 Harness；portfolio 的精确冻结样例可使用首发库。新题面、附件或资料版本不能沿用旧任务的认证绑定。模拟诊断中的 execute 已观察到 7 次请求、5 个结果验证通过的接管批次，不能当成真实质量或费用收益。

后台保留双层预算：每任务默认 0.25 美元/24 次，全启动默认 0.25 美元/256 次，每请求最多 1000 输出 token；新任务不重置全局限制。任务上限用 `--budget-usd/--request-limit` 配置，全启动用 `--run-budget-usd/--run-request-limit` 配置。固定 `reasoning_effort="off"`，默认关闭压缩；请求、缓存输入/输出 token、费用和 verified skips 仍完整记录，代理估值需与账单核对。免费模拟不展示额度表单，实际支出为零。

真实连接须在服务器根目录的私有 `.env` 填写 `DEEPSEEK_API_KEY`，公共字段模板为 `.env.example`；不要提交或发送密钥。统一 npm 入口通过 Node `loadEnvFile` 读取它（要求 Node 20.12+），已有环境变量优先。填写密钥不会自动调用付费模型：

```sh
npm run web:real
```

这个显式入口只开放真实连接。官方聊天首次发送会显示题面与预算确认框；也可在 `/tasks` 预览并确认，之后才执行。官方聊天入口的真实接口验证见[确认流程验收](docs/experiments/native-chat-confirm-20261009-v1.md)，浏览器实际点击仍待确认。官方聊天不能绕过确认；SDK 的真实 API 基本连通已通过，真实 Web 后端最小闭环已通过；浏览器体验和科研交付质量仍需分别验收。

免费复验、旧入口与停止：

```sh
npm run web:tasks:check
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
