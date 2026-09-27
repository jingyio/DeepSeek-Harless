# 实验更新后的组会决定：合成开发基准

这是**合成数据与模拟应用**，用于先检查 SSS 的跨工具参数流和完整模型请求机会。它不是 WPS 云端、Obsidian 或 Zotero 的真实连接成绩，也不代表科研结论。四题是四个不同的研究决定；同一题的后续更新仍只算同一题。

## 任务

研究者收到一条新实验结果事件，需要给组会做一页待审决定：旧主张能否维持、要收窄到什么范围、下一个最小检查是什么。允许“资料不足”。Agent 可见任务仅给事件 ID、问题和只读范围，见 `tasks/`。隐藏评审包见 `review/`，不得放进 Agent 上下文。

| 独立题 | 表格指标 | 旧主张的风险 | 必须由语义层处理的缺口 |
| --- | --- | --- | --- |
| `family_shift` | 正确数／测试数，已见与未见家族 | 总体上升掩盖未见家族下降 | 是否应收窄泛化主张；先查划分还是补实验 |
| `label_audit` | 正确数／测试数，已审与待审标签 | 总体增益主要来自待审子集 | 待审标签能支持什么；审计与重复实验如何取舍 |
| `hardware_latency` | 总耗时／请求数，快慢设备 | 设备构成变化形成总体延迟优势 | 能否归因于方法；同设备配对测试优先级 |
| `novel_queries` | 正确数／测试数，全新与重复查询 | 总体上升掩盖全新查询下降 | 能否扩大检索试点；先去重还是补测试 |

每题的事件公开当前与上一轮实验对象 ID，上一轮版本哈希由事件固定。只读 MCP 工具从事件返回对象、固定版本、读取表格结构并生成数据编号；复算或抽查原始行必须使用该编号。Agent 自己选择分组并判断科研含义。`sources/` 分别保存两版 WPS 可打开的 `.xlsx`、模拟 Obsidian 主张、模拟 Zotero 批注、指标契约和事件。模拟论文批注均明确标记为虚构。工具**不会**判断是否修改旧主张。

## 机制机会与公平对照

可能的局部参数边是 `read_change.experiment_id → pin_object.object_id`、`pin_object.source_id → read_pinned_object.source_id`、`read_pinned_object.value.dataset_id → aggregate_pinned_experiment.dataset_id`。这些只是**预登记机会**，不是已挖到的 Motif。普通 Agent 必须先自由执行；前两题轨迹用于发现与编译，第三题用于独立认证，第四题才做同题普通 Harness 与 Motif 对照。不能把任务说明、`script_baseline.py` 或模拟事件转成手写 Motif。

一条模型请求能否真正省掉，取决于普通 Agent 在读到事件或固定来源后，是否还要请求模型来填写后续工具参数。若普通 Agent 同轮已经计划了全部读取，或后续必须选择分组和解释含义，本题也可能产生 **0 次有效跳过**。预登记的唯一计数口径是相同交付质量下，实际 API 请求数、缓存命中／未命中 token、费用、耗时和人工修订。工具调用次数或脚本 0 次模型请求不等于 Motif 增益。

`script_baseline.py` 是强对照：它能跨四题完成事件读取、版本固定、两个维度的数值复算、旧主张和批注读取，0 次模型请求，然后明确停在科研判断处。可把它的证据包交给**同一个模型**写决定，与普通 Harness 和 Motif 比较；记录脚本维护成本，但不得用维护成本替代运行时费用。若脚本加模型同样合格且更便宜，SSS 在此任务族没有被证明有额外价值。

## 本地运行

```sh
.venv312/bin/python benchmarks/meeting_decision_chain_v1/build_fixtures.py
SSS_MEETING_CASE=family_shift .venv312/bin/python benchmarks/meeting_decision_chain_v1/mock_apps_server.py
.venv312/bin/python -m benchmarks.meeting_decision_chain_v1.script_baseline family_shift
.venv312/bin/python -m unittest tests/test_meeting_decision_chain.py
```

MCP 服务器使用 stdio；第二条命令会持续等待客户端连接。测试时一个 Agent 进程只挂载一个 case，工作目录放在 `.local`，仅暴露本 MCP 与交付所需的工具；不得把 `sources/`、`review/` 或构造脚本复制进 Agent 工作目录。Agent 不应有直接遍历仓库的 shell 权限，否则该模拟应用隔离就不成立。若要用真实 WPS 数据，须另接真实来源并重新冻结权限、版本、评审和预算，不能把本夹具的成绩外推。

DSH 工具补丁见 `config/meeting-decision-chain.patch.yml`，用于轨迹编译的工具契约见 `config/meeting-decision-chain-contracts.json`。契约只声明工具参数与可观察输出字段，不预写执行 DAG；是否形成候选 Motif 取决于实际调用轨迹和独立留出认证。

v1 的四题试跑与成本归因见 `experiments/组会决定链Motif前瞻试验_2026-09-27.md`。它测到在线整轮跳过，但没有合格交付总成本收益。v1 原始轨迹和结果留在本机 `.local/benchmarks/meeting-decision-chain-v1/`，不得拿它们认证下面 v2 新工具契约。

## v3：新版工具契约与重复对照

MCP 的参数 schema 现在明确区分应用对象 ID、`pin_object` 返回的 `source_id`、实验表返回的 `dataset_id`；依赖查询仅接受当前 `experiment_id`。无效格式在工具入口拒绝。新版工具说明对普通组和 Motif 组完全相同。交付提示也对两组固定为可直接渲染的 Markdown 正文。正式新版记录存放在 `.local/benchmarks/meeting-decision-chain-v3/`，与 v1 隔离。此前 v2 的三项普通组试跑揭示了“上一版实验被错传给当前依赖查询”的接口缺口，因此只作诊断，不参与 v3 编译或成绩。

先在 `family_shift`、`label_audit` 的**新版普通 Harness**轨迹上重新发现参数边；再用 `hardware_latency` 的新版轨迹独立认证。`site_transfer`、`tail_terms`、`lot_stability` 是三个新决定，只用于前瞻效果对照，不准进入编译、认证或阈值调节。其封存判定标准在 `review/v2_criteria.md`。每题普通组与 Motif 组均使用同一任务、工具、模型和输出格式，分别记录调用错误、跳过的模型请求、所有请求的输入/输出/推理 token、缓存命中、费用、时间和人工修订；特别对照最后写稿前与最后一次写稿的用量。先按质量合格判定，再比较合格交付总成本。

任务全部仍是合成夹具。工具说明修复后的效果若成立，也仍需在真实跨应用科研决定上验证。多次独立任务可以减少“单个会话波动”的影响，但不能把三个相似的合成决定当成广泛科研使用证明。
