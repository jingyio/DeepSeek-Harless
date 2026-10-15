# 统一对话轮次轨迹验收

- 日期：2026-10-16（北京时间）；代码 PR #37，正式运行 `bfc86c1d08d1ed7d213faebf3000d7525bfdb9db`。
- 问题：旧轨迹将单路和双路任务混入同一下拉列表，遗漏普通聊天轮次；旧 native turn location 在连续任务中重复，导致编号和真实消息顺序不符。系统下拉框颜色及字体不符合页面主题。
- 实现：通过公开 trajectory/chat 快照按用户消息 seq 与任务 anchorSeq 合并，分页完整后连续编号。普通/单路一列，双路左右两列，上方每轮独立选择 Baseline/Motif；实际优化事件用颜色及文字同时标注。主题字体、授权图片加载、真实运行事件及分页错误恢复保留；正文独立滚动，composer overlay 使用原生布局约定。

## 验证与证据边界

- 确定性诊断：相关前端 98 项通过，包括八轮混合消息、重复旧 turn location、单路任务、各轮独立选择、搜索不重编号、跨页加载及失败重试、过期会话响应、图片与流事件、影子候选不冒充已验证优化。
- PR 最终四项跨平台 CI 全通过：Linux Python 949 通过/3 跳过，Node 709 通过/3 跳过；Windows Python 756 通过/196 跳过，Node 708 通过/4 跳过。两平台 smoke、Motif 检查通过。
- 真实浏览器只读验收：使用隔离 stage 中此前真实 API 生成的 Chat→Data→PPT 三轮历史。全部轮号/消息均显示，第二轮选 Motif 后第三轮仍为 Baseline，双列事件完整；桌面列宽各 463px、间距 24px，字体与页面相同；390px 下纵排，页面宽度与 scrollWidth 均为 390px。最后代码刷新后轮次导航、三种排列控件、侧别选择及浏览器无错误复核通过。
- 初次浏览器检查发现未带 composer overlay 标记时继承聊天滚动位置，顶部图随内容离屏；补原生标记、overflow 与底部空间后复验修正。没有改上游包或生成类名。
- 本轮不涉及模型行为变化，未新增模型请求；旧真实轨迹只证明展示与交互，不重新声明分析质量或 Motif 成本收益。

## 发布与数据保全

- 正式从 `19e586b6b161defc89f581700a6938b38480655f` 切到本次合并提交；83 个任务空闲后执行。配置零变化、预算进程不重启；6,473 条保护条目在切换期间一致，上线复核 333 不可变文件、131 preset、3 账号与27组评分保留。
- 从实际启动图取得前端资源，确认服务中的 client 与部署源码一致；旧历史、模型目录、PPT 只读初始化和公网登录页正常。复核脚本初次缺少已审阅依赖文件，未执行审计即退出；补传并匹配固定 SHA 后全部通过，没有重新部署或改数据。
- 每任务 $0.23；累计请求次数、累计费用及额外输出上限 null；账本保留 897 请求/代理估费 $0.638632706，实付未知。验收、部署与复核新增模型请求均为 0。
- 临时 stage 40 个任务均终态，3 个临时进程与本机转发、临时标签已关闭，配置及旧日志保留。回退只恢复应用代码，不回滚用户记录、评分或预算账本。

私有证据（不入 Git）：`.local/unified-turn-trajectory.png`、`.local/unified-trace-ci.log`、`.local/postdeploy-unified-trajectory.json`；远端部署区 `unified-trajectory-hotfixes/20261015T161850Z-bfc86c1d08d1-80e58649/receipt.json` 与 `postdeploy-unified-trajectory-acceptance-bfc86c1d08d1-20261015T161946Z-8e86aec9.json`。stage 关闭收据为 `stage-shutdown-unified-trajectory-d2f40e544741460095e2a1594abcffc2.json`。
