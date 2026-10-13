# 真实 Web 连接恢复与 API 验收

- 实验 ID：`web-real-recovery-20261009-v1`，2026-10-09，Codex。
- 问题：浏览器 `ERR_CONNECTION_REFUSED`；本机 SSH 隧道退出，服务器原 Web 3086 停止。重新 SSH 时曾观察到 `Exceeded MaxStartups`，不能据此断言旧进程退出的原因。截图认证地址还混入终端提示符，启动器 URL 文件缺少末尾换行已修复。
- 恢复：新 SSH 控制连接保活；3086 Web 以后台方式恢复。旧运行 `f0479c2c28e84577ac1a1508890e41f4` 无任务、无请求、无费用，原数据保留，没有通过重启规避已发生预算。
- 配置：服务器 `/root/autodl-tmp/jjy`，`feature/paper-submission` / `2368235f274329be6227a8393b850633cb943da4` 加未提交公共适配；不是 PR 精确提交副本。新运行 `9ea9d68a37a44627ad3ab1d545678c37`，example、真实 DeepSeek、baseline/execute、reasoning off，每任务与全启动均 0.25 美元，24/256 次，每请求输出上限 1000。CLI/process 的实际端口为 3086；旧 effective-config 顶层 port 仍为默认 3080，不能把该字段当作实际监听值。
- 方法：认证后通过同源任务 API 预览、确认、轮询两项不同题面；无第三方应用写入。使用公开合成笔记 note:alpha/beta，不是论文生产验收。浏览器自动操作被安全策略拒绝，本次没有完成浏览器点击体验验收。
- 结果：登录、任务页和 API 可用。baseline 任务 `269a059eab554a9fbe9b435dda251fd8`、execute 任务 `661b207edc0a4e09831ec2b5345ad798` 均 completed；每项 3 次真实请求、4 次 MCP、0 工具错误，Session 不同。两份答案的 source_id 与 version_sha256 逐项符合原始笔记。execute 明确 `no_certified_library` 回退，verified skips 为 0。
- 用量：baseline prompt 3737（hit 2304 / miss 1433）、output 937，6.462 秒，估费 0.001568124 美元；execute prompt 3719（hit 2816 / miss 903）、output 524，3.579 秒，估费 0.000916596 美元。合计 6 请求、8 工具、prompt 7456、output 1461，代理估费 0.002484720 美元，实际账单未核对；同一启动剩余额度估算约 0.247515 美元，不重置账本。
- 证据：两端私有 `.local/experiments/web-real-recovery-20261009-v1/` 的 configuration.json、verification.json、逐任务 JSON 和答案；服务器本次运行目录保留事件与账本。认证地址只在私有 access-url.txt，不进入文档或 Git。
- 修复验证：启动器语法解析通过，认证文件以换行结尾；当前运行已直接修正该私有文件，不需要为格式修复再次重启。
- 结论：支持真实 Web 后端任务入口、MCP 和无库回退可运行；质量未独立盲评，没有真实 Motif 降本结论。负责人还需在浏览器用干净的当前认证地址登录，查看上述两项任务并完成点击体验验收。
