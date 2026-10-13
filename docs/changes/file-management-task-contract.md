# 重命名与读取范围的显式任务契约

本轮修复普通文件管理任务的机械质量。新任务使用 `sss-file-task-v1` 和独立的 `task_execution_version_sha256`，通过 `scenarios/file-management/task_tools.py` 启动。旧 FileScene、CollectionScene、ReportScene 及旧基准判定保留；历史失败不改成通过。

## 共享接口与版本

- 新 `TaskScene(ReportScene)` 保持14个工具名、顺序和参数结构。`read_task` 增加适用的 `task_contract`、`reading_contract`、`task_execution_version_sha256` 和当前报告 ID 的含义。不同任务不展示其他任务的默认字段。
- 重命名返回 `rename_targets`，分类返回 `classification_targets`。分类表仅给每个原路径的候选完整目标路径，选择路线或保持原位仍由模型根据实际读取决定。
- `preview_actions` 校验编号/转换参数/合法分类路径，并要求转换、分类先完成原输入读取与一个完整集合；空白文本保持原位。拒绝不写文件，提示含完整合法路径。没有文件变化的任务读取汇总后直接提交报告。
- `submit_report` 保留原 `sss-file-report-v3` 字段，追加 `task_contract_version`、`task_execution_version_sha256`、`reading_contract`。成功工具回执不代替程序验收。
- 固定 `scripts/validate-file-delivery.py` 只对显式含 `task_contract` 的新题调用新验收器；无该字段沿用旧路由。任务文件 SHA、目录副本、当前回执、逐轮不可覆盖归档、原预算与最多2轮普通 Harness 修复继续生效。越界读取不能靠重试抹掉。
- 新 [JSON Schema](../schemas/file-task-contract.schema.json) 用于前端结构预校验；相对路径、目录权限与跨字段约束仍由服务端检查。未知版本/字段拒绝。

新增 Python 只用于固定 MCP 工具、实验控制和验收；在线 Harness 调度/修复钩子继续使用现有 TypeScript，没有新增 Agent 循环或修改上游 Harness。

## 验收口径

| 任务 | 必读原文件 | 其他读取与文件结果 |
|---|---|---|
| 重命名 | 无 | 新实验显式设置 `allow_optional_original_reads=true`，允许按实际版本读取副本原文件和已改名结果；全部原路径统一 Unicode 码点排序计数，不能按扩展名重新编号。保留字节和无关文件。 |
| 转换 | `conversions` 的全部原输入，包括空文件和图片元数据 | `allow_output_verification_reads` 控制产物读取；`require_output_verification_reads=true` 时还必须实际读取全部产物。仅声明的产物、匹配成功转换日志、当前版本和实际执行后读取有效；无关原文件禁止读取。 |
| 内容分类 | `source_prefix` 下全部 `.docx/.txt/.md` | 0字节与纯空白也必须有真实 `readable` 观察和完整集合成员记录，保持原位。全部为空/未命中时不产生写操作；目录其他文件不读、不改。 |

必读集合至少有一个包含全部且仅含所需原输入的真实 `collect_reads` 结果。先前部分集合、工具拒绝和读取历史仍保留；不能把漏读和解析失败当成空文件。读取记录与原始成功工具事件、字节/版本、集合摘要和报告逐项绑定。

重命名编号从1开始，最少两位；按最终后缀小写分目录和命名，多重后缀取最后一个；无后缀使用 `no-extension/item_01`。候选编号表与预览守卫是两组共用普通程序，不能归入学得 Motif 收益。

转换文本与 CSV 内容独立重算，JPEG 与源图的标准 RGB→JPEG 结果比对，所有未选原件字节保留。读取每文件最多6000字符，PDF只有前两物理页、图片无OCR；文本转换保存转换器支持范围的完整文本，不能据此声称转换了整个 PDF 或科学理解正确。

## 库兼容边界

新任务继承 `select_files/pin_file/read_file/collect_reads` 的原函数对象与原执行版本；实际 MCP 预检确认这四个工具 schema 一致。原四个依赖源码未改，L2 文件 SHA/digest 原样锁定，不重写旧证书，也不从新留出学习。新操作/交付/验收的执行版本与全部源码另行冻结。

兼容性只涉及这个读取图。效果守卫、分类路线、编号和验收没有因此获得 Motif 认证；若以后修改读取图或其守卫，需要重新认证。恢复后仍停用自动 Motif，后续由同 Session 的普通 Harness 在原限制内处理。

首轮因零必读被误表述为禁止任何读取，以及分类暴露不适用的 `normalized/` 字段而出现失败。第二版明确可选读取，并按任务显示字段、候选路径和无写操作完成方式；使用不同路径/文本重新冻结验证，首轮结果和费用保留。最终24次新留出全部通过，结果见[实验记录](../experiments/file-management-task-quality-20261013.md)。
