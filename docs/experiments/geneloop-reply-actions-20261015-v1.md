# GeneLoop 回复操作栏一致性验收

日期：2026-10-15。开发基线 `86c50f2`，生产基线 `5d2e6a0`。

## 修改范围

`client.js` 的对照操作栏使用浏览器公开 primitives 的原生图标、Tooltip 和定位/外点关闭能力。图标按钮 28px、图标 15px，随原生字体增量缩放；复制后勾选一秒复原、赞踩选中实心，分支仍绑定所选侧的输出摘要。用量和用时格式与 Chat 一致，完成时间来自实际任务记录。点击统计查看该侧的真实分项，缺失信息不伪造。

按公开全对话 timeline 最后一轮判定常显，历史回复桌面 hover/focus 显示；触屏不隐藏，展开统计时保持操作栏显示，评分始终独立。统计在窄栏整组换行；手机宽度采用原生紧凑图标，保留可访问名称。未修改上游 Harness 或后端。

## 检查与浏览器证据

- 无模型组件诊断覆盖最新/历史（包括后续普通 Chat）、未知轮次、原生图标身份、复制迟到回调/一秒复原、未知指标省略、真实计数/时间、弹层和 Escape/外点关闭。最终相关前端测试 93/93 通过（paired、chat presentation、native picker、trajectory、managed workspaces 五个文件）。
- 隔离 stage 复用既有真实 Chat → data → ppt 三轮，旧 data 两侧 reveal=hover/opacity=0，最新 ppt 两侧 reveal=always/opacity=1；鼠标进入历史 Baseline 仅显示该侧，键盘聚焦同样显示。
- 浏览器核实 Chat 和对照使用相同 SVG，按钮 28px；复制得到完整回复并显示已复制，赞踩选中后可取消。
- Motif 用量明细实际为输入 61,480、输出 1,785、总量 63,265 tok；用时详情显示实际开始/完成时间，没有构造 TPS/TTFT。
- 桌面 1280/1600 与手机 390 宽度检查；等待原生侧栏响应式过渡完成后，手机四个 pane 均 260px 且无横向溢出；统计弹层 left=98/right=378，保留 12px 视口边距。视口覆盖已复原。
- 本轮仅 UI 行为，新增模型调用 0 次。未把已有真实结果当成本轮重新执行模型的证据。

## 发布

[PR #32](https://github.com/jingyio/DeepSeek-Harless/pull/32) 已合并并发布为 `e5b4d360e57ffb7a17cf5f16a0f4cdfe15420aaa`。四项 CI 均通过：run 38740089718（Linux 4m13s / Windows 4m38s），run 38740142430（Linux 3m40s / Windows 4m04s）。

生产 79 个任务空闲后切换，6,349 条保护数据指纹一致；上线检查 3 个账号、24 组对照评分、125 份 preset、324 份不可变文件保持。五个旧终态恢复正确，7 个既有 PPT preset initialize/list 成功、工具执行 0 次。配置变动为零，预算进程未重启；复核前后均 884 请求、峰值代理估费 0.619592442 美元。此前到本轮之间的外部实际使用不计作本轮测试，本轮模型请求为 0。

实际服务的客户端 SHA256 `09b3e709fa75bb3eefbc93c40287ea25b62c1caffb302f578ffaa0224ffe8739`，boot revision `d09aa7be5526`，源码与服务字节一致。公网浏览器登录页正常；未在正式账号发送测试请求。旧页面需要刷新获取新客户端。

私有验收文件 `.local/postdeploy-reply-actions-acceptance.json`；部署收据位于当前 deployment 的 `reply-actions-hotfixes/20261015T131535Z-e5b4d360e57f-af336158/receipt.json`，上线验收为 `postdeploy-reply-actions-acceptance-e5b4d360e57f-20261015T131627Z-c0f1a661.json`。页面截图 `.local/reply-actions-unified.png`。

收尾：确认 33 个 stage 任务和 15 组对照均终态后关闭 3 个临时进程、本机 SSH 转发及浏览器标签，未删除任何文件。回退只恢复应用到 `5d2e6a0`，不得覆盖会话、文件、评分或账本。
