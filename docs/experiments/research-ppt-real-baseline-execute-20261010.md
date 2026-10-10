# 真实论文 PPT baseline / execute 对照

- 实验 ID：`research-ppt-real-baseline-execute-20261010`
- 类型：真实前瞻试跑；来源为公开论文，原始 PDF 保存在服务器 `.local/`
- 代码基线：服务器 `883ee5c`；运行时另有未提交的 PPT 提示容量约束修改
- 任务：从一篇 PDF 生成 6 页中文科研 PPT，每页保留来源页码，输出可编辑 `.pptx`
- 来源 SHA256：`bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`
- 模型：`deepseek-flash`；`reasoning_effort="off"`

## 配置与结构

- 输入版本、MCP 工具集合和顺序在 baseline / execute 间保持一致。
- execute 使用在线 manifest digest `709f6119a8990f5ae0cd0143dcdf8d2285de9582988f3812207fafe7a15d1ffe`。
- RSI 守卫由 `propose_guard` 认证，digest 为 `a961082d2aae0dd0cbc0072c939fc35bfbef971ac85318aa4c5e1a91e31982e9`。
- 提示修复将普通页约束为最多 4 条、每条最多 45 字符、总正文最多 160 字符；图表/图片页最多 2 条、总正文最多 70 字符，并要求文本溢出时缩短后重试。

## 运行结果

首次 baseline 使用 10 次模型请求，因第 3 页文本溢出失败，未产出 baseline PPTX；服务器直接复现的错误为“第 3 页文本溢出，请缩短或分成两页”。

提示修复后的 baseline 重试成功：

- 8 步、8 次模型请求
- 输入 11,924 token；缓存读取 52,096；输出 2,963；总 token 66,983
- 代理记账 `$0.007445376`
- 产物通过页数、可编辑文本和 notes 检查：6 页、36 个文本块、6 条 notes

execute 对照成功：

- 9 步、8 次模型请求
- 输入 13,119 token；缓存读取 63,488；输出 2,431；总 token 79,038
- 代理记账 `$0.007233828`
- `model_requests_skipped_verified=1`
- 产物通过同样的结构检查：6 页、36 个文本块、6 条 notes

baseline 重试与 execute 的模型请求数均为 8。本次单任务中，1 次 verified bypass 被额外的 `read_page` 调用和轨迹差异抵消，没有观察到请求数下降；不能据此宣称 token 或费用稳定下降。两份 PPTX 均未进行语义质量盲评或人工目视验收，结构检查也不代表科学内容和视觉质量合格。

观察到的三次模型运行代理费用约为 `$0.025`，需与真实账单核对。零模型结构链路另有 0 请求的可编辑 PPTX，但它使用固定证据页内容，不能作为语义质量等价对照。

## 复现与日志

实验原始日志仅保存在服务器 `test-logs/` 和 `.local/runs/`，不进入 Git。匿名摘要保存在服务器 `.local/research-ppt/experiments/real-baseline-execute-20261010.json`。

关键日志：

- `test-logs/research-ppt-real-baseline-01.log`
- `test-logs/research-ppt-real-baseline-retry-after-prompt-fix-01.log`
- `test-logs/research-ppt-real-execute-02.log`
- `test-logs/research-ppt-render-fix-01.log`
- `test-logs/research-ppt-prompt-preview-after-fix-01.log`
- `test-logs/research-ppt-real-execute-preflight-after-prompt-fix-01.log`

后续最小验证：在至少 5 个独立论文任务上固定提示、工具集合、步数和质量门槛，盲评 baseline / execute 的内容正确性、来源覆盖、人工修订时间和总成本，再判断 RSI 是否带来可重复收益。
