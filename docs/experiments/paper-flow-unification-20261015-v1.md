# 旧论文 Motif 与报告脚本同包 Shadow 验证（2026-10-15）

- **问题与假设**：旧实验一的 9 条候选与实验二的 PDF 排版脚本能否在当前 Web 论文任务中共存，旧候选是否仍有严格整请求匹配。若没有匹配或交付失败，不能声称两次收益已复现。
- **任务与配置**：V100 私有隔离检出、旧真实论文的 14 份 `.tex/.bib` 平铺副本，同一自然语言题面；输入字节及题面哈希两轮相同，题面 SHA-256 `6fc447c1520a549cb9a07d344e4d79968dc8e9fb47a78111f0b040c5527896fb`。实际 20 工具 Schema 哈希 `5cfdd7a662fa416f5fe63b97c37ee65c40c1cd82a9cf816c5f6bc46f4bfa379c`，在线 manifest 哈希 `e22428bb12f862c99fbec925aba2ba7e3bb7ef10b4989f0f3369bfdd84e2755a`。模型 `deepseek-flash`、`reasoning_effort=off`、单次输出 4000；每任务及本次启动各 $1 预算代理上限，请求次数不限，公共 Web 默认额度未改。旧库、轨迹、输入、有效配置、逐请求账本和 PDF 均留在 V100 `.local/`，未进入 Git。实验 ID `paper-flow-unification-20261015-v1`。
- **重编与权限**：`scripts/compile-paper-flow-shadow-bridge.py` 对旧库摘要、3 条来源轨迹及请求文件哈希、9 个图和证人、当前 6 工具参数 Schema 做校验。私有 sidecar 包含 6 条只读 Shadow 候选及 3 条旧报告流程的当前映射；三条报告流程仍由模型决定与调用。私有 v7 组合包保留此前认证的 2 条只读 Motif、20 工具与获准 PDF 排版工具。sidecar 被组合包文件锁及任务确认摘要冻结，在线只观察同一 Session，不授予 Execute。旧候选的原证书没有被冒充为新执行证书。

| 运行 | 任务状态 | 真实模型请求 | 工具调用/工具错误 | Shadow 候选 | Verified Skip | 代理估费 | 耗时 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Origin `098e0db318654fdabe4256445f4c91fa` | completed，1 份 PDF | 18 | 18/0 | 0 | 0 | $0.053694264 | 86.787 秒 |
| Shadow `fa6b386735d0457fb17eff2e9df1ad3a` | failed，生成 3 份但均未过覆盖守卫 | 28 | 27/0 | 4 | 0 | $0.071495532 | 106.699 秒 |

- **候选核对**：Shadow 的 4 次通用计数中，3 次来自旧 6 条只读流程，1 次来自原有认证只读库。旧流程里 `read_pinned_citation_records` 的参数摘要与随后真实工具调用相同；任务开头的 `pin_paper_citations`、外部元数据调用未成为后续整请求。报告写入另有 2 次 `paper_report_shadow_candidate`，其中后一次 `finalize_current_audit` 的参数摘要与真实调用相同；这些写流程不计 Verified Skip。Shadow 没有替代任何模型请求，当前匹配不能称为费用下降。
- **失败与费用**：Shadow 产生报告和 PDF，但模型给两条 issue 加了排版脚本未呈现的额外 `evidence` 字段；三份导出收据都是 201/203 字段字面覆盖，`all_fields_present=false`，任务正确判为 `paper_pdf_not_delivered`。28 次请求包含两次预算内的交付续行及重复导出；两轮合计 46 次请求、$0.125189796 代理估费，账单实付未知。此数是本实验两轮，不覆盖或重置此前失败/重试账本。质量未人工评审，同题输出内容也不等价。
- **结论与下一步**：当前已验证旧轨迹有至少一条严格匹配价值，也验证旧候选、现行只读证书和 PDF 脚本能同包加载；尚未观察到 RSI 净降本，更没有复现旧 160→20。此任务的 Origin 已只有 18 次请求，不能用旧 160 次基线作当前分母。按用户最新要求不再重复跑 Origin；下一步先让报告字段与排版/覆盖守卫一致，再在冻结输入下仅用 Shadow 检查更多可严格匹配的完整请求。任何 Execute 扩权需另行独立认证与守卫验证，不能把 Shadow 候选直接执行。
- **复现入口**：无模型可运行 `python3 scripts/compile-paper-flow-shadow-bridge.py --old-library <V100私有旧库> --training-runs <V100私有轨迹目录> --schemas <20工具Schema文件> --output <.local/sidecar.json>`，随后 `python3 scripts/compile-paper-composite-runtime.py --citation-library ... --uploaded-library ... --schemas ... --renderer-deployment ... --flow-shadow <.local/sidecar.json> --output <.local/组合包>`。真实任务使用 V100 私有 `.local/paper-real-source-main-20261015-v1/compare.py`，`PAPER_COMPARE_MODE=shadow`；需 `source .local/remote-env.sh`、隔离密钥及任务预算，原始论文不公开。组合包与有效配置快照在 `.local/paper-local-batch-v7/compiled/runtime/` 和对应 run 的 `tasks/<TASK_ID>/effective-config.json`。

## 交付失败修复与仅 Shadow 复测

用户指出 Shadow 不跳过模型是预期，任务不能交付才是严重问题。因此在 `stage_current_audit` 暂存入口拒绝排版脚本不呈现的附加记录字段，返回准确 `extra_fields` 且不写草稿；旧草稿在 finalize 时同样拒绝。提示要求把 issue 的证据放进 `finding`。没有改 PDF 排版脚本或放宽 100% 字段覆盖守卫。V100 用变更后的代码/提示重编私有 v8 包，两个已认证只读图与六条旧 Shadow 候选仍保留；免费论文场景矩阵 28 个冻结预览、真实 MCP/上传/输出授权和双用户拒绝通过。

仅重跑 Shadow `7229de7c61b54c11bcbd46a0791a62f4`，同一 14 份输入与用户题面、同一模型及上限：任务 **completed**，17 次真实请求、17 次工具调用、4 次工具错误、1 次旧流程 Shadow 候选、0 Verified Skip，代理估费 $0.045906192，耗时 75.816 秒。模型生成 34 条参考文献的任务报告和一份 8 页 PDF，导出收据 198/198 字段字面覆盖，输入字节未变。错误分别是两次使用了错误的当前文件句柄、两次在报告定稿前尝试读取报告；模型随后恢复并交付。候选是任务起点的 `pin_paper_citations`，实际下一调用并非该工具，故本轮旧流程严格整请求命中为 0。内容真实性、语义完整性和视觉质量未人工评审。

这轮 17 请求与之前 Origin 的 18 请求只有一轮随机对照，且提示/代码版本不同；不能把 1 次差异解释成 RSI 节省。旧 160→20 来自已有报告直接使用排版脚本，此任务还须生成报告；当前还没有复现自动执行收益。三次本实验运行合计 63 次请求、$0.171095988 代理估费（含失败轮和恢复），实付未知；此前其他论文实验账本仍须合并核对。用户要求抓紧前端验收，但这份私有 v8 尚未部署到公网成员服务，现网测试不可作为此修复的验收。
