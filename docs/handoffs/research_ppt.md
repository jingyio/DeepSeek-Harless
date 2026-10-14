# 科研 PPT 当前交接

## 2026-10-14 自动结构学习与 main 同步

- 分支：`feature/research-ppt-agent` 从 `7375185` 快进到 `origin/main@67e8445` 后恢复本轮改动；本次改动尚未提交或推送。main 的统一成员场景和配对比较保持原入口；另以 `--ppt-native` 显式启用单用户科研 PPT 的 V17 双路交付与反馈学习。其他未合并分支 `feature/rsi-research-agent` 和邮件日历演示与本次 PPT 代码无直接依赖。
- 已完成：主聊天原稿评价绑定 Session、trial、PPTX SHA，三项质量、人工时间与学习许可写入私有反馈库。授权后后台无模型检查三个独立任务，认证只读参数边；后续两个合格新任务验证实际旁路、请求和代理费用后才自动晋级。active 或有界候选仅在新 PPT 任务中使用，不在每次调用模型生成工具。
- 入口：在已安装 PPT 场景依赖、真实 DeepSeek 私有配置的单用户服务器执行 `npm run web:real -- --scenario ppt --ppt-native --ppt-run-budget-usd 3`。未加开关时走 main 的统一场景路径；成员预算 broker 明确拒绝此专用入口。`/ppt` 保留备用，原生聊天只返回优化稿和评价表，普通组账本后台保存。
- 已验证：最新 main 合并后的服务器隔离副本根仓库 Python 668 通过/193 跳过、Node 449 通过/3 跳过；PPT Python 312 通过/1 跳过、Node 120 通过；`npm run smoke` 通过且 0 付费请求，日志在隔离副本 `.local/test-logs/*-2f4c8d2.log`。单用户 `--ppt-native` 在隔离副本以无效占位密钥完成无模型启动，鉴权接口返回预期 401；尚未做合并后带真实密钥的主聊天路由验收。Motif 预检回退现在重新冻结普通模式参数，定向 26 项测试通过。旧基点的真实 15 页生成、下载与第 4 页同稿修改记录见 `docs/experiments/research-ppt-frontend-rsi-20261014.md`；该任务优化组总费用比普通组高 6.2%，没有新增 verified skip 或人工质量评价，不能宣称新 RSI 降本。
- 限制：成员统一路径目前只使用已认证 PPT 读链，不采集本专用反馈或自动晋级；单用户学习库不是跨成员共享产品服务。首版 active 有效时不训练下一代候选。原生聊天修订不加载生成 Motif；科学质量和完整重启后的聊天映射未验收。原始日志、私人输入与凭证均留 `.local/`。
- 接手：先以真实密钥做一次最新 main 的单用户主聊天路由验收；再用三个独立用户授权原稿评价与两个新任务测候选真实旁路及成本。部署前确认私有预算、字体、LibreOffice 和 Node 兼容预加载，不能迁移或清空旧用户状态。当前有效 active 时不继续发现下一代候选，尚非无限自进化。

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
