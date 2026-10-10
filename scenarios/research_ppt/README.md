# 科研 PPT Agent

接收 1–8 份 PDF/PPTX、1–30 页要求与用户说明，目标是生成可编辑 PPTX，或将现有 PPTX 改为学术/组会风格，并提供真实 PDF 预览、来源与交付验收。

V6 已完成同一 MCP 会话中的可靠局部修订、真实 DeepSeek 生成图件目录工具及独立功能认证，并从正常工具轨迹认证新目录读取 Motif。新任务中一个 batch 实际执行两个读取工具，核验跳过一次完整模型请求。四组真实交付均有需修订的科研表述；尚不能计作统一质量合格或宣称稳定降本。结果、失败及成本见 [V6 实验记录](../../docs/experiments/research-ppt-v6-tool-rsi-20261011.md)，当前状态见 [交接](../../docs/handoffs/research_ppt.md)。

V4 的图像提取、受限样式修改、真实渲染核验与交付链已实现；两轮 5 题×三组共 30 个真实 DeepSeek 对照及逐页辅助审查已完成。历史来源读取 Motif、两套 15 页辅助修订稿及限制见 [V2–V4 实验记录](../../docs/experiments/research-ppt-v2-20261010-results.md)。生成/验收段仍是普通代码。

V5 已接入固定科研设计 Skill、原生可编辑方法流程与短结论，完成真实 DeepSeek 布局提案、训练回放、独立机械认证及服务器复验。原五题三组15次真实运行、两题反馈 pilot 六次、单独 QLoRA 精修一次均已交付并逐页辅助审查。布局认证仅证明几何和内容保持；设计质量尚未人工盲评，稳定同质量降本仍待验证。结果单列 [V5 实验记录](../../docs/experiments/research-ppt-v5-design-rsi-20261010.md)，不覆盖历史结果。用户已授权本轮结束后以中文提交到 `feature/research-ppt-agent`，提交前告知范围，不创建 PR。

## 部署与权限

全部实验和测试在服务器执行，所有测试日志保存到 `/root/autodl-tmp/xjj/test-logs/`。项目已有环境入口：

```sh
cd /root/autodl-tmp/xjj
source .local/activate.sh
mkdir -p test-logs
set -o pipefail
```

场景依赖见 [requirements.txt](requirements.txt)、[package.json](package.json) 与锁文件。当前 TS 构建要求 Node.js >=22；公共底座要求 Python 3.12。真实渲染需要 LibreOffice 与可用中文字体，PDF 预览/检查依赖需按当前实现安装并记录版本；依赖缺失不能宣称验收成功。输入论文先下载到本机，再上传服务器私有 `.local/`，保持用户要求。

新 Linux 部署先按根 README 安装底座，再安装场景依赖：

```sh
python -m pip install -r scenarios/research_ppt/requirements.txt
npm ci --prefix scenarios/research_ppt
npm run build --prefix scenarios/research_ppt
```

系统另需 `libreoffice-impress` 与 `fonts-noto-cjk`（Ubuntu/Debian 软件包名）；在部署机确认转换工具与字体可用。已有服务器环境不需要每次重装依赖。

`DEEPSEEK_API_KEY` 保存在项目受保护环境或 Harness 凭证存储，`DEEPSEEK_BASE_URL` 配置 API 地址，不在公共文件或日志写入值。默认 `reasoning_effort="off"`、关闭上下文压缩，付费前核对有效上游请求确实关闭 DeepSeek 思考模式。

准备任务时 `--allow-output` 授权写入该任务的私有输出目录；`--allow-rsi` 授权受限准入规则或布局策略提案/认证。默认运行只预览，显式 `--call-model` 才发起付费调用。付费预算必须先获用户确认；2026-10-10 用户已授权本轮实验不限预算，仍使用显式运行守护上限。原始论文、用户文件、密钥、运行轨迹与产物不提交 Git。

## 准备与预览

生成组会 PPT 的例子；实际路径替换为已上传的来源：

```sh
python -m scenarios.research_ppt.cli prepare \
  --input .local/research-ppt/inputs/paper-a.pdf .local/research-ppt/inputs/paper-b.pdf .local/research-ppt/inputs/paper-c.pdf \
  --instruction '将这三篇论文整理成15页中文组会PPT，比较方法与适用条件，保留主要实验图和来源' \
  --slides 15 --template lab --operation generate --allow-output
```

命令打印私有 `job.json` 路径；随后将它传给 `--job`。已有 PPTX 重风格例子，`--slides` 填写希望保留的实际页数：

```sh
python -m scenarios.research_ppt.cli prepare \
  --input .local/research-ppt/inputs/source-deck.pptx \
  --instruction '改为学术会议风格，保留现有页数、正文、图片、表格和讲者备注，生成新的可编辑文件' \
  --slides 15 --template academic --operation restyle --allow-output
```

`academic` 和 `lab` 是受限样式预设；V4 识别明确 placeholder 标题及受限的普通标题，转换已知装饰/表头色并保持文字与背景对比，核验原 notes 前缀、布局几何、媒体/原生图表及嵌入数据保留。模糊标题与未知用户底色不强猜。首版不等同于任意用户母版的完整导入；动画、SmartArt、复杂母版/布局仍需具体核验，不能保证任意文件完全无损修改。

```sh
python -m scenarios.research_ppt.cli run \
  --job .local/research-ppt/jobs/JOB_ID/job.json \
  --mode baseline --execution steps --budget-usd 1 --max-steps 40 \
  2>&1 | tee test-logs/research-ppt-v2-20261010-preview.log
```

此命令无 `--call-model`，只产生配置预览。`1` 是每次运行的防失控上限，不是预计费用。预算代理按请求上界预留，过小的上限可能在实际费用较低时就拒绝下一请求；本轮第二轮对照采用 `$1` / 40 步。日志与产物需为每个运行使用新名称/目录，保留旧结果。模型运行在该预览基础上显式增加 `--call-model`，仅在预算确认后执行。

## 工具与执行方式

| MCP 工具 | 功能与边界 |
| --- | --- |
| `list_inputs` / `pin_source` | 返回允许的输入，校验来源 SHA256 并解析，返回绑定句柄 |
| `read_source` / `read_page` | 读取正文/素材清单及指定页；被截断的正文要按需求补读 |
| `list_templates` | 列出支持的样式预设与约束 |
| `extract_figure` | 提取已绑定来源中的图，或渲染页区域；保留来源定位和图像版本 |
| `render_deck` | 将模型提交的结构化内容计划生成原生可编辑 PPTX |
| `restyle_deck` | 对已有 PPTX 的受限标题/装饰/表头样式做副本修改，保持文字对比，核验原 notes、布局与内容/媒体保留 |
| `inspect_deck` | 检查 PPTX 的结构、页数、可编辑对象和 notes |
| `validate_deck` | 真实渲染 PDF/预览并核验交付条件，缓存命中也重核文件 SHA；失败或缺依赖须报告 |
| `deliver_deck` | 重核 PPTX/PDF/PNG 与来源版本后登记交付；替换、删除及越界路径拒绝 |
| `build_delivery` | 普通组合操作，一次调用完成 generate/restyle、核验和交付；不是学得的 Motif |
| `rsi_status` / `propose_guard` | 通过受限 RSI 入口读取和认证准入候选，不允许任意代码执行 |
| `layout_policy_status` / `propose_layout_policy` | 只读训练诊断、提出完整七字段布局策略并真实回放；最多三次提案，不从 schema 合法自动启用 |

内容选择、叙事、科学结论和图表解释仍由模型完成。字符/几何与来源版本检查不能替代事实审查和每页视觉检查。原生文字、表格和生成的图表可编辑，嵌入论文原图仍是图片。

V5 普通生成会话默认将 [research-ppt-design](skills/research-design/SKILL.md) 全文追加到稳定提示前缀，记录 Skill SHA；`prepare --no-design-skill` 可显式关闭，不用于本轮三组对照。它吸收固定 MIT harness-anything 的通用工程思路并独立编写科研设计规则，许可及来源见 [provenance.json](skills/research-design/provenance.json)，不是学得的 Motif。

页面可选 `takeaway`（最多 90 字符）及 `layout="process"`、`process.steps`（2–5 项 `label/detail`，页级 `bullets=[]`）；流程文字、框和箭头保持原生可编辑。字段上限不保证排版容量：短标题、短结论优先，五步流程优先不用结论框，或保持每步解释约 20 中文字符。溢出明确拒绝，不自动删科研内容；实际限制见 [prompt](prompt.md)。

PDF 的嵌入图片可能只是阴影或遮罩，并不等于完整论文图。`read_page` 返回真实图注及几何候选，优先将 `candidate_id` 交给 `extract_figure`；包含矢量内容的完整图走页区域渲染。图片透明度合成到白底，明显空白和遮罩片段拒绝或过滤。图注定位只提供可追溯素材，不自动证明模型解释正确；复杂跨页图和 OCR 尚未验证。

三种实验组共享工具能力，区别在发起方式：

```text
A 普通逐步：--mode baseline --execution steps
B 普通组合：--mode baseline --execution composed
C 认证复用：--mode execute  --execution steps --manifest LIBRARY_MANIFEST
```

`shadow` 只观察匹配，不能计为实际跳过。现已验证的 PPT Motif 范围主要为 `pin_source → read_source`；新增生成/验证链需要真实训练、独立认证、匹配及副作用/版本守卫后才能成为在线跳过证据。当前结构专用入口会拒绝语义 embedding 匹配，不能假称已使用真实 embedding 完成新增链认证。

## 真实学习与 RSI

`learn` 使用至少两个独立训练运行目录和一个独立留出目录。每个目录须含真实 Harness 事件及已冻结 `task-identity.json`：

```json
{
  "train": [".local/runs/TRAIN_A", ".local/runs/TRAIN_B"],
  "heldout": [".local/runs/CERTIFICATION_C"]
}
```

```sh
python -m scenarios.research_ppt.cli learn \
  --dataset .local/research-ppt/experiments/research-ppt-v2-20261010/dataset.json \
  2>&1 | tee test-logs/research-ppt-v2-20261010-learn.log
```

真实评测禁止用模拟 Provider/工具生成训练轨迹。编译输出不等于新的在线能力已验收；检查 library、manifest、守卫、运行时支持与实际 bypass 审计后再报告效果。

`improve` 要求任务使用 `--allow-rsi`；`cycle` 按当前入口将预算分给任务与改进两段。规则候选只能在固定协议检查和独立任务验证通过后作为效果证据，提案和认证费用进入学习成本。V5 RSI 未生成工具；V6 在固定图件目录范围内生成真实 TypeScript 工具。任意工具自主发现及完整排版算法尚未实现。

### V5 布局策略学习与复现

先在 `.local/` 冻结历史真实计划资料集：`{"schema_version":1,"cases":[...]}`，每项为 `id/split/plan/sha256/run_id`；`split` 分为 `train` 与 `heldout`，`plan` 是历史 PPTX 同目录的绝对 `plan.json` 路径，须包含真实运行 ID 和对应 SHA。按本轮方案至少两个训练任务、一个独立认证任务；同一运行不能跨划分，留出不反馈给模型。准备任务时增加 `--allow-output --allow-rsi --layout-suite .local/research-ppt/v5/layout-suite.json`，后续 `JOB_ID` 替换为实际返回路径。

```sh
python -m scenarios.research_ppt.layout_learning \
  --job .local/research-ppt/jobs/JOB_ID/job.json --prepare-training \
  2>&1 | tee test-logs/research-ppt-v5-layout-training.log
python -m scenarios.research_ppt.cli improve \
  --job .local/research-ppt/jobs/JOB_ID/job.json --budget-usd 0.75 --max-steps 10 \
  2>&1 | tee test-logs/research-ppt-v5-layout-preview.log
```

第一条只做真实训练回放，不调用模型；第二条默认只预览，已获预算授权后增加 `--call-model` 才让 DeepSeek 提案。布局学习会话仅开放两个布局 MCP 工具；最多三次持久化提案，格式失败也计数。策略完整包含 `schema_version=1`、`media_position=right/bottom`、`media_fraction=0.50–0.72`、`body_columns=1/2`、`body_font_size=20–24`、`table_font_size=17–20`、`body_gap=0.08–0.28`，字号须整数。策略只能改变几何与字号，不能改文字、事实、notes、来源、页数、权限或验证器。

模型返回通过训练的冻结 `proposal_path` 后，显式独立认证：

```sh
python -m scenarios.research_ppt.layout_learning \
  --job .local/research-ppt/jobs/JOB_ID/job.json \
  --proposal .local/research-ppt/jobs/JOB_ID/layout-rsi/proposal-PROPOSAL_ID.json --certify \
  2>&1 | tee test-logs/research-ppt-v5-layout-certification.log
```

训练门槛为失败减少或原图平均面积提高至少 10%，认证须无回归、保留内容与真实 OOXML 文字/notes/来源。认证集只绑定一个冻结候选，不能反馈后换候选继续调参。证书再核资料、提案、代码版本及 PPTX/PDF/PNG 证据 SHA；`mechanical_certified=true` 仅是机械/几何代理，不证明审美或科研质量。新任务的 `prepare --layout-policy CERTIFICATE_PATH` 接受完整证书，不接受裸策略；五类枚举布局失败才回退默认策略，在新目录生成且保留候选失败证据。证书或依赖变化拒绝使用，不靠回退绕过版本守卫。

新矩阵默认预览，三组共享同一 Skill、工具和模型配置；缺有效证书时 `motif_rsi` 明确跳过：

```sh
python -m scenarios.research_ppt.experiment_v5 \
  --inputs .local/research-ppt/v5-inputs --certificate CERTIFICATE_PATH \
  2>&1 | tee test-logs/research-ppt-v5-matrix-preview.log
```

真实运行增加 `--call-model`；默认每 run 防失控上限 `$0.75` / 40 步、矩阵 `$15`，可用 `--task` / `--group` 选子集，`--resume` 恢复同版本且同为真实或预览的实验目录。五题是不同用户任务，不是五篇固定合成一个 PPT；支持 `--matrix` 提供其他题面。V5 原矩阵已完成五题三组共 15 次真实运行，P1/P2 审查反馈 pilot 另完成六次，原始记录及比较条件分别冻结；不把重复材料修订称为新独立数据集。

## 验收、日志与实验方案

底座的服务器检查：

```sh
npm test 2>&1 | tee test-logs/research-ppt-v2-20261010-npm-test.log
npm run smoke 2>&1 | tee test-logs/research-ppt-v2-20261010-smoke.log
npm run motif:check 2>&1 | tee test-logs/research-ppt-v2-20261010-motif-check.log
```

这些是工程/模拟诊断，不代表真实生成质量。真实文件验收须完成 PDF/PPTX 读取、原图/页区域提取、15 页生成、现有 PPTX 重风格、真实 LibreOffice 渲染、失败拒绝和交付版本绑定，并保存各项日志和产物。

最新方案与结果：[research-ppt-v5-design-rsi-20261010](../../docs/experiments/research-ppt-v5-design-rsi-20261010.md)。服务器通过场景 Node 17 项、Python 38 项，以及根 `npm test`（136 Python、29 Node）与 `npm run smoke`。真实布局学习为 3 次 DeepSeek 请求、1 次候选提案，独立机械认证通过；原图平均面积训练增加 18.10%、留出增加 21.53%，不能替代审美或事实评审。原矩阵请求为 96/103/81、总 token 为 3,281,023/4,461,354/2,958,970；独立 Motif 组成本增加，RSI 组本次总量下降，不足以证明因果或同质量收益。原 15 份共 138 页已辅助审查，14 份需修订、1 份未观察到重大问题；账单、人力及独立人工盲评仍未知。

修订仅补齐缺失 `bullets: []`，显式 `null` 或错误类型继续拒绝，保留来源/notes并记录规范化反馈。修复后两题 pilot 与原矩阵分别报告，真实模型根据相同审查意见重新生成；没有使用 Codex 代写成品。程序通过不证明科研内容合格。

V5 本机成果：`.local/research-ppt/v5-deliverables/original-matrix/` 含15份原稿、并排导航及29页八节报告；`post-review-pilot/` 含六份反馈修订稿及17页报告；`final-refined-examples/` 含 RAG 组会8页与 QLoRA 学术7页两份可编辑 PPTX、PDF及逐页图。两份样例经辅助审查未见重大/中度问题，仍有小问题，非人工盲评合格。所有成品、私人论文与原始证据留在忽略目录，不随仓库分发。场景 smoke 首跑模拟状态识别错误已修复并在服务器通过，失败与复验日志均保留。

以下为 [V2 历史方案](../../docs/experiments/research-ppt-v2-20261010-plan.md) 的保留结果：已执行真实训练 2 题、独立认证 1 题及两轮各 5 题×三组；第二轮使用修复后的图片处理与新的运行上限，单独记录，不能与首轮混合为同条件重复。R1 辅助审查 120 页、R2 127 页，每轮均为 10 个需修订、4 个未观察到重大问题、1 个无成品运行，非独立人工盲评。任务之间复用了部分论文与旧 PPT，不是五个完全独立来源集合；尚不能宣称稳定同质量降本。

最终 V4 场景在服务器通过 31 项 Python（29 项基础及 2 项预览守卫新增检查），Node 6 项此前通过且后续未改 TS；另有 4 项图片回归通过。日志保存在私有 `test-logs/`，预览守卫回归见 `research-ppt-v4-final-preview-guard-regression-20261010.log`。工程验证不能代替科学/视觉质量评审。

V2 真实 RSI 最终返回基础准入程序，未观察到新规则收益；首次运行有 6 次提案，超出当时仅提示的 3 次限制。服务端现已补充每任务持久的 3 次硬限制，schema 失败也计数，超限保留旧规则。后续先人工盲评，再比较包含缓存、失败恢复、RSI/学习和修订时间的总成本。

实现与下载来源见 [SOURCES](SOURCES.md)，真实历史观察见 [首篇对照](../../docs/experiments/research-ppt-real-baseline-execute-20261010.md)。未通过视觉/事实审查的产物写“质量未评审”，不能因为结构测试通过宣称降本。

## V6 可靠局部修订与真实工具学习

`read_deck_plan(deck_id)` 读取本任务生成并保留的完整计划；`revise_deck(deck_id, updates)` 接受 `[{"page":6,"changes":{"takeaway":"新结论","notes":"修订说明与来源依据"}}]`，在新目录生成副本。未指定字段保留；只有可选媒体/布局字段显式 `null` 才移除。非目标页通过实际 OOXML、notes、媒体、表格、图表、关联资源及共享主题/尺寸核验，否则拒绝候选并保留原稿和失败文件。修订稿须重新 `inspect_deck → validate_deck → deliver_deck`；旧 validation 只对应原稿。计划和 deck 句柄目前存于服务进程内存，仅支持同一 MCP 会话；重启恢复、任意外部 PPTX 的局部内容修改尚不支持。

离线工具学习入口默认预览：

```sh
python -m scenarios.research_ppt.tool_learning \
  --train-job TRAIN_JOB_A --train-job TRAIN_JOB_B \
  --train-run TRAIN_RUN_A --train-run TRAIN_RUN_B \
  --heldout-input INDEPENDENT_PDF --out NEW_PRIVATE_DIRECTORY
```

显式 `--call-model --api-env .local/deepseek.env` 才真实付费。需要两个成功正常 API 任务、对应唯一 PDF 和原始事件/账本，不能用诊断数据晋级。DeepSeek 输出候选 JSON 的 `name/description/input_schema/code`；宿主执行 AST 限制、实际 TypeScript 编译和 Node 模块运行，最多三候选，拒绝也计数。真实训练后由模型决定 accept/revise/stop；accept 后首次处理隐藏 PDF 做一次独立功能认证，失败不反馈用于继续调参。来源、响应、代码、schema、宿主和执行证据变化均使旧认证失效。

生成工具宿主需要完整安装场景 npm 依赖（含 TypeScript），不能使用 `--omit=dev`。本轮候选、证书、原始轨迹及新 Motif 留在私有 `.local/`，不随仓库分发；新克隆须使用自己的正常任务重新学习和认证。

功能认证目前针对全部真实图注候选的字段保持和排序，范围由开发端固定；模型提炼依据、编写代码及修复实现。它不能代替科学选图、论文理解或质量评审，也不是完全自主功能发现。`prepare --generated-tool-certificate CERTIFICATE` 在正常场景动态开放 `pin_figure_catalog(document_id)` 和模型命名的 `read_pinned_…(source_id)`；在线调用实际执行已编译 TypeScript，来源与结果另由固定 oracle 核对。人工脚本对照使用相同 MCP schema，通过实验私有配置选择参考实现，不能算生成工具或 Motif。

新 Motif 另用 `python -m scenarios.research_ppt.motif_v6 --dataset DATASET --contracts CONTRACTS --version-fields VERSIONS --tool-schema ACTUAL_SCHEMA --generated-tool FULL_TOOL_NAME --mining witnessed_edges --out-dir NEW_PRIVATE_DIRECTORY` 学习。沿用两个独立正常训练任务和一个独立认证任务，完整轨迹不裁剪；公共参数边编译器容许无关只读操作交错，写入/失败仍是 barrier。默认 `sequence` 保留相邻挖掘路径及其失败结果。加载 manifest 检查来源、工具代码/schema 和编译证据锁；是否真实跳过请求须看在线审计，两个工具旁路不自动等于两次请求节省。

`DATASET` 为 `{"train":["正常训练运行目录A","正常训练运行目录B"],"heldout":["独立认证运行目录"]}`，各目录须有完整 `agent-events.jsonl` 和由公共 `freeze-dsh-task-identity.py` 冻结的 `task-identity.json`。动态目录契约须按实际 MCP schema 扩展默认 `contracts.json`：pin 返回 `source_id/version_sha256`，read 的必填参数及来源参数为 `source_id`，输出字段与实际工具一致，版本字段取实际 `version_sha256`；禁止凭空填入图边。`experiment_v6` 的 Motif 组还使用旧私有准入证书 `.local/research-ppt/rsi/v2-20261010/active-guard.json`，是本轮实验复现依赖；新安装须先通过 `improve` 认证并启用自己的准入程序，并通过普通 `cli run --mode execute --manifest ...` 加载，不应假设该历史文件存在。

本轮配置和结果见 [V6 实验记录](../../docs/experiments/research-ppt-v6-tool-rsi-20261011.md)。使用默认布局；V5 布局证书绑定旧代码，不能假称继续有效。所有实验在服务器留日志，本机仅编辑、下载和审阅。`experiment_v6` 默认预览，显式 `--call-model` 才执行新任务并保留各组有效配置、实际 MCP schema、费用、失败、初稿与修订交付证据。未完成人工盲评和账单核对前不宣称同质量总成本下降。

## V4 及此前最终成果

本机私有下载目录为 `.local/research-ppt/v2-deliverables/`；两套 15 页最终辅助修订 PPT 为 `final-decks/academic/research-ppt-15slides-academic.pptx` 与 `final-decks/lab/research-ppt-15slides-lab.pptx`，包含各自 PDF/逐页 PNG。真实 MCP 交付后的每页 PNG SHA 与已审候选一致，辅助修订不计原模型自动成功或三组收益。报告 v1 已生成并辅助目检全部 30 页；v2 `research-ppt-experiment-report-v2.pdf` 已生成、下载，共 31 页，逐页辅助目检未发现阻断问题。报告定位与 SHA 以 [结果记录](../../docs/experiments/research-ppt-v2-20261010-results.md) 为准。

`research-ppt-deliverables-final.zip` 已下载，SHA `c6f81d7efac92b9228e3407b933ba74e710859d540014a5818aaded7f3c756cf`，含新版报告、目视记录和 41 份核验 PPT，包括训练、重试和修订，不是 41 个独立任务。全部论文、产物与原始证据继续留在忽略的私有目录，不随仓库提交。
