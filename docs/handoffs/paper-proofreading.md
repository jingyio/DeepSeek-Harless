# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：第三轮 Script Motif，从脚本缓存推进到当前语义确认后的连续结构执行。已真实运行原参考文献题面；没有证明稳定净降本。用户追加质疑 Baseline 漏检，核查确认三组报告路径/质量门不一致，不能按同等合格质量解释费用差。
- 分支 / commit / 工作区：独立 worktree `codex/paper-script-frontier`，基线 `394389448eafc73f89087ca461d2116c5dd61e51`；本文件随实现本地提交，具体见 `git log -1`。未推送、未 PR、未合并、未部署；桌面原脏工作区及生产/旧认证库未改。
- 已完成：新增 `src/adapters/script_execution_frontier.ts`，从真实前驱关系发现 2–8 节点的同输入无分支片段；当前目标下模型通过既有 Bash 选择 selected/unknown/ambiguous/unneeded，Runtime 自动绑定唯一文件、验证回执/输入版本、连续执行到结束或失败。当前只支持必要性选择，不是任意参数槽位或科研判断自动化。
- 已完成：Runtime、Web adapter、认证入口接入；Python/TS 统一 `/work/outputs` 到当前 outputs/code 的虚拟路径绑定，修复真实任务无候选的原因。记录已完成当前 Evidence、取消变更目标、去重已验证节点。无工具表扩张，不调 embedding 阈值。
- 已完成：费用分类新增 semantic_slot_resolution，细分报告阶段可见动作，未知 usage 不算零。GELU malformed unneeded 命令后撤回邀请的 fail-closed 小修复在真实实验结束后完成；仅局部测试，不冒充该版本完整任务效果。
- 已验证：Node 22.22.3/Python 3.12.14/Harness 0.1.5-rc.3。完整 `npm test`：903 Python 通过/199 跳过、866 Node 通过/5 跳过；无模型 smoke 通过；末次状态机/真实沙箱局部 20 通过。第一次局部漏设 SSS_PYTHON 导致系统 xcrun 被沙箱拒绝，补环境后通过；失败日志保留，无守卫放宽。
- 实验结论：[paper-script-frontier-20261019-v1](../experiments/paper-script-frontier-20261019-v1.md)。RMSNorm 同题 Baseline 101/$0.162408540/950.781 秒，Cache 144/$0.194030328/912.206 秒，Execute 286/$0.371369304/1113.774 秒。Execute 一次 106 输出 Token 的付费确认后连续 2 次 provider 跳过，并另有 1 次网络缓存成功；仍 PDF 交付失败。Cache 此次未使用缓存。GELU 候选已发现，但 malformed unneeded 未被接受，0 自动接管，后 HTTP 502。
- 核心反例：总差 185 请求中，报告协议差 181（6→187），其余 95→99。Baseline 使用通用导出，没有结构化审计校验；PDF 引用计数 30/41 与源文实际 37/58 不符。Execute 27 次定稿全部拒绝（9 次状态/优先级，18 次重复来源），不是同等必要取证。全部三臂都没有合格质量证据。不得把“失败恢复更多”宣传为更认真，也不得把 Baseline 低费用宣传为同质量优势。
- 配置与数据：原题 `scenarios/paper-submission/reference-audit.prompt.md` 未变；DeepSeek Flash/off、30 工具同顺序、native baseline/RSI off、32,768 输出限额、无压缩。私有 `.local/script-frontier-20261019-v1/` 的 runs/aggregate/breakdown/quality 与每 run 的 source-snapshot/effective-config/events/ledger 对应。RMS/GELU 都是上一轮未训练评测输入的重测，不是新独立样本。
- 库与学习：实验 v2 库 7 算子，摘要 `8aa71d398879e2f154fbad622c4fcb90534499c3487b427adfd8a257c508fe87`；实验后 fail-closed 改动经真实重放另发 v3，摘要 `fd51a752303e66c1df36714a305ca264b8838b7b15c3694589fd6e7125f43080`，旧库不改。136 历史请求/$0.282083184 已在旧账，不重复加；本轮无新增学习 LLM 调用，离线/HTTP/人工成本未完整计量。
- 未完成与阻塞：报告 stage 延迟校验、来源只追加、已写 citation_checks 不可覆盖、read 只能读定稿造成恢复陷阱；报告路径验收不统一。本轮未改报告服务。未实现一般多阶段参数流、语义缺口批量解析或稳定跨论文完整收益；未做独立人工盲评、新 Linux/Windows 验收。远程 V100 旧费用未核清。
- 接手下一步：1）修复并局部回放通用报告协议：暂存前校验、幂等写入、草稿读取与明确修复入口；保留来源/CAS/定稿边界，不降低事实要求。2）三组统一最终内容/版本验收、允许同样有效的批量/确定性输出，报告工程优化单列，不能故意给 Baseline 增加调用。3）仅协议通过后做新论文配对重复对照和独立质量评审，计入学习/失败/恢复；效果稳定后由用户决定 PR。
- 最短复现：隔离环境中设置 `TMPDIR=/private/tmp`、`SSS_LOCAL_SCRIPT_EXPERIMENT=1`、`SSS_PYTHON` 和既有 renderer/font；`node scripts/project.mjs python scripts/run-script-motif-experiment.py --real-model --source /path/source.zip --mode execute --script-config /path/frontier.json --budget-usd 0 --max-output-tokens 32768`。配置 `catalog:true,executionFrontier:true`，最终代码用新 v3 库；旧实验必须用快照及旧冻结库。frontier 不需启动 embedding。Baseline 不带 sidecar，Cache 关闭 frontier。
- 权限与预算：用户允许本地真实测试，费用/请求无上限、保留输出限额；本轮 696 请求/保守估费 $1.376831772，其中 usage 可见 $0.903972372，4 无 usage、1 pending 保留。连同前两轮，本地 2,793/$4.587678180；非提供商实付/账户总额，远程未知不算零。所有本轮任务已结束，不再追加付费完整重试；原件、外部应用、生产均未写。
- 回退与风险：不用 sidecar 即恢复普通原生运行；代码可回到 `3943894`。不要删除 .local、失败账本或修改旧库锁。macOS 沙箱边界仍有平台限制。当前结果不足上线或提交 PR。

前两轮：[Script Motif 初版](../experiments/paper-script-motif-20261018-v1.md)、[脚本 Evidence 改进](../experiments/paper-script-evidence-20261019-v1.md)。旧结论及费用保留，当前报告补充路径混杂证据。
