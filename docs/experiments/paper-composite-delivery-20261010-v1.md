# 复合取证与写入后自动校验

- 实验ID：paper-composite-delivery-20261010-v1；2026-10-10，Codex；feature/paper-submission，未提交/未推送。
- 问题与否定条件：将重复取证合成一次、把结构校验接入工具生命周期，能否减少整次模型控制请求。若来源变化仍通过、漏项/重复未报、失败被当作交付或质量未评审就宣称降本，则不支持目标。
- 范围：同一私人主稿的活动引用/预印本版本取证阶段；不是完整论文修订或最终PDF，不是独立论文泛化。

## 改动与边界

1. Python场景MCP新增显式opt-in `SSS_PAPER_COMPOSITE_EVIDENCE=1`：collect_paper_citation_evidence(case_id) 内部复用固定来源→活动引用→完整原文→批量arXiv元数据，保留内部步骤、诊断、哈希和版本；单次最多64引用键/64唯一标识，响应≤1.5MB，来源变化失败。没有模型判断、生成代码或论文写入。原六工具及旧opt-in保持。复合能力为工程实现，不冒充新挖掘Motif。
2. `paper_triage_validation.ts` 是结构校验的唯一实现，使用共享 `schemas/paper-citation-triage.schema.json`，检查格式、字段、枚举、漏项/重复/越界、已知源码问题是否报告，以及冻结来源。仅固定工作区triage.json，拒绝符号链接/超限、未知或过期证据。校验通过不认证标题作者、正式版本、来源网页内容或真实性。
3. `dsh_paper_delivery_check.ts` 使用公开 tools/result 和 tools/post-execute，无新Agent循环。同一校验器同时作为显式 check_paper_triage() 工具与写入后Hook：off不自动查；shadow只记录、不改变响应；enforce把通过结果附回写入结果，失败返回可修复的工具错误。文件已写入，block不等于撤销写入。尊重其他策略拒绝和取消。该Hook是明确工程策略，非已学习的Motif、无自动concludeTurn或虚报skip。
4. 新条件模型实际五工具：collect MCP、web_fetch、write、edit、check_paper_triage；三组相同。工具的存在不等于已学会自动选择/组合。当前旧九工具编译器拒绝认证新复合能力，旧库和所有失败保留。

## 条件、预算与有效配置

真实模型deepseek-flash，reasoning_effort=off，输出8192，压缩关闭，无请求次数上限；服务器Node22.23.3/Python3.10.8/Harness0.1.5-rc.3/SDK0.1.5rc1，Linux5.4。私人副本非沙箱授权沿用，不投稿、不改原件、不重启Web。题面及工具schema/order相同；每运行工作目录和句柄独立，API取证时间可能不同，未宣称系统前缀/缓存输入字节相同。

开始累计4.73918825，冻结上限4.84521046美元；新实验ID不重置预算。有效题面、manifest、API请求、冻结源码/checker配置、工具schema、账本和交付留在 .local/paper-reference/<ID>/。事后 effective-config-supplement.json 补录逐请求schema/order、缓存/输出用量与缺失字段。原始论文、请求/日志不进入Git；两端证据同步，归档排除dsh凭证目录。

## 验证与结果

- 两端全量免费217 Python/102 Node通过；新增delivery专项9 Node通过，包含真实 Harness ToolRuntime 注册表的反馈/错误提交；真实MCP stdio主稿34键/34原文/15元数据、短稿14/14/5，合成缺失1/重复1诊断仍保留，模型调用0。真实官方HTTP不计模型费用。
- 历史报告免费检查：15/15结构通过，原始报告字节未改，写入后反馈accept；文献结论未评审。

| 组别 | 实际状态 | 模型请求 | 新增代理估费/美元 | 秒 | 工具行为与交付 |
| --- | --- | ---: | ---: | ---: | --- |
| baseline / check off | completed | 8 | 0.013498044 | 35.526 | collect1、write1、check3、edit2；15/15覆盖、最终结构通过，来源未变 |
| shadow / check shadow | error | 8 | 0.021107160 | 47.713 | collect1已得15/15元数据、web_fetch19；无写入/校验/交付，长上下文预留触及剩余预算 |
| enforce | 未运行 | — | — | — | 真实shadow未合格，不绕过执行前置条件 |

shadow最后已接受请求的保守输入上界200529、预留0.0699891美元；下一请求被预算代理拒绝，不是次数上限，也未确认供应商限流。失败原始证据与费用保留；不以该shadow比较合格成本。

免费历史回放基线实际write/edit与同一packet，最终triage字节哈希与原件一致；3次自动检查中1次通过、2次返回修复问题。严格整次回复比较得到2/8=25%机会：一次纯检查返回通过，一次纯检查返回确定性修复反馈；另一检查回复含文本，保守单列。回放新模型请求0、实际跳过0、semantic_quality=not_reviewed，不是前瞻shadow或实际节省。数据在 baseline-delivery-replay/verification.json 与audit.json，分析不授予执行权限。

## 复现与下一步

```sh
source .local/remote-env.sh
# 默认仅预览：
node scripts/project.mjs python scripts/paper-citation-rsi.py --experiment paper-composite-delivery-20261010-v1 --arxiv-batch --bounded-evidence --composite-evidence
# 免费MCP预检（已存在输出不覆盖）：
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase preflight --experiment paper-composite-delivery-20261010-v1 --arxiv-batch --bounded-evidence --composite-evidence
# 已结束的真实组对应参数，均另需 --call-model：
# baseline: --phase collect --delivery-check off
# shadow: --phase evaluate --mode shadow --delivery-check shadow
# enforce: --phase evaluate --mode execute --delivery-check enforce
# execute还须成功shadow、最终结构通过与整请求分析至少一次机会；不使用旧失败shadow授权。
node scripts/evaluate-paper-delivery-shadow.mjs PRIVATE_COMPLETED_SHADOW_RUN
node scripts/replay-paper-delivery.mjs PRIVATE_COMPLETED_BASELINE_RUN NEW_PRIVATE_REPLAY_OUTPUT
```

当前累计代理4.77379344/4.84521046美元，余额上界0.07141702；账单未知。已向负责人提出追加1美元请求，未收到许可前不扩展支出。下一步在足够预算预留下完成匹配shadow/enforce，再评审语义质量；将新正常复合工具轨迹纳入编译覆盖后，才研究跨任务自动组合和学习曲线。20%实际调用下降与合格总成本目标尚未达成。
