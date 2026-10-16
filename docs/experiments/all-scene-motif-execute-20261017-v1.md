# 三种网页场景默认 Execute 与思考开关

实验 ID：`all-scene-motif-execute-20261017-v1`。

## 目的与配置

用户要求 `/ppt`、`/data`、`/paper` 的 Motif 都实际执行。此前 PPT 与 Data 已有 Execute 库，Paper 产品默认仍是 Shadow；原私有 Paper Execute 库只覆盖结构化论文/参考文献路径，不能代替普通上传文档的读取认证。

本次基于 main `30b5a37423f4f2b5e1568dc44d8442610069dc0c`，不修改上游 Harness 或 Motif 核心。公共 Registry 将 Paper 默认改为 `paper-web-v1`，PPT 兼容包更新为 `ppt-web-v2-r7`，Data 保留原回执库。所有新默认对照的 Motif 为 Execute；旧 Shadow 证据与历史记录仍按原模式保存。无有效认证或未命中时由普通模型继续，不将回退计为优化成功。

真实采集通过网页后端原生任务 API 和 `session/prompt`；这是实际 HTTP/MCP/模型验收，不冒称浏览器人工点击测试。运行在隔离候选环境，模型由原共享费用代理记账，沿用原累计账本。每任务、每侧、累计费用、次数和输出配置均为 `null`，不重置历史；服务商原生容量边界继续存在。凭证、原始轨迹、私人服务器路径只留 `.local/`。

## On / Off 与 max

页面仍只有 Off / On，默认 Off。`harless_reasoning.ts` 与会话模型目录将 UI 可选项限制为 `off`、`high`：

| 页面 | Harness 配置 | DeepSeek 请求 |
| --- | --- | --- |
| Off | `reasoningEffort: off` | `thinking.type: disabled`，省略 `reasoning_effort` |
| On | `reasoningEffort: high` | `thinking.type: enabled`，`reasoning_effort: high` |

`max` 是模型 API 支持的思考强度，不是页面新增选项，也不是 DSH 的额外规划轮数。DSH 的同名配置是向提供商传递参数的适配层。思考强度、输出长度 `max_tokens`、Agent 工具循环与 RSI/Motif 开关含义不同。模型思考参数见 [DeepSeek 官方文档](https://api-docs.deepseek.com/guides/thinking_mode/)。本次没有添加 max 选项。

## 新 Paper 库的来源与边界

公开入口 `scripts/learn-web-paper-document-motif.py` 直接复用现有 `witnessed_edges` 挖掘器；契约来自真实 MCP 参数，不手填图。两个独立普通任务作为训练，一个不同任务作为留出，均使用 Flash / Off / Baseline。题目分别检查样本数算术、JSON 正文语法和 CSV 汇总一致性，保留合成来源声明。使用原始任务、有效配置、全部事件与精确 task ID 账本核对，公开证据只存摘要。

学习的唯一结构是 `pin_document → read_pinned_document`，把实际固定操作返回的 `source_id` 传给默认 `page: 1`。模型仍决定用哪个文件、是否继续读后续页以及如何校对；不跳过校对判断，不复用生成结论，不自动写用户原件。第一页默认值、完整 24 工具 Schema、来源版本、账号上传许可和代码/证书锁必须一致。在线通过已有 `closedContinuation` 接口授权这一固定只读续接，不扩展为任意工具执行。

最初在旧生产版本采集了四次任务，其中 JSON 一次直接使用已注入正文，没有形成工具边；其他三项形成了候选。但旧版读取工具说明与 main 的描述不同，严格 Schema 守卫拒绝认证。这四次及编译失败完整保留并计入 excluded 成本，未放松守卫或改写旧轨迹。随后在候选版本重新采集三个独立任务。

| 采集 | 真实请求 | 代理估费（USD） | 用途 |
| --- | ---: | ---: | --- |
| 旧版四次（包括无工具边的一次） | 20 | 0.010596192 | 排除，保留成本与反例 |
| 当前训练 A | 5 | 0.002604084 | 正常训练轨迹 |
| 当前训练 B | 5 | 0.002507148 | 独立训练轨迹 |
| 当前留出 C | 5 | 0.002641152 | 独立结构认证 |
| 采集合计 | 35 | 0.018348576 | 不含后续验收，账单实付未知 |

编译本身不调用模型。认证只证明结构与来源传递，不代表整份校对报告的科研质量、跨论文泛化或净成本收益。训练任务即便完成也可能触发普通导出或错误恢复，全部事件与费用保留，不能把筛出的读取边当作整个任务没有问题。

PPT r7 沿用 r6 的相同两项训练与一项留出证据、相同 library/manifest，不重新采样。实际 1–30 页 MCP Schema 与 r6 相同，只更新当前共享适配器兼容锁；编译零模型调用。原 r4/r5/r6 与 Legacy 证书保留。

## 验收记录

### 初次候选：八个真实任务

| 场景/模型 | 模式 | 请求 | total token | 验证跳过 | 工具错误 | 代理估费 USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Paper TXT Flash Off | Baseline | 5 | 49,330 | 0 | 0 | 0.00402827 |
| Paper TXT Flash Off | Execute | 3 | 30,595 | 1 | 0 | 0.00282822 |
| PPT Flash Off | Baseline | 6 | 87,111 | 0 | 0 | 0.00330966 |
| PPT Flash Off | Execute | 12 | 213,326 | 1 | 7 | 0.00839783 |
| Data Flash Off | Baseline | 20 | 410,460 | 0 | 0 | 0.01415416 |
| Data Flash Off | Execute | 6 | 105,331 | 10 | 0 | 0.00871775 |
| Paper PDF Pro On | Baseline | 5 | 48,650 | 0 | 0 | 0.02176205 |
| Paper PDF Pro On | 普通回退 | 6 | 64,700 | 0 | 1 | 0.02271949 |

八任务全部完成，63 请求、12 验证跳过、代理估费 $0.08591743。32 个文件经原鉴权路由下载，大小及 SHA 与回执逐一一致。PPT 两侧均 3 页可编辑 PPTX、3 页 PDF 及预览，notes 中两份 Word/PDF 标记均保留；Data 两侧报告均 2 页，有效 n=38、斜率约 0.844、R² 约 0.927 与小 p 值出现；Paper 两侧均保留合成限制和核验范围。PDF 文字无 U+FFFD 或 NUL，首屏渲染另行目视检查。数字存在只算初步核对，不能替代逐项科研审阅。

PPT Execute 有 7 次工具错误，最终修复交付，但请求、token 与费用都高于 Baseline；不得以一次读取跳过声称此任务降本。Paper 把 `data shows` 定性为确定语法错误，忽略现代单复数用法的风格差异，是内容质量负例。没有据此认证整体质量或收益。

独立复核发现 Windows 默认 CP936 读取含中文 Schema 会失败，已将共享 JSON 读取显式设为 UTF-8。同证据重新编译两份未发布候选的兼容证书，旧候选完整保存在私有归档；library、manifest、source-evidence 等结构不变，未再次采样。重编期间 Paper Pro On 的库锁不一致，按预期回退 `runtime_bundle_certification_invalid`；此行不计 Execute 成功，费用和 1 次错误保留。初次八任务属于首个候选的验收，最终认证冻结后须另作全模式预检及 Pro On 复测。

免费协议检查与真实模型生成、下载、内容检查分开记录。没有普通脚本对照或独立同质评审时，不依据 verified skip 宣称净收益。
