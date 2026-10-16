# 论文 RSI 机制闭环验收

## 问题与验收范围

2026-10-16 用户更新门槛：先保证 RSI loop 通畅有效，以便开始真实业务测试；不再要求有限样本下先证明稳定的 baseline 费用优势。本轮检查从真实正常轨迹、离线编译/认证、版本发布，到下一 Web 任务的匹配、绑定、只读执行及审计。费用效果和完整论文质量另行研究。

先使用此前同一真实论文 ZIP 的两条正常训练会话 `baseline-05/06` 和一条留出会话 `heldout-03`，重建已有的书目读取 Motif；再把本轮实际完成的 `mechanism-shadow-02` 正常轨迹吸收入下一版训练，由更新后新任务验证。没有把 Execute 自生轨迹用作训练或拿当前评测结果追改其先前库。所有会话仍来自同一论文，不代表跨论文泛化。新任务检查原始书目第 1–12 条的字面记录，不能冒充全部 315 条参考文献的外部真实性核验。

## 配置与实际流程

- 代码基点：`codex/harless-motif-libraries-20261014@7fdd6a5` 加本轮提交的修订；未修改上游 Harness 或用户认证模块。
- 环境：V100，Python 3.10.21、Node 22.23.3、DSH 0.1.5-rc.3，独立代码副本 `.local/integration/paper-loop-mechanism-20261016`；原主目录及其他隔离检出中的未提交工作未覆盖。环境与核心代码摘要另存私有 `mechanism-environment.json`。
- 真实模型：`deepseek-flash`，推理 Off，每任务 $0.23，累计费用和请求次数不限，输出使用提供商默认容量。新任务各用独立 Session；所有失败/恢复支出保留，不重置历史账本。
- 实际 MCP：重新调用两个论文 MCP 的 `list_tools` 得到完整 23 工具。训练时的 22 工具快照保留；参与新边的工具参数 Schema 未变，`collect` 的描述更新仅澄清句柄和结果字段。部署包按当前完整 23 工具和代码重编。
- 学习：通过现有 `extract_dsh_trace`、参数来源推断、`mine_witnessed_parameter_edges`、`compile_witnessed_edge_motif` 与 `certify_witnessed_edge_motif`，重编 `collect_current_local_citation_evidence → read_pinned_bibliography_first_page`。认证摘要仍为 `fad88ff9ae2e8fe1120b15eabcb45f6724d43a2474d0a2a38207ff1942e8a540`，不是新发现或新科研认证。
- 发布：现有 `compile-paper-composite-runtime.py` 从父库的两条只读 Motif 生成包含三条的独立新包，旧两条保持不变。旧包和旧任务不覆盖；新任务经服务器私有 `HARLESS_PAPER_RUNTIME_BUNDLE` 加载。离线学习/发布由命令显式触发，不是 Web 自动学习。
- 下一任务：使用真实 ZIP 的任务批准副本。核对任务/Session、Manifest、认证文件、来源和绑定收据；读取参数来自当前 `collect` 返回的句柄，不复用训练时的字面值。六个评测 Session 和句柄均不同，书目读取结果各含 12 条记录。

最后一轮将 `mechanism-shadow-02` 加到原两条正常训练轨迹，保留 `heldout-03` 只作认证。该 Shadow 会话有一项前置普通工具错误，学习只采用后续 `collect → first_page` 无错且来源明确的局部见证；错误步骤不进入图。现有挖掘/编译器重新得到同一参数边，正常训练支持从 2 增至 3，认证摘要变为 `a034ed793f39ae3ec71d06b795ac0cefbc5c604d7fa4a99f94afe92d4742dd65`。库仍为三条 Motif，更新的是见证和版本，不声称覆盖增加；旧两条保留。`round-0002-after-shadow` 的库摘要与上一版不同，之后的 Execute-04 验证实际采用了这个更新片段。离线更新零模型请求。

## 本轮发现与最小修订

1. **Shadow 正常读取被误记版本失效。** `@from_anchor` 的结果记录只识别 Execute 的 synthetic pending call，Shadow 虽预先预测正确、正常模型调用的句柄和版本也相同，仍被记为 `source_version_mismatch`。`dsh_online_motif.mjs` 现在暂存请求前已通过共享匹配器验证的 Shadow proposal；只用于接受工具名、参数及版本都相同的正常结果。任一中间结果或新请求会清理预测，不产生 pending、合成调用或跳过收据。
2. **私有组合库的 Library SHA 展示字段缺失。** 原包已有 Manifest 和认证文件对 `library.json` 的摘要绑定，但 `load_uploaded_bundle` 未向场景返回 `runtime_library/runtime_library_sha256`，任务快照该字段为空。现补齐已验证的文件路径和字节 SHA；旧记录保持原样，最终 Execute 新任务验证该字段确实存在且正确。
3. 新论文部署包的代码锁增加 `dsh_online_motif.mjs`。共享适配器和 loader 改动使 PPT 当前代码兼容锁失效，已审阅后同步兼容摘要及登记文件；PPT 原训练证书、库、工具 Schema 和 Execute 规则不变，不宣称新训练。

## 真实结果

| 任务 | 模型请求 | Shadow 候选 | 已验证跳过 | 工具错误 | 代理估费 USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shadow-01，修订前 | 3 | 1 | 0 | 0 | 0.007608804 |
| Execute-01，修订前 | 3 | 0 | 1 | 1 | 0.007349016 |
| Shadow-02，Shadow 修订后 | 4 | 1 | 0 | 1 | 0.007736484 |
| Execute-02，Shadow 修订后 | 2 | 0 | 1 | 0 | 0.007567176 |
| Execute-03，Library SHA 补齐后 | 4 | 0 | 2 | 0 | 0.008457708 |
| Execute-04，吸收 Shadow-02 后的新库 | 3 | 0 | 1 | 0 | 0.007934784 |

累计本轮新增 **19 次真实模型请求、$0.046653972 代理估费**。不是提供商账单，不把这些不同执行路径作净降本对照。离线编译和定向测试没有模型调用；另有一个只预览的新包任务，零模型调用，其私有标签误写为 `mechanism-parent-preview`，实际配置为三条 Motif 的新包，不用它证明父库任务。

Execute-01 的错误发生在模型把 ZIP 名传给仅接受入口 TeX 的 `pin_paper_sources`，之后由正常 Harness 改用 `collect` 恢复；Shadow-02 的普通工具错误保留在私有审计，不计作接管成功。最终 Execute-03 是零工具错误；两条已验证跳过的完整 audit 链均包含 bypass attempt、工具结果验证及 verified skip。Shadow-02 没有合成调用，正常读取也不再被误记版本失效。

免费验收还拒绝了篡改库文件、篡改工具 Schema 和陈旧代码锁的三个包。新增自动回归覆盖正确预测、错误版本、错误句柄、工具失败、其他 Session、中间写入和没有请求前预测的情况；后六类不被当作正常来源续接，全部情形都不产生 Shadow 跳过。

机械检查确认当前句柄/版本绑定和 12 条结果，不包含论文内容人工评审、正式版本判断或逐页 PDF 质量认证。

## 自动检查

- `node scripts/project.mjs python -m pytest tests/test_parameter_learning.py tests/test_witnessed_edge_motif.py tests/test_harless_rsi_bundle.py tests/test_versioned_evidence_guard.py -q`：最终 33 通过。
- `node --test tests/test_*.mjs`：最终 717 通过、3 条件跳过，0 失败。
- `npm test`：首跑 967 通过、5 失败；其中本轮导致的 PPT 兼容锁失败已修复并包含在上述定向复测中。其余 4 个文献 PDF 解析环境失败仍未修复，完整命令未重新跑绿；Python 阶段失败后原命令不运行 Node，所以另跑完整 Node。
- `npm run smoke`、`npm run web:controls:check`：最终均通过，无付费模型调用，日志随本轮收据归档。
- 本地缺 `pytest`，上述 Python 验证在 V100 执行；不把本地缺依赖说成测试通过。

## 配置、复现与回退

私有验收目录为上述隔离检出的 `.local/paper-rsi-loop-mechanism-20261016/`，含 `setup.py/compile_check.py/audit.py`，仅编排已有入口，不实现另一套 Runtime。真实摘要、原始事件、`mechanism-round.json`、`mechanism-acceptance.json`、库和认证包位于同一隔离检出的 `.local/paper-bibliography-training-20261016/`。它们包含输入/配置/事件摘要、逐请求 token 和估费；全部不进 Git。复编使用 `scripts/capture-paper-mcp-schemas.py` 与 `scripts/compile-paper-composite-runtime.py`；后者 `--output` 必须指定不存在的新版本目录。

最终私有部署候选为 `round-0002-after-shadow/runtime/`。此前 v2/v3 是同一学习产物的代码兼容重编，不是两轮新增学习；round-0002 才吸收了本轮新的正常 Shadow 见证。认证包绑定原证据及当前代码；换代码后应重编，不能手改认证 SHA。真实验证入口仍是 `npm run web:real` 的场景任务 API，不修改生产环境变量或全局 cwd。

**结论：已验证窄只读 RSI 机制链，可作为开始受控论文业务试用的依据。** 学习/发布需要显式离线操作，尚未证明自动自主学习、跨论文覆盖和稳定净费用收益。完整 315 条外部核验、Crossref 大结果恢复问题以及 4 项旧文献 PDF 环境失败仍在，不能把机制验收当作全面上线质量验收。PR #19 由用户审阅合并；生产成员进程和私有包本轮未切换。关闭 RSI 可回到普通 Harness；回退本次代码须一并恢复 PPT 兼容登记，保留全部私有证据和累计支出。
