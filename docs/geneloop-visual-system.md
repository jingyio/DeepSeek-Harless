# GeneLoop 网页视觉规范

美化基线为 `e1b90a37447bd389f2af5b4bff9e468319a89536`。完整源码保存在远端标签 `pre-apple-ui-20261016`，本地独立备份包 `.local/pre-apple-ui-20261016.bundle`。本轮 Emil 设计细化前的版本为 `c793937`，另存标签 `pre-emil-ui-20261016` 与同名私有 bundle。所有样式集中于 `src/adapters/geneloop_theme.css`，通过现有页面入口内联加载，不依赖第三方字体、图标 CDN 或额外网络请求。

修改 CSS 后运行 `node scripts/sync-geneloop-theme.mjs`，同步到原有品牌脚本的生成区；账户页读取同一 CSS。`--check` 与回归测试防止两处视觉版本漂移。PPT 认证锁覆盖的任务代码逐字保持基线，不因美化更新执行认证。

## 设计方向

参考 Apple HIG 的层次、材质和清晰文字，以及 Google 网页的信息密度与清晰操作。GeneLoop 保留自己的螺旋标识、蓝色操作、绿色 Motif 含义。内容左对齐，阅读区域延续用户可调整的宽度，侧栏／正文／浮层保持明确层级。避免把每个段落包成卡片或用模糊效果覆盖正文。

- 浅色：柔灰 `#f5f5f7`、纸白 `#ffffff`、石墨 `#1d1d1f`、次级灰 `#62626a`、蓝 `#0066cc`、绿 `#147d64`。
- 深色：画布 `#161618`、表面 `#222225`、文字 `#f5f5f7`、次级灰 `#b0b0ba`、蓝 `#82b6ff`、绿 `#69d1b5`。
- 字体使用平台系统字族，Apple 设备使用系统字体，Windows 使用 Segoe UI，中文回退苹方／微软雅黑。界面 12–14px，标题 20–30px；聊天内容仍服从原有字号设置，代码保留等宽字。
- 圆角随层级：小控件 8–12px、卡片 14–20px、输入框和弹窗 24px。浮层使用细边框、低强度双层阴影和可退化的背景模糊；静态正文不加动画。
- 图标保留现有 SVG 语义与点击区域，统一光学尺寸、圆端线条和按钮底座。按下时立即响应，松开后回到原位；尊重减少动态、减少透明度、高对比和强制颜色设置。

界面结构：侧栏用于持续导航；顶部标题与对话／轨迹分段选项；中间阅读；底部独立输入表面。设置与登录、归档、回收站、模型菜单、双栏、评分、文件卡片、过程和轨迹共享同一套颜色与材质。

## Emil 设计规范与动效

按用户指定安装并参考 [emilkowalski/skills 的 apple-design](https://github.com/emilkowalski/skills/tree/main/skills/apple-design) 和 [animation-performance](https://github.com/emilkowalski/skills/tree/main/skills/animation-performance)，来源固定为 `2d228630ba1446365f614a108cb8252f1feda202`。技能仅用于设计指导，不进入应用运行时，也不新增动画依赖。

诊断发现原按钮与输入框会逐帧重绘阴影，菜单和设置则直接挂载出现。本轮删除阴影/边框动画，静态保留原来的层次；菜单模糊由 24px 收敛到 12px，避免过重材质。设置标题提高字重与层级，平台字体开启 optical sizing。

- 小控件按下缩至 97%，60ms 响应，180ms 回位；导航行直接高亮。禁用控件保持原行为。独立 `scale` 不覆盖上游定位 transform，不缩小布局点击区域。
- 对话历史只在原加载边界确认 ready 后进行 220ms 淡入/4px 位移；不动画整个页面、工作区侧栏或输入框，不对流式 token 添加动画。不等待动画结束再放开操作。
- 菜单 140–180ms、设置面板 240ms 轻微淡入，使用 CSS opacity/translate/scale，无弹跳。关闭/卸载沿用原来的即时行为；Escape 和再次导航可以随时打断，不为退出动画延迟关闭。
- 不引入 rAF 循环、每帧 React state、全局 DOM 监听、`transition: all` 或 blanket `will-change`。减少动态时跳过新入场与缩放，减少透明度时去掉浮层模糊，高对比时强化边界。

验证区分静态截图、交互检查和 CPU 模拟；桌面 4× CPU 降速不代表真实中端手机 GPU、内存或 Safari 测试。底层请求耗时不由动画缩短，不能据此宣称后端提速。

## 功能与回退边界

视觉层不改事件、接口、任务分发、模型、权限、额度、文件、评分或存储。原生主题与字号控制继续生效，隐藏状态、禁用状态及键盘焦点仍由原组件持有。少量布局类绑定固定 `@deepseek-ai/dsh` 0.1.5-rc.3；升级依赖时必须核对这些类及真实截图，不允许修改 node_modules 掩盖不兼容。

发布前检查明暗主题、登录/注册、主页/侧栏、场景和模型菜单、普通与双栏历史、文件下载、设置各面板、弹窗、轨迹、窄屏与键盘焦点。测试只使用隔离 QA 账号与合成材料。

回退时将**应用代码**切回 `pre-apple-ui-20261016`，使用原配置重启应用入口；保留账户、会话、附件、结果、评分、累计账本及预算进程。不得恢复旧数据库或账本。也可单独撤销两处内联样式注入及账户 body 样式类，原始组件样式完整保留。

参考：[Apple 材质](https://developer.apple.com/design/human-interface-guidelines/materials)、[Apple 字体](https://developer.apple.com/design/human-interface-guidelines/typography)、[Google Material 字体](https://m3.material.io/styles/typography/overview)。这是 GeneLoop 自有实现，不使用 Apple 专有字体或 SF Symbols 资源。
