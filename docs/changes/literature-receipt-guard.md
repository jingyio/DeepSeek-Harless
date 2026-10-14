# 单个引用凭证与完成收据守卫：GitHub提交说明

原生轨迹曾出现两类问题：模型把字符偏移猜成quote_id，以及只说“接下来补读”便结束，未发布任务产物。本轮增加精确引用寻址和有界完成性检查，保留全部语义判断、失败/恢复费用和原生轨迹；没有新增learned Motif，不将续接算作模型跳过。

## main同步与分支状态

已fetch并检查远端main `bc1ecd5ba17fa4f12b2d2eaa780d72b5076b79cc`。本地此前没有main分支，现已建立main并跟踪origin/main，两者提交一致。工作目录仍在feature/rsi-research-agent/HEAD2368235，未切换、reset或覆盖场景未提交工作。

将main新增的23个文件及5个原本无本地改动的文件带入当前开发目录；package.json、scripts/project.mjs按字段合并，保留build:continuation、UTF-8环境和原测试；README、接口和交接文档保留文献场景记录。没有宣称已经执行完整Git merge或把修复提交到main。回退备份和逐文件来源位于私有upstream-sync.json及before目录。

同步包含官方Web启动器、动态任务请求/插件、任务与启动双层预算、预览确认桥接及已有测试。npm run scenario保留，npm run web/web:real与main同义；.env自动加载不打印值。实际模型测试仍沿用用户授权，产品Web保持任务预算预览确认，无科学结果的人工审批步骤。

## 新增共享接口（编辑前已向用户列出）

1. `src/adapters/scenario.py`允许一个可选严格字段completion_guard：tool必须在allowed_tools内，statuses为1–4个有界状态名，max_continuations为0–2整数。未配置的场景不改变行为。服务端加入固定插件路径和项目.local产物根目录，不能从请求任意指定插件或扩大工具范围。
2. `src/adapters/dsh_completion_guard.ts`使用现有公开agent/turn-stopping、Agent.steer和tools/result接口。只接受指定工具的成功结果、允许的状态、私有常规文件及其规范JSON SHA一致的收据。错误、pending、模型文字和承诺不算完成。收据存在/哈希验证不是科研语义认证；原场景collector继续检查任务、来源和权限。
3. 缺收据时最多两次同Session、同turn续接，消息source.kind明确为task-completion-guard；预算/请求计数不重置，不伪造Human输入、工具调用、成功或skip。耗尽抛TASK_MISSING_DELIVERY_RECEIPT，取消不产生续接。每个Agent拥有独立状态；Web每任务新Session，状态不能从上一任务继承。
4. `scripts/harness-web.py`将prepare_scenario.agent_plugins带入官方preset，与SDK加载同一策略；快照记录新插件代码SHA。保持main已有单任务执行槽、Session隔离、总预算和模型守卫，不修改上游Harness、SDK依赖或Web思考模式权限。
5. `scripts/run-scenario.py`指标增加completion_guard_enabled/completion_continuations，直接从原生插件来源消息计数。新消息仍产生真实模型请求，照常记入费用；不是Motif验证跳过。

main已有mcp_rows/environment_references、State.request_limit、create_server.state_selector和Web接口按main同步，未另造一套在线预算或Agent循环。新在线插件用TypeScript，要求支持原生类型剥离的Node（本机22.22.2）；没有修改node_modules。用户报告的服务器22.23.3/Python3.10.8及main验收记录保留，不冒充本轮服务器验证。

## 文献场景接口

- `read_pinned_pdf_context.quote_spans`新增citation_id，绑定任务、已读来源、来源版本、原文片段SHA和原quote_id；必须实际读过才能解析。重复读保持同一凭证，不做模糊补全或替换未知引用。
- preview_research_notes及submit_claim_repair接受`{"citation_id":"cite-实际返回的ID"}`；旧source_id/quote_id和原preview的verbatim quote仍兼容。发布前只将引用寻址规范化成原有source_id/quote_id结构，原生模型参数不修改，后续依赖图、引用重放与修复接口继续使用原结构。
- 跨论文、跨论断、未读、未知凭证和文件变化仍拒绝。支持锚点、数值/技术名、字符与额度边界不放宽，字段内容和研究取舍仍由模型决定。新增引用字段会增加工具返回上下文，不能直接宣称Token/费用下降。
- pdf-scenario和pdf-repair-scenario启用完成守卫；两个提示优先复制单个引用凭证，并要求实际提交。阅读运行快照及契约/frame摘要绑定守卫SHA，代码变化不能直接沿用旧结果/认证。解析偏移和磁盘解析缓存profile仍为v3，没有人为升级旧引用。

## 前端与思考模式口径

用户已澄清：最终产品使用自己的前端，暂时可用官方Harness Web。模型、MCP、完成守卫、预算、记录属于后端；更换前端不应重写它们。现有文献agent.ts工作台继续承担每任务生成冻结PDF输入→SDK阅读/复核/交付。

main的官方Web已有动态任务，但文献MCP的目录和研究问题当前从冻结任务文件加载；尚未完成其与/tasks任意新研究问题的逐Session绑定，不能把通用Web验收说成文献产品已迁移。后续需明确这项接入，不接受浏览器本地路径或串用旧问题。

当前SDK与Web都固定off；官方Web还拒绝选择其他effort。因此本轮不报告思考模式比较。后续冻结同一论文/问题/工具/质量门槛，比较Harness off/high与各自加Motif的组，分别记录实际请求配置、思考/输出Token、失败、总费用和交付质量。前端只作为共同入口，不能用界面按钮代替后端实测。官方参数依据：[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 验证与回退

回归、SDK故障注入、Web两独立Session有界失败、真实三论文任务、缓存和完整失败账目见[实验记录](../experiments/receipt-fix-20261012-9c6d79d9.md)。没有提交/推送/PR，私有论文、Key、原始日志不入Git。

回退共享变化需恢复scenario/guard/Web preset和SDK指标，删除场景completion_guard字段并恢复引用入口/提示及相关测试；main分支跟踪可保留。回退不删除原生事件、拒绝提案、账本或用户PDF。旧Motif/依赖若执行或契约版本变化，须重新验证/认证，不能强制沿用。
