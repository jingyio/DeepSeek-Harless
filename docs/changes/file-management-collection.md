# 集合读取图：共享接口实施记录

2026-10-13，用户授权按新计划实施，沿用文件管理系列1000美元上限、实验副本和完整失败/费用记录。当前实施目标是模型选定集合后的读取图；写操作和语义分支后续认证，不扩大原文件权限。

现有inventory/entry控制器有批量派发/结果复核，但只在任务入口运行并绑定paper_id/PDF。新图复用原Harness插件生命周期、syntheticToolStreamBatch（最多8）、摘要/工具观察、SDK/场景/预算入口；独立`sss-collection-read-v1`协议避免放宽旧只读manifest/旧入口认证。

## 场景新增接口

旧FileScene和12工具不改，新CollectionScene继承它并提供同一14工具集合供两组使用：

- `select_files(file_ids)`：模型实际声明0–32个不重复当前ID，返回collection_id、成员files（含file_id/path/sha256/source_version）、input/snapshot/execution摘要和collection_sha256。只建立会话读取范围，不代选、不分类、不读正文。
- `collect_reads(collection_id, source_ids)`：仅接受该集合全部实际已读且版本一致的句柄；拒绝缺失、重复、集合外或陈旧来源；返回完整覆盖、每项状态/观察摘要。不可读/metadata-only明确保留，semantic_judgment_certified=false。

两工具的私有selection/summary文件是执行审计记录，与read_file的私有读取记录同类；没有用户文件修改或内容索引构建。build_index仍为效果操作，不纳入只读图。工具收据仅证明覆盖/版本，不认证文件选择或语义结论。

## 图协议和守卫

源为实际模型调用select_files得到的集合；foreach内pin_file.file_id绑定实际成员、read_file.source_id绑定对应pin输出，最后gather完整实际read输出source_ids和源collection_id。节点/参数关系须由不同大小、不同任务普通原生轨迹见证，独立认证后才导出；没有认证不得执行。算法容量/工具的能力描述属于工程实现，不能称学得程序。

输入/当前快照、源码解析执行版本、成员身份/版本、四工具schema、实际prompt/session/user envelope均核验；模型仍决定集合。未知工具插入、错误、范围/版本变化、用户续问触发交接。完整实际结果后才记录verified batch，实际HTTP/费用另计。只接管当前Session第一个有效集合；完成后交回模型建立索引、判断、报告，后续集合仍普通Harness。

CLI/环境/TypeScript实现、编译证据、兼容测试及最终结果记录如下。本机改前脚本/适配器保存在`.local/file-management/interface-before-collection-20261013/`；现有未提交工作保持，不用整份Git diff冒充本轮增量。

## 已实现的共享接缝

- 新`src/motif_core/offline/collection_compiler.py`：检查真实model assistant usage/调用/唯一结果、源数组时序、每个成员pin/read实际参数与同来源版本、完整gather及无其他操作插入；至少两独立且不同大小训练、另一任务认证。独立格式不放宽旧trace/entry/read-only manifest约束。
- 新`src/motif_core/collection_read_policy.ts`：只解释认证的foreach(pin,read)+gather形状；每块最多8，最多32成员；实际工具结果逐项核验，完整batch才记`collection_model_request_bypassed_verified`，完成后交回模型。空显式集合只gather空覆盖，未读取内容不虚构。
- `dsh_entry_motif.ts`复用已存在插件装载/Agent钩子/摘要/user envelope检查，新增`createCollectionGate`在模型选择后接管；旧entry只入口限制和terminal行为保持。环境`SSS_COLLECTION_MOTIF_POLICY/TASK`与旧entry/terminal互斥。
- `scripts/run-scenario.py`新增配对`--collection-policy/--collection-task`：仅native baseline配置，私有常规文件、允许工具、实际session/prompt绑定、权威Node校验，独立记录policy digest和collection执行模式/verified批次；预算代理不变，普通组清空该环境，拒与legacy/PTC/entry/terminal混合。
- `experiment.run_one`新增可选server_path/verify_result/collection_policy/collection_task，默认仍旧12工具/旧验收；新字段记录实际策略/任务hash。`common.source_code`增加新共享源码哈希，实验冻结源码并逐attempt保留。
- npm test增加11项Node回归，Python增加9项原生本机观察/来源/完整性/过期/空集合回归。当前503Python/111Node通过，3Docker跳过；14工具真实MCP预检通过，18题原smoke继续验证。

不引入依赖、不改上游Harness、旧文献场景或旧库。当前新TS插件路径需Node22.18+，默认SDK/Web不启用。复现时CLI默认仅预览，新cloner需要自己的普通轨迹/认证库，私有策略不分发。

## 实际验证与学习边界

首轮真实训练6任务，集合数7/2/12/4/18/3，盘点与属性检索共同参数关系；4独立认证见证，并用未训练的增量流程认证。受限foreach/gather语法、四角色与字段接口由工程限定，编译器验证这些图的实际成员传递、同迭代句柄、完整覆盖和独立变大小证据；目前不是任意控制流结构的自动发现。没有把工具实现/容量或模拟Provider当训练成果。

认证策略通过实际SDK/MCP20文件：4模拟请求/7已核验批次/20读取；过期快照7请求/0续接完整回退，0真实API。12真实配对两组全部验收通过，HTTP54→39，峰值估费−15.58%；其中14文件内容检索估费+1.15%。完整证据/限制见实验记录。相同14工具下比较，不与旧12工具的结果直接拼成增益；尚未比较普通批量工具/脚本或原标量Motif，也未人工盲评/实付核账。

准备器日程交替问题在0评测时发现，以独立冻结的evaluation-schedule/evaluation-driver修订后执行，原源码/训练/库不动。新`scripts/run-file-collection-eval.py/check-file-collection.py/audit-file-collection.py`仅调度/免费协议检查/离线原事件与账本审计，不加入Runtime规则；辅助脚本摘要单独归档。原准备器问题保持在旧源码，后续新版本修正不追改旧结果。
