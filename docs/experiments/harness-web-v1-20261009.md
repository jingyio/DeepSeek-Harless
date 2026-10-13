# Harness Web 免费联调验收：harness-web-v1-20261009

## 问题与假设

为既有运行内核加官方 Web 操作入口，验证会话 preset、MCP 权限、服务端预算和 Motif 接缝。若浏览器不能真正派发 MCP、改变会话/配置绕过限制，或失败批次记为成功 skip，则假设不成立。页面资源成功加载只算启动验收。

## 任务与配置

合成/运输夹具诊断，无付费 Provider。example 固定两条笔记的版本再读取；portfolio 使用 `l_retrieval_persistence` 与首发认证 library。baseline/shadow/execute 使用相同题面、来源、工具和 1000 token 输出上限。没有新训练、真实科研任务质量评审或费用对照。

两端 `feature/paper-submission`，基准 commit `2368235f274329be6227a8393b850633cb943da4` 加未提交改动。服务器 Ubuntu 22.04、Node 22.23.3、Python 3.10.8、DSH 0.1.5-rc.3。预算 0.25 美元、最多 24 次代理请求，Off、无压缩；模拟用量固定为每次 100 输入/20 输出，不能当成实测 token。有效配置、代码/题面/场景/hash 与原始日志位于每个 `.local/web/runs/<id>/`，原生诊断清单是 `.local/web/protocol-check.json`。浏览器截图和同步结果位于本地 `.local/web-review/`，不提交。

复现：服务器加载私有环境后 `npm run web`，本地 SSH 转发、官方 token/cookie 登录、选择隔离 work、在首页粘贴 prompt 并发送。Motif 用 `--scenario portfolio-v1 --mode <mode>`。原生协议诊断 `npm run web:check`，不能替代浏览器步骤。

## 已验证结果

| 检查 | 结果 |
| --- | --- |
| 官方页面、资源、cookie、会话与事件 | 本地 SSH 转发及实际浏览器通过；无认证创建返回 401 |
| example | 浏览器四次真实 MCP 调用、五次模拟请求，答案有两条来源及版本 |
| 会话/preset/模型权限 | 新会话、fork、其他模型/provider、错误 session、改变题面被拒绝；preset 根只提供专用场景 |
| 请求数/预算 | 实际浏览器上限 1：一次 MCP 后显示 HTTP 429，服务端记 budget_exhausted、只转发一次；原生诊断预算 0 时一次也不转发 |
| portfolio baseline | 浏览器 13 次 MCP；14 次模拟模型；0 候选/尝试/verified skip |
| portfolio shadow | 浏览器 13 次 MCP；14 次模拟模型；9 个候选，0 尝试/verified skip |
| portfolio execute | 浏览器 13 次 MCP；7 次模拟模型；5 次接管尝试，5 个结果验证成功批次 |
| 旧来源版本 | 原生 Web 返回普通模型路径，14 次请求、0 接管成功 |
| 工具失败 | 一次此前合法批次 verified，后续失败批次只记未验证；回退后在 24 次请求上限耗尽。失败/成功批次集合不相交 |
| 越权工具、Provider 故障、取消 | 三组原生诊断通过；越权工具被拒，Provider 故障终态 failed，取消终态 cancelled |
| schema/用户 envelope/辅助请求 | 新 Web 策略测试拒绝；保留既有 Motif 错误会话、schema 变化、版本漂移及工具失败回归 |
| SDK/公共回归 | 137 Python、30 Node；smoke 18 题/83 对象；4 Motif 重编译、46 公共证据重放、SDK 四组对照通过 |

浏览器独立 run：example `b1bce3882e5f470eb6f8ccc088e7a505`，portfolio baseline `534d7e3858cb4bcd96b7f092c9797cb2`，shadow `39dbd0c1f09c404c9bddd6cdb513a976`，execute `fe53e26f5e8944158f9eca9075ba2eda`。三组取得同四个对象及版本。UI 的步数包含 Motif 合成工具决策，不能代替预算代理的上游请求数。

浏览器请求上限 run 为 `305e8e2a59c04e8cb05bf4e4f5549369`，截图 `browser-budget.jpg`。最终记录增强后又完成 11 组服务器诊断和全部 SDK 回归；每个 run 保留其当时的代码哈希，不追改先前浏览器记录。最终正常诊断额外核验模型请求实际为 `deepseek-flash`、`thinking.type=disabled`、`max_tokens=1000`，记录初始会话事件、会话头与任务绑定。

## 失败及处理

初始页面输入裁剪了题面两端空白，严格原始 hash 拒绝请求；明确记录传输规范化 hash，内部字符仍精确检查。Controller prompt 的取消信号最初遗漏，导致 `throwIfAborted` 错误；按安装声明恢复转发。固定 DeepSeekAdapter 最初遗漏扩展准备函数，产生请求扩展错误；补官方空扩展协议。preset schema 最初读成空的全局视图，之后又受工具顺序影响；通过官方 scope API 及 system-prompt 默认排序修正，完整 schema 检查一直保留。工具失败诊断初版错误地要求整个 run 的 verified 总数为零；实际此前已有合法成功批次，改为严格验证失败批次不计成功，并保留该反例。

浏览器连接曾初始化超时，后来通过 in-app browser 恢复，实际操作已完成；SSH master 过期后重连并恢复端口转发。批量停止运行目录的脚本被自动审批拒绝，未执行；已替换为按明确 RUN_ID、PID 和进程启动标识停止单个任务的入口。未修改上游核心或放宽认证。

## 成本、结论与限制

所有新增真实付费请求、账单支出为 0。账本中的美元值仅按模拟 usage 代入既有峰值规则，既不是账单也不是 Motif 降本证据；端到端耗时、人工作业/开发成本和真实任务质量未评审。本轮在这些条件下支持官方 Web → SSS 场景 → 真实 MCP → 原生答案及受限 Motif 接缝可运行。

真实 Provider/embedding、付费预览确认 UI、多人账号隔离、论文生产投稿和其他平台 Web 未验证/未开放。跨启动不恢复旧任务，只允许同一次启动内页面恢复；新任务需重启。官方新会话拒绝目前记浏览器警告，预算耗尽显示通用 HTTP 429，缺少专用友好提示。后续先保持单操作人免费试用，另行设计并授权真实模型入口。
