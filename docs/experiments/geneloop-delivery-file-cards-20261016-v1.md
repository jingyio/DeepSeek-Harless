# 交付文件卡片与正文文件链接

- 范围：基于已发布 `7076ecb`，分支 `codex/delivery-file-cards`，仅改网页呈现、相关组件诊断和文档。
- 卡片与原生上传附件共用公开的 `FileTypeIcon`、`fileExtension`、`fileSizeText`。左侧类型图标，中间名称及类型/大小，右侧小下载图标；64px 高、16px 圆角，长名省略但提示完整 basename，窄栏按可用宽度收缩并换行。大小缺失/非法时省略，真实零字节仍显示。
- 正文中已登记的文件链接采用蓝色文字，重置原生代码胶囊和按钮两层背景/边框；普通 inline code、代码块、原生点击和自定义 caption 保留。文件提示只显示名称，路径匹配仍依赖该侧批准的不可变回执。普通 Chat 原生文件 mention 使用同一视觉规则。
- 下载仍使用既有账号鉴权、same-origin/no-store、大小和 SHA256 验证、防重复点击、超时、取消及失败重试；不增加模型调用，不改变工具、Motif 库、后端导出或成品发布权限。

## 验证

- 组件诊断：`node --test tests/test_harless_paired_client.mjs tests/test_geneloop_chat_presentation.mjs`，61/61 通过。配对组件 54 项覆盖 PDF、DOCX、PPTX、CSV、JSON、TXT、PNG、ZIP、未知扩展名、无扩展名、0/缺失/负大小，以及匹配路径、自定义文字、重复下载、鉴权错误、SHA 错误、超时和重试。格式样例为明确的无模型诊断字节，不当成文档生成质量证据。
- 服务器完整 `npm test`：Python 796 通过/193 既有跳过，Node 742 通过/3 既有跳过；smoke、motif:check 均通过。全部为零模型回归，没有新生成或费用。
- 本机 Edge 使用既有诊断账号的真实 PPT、论文、数据会话，只在唯一原生插件 bundle 中替换完整候选客户端（SHA `a3bcc52ca5c810b1f2099e499df9fa473f661d4bfd94482c7446dc8293f45add`）。28 张实际卡片 260×64px、16px 圆角、原生图标/下载图标和主题字体通过；13 个真实正文文件 mention 为蓝色、无背景/边框且继承字体，26 个普通 inline code 保留底框。深浅主题及窄屏尺寸无横向溢出，长文件名另作为明确标注的 DOM 布局诊断。
- 实际点击下载 PPTX、PDF、PNG、Markdown、SVG 五种既有成品，大小及 SHA 全匹配，键盘可触发下载，页面 JS 异常 0。初版浏览器路由误拦截长连接导致诊断脚本关闭错误，收窄到 `/plugins/` 后通过，失败证据保留；没有付费请求或生成重试。浏览器验收只证明样式和已有文件下载，不是重新验证文件生成质量。
- 私有截图、下载及网络诊断位于忽略的 `.local/delivery-cards-browser/`；不提交凭证、原始会话或资料。最终 CI 与发布状态在对应 PR 回执记录。
