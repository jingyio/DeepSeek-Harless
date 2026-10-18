# 科研 PPT 当前交接

## 2026-10-18：ppt-master 默认接入、真实结构训练及网页对照

- 分支 `codex/ppt-master-motif`，基线 `7d74e9e`。`/ppt` 改用完整官方 ppt-master 6.6.0：固定 13,016 文件摘要、只读挂载、新 MCP 入口和模型选定来源的 pin/read；旧制作工具与 host_delivery 不再用于默认 PPT。全部幻灯片由 GeneLoop 制作，测试者未修稿。
- 新 `motif-libraries/ppt-master-v1` 来自 Attention/DoRA 两训练与 LoftQ 独立留出，经原 witnessed-edge 编译器生成一个首页读取衔接；真实 AdaLoRA 网页对照命中 1 次 verified skip。普通批量读取/会话私有临时目录/渲染环境优化不算 Motif 学习。Paper v7 仅用原证据重新编译共享代码兼容锁，0 新模型请求，旧库保留。
- 两路完成六页 PPTX/PDF/PNG、备注及可编辑对象；网页上传/双路发送/预览/下载 SHA/刷新保留通过。Baseline 74 请求/$0.68057381/546.154s；Motif 86/$0.73033102/617.852s。Motif 费用高 7.31%，整体成本收益未成立，且两版都有公式/表格/来源缺陷，`quality_cost_promoted=false`。
- Linux全量 Python 1046通过2跳过、Node817通过3跳过，smoke/motif:check通过；Windows定向28通过1跳过，全量受符号链接/环境限制不能称通过。完整失败、费用、配置和质量证据见[实验记录](../experiments/ppt-master-motif-20261018.md)。含被拒绝候选，共713请求，代理估费$5.74779583，账单/人工/CPU未计价，原累计账本未清零。
- 私有原稿、下载核验、评测报告位于 `.local/deliverables/ppt-master-motif-20261018/`；服务器隔离实验的 `evaluation/private-evidence/` 保存原事件和有效配置。公开只存匿名摘要与认证。权限沿用真实API不限请求/费用/额外输出的测试授权。
- 未完成：独立人类盲评、重复同质成本验证。接手优先处理普通流程的事实与渲染恢复，不将新库描述成全流程或科学判断学习。回退必须把旧代码、旧场景注册表、旧证书配套恢复；旧技能/库未删除。
- 合并与正式切换状态将在完成发布后追加；当前这段不声称已上线。


## 2026-10-16 网页组合交付、局部恢复与新读取库

- 当前分支 `codex/ppt-workflow-learning` 已保留 main 的统计来源检查/输入标签修复。原 CLI 完整 `research-design` Skill 自动追加；网页两侧默认 `host_delivery`，渲染→检查→验证→交付由普通脚本组合，失败保存私有草稿并让原模型只修指定页。最新句柄反馈、同任务预算、取消/来源/权限/schema/实现锁保持，CLI 旧次数诊断保留。
- 新库 `motif-libraries/ppt-web-v2-r4/` 来自真实独立 RAG/QLoRA 训练与 DoRA 留出，现有编译器产出两条只读 pin/read 边，30 页数×21 完整实际 schema；不是手写 DAG、不是全稿设计或修复写入的学习。原库图和证书未改。科研稿有错误，显式未通过质量费用晋级。
- [实验及 workflow](../experiments/ppt-web-workflow-learning-20261016-v1.md) 和同目录 results.json 保留全部负例、缓存命中/未命中、输出、费用、耗时与文件质量。学习共 177 请求/$0.232263144（含失败），离线编译 0 模型；完整本轮 397 请求/$0.477209820，均代理估费，实付未知。
- 短说明三组实际交付，B0/B1/B2 请求 15/8/6；普通脚本和 Motif 收益分开。长论文六条件只有两份交付且有科研错误，不能据此宣称同质省费。原生网页 10 下载逐个 SHA 校验/刷新完成通过，Motif 两次实际 skip；其费用比 Baseline 略高，反例保留。
- 根 Python 795、Node 734、PPT 121 项通过；新增真实库锁 9 项及 smoke/motif:check 通过，最终 CI/发布见 PR 回执。私有 `.local/ppt-workflow-20261016/` 保存题面/原 PDF/真实轨迹/检查图，受保护数据不清理，预算沿用每侧 $0.115/每对 $0.23，累计与额外输出限制 null。
- 未完成：独立人类盲评、公式/图注/引用与叙事修订、人工分钟/账单核对、重复同质成本验证。本次没有新增运行期前端流式画面验收。下一步优先处理这些质量错误，不增加学得语义/全流程降本的主张。

## 2026-10-15 辅助附件准入的运行兼容复核

本次独立审阅以 `2a03e22` 为基线，检查共享 `harless_task_scope.ts` 与 `dsh_web_tasks.ts` 的 PPT 输入路径。附件入口接收并保存 Word、需求文本等辅助文件，但 `job.json.inputs` 与 `bindUploadedPptTask` 使用相同的 PDF/PPTX 子集；混合上传保留原上传顺序对应的 `document_id`，不重新编号。只有辅助文件时保持 `source_pending`、空 PPT job 和 `allow_output: false`，不创建已认证读取绑定。PPT 工具不会因此把辅助附件当作可 pin/read 的来源。

原上传 receipt 归属、字节数、文件 SHA、任务 job 身份、符号链接/硬链接/真实路径检查不变；所有附件仍进入批准快照和 `scopeDigest`。新增正文提取只读已批准副本，校验来源 SHA，发送前再核验完整 scope。现有 `pin_source`/`read_source` 参数契约、完整工具 schema、执行器和原训练产物未改。提取文本可影响模型的内容判断，不构成原 Motif 新能力或质量/费用认证。

已完成零模型诊断：从基线源码与当前源码分别绑定空来源、单 PDF、单 PPTX 和大小写混合 PDF/PPTX 四组，返回行、保存字节、job、批准快照及 scope 摘要逐项一致；混合辅助附件只将 PDF/PPTX 版本交给旧绑定，来源篡改、job 不匹配、无归属 receipt 和字节数变化仍拒绝，辅助文件改动使 scope 失效。`node --test tests/test_harless_report_inputs.mjs` 四项、`python -m pytest -q tests/test_harless_rsi_bundle.py` 六项通过；后者允许本机尚未构建的可选 `dist/` 文件缺失，不代表完整部署锁已验证。此处未运行真实模型或实际 MCP 初始化，不能把这些诊断称为实际工具/模型验收。

仅更新运行兼容记录中的 scope 源码锁（`a7b2c4dafba7d9babb7effc17f32961df4dac62aba0a29f28842483cab49ab3d`）及 `entry.json` 对该记录的摘要；原 certificate、library、manifest 与 schema 文件不改。部署前仍须核验最终源码/构建产物的全部 65 锁，实际 MCP 在 1/6/8/10/12 页的完整允许 schema，与混合附件/仅辅助附件的上传、当前来源绑定和既有读取守卫；由根任务统一执行并追加实际结果。更改 scope 后须重新审阅摘要，不沿用本次锁。

## 2026-10-15 输入限制取消后的运行兼容复核

共享 `harless_task_scope.ts` 仅取消 literature 分支的 4000 字符限制，导致 PPT 部署兼容锁失效；PPT 任务绑定、来源权限、SHA 与已学习 pin/read 读取路径均未改。此次只更新 `runtime-bindings.json` 的该文件锁与明确复核说明，并同步 `entry.json` 摘要；原训练证书、库、manifest 和 schema 文件逐字节保留，不构成重新训练或质量/成本晋级。

服务器私有诊断树已验证完整 65 个代码锁、20 项库/场景/编译守卫测试；实际 MCP initialize/list 在 1/6/8/10/12 页均返回 21 个工具，按既有 Web 允许列表选取的完整 19 工具 schema 与五个登记变体相等，job 字节未改变。模型调用与工具调用均为 0；生产切换由根任务统一执行。新增源码锁回归可在未构建 PPT 的根测试中发现共享源码漂移，存在构建产物时再核对完整运行包。

## 2026-10-14 后续分支集成

`feature/research-ppt-agent@7375185` 的 V16/V17 场景代码、反馈、局部恢复与持久库实验已纳入独立集成分支；历史真实实验仍按原记录解释。双路主聊天代码位于场景内，但未接入默认 `/harless`：其现有契约只支持本地操作人，且不继承 Mode/RSI，不能覆盖 PR #13 的统一 Runtime 与成员路径。匿名实验 Markdown 已复制；历轮 PDF 与私有产物不入 Git。

本机 PPT Node 构建/118测试通过；Python 279通过、2跳过，10个真实渲染断言因本机 LibreOffice PDF CJK 字形缺失失败。相同集成树在 V100 固定 Noto/LibreOffice 环境通过291项 Python、118项 Node；原字形守卫未放松。场景代码和 Prompt 改动使先前私有 PPT Runtime 包的代码锁过期；未重新认证前 Execute 应拒绝，不能靠重写旧摘要放行。本轮模型请求0。

## 2026-10-14 Web/成员部署（当前补记）

- Codex在 `codex/harless-launch-readiness-20261014` 完成Web库绑定与成员依赖挂载；最终功能验证 `396e2cf`，[PR #13](https://github.com/jingyio/DeepSeek-Harless/pull/13) 已推送/未合并，未切换公网、未修改原PPT研究数据/论文协作者工作区。
- 已取回的独立正常轨迹2训练/1留出经原编译器与实际完整19Schema认证，`deployment-v3/runtime`仅五个在线文件，只读闭合pin/read；逐任务用批准上传SHA绑定，不继承历史source_id。认证不是质量/费用晋级。旧证据保留，部署代码锁更新生成新包。
- 真实合成只读任务成功2HTTP/1Verified Skip；先前预算失败1HTTP/1局部skip单列。两成员实际bwrap/MCP、各一页中文PPTX/PDF/PNG机械交付通过，0模型，科学质量未评审。CPU转换及task内validation与checkpoint路径兼容修复；跨任务/软链接仍拒绝。
- 最短部署：安装/构建场景依赖，配置私有三个 `HARLESS_PPT_*` 变量及网关 `memberSceneDeployment`，运行 `node scripts/project.mjs python scripts/check-harless-members.py --render-ppt`；库准入与输出依赖失败明确拒绝。用户菜单可选页数/模板/新副本权限，默认只读。
- 结果、失败、环境、累计预算与版本边界见 [上线准备记录](../experiments/harless-launch-readiness-20261014-v1.md)。下一步与Session负责人联合公网验收，再以真实论文生成任务独立人评。原V15研究结论不改，以下为历史交接。

## 2026-10-14 私有库迁移补记

Codex 按用户授权从旧部署取回 12 份 PPT Manifest 及 322 个库/认证依赖文件，同步到 V100 `.local/imports/ppt-library-transfer-20261014/`；本机同名私有目录也保留备份。两端逐项 SHA256 核验通过。4 份完整证据锁匹配旧部署，当前 Runtime 格式检查接受 10/12、拒绝 2/12；当前代码相较旧证据仍有版本变化，尚未认证迁移或绑定 Web Execute。此次模型调用 0，未改变预算、权限或历史证据。详情与接手步骤见 [迁移记录](../experiments/ppt-library-transfer-20261014-v1.md)。以下保留原场景发布交接；原本机 `H:/DeepSeekHarness` 路径属于原负责人环境，不能当作本次 macOS 已存在的文件。

- 更新时间与交接人：2026-10-13，Codex。
- 目标与本次范围：停止扩展研究机制，收敛课题组试用。保留接口，朴素组会稿、双路生成/记账、版本安全修订、显式反馈与受控学习；结果见 `docs/experiments/research-ppt-v15-deployment-20261013.md`，历轮索引见 `docs/experiments/research-ppt-reports/README.md`；20 份 PDF 留在团队私有归档，不进入 main。
- 分支 / commit / 工作区：原场景开发位于 `feature/research-ppt-agent`；不含 PDF 的集成改动从 main `b330bb4` 另建 `codex/research-ppt-clean-pr`，已提交并推送，见 PR #5。原场景工作区与私有数据未覆盖；PR 审查及 CI 完成前不合并。
- 已完成：`trial.py` 两独立job、同模型/来源/schema/19工具、预览/显式付费、全账本/实际交付/待评审；`feedback_learning.py` 私有不可变反馈、去重、2训练/1留出、现有编译器、候选隔离、收益晋级/回滚；`accounting.py/runtime_snapshot.py` 替代旧轮次依赖。`ts/render.ts` lab v15.1及prompt/Skill采用朴素科研表达。TypeScript在线/Python后端，不改上游Harness。
- 最短入口：先按根README及 `scenarios/research_ppt/deploy-ubuntu18.md` 安装/构建并激活实际环境；`npm run ppt -- --input .local/inputs/paper.pdf --slides 6 --template lab --allow-output --collect-feedback` 仅预览；确认后 `npm run ppt -- --trial <实际trial.json> --call-model`。MCP与Python/JSON接口保留，无新UI。`--operation restyle` 受限样式转换；`direct_edit` 限同job、完整plan及明确page/changes，执行携原SHA生成新副本。
- 已验证：均在服务器 `/mnt/sevenT/junjiex/DeepSeekHarness-v9` 激活环境执行，日志 `test-logs/research-ppt-v15-deployment-20261013/`。最终根npm test 146Python/47Node；smoke18诊断/0付费；场景build及初批83Node/176Python；最终新增产品53回归；真实两路stdio schema/无active fallback、真实ledger/交付取证、局部修改真实LibreOffice与非目标XML/notes/media/样式保持。批次不相加；协议夹具不是云效果。单独Node测试缺统一Python环境曾失败，根统一入口复验通过，旧失败保留。
- 实验结论：V15 DoRA六页普通/组合请求18/12、token536799/307233、代理估费0.02201855/0.01778932美元、耗时92.503/75.822秒，双路总0.03980787美元。观察请求−33.33%、token−42.77%、费−19.21%；原稿有来源/均值/流程/局限问题，普通组使用组合修订、未独立人评，不支持同质量稳定降本。verified Motif=0，不称RSI效果。明确辅助修订新副本均0新增模型，不计原自主成功；人工/计算/维护/实付未知。
- 历史结论：V3 E4输出保持时减少请求、V10明确标题修改10/7→0有局部证据，不能推广完整生成。V6新工具/Motif真实使用但总成本仍高；V13/14候选或继承码verified各1，质量/恢复抵消局部收益。V14三组机械成功但科学有错，不支持同合格质量净收益。公开V1–V14总报告18页不构成跨任务持续降本曲线。
- 学习边界：默认learn=false、科学/视觉pending；本轮两路原账本入库至显式v2库，原记录不改，训练0/新候选0。稳定前缀/共同题面从真实prompt字节导出，完整prompt绑定manifest；旧缺字段拒绝认证。`--candidate-version` 隔离评测，`--use-active-learning` 仅继承当前有效晋级版。晋级需两独立新任务人评/全费/人工分钟、真实execute/manifest/冻结审计/verified旁路；active和回滚重查最新批准证据。本轮没有真实新候选晋级或完全自主长期学习结果。
- 配置与数据：公共Schema/锁/工具在 `scenarios/research_ppt/`；来源、credentials、runs、反馈、交付留 `.local/`。变量 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL` 用途公开，值不记录。服务器旧HEAD `6ced8277d7743bcb260975290665af26d105274a` 加部署，真实运行不是最终发布HEAD；原快照保持。思考/压缩off，proxy账本不当实付。
- 交付：原稿本机 `.local/research-ppt/research-ppt-v15-deployment-20261013/deliverables-01/`；辅助稿同根 `assisted-02/assisted-{baseline,optimized}-02/delivery/revised.pptx`，含PDF/PNG/overview。原稿22/辅助38文件SHA/size核验一致。V1–V14 PDF/清单/39PPT路径索引在本机 `.local/research-ppt/reports/`；公开汇总PDF身份见 `summary-manifest.json`。
- 发布清理：保留最新main团队Web/请求上限/预算/API。PPT公共差异仅场景、文档、入口、Windows file-URI及窄闭合pin/read，增加版本/schema/barrier回归。八个历史矩阵/报告脚本逐文件备份核验至本机 `.local/research-ppt/release-archive-20261013/`；开发树/历史数据和关键安全测试保留。见 `docs/research-ppt-release-cleanup.md`。V12–14隔离原生服务/五套素材未作为本次默认后端发布，私人原型不称已接入。
- 未完成与限制：同学独立科学/视觉评审及人工分钟、账单；任意外部PPT无损编辑、完整主张/公式自动正确性、任意中断恢复、完全自主进化；基础插件无Python依赖。Ubuntu18需兼容工具链/字体，SDK runtime-bin缺项仍不能泛称标准pip部署完成；Windows完整真实渲染未验证。
- 接手下一步：1）同学提交1真实任务、双路运行并填review，科学/视觉不合格不发布节省结论；2）按具体页反馈明确patch，记人工分钟且原稿保留；3）独立授权合格轨迹2训练/1留出后离线认证，以两新任务完整质量/费用决定晋级，无active走普通流程，不扩候选矩阵。
- 权限与预算：既有不限DeepSeek实验授权持续，本轮proxy0.03980787美元、实付未知；默认预览，每路1.50美元/40步。新副本、备份及整理中文commit/push已授权，提交前告知，无PR；后续用户数据学习需明确授权，私有日志/凭证不公开。
- 回退与风险：发布前产品基点 `4008d2d`；新风格可选academic或旧renderer。来源/代码/证书改变需新job/认证，不重签旧结果。权限/schema/version拒绝保持；异常写锁先确认无写入者再处理，不称任意SIGKILL自动恢复。科学理解/选材仍需模型/人审，机械通过不是事实/审美合格。
