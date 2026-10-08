# 结构化 MCP 的三类真实数据核查记录

2026-09-26。原始来源、事件流、预算账本和回答均在被忽略的 `.local/benchmarks/structured-phase-transfer-20260926/`，不提交个人资料或运行日志。本报告只讨论**数据核算阶段**，不能代表完整论文核查、跨应用科研闭环或 Motif 成本收益。

## 问题与条件

此前普通 DeepSeek Harness 的两次论文图表核查几乎全用本地命令，MCP 调用为 0；第三次 Figure 9 核查也证明结构化 MCP 虽在工具清单里，Agent 未必选用。为了区分“工具不可用”和“工具没有被选”，这里保留真实研究问题与冻结文件，另设一个数据阶段条件：`sdk-minimal` 仅暴露只读的结构化 MCP。它是受限条件，不与普通 Harness 的完整任务直接比较成本。

每项任务先固定文件哈希和验收数字，再调用 DeepSeek Flash。调用经本地费用代理设置上限，结果事件保存于 `.local`。费用列为代理**保守预留**，尚非 DeepSeek 官网账单。总 token = 未命中输入 + 缓存命中输入 + 输出。

| 数据阶段任务 | 状态 | 模型请求 | 总 token | MCP 调用 | 保守预留 |
|---|---|---:|---:|---:|---:|
| AppWorld coverage：核对原始/图用记录及重复任务影响 | 关键数字正确；仅数据阶段 | 6 | 20,179 | 10（9 成功，1 次不适用比对报错） | US$0.034854 |
| TauBench Figure 7：三份 trial 的成功率及动作数 | 首跑缺少文件清单而未完成；补清单后数据阶段正确 | 7 | 32,741 | 15（均成功） | US$0.052155 |
| APIBank MPLS：按比例比较历史实验策略 | 首跑出现逐 seed 过度断言；补排名工具后的诊断重跑在组均值问题上正确 | 9 | 28,091 | 8（6 成功，2 次不适用调用报错） | US$0.052653 |

这些回答尚未经研究者盲评。第一轮 TauBench 耗费 9 请求、25,867 token、31 次工具调用，因没有列目录工具而没有完整核算；第一轮 APIBank 耗费 10 请求、39,037 token，虽然均值正确，却误称 MPLS 在全部 9 个 fraction×seed 单元均最差。原始记录显示 MPLS 仅在 6/9 单元最差。这两个失败保留为失败，不能被重跑覆盖。

## 对具体研究问题的收获

- AppWorld：原始 `per_task_common` 200 条，图用 CSV 196 行、92 个 task ID。重复最多的任务 `8749218_2` 出现 22 次、贡献 +456 次调用节省；全部实例合计 +401，剔除该任务后为 −55。此为数据敏感性事实，尚不证明图题的因果说法。
- TauBench：三份 30 条 trial 的 reward 均值分别为 ReAct 0.8667、ReAct-ACT 0.7667、MotifAgent 0.8；若图中 ReAct 柱为 76.67%，数值上只与 ReAct-ACT 文件一致。完整图表口径与版本仍需核对。
- APIBank：历史 controlled aggregate 的 27 行记录中，按 fraction×policy 聚合，每组 3 次，MPLS 在 0.2、0.5、0.8 的平均 SLO goodput 均低于 LPM 与 DFS-weight。诊断重跑使用 `rank_grouped_result` 明确确认三组平均值排名，不再把未核的逐 seed 排名写成事实；这批历史数据不能直接替代 Figure 9 自身来源。

## 实际工具与轨迹

通用工具现为 `list_research_sources`、`pin_source`、`inspect_records`、`aggregate_records`、`rank_grouped_result`、`compare_sources`、`compare_results`。它们不预写上述三个科研题目的指标或结论。来源列表只返回有界文件名/大小；版本 ID 在每次消费时重新核对哈希；统计和排名需由 Agent 明确选择字段、分组和方向。所有工具失败都留在事件流，不计入可执行候选。

跨三项**数据阶段**轨迹，在最少三个不同任务支持的门槛下：连续序列候选 **0**，已见证的局部参数边 **2**：`pin_source.source_id → inspect_records.source_id` 共 6 次，`inspect_records.dataset_id → aggregate_records.dataset_id` 共 12 次。批量固定多个文件、交错检查，以及 APIBank 的失败后重试破坏了连续序列；不能为了得到 Motif 而事后重排调用。结果保存在 `.local/benchmarks/structured-phase-transfer-20260926/three-task-candidates.json`，可用 `scripts/mine-structured-dsh-candidates.py` 重算。

候选挖掘入口现同样使用 `--trace TRACE_ID IDENTITY_LOCK EVENTS_JSONL`，并核对冻结 manifest／事件哈希及独立研究决定。按新入口重算这三项，仍是连续候选 0、参数边 2，结果保存在同目录 `three-task-candidates-with-identity-lock.json`。旧文件保留为历史记录，不能把其中自由填写的 task fingerprint 当作独立性证明。

**这两条边本身不是可执行 Motif。** 现有连续序列编译器不能接管批量/交错子图。新增的窄 `edge_compiler` 可以从 AppWorld 与 TauBench 的真实调用中分别编译 `pin_source → inspect_records` 和 `inspect_records → aggregate_records`；它只接受契约声明的参数、同一安全片段内的唯一来源，不把交错调用重排为虚假的连续轨迹。DR³ 的独立来源清单轨迹验证了这两条结构边。实际工具重放分别得到 15 条记录，以及 `n=15`、不同标题数 `15`。验证记录在 `.local/benchmarks/structured-phase-transfer-20260926/structural-transfer-check.json` 和 `inspect-aggregate-structural-check.json`。

**这些候选未注册为产品 Motif。** DR³ Agent 的标题计数正确（15 条、15 个不同标题），但附加审阅文字把标题中的 CSDN 条目报为 5，实际为 7，因此完整回答的质量门未通过。结构参数流验证与合格科研交付必须分开。运行时现可把 `group_by=[]` 和结构化 `measures` 作为受校验的语义槽位交接、暂停和恢复，所选字段与指标仍由模型或研究者给出；它们不是从旧任务复制的科研判断。

## Model RSI 新资料清单留出与三节点片段

未参与编译的 Model RSI `candidate-inventory.json` 仅含六份资料的角色、路径、字节数与版本摘要，不含笔记或 PDF 正文。Agent 在只读 MCP 条件下自然调用 `pin_source → inspect_records(records_path="sources") → aggregate_records`，5 次 Flash 请求、12,000 token、5 次 MCP 调用；保守预算预留 US$0.024130。预注册核对：六份资料共 910,008 字节，`model_rsi_week7` 为 870,396 字节，约占 95.6%。回答没有把字节数当作 token 或科学价值，也没有声称读过正文；这是**元数据阶段**的单人核对，尚无盲评。

`chain_compiler` 仅在两个已见证的边共用**同一次** `inspect_records` 调用、且其间无失败/未批准调用时才组合三节点片段。用 AppWorld、TauBench 两项训练轨迹编译，并在 Model RSI 新轨迹上验证，内核实际执行三个工具得到 `entries=6`、`size_bytes=910008`、`max_size=870396`。在 APIBank JSON 对象上沿用空的默认 `records_path` 时，记录检查返回 `rows`、`groups`、`mpls_paired_gains` 三个候选并触发有类型的语义交接；填入 `rows` 后从同一片段恢复，重用已固定来源，完成 27 条、9 组的统计。无关路径不能填入；恢复前来源版本改变会阻断执行。来源版本在每个节点前重验。私有审计见 `.local/benchmarks/structured-phase-transfer-20260926/model-rsi-three-node-heldout-check.json`、`nested-records-fallback-check.json` 和 `nested-records-semantic-handoff-check.json`。

可用 `scripts/compile-witnessed-read-chains.py` 从保存的 DSH 事件流重新编译：两个训练任务各传一次 `--train TRACE_ID IDENTITY_LOCK EVENTS_JSONL`，未参与编译的任务传 `--heldout TRACE_ID IDENTITY_LOCK EVENTS_JSONL`，结果以 `--out` 写入 `.local/`。`IDENTITY_LOCK` 由 `scripts/freeze-dsh-task-identity.py --task-dir ... --decision-id ...` 在每个任务目录生成；它锁定任务 manifest 和事件文件的 SHA-256，编译入口不再接受临时手填的 `TASK_FINGERPRINT`。同一研究决定的不同条件必须使用同一个 decision ID；相同研究问题即使误填不同 ID 也会被拒绝。历史 AppWorld、TauBench、Model RSI 三项已生成本地锁，重新编译仍得两条边、一个三节点候选、零拒绝；三节点 `certified_digest` 与旧产物相同。新输出在 `.local/benchmarks/structured-phase-transfer-20260926/recompiled-three-node-with-identity-lock.json`，状态仍为 `structural_only_not_product_registered`。decision ID 的语义归类仍须研究者核对，哈希锁只能防止事件或 manifest 被悄然替换。

这个片段仍未进入产品库：Model RSI 任务的结构和元数据数字通过，不等于完整科研决定合格，也没有与简单脚本/缓存进行等条件成本比较。上述 APIBank 恢复测试的 `rows` 由测试明确选择；跨多来源的局部重算尚未实现。

随后单独验证了 DeepSeek Harness 的**有界语义端口**。交接只给模型当前研究意图、三个候选数组的记录数和字段名；模型无权调用下一工具或改动统计式。首次提示意外带上验收数字 27，模型 1 次请求、587 token 后选对 `rows`，只能算接口烟测。去掉任务意图中的验收数字后，模型在 1 次请求、580 token 中返回了 `['rows']` 形式；运行时拒绝列表值，没有执行后续统计。把单选提示明确写成“返回字符串而非列表”后再运行，模型 1 次请求、559 token 返回合法的 `rows`，片段复用已完成的 `pin_source` 并得到 27 条、9 组。最后通过 `MotifController` 主控重放同一候选：模型 1 次请求、559 token，`pin_source` 只调用一次，暂停、单选、恢复和统计均由同一主控状态承接。四个请求的费用闸门保守预留合计约 US$0.01154，尚未核对官网账单；私有审计见 `apibank-*-handoff-*-budget.jsonl`、`apibank-semantic-handoff-format-failure.json`、`apibank-semantic-handoff-model-check.json` 与 `apibank-controller-handoff-model-check.json`。这只证明窄数据阶段的一次真实语义交接可用，不能推断科学结论质量或成本优势。

同一 APIBank 来源上另做无模型局部重算：先按 fraction×policy 计数，后改为同组平均 goodput，第二轮只调用 `aggregate_records`，已固定来源与已检查记录均由当前版本的缓存复用；结果见 `.local/benchmarks/structured-phase-transfer-20260926/apibank-local-recompute-check.json`。这说明局部参数依赖可以被执行和观察，**不说明 Motif 优于普通版本化缓存**，后续对照必须把缓存作为独立基线。

## 同题顺序脚本、普通缓存与 Motif 对照

新增 `scripts/compare-structured-read-runtimes.py`，让三组使用**同一份冻结来源、相同 `records_path`、相同两轮统计式和相同底层工具函数**。顺序脚本每轮重新调用三个工具；普通缓存按来源 SHA-256、工具名与参数复用结果；Motif 使用经轨迹认证的三节点片段和自身证据缓存。每组都做来源版本检查，模型请求均为 0。这是结构执行条件，不等同于原生 Harness 的开放式科研任务。

| 资料和两轮问题 | 顺序脚本工具调用 | 普通版本化缓存 | Motif | 结果 |
|---|---:|---:|---:|---|
| APIBank：按 fraction×policy 计数 → 同组平均 goodput | 3 → 3 | 3 → 1 | 3 → 1 | 三组逐组结果相同；均为 27 条、9 组 |
| Model RSI 清单：资料数与总字节 → 最大资料字节 | 3 → 3 | 3 → 1 | 3 → 1 | 三组结果相同；6 份、910,008 总字节、870,396 最大字节 |
| DR³ 检索清单：结果数 → 不同标题数 | 3 → 3 | 3 → 1 | 3 → 1 | 三组结果相同；15 条、15 个不同标题 |

因此，在来源、记录数组和指标都已明确的这三个数据切片中，Motif **没有显示出普通版本化缓存之外的工具调用收益**。毫秒级本地时间受 SQLite、文件缓存和运行顺序影响，不作为速度优势证据。Model RSI 同时是该片段的结构认证资料，本对照只作诊断，不是全新留出质量成绩；DR³ Agent 原始交付还存在错误的来源计数，本表也不替它通过质量门。参数、来源及 artifact 哈希、每轮调用与输出记录在 `.local/benchmarks/structured-phase-transfer-20260926/read-runtime-comparison.json`；测试实例在同目录 `read-runtime-comparison-cases.json`。下一轮应优先找真正需要重新选择来源、工具或证据的完整任务，并与同样允许缓存的普通 Harness 比较；若仍相同，就缩小 Motif 的默认适用范围。

**当前产品判断**：固定三步数据核算先使用普通版本化缓存；三节点 Motif 保留为研究候选，不因从轨迹自动编译成功就启用。下一轮的差异必须来自有实际研究价值的跨来源参数流、语义交接或证据变化后正确的局部失效，并以合格交付的总成本检验。缓存基线也应获得相同的来源版本和可用工具，不能被人为削弱。

## 验证与限制

- `npm run test:structure`：本次对照完成后 219 项通过，包含候选路径交接、单选列表拒绝、主控恢复、恢复前来源变化阻断。
- `npm run connectors:doctor -- --list-only`：六个默认连接器均正常枚举；本地科研工具 13/13，总默认 MCP 工具 87。精简数据条件含上述 7 个工具；它未使用 Zotero、Obsidian、日历、Gmail、文献发现或 Quarto。
- 首轮 AppWorld 普通可用工具条件为 10 请求、259,973 token，报告不完整且 MCP 为 0；它与受限阶段问题范围不同，不能将 token 差额记成 Motif 节省。
- 没有进行人工盲评、官网账单核对、完整跨应用任务或增量事件。已做 Model RSI 留出资料上的结构重放，但它不是普通 Harness 与 Motif 的公平效果对照；现阶段不能说 Motif 已提高完整交付质量或降低总成本。
