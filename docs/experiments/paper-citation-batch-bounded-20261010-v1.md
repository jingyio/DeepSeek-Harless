# 引用取证阶段权限：失败与恢复反馈

- 实验 ID：paper-citation-batch-bounded-20261010-v1；2026-10-10，Codex。
- 假设：统一缩小取证阶段工具范围能减少无关检查，使冻结结构有更清晰的续接边界。若仍循环猜参数或没有合格交付，则不支持该阶段已形成稳定收益。
- 条件：与前轮同一主稿及阶段输出；新 opt-in --bounded-evidence 要求 --arxiv-batch，只对本实验生效。三组计划使用同一7工具：四个citation MCP、web_fetch、write、edit；写入仅工作区triage.json、登记只允许当前case。项目/Web/Coding默认工具保持原状。不修改上游或重启Web。
- 模型、预算：真实deepseek-flash，推理off，输出8192，关闭压缩，无请求次数上限，私人副本已授权非沙箱。累计起点4.70861215，上限4.84521046美元；新ID不重置。只实际运行baseline，未运行本条件shadow/execute。

## 实际结果

baseline error，19次真实请求、新增估费0.030576108美元、57.338秒，无triage，来源未变。真实请求schema确认7工具权限生效。9次登记中8次case_id猜错，被守卫拒绝，第9次正确登记；另有29次web_fetch。下一请求的保守长上下文预留超过余额，代理返回预算拒绝，Harness表现error；不是次数限制或已证实的供应商限流。

最终累计代理估费4.739188258美元，余额上界0.106022202美元；账单未知。未完成输出，不计算合格成本或请求降幅；未把失败续写当作独立训练或验证任务。不能用本轮证明20%目标。

## 修复与验证

错误消息原先仅表示“只能登记当前案例”，未提供正确case_id，模型反复猜测。已在后续代码提供登记case_id，使失败可恢复；守卫仍拒绝跨案例。此修复未追改本次轨迹，未付费重试，尚未验证真实恢复效果。两端全量215 Python/93 Node通过；反馈专项8 Node通过。MCP无模型预检主稿34引用键/15标识、短稿14/5、合成缺失1/重复1，全部守卫检查通过。

原始证据、实际请求schema、失败账本/manifest与输出放私有 .local/paper-reference/<ID>/，双端同步，不进Git。baseline执行时权限代码副本另存evidence-policy-executed-v1.ts并与manifest哈希核对；当前反馈修复不是当时执行版本。effective-config-supplement.json记录事后环境、schema/用量，账单/盲评/人工时间明确未知。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase preflight --experiment paper-citation-batch-bounded-20261010-v1 --arxiv-batch --bounded-evidence
# 付费调用仍需--call-model；已有run不可覆盖，恢复须新快照且沿用原预算。
```

下一步：先检验准确参数反馈和端点契约，再扩大从轨迹编译的元数据/网页参数节点；有足够费用预留后才开展新条件匹配基线/shadow与质量评审。不能靠降低守卫、忽略解释或反复换ID达到比例。
