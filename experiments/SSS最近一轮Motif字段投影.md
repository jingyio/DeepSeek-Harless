# SSS 最近一轮 Motif 工具输出字段投影

更新：2026-09-28。本实现位于 `src/adapters/motif_output_projection.py`，由 SSS 持有原文、投影视图和 `sss_expand` 恢复入口。Distil 源码与恢复存储不参与这部分实现；Distil 只是可选的下游代理。

## 范围与守卫

- 只加载单个、摘要未变的 `trace_validated_read_only` 编译 Motif，或只含一个该产物的认证库。普通 JSON 投影字段取自已编译的参数传递与选择证据中的 `from_tool`／`from_field`。
- 另一种 `output_projections` 来自独立任务的原始工具轨迹：训练和留出输出须与 `tool/result` 哈希一致，并通过特定 codec 的证据保留与显著缩短检查。当前 `marked_html_visible_text_v1` 保留 Gmail 提醒的来源版本、邮件头和所有可见文字，移除 HTML 呈现标记与链接 URL；原文可精确恢复。它不根据论文相关性选择片段，不能代替语义判断。
- 每次请求识别最近一个尚未得到助手回答的工具调用批次。普通字段投影要求成功 JSON、所需字段齐全且视图更短；证据视图要求认证 codec 在当前输出上再次通过格式和完整可见文字守卫。其他工具结果保留原样，尤其避免将终端证据缩成空对象。
- 原始结果先写到本机 `.local/distil-sss/projections/<run-id>/originals/`；投影视图写到 `views/`，完整原文凭 SHA-256 前缀句柄写到 `restore/`，恢复记录写到 `expansions/`，权限限制为当前用户。恢复按原始字节验证，保留 CRLF。后续请求重用同一视图，不随其成为旧轮次而变动。旧轮次不首次压缩。
- 每个请求都追加固定的 `sss_expand` 工具定义。模型调用它时 SSS 在本机读取原文，接上工具回复后继续模型请求；不存在原文或摘要校验失败时中止，避免继续使用伪造恢复内容。最多允许四次恢复续问。
- 普通 DSH／SSS 路线可用 `--mode plain`，联用 Distil 时 SSS 位于 DSH 与 Distil 之间。预算闸门仍在最上游，恢复续问及 Distil 自身的额外请求都经过它。

无模型示例：

```bash
.venv312/bin/python scripts/run-distil-dsh.py \
  --mode plain --upstream http://127.0.0.1:<mock-port> --budget-usd 0.01 \
  --motif-output-projection .local/motifs/research-retrieval.json -- \
  <isolated-dsh-command>
```

正式模型试验仍需任务级请求上限、预算预览和人工质量审核。该实现暂不压缩长／短历史，不按轮龄重复改写工具结果，也不证明最终回答质量或缓存计价后总费用更好。代理为拦截 `sss_expand` 把下游模型请求改为非流式，最后向流式客户端返回一个完整响应帧；因此首 token 延迟可能增加。`sss_expand` 增加的请求和缓存命中变化须一并测量。

无付费验证：`.venv312/bin/python -m unittest tests.test_motif_output_projection tests.test_distil_dsh -v`。测试覆盖完整原文找回、旧轮次视图稳定、错误结果保留、SSS 流式客户端与原生 Distil 串联；不连接真实模型。
