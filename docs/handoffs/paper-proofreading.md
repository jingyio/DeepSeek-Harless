# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：按用户要求找回此前真实论文任务，先测论文效果，推迟其他场景扩展；完成三组完整任务与两组独立计量的历史恢复。没有修改在线机制或旧认证库。
- 分支 / commit / 工作区：独立 `codex/paper-negative-real-eval`，Runtime 冻结 `8fa7f23c8affb18c2b16caf2f1948acc16f8cd9f`；报告与离线分析修订见本地 git log。未推送、PR 或部署，原脏工作区、生产、私人原件未改。
- 已完成：沿用原 `reference-audit.prompt.md` 与 RMSNorm 源码；Baseline / Positive / Positive+Negative 从原件新执行，恢复对照复制真实历史失败草稿，不做故障注入。已知论文参与历史训练，不是独立论文泛化。
- 已完成：离线 `analyze-script-motif-cost.py` 补记 `finalized:false` 等结构化软拒绝与批量 bibliography 暂存边界，和原生异常分列；不改 Runtime、提示或工具 schema。原始 summary 保持不改，最终质量结论另存。
- 已验证：五项真实 DeepSeek Flash/off 原生完成，usage 完整、新 pending/未知均 0；端口 3240–3244 已关闭。最终版本 PDF 全页渲染并只读检查，三组均未通过，未做独立人工盲评。分析器针对性 8 项测试通过；本轮未重复全部回归。冻结机制上轮 927 Python/887 Node 与 smoke 通过，仍仅是诊断。
- 实验结论：[paper-negative-real-20261019-v1](../experiments/paper-negative-real-20261019-v1.md)。完整 Baseline 130/$0.156665400、Positive 162/$0.254353860、正负面 93/$0.142988208。正负面账面低 8.7%，但三组报告均不合格且负面事件为 0，不能归因或声称同质量净降本。正面两组各真实跳过 2 次请求，未覆盖后续脚本/报告/恢复。
- 实验结论：Baseline/正负面通用导出绕过结构验收且存在计数/编号错误；Positive 17 次结构软失败后回退通用报告。恢复 Baseline 49/$0.030089196、Negative-only 14/$0.009216252；后者实际提示 1、硬早停 0，两组都未成功定稿。前者 6 次重复 ID 失败跨 5 个版本，不能依靠原样重试识别；该单对只支持继续检验提示减少无效恢复。
- 配置与数据：`.local/paper-negative-real-20261019-v1/` 保存授权、有效配置、runs、五组 summary/breakdown、quality-review、aggregate、final-state、全部中间稿/渲染。原生轨迹/账本在 `.local/web/runs/<run-id>/tasks/`，逐运行 source-snapshot 在 `.local/script-motif-experiments/<run-id>/`。题面/来源/工具/库 SHA 和复现命令见实验记录；凭证仅由私有环境加载，未展示。
- 配置与数据：沿用 `.local/negative-causes-20261019-v1/positive-library-002` 与 `library-004`，digest 分别 `111bbbd765b47f0bb4c2a8ca7d2106acab1fb5202923840254b88db427897ac8`、`08becf591624e9fd2a92222604e5aac6ddfe373d1cef83ea2ede53e85822895c`。冻结库，无本轮学习调用。编译器 v2、原因双向干预、2 类真实认证与其余合成诊断边界见[原因学习记录](../experiments/paper-negative-causes-20261019-v1.md)。
- 未完成与阻塞：没有合格净降本、成功自动恢复、真实硬早停或独立新论文泛化。当前草稿读取/替换修复协议不足；不同导出路径门槛不一；确定性计数、原编号与最终版本缺少统一来源。不能用最终有 PDF 或原生 completed 代替验收。
- 接手下一步：1）支持当前未定稿状态读取与按 SHA 有界修复，先使自然失败恢复成功。2）所有报告出口共用原编号/身份、计数和来源版本验证，语义判断仍由模型负责。3）再做独立论文多次配对，区分 Prompt/Enforce、脚本复用与真正整请求跳过，用户认可稳定效果后再决定 PR。
- 最短复现：`.venv-sss/bin/python -m pytest -q tests/test_script_cost_breakdown.py`；真实统一入口 `node scripts/project.mjs python scripts/run-script-motif-experiment.py --real-model ...`，完整参数见实验记录。当前本地使用 TMPDIR=/private/tmp、SSS_LOCAL_SCRIPT_EXPERIMENT=1 和私有字体/renderer；这不代表生产或 Windows 验收。
- 权限与预算：用户允许本地真实 API 无限额，`cap_usd:null/reset_history:false`。本轮新增 448 请求/$0.593312916，累计本地 3283/$5.307766608 保守估费；旧 pending 1 与 V100 未核清费用保留，不是账单实付。本轮无后台付费任务、无新学习请求；开发/审阅时间未完整计量。
- 回退与风险：本轮仅离线分析与文档，可按提交单独回退；关闭 negativeLibrary 停用负面机制。Runtime/协议后续改动仍须重编认证，不改旧锁、不删除私有失败记录，不扩大外部写入或投稿授权。

前轮：[多错误原因学习](../experiments/paper-negative-causes-20261019-v1.md)、[字段依赖](../experiments/paper-negative-fields-20261019-v1.md)、[负面提示](../experiments/paper-negative-motifs-20261019-v1.md)、[连续执行](../experiments/paper-script-frontier-20261019-v1.md)。
