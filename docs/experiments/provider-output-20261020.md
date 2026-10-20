# 避免 DeepSeek 默认8K输出截断

报障账号两次真实请求均 completion_tokens=8192；应用 max_output_tokens、每任务/累计费用、请求次数均 null，任务日志 output_cap_sent=false。旧实现删除输出参数，因此命中了 DeepSeek 非思考模式省略参数时的8K默认值。此默认值不是模型最大容量。

2026-10-20核对[官方API](https://api-docs.deepseek.com/api/create-chat-completion/)及[模型说明](https://api-docs.deepseek.com/quick_start/pricing/)：非思考默认8K，思考默认64K/Max128K，最大单次输出393216 tokens。按用户新的取消限制要求，WebDeepSeekAdapter 在任务不指定应用 cap 时显式使用这个真实的服务商容量；明确指定的诊断 cap 仍按原值。所有者、成员模板和报障账号当前费用/次数/output cap 都已核对为null，未清零累计账本。统计与归属检查继续存在。

私有实验 `concurrent-chat-20261020/long-output-9b3235aa.json` 使用真实 Flash/Off、相同1000行英文编号文本、两条独立合成预算路由，经过既有共享预算代理；只改变 max_tokens 省略/393216：

| 方式 | 完成token | 结果 |
|---|---:|---|
| 原省略参数 | 8192 | 第683行中途截断 |
| 服务商最大容量 | 11999 | 完整1000行，最后一行编号1000 |

这验证真实请求能越过默认8K截断点，不表示提供商单次容量或上下文可以无限。测试未读写任何用户文件、未修改其他任务。单元测试验证prepared/direct两条Adapter入口使用统一容量，并保持显式有限诊断参数。两次请求usage完整，代理估费分别$0.0098532 / $0.0144216，合计$0.0242748；账单实付未知。

源码be2c8cc包含当前主线合并及新兼容库paper18/ppt13，无新训练或质量推广。全量CI发现File转发仍委托基础Adapter而遗漏新容量；75ffc8b尝试替换委托Adapter，触发File种子的源码锁拒绝。该失败保留，未改旧证书或绕过守卫。

最终方案保留原File Adapter字节及其认证，在原生公开模型默认值中统一声明393216，让Harness把相同参数传入普通及文件两条路；任务请求守卫同步严格验证该值。模型请求日志分别保存真实wire值和null应用cap。两路序列化正文仍须完全一致；测试额外断言两路都传393216，File历史种子拒绝及当前种子准入均通过。该准入修复使用新兼容库paper19/ppt14，保留所有旧版本。最终完整回归和发布状态待收尾补录；原始结果留私有目录，不公开凭证或原请求日志。
