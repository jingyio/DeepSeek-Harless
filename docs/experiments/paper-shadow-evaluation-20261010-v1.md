# 论文评测改为 shadow 主线

- 更新时间：2026-10-10；按负责人最新要求调整评测路线。
- 类型：对既有真实 shadow 的历史分析，未新增模型运行、未新增付费请求；不算新的独立任务。
- 问题：在保持原生 Harness 真实执行的条件下，定位结构匹配、证据失败和完整工具调度请求，避免跨运行策略差异干扰早期机制评测。

## 评测口径

1. 冻结训练库、题面、来源、工具契约/顺序及权限配置，继续记录真实质量、请求、缓存、费用和耗时。近期主线为 shadow；不因候选命中改变原生结果。
2. 分别记录选定批次、候选工具数、验证通过/失败/未观察项。当前显式选择目录与提交协议为工程适配，不能把 30/30 当作全 Agent Loop 覆盖率或自动挖掘完整工作流的证据。
3. 关联成功提交绑定后的下一次原生模型消息。只有完整调用集合匹配、无其他动作、全部结果通过守卫，才能列为保守的纯工具调度机会；按 turn/step 去重，不按工具次数累计整请求。
4. 匹配工具同时有文本时，列为“需要语义审阅”；文本可能只是调度说明，也可能承担研究判断，分析器不猜。混有其他工具、失败或证据不全时不纳入保守机会。
5. shadow 实际跳过为 0，直接跳过请求产生的节省为 0；反事实费用未知。潜在机会不意味着未来 execute 会保持相同质量/缓存/策略。模型科学判断、报告质量和语义误判率需要独立评审。
6. 不选择“最便宜的一次 shadow”作为成绩，也不把不同轨迹 50→15 当作 Motif 收益。相同条件下报告全部运行和失败；下一阶段优先独立任务/来源更新，当前同一论文重复会话不算跨任务泛化。

## 已有真实证据

来源：`paper-reference-continuation-20261010-v2/runs/continuation-shadow`，此前实际模型 `deepseek-flash`、推理 off、输出 8192、无次数上限、压缩关闭。库从先前五条正常轨迹冻结，未使用本次结果重新选取原型。原实验代码/预算/范围差异见前一份记录。

| 指标 | 结果 |
|---|---:|
| 实际模型请求 | 15 |
| 显式选定批次 | 4 |
| 结构结果通过 | 30/30（15 读取、15 查询） |
| 完整结果通过的批次 | 4/4 |
| 保守纯工具调度机会 | 3 次 |
| 匹配工具但含文本、需审阅 | 1 次 |
| shadow 实际跳过 | 0 |
| 反事实费用节省 | 未测量 |

这次真实 shadow 代理估费 0.038702724 美元、耗时 60.54 秒，属于此前已发生支出。本次分析没有新费用；历史累计约 4.19263，冻结上限 4.84521046，余额上界约 0.65258，账单未知。

含文本的响应经 Codex 初阅只有读取选定记录的调度说明，没有该响应内的科研判断；自动分类仍单列，独立质量认证未完成。初阅另存 `shadow-text-review-v1.json`，不追改自动统计。

最终条目集合覆盖 15/15，但前次初看仍有过度判定作者省略等语义问题，质量未盲评。shadow 更可靠的含义是降低接管对原生流程的影响，不代表这一次报告更准确或更便宜。

## 实现与复现

- `scripts/paper-reference-continuation.py`：近期默认模式 shadow；无 `--call-model` 仍只预览，旧运行拒绝覆盖。保留显式 baseline/execute 入口。
- `scripts/evaluate-shadow-continuation.py`：独立历史分析器，不调用模型、工具或网络；隔离 root Session，定位真实请求边界，输出输入/代码哈希和候选分类；新输出文件拒绝覆盖。
- 私有分析结果：`.local/paper-reference/paper-reference-continuation-20261010-v2/shadow-evaluation-v2.json`。旧初稿分析文件保留，不覆盖原始事件、答案或账本。

```sh
node scripts/project.mjs python scripts/evaluate-shadow-continuation.py \
  .local/paper-reference/paper-reference-continuation-20261010-v2/runs/continuation-shadow \
  --output .local/paper-reference/paper-reference-continuation-20261010-v2/shadow-evaluation-v2.json
# 仅重测当前原稿/题面时给新 suffix；仍受原累计预算约束，不新开额度。
node scripts/project.mjs python scripts/paper-reference-continuation.py --suffix=-new-shadow --call-model
```

## 验证与交接

专项 7 项诊断通过：纯工具与实际收益分离、文本审阅、混合工具拒绝整请求计算、失败/缺失证据不认可、子会话隔离、execute 不冒充 shadow，以及既有 Bib 解析。本机与服务器免费全量 177 Python / 80 Node 通过。没有进行新的模型行为验收；本次分析使用已有真实运行。

下一步先由负责人独立审阅风险等级与来源，记录反例与未覆盖部分。当前入口仍固定此前原稿；独立论文/修订任务须新增显式输入配置、冻结摘要后再继续 shadow，不能把改 suffix 当新任务。保留 execute 作为之后定向验证的工具，但本轮不自动运行。代码未提交/未推送，团队尚未同步到主分支。
