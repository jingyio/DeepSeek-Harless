# v2 工具与授权边界

这些工具是真实读写 CSV、执行统计、绘图和生成 PDF 的 Python 软件。标准正文也是人工编写的、按统计设计选择的有限规则；不能把这些工具实现本身称为从轨迹学出来的模体。模体的可复用边、参数来源和认证证据由另一个编译器从普通 DSH 运行记录中提取。

## 输入与科学决定

服务读取 `RRA_DATA_ROOT/cases/RRA_CASE/` 下的 `data.csv`、`study.json`、`task.txt`。任一文件改变都会使旧收据失效。运行输出只写入 `RRA_RUN_ROOT`。不知道来源真实性时不标记为真实实验或合成数据；只有明确的 `synthetic=true` 才标记合成。

`inspect_study()` 无需参数，返回实际列名、前几行、缺失数量、低基数列取值及研究说明。随后 LLM 调用 `approve_workflow(study_id, plan)`，明确选择统计方法、列、缺失策略、图、报告要求与大纲。例如下面仅展示参数结构，不是生产运行中自动灌入的答案：

```json
{
  "analysis": {
    "design": "regression",
    "outcome_column": "value",
    "predictor_column": "predictor",
    "missing_policy": "complete_case",
    "confidence": 0.95,
    "hypothesis": "双侧估计解释变量与结局的线性关联",
    "design_evidence": {"source": "study_description", "quote": "从实际说明复制支持设计的原文"}
  },
  "figures": [{"kind": "scatter_fit"}],
  "report": {"page_mode": "auto", "pages": null, "style": "technical"},
  "interpretation_mode": "standard",
  "custom_focus": "discussion",
  "allow_deterministic_continuation": true
}
```

`design_evidence.source` 可为 `study_description` 或 `user_request`。工具检查引文确实存在于指定来源，拒绝编造引文或引用默认的“未提供研究设计说明”。引文是否在科学上支持所选设计仍是 LLM 和审阅者的责任；此检查不是理解自然语言的自动科学裁判。背景不足以确定观测之间关系时必须询问，不能根据案例编号、文件名或仅凭数据能拟合就宣称设计成立。

支持 `independent_groups`（Welch 两组检验）、`paired`（配对 t 检验）、`regression`（带截距的一元 OLS）。两组需指定 `group_column/reference_group/comparison_group`；配对还需 `subject_column`。方向为比较条件减参照条件，或回归斜率。缺失策略只支持显式 `complete_case`；配对缺失时删除整对。工具不支持多重检验、多层模型、生存分析、混杂调整或自动识别因果。

图种有七种：`distribution_ci`、`group_ecdf`、`effect_interval`、`paired_change`、`change_distribution`、`scatter_fit`、`residuals`。选择一至三种不同且兼容的图，并必须包含该设计的原始数据主图。图输出 PNG、SVG、PDF；图形文字为英文、报告正文为中文。可省略 `figures[].title` 使用内置英文标题；显式图题必须为不超过一百字符的 ASCII 英文。中文图题会明确拒绝并提示该限制，不会被静默丢弃；用户明确要求中文图题时需澄清当前能力边界。

报告支持 `auto`（自然分页）、`max`（最多指定页数）、`exact`（恰好指定页数），页数范围为一至六页；样式为 `brief`、`technical`、`paper`。当前单栏全宽图版式的一页报告最多容纳一张图，一页 `brief` 最多四个标题：批准时提前检查，超出时要求模型重新合并其自行拟定的标题；如果用户明确要求更多图或标题，则说明冲突，不能默删。`brief` 有独立的精简正文，保留估计对象、样本数、CI、p、删除量、假设和来源限制。排版器不会为满足页数删除正文或填充空页，无法满足时返回失败。用户大纲的标题和顺序必须保留；每个标题通过 `roles` 映射到 `summary/methods/results/diagnostics/limitations/next_steps/provenance`。至少包含 methods、results、diagnostics、limitations，可将多个角色合并在同一标题下。v2.1 的模型讨论插入既有 next_steps（无此角色时使用 limitations、再无则 results）章节，不再擅自追加第五个标题。

## 收据链与回退

标准模式：

```text
inspect_study → approve_workflow [LLM 语义决定]
  → run_analysis(plan_id) → verify_analysis(analysis_id)
  → build_evidence(verified_id) → render_figures(evidence_id)
  → verify_figures(figure_bundle_id) → compose_report(packet_id)
  → layout_report(draft_id) → audit_layout(layout_id)
  → verify_report(report_id) → deliver_report(verification_id)
```

上面的链表示工具的允许组合，不是预先塞给在线插件的模体库。普通 Harness 仍由真实模型发出工具调用；执行模式只有在轨迹学习、认证和当前来源、schema、收据、授权校验都通过后，才可能跳过中间模型请求。

`allow_deterministic_continuation` 默认不授权，模型显式选择 true 才会在收据中写入下一工具的授权。它只允许该计划的确定性续步，不授权重新选择统计方法或凭空添加解释。每个工具返回单独的内容寻址 ID，带实际记录文件哈希、来源版本、工作区、计划 ID 和允许调用工具。

`interpretation_mode="custom"` 时，`build_evidence` 必须停止续步并交还 LLM。模型读取实际结果后调用 `approve_interpretation(evidence_id, commentary)`；`commentary.paragraphs` 为一至三段、每段十至八百字符。`build_evidence` 返回 `available_placeholders`，逐项列出准确 token、值、含义与来源，以及包含必需授权字段的完整调用示例。除效应、CI、p、n 外，还可引用实际检验 t 值、自由度、标准误、组均值/标准差、Shapiro W/p、回归截距/拟合优度/残差标准差，以及批准方案的置信度与显著性阈值；只列该设计实际可用的指标。新增统计量从 CSV 用独立公式复算，Shapiro 使用同一 SciPy 算法对重建残差复核，这不称为独立的正态检验算法。

例如置信水平写 `{{confidence_pct}}%`，阈值写 `{{alpha}}`，所检验的零效应写 `{{null_value}}`，而不键入裸数字。只有与段落顺序一致的段首 `1.`、`2.`、`3.` 允许作为排版编号；正文中的科研数字仍须绑定。无效输入一次返回全部发现的问题，包括段落数量/长度、缺失的明确授权、非法 token、具体裸数字、段落位置及替换提示。工具不会自动插入 `allow_deterministic_continuation=true`，失败时不签发续步授权。通过后保留原始模板和所用 token 的来源映射，方便追溯。自定义段落会标记为需要科研复核，模板的科学限制仍保留；数字绑定不能证明自由文字的解释正确，也不是全自然语言科学事实核查器。

v2.1 在用户原文出现明确的研究/采样方案比较要求，或元数据给出 `research_options_min` 时，要求 `custom_focus="research_options"`。这里只使用有限的明确比较词句，不根据案例编号选择路径，也不声称理解任意自然语言。模型可主动选择该 focus；此时 `commentary.research_options` 至少两项、至多四项，每项含 `name`、`rationale`、`tradeoff`，另需 `comparison_summary` 解释方案之间的目标或取舍。所有字段使用相同数字绑定规则，输出保留实际方案比较文字。结构完整、名称不同并不能证明科学内容合理，最后仍需人工或独立科研审阅。工具反馈列出已观察到的措辞风险：不能将观测范围称为可用外推范围，不能以 p 或正态检验证明假设，不能保证重复采样/协变量会改善正态性；另用窄规则拒绝“效应量大于其自身数值”的错误比較。

一页 `brief` 的 custom 批准前，会先展开所有数值，将真正要输出的标准正文、自定义文字、标题、数值表、图注与固定图尺寸交给 `document_engine.measure_capacity`。这与 PDF 渲染使用同一字体和 ReportLab 排版对象，但不写 PDF、不生成模拟图。超容量反馈包含实际展开字符数、排版高度及可用高度；压缩字数建议由本次完整内容与剩余高度计算，不是通用字数阈值。模型须保留含义自行缩写，再用原来的 evidence_id 提交，统计不必重跑；工具不会裁掉原文。测量是前置估计，不能替代最终真实 PDF 的页数、字形边界与文件检查。

v2.1 的源图字号提高到轴标签十六点、刻度/图例十五点、标题十八点，长标题按词换行；数据、估计、坐标范围保持原计算。图嵌入 PDF 后仍会缩放，实际字号与可读性须结合最终页图审阅。

统计核验从原始 CSV 另行复算核心值；图核验重开文件并检查哈希、分辨率、非空、向量与数值来源；排版核验重开真实 PDF，检查页数、文字保留、边界、重叠、图注邻接与文件哈希。排版最多尝试四组有限配置，失败尝试保留。仅 `deliver_report` 成功表示自动检查后的文件交付；不代表专家已经认可研究结论。

## 离线工具测试

```bash
python -m unittest benchmarks.research_report_agent_v2.tests.test_workflow_tools -v
```

测试在临时目录生成明确标记的合成数据，真实执行统计、绘图和 PDF 全链，不调用模型。覆盖三个统计设计的独立复算、exact 一页和用户大纲、显式授权、custom 语义屏障、来源任务变更、跨工作区/非法 ID、PDF 与布局清单篡改，以及未知来源不被标记为合成。测试里的预设分析计划只用于单测，不作为付费实验轨迹或学习证据。
