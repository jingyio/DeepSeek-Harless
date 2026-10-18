# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：基于最新 main 的独立 Script Motif 最小真实闭环：从 Bash/Python 轨迹参数化、沙箱认证、本地语义匹配、原生 Runtime 跳过请求、完成后自动学习/下一任务冻结版本，并用原始完整参考文献检查题面对照。不是生产发布，也未达到稳定降本。
- 分支 / commit / 工作区：`codex/paper-script-motif`，基线 `9f945a5`；本分支本地检查点保留代码/记录，未推送、未 PR、未合并。原桌面脏工作区和生产服务未修改。用户明确要求看到稳定效果后再决定 PR。
- 已完成：`script_motif_compiler.py` 从真实正常脚本推导路径参数与契约；`learn-script-motifs.py`/`certify-script-motifs.mjs` 重放来源及不同输入，保存拒绝原因、摘要和代码锁；`script_motif_runtime.ts` 用前驱/文件契约筛选、目标及前驱 embedding 排名、一次性 grant 和当前输入回执验证。语义分差不足、输入变更或回执不完整回退。
- 已完成：`script_motif_web.ts`/`script_motif_shell.ts` 和独立 `script-motif-web.py` 复用原生循环与命令执行器；`advance-script-motifs.py` 接完成事件自动发布私有不可变库。`run-script-motif-experiment.py` 提供统一原生 Web API 复现入口，`summarize-script-motif-run.py` 独立核算。新公开 runner 为本轮实际私有 runner 抽取，参数入口已验证，尚未另开付费全程验收。生产 Web/shell/Registry/认证库均保持原字节。
- 已验证：本地独立 Python 3.12.14/Node 22.22.3，最终 `npm test` Python **881 通过/199 跳过**、Node **850 通过/5 跳过**；`npm run smoke` 无模型通过。运行测试需指定项目 `SSS_PYTHON`、已审核 `HARLESS_REPORT_FONT`，macOS 使用 `TMPDIR=/private/tmp`。实际 OS 沙箱拒绝外部读、输入写和网络，回执执行/输入版本校验通过；注入相似度的单测仅作诊断。
- 实验结论：[paper-script-motif-20261018-v1](../experiments/paper-script-motif-20261018-v1.md)。真实轨迹自动发布 5 个算子，下一任务成功冻结并复用；最新完整原题 4 次验证跳过，但 **173 请求/$0.260957028/922.482 秒**，Baseline **88/$0.220640676/489.344 秒**。最新 Execute 最后输出达 8,000 Token 上限，仅留下占位 PDF；旧 Execute 也触顶且无 PDF，均不合格。Baseline/Shadow 仍有计数、编号和优先级问题，未盲评通过。不能声称净降本或跨论文泛化。
- 配置与数据：公共原题 `scenarios/paper-submission/reference-audit.prompt.md`；原生 30 项工具、同一题面/来源/渲染配置，`deepseek-flash/off`。实际 sidecar mode 独立于 native baseline/RSI off；Qwen3-Embedding-0.6B 本地 MPS，本轮阈值 `.5/.6/.04` 加三个负目标。私有根 `.local/script-motif-20261018-v1/`，原生日志 `.local/web/runs/<run-id>/`；完整 run/task-id、输入/模型/库摘要和失败在实验记录。私有自动库 `auto-library/round-68b12be9b79b4ac8b106808bf1c87d47`，摘要 `232503be043a77f882960f23dedc8b0f65c0cce5d9786b35a27addb020c7d3ea`。凭证只由私有环境加载，不提交。
- 未完成与阻塞：当前仅单条 Python 脚本，不覆盖任意 Bash/MCP DAG；一阶前驱和文件类型不足以判断必要工作，多个程序会重复检查。最新组 112 次 embedding 累计 107.035 秒；需要候选向量缓存和 Evidence 已完成判断。通用数字/正则参数、自动淘汰、复杂依赖图、worker 崩溃监控和 UI 计数未完成。原生 completed/PDF 存在未保证报告实际交付，长输出恢复未修复。未验证新实现的 Linux 真实执行或 Windows；本地 sandbox-exec 无 Linux 等价内存上限。
- 接手下一步：1）针对两次 max-tokens 失败，局部修复长输出恢复和内容交付门槛，再按同配置验收；2）为重叠脚本补 Evidence 输入/输出契约、去重与局部前驱图，避免已完成检查再次执行；3）在真正未见论文/普通文档上开展前瞻对照，包含学习/回退和人工修订成本，通过稳定门槛后由用户决定 PR。复现命令见 [接口](../interfaces.md#script-motif-实验接口)。
- 权限与预算：用户明确本地亦可真实测试；沿用无限额实验授权，单次输出 8,000，保留所有历史费用。本轮本地 **823 请求/$1.471504008 代理估费**，包含失败、重试与 3 次 usage 不完整的保守记账；不是账单。V100 隔离启动尝试后 SSH 持续断开，最终只读重试仍失败，远程状态/费用待核清，不能算 0。没有修改私人原件或投稿、外部写入、生产部署授权。
- 回退与风险：实验入口默认不启用；停止实验服务、使用原生 `harness-web.py` 即回到主线行为，已有库/用户文件不受影响。回退新代码至 `9f945a5` 时保留 `.local` 中全部轨迹、失败、账本和认证版本，不能重锁旧证书。当前实现仍为实验方案，不适合直接上线。

此前默认第一页读取 Motif 的自动学习历史保留在 [2026-10-17 验收](../experiments/web-paper-auto-learning-20261017-v1.md) 及 Git 历史；本轮 Script Motif 不改写其原结论，也不将旧测试当作新实现验证。
