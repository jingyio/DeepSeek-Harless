# F02：经验执行与更新的共同接口（审核候选）

F02 交付一个能运行、能解释决定的小闭环。先运行 `npm run rsi:demo`，再按需要查看接口；不必逐行审核生成的 JSON。

## 用同一个例子理解结果

| 当前目标 | 局部操作 | 演示结果 |
| --- | --- | --- |
| A：科研实验数据报告 | 按组统计观测数量 | 对 A 的输入实际运行固定 Python 程序 |
| B：活动报名汇总 | 按组统计人数 | 使用同一程序，重新绑定 B 的输入和当前操作依据 |
| C：只写邀请文案，不处理报名数据 | 不需要汇总 | 没有当前操作依据，交回模型 |
| B 中途改变数据版本或撤销权限 | 原有依据失效 | 交回模型或拒绝，不派发程序 |

这只是两个不同任务目标下的**局部计数**，没有完成整份科研报告或报名业务。算子和样本均为人工编写的公开合成诊断，不能作为自动挖掘、跨领域泛化或降本成绩。B 的报名是否有效也没有由计数程序判断。

## 完成后能拿到什么

1. **一个演示入口**：展示实际执行、版本/权限/证据失效与回退。默认免费；真实模型联调必须显式开启。
2. **两端都能读的记录**：Python 导出，TypeScript 运行时校验；错误格式、未知版本和不支持的嵌套 Schema 被拒绝。
3. **后续模块的接缝**：当前执行依据与回执，以及诊断、候选修改、独立验证、发布、回滚记录。F03 接计量，F05 产生经验修订，F08 产生 Matcher 代码修改。

## 最短复验

先按 README 安装固定依赖（Node 22.18+、Python 3.10+；本轮本机 Python 3.12）。

```sh
npm run rsi:demo
npm run rsi:check
npm test
npm run smoke
npm run motif:check
```

`rsi:check` 检查生成文件一致性、Python 样本和 Node 定向回归。生成文件的可审阅来源是 `scripts/build-rsi-schema.py` 与 `scripts/rsi-protocol-fixtures.py`。修改协议后重新生成；不能靠修改旧库哈希绕过认证。

真实联调入口为 `scripts/check-rsi-protocol-real.py`，默认只预览。执行必须提供私有授权、历史记账快照和 `.local/` 输出目录，并加 `--real-model`。普通模式复用 `call_bounded_prompt`/Harness 做有界选择；加 `--native-harness` 则复用 DSH 原生 AgentLoop、工具限制和工具生命周期，记录原生事件及同一个 call_id 的协议回执。两种模式共用累计费用代理。参数、结果及失败见[本轮记录](experiments/f02-protocol-local-20261024-v1.md)。

## 接口与职责

| 入口 | 输入 → 输出 | 责任 |
| --- | --- | --- |
| Python `validate_record` / `write_record` | 记录 → 校验结果 / 精确字节摘要 | 离线导出；不作在线执行授权 |
| TS `validateRsiRecord` | 记录 → 已检查副本 | 共享格式及受支持的工具 Schema 子集 |
| TS `admissionDecision` | 当前请求 + 可信宿主状态 → execute / handoff / reject | 核查当前任务、操作依据、证据、代码/组件版本及权限 |
| TS `executeRsiOperation` | 请求、当前参数、宿主读取和原生派发回调 → 决定、事件和结果 | 派发前重新检查；失败保留回执并交接 |
| TS `validateRsiUpdate` | 候选/验证报告的原始字节 + 可信审核状态 → 版本变更计划 | 拒绝过期父版本、篡改、证据越界和训练/验证重叠 |
| TS `publishRsiUpdate` / `rollbackRsiUpdate` | 已检查修改 + 原子提交/恢复适配器 → 回执 | 适配器成功后才产生成功回执 |

宿主状态必须来自已认证库、当前会话证据和既有权限系统；不得直接采用模型提交的同名 JSON 作为权限、认证或独立审核。模型当前选择只解决操作是否需要，不能授予文件访问或外部写权限。原生派发回调必须继续运行自己的实时守卫。本轮 helper 拒绝 `external_write`，无法解析的 Bash 保持 `opaque`。

每次准入绑定当前 `state_version`、参数字节摘要及依赖集合；新观察后可重新提出局部请求，不需要预知完整工具序列。协议不实现候选检索或结构匹配算法；演示的候选由宿主给定。

## 记录与计量约定

- 共同信封为 `protocol: geneloop.rsi/v1`、`record_type`、`payload`。未知版本/字段失败关闭；当前为 G0/F03 联审前的候选，尚未正式冻结。
- Operator 含来源、输入输出格式、参数来源、结构签名、依赖、权限效果和代码摘要。来源包括 Tool/Bash/Python；执行资格由可信宿主另外检查。
- `execution_event` 记录 started/succeeded/failed、同一 call_id、实际参数和结果摘要。它不是 Provider 请求数；Runtime 内的执行也不自动算一次请求节省。
- `provider_request` 从真实费用账本投影。按 `(ledger_ref, id)` 去重，终态替换 booking；未知 token/费用保持 `null`，失败与未结算预留单列。`observed_peak_usd` 是保守代理估费，账单未核对。
- Motif、Matcher 分别带版本与 SHA。`rule_revision`/`motif_split` 改 Motif，`matcher_code_patch` 改 Matcher；适配器负责实际差异和可信边界。Miner/Updater 等后续扩展需新增受检协议版本，不能向旧版偷偷塞未执行字段。
- 候选、验证报告与回滚所用的已发布回执按**精确存储字节**绑定；不依赖 Python/JS 对浮点数或 Unicode 的重新序列化得到相同摘要。独立审核报告白名单和已发布回执摘要来自宿主，不接受候选自报 `passed` 或伪造回滚目标。

## 与现有路径怎样衔接

| 现有模块 | 本轮处理 | 后续接入责任 |
| --- | --- | --- |
| `dsh_trajectory.py`、`reuse_mediation.ts` | 原接口与认证锁保持，运行原有回归 | 原生宿主把真实证据绑定为当前请求，保留原生 guard/observe 生命周期 |
| `experience_registry.py` | 保留原不可变对象、证书核验、发布和 expected generation | 组件适配器在 `commit` 回调内复用这些检查；新信封不能直接冒充旧证书 |
| `failure_evolution.py`、`script_description_learning.py` | 作为已有局部学习基础，不改算法 | F05 适配诊断/规则修订与分支认证 |
| Matcher 更新 | 提供格式、独立审核及发布接缝 | F08 生成真实代码 diff、独立验证并加载后续版本 |

本轮 opt-in 接口不自动迁移旧库或接管生产。演示宿主的 `certified:true` 仅是明示的人工诊断信任，不能接入真实用户会话。完整学习认证、实际组件发布适配器和 F03 ABI 联审仍需后续工作；不因本 PR 测试通过就关闭整个 F02。
