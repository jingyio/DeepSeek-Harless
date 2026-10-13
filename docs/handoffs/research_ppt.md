# 科研 PPT 当前交接

- 更新时间与交接人：2026-10-13，Codex。
- 目标与本次范围：用户接受V17效果与成本并放行；完成必需前端对接，合入最新main菜单，整理必须代码/维护回归/历轮报告，推feature/research-ppt-agent，不开PR。
- 分支 / commit / 工作区：独立发布树research-ppt-v17-release；081db45已本地提交V17整理与接口，本次最终提交合入main 62ee46b；按已授权推feature/research-ppt-agent，实际远端commit以Git与本次完成回复为准；原H盘及reports-v14脏工作区未覆盖。
- 已完成：V17可靠交付/局部恢复，持久资料组件库；ts/web-tasks.ts复用认证与trial实现流式上传、回执绑定、独立双路job、预算确认、串行后台状态、取消、重启不自动重付费、交付SHA下载和费用展示。main原生/harless菜单PPT选项进入/ppt；其他main模型/菜单逻辑保留。Python web_bridge仅复用prepare_trial，不造模型循环。
- 最短入口：根/场景安装与服务器渲染依赖按README/deploy-ubuntu18.md；配置私有DEEPSEEK_API_KEY；npm run web:real -- --ppt-run-budget-usd 3。打开本次Harness认证地址，在原生/harless菜单选PPT或访问/ppt。
- 参数：默认15页，1–30；1–8 PDF/PPTX，每份100MiB，总256MiB，说明10000字符。双路$3/每路$1.50、60步骤/8000输出，off/off；PPT独立启动额度按确认上限预留，不退回未结算费用，普通任务预算不变。每次任务不生成新工具。ZIP/来源/版本/权限守卫保留。
- 已验证：此前发布准备根151Python/53Node、场景94Node/286Python、真实无模型渲染与恢复通过。新增6项PPT参数回归通过；真实HTTP上传/默认15/确认/鉴权拒绝/重复提交拒绝/成品下载SHA通过。最新main原生菜单回归增加PPT真实跳转断言；最终根153Python/56Node、场景100Node及无模型smoke通过；最新菜单/接口免费验收通过。
- 真实验收：research-ppt-v17-web-integration-20261013，Attention Is All You Need，双路15页均机械/策略通过，34文件鉴权下载核SHA。本机.local/research-ppt/research-ppt-v17-web-integration-20261013/test-logs/web-integration/{baseline,optimized}/presentation.pptx及PDF/PNG。
- 成本：普通16请求/577251token/$0.04936341；优化12/315436/$0.01867534；请求少25%、token少45.4%、代理模型费少62.2%。两路合计$0.06803875；无上游失败/无未结算。固定宿主交付收益，不是本轮新RSI；verifiedskip0，科学/审美待用户评审，人工修改/账单实付未知。
- 实验结论：用户接受的旧V17两稿质量与费用下降为用户评审证据，非独立盲评；新Attention抽查架构页和实验表可读，未冒充完整人评。V16等负面证据及20历史PDF报告保留，docs/experiments/research-ppt-reports/为索引。
- 配置与数据：公共schema/锁/提示在scenarios/research_ppt；私有DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL不展示。长期库保留，解析缓存/候选生成默认关闭。server test-logs与trial/effective-runtime保留源哈希、真实账本；不提交私人论文/成品/原始日志。更新前源码私有归档，旧证据不覆盖。
- 未完成与边界：网页自然语言改页/反馈评审/自动学习、多账号隔离暂缓，MCP/离线review与认证接口仍可用。原生聊天不自动当PPT任务，需显式入口。新main允许普通聊天直接执行，本场景坚持冻结预算确认。不能保证任意PDF规划/渲染必然成功或费用总下降。
- 接手下一步：1）前端同伴沿frontend-integration.md复用上传/preview/submit/status/download；2）用户审阅Attention两份成品并追加review及修改分钟；3）有真实需求再加网页反馈/改页，不扩大候选模型试跑。
- 权限与预算：已明确授权本次真实测试与中文提交/推分支，无PR；本次实际代理模型费$0.06803875，预算上限$3，不是账单实付。
- 回退与风险：分支提交恢复，私有证据/旧源码归档保留；main核心及上游Harness不改。当前单一可信操作人，不能对公网宣称多用户安全；机械交付不认证科学正确。
