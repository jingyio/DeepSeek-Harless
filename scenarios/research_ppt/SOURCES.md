# 科研 PPT 场景的外部参考与复用边界

核对日期：2026-10-10。本文记录已下载、已阅读的参考，不代表已经集成或在服务器验证。参考副本位于忽略的 `.local/research-ppt/upstream-references/`，下载 ref 和 archive SHA256 位于该目录的 `sources.json`。不向用户文件或上游仓库写入。

## 随场景分发的科研设计 Skill

- 新增 [`skills/research-design/SKILL.md`](skills/research-design/SKILL.md)，版本 `research-design-v1`。它独立编写科研叙事、证据条件、信息层级、结构选择与真实预览修正规范；输入 1–8 份 PDF/PPTX、1–30 页仍由任务决定，没有固定论文数、页序或实验主题。
- 吸收下述 MIT harness-anything 固定版本的 JSON 数据驱动、统一预设、图片等比放置和真实 PPTX/PDF/逐页预览思路，没有复制脚本、学校背景或标识。源文件 SHA256、原版权和完整 MIT 文本记录在 [`provenance.json`](skills/research-design/provenance.json)。没有重新读取、复制或改编已排除的专有 Skill 或本机 bundled 专用代码。
- Skill 对应 `prompt.md` 中的设计要求，使用受限 `takeaway` 和 `process` 结构，由实际渲染器提供可编辑能力；仅添加提示不能等同于接口已支持，运行时契约与服务器验收必须同步。入口须真正加载固定 Skill 文本，并在每次实验快照记录相对路径、版本和实际 SHA256；不是要求 Agent 用受禁的文件工具自行读取它。
- 当前新增属于工程设计能力，不能称为学得 Motif 或 RSI 收益。是否使 PPT 更可读、减少修订或降低成本，要以新实验 ID、相同质量门槛和真实成品对照记录；旧基础模板实验保持原结果。

## harness-anything

- 项目：<https://github.com/yb2460/harness-anything>
- 固定来源：[`e1924f8499ad6aaa11c579d5492205cfaa89c5d6`](https://github.com/yb2460/harness-anything/tree/e1924f8499ad6aaa11c579d5492205cfaa89c5d6)
- 许可：[MIT](https://github.com/yb2460/harness-anything/blob/e1924f8499ad6aaa11c579d5492205cfaa89c5d6/LICENSE)，Copyright (c) 2026 cli-anything-wps contributors。复制或实质改编代码时须保留该版权与 MIT 许可文本；示例背景、校徽等资产不能仅凭代码许可推定其品牌使用权。
- 已读 skill：[`cli_anything/wps/skills/SKILL.md`](https://github.com/yb2460/harness-anything/blob/e1924f8499ad6aaa11c579d5492205cfaa89c5d6/cli_anything/wps/skills/SKILL.md)。值得借鉴的是数据驱动页面、统一样式预设、PPTX/PDF 一致性核验与交付检查。固定招生页序、四字标题等规则不适用于全部科研汇报，不作为本场景的强制模板。
- 已读引擎：[`WPS/ppt-engine/README.md`](https://github.com/yb2460/harness-anything/blob/e1924f8499ad6aaa11c579d5492205cfaa89c5d6/WPS/ppt-engine/README.md)。JSON 元素路由、图片等比放置可参考；其执行后端是 Windows 的 `KWPP.Application` COM，不能直接作为 Linux 服务器实现。
- 优先可借鉴脚本：[`WPS/ppt-engine/pptengine/verify.py`](https://github.com/yb2460/harness-anything/blob/e1924f8499ad6aaa11c579d5492205cfaa89c5d6/WPS/ppt-engine/pptengine/verify.py)。读取真实渲染 PDF 的文字 span bbox，与页面边界比较；生成逐页 PNG 供目检。该检查本身不能证明文字未被文本框裁剪、没有元素遮挡或内容正确。上游缺少 PyMuPDF 时会跳过，本场景交付验收必须明确报告检查未完成，不能当作通过。
- 跨平台参考：[`illustrator-harness/agent-harness/POWERPOINT.md`](https://github.com/yb2460/harness-anything/blob/e1924f8499ad6aaa11c579d5492205cfaa89c5d6/illustrator-harness/agent-harness/POWERPOINT.md) 记录 `LibreOffice Impress → PDF → pdftoppm` 预览路线，以及 PPTX 的 slide/master/layout/theme 分工。不能将整个仓库概括为只支持 WPS COM。

## pptx-automizer

- 项目：<https://github.com/singerla/pptx-automizer>
- 固定来源：[`fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367`](https://github.com/singerla/pptx-automizer/tree/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367)，该 ref 的 `package.json` 版本为 `0.9.3`。
- 许可：[MIT](https://github.com/singerla/pptx-automizer/blob/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367/LICENSE)，Copyright (c) 2021 Thomas Singer。
- 平台与接口：Node.js >=20，TypeScript/Node 库；对现有 PPTX 做模板导入、合并、元素修改，支持借助 PptxGenJS 增加原生内容。比 COM 后端更符合当前服务器与 TypeScript 分工。
- 已读能力：[文本修改](https://github.com/singerla/pptx-automizer/blob/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367/docs/text.md)、[母版与布局](https://github.com/singerla/pptx-automizer/blob/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367/docs/masters-layouts.md)、[PptxGenJS 内容生成](https://github.com/singerla/pptx-automizer/blob/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367/docs/generation.md)。适合后续用户提供模板并要求保留原生对象的任务；调用先排队，在 `write()` 时实际应用。
- [限制](https://github.com/singerla/pptx-automizer/blob/fd3fe0ae94ba7f58a28f60e8edc1e94514c5f367/docs/limitations.md)：动画不在支持范围；复杂媒体/特殊关系需要另行验证；复杂内容位于 slide layout 时可能出问题；编辑单页也需将其他页纳入输出过程。不能宣称任意 PPTX 完全无损保留。
- 当前决定：已下载源码和文档作参考，未新增运行依赖、未执行上游脚本。最小实现可先使用受限的 OOXML 样式变换保留现有对象，遇到复杂模板再评估接入本库；所有路径都要渲染和内容保留验收。

## anthropics/skills 的 pptx

- 核对来源：<https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/pptx>
- 本 ref 的 [`LICENSE.txt`](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/pptx/LICENSE.txt) 标为 Proprietary，包含复制、派生、分发与副本保留限制，不能视为可自由复用的开源 skill。
- 当前决定：核对许可后移除了此次下载的专用副本；没有安装、执行、复制到公共代码或改编其脚本与提示。实施依据使用许可清晰的项目、规范和独立代码，不将此 skill 作为本项目可分发依赖。

## 工程边界

成熟 skill 的质量规范可指导模型完成内容与版式任务，确定性脚本可作为 MCP 的能力来源；只有从正常轨迹挖掘、独立认证且后续任务可正确回退的参数流与执行结构，才作为 Motif 效果证据。下载参考、工具封装、固定工作流均不自动构成学得的 Motif 或真实降本结论。

当前已有 PptxGenJS；服务端渲染可以采用 LibreOffice/Poppler，外部执行器的版本、字体与许可证需在部署依赖里记录。PDF 图像提取继续优先复用场景的现有 `pypdf` 能力；对嵌入图像覆盖不全的矢量图，可提供页区域渲染能力，保留页码、裁剪区域、来源版本与图像哈希。
