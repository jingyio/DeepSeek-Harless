# 文献Agent：逐论断自动补证据、修复与直接交付

用户希望普通PDF文献Agent直接给结果，不以人工审批为交付前提。本次补上“自动审阅发现证据缺口后，同篇检索/补读→缩窄或撤回→有界停止→直接交付”路径。模型判断支持关系，场景Runtime管理身份、来源、范围和停止条件。

## 范围及接口

本轮无共享核心、上游Harness、预算代理、依赖或Motif IR接口变化。沿用现有Harness、场景MCP及预算启动器；开启逐论断审阅时替代旧整稿审阅，避免相同字段重复进入两次审核；设repair_rounds=0仍可做旧路径对照。在线协调位于场景TypeScript，Python只负责既有MCP/离线输入封装及收据回收，没有新增Python模型循环。此前共享自动续接变化另见`approved-plan-continuation.md`。

| 文件 | 变化 |
| --- | --- |
| `scenarios/literature-notes/agent.ts` | `repair_rounds=1`默认，可设0–2；`repair_only`/CLI `repair --job`冻结已有稿，只增加补证据阶段；记录每轮、停止原因、全部实际费用。 |
| `agent-support.py` | 第一轮选所有字段，以evidence_first_reextract隐藏旧句独立重提取；后续只选缺口/数值缺口；冻结输入摘要，后续保留原论断导航；打包前绑定当前审阅工件。流程文件变更使旧完整结果缓存失效。 |
| `pdf_repair_tools.py` | 四工具、逐论断读取权限、同篇检索/补读上限、实际相邻引文上下文、分批有效决定暂存、数值/引用/来源检查、完整发布与双摘要收据。 |
| `pdf-repair-scenario.json` / `pdf-repair-task.md` | 公开工具白名单及支持范围、字段含义、缩窄与撤回的规则。 |
| `repair-pdf.py` / `review-pdf.py` | 复用`run-scenario.py`；优先收原生工具事件见证的最终收据，pending决定不算交付；无收据时可验证原生最终模型JSON提案，严格区分回收来源；绑定修订稿、审阅audit、输入和修复计划摘要。 |
| `pdf_repair_recovery.py` / `recover-repair.py` | 对原生日志中最终模型JSON提案做离线回收：严格形状/目标绑定，重放实际读工具并核对观察，校验每项；不合格提案标技术缺口，零新模型。`receipt_origin=validated_model_final_json_recovery`独立记录，不伪造原生模型提交。 |
| `agent-ui.html` | 修复进度、各轮统计、失败警示及续修按钮；比较表/笔记直接交付，无人工勾选门槛。 |
| 相关Python/Node测试 | 参数来源、分批失败隔离、尝试上限、失效、只读MCP、原生收据、费用、无需审批交付。 |

场景新增MCP接口：

- `read_claim_repair_packet(claim_id)`：第一轮隐藏旧句/status，只返回字段名、实际原引文和同窗口相邻片段，以避免抄回旧错误；比较模式返回当前论断；后续轮有来源重放的原论断导航。引用许可限于该论断，不代表语义支持。
- `search_claim_evidence(claim_id, query)`：字面导航，最多2次/论断、每次最多3命中；未命中不证明全文没有报告。
- `read_claim_evidence(claim_id, page, start=0)`：实际读取同篇窗口，最多3次/论断、6000字符/窗口；失败尝试同样占额度。
- `submit_claim_repair(decisions, synthesis_hypothesis)`：可分批提交。第一轮独立重提取只允许revised或缺口；比较模式中显式`supported`的原句/引用由Runtime精确复制；`revised`需要模型选择的实际证据；缺口文本由Runtime写入。错误返回具体claim_id、缺失数字、允许的引用身份和剩余次数，其他有效决定保留。每项最多3次事实校验尝试，耗尽后仅能显式留缺口。所有目标都有有效决定才发布完整工件，非目标字段逐字保留。

`repairing`表示额外复核中；`repair_stop_reason`区分无未解决项、轮次上限、预算不足及`stage_failed`。完整账本下，额外语义阶段失败可停止并交付上一份来源校验通过的稿，标注`repair_warning`，不能假称修复成功；来源/配置变化、账本缺失或工件绑定不合法仍失败。原始PDF、旧任务和失败日志不修改。CLI `recover --job`仅用于完整账本下未完成提交的原生结构化提案；生成新任务并单列历史费用，不将历史阅读/提案成本藏进“0费用”。普通修复启动器在缺原生提交时也使用同一离线校验回收逻辑。

## 参考及验证边界

借鉴AutoTool的参数流、G-Agent的局部片段与来源、结构—语义分离的有界交接、Stagehand的探索/重放/失效及数据分析Agent的真实账本对照。落实与不适用处见场景`reference-design.md`。

新工具中的参数复制、相邻上下文和暂存属于普通程序优化；本轮未从新修复轨迹训练/认证新Motif，也未证明新工具可以跳过语义判断。第一次全字段审阅会新增费用；需要同质量的普通Harness/脚本/缓存/Motif对照才能宣称RSI净收益。自动审阅可能漏检，直接交付不等于专家质量认证。

验收保留失败实验和真实请求费用，不用“改成revised”“零结构缺口”替代语义质量结论。实验记录见`docs/experiments/claim-repair-20261010.md`。私有论文、密钥、工件和原生日志仍在忽略目录中。本轮未提交、推送或创建PR。
