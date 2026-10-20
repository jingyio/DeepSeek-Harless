# 未知目标回退与跨计划去重写入检查

2026-10-14，用户授权在本地修复未知目标回退的重复文件问题，使用新材料验证质量和持续学习相对冻结库的完整费用；旧最终留出不学习，暂不推送 GitHub。沿用 DeepSeek、reasoning_effort=off、系列1000美元上限、每题5美元/96请求步/4000输出/最多2轮原验收修复，只操作 testpdf 的新实验副本。

## 写入接口

`scenarios/file-management/workflow_tools.py` 在 FM05 精确字节去重合并中增加跨计划检查：从真实当前 SHA 与获准目标前缀推导已占用的字节组，再合并当前预览动作；相同 SHA 的第二个输出在任何副作用发生前拒绝。`execute_plan` 在写入及备份分配前复验同一条件，已有回执的重复调用保持幂等，外部版本变化仍先由原状态检查拒绝。

这是 FM05 的交付不变量，不将其推广到备份流程。FM17 仍允许为不同原路径复制相同字节，随后必须从真实备份恢复。去重检查不读私有 oracle、不选最大或最小代表；模型须读取真实规则，选择路径。错误代表仍会被原独立验收拒绝。替换已生成代表需用原授权 `restore_plan` 按反向执行顺序恢复，不新增删除、覆盖、读源内容或重启权限。

`submit_report` 另检查每个实际原始 SHA 组已有恰好一个输出，包括空文件。遗漏时返回真实 SHA 与已有获准来源路径，要求按实际规则补齐；不读取私有预期代表路径、不授予额外读取权限。第一版仅查重复仍漏掉一份104字节文本，第二版补上覆盖检查；原失败留存，不重跑原题改成绩。

`read_task` 为 FM05 增加只读 `workflow_effect_constraints` 输出，说明跨计划 SHA 唯一性、提交时完整覆盖、代表选择职责、原授权恢复方式和拒绝预览无副作用。`preview_actions`/`execute_plan`/`submit_report` 的参数保持原契约。服务文件 SHA 改变，`workflow_execution_version_sha256` 因而变化；原库/脚本/证书的字节和执行版本不改，旧经验失效后回普通 Harness，不能直接改签名让旧库通过。

## 新实验与版本

`scenarios/file-management/fallback_rsi.py` 创建修复前/后的独立新材料，每批6对直接普通 Harness / 实际检索后未匹配回退，按任务交替顺序。新目标只改措辞，规则、权限和隐藏验收绑定不变；这些诊断不参与学习，失败及原修复次数保留。

`scenarios/file-management/continual_rsi.py` 冻结10个新的日常操作条件，H/S/F/R交替运行。旧服务经验原版本留存并停用；从全新普通轨迹重新学习、独立认证当前服务版本下已有四种程序的共享种子，冻结F。新目标表述起初不匹配，两组均回普通Harness；R从实际失配/成本触发的普通轨迹学习新目标守卫并独立认证，最多两轮激活。第一轮成果须在下一轮真实执行。调度上限不因失败增加。

完成两轮升级后才创建新的10条件最终留出，含2个未知目标和2个外部版本变化；F继续用种子版本、R用最后版本，最终运行不触发学习/认证/激活。固定期限不因费用结果为负而延长。检索仍按真实目标/规则摘要及版本守卫，未新增未经认证的同义词匹配。

完整API比较包括同日常流和最终任务、共同历史建库及失败、新服务种子重建、R新增探索/认证/失败，以及本轮共同修复诊断费用。诊断费用列为四组共同验证开销；原历史种子/学习开销只属于F/R。各项从原 outcome/HTTP usage重算，账单实付仍未知；人工金额按用户要求不折算，开发维护不视为零成本。旧最终材料和轨迹不用于学习或候选选择。

## 验证入口

`scripts/check-merge-copy-guard.py` 在真实MCP、新副本中免费检查同计划重复、跨计划重复、执行幂等与恢复后替换。`scripts/audit-fallback-rsi.py` 独立核对组间材料/schema、实际后置字节、原读取范围、模型轨迹、HTTP usage/费用、修复上限、版本链和训练/认证/最终划分；不能把安全停止算作合格交付。

```sh
node scripts/project.mjs python scenarios/file-management/fallback_rsi.py --parent .local/file-management/<原经验库实验> --phase before
node scripts/project.mjs python scripts/check-merge-copy-guard.py --experiment .local/file-management/<修复后诊断>
node scripts/project.mjs python scenarios/file-management/fallback_rsi.py --experiment .local/file-management/<新诊断> --call-model
node scripts/project.mjs python scenarios/file-management/continual_rsi.py --parent .local/file-management/<原经验库实验>
node scripts/project.mjs python scenarios/file-management/continual_rsi.py --experiment .local/file-management/<新持续学习实验> --call-model
node scripts/project.mjs python scripts/audit-fallback-rsi.py --experiment .local/file-management/<完成实验>
```

真实结果见[实验记录](../experiments/file-management-fallback-rsi-20261014.md)。默认SDK/Web未启用这些实验入口；新代码只在本地，不改上游Harness或原Motif IR。
