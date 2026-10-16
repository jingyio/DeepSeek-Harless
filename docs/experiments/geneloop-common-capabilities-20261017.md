# 全场景联网与代码执行验收

- 范围：按用户要求，对 Chat、PPT、Data、Paper 和注册的 Files 场景开放联网搜索、网页读取、命令行、通用代码及后台任务。合成能力验收，不是专业报告质量或 Motif 节省实验。
- 代码：基线 `30b5a3742`，分支 `codex/all-scene-web-execution`；最终版本以关联 PR 的合并 SHA 为准。未修改上游 Harness 核心。
- 环境：Linux、Node 22.23.3、项目 Python 3.10、锁定的 DSH npm 依赖。真实 DeepSeek Flash/Pro，Off/High；任务与累计费用、请求次数、主模型输出均无应用额度上限。搜索子请求使用原生 provider 的 `maxTokens=4096/maxUses=3`，不代表任务额度。服务商限制仍适用。

## 实现与调优

公共六工具 `web_search/web_fetch/bash/job_list/job_output/job_kill` 通过原生插件和生命周期接入全部产品场景。搜索经现有鉴权、任务路由和累计账本；Flash/Pro 使用实际选择的模型。当前服务提供 Bash、Python、Node；未安装或验证 PowerShell。

每条命令在会话专属 bubblewrap 中执行，输入只读、生成物写入 `outputs/code`，不给模型宿主凭证和其他会话目录。普通账号的外层隔离在旧内核上不能嵌套 user namespace，因此增加仅本账号可见的私有 Unix socket，由网关在外层建立同样的会话隔离命令进程。连接取消和网关退出会终止对应命令。网页进度显示搜索、阅读、执行命令和后台状态。

代码生成的 JSON、表格、文档等纳入有界、当轮、不可变交付快照，网页提供下载。Data 的专业报告仍需原交付认证；通用代码文件标为 `code-output-v1`，不冒充已通过专业统计报告审核。PPT R7 用同一批已冻结的两份训练证据和一份 held-out 证据重新编译、核对，适配新增公共工具与执行代码锁；不增加训练样本，也不宣称新的复用收益。R6 和更早版本保持。

## 真实模型结果

验收任务：搜索 Python 官方 JSON 文档，实际读取正文，计算 `[3,5,8,13]`，生成含 `sum=29/mean=7.25` 的 JSON；启动后台任务、读取真实标记、取消另一个长任务。自动检查六工具调用、工具错误、HTTP 200 正文、文件数值、后台输出和停止状态，不能只凭最终文字判通过。

普通账号最终验收：

| 场景 / 模式 | 模型 | 结果 | 秒 | 请求数 | 代理估计模型费用 USD |
| --- | --- | --- | ---: | ---: | ---: |
| Chat / shadow | Flash Off | 六工具、数值、输出、取消通过 | 22.56 | 8 | 0.008586 |
| PPT / shadow | Flash Off | 同上 | 21.15 | 6 | 0.007968 |
| Data / shadow | Flash Off | 同上 | 28.31 | 7 | 0.006588 |
| Paper / shadow | Flash Off | 同上 | 19.44 | 7 | 0.012810 |
| Files / shadow | Flash Off | 同上 | 24.25 | 7 | 0.009448 |
| PPT / execute | Flash Off | 同上，认证有效 | 24.49 | 7 | 0.009458 |
| Data / execute | Flash Off | 同上 | 26.27 | 6 | 0.006150 |
| Chat / baseline | Pro High | 同上 | 36.46 | 10 | 0.039209 |

独立实例另有五场景 Flash Off baseline、Chat Flash High、Pro Off/High 通过记录。所有最终样本工具错误为 0；这些公共工具不触发领域 Motif，`verified_skips=0`，不能据此声称优化节省。搜索服务附加费用未纳入模型 token 估费，实付账单未知。各样本缓存命中/未命中、输出 token、真实请求、耗时及初始失败费用保留在私有验收 JSON/账本，不将上述成功样本费用当作全部开发成本。

真实网页已操作 Chat、Data、PPT、Paper，观察实际执行及两侧文件。通过浏览器下载 PPT、Paper、Data JSON，读取下载内容均为正确数值。最终 PPT 再检查新 R7 无旧认证回退。账号间任务详情与下载采用同一 URL 对照：所属账号 200，另一账号 404。

## 失败与修正

- 初版缺少原生 shell 的 sandboxMode、旧任务 ID 兼容；修正后复测。
- 服务器旧 bubblewrap 不支持 `--clearenv`，改为 `env -i`；普通账号嵌套 user namespace 被内核拒绝，改私有账号命令代理，保留外层隔离。
- 成员 DNS 文件是符号链接，缺失最终只读目标；只挂载解析后的固定公共配置文件。
- 原生 owner 搜索缺少持久会话到当轮账本的路由，改走现有 broker；拒绝无拥有者、未提交、取消和跨账号请求。
- Data 文件已生成但被报告下载过滤器隐藏；增加独立代码文件标识及回归，不放宽专业认证。
- PPT 新代码使旧认证不兼容；用原证据重编译 R7。成员路径中的公开 config 代码锁也映射到 `/app/config`，不挂载整个配置目录。
- 网关重启时的 503、并发启动的 busy 不计成功，保留失败日志，服务 ready 后串行复测。
- 首次正式发布复核暴露最终请求校验漏测：原生搜索发送 Anthropic 文本块，而最后增加的严格校验只接受字符串。候选环境长期运行的预算进程未重载这次校验，单元夹具又只有字符串，导致候选真实调用通过但冷启动正式搜索返回 400。两端 provider 均为 `0.1.5-rc.3`、文件哈希相同，并非插件版本差异。补充严格文本块校验和回归（仍拒绝图片、未知字段、空数组和错误类型）；必须冷启动最终预算进程再验收，首次上线不算联网通过。

## 回归与复现

- 服务器 `npm test`：Python 819 passed / 193 skipped；Node 766 passed / 3 skipped。最后成员路径修正另跑网关 17 项全部通过。
- `npm run smoke`：18 个离线案例通过，模型请求 0。不是模型质量证据。
- 定向验证鉴权、取消、搜索请求格式、命令不含凭证/外部会话、原件只读、代码文件与专业报告区分；包括真实 Linux bubblewrap 和私有代理测试。
- `scripts/check-common-capabilities.py --run <private-output> --base <test-origin> --account-session <private-cookie-json> --mode shadow --real-model`；参数可选 `--scenes`、`--model`、`--reasoning`。真实调用在已授权服务器执行。
- 原始证据在服务器验证目录 `geneloop-capabilities-20261017/.local/capability-stage` 及关联成员任务目录，独立 run `68548557e0c246289fe9095e1e2932ac`。配置快照、事件、结果、原始日志、账户会话均不提交 Git。

发布保留原累计账本、账户、会话、附件、下载与回滚代码，只在无活动任务时切换；最终 CI、发布回执与上线复核以 PR 更新为准。未在本实验重新制作专业 PPT/论文/统计报告，不能把通用能力验收扩写成其专业质量认证。
