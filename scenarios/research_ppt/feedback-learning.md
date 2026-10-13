# 用户反馈与离线改进

本模块让部署后的真实使用留下可审计的数据，并管理待学习队列、候选版本和回滚。它复用已有 Motif 编译器，不启动新的 Agent 循环、不调用云模型，也不在每次制作 PPT 时生成工具。**它不是完全自主的自进化服务，尚未证明部署后稳定降本。**

## 用户使用时

前台入口显式取得收集许可后调用 `FeedbackStore.collect(record)`。默认只收集，`consent.learn=false`；科学和视觉质量在用户审阅前为 `pending`。采集失败必须保存错误并继续交付，不能因此丢失已生成的 PPT。

私有记录只放在 `.local/`。包含匿名来源 ID/哈希、任务与双组配对 ID、实际模型/工具/提示/模板/实现版本、请求数、缓存命中/未命中输入和输出 token、代理估费/账单/恢复费用/耗时、质量、人工修订分钟和文字反馈。未知费用明确为 `null`，不默认为零。不要在反馈中粘贴密钥、论文正文或个人资料。

同一 `run_id` 的反馈更新追加一个不可变修订，旧反馈保留；任务、来源、组别、配置和候选版本不能追改。运行失败、质量失败、尚未审阅和优化组轨迹都保留用于诊断；不会自动变成训练成功案例。

```sh
python -m scenarios.research_ppt.feedback_learning \
  --store .local/research-ppt/feedback collect --record .local/research-ppt/TRIAL/baseline-feedback.json
python -m scenarios.research_ppt.feedback_learning \
  --store .local/research-ppt/feedback queue
```

记录的最小结构如下；这是字段示意，哈希、版本、数字必须由入口的实际快照/账本填充：

```json
{
  "schema_version": 1,
  "run_id": "实际运行ID", "task_identity": "稳定独立任务ID", "pair_id": "双组共同ID",
  "group": "baseline", "consent": {"collect": true, "learn": false},
  "source_evidence": [{"source_id": "匿名来源ID", "sha256": "实际64位哈希"}],
  "versions": {"model": "实际模型", "provider": "实际端口", "reasoning_effort": "off",
    "tool_schema_sha256": null, "prompt_sha256": null, "prompt_prefix_sha256": null,
    "template_sha256": null, "runtime_sha256": null},
  "execution_strategy": "steps", "shared_prompt_sha256": null,
  "quality": {"delivery": "passed", "scientific": "pending", "visual": "pending",
    "reviewer": "unreviewed", "revision_minutes": null},
  "cost": {"requests": null, "cache_hit_input_tokens": null, "cache_miss_input_tokens": null,
    "output_tokens": null, "proxy_usd": null, "billed_usd": null, "recovery_usd": null, "elapsed_seconds": null},
  "run_dir": ".local/实际Harness运行目录", "identity_confirmed": false,
  "delivery_evidence": {"path": ".local/实际delivery-receipts.json", "sha256": "实际64位哈希"},
  "prompt_evidence": {"path": ".local/实际任务prompt.md", "sha256": "实际完整提示64位哈希",
    "shared_prompt_sha256": "实际共同题面64位哈希", "prefix_sha256": "实际固定提示前缀64位哈希"}
}
```

`delivery_evidence` 是实际原始成功工具结果绑定的收据：包含 `mechanical_delivery_verified`、`run_events_sha256`、`files=[{path,sha256}]` 和原始 `receipts`。机械通过不等于科学正确；用户的 `passed` 字段也不构成工具或 Motif 认证。学习和发布时再次核验运行事件、完整账本和交付文件的字节。

提示版本分为两层：`prompt_sha256` 继续绑定每次实际完整提示，与原始 Harness manifest 的 `question` 字节和摘要逐项核验；`prompt_prefix_sha256` 从真实提示文件中唯一的 `本次任务` 分界前导出。跨独立任务只比较这份已核验固定前缀及模型、工具、模板、运行实现版本，允许题面和来源不同。双路收益验证还要求 `shared_prompt_sha256` 与实际任务 JSON 相同，仅允许公共逐步／组合执行后缀不同；后缀与 `execution_strategy` 声明必须匹配。修改工具/schema、固定提示、模板或实现，仍会拒绝兼容。

旧记录若没有真实前缀、完整提示文件和共同题面证据，只保留诊断价值，不能默默补一个前缀哈希后认证。需由新入口显式采集新的完整记录；不追改旧反馈、原始 manifest 或旧证书。测试用的提示／manifest 协议夹具不构成真实 API、用户质量或晋级证据。

有多个失败/恢复尝试时，`accounting_run_dirs` 列出全部尝试目录，`run_dir` 为最终交付运行，费用汇总包含所有目录。没有列出的费用不能声称已统计；账单、机器、维护和人工金额未采集时仍为未知。

## 离线学习

由负责人或用户明确授权学习并审核任务独立性。用户完成科学/视觉审阅后追加新反馈；`reviewer` 必须为 `human` 或 `user`，不能把 AI 辅助审阅当独立人工审阅。学习只接收质量合格的正常 baseline 轨迹、完整真实API账本、机械交付和实际配置。

复用公共身份冻结入口，而不是新造任务身份：

```sh
python scripts/freeze-dsh-task-identity.py \
  --task-dir .local/实际Harness运行目录 --decision-id 稳定独立任务ID --events agent-events.jsonl
```

同一任务普通组/优化组、同一研究问题的续写不会计为两个独立任务。最小一次学习是两个训练任务和一个独立留出任务；先预览划分，默认不会编译或发布：

```sh
python -m scenarios.research_ppt.feedback_learning --store .local/research-ppt/feedback preview \
  --train TRAIN_RECORD_1 TRAIN_RECORD_2 --heldout HELDOUT_RECORD \
  --tool-schema .local/实际schema快照.json
python -m scenarios.research_ppt.feedback_learning --store .local/research-ppt/feedback learn \
  --plan .local/research-ppt/feedback/plans/PLAN_ID.json
```

确认预览后增加 `--confirm`，复用 `motif_v6.learn` 的现有编译、独立轨迹认证、schema 绑定与源码/证据锁。结果只登记为 `candidate`；编译失败保留结果，不能覆盖失败记录或重复使用同一计划偷换留出。自定义工具集合须传实际 `--contracts` 和 `--version-fields`，未批准或契约不匹配的工具由已有编译器拒绝。

这条管理入口仅编译已有正常轨迹，没有新的模型工具生成或布局学习算法。原有 [工具学习](tool_learning.py) 与 [布局学习](layout_learning.py) 仍各自按其预算、候选限制和独立认证协议显式运行；不能将本模块登记为已完成这些学习。

## 后续收益验证与受控发布

认证成功不等于收益准入。新候选需要至少两个未参与训练/认证的独立真实任务，普通组和候选组采用匹配输入、模型、提示、基础工具与质量门槛；优化反馈标记 `candidate_version`。两组真实运行身份均冻结，并人工审阅质量与修订分钟。

发布门槛核验真实原始账本、事件/机械交付收据、来源/配置一致、新任务独立、所有质量合格、人工修订时间不增加、各任务代理费用不增加且合计下降。候选组还须真实 `mode=execute`、manifest 摘要相符，并有冻结的同会话在线审计与至少一次 verified 模型请求旁路；仅填写候选版本或普通组合收益不能晋级。有失败反馈时先诊断，不仅选择节省的成功记录。费用缺失不能按零晋级。

首次候选不必先晋级。用双路入口 `--candidate-version CANDIDATE_VERSION --feedback-store <本库>` 显式创建隔离评测；它复核编译证据，沿用当前来源、schema、准入和权限守卫，不更改 active。若新安装缺少准入程序，先在 `cli prepare --allow-rsi` 创建的一次性授权 job 上，通过已有 `propose_guard` MCP 接口提交并认证格式/页数准入规则，再进行新任务预览。该规则认证只证明机械边界，不证明候选收益或科研质量；不要复制历史 `active-guard.json`。候选评测仍需真实新任务、人评与完整费用，接口诊断不替代这些证据。

```sh
python -m scenarios.research_ppt.feedback_learning --store .local/research-ppt/feedback status
python -m scenarios.research_ppt.feedback_learning --store .local/research-ppt/feedback activate \
  --version CANDIDATE_VERSION --pairs NEW_PAIR_1 NEW_PAIR_2
```

默认显示收益预览；负责人明确确认后增加 `--confirm`，只更新此私有库的 active 指针，**不修改当前执行中的任务，不自动注入公共 Runtime**。产品入口可显式调用 `FeedbackStore.active_manifest()` 或 `active-manifest` 命令继承已晋级且当前有效的版本；该函数复核编译依赖、源轨迹、学习授权及最新反馈。入口仍须使用已有 Runtime 的当前工具/schema、任务来源、参数、版本和权限守卫。若入口没有接入此选项，则 active 只是管理登记，不宣称已上线。明天默认使用稳定工程链，尚未获收益验证的 candidate 不自动启用。

```sh
python -m scenarios.research_ppt.feedback_learning --store .local/research-ppt/feedback rollback
```

默认预览回滚到上次版本；增加 `--confirm` 才追加回滚记录。active 加载和恢复旧版本还重查批准时的收益配对及最新质量/授权，反馈更新必须重新核验、明确晋级，不能继续沿用旧批准。证据或源码变化后候选标记 `valid=false`，旧认证不会因曾经 active 而继续有效。

此门槛支持人工审核质量、代理API费用和人工修订分钟范围的观察。账单实付、计算、维护和学习人工费用未完整采集时，不宣称完整总成本下降或达到盈亏平衡；学习成本与后续任务费用分别保留。每任务独立目录，写入锁防并发覆盖，异常终止遗留 `.write-lock` 时先确认无写入者再人工移除。

## 验证边界

`tests/test_feedback_learning.py` 仅为合成机制诊断，覆盖授权、未知费用、不可变修订、双组去重、失败不晋级、私有路径、并发锁、证据字节变化，以及实际提示文件导出的固定前缀、不同题面、双路策略差异和旧记录拒绝。训练／留出身份和真实账本门槛继续独立检查；配置可比不等于任务已经通过认证。根负责在服务器运行并保留日志。测试通过不代表真实用户质量、完全自主学习或稳定费用下降；真实试用先记录 `pending`，待用户反馈再形成结论。
