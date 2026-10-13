# Harless 场景与 RSI 控制验收

- 问题：通过原生命令和选择面板能否切换场景/模式，并保持已确认任务的输入、证据、工具和预算绑定。若选择产生模型请求、修改运行任务、混用工具或新任务重置总预算，则不支持本实现。
- 任务：工程协议诊断与真实模型处理合成公开资料；没有私人论文/外部应用写入。example 与 portfolio-v1 两项独立任务，同一启动/总账本、不同 Session；不是质量/成本收益对照。
- 代码：基于远端 main `b143bccb0167261bd9a7b8c3269710ef726bdf5f`，本机分支 `codex/harless-controls`。V100 单独快照目录 `.local/validation/harless-controls-20261013-v1/`，没有覆盖服务器论文分支；私有 source-snapshot.json 和 effective-config 保存基线、改动文件摘要及运行环境。真实验收后另有中文提示、诊断选择器与测试修订，在线 TS 接管规则未再改变。
- 配置：V100 Node22.23.3 / Python3.10.21、DSH0.1.5-rc.3；deepseek-flash、reasoning_effort=off、Shadow、压缩关闭、输出1000。每任务0.03美元/24次，全启动0.06美元/32次。真实未配置 embedding，portfolio-v1 明确 no_embedding_service 回退；没有用固定向量证明语义命中。
- 私有记录：真实 run `87e58d3937a743a1891ad3491d634833`；控制结果 `.local/harless-controls/87e58d3937a743a1891ad3491d634833.json`，逐任务 effective-config、事件和 ledger 在该 run 目录。本机已同步 `.local/validation/controls-real.json`；原始请求/答案不进 Git。

| 任务 | 状态 | 真实请求 | 工具/错误 | 缓存命中/未命中输入 | 输出 token | 代理估费（美元） | 秒 |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| example | completed | 3 | 4 / 0 | 2176 / 1543 | 736 | 0.001359156 | 6.321 |
| portfolio-v1 | completed | 12 | 16 / 0 | 41600 / 4854 | 2224 | 0.004374600 | 20.713 |

合计15请求、20工具、0工具错误、估费0.005733756；账单实付未知。候选和验证后跳过均0，没有节省证据。答案质量未盲评，不把 completed 当作科研结论合格。控制操作本身0请求，预览后改场景/Off不改变旧确认，新 Session 正确继承下一任务选择。

- 免费诊断：原生 Remote `commands/execute` 的裸命令、list/status、模式/开关、非法参数、公开 preset 重组和后续实际 schema 通过。三模式的原有任务协议回归保留；无库 Execute 改为显式拒绝，Shadow 无库回退另测。免费三场景Shadow完成（example/portfolio-v1/portfolio-v2为5/14/17模拟请求）；既有portfolio-v1三模式14/14/7模拟请求及5次verified skip 只证明机制，不能当作真实收益。本机最终 `npm test` 151 Python/51 Node，`smoke`18题/83对象；服务器对应结果在当前交接。
- 失败及修复：初次启动器插入配置快照时产生缩进错误，编译诊断后修复；跨场景新 Agent 创建时误先施加默认场景工具限制，原生接口报 unknown tools，改为公开 create 完成后按所选 preset 绑定，重验通过。旧无库 Execute 回归预期与新明确拒绝规则冲突，保留拒绝及 Shadow 回退两类检查。一次浏览器验收 SSH 转发断开导致 Failed to fetch；服务器仍在，专用保活隧道恢复，不能把它当作模型或场景失败。
- 浏览器：已实际验证场景菜单、RSI Off→Baseline、On恢复Execute、Execute禁用条件和“使用此配置新建任务”；原生输入框识别 `/harless`。原生命令弹面板的最终点击尚未验收：预览重启后需要新登录，自动审批禁止打印token，已只同步私有登录文件并尝试内置浏览器安全登录（排队）；当前Chrome刷新返回ERR_BLOCKED_BY_CLIENT，没有绕过浏览器屏蔽。浏览器预览为显式免费模拟，不替代上述真实 API 记录。
- 结论：在已测环境支持命令/面板、每会话场景选择与逐任务冻结；不支持泛化认证库、自动持续学习发布、多用户文件隔离或效益结论。下一步先让场景负责人登记真实 MCP 和工具契约，再独立认证适用库；PPT 尚无 MCP。

- PR发布后的CI修订：`https://github.com/jingyio/DeepSeek-Harless/pull/4` 已创建、未合并。首次push/PR检查的Linux通过；Windows检查在 `test_harless_scenarios.py` 将POSIX `0600`权限位用于Windows上失败（150通过/1失败；push run38379055023）。Windows chmod/stat不能证明ACL隔离，现仅在POSIX保留原权限位断言，其余场景登记、preset和认证输入检查继续在两平台运行；没有删去Linux权限检查，也不宣称Windows Web/ACL已经验收。后续CI结果以PR当前提交为准。
