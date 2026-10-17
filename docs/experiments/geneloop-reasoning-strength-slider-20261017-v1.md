# 网页思考强度滑杆验收

## 范围

用户要求在网页通过横向拉动调整全部思考强度。基线为 main `eda501e`，分支 `codex/reasoning-strength-slider`。当前 API 的实际档位是 Low/High/Max，加上关闭思考的 Off；minimal/medium/xhigh/ultra 是兼容别名，不作为额外强度展示。依据：[DeepSeek 思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。

采用原生离散 range，显示关闭/低/高/最高；只展示当前模型与已安装 Adapter 共同支持的档位。支持拖动、点击档位和键盘方向键/Home/End。保持默认 Off，旧 On 保存的 high 不迁移。使用既有原生模型目录、选择队列及发送屏障，不另建 Agent 循环；选项即时显示，保存失败回滚并保留草稿、附件。预留说明高度，避免拖动时控件移动；异步目录加载后补上首次焦点，Escape/外点/离开面板关闭。

## 参数与 Motif

Off 由原生适配器发送 thinking.disabled，不携带 reasoning_effort；Low/High/Max 发送 thinking.enabled 与相同原生 effort。档位绑定会话及本轮两侧，所有非 Off 值进入幂等摘要，拒绝以相同请求 ID 修改强度。思考强度不改变 Execute/Shadow，也不额外加入输出上限；Max 的原生输出费用预约继续使用现有预算 gate。

任务准入代码变化触及当前 Motif 代码锁，因此免费重编同一真实冻结证据，另发 PPT r9 和 Paper v2。两场景各自原两个训练决定与一个留出决定、图、参数边、完整工具 Schema、来源证据字节保持。旧 r8/v1 保留，Legacy PPT 仅更新兼容绑定，Data 不变。新增采集/模型/场景工具调用均为 0；不把兼容重编称为新训练或质量、费用收益。

## 验证

定向诊断已覆盖四档原生 HTTP 序列化、按模型能力取交集、Max 默认输出费用预约、四档双侧冻结与幂等冲突；滑杆诊断覆盖模型目录变化、快速跨档、即时显示、顺序保存及失败回滚。它们属于确定性协议检查，不冒充真实模型验收。

Linux 完整 Node 回归 794 通过，3 项 Docker 测试未显式启用；最后前端焦点/稳定布局修补另经 40 项定向协议检查通过。Python 全量在完整 PDF 工具环境中 1020 通过、4 项旧文献 MCP 子进程因未继承打包动态库失败；复用既有 Poppler 包装脚本后，这四项定向 4/4 通过，共覆盖全部 1024 项。没有改测试来隐藏环境失败；首次 PATH 未包含工具链时的 193 项 skip 与失败日志均保留。无模型 smoke 通过。

隔离 stage 的真实原生 Web HTTP 验收：Flash/Pro × Off/Low/High/Max 共八个独立 Chat，8/8 completed、8 次模型请求；各任务配置中实际模型/档位与选择相同，max_tokens 仍省略。另做 Flash Max 的 Paper Baseline/Motif 双路，2/2 completed、16 次请求、1 次真实 Execute 验证跳过，4 个 PDF/Markdown 文件经鉴权下载并核对 SHA。合计 24 次真实请求，代理估费 $0.03483096，账单实付未知。没有把简单 Chat 的 token 当作不同强度质量对照。

浏览器经正常登录验证四个离散位置、鼠标实际横向拖动、点击档位、Tab/方向键/Home/End、Escape 返回触发器；切换 Pro 使用默认 Off。Max→Low 实测滑杆 x/y/width/height 完全不变。深色桌面与 390×844 浅色界面均通过；窄屏面板宽 320px、左边距 12px，无页面水平溢出。测试后恢复主题、视口，无浏览器 JS error。确定性夹具另覆盖迟到保存、立即发送、失败回滚和跨会话独立。

隔离环境首次沿用正式 Origin 导致本机浏览器登录被 CSRF 正确拒绝；改为仅此 stage 的精确 localhost Origin/受信任主机后正常登录，没有注入 cookie 或放宽正式守卫。两次准备中的路径映射错误与相关目录同样保留。正式发布、CI 与公网复核以对应 PR 最终回执为准；原始来源、账号凭据、完整轨迹和错误记录仅存私有 `.local/reasoning-slider-*` 及隔离服务器目录，不提交。

费用和请求次数、每任务与输出上限沿用 null，累计账本不清零。真实调用记录代理估费，账单实付未知。本轮只验证选项、执行和交付连通性，不评估不同强度的整体质量排名或 Motif 稳定降本。
