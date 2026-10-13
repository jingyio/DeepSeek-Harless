# 科研 PPT 设计来源核验与最小吸收方案

- 日期 / ID：2026-10-12，`research-ppt-design-sources-20261012`。
- 类型：公开来源代码调查、作者示例视觉检查及一份现成 PPTX 的服务器渲染诊断。不是新一轮 Agent 降本实验，不改写 V1–V10 结果。
- 结论：优先吸收 Academic PPT Master / PPT Master 的学术页面原型，参考 PPTAgent 的参考稿版式继承。保留现有 Agent、TypeScript 渲染和来源/版本验收；单独增加提示词不足以解决当前页面表达限制。
- 调查当时状态：已下载或读取来源、核验许可与版本、查看示例；尚未接入新设计、未运行作者生成 Agent、未证明新任务质量或成本收益。后续落地状态见文末及 V11 结果；原诊断不追改。没有提交、推送或 PR。

## 现状和问题

V10改善图文容纳、表格列宽与流程排布，但仍主要采用固定标题区和项目符号。当前 `skills/research-design/SKILL.md` 是独立编写的指导；此前参考 harness-anything 的 JSON/渲染分离、等比图片和预览检查，没有复制其视觉引擎或模板资产。

`ts/render.ts`、`ts/delivery-adapter.ts` 和 `service.py` 均限制每页最多一种 image/table/chart/comparison/process 主体；没有公式、图片注释和多面板字段。标题区、takeaway及只在 notes 中记录详细来源，使科研证据难以成为视觉中心。更强 Skill 也不能输出契约不支持的组合。

## 来源比较

| 优先级 / 来源 | 已核验证据 | 适合吸收 | 限制与不吸收部分 |
| --- | --- | --- | --- |
| 1：[Academic PPT Master](https://github.com/M1n-n9/academic-ppt-master/tree/6825d33f2931b8894435b9bd25c08cfce3476ff0) | MIT，commit `6825d33f2931b8894435b9bd25c08cfce3476ff0`；实际查看 Attention 12页公开预览与设计规格 | academic-clean / academic-defense 的机制、实验结果、原图、公式带、重点数值、条件与局限页型 | 单次发布、一个示例，未运行其导出器，未见随仓库分发的成品PPTX/测试目录；部分字体过小；固定五模块/侧栏不应成为任务约束。公式默认PNG、SVG图表转形状不等于原生可改数据的chart |
| 1的引擎来源：[PPT Master](https://github.com/hugohe3/ppt-master/tree/ca04346de145ed6462ddf34682848e71df5e20a2) | MIT，commit `ca04346de145ed6462ddf34682848e71df5e20a2`；查看公开Attention封面、style/layout规格和能力映射 | 设计身份、页面结构与内容分离；类型化slots、chart-insight / table-summary / picture-caption布局 | 自由SVG→DrawingML路线与现有契约差异较大；原生chart/table另有专门路径，母版需要structured路线；不保证任意SVG/任意PPTX无损往返 |
| 2：[PPTAgent参考稿版本](https://github.com/icip-cas/PPTAgent/tree/d53296bc0ddd73e81d51c523d20dd711c7f233f3) | MIT，v0.2.0实际commit `d53296bc0ddd73e81d51c523d20dd711c7f233f3`；阅读SlideInducter、_edit_slide、ShapeElement.build及限制说明 | 从真实参考稿提取布局/内容schema，保留原页设计并替换内容；可离线整理受限布局族 | 不自动发明新布局；复杂group/freeform/media等有解析限制。未运行其Agent或完成其示例视觉验收。当前main已转新版Skill，不能混同版本 |
| 3：[Noi1r PowerPoint Skill](https://github.com/Noi1r/powerpoint-skill/tree/a39cd8cfba332741a96d52bebd2bb378b638364e) | MIT，commit `a39cd8cfba332741a96d52bebd2bb378b638364e`；读取设计helper、主题、OMML注入实现；服务器渲染公开25页PPTX | 公式/符号组织、图示pipeline、组合页面helper；与我方PptxGenJS技术接近 | 本轮公式真实渲染有严重变形；页18文字保留检查未通过。不能直接搬其OMML路径；固定参考页/附录数量、密度下限和自评分不作为我方验收 |
| 辅助：[K-Dense scientific-slides](https://github.com/K-Dense-AI/scientific-agent-skills/tree/92ace75ac21efe19a620434e0ca4e356081fe807/skills/scientific-slides) | 该Skill标MIT，根LICENSE.md MIT；commit `92ace75ac21efe19a620434e0ca4e356081fe807` | 科研叙事、图表可读性、条件/不确定性和可见引用指导 | 默认整页图像→PDF不符合可编辑PPTX。没有读取/吸收其另一个pptx子Skill，不将仓库根MIT当作所有子目录许可 |

Academic PPT Master 的 [ATTRIBUTION.md](https://github.com/M1n-n9/academic-ppt-master/blob/6825d33f2931b8894435b9bd25c08cfce3476ff0/ATTRIBUTION.md) 明确引擎来自 hugohe3/ppt-master。若改编代码或资产，需保留两方许可、固定来源和差异；图标/品牌/论文图件另核验。当前只下载到忽略的私有参考区，没有分发这些代码或资产。

另查过 HKUDS/Paper2Slides：官方流程生成整页PNG和PDF，不选为我方PPTX引擎。Touying/Beamer Metropolis可参考成熟科研排版，但常规PDF/整页PNG包装PPTX不等于原生编辑；本机presenting-conference-talks的PPTX示例仍以title+bullets为主，不作为本次视觉主线。

## 本次真实诊断及边界

- 输入：Noi1r公开 `example/linear_perm_slides/linear_perm_slides.pptx`，395,193字节，25页，SHA256 `93d909bcdbb27b5ecc13c9658f7347a9a5fff1f761400732148ba4c3ed986b7f`。包内有14个 `<m:oMath>` 节点、3张原生表，无残留MATH占位符；这只证明相应对象存在，不证明科学正确或兼容。
- 在既有服务器用户环境激活后，使用现有 `validation.validate_delivery` 渲染；Python3.12.15、LibreOffice7.6.7.2、PyMuPDF1.26.7、Linux/glibc2.27，项目静态字体配置。代码HEAD `6ced8277d7743bcb260975290665af26d105274a` 加既有未提交V9/V10改动。
- 得到25页PNG/PDF，25.269秒。自动状态 `failed`：页18一项文字保留缺失；SVG尺寸读取一项warning。辅助视觉查看1/3/5/7/11/18页，5/11/18等页公式被严重横向拉伸，不能接受为兼容结果。尚未在PowerPoint中打开，也未做完整科学内容审阅；不据此断言PowerPoint也显示错误。
- 模型请求/模型费用：0；没有执行作者代码生成或联网API。CPU/维护时间仍有成本，未计价。
- 私有有效快照/摘要：`.local/research-ppt/design-sources-20261012/config.json`、`validation-report.json`、`reference-overview.png`。服务器日志：`test-logs/research-ppt-design-sources-20261012/reference-render-01.log`；原始验收目录由report引用，失败证据保留。

## 最小落地顺序

1. 首先实现3种有界科研页型：证据聚焦（大原图+少量注释+可见出处）、结果总结（原生chart或表+关键结果+条件）、方法机制（可编辑模块/连接+简短解释）。先不重写Agent或开放自由画布。
2. 增加可选有限`archetype`、最多3项有来源说明槽；服务从已核验source/page及实际图号metadata生成可见出处。旧plan保持兼容。多图和公式分别作为后续小步，不绕过其保持/渲染验收。
3. 改动集中在`ts/render.ts`、`ts/delivery-adapter.ts`、`service.py`、`validation.py`、明确编辑入口及设计Skill/provenance；使用现有Noto和原生表/图/形状，不把整页PNG称可编辑。
4. 先选已有稿的3个典型页做同内容重排，保持事实、图件字节、实验条件及来源；真实PPTX/PDF/PNG与非目标页保持后，请用户比较可读性和科研风。再用一篇新论文验证生成能力，并记录全部请求、token、修复和人工时间。

本步首先是普通产品设计改进。外部Skill或人工版式不自动变成Motif/RSI；后续只有从真实重复失败中自主发现有适用条件的选择/修复，经独立认证并在新任务继承使用、超过普通规则的收益，才作为RSI效果报告。

## 后续落地状态：V11

上述三种页型、来源索引说明槽与实际来源栏检查已独立实现，renderer 为 `research-ppt-layout-v11.2`。三份旧稿同内容真实重排和一份 VeRA 六页真实模型稿/辅助来源修订完成，成品下载到用户本机供对照。固定 Academic PPT Master/PPTMaster 来源与完整 MIT 许可保留于场景 provenance，没有复制执行器或视觉资产。原图过小、页脚侵入与 DoRA 非目标字体分片差异均保留负证据。结果和费用见 [V11记录](research-ppt-v11-scientific-design-20261012.md)；独立审美/科学人评、完整生成降本与新 RSI 仍未证明。
