# DeepSeek Harless：Motif × DeepSeek Harness × 自定义 MCP

DeepSeek Harless 是本项目统一的产品名称；当前仓库是供场景开发使用的最小主线。MotifAgent 的迁移内核负责有证据支持的结构执行；DeepSeek Harness（DSH）负责 Agent 循环、语义判断、工具派发和会话。场景通过 MCP 扩展。历史环境变量、协议标识和目录保持兼容，不因产品更名修改其含义。

项目负责人已明确：后续模型联调、场景验收和质量/成本对照统一使用真实 DeepSeek API。服务器先加载 `.local/remote-env.sh`，在私有 `.env` 配置 `DEEPSEEK_API_KEY`；Web 用 `npm run web:real`，SDK 场景用 `npm run scenario:real -- --scenario scenarios/example/scenario.json --budget-usd 1`。Web 每任务与整次启动均默认上限 1 美元；SDK 每次运行默认上限 1 美元，运行前核对预览与有效配置，超出既有上限另行确认。已完成一次 SDK/Harness/MCP 的真实 API 闭环：3 次 HTTP 200、4 次工具、来源引用一致，见[最小真实调用记录](docs/experiments/deepseek-real-api-smoke-20261009-v1.md)。3080 的历史服务为模拟模式；3086 真实 Web 后端两项任务已通过，浏览器点击体验仍待确认，见[连接恢复与真实 Web 验收](docs/experiments/web-real-recovery-20261009-v1.md)。

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
npm run scenario:real -- --budget-usd 1 --max-steps 16
```

每次请求经过本机预算代理；模型输出、轨迹、预算账本与 Motif 审计只写入 `.local/`。费用表是仓库固定配置，运行付费实验前应核对；预算记账不等于真实账单。`--max-steps` 限制 Agent 步数，代理账本才记录实际上游请求。默认不开上下文压缩。

## 论文场景基础环境

最新[导出收据与成本优化](docs/experiments/paper-rsi-export-receipt-20261012-v6.md)：同论文三项新版原生15请求、execute9请求，5次接管已核验，完整结构/字段保留全通过；1次请求差来自原生额外无变化写入，严格Shadow4/15。新版同工具代理估费低12.75%，比旧V5 execute低21.55%（包含收据/输出工程优化，不全归因于Motif）。一份最终说明混淆报告key与Bib键范围，保留；完整事实/PDF、跨论文与人工盲评未验收，学习未摊平。累计7.96362748/10美元，无付费进程，代码未提交/推送。

新增[连续输入Schema与状态守卫](docs/experiments/paper-rsi-effect-guards-20261012-v5.md)：生成算法不改，合格输出能再次作为输入；新固定范围真实请求14→9，减少35.71%，代理费仅降3.56%，三结构验收通过，已有完整报告复核费用反而升3.89%。失败检查拒绝目前只有免费诊断，真实模型恢复未验收；学习未摊平。累计7.947135/10美元，夜间固定计划完成，停止新增调用。

最新[本地最小视图与真实execute](docs/experiments/paper-rsi-local-view-execute-20261012-v4.md)：四正常Session学出两局部图；三项同工具原生15请求、execute实际9请求，6次接管全部核验，严格Shadow6/15＝40%，三项完整结构/字段保留通过。同工具代理估费下降13.24%，学习尚未摊平；未验收完整文献事实/PDF、跨论文或人类盲评。[V2/V3失配与覆盖失败](docs/experiments/paper-rsi-local-view-shadow-20261012-v2-v3.md)全部保留，不追改旧结果。可读[两局部图](examples/motif-library/trace-rsi-patch-execute-v1/README.md)及[生成修订程序](examples/rsi-tools/report-patch-v1/README.md)；视图和排版是工程提供，算法和调用图有真实生成/轨迹证据。用户最新允许本地模型测试、累计10美元，代理金额7.927070美元，含全部旧失败/预留；公共默认1美元不变。后续源码变化按各轮代码快照复核，不能更新旧manifest绕过守卫。

生成工具的结构修订链新增[完整批次与调度通道 Shadow](docs/experiments/paper-rsi-batch-shadow-20261011-v2.md)：两正常Session编译并冻结局部库后，三个预定新范围各匹配2/5严格整请求，合计40%；对应原生请求费用占23.1%，实际跳过/费用节省仍为0。两条通过原字段保留、另一条失败保留；这是同论文结构修订子任务及统一输出协议的机会，不是完整论文交付或真实降本。入口为 `node scripts/project.mjs python scripts/paper-rsi-batch-shadow.py preview --protocol-version tool-channel-v2`，默认免费预览，详见[接口](docs/interfaces.md)。

局部 Motif 进一步学习了[状态条件](examples/motif-library/trace-rsi-state-shadow-v1/README.md)：同一会话中相同版本已经检查过时，拒绝重复续接。历史回放消除2次结束误预测并保留4次正确预测；三条真实Shadow结构验收通过，工具调度匹配5/15，严格整请求和实际跳过仍为0。新增多工具批次反例及未触发的真实结束分支均保留，见[本轮记录](docs/experiments/paper-rsi-state-shadow-20261011-v1.md)。

生成工具已接入正常论文报告修订：两条正常轨迹编译两个局部 Motif，冻结后两条新范围 Shadow 各匹配 2/6 次工具调度。请求均带模型文字，严格整请求和实际跳过仍为 0；还发现“最后重读后应总结，却预测再检查”的结束状态反例。当前是同论文的范围变化与故障注入，尚非完整论文修订或跨论文验收。入口、失败记录及成本见[实验记录](docs/experiments/paper-rsi-generated-task-shadow-20261011-v3.md)；[可读局部图](examples/motif-library/trace-rsi-shadow-v1/README.md)不替代私有认证库。

服务器已安装 LaTeX/BibTeX、latexmk、Poppler 和 chktex；三种引擎的公共 ACM 夹具已通过。安装与无模型复验见[环境入口](scenarios/paper-submission/environment/README.md)。真实论文原生基线先被容器沙箱阻塞；本次获用户非沙箱授权后，按最新要求取消次数限制，在累计 1 美元预算内重测并补交中文报告。主稿为 14 页，报告复核仍发现误读和计数错误，质量未人工盲评，见[重测与复核记录](docs/experiments/paper-native-baseline-20261009-v2.md)；此前失败保留在[历史记录](docs/experiments/paper-native-baseline-20261009-v1.md)。这两个验收分别记录，不能用公共夹具通过代替真实论文检查。 后续 [PTC 对照](docs/experiments/paper-ptc-baseline-20261009-v1.md)已完成报告补交，但本次调用和估费高于 Native，仍有质量错误；尚不能视为可靠验收或降本。

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

后台保留双层预算：每任务默认 1 美元/24 次，全启动默认 1 美元/256 次，每请求最多 1000 输出 token；新任务不重置全局限制。任务上限用 `--budget-usd/--request-limit` 配置，全启动用 `--run-budget-usd/--run-request-limit` 配置。固定 `reasoning_effort="off"`，默认关闭压缩；请求、缓存输入/输出 token、费用和 verified skips 仍完整记录，代理估值需与账单核对。免费模拟不展示额度表单，实际支出为零。

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

## 论文 Motif 真实诊断入口

后续新增[参数化读取与并行查询局部证明](docs/experiments/parameter-motif-proof-20261010-v1.md)：从五条原生轨迹提取参数原型，在显式选定输入的真实小任务中，两类 execute 均将 API 请求从 3 次变为 2 次，工具覆盖不变。入口 `node scripts/project.mjs python scripts/parameter-motif-proof.py --phase preview` 默认不调用模型，运行依赖服务器保留的私有训练轨迹。它没有自动接管完整论文流程、复用任意脚本或完成跨任务认证；产品默认预算和原有认证规则不变。

连续接管扩展入口 `node scripts/project.mjs python scripts/paper-reference-continuation.py` 默认只预览。它使用主稿实际引用目录，由模型提交可验证的选定输入，再多轮交接结构收集与语义比较；协议见 `schemas/parameter-motif-selection.schema.json`。真实对照/范围漂移等负面证据见[阶段任务记录](docs/experiments/paper-reference-continuation-20261010-v2.md)。当前限服务器私人实验环境，未接入 Web 或完成完整论文质量验收。

论文近期评测主线改为 shadow：该入口 `--call-model` 未指定模式时使用 shadow，默认不带此参数仍只预览；重跑必须指定新 `--suffix`，不覆盖旧运行。已有真实 shadow 可用 `scripts/evaluate-shadow-continuation.py <run> --output <新的私有结果路径>` 离线分析整次工具调度机会，无新增 API。口径和限制见[shadow 评测记录](docs/experiments/paper-shadow-evaluation-20261010-v1.md)。

两次新增真实 shadow 复验合计发现 5/57 个完整纯工具请求机会（8.8%，实际跳过 0），未达到稳定 20%；逐请求清单、选择协议开销与 RSI 下一步见[复验记录](docs/experiments/paper-shadow-confirmation-20261010-v1.md)。

后续验收改为[持续学习闭环](docs/paper-rsi-loop.md)：已接通正常轨迹登记、不可覆盖的库版本、下一任务固定库与任务完成后编译。入口 `scripts/paper-motif-learn.py` 初始化训练/验证划分；论文入口增加 `--learning-store`、`--learn-after`、私有新稿 `--input-zip`。读取/arXiv 之外新增从正常轨迹提取的 Crossref 查询模板；仍限显式选定输入的 shadow 诊断，没有接管完整修订脚本或证明实际调用随学习下降。真实结果与限制见[顺序学习记录](docs/experiments/paper-rsi-sequential-20261010-v1.md)。

开始内化重复 bash：论文 MCP 显式 `SSS_PAPER_REFERENCE_RECORDS=1` 可增加批量参考文献原文/哈希工具，默认六工具保持。服务器真实 stdio MCP 核对 34 条原文一致，未调用模型；这是人工从轨迹提炼的工具底座，尚未自动编译调度 Motif 或验证节省。入口 `scripts/check-paper-reference-tools.py` 和边界见[工具化记录](docs/experiments/paper-bash-toolization-20261010-v1.md)。

[论文场景](scenarios/paper-submission/README.md)增加六个只读证据 MCP 工具，复用 Python 离线编译和共享在线拦截器。受控轨迹编译出的三个来源读取 Motif，在同工具真实 API 对照中把模型请求从 3 次变为 2 次，验证跳过一次完整请求；本次费用和耗时未降低，质量未盲评。诊断库与生产认证隔离，未接入 Web、未接管重新编译/修稿/视觉判断。默认入口只预览，详见[实验记录](docs/experiments/paper-motif-shadow-execute-20261009-v1.md)和[交接](docs/handoffs/paper-submission.md)。

论文RSI新增活动引用批次与官方arXiv批查询MCP，入口 `scripts/paper-citation-rsi.py` 默认预览、按条件显式启用工具；从真实轨迹编译调度边/链。当前批查询shadow为1/19潜在整请求机会、实际跳过0，后续阶段权限基线预算拒绝，20%目标未达到；完整论文质量未验收。最新条件、失败及接手动作见[论文交接](docs/handoffs/paper-submission.md)与[批查询实验](docs/experiments/paper-citation-batch-20261010-v1.md)。这些诊断尚未接Web，默认Coding工具不改变。

## 论文复合取证与自动检查

新增单次取得活动引用、原始BibTeX及arXiv元数据的MCP；TypeScript插件提供同一结构校验器的显式工具和写入后自动反馈。`--composite-evidence --arxiv-batch --bounded-evidence` 明确启用，默认预览。新预算记录由 `--budget-record` 指定并冻结，旧累计记录不改。提高预算后主稿baseline/shadow/execute为8/9/7请求，短稿6/8/7；六次均精确覆盖和结构通过。自动校验/修复可用，但基线与execute合计均14请求、execute估费高30.3%，语义未盲评，未达到20%总体下降；新Hook尚未学成Motif。见[最新实验](docs/experiments/paper-composite-delivery-20261010-v2.md)与[论文交接](docs/handoffs/paper-submission.md)。

论文 Shadow 增加[局部编译与逐请求审计](docs/experiments/paper-shadow-compiler-audit-20261011-v1.md)：从两条正常基线挖掘 write/edit→只读检查，冻结候选后回放留出 Session。严格仍为3/17，另有1条含旁白匹配与1条预测反例；只读复用、模型内容/选择和查询恢复缺口分别记录。无新增 API、未运行 execute、未证明稳定20%。入口 `scripts/compile-paper-shadow.py` 与 `scripts/audit-paper-shadow.mjs` 只输出私有诊断，不加载生产插件。


## 论文 RSI 前瞻 Shadow（十任务）

`scripts/paper-rsi-overnight.py` 默认预览，付费运行仅限已授权服务器。模块化 MCP 提供原始引用、arXiv 元数据和 Crossref 著录候选；`read_current_triage` 只读当前产物供恢复，`check_paper_triage` 只验证结构、范围与来源。

Python 从正常基线编译 `source_bound_readonly_batch_shadow` v1：当前任务绑定、来源参数边、并行只读批次、成功写入后的检查与失败编辑后的读取。TypeScript 在真实 LLM 请求前用冻结库记录预测，模型照常运行，无自动执行与实际跳过。工具 schema/顺序、代码与来源版本必须一致；分支歧义或守卫失败即不预测。详细结果和限制见 [实验记录](docs/experiments/paper-rsi-overnight-20261011-v1.md)。


三轮夜间实验已完成：同一篇论文十种变体、13条baseline与21条Shadow，共616次真实模型请求；严格整请求匹配21.4%→32.5%→27.4%，最佳单任务50%，实际跳过0。最终[9个候选结构](examples/motif-library/paper-shadow-v1/README.md)是从正常轨迹编译的局部边，可供读代码与调试理解，不是执行认证库。第三轮有一次无产物失败，文献语义未盲评，不能宣称实际降本或完整论文验收。结果、费用与接手步骤见[最终记录](docs/experiments/paper-rsi-overnight-20261011-v3.md)；新增查询恢复/产物恢复入口依赖服务器私有训练，默认只预览，继续暂停execute。

## DeepSeek 自生成工具的 RSI 入口

新增 `scripts/paper-rsi-trace.py`：先读取真实正常任务轨迹，让 DeepSeek 自主选择工具目标与输入输出，再生成、开发测试和修复程序；源脚本在有界内存解释器中计算未见反例，验收后冻结为动态名称的 TypeScript MCP。默认只预览，不自动执行 Motif；接口与边界见 [轨迹驱动 RSI](docs/interfaces.md)。不支持的历史 bash、失败版本和学习费用保留，不能用工具样例通过代替跨论文或节省请求的验收。

```sh
# 服务器加载环境，prepare/freeze/stdio 检查不调用模型。
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase preview
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase prepare
# 真实学习须在已授权累计预算内显式启用；实验目录与label不可覆盖。
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase learn --label learn-v03 --call-model
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase freeze --label learn-v03
node --experimental-strip-types scripts/check-trace-rsi-mcp.mjs \
  .local/paper-reference/paper-rsi-trace-tools-20261011-v3/frozen-tool.json \
  .local/paper-reference/paper-rsi-trace-tools-20261011-v3/heldout.json
```

当前默认资料是服务器私有历史轨迹；可用 `--train-run` 登记其他本仓库 `.local/` 正常轨迹，仍须通过源重放支持与版本检查。生成工具加载只需 Node，轨迹准备/预算/实验控制仍使用 Python。新入口未接 Web、未验证 Windows；以下固定目标原型保留。

`scripts/paper-rsi-tool-learning.py` 将固定版本 Harness 的原生 `cordis_define` / `cordis_run` 接到独立学习会话：DeepSeek编写、测试和修复纯数据检查程序，通过独立样例后保存固定版本，再由TypeScript MCP服务加载。学习工具集与论文服务工具集分开，默认入口不变。这是有界工具程序，不运行任意生成脚本；Node22已验证，服务器专用实验入口未验证Windows。

服务器加载 `.local/remote-env.sh` 后，`node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase preview` 只显示累计预算。付费阶段须显式指定 `--call-model`，共享原论文累计预算；免费 `freeze` / `compile` 和 `score-paper-rsi-shadow.py` 负责验收、编译与统计，`rsi-server.ts` 提供固定工作副本的读、写和只读结构检查。

首轮真实闭环：生成工具通过11项独立结构样例；两个原生修订任务及一个留出Shadow各4请求、结构通过。两条正常轨迹编译1个“写报告→检查”的局部候选，留出局部匹配1次，但回复含旁白，严格整请求0/4、实际跳过0。工具学习本身用了92请求；全轮新增代理估费0.089142美元，不能据此声称实际降本。见[实验与复现记录](docs/experiments/paper-rsi-tool-learning-20261011-v1.md)。
