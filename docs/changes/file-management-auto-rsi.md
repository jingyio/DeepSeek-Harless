# 自动经验库与两轮改进接口 2026年10月14日

用户授权按统一库、自动检索、改进发现、普通探索、独立认证、激活/回退、四组对照的顺序推进。沿用 DeepSeek 配置和系列1000美元上限；本批另设300美元上限，每题5美元、96请求/步、4000输出、最多2轮普通验收修复。工作仅在 `testpdf/file-management-experiment` 新副本进行，不改原三PDF，不上传新私有库或轨迹。

`src/motif_core/offline/experience_registry.py` 提供 Python 离线版本库。原 JSON 字节按 SHA 保存在 `objects`，不可覆盖；`versions/000001.json` 等包含前版摘要、激活/停用状态和来源依赖，`current.json` 原子指向当前版本。新增 `sss-experience-registry-v1` / schema 1，见 [Schema](../schemas/experience-registry.schema.json)。旧库/证书保留。脚本入库要求原字节证书、独立材料、成功实际执行且不靠普通修复通过；Motif 要求原 artifact 摘要与独立任务指纹。任意候选不能仅因频繁出现被激活。

`src/adapters/dsh_experience.ts` 是新 TypeScript 插件，显式 `SSS_EXPERIENCE_BINDING` 私有配置才加载。绑定包含冻结库版本/原字节、当前任务/真实提示/运行代码哈希和审计路径，**没有** `profile_id`、正确脚本 ID 或 oracle 内容。运行时读取真实 `read_task`、`list_files` 和获准规则；目录版本由已认证的路径/字节/parser关系和实际 `pin_file` 核验。对真实目标摘要、规则正文摘要、目的前缀、MCP schema、权限、源成员、服务/执行源码版本进行匹配。冲突或缺失回普通 Harness。保守目标摘要匹配不能识别任意同义改写；未匹配的自然语言目标继续走普通模型，不能当成已经实现语义泛化。

Whole script 执行继续使用原 v1/v2 受限控制器，指令只含 SHA代表和最多两阶段有界复制，不执行任意生成代码。模型选集合后的读取 Motif 继续用现有 TS 控制器；计划仍要求原持久化 job/授权组合绑定。读取边 library 可以统一保存和核验，本次自动执行子集优先选择集合读取；没有增加通用任意图 Runtime 或恢复证书。默认 SDK/Web、MCP schema、原 IR、原脚本和认证代码均保持。新模块不修改上游 Harness。

`scenarios/file-management/auto_rsi.py` 是离线调度入口：真实运行出现重复高成本/匹配失效/失败才安排普通探索，使用实际观察任务的新副本，保留规则、权限和冻结标准。source txt/md 字节变化维持重复类与空文本语义；独立材料生成器转换隐藏 oracle 的原字节身份，**选择和学习不读取 oracle**。既有 Python 关系归纳编译器从原始模型调用及实际效果提炼程序，按指令结构分组，去掉 `profile_id`，不使用标签指定正确模板。最多两轮升级，每机会最多四份普通探索；不足时保留拒绝记录并至多安排两份新副本，原失败题和其修复次数不重置。

候选在第一次独立认证材料曝光前冻结；认证材料随后新建，依固定验收检查真实 SDK/MCP 候选执行、当前字节和回执。候选必须单独通过、0模型修复才能认证；失败保留、不改标准。认证成功自动原子发布新版本。选中候选失败/进入普通修复时，本 Session 停止经验执行；控制器在非留出阶段保守停用相关条目，保留原版并允许新学习。此停用可能因全任务失败触发，不能据此断言读取图本身有缺陷。

持久化控制事件形成逐文件 SHA链；未完成任务继续使用已有 outcome，不再次收费或覆盖。跨版本续接只导入未曝光认证/最终留出、MCP依赖相同的原普通/操作证据，逐文件锁定；失败依旧排除训练且计费。第一轮空候选、失败和补充探索分开记录。

实验 F/R 共用同一真实历史种子：v1两脚本和G4 Motif；R新版本来自本次新普通经验，不能偷用已提前学习的历史v2模板。第一轮新库必须在第二轮实际任务执行成功后才能继续升级。两次自动认证/激活之后才生成新的最终留出；最终36运行按H/S/F/R轮换，冻结F种子和R末版，禁止触发探索或学习。额外相同操作任务流H/S/F对照由 `scripts/compare-auto-rsi-stream.py` 执行，不学习；统一计入执行、种子、探索、认证、失败和修复API估费，人工金额按此前指示不折算。操作流对照后执行，缓存/时间顺序限制如实记录。

免费入口 `scripts/check-auto-rsi-sdk.py` 以拒绝模型请求的本地 Provider 核验真实 SDK/MCP；仅是机制检查，不是质量/费用证明。`scripts/audit-auto-rsi.py` 独立重算实际源/schema/输入/角色、原生训练、候选/证书/版本链、后置字节、原HTTP usage/费用、无修复后自动执行和最终留出未学习。公共测试 `npm test` 注册新 TS 拒绝场景和 Python库/机会/冻结回归；相关 smoke 仍无云调用。

入口默认准备/预览，显式 `--call-model` 才执行授权实验：

```sh
node scripts/project.mjs python scenarios/file-management/auto_rsi.py
node scripts/project.mjs python scripts/check-auto-rsi-sdk.py --experiment .local/file-management/<新实验ID>
node scripts/project.mjs python scenarios/file-management/auto_rsi.py --experiment .local/file-management/<新实验ID> --call-model
node scripts/project.mjs python scripts/audit-auto-rsi.py --experiment .local/file-management/<新实验ID>
```

本次是两个确定性文件流程中的有界经验更新控制器。没有修改学习器自身、扩展任意脚本执行权限，也没有证明所有办公流程、真实人类语义质量或完整成本的改善。结果和限制将同步当前交接和实验记录；费用仍为代理估费，实付账单待核。
