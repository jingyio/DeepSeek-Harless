# 通用 MCP 操作图 RSI 与默认 Web 验证

2026-10-15，`feature/rsi-research-agent`，基线 `fcdcc48`；所有新改动本地未提交、未推送。通用协议、具体权限/参数及入口见 [接口实施记录](../changes/generic-mcp-operation-rsi.md)。

## 问题、设计与边界

验证能否从正常任务中的真实参数流学习不同长度的 MCP 图，由新库参与后续任务，继续学习更长结构，并接入既有 Harness Web。允许合格图自动激活，完整净收益仅观察。禁止用 profile_id、预写正确路线、模型生成调用或最终留出作为新边的学习证据。

这是授权文件副本上的机制开发实验；复制/移动/转换/归档/隔离、结果读取、报告由真实 DeepSeek 与原 MCP 文件效果完成。材料由原已授权副本/五类生成文件准备，认证再次复制并对非空文本添加独立 nonce；不同格式并非全部内容重新生成，不能把它当独立办公业务或语义泛化评测。最终留出未打开或用于学习。独立程序验收检查实际字节与轨迹，人工盲评/科研理解质量未评审。本轮没有重做 H/脚本/冻结库/RSI 全量成本对照，不主张稳定净收益。

## 执行配置与复现

沿用原 `deepseek-flash` / DeepSeek API 私有配置，reasoning off、无压缩、固定实际 MCP schema。每原任务 USD5 /96 步和 HTTP /4000 输出 /最多2次验收修复；系列 USD1000，单流学习池 USD25。502/503最多2次同任务重试，失败 HTTP、未知 usage 和保守估费都计入原限额。认证费用并入学习池和系列；账单实付未核实。

新文件入口为 `operation_tools.py` 和独立 operation_contract；15工具的实际 schema/_meta、任务/source/runtime/learner摘要、有效配置、原生事件、账本、库快照及认证源文件均封存在私有 enrollment 中。Python 编译、TypeScript 在线续接；未修改上游 Harness 或原发布 collection/reentry 执行器与证书。

```sh
# 先准备/冻结；输出实验目录，不付费
node scripts/project.mjs python scenarios/file-management/operation_study.py
# 在已授权模型/预算内运行新任务及自动认证
node scripts/project.mjs python scenarios/file-management/operation_study.py --experiment <新实验目录> --call-model
# 默认 Web 免费真实 Harness/MCP 检查，包括在途取消
node scripts/project.mjs python scripts/check-operation-web.py
# 真实 Web 使用已认证库、新五类资料副本和既有任务API
node scripts/project.mjs python scripts/check-operation-web-live.py --rsi-config <私有rsi.json> --call-model
# 只读审计：含训练原生来源、独立证书、实际交付和全部API费用
node scripts/project.mjs python scripts/audit-operation-rsi.py --state-root <私有state> --experiment <文件实验目录>
```

已完成的严格版本文件流为 `.local/file-management/fm-operation-rsi-20261015-a3adca6c`，库在同名 `.local/rsi/`。`protocol.json`、`protocol-lock.json`、`frozen-driver.py` 及每次 enrollment 的源码副本绑定实际执行。`independent-file-phase-audit.json` 在接 Web 前冻结，后续总审计另存，不覆盖。

## 全部真实开发批次

| 批次后缀 | 真实执行数（含认证） | HTTP | 代理估费 USD | 结果与负面证据 |
| --- | ---: | ---: | ---: | --- |
| `04b85c64` | 6 | 52 | 0.022857660 | 普通交付6/6；空库缺审计文件使6个 worker失败，0激活；保留全部错误与费用。 |
| `ee34fb33` | 12 | 106 | 0.048132804 | 普通交付6/6；2个两节点图独立认证激活；1次普通任务验收修复，不能进干净训练；列目录打断更长发现。 |
| `bfd735a4` | 18 | 143 | 0.074790960 | 普通交付6/6；当时认证2/3/5节点图，后续审计发现失败调用被采集器省略。3/5节点图事后明确停用，旧证书/事件不改；另一2节点候选因认证完成次数不符拒绝。 |
| `a3adca6c`，严格失败边界 | 18 | 139 | 0.071073120 | 普通交付6/6，全部0验收修复；新2/5/3节点图独立认证激活；另一个2节点候选保守拒绝。 |

四批文件流共54真实执行、440 HTTP、USD0.216854544；认证、未激活候选和旧缺陷费用均包含，不能只报告末批费用。四批已封存 HTTP 均200；工具读取失败仍在原事件中，不能据此称无失败。

严格版本的递归来源：第一图 `preview_actions → execute_plan` 从两份普通新任务的真实 plan_id 关系学习；已认证前缀在转换/归档任务实际执行后，模型新增实际 receipt 检查、产物 pin/read 决定；两个独立新轨迹支持 `preview_actions → execute_plan → inspect_plan_result → pin_file → read_file`，新边索引2/3/4均为原生模型，原生成节点1仅证明旧前缀。新图再经过1次新原生见证和2次隔离候选执行激活，后续复制任务实际复用4次结构续接。另有3节点结果读取后缀独立认证。

严格文件流139 HTTP估费USD0.071073120，其中认证等学习费用USD0.050325624，普通任务费用USD0.020747496；累计运行耗时310.706秒（不含全部开发/人工时间）。输入缓存命中629120、未命中89912、输出33604 token。不能将最后任务的跳过次数直接换算为已证明的费用节省。

两个版本的额外 `pin_file → read_file` 候选被拒绝，原因是隔离认证预先要求每任务恰好完成一次图，而模型在原件和产物各读取一次，出现两次完成。交付本身合格，认证程序仍按原冻结标准拒绝，没有改标准让它通过。这是当前认证对同一图重复出现的保守限制，费用与 failure.json 全部保留。

## 默认 Web 真实结果

真实默认 Web 使用同一个已认证私有库，新的服务端登记副本包含 txt、docx、xlsx、PDF、PNG。实验 `.local/file-management/fm-operation-web-20261015-2a29f297`；宿主 `.local/web/runs/2a29f297d1af46848cac01644a5944f9`。用户目标经既有 preview/submit 路由实际交给 Harness，不传正确模板 ID。

| 新目标 | 真实 HTTP | 验证的模型请求跳过 | 实际交付 |
| --- | ---: | ---: | --- |
| 文本复制并读取产物 | 6 | 4 | 合格 |
| 移动，只核验回执 | 7 | 1 | 合格；没有额外结果读取授权 |
| Excel转CSV并读取产物 | 6 | 4 | 合格；独立核对真实表格行 |
| PDF复制并读取产物 | 6 | 4 | 合格；原PDF不变 |
| 图片隔离并读取产物 | 5 | 4 | 合格；元数据读取范围保留 |

5/5完成、0验收修复，30 HTTP200，17次结构续接经实际工具结果验证；USD0.020767548。每任务均封存真实生命周期、原MCP schema、接受结果和完整账本，自动进入同一worker队列。当前已有图完整覆盖这些机械后缀，没有声称Web又学出新图或新增激活；源码/使用证据和队列检查通过。原登记目录、实验原PDF与全部任务前材料保留。

严格文件流加Web共23次真实执行、11/11普通交付、169 HTTP、USD0.091840668，学习费用仍USD0.050325624。23份预算预留全部结算，没有遗留在途任务；综合独立审计 `independent-combined-audit.json` 通过，当前源码闭包匹配。新版本库保留3个active条目，代数4；本机定位 `.local/rsi/operation-current.json`，原只读库指针不改。

**本轮总计59次真实执行、470 HTTP、代理估费USD0.237622092**，包含前述全部旧版本缺陷、失败候选和认证。全文件系列1084尝试/10888 HTTP/估费上界USD8.251297232，按USD1000上限余USD991.748702768，实付未知。费用不是把跳过次数乘某固定单价得到；未计算开发人工成本，也未证明完整净收益。

## 免费验证、失败与保全

- 当前完整回归：632 Python通过；Node 211通过、3可选Docker跳过；smoke通过（真实MCP/免费夹具，不产生云费）。有意义的新增检查覆盖异名 MCP、分叉依赖、继承前缀/新原生边、失败调用屏障、循环/常量拒绝、授权/范围/schema/版本失效和有限503重试。
- CLI/SDK/MCP模拟 Provider：10请求普通执行与6请求/4真实结构续接的受限图夹具通过，显式 mock 不训练、不作为云端收益证据。
- Web API免费检查：两任务复制/移动交付及轨迹/费用封存通过；越界路径、错误格式和转换权限拒绝；取消在途请求后完整结算并封存 cancelled 记录，不训练、不重置限额。模拟运行不计入真实费用表。
- 初期免费失败保留：不合法 pin auto_continue 声明、误用只读 bootstrap 质量程序、MCP env 引用未解析、Web fixture计数字段缺失。分别在新材料/新版本重验，没有覆盖旧输出。
- 实际修复：空库也写 runtime_ready 审计；允许明确声明的安全只读穿插但不计跳过；保留失败/未知工具调用为图屏障；读取明确区分file_id与source_id；Web终止使用实际 task_terminal 事件、在途结算后才能封存；同任务502/503最多两次重试。
- 开发归档 `.local/general-rsi-development-20261015-244a9c2b` 保留本轮之前113个脏/未跟踪源码副本、逐文件改动diff、完整检查日志和历史保全清单。267609个原私有文件保全检查通过：267608逐字节不变，1份原JSONL仅追加、原完整前缀SHA保持；原PDF与旧最终集未改。最终源码/diff/保全结果以归档final.json为准。

## 结论和后续范围

当前支持的结论是：工具名无关的有界标量 DAG 学习接口已实现，文件管理普通运行中的两代新图能够自动发现、独立认证、发布并由后续任务使用。服务端明确声明的原授权写操作已参与，不再只限两类只读图。默认 Web 的同一任务 API 接入实际复用与任务后学习封存。

其它 MCP 仍需真实的服务端权限/材料/验收适配器；本轮没有授权或验证外部应用写入。2–8节点标量图、明确语义入口和有限穿插不等于任意循环、集合变换、任意新流程全部自动学会。新操作服务的跨进程恢复、多个产物的唯一句柄、重复图认证和浏览器视觉交互仍有独立验收工作。稳定完整净收益继续记录，不作为目前合格激活条件；本轮不能宣称通用RSI全部完成或生产上线。
