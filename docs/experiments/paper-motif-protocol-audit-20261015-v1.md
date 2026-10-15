# 两次论文实验的 Motif/脚本协议核对（2026-10-15）

**问题。** 判断旧两次实验的产物能否在当前 Web 论文场景共用一个可追溯的场景包；不把 Shadow 预测或模型主动使用 PDF 工具误标为自动执行证书。核对的是 V100 私有原库与当前 20 个实际 MCP Schema；无需模型请求。

**实验一：保存工具。** 私有旧库 `paper-rsi-overnight-20261011-v3/libraries/v01/library.json` 为 `source_bound_readonly_batch_shadow`、`execution_policy=shadow_only`，有 9 条单节点后继候选。旧库严格要求当时完整的 11 工具 Schema 哈希、工具顺序及代码哈希；原结果第一至三轮分别为 24/112、37/114、45/164 个严格整请求匹配，实际跳过为 0。下面只列工具动作和迁移状态，不公开原始论文或参数内容。

| 旧候选 | 后继动作 | 当前 20 工具 Schema | 当前可执行证书 |
| --- | --- | --- | --- |
| `paper-flow-c1dd056e6bcb` | pin 引用 | 同名且参数 Schema 相同 | 无；旧 `case_id` 需重新绑定当前 Session |
| `paper-flow-d15aaf187eca` | 读 pin 后引用 | 同名且参数 Schema 相同 | 仅另有当前 pin→read 两步认证，不等于旧候选已认证 |
| `paper-flow-91670d314bd2` | 读原始 BibTeX 记录 | 同名且参数 Schema 相同 | 旧证据保留，当前包未启用该边 |
| `paper-flow-57fa980a154a` | 查预印本元数据 | 同名且参数 Schema 相同 | 无；外部来源、版本和失败处理需重审 |
| `paper-flow-4c8e00cebdef` | 查正式文献元数据 | 同名且参数 Schema 相同 | 无；外部来源、版本和失败处理需重审 |
| `paper-flow-6fa6cb4ccaf9` | 恢复正式文献查询 | 同名且参数 Schema 相同 | 无；须审计查询与来源绑定 |
| `paper-flow-1254fc79a35f`、`paper-flow-e4d6cba4afc9` | 旧 `triage.json` 写后检查 | 旧写入/检查入口未在当前场景 | 无；不能直接投射到新报告写入工具 |
| `paper-flow-f813f5b15671` | 旧 triage 修复后读取 | 旧读取入口未在当前场景 | 无；需重编当前报告状态链 |

六个仍在场的论文工具的**参数 Schema 哈希逐一相同**，所以工具参数协议本身没有因接入 Web 而全部改写；变的是整套工具集合/顺序、代码版本、任务/Session 绑定和写入工作流。旧库整包不能原封不动挂到 Web，也不能只改 manifest 哈希绕过旧证据守卫。当前 V100 私有 v5 包只从历史轨迹重新编译了两条只读 pin→read 证书，未将旧 9 条全部迁入。

**实验二：保存脚本。** 160→20 次请求来自模型在明确绑定当前审查报告与冻结排版工具后主动使用脚本；旧记录中的自动 Verified Skip 为 0。这份脚本已在当前场景作为 `export_current_audit_pdf` 能力接入，按当前 Task 输出授权、报告 SHA、审阅排版包版本和结果覆盖率守卫执行。它仍需模型先产生审查报告并选择调用，不能用 `read_motif` 类型证书冒充模型请求跳过。当前 `capabilities.json` 已将 PDF 标为 `model_invoked_only`、`rsi_verified_skip=false`。

**统一方式与未完成工作。** 同一版本化论文场景包可同时记录三种能力：已认证的只读 Motif（在线 Runtime 可以 Execute）、经版本校验但仅 Shadow 观察的旧候选、带任务授权的模型调用排版工具。三者共享工具 Schema、来源哈希、Session/Task 绑定和审计字段，但执行权限必须分开。下一步先从旧轨迹在当前源码与任务绑定下重新编译六条只读候选，核实独立留出轨迹与参数来源；旧 triage 三条需要按当前报告工作流重新挖掘；PDF 链路继续按报告版本守卫，并用同一真实论文做质量与费用对照。**截至本记录，统一来源审计已完成，统一在线候选库尚未完成，不能声称两次实验的收益已经合并复现。**
