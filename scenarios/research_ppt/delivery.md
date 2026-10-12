# 科研 PPT 可靠交付入口

该入口在原有 V6 场景之外，提供固定工具集合的同 job 重启恢复及 TypeScript 有限交付适配器。普通场景的 RSI/布局接口仍使用原 `server.py`。新增入口不启用 V7/V8 未晋级的 claim 生成工具，也不分发私有来源、轨迹、凭证或旧认证 manifest。

这是本次公共移植版，需要以本次服务器回归记录判断验证状态。历史 V7/V8 真实实验使用 `.local/` 冻结代码及 SDK 1.30.1，不能把旧成绩冒称新路径已验证。新场景显式固定 MCP SDK **1.32.1**；根 DSH 的原依赖没有随此场景变更。

## 安装与直接 MCP 入口

先完成仓库固定安装及 Python 环境；场景另需 Linux 上的 LibreOffice、Poppler、字体、PyMuPDF/Pillow 等已有渲染依赖，详见 [场景 README](README.md)。新入口完整依赖仍包含 Python 工具后端，不代表基础插件已经无 Python。

```sh
npm --prefix scenarios/research_ppt ci
npm --prefix scenarios/research_ppt run build
python -m scenarios.research_ppt.cli prepare --help
```

使用公共 `cli.py prepare` 准备任务，默认预览；明确授权后加 `--allow-output`。来源应先复制到受保护的仓库 `.local/`，任务/产物只允许位于该目录。

```sh
python -m scenarios.research_ppt.cli prepare \
  --input .local/research-ppt/input/paper.pdf \
  --instruction '根据论文生成6页可编辑汇报，每页保留来源与notes' \
  --slides 6 --allow-output
node scenarios/research_ppt/dist/mcp-adapter.js --job .local/research-ppt/jobs/<job-id>/job.json
```

第二条是 stdio MCP 服务，由调用方通过 MCP 连接，不是交互聊天界面；本入口没有自建 Agent 循环或模型调用。它可以被现有 Harness 自定义 MCP 配置启动。`SSS_PPT_DELIVERY_PYTHON` 或 `SSS_PYTHON` 用于指定工具后端解释器。服务只启动固定 `delivery_server.py`，自定义 `--backend` 不能指向任意 Python 脚本；`--root` 必须与安装场景所在仓库一致。

`--export-schema .local/<目录>/schema.json` 输出真实后端加适配器 MCP schema 快照，目标父目录须已存在且输出文件尚不存在；该快照属于私有运行配置。

## 四个新增工具的责任

V9 `python -m scenarios.research_ppt.cli run --job ...` 默认启动本入口；无 `--call-model` 仍只预览。正常生成的 `--execution composed` 使用 `render_delivery`，局部修订由模型按实际任务选择 `revise_delivery` 或逐步工具。`--runtime legacy` 显式恢复旧内存入口；RSI提案使用原服务，旧动态目录工具不在本入口加载。

`prepare --document-cache` 开启普通B1内容缓存，默认关闭。键包含来源SHA、解析/几何schema及实现、Python/相关库版本；读取时核payload/版本，损坏重算。每个job仍独立批准输入并创建未读句柄，缓存不授权调用、不恢复科研结论。cache命中不计模型请求旁路。

科学直接结果可用 `python -m scenarios.research_ppt.evidence_audit --job ... --sidecar ... --out ...` 独立审计，侧表协议见 `evidence.schema.json`。没有独立人审事实时返回unknown；与来源摘录一致也不能自证科学正确。当前侧表未绑定PPT可见内容、未接入交付质量gate，报告显式记录这些限制。

| 工具 | 输入 | 执行与边界 |
| --- | --- | --- |
| `render_delivery` | `plan` | 固定页数与机械容量预检，实际 render→inspect→validate→deliver。普通有限组合脚本；不自动删内容、补页或重试。 |
| `revise_delivery` | `deck_id, updates:[{page,changes}]` | 新副本局部修订、非目标页 OOXML/notes/media/styles 保持、实际渲染验收交付。原稿保留。 |
| `pin_deck_pages` | `deck_id,pages_csv`，例如 `2,5` | 固定调用者明确选择的页面，绑定 PPT SHA、来源版本及选页投影。不会选择相关页。 |
| `read_pinned_deck_pages` | `source_id` | 复核当前版本后返回明确页面的完整结构化计划，不修改内容。 |

前两个工具 `read_only=false`，后两个为只读。四工具契约见 [delivery-contracts.json](delivery-contracts.json)，版本字段见 [delivery-version-fields.json](delivery-version-fields.json)。契约输出列描述成功路径；失败返回错误，不将文件存在当交付。

`version_sha256` 使用与 Python `PPTService.input_version` 一致的 job 输入 SHA 列表编码摘要；它不是单篇 PDF SHA。`file_sha256` 单独绑定当前 PPT，两者都要检查。TS pin 仅在当前进程内有效，重启旧 pin 拒绝，调用方需明确重新 pin。后端固定15个原始工具，TS按固定顺序追加4个。

## 状态恢复及版本兼容

`service-checkpoint.json` 保存同一 job 的纯 JSON 状态、已读来源/图件、完整计划、deck与validation。恢复同时绑定 job、权限、来源、宿主代码、实际构建产物及工具协议版本；摘要用于损坏检查，不是抵御有本机写权限者的签名。旧验证 PDF/PNG损坏时，只撤销相关validation，保留deck和计划，必须重新真实验收。

公共移植使用 checkpoint **schema 2**，明确区分公开宿主位置和版本依赖协议改变。历史私有 **schema 1** 直接拒绝；没有重签、路径重绑定或自动跨 job 迁移。历史代码与 checkpoint 保持私有冻结。新增/更新公共代码后旧checkpoint拒绝是版本守卫，不能删检查来继续旧任务。

## 无模型真实工程回归

所有实验在 Linux 服务器完成并留 `test-logs/`。默认诊断用 PyMuPDF 创建明确标注合成来源的 PDF，再调用公共 `cli.prepare`，无付费模型和假工具。

```sh
python -m scenarios.research_ppt.delivery_smoke \
  --out .local/research-ppt/delivery-smoke/<new-run-id>
```

输出目录必须尚不存在；诊断产生新任务、新 PPTX、真实 LibreOffice PDF及逐页PNG，验证TS→Python stdio MCP、明确局部修订和非目标保持、同 job 重启交付、TS重新pin、权限/版本/损坏拒绝及过期实例覆盖保护。`--job` 可指定刚准备、已授权输出且未运行的本次诊断任务；不要求历史私有 job/证书。诊断只变更本次新产物，不修改来源原件或公共代码；所有失败证据保留。

上述回归是工程连通性与恢复检查，不能证明科研事实、图件语义或审美质量合格，也不能证明成本下降。模型理解、选材与科学判断仍在语义层。只有从正常轨迹学得并经独立认证的 pin→read 结构，才能另行称 Motif；交付组合本身仍是普通脚本。
