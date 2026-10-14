# 论文校对场景当前交接

- 更新时间与交接人：2026-10-14，Codex。
- 目标与本次范围：把旧论文引用 Motif 与旧 PDF 排版程序绑定当前 Web Task，并保留 main 的结构修订程序；共用在线 RSI Runtime，不自动执行写工具。
- 分支 / commit / 工作区：`codex/harless-motif-libraries-20261014`，已整合 main `1ee0bf4`；私有 V100 隔离检出 `/home/jingyij/jjy/.local/integration/harless-motif-20261014`。提交与 PR 状态以 Git 为准；生产进程未切换。
- 已完成：`scenarios/paper_proofreading/` 的 `paper_checks` 增加旧引用取证与 PDF 工具，连同 main 的 `paper_trace_rsi` 共 17 工具。`src/adapters/harless_task_scope.ts` 冻结上传、任务与输出授权；`harless_paper_renderer.py` 校验审阅包；`scripts/compile-paper-composite-runtime.py` 从原引用库和当前上传读取库编译两条只读局部图。PDF 仍为模型显式调用，收据不代表内容审阅。
- 已验证：V100 抓取 17 个实际 MCP Schema；私有 `.local/paper-composite-20261014-v5/runtime/` 编译通过，Schema SHA `9726f5aeb7d3bb8a74670180433008567143350e9dd3736621ae6bdbed95a7e7`。场景矩阵 27 个有效冻结草稿、论文 MCP/上传、PDF 授权及双用户拒绝通过，0 模型；两个实际 bwrap 成员共 10 个五场景任务通过。真实 `deepseek-flash`/reasoning off 的 Execute 引用链 4 请求、1 Verified Skip、0 工具错误，代理估费 $0.002676852；PDF 基线导出 3 请求、1 个 75,162 字节文件、0 工具错误，代理估费 $0.002420208；账单实付未知。详见 [实验记录](../experiments/paper-legacy-reuse-audit-20261014.md)。
- 五场景完整 `web:scenes:check` 另通过五组实际 MCP/上传、Files/PDF 授权预览和双用户拒绝，0 模型请求。
- 回归：`npm run smoke`、`npm run web:controls:check`、论文 `npm run web:scenes:check` 通过。V100 完整 `npm test` 为 861 Python 通过、4 个文献 PDF 用例失败，Node 阶段被入口跳过；单独按项目 Python 环境运行 Node 全量为 450 通过、3 条件跳过。原因集中在文献 PDF 解析/旧句柄，需要单独处理。早先直接运行 Node 时未设置 `SSS_PURE_CODE_PYTHON`，纯代码用例失败属于入口环境问题，按正确环境已通过。
- 配置与数据：公共 Registry 在 `config/harless-scenes.json`，论文工具 Schema/Prompt 在场景目录；私有 `HARLESS_PAPER_RUNTIME_BUNDLE` 指向 v5 五文件包、`HARLESS_PAPER_RENDERER_ROOT` 指向审阅部署。成员 `libraryRoot` 挂在独立 `/app/private-motif-library`，不遮住仓库 `motif-libraries/`。旧原始轨迹、渲染包、凭证及运行结果均留 `.local/`，不进 Git。
- 未完成与阻塞：没有合并后同题同提示 Origin 对照、逐页 PDF 质量/引用真实性人工评审；旧 `read_pinned_citation_records` 仍是模型调用工具，未提升为自动跳过；PDF 写入不能作为 Verified Skip。公网生产未部署此分支。文献 PDF 回归需修复。
- 接手下一步：1）审阅 PR 并验证完整五场景矩阵；2）在生产部署前用最新 commit/完整 Schema 重新确认私有包代码锁、两个真实账号及预算累计；3）用独立真实论文做同条件 Origin/Shadow/Execute 质量和费用对照，逐页核 PDF。
- 权限与预算：真实任务每项 12 请求/$0.03、每次启动 24 请求/$0.06、输出 cap 1000；本次合并后新增 7 请求、代理估费 $0.00509706，账单未知。外部投稿与私人原件写入未授权。
- 回退与风险：关闭 RSI 或撤销私有库环境变量后 Execute 明确拒绝；可回退本 PR 的论文工具与输出授权。回退不删除账号、Session、私有轨迹或累计预算。
