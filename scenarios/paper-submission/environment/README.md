# 论文实验共享基础环境

原生 Harness、Code Mode 与后续 MCP/Motif 组使用相同的编译器和基础程序。
这里提供公共环境夹具与无模型验收入口，不包含论文校验策略或真实论文。

当前服务器为 Ubuntu 22.04。安装基础组件：

```sh
apt-get update
apt-get install --no-install-recommends latexmk texlive-latex-extra \
  texlive-fonts-recommended texlive-fonts-extra texlive-science texlive-publishers \
  texlive-plain-generic texlive-xetex texlive-luatex fonts-linuxlibertine fonts-inconsolata \
  tex-gyre cm-super poppler-utils chktex
```

在服务器项目目录加载既有隔离环境，再用统一入口验收：

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/check-paper-env.py
```

脚本分别用 pdfLaTeX、XeLaTeX、LuaLaTeX 编译相同的 ACM/算法/表格/数学夹具，
验证 BibTeX 结果、交叉引用、PDF 元数据和字体嵌入。关闭 shell escape，忽略
用户 latexmk 配置；这只是公共夹具的环境检查，不是任意 LaTeX 的隔离沙箱。
记录引擎/工具/已安装包版本、夹具哈希、代码 commit 和工作区状态。生成文件
保存在 `.local/paper-env/runs/<RUN_ID>/`，不进入版本控制。

`acmart` 使用系统安装版本；真实工程自带的类文件和额外依赖仍需独立核对。
夹具的引用是虚构条目，只用于验证 BibTeX 管道。通过不代表会议合规、论文
质量或模型降本。Biber、中文字体、特定会议模板与私人论文尚不属于此验收。

后续原生基线保留通用文件、终端和网页工具，由模型选择操作。不要在环境
夹具中预置整套论文检查答案或手写任务 DAG。新工具与 RSI/Motif 的收益必须
在独立任务上测量，并记录工具生成、认证、重试及人工修订成本。

原生终端还要求有效的 Harness 沙箱后端。当前服务器已安装 bubblewrap，
但容器禁止创建所需 namespace，宿主内核 5.4 也没有 Landlock 后备能力。
本脚本直接检查编译环境，不代表 Harness 的 `workspace-write` 终端可用。
本次私人基线已单独获用户非沙箱授权；通用入口不得自动沿用该权限。
