# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：响应用户纠正，Negative Motif 必须识别错误相关字段及失败条件，不能仅依赖工具序列/完整参数原样重试。本轮实现受信只读校验器的自动字段切片与跨版本局部门控，未证明稳定净降本。
- 分支 / commit / 工作区：独立 `codex/paper-negative-dependencies`，基线 `0d732c6`；本记录随实现本地提交，具体见 git log -1。未推送、未 PR、未部署；原脏工作区、生产服务、旧认证库与原始论文不改。
- 已完成：新 `negative_field_compiler.py` 从 AST 别名、静态键、映射及比较导出依赖字段和必要失败条件；`learn-negative-motifs.py --field-profile` 用真实失败/成功状态及局部依赖外干预认证。显式审阅的只读函数必须属于历史工具实现锁；不自动执行模型脚本、不逐错误注册字段，不是一般因果学习。
- 已完成：新 TypeScript `negative_field_runtime.ts` 有界解释纯数据 IR；`script_negative_runtime.ts` 先当前失败提示，再确认 notice 实际进入模型请求。来源/目标/schema/包装任务身份/非版本参数不变、当前实际 SHA 匹配且谓词仍成立时，跨版本拦截工具主体；真实修复、类型未知、范围变化及其他工具可继续。不将拒绝当新训练失败或完整模型跳过。
- 已完成：原有正负库装载、原生 Harness tools.guard 与回退复用；5 类负面规则中 1 类升级为 sources[*].id 唯一性条件，复杂枚举错误等仍保守回退。正面 7 算子在新依赖锁下实际重新认证，未重写旧库锁，不扩 30 工具。
- 已验证：完整 915 Python/884 Node 通过，199/5 跳过；无模型 smoke 通过。最终仅修正未绑定时的提示文案，16 项相关 Node 再通过；最终库重新编译/认证并检查共同装载。原生工具注册器验证修改内容和版本但仍失败时主体不执行，其他工具正常；跨语言通用 records/tag 夹具验证非论文专用提取。
- 实验结论：[paper-negative-fields-20261019-v1](../experiments/paper-negative-fields-20261019-v1.md)。在新私有副本中实际重放历史 85 次 stage，全部 SHA 与原结果一致；27 次 finalize 原错误重现；18 次重复 ID 条件为 true，另外 9 次枚举错误为 false。实际 notes 干预仍同错误；认证另有 8 处依赖外编辑。历史重放与训练同轨迹、干预为局部诊断，不是独立真实任务、模型早停率或净收益。
- 配置与数据：私有 `.local/script-negative-fields-20261019-v1/` 保存 field-profile/effective-config、replay、snapshots、field-evaluation-final、full-test/smoke/node-final 日志和认证拒绝。最终负面 library-004 digest `4fcbd3b9a0c1b7358538da44cfeded95ae2a0e8fb0075768ca7bf79e62d520a5`，正面 positive-library-002 与 combined-config.json；旧轮 `.local/script-negative-20261019-v1/` 及所有失败轨迹保留。
- 未完成与阻塞：尚未在新模型任务验证提示后的字段修复与全流程收益；复杂控制依赖/不透明 Bash、Python 错误不支持；未修复草稿不可读/不可修复接口，也没有一般多节点负面图、自动修复或全局早停。前轮服务/流错误与不合格报告仍是有效负面证据。
- 接手下一步：1）修复可读、可修复且幂等的草稿接口与可信错误返回，保留版本守卫。2）在新独立任务及相同完整质量门槛比较 Prompt/Enforce 与普通工程基线，记录全部失败/学习/恢复成本。3）复杂条件扩展通用控制依赖，不写逐错误规则；合格且稳定后用户决定 PR。
- 最短复现：先看 docs/interfaces.md 的 Negative Motif 接口；编译真实已结束 task + 匹配历史 implementation-file + 私有 field-profile，写入新 output；npm test / npm run smoke，相关 Node 入口为 tests/test_script_negative.mjs。本地使用项目 Python、TMPDIR=/private/tmp，沙箱需 SSS_LOCAL_SCRIPT_EXPERIMENT=1；renderer/font 沿既有私有配置。服务器/Windows 未做新验收。
- 权限与预算：本地真实测试沿用无限额授权，本轮未新增模型调用。累计旧本地 2835 请求/保守估费 $4.714453692，旧 1 pending 保留、V100 未核清，非账单实付；CPU/HTTP 认证与开发时间未完整计量。没有后台付费任务。
- 回退与风险：关闭 negativeLibrary 即恢复正面行为，回退 0d732c6 恢复前轮代码；实验代码锁改变须重新实际认证，不能编辑旧锁。原始材料、旧快照、失败与账本全部保留。当前结果不足上线或 PR。

前轮：[负面提示与原样重试](../experiments/paper-negative-motifs-20261019-v1.md)、[连续执行](../experiments/paper-script-frontier-20261019-v1.md)、[脚本 Evidence](../experiments/paper-script-evidence-20261019-v1.md)、[初版](../experiments/paper-script-motif-20261018-v1.md)。
