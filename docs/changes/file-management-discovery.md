# 普通文件管理探索接口与提交说明

## 授权和目的

用户于2026-10-13将场景改为普通文件管理，授权在 testpdf 实验副本中创建五类文件，使用现有 DeepSeek 配置，总预算上限1000美元。先跨流程探索、统一汇集轨迹学习，记录全部费用、失败和共享接口变化。新要求优先于 AGENTS.md 的旧科研跨应用场景路线。

## 逐项变化

- 新 `scenarios/file-management/`：材料作者、任务准备、MCP、独立后置验收、实验调度和离线学习。
- `read_task/list_files/pin_file/read_file/hash_files/build_index/search_index/compare_snapshot/preview_actions/execute_plan/restore_plan/submit_report` 为场景 MCP 工具，不新增共享 ToolContract 字段。
- 文件身份绑定相对路径和文件 SHA。source_id 绑定任务、当前文件及解析版本，参数只能来自实际工具返回。
- 操作 Action 字段为 op、file_ids、destination、format。工具限制副本权限；计划保存当前快照，执行再次核对；修改记录 before、completed、after。拒绝覆盖和过期计划。恢复不覆盖后续已发生的操作。
- submit_report 返回小收据，完整报告保存在私有文件，并核对输入/产物摘要和原生调用。文件状态通过独立验收判断；模型自报完成不直接成为通过。
- 作者工具使用 Codex bundled 依赖；运行解析 Word/Excel 采用标准库 OOXML，图片使用固定 `Pillow==12.3.0`，该版本加入 requirements.txt。未替换已有依赖。
- 预算在新场景跨实验累计，单任务沿用现有预算代理。不把全局1000美元改为单请求或单任务上限，也不修改代理价格、上游核心、SDK或现有场景。

## 共享接口状态

本阶段没有修改共享 Harness、Runtime、IR、编译器、轨迹协议或预算接口。复用已有读取边编译、认证和 manifest 导出。

下一阶段若认证分支、数组遍历或副作用 Motif，需要版本化图 IR、状态谓词见证、输入输出集合守卫及写操作收据/幂等/恢复契约。当前只有观测图，不通过将写操作标为只读来导出旧 manifest。具体接口要根据跨流程证据另行记录后实施。

## 验证与结论位置

新回归 tests/test_file_management.py 检查路径/身份、冲突拒绝、幂等执行、精确恢复、后续变化拒绝恢复、实际读取后才能建索引。真实结果与费用在 docs/experiments/file-management-discovery-20261013.md；原事件及失败在私有实验目录。尚未提交或推送，不替已有未提交改动作提交决定。

建议提交标题：增加普通文件管理任务集和跨流程轨迹学习入口。

建议正文：增加五类文件实验、十二类任务和普通 Harness 探索；统一保留原始事件、费用、失败、文件状态及参数来源，复用现有编译器独立认证局部读取 Motif。写操作只在任务副本中执行并核验，通用执行图与收益验证另行开展。
