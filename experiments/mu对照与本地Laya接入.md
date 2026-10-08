# mu 对照与本地 Laya 接入

> 2026-09-25。用户指定 `qybaihe/mu` 为重要对照，并允许本地部署 Laya。以下区分上游代码事实、SSS 本机实测和待验证假设。mu 冻结观察 commit：`8252cc6ed561e45ff658c9c89f134b9e90499bc8`，本机只读副本在被忽略的 `.local/mu-upstream/`。

mu 的 npm 基线另以 `mu-agent@0.1.4` 安装在 `.local/mu-baseline/`，本机 `mu doctor` 已运行：Node 22.22.3 和包完整；当前没有 mu 的生成模型登录、Jev key 或默认模型，因此**尚不能做付费的 mu 同题运行**。SSS 现有 DeepSeek Harness 凭证没有被复制到 mu。医生报告里“命令未在全局 PATH”只因刻意做本地隔离安装，执行可使用 `.local/mu-baseline/node_modules/.bin/mu`。正式基线要记录该发布包的实际版本与源码 commit 是否一致，不能混用开发分支代码和 0.1.4 的成绩。

## 1. mu 的实际设计

[mu README](https://github.com/qybaihe/mu) 和本机 `packages/kyrn-judge/src/` 显示：它是基于 pi 的通用编码 Agent，加了约 35 个有界判断点，涉及输入、上下文、工具、安全、完成与多 Agent 通信。每个判断点可设 `off`、`shadow`、`active`，并可选择 Jev、Laya、LLM 或级联；判断有账本。`tool.admission` 按块过滤工具输出，`context.forget`、`context.compact` 和 `cache.warming` 管模型上下文与缓存。`turn.completion` 检查收尾，`tool.risk` 等处理权限。它也有实际的 [Laya 本地后端与 37 条场景诊断](https://github.com/qybaihe/mu/blob/main/kyrn/docs/03-local-judge.md)，其中基础版 Laya 在复杂元判断上不稳。README 里的速度与节省数字是作者机器／会话的观察，尚不是我们同题复验后的端到端质量与成本结论。

mu 已覆盖“廉价判断器 + Agent”这条路线，SSS 不应复制它的判断点列表后声称创新。与 MotifAgent on SSS 的主要差别是控制粒度：mu 在**通用 Agent 的每轮／每次工具调用**上判断要让什么进入上下文、是否继续；SSS Motif 内核在**某类完整任务的跨步骤与跨版本执行**中持有证据、参数绑定、失效和恢复。这两个粒度可以叠加，但效果不必然正交：mu 的输出筛选可能改变 Motif 能看到的证据，Motif 的结构压缩也可能让 mu 的上下文判断没有发挥空间。

## 2. 要验证的三条路径

| 路径 | 具体执行 | 成立的证据 |
| --- | --- | --- |
| SSS 独立路径 | MotifAgent 管任务，DSH 提供受限生成模型调用，Laya／Jev 只判断有界缺口 | 在公开研究题与增量任务上，合格率不低于强基线，合格任务总成本／修订量更好 |
| mu 作为基线 | 原版 mu 按同样任务、来源、生成模型、权限和预算工作 | 真实运行日志与人工盲评；不能用 README 数字替代 |
| mu + SSS | 将科研交付／代码迁移 Motif 暴露为 mu 的工具或扩展；mu 管通用交互，Motif 管内部证据图与恢复 | 相比原版 mu，新增 Motif 后合格交付和增量更新指标改善；计算所有判断、模型和人工费用 |

mu 的扩展代码实际通过 `ExtensionAPI.registerTool` 注册工具；优先尝试把 SSS 作为独立工具进程接入，保持上游只读。若工具接口无法保存跨轮状态或让 mu 正确展示证据／费用，再评估扩展接口，最后才考虑 fork。对代码迁移也做同题比较：mu 独立改、SSS Motif 迁移、mu 调 SSS 工具。若 SSS 只在办公科研有效，就将产品定位收窄，不承诺通用编码 Agent 胜过 mu。

## 3. 本机 Laya 部署与真实运行

机器为 Apple Silicon、24 GB RAM。按 [Laya 官方仓库](https://github.com/NandhaKishorM/laya)安装 `laya[serve]==0.3.20` 到独立的 `.local/laya-venv/`，权重缓存在 `.local/laya-cache/`。本次下载的 Hugging Face `convaiinnovations/laya` revision 为 `55cf4c4ebb4ebe31b2550e8bdf3bd21b9975385`；本地多语言检查点已加载。环境约 915 MB，缓存约 647 MB。官方 PyTorch 推理后端在本机可用；与 mu 文档的第三方 Core ML 后端不是同一实现，不可直接拿延迟比较。

```bash
npm run laya:start
curl -fsS http://127.0.0.1:8766/health
.venv312/bin/python scripts/laya-shadow-dr3.py --out .local/laya-dr3-shadow-new.json
```

服务只绑定 `127.0.0.1:8766`，提供本地 `/v1/systemone`；启动脚本设置 Hugging Face 离线模式，本机重启后已用缓存权重完成一次推理。SSS 的 `src/adapters/laya_decision.py` 只允许本机地址，检查候选集合和概率，使用独立进程的 HTTP 接口，不把模型依赖装进主环境。服务关闭后可用同一命令重启。`laya-shadow-dr3.py` **只记录** 15 份公开资料摘录的判断，不用于删除或隐藏来源；输入取每份文件前 900 字符，结果在被忽略的 `.local/laya-dr3-shadow-20260925.json`。

两条手工控制输入的真实推理分别判为 `relevant`（3DGS 位姿重定位段落，选项概率 0.5482、模型 confidence 0.0067）和 `irrelevant`（MPEG-4 段落，选项概率 0.5976、confidence 0.0277）。15 份资料的 shadow 扫描中，Laya 将 `web-09` 的 RegGS 配准材料判成 `background`（概率 0.871）。该材料前 900 字符包含推送广告与论文信息；其标题及后文明确讨论 3DGS 配准。此例说明不能将 Laya 的选项概率当成来源排除的可靠阈值。这个扫描没有正式人工标签，不能报准确率；下一步应冻结逐项相关性标注、窗口与提示，再与 Jev／生成式模型／简单规则同题比较。

Laya 官方文档也说明：多语言检查点默认上下文 1024 token，长文档需显式扩大窗口；出厂概率未校准，基础检查点在领域任务上可能很弱。SSS 对中文资料应先切出有证据 ID 的候选摘要，在保留全部原始资料与回退路径的条件下做 shadow；只有本领域精度和阈值通过留出集，才允许参与自动路由。[官方模型与限制](https://github.com/NandhaKishorM/laya#honest-limits)

## 4. 公平比较与下一步验收

固定两类任务：① DR³-Eval `zh/003` 的有界研究报告，以及后续课题组真实资料更新；② 冻结仓库上的代码迁移测试。至少有普通脚本、DSH 原生 Agent、mu 原版、SSS Motif 和 mu+SSS；若 Laya 参与，再对同一结构分别做 `off`、`shadow`、`active`，不把 shadow 判断算成质量增益。各组公开同一来源、任务文字、生成模型、工具权限、最大预算、运行环境与人评 rubric。mu 的上下文压缩和 SSS 的证据图分别做消融，防止把缓存收益记到结构上。

主要指标：人工盲评合格率、每个合格交付的总成本、人工修订分钟数、端到端时延；增量任务另看旧结论失效、未变证据复用、错误引用与恢复失败。若 mu+SSS 优于 mu，说明 Motif 工作流可正交增强它；若仅独立 SSS 好，说明产品路径可能更适合领域工作台；若差异不显著，应报告无收益并缩小主张。

当前已完成的是 Motif 状态／证据内核在合成 A→B 任务上的真实运行、mu 源码核查、Laya 本地部署和 shadow 扫描。**尚未运行 mu 同题端到端对照，也未完成公开报告质量评测。**
