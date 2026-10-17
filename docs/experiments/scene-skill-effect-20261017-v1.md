# 三场景 Skill 效果实测（先导实验；PPT 对照已排除）

## 2026-10-18 方法更正

用户明确要求由 GeneLoop 自己使用原技能和 ppt-master 制作，测试者不得参与 PPT 制作。下文是先导阶段历史记录，不是当前有效 PPT 对照结论。其后曾用独立 DSH SDK 继续候选制作，并向模型反馈具体修订意见，测试者还亲自改了第 8 页公式排版；这不符合用户要求。**全部独立 SDK PPT 版本（包括初稿、模型修订稿、人工改稿）均排除出 GeneLoop 原样对照，不能用其效果推荐替换技能。** 原始文件及负面证据保留，不删除或追改。

先导实验最终共 313 次真实请求，代理估费 $2.507185648：其中原 Web 十路 122 次、$0.924773344；独立 SDK PPT 共 191 次、$1.582412304。不是服务商已对账实付费用。后续有效实验使用新 ID `geneloop-ppt-skill-ab-20261018`，真实 GeneLoop 网关和 `/ppt` 场景，新账号、新会话、同一材料/题面/Pro Off，禁止测试者补写、修订或向制作过程反馈评审意见。Paper/Data 原始模型产物没有人工修改，其结果仍按下文限制解释。

---

以下为先导阶段记录，阶段费用和“待确认”状态已被上述更正取代。

## 问题与当前结论

检验“给已有场景增加专门技能，是否改善真实交付质量”。截至本阶段，Paper/Data 两组对照和 PPT 当前流程已完成；完整 ppt-master 只完成准备与设计建议，未生成候选页面。**不能宣称三组全部完成或 ppt-master 已升级 PPT 效果。** 线上默认技能、模型和渲染器未修改。

- Paper：主比较版增加结构化证据与严重度，但新增严重数学误报，当前不支持直接替换默认流程。
- Data：两版均通过独立数值复算；技能版解释更细，版式基本不变，主比较代理估费约翻倍。只支持本题上的局部解释改善。
- PPT：原流程交付可编辑 10 页、备注和真实 PDF；存在封面断行、ASCII 公式等视觉问题。候选须继续实际生成与验收后再判断。

## 设计、材料与技能

这是公开论文与仓库合成数据上的真实模型测试，每场景一个题目，非盲评技术/视觉审查，没有训练或独立认证集，也没有独立用户盲评。评审先看交付与内容硬要求，再看费用；不以请求减少代替质量。

| 场景 | 固定题目与材料 | 候选变化 |
|---|---|---|
| PPT | 《Attention Is All You Need》v7，严格 10 页、16:9、中文研究生组会、原文图表至少两处、编辑性与备注 | 完整 ppt-master 6.6.0，原生 DSH + 隔离 bash；同时改变流程和导出器，属于系统级比较 |
| Paper | 同一论文，标准深度只读审阅，3–5 页 PDF + Markdown | paper-review-audit 2.6.0 的正式说明和适用参考注入现有 `/paper` |
| Data | `examples/web-data-report-demo/` 中固定 CSV、metadata 和题面；含截距 OLS、两图、不超过 3 页 | K-Dense statistical-analysis 2.0 正式说明与 assumptions/reporting/test-selection 参考注入现有 `/data` |

Paper/Data 是技能指导集成实验，**不是完整技能机械检查器、脚本和指定依赖栈的安装认证**。未修改场景工具或源文件。Data 技能建议的 Python 3.12+ 栈未采用，沿用实际服务器环境。PPT 候选完整包复制到独立沙箱，attribution_guard 已通过；来源转换、初始化、模板索引读取完成。

Web 每项任务自带 Baseline/Motif 两路；主比较固定用 Baseline 路径，Motif 仅作辅助观察，不能算匹配条件的独立重复。提示长度、缓存条件和自带优化不同；不据此推断一般性成本收益。

来源：

- [论文 v7](https://arxiv.org/abs/1706.03762v7)，PDF SHA256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`。
- CSV SHA256 `f75296d587ff117ab9520a1d26abc1d6df47b48e7270f756d8ffd4da67bae78a`；metadata `4e411aa0498e1fea3139894246839d6a16adbe595901929e790740d6e777e627`。
- ppt-master SKILL SHA256 `6b568cfa5b17229f264c3366c5e07844df5749b243c31af15e12424d75c30185`。
- paper-review-audit SKILL SHA256 `07c6229ce29b09d113c74dcf1da29705803e50d282fc5c7110fee6c5dd4df525`。
- [statistical-analysis 固定提交](https://github.com/K-Dense-AI/scientific-agent-skills/blob/a1043ef544e3a100c28e70a736b6cf32554d0677/skills/statistical-analysis/SKILL.md)，SHA256 `e112848726b3713267cac65e4e2c15491a0a26ee1ed628db01195f7e43f97997`。软件参考：Kassis et al. (2026), [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://arxiv.org/abs/2609.00065)。

## 运行配置与复现

- 代码基线 `5a27208ec9e4051eedb7ecae6a297246a6c9a1f7`，本地实验分支 `codex/scene-skill-effect-tests`；没有产品代码改动。
- 真实服务器模型 `deepseek-v4-pro`，官方 provider，`reasoning_effort=off`；请求次数/累计费用/单次输出限制均为 null，沿用生产原累计账本，未清零。所有调用属于已授权实验。
- Node 22.23.3，DSH 与 dsh-llm 0.1.5-rc.3，Python SDK 0.1.5rc1；Python 3.10.21，Linux/glibc2.28。NumPy 2.2.6、pandas 2.3.3、SciPy 1.15.3、statsmodels 0.14.5。实际值见私有 `independent-oracle.json`。
- Web 使用独立 QA 账号、新会话、原生模型选择、二进制文件上传、`session/prompt` 和 comparison 下载入口。旧测试登录失败两次后改用新 QA 账号，失败发生在模型任务启动前，未产生该任务模型费；不改生产用户数据。
- PPT 候选通过公开 SDK `create_harness` 和既有 GeneLoopShell，bubblewrap 只读输入与运行库、可写实验输出，不挂载凭证和其他用户目录。代理请求仍转入既有费用控制端点，按实验 session 计入原账本；没有创建替代累计账本。
- 私有实验目录 `.local/skill-effect-20261017/`：`baseline.py`、`ppt_candidate.py`、`oracle.py`；每组 `prompt.txt`、`submission.json`、`latest.json`、各侧 `stats.json` 与原始成品。PPT 准备有 prompt/events/result/cost 文件。文件和技能摘要见 `input-skill-hashes.json`，评审标准先记录于 `rubric.json`。
- 最短复现路径：在服务器同基线环境准备独立 QA 账号和同一输入后，运行 `python .local/skill-effect-20261017/baseline.py ppt paper data`，再运行 `python .local/skill-effect-20261017/baseline.py --skill paper data`。这会再次真实付费，使用新实验目录/ID，不覆盖本次输出。PPT 先运行 `ppt_candidate.py prepare`；只有收到实际用户确认/委托后才能以 `continue` 恢复。
- 原始快照保留工具调用顺序、来源及库摘要。完整 schema 字节未在本实验单独导出，以固定代码及锁文件为恢复依据，不声称采集完整。未单独计时人工审阅与环境准备，不将其算成零。

## 质量核验与反例

### PPT 当前流程

主路径 10 页、16:9、10 份备注；OOXML 检查有 124 个可编辑形状、2 个 native 表格和 2 个原文图片。PDF 真实渲染，逐页缩略图检查；结构数不代表所有机制元素都满足可编辑性。BLEU 28.4/41.8、成本数量级与来源对应，备注识别 41.8/41.0 原文矛盾。

封面长标题末字独占一行，公式采用 ASCII sqrt/下划线/幂符号，部分文本页留白较多。主路径 7 次 render/repair 工具错误，辅助路径 3 次，最终交付成功；错误与中间版本保留，不能描述成一次成功。

### Paper

主路径两版均 3 页，候选辅助路径 4 页。两版均找到 EN-FR BLEU 41.8 与 §6.1 的 41.0 不一致。但原文单独不能确定真实测量值，直接认定应改为 41.8 过度确定。

当前流程把 Table 2 跨 EN-DE/EN-FR 居中的 Transformer FLOPs 读成 EN-FR 缺值。独立查看 PDF 第 8 页可见跨列共享单元格，不应将文本抽取缺位升级为原稿缺陷。

候选主路径修复了这项理解，却新增 **FAIR-001 Major 误报**：认为 1/5、1/6 并非 1/4，故“less than 1/4”无支持。实际 `2.3e19 / 1.4e20 = 0.1642857 < 0.25`，不等式成立。候选把摘要标为第 2 页（实际第 1 页），还在未视觉核验时推断图/公式格式及表格排版错误。结构更完整不抵消内容错误，因此不能通过“减少虚假缺陷”的质量门。

候选 Motif 路径正确解释了小于 1/4，且将提取错位标为待视觉复核；同时仍有过度断言分数笔误等问题。这是重要负/正混合证据，不能挑辅助成功案例替代预定主比较。两条候选路径各有 1 次 report export 错误后修复。

### Data

两版主路径均 2 页、2 图、完整案例 n=38，无插补；排除 SIM-009、SIM-028。独立 NumPy 最小二乘和闭式协方差（不调用报告工具的拟合结果）核验：

- 斜率 `0.8438145279764133`，截距 `11.307453278801809`。
- 95% CI `[0.7640458716556244, 0.9235831842972022]`，双侧 p `4.235211557068047e-22`，R² `0.9274577485771388`。
- 残差 Shapiro W `0.9792087346907975`、p `0.6894420769010781`。

两版主报告在输出精度内一致，披露纯合成、完整案例、关联非因果。候选更清楚地区分均值置信带与预测区间，说明缺失机制和统计/实际意义；原版也已有假设不能仅凭未拒绝证明的提示，不能将已有功能归功于新技能。

两版沿用同一报告渲染器，视觉无显著升级；英语图标签、表中 CI 置信水平需正文补充等问题仍在。统计上未发现本题硬错误，不代表复杂统计任务通过。两版主路径均零工具错误。

## 成本、耗时与人工介入

费用为代理估费，`actual_paid_usd=null`，未对账服务商账单。时间为 lane started/finished 差，不含提交前和队列等待，已包含该路径内部工具及重试。准备、审阅、字体/依赖配置和下载另计但未独立计时。

| 实验/路径 | 请求 | 工具错误 | 缓存命中/未命中输入 | 输出 token | 秒 | USD 估费 |
|---|---:|---:|---:|---:|---:|---:|
| baseline-ppt/baseline | 17 | 7 | 536064/51679 | 11526 | 159.2 | 0.137446 |
| baseline-ppt/motif | 11 | 3 | 273280/22631 | 7656 | 108.6 | 0.072215 |
| baseline-paper/baseline | 8 | 0 | 182784/44494 | 9813 | 266.6 | 0.105634 |
| baseline-paper/motif | 7 | 0 | 170880/15082 | 8086 | 161.6 | 0.059448 |
| candidate-paper/baseline | 11 | 1 | 405248/49058 | 10446 | 264.0 | 0.123954 |
| candidate-paper/motif | 12 | 1 | 503936/13468 | 16982 | 287.3 | 0.107200 |
| baseline-data/baseline | 17 | 0 | 312960/23614 | 4052 | 69.4 | 0.060987 |
| baseline-data/motif | 9 | 0 | 140800/14720 | 3757 | 55.9 | 0.040503 |
| candidate-data/baseline | 19 | 0 | 818688/50585 | 5143 | 89.8 | 0.123161 |
| candidate-data/motif | 11 | 0 | 430976/43800 | 4406 | 67.3 | 0.094227 |
| candidate-ppt-prepare-only/native | 18 | 未计数 | 407296/54512 | 4002 | 84.2 | 0.105725 |


当前共 140 次真实请求、代理估费 **$1.030498128**，包括十路 Web 运行及 PPT 准备。PPT 候选未完成，不能用准备费用与成品费用比较。主比较 Paper 估费 $0.1056→$0.1240，Data $0.0610→$0.1232。不同缓存条件、提示长度和单次波动限制成本归因。

Web 提交至下载完成（含同账号队列等待）分别为：PPT 原版 172.0s、Paper 原版 431.7s、Data 原版 497.0s、Paper 候选 682.9s、Data 候选 767.0s。多个提交有重叠等待，不能求和当总墙钟时间。

模型产物未人工重写。人工负责准备固定题面、技能参考、实验沙箱与独立复算/视觉核验。PPT 全包首次复制不完整后重传并重新检查，首次复算版本查询报错后修正，报告本地预览脚本编码/文件选择问题已纠正；这些是实验基础设施修复，不记成模型质量成功。PPT 原生运行读取模板索引时存在低层路径调用规范偏差，不能宣称完整技能协议已全部通过。

## 成品、未完成项与下一步

本地可审阅交付位于 `.local/deliverables/scene-skill-effect-20261017/index.html`，包括实际渲染预览、两版原始 PDF/MD、PPTX、辅助 Motif 产物、计量摘要、独立复算与逐文件 SHA256。原始日志及账号凭证不入 Git；输入为公开论文和合成数据。

PPT 候选因技能明确要求设计确认而暂停：`ppt-master/workflows/generate-pptx.md` Step 4 写明 **“the always-on user gate unless explicitly delegated”**。已向用户展示具体推荐（10 页、16:9、中文白底学术风、原文图表、可编辑机制图与备注）并询问是否委托设计；尚未收到回答，不能将等待或沉默当确认。没有正在运行的 PPT 模型进程；保留原会话以便确认后继续，费用记录未清零。

后续：收到设计委托后，按实际技能完成三个方向及选择、设计规范、逐页 SVG、notes/finalize/export 串行流程、真实渲染、逐页视觉核验，再补齐最终比较。Paper 优先补不等式复算和 PDF 图表核验后再测试；Data 先尝试提炼短检查清单，以验证能否保留解释收益而减少长上下文成本。上述均未实施，不描述为已调优。

本阶段只新增实验文档；产品无需部署或回滚。PPT 全部完成前不将本记录写成最终验收，也未创建/合并本实验 PR。
