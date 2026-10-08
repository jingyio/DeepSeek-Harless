# WPS 实验记录 → 组会简报（合成 mock）

这是一套**虚构数据、只读执行**的开发夹具。它检验 WPS 可编辑的 `.xlsx` 输入、数值复算、依赖失效和 Quarto 交付；不代表真实科研质量、Motif 收益或模型费用节省。`run_mock.py` 是普通确定性脚本基线，不是 Motif 算子。

## Agent 任务扩展

用户指出固定表格到固定简报的整个任务可由脚本完成，因此新增[Agent 可见任务](agent_task.md)：研究者要在有限算力下，结合实验数值、Obsidian 旧状态和两篇虚构论文批注，决定组会上建议先做什么。`run_mock.py` 只完成其中的数值复算与变更守卫；它没有读取笔记和批注，也不会替研究者作证据取舍。独立的[评审包](agent_review.md)不应交给 Agent。

`mock_apps_server.py` 在一个**模拟 MCP** 中分别提供 WPS、Obsidian、Zotero 的限定只读对象；每个对象先固定版本再读取，旧句柄在来源改变后失效。它与真实三个应用的连接器不同。MCP patch 为 `config/wps-meeting-agent-mock.patch.yml`，可挖掘的工具契约为 `config/wps-meeting-mock-contracts.json`。`tests/test_wps_meeting_agent_mock.py` 检查了三类来源、版本失效和 MCP 连接。此扩展只准备了一个合成研究决定，尚未产生原生 Agent 轨迹或合格 Motif；不能把初始和两次更新当三个独立任务。

用项目的 `.venv312/bin/python -m unittest tests/test_wps_meeting_agent_mock.py` 运行无模型检查。若以后运行付费 DSH，应先冻结 Agent 可见包、隐藏评审包和费用上限并取得研究者确认；单次合成 Agent 试跑只供开发诊断，不报告 SSS 增益。即便一个特定 mock 可以事后写出专用脚本，也要以未见过的不同任务检验是否存在不能由普通脚本或缓存同样解决的局部复用价值。

`scripts/run-wps-meeting-agent-mock.py` 的默认模式生成 `.local/benchmarks/wps-meeting-agent-mock-v1/native-03/PREVIEW.json`，冻结任务、模拟来源、评审规则和执行代码的哈希。已验证缺少与预览匹配的明确批准时，`--call-model` 在发出任何付费请求前拒绝执行。获批准后运行的一次原生 DeepSeek Flash Agent 开发试跑由本地 US$1 费用门限保护，最多 10 个模型步骤，每次输出上限 3500 token；产物和逐请求记录保存在 `.local`，不提交仓库。`native-02` 的评测污染和关闭内置文件、shell 工具后的 `native-03` 复跑见[试跑记录](agent_trial_result.md)。当前 runner 的 `native-03` 槽位已用，不能重复付费执行。合成试跑不能估计 SSS 相对原生 Agent 的增益，因为当前没有适用于此工具集的已认证 Motif，也只有一个独立合成研究决定。

## 文件与运行

- 表格：[experiment_log.xlsx](../../outputs/wps-meeting-mock-v1/experiment_log.xlsx)。六条虚构运行记录，WPS 可打开并修改。
- `mock_contract.json`：模拟已审阅表述及其精确数据依赖，另有两种增量事件。
- `build_workbook.mjs`：重建表格。使用 Codex bundled `@oai/artifact-tool`。
- `run_mock.py`：只读表格，在内存中施加事件，复算并生成 Quarto 草稿。需要 `openpyxl` 和 `quarto`。

示例：

```sh
python benchmarks/wps_meeting_mock_v1/run_mock.py --scenario base
python benchmarks/wps_meeting_mock_v1/run_mock.py --scenario duration_update
python benchmarks/wps_meeting_mock_v1/run_mock.py --scenario result_update
```

重建 `.xlsx` 前，需让 `build_workbook.mjs` 所在目录的 `node_modules` 指向 Codex bundled Node 依赖；该链接被本目录的 `.gitignore` 排除。运行脚本使用含 `openpyxl` 的 Python 环境。常规试用只需打开现成的表格并运行上述命令。

输出在 `outputs/wps-meeting-mock-v1/reports/`：各场景的 HTML 简报、可编辑 QMD 和 JSON 决策记录。

| 场景 | 变化 | 正确行为 |
| --- | --- | --- |
| `base` | 冻结的初始输入 | 使用模拟已审阅表述，复算 71.0% 与 79.0% |
| `duration_update` | 候选运行耗时由 103.8 秒变成 97.8 秒 | 更新耗时表格；正确率结论依赖未变，可沿用模拟表述 |
| `result_update` | 候选运行正确数由 80 变成 63 | 复算正确率；旧表述失效，生成待语义复核的报告，不生成新科学结论 |

输入校验拒绝重复运行、缺失或错误的分母、错误的正确数、未知来源、配对种子不齐和结构变化。事件还检查旧值，防止在错误版本上应用更新。WPS 云文档 API、真实事件订阅、Obsidian 主张读取、Motif 挖掘／执行和模型交接均**尚未接入此 mock**。未来如需把它用于方法评测，应先取得不同真实任务的轨迹，并与这个脚本及版本缓存公平比较；合成事件只能作守卫回归。
