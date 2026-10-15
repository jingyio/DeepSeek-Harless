# 论文校对场景当前交接

- 更新时间与交接人：2026-10-15，Codex。
- 目标与本次范围：把旧论文引用 Motif 与旧 PDF 排版程序绑定当前 Web Task，并保留 main 的结构修订程序；共用在线 RSI Runtime，不自动执行写工具。
- 分支 / commit / 工作区：`codex/harless-motif-libraries-20261014`，已整合 main `67e8445`；[PR #19](https://github.com/jingyio/DeepSeek-Harless/pull/19) 待审。私有 V100 隔离检出 `/home/jingyij/jjy/.local/integration/harless-motif-20261014`；生产进程未切换。
- 已完成：`scenarios/paper_proofreading/` 的 `paper_checks` 增加旧引用取证与 PDF 工具，连同 main 的 `paper_trace_rsi` 共 17 工具。`src/adapters/harless_task_scope.ts` 冻结上传、任务与输出授权；`harless_paper_renderer.py` 校验审阅包；`scripts/compile-paper-composite-runtime.py` 从原引用库和当前上传读取库编译两条只读局部图。PDF 仍为模型显式调用，收据不代表内容审阅。
- 已验证：V100 抓取 17 个实际 MCP Schema；私有 `.local/paper-composite-20261014-v5/runtime/` 编译通过，Schema SHA `9726f5aeb7d3bb8a74670180433008567143350e9dd3736621ae6bdbed95a7e7`。场景矩阵 27 个有效冻结草稿、论文 MCP/上传、PDF 授权及双用户拒绝通过，0 模型；两个实际 bwrap 成员共 10 个五场景任务通过。真实 `deepseek-flash`/reasoning off 的 Execute 引用链 4 请求、1 Verified Skip、0 工具错误，代理估费 $0.002676852；PDF 基线导出 3 请求、1 个 75,162 字节文件、0 工具错误，代理估费 $0.002420208；账单实付未知。详见 [实验记录](../experiments/paper-legacy-reuse-audit-20261014.md)。
- 五场景完整 `web:scenes:check` 另通过五组实际 MCP/上传、Files/PDF 授权预览和双用户拒绝，0 模型请求。
- 最新 main 合并后 v6 论文免费矩阵再通过 27 个有效冻结预览和双用户拒绝，两个实际 bwrap 成员共 10 个五场景任务也通过；定向论文/比较 Node 39/39、论文/数据 Python 39/39 通过。v6 引用 Execute 再完成 4 请求/1 Verified Skip/0 工具错误，代理估费 $0.002019408；PDF 真实导出为 v5 实测，不能写成 v6 实测。
- 2026-10-15 全任务复测：论文上传上限从 8 扩为 16，其他场景不变，v7 包按新代码锁重新编译。15 份旧论文材料通过任务准入；原样平铺材料因 `sections/...` 路径无法由现有上传协议保存，源码与引用工具拒绝。隔离副本仅改写 9 处 `\input` 路径后，15 文件清单、源码/引文检查、当前报告读取和获准 PDF 导出均无模型通过；PDF 151,255 字节、输入哈希未变，内容/视觉质量未评审。真实全任务 Origin 三次与相同工具集短 Origin 一次均在首请求收到 DeepSeek HTTP 503，合计 4 请求、$0.0295977 保守预估（实际 usage/账单未知），Shadow/Execute 未完成；不能报告新库净收益。见 [全任务实验记录](../experiments/paper-composite-full-20261015-v1.md)。
- 回归：`npm run smoke`、`npm run web:controls:check`、论文 `npm run web:scenes:check` 通过。V100 完整 `npm test` 为 861 Python 通过、4 个文献 PDF 用例失败，Node 阶段被入口跳过；单独按项目 Python 环境运行 Node 全量为 450 通过、3 条件跳过。原因集中在文献 PDF 解析/旧句柄，需要单独处理。早先直接运行 Node 时未设置 `SSS_PURE_CODE_PYTHON`，纯代码用例失败属于入口环境问题，按正确环境已通过。
- 配置与数据：公共 Registry 在 `config/harless-scenes.json`，论文工具 Schema/Prompt 在场景目录；本分支最新私有 `HARLESS_PAPER_RUNTIME_BUNDLE` 指向 `.local/paper-composite-20261015-v7/runtime/` 五文件包、`HARLESS_PAPER_RENDERER_ROOT` 指向审阅部署。成员 `libraryRoot` 挂在独立 `/app/private-motif-library`，不遮住仓库 `motif-libraries/`。旧原始轨迹、渲染包、凭证及运行结果均留 `.local/`，不进 Git。
- 未完成与阻塞：DeepSeek HTTP 503 阻断新库同题同提示三模式真实对照；旧完整 LaTeX 包的相对目录不能原样上传，需安全路径协议。逐页 PDF 质量/引用真实性人工评审未做；旧 `read_pinned_citation_records` 仍是模型调用工具，PDF 写入不能作为 Verified Skip。公网生产未部署此分支。文献 PDF 回归需修复。
- 接手下一步：1）审阅 PR 并验证完整五场景矩阵；2）在生产部署前用最新 commit/完整 Schema 重新确认私有包代码锁、两个真实账号及预算累计；3）用独立真实论文做同条件 Origin/Shadow/Execute 质量和费用对照，逐页核 PDF。
- 权限与预算：早期真实诊断每项 12 请求/$0.03、每次启动 24 请求/$0.06；main `1ee0bf4` 合并后有 7 请求/$0.00509706，更新到 `67e8445` 的 v6 再增 4 请求/$0.002019408。v7 全任务实验使用独立隔离上限每项 240 请求/$1、整轮 720 请求/$3，4 次 HTTP 503 请求合计额外 $0.0295977 保守预估。上述可见记录累计 15 请求/$0.036714168 代理估费，未知实际 usage/账单；失败与重试不删账。公共 Web 默认额度不变，外部投稿与私人原件写入未授权。
- 回退与风险：关闭 RSI 或撤销私有库环境变量后 Execute 明确拒绝；可回退本 PR 的论文工具与输出授权。回退不删除账号、Session、私有轨迹或累计预算。
