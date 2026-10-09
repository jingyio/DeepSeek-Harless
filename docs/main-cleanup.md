# main 清理记录（2026-10-09）

目的：给三个场景提供共同开发起点，保留 Motif 核心、DSH 插件、通用 MCP 扩展、预算和测试。此次没有运行付费模型，也没有删除本机 `.local` 中的凭证、私人资料和原始实验记录。

## 备份与恢复

- `archive`：`810edf4`，保存清理请求开始时的工作树，包括用户修改的题面及参考 PDF (32)。
- `archive-pre-cleanup-20261009`：`1d7ec26`，保存 main 清理前的完整状态，包括随后出现的参考 PDF (31) 替换。
- 这些是本地 Git 分支；未自动推送到 origin。历史 PDF 各版本均在相应分支及其提交历史中。

查看历史文件无需切换并污染新 main：

```sh
git show archive:experiments/办公科研主线与MotifAgent对齐设计.md
git diff archive-pre-cleanup-20261009 main --stat
```

需要完整旧代码时，建立独立只读查阅目录：

```sh
git worktree add --detach ../SSS-archive archive-pre-cleanup-20261009
```

需要某个旧模块时，先检查依赖再有选择地恢复，不把全部 archive 合并回 main。历史需求和实验设计仍可在归档查阅；main 上的文档已更新为实际保留的入口。

## 从 main 移出的跟踪文件

共移出 677 个原跟踪文件。原始内容保存在备份分支；node_modules、虚拟环境、忽略文件和 `.local` 均不在这个计数内。

| 原位置 | 文件数 |
| --- | --- |
| `.dsh` | 1 |
| `benchmarks` | 198 |
| `config` | 29 |
| `experiments` | 109 |
| `office` | 2 |
| `outputs` | 48 |
| `reference` | 3 |
| `reports` | 4 |
| `scripts` | 157 |
| `source` | 3 |
| `src` | 53 |
| `tests` | 66 |
| `根目录历史文件` | 4 |

主要包括：旧办公/迁移/应用试跑脚本、实验比较与汇报、研究中间产物、历史场景夹具、专用连接器和对应测试。`src/graph` 是早期手写结构原型，已经归档；实际 Motif 内核保留在 `src/motif_core`。Google Gmail/Calendar 包和旧重型办公依赖已从安装清单移出。

## 保留与新增

保留完整来源许可/迁移记录、通用挖掘/编译/认证与读取执行核心、handoff/reentry、纯代码隔离、在线匹配、预算代理，以及两个科研 portfolio 的 18 项冻结夹具。有效的失败边界测试继续保留。

从 `test_dsh_trajectory.py` 中移出旧 SSS 场景的函数签名绑定检查，但保留参数来源认证/拒绝检查；从 failure feedback 测试中移出依赖已归档工作流的来源读取测试。三个依赖已归档 Distil 启动器的集成测试随启动器归档；通用投影与本机 HTTP 协议测试继续执行。这些是按模块退休清理，不是掩盖核心失败。

新增统一跨平台命令、自定义 MCP 配置与白名单、最小示例服务、普通/shadow/execute 统一入口、私有运行记录，以及接口和协作文档。JS 插件的受限 Python 执行使用当前解释器；固定 SDK 的 Node 启动接缝集中在一个适配器中。

## 验证与限制

本机验证通过 133 项 Python 测试、24 项 Node 测试；18 题 stdio MCP smoke 读取 83 个来源对象，八种工具全部覆盖。真实 SDK 初始化、环境密钥引用、两套场景预览均已检查；额外通过本机模拟 Provider 验证真实 Harness 连续两次 MCP 调用与三次预算代理请求，回归不依赖历史 .local 产物。无新付费实验。合成工具覆盖不能算科研答案正确性或 Motif 收益；Windows 原生和真实 HTTP MCP 服务仍需联调，当前只在 macOS 执行验证。已增加 Ubuntu/Windows CI 配置，但尚未在远程运行。

此次仅清理当前 Git 树；历史提交中的文件和本机私有数据仍然存在，仓库历史体积不会因此消失。新增同学可以使用浅克隆减少历史下载量。
