# 脚本规则/目录变化、普通修复与第二版认证

用户授权继续验证旧脚本失效、原同会话普通 Harness 修复、新普通轨迹学习与独立认证，再用新留出比较质量和完整成本；原 testpdf 实验副本权限、DeepSeek 配置和 1000 USD 系列上限保持，暂不提交/推送。

新增 `script_adaptation_study.py` / `script_adaptation_learning.py`、`dsh_learned_script_v2.ts`、独立审计与真实 SDK/MCP 免费检查。第一版执行器、编译器、候选/证书/原轨迹和原留出不修改；现有六个实际服务依赖、14 工具/schema 和现有 Motif 库不变。没有新增公共 CLI 参数、HTTP task kind 或默认 SDK/Web 激活。

`sss-learned-copy-script-v2` 保留原有受限复制语法，增加从真实普通选择推导的 min/max 哈希代表与排除零字节 .txt 的原件选择。复制目标用实际任务 destination_prefixes 的槽位绑定，原件/前段备份仍通过真实身份传递。目标摘要、上下文文本摘要与实际目标前缀组成成对的 guard_cases，禁止将分别见过的目标/规则/目录任意交叉组合。模板绑定执行器自身、共享 digest/事件工具和终结流模块的原字节 SHA；证书绑定同一依赖，旧证书不静默迁移到新代码。

新增可选 `SSS_LEARNED_SCRIPT_V2_BINDING`，仅私有实验 patch 启用。与 L1 分开选择，每个任务至多一个脚本执行器；版本、输入、目标、规则、读取范围、权限、工具/schema或字节守卫不符时永久停用，原同会话普通模型接管。每次效果仍通过原 preview/execute，复制后核对实际字节快照和收据，最终由原固定验收裁决；无任意代码执行或权限扩大。

`SSS_SCRIPT_REPAIR_PROBE` / `dsh_script_repair_probe.ts` 只用于四项初版验证和一个新副本补充验证：实际 L1 失配后生成一次“未完成草稿”终结流，无成功回执、无副作用或模型决定伪装。原固定验收记录第一次失败，原 Harness 分配一次修复，真实 DeepSeek 在相同 session、任务、5 USD/96 步及两轮上限内执行/交付并复验。该受控草稿与 L1 介入轨迹不得训练；不把主动设置的失败解释为自然模型错误或产品频率。

首批新普通训练覆盖两种去重选择和两种备份选择，各两份不同数量/目录的真实任务。清洁普通 H 轨迹才可学习；免费/模拟、旧脚本回退、验收修复/restore、独立认证和留出全排除。候选先冻结，8 次新 L2 实际执行认证通过后，才创建 8 条件×H/S/M/L1/L2 共 40 新留出。

目录变化分别报告：FM17 的 source/ 内嵌套重排属于 L1 原参数能力；FM05 改源根/目标路由越过原匹配边界。新规则是 FM05 最小→最大路径代表、FM17 排除零字节文本且保留零字节 Markdown。预写 S 按新规则人工维护且 API 可为零，人工金额按用户要求不折算；M 使用原兼容读取图，FM17 普通回退。L2 计入旧 L1 获取成本、新验证/修复、新探索及认证，增量和从头总 API 费用分别报告。

状态及最终结果见 [实验记录](../experiments/file-management-script-adaptation-20261014.md)。已完成65次实际运行、790HTTP、USD0.715712544；正常H/S/L2各6/6、M5/6、L1 4/6，10版本受控停止未完成。L2完整API USD0.374614224，仍不优于预写脚本。当前仅开发材料机械质量，真实办公盲评、账单与跨平台行为另列，不能由单次基准推断通用学习或自动维护优势。

补充生命周期与审计接口：study新增--training-parent，仅允许尚未暴露候选/认证/留出的既有验证与普通探索记录，经原protocol/outcome/source依赖SHA只读引用；原失败与排除费用一次计入维护，新source/version保存为新实验ID。源目录/目标路径说明在新题面明确，原14工具、业务后置条件和读取权限不变；不读取隐藏oracle做脚本选择。维护25次/356HTTP/USD0.274608132保守归入L2，另计首版准备；S人工金额按用户要求不折算，工时未核实。

版本V沿用dsh_workflow_experiment在实际preview后改变副本，并在下一loop主动中断，不能当自然模型回退/恢复证据。新增scripts/check-script-adaptation-stale-sdk.py是独立免费诊断入口，不改冻结运行器：生成私有sss-free-stale-preview patch与SSS_FREE_STALE_CONTROL，只变声明的副本目标且不主动中断，使实际L2 execute_plan收到MCP错误；随后模拟普通Provider原两轮验收后保持未完成、未知字节保留。脚本停止后的自动派发为0、0云请求，role=free、不学习或计真实收益；原事件、检查器/临时插件/patch SHA保存。补充检查源码在paid-source之外的analysis-source单独归档，不追改已执行协议。

回归：test_script_adaptation.mjs覆盖两代表顺序、零字节txt/md选择、受限指令/schema/源闭包拒绝；test_script_adaptation_learning.py覆盖角色排除、认证暴露禁止、失效MCP依赖拒绝和失败导入费用一次保留。project.mjs仅注册新增Node测试。npm test 573Python/173Node通过（3可选Docker跳过），18题免费smoke；实际SDK检查及65次独立权限/字节/HTTP/原事件/停用/角色审计通过。v1、公共run-scenario/验收器/acceptance_guard、依赖与默认SDK/Web配置均未变动。
