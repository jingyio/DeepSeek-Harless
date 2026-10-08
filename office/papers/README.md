# 论文摘要与归档试用区

把待处理 PDF 放进 `inbox/`，或在 Harness 中直接给出其他本地 PDF 的绝对路径。运行 `npm run office:setup` 创建目录和 PDF 提取环境。`inbox/`、`archive/`、`notes/` 的内容不进入 Git。

在 Harness 会话中选择 SSS 工作区，输入：

> 使用 paper-review 技能阅读 `office/papers/inbox/文件名.pdf`，生成中文阅读卡片并给出归档预览。先不要执行归档；我核对后再确认。

归档会复制原 PDF；确认之前不会改动原文件。扫描件、公式和复杂图表可能无法从 PDF 文本中完整提取，应人工查看原件。阅读卡片格式见 [note-template.md](note-template.md)。

此流程对应 WorkBuddy 的“读取本地论文 → 摘要/分类 → 确认后整理文件”单项任务；它目前没有 WorkBuddy 的资料库、团队协作和丰富产物预览。首轮比较应使用相同论文和验收规则，记录准确性、耗时、费用、人工修改量和独立完成率。
