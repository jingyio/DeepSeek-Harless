# Harless 场景、模式与 RSI

在原生 `/harless` 菜单选择 Scene、Mode、RSI。选择只影响后续任务；已预览、确认、运行的任务保持冻结配置。菜单不调用模型。前端只传登记 ID 和配置值，不传服务器路径、启动命令或工具调用。

| Scene ID | 后端配置 | 能力与边界 |
| --- | --- | --- |
| `ppt` | `scenarios/research_ppt/web-scenario.json` | 既有 19 工具 TS Adapter/Python 后端，批准 PDF/PPTX、读取、生成新副本、修订、实际渲染验收与交付 |
| `paper-proofreading` | `scenarios/paper_proofreading/scenario.json` | 5 只读工具：PDF/文本读取与模型校对，复用论文分支 LaTeX 字面引用/标签/浮动体/已有日志检查；不编译、不查外网、不修改原稿 |
| `research-data-analysis` | `scenarios/data_analysis/scenario.json` | 4 只读工具：真实 UTF-8 CSV/TSV 的列类型、空白缺失、描述统计、完整样本 Pearson 相关；不执行任意代码、插补、显著性或因果推断 |
| `files` | `scenarios/file-management/web-scenario.json` | Files：13 个文件 MCP 工具，盘点、读取、查重、文本索引与检索；显式开启整理权限后，仅对本任务上传副本执行获准的复制、移动、隔离计划，并保留预览、授权和恢复收据 |
| `new-scene` | `scenarios/general/scenario.json` | 普通 Harness + `list_files/read_file`，读取本 Session 已上传的 UTF-8 文本；没有样例数据、shell 或任意主机文件能力 |

论文平铺源码保留原文件名，最多 8 个文件；嵌套目录/动态 TeX/宏展开不作为完整校验。数据最多 100,000 行/128 列、拒绝重复列名、参差行和非有限相关输入；只把空白视为缺失。所有文件读取复核任务准入 SHA，不能通过重新 pin 接受确认后漂移的资料。

## 模式与库

| 选择 | RSI | 实际策略 |
| --- | --- | --- |
| Origin (`baseline`) | On/Off | 原生 Harness；不创建 Motif interceptor |
| Shadow | On | 合格库进行匹配审计，继续 LLM；未认证的部分记录回退 |
| Execute | On | 启动核验库、完整有序 Schema、代码/证据绑定；结构提案须通过参数来源和版本守卫，实际工具结果通过后才计 Verified Skip |
| Shadow/Execute | Off | 保留选择，当前任务实际 `baseline`；再次 On 重新检查准入 |

PPT 通过服务器 `HARLESS_PPT_RUNTIME_BUNDLE` 加载 `online-manifest.json/library.json/tool-schemas.json/task.json/certification.json`。认证包只允许 `independent_trace_structure / structural_only / ppt_uploaded_sources_v1`。每次预览把批准输入的 SHA 与当前 Task/Session 绑定到 `bound-motif-task.json`，冻结摘要；不复用历史题面或历史 source_id。`source_id` 只能从本任务真实成功 pin 的结果绑定。

结构认证仅覆盖唯一闭合的 `pin_source → read_source` 读链；需要语义排名时明确交回 LLM，不提供固定向量伪装匹配服务。一般需语义匹配的历史入口仍要求实际 loopback 服务。只有整个执行批次的真实结果验证通过才增加 `verified_skips`。PPT 库尚未质量/费用晋级，机制通过不代表科研质量或稳定净降本。论文、数据分析、Files 和通用场景当前无产品认证库，Execute On 明确拒绝；Files 的私有实验库不自动发布为产品库。

管理员可用 `scripts/publish-ppt-runtime.py --dataset ... --schemas ... --output ...` 从两个独立正常轨迹及一份留出重新编译；或用 `--compiled-manifest` 对未变化且全部证据锁仍有效的认证 IR 更新部署绑定，不重新运行留出、也不改旧证书。完整实际 Harness Schema 为认证输入，不从当前任务临时凑出认证。历史 `example/portfolio` 只在 `config/harless-diagnostics.json`，不出现在产品映射。

## PPT 输出与私有依赖

PPT 的原生菜单增加下一任务页数、模板、输出权限。默认 6 页、academic、只读；明确选择“允许生成 PPT 新副本”后，下一次发送仍须附批准 PDF/PPTX。发送确认只授权所属任务的新产物，不授权修改原稿。任务 API 的显式 `scene_options` 覆盖菜单值；改变菜单不改变已预览任务。`set_scene_options` 和继承 Session 均复用现有认证及隔离设置。

Files 的菜单增加“整理权限”，默认只读。选择“允许整理任务副本”并确认任务后，最多 6 步，只允许原始上传文件作为来源，目标限制在 `organized/`、`copies/`、`quarantine/`，不可覆盖；MCP 必须先预览，再取得同计划授权回执，执行与恢复留下私有日志。结果和备份均属于当前用户的 Task/Session。普通文本检索不需要整理权限；内容解析有格式与长度边界。
Files 的 Word/Excel XML 单成员读取上限 4 MiB，Excel 最多解析 10,000 行，工具元数据只预览前 50 行/每行 32 列/每格 200 字符；超过解析边界返回不可读诊断。图片只读取元数据，PDF 仅提取前两页。整理权限不包含转换、归档、删除原件或跨目录读取。

服务器设置 `HARLESS_PPT_RENDERER_ROOT` 为固定 LibreOffice 安装根，`HARLESS_PPT_FONT_ROOT` 为固定静态字体配置目录。只在对应 MCP 子进程传递 PATH 与 Fontconfig；不改变全局 cwd/env。缺依赖时 PPT 仍能只读，输出任务明确返回 `scene_output_unavailable`。转换使用独立任务 profile 和 CPU/无界面设置，PDF/PNG/验收报告归所属任务。渲染、文字、字形、来源或产物哈希失败不标记已交付。

## 用户、Session 与任务冻结

沿用已完成的账号网关和 bwrap 隔离。管理员在私有网关配置增加 `memberSceneDeployment:{projectRoot,pythonExecutable,pythonRoots,libraryRoot?,rendererRoot?,fontRoot?}`。它只挂载只读公共代码/安装依赖和纯 Runtime 库；拒绝整个用户目录、继承凭证、原始轨迹、私人输入和任意启动命令。每名成员的输入、设置、Session、输出和预算路由仍属自己的环境；没有该部署字段的旧配置继续明确使用 chat-only 策略，不继承所有者资料。
Files 的成员部署白名单仅接受固定 `scenarios/file-management/plan_tools.py` 与由服务端 Session 工作区生成的 `FM_WEB_WORKSPACE/FM_TASK_FILE/FM_OUTPUT` 三项路径；不会把用户输入转换成 MCP 启动命令或主机文件路径。

任务冻结 Scene/配置版本、选择与实际模式、RSI、Prompt、完整工具 Schema/权限、库/Manifest/认证及动态绑定摘要、软件文件摘要、Provider/输出 cap、任务及启动预算、用户/Session/Task、上传/job 摘要。确认后变化拒绝。库、配置切换不修改运行中的任务；费用、请求上限和错误恢复沿用原代理。旧会话迁移由另一协作者处理，本次不改归属校验。

附件复用官方 `fileUploads.resolve` 和所属 Agent；最多 8 文件、每文件 20 MiB，简易任务上传 API 仍限 256 KiB。两个账号不能读取对方 Task、Session、receipt、输入或轨迹。五场景可以依次创建新任务；重绑定 Files/PPT 使用新 Session，普通 workspace 连续纯文字对话保留主线行为。

## 验证入口

```sh
npm test
npm run smoke
npm run web:controls:check
npm run web:scenes:check
node scripts/project.mjs python scripts/check-harless-members.py
node scripts/project.mjs python scripts/check-harless-members.py --render-ppt
# 真模型必须在累计授权内明确启用，记录原失败/重试：
npm run web:scenes:check -- --real-model --scenes paper-proofreading research-data-analysis
npm run web:scenes:check -- --real-model --scenes ppt --mode execute
# 实际工具/渲染与 Runtime 协议诊断，不调用云模型：
node scripts/check-ppt-runtime.mjs <所属私有任务/job.json>
```

本轮结果见 [上线准备记录](experiments/harless-launch-readiness-20261014-v1.md)，历史桥接见 [桥接记录](experiments/harless-scenes-runtime-20261013-v1.md)，库取回见 [迁移记录](experiments/ppt-library-transfer-20261014-v1.md)。科研质量、模型自主完整 PPT 生成及稳定费用收益需要独立后续验收，不能用固定计划的机械交付代替。
