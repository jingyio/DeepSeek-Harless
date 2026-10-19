# 论文校对当前交接

- 更新时间与交接人：2026-10-20，Codex。
- 目标与本次范围：恢复真实调用前的中间输入，学习可执行诊断片段，验证当前产物短参数绑定与 Runtime 连续控制。用户最新要求：配置/环境固定时复用已有 Baseline，优先审计 Motif 机制轨迹；不能以随机轨迹的费用高低单独判断机制有效或无效。
- 分支 / commit / 工作区：`codex/evidence-slice-takeover`，基于 `2c0b35331cb12968c2d68e3e841d165626a6bb75`；本轮提交见 git log，独立 worktree。原脏工作区未动；未推送、未 PR、未部署。用户看到效果稳定后才考虑 PR。
- 已完成：`reuse_snapshot.py` 校验并恢复有界调用前快照；脚本挖掘/认证使用真实版本；heredoc 解析补齐无 `-` 与空格写法。`probe_motif_compiler.py` 从多任务实际失败/子集试验学习字段轴；`probe_frontier.ts` 在有界试验中续接实际原生工具结果。`reuse_mediation.ts` 保持 nonce、来源、schema、权限守卫，工具副作用需显式 `probeTools`，默认关闭；动态提示不再改变系统前缀。不新增模型可见工具。
- 已完成：`evidence_report.py` 与 `paper-evidence-server.py` 提供私有 `--report-evidence` 变体，修复配置字体缺字回退并返回带摘要的当前失败字段证据。生产 `session_report.py` / `document_engine.py` 无改动，原认证库无变动；新变体明确未经生产认证。字体修复属于人工服务修复，不算 Motif 学会原因。
- 已验证：真实 Execute003 一次语义选择后 24 个不同原生调用及 24 个结果，9.077 秒区间内 0 provider 账本请求、0 带 usage 的 assistant 消息；到 `probe_limit` 停止并交回证据。已证明控制转移，未定位最小原因，不能换算净省 24 请求。
- 已验证：Execute004 一次 120 字节选择绑定 26,157 字节参数成功；Execute005 两次 120 字节选择各绑定 24,989 字节并成功，同报告重复导出暴露结束条件缺口。机器复核这两项完整报告保留 37/37 条目及状态/优先级、来源版本；科研事实未独立盲评，Execute004 原因解释错误。
- 已验证：`npm test` Python956通过/199跳过、Node908通过/5跳过；`npm run smoke`无模型通过。收尾子序列类型/重数/顺序守卫后4项针对性测试通过；提示修正为“未证明最小的失败见证”后19项Node检查通过，库实际重编/认证装载通过。原样草稿六页渲染已检查，两处 `ğ` 不再丢失。Windows 未验收。
- 学习状态：`frozen-release-004` 12 个旧真实集重认证脚本（含5个AST片段），`native-release-002` 2个原生契约/1个诊断契约，当前TS可装载。新轨迹 heldout 发布0，115缺失输入、3回放失败、2输入依赖不足；额外失败及重复认证保留。不能称已实现持续库增长。
- 实验结论：[边界证据与控制接管实验](../experiments/paper-evidence-slice-20261019-v1.md)。本轮全部8项是同论文历史报告局部恢复，不是独立论文或完整校对对照。报告列出全部运行、token、费用、失败和代码变体；没有再用成本差额否定/证明局部控制机制。没有新 embedding 调优。
- 配置与数据：`.local/evidence-slice-20261019-v1/` 包含authorization、aggregate、control-audit、breakdown-v2、quality及各轮编译/测试。最后付费 Execute005 用 `execute-006.json` / `native-006`；收尾只读诊断与重编后用 `execute-release.json` / `native-release-002`，未追改付费快照。最后配置为native-only，脚本库空，不把产物引用说成在线脚本命中。模型deepseek-flash、reasoning off、单次输出32768、请求不限。
- 未完成与限制：学到的子集诊断轴不是错误因果，未缩小到有效最小见证；工具字段证据仍需连到更有效修复。成功产物重复导出、页数约束、最终总结/交付结束条件仍有缺口。新脚本缺少兼容输入和跨任务 heldout 绑定；尚无新独立论文上的泛化证据。
- 接手下一步：1）固定环境复用既有轨迹核对字段证据与诊断动作，减少无关试验。2）学习同版本成功产物的直接引用与终止条件，保留必要语义总结。3）针对真实 missing_script_input 补齐数据依赖，再认证下一任务；不用降低阈值或手写论文路线制造命中。只有配置/环境变化或需要独立效果结论时重测相应 Baseline。
- 最短复现：新实验记录给出统一 runner 的显式付费命令；使用 `--report-evidence --reuse-checkpoint` 是局部恢复，不与完整任务混分母。Python入口用 `node scripts/project.mjs python`，系统python3未装pytest。锁定代码变化后重新编译/认证，不能手改hash。
- 权限与预算：本地真实API无限额持续授权、reset_history:false。本轮717次尝试，已知usage估费$1.281259692，另$0.228752400未结算预留；保守合计$1.510012092。本地累计4700次/$7.864003968保守估费；旧pending1+本轮pending1，V100和账单未核清。开发/人工时间未完整计量。付费任务已结束。
- 回退与风险：回退本轮提交或关闭私有sidecar/`--report-evidence`；原件、生产和旧库未改，未写外部应用/投稿。停止/回退不删除失败轨迹。保留实验开关，未提交PR。

前轮：[统一复用](../experiments/paper-unified-reuse-20261019-v1.md)、[具体读写实例](../experiments/paper-operation-breakdown-20261019-v1.md)、[接管Breakdown](../experiments/paper-takeover-breakdown-20261019-v1.md)。
