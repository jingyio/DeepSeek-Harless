# 批准阅读计划后的 Motif 在线自动续接

用户在2026-10-10明确授权修改共享接口，并要求留存 GitHub 提交说明。原问题是证据准备链已离线认证，但共享在线免语义匹配只支持有限 `read_pinned/source_id` 读取，新 verify/build 仍需 embedding，无法自动接管。改动使 Runtime 在当前任务明确授权、真实工具许可有效且已认证参数完整绑定时执行机械核验/组装，执行后才记账验证跳过。

## 共享变更逐项记录

| 文件 | 变化及理由 |
| --- | --- |
| `src/adapters/dsh_trajectory.py` | `ToolContract` 最后增加默认 `None` 的 `continuation_policy`，保留已有位置参数兼容 |
| `src/adapters/tool_contract_loader.py` | 严格解析三步许可、只读/稳定/单参数/无默认值范围，拒绝无界或不匹配声明 |
| `src/adapters/tool_schema_contracts.py` | 对许可工具检查完整真实 MCP inputSchema 摘要；原描述匹配规则保留 |
| `src/motif_core/offline/continuation_policy.py` | Python 离线许可格式、原始成功观察与同计划链校验；不添加 Agent 循环 |
| `src/motif_core/offline/trace_compiler.py` | 新许可进入契约签名；训练/留出检查许可，完整链绑定策略摘要；旧契约不增加散列字段 |
| `src/motif_core/offline/edge_compiler.py` | 实际参数边的见证必须同时满足一致的当前任务/计划/版本许可，防止常见工具序列升级权限 |
| `src/motif_core/offline/chain_compiler.py` | 仅对完整已见证三节点链生成许可摘要，沿用不同任务训练和留出认证 |
| `scripts/export-online-motif-manifest.py` | 只导出许可覆盖的完整认证链；有许可为 v2，无许可仍为 v1；旧库不能通过换契约升级 |
| `scripts/prepare-online-motif.py` | 接受 v1/v2 后仍交权威 Node 校验，不绕过认证/任务检查 |
| `src/motif_core/approved_plan_continuation.ts` | 新在线规则：manifest、任务许可、每个实际 schema、原生工具 grant、阶段、唯一参数、执行后许可复核 |
| `src/motif_core/approved_plan_continuation.generated.mjs` | 随仓库提交的生成桥接；既有插件运行无需新增 TS loader，规则源仍为 TypeScript |
| `src/motif_core/online_skill_runtime.mjs` | 调用新规则；许可候选校验失败直接排除，禁止 embedding 重新授权；原窄读取匹配保留 |
| `src/adapters/dsh_online_motif.mjs` | 原生 `tools/result` 复核许可/成功状态、记录策略依据、失败停止续接，保留公共事件生命周期和预算 |
| `scripts/build-continuation-policy.mjs`、`scripts/project.mjs`、`package.json` | 增加生成/一致性检查，将新 Node 回归纳入 `npm test` |
| `.gitignore` | 忽略本地 `testpdf/` 用户论文，提交公共测试夹具与代码即可 |

没有修改 `node_modules`、上游 Harness 或预算算法，没有放宽共享字符串长度，也没有把工具改名为 read_pinned。新策略与旧工具 schema 都保持固定工具集合；脚本与 Motif 使用同一 MCP 工具实现。

场景变化：`pdf_evidence_tools.py` 只在当前会话已注册且批准的计划上签发/传播有限许可；legacy 内联 JSON 可手动执行但不发自动许可。`pdf-evidence-contracts.json` 声明边界及实际 schema 摘要。`run-evidence.py` 冻结任务策略授权并保存共享代码摘要/manifest 摘要；`check-evidence.py` 验证 baseline、普通脚本、Motif 的同计划包一致与零 embedding。科学理解、页/窗口相关性、论断支持与写入知识库仍交回模型/审阅。

## 兼容与迁移

- 现有 v1 无许可契约的签名、认证及运行方式不变；新字段默认拒绝授权。旧 Runtime 拒绝新 v2 manifest，不能静默忽略许可。
- 旧原始轨迹/证据包与新实现版本不同，保留历史，重新收集正常真实模型轨迹；不追改旧结果添加 grant。
- 新规则当前只支持单一参数传递的完整三步只读链；不自动发现科研语义分支，不支持任意代码执行或外部写入。
- TypeScript 产物用 `npm run build:continuation` 生成，开发构建 Node 22.18+；运行使用生成 JavaScript。当前实际验证 macOS、Node 22.22.2，新增功能未宣称其他平台已验证。
- 本地 embedding 配置仍是公共 CLI 的要求；闭合许可路径不发 embedding 请求，其他 v1 语义路径仍按原逻辑执行。
- MCP 是可信执行边界；内容摘要/grant 不是抗恶意服务的密码学授权。

## 测试、实验与费用

具体结果在 [实验记录](../experiments/approved-continuation-20261010-94934aab.md)。测试包括 Python 训练/留出许可一致性、旧库不能升级、schema 漂移；Node 原生两次验证跳过与后续语义交回，以及缺/错许可、错任务/计划/版本/receipt/阶段、needs_review、工具失败、shadow 和格式拒绝；真实 Harness + MCP 的固定计划三组机械证据包一致。真实 DeepSeek 训练与前瞻在线验证另记，不能用模拟请求数替代真实费用。

历史首轮全仓检查发现 `prepare-online-motif.py` 仍只接受 v1；已纳入兼容改动。失败未涉及 API，保留测试记录；最终通过结果见实验文档。

## 可用于 GitHub 的标题与正文

后续增加场景内固定计划对照与强缓存基线，没有新增共享接口：`run-evidence.py` 的可选 `--frozen-plan` 校验当前任务/明确许可及输出计划一致性，`compare-evidence.py` 通过公共 runner 轮换顺序/累计费用/失败停止，`reuse-evidence.py` 复核完全相同显式请求的原生来源并复用结果；`check-evidence.py` 和相关测试覆盖相同提示、计划漂移、拒绝许可、记账缺失和两次实际免费接管。MCP实现/schema、执行版本、上游Harness与预算不变。

真实3轮记录见 [固定计划对照](../experiments/frozen-evidence-20261010-997d9e47.md)：Harness/script/Motif每次6/4/4请求、包一致，Motif两跳过/零embedding，平均6.636秒；费用较脚本仅低1.8%且有反向轮次，学习成本尚未摊平。完全相同任务缓存0请求。最新284 Python+44 Node通过；独立材料与完整科学质量未验证，后续方案见 [分层验收](../experiments/literature-evaluation-protocol.md)。

建议标题：`feat: 在批准阅读计划后自动续接已认证的证据准备 Motif`

正文：

此前证据提取→机械来源核验→原文证据包组装已经离线认证，但在线 Runtime 对后两个步骤仍依赖语义匹配。新增版本化、默认拒绝的批准计划续接许可，绑定冻结用户任务、当前计划、完整工具 schema、执行版本与实际参数来源；在原生 Harness 工具派发完成且许可/成功状态复核后才计入验证跳过。科学理解与论断支持继续交回模型及审阅。

共享 ToolContract、离线编译/认证/导出和在线 matcher/result 守卫做了最小扩展，许可产物使用 manifest v2，既有无许可 v1 保持原契约行为。在线新逻辑用 TypeScript，既有 `.mjs` 插件调用提交的生成桥接。验证、真实请求/费用与适用边界详见上述实验记录；不主张完整科研交付质量或净费用已改善。

补充固定模型批准计划的普通Harness/脚本/Motif三轮真实对照，原文包相同，每次请求6/4/4；Motif实际两次验证跳过，平均运行更快，费用相比脚本优势很小且有反向轮次。保留相同请求的0模型结果缓存强基线、所有逐请求费用与学习开销；不把重复同计划运行当作新语料或独立科研质量验收。

提交时只纳入代码、公开配置、测试与文档；`.local/`、API key、原始运行日志和 `testpdf/` 私人论文不提交。本次未执行 commit、push 或创建 PR。
