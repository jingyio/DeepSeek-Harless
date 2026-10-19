# 学习脚本复用：普通新轨迹、独立认证与四组留出

首批已完成：从新的普通 Harness 轨迹编译出两个完整复制脚本模板，独立认证后完成 24 次 H/S/M/L 新留出。正常/边界四组均 4/4；8 次版本变化停止仍保留为未完成交付。学习脚本复用执行为零模型请求，与预写脚本相同；计入建库和认证后，首批完整 API 成本仍高于预写脚本和普通 Harness。

客户端日期 2026-10-14；feature/rsi-research-agent / HEAD dfe4fcc，全部改动本地未提交/推送。实验材料为 testpdf 标记副本，五类二进制容器复用，文本、路径、数量、重复与嵌套条件重新生成；不是真实办公前瞻试用、人类盲评或任意文件管理能力认证。

## 提炼、失败与冻结顺序

- `8792969c`：4 次新普通探索均机械交付合格，61 HTTP / USD0.041491572。FM05-E 额外读取源内容，受限编译器拒绝这一见证；首次编译失败、原事件及费用全部保留，没有认证或留出曝光。
- `ef863a4d`：按原事件/结果 SHA 导入这 4 个普通探索，核验同一实际 MCP 依赖；补 1 次全新 FM05-E 元数据探索，读取授权收窄到规则，12 HTTP / USD0.008004540。兼容的 4 份成功普通见证（每模板两份不同数量任务）用于提炼，额外读取见证排除但费用计入。
- 候选在全部认证前锁定。4 个独立 N/E 条件分别执行普通 H 参考和候选 L（独立实际副本），共 8 运行全部合格，63 HTTP / USD0.050509980；4 次 L 为真实 SDK/MCP 全脚本执行，均 0 HTTP。认证不修改候选。
- `certificate.json` 固定后才生成 6 个全新 N/E/V 留出条件，四组轮换执行共 24 次。角色、来源、实际工具/schema、源字节、配置和候选/证书摘要均绑定。旧 54 留出、G4 库及三篇原始 PDF 不动，新留出不训练或修库。

`034941e1`、`47931735` 为免费准备版本；旧版本在测试清单改变后被误用于免费预检，冻结检查拒绝，0 API/0 副作用。另一次事后守卫分析误取 MCP 导出的 schema 字段别名而失败，改为 inputSchema/input_schema 后 5 个反事实守卫检查通过，0 API；未修改执行器或认证结果。开发错误和修订也保存。

## 机制与同条件对照

FM05：真实规则读取和 SHA 分组，选择每组完整源路径字典序最小者，复制到 merged/<full source path>；保留同名异字节。FM17：源路径到 backup-set 的前缀变换，刷新实际身份后从备份复制到 recovery-drill。模板从实际模型所选操作、参数传递和字节收据推导，合并相邻等价复制；没有保存临时 ID 或答案路径。

格式 `sss-learned-copy-script-v1` 只允许 hash_representatives / copy_map 两种有界指令；工程限制选择假设和执行语言，不是任意程序归纳或模型生成任意 TypeScript。由任务契约显式选候选，在线再核对真实目标/题面/上下文/权限/工具/版本/字节；不是自然语言自动脚本检索。拒绝未覆盖条件，原同会话 Harness 接管，原 5 USD / 96 步请求 / 4000 输出 / 两轮验收修复保持。版本控制沿用实际预览边界单文件变化；没有自动恢复未知外部足迹或原位增量更新能力。

H：原普通 Harness；S：预写固定规则程序（直接实际 MCP，无模型）；M：旧冻结库，FM05 集合读取、FM17 普通回退；L：新轨迹推导的整段脚本，通过公开原 Harness 插件生命周期执行。四组相同题面、初始字节、实际 14 工具与顺序、复制权限、预算和固定验收，工作副本独立。S 与 L 都可零模型，L 多一次当前目录核验并承担 SDK 开销。

## 留出质量与执行成本

| 组 | 正常/边界交付 | 版本停止（未交付） | 全部真实 HTTP | 全部执行代理 USD | Runtime 秒 |
|---|---:|---:|---:|---:|---:|
| H 普通 Harness | 4/4 | 2/2 | 77 | 0.057222300 | 161.271 |
| S 预写脚本 | 4/4 | 2/2 | 0 | 0 | 2.216 |
| M 现有 Motif | 4/4 | 2/2 | 61 | 0.045803244 | 118.295 |
| L 学习脚本 | 4/4 | 2/2 | 0 | 0 | 10.538 |

时间为各执行 Runtime/脚本时长之和，包含版本停止，不包括开发、材料准备、预检与人工。S 的 Python MCP 直接驱动与 L 的原 Harness/SDK 执行开销不同，不能单凭执行时间把差异归因于学习来源。

四组共同合格的 4 个条件 H/S/M/L 请求 59/0/47/0，代理 USD0.046612320/0/0.037236216/0。FM05 全 N/E/V 的 H/M 为 39/31 HTTP，USD0.032942880/0.027577704；M 核验 15 个读取续接。FM17 H/M 为 38/30，USD0.024279420/0.018225540，M 无自动图，因此这部分差异是普通模型运行差异，不能计为 Motif 收益。L 留出核验 52 个实际工具步骤，4 个完整交付、2 个版本中断；核验步骤不是推测省下的模型请求数。

## 全成本与修复

L 全部建库/认证：5 普通探索 + 8 认证运行，136 HTTP / USD0.100006092，含被排除见证和补充探索；离线编译 0 模型 API，开发维护/人工工时未核实，不记作免费。

| 组 | 本批执行 USD | 计入库准备/认证的完整 API USD |
|---|---:|---:|
| H | 0.057222300 | 0.057222300 |
| S | 0 | 0（人工未折算） |
| M | 0.045803244 | 0.281582008 |
| L | 0 | 0.100006092 |

M 的 USD0.235778764 准备费引用原获取、认证与在线验证，覆盖的库范围比这两个流程更广；L 是新的两流程小库。全库准备费分开列出，不能据表声称同范围的通用库效率优势。

全本轮 37 执行（21 有真实 API、16 零模型）/274 HTTP/代理 USD0.203031636，29 交付合格、8 受控版本未交付。49 工具错误全部保留，普通模型在工具层纠正参数的费用包含在原任务总费中。没有真实验收重试消息；L 自然修复 API 费用为 0，本批没有真实 DeepSeek 的 L 验收失败修复样本。另有本地模拟 Provider 的真实 SDK/MCP 检查：故意失配停用 L，普通回退首次验收失败、原同会话一次修复后通过；10 mock HTTP，0 云费用，不能替代真实模型修复证据。所有错误、失败轮次及请求/usage/费用日志保留。

累计文件系列 620 执行 / 5880 HTTP / USD4.700445860，原 1000 USD 估费余额 USD995.299554140。费用使用 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)核验的冻结峰值表（缓存命中/未命中/输出分开）；实际账单未知。人类金额按用户要求不折算，盲评与维护成本仍未知。

## 复现与验证

私有当前指针 `.local/file-management/script-reuse-current.json` → `fm-script-reuse-20261014-ef863a4d`；原 8792969c 的事件/输入/源文件版本继续原地保存，以 SHA 引用，不覆盖。原始材料在 testpdf/file-management-experiment 对应 ID；开发改前/差异/失败及全部日志在 `.local/script-reuse-development-20261014-9c915457`。

```sh
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py
# 先对新 ID 免费检查和普通探索；--call-model 已含副本副作用授权，默认仅准备/预览。
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --free
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --role explore --call-model
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --learn
# 若见证不足，保留失败，从未曝光认证/留出的训练父版本补新元数据探索：
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --training-parent .local/file-management/<UNEXPOSED_PARENT>
# 候选已锁后检查真实 SDK/MCP，再执行认证；检查产生的模拟/自动轨迹不能训练。
node scripts/project.mjs python scripts/check-script-reuse-sdk.py --experiment .local/file-management/<NEW_ID>
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --role certify --call-model
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --certify
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --freeze-holdout
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/<NEW_ID> --role holdout --call-model
node scripts/project.mjs python scripts/audit-script-reuse.py --experiment .local/file-management/<ID>
```

全量独立审计 37 项通过：原正常模型来源/不可训练角色、原源版本、候选/证书、四组字节/题面/schema、实际后置/版本停止足迹、每个真实 HTTP 与 usage/费用、旧留出和三 PDF。568 Python / 170 Node 通过，3 可选 Docker 跳过；18 smoke 通过。2 次真实 SDK/MCP 零模型程序检查和 1 次本地模拟修复通过；5 个反事实版本/权限/目标/前缀/输入守卫检查均在副作用前停用，0 云费用。

结论：在这两个固定复制流程中，新的普通轨迹可以被提炼为带参数的完整脚本，并通过独立认证在新材料上复用；支持受限可靠复用。当前执行费用与预写脚本相同，且本批 L 计入准备费高于 H/S，不支持本批完整成本更低、自动维护或通用脚本学习。下一轮应验证新规则/目录变化后的失效、重新提炼和维护成本，并加入语义选择后执行脚本的混合任务；先新的探索和认证，再新的留出，保持旧留出不训练。默认 SDK/Web/动态前端不启用，暂不推送。

接口变动见 [详细记录](../changes/file-management-script-reuse.md)。
