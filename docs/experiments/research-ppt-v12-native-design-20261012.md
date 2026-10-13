# V12：真正运行原生 PPT 工作流，再选择生成后端

- 实验 ID：`research-ppt-v12-native-design-20261012`，2026-10-12。
- 计划：[原生生成与后端选择](research-ppt-v12-native-design-20261012-plan.md)。
- 结论状态：两种工作流已真实生成、原生编译并经辅助修订交付六页 PPTX；服务器实际渲染检查通过。未完成独立科学/审美盲评，未证明相同质量下成本下降，未产生新 RSI。
- 公共改动只有计划、报告与交接。TypeScript MCP、上游固定源码、论文、轨迹、原稿、失败、修订和交付均留私有 `.local/`；尚未替换产品默认后端。

## 总的结果

此前 V11 没有运行 harness-anything 的 PPT 引擎，也没有运行 Academic/PPTMaster 的自由 SVG 编译链；实际仍是我方 JSON→PptxGenJS。吸收设计方法不能作为上游效果测试。本轮用同一原始公开 VeRA PDF，让 DeepSeek 各自重新阅读、规划和逐页创作，再调用固定版本上游 checker/finalizer/SVG→DrawingML compiler，没有向模型提供 V11 的页面计划。

原生链路确实突破了旧有限页型：模型能直接安排完整画布，产生可编辑文字、方法形状、线条和独立原图。但初次创作均不能直接可靠交付，真实暴露了布局、转换、科学事实和服务封装问题。最终结果包含 Codex 来源/视觉反馈、DeepSeek 同任务修订及少量明确记录的辅助编辑，不是无人干预的成功样本。

| 本轮工作流 | 最终页数 | 可编辑文字 run | notes | 原论文图片 | 全部真实模型请求 | 全部 token | 代理估费 USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Academic PPT Master | 6 | 304 | 6 | 1 | 64 | 7,621,581 | 0.28849044 |
| PPTMaster Default | 6 | 123 | 6 | 3 | 93 | 11,718,897 | 0.31842778 |
| 合计 | 12 | — | 12 | — | 157 | 19,340,478 | 0.60691822 |

请求和费用包含输出截断、步数停止、失败与模型恢复，不只计算最终成功阶段。费用为预算代理账本估费，实付未知；Codex辅助、人工、服务器与维护费用未计价。Academic与PPTMaster明确同源，比较的是两种工作流，不是两个独立引擎。

| 工作流 | 未命中输入token | 缓存命中输入token | 输出token |
| --- | ---: | ---: | ---: |
| Academic | 436,112 | 7,089,536 | 95,933 |
| PPTMaster | 528,873 | 11,112,448 | 77,576 |
| 合计 | 964,985 | 18,201,984 | 173,509 |

逐请求账本汇总快照：私有 `evidence-audit/accounting-20261012T053601Z.json`；原账本与逐阶段配置分别保存，汇总不覆盖旧记录。

## 1 / 数据集与真实任务

任务为公开论文 VeRA（arXiv:2310.11454v2）的六页中文科研组会稿，要求机制、原图、数值结果、实验条件、局限与可编辑正文。原始 PDF SHA256 为 `b91f11fc716e3dae85ed7954e11a7e3c93cce93cbd4c7bde243735c44426c7ab`，21页。论文与上游源码先在本机下载，再上传服务器；模型、测试与渲染全部在服务器留日志。本机只读源码、下载、备份和查看预览。

这是一个任务上的两种工作流试用，各一次初始生成及其恢复。修订续写不算独立任务；没有训练/认证/评测划分，不报告跨任务成功率或统计显著性。

| 固定来源 | commit | 使用范围 |
| --- | --- | --- |
| [Academic PPT Master](https://github.com/M1n-n9/academic-ppt-master) | `6825d33f2931b8894435b9bd25c08cfce3476ff0` | 学术工作流、自由SVG、原生compiler |
| [PPTMaster](https://github.com/hugohe3/ppt-master) | `ca04346de145ed6462ddf34682848e71df5e20a2` | Default工作流、设计锁、checker、原生compiler |

MIT、ATTRIBUTION及固定来源保留在私有完整源码。项目许可不概括论文、字体、图件与各依赖许可。PPTMaster attribution guard 服务器真实运行返回0；未修改上游执行器。

输入抽图也有缺陷：两个标为 Figure2/3 的 p8 PNG 均包含 Table5尾部和两个图，是混合重复裁片，不能当独立完整原图。两组最终均停用它们，保留旧资产、模型误用稿和来源复核证据。真正 Figure1 完整保留；PPTMaster 另保留完整 Figure4/6。原图字节保持并不能认证抽取区域正确。

## 2 / 让模型在读取与结果出现后做决定

主作者是 DeepSeek。它先读取冻结 PDF 文本和上游 Skill，再写 `design_spec.md/spec_lock.md`，逐页读取设计锁、写单页 SVG 与 notes，最后请求导出。页面不是我方旧 JSON 页型重排，也没有由脚本替模型绘制。

五个固定 MCP 工具依次为 `read_reference`、`save_design`、`read_design`、`write_page`、`export_deck`。私有 TypeScript 服务通过真实 stdio MCP 暴露；Python 只执行固定 checker、finalizer、compiler 和交付检查。拒绝越界文件、远程/活动SVG、任意shell/eval；新页面顺序写，修订校验旧SHA、允许页和来源依赖。逐次工具参数、结果、失败保存于 `actual-mcp-calls.jsonl`。

模型根据上游检查结果修稿。但 DeepSeek 本轮没有视觉输入，不能称模型自主看稿：Codex实际查看全部PNG、核对原论文，再将文本反馈交给DeepSeek。最终另有明确辅助编辑：Academic修正第5页notes误引Table1及修订旁白；PPTMaster修正第1页notes训练表述、第5页归一指标可见口径及notes，并同步活动图片清单。全部位于新副本、带旧/新SHA与原因；不冒充DeepSeek自主生成或RSI。

## 3 / 与原有 DSH 流程的对比

| 环节 | V11产品链 | V12试用链 |
| --- | --- | --- |
| Agent循环与记账 | Harness及预算代理 | 继续复用同一公共入口 |
| 作者提交 | 有限JSON Slide计划 | 设计锁与自由SVG、逐页notes |
| 确定性渲染 | 我方PptxGenJS | 固定上游SVG→DrawingML |
| 版式自由度 | 有界页型、单主体约束 | 全画布安排，更多对象布局 |
| 来源与交付 | 场景已有守卫与LO | 私有任务/图件/SHA守卫，加既有LO检查 |
| 当前产品地位 | 默认链路 | 隔离可调用原型，未正式发布 |

链路为 `Harness/DeepSeek → TypeScript MCP → 模型SVG与notes → 上游固定compiler → 独立LO/PDF/PNG → 来源/视觉辅助审阅`。没有改 Harness 核心，没有复制另一套Agent循环。

harness-anything 未实际运行的原因是所参考 `WPS/ppt-engine` 子链需要 Windows、WPS、pywin32，并实际调用 `KWPP.Application`；当前实验服务器是Linux。这只是该子链的平台限制，不能推广为整仓仅支持Windows。未跑就没有效果结论，也不能将我方简陋归因于它。

V11 VeRA历史生成为20请求/684,296 token/代理约0.04603美元，但内容、工具契约、风格要求和辅助恢复不同。本轮不以它计算“降本率”；原生流程目前没有匹配质量的公平baseline，至少不能据本轮称更省模型费用。

## 4 / 费用比较与归因

| 阶段 | 请求 | token（含缓存命中） | 代理估费 USD | 阶段耗时秒 | 实际结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| Academic generation-01 | 27 | 4,228,001 | 0.13664096 | 218.82 | 六页完成；错误CLI参数、转换与内容缺陷 |
| Academic repair-04 | 24 | 2,480,422 | 0.09476946 | 158.59 | 导出通过；讲稿单位/行列及表头仍需修 |
| Academic feedback-06 | 13 | 913,158 | 0.05708002 | 108.63 | 主要问题已修；小notes错误另辅助改 |
| PPTMaster generation-01 | 11 | 857,798 | 0.05518052 | 69.03 | 设计输出触及8000上限，0页 |
| PPTMaster generation-02 | 40 | 6,812,706 | 0.14835888 | 218.23 | 六页SVG完成，达到40步，未交付 |
| PPTMaster repair-05 | 6 | 89,825 | 0.01158737 | 58.09 | 原生PPTX已导出，文字保留/事实不合格 |
| PPTMaster feedback-07 | 36 | 3,958,568 | 0.10330101 | 172.22 | 数据与布局修复，活动图片锁阻止导出 |
| 最终辅助编辑及固定导出08/09 | 0 | 0新增DeepSeek | 0新增DeepSeek估费 | 27.00 / 21.74 | 两份最终样稿实际渲染通过 |

模型阶段耗时合计约1003.60秒，另有固定检查、导出、下载及辅助审阅；该和数不是包含开发/审阅等待的本轮墙钟时间。修订不是新增独立任务。模型请求账本完整，实际账单、Codex用量、人工分钟、CPU与开发维护金额未知。缓存命中token占总量较大，不能用total token直接替代费用。

成本高的已观察原因包括：上游参考内容和重复设计锁较长；设计输出容量不足；向模型返回长整稿错误；重写布局引入新边界错误；服务没有设计资料清单的有界修订入口。不能把这些工程恢复成本记成RSI发现/认证成本，也不能遗漏它们。

## 5 / 调用次数与全部运行记录

每个阶段有效配置、题面和SHA分别保留在私有 `<job>/prepared-config.json`、`scenario.json`、`native-job.json`、`prompt.md`、`harness-01/config.json`。每个运行的manifest、preview、metrics、逐请求账本和事件位于 `.local/runs/<run-id>/`：

| 阶段 | run-id |
| --- | --- |
| Academic generation-01 | `59f8306fe6a94b0e9ce33f21a48e510a` |
| Academic repair-04 | `c405b1cf691647e4a44631ab0bbfb0d0` |
| Academic feedback-06 | `97db877352bc41e492a2ca49ce421651` |
| PPTMaster generation-01 | `b934ee2e3fe84b8abea2693dc6635026` |
| PPTMaster generation-02 | `e07558fe0938459a93cc12d83874a6f0` |
| PPTMaster repair-05 | `9a454f09c7004d32ac5804082d14d1ba` |
| PPTMaster feedback-07 | `d148d2bee60544209e99c1078548eb13` |

有效模型为 `deepseek-official/deepseek-flash`，`reasoning_effort="off"`，压缩关闭，`mode=baseline`，CAS/Motif关闭，manifest_digest为空。工具集合及顺序固定为上述五项；每阶段1.50美元/40步/每请求8000输出，总预算沿用用户不限授权，模型串行。Academic初始运行前缀86493字符；PPTMaster通过阶段资料束读取，实际加载以工具事件为准，不能声称所有参考都完整加载。

服务器原代码HEAD为 `6ced8277d7743bcb260975290665af26d105274a` 加既有部署文件与私有原型；本机开发worktree已为 `d168e92477f57a07cd39b3f169de0ec96e959af6`。两个状态有区别，旧快照不追改。Ubuntu18/Python3.12/Node22包装器/LO7.6/静态Noto是本轮运行环境，字体与跨平台兼容仍有边界。Provider完整payload、内部重试、账单核对等缺失项明确为未知。

最短复现入口使用服务器项目环境，按私有任务记录加载模型凭证；无需在公共文件写密钥：

```sh
source .local/activate.sh
python .local/research-ppt/research-ppt-v12-native-design-20261012/native_smoke.py
# 新实验ID/目录内prepare，再复用scripts/run-scenario.py；旧目录不可覆盖重跑。
```

私有新任务脚本与入口保存了确切命令、预算和版本。它仍有VeRA/六页硬编码，不能当通用安装入口宣传。日志位于 `test-logs/research-ppt-v12-native-design-20261012/`。真实无模型MCP smoke通过五工具/越界拒绝；首次客户端字段误用失败保留。此次没有公共运行时改动，未为形式重跑全仓付费或根测试；沿用V11已有根test/smoke结论，不能写成本轮重新验证。

## 6 / 报告质量与评审边界

| 已发现的问题 | 处理及证据边界 |
| --- | --- |
| Academic exporter不支持误传的`--no-image-optimize` | 独立修正封装并保留旧源码/失败；不称模型自动工程修复 |
| Academic上下标dy引发公式叠字 | 原生转换器兼容问题；模型改为明确普通文字，未测试OMML |
| p8图件混合裁片 | 独立查看原页与图片后停用；不是导出器二次裁图 |
| Academic K误读为M，多1000倍 | 来源反馈后模型修正，notes独立复核 |
| PPTMaster跨模型RTE/CoLA归属及LoRA柱图读数错误 | p3/4/5来源反馈后模型修正；最终归一口径辅助补清楚 |
| PPTMaster文字保留失败 | `≪`在PDF抽取排序改变，PNG字形实际存在；改普通文字且同时纠正源维度笔误，未放松validator |
| 错图移除后仍被设计锁要求引用 | 服务缺少计划修订能力，模型无权修改；新副本同步库存/锁及收据，并保留变更依据，未删checker |

最终两份六页PPTX经过上游检查与真实LO/PDF/PNG，文字保留、页数、notes、已提交来源、字形与基本几何检查通过；独立辅助逐页查看及源数值复核。未进行人工盲评、用户满意度或人工修订时间测量，不能从自动通过推导“科学完整正确/精美”。

编辑性边界：正文/线条/方法形状是原生对象，表格是文字与线组合；两组原生数据表格、数据图表、OMML公式均为0。原论文图仍是图片，内部标签和实验数据不能逐项编辑。公式为普通可编辑文本，不是公式对象。Academic数值更完整但较密，末两列表头间距紧；PPTMaster较疏但第6页附图小，页脚残留过程说明。可审阅真实样稿，不是成熟无干预产品。

另真实渲染了上游公开Attention15页成品，提供官方效果参考；它不是本轮模型生成。原稿外链触发安全拒绝，安全副本仅移除外链动作；LO仍有公式黑色/比例兼容缺陷、没有notes。保留原稿及负面证据，不将其视为质量认证。

## 7 / 逐页展示与交付

最终私有交付基于 `academic-assisted-final-09/project/exports/attempt-01/` 与 `pptmaster-assisted-final-08/project/exports/attempt-01/`，包含PPTX、PDF、六页PNG和整稿拼图；备份到本机 `.local/research-ppt/research-ppt-v12-native-design-20261012/`，原始及失败稿分别保留。原始日志与来源不进入Git。

便于审阅的最终两组文件在 `deliverables-native-20261012T091728Z/academic-native-VeRA/` 和 `deliverables-native-20261012T091728Z/pptmaster-native-VeRA/`，各有 `presentation.pptx`、`presentation.pdf`、`overview.png`、六页PNG、交付报告和独立对象/来源/保持审计。24个文件从服务器下载到本机后逐一核验SHA256，0不一致，manifest SHA256为 `910c069cf1ea4d68bf1c04f073293b3c721d39b47c15dfb897263277dd3a26ca`。

完整本轮证据包已在本机 `server-evidence-20261012T092039Z/` 保存 `evidence.tar`、`manifest.json`、`restored/` 和 `local-sha-verification.json`；1382个文件、63,363,692字节恢复后逐文件核验SHA256与大小，0不一致。包含7个付费run、9阶段配置快照、原稿/失败/辅助修订、相关实际validation与test-logs；排除凭证和已另存的固定上游源码包，实际APIkey值扫描通过。这是本轮明确清单的备份，不等于服务器整个项目全量同步。archive SHA256为 `cacb7616a8ea90f1b4c35cef7ab21844b8484990e74b861ad180ba7be356c0d9`，manifest SHA256为 `849eebd6b1b3206bdb0a8110682536afa1f36fb7ed5c634fdbb589f4a30a090e`。包内文档是封存时镜像，本段备份核验结论随后追加，未追改封存包。

保持性证据也区分层次：Academic09相对06的SVG/notes除第5页notes外保持，父PPTX存在，可核验非目标OOXML；PPTMaster08相对07的SVG除第5页、notes除第1/5页外保持，但07没有成功导出PPTX，父OOXML保持性证据不足。不能把源文件保持推导为不存在的父PPTX保持。

| 页码 | Academic最终稿 | PPTMaster最终稿 |
| --- | --- | --- |
| 1 | 论文、机制、部署存储动机 | 论文、更新公式与冻结/训练对象 |
| 2 | 相关工作与内在维度动机 | 存储需求与参数冗余 |
| 3 | 原生方法对象、参数定义、初始化 | 完整Figure1、两更新式、源维度笔误边界 |
| 4 | 完整Figure1与Table1理论存储数值 | Table2的Avg/RTE/CoLA与ViT参数 |
| 5 | 六任务GLUE表与公平比较条件 | 消融、完整Figure4、归一指标与时间/显存 |
| 6 | 原生消融表、结论、条件与局限 | 结论、实验条件、局限与Figure6 |

## 8 / 学习成本、复现与适用范围

本轮没有生成/认证/启用新Motif或Code RSI，`model_requests_skipped_verified=0`。普通后端、规则、辅助修订不能包装成RSI。当前首先获得的是可调用真实原生生成链和一组能审阅的交付；可靠性与累计成本仍需改善。

推荐后端按用途选择：

| 候选 | 适合用途 | 当前证据 |
| --- | --- | --- |
| PPTMaster compiler＋Academic学术层 | 新论文生成自由布局科研稿 | 本轮真实运行；同源；需来源/设计修订/交付守卫 |
| [Office-PowerPoint-MCP-Server](https://github.com/GongRzhe/Office-PowerPoint-MCP-Server) | 已有PPT对象编辑、原生表图 | 真python-pptx MCP、无内置LLM；仅源码审计，保真/重启/渲染尚未实测 |
| [PPTAgent](https://github.com/icip-cas/PPTAgent) | HTML自由设计及视觉评审 | 当前main MCP仅视觉评审且有模型费用；生成走CLI/Node，Ubuntu18浏览器兼容待测 |
| harness-anything WPS子链 | Windows WPS执行端 | 本轮未运行，无效果结论 |

下一步最小工程工作：将私有五工具原型移入现有场景，去掉论文/页数硬编码，固定版本及许可；增加有界设计修订，使有证据的素材失效能同步计划、锁、收据和相关页；每次写页先做轻量独立布局/合同预检查，导出只返回准确blocking子集，避免无权限问题诱发反复模型请求。保留原稿、依赖、非目标页和实际渲染验收，不裸接任意文件路径和所有Office工具。

这些先作为普通工程优化/B1，与现有生成路径在少量新论文任务上比较合格总成本。只有从真实轨迹学到适用条件、独立认证并在新任务继承执行、额外减少模型决策或提高质量后，才讨论RSI增量。当前不继续无目标生成工具或扩大模型评测。
