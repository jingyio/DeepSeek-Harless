# Windows 首次 CI 失败与兼容修复

- 日期：2026-10-09；失败提交 `410ba3b`，GitHub Actions 运行 `37888161426`。
- 现象：Windows Python 测试 8 失败、128 通过；Node、smoke 和 Motif 验收尚未执行。不能因此认定 Harness/MCP 在 Windows 不可用，也不能在后续检查完成前声称 Windows 全部支持。
- 原因一：Git 检出将 LF 转成 CRLF，冻结夹具与样例身份按字节做 SHA-256，因此失败。将两份本地 LF 夹具转换为 CRLF 后，精确复现 Windows 日志中的两个错误摘要；并非资料内容或 Motif 参数边改变。
- 原因二：部分测试的 `read_text()` 未指定编码，Windows CI 使用 cp1252 解码 UTF-8 中文而失败。
- 原因三：候选文件测试将 Windows `st_mode` 与 Unix `0600` 比较，得到 438（八进制 `0666`）与 384（`0600`）不相等。Windows 权限由 ACL 管理，该数字不能证明 ACL 范围；本次不声称新增了 ACL 认证。
- 修复：`.gitattributes` 固定文本 LF；统一入口设置 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`；相关测试读写显式 UTF-8；仅在非 Windows 系统上断言 Unix 模式位，候选状态、内容摘要、篡改拒绝及禁止自动晋升仍在所有平台验证。
- 不变的验收约束：未修改冻结数据、题目或 library/manifest 摘要，未重新计算锁来掩盖失败，未删除整个测试或跳过 Windows CI；不改 Harness 核心。
- 本地验证：macOS 的 136 项 Python、29 项 Node 回归通过。后续以修复提交对应的 GitHub Actions Ubuntu/Windows 结果为准；本机回归不能代替 Windows 原生结论。没有新增付费 API 调用。
- 已有 Windows 副本：保留自己的未提交工作后，重新克隆最新 main 并执行 `npm ci`、`npm run setup`、`npm test`、`npm run smoke`、`npm run motif:check`；不要强制清理带有个人工作或私有运行数据的目录。

- 远端验证结果：修复提交 `c05127f` 的 [GitHub Actions 37888988141](https://github.com/jingyio/DeepSeek-Harless/actions/runs/37888988141) 已完成；Windows/Ubuntu 两组均通过依赖安装、Python/Node 全套测试、18 题 MCP smoke 和 Motif 样例闭环。按 `core.autocrlf=true` 本地干净检出的 79 个冻结文件也保留原哈希。支持范围是当前离线/模拟协议；真实云 API 与自定义应用权限仍需场景联调。
