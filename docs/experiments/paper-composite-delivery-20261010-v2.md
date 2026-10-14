# 提高预算后的复合取证与自动校验测试

- 实验 ID：`paper-composite-delivery-20261010-v2`；2026-10-10，Codex。
- 分支：`feature/paper-submission`，基点 `2368235f274329be6227a8393b850633cb943da4`；本次改动未提交、未推送。
- 问题：复合取证与写入后自动反馈能否减少模型重复控制，并迁移到不同活动稿件范围。若结构错误未报、来源变化仍通过或合格任务的总体调用/成本没有下降，则不能支持相应效果主张。
- 结论：六次真实运行均完成。自动校验和错误修复协同可用，但两组 baseline 共 14 请求，execute 也为 14 请求，估费增加约 30.3%；尚不支持总体降本或达到 20% 调用下降。

## 任务与对照

同一私人论文的主稿和短稿分别使用活动引用范围：主稿 34 个引用键/15 个预印本组合，短稿 14/5。不是独立论文泛化，不是完整参考文献核验或最终 PDF。原稿不改；本轮各组都有独立 Session 和工作区。

三组使用同一题面、五个模型可见工具及顺序：`check_paper_triage`、`edit`、`mcp__paper_checks__collect_paper_citation_evidence`、`web_fetch`、`write`。同一稿件的题面 SHA-256 三组一致；全部请求的工具 schema/order 摘要一致。不同稿件的题面只改变登记案例，工作目录、句柄与 HTTP 取证时间独立，不能据此宣称系统前缀或缓存字节完全一致。

唯一分组变量是结构检查反馈：baseline/off 由模型显式调用检查；shadow 在写入/修改后检查并记录，不改变反馈；execute/enforce 自动把检查结果送回写入/修改结果。显式与自动路径使用同一个 TypeScript 校验器，失败不撤销已写文件。没有自动结束 Agent，也没有改上游 Harness。

这是工程复合工具与 Hook 的测试。新条件未加载旧 Motif 拦截器，当前编译器没有认证新复合/交付节点；没有新的学习/认证/留出划分，不能冒称本轮自动学会新 Motif。此前挖掘实验仍见各历史记录。

## 配置、预算与复现

- 实际模型 `deepseek-flash`，`reasoning_effort="off"`，输出上限 8192，压缩关闭，无请求次数上限；服务器 Linux 5.4、Node 22.23.3、Python 3.10.8、Harness 0.1.5-rc.3、SDK 0.1.5rc1。
- 用户本轮“提高上限，继续测试”批准此前提出的追加 1 美元。新累计上限 **5.84521046 美元**，起点累计 **4.77379344**；未重置任何失败或旧费用。旧 `parameter-motif-proof-20261010-v1/effective-budget.json` 不改。
- 新私有授权记录 `.local/paper-reference/<本实验ID>/authorized-budget.json`，SHA-256 `80d4b1ffdfc3af8922aa5bfcbd982928cbaf5d62779594e365f318c271eeb249`。新增 `--budget-record` 指定记录；默认仍使用旧上限。每运行冻结授权内容、路径及摘要，启动前复核未变，拒绝公开路径、符号链接、超限文件及非有限/非正额度。此选项不代替用户授权，也不改变通用 SDK/Web 的预算。
- 私人副本非沙箱授权沿用；不投稿、不写外部应用、不重启 Web。密钥仅服务器 `DEEPSEEK_API_KEY`，统一入口读取私有 `.env`，不记录值。

服务器复现入口如下；现有运行不可覆盖，重测须新 ID/运行标识且继续累计费用：

```sh
source .local/remote-env.sh
paper_args=(--experiment paper-composite-delivery-20261010-v2 \
  --arxiv-batch --bounded-evidence --composite-evidence \
  --budget-record .local/paper-reference/paper-composite-delivery-20261010-v2/authorized-budget.json)
node scripts/project.mjs python scripts/paper-citation-rsi.py "${paper_args[@]}" --phase preview
# 每个 case 为 manuscript 或 abstract；以下付费入口已执行，不能覆盖旧目录：
node scripts/project.mjs python scripts/paper-citation-rsi.py "${paper_args[@]}" --phase collect --case manuscript --delivery-check off --call-model
node scripts/project.mjs python scripts/paper-citation-rsi.py "${paper_args[@]}" --phase evaluate --case manuscript --mode shadow --delivery-check shadow --call-model
node scripts/evaluate-paper-delivery-shadow.mjs .local/paper-reference/paper-composite-delivery-20261010-v2/runs/evaluate-manuscript-shadow
node scripts/project.mjs python scripts/paper-citation-rsi.py "${paper_args[@]}" --phase evaluate --case manuscript --mode execute --delivery-check enforce --call-model
```

有效配置在各运行 `manifest.json`、`authorized-budget-snapshot.json`、`delivery-check-config.json`、`prompt.md` 与 `effective-config-supplement.json`。保存全部请求、事件、账本、工具顺序/摘要、来源文件版本、最终输出和审计；`actual-code-snapshot.tar.gz`/`code-snapshot.json` 保存实际相关源码。环境补录明确标为事后记录；账单和人工盲评仍缺失。私人数据/原始日志均留 `.local/`，证据同步回本地时排除 `dsh` 凭证目录。

## 验证与结果

两端 `npm test`：**227 Python / 102 Node 通过**，不调用模型；其中预算记录诊断新增 10 项。真实无模型 MCP stdio 预检主稿 34 原文/15 元数据、短稿 14/5，合成案例缺失/重复诊断保留。默认六工具保持，新 opt-in MCP 列表七工具、阶段模型实际五工具。

六次运行均 `completed`、精确覆盖预期组合、最终结构校验通过、来源版本未变。没有预算拒绝或输出截断。

| 稿件 / 组别 | 请求 | 新增代理估费 / 美元 | 秒 | 网页调用 | 自动 / 显式检查 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 主稿 baseline | 8 | 0.022348068 | 52.748 | 5 | 0 / 2 |
| 主稿 shadow | 9 | 0.015795912 | 41.974 | 1 | 3 / 2 |
| 主稿 execute | 7 | 0.026379432 | 53.133 | 12 | 2 / 0 |
| 短稿 baseline | 6 | 0.007707108 | 33.206 | 2 | 0 / 1 |
| 短稿 shadow | 8 | 0.009489252 | 35.839 | 3 | 2 / 2 |
| 短稿 execute | 7 | 0.012793452 | 42.051 | 5 | 2 / 0 |

两次 execute 各经历一次 `needs_repair` 和一次 `passed`，随后正确修复结构错误，没有再显式调用检查器。两稿错误均为 `citation_issue_key_outside_scope`；具体反馈和文件摘要保存在各运行审计。这证明公开工具生命周期可传回修复信息，不证明文献判断正确。

严格完整响应分析：主稿 shadow **1/9=11.1%** 为纯检查请求机会；短稿 **2/8=25%**，包括一次通过检查、一次确定性错误反馈。合计 **3/17=17.6%**；带文本或混合操作单列，不自动算跳过。shadow 实际跳过 0；本轮没有 Motif 请求拦截，`verified_skips` 也是 0。自动反馈减少显式检查调度与真正拦截一次未发出的请求分别统计。

| 合计 | baseline | shadow | execute |
| --- | ---: | ---: | ---: |
| 模型请求 | 14 | 17 | 14 |
| 代理估费 / 美元 | 0.030055176 | 0.025285164 | 0.039172884 |
| 运行耗时合计 / 秒 | 85.954 | 77.813 | 95.183 |
| 缓存命中输入 token | 260096 | 255744 | 283264 |
| 缓存未命中输入 token | 43850 | 32349 | 66647 |
| 输出 token | 12783 | 11705 | 14566 |

主稿 execute 相对 baseline 请求下降 12.5%，短稿增加 16.7%，合计没有下降。execute 相对 baseline 估费增加 **30.3%**、耗时增加约 10.7%；相对 shadow 请求少 17.6%也不能作为同质量基线收益。网页操作与模型判断不同、样本少，不能把组间总差异完全归因于 Hook。

本轮新增累计代理金额 **0.09451318 美元**，含全部历史为 **4.86830662**，上限 **5.84521046**，剩余上界 **0.97690384**。逐运行浮点结算与全局重算相差约 1e-8 美元，以全局账本重算为准。均为代理估费；账单实付、人工修订/开发维护成本未核对。

## 质量、失败与限制

语义质量未人工盲评，完整报告/PDF 未验收。Codex 非盲初阅发现：同一文献在三组被分到 P1/P2/P3/无问题；基线多次在“未发现正式发表线索”情况下直接标 P2，execute 又把引用键的年份作为需要统一的事实问题。引用键是别名，单凭其命名年份不构成著录年份错误；`and others` 也需结合格式判断，不能自动当作者造假或漏列。产物保持原样，未事后修订为正确报告。

网页成功状态不等于取得论文证据：短稿访问 OpenReview 得到 HTTP 200 的浏览器验证页；execute 两次遇到跨域重定向拒绝，再尝试出版方直链。主稿 shadow 一次把本地文件地址送到 `web_fetch`，原生工具以 `WEB_INVALID_URL` 拒绝，未读取本地文件。这些恢复已计入调用/费用；不绕过验证页或网页工具的跨域守卫。

主稿 execute 额外访问 12 个 arXiv 页面，部分为补查元数据工具未提供的 Comments/版本线索。现有批量接口的 DOI/journal-ref 空值不证明没有正式版本，不能把全部补查简单认定为无效。查询、版本选择、判断与解释的差异仍超过省去的显式校验开销，是后续需要分解的空间。

## 下一步最小验证

1. 从这六条正常轨迹按实际失败/证据缺口提取查询与恢复节点，补齐可追溯的版本线索和页面类型识别；已有证据足够时 Runtime 续接，未知出版关系交回模型。保留跳转/权限/来源变化反例，不能用 HTTP 200 或旧频率授权跳过。
2. 为复合取证、产物检查与查询恢复扩展离线编译/认证覆盖，冻结新库后用下一份独立论文 shadow。工程工具内化与真正 Motif 学习分别报告，不把手工 Hook 命名为已学习结构。
3. 先盲评文献判断和优先级，再做同质量成本对照及普通脚本/缓存对照。当前证据不支持“20% 已达标”或“每轮学习后调用持续下降”。无需继续相同机制的无变化付费重测。

旧预算受限失败与历史回放见 [v1 记录](paper-composite-delivery-20261010-v1.md)，不改成成功。新模型运行已全部结束，代码/文档与私有结果两端同步；未提交/未推送。
