# 检索报告契约与完整基准接口记录

2026-10-13，用户授权先修检索报告、用新留出验证，再完成原第六阶段基准。此前第五阶段报告/两库/15失败不修改。本阶段不改上游Harness、预算代理、依赖或默认SDK/Web，也不合并任意控制图。

## 触发问题与新契约

旧失败轨迹中，search_index返回正确命中，模型summary也描述正确，但submit_report.file_ids混入全部已读取文件/第一阶段上下文；旧工具只检查ID当前有效，仍签发delivered，原验收随后判失败。新契约在交付点拒绝这个类型混淆，允许模型纠正；不会自动替换模型提交的错误ID或放宽验收。

新增独立report_tools.ReportScene继承CollectionScene，两个实验组共同使用14工具、相同顺序和schema。read_task追加report_contract/version/kind、报告执行版本和继承读取版本。submit_report新增必需report_kind=task_result|literal_search与可选search_receipt_id；kind必须与任务一致，ID唯一。普通任务省略search_receipt_id，保持原当前ID和效果收据核验。

literal_search只允许最后一份完整collect_reads集合；若声明两阶段，须实际完成两份。build_index要求恰好该集合实际read handles；query必须等于冻结任务查询，或来自实际已读notice JSON的query（不从隐藏预期答案推断）。search_index沿用普通大小写不敏感字面子串检索，追加opaque search_receipt_id、collection_id/coverage、input/snapshot/index observations/report version摘要、明确file_ids=命中、原文excerpt/source、不可搜索状态及范围限制，私有保存搜索收据。

submit_report要求实际本会话搜索收据、相同当前集合/覆盖/query/版本/索引和完全一致命中ID；错填/漏填/多填、陈旧集合、错误query/kind、没有搜索均拒绝，不生成成功report。有效report.json内保存完整搜索收据，artifact摘要重新计算，原完成守卫只认实际合法提交。图片未OCR、PDF前两物理页/每文件至多6000字符、无字面命中不等于语义不存在均明确。自动封装是两组共用普通程序功能，不算Motif学习或语义判断。

## 读取库兼容与版本边界

select_files/pin_file/read_file/collect_reads四方法与原CollectionScene是同一函数对象，未覆盖、未改变返回或参数/schema；原file_tools.py/common.py/collection_tools.py字节保持。读取控制图execution_version_sha256继续指向这三份实际继承依赖，报告层单独report_execution_version_sha256绑定新report_tools及继承图摘要。全实验source_code另冻结所有场景/适配/TS，不能将继承图版本当整个服务版本。

因此本阶段复制第五阶段已认证L1/L2原字节，不手工改摘要或冒称新学习；四工具schema和实际SDK路径须核对。新契约不是L3，没有用新留出重新训练，旧证据/失败保持。新Task的input/prompt/current source scopes重新绑定。报告以外写步骤均由普通Harness执行；完整基准使用既有FileScene副本权限/预览/日志/恢复，不冒称单独PlanScene的持久化能力已被组合进L2。

## 验证与证据

新增7项负/恢复测试：检查集合混入时无交付后正确恢复、提前/错范围索引、query/receipt/kind/重复ID绑定、空命中、陈旧集合/外部字节变化、空query拒绝、继承读取实现/版本一致。check-report-contract.py用实际stdio MCP对三种新查询检查错误范围/集合/kind拒绝与正确收据；check-report-sdk.py用本机脚本Provider和实际SDK/MCP检查H/L1/L2及陈旧input，0云请求，脚本不进入训练。回归/付费质量/基准结果随后追加。

report_study.py首次准备冻结36次新质量留出与144次完整基准，父库hash/锁/执行源码/材料/input/prompt/schema/顺序不变才启动。36质量全部完成且主H/L2各12/12合格才通过预登记质量门；否则保留本版本并另建修复版本，不先跑基准。完整基准24条件=12原流程×2新材料条件，两组各3次、每组各36次先执行；未知/未覆盖结构仍普通模型，不为触发库而读无关文件。

单题5USD、96步、输出4000；180次理论上限900USD受系列1000保护，全部拒绝/修正/失败/恢复和HTTP计费。仅生成/复制testpdf实验副本；Office/图片二进制复用已QA模板，没有新作者化或版式变更。实际账单/人工盲评/维护工时未完成，不将机器后置检查推广为真实办公/科学质量。

## 第二版：显式源阶段守卫，重新学习认证

第一版e1f92d4d的30任务14合格/16失败，USD0.333062184；收据本身与选定集合匹配，但模型曾把stage_a加stage_b作为第二集合，目标范围错误，质量门失败。该版在下一个不同条件调用前停止，保持原源码/输入/费用/失败；144基准未启动。副本工作标记作为安全停止控制已恢复，控制过程/最终副本/原事件保留。

新7c213732使用sss-file-report-v2，report_contract.inspection_stages字段分别定义path_prefix与可选extensions或extensions_notice_path。select_files先检查没有未汇总的集合、当前阶段存在、file_ids恰好符合声明前缀及实际已读notice扩展名；错误调用在集合创建/读取前拒绝，成功后调用原CollectionScene方法。它是两组共享的任务范围校验，不是Motif学得选择、不执行文件指令或预先选择第二阶段。

select_files已覆盖，旧“继承四方法/读取版本不变”只描述第一版。第二版读取执行版本升级为report_version（绑定新report_tools及原三依赖摘要），task_scope明确记录新版本，源工具description重新绑定；pin/read/gather实现不变。旧L1/L2保存ancestor文件，禁止摘要替换使旧证书适用。新3普通训练/2独立认证构L1，6新L1经验/3独立认证构L2；控制语法仍受限，同形图的版本重新学习认证不能冒称任意新图发现。L1 learning-lock在新经验前冻结，L1/L2 library-lock在零质量/基准时冻结。

538Python/132Node通过、3Docker跳过。新增在创建集合之前拒绝首阶段/第二阶段混合、完成后额外阶段的测试；原错误报告、query、空命中、陈旧状态检查保留。源守卫改变MCP服务而不修改TS在线内核/共享CLI/预算/上游Harness，原14工具顺序及参数名保持（源description/执行版本改变）。具体源码改前快照在.local/file-management/interface-before-report-v2-20261013，冻结版本和新证据各保留，不把目录完整Git diff称本阶段增量。

第二版194任务理论970USD受全系列1000保护；含第一版失败累计估费USD1.790679000后仍有足够理论余量。所有新经验费用、守卫拒绝、模型修正、质量失败与基准失败均计入，完整分析同时报告共用契约修复与认证图跳过，默认SDK/Web不开新策略。

## 第三版：盘点检查集合与当前效果结果分别提交

第二版7c213732完成14次，9合格/5失败，133HTTP/USD0.113065740。3普通训练/2认证L1均合格；6新L1经验仅1合格，其他报告只列第二批成员而遗漏首批，3字面检索认证合格。新残余支持不足两个独立任务，L2编译明确拒绝；没有伪造第二支持或把失败任务纳入训练，未运行该版新质量/基准。旧L1、五失败、编译异常/源码/HTTP/最终副本保留。

第三版d3053cd5升级sss-file-report-v3，report_kind增加inspection：完整完成声明集合后，file_ids必须恰好包括每份collect_reads.files的全部实际成员（含先前上下文），且没有集合外读取，才能发布。report.json额外保存实际inspection_receipts；错填只列第二批/提前提交拒绝且不生成成功收据，模型可以纠正。task_result用于写操作等当前文件结果，literal_search继续仅命中集合；read_task暴露具体种类/字段含义，提示也分别表达三类，检查集合不再与检索集合或移动后身份混用。

报告代码升级使受保护执行版本改变，再用新的原生3训练/2独立认证和6新L1经验/3独立认证获取新L1/L2，未编辑旧摘要。14次均合格，无工具错误；新库零留出前冻结。第三版新质量数量7/9、9/13、8/11，查询Frame{8}、GRAPH、missing<92>，新文本/目录/通知及另冻结完整24条件；保持194次理论970USD与全系列1000保护，启动前245次/2173HTTP/USD1.903744740估费。

540Python/132Node通过、3Docker跳过；新增完整检查集合拒绝/恢复及未完成阶段拒绝两项，原8项负检查保留。实际MCP三查询新拒绝/正确回执检查0云请求。三个版本各自冻结/失败不覆盖，变更前记录在interface-before-report-v2/v3-20261013；新服务与旧FileScene权限/报告分开，仍无上游Harness/TS内核/预算代理变化。

## 完成、费用与最终证据

第三版14获取/认证和36新质量全部合格；实际SDK H/L1/L2两集合11/8/5模拟请求，L2陈旧input11/零续接，0云请求。九成员第二段正确产生5批；辅助检查旧三批常量的免费失败及修正源另存，未改变冻结运行规则。原调度器失败状态与继续阶段记录分别保存，已有日志不覆盖。

预登记门通过后完成144基准，H60/72、L2 62/72；60共同合格配对610→401HTTP、估费−16.02%。9重命名文件目标错误、12转换/1分类严格读取范围失败主验收全部保持失败；事后已有文件后置诊断只用于解释范围与实际文件结果差别，不替换主口径。完整基准再入batch为0，不能把首集合收益称为跨全流程再入增量或认证相对手写脚本优势。

第三版194次/1799HTTP/USD1.495762620；加两负版本，本次238次/2279HTTP/USD1.941890544，全系列439次/3972HTTP/USD3.399507360峰值估费，实际账单未知，68累计主验收失败保留。详情及逐项失败：[完整结果](../experiments/file-management-report-benchmark-20261013.md)。

独立审计194次通过Source/input/prompt/schema/原事件/实际参数/HTTP/tokens/费用/两库锁/效果来源/最终副本，1985读取/33搜索收据重放、5普通见证及7续接见证重算，无质量/基准训练。统一11实验433图/13076节点，4104Runtime节点排除学习；scalar观察器不认证新图。新原始文件与效果产物读取都按pristine或有操作日志来源的retained-final重放，未改变验收来使失败通过。

六辅助脚本的完成源与SHA在第三版analysis-source，v2/v3精确前后patch/摘要在shared-interface-revisions.patch/json，付费/学习源码在frozen-source；旧调度器源码/SDK失败/停止控制/学习排除记录另留。完成后文档更新只改变场景README的当前冻结hash；已有paid attempt不覆盖，重现用归档源码或prepare新版本。默认SDK/Web仍关闭新服务/策略，没有外部部署/提交/PR。
