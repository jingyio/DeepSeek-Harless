# GeneLoop 三场景文件质量验收：2026-10-16

## 结论与范围

**未通过完整质量验收。** 在与正式运行 `bfc86c1d08d1ed7d213faebf3000d7525bfdb9db` 同版本的隔离网页，通过 Chromium 141、真实登录账号、原生文件上传/发送/SSE/下载，完成 18 组测试、36 侧输出。覆盖 DOCX、CSV、文本层 PDF、JSON、TXT，另测混合附件与结构化参考文献 JSON。实际点击下载 31 个文件，31/31 字节数与 SHA256 均匹配后台回执。网页 JavaScript 异常为 0。

每侧生成结束前均记录到文字增量（44–232 个不同的非零长度，含工作过程和回复），不是只在完成后返回全文。该观察不代表逐 token 帧率、任意网络/浏览器或公网代理缓冲都已通过。

这是合成材料验收，使用 Flash / Off，非 Pro/On；不是科研质量认证、广泛支持所有文件的证明或成本收益实验。Word 指 DOCX，PDF 有文本层；未覆盖旧 DOC、扫描 OCR、复杂公式/表格、损坏/加密/超大文件、真实长论文、PPTX 反向编辑。数据场景仅说明文件而无数值表时，明确要求补数据是正确行为，不计作伪造报告的失败。

公网账号及 CDN 登录下载未在本轮重测。浏览器连接同代码隔离 stage，测试代理转发既有测试账号和允许的 Origin；没有绕过产品鉴权、伪造模型、修改正式应用或重置预算。

## 逐项结果

| 用例 | Baseline 文件数 | Motif 文件数 | 内容与交付结论 |
|---|---:|---:|---|
| `data-combined` | 7 | 7 | 两侧各 7 文件，统计数值正确；指标漏项，未通过完整质量验收。 |
| `ppt-pdf` | 0 | 8 | Baseline 无交付；Motif 生成可编辑 PPTX/PDF 和 6 张预览，但 3 页要求变为 6 页。 |
| `paper-txt` | 0 | 0 | 两侧发现样本数矛盾及因果越界；普通校对没有导出。 |
| `ppt-docx` | 0 | 0 | 附件提取可用，但不能作为正式 PPT 来源；两侧无交付。 |
| `ppt-csv` | 0 | 0 | 附件提取可用，但不能作为正式 PPT 来源；两侧无交付。 |
| `ppt-json` | 0 | 0 | 附件提取可用，但不能作为正式 PPT 来源；两侧无交付。 |
| `ppt-txt` | 0 | 0 | 附件提取可用，但不能作为正式 PPT 来源；两侧无交付。 |
| `data-csv` | 0 | 7 | Baseline 布局失败；Motif 7 文件，但单位/数据性质表达不一致。 |
| `data-docx` | 0 | 0 | Word 标记读取正确；没有数值表，诚实要求补数据（预期边界）。 |
| `data-pdf` | 0 | 0 | PDF 标记读取正确；没有数值表，诚实要求补数据（预期边界）。 |
| `data-json` | 0 | 0 | 设计信息可读；没有数值表，未伪造分析（预期边界）。 |
| `data-txt` | 0 | 0 | 需求可读；没有数值表，未伪造分析（预期边界）。 |
| `paper-docx` | 0 | 0 | 通用提取成功，专用 pin 失败；没有导出。 |
| `paper-pdf` | 0 | 0 | 文字层读取和标记正确；没有导出校对报告。 |
| `paper-csv` | 0 | 0 | 通用提取可用，专用 pin 失败；没有导出。 |
| `paper-json` | 0 | 0 | 普通研究 JSON 能提取，专用 pin 失败；没有导出。 |
| `paper-structured` | 1 | 1 | 两侧各导出 1 份 Markdown，结构与待核验状态保留；不是文献真实性认证。 |
| `ppt-combined` | 0 | 0 | 五份内容可提取并识别 TXT 错误；页数冲突，两侧无交付。 |

## 已确认问题及归因

### Q01 · 高 · PPT 页数要求没有绑定到实际任务

要求含封面共 3 页；PDF 输入的 Baseline 无交付，Motif 生成 6 页。五种混合附件的两侧均因同一冲突停止。

网页接入问题。harless_task_scope.ts 的 slides 使用 options.slides ?? 6，原生聊天提交没有把文字中的页数变为该参数。原分支 CLI 可显式传 --slides，生成器本就严格检查页数。原生成器没有把 3 页主动改成 6 页。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/src/adapters/harless_task_scope.ts#L125)。下一步：在发送前明确绑定本轮页数，任务上下文与用户要求一致；复测 3、5、8 页均按要求交付，不降低页数验证。

### Q02 · 高 · PPT 非 PDF/PPTX 输入无法独立生成

Word、CSV、普通 JSON、TXT 单独上传的八侧都没有产物。附件已上传且有正文提取，但工具 list_inputs 为空、output_enabled 为 false，回复多次误导为需要重新上传或开启权限。

原场景已有来源格式边界，网页接入的解释和能力范围不一致。原分支 README/解析器只支持 PDF/PPTX；当前任务绑定仍筛掉其余类型。不能据此声称合并丢失了原本已存在的 Word→PPT 能力。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/src/adapters/harless_task_scope.ts#L125)。下一步：为多格式资料实现带版本和来源追溯的正式生成入口；同时准确说明格式限制，避免无效重传和权限提示。

### Q03 · 高 · 数据报告没有完整满足指定指标

五文件混合输入生成的两份 PDF，其关键统计表都缺 R²；Baseline 的正文也没有 R²，尽管聊天里给出了该值。Motif 正文有 R²。CSV 单文件的 Motif 正文有 R²，但表格也没有。

内容选择与需求验收缺口。原分支和当前工作流都支持 r_squared；已观察到的组装输入只选择了五项指标。差异仅包含标签等兼容改动，没有删除 R² 能力。未做旧分支模型同题随机对照，不能把模型漏项归因于融合或证明旧提示必定通过。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/benchmarks/research_report_agent_v3/workflow_tools.py#L35)。下一步：交付前逐项检查用户要求，表格包含 n、斜率、95% CI、双侧 p、R²，聊天文字不能替代文件内漏项。

### Q04 · 高 · CSV 单文件丢失已说明的单位和合成属性

用户明示天、MPa、独立样本和合成数据。Motif PDF 方法段承认单位，结果及结论却写“未提供单位”；图轴未标 MPa，数据属性也没有完整保留用户声明。

语义信息与结构化数据入口脱节。report_intake 只把一个 JSON 作为 study，否则使用空对象；原 intake 也不从自然语言推断字段。因此既有结构化入口限制在聊天整合后暴露，不能把明确声明的缺失解释为用户没有提供。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/scenarios/data_analysis/report_intake.py#L147)。下一步：将用户明确说明的单位、设计和数据性质绑定并保留来源；未独立核验可以注明，不应抹去用户声明。

### Q05 · 高 · 数据报告布局失败后恢复不充分

CSV 单文件 Baseline 两次稿件均被 no_content_overflow 拒绝，无可下载文件。标题右边界 564.0 pt 超出内容边界 551.28 pt；不是纸张实际裁切。回复又要求用户允许最多 3 页，但原请求和任务参数已允许 3 页。

这一排版问题不是当前融合独有。保持同一份两版正文、图表、WenQuanYi 字体，在原分支 v2.2 与当前 v2.4 渲染器各重放，两者分别同为 3/2 页且均触发同一边界检查。重放 0 模型请求。初次未控制字体的诊断不用于此归因。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/benchmarks/research_report_agent_v2/document_engine.py#L196)。下一步：修正长标题换行与内容框测量，保留布局守卫；模型在既有三页权限内修复，不重复请求已授予的页数。

### Q06 · 高 · 论文场景的专用读取工具与附件层不一致

Word、CSV、JSON 已被通用层提取；paper_checks.pin_document 仍按后缀拒绝，产生重复工具失败。模型只能借助已注入的提取文本做有限检查。Word 的唯一标记能被读到，不等于专用工具正常。

网页新适配层的能力缺口。原 scenarios/paper-submission 代码与分支相同，网页走新增 paper_proofreading；后者允许 PDF/TeX/文本而没有 DOCX/CSV/JSON。原分支也未证明通用 Word 校对已经具备。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/scenarios/paper_proofreading/server.py#L83)。下一步：专用工具复用带版本核验的多格式文本提取，清楚区分文字校对和版式/图片核验；格式不支持只报告一次可执行原因。

### Q07 · 中 · 普通校对报告不能下载

PDF/TXT 普通校对能给出文字建议，TXT 中 40−2=39 和因果过度表述被发现，但没有导出文件。只有指定结构的参考文献 JSON 成功导出两份 Markdown；文件保留“真实性待核验”，没有假装核验虚构文献。

Web 导出接口范围有限。export_revision_report 仅处理 report.references 的结构修订，不能导出普通正文校对。原分支只读诊断/结构修订也没有覆盖任意正文报告；属于未接齐的产品能力，而非证明原文件生成器损坏。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/scenarios/paper_proofreading/revision_session.ts#L76)。下一步：为正文校对提供独立报告导出；有内容、有引用和修改建议再生成文件，不导出空参考文献报告冒充完成。

### Q08 · 中 · 回复语言与错误解释不稳定

多组中文请求收到英文开场甚至整段英文；PPT 不支持的来源被解释为授权问题；论文 Word 校对把“保留原数据并披露分析排除”标为冲突，属于不必要的疑点。

提示、工具反馈和模型判断问题；本轮没有独立提示消融，不能给出融合因果结论。

定位：[代码](https://github.com/jingyio/DeepSeek-Harless/blob/bfc86c1d08d1ed7d213faebf3000d7525bfdb9db/scenarios/paper_proofreading/prompt.md)。下一步：保持用户语言，用准确的工具失败类别反馈；避免把合理的数据保留规则错误标成矛盾。

## 原分支比较与数字复算

已 `git fetch origin`，固定对应分支提交：

- `origin/feature/research-ppt-agent`：`73751854d65465d2ceb878a525002431d13cdd05`。
- `origin/feature/data-analysis-agent`：`0072779f0cfcc6383ac3cf0421305bdc9591d3ea`。
- `origin/feature/paper-submission`：`eb07efb0b621dc1dedde51b70a300880b00ec034`。

PPT 的提示词与内容渲染文件没有因本次集成被替换；差异主要是私有任务范围、恢复、渲染验收目录及 CPU 渲染配置。原 CLI 支持显式页数，Web 自然语言入口未绑定页数，这是可定位的接入问题。数据 v31 目录与原分支无差异；v3 主要差异是输入长度接口、置信度占位符约束、指标标签/失败详情，v2 包含字体兼容。论文原 `scenarios/paper-submission` 目录与分支无差异，Web 使用新增 `paper_proofreading` 接口，不是原工具全集。

排版重放固定已失败的两份 document payload、同一图表与 WQY 字体（SHA256 `2420e8078af796b19a3f6ef13de527a1a91c1e7171eea115926c614ced1009b3`）。原 v2.2 和当前 v2.4 分别都得到 3 页/2 页、同一 no_content_overflow 失败；长标题 x=564.0 pt 超出内容边界约 12.72 pt。原分支使用其既有已注册字体入口，当前使用配置字体，源函数未改。保留初次 STSong 环境诊断，但不据其作等条件归因。此重放只比较渲染器，不等于旧版端到端模型重跑。

独立 SciPy 复算：40 行，排除 SIM-009/SIM-028，n=38；斜率 0.843814528 MPa/天；95% CI [0.764045872, 0.923583184]；双侧 p=4.235211557×10⁻²²；R²=0.927457749。已生成报告中的已展示数值与复算一致；不能以此掩盖 R² 漏项或单位表述矛盾。

3 份数据 PDF 的全部 6 页、PPT PDF 全部 6 页、独立图表和 PPTX 可编辑文本/来源备注均已检查。PPTX 6 页均有原生可编辑文本，约 11–13 个文本形状/页；没有据此认证所有形状或动画均可编辑。结构化 Markdown 两份相同，保留虚构测试条目的原内容和“待进一步核验”，字段检查 false 未被报告为通过。

更正：初次缩略视图曾怀疑混合输入 Motif 表格覆盖页脚，完整页面复核未确认该问题，已撤回，不列为缺陷。成功 PDF 排版基本可读，实际排版拒绝发生在另一个 CSV-only Baseline。

## 配置、成本、证据与收尾

- 运行模型为 `deepseek-flash`，UI 显示 DeepSeek V4.1 Flash，reasoning Off。Baseline/Motif 使用同来源、同请求和各自独立任务；Paper 为既有 Shadow 模式。每对总任务预算 $0.23、每侧 $0.115；累计请求/费用上限与额外输出上限均 null。没有重试已结束用例以绕过预算。
- 18 组共 182 个真实模型请求；输入 1,656,925 token（缓存命中 1,530,877、未命中 126,048），输出 54,004；代理估费 $0.111804462，实际服务商账单未知。记录 22 次已验证模型跳过、31 次工具错误；质量未齐平，不能宣称节省成本或 Motif 普遍更好。
- 原累计账本由 897 / $0.638632706 增至 1,079 / $0.750437168，未清零；关闭 stage 前后均 1,079 请求。原预算和正式 owner/gateway 进程保持。36 个本轮任务全部终态；历史 stage 总计 75 completed + 1 cancelled，36 组对照含历史失败，均终态后关闭 3 个临时服务进程，文件删除 0。
- 私有原始证据：`.local/quality-web-20261016/`（每组 prompt、snapshot、真实 SSE 增量、截图、下载文件），输入 `.local/stream-attachment-acceptance-fixtures/`；分支比较 `.local/quality-branch-comparison/`；远端两种渲染诊断 `quality-render-replay-20261016` 与 `quality-render-replay-wqy-20261016`。源/输入/下载哈希随本地交付包 manifest 保存。
- 浏览器入口脚本 `.local/quality-matrix.mjs`。Windows 原生自动化超时；旧 Chromium 110 不兼容现代客户端，升级隔离测试浏览器至 141 后运行。早期 upload 监听及新会话等待问题在发送模型前修正，失败证据保留，非产品缺陷。没有删除负面模型结果或用固定回复替代。
- 本轮是网页验收和只读归因，生产代码未改、未部署。仅增加实验说明和主线交接；未新增全量 CI 或付费重复测试。原模型提示/工具配置在 task effective-config 和原 journal 保留；没有声称所有部署字段已在公开摘要展开。
- 下一步先修 Q01/Q06 的入口契约，再修 Q03/Q04 的需求保留与交付校验，以及 Q05 标题换行和恢复；Q02/Q07 为需明确实现的能力扩展。修复后复测同一固定资料与要求，再加真实长文档验收。
