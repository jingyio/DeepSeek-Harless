# GeneLoop 产品身份、消息隐私与过程折叠

## 问题与范围

用户要求普通聊天默认显示最终回答，点击工具调用才展开上下文、工具和早期消息；内部插件标识与服务器目录不应出现在用户界面。原生 Compact 在执行中和部分历史分页条件下强制展开，因此仅修改默认偏好不能满足该要求。另一条问题链是新旧 Web 会话仍可通过默认系统身份、运行环境、工具结果、历史读取或传输错误展示底层框架及部署信息。

本轮假设：保留原生执行与消息流，在 Web 提示绑定、公开输出投影和公开聊天插槽三个位置处理，可以统一新旧会话的产品呈现，且不破坏流式、文件、分支及原始证据。若最终回复丢失/重复、重连游标改变、用户原文或文件字节被改写、旧会话不能继续，均视为不满足要求。

## 配置与实现

- 工作分支：`codex/geneloop-message-privacy`，实现 `c52fa444e9f68d756c2a6eb3359b4343543dd78a` 经 [PR #29](https://github.com/jingyio/DeepSeek-Harless/pull/29) 合并为 `926704c64dc27cddd0284bf64632b033da66b369`。正式运行该合并提交，合并树与验收实现树相同；发布记录的后续文档提交不需重启运行代码。
- 本节确定性检查环境：Windows，Node 24.16.0，Python 3.13.5；无模型调用。Harness 保持固定 `0.1.5-rc.3`，新增直接依赖 `ws@8.21.3`。真实验收实际模型、Off、输入摘要和私有记录标识见后文；未重复做前一轮已通过的 On 模型行为测试，正式原生模型目录 On/Off 均复核通过。
- `config/geneloop-persona.json` 供 Python Web 启动器、场景 registry 与 TypeScript preset 共用。`bindProductPrompt` 通过公开系统提示 section 和运行环境抑制接口应用于新建及恢复 Agent；原场景提示、工具 schema、证据规则及权限继续有效。研究入口仅在显式 `web_deployment=True` 时采用产品提示，默认研究 CLI 不变。
- `harless_public_output.ts` 返回独立的浏览器展示对象，处理新旧消息的读取、实时帧、恢复快照、任务/对照视图与相关元信息。已知框架名称统一为 GeneLoop，常见内部绝对路径隐藏，系统提示只保留设置通知。原始 journal、执行 inspect、用户来源消息、用户排队输入和文件字节不改写；事件/游标、评分身份及下载回执保持。
- `harless_public_transport.mjs` 处理原生 RPC 失败和 WS mux 错误/指定事件元信息。成功请求数据、二进制与无关流不做文本替换；文件/SSE 不进入 unary JSON 缓存投影。错误给出用户提示，内部 details、host home 与新增会话 cwd 不直接外发。
- `harless_web_client/client.js` 只覆盖公开 chat node 插槽；默认最终回答，生成中保留当前真实增量和状态，过程按钮可反复开关。最终文字复用原生 assistant renderer，图片/授权文件入口及原生 turn-tail 复制、分支等操作保留。trace 目标和上游源码未改。Baseline / Motif 为展示名称，Shadow 另显示“影子评估”。
- PPT `runtime-bindings.json` 仅更新共享 task scope 的产品身份代码 SHA，`entry.json` 随之更新登记摘要。原学习边、来源所有权/摘要、job、参数、完整工具 schema 和训练证书不变，不进行新训练，不新增质量/收益主张。

## 已验证的定向检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 普通聊天、双栏、品牌 | `node --test tests/test_geneloop_chat_presentation.mjs tests/test_harless_paired_client.mjs tests/test_geneloop_brand.mjs` | 39 通过 |
| 产品身份、公开输出与传输 | `node --test tests/test_harless_product_prompt.mjs tests/test_harless_public_output.mjs tests/test_harless_public_output_review.mjs tests/test_harless_public_transport.mjs` | 21 通过 |
| Python 产品配置及 Web/研究入口边界 | `python -m pytest -q tests/test_harless_product_prompt.py` | 4 通过 |
| 补丁格式 | `git diff --check` | 无错误 |

聊天组件检查覆盖默认折叠、反复展开、真实 delta 更新、推理与正文分离、会话切换、历史中断，以及原生 Compact 的外层回答边界；实际浏览器对样式、模块装配和交互的后续验收见下一节。公开输出检查覆盖路径/产品名任意分帧、断线恢复、事件序号与下载标识、用户消息/文件不变、旧会话绑定和作用域释放。传输单元检查覆盖错误 envelope、指定 WS 事件以及不相关成功流不变，不能代替实际网络连接验收。

Node 检查输出了现有 TypeScript 模块类型自动识别警告，进程均成功退出；未为消除警告调整仓库模块模式。

## 真实、浏览器及发布验收

- Linux Node 22.23.3 / Python 3.10，`npm test`：Python 755 通过、193 条件跳过；初次 Node 622 通过、3 跳过。补完独立边界回归及 gateway persona 后，完整 Node 629 通过、3 跳过。最终本机 75 项前端/输出/传输/gateway 定向检查通过。此前直接在 Windows 执行完整 Node 的 13 个失败为 12 个 symlink EPERM 与 1 个未提供纯代码 Python 环境的旧用例；Linux 同用例通过，未删改这些检查。CI 结果发布时补记。
- 实际浏览器：普通会话真实 `list_files` 一次后默认显示最终答复；过程按钮展开显示“查看文件”及真实空列表，第二次点击收起；复制得到完整 Markdown；刷新、重新打开同一历史会话仍默认折叠且回答完整。截图 `.local/geneloop-private-chat-verified.png`。首次 AX 编辑器填值误发 `gge`，保留原记录，随后改用编辑器语义填值并检查内容再发送，不冒充计划中的用例。
- 普通聊天后续提问明确要求查看上传文件、介绍身份与说明部署位置。模型回答自称 GeneLoop，没有披露服务器目录；两轮 UI 显示共 3 个模型步骤、约 3.6K token。这仅验证本次输出，不代表任意提问都可依赖提示词阻止泄漏，因此另有公开投影与任意分片回归。
- `/data` 真实双栏方法讨论：`deepseek-official/deepseek-flash`、Off、每侧 0.115 美元；`max_output_tokens=null` 且不发送 `max_tokens`。两侧各 1 请求、0 工具，均完成且自称 GeneLoop；Baseline 在结束前观察到 9 个不同正文长度（51–758 字符），Motif 7 个（37–618），最终分别 786/739 字符。SSE 与独立 GET 身份一致，约 15.9 秒观察窗口无错误。输入 SHA256 `ad23ab2d96f1904e9cb503eb8c44f5543071ec7aa810fb00aee2f1be6eb40c78`，私有证据 `message-privacy-data-real.json`、`message-privacy-data-stream.json`。
- 数据双栏 token：输入各 4387，缓存命中 256/4224，输出 453/425；代理估费分别 0.001784436/0.000584244 美元，合计 0.00236868 美元，非账单实付。验收后共享累计 798 请求、估费 0.548247474 美元；共享账本含其他历史与可能并行活动，不能将总量变化都归为本轮。
- 发布：PR/分支四项 Windows/Linux CI 全部通过（`npm test`、smoke、motif:check）。部署前 65 个任务空闲；运行切换只重启应用，原预算进程与历史收据保持。正式只读复核验证 112 份既有 preset 仅修改 persona 配置，MCP 绑定完整；3 个账号、16 份旧来源与 234 份成品 SHA 保持，2 个可访问旧对照的终态/评分匹配，7 份旧 PPT preset 实际 initialize/list 成功且 job/checkpoint 不变，65 个 PPT 代码锁通过。验证不调用模型或工具执行。
- 公网浏览器登录页正常，站点品牌 GeneLoop；登录后的交互验收在隔离 stage 完成，未修改生产账号或凭据。正式预算进程签名保持，复核前后均为 799 请求、估费 0.548624454 美元。私有收据：`message-privacy-hotfixes/20261015T100450Z-926704c64dc2-71171aea/receipt.json`、`postdeploy-message-privacy-acceptance-926704c64dc2-20261015T100722Z-b598a992.json`；运行入口 `current-runtime.json`。26 个 stage 任务均已结束后停止测试服务、关闭临时浏览器及 SSH 转发，私有证据保留。

## 已发现的边界与回退

- 原生 Compact 可能把一个未知非文本 assistant block 视为最后回答，若只按文本选择承载节点，较早文字会被原生外层隐藏。当前使用公开 `turnProcess.spec.answerStep` 选择承载节点，文字仍取最后可见回答，并补回归；回合状态统一读取公开 timeline，避免旧节点位置状态造成重复显示。
- 输出过滤处理已知框架标识和路径形式，不是任意敏感信息识别器；产品提示也不替代真实工具权限、来源校验或账号隔离。模型的科研内容、统计质量及普遍成本收益不属于本轮已验证结论。
- 工作区继续按不透明 ID 和 sessionIds 分组，不依赖公开 cwd。模型/供应商名称保持真实，协议 ID、来源/许可证、上游包名不为展示更名而改动。
- 回退只能恢复应用入口、代码及相应配置；不得回滚用户 journal、附件、交付、评分、账号或累计账本。回退目标为此前运行的 `3bb96877f246aa418d5faf4b1577973cfa12e072`，对应新切换收据的 `backup/previous-runtime.json`；本次成功，未发生回退。
