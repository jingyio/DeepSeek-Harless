# 避免 DeepSeek 默认8K输出截断

报障账号两次真实请求均 completion_tokens=8192；应用 max_output_tokens、每任务/累计费用、请求次数均 null，任务日志 output_cap_sent=false。旧实现删除输出参数，因此命中了 DeepSeek 非思考模式省略参数时的8K默认值。此默认值不是模型最大容量。

2026-10-20核对[官方API](https://api-docs.deepseek.com/api/create-chat-completion/)及[模型说明](https://api-docs.deepseek.com/quick_start/pricing/)：非思考默认8K，思考默认64K/Max128K，最大单次输出393216 tokens。按用户新的取消限制要求，WebDeepSeekAdapter 在任务不指定应用 cap 时显式使用这个真实的服务商容量；明确指定的诊断 cap 仍按原值。所有者、成员模板和报障账号当前费用/次数/output cap 都已核对为null，未清零累计账本。统计与归属检查继续存在。

私有实验 `concurrent-chat-20261020/long-output-9b3235aa.json` 使用真实 Flash/Off、相同1000行英文编号文本、两条独立合成预算路由，经过既有共享预算代理；只改变 max_tokens 省略/393216：

| 方式 | 完成token | 结果 |
|---|---:|---|
| 原省略参数 | 8192 | 第683行中途截断 |
| 服务商最大容量 | 11999 | 完整1000行，最后一行编号1000 |

这验证真实请求能越过默认8K截断点，不表示提供商单次容量或上下文可以无限。测试未读写任何用户文件、未修改其他任务。单元测试验证prepared/direct两条Adapter入口使用统一容量，并保持显式有限诊断参数。源码be2c8cc包含当前主线合并及新兼容库paper18/ppt13，无新训练或质量推广。费用、完整回归和最终发布状态待收尾补录；原始结果留私有目录，不公开凭证或原请求日志。
