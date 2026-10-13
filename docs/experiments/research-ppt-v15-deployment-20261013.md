# V15 朴素组会稿、双路试用与反馈部署收敛

实验 ID：`research-ppt-v15-deployment-20261013`；设计见[本轮计划](research-ppt-v15-deployment-20261013-plan.md)。本轮面向课题组实际试用，不新增研究算法。用户选择保留接口，未要求新建网页。

## 结果与边界

同一公开 DoRA 论文、同一六页中文题面，普通 DSH 与普通组合优化各独立生成、真实渲染交付。观察请求 18→12、总 token 536,799→307,233、代理估费 0.02201855→0.01778932 美元。但原稿均有来源/表述问题，普通组还调用了一次组合修订；没有独立用户质量评审，**不支持相同合格质量下稳定降本，也不把差额归于 RSI**。

两份原稿保留；明确辅助修订新副本以零新增模型请求交付，非目标页保持核验通过。辅助修订和来源审核不是 Agent 自主成功，其人工、Codex、计算及维护费用未知。

## 1 / 真实任务与公平条件

- 类型：真实 API 新生成；不是历史轨迹回放或模拟 Provider。
- 输入：公开 DoRA，arXiv `2402.09353v6`，23页，原 PDF SHA256 `f048986e4d0b1c5b0a3f6c3c709ab245a5bcb993aa92704d6170304b413f08a4`；按用户要求先本机下载再上传服务器。
- 任务：六页中文组会稿，覆盖动机、幅度/方向分解、方法、同条件实验和局限，至少一幅完整原图，保留 notes/页码，避免装饰性卡片堆砌。六页仅是本题，不限定产品。
- 模型：`deepseek-flash`、`deepseek-official`、思考/压缩 off；各 $1.50 防失控上限、40步、每请求8000输出，串行 baseline-first。预算不是实付。
- 两组共用相同基础提示、设计 Skill、lab 版式和固定19工具；不同执行策略后缀，独立 job/计划/工具状态/答案。解析缓存关闭。两路真实 MCP schema SHA `16e07d6d778ec3e39dbd0b31bf6ff57a56257242186a1a116ba9cc726c4fc87b`。
- trial ID `trial-20261013T025300Z-a1a42cef`；配置 SHA `abb6e8c99b91d05df4fd24e4153c61d6518f307e59dccc5b2ef2715e2c9b45ee`。
- 私有有效配置位于 `.local/research-ppt/trials/<trial-id>/trial.json` 和 `effective-runtime.json`，绑定源码/构建、OS、依赖、来源/题面/提示、模型/工具/顺序、上限/价格。完整 Provider payload 与工具排序未独立采集，真实账单尚未核对。
- 运行基点：服务器 HEAD `6ced8277d7743bcb260975290665af26d105274a` 加本轮部署源码；不是最终发布 commit。发布树合入 main `b143bccb0167261bd9a7b8c3269710ef726bdf5f`，最终提交号由场景交接和 Git 提供。原运行快照不追改。

## 2 / 产品 workflow 与使用接口

`trial.prepare_trial → cli.prepare/run预览 → 两组真实schema冻结 → run-scenario.py/公共DSH SDK → 可靠TypeScript MCP适配器 → Python文档/交付后端 → 真实LibreOffice/PDF/PNG → 实际交付回执和费用比较 → 人工评审`。

语义仍由模型承担：理解论文、取舍、叙事、图表解释与不明确反馈。工程脚本固定参数/依赖、版本和权限检查、渲染与交付。优化组的 `render_delivery` 合并机械后续操作；手写组合不称新 Motif 或 RSI。普通模型也能完成任务，此处比较的是相同底座、不同执行策略的完整账本。

入口见[双路使用说明](../../scenarios/research_ppt/trial.md)与[场景 README](../../scenarios/research_ppt/README.md)。`npm run ppt` 默认预览，明确 `--call-model` 才付费；保留 Python/JSON 与19工具 MCP 接口，未新增 UI。明确场景选择负责触发和授权；embedding 不承担副作用授权。

lab 调整采用深蓝标题、灰黑正文、朴素白底，移除固定英文分类标签、色条和强调线。保留原生文字、数据表、流程、原图与 notes；少量方法框仍为可编辑流程结构。固定科研设计 Skill 已加载，不等于使用 harness-anything 引擎。公共产品仍是 JSON→PptxGenJS；V12–V14 原生模板服务保持历史隔离试用，不宣称接入此默认入口。

## 3 / 全部真实请求与费用

| 指标 | 普通 DSH | 普通组合优化 | 观察差异 |
| --- | ---: | ---: | ---: |
| 上游模型请求 | 18 | 12 | −33.33% |
| 未命中输入 token | 37,146 | 26,987 | −27.35% |
| 命中输入 token | 493,056 | 273,536 | −44.52% |
| 输出 token | 6,597 | 6,710 | +1.71% |
| 全部 token | 536,799 | 307,233 | −42.77% |
| 代理观察估费（USD） | 0.02201855 | 0.01778932 | −19.21% |
| 端到端执行秒 | 92.503 | 75.822 | −18.03% |
| 工具调用 | 23 | 19 | −4 |
| 失败/不可解析工具结果 | 2 | 1 | 全部保留 |
| verified Motif旁路 | 0 | 0 | 本轮不是RSI对照 |

两路代理估费合计 `$0.03980787`。上游失败请求均0；工具失败与模型恢复已经包含在上述完整请求、token和费用中。精确恢复费用无法从当前公共事件独立拆分，记 `null`；重复读取不直接称重试。账单实付、人工修订分钟、Codex、CPU/维护金额未知，不能把它们按零计算。

普通组真实运行 `c6befd8970344f46b0090f9982c8039d`；优化组 `692c99983fdb4ce4b9d2d572d7680129`。各 `.local/runs/<id>/` 有完整 manifest、events、cost-ledger、metrics 与答案。优化组还读取更多来源页；内容取舍、失败恢复和缓存顺序不同，不能把6次全部请求差额归因于交付组合。普通组调用1次 `revise_delivery`，`strategy_adherence=false`；入口如实阻止发布严格策略对照的同质量结论，而未偷偷删掉费用或重跑挑选有利结果。

## 4 / 质量缺陷、辅助修订与展示

两组原稿都真实导出6页可编辑 PPTX/PDF/PNG；原生数据表和方法流程存在，Figure 2完整三面板、图例和坐标轴保留，原图内部不逐项编辑。AI辅助检查全部12页未发现明显重叠/缺字，但源图内小字较密，大幅留白与审美可用性仍需用户评审；模型没有图像输入，不称自主视觉质检。

发现并保留的反例：

- 普通组p3 notes式(3)(4)漏标PDF p3；p4列范数梯度分离漏标p5；p6 LLaVA解释漏标p7；两组流程文字容易被误读为幅度/方向顺序训练。
- 优化组p3方向差异定义漏明列平均；p5显存/精度说明漏标p5；p6只有跨模型口径限制，对题面要求的局限说明不足。
- 辅助副本显式补来源/均值/联合训练/局限；普通组notes改成可追溯Table 4具体口径，不从Figure 5估读精确rank数值。保留全部原稿与原成绩。
- 首次辅助预览因改变sources未显式更新evidence_notes被安全拒绝，0模型、无交付覆盖。修正显式patch后两路均通过；此失败不隐藏。

明确辅助操作使用现有 `direct_edit`，每组预览1次read、执行4次MCP，新增模型请求0，真实渲染和非目标页XML/notes/media/关系及样式保持核验通过。它是普通确定性修改，不是新RSI；不能把修订后的稿算作原自主结果质量合格。

本机原稿根为 `H:/DeepSeekHarness/.local/research-ppt/research-ppt-v15-deployment-20261013/deliverables-01/{baseline,optimized}/presentation.pptx`；新副本为同实验目录 `assisted-02/assisted-{baseline,optimized}-02/delivery/revised.pptx`，各有PDF、逐页PNG和overview。服务器同名实验根保留运行、patch和收据。原稿22文件、辅助包38文件下载SHA/size一致；辅助包SHA `cd48da6a14a0a2385819094e44f73d87b6b2a0446b24f9af2cef320192ae9ffd`。以上只用于辅助审阅，独立用户评审未完成。

## 5 / 部署后的反馈与受控学习

新增 `feedback_learning.py` 管理显式授权、不可变反馈、独立任务去重、2训练/1留出预览、已有 `motif_v6` 离线编译、候选/active隔离、后续收益准入及回滚。它不是新增工具生成算法，也不是完全自主进化。在线执行仍沿用现有 Runtime，不另造规则引擎。

修复两项实际阻塞：不同论文完整prompt本来不同，不再用完整prompt相等判训练兼容；普通/组合后缀不同，不再要求两组完整prompt相等。完整prompt仍绑定真实文件/manifest，稳定前缀与共同题面由真实字节独立导出，仅允许已知策略差异；旧缺证据记录拒绝认证，不静默迁移。

新增首候选 `--candidate-version` 隔离评测入口，解决先晋级才能测试的循环。active加载和回滚再查最新训练授权、批准配对与质量/费用证据。晋级还必须真实execute、对应manifest摘要、同会话冻结审计、至少1次verified模型旁路；仅贴候选标签或普通组合节省不能晋级。当前部署没有已晋级版本，默认普通工程对照并记录fallback；candidate/active路径仍需已有独立准入程序、schema及版本检查。

用本轮真实账本/原始工具交付回执验证新版反馈取证：两组均成功入库并复算18/12请求及完整费用，`learn=false`、质量pending、独立合格训练0。原旧记录保留；显式将原提示字节的新增前缀字段补录到独立私有v2库，不追改历史。**本轮没有新候选学习、晋级或生产收益证据**。

## 6 / 服务器验证与发布

全部测试、解析、模型、编译、渲染在服务器；日志位于 `test-logs/research-ppt-v15-deployment-20261013/`。本机只编辑、阅读、下载/字节核验和查看服务器PNG。

| 验证 | 结果与日志 |
| --- | --- |
| 合入main后根npm test | 最终146 Python/47 Node通过，`root-test-main-02.log`；新增document_id闭合读取及漂移/schema/barrier回归 |
| 根npm run smoke | 18开发诊断通过，0付费，`root-smoke-main-01.log` |
| 场景build/初版回归 | build通过；83 Node/176 Python通过；不是完整最终源码的一次性总成绩 |
| 最终新增产品回归 | 53通过，`new-product-tests-03.log`，含记账/cli/反馈/试用边界；协议夹具不当作真实云效果 |
| 真实无模型入口 | 新双路schema与预览、无active fallback通过，`entry-check-final-01.log` |
| 真实反馈取证 | 原账本/交付/提示字节复核通过，`real-feedback-v2-01.log` |
| 明确页面修订 | 真实MCP/LibreOffice导出及非目标页保持通过，`assisted-revision-02.log`；首次拒绝保留01日志 |

直接单独Node测试首次没有统一入口配置的Python，受限code-node回退导致旧回归失败，留 `core-frontier-02.log`。随后使用根统一npm入口，完整146/47通过；没有删除旧检查或放宽守卫。不同测试批次不相加为新效果证据。

发布保留main已有Web/API/预算/请求上限，仅场景必要代码、关键安全回归与历轮设计/报告。移出八个一次性历史实验/报告脚本，逐文件备份后核SHA/size；详见[清理记录](../research-ppt-release-cleanup.md)。V1–V14总报告18页已独立交付，并纳入[报告索引](research-ppt-reports/README.md)，不重复算作实验。本轮无PR；实际commit/push状态以[当前交接](../handoffs/research_ppt.md)与Git为准。

## 7 / 下一步最小试用

本轮私有证据已下载恢复到本机实验根 `evidence-final-01/`：575文件/19,833,759字节逐项SHA/size一致，0不一致；archive SHA `384a2255437a95fb671b1a6de98fa05ec47fb719f7884e040dd88341ea43842a`，manifest SHA `59128b98e271df7a8a244f6b1e6e12e0775af8e202020a6da7988ddc2f8ec06c`。包含本轮双路配置/任务/完整账本、成功验收、日志和场景源码快照，排除凭证/安装环境/前置源码备份/重复ZIP；不是全服务器镜像。封存后新增本条核验说明不追改包内文档。

先由同学提交1个真实PDF/PPTX任务，通过固定接口双路运行并记录逐页人评/修订分钟；两个费用相加是试用总支出，单路才是部署候选成本。科学与视觉均合格后才比较费用。反馈积累到独立2训练/1留出再显式离线认证，无active不强行启用。任意外部PPT精细无损编辑、公式原生OMML、任意复杂科学事实自动认证、完全自主长期学习均未达成；默认新入口先按已验证范围使用。
