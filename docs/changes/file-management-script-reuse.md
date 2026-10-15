# 从普通 Harness 轨迹学习复制脚本模板

用户授权：新增学习脚本复用组 L；先新普通探索，冻结模板，独立认证，再创建新留出与 H/S/M 比较。原 1000 USD 系列预算、testpdf 实验副本权限和最多两轮普通修复保持；全部费用、轨迹及失败留存，不推送 GitHub。

本轮新增 `script_reuse_study.py`、离线 `script_reuse_learning.py`、独立审计 `audit-script-reuse.py` 和真实 SDK/MCP 免费检查 `check-script-reuse-sdk.py`。首批仅 FM05 哈希去重合并与 FM17 实际备份恢复。已有服务、计划/任务契约、认证库和原留出不改。

新格式 `sss-learned-copy-script-v1` 保存正常模型轨迹的事件/输入/结果 SHA、任务指纹、实际工具 schema、执行版本、目标摘要、上下文规则摘要及受限指令。编译器从至少两份新独立普通成功轨迹推导 SHA 分组代表选择、目录前缀替换和前段实际输出到后段输入的关系；相邻等价复制可合并为一个有界批次。普通失败、模拟、认证、留出与 Runtime 节点均不得训练。候选在任何认证执行前锁定，认证不改候选。

新增 TS `dsh_learned_script.ts` 只在私有实验 patch 和显式 `SSS_LEARNED_SCRIPT_BINDING` 下加载。复用原 Harness `agent/created`、`tools/result`、`llm/stream`；没有新 MCP 工具、CLI 参数、上游循环或动态代码执行。模板只能 `hash_representatives` 和 `copy_map`，数据来自实际 read_task/list/hash/read/preview/execute/report；32 源上限，最多两段复制，不授权重命名、清理、任意代码或语义判断。

匹配校验实际用户题面、目标、读取范围、复制权限、目标前缀、上下文文本、工具 schema 和服务版本。复制前经过原 preview，复制后核对预期字节快照与执行收据，再提交所有当前身份；原固定验收器决定交付。失配/工具失败永久停用脚本，同会话普通 Harness 接管，仍受原预算/步数/两轮验收修复约束。版本变化实验在既有实际预览边界停止，未知外部足迹不自动恢复。

留出要求独立 `certificate.json` 和候选/源码/题面绑定；认证既有普通 H 参考执行，也有候选 L 在另一副本上的真实 SDK/MCP 执行。仅普通成功轨迹用于提炼，候选自动轨迹只作为认证证据。新留出在认证完成后才生成、四组轮换顺序；现有 M 在 FM05 使用原集合读取策略，在 FM17 保留普通回退，S 两流程为明确固定规则的零模型程序。

自动脚本是从轨迹推导的受限程序模板，不等于 DeepSeek 生成任意 TypeScript 后自动审查，也不证明通用程序学习。脚本选择空间和执行器是工程限制；结果必须与预写脚本比较，学习来源不能单独算调度效率收益。开发阶段机械质量、人类盲评和实际账单分别报告。

验证记录与最终结果见 [实验记录](../experiments/file-management-script-reuse-20261014.md)。默认 SDK/Web/HTTP 前端不启用这份私有库。

实际版本：8792969c首次提炼拒绝一份额外读取见证；ef863a4d按原SHA和不变服务依赖导入未曝光认证/留出的普通探索，补一个新收窄读取范围的任务。5普通中4学习，全部费用计入。新--training-parent仅离线实验协议，不是公共Harness参数；禁止从已曝光认证/留出的父版本补学习。37全量审计、568Python/170Node、3可选Docker跳过与18smoke通过。候选/证书不因新留出修改，当前所有变更本地未提交/推送。
