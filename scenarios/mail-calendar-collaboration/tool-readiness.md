# 归档工具恢复与第一阶段就绪情况

2026-10-11：已从本地 archive选择性恢复邮件/日历工具、授权入口及回归测试，固定依赖并新增`scenario.json`。工具恢复与无模型诊断完成；真实账户连接、首批Demo质量和MGGA收益尚未验收。

## 已恢复

- Gmail：搜索、正文/完整线程读取、收件箱线程批量读取、本地邮件草稿及读取；不强制逐封串行。
- Calendar：日历/事件查询、搜索、单事件读取、忙闲、当前时间、空档计算及候选重新核验、本地新建事件预览。
- 原人工发送/建会确认代码保留，场景工具白名单不暴露`send_email`、`create-event`或打开确认页面的工具；Calendar新增服务端白名单，直接调用未允许工具也拒绝。
- 源码与原始摘要见[来源清单](archive-source.json)，固定来源commit `810edf46872e190019667239cb4e5b6b85df8f99`。现在无需取得archive即可安装这些已恢复模块；没有推送整个archive、私人资料或原始轨迹。

复用旧`.cjs`实现，仅抽出测试入口、用当前Node解释器启动依赖包并补Calendar白名单，不另建Agent循环。新场景Gmail使用`scoped_gmail_request`命名，保留原轨迹解析器对结构化元数据的识别；Calendar工具中的连字符由现有Harness规范成下划线。

## 安装、授权与入口

在分支的项目根目录安装：

```sh
npm ci
npm run setup
npm run mail-calendar:check
npm run scenario -- --scenario scenarios/mail-calendar-collaboration/scenario.json --budget-usd 1
```

最后一行只生成配置预览，不连接Google或调用模型。`mail-calendar:check`使用合成输入与工具替身，验证真实MCP协议、权限拒绝、本地预览和确定性时段计算，不能当成真实账户/模型验收。

Google OAuth客户端和token留在服务器私有`.local/google-gmail/`、`.local/google-calendar/`。服务器操作需先加载`.local/remote-env.sh`；从Google Cloud取得客户端并启用对应API、登记测试用户，然后分别执行`npm run gmail:auth`（只申请gmail.readonly）与`npm run calendar:auth`。这是后续操作者授权入口，本次未执行。Calendar上游的OAuth权限与本场景工具白名单分别核对；有OAuth写权限不代表Agent获准写入。

授权脚本不会修改父进程环境，启动前仍须在项目根目录设置以下私有文件路径；不打印文件内容：

```sh
export GMAIL_OAUTH_PATH="$PWD/.local/google-gmail/oauth-client.json"
export GMAIL_CREDENTIALS_PATH="$PWD/.local/google-gmail/tokens.json"
export GOOGLE_OAUTH_CREDENTIALS="$PWD/.local/google-calendar/oauth-client.json"
export GOOGLE_CALENDAR_MCP_TOKEN_PATH="$PWD/.local/google-calendar/tokens.json"
```

若Gmail授权复用了Calendar客户端，`GMAIL_OAUTH_PATH`改指该客户端路径。缺失或过期时如实失败，不切回模拟Provider声称真实通过。密钥/账号授权不在Git中；Windows授权入口未验证，当前shell授权脚本面向Linux/macOS。

真实模型运行在服务器，使用`npm run scenario:real -- --scenario scenarios/mail-calendar-collaboration/scenario.json --budget-usd 1`或同场景的Web入口。运行前登记实际模型（此分支SDK默认deepseek-flash）、baseline/shadow模式、reasoning_effort=off、累计预算及输出/步数上限；默认不压缩，不新开任务规避累计额度。此分支SDK原默认预算仍为0.25美元，示例显式指定1美元，不改公共默认。本次没有调用真实模型。新的自动execute测试保持暂停。

`prompt.md`是授权真实账户的只读需求；不会把合成review资料整体塞给模型。正式首批逐题验收需先把已接受题面实例化到对应真实来信/日程和访问范围，不能拿虚构ID查询真实账户。

## 尚未完成

1. 旧`prepare-event`仅预览新建事件。B01/A03/D03的既有提醒更新/取消目前只能输出可审阅差异，尚无专用更新/取消预览工具，也不实际修改日历。
2. 真实偏好/事项状态、账户内访问范围、分页/线程完整性和新鲜性合同仍需验收。消息ID不代表整个线程没有新回复；历史读取边不是当前有效授权。
3. 尚无本场景正常真实轨迹、独立认证库、通用Motif组合或真实跳过/省费证据。每日调度与真实推送不在本次恢复范围。

先在上述边界内跑通原生任务并人工评质量，再审计可替代的完整模型请求；压力测试后置，不能为展示机制添加步骤。

## Windows诊断兼容修复

归档本地队列此前把Unix权限位当作所有平台的文件安全判据，Windows会错误拒绝正常预览。现仅在POSIX平台核验权限位；普通文件、符号链接拒绝、内容摘要及操作状态检查仍在所有平台生效，并增加POSIX宽权限拒绝和日历内容篡改回归。Windows私有目录依赖操作者配置的ACL，当前不自动配置或认证ACL；授权脚本与真实账户流程仍未验证，人工发送/建会的凭证安全守卫保留不变。CI成功仅表示无模型诊断通过。
