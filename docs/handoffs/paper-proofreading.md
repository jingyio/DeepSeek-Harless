# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：接续第三轮执行片段，按用户要求增加 Negative Motif：先 prompt 引导，再局部早停。当前已实现实验编译/在线接线；仍未实现稳定净降本。
- 分支 / commit / 工作区：独立 `codex/paper-negative-motifs`，基线 `44a1d36`；本记录随实现本地提交，具体见 git log -1。未推送、未 PR、未部署；原脏工作区、生产服务、旧认证库与原始论文不改。
- 已完成：`script_negative_compiler.py` / `learn-negative-motifs.py` 从真实 MCP 失败和非失败对照学习工具、错误码、版本回显与 false outcome 标志；5 类规则，4 类具备严格同版本重试资格，批量超限仅提示。不是手写错误名 if 分支。负面学习仍为显式离线入口，未接成生产自动学习。
- 已完成：`script_negative_runtime.ts` 复用 observation 解包 MCP canonical value，先在当前失败后提示；确认 notice 进入实际模型请求，且同参数/同 JSON 状态文件/原来源/目标/schema 未变时，用 tools.guard 阻止工具主体；其他路线仍可用。新反证、输入变化和不透明错误失效。拒绝不被当作新训练失败，不把工具早停记作完整模型请求跳过。
- 已完成：Web adapter 允许正负库共同装载或单独负面消融；不扩 30 工具。正面认证代码锁补负面 Runtime 依赖，另行实际重认证；旧库锁不改。runner 增加显式同源私有 checkpoint 局部恢复与诊断超时取消，不能把恢复探针算完整任务。
- 已验证：完整 906 Python/881 Node 通过，199/5 跳过；无模型 smoke 通过。探针后收紧 false outcome 资格，局部 25 Python/33 Node 通过。原生 ToolRuntime 两次重复调用被阻止、主体不运行，其他工具可执行。最终安全收紧未再跑付费完整任务。
- 实验结论：[paper-negative-motifs-20261019-v1](../experiments/paper-negative-motifs-20261019-v1.md)。真实局部三臂在 3/3/4 请求后 HTTP 502 失败，未命中负面模式。初次协议探针 18 请求，暴露新模块漏解 MCP 包装，0 提示；修复后探针 14 请求，捕获真实 duplicate_source_ids、绑定当前草稿哈希，notice 进入下一模型请求各 1 次，但模型未原样重试，真实早停 0；后流失败。没有净降本/合格恢复结论。
- 核心覆盖限制：原失败轨迹 35 次已知模式中，只有 3 次同完整参数原样重试，32 个不同绑定。全文件版本变化（包括无关 notes）会放行，未学习错误字段依赖范围；不能消除此前 181 次报告请求差。原报告草稿不可读/不可修复的接口问题仍未修复；负面早停不能掩盖未完成交付。
- 配置与数据：DeepSeek Flash/off、30 工具同序、局部输出 8192、费用/请求不限，180 秒取消检查从 submit 返回计时。私有 `.local/script-negative-20261019-v1/` 含授权、配置、库、runs/aggregate/final-state、失败日志；各 run 原始轨迹在既有 `.local/web/runs/`。训练用一条真实失败轨迹与两条结构定稿成功对照，费用在旧账，不重复计。
- 库：最终负面 library-005，5 类，digest `4b2c4796ca1713b8267e55a38ccc17e12e70d7453e033765143b5b13befe273f`；真实探针用此前 library-004。正面重认证（7 算子，digest 692b36f562a93597db334d5eacaea93344786e3911180cd4c98e46146bbf96b8）与 combined-final-config.json 私有保留，正负共同装载检查不等于真实共同执行验收。服务器/Windows 未做新验收。
- 未完成与阻塞：服务商/流错误导致真实局部对照中断；没有真实模型再次提交同版本错误后的早停样本；最终代码仅局部回归。当前负面模式只有失败结果与原样重试，不覆盖 Bash/Python 的不透明错误，不支持一般多节点负面图、错误因果学习、自动修复或完整任务全局早停。不得把中断/局部工具拒绝当节省。
- 接手下一步：1）修复可读/可修复且幂等的报告草稿接口和可信错误返回；学习相关字段依赖，保留反证/变更放行。2）服务稳定后在新任务、相同完整验收条件下比较 Prompt/Enforce 和普通工程基线，包含失败/学习成本。3）与正面执行片段联测合格交付，稳定后由用户决定 PR。
- 最短复现：见接口 Negative Motif 实验接口与实验记录。learn-negative-motifs.py 传真实已结束 task、当前匹配的 implementation-file 和新的私有 output。sidecar `negativeLibrary` + `negativeMode:prompt/enforce`；需要正面片段再加载重新认证的 library 与原配置。局部恢复显式 recovery-checkpoint，来源哈希必须相同。
- 权限与预算：本地真实测试按现有无限额授权；本轮新增 42 请求/保守估费 $0.126775512，usage 可见 $0.016726812，4 未知 usage、pending=0；提交前目录失败 3 次为 0 模型请求。连同前轮本地 2835/$4.714453692，旧 1 个 pending 仍保留，远程 V100 未核清，非账单实付。所有本轮任务已结束，未继续付费重试。
- 回退与风险：不用负面配置恢复原有行为；回退到 44a1d36 恢复第三轮代码。旧结果用旧快照与库；不要更改旧锁、删除 .local 或重置账本。结果不足上线或 PR。

前轮：[连续执行](../experiments/paper-script-frontier-20261019-v1.md)、[脚本 Evidence](../experiments/paper-script-evidence-20261019-v1.md)、[初版](../experiments/paper-script-motif-20261018-v1.md)。
