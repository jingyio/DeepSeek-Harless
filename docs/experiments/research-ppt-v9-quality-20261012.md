# V9 质量与结构执行验证

- 实验 ID：`research-ppt-v9-quality-20261012`；2026-10-12，Codex。
- 问题与假设：先消除完整计划漏字、轴变量/单位不可见、PPTX页号错配、复合图截断以及数值/方法/条件错绑定，之后才检验条件结构相对于普通规则的净收益。工程修复不称RSI创新。
- 设计依据：[V9审计](research-ppt-v9-audit-plan-20261012.md)。训练、独立认证和评测继续分开；发现自然执行机会之前不制造重复调用、不扩大候选数量。
- 代码基线：`6ced8277d7743bcb260975290665af26d105274a`；本轮在隔离工作区实施，未提交、未推送。
- 环境变化：原AutoDL实例关机；用户明确授权本地开发、测试与备份恢复。新服务器 `Ubuntu 18.04 / glibc 2.27` 已通过本机公钥连接；部署位于用户存储目录，依赖使用项目内环境，无root安装。公开记录不包含服务凭证。
- 任务与对照：Gate0实际OOXML/PDF/PNG工程回归及真实论文图件反例；Gate1限定两个独立正常训练和一次隐藏认证；通过后执行审计计划的两个新材料增量修订任务×B0/B1/B2/B3。当前尚未开始模型对照。
- 配置与复现：锁定根及场景安装清单；本轮测试日志在 `test-logs/research-ppt-v9-quality-20261012/`，有效实验快照、原始数据与交付在 `.local/research-ppt/v9-quality-20261012/`。本机开发和服务器测试分别记录，不混称历史环境。
- 已实施待集成：默认公开TS可靠交付入口；计划文字/图表数据oracle；真实PPTX页序；三态直接科学结果元组及版本/Unicode摘录定位。科学侧表独立审计，不因逐字摘录存在而通过科学支持或全稿质量。
- 测试与质量：阶段结果随回归追加；工程测试不代表领域质量。独立人工盲评、人工修订分钟、费用账单仍待取得。
- 成本：截至初始记录尚未新增付费请求。不限预算授权继续有效，但每任务防失控上限、候选次数和试验规模保留。依赖安装/数据恢复的耗时单列，不能计入模型收益。
- 回退：旧根工作区和他人改动不覆盖，旧报告/失败轨迹不更改。原备份仅在所有字节和Linux元数据有可核验本机映射之后清理；Linux符号链接不直接在Windows创建。

## Gate0 工程验证（2026-10-12追加）

完整服务器备份已恢复并核验121,398成员（69,525普通文件、24,921目录、26,952软链元数据，5,814,966,269文件字节），所有文件两次SHA及原路径/权限/时间/链接目标独立核验通过。本机已有文件保留，Linux环境隔离。恢复收据/manifest/重建说明在忽略的`.local/server-sync/20261012-restored/`。用户授权删除的旧备份约7.17GB逻辑字节，但自动审批两次拒绝删除，只返回“blocked by policy”；未绕过，旧备份未删，cleanup收据明确blocked。不能宣称已释放空间。

已实施P0计划保留、图表轴变量/单位可见、真实PPT页序与复合图完整性保护，默认可靠TS入口，以及默认关闭的普通CAS。科学结果元组侧表返回pass/unknown/fail；无独立人审事实不能通过科学支持，当前未绑定PPT可见内容、未接入交付质量gate。既有FA2 Figure5页11完整裁图已辅助比对4个panel、图例和轴，不认证科学解释。

新服务器场景113项Python通过（`test-logs/v9-scene-python-02.log`）；真实LibreOffice、PNG、同job两次重启、局部修订和非目标OOXML保持通过（`v9-delivery-smoke-01.log`）。新增条件协议后30项Node通过（`v9-scene-node-03.log`），随后缓存授权隔离和多图注反例13项通过（`v9-cache-geometry-04.log`）；首次pytest相对import收集失败保留在03日志并已改为绝对模块import。上述不同范围不能简单相加为一个完整测试轮次。

根底座首次134通过/2启动失败。实际Node被conda依赖解算降至20.20.2，DSH入口 `import.meta.main` 未执行；安装校验后的用户Node22.23.2修复该层。node-pty预编译依赖glibc2.28而本机2.27，加载器吞掉低层错误造成误导的“找不到模块”；用Node发行包内headers源码编译后PTY最小spawn通过。第三轮根135通过/1运行时SIGSEGV，仍在定位；不得删除有效测试或据此宣称底座全绿。失败日志依次为`v9-root-tests-linux-01.log`、`v9-root-tests-linux-node22-02.log`、`v9-root-tests-linux-node22-pty-03.log`。

环境：Ubuntu18.04/glibc2.27、Python3.12.15、Node22.23.2、LibreOffice7.6.7.2、NotoSansCJK、conda PyMuPDF1.26.7（MuPDF1.26.12）、MCP SDK1.32.1、DSH0.1.5-rc.3。无root安装；SDK0.1.5rc1显式不装平台不兼容runtime-bin，仍走已记录固定SDK→npm启动接缝；`pip check`该缺依赖不能写成通过。环境安装、字体及原生重建不计作模型优化收益。

## B1 普通缓存实测

后续SIGSEGV已定位并修复：`require(sharp)` 后 `process.report.getReport()`触发glibc2.27加载`libgcc`的ELF relocation崩溃；单独PTY spawn、报告或sharp加载未触发，GDB私有堆栈支持该组合归因。先预热诊断报告后加载sharp可稳定通过，真实40×30 PNG→24×12与RGB核验通过；项目内Node wrapper用私有preload，不改上游、系统库、工具权限或全局LD_LIBRARY_PATH。最新根`npm test` **136 Python / 29 Node通过**、`npm run smoke` **18场景通过**，日志`v9-root-tests-linux-node-wrapper-12.log`、`v9-smoke-linux-node-wrapper-12.log`；前述失败均保留。运行快照还须绑定实际Node executable、wrapper/preloadSHA与兼容recipe，不能仅凭相同Node版本宣称任意Ubuntu18部署支持。

`cache-diagnostic-01`以4篇真实公开论文测同一解析器的未缓存一次、冷缓存一次、热缓存两次，完整payload SHA一致；无模型请求。PiSSA/LoftQ用于后续训练，DoRA/AdaLoRA保留为新任务材料；此处只读取文件作后端诊断，不读取隐藏答案/科学评审真值。

| 来源 | 未缓存秒 | 冷缓存秒 | 热缓存1/2秒 | 完整payload一致 |
| --- | ---: | ---: | ---: | --- |
| PiSSA | 12.478 | 12.485 | 0.041 / 0.040 | 是 |
| LoftQ | 2.476 | 2.521 | 0.022 / 0.014 | 是 |
| DoRA | 7.375 | 7.488 | 0.158 / 0.159 | 是 |
| AdaLoRA | 2.979 | 3.066 | 0.040 / 0.034 | 是 |

在这些观察中热缓存后端时间下降约97.8%–99.7%；冷缓存没有加速。没有控制操作系统文件缓存/负载，没有端到端模型或人评质量对照，不能称稳定PPT总耗时收益、token下降或RSI收益。独立配置/原始结果在`.local/research-ppt/v9-quality-20261012/cache-diagnostic-01/`，本机同步结果和日志保留同实验ID。

## Gate1 当前边界

新增TS有界条件协议及12项正反例测试通过，默认off；Python离线发现/候选/独立认证实现中。协议只允许既有只读页pin/read，严格检查实际schema、前向参数边、宿主与实时scope及结果。尚无新学得候选、可信认证、公共在线接入或实际模型请求旁路。正常训练入口为`python -m scenarios.research_ppt.experiment_v9 seed/revision`，默认预览，调用公共`run-scenario.py`；每个阶段保存实际MCP schema、代码/源/prompt哈希、版本和完整失败日志。不人为指定重复工具链；若正常轨迹无条件机会或两分支不能独立覆盖，则不晋级、停止alpha扩展。

## 真实训练前的交付反例与修复

`pissa-train-01`初稿与反馈、`loftq-train-01`初稿实际完成34次DeepSeek请求，上游均200；代理观察估费合计 **$0.03340449**，并非实付账单。PiSSA初稿12次/242,338总token，反馈8次/93,015；LoftQ初稿14次/280,636。三次共615,989总token，含缓存命中输入548,864、未命中56,043、输出11,082；推理token为0。它们不是B0/B3公平收益对照，也不能因运行状态done算合格交付。

实际逐页预览发现中文全部方框，原验收却passed。外层场景配置和内层TS→Python MCP都漏传`FONTCONFIG_FILE/PATH`，LO因此使用系统DejaVu字体。旧PDF的`ActualText`仍能抽出中文，文字保留检查漏报。已在`cli.py`及`ts/mcp-adapter.ts`显式仅传两项字体配置，禁止为修字体透传所有凭证环境；无模型诊断入口也按相同边界传递。新增`validation.py`实际CJK绘制覆盖与可见GID0检查，旧PiSSA PDF四页均被拒绝；Unicode存在不再直接等同可读。

第一次补字体后PNG中文正常，但可变字体由LO导出为Type3轮廓字形：MuPDF给出ignored-text，同时实际绘制CharProcs路径。当前oracle不能确认这种表示，严格拒绝，不将“无法确认”写成真实缺字。项目改用已存在且SHA核验的静态Noto OTF及独立私有`fonts-static.conf`，不修改系统或原字体配置。静态重导四页字形全部通过；仍有一处上标转置被提取器排到另一行，文字顺序校验拒绝。仅行内几何排序不能解决，未加入跨行猜测或放宽内容保留；后续新任务采用可读ASCII公式并解释符号，旧计划不追改。

有限辅助审计确认PiSSA反馈只修改第2页标题：其余1/3/4页XML、依赖及PNG不变，notes/media全部相同。局部修订机制在这个任务上正确，但整个交付视觉失败。原论文GLUE叙述还压缩混用了两种LoRA对照，PPT沿用后含歧义：1.21为相对LoRAK的绝对百分点，7/8对应LoRAG。原文摘录存在不足以科学认证；新任务明确指标、方法、对照、条件及百分比/百分点，科学独立人评仍未取得。

对应私有证据位于`normal-traces/`、`font-diagnosis/`、`font-revalidation-01/`、`font-revalidation-static-02/`及`pissa-artifact-audit-01/`，原报告/日志不覆盖。5项真实PDF字形回归最终全部通过、无skip（`v9-glyph-guard-09.log`），夹具首次两项失败保留08日志并记录真实修正。`delivery-smoke-font-static-02`捕获诊断客户端自身未传字体；03在最后说明文字上传期间正确拒绝实现版本变化；冻结后04通过完整真实交付/重启/局部修订。三者均0模型，失败与修复耗时单列，不能计成RSI降本。

最新根测试136 Python/29 Node、18题smoke（SDK初始化/0付费）、场景30 Node通过，日志`v9-root-tests-final-13.log`、`v9-smoke-final-13.log`、`v9-scene-node-final-13.log`；完整场景Python回归仍待本段之后追加结果。部署细节和限制见[用户目录部署记录](../../scenarios/research_ppt/deploy-ubuntu18.md)。

完整场景最终回归 **147 Python通过**（448.55秒，`v9-scene-python-final-14.log`）；一条重复ZIP成员警告来自主动构造的安全反例，不是正常交付警告。随后才冻结并启动`pissa-train-02`与`loftq-train-02`，不复用旧job或重签旧checkpoint。新有效快照增加字体配置、Conda/系统字体探针及候选字体SHA；运行文件SHA改为单独流式核验，字体/Node不沿用论文30MiB输入限额。新任务的ASCII公式及明确比较条件属于配置变化，01/02不是公平机制对照，不从它们的请求差计算节省。

## 冻结后两个真实正常任务与全部成本

`pissa-train-02`、`loftq-train-02`分别接收一篇公开论文，生成4页中文初稿，随后在同job的新模型会话执行反馈“只将第2页标题改为核心机制与适用条件，其余正文/图件/来源/notes与其他页保持”。这是两个论文决定，各自的seed/revision不算四个独立科研决定。任务未指定工具顺序；实际初稿、恢复、pin/read与修改均由正常Harness/DeepSeek调用完成，未用模拟Provider产出这些论文PPT。

新初稿及修订共4份均通过实际PPTX→LibreOffice PDF→PNG机械验收，包括计划文字、实际可见中文字形、表格位置和原图字节保持；**科学独立人评和统一视觉盲评仍未完成**。报告中的`passed`只指机械层。旧01交付的原始passed记录保留，已由后续负面审阅判为视觉失败，不能混入科学合格样本。

| case / 阶段 | 实际请求 | 缓存未命中输入 | 缓存命中输入 | 输出 | 全部token | 代理观察估费USD | 阶段秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pissa-train-01 初稿 | 12 | 25,449 | 211,712 | 5,177 | 242,338 | 0.01511738 | 78.259 |
| pissa-train-01 修订 | 8 | 9,366 | 82,048 | 1,601 | 93,015 | 0.00522329 | 44.899 |
| loftq-train-01 初稿 | 14 | 21,228 | 255,104 | 4,304 | 280,636 | 0.01306382 | 65.147 |
| pissa-train-02 初稿 | 15 | 19,322 | 312,320 | 13,028 | 344,670 | 0.02330412 | 103.916 |
| pissa-train-02 修订 | 8 | 9,683 | 82,944 | 2,054 | 94,681 | 0.00586736 | 45.998 |
| loftq-train-02 初稿 | 18 | 30,199 | 455,680 | 14,234 | 500,113 | 0.02887458 | 102.662 |
| loftq-train-02 修订 | 9 | 8,729 | 94,336 | 1,859 | 104,924 | 0.00541551 | 45.055 |
| 全部尝试 | **84** | **123,976** | **1,494,144** | **42,257** | **1,660,377** | **0.09686606** | **485.936** |

所有7阶段上游请求/完整token账本可核对，均完成且上游失败0，推理token0，新verified旁路0。价格是预算代理观察估费，实际账单未知；开发、部署、字体诊断、人修订与维护的时间/费用未统一量化。485.936秒是准备及各阶段wall time的和，**不是包含所有诊断、人评和安装的产品端到端总耗时**。合格件数因人评缺失而未知，不计算每合格交付费用或盈亏平衡。

正常训练使用`deepseek-official/deepseek-flash`（运行manifest的model为`deepseek-flash`）、`reasoning_effort="off"`、压缩off、baseline模式、CAS off、固定19工具，每阶段0.75美元/40步/8000输出上限；有效字段以各阶段`config.json`及manifest/preview为准，不能从当前默认值倒推。每阶段实际MCP schema和工具顺序独立导出并锁SHA。Provider面对的完整工具payload哈希及内部重试策略未采集，账单与人工指标也缺失，配置快照明确列出这些缺项。原运行ID及逐请求账本位于私有归档，公开只列最短复现定位：

```sh
source .local/activate.sh
set -a; source .local/credentials/deepseek.env; set +a
python -m scenarios.research_ppt.experiment_v9 seed --case <新的case-ID> \
  --source .local/research-ppt/v9-quality-20261012/inputs/pissa.pdf --call-model
python -m scenarios.research_ppt.experiment_v9 revision --case <同一新的case-ID> --call-model
```

重新执行需新ID，原case和attempt禁止覆盖。凭证仅私有文件，公共配置引用变量名；不把密钥写入命令或报告。01与02改变了字体、验收和任务公式表达，不能作为效果前后对照；PiSSA和LoftQ任务内容也不同，不能拿它们的请求差归因于论文或机制。

## Gate1：有短链证据，没有可晋级的条件结构

运行`conditional_learning prepare`使用两个独立论文的02修订原始轨迹及实际schema；结果为`opportunities_only_not_learned_or_certified`，共3机会，而非“没有任何结构机会”。准备器返回0不代表认证通过，bundle完整内容已审阅。

- PiSSA出现`read_deck_plan→pin_deck_pages→read_pinned_deck_pages`，但仅一个独立决定支持，不能冒称共享子图。
- PiSSA与LoftQ都出现`pin_deck_pages→read_pinned_deck_pages`，真实`source_id`参数边及版本/文件/页范围一致，支持短读取链候选。
- 共同锚点的`pages_csv="2"`、`scope="explicit_pages_from_current_persisted_plan"`、`scientific_quality="not_reviewed"`均恒定。其余变化是deck、来源及版本身份，不提供有意义的自然条件差异。scope由成功pin契约固定，人为构造不同scope不是自然成功分支。
- 协议允许空分支保守交回语义层，但它不算学得行为；从恒定字段生成条件加空分支，仍未证明相对既有短Motif或手写规则的增量。当前没有供隐藏认证核验的真实两分支覆盖。

因此本轮**停止模型提案、隐藏认证和B0/B1/B2/B3 alpha扩展**。新增候选0、准入证书0、新任务条件执行0、整次模型决策旁路0，没有新的RSI净收益结论。记录为`conditional/gate1-review-01.json`，只读证据审计，不冒称功能认证。条件TS协议及Python准备/认证代码保持默认off、尚未接公共在线插件；不发布该短链为新条件Motif。

这说明当前两个窄页标题反馈和受限pin/read协议不足以验证条件Graph假设，**不说明仓库没有其他可蒸馏结构，也不证明条件RSI一般无效**。下一次最小研究先处理科学对照/可见主张证据绑定，再从真实不同修订需求中寻找可判的状态差异；只有普通规则仍存在实际缺口、轨迹自然支持相应分支，才另立ID冻结条件机制。不能按论文名、随机ID、固定提示路线生成“条件创新”。

## 交付与本机核验

服务器原始论文、7阶段完整轨迹/有效配置、job/checkpoint、旧失败与新验证PDF/PNG、Gate证据及截至归档的`v9-*.log`均打包；排除LO临时profile，不含API凭证。私有归档`v9-private-evidence-01.tar.gz`共24,102,918字节、372文件，SHA256 `9b2a1a4604641435e60451d53173234d6cd48577c82dc656d0793fb936cd5505`。文件manifest SHA256 `b100f046b80e4e18a16ecc6c21252ca766f9ee129bcc7ab973acd4467136c3b7`。

已下载至用户本地项目`.local/research-ppt/v9-quality-20261012/`，安全展开到新`server-v9-final-copy`，归档SHA、成员集合与全部文件SHA/字节一致；没有覆盖本机已有研究文件。`local-verification-01.json`状态verified。完整归档日志结束输出另行下载，最新测试日志也已同步本机`test-logs/research-ppt-v9-quality-20261012/`。这些都是私有数据，不进入Git。

`review-decks-02/`提供PiSSA/LoftQ初稿及仅第2页标题修订的PPTX/PDF/四页拼图，各副本与原始产物SHA一致；`review-index.json`明确这是普通Harness实际使用与局部修订对照，**不是baseline与RSI降本对照**。01审阅目录曾因误用checkpoint字典顺序而对调LoftQ初稿/修订标签；已按原seed/revision的answer及工具事件建立02勘误副本，原PPT和轨迹未改，01保留作负面记录。正确LoftQ初稿为72507061前缀，修订为737a923c前缀。新稿表头存在不自然换行、实验表的对照/指标说明与图文字大小需进一步核验，机械通过不赋予科学或审美通过。

代码与文档仍在基线commit的隔离工作区中，未提交、未推送、无PR；新服务器部署验证不等于团队分支已经同步。最终公共文件检查/辅助审阅的新增结论后续追加，本记录不删历史负面证据。

## 最终只读辅助审阅：机械保持成立，科学交付仍需修订

在本机对已SHA核验的副本追加只读ZIP/PDF/原文审阅；真实模型仍全部在新服务器运行。本机辅助检查日志为`test-logs/research-ppt-v9-quality-20261012/v9-artifact-review-local-01.log`，私有证据为`aux-deck-audit-20261012-01/final-review.json`。这不是独立人工盲评，也不追改原运行质量字段。原文SHA与训练输入一致，初稿/修订身份已按原始answer和工具事件复核。

两对PPTX只改变`docProps/core.xml`中的创建/修改时间及`ppt/slides/slide2.xml`中的一个标题文本；去除该文本后页2结构相同。其他1/3/4页XML及关联资源、notes/media字节相同；1600px PDF重渲染非目标页像素相同，页2变化仅标题区域。两份标题都正确改为反馈要求的“核心机制与适用条件”。这支持本任务中的指定页保持能力，不代表任意对象、外部PPT或跨版本增量修订。

辅助提出10条科学/视觉问题（1条major、8条moderate、1条minor；评级由Agent辅助审阅作出）。关键反例：

| 位置 | 辅助观察与原文依据 | 影响及下一步 |
| --- | --- | --- |
| LoftQ页3 notes | 把2.5-bit写成前4层4-bit；原文PDF p12 Table5图注明确3/2.5/2.25-bit对应前16/8/4层4-bit | 明确实验条件错归，需改为前8层并展示混合精度规则；字面数字相同不足以正确复现 |
| LoftQ页3表 | 数字对应原表，但`5.70 / 35.1`无可见指标/单位/方向；QLoRA13B 2.5-bit仅19.39，漏GSM8K的N.A. | 应分开WikiText2困惑度与GSM8K准确率(%)，保留不收敛状态与匹配基线 |
| LoftQ页4原图 | p13 Figure3三个panel、轴和数据标签完整，但图注只保留第一行，截掉后续模型/量化条件 | 现有guard验证的是提交crop的字节保持，不能证明原论文完整图注；扩展裁图或显式补条件需新版本和回归 |
| LoftQ页2/4结论 | 把图3选定MNLI/XSum任务的最佳T泛化到全部GLUE/BART；“跨架构仍未验证”忽略p7–11已有DeBERTa/BART/LLaMA2实验 | 限定到图中任务与论文未测领域；不能据保留来源自动放行科学边界断言 |
| PiSSA页3表 | 9个展示均值与p7 Table2一致，但Mistral仅PiSSA、无配对LoRA；HumanEval断成两行 | 补原表配对行或移除孤立模型；优化列宽和表头，可编辑性通过不等于可读性好 |
| PiSSA页1/4表述 | 把初始化解释泛化为排除秩影响，并将全参/LoRA/PiSSA一起说“只改初始化” | 应区分可训练参数集合和条件范围，需领域审阅，而非格式程序猜测 |

LoftQ还有未外部核验的“未经同行评审”出版状态断言；只读单份arXiv PDF不能确认该事实。数字的摘录准确与科学解释/实验条件准确分开报告。当前新稿为`auxiliary_review_needs_revision`，不能声称全稿稳定科研可用或质量等价，更不能用其费用证明降本。

下一优先级据此调整：**先把科学元组和完整图注证据绑定到可见Slide IR及notes，并保留unknown/人工交接；再处理清晰表头及匹配对照，之后才收集自然状态差异验证条件RSI。** 普通CAS与严格机械验收作为工程成果保留；当前没有足够证据启动候选工具生成或扩大付费矩阵。最终公共diff只含场景源码/测试/协议与文档，未发现密钥、私人论文或原始日志，上游Harness未修改；`git diff --check`通过。静态字体的部署先决条件已补明，不把当前主机的私有兼容recipe说成一键通用安装。
