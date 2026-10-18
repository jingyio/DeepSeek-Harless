# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：第二轮 Script Motif 实际降本瓶颈改进。复盘上一轮四个完整任务，在两篇未见论文上完成 Baseline/普通脚本 Cache/完整 Execute，并保留协议修复前后 8 次运行。没有达到稳定降本或合格交付。
- 分支 / commit / 工作区：独立 worktree 的 `codex/paper-script-evidence`，基线 `7e42588d00481d2faeff4a41a0516e8468a0b14a`；本文件随第二轮实现本地提交（具体提交见 `git log -1`），不推送、不提 PR、不合并。桌面原脏工作区、生产入口/认证库未改。用户要求稳定效果后再决定 PR。
- 已完成：Python 编译器识别保存 `.py`、后续调用和 `sys.argv`；保留真实来源/输入版本/拒绝记录。`certify-script-motifs.mjs` 用实际不同参数及新 HTTP 证据认证。7 个算子：6 本地、1 arXiv；不是任意 Bash 管道工具化。
- 已完成：`run-certified-script.mjs`/`fetch-script-evidence.py` 在可信固定 arXiv/Crossref GET 边界取新证据，再送入禁网只读沙箱；不复用历史输出。原有 Bash 提供缓存目录和批次执行，不加工具 schema。Runtime 支持已验证前驱文件参数流、需求前驱、原子回执、受限 cd 前缀和管道拒绝提示；当前标量/网络对象仍由模型选择。向量缓存只缓存 embedding，不缓存决策。
- 已完成：`analyze-script-motif-cost.py` 按完整真实请求归因，区分代码生成、已有脚本调度、搜索内部模型、报告阶段和错误恢复线索。独立 wrapper 统一三组实际输出上限 32,768，公共 `harness-web.py` 恢复原字节，未重锁生产证书。
- 已验证：Python 3.12.14 / Node 22.22.3 / Harness 0.1.5-rc.3；最终 `npm test` **898 Python 通过/199 跳过、854 Node 通过/5 跳过**。随后仅离线分类器调整，针对性 **4 通过**；`npm run smoke` 无模型通过。实际沙箱、HTTP 哈希、批次原子性、native Shell bridge、cd/head 反馈及不同文件绑定均有针对性诊断；不能把诊断 continuation=0 当付费任务跳过。
- 实验结论：[paper-script-evidence-20261019-v1](../experiments/paper-script-evidence-20261019-v1.md)。RMSNorm Baseline **113/$0.140660412/630.098 秒**；修复后 Cache **103/$0.155966208/313.740 秒**，2 次真实新参数网络脚本复用、0 自动请求跳过；Execute **113/$0.163707156/772.177 秒**，0 复用/跳过。Cache 请求 -8.85% 但费用 +10.88%；Execute 费用 +16.38%。GELU、RMSNorm v2 负面结果完整保留。八份交付都有计数/编号/版本/交付问题，没有独立人工盲评，不支持同质量降本。
- 核心证据：v2 Execute 曾主动选择缓存，但 `cd ... && geneloop-cache ... | head` 没进入旧缓存执行器，后来已修复。v3 Execute 未主动选择缓存，因此结构资格未达到、0 embedding，不是相似度阈值拒绝。最差 v2 执行开始报告后还有 314 请求/$0.47636604，占总费约 92%，含补检，不等于纯排版。报告恢复与语义参数选择成为主要剩余成本；只增局部读算子不足。
- 配置与数据：公共原题 `scenarios/paper-submission/reference-audit.prompt.md` 未变，SHA256 `6199102371fc38c05912b76596bb6c48cbde4ee1eb157bafe0cae4eae0de4a89`。真实 `deepseek-flash/off`、30 工具、native baseline/RSI off，sidecar 决定实验组。Qwen3-Embedding-0.6B 本地 MPS；私有阈值 `.5/.6/.04` 沿用，不降阈值。最终库 `.local/script-evidence-20261019-v1/library-frozen-003/library.json` 摘要 `c517d8d859ad4b8160fc75c84868711dda1a0d76b5b2cd79edfed63f8f472c4a`；实际配置、源码快照和账本在 `.local/script-motif-experiments/<run-id>/`、`.local/web/runs/<run-id>/tasks/<task-id>/`；run/task 表在实验记录。凭证只经私有环境加载。
- 学习成本：历史训练及留出共 136 请求/$0.282083184，已在上一轮总账；本轮学习没有新增 LLM 请求，计时的 v2 学习认证 5.24 秒，包含 4 HTTP 获取。其他开发重认证、机器/安装/人工成本未完整计时，不算零。新评测轨迹未训练冻结库。
- 未完成与阻塞：未实现净降本；需求前驱需模型先选缓存、标量/网络目标不能从 Evidence 自动流入，导致完整请求替代入口不足。库覆盖很窄，不支持任意 Bash/网络/写报告脚本；仍无完整任务进度和证据覆盖图。平台报告和最终回复不同版本、摘要与逐条计数矛盾仍存在。没有新 Linux/Windows 真实验收。远程 V100 旧状态/费用未核清。
- 接手下一步：1）将模型确认的检查计划/对象集合转成有类型 Evidence，自动挖掘的程序绑定字段并运行已授权只读批次，验证完整请求替代及语义交接；2）复用现有 renderer，把审计数据、确定性渲染与导出拆开，强制编号/计数/实际文件版本一致，作为普通工程基线单列；3）以上局部通过后做独立论文重复前瞻对照与人工盲评，包含学习/恢复成本，通过后由用户决定 PR。不要再靠降阈值或重复同一题挑便宜样本。
- 最短复现：安装锁定依赖、私有 API/renderer/font、启动本地 embedding 后，`node scripts/project.mjs python scripts/run-script-motif-experiment.py --real-model --source /path/source.zip --mode execute --script-config /path/execute-v3.json --budget-usd 0 --max-output-tokens 32768`。仅已有无限额授权使用 0；macOS 显式 `SSS_LOCAL_SCRIPT_EXPERIMENT=1`、`SSS_PYTHON`、`TMPDIR=/private/tmp`。完整三臂命令见[接口](../interfaces.md#配置与真实复现)。旧版本复现用对应源快照，不能改库锁。
- 权限与预算：用户已允许本地真实测试，费用/请求不限；单次输出 32,768。本轮 **1,274 请求/$1.739342400**，全部本轮任务 pending=0/unknown usage=0；两轮本地共 **2,097/$3.210846408**，含上一轮 3 次 usage 不完整的保守估计。全部为代理估费、非账单；不是账户总额，远程未知不算 0。没有改私人原件、投稿、外部应用写入或生产部署。
- 回退与风险：停止本轮独立实验进程，使用公共 `harness-web.py` 即回到原生行为；代码回退到 `7e42588` 可恢复上一轮，不删除 `.local`、旧认证库/失败/账本。macOS 使用 sandbox-exec，无 Linux 等价内存上限。结果尚不足直接上线。

上一轮记录：[paper-script-motif-20261018-v1](../experiments/paper-script-motif-20261018-v1.md)。此前自动学习历史见 [2026-10-17 验收](../experiments/web-paper-auto-learning-20261017-v1.md)；不改写旧结论、不将其当新实现效果。
