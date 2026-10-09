# 主线当前交接

- **更新时间与交接人**：2026-10-09，Codex 根据项目负责人的要求整理；后续主线负责人由课题组确定。
- **目标与本次范围**：提供三位同学可共同使用的 Motif / DeepSeek Harness / 自定义 MCP 底座。本次补齐中文项目约定、配置和实验记录规范、交接模板；没有改变运行代码。
- **分支与版本**：本地 `main`，运行底座提交为 `9388ed0`；本次文档提交见 `git log -1`。归档分支为 `archive`（`810edf4`）与 `archive-pre-cleanup-20261009`（`1d7ec26`）。这些本地提交和分支尚未推送，不能假定同学已经拿到。
- **已完成**：通用场景入口 `scripts/run-scenario.py`、场景配置适配 `src/adapters/scenario.py`、SDK 启动边界 `src/adapters/harness_runtime.py`、工具白名单与在线 Motif 插件；保留 Motif 核心及许可来源、18 项冻结科研夹具。入口见 `README.md`，协议见 `docs/interfaces.md`，合作方式见 `docs/collaboration.md`。
- **已验证**：此前在 macOS 及不含历史 `.local` 数据的临时目录执行 `npm test`，通过 133 项 Python、24 项 Node 测试；`npm run smoke` 通过 18 题、读取 83 个来源对象。另有本机模拟 Provider 的真实 SDK/MCP/预算代理闭环。以上属于离线协议与回归检查。本次纯文档修改检查 diff 和路径一致性，未重复运行模型或整套测试。
- **最近复核（2026-10-09）**：回答项目结构与连通性问题时，在当前本机重新执行 `npm test` 和 `npm run smoke`，仍通过 133 项 Python、24 项 Node 及全部 18 题工具检查；包含真实 Harness 对本机模拟 Provider 的三次请求、两次 MCP 调用。没有付费云调用或新的科研效果结论。当前在线路径为场景配置 → Python SDK → Node Harness → 可选 JS Motif 插件 → MCP；Python controller 为独立结构执行路径。新场景接入 Harness 后，要另行收集轨迹、编译认证 library 并配置任务/embedding 才能启用 Motif。现有 `docs/collaboration.md` 未提交修改属于用户工作，本次保留。
- **后续技术路线（2026-10-09，用户明确）**：Python 负责离线学习、编译和科研实验；新增 Harness 在线逻辑用 TypeScript，逐步迁移现有 JS 插件。生产在线 Runtime 以 TS 为权威，Python controller 用于参考/离线验证；不实施之前讨论的 Python 在线桥接方案。SSS 已通过 npm 安装并启动本地 Harness，已有原生插件，但独立插件分发、共享 Schema/类型及无额外 Python 的已有 library 执行尚未完成。当前纯代码节点和实验预算代理仍依赖 Python。本次仅核对代码和更新文档，没有重构、重跑付费实验或重复全套测试；用户在协作文档和 `dsh_client.py` 中的未提交修改保留。
- **实验结论**：离线检查支持当前工具链和所覆盖的安全守卫可运行；没有本次真实研究交付的盲评或付费同题对照，不能据此宣称 Motif 降本或科研质量提升。清理与验证依据见 `docs/main-cleanup.md`；后续实验按 `AGENTS.md` 记录在 `docs/experiments/`。
- **配置与数据**：公开场景在 `scenarios/`，通用配置在 `config/`，依赖在 `package.json`、`package-lock.json` 和 `requirements.txt`。新入口默认 baseline、预览、`reasoning_effort="off"`，预算上限 0.25 美元、16 步、单请求输出上限 3000 token；实际实验以预览和配置快照为准。密钥使用本机 `DEEPSEEK_API_KEY` 或 Harness 凭证存储；MCP 认证用场景的 `from_env`。私人资料与历史原始记录在各自本机 `.local/`，不随 Git 分发。未在本记录中读取或记录任何密钥值。
- **未完成与限制**：Windows 原生及真实 HTTP MCP 服务尚未联调；Ubuntu/Windows CI 已配置但未远程运行。三个实际场景及负责人尚未在仓库冻结。在线 JS runtime 是 Python 结构执行的子集，不是完整移植；embedding 和具体 MCP 服务的平台适配仍需场景验证。仓库定价表也需在付费实验前核对。
- **接手下一步**：
  1. 主线负责人确认团队共享仓库及同步范围，将需要的本地提交推送；验收是同学能取得相同版本并运行基础检查。
  2. 三位同学各开场景分支，复制 `scenarios/example/`，实现最小只读 MCP 链路；验收包括正常调用、版本/权限拒绝检查及各自场景交接记录。
  3. 选定真实独立研究决定，冻结任务、来源、基线、配置和质量标准；先预览预算，获得对应调用权限后再做付费对照。
- **权限与预算**：当前授权涵盖本地备份、主线整理及文档完善。此前整理和本次文档工作没有付费模型支出；团队后续总预算与剩余额度未知。没有授权本次发送邮件、写外部应用或开始新的付费实验。
- **回退与风险**：文档可按对应提交单独回退；完整历史可从两个归档分支查阅。不要直接把全部 archive 合回 main，也不要删除 `.local/`。通用入口的 `--call-model` 会启用付费调用；有副作用的 MCP 还需服务端权限、预览和确认。
