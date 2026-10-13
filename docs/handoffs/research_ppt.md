# 科研 PPT 当前交接

- 更新时间与交接人：2026-10-13，Codex。
- 目标与本次范围：停止扩展研究机制，收敛课题组试用。保留接口，朴素组会稿、双路生成/记账、版本安全修订、显式反馈与受控学习；结果见 `docs/experiments/research-ppt-v15-deployment-20261013.md`，历轮索引见 `docs/experiments/research-ppt-reports/README.md`；20 份 PDF 留在团队私有归档，不进入 main。
- 分支 / commit / 工作区：发布树 `C:/Users/Xia/.codex/worktrees/research-ppt-reports-v14/DeepSeekHarness`；基于已推的 `4008d2d1c7794cbdb5882cf6d3222bab1f067b5e` 合入 main `b143bccb0167261bd9a7b8c3269710ef726bdf5f`。本记录随最终中文提交发布至 `feature/research-ppt-agent`，实际提交号/推送状态查 Git 与交付答复，无 PR。本机 `H:/DeepSeekHarness` 团队未提交改动保持，不覆盖其 `.git` 或旧根源码。
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
