# 通用 MCP 参数图学习与文件管理前端接入

2026-10-15；`feature/rsi-research-agent`，基线 `fcdcc48`。本轮仅本地开发，暂不提交或推送 GitHub。旧库、原始失败、最终留出、上游 Harness 和冻结 Motif 源仓保持。

## 新共享接口

| 接口 | 实现与含义 |
| --- | --- |
| MCP `_meta.sss_learning` | `sss-mcp-learning-v1`；每个算子的作用、可导出参数、允许续接、成功状态、任务范围条件。声明算子契约，不声明流程路线。普通 `readOnlyHint` 不构成写授权。见 [schema](../schemas/mcp-learning-contract.schema.json)。 |
| 实际返回 `_sss_scope` | 原任务/权限/初始状态及执行版本摘要；效果工具成功时还必须返回 `_sss_authorized=true`。宿主只信任服务端登记的 MCP/适配器，模型文字不能产生权限。 |
| `LearningAdapter` | `src/adapters/mcp_learning.py` 中登记 `validate/scope/runtime_sources/verify_record/copy_material`。材料与业务验收由场景负责，学习器与 TS 执行器不依赖工具名称、任务 ID 或 profile。新增场景须登记真实的授权和独立验收适配器。 |
| `sss-operation-graph-v1` | Python 从真实调用参数与此前输出唯一相等的标量句柄编译 DAG；2–8 节点，允许引用任意较早节点。禁止学习语义常量、任意代码、循环和猜测句柄。见 [IR schema](../schemas/operation-graph.schema.json)。 |
| `operation_graph` 版本库条目 | 与原 experience-registry 共存，必须有独立实际认证、原始事件/源码摘要和不可变对象。旧 collection/reentry/script 条目与原证书不改签。新运行模块单独版本核验。 |
| `SSS_OPERATION_BINDING` | 显式 CLI 的 TS 运行插件；真实模型提供入口决定，核验任务范围、源码、实际 schema 与每个结果后逐节点续接；失败交回普通 Harness。默认 Web 通过同一模块与既有公开宿主钩子接入，无新 Agent 循环。 |
| Web `continuous_learning` | 既有 `/api/harless/tasks` 返回额外的库代数/等待结算/封存记录/学习队列状态。提交学习不等于已认证或已激活。模拟 Provider 只封存观察记录，不参与真实学习。 |

MCP catalog 采集复用现有 stdio / streamable-http 客户端。通用协议已实现；当前真实业务验收适配器为文件管理，新名称/分叉图用免费检查覆盖。其它真实 MCP、外部应用写入和其业务质量尚未认证，不能仅凭 metadata 开放。

## 发现、认证与执行

至少两份独立普通 Harness 新任务决定与变化的真实绑定值支持候选；已认证前缀可出现在后续轨迹，但新边必须来自实际模型决定。生成调用只能证明原认证前缀，不能证明新参数关系。最终留出、修复轨迹、模拟模型、不完整 usage 和变动源码不进入干净学习。

认证先冻结候选/源码/验收，再用新字节材料取得一个新原生见证和两次隔离候选执行。全部交付通过原权限和业务验收、完整图实际执行且无修复，才发布新库。质量失败或守卫失效停用相关条目；基础设施 502/503、预算耗尽和用户取消分别记账，不自动当作图反证。净收益仅记录，不阻止合格激活。

图执行从真实模型入口开始，每次提议一个真实 MCP 调用。原生同批预取只记作 native step，不算跳过；MCP 明确声明的安全读取可穿插，但仍留在完整轨迹，不算跳过。失败、语义调用、范围/状态/授权或版本变化均中止续接。无匹配、无有效库、缺标量返回或多个产物无法唯一绑定时继续普通 Harness。

## 文件管理与默认前端

新增 `operation_tools.py`，在原 FileScene/ReportScene 上扩展 15 个受限工具。模型自行构造 `preview_actions`；服务在任何效果发生前核对原目标的操作、实际 source ID、destination、format，再执行原版本/权限/不覆盖守卫。`execute_plan` 返回实际 receipt，`inspect_plan_result`核对当前真实产物；只在目标要求结果读取时允许该续接。批量产物没有唯一 primary handle 时交还模型。计划重复执行保持原实际效果和同一 receipt。

独立 `sss-file-operation-contract-v1` 检查完整操作日志、实际字节、未经请求的变更、报告身份/快照/回执和必要产物读取；转换目前认证范围是 text/csv，ZIP 读取明确为元数据。持久化恢复仍使用原 durable job 路径；新服务不宣称跨进程自动恢复已认证。

```sh
# 免费模拟，复用默认 Harness Web 和 /tasks 页面
npm run web -- --scenario file-management --budget-usd 5 --request-limit 96
# 已授权真实配置；预览后仍需页面确认输入和预算
npm run web:real -- --scenario file-management --budget-usd 5 --request-limit 96
# 同一私有经验库在 CLI 与 Web 间复用（配置信任由服务器提供）
npm run web:real -- --scenario file-management --rsi-config <私有rsi.json> --files-dir <已登记实验副本> --budget-usd 5 --request-limit 96
```

未指定配置时服务器创建独立私有库及有标记的新实验资料，不自动导入不兼容的历史认证。任务 UI 选择文件、操作、相对目的路径与结果读取要求，内部转为冻结 goal；每任务使用独立材料副本。外部前端可复用原 preview/submit/cancel 路由，在该服务器 profile 下 instruction 为 `{"actions":[{"op":"copy","source":"notes.txt","destination":"out/note.txt","format":"none"}],"require_result_read":true,"objective":"用户要求"}`；浏览器表单已承担编码，不要求用户写 JSON。服务器登记 source、adapter、工具、预算和库；客户端不能指定插件、模块或扩大权限。

任务终止先关闭付费入口，等待在途账本结算后封存，与 CLI 共用自动学习队列。取消仍保留失败及实际费用；未结算期间保留预算所有权与预留，不让新任务重置限额。验收失败仍在同 Session 最多两次普通 Harness 修复，Motif 关闭。

## 预算与接口兼容

原系列 USD1000，每任务最多 USD5/96 步及 HTTP/4000 输出，最多两次验收修复；学习池另外受原系列和配置限额约束。502/503 最多两次重试，计入同一原任务的 HTTP、预算及每条账本，不能重置；保守估计和未知 usage 保留，账单实付未核实。没有模型重试工具效果。

修改了 `continuous_rsi.py` 的 adapter/catalog/binding/seal、学习器的图分派/认证/失效、Web 宿主的同一生命周期挂接、预算代理的有限传输重试、原独立交付校验的 operation_contract 分派。CLI `--rsi-config` 与旧不带 adapter 的只读入口兼容；原既有 HTTP 动作和状态名保持。增加源码闭包后旧运行证据可审计、不能改签为当前训练。

详细结果、包含失败的费用和开发归档见 [实验记录](../experiments/generic-mcp-operation-rsi-20261015.md)。通用标量 DAG 是已实现的扩展范围；任意控制流、集合转换、未知 MCP 自动授权、所有文件格式质量、科学语义质量和稳定完整净收益仍待验证。
