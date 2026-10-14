# 普通文件读取 Motif 在线接入：共享接口记录

2026-10-13，用户已授权继续实验和记录共享接口变化。改动前的本机代码保存在 `.local/file-management/interface-before-online-20261013/`，其中包含此前聊天的未提交修改；本文件描述本轮增量，不能把整个 Git diff 当作本轮修改。

## 问题和行为

已有认证库包含 `pin_file.source_id → read_file.source_id`。旧闭合读取判断限定 `read_pinned_*` 名称，因此这个实际来源句柄会走 embedding/模型回退。本轮加入显式能力声明，沿用认证依赖、实际结果和任务允许版本，不用文件名或内容关键词选路径。

## 共享变化

| 文件/接口 | 新行为 | 兼容与范围 |
| --- | --- | --- |
| `scripts/export-online-motif-manifest.py::export_manifest` | 新增仅关键字参数 `source_dereferences=()`；CLI 可重复 `--source-dereference <tool>` | 默认输出与旧库一致；只在显式请求时导出新字段 |
| `manifest.contracts[tool].source_dereference` | 可选布尔 `true`，表示固定来源句柄的直接读取 | manifest schema仍为1/2；新摘要必须重算，旧Runtime不会因此闭合新名称，需配套更新 |
| `src/motif_core/source_dereference.ts` | 校验声明和闭合读取名称兼容判断 | TypeScript为源，生成`.mjs`供Node20旧路径使用；不引入Python在线规则 |
| `src/motif_core/online_skill_runtime.mjs` | 调用新声明校验；原`isClosedSourceRead`保留形状限制并接受显式声明 | 旧`read_pinned_*`行为保留；并行上限8、历史屏障、结果复核、模型回退保持 |
| `scripts/build-continuation-policy.mjs` | 生成/检查两个TypeScript桥接文件 | npm test的既有生成检查继续涵盖两者 |

声明的最低条件：只读且离线重放稳定；一个必需`source_id`参数；无默认参数或任务槽；返回`source_id/source_version`；恰好两个工具且唯一同来源参数边直接复制`source_id`；双方显式`source_version`守卫；无代码节点。声明属于执行策略，参数依赖和来源来自已认证轨迹；它不会创造新Motif，也不能授权选择、转换、写入、分支或数组图。

每个候选仍需模型先实际调用pin，收到工具句柄、在当前任务版本清单内，且唯一后继、schema匹配、无屏障；成功实际读取结果与绑定/版本一致才计入`model_request_skipped_verified`。解析不可读是明确读取诊断，不当作内容成功。

第一版48次对照全部结束后发现：适配器的固定12条历史会在13来源pin/read批次中丢失尚未读取的锚点。13文件免费SDK/MCP复现需要5次模拟请求，2个续接batch后仍有模型补读。第二版TS新增`sourceDereferenceHistoryCapacity(task, manifest)`，仅对显式声明的来源读取，按允许版本清单保留最多两条pin/read观察并留少量前置记录，容量12–64；32来源上限保持，批次上限仍8。适配器只调用此TS函数并按容量截断。旧名称路径/未声明能力仍12条，屏障、版本、唯一后继和结果检查不变，没有扩大文件权限或动态接收未知版本。

新增原生interceptor回归：13个模型实际pin观察经过两个batch完成13个互异读取、不调用模型补读，然后正确交回模型，历史保持有界。修改后相同免费SDK/MCP13文件检查为4次模拟请求/2个batch，全部读取由Runtime完成。该容量是工程实现，参数边来自已有认证库；不把容量调整称为新学习。第一版原代码和结果保留在冻结实验，改前适配器/TS另存`.local/file-management/interface-before-history-20261013/`。

第二版只预登记盘点、索引、内容检索×两材料，共6对12次完整任务，以13来源窗口丢失的诊断选择范围；不是按费用正结果筛选。清单/library/认证摘要与第一版相同，执行源码不同，用新实验ID保存。`online-study.py --families inventory index content_search`选择该范围，默认仍全部12流程。

可复用的纯离线`scripts/audit-file-management.py`逐项核对冻结源码副本、pair输入/提示/schema、真实HTTP账本/SDK缓存/费用、Runtime实际读取和最终实验副本；`scripts/collect-file-management-graphs.py`合并普通及介入图，排除Runtime节点的学习来源、保留失败，并按材料/题面规则去重条件支持，重复同题不增加独立证据。它们不参与在线决策，没有新增模型调用或文件管理权限；分析源码另存hash。

本轮源库、`certified_digest`和训练/认证证据保持。原执行manifest `fb127150…98b`新增声明后为`eb01554b…673`；导出时去掉声明并重算摘要必须与旧清单完全相等，证明没有追改认证。

## 场景调度和验收

`experiment.py::run_one`新增可选manifest/task/本地embedding参数，省略时仍为普通baseline。预算继续累计整个文件管理系列，默认单题5美元，系列1000美元。`online-study.py`准备24对48次新任务，默认仅冻结预览，`--call-model`显式启动。输入、提示、schema和顺序在每对相同；轮换先后组；同一生成实验路径从受守卫的pristine副本重置，先保留每次最终文件/账本/事件/失败再重置。原PDF和旧失败均不动。

新版题面只澄清检索`file_ids`为命中集合，以及重命名跨扩展名全局计数；旧验收记录保持。新任务版本2，两组共用。`source_code()`增加共享执行器/导出器/TS桥接摘要，以阻止运行中换代码。新实验保存可重放源码。

## 验证和回退

新增离线测试验证认证摘要不变、非法声明拒绝；Node测试覆盖显式名称、过期版本、额外必需参数、错误关系/默认值/版本字段/任务槽。`check-online.py`通过真实SDK/MCP和本机脚本HTTP Provider检查正常/过期/旧清单路径；免费模拟证据不进入训练，也不作真实效率结论。完整npm test、真实配对结果和反例见对应实验记录。

关闭执行manifest选项即可回到普通Harness；无需回滚场景文件操作。新生成声明不会自动用于Web或旧场景。仅本机macOS验证；新克隆需要自己的认证库，不分发私有数据和原始日志。本轮未提交、推送或创建PR。
