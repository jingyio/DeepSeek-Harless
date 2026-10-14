# 长期资料与组件库

`knowledge_library.PersistentLibrary` 保存每次登记的资料副本、内容版本、受限组件描述和跨任务复用事件。默认目录是 `.local/research-ppt/library/`，任务结束和服务重启都不删除它；不要把它放进临时 job 目录，也不要随清理历史任务清空它。库属于实际缓存/资产管理工程，登记成功不是 RSI 成果。

## 身份与复用边界

- `tenant_id` 由可信后端的当前操作人身份传入。当前 CLI 可使用固定本机操作人 `local-user`；它不代表已上线多用户登录。接前端时不得直接信任模型、浏览器表单或 MCP 参数自行声称的身份，也不得把共享 Linux 账号或此 Python 类称为文件系统隔离。
- Unix 库根收紧为 `0700`、新数据/记录为 `0600`，保护其他操作系统账号直接访问；仍不隔离同一服务账号下的恶意进程。Windows 的权限由 ACL 决定，此模块不能替代 ACL 验收。
- 默认私有。不同租户即使上传完全相同字节，也有不同资源 ID 与缓存访问域。不得因为 hash 命中就把某人的私有论文、讲稿或反馈交给另一人。
- 明确授权后可以公开共享文档或固定组件。要求同时保留 `confirmed=true`、HTTPS 出处、实际许可和用户授权记录定位。公开可获取不等于有权共享；本模块只保存授权依据，调用方还应核实许可。示例见 `persistent-library.example.json`。
- `set_document_sharing(..., visibility='private')` 撤回跨租户共享，所有者仍能读取；`revoke_document` 或 `revoke_component` 停用全部后续访问，原字节和负面证据保留。已经发送给用户的 PPT/副本、已解析的 job 快照不能远程收回；每次新读取须再次验证共享状态。
- 原有 job 的 `pin_source`、来源 hash、页面校验和写入确认保持独立。库访问回执不是写入权限，也不允许旧任务的认证句柄自动沿用到新任务。

## 接入函数与流程

```python
from scenarios.research_ppt.knowledge_library import PersistentLibrary

library = PersistentLibrary()  # 所有任务使用同一持久根；不根据 job_id 创建新库
entry = library.register_document(
    uploaded_path, tenant_id=trusted_identity, job_id=new_job_id,
    expected_sha256=uploaded_sha256, visibility='private',
)
resolved = library.resolve_document(
    entry['resource_id'], tenant_id=trusted_identity, job_id=new_job_id,
    expected_sha256=entry['source_sha256'],
)
# job 输入保存 library_resource_id、可信 library_tenant、固定版本与持久副本 path。
# MCP 仍为本 job 重新授权/pin，再读取该 job 中的 resource_id。
payload = library.parse_document(
    entry['resource_id'], tenant_id=trusted_identity, job_id=new_job_id,
    expected_sha256=entry['source_sha256'], audit=cache_audit.append,
)
```

`register_document` 只接受 1–100 MiB 的 PDF/PPTX，复制时核对原文件及副本 hash，文件变动拒绝准备。PDF 解析不在登记时重复发生，`parse_document` 使用现有 `document_cache.cached_parse_document`；来源、parser/schema/依赖改变仍按原缓存守卫生成不同 key。返回值保持原解析 schema，不额外附加权限字段或科学正确性标记。cache audit 增加 `library_resource_id` 和 `library_event_id`，可统计同一资料跨 job 的实际 miss/hit。

`parse_document` 解析前后复查当前授权与来源版本，撤回发生在解析过程中也不能返回 payload。`use_cache=False` 使用真实解析而不读写解析缓存；长期保留的原字节仍存在，不能将保留副本的命中冒充解析/token降本。`cache_directory` 只提供已核验的缓存定位，不是一张可永久使用的访问许可证；如调用方绕开 `parse_document`，仍须每次重新 `resolve_document` 并核版本。建议场景工具统一走 `parse_document`。

当前已接入 `cli.prepare(..., tenant_id='local-user', persistent_library=True)`，默认登记到固定长期库。新任务同时登记并冻结实际宿主固定组件：`document_parse`、`render_delivery`；有输出授权时另含生成后局部改页入口 `direct_edit`。任务的 `library_component_schema_version=1` 与 `library_components` 共同保存 script ID、资源 ID 和组件版本。登记相同租户/实现时复用同一组件记录，来源与组件的读取授权仍分别核验。`PPTService.current/pin_source/page_geometry` 检查资源授权、版本及持久副本路径，图件目录也使用资源域缓存。`document_cache=False` 的原配置语义保持；`persistent_library=False` 允许显式使用原始活文件版本守卫。新任务默认使用冻结副本：上传临时文件删除/变动不会改旧快照，若希望使用更新的来源，重新准备任务得到新版本。更改持久副本则旧任务拒绝读取。

`CheckpointPPTService` 恢复前及每次工具操作调用上述 current 检查，因此撤回后不能恢复 checkpoint 已解析的文本来绕过权限；版本清单同时绑定 `knowledge_library.py`。这仍是同一可信操作人/服务账号下的受控接口，不是已完成的前端登录授权。

`list_resources(tenant_id=..., kind='document'/'component')` 只列当前可访问资源的摘要，不返回其他用户私有记录、所属账号或证书路径。登记/读取/解析/撤回事件写入 `events/<event_id>.json`，含真实 job ID、资源/版本、UTC 时间、自身完整性摘要；事件不可由正常 API 覆盖。不保存密钥，不在公共报告发布私人标题、路径或原始轨迹。摘要能诊断损坏，不等于对拥有同一操作系统账号的恶意进程提供防篡改保证。

## 组件登记与执行

请求 schema 见 `component-descriptor.schema.json`。可登记：

1. `fixed_script`：仅 `render_delivery`、`direct_edit`、`document_parse`，映射到已存在的固定宿主源文件；每次解析 descriptor 核验当前实现 hash。`render_delivery` 包含渲染器、交付适配器和固定执行策略的源码版本；不对准备入口自身做自指 hash。这仍不是完整依赖/构建产物认证，编译产物一致性由构建/既有宿主另行验证。变更须新任务重新登记，旧组件与旧 job 的绑定拒绝使用，运行中不自动换成新版本。登记器不动态 import、不执行命令、不生成/eval 任意代码；实际入口继续由既有宿主控制。
2. `certified_generated_tool`：私有 `.local` 中的认证路径及 SHA。登记和复用调用已有 `generated_tools.load_certified_tool`，重新核候选、实现、独立训练/留出及来源证据；不允许仅填写 `certified=true` 冒充认证。当前证书依赖私人轨迹，未独立脱敏打包前禁止跨租户公开，不能把别人的轨迹路径当共享组件。
3. `certified_motif`：私有 manifest 路径及 SHA。登记/复用调用既有 `motif_v6.validate_compilation` 重新检查来源、工具/schema、编译输出和证据锁；登记同时冻结 learning-report/evidence-lock 摘要。它只证明独立轨迹编译边界，不代表科学质量、费用晋级或可在任意题面使用。库不执行 Motif，不自动晋级，运行时仍需原有匹配与版本/权限守卫。未独立脱敏打包前禁止跨租户公开。

```python
component = library.register_component(
    {'kind': 'fixed_script', 'script_id': 'render_delivery'},
    tenant_id=trusted_identity, job_id=new_job_id,
)
bound = library.resolve_component(
    component['resource_id'], tenant_id=trusted_identity, job_id=later_job_id,
    expected_sha256=component['version_sha256'],
)
# bound 只是受限 descriptor；不得拿 description/path/code 当命令执行。
```

`validate_job_components(job, library=...)` 核验新任务的冻结组件集合、当前身份、撤回状态和实现版本，返回严格的固定 descriptor，不执行它们；运行前 CLI 和服务来源核验调用此入口。绑定字段缺项、额外脚本、错误资源种类、schema 布尔值或版本变化均拒绝。两个组件字段均不存在的历史 job 显式保持旧流程，返回空描述，不能称该历史任务已使用组件库；任何一个字段存在就不能降级。旧 job 在用户有权编辑整个私有任务文件时的完整身份与防篡改边界仍依赖可信宿主及既有 job/checkpoint 版本守卫，不能把这两个字段称为防恶意文件篡改机制。

库登记不会让模型自动选择高频组件。固定执行路径由 Harness/场景入口控制，组件库只保存并校验当前允许的宿主版本；它不是新 RSI 成果或自动生成脚本。实际组件登记、跨任务解析、拒绝撤回与版本变化需要服务器验证后才能报告通过。资料缓存仍是独立开关；固定脚本记录复用不等于跳过了模型决策或获得 token 节省。从真实反馈自动发现结构、生成候选、独立认证及在后续新任务省费仍属于已有 `feedback_learning`/工具学习闭环，必须单独保存真实证据。永久资料保留也不是自动授权将私人数据投入训练；学习许可与公开许可应分别收集。

## 验证与当前限制

在服务器激活项目环境后执行并保存日志：

```sh
python -m unittest scenarios.research_ppt.tests.test_knowledge_library scenarios.research_ppt.tests.test_service_library -v
```

测试包含实际 PDF 解析及跨 job/restart 缓存复用、默认租户隔离、公开授权/撤回、复制与来源版本、解析中撤回、固定组件版本失效、合成独立轨迹实际离线编译后 Motif 登记/锁失效、伪造证书/任意代码拒绝、写锁拒绝，以及场景读取与 checkpoint 恢复。它们是无模型工程诊断，不代表已获得用户数据的共享/训练许可，不证明科研质量或成本收益。所有测试在服务器执行并留日志，未运行时不能写通过。

写入使用互斥文件锁与原子替换；正常锁竞争最多等待5秒，超时拒绝，不按超时删除他者锁。释放时核本次token，避免清除被替换的他者锁。残留锁只在管理员确认无活动写入者后处理。当前没有配额、备份调度、登录系统、向量检索或自动物理删除。资料越多并不必然省模型费用；实际收益需区分解析耗时、上下文重复读取、组件命中、认证/维护成本和合格任务的端到端费用。
