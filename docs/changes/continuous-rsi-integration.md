# 普通运行的持续 Motif 学习接口（2026-10-15）

普通公开 CLI 完成任务后，先封存原生轨迹、验收、HTTP 费用和实际 schema，再自动唤起独立 Python 学习服务。服务从合格的新普通轨迹发现支持的参数图，冻结候选，用新副本独立认证，发布不可变经验库版本。当前任务使用启动时冻结的版本，新版本只用于后续任务。稳定净收益仅记录，不是激活条件。

## 入口与授权配置

`scripts/run-scenario.py --rsi-config <private.json>` 为显式入口；不带该参数保持原入口。原有预览、`--call-model` 和预算代理仍生效。不能与手动指定旧 policy 或持久化写任务组合。首版接入 `report_tools.py` 的只读文件管理报告；写操作、其它 MCP 和默认 Web/SDK 尚未接入此学习服务。

私有配置 `sss-continuous-rsi-v1` 包含 `state_root`、明确的 `workspace_roots`、`mode=observe|learn`、`provider_mode=real|mock`、系列/学习预算、`limits`、`auto_worker` 和 `allow_material_copy`。只能授权 `testpdf/file-management-experiment/` 下的指定副本；拒绝路径中的符号链接。真实学习要求 `real`，模拟只能观测。当前原授权上限为系列 1000 USD、每题 5 USD、96 步/请求、4000 输出 token、2 次同会话验收修复。认证子任务共用同一学习池与系列预算，不能改变权限。预算预留和未决费用在重启后保留。

`scripts/rsi-worker.py --config <private.json>` 只查看状态；增加 `--drain` 才处理已有队列并按配置开展认证。正常 CLI 可自动启动该服务，实验驱动不按题号调用编译器或指定正确模板。中断认证保留开始标记；未封存的付费子任务不重新冷启动以重置限制。

## 原生通知与封存

TypeScript 插件 `dsh_continuous_rsi.ts` 记录实际 Agent 的工具参数 schema 和 `agent/disposed`，每会话只发一次结束通知。通知不是成功声明；Python 入口在独立验收和原账本最终记账后生成 `sss-continuous-run-v1` 和带原记录 SHA 的队列项。来源副本、原事件、实际读取、报告、源码快照、库版本均按哈希封存。

没有完整 usage 的失败请求，按原 ledger 的 `reserved_upper_usd` 保守记费，标记 `observed_usage_complete=false`，不能训练或认证。历史失败的费用核清为追加审计文件，不覆盖原记录，不重置请求；实际账单仍需核对。

## 发现、认证与版本

`continuous_motif_learning.py` 从实际模型选择、原工具调用与参数流发现集合读取图；从已执行父 Motif 后的实际新模型选择发现第二段读取图。复用现有 Python `collection_compiler`、`reentry_compiler`；没有新增任意代码执行、手写业务路由或 `profile_id`。每个候选至少两份不同材料的普通模型决定，冻结编译产物及训练记录；失败、修复、模拟、旧源码和最终留出被排除并保存原因。

同一机会已有活动候选时不重复认证。候选失败或停用后，新的独立证据使编译摘要变化，才建立新的修订任务；旧失败、开始标记和费用不覆盖，相同证据不重复付费。超出两段语法的活动结构明确记为未支持的发现类型。

新增 `certified_motif_v1` 入库条件：一份新原生图见证、两份新实际候选执行、三份独立材料且不与训练重叠；报告通过、原权限/版本守卫通过、真实生成批次存在、无修复/失配。认证标准事先固定，拒绝候选不会发布。原库格式和旧证书不改签。运行失配或交付失败会停用相关候选，普通 Harness 继续，旧快照保留。

`collection_read_policy_v2.ts` 支持模型同轮 `select_files` 后发出的真实 `pin_file`：核对选中成员、参数、来源版本及唯一句柄，只生成尚未执行的结构段。真实模型 pin 明确记作 `collection_native_pin_adopted`，不是跳过模型请求。`collection_reentry_policy_v2.ts` 用同一执行器实现两段交接。旧执行器字节保持，已发布库的源码锁不变；新两模块进入运行依赖摘要，重新认证后使用。范围仍为最多 32 成员、每批 8 操作、最多两段集合；语义选择和摘要由模型完成。

## 验证与回退

免费检查：`node scripts/project.mjs python scripts/check-continuous-rsi.py`，真实 CLI/SDK/MCP 接本地模拟 Provider，模拟证据拒绝训练。真实流预览：`node scripts/project.mjs python scenarios/file-management/continuous_study.py`；生成全新材料后才显式 `--experiment <path> --call-model`。独立审计：`node scripts/project.mjs python scripts/audit-continuous-rsi.py --experiment <path>`。费用包含普通任务、发现后新材料探索、认证、失败和修复。

移除 `--rsi-config` 回到普通 CLI；`mode=observe` 只封存不学习；`auto_worker=false` 只入队等待人工运行服务。不修改上游 Harness 或冻结原 MotifAgent，不推送私人库/轨迹，不自动推送 GitHub。首版是有界参数图的真实连续学习闭环，不能据此宣称任意新结构、默认前端集成、真实办公泛化或整体净收益已经实现。
