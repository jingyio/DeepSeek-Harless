# 历史管理 Motif 的本地重认证

2026-10-18，用户要求检查旧库、按当前契约重认证可复用结构、保留旧版及失败费用，并只读对比个人 GitHub 分支。本轮不推送、不合入 main。实验结果另见 `docs/experiments/management-recertification-20261018.md`。

## 计数与失效

历史连续库有28个不同版本 artifact：24个操作图归为10种精确节点/绑定结构，另外是3个集合版本与1个两阶段版本。这不含更早公开库中的所有专用流程、清单或脚本，也不等于28种独立工作流。日常入口原第12版8项中，5项状态为active，但只有1项运行时源码完全兼容；4项版本过期，另外3项disabled。

失效检查绑定原运行时文件字节。旧认证通过不表示能在新MCP、权限和目标验收契约下直接复用；源码变动也不证明旧结构本身错误。旧证据和政策保持原字节，新认证生成新对象和追加版本。相同结构的多个旧版本只认证一次，已有当前有效认证不重复付费。

## 离线接口

新增 `src/adapters/management_recertification.py` 和 `scripts/recertify-management.py`。这是显式维护入口，不改变前端MCP工具、在线TypeScript解释器、权限或预算协议，也不自动批量重签旧档案。

```sh
node scripts/project.mjs python scripts/recertify-management.py \
  --old-policy .local/path/to/old-policy.json \
  --old-certificate .local/path/to/old-certificate.json \
  --template .local/path/to/frozen-template \
  --job .local/rsi/daily-management-real-v3/learning/new-recertification-job
```

不带 `--call-model` 只校验原证书并显示原预算。显式真实执行沿用既有密钥加载器，不在参数或日志打印密钥。模板需包含 `task.json`、`pristine/`、`enrollment.json`；enrollment提供原提示文本及场景文件位置，明确为材料模板，不能冒充模型训练记录。

历史策略只能提出节点和参数绑定。当前工具catalog重新核验每条导出边、必填参数、节点边界和自动续接权限。三份不同新材料分别用于：无经验库的真实模型原生见证，以及两个隔离候选库中的真实执行。两次均须实际完成全部节点、通过交付与权限检查、没有验收修复或deferred，并通过原 `check_motif_certificate` 才发布。

短图可以是实际原生长图的连续前缀。新证明保存每个真实调用、结束结果序号及完整事件摘要；只限定图观察的结束点，不删除或重写原始事件，不跳过失败、未知工具等中间屏障。原完整任务仍经 `frame()` 校验。此路径用于重新认证已学结构，不是用手写图替代自动发现。

复制后读取的认证材料另冻结 `recertification-checks.json`，把新副本完整读取绑定到该次原件摘要；原适配器继续重算正文和元数据。该附加检查只收紧认证，不修改产品v4验收。产品现有read谓词直接查原始路径，对新生成文件的读取目标表达仍有限，不能把本轮离线附加检查称为已修复全部日常语言验收。

认证仍使用management_v3、quality-v4、operation-certification-v2，系列USD1000、共享学习USD25、单任务USD5/96步和请求/4000输出/2次修复。不中断原账本，不给历史批准令牌新权限，不使用最终留出集。

未完成认证恢复原enrollment及原预算；已封存结果复用，不重复付费。缺少可重放的中间文件等磁盘错误会保存拒绝结果，而非激活或循环重跑。已有失败只保留；新材料或协议修订有独立锁，不能覆盖旧标准和成绩。

## 兼容边界

当前原生 `/management` 执行operation_graph，旧collection/reentry专用IR和旧计划/恢复工具没有直接接入这个入口。集合参数图可能覆盖部分相同操作，但不表示完整迁入旧foreach或两阶段宏。高风险确认和跨任务撤销继续按原生权限处理。脚本、政策清单、认证摘要也不能一律计作当前活动Motif。

新对象、原轨迹、完整证书与费用都在私有 `.local`；重认证证明含本机材料定位信息，不作为可直接公开的分发包。本轮GitHub对照只读个人分支及已有公开包，公开包均不自动授权激活。
