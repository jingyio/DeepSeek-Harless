# 论文 RSI：查询恢复工具与已完成节点（第二轮完成）

- 实验 ID：`paper-rsi-overnight-20261011-v2`，2026-10-11。
- 沿用第一轮累计8美元授权，旧费用/失败不重置；实际跳过0，暂停execute。
- 同一篇论文的同十种变体，重新运行其中3条baseline、7条shadow。不是十个新独立任务，也不是独立论文盲测。

## 假设与变化

上一轮43次预测有7次下一操作不符，部分发生在重复读取后；原生模型还反复重组标题检索URL。假设：把已出现的完整标题查询参数化为只读MCP，并记录当前版本下已完成的局部节点，可以扩展只读衔接并减少错误触发。

- `src/adapters/paper_query_recovery.py` 从前三条第一轮baseline学习URL信封与当前原始标题的完整词/前缀转换，保留见证、来源摘要和查询协议版本。实际冻结库只有 **1个Crossref协议、1个Session见证**；不能称为认证工具。第一轮全部10基线还可挖掘出3种查询信封，但该诊断库没有用于本轮留出。
- `recover_pinned_formal_reference_queries(citation_id)` 绑定当前引用与原始标题；固定Crossref/DBLP域名、只读GET、最多2种信封/30请求、结果限额/超时/来源变化守卫。默认不注册；通过私有编译库显式启用。
- **没有DBLP成功见证**：原生工具取得HTTP200机器人验证页，编译器拒绝作为元数据证据；不能为补覆盖虚构一个DBLP成功协议。
- TypeScript observer增加已完成节点表，使用当前工具参数、Session及来源版本；失败刷新清除旧成功，新pin重置。不执行候选或注入模型结果。
- `scripts/paper-rsi-recovery.py`：新条件预览/初始化/基线/冻结编译/真实shadow。
- 相同工具、顺序和提示用于本条件两组。提示进一步约束工具阶段无旁白、查询恢复及失败编辑后读取。第一轮没有这些条件，不能把条件间差异全归因于Motif。

## 实测

| 变体 | shadow请求 | 严格整请求匹配 | 比例 |
|---|---:|---:|---:|
| 缺失引用键 | 17 | 7 | 41.2% |
| 重复条目 | 18 | 6 | 33.3% |
| 错误arXiv标识 | 13 | 3 | 23.1% |
| 错误年份 | 14 | 3 | 21.4% |
| 错误DOI | 14 | 7 | 50.0% |
| 另一引用子集 | 13 | 6 | 46.2% |
| 增量引用 | 25 | 5 | 20.0% |
| **合计** | **114** | **37** | **32.5%** |

53次请求前预测：37严格匹配、13工具匹配但有文本、2下一操作不同、1工具失败/版本结果缺失；61次无预测。严格口径保留所有非空文本和模型写/改/终结请求，不将局部节点数或跨请求工具合并估算冒充整请求替代。

全部10次运行completed，集合/结构/来源通过。语义质量未盲评，最终PDF未验收。前三训练任务实际11/24/20请求，共55次；相同输入第一轮9/11/16，共36次。**内化查询并不保证基线请求下降**，新工具也未消除网页查证和报告修复，不能根据shadow比例宣称成本节省。

本轮共169次真实模型请求，新增代理估费约0.22846494美元，累计约5.41715402/8美元，账单未知。失败编辑、恢复、重复查询全部计入。

## 配置、复现与数据

- 模型deepseek-flash/off/8192输出，无请求次数限额，无压缩，既有非沙箱授权；服务器执行，不改原件、不投稿。
- 私有根`.local/paper-reference/paper-rsi-overnight-20261011-v2/`；`manifest.json`保存有效配置/代码/来源、每次请求保存真实body与用量。原始材料与凭证不提交。
- 查询库摘要：`35512689085d2803031957119b6d3e30a9e43dda509b993d131eeee219172c11`；仅前三第一轮baseline训练。
- 流图库训练本轮前三baseline，先冻结后运行其余7条shadow；后续第三轮不修改此库。
- 两端251 Python/109 Node回归通过；真实MCP预检12工具，5次恢复查询均返回有类型的候选或空结果，原始证据保留。
- 用户新授权摘要沿用`a7c0dab9b74bc7c0e9475cf6a056613896e53cab7dd3268b193dc13157067031`。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-recovery.py --phase preview
node scripts/project.mjs python scripts/paper-rsi-recovery.py --phase setup
node scripts/project.mjs python scripts/paper-rsi-recovery.py --phase baseline --case t01_main --call-model
node scripts/project.mjs python scripts/paper-rsi-recovery.py --phase compile
node scripts/project.mjs python scripts/paper-rsi-recovery.py --phase shadow --case t04_missing --call-model
```

完成运行不可覆盖。冻结库按其manifest代码摘要复现；第三轮只允许明确记录的离线编译器/shadow observer迁移，改变实际工具、提示或来源实现必须重新训练。

## 结论与边界

在此论文分诊条件下，已观察到请求前严格匹配从第一轮21.4%到本轮32.5%，但不是相同条件下的因果节省证明。当前最好的单任务是50%，不是普遍可达比例或全局算法上限。真实跳过和节省账单均为0。

源字段绑定与局部已完成状态有维护价值；查询能力从历史脚本/URL进入MCP后，仍需下一步的学习衔接来减少模型调度。频率、HTTP200、旧网络内容、语义状态不构成自动执行授权。

第一轮发现的Crossref404误判、引用键年份误判与无正式版证据的P2问题仍是质量验收风险；报告结构通过不能掩盖它们。应先独立评审来源/版本判断，再讨论execute与合格总成本。
