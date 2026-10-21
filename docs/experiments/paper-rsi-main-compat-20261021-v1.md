# 提示型 Script RSI：同步 main 与新版 DSH 兼容验证

## 结论与范围

已同步 `origin/main` 的 `73591f62`（PR103），合并提交为 `3a295837`。文档冲突保留了 main 的 Artifact Motif 实验、当前提示型 RSI 状态和 PR100 历史，没有修改生产配置或上游 DSH。

本次修复两个接口问题：辅助模型请求不能消费 Motif 状态；新增无关工具不能使已认证的目标工具提示失效。局部真实任务观察到自动发布的 Negative 库在新版 44 工具环境中被后继任务精确加载，并实际投递 5 次提示。这支持兼容链路有效，**不证明恢复成功、净降本或完整论文报告合格**。两个限时任务均取消且没有交付报告 PDF，全部费用保留。

本分支还包含此前默认关闭的 Positive 描述学习和提示型 Negative 学习。其历史真实结果与全部失败分别见[描述更新](paper-description-rsi-20261020-v1.md)和[Negative 闭环](paper-negative-rsi-20261021-v1.md)。本次不重跑 Baseline，不扩大执行或早停权限，不部署。

## 问题、改动与否定条件

1. 新版 DSH 的 `llm/stream` 也承载 compaction 等请求。实验续接现在使用 SDK 的 `isAgentLoopRequest` 身份标记，且仍位于原生 admission 之后；辅助请求直接交给原生 continuation，不更新 Evidence、不消费复用片段或提示回执。若辅助请求进入 Motif 或改变其状态，该项验证失败。
2. 历史完整工具表为 30 个，当前为 44 个，整表摘要不同；目标报告工具的参数 schema 相同。自动学习器仅在所有失败见证记录同一目标 schema 时，编译 `exact_tool_schema_prompt_only` 并逐见证绑定摘要。Runtime 对这种规则检查目标参数 schema，继续检查实现锁、当前失败、来源和用户要求；旧规则仍要求整表一致。目标 schema 变化必须失效；loader 禁止将新范围用于早停策略。此项不依靠修改旧库摘要通过认证。

完整工具表摘要：旧 `a4005ea5ec1cfa75d6c0e486d877b0614133a267c2b6f6c652049059317b2273`，新 `a74972f2d3ece47437a8d702ff4822eed5e7d39b66b7612652d2171b20149822`。编译候选仍按历史整表分组；本次没有实现跨任意 schema 的规则迁移。

代码位于 `script_motif_web.ts`、`script_negative_compiler.py`、`script_negative_learning.py`、`script_negative_runtime.ts`。参数、接口和回退边界见[接口文档](../interfaces.md#可选-negative-提示学习独立私有实验)。

## 配置与可复现入口

- 类型：历史真实论文报告失败的局部恢复任务；同论文恢复变体，不是新论文或完整参考文献核验。训练沿用已有真实失败，后继当前调用是新生成的真实工具结果。
- 代码：合并提交 `3a295837` 加本次兼容补丁；任务目录保存完整代码快照，最后提交号由 Git 追溯。未修改原件、正式服务、公共库或全局代理。
- 环境：macOS 26.5.2 arm64；Node 22.22.3、Python 3.12.14；`@deepseek-ai/dsh` 与 `dsh-llm` 为 `0.1.5-rc.3`。Linux/Windows 效果未在本轮实测。
- 模型：真实 `deepseek-flash`，`reasoning_effort=off`；Agent 输出上限 32768，学习输出上限 1536、最多 1 条候选；费用及请求上限不限，`cap_usd:null`、`budget_policy:uncapped_user_authorized`、`reset_history:false`。沿用历史授权与累计账本。
- 模式：实验 `shadow`，Negative 为 `prompt`，提示有实际干预；不是纯观察 Shadow。仅加载 Negative 指针，不评估 Positive/Embedding。当前有效压缩策略为 `native-pressure-checkpoint-v1`，不能沿用前轮“压缩关闭”的描述。辅助请求分流有确定性回归，未故意制造真实压缩压力。
- 输入沿用历史来源、恢复 prompt、checkpoint 和 scope；私有来源 SHA 前缀 `4bd41694`，原始 prompt SHA 前缀 `443bd3f6`。注入当前任务状态后的有效 prompt 摘要按两次任务分别记录，不能将原始题面摘要等同于有效请求摘要。
- 私有根目录 `.local/paper-rsi-main-compat-20261021-v1/`：授权、`shadow.json`、`current-compilation.json`、克隆的 `learning-store/`、两次日志和 `aggregate.json`。逐 run 的有效配置、源码快照、summary 在 `.local/script-motif-experiments/<run_id>/`；原始事件和 `effective-config.json` 在 `.local/web/runs/<run_id>/tasks/<task_id>/`。凭证仅由既有私有环境加载，未展示或提交。

按 README 准备项目环境，并将下面变量指向既有私有文件；第二次只将 `--max-seconds` 改为 `180`，两次均使用同一 store，不清零账本：

```sh
SSS_PYTHON="$PWD/.venv-sss/bin/python" \
SSS_PURE_CODE_PYTHON="$PWD/.venv-sss/bin/python" \
SSS_LOCAL_SCRIPT_EXPERIMENT=1 \
HARLESS_REPORT_FONT="$REPORT_FONT" \
node scripts/project.mjs python scripts/run-script-motif-experiment.py \
  --real-model --mode shadow --report-evidence \
  --source "$SOURCE" --prompt "$RECOVERY_PROMPT" \
  --reuse-checkpoint "$CHECKPOINT" --preserve-recovery-structure \
  --recovery-goal-scope "$SCOPE" \
  --script-config .local/paper-rsi-main-compat-20261021-v1/shadow.json \
  --learning-store .local/paper-rsi-main-compat-20261021-v1/learning-store \
  --budget-usd 0 --max-output-tokens 32768 --max-seconds 60 --port 3230
```

本机已有失效代理，本轮只在实验进程中清空代理环境；没有修改全局配置。先用当前 `learn_negatives` 与 TypeScript loader 实际重编译和认证历史候选：生成/独立审核共 2 次真实请求，发布 1 条规则，摘要 `0661665cbdf0f094a5ae2a06faf56f87aa3113f41becaeb85c2f161eb470cbde`。不是仅重算锁，也不是运行前手写引导。

## 局部真实结果与失败

| 项目 | real-001 | real-002 |
| --- | --- | --- |
| run | `62cab4bc3be54ded89eae27d7f7a36f4` | `232d3d631add47c9983bdf1612c5e19b` |
| task | `4dc98701866040acabd4f3ba9447fff0` | `9befbb3b23dc4b90948ea623a070f42f` |
| 窗口 / 状态 | 60 秒 / cancelled | 180 秒 / cancelled |
| 实际耗时（含取消收尾） | 61.520 秒 | 197.887 秒 |
| 加载学习库 | 1 | 1 |
| 当前失败 / 提示投递 | 0 / 0 | 5 / 5 |
| Agent 请求 | 11 | 21 |
| 输入 Token | 206,594 | 833,748 |
| 缓存命中 / 未命中输入 | 191,872 / 14,722 | 808,704 / 25,044 |
| 输出 Token | 11,952 | 51,624 |
| 保守估费 | USD0.019910232 | USD0.196424724 |
| 汇总时新增未知 / pending | 0 / 0 | 0 / 1 |
| 报告 PDF / 完整请求跳过 / 早停 | 0 / 0 / 0 | 0 / 0 / 0 |

第一次只完成读取和检查，未到可匹配失败，不能算投递通过。原生 `read` 返回 Linux no-follow descriptor 限制，模型随后改用 Bash；这是 main 既有平台安全边界，本轮没有绕过或放宽。结束时一个未完整形成的导出调用不能作为有效原生失败见证，采集器按原契约跳过。

第一次结束后，现有 worker 自动发布摘要 `7b19cb56e70c11a741095116219481278a2722400e92ccea05978cf69bb8ead4`，第二次精确加载该版本，真实当前结构失败后送达 5 次已审核提示。两次任务结束均自动发布，发布阶段模型调用为 0；最终事件摘要与发布所用证据一致，无组件 fallback。这一轮没有人工恢复 worker。

第二次仍反复生成完整报告参数和错误恢复，没有完成报告。投递次数不是修复次数，更不是省下的模型请求；未做科研事实评审或逐页 PDF 视觉检查，质量未评审。限时结束保留为局部兼容诊断，不能与完整任务或前轮不同 DSH 工具配置直接比较费用。

## 费用与累计

新增 Agent 共 32 请求 / USD0.216334956；实际重编译学习 2 请求 / USD0.000754500，**合计 34 请求 / USD0.217089456**。全部失败、重试和取消前预约保留，来自复制 store 的旧学习账本不重复计费。新增 pending 1 笔、未知用量 0 笔；此前 6 笔未知和 1 笔 pending 继续待核。

累计为 **5952 请求 / USD10.642505592**，不是供应商账单实付，未与账单或旧 V100 历史核对。保守估费保留未结算预约，开发、人工和本地计算成本未货币量化。本轮没有配对净降本结论。

## 免费回归与交付限制

- 相关 Python 38 项、Node 38 项通过。
- 合并后 `npm test`：Python 1517 通过 / 235 跳过；Node 1357 通过 / 15 跳过。
- `npm run smoke`、`npm run motif:check`、`git diff --check` 通过。
- 覆盖正常 Agent 续接、辅助请求不触及状态、无关工具新增、目标参数变化失效、旧规则整表约束、prompt-only 不获得早停权限、编译见证目标 schema 绑定。这些是确定性诊断，不冒充真实效果。

本轮按用户授权提交审阅 PR，不合并或部署。实验仍默认关闭；移除独立 sidecar 中的学习库接入即可走原生路径，保留历史库与账本。下一步若继续降本，应从提示后重复生成完整参数的实际轨迹切入有类型局部修订；本 PR 不把通用原因自动发现或稳定费用下降列为已完成。
