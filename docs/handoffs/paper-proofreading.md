# 论文校对当前交接

- 更新时间与交接人：2026-10-20，Codex。
- 目标与范围：补通新报告失败的采集、条件编译认证和实际加载，保留当前证据安全边界；真实测试后仍未证明稳定净降本，不扩场景、不调 embedding。
- 分支/提交：独立 `codex/paper-negative-recovery`，基于 origin/main `4b7a215`（PR94 已合并），实现提交以本分支 Git 历史为准，本地提交尚未推送。原脏工作区未动；尚未 PR/合并/部署，遵循效果稳定后再 PR 的要求。
- 已完成：`negative_outcome.py/.ts` 统一 `failed_checks` 与旧协议，成功对照必须有明确成功标志；`negative_constraint_compiler.py` 对已审阅 `structure_issues` 原语做实际回执与双向干预认证；TS 绑定当前完整 scope 重算错误条件。负面提示追加发送，只有实际模型请求看见后才允许早停。未知页数原因仅提示。
- 当前值复用：`reuse_mediation.ts` 新增 `patches[].from`，复制字段并检查两端依赖；已匹配负面条件可提供候选，不能自动修订或声称语义无损。runner 新增 `--recovery-goal-scope`，原 scope SHA 必须与实际失败回执一致，将失败候选与完整目标分开。
- 已验证：定向 Node56；全量 Python1300/Node1159 通过，213/5 跳过；无模型 smoke18题/83来源及 motif:check 通过。初次遗漏项目 Python 的局部失败日志保留；本轮未运行 GitHub CI。
- 真实结果：共3次历史产物局部恢复，113请求，13次实际提示、6次局部早停，完整请求skip为0。001为38请求/$0.071828424，逐条记录/来源版本保留；002为47请求，流超时未交付，保守估费$0.266239308含待核预留；003为28请求/$0.050857044，导出通过但逐条表和来源文字被改写，模型没选择字段复制候选，不能认定无损降本。两次成功后均无额外工具调用。
- 实验结论：[本轮完整记录](../experiments/paper-negative-recovery-20261020-v1.md)。排除了“新失败不参与编译/加载”和“只能拦重复 ID”；剩余主瓶颈是开放模型循环里反复读取/生成脚本和未知的页数修复条件。不是通用自动原因学习，不是跨论文独立评测，也未做科研盲评。
- 配置与数据：`.local/paper-negative-recovery-20261020-v1/` 保存授权、逐轮配置/日志/quality/native/breakdown/aggregate；003用 execute-003.json、negative-004、native-002。完整源码/环境快照随 `.local/script-motif-experiments/<run>/` 保存，不追改旧hash。未调用 embedding；离线编译模型费用0。
- 最短复现：按实验记录统一runner命令；结构恢复在原参数上增加 `--recovery-goal-scope`，需要已授权字体/原始输入/实际checkpoint/锁定的库及 `SSS_LOCAL_SCRIPT_EXPERIMENT=1`。代码锁变化必须重编新库，不能改旧摘要。
- 权限与预算：本地 DeepSeek Flash，reasoning off，输出32768，请求/费用不限，reset_history:false。本轮保守估费$0.388924776，已观测$0.213109776，余$0.175815为1笔待结算预留。累计5085请求/$8.701509444保守估费，旧pending2+新1；V100/账单仍待核。三个真实任务已结束，不重启生产服务。
- 接手下一步：1）对已认证错误实现有界的类型化修订交接，先确认模型实际选择当前值复制、Runtime连续执行，减少数组搬运脚本。2）核验逐条记录/来源信息与最终解释的保留，不用形状合格代替科研质量。3）局部复杂恢复收益稳定后再提交PR、考虑独立论文和扩场景；目前不宜用单次成功声称净费用下降。
- 回退与风险：禁用负面sidecar/实验恢复开关回原路径；公共库、生产服务、私人原件不改。未知数值形状及缺少证据均退回模型；不把页数观测当根因。

前轮：[显式当前操作接管](../experiments/paper-recovery-control-20261020-v2.md)、[恢复与成功复用](../experiments/paper-recovery-evidence-20261020-v1.md)。
