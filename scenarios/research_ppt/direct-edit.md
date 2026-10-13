# 明确页修改：零模型直接入口

明确知道页号、字段及新值时，可直接修改本场景生成的稿，不需要让 DeepSeek 再决定如何调用工具。入口使用 TypeScript 客户端连接现有真实 `mcp-adapter.js`，调用 `read_deck_plan`、`revise_delivery` 和结果核验；后者仍由 `DeliveryAdapter.reviseDelivery` 执行局部修订、非目标页保持及真实渲染交付。Python 模块只选择当前解释器并启动 Node，不增加 Agent 循环。

这是普通确定性工程路径，**不是学习的新 Motif 或 RSI**。代码路径不启动 Harness 或 provider，记录 `model_requests=0`、输入/输出 token 为0；记录依据是该入口没有模型调用路径，不能冒称 API 账单代理实测或自动节省了某个固定请求数。CLI 所用 MCP 与渲染仍有耗时和维护成本。

## 使用

先安装场景依赖并构建。真实服务器先激活项目环境，保留项目 Node wrapper 与 `FONTCONFIG_FILE/PATH`；该入口及两层 MCP 仅传工具链和字体白名单，不传 API 密钥。

```sh
source .local/activate.sh
npm run build --prefix scenarios/research_ppt
python -m scenarios.research_ppt.direct_edit --help
```

准备私有 `updates.json`，内容必须是精确的新值；不会解释“更学术”“缩短一点”等自然语言要求：

```json
[
  {"page": 2, "changes": {"title": "明确的新标题"}}
]
```

默认预览，不改 PPT。`--job`、`--updates` 和输出都必须在本仓库 `.local/`。`--deck-id` 来自同 job 的实际交付结果。

```sh
python -m scenarios.research_ppt.direct_edit \
  --job .local/research-ppt/jobs/<job-id>/job.json \
  --deck-id <actual-deck-id> \
  --updates .local/research-ppt/edits/updates.json \
  --out .local/research-ppt/edits/<new-preview-id>
```

预览给出每个字段原值/新值、目标页、原稿 SHA、模型预算0和新副本影响，并写入私有 `preview.json`。确认后显式加 `--apply`，同时携带预览中的 `original_sha256`，防止误用已变化的稿。输出目录必须是新的；不会覆盖预览包、已有文件或原稿。

```sh
python -m scenarios.research_ppt.direct_edit \
  --job .local/research-ppt/jobs/<job-id>/job.json \
  --deck-id <actual-deck-id> \
  --updates .local/research-ppt/edits/updates.json \
  --expect-sha256 <preview-original-sha256> --apply \
  --out .local/research-ppt/edits/<new-apply-id>
```

成功输出 `revised.pptx`、`revised.pdf`、所有 `slide-XX.png`、`receipt.json` 及真实 MCP 调用记录。保留后端原位置的新 deck，便于后续同 job 修订；导出包是经过 SHA 核验的副本。原稿 SHA/计划、实际新稿计划、非目标页 OOXML/notes/media/styles 保持和 PDF/PNG 均核验后才导出。不自动重试或缩短内容；失败保留私有收据和后端报告，交由调用者处理。

## 支持边界

- 仅支持**同 job 生成且保留完整计划**的稿。任意外部 PPTX、只做 restyle 没有生成计划的稿不支持；不接受 `--pptx` 或自由描述。
- `changes` 可指定 `title/bullets/sources/notes/image/table/chart/layout/comparison/process/takeaway`。所有值仍受公开计划容量约束；来源和图件必须是本 job 批准的有效句柄。
- 未指定字段保留。可选 `image/table/chart/layout/comparison/process/takeaway` 只有显式 `null` 才移除；改变 layout 但未清除冲突媒体会拒绝。
- 原 job 必须已经 `allow_output=true`；`--apply` 不修改 job 权限。来源、job、checkpoint 或工具实现版本改变均由既有守卫拒绝；不会重签旧 checkpoint。
- 默认预览仅调用读取计划，不生成新 PPT/PDF/PNG；MCP 初始化/审计记录仍可能写入私有运行区。
- 修改科学主张、数字、条件或引用时，入口只忠实执行明确值，不认定其科学正确；机械验收不是独立视觉/科学人评。
- Windows 协议与薄启动器可单独检查；真实 MCP→LibreOffice 字体渲染是否可用需各环境实测，不能以单元测试宣称跨平台交付稳定。
