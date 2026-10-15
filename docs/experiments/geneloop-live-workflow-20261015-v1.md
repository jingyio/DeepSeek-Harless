# GeneLoop 场景实时过程、回复操作与模型选择

## 问题、假设与范围

本轮处理普通聊天与场景双栏体验不一致：双栏缺少连续过程消息、轨迹和回复操作；会话长期保留默认标题；模型选择器和服务器实际允许的模型不一致。假设是复用原生模型流、工具事件与会话生命周期，在产品层保存和呈现真实事件，就能改善反馈及时性，并保留原对话、来源、评分及计费边界。若依赖模拟进度、丢失中间回复、分支混入另一侧回答、切换模型改变既有任务，均不满足要求。

这是产品交互与协议回归，确定性用例及目录发现不代表模型完成任务的质量，也不构成 Motif 降本效果证据。

## 有效配置与模型证据

- 分支 `codex/geneloop-live-workflow`；本机检查基线 `8004668913b813dc07d42994c1b2578d88611db6`，最终实现提交 `b58764c` 经 PR #30 合并为 `ce272476e0cd597e9d1e4f21ed5760c6e930f5bd` 并正式运行。检查环境 Windows、Node 24.16.0、Python 3.13.5，Harness 固定 `0.1.5-rc.3`，未修改上游包。
- 共享服务原每任务预算 0.23 美元保持，双栏每侧 0.115 美元；累计费用和请求次数不设上限，沿用原账本。`max_output_tokens: null` 继续省略请求的 `max_tokens`，不通过减少输出或重建预算使高费用模式获准。
- 2026-10-15 10:23:16 UTC 使用服务器已有凭据只读请求官方 `/models`，HTTP 200，返回且仅返回 `deepseek-flash` 与 `deepseek-v4-pro`。Flash 输入模态为文本/图片，Pro 为文本；两者目录所报上下文 1,048,576 token、最大输出 393,216 token。私有证据 `.local/geneloop-model-catalog-audit.json` 只保留公开能力字段，不含凭据；该操作模型请求数为 0。[官方模型目录接口](https://api-docs.deepseek.com/api/list-models/)
- 原生 adapter 的上下文、模态、系统提示更新行为及序列化能力直接保留；目录中可选模型取服务器已验证列表与当前已支持、已计价模型的交集。退役别名不再作为独立选项展示，未知模型不会自动开放。Flash 默认 Off，用户显式选择模型；双栏两侧冻结同一个模型与推理模式，不自动替换模型。

以下为本轮核对并与现有费用代理一致的价格，单位为美元/百万 token。费用代理按峰值预留及估费；离峰账单仍须按服务商实际账单核对。[官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)

| 模型 | 峰值缓存命中输入 | 峰值缓存未命中输入 | 峰值输出 | 离峰价格 |
| --- | ---: | ---: | ---: | --- |
| `deepseek-flash` | 0.006 | 0.30 | 1.20 | 对应峰值的一半 |
| `deepseek-v4-pro` | 0.044 | 1.32 | 3.96 | 对应峰值的一半 |

省略 `max_tokens` 时，官方 Off 默认输出预算为 8,192 token，On/`high` 为 65,536 token。Pro On 仅输出的预留费用即为 0.25952256 美元，已超过当前每任务 0.23 美元，故明确标注“On（当前预算不可用）”，选择或预览时说明原因，并提示先选择 Off；不产生模型请求，不默默改模式。Flash On/Off、Pro Off 可选；后续每次请求仍由原代理计算输入、输出和累计支出，长输入或后续轮次仍可能达到任务预算。[官方请求默认值](https://api-docs.deepseek.com/api/create-chat-completion/)

## 根因与实现

- 场景旧进度只保留最新 `answer` 与简短工具活动。后续模型步骤会覆盖早期说明，双栏主要依赖轮询读取快照。`harless_task_progress.ts` 新增按实际模型步骤保存的 `messages` 和 `trace`；`dsh_web_tasks.ts` 从真实增量通知订阅者，`harless_comparison.ts` 将每侧更新直接交给现有 SSE。轮询仍用于恢复和最终交付核对。推理只显示生命周期，不外发私有推理正文、工具参数或内部错误栈。
- 旧任务没有 `trace` 时，只在找到该任务精确请求事件后重建进度，避免已保存的工具活动与重放事件重复累加；找不到事件锚点则保留旧活动。恢复不改原始 journal、不重发模型请求，并排除锚点前其他任务的工具事件。
- 双栏组件显示真实消息、耗时及用量，提供各侧复制、反馈和分支；轨迹可按侧查看。服务端对反馈、分支继续校验会话所有权、侧别及输出摘要；所选一侧分支只继承相应回答和材料。只有已核验的模型请求跳过事件标注优化，候选与核验失败不能冒充节省。
- 浏览器分支验收曾失败：新分支挂载普通场景工具，却继承了数据场景限制。已改为从已登记场景创建独立 preset，并在私有分支记录保存 `mounted_scene`；后续场景选择与实际挂载分别维护，切换场景后冷恢复也不会限制不存在的工具。未知初始化错误只在私有诊断保留，用户收到可恢复提示。严格挂载工具回归覆盖普通、数据、论文、PPT；修复后实际 Motif 分支成功，手动改名刷新保持。失败编号和原诊断未清除，不将先前失败改记为成功。
- 上游原生模型目录包含更多历史别名，但旧产品 `policy.models` 只允许 Flash，造成展示与实际选择边界不一致。`harless_models.py` 在新真实启动前只读发现模型并生成配置、费用依据和不可用模式原因；`harless_reasoning.ts` 只筛选并标注原生目录，`dsh_web_tasks.ts` 在选择与任务预览时检查模式。旧运行配置须在部署时显式更新 owner 与 member policy，不能仅替换前端。
- 会话没有与实际用户主题绑定的本地标题规则。`geneloop_conversation_titles.ts` 从真实用户内容提取简短主题，不请求辅助模型；问候保持暂定名，出现实质任务后更新。同一工作区重名编号，手动名称和分支名称保留；旧默认名从可用历史恢复。独立审阅发现“你好，请介绍本项目的安装方式”会固定为“你好”，已补句首问候处理及回归。

## 已执行的确定性检查

| 检查 | 命令或记录 | 结果 |
| --- | --- | --- |
| 原生任务、场景连续路由、模型选择/推理与 provider 参数 | `node --test tests/test_dsh_web_tasks.mjs tests/test_harless_reasoning.mjs` | 54 通过 |
| 模型发现、费用预留、启动快照和既有启动边界 | `node scripts/project.mjs python -m pytest tests/test_harless_models.py tests/test_unlimited_output_budget.py tests/test_harness_web_public_origin.py tests/test_harless_product_prompt.py tests/test_web_request_limits.py -q` | 26 通过 |
| 本机全部 Node 用例 | `.local/live-workflow-node-all.log` | 648 项：631 通过、13 失败、4 跳过 |
| 纯代码用例补齐运行环境后的复核 | `.local/live-workflow-node-pure-code-recheck.log` | 1 通过 |
| Linux 完整 Python / Node 检查 | 隔离 stage 全量检查，后续新增回归另列 | Python 759 通过、193 跳过；Node 646 通过、3 跳过 |
| 取消状态及恢复 | Linux 定向 `tests/test_harless_task_progress.mjs` | 8 通过 |
| 自动标题及原生改名返回契约 | `tests/test_geneloop_conversation_titles.mjs` | 3 通过 |
| 旧任务进度恢复、无锚点保留、重复重启 | `node --test --test-name-pattern 'Legacy progress\|Task API exposes real text' tests/test_dsh_web_tasks.mjs` | Windows 4 通过 |
| 最终改动相关完整 Node 文件 | `.local/live-workflow-linux-final-related.log`，含分支四场景挂载/冷恢复、标题、旧进度、过程下载 | Linux 143 通过，0 失败/跳过 |

全部 Node 失败中，12 项在创建符号链接时遇到 Windows `EPERM`；另一项未配置 `SSS_PURE_CODE_PYTHON`，指定本机现有 Python 后单独复核通过。这与上一轮记录的本机环境限制一致；没有为取得通过而删除或改写这些安全检查。本机整套不能记为通过。Linux 完整检查及其后增加的定向用例按上表分别记录；最终四项 Windows/Linux CI 全通过，TypeScript 模块自动识别警告仍存在。

模型诊断使用安装的真实 adapter 对本机 HTTP 接收器验证 Flash Off/On、Pro Off 的线路和 `thinking`/`reasoning_effort`，确认 `stream: true` 且不发送 `max_tokens`；这属于零付费请求契约检查。费用测试验证 Pro Off 可在两个独立 0.115 美元 lane 中各预留一次，Pro On 在 0.23 美元任务中拒绝且请求数不增加；不代表长输入或无限轮次均可在该预算内完成。

## 真实 stage 验收

隔离 stage 使用真实模型完成一轮 Pro Off 普通聊天及一轮 Flash Off 数据报告双栏。每任务仍为 0.23 美元，双栏每侧 0.115 美元，未扩大费用边界；未发送 `max_tokens`。下列费用为代理记录的估费，实付仍需服务商账单核对，token 为模型输入加输出总量。

| 任务 / 侧别 | 实际模型与模式 | 模型请求 | 工具调用 | 助手消息 | 总 token | 耗时 | 代理估费（美元） | 已验证跳过 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 普通聊天 | `deepseek-v4-pro` / Off | 1 | — | — | 1,111 | 7.1 秒 | 0.00167244 | — |
| 数据报告 Baseline | `deepseek-flash` / Off | 16 | 15 | 13 | 201,300 | 40.183 秒 | 0.009210264 | 0 |
| 数据报告 Motif | `deepseek-flash` / Off | 7 | 16 | 7 | 83,262 | 33.308 秒 | 0.007335108 | 10 |
| 同对话转 PPT 讨论 Baseline | `deepseek-flash` / On | 1 | 0 | 1 | 11,126 | 4.767 秒 | 0.003735600 | 0 |
| 同对话转 PPT 讨论 Motif | `deepseek-flash` / On | 1 | 0 | 1 | 11,413 | 4.245 秒 | 0.001341192 | 0 |

两侧均交付一页 PDF 报告和 3 份图文件，8 份产物全部实际下载并验证 SHA。SSE 在两侧各自完成前均出现多次不同文本；浏览器观察到生成中多段说明持续保留。私有验收汇总在 stage 的 `.local/paired-stage/live-workflow-results.json`，只读复验入口为 `.local/verify-live-workflow-results.py`，复验本身不发模型请求。

本轮记录的是任务运行、流式变化、可下载交付和摘要完整性，尚未进行独立盲评，报告科研质量未评审。表中请求、token、耗时与费用差异仅属于这一次验收，不能推广为普遍成本或性能收益；工具次数不同也不能直接解释为质量差异。缓存命中/未命中和输出细分保留在私有逐请求账本，本表不以总 token 推算费用。

浏览器将同一父对话从 `/data` 切换到 `/ppt` 并开启 Flash On，要求只讨论三页汇报结构，不生成文件或调用工具。两侧各一次真实请求完成，均保留实际思考状态，父会话与此前交付仍在。该轮没有伪造文件产出；私有快照为 `.local/paired-stage/live-workflow-flash-on-result.json`。

上述 stage 验收共 26 次真实请求、代理估费 0.023294604 美元；原共享账本累计 825 次请求、代理估费 0.571919058 美元，未重置。累计值包含历史消费，不能当作本轮消费；正式切换前后仍需复核原预算进程与账本。

## CI 与正式部署

[PR #30](https://github.com/jingyio/DeepSeek-Harless/pull/30) 已合并，正式运行 `ce272476e0cd597e9d1e4f21ed5760c6e930f5bd`。[分支 CI](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38723138792) 与 [PR CI](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38723194974) 的 Windows/Linux 共四项全部通过。

切换前确认 66 个既有任务均非运行态；停止服务后记录并逐项核验 5,927 个受保护目录/文件/链接条目，再启动新版本。仅修改 owner/member 两处模型目录；旧 preset、MCP、启动规格及预算进程保持。上线后只读复核通过：3 个账户、20 份对照评分、112 份 preset、253 个不可变文件，另按历史迁移清单核验 16 份来源和 234 份产物摘要；7 份原 PPT preset 的 initialize/list 通过且无工具调用。新前端实际组合资源包含精确版本代码，原生目录返回 Flash/Pro 及正确推理档位，登录页 HTTP 200。预算进程未重启，复核前后仍为 825 请求/代理估费 0.571919058 美元。

私有发布收据位于 `live-workflow-hotfixes/20261015T105742Z-ce272476e0cd-5869ecde/receipt.json`；只读复核为 `postdeploy-live-workflow-acceptance-ce272476e0cd-20261015T105914Z-2e62eb62.json`。部署与复核新增模型请求 0。原始用户数据和日志不回滚、不替换。

## 结论与边界

确定性检查支持目录与选择一致、正确的原生请求契约、Pro Off 预算兼容，以及真实事件驱动的消息/轨迹保存机制。真实 stage 验收补充验证 Pro Off 可完成请求、Flash Off 数据报告两侧可以持续流式展示并交付文件、同对话 Flash On 跨场景讨论及分支可用；正式代码、配置和数据保留已按上述只读复核确认。Pro On 继续受当前任务预算限制；不得为开放选项扩大预算、偷偷截断输出或循环新建任务。

回退只恢复应用代码和对应配置，不回滚会话、来源、交付、评分或累计费用记录。原预算服务已包含两种模型定价，开放 Pro 不要求重启或重置预算服务。
