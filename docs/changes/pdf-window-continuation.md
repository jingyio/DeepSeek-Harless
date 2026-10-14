# 多窗口读取续接：实施前接口与 GitHub 说明

2026-10-12。目标是在主题文献检索中，模型选完并pin多个窗口之后，由既有Motif Runtime读取工具已经签发的source_id，交回模型作相关性/支持/综合判断。不是自动选择窗口、合并多个命令或新建Agent循环。

## 复用检查与决定

现有`proposeReadyBatch`已支持交错历史、多条同源边、最多8个读取一批、实际结果回调后计数、失败回原Harness，以及闭合source_id读取免embedding。现有标量输入只接受字符串；旧pin默认参数守卫拒绝自定义整数start/length。没有必要新增遍历协议/插件。

**不修改共享核心、旧manifest版本、上游Harness、预算接口或正式Agent默认工具集。** 新增独立文献窗口场景，用规范十进制字符串表达页/偏移/长度，所有4个参数必填。两组共同使用这种接口；接口表示变化/工具本身缓存不是Motif收益。旧探针13条链不是新接口训练样本，不转写历史参数或伪造模型事件。

## 场景接口

- `pdf_window_tools.py`复用WorkflowProbeScene/PdfScene，任务仅允许topic_search；原PDF只读，输出仅.local。
- `pin_pdf_context(paper_id: string, page: string, start: string, length: string)`：page为1起的物理页；start为0起规范十进制，最多7位且<=1,000,000；length为1..12000规范十进制字符串；拒绝负数、浮点、前导零、布尔、非字符串。转换后执行原pin工具，保留PDF/解析器/页窗口/来源身份守卫。Runtime不生成这些参数，只观察真实模型已执行成功的pin。
- `read_pinned_pdf_context(source_id: string)`仍用原工具，只读取本会话已签发窗口，返回完整text/quote_spans/来源版本；不选择相关片段，不复用旧会话引文。
- input/search/report仍用同一窄任务能力；报告完整覆盖、同篇已读引用/缺口、工件SHA核验，不等待人工审批。说明长度错误暂缓修改，不放松支持/来源约束。
- 场景实现版本覆盖wrapper、原PDF/parser、基类、场景配置/题面/工具契约。运行开始核对当前工具schema、library学习来源与版本，执行中再次检查来源/实现。版本/schema变更须新认证，不能仅换工具名加载旧库。

## 学习与在线执行

Python复用infer_dsh_provenance/mine_witnessed_parameter_edges/compile_witnessed_edge_motif/certify_witnessed_edge_motif/library_from_certified/export_manifest。两个不同研究问题/论文数的普通原生训练任务，一项不同研究问题/范围独立认证。只学习source_id返回值→下一read参数；参数常数或重复同任务不作迁移证明。

在线加载原`sss-online-motif`/原生SDK公开回调；manifest仍v1；结构任务冻结当前文档版本集合、题面、任务SHA，读取边由实际模型pin结果触发。查询、pin和科学解释仍由模型负责。入口/terminal/旧其他库不组合，不启默认Web。

现有SDK要求配置loopback embedding endpoint，即使闭合读取不用embedding。实验启动一个拒绝embedding请求的本地观察端点，记录实际访问数；不生成模拟向量，不用embedding分数授权跳过。若访问则保留失败/回退，不能声称0embedding。工具失败或版本不符，既有守卫回原模型；只有所有实际读取结果核验后计verified batch，batch数不是实际净减少请求。

## 实验与验收

在付费前确定ID/输入/工具/提示/代码快照、训练/认证/评价划分与交错顺序；保留学习、失败、重试和认证费用。先免费测试参数/陈旧来源/批量/已读去重/原Harness回退，再新普通轨迹学习与独立认证，然后至少两个问题各3轮原Harness/learned-Motif对照。

自由选词/选窗对照观察完整任务实际调用、输出、缓存输入、代理估费、耗时、错误与交付覆盖。模型可能选择不同窗口，不能把全文输出差异都归因读取续接，也不能把机械收据等价当科学质量等价。若缺少相同窗口证据，可补一个来源于真实模型选择的冻结窗口组件对照，单独报告范围。旧探针两主题25请求中4个纯read响应/793输出只是筛选依据，不是承诺节省。

本轮不会修目录标题、扩前端、安装新系统或写用户知识库。取消新场景`--manifest`即可回原Harness；旧应用/服务/历史.local均保留，未经请求不commit/push。
