# 第二个入口 Motif：清单到 PDF 准备（实施前接口记录）

2026-10-12，用户授权继续学习第二个 Motif，并做普通 Harness / 一个 Motif / 两个 Motif 的完整任务对照。优先结构学习和实际模型请求、输出 token，不扩展产品闭环。原 PDF、原始事件、预算和上游 Harness 保持现有入口。

## 发现与认证边界

原生任务 f780c803077e4bbfaeeb29d417ec945a（三篇）与 11c8a8e02b7a4e278f0fb61866cca9f5（两篇）先执行 list_pdfs，再准备清单中的所有 PDF。prepare_pdf 参数来自 papers[].paper_id；有原生模型消息、usage、工具参数和成功结果配对。实际准备顺序可以不同，学习集合完整覆盖，在线按工具清单顺序调度，不学习相关性排名。

已有一篇独立问题的历史轨迹使用旧解析器，当前导航/版本重放不同，不能用于认证。保留该拒绝依据，另跑一个普通 Harness 单篇新问题作为认证；认证完成前不得加载在线执行。准备结果包含 cache_stats，故原契约 replay_stable=false 保持不变；来源/解析版本及除 cache_stats 外的所有输出逐项重放一致，缓存统计保留原值，不声称逐字相同或工具缓存为新 Motif。

## 所需共享接口变化（先记录，再实施）

1. entry_compiler.py 增加清单前沿见证/编译：唯一零参数清单读取 → 返回数组的单一字段 → 对全部选中项执行单参数准备 → semantic handoff。复用原 library/独立认证摘要，拒绝未选目标、重复、失败、运行时生成、先做语义选择或不完整覆盖。允许受来源守卫的 read-only 非 replay_stable 工具，记录唯一 cache_stats 投影例外。
2. 新受限在线 inventory_entry_policy.ts，协议 sss-entry-inventory-v1：一个 source 工具、一个 foreach 工具、固定数组/ID/版本字段、≤20目标/每批≤8。先核对清单 task_sha256、完整冻结清单、question；参数必须从实际清单返回对象获取，再核对逐文 PDF/解析版本。低文本/版面诊断原样交模型，不自动 OCR 或科学判断。
3. 现有 entry_read_policy.ts 验证/控制入口分派到新协议，sss-entry-read-v1 行为保持；现有固定 Harness 插件复用原工具流/Session/提示守卫/预算。SDK allowed_tools 校验扩为策略声明的全部工具，不增加任意模块或任意代码执行接口。

## 场景接入与实验

run-pdf.py 增加显式 --entry-policy，生成本次来源冻结 task；agent.ts CLI/程序选项增加 reading_entry_policy、claim_entry_policy。两项都默认关闭；第一轮已有证据 support_audit 可用旧 claim Motif，后续缺口修复与综合继续普通 Harness，保留已知负面结果。旧 manifest 与 entry 策略互斥，增量路径暂不启用阅读入口策略。Web/HTTP 不接收客户端策略路径。

完整任务三组用相同问题、论文、工具、预算、自动核源和复核/综合要求，仅入口结构不同。冻结实验代码/策略/来源，交错顺序，全部失败、重试和续接费用保留。直接替代的清单/准备请求与后续随机语义路径分开；机器来源门槛不是专家支持判断或新材料泛化。学习/认证原始阶段费用单列，开发成本未知。不要求胜过手写脚本。

共享改动后执行 npm test、免费真实 Harness/MCP 检查与 smoke；付费前查看 SDK 预览与实验协议。实测后补充结果和最短复现入口。

## 实施情况

已实现上述三个共享接缝及两个场景选项；没有更改上游 Harness、原 ToolContract 标志、旧 contract_signature/manifest/计价。新增 guarded inventory_contract_signature 是显式的受来源保护准备协议，初次离线编译因旧 contract_signature 正确拒绝非 replay-stable 工具而失败，未放松旧规则；失败目录与原因保留。

新认证原生 run `2e41d77733184d0b9580ff92554115fe`：单篇不同问题，12 HTTP200 / 输出3236 /估费USD0.015132576，reading 草稿来源门槛通过、0缺口，科研支持未独立认证。学习3/2篇、认证1篇的入口均2个provider请求；完整历史三阶段30请求/USD0.078250040，编译新增请求0。策略摘要 `2b9243713dcc60702c8e2486b217620de24f6ff34470c5ee5b46c89be67aa927`。旧单篇轨迹解析器不同不认证。

免费真实 Harness/MCP：新入口4个实际调用（清单+3准备）与重放一致，2核验批次，mock provider 1 /真实API0；旧claim入口5个真实读取与重放一致。npm test：413 Python、79 Node通过、3可选Docker跳过；场景独立27 Node通过。smoke 通过、API0。协议/原始日志在私有 `.local/literature-notes/inventory-motif-20261012-9af4e5f0`。

## 完整对照与提交范围

已完成两个新问题、每组三轮、18完整任务/65原生子运行，共446请求/USD1.313175240；本轮加新认证共458/USD1.328307816。三篇任务H/单/双自动合格2/1/0次；两篇任务2/1/3次。两篇双Motif请求30→25.33、输出13686.67→12354.33，费用高0.52%；三篇双Motif输出增加且0/3合格。不支持全局组合默认启用，旧Web/SDK普通入口默认不变。详细失败、缓存费用分解与原生请求证据见[完整实验](../experiments/inventory-motif-20261012-9af4e5f0.md)。

建议GitHub提交标题：`学习并认证 PDF 清单准备前沿，增加完整任务 Motif 对照`。正文须说明：新增受限清单数组绑定协议及离线见证；旧协议/契约/预算不变；来源/解析器/提示/schema失败回到模型；场景两个选项显式开启，第一轮复核以外保持native，HTTP拒绝策略路径；真实实验有任务依赖的请求/token收益及质量失败，费用尚未降低。不要写“实现通用RSI”或“整Agent已可靠降本”。

本次文件：共享 `entry_compiler.py` 增量、`inventory_entry_policy.ts` 新增、`entry_read_policy.ts` 分派、`scripts/run-scenario.py` 全工具允许集校验；场景 `inventory_entry.py`、`learn-inventory.py`、`check-inventory.py`、`compare-frontiers.ts` 与 `run-pdf.py`、`agent.ts` 接入；对应 Python/Node边界回归及中文接口/实验/交接文档。没有改前端、依赖或上游，没有提交私人策略/资料/原始日志；工作区原有改动保留，尚未commit/push/PR。
