# Motif 候选的轻量语义路由

## 位置

MotifController 先凭认证过的工具轨迹、目标输出和当前输入版本给出候选集合。只有出现多个候选时，候选路由器才读取 `motif_choice` handoff；它不能添加候选、改变参数依赖或直接调用工具。路由结果是建议，显式接受后仍由 MotifController 核对 handoff 签名、资料版本和参数，再决定继续运行还是停在下一个语义缺口。

## 可替换判断器

- `src/adapters/local_embedding.py`：本机 OpenAI 兼容 `/v1/embeddings` 接口，按当前意图和候选描述的向量相似度排序。已在 `.local/models/qwen3-embedding-0.6b` 下载固定版本 `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` 的 [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)，SHA-256 已按官方仓库的权重记录核对。服务以 `npm run embedding:start` 在本机 `127.0.0.1:8776` 启动。若要在另一台机器重现，先运行 `npm run embedding:setup`；官方 Hugging Face 下载不畅时可用 `npm run embedding:setup -- --mirror`，脚本仍核对官方 SHA-256。阈值尚未校准。
- `src/adapters/laya_decision.py`：本地 Laya 的 Choice 接口。当前是诊断后端。英文基础检查点默认 512 token；中文使用的 multilingual 检查点默认 1024 token，其中部分留给选项。长状态仍可能被截断，零样本效果与概率校准都不能视为 Jev 的替代证明。
- `src/adapters/jev_decision.py`：TypeSafe Jev 官方 API 的 Choice 接口；默认禁用付费请求，显式开启并提供 `TYPESAFE_API_KEY` 后才会请求。尚无本机密钥，也没有发起真实 Jev 调用。

三种后端都只处理相同的 Motif 候选；低分、分差不足、模型主动选择 `__defer__`、响应形状错误时停止并交回语义层。没有 TF-IDF 路径，也没有在某个后端失败时悄悄改用另一个后端。阈值现在由调用方显式提供，**尚未在课题组真实任务上校准**，不能据此自动执行。

## 接入与未完成事项

`src/adapters/motif_candidate_router.py` 接收控制器当前的 handoff；`advise_with_embeddings` 或 `advise_with_choice` 返回建议，`resume_approved_advice` 才把经批准的建议交给控制器。测试验证了候选集合不变、低置信度退级、旧资料版本的建议失效，以及未批准时零工具调用。Jev 测试只模拟官方响应格式，不产生费用。

候选文字现可由 `descriptions_from_contracts` 从**当前认证 Motif 的工具描述与参数流**自动组合；`advise_current_with_embeddings`／`advise_current_with_choice` 直接使用这一索引。`compile-dsh-motif-library.py` 的 manifest 可指定 `tool_schema_file`，从 MCP 的 `tools` 列表读取描述，并核对输入 schema 的必填参数与批准的执行契约；缺少说明或参数不一致时自动匹配停止。不拿旧任务原文或临时手写路径冒充匹配描述。该描述的版本尚未独立保存为可修订的匹配索引，领域语义也未因此学到。

本机实测：三条中英文文本返回三个 1024 维有限向量，端到端耗时约 1.9 秒。将模型接到真实 Motif handoff 后，`search→read` 和 `lookup→read` 两个描述相近的候选得分分别为 0.4772 与 0.4928；设置高阈值时正确退级，零工具调用。这是连通性和安全边界检查，不能算匹配准确率结果。

待完成：从真实 DSH 工具 schema 收集并固定描述版本，验证衍生文字是否能区分实际候选；在真实课题组任务上校准阈值和比较 Jev/Laya/embedding；把顶层规划、证据选择、报告写作与增量更新统一接到 SSS 状态机。当前只是**多候选选择边界的接入**，并非整条科研交付链已完成。

TypeSafe 官方申请入口：[控制台](https://console.typesafe.ai/login)。官方 [API 契约](https://api.typesafe.ai/openapi.json) 规定 Bearer API key 和 `/v1/systemone` Choice 问题。账户登录、邮箱验证、条款和密钥创建需由账户持有人完成；密钥只放本机受保护环境，不写入仓库或聊天。
