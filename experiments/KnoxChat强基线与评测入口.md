# KnoxChat 强基线与评测入口

> 2026-09-25。用户指定 [Open VSX 的 KnoxChat](https://open-vsx.org/extension/knoxchat/knoxchat) 为强基线。这里记录可核查能力和比较协议，不把上游宣传当成 SSS 已复验结果。

## 核实结果

Open VSX API 本次返回 `knoxchat/knoxchat` macOS arm64 版本 **1.5.2**，发布时间 2026-09-22，MIT 许可。本机 VS Code 1.138.0，高于其所列最低版本；Node 22.22.3 低于页面所列 Node 24.19.0，因此即使安装扩展，也必须先核实其打包运行时能否满足要求。发布仓库 [`knoxchat/knoxchat`](https://github.com/knoxchat/knoxchat) 自述仅用于发布，实际源码在 [`knoxchat/knoxcoder`](https://github.com/knoxchat/knoxcoder)。已将源码只读克隆到被忽略的 `.local/knoxcoder-upstream/`，观察 commit `1c0f1d0189fef8aaf323fe2357a03367a7344311`。**尚未证实该 commit 与 VSIX 1.5.2 精确对应。**

KnoxChat 的产品面比 SSS 当前原型完整得多：VS Code 内的 Agent、约 30 个内置工具、项目记忆、文件与记忆联动检查点、权限、并行只读工具、构建／诊断反馈和 `/autonomous`。源码的 `extensions/knox/core/agent/loop.ts` 确有共享 Agent 循环，包含工具批次、步数上限、重复循环停止和上下文整理；`core/eval/README.md` 说明其 CI golden 使用预先写好的模型工具调用来测工具／权限／中止路径，**不是实时模型在公开任务上的成功率证明**。官方列出的记忆和检查点细节见 [Open VSX 页面](https://open-vsx.org/extension/knoxchat/knoxchat)。

这使 KnoxChat 成为**代码迁移和真实同学试用**的强产品基线。它的记忆、检索、检查点与 SSS 的“减少重复上下文／恢复”目标有交叉；SSS 必须证明来源哈希、参数依赖、旧结论失效以及测试反馈形成的执行型 motif 在同任务中产生额外收益。Knox 的检查点能撤销文件，SSS 的证据依赖图要能精确指出哪些结论或补丁应失效；这是可测假设，不能仅凭设计图断言胜出。

## 同题实验

| 场景 | KnoxChat 原版要交付 | SSS Motif 要交付 | 主验收 |
| --- | --- | --- | --- |
| 冻结代码迁移 | 对旧接口的批量修改、测试与变更说明 | 相同仓库与需求的候选补丁、测试、依赖失效与恢复记录 | 测试通过、行为未退化、人工修订、总 token／费用／耗时 |
| 办公科研更新 | 给定资料与更正文件，建立对比简报并更新 | 相同输入下的来源台账、引文、报告与增量更新 | 人工盲评、旧结论失效、错误引用、合格交付成本 |

固定模型、API 计费方式、输入快照、任务说明、工具权限、预算和时间上限。Knox 是编辑器产品，SSS 目前是脚本：效率比较应同时报告**纯任务结果**与**同学实际操作时间／体验**，不能只比后台 token。代码迁移可先用独立仓库的冻结测试和行为 oracle；办公题先用 DR³-Eval 报告质量与 SSS 两阶段更新题，合成题只用于机制回归。除 Knox 原版与 SSS 独立路径，还可试 Knox 调用 SSS 的外部工作流，但要把接入和人工操作成本计入。

## 当前准备状态

源代码与发布页已核查；尚未运行 Knox 的实时模型任务。尝试下载 43 MB 的 macOS VSIX 时，当前镜像连接只有约 25 KB/s，已中止不完整下载，避免长时间占用；没有改动用户默认 VS Code 配置。后续先在隔离的 VS Code `--user-data-dir` 和 `--extensions-dir` 安装固定 VSIX，确认它能使用与其他基线相同的 DeepSeek 模型，再进行同题测试。其目前的公开 CI golden 可作为工具执行正确性的参考，不作为质量成绩。
