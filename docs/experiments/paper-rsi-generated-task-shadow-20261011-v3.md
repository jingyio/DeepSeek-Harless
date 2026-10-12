# 生成工具的正常使用、局部 Motif 编译与前瞻 Shadow

2026-10-11，Codex。状态：完整机制链已跑通；尚未证明整请求替代或实际降本。代码未提交、未推送。

## 本轮验证什么

上一轮由 DeepSeek 从正常 bash 轨迹选择目标并生成 `triage_catalog_coverage`。本轮保持该算法和冻结库不变，让它参与新的正常报告修订，再从实际调用学习续接关系。实验不是完整论文修订，也不重新核验文献真实性。

假设是：同一生成工具在不同引用范围中复用后，历史轨迹能产生带当前参数绑定的局部 Motif，预测下一任务的工具调度。如果模型选择不同操作、报告或来源变化，则不能计为匹配。

## 任务、划分与质量门槛

训练使用同一私有论文的主稿 `t01_main`（15 对）及摘要 `t02_abstract`（5 对），两个独立正常 Session。冻结后评测 `t09_subset_b`（5 对）和 `t10_incremental`（8 对）。后二者是同论文的合成引用范围，不是两篇独立论文，也不是新的外部科研决定。

输入是历史分诊报告的私有副本，注入缺失一项、重复一项、错误 arXiv 配对。模型负责判断和修订；目录来自活动引用及原始 BibTeX 的字面标识。目录中的 `records/<index>.txt` 是 JSON 内的虚拟定位符，原 BibTeX 文件另外绑定哈希，不代表存在对应实体文件或完成出版核验。

独立验收直接比较源稿期望配对及冻结报告快照：完整且无重复、只修正既有条目的 arXiv 配对、其他既有字段与数组顺序原样保留、缺失项仅新增带“待进一步核验”的最小占位、报告其他顶层字段不变、代码与来源未变。另运行生成程序检查，但不以其自检代替独立验收。科研判断正确性未人工盲评，原报告可能仍含历史错误。

v3 四任务使用相同提示模板、模型、工具集合及顺序。没有强制模型按某个 DAG 调用，也没有要求其只输出纯工具消息。保留旁白、最终解释、重试和全部请求分母。

## 已实现的接口

- `trace-rsi-task-server.ts`：`read_task_state({})` 读取当前报告及模型所选字段投影；`write_report({report_sha256, report})` 以当前版本保存私有副本；动态生成工具接受 `{input_id}`。
- 每次读取或写入返回 `input_id/input_sha256/report_sha256/source_version/candidate_sha256/catalog_sha256`。句柄绑定当前 Session、报告、来源、目录与生成程序；旧句柄、伪造句柄、跨 Session、源码或代码漂移均拒绝。
- `trace_rsi_motif_compiler.py` 从完整助手声明、调用 ID、参数和成功结果学习局部边。训练仅接受合格正常 baseline，保留请求位置和文本存在信息；单 Session 候选不用于预测。
- `dsh_trace_rsi_shadow.ts` 在真实模型请求之前预测当前工具参数及纯程序结果，再与真实工具结果比较。所有请求继续交给模型，不调用 MCP 来实现接管，不授予执行权限。
- `paper-rsi-generated-task.py` 复用既有真实 Harness 与累计预算入口；`check-trace-rsi-task.mjs` 是运行后的免费诊断，不混入学习见证。

生成算法未人工改写。任务适配、版本句柄、独立质量检查、编译器与运行时仍是工程基础设施。

## 冻结出的两个 Motif

1. `read_task_state → triage_catalog_coverage`。
2. `write_report → triage_catalog_coverage`。

每条边均有两个训练 Session 支持，参数都是从当前返回收据提取 `/input_id`，不是沿用历史任务的句柄。模型生成工具候选摘要为 `610ce5ded7c551e7ab90da8fd9559b7e6c4efa949a0652b7bc2b900b528d19c6`；冻结工具 manifest 为 `a84415d2cae2b2cc92e9bd48b19423a5b34e32982638ad2369dc4ab4cb6d4bef`。

v3 Motif manifest 为 `97c91f65bbd5a9584fcc9f6b519b2bd1cc3f18642acf750563f7a861b9df71ce`；库文件字节摘要为 `05534660cbd8cbd4c4c3a60b0be2480b12be217ddf86a1b8f8d8f465f3fe6996`。正式见证和库留在私有实验目录。公开可读摘要不代替可加载库或认证。

## v3 真实结果

| 运行 | 真实请求 | 结构及字段保留 | 局部调用和结果匹配 | 严格整请求 | 新增代理估费 / 美元 | 模型运行秒数 |
|---|---:|---|---:|---:|---:|---:|
| baseline-main | 7 | 通过 | 不评测 | 不评测 | 0.014136204 | 26.06 |
| baseline-abstract | 5 | 通过 | 不评测 | 不评测 | 0.007979832 | 20.95 |
| shadow-subset | 6 | 通过 | 2 | 0 | 0.008330064 | 20.98 |
| shadow-incremental | 6 | 通过 | 2 | 0 | 0.010301844 | 22.50 |

两条 Shadow 合计局部匹配 **4/12 = 33.3%**；严格整请求 **0/12**；实际跳过 **0**。每条 Shadow 有三次预测：两次检查匹配，最后一次不匹配。预测精确率为 **4/6 = 66.7%**，不能只展示命中而隐去反例。

两次命中分别位于请求 2 和 4，完整参数、当前版本和真实输出一致，但请求均含模型文字。请求 4 的文字只说明“保存成功，接下来检查”，人工阅读认为存在控制交接的继续研究空间；它仍不计入严格自动统计。请求 2 包含模型对当前问题的解读，不能未经审阅直接丢弃。

反例发生于请求 6：模型在请求 5 重读已修订报告后，下一步输出最终总结；图仍预测再次检查。版本守卫通过不代表业务状态需要续接。这个图尚未学会“已验证并准备结束”的条件，因此不能据其频率开启自动执行。

| 运行 | 缓存命中输入 token | 缓存未命中输入 token | 输出 token |
|---|---:|---:|---:|
| baseline-main | 77184 | 21317 | 6065 |
| baseline-abstract | 28672 | 7194 | 4708 |
| shadow-subset | 34944 | 9932 | 4284 |
| shadow-incremental | 42624 | 12551 | 5234 |

耗时仅是模型运行与工具调用区间，未包含本轮开发、同步、修复及免费测试。人工语义修订时间未测量。

## 失败保留与成本

- v1 主稿 6 请求，结构覆盖通过，但部分既有判断字段被模型改写，未通过独立验收，不用于训练。新增估费 0.012151956 美元。v2 明确规定字段保留与最小占位；这是任务约束修订，不追改 v1 的结果。
- v2 两条合格训练各 5 请求；首次 Shadow 启动时错误假设 provider 工具顺序等于 MCP 声明顺序，启动失败，0 请求。错误为 `invalid_trace_shadow_tool_order`。保留该失败及旧代码快照。
- 修复按 Harness 实际 provider 顺序保存库，在每次预测时仍精确比较完整 schema 与顺序。新建 v3、重跑训练；没有把旧代码见证冒充新版本。新增真实顺序回归。

本轮 v1–v3 合计 **40 请求**，新增代理估费约 **0.070375 美元**；包含历史失败与重试的累计约 **6.046825 / 8 美元**，剩余额度上界约 **1.953175 美元**。实付账单未核对。上一轮工具学习的 308 请求及约 0.274440 美元仍在累计账本内；本轮局部命中不能抵消学习费用，也没有净收益证据。

## 配置、复现和免费验证

基底 commit `2368235f274329be6227a8393b850633cb943da4`，分支 `feature/paper-submission`，工作区未提交。模型 `deepseek-flash`，推理 off，单次输出 8192，无请求次数上限，无上下文压缩；各运行独立 DSH_HOME。继承已授权私有非沙箱实验权限，仅修改副本，不投稿、不写外部应用。

服务器入口：

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-generated-task.py preview
# paid 标签必须未使用，不覆盖历史结果
node scripts/project.mjs python scripts/paper-rsi-generated-task.py baseline --case t01_main --label baseline-main
node scripts/project.mjs python scripts/paper-rsi-generated-task.py baseline --case t02_abstract --label baseline-abstract
node scripts/project.mjs python scripts/paper-rsi-generated-task.py compile
node scripts/project.mjs python scripts/paper-rsi-generated-task.py shadow --case t09_subset_b --label shadow-subset
node scripts/project.mjs python scripts/paper-rsi-generated-task.py shadow --case t10_incremental --label shadow-incremental
```

这些标签已运行，复用会明确拒绝。复核已有结果使用 `verify --label ...` / `score --label ...`，不产生模型费用；新 paid 重测须新实验 ID 并继续累计历史费用。

私有 `.local/paper-reference/paper-rsi-generated-task-shadow-20261011-v{1,2,3}/` 保存有效配置、来源/代码哈希、版本、工具顺序、逐请求、事件、成本账本、报告、独立验收、预测与评分。本地已同步私有结果。manifest 的额外绑定由运行后追加实际配置快照，注明 `binding_snapshot_stage`；原配置/预算快照保留，不把这些补录字段称为启动前签名。

本地最终 `npm test`：292 Python / 158 Node 免费回归通过；服务器同样执行最终回归。服务器无模型 smoke 18 题 / 83 工具调用通过，含 SDK 初始化；不代表模型科研质量。新增接口的 Windows 模型联调未验证。

## 结论与下一步

已支持“从正常 bash 发现并生成工具 → 正常使用生成工具 → 从真实衔接编译局部图 → 后续任务前瞻 Shadow”。参数和输入是动态绑定的，不是手写完整任务 DAG，也不是缓存旧论文结论。

证据不支持可靠整请求接管、跨论文认证或净降本。下一步优先从成功续接与结束反例一起学习状态条件，再设计控制旁白的有界交接：模型的科研判断必须保留；已明确的检查调度才交给 Runtime。用新版本库、后续任务评测，保持严格整请求、人工旁白判断及实际跳过分别统计。继续暂停 execute。
