# 同题参考文献核验：五条 Native 轨迹与两条 Motif 评测

- 状态：2026-10-10 采集停止。v2 baseline-01 在第 98 次请求触及单次 8000 输出上限，未生成完整报告；五条正式轨迹和两条 execute 均未完成。没有效果或合格报告结论。
- 问题：完整参考文献核验及 PDF 交付过程中，哪些重复控制可以从正常工具轨迹编译并在 Harness 请求前接管？若交付质量下降、不能安全恢复或合格总成本增加，则不支持本轮降本假设。
- 范围：同一私人论文的五个新 Session / 新工作目录是独立运行，不是五个独立科研决定；本轮只有同题重复诊断认证，不冒用生产库的独立任务认证。用户最终要求已冻结在 `scenarios/paper-submission/reference-audit.prompt.md`，各组不追加检查线索。

## 对照与复现

服务器加载 `.local/remote-env.sh` 后使用统一入口：

```sh
node scripts/project.mjs python scripts/paper-reference-experiment.py --experiment-id paper-reference-five-native-two-motif-20261010-v2
# 以下 collect / compare 启动真实付费任务，仅在已授权剩余额度内运行：
node scripts/project.mjs python scripts/paper-reference-experiment.py --experiment-id paper-reference-five-native-two-motif-20261010-v2 --phase collect --call-model
node scripts/project.mjs python scripts/paper-reference-experiment.py --experiment-id paper-reference-five-native-two-motif-20261010-v2 --phase compile
node scripts/project.mjs python scripts/paper-reference-experiment.py --experiment-id paper-reference-five-native-two-motif-20261010-v2 --phase compare --call-model
```

以上是 v2 当时的历史命令（执行代码摘要 `819c0ef0896a90eb86224c7e96ea1ad5488a289da1447498cd2c3e1f68f2829d`）；当前入口已准备改为 16000 输出，不能用当前脚本冒充重现 v2 的配置。原执行代码位于私有 `code-history/executed-controller.py`；复现须在隔离的同路径 checkout 恢复该版本及其依赖摘要，不能直接运行嵌套备份文件，因为它由文件路径确定仓库根。

入口默认只预览。各运行只有一份原始 ZIP，模型自主使用原生工具，不配备论文 MCP、预制场景 DAG 或预生成脚本。第一至第三条用于训练，第四至第五条留出验证；随后冻结库再评测，不用评测输出反向认证训练库。`--start-index` 仅用于已有运行结束后继续未创建的编号，禁止覆盖旧运行。

- 题面 SHA-256：`6199102371fc38c05912b76596bb6c48cbde4ee1eb157bafe0cae4eae0de4a89`。
- 私人 ZIP SHA-256：`7aafe2468ac50d69c23c3dab719213b47406b2c33efe55dc911c361f25360027`；原件不改，不进入 Git。
- 配置：`deepseek-flash`，`reasoning_effort=off`，压缩关闭，原生工具 schema 集合/顺序保持一致，每次输出上限 8000，无请求次数上限。获准非沙箱终端，仅本次私人实验副本；不投稿、不改原件、不写外部应用。
- 环境：服务器 Ubuntu 22.04 / 内核 5.4，隔离 Node 22.23.3、Python 3.10.8、Harness 0.1.5-rc.3；基点 `2368235f274329be6227a8393b850633cb943da4`，有未提交工作。逐运行 manifest 保存实际配置、公共代码摘要、原始请求/事件、工具边界文件版本和账本。当前自动代码快照未覆盖全部新原生插件文件，需补充实际执行版本审计，不声称完整采集。
- 私有根目录：`.local/paper-reference/paper-reference-five-native-two-motif-20261010-v2/`。每条运行 `manifest.json` / `agent-events.jsonl` / `file-versions.jsonl` / `requests/` / `cost-ledger.jsonl` / `metrics.json` / `answer.md` 与产物不提交。

## 失败预试与预算

先前 ID `paper-reference-five-native-two-motif-20261010-v1` 的 baseline-01 使用同题、同输入、输出上限 3000，49 次真实请求后以 `max-tokens` 结束，没有报告 PDF。代理新增估费约 0.05933312 美元。此运行不混入五条正式样本；实际控制器保存于该私有 ID 的 `code-history/executed-controller.py`，不追改旧结果。

v2 将所有正式 5+2 的输出上限统一提高到 8000，其他任务条件不变。旧 Native/PTC、论文 MCP Motif 与此预试均继续计入累计论文 1 美元预算：v2 开始前共 303 次请求，代理约 0.33153306 美元。中间控制台金额可能包含在途请求的保守预留，只有结算 ledger / metrics 才能报告本次费用；账单实付未知。若预算不够，停止并报告未完成数量，不换 ID 重置费用。

## 原生诊断协议

`native_motif_compiler.py` 从真实工具轨迹编译两类受限候选：有实际文件字节版本和结果摘要的本地只读续接，以及真实后台任务句柄到 `job_output.job_id` 的传递。至少两条训练运行支持并由一条留出运行验证；后台句柄证据按运行与会话内 ID 区分，不能将不同 Session 的 `bash-1` 混为同一个任务。禁止将模型生成的任意 Python / shell 程序直接重放。

`dsh_native_motif.ts` 使用共享 `attachMotifInterceptor`，绑定 Session、原始题面、人类输入不变、ZIP、工具 schema。只读节点把已认证 argv IR 重新生成字面参数，不求值原始 shell 文本，检查路径/字节和真实输出。后台读取仅限 Harness registry 确认由本会话拥有且已结束的任务，不创建/杀死后台进程、不忙轮询，读取真实增量输出。只有真实结果核验通过才计 verified skip；失败交回模型。空候选库照常走原生模型，不强行凑接管次数。

最终代码两端全量开发回归均通过 166 项 Python、51 项 Node；这不是效果或交付质量认证。新协议未接入 Web，也未做 Windows 验收。

## 已观察与待验收

第一条正式基线原生行为包括后台检索、长时间等待、补查来源和中文 PDF 生成。第 98 次模型输出在报告生成脚本的工具参数尚未结束时截断，Harness 正确返回 `max-tokens`，工具没有执行。采集器按失败策略停止，不继续污染训练集。原始主稿含 `\nocite{placeholder}`，现有稿件缺少可直接采用的完整渲染编号依据；模型自行生成 `\nocite{*}` 文献专用副本，列出 314 条。此前修复编译副本的 34 条不能冒称当前原稿编号。

后续评审必须检查：是否交付可读 PDF；是否明确编号重建依据；是否覆盖实际论文引用且区分未纳入正文的文献库条目；逐条真实性/版本结论是否有可复核来源；P0–P3 与统计是否一致；逐页无乱码、裁切、表格越界。模型结束、PDF 存在、检查质量合格分别记录。未经盲评不比较“合格成本”；不能从同题重复运行推断跨论文泛化。

v2 baseline-01 结果：98 次真实请求，未缓存输入 149729、缓存输入 10792704、输出 42851 token；新增代理估费 0.161096124 美元，耗时 2957.904 秒；实际工具调用 bash 98、read 4、todo_write 2、job_output 1。原始 ZIP 未变。模型阶段未完成，最终报告 0 份，质量不合格（未交付），未执行逐文献真实性评审。

自动标题筛选找到 `report/test2.pdf`，仅一页测试中文渲染，不是报告。Codex 在本地渲染该页后确认表格右侧越界；未修改或交付。原 `metrics.json` 保留，不追改候选列表；补充审计为私有 `review/codex-qa.json`。今后候选检测显式记录 `candidate_only/font_test_only`，仍不能代替最终质量评审。

累计请求 401，代理约 0.4926292 美元（逐账本舍入值与单运行浮点累计末位略有差别），剩余约 0.5073708 美元，账单实付未知。曾误将控制台在途预留当已结算金额并建议提额，已向用户纠正；没有因此提高额度或发起新付费任务。此后依据两次实际失败，已询问是否授权累计 3 美元重跑 5+2；答复前保留 1 美元。

后续配置已准备：`paper-reference-five-native-two-motif-20261010-v3`，输出统一 16000，题面/ZIP/schema/模型/推理不改，`--budget-usd` 默认 1，只有明确获准才可传 3；未启动付费采集。新 manifest 扩展实际代码与锁文件摘要，保留旧控制器历史；编译必须有五条已完成运行，不能将 98 次失败冒称五个任务，也不能用一条轨迹强行认证库。五个新运行自身仍须核查交付质量。

目前原生诊断开发、人工复核/维护成本未货币化，不能忽略；没有节省或完整闭环结论。服务器非沙箱条件下，新目录不构成文件系统隔离；还须审计后续运行是否读取了其他运行的答案/轨迹，发生污染的样本不能作为独立运行认证。
