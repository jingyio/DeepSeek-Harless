# F02 本地协议与原生 Harness 联调

## 结果先看这里

F02 的局部执行与更新接缝可运行。原生真实模型中，A/B 各调用 2 次模型、执行 1 次固定 Python 计数；C 只写邀请时调用 1 次模型、没有工具执行。最后一轮原生调用 ID、协议回执和 Provider task_id 逐项一致。

这支持当前人工算子、合成输入和显式任务依据下的协议接线。没有完成完整报告/报名业务，没有自动学习、通用跨任务迁移或降本结论；没有 AppWorld 成绩。当前为待两人审核的最小实现。

## 问题、任务与对照

验证 Python 导出与 TypeScript 运行校验是否一致；当前操作依据、证据或权限失效时能否停止；原生工具派发能否留下可关联的记录。任一拒绝分支实际执行、回执与实际调用不符、两端接受结果不一致，都会否定相应机制检查。

- A：科研报告目标中的按组计数；输入 control/treatment，独立期望值为 2/1。
- B：活动报名目标中的按组计数；输入 poster/workshop，独立期望值为 1/2。
- C：只写邀请，不处理报名数据；期望没有 Python 派发。
- 负例：版本/证据改变、权限撤销、语义义务缺失、无算子、缺列、错误输出、工具失败、过期或被篡改的更新与回滚。

全部是人工编写的开发诊断。三种任务目标重复联调，不能把请求数或重复次数当独立任务数量。无训练/正式测试 split，没有调参官方 Test。发布/回滚的提交适配器用诊断状态验证，实际学习与生产组件发布由 F05/F08 继续实现。

## 配置与复现

基于 #114 的 `bb4c8e7ae3d283f846f8804e30de742b0d9b8aaf`，独立分支 `codex/f02-protocol-v1-20261024`；最终源码版本以本 PR commit 为准。

- 本机 macOS，Node 22.22.3、隔离 Python 3.12.14，DSH npm 0.1.5-rc.3、Python SDK 0.1.5rc1。共享模型为 `deepseek-flash`、`reasoning_effort=off`，每请求最多 1000 输出 token，关闭额外压缩。
- 费用与累计请求次数不限：私有授权 `cap_usd:null`、`budget_policy:uncapped_user_authorized`、`reset_history:false`。只读计算，无外部应用写入或生产发布。
- 原生工具表固定为一个 `group_count`；同一固定 Python 代码、合成输入及当前操作依据。TS 负责准入与工具生命周期接线，计算示例仍需 Python，不能称已实现无 Python 插件产品。
- 参数、来源和代码摘要随私有 `config.json`、历史账本快照、原生 `*-native.json`、`*-provider-records.json` 与 `summary.json` 保存于本轮 `.local/f02-protocol-local-20261024-v1/attempt-*`。原始事件/回答不提交 Git。

```sh
npm run rsi:demo
npm run rsi:check
# 显式真实联调，路径均为操作者自己的私有记录：
node scripts/project.mjs python scripts/check-rsi-protocol-real.py \
  --real-model --native-harness \
  --authorization .local/authorized-budget.json \
  --history .local/historical-account.json \
  --output .local/f02-protocol-local-20261024-v1
```

密钥由 `DEEPSEEK_API_KEY` 环境或既有私有 `.env` 提供；不进入参数、文档或日志。新进程由既有本地代理转发官方 API，原历史账本只读汇总，费用 checkpoint 不清零。

## 实际运行与费用

| 尝试 | 真实请求 | 结果 |
| --- | ---: | --- |
| 首次依赖定位 | 0 | 新检出缺少 npm Runtime 入口，请求前停止；失败保留 |
| 有界语义选择 | 3 | A/B 选择汇总，C 交接；局部结果符合期望 |
| 原生 Harness 第 1 轮 | 5 | A/B 各执行一次，C 无工具执行 |
| 原生 Harness 第 2 轮 | 5 | 补齐任务 ID / 原生 call_id 关联后复核通过 |
| 原生 Harness 最终轮 | 5 | 最终协议与原生/计量关联通过 |
| **本轮合计** | **18** | **18 个上游回执均 HTTP 200，用量完整；无新未知费用** |

合计输入 7056 token（缓存命中 2560，未命中 4496），输出 491。按现有代理峰值费率重新计算约 **USD 0.00195336**；逐行日志有显示精度舍入。账单未核对。官方峰值单价为缓存输入 0.006、未命中输入 0.30、输出 1.20 美元/百万 token，周末非峰值费率为一半；本轮继续用保守峰值估费，不把它称作实付账单。[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)

沿用本地历史 7340 请求/USD 10.45040444（244 个账本/回执摘要，含 3 笔未结算请求）；当前本地已知累计为 7358 请求/约 USD 10.45235780。其他主机和账单仍未知，原记录、失败和预留保留。开发、安装、审核时间没有计作收益；没有质量/费用对照，不能据此计算节省比例。

代理在成功响应后打印过本机 keep-alive 连接重置警告；18 条上游记录均完整结算，不据该警告虚构额外请求，也不删除它。

## 检查、失败与限制

- F02 定向：28 项 Python、30 项 Node 通过，含两项原生工具生命周期 HTTP 诊断。免费固定 Provider 仅用于这些诊断，真实行为结果来自上表的真实请求。
- 既有 smoke 与 motif:check 通过。最终冻结源码完整检查：Python 1547 过/235 skip；Node 1405 过/15 skip/1 失败。唯一失败是下述旧上传 typed-413 检查，不能称全仓全绿。
- 环境失败保留：最初复用环境缺 PyMuPDF；新隔离环境又缺报告导出所需 matplotlib。补装 matplotlib 3.11.2 后，原两项报告导出失败消失（相关文件 16 过/1 skip），未改或放宽断言。
- macOS `/var` 临时目录别名触发 12 项既有路径守卫拒绝。使用物理路径 `TMPDIR=/private/tmp` 后相关 40 项检查为 39 过/1 skip，守卫不变。
- 旧超大上传 `oversized upload already in flight still receives typed 413` 检查出现 EPIPE/ECONNRESET；未修改的 #114 基线独立复跑同一文件也是 8 过/1 失败，因此保留为已有本机传输问题，本 PR 不改网关。另一次在测试期间修改源码，触发新增 SHA 一致性检查；冻结源码后 F02 定向及最终全量中的该项通过，失败不删除。
- 人工算子诊断宿主的认证标记不等于真实学习认证；实际原生 guard、独立证书和不可变 Registry 不能被该标记替代。科研/邀请自然语言质量未盲评。

## 接下来怎样验收

两位合作者先审共同格式、当前操作依据及 F03 计量接缝；#114 的 G0 研究约定通过后再冻结 ABI。F05 提交真实反馈产生的规则/分支变化，F08 提交真实 Matcher 代码变化与独立验证。本 PR 用 Refs #110，不自动关闭整个 F02；不合并或部署。
