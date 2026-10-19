# 本地文件管理日常使用

GeneLoop main 的日常入口为 `npm run web:real`，进入工作区后输入 `/`，选择 **file — 文件管理**，或直接输入 `/file 描述需求`。`npm run management` 是带原文件管理限额的同一 Web 启动别名，不再另起旧前端或启动别的用户的历史认证进程。`/management`、`/files` 仍作为文件管理提交前缀兼容；菜单统一显示 `/file`。`--mock` 仅用于免费协议诊断。

文件管理沿用当前 DeepSeek Harness SDK、TypeScript 在线 Motif 与 Python 离线学习/认证，文件模型请求同时通过原平台计费和原持久化任务预算。当前该入口使用 DeepSeek / Off；任务默认最多 96 步/请求、4000 输出 token、2 次验收修复及 2 次服务商重试，另受平台和账号的累计限额约束。不能把“持续学习”解释成任意代码自改或忽略权限/认证。

Web 每个账号的长期目录在 `.local/web/file-management/accounts/<账号摘要>/`（成员沙箱内对应相同持久挂载），包括任务、原始轨迹、费用、工作副本和 `rsi/daily-management-real-v3`。跨工作区共享该账号的经验，文件副本按工作区隔离；其他账号的经验和资料不混用。公开种子按不可变版本保存在 `motif-libraries/file-v*`，仅安装与当前源码和目录契约一致的最新版本，只带可复用 IR、源码锁及脱敏认证摘要，不含私有原始证据或旧授权。失配或没有合适经验时走普通 Harness；新轨迹经独立认证后才进入活动库。

下文保留文件管理本地研究与维护能力。旧研究档案位于 `.local/rsi`；这些档案的 CLI 统计不能当作某个网页账号当前库的统计。不要清理或上传 `.local`。

## 文件场景的并行准备与时序目标

`/management` 仍自动执行并开启持续 RSI，使用原长期库与预算。已登记 MCP 的工具请求可在同一原生消息中准备；已独立认证业务的多个请求各自保存状态并续接，效果逐个核对，不能把一个请求的收据用于另一个请求。其它业务的准备不等于允许自动执行。

可以直接描述：`时序要求：先完整读取 a.txt，再完整读取 b.txt。不修改任何文件。完成后核验并提交报告。` 系统会冻结文件与首个完成顺序，并从原生轨迹核对；PDF/图片要求实际全文/OCR覆盖，打开或预览不算完整读取。后续合法复读允许，首次顺序错误不能靠后来重读抹去。复杂或未完整解析的表述显示待复核。

同批 PDF 打开/备忘录读取、2–16项准备后执行等受支持表述及限制，见[接口说明](changes/parallel-temporal-rsi.md)。最终以宿主完整验收为准，单次 `submit_report` 的暂存回执不代表时序已通过。失败保留原权限、版本、费用和恢复信息，按原修复上限回退或失败退出，不会放宽标准入库。

## 使用与状态

安装 `npm ci`、`npm run setup`，通过环境、项目 `.env` 或既有 `.local/deepseek.env` 配置 DeepSeek。打开启动日志所指的私有本地登录入口，创建工作区和会话，上传文件，用 `/file` 描述需求。历史访问地址可能在服务重启后需要重新登录。

文件管理自动执行、自动匹配经验并在任务封存后持续学习，界面没有 Execute 或 RSI On/Off 开关。通过 `/file` 或文件场景接口提交的后续任务使用此行为；日常入口不读取旧前端的 Execute/RSI 开关。网页沿用原生回复、工具过程和交付卡片；账号库、学习和费用状态可由受认证的文件场景接口查询，高风险操作继续单独确认。已有任务的冻结资料和原记录不追改，恢复仍核验原版本和权限。[兼容规则](changes/management-automatic-ui.md)。

`npm run management -- status` 免费查看当前管理库与凭证是否配置；`npm run management -- motifs` 免费列出每个经验档案的代数、经验类型、停用数、源码失效数与失败候选。不同源码/证书版本的经验记录不能当作不同工作流数量，也不能把兼容数当作历史学习总量。当前匹配还须通过具体任务的 schema、权限、参数及版本守卫。

`npm run management -- experience status` 免费查看长期目录，`experience sync` 免费汇集历史记录。`experience maintain --call-model` 显式处理认证队列；历史 CLI 维护入口可显式处理；当前 Web 账号在普通任务封存后自动处理，遵守原配置的 `mode` / `auto_worker`。仅观察或关闭自动worker时不会在启动时发起认证。失效候选不执行，相同证据失败不会因重启反复计费。

长期目录在原管理库的 `experience` 下，`registry` 是同一库的认证活动视图，不再按新契约另建日常库。旧库按当前契约重认证保留原证据，重新取得当前模型见证和两次独立实际复用；不能只更换源码摘要并启用。支持的 v3/v4 质量材料以新副本迁移为 v5，保留原谓词与权限；旧任务和证书不原地重签；[旧IR及脚本适配](changes/management-legacy-adapters.md)为已知历史格式登记当前执行表示，独立认证后才能使用。其它未登记格式仍保留为历史项。[长期库与自动迁移](changes/managed-experience.md)、[此前真实结果](experiments/managed-experience-20261018.md)及[原离线重认证](changes/management-recertification.md)记录边界。

学习脚本只支持已见证的去重代表选择、批量复制和备份后恢复复制；精确核验目标、规则正文、实际来源范围与当前状态，不支持任意代码。已存在目标、规则或目录不匹配时交普通Harness，原高风险确认和预算仍有效。未送审即因版本更新归档的预备材料标记`superseded`，不作为付费在途或质量失败。

新增flow经验支持工具声明的有限条件组合、实际继续句柄控制的循环及多文档交错读取；每个活动根独立绑定，最多16个活动根、每根64次调用，仍受原任务96步/请求总上限约束。新分支逐个收集独立原生见证、冻结并独立认证，失败/未知条件回普通Harness；原v1/v2图可作已验证前缀，不能冒充新的模型决定。通用精确编辑/新文本准备请求的准确执行和收据检查接同一库；任意代码本身及未知业务判断不自动认证。[契约与验证范围](changes/control-flow-rsi.md)。[实测](experiments/control-flow-rsi-20261019.md)保留旧图失配、并行准备回退和备忘录时序未满足的反例；程序文件验收通过不代表所有自然语言时序都已验证。

历史单用户 CLI 真实库保持 `.local/rsi/daily-management-real-v3`；当前 Web 各账号的活动库与工作区副本均在前述账号目录内，原生会话与平台累计账本位于 `.local/web`。实验旧库、旧脚本、失败候选、原始轨迹和费用继续保留，勿清空 `.local`。发布流程为测试后创建面向 main 的 PR，由用户审阅合并；不自动合并或部署。

## 通用工具与完整阅读

工具选择继续由普通 DeepSeek Harness 完成，无需先学习 Motif。文件管理提供 `discover_tools`、`describe_tool`、`prepare_tool_call`、`execute_tool_call`、`inspect_tool_result`，使用真实 MCP catalog 和 schema；本机扩展写入私有 `.local/general-tools/providers.json` 或通过 `SSS_TOOL_PROVIDERS` 指向配置。格式与默认服务见 `scenarios/file-management/general-tools.json`。模型不能自行注册主机命令或扩大权限；需要账号的服务须在本机配置凭证引用，额外计费服务须有预算适配。

PDF 的 `read_file` 仍是明确标为不完整的首页预览。完整阅读使用 `open_document(mode=text)` 后持续调用实际返回的 `read_document_chunk` 句柄，再用 `document_coverage` 检查缺页和缺字符；`search_document` 仅搜索已实际返回的内容。扫描件使用 `mode=ocr`，图片或 PDF 任意物理页可用 `view_document_page` 直接交给当前 DeepSeek 的原生图像链路。文字层覆盖、OCR 覆盖和视觉观察分别记录，不能相互冒充。

PDF/OCR 需要本机提供 Poppler 的 `pdfinfo`、`pdftotext`、`pdftoppm` 及 Tesseract，默认 OCR 语言 `eng+chi_sim`。命令路径可用 `FM_PDFINFO`、`FM_PDFTOTEXT`、`FM_PDFTOPPM`、`FM_TESSERACT` 配置，`FM_OCR_LANGUAGES` 指定实际已安装语言；更改解析器或语言会使旧执行证明失效。基础 Python 库由 `npm run setup` 安装。通用编辑产生独立的新文件，精确匹配次数不符就拒绝；隔离代码复用已有 Docker 执行器，仅支持 TypeScript/JavaScript，需启动 Docker 和准备项目固定镜像。不会自动转为宿主代码执行。

默认跨场景目录还包含已有数据报告、论文检查和 PPT 服务。数据依赖见 `scenarios/data_analysis/requirements-report.txt`；PPT 服务须在 `scenarios/research_ppt` 安装并构建，其相关 Python 功能还需 PyMuPDF、python-pptx、reportlab。工具发现会返回真实依赖错误；目录列出工具不等于所有业务产物已独立验收。新产物在任务的 `general/` 输出中保留原始工具收据。

前端状态查询按配置合并和短时缓存，并与任务修改队列分开；此缓存仅用于显示，任务准入、权限、预算和证书仍实时核验。Files API 免费传输记录与真实模型请求分别计数；使用量未知的真实模型请求仍保留原费用上界，不能因免费上传记录误判为模型用量缺失。

## 私有备份

先正常退出本地服务，等待学习认证进程封存，再执行：

```sh
npm run management -- backup --output .local/backups/management.zip
npm run management -- verify-backup --archive .local/backups/management.zip
```

备份固定覆盖 `.local/rsi`、`.local/management-copies`、`.local/web`、`.local/runs`、`.local/file-management`、`testpdf/file-management-experiment`、`.local/file-jobs`、`.local/operation-jobs`、`.local/management-acceptance` 和 `.local/management-imports`。其中包含连续 RSI 库/配置/证书/原轨迹、任务副本、前端历史/账本、SDK 原始运行、旧文件管理实验材料与恢复数据。其它开发临时目录、工作区外原件、代码和未列出的材料需另行备份，不承诺覆盖整台电脑。

通用 MCP 的私有 `.local/general-tools/providers.json` 不在上述固定数据备份范围；换机器时按本地服务、路径和凭证引用重新登记，不自动迁移主机执行权或服务凭证。通用工具在任务目录中的请求、收据和产物随原任务数据保留。

相同字节只保存一次；恢复文件使用独立副本，不用相互影响的硬链接。逐文件 SHA、空目录、原费用及预留、原源码摘要一同冻结，备份前后核对，防止复制期间发生变化。归档权限为本机私有 0600，不上传 Git。生成的 `dsh/profiles`、`web-dsh/profiles` 内 `node_modules` 不打包，恢复后重新安装；用户资料中的同名目录不排除。API 凭证及 DSH 凭证存储不属于迁移授权，恢复后沿用本机独立配置。

输出已有文件、符号链接、活动服务/worker、数据改变或损坏包会拒绝。失败回执与未完成归档保留，不删除原件。备份是本地私有归档，不能把它当作脱敏公开经验包。

## 原路径恢复

```sh
npm run management -- restore --archive .local/backups/management.zip
```

只恢复原项目绝对路径下的缺失数据根；已有数据若逐字节相同则幂等跳过，任何差异都拒绝覆盖。恢复前后校验所有文件和目录，原证书、轨迹、任务与费用字节不改写。中断恢复仍要求原源码、权限及文件版本；升级后不会强行续跑失效任务。

## 换路径冷迁移

在新检出的项目目录准备好代码和依赖后，从原目录执行：

```sh
npm run management -- migrate --archive .local/backups/management.zip --destination /absolute/path/to/new-checkout
```

目标须没有已有活动管理数据。原始备份完整复制到目标的私有 `management-imports`；用户文件提取为可打开/重新上传的副本。历史经验、证书、任务和前端历史留在原始归档中供核验，不能将旧绝对路径、旧确认或运行中任务自动转为新授权。新日常档案通过后续真实任务和独立认证形成可执行经验；原经验不删除、不重签、不自动激活。此模式不承诺原会话在新路径中无缝续跑；需要原任务时按对应源码版本在原路径恢复。

原系列已用费用、请求、尝试数及未结算上界随导入回执继承；原学习费用/预留和原生服务累计计数同时保留。重复导入同一包幂等；不同包或已有数据不能通过反复导入重置预算。导入回执或归档元数据改变会阻止后续预算使用。

## 日常目标验收

以下明确表述可在第一步文件操作前冻结完整验收条件：

- `按文件类型复制整理到 organized，保留全部原件和内容，并创建 organized/empty 空目录。完成后核验并提交报告。`
- `把 note.txt 移动到 arranged/note.txt，保留其他文件不变。完成后核验并提交报告。`
- `把 note.txt 重命名为 renamed.txt。完成后核验并提交报告。`
- `把 note.txt 复制到 intermediate.txt，完整读取该副本，再重命名为 final.txt，保留原件。完成后核验并提交报告。`
- `通读全部文本文件，给出完整读取覆盖清单，不修改任何文件。完成后核验并提交报告。`

按类型整理使用扩展名规则：PDF/Word→documents，Excel/CSV→tables，图像→images，TXT/Markdown/JSON→notes，其余→others；保留原相对路径。验收检查原文件覆盖、实际输出字节、预期目录/空目录、移动后的源路径和无额外影响。读取要求所选文本完整可读且未截断，不能用“调用过读取工具”代替完整阅读。

当前 `sss-management-quality-v6` 保留 v5 的完整目录、无多余副本、原始身份及中间读取来源检查，并增加全文/OCR 覆盖与视觉来源重放；字节相同也不能任意交换来源。错误路径在写入前拒绝，最终提交再独立核验。未完整解析的表述（例如“按重要性整理”）、冲突目标或未支持的语义目标显示“目标待复核”；Agent 仍可按原权限执行并报告实际结果，不把内部效果校验当作全部业务目标已经实现。新的谓词标准独立认证，旧失败和旧证书不重签。任意自然语言业务目标仍未全面自动验收。详细变化见[严格交付契约](changes/management-quality-v5.md)与[v6 接口](changes/general-agent-tools.md)。

文件管理上传的图片也作为文件保留原始字节和名称，参加同一份任务清单。整理验收核对文件字节和路径；图片视觉理解、OCR、文档排版或表格重算须另行明确需求，不能把复制核验写成这些内容已经审阅。重启后点击“继续原任务”，读取原文件和操作回执，继续剩余工作。

覆盖、不可恢复删除和外部目录继续逐计划确认。副本内普通整理不额外增加授权步骤。每任务5美元/96步和请求/4000输出/2修复，系列1000、共享学习25以及更低既有限额都保留；净收益持续记录，不作为开启学习的门槛。
