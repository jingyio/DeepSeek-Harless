# 本地入口、私有迁移与目标验收接口

2026-10-18，仅 `feature/rsi-research-agent`。本轮以本地单用户项目为准，服务器部署与多账号适配后置。历史入口及旧结论保存在 `docs/history/readme-before-local-entry-20261018.md`，原证据不改写。

`scripts/management.py` 统一 `npm run management` 的启动、`status`、`motifs`、`backup`、`verify-backup`、`restore`、`migrate`。日常启动默认真实模型，旧 `--real-model` 兼容，模拟诊断须显式 `--mock`；查询、备份和启动本身不调用模型。场景固定为原生 Files，预算参数只能在既有限额内缩小。沿用原持久化目录及 `daily-management-real-v3`，不生成新的日常库来重置历史。

`management_inventory.py` / `sss-management-inventory-v1` 检查不可变版本库，分别报告版本化经验记录、种类/状态、源码兼容活动项与失败候选；历史条数不是不同工作流数量。源码兼容仅是筛选条件，具体任务仍核验 schema、作用域、权限、参数、状态和证书。

`management_backup.py` / `sss-management-backup-v1` 私有 ZIP 以内容 SHA 去重，保存固定数据根、空目录、可执行位、源码摘要、原系列与学习已用/预留费用、经验盘点。固定范围和依赖/凭证排除项见[本地说明](../management-local.md)。逐文件检查前后快照，不跟随用户符号链接，不覆盖已有输出；失败回执和部分包保留。服务检查识别已确认的非 Node 进程号复用，保留原记录且不终止无关进程；身份不明时仍拒绝。

原路径 `restore` 要求全包校验及无活动写者，仅补缺失的数据根；已有差异先拒绝。换路径 `migrate` 是冷迁入：原证书、任务和会话保留为原始归档，用户资料提取独立副本，不把旧绝对路径或旧确认转换为新权限。`sss-management-cold-import-v1` 回执绑定原始包和预算；原生累计账本保持原字节。新路径不无缝续跑旧会话，须重新附加文件、运行任务并独立认证。原系列费用、请求、尝试数和未结算上界，以及原学习已用与预留进入原限额计算；重复迁入不能重置预算。

`management_goals.py` / `sss-management-goal-v1` 在文件操作前从完整匹配的明确目标冻结谓词和预期树。仅覆盖说明中的按扩展名整理、单文件复制/移动/重命名、全部文本完整读取；不是动作脚本或 Motif，也不选择执行路径。`management_contract.py` 升为 `sss-management-quality-v4`，新增空目录与完整读取谓词，分别返回 `effect_integrity_verified`、`semantic_quality_verified`、`goal_status`（`verified` / `failed` / `review_required`）、检查范围和待复核原因。全树检查拒绝遗漏、额外副作用和内容变化；完整读取不能截断。

`management_prepare` 保留显式冻结基准谓词，日常 `quality=None` 才调用目标解析。未知或部分解析的目标仍可按原权限执行，但不会伪报目标已全面验收。`management_web.collect` 重新核验实际结果，报告及原生设置状态携带目标验收信息，前端显示“目标验收通过”或“目标待复核”。其它场景的任务 DTO 不增加此字段。17 工具完整 catalog 和权限逻辑保持一致。

新验收标准加入执行版本、MCP 运行时源码守卫和学习源码冻结；旧库保持原字节并按规则失效。独立认证使用新字节材料重新计算相同目标谓词与预期摘要，禁止修改标准使候选通过。认证摘要标明 v4；旧证书不重签。旧最终留出集不参与学习，失败和完整费用继续保留。此次不扩展任意 MCP、任意自然语言语义验收或跨任务自动撤销。
