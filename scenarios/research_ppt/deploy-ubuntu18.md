# Ubuntu 18.04 用户目录部署记录

2026-10-12 在一台无 root 权限、Ubuntu 18.04、glibc 2.27、Linux x86_64 服务器验证：根 `npm test` 136 项 Python / 29 项 Node 全通过，`npm run smoke` 18 个用例全通过，SDK 初始化成功、付费模型请求为 0。场景另有真实 LibreOffice→PDF→PNG、MCP 交付和重启回归，范围见 [V9 记录](../../docs/experiments/research-ppt-v9-quality-20261012.md)。这不是科研内容合格或 RSI 降本结论。

这是旧系统的项目私有兼容记录。新部署优先选择受支持的新 Ubuntu，按照[根 README](../../README.md)和[场景 README](README.md)安装固定依赖。不要默认向其他机器复制此处的加载顺序处理或 `--no-deps` 例外；不能据此宣称 Ubuntu 18.04 普遍兼容。

以下路径相对项目根，不包含服务器身份、密钥或用户论文。Conda 命令可从实际 `conda-meta/history` 找回；其余片段是对已完成操作的等价复现，原始终端命令未全部保存。记录的 SHA 是实际下载包/运行文件证据；下载源校验和也应重新核对，不能只信文件名。

## 1. 已验证版本与安装边界

| 组件 | 本轮实际版本 / 位置 | 边界 |
| --- | --- | --- |
| micromamba | 2.9.0，`.local/bootstrap/bin/micromamba` | 只管理用户目录 `.local/toolchain` |
| Python | 3.12.15，Conda build `h5f976f7_1_cpython` | `.venv-sss` 开启 `include-system-site-packages`，复用 Conda PyMuPDF |
| PyMuPDF | 1.26.7，Conda build `py312h8285ef7_0` | 本机 pip 从源码编译失败，改用 Conda 包；不更改场景版本要求 |
| SDK | `deepseek-harness-sdk==0.1.5rc1` | `--no-deps` 安装；`deepseek-harness-runtime-bin` 未安装 |
| Python MCP | `mcp==2.2.0` | 激活后由 Python `importlib.metadata` 查询；不是 Node SDK 的版本 |
| Node MCP SDK | 根 `@modelcontextprotocol/sdk==1.30.1`；场景 `1.32.1` | 分别查询两套 `node_modules` 元数据，均由各自 npm 锁文件固定 |
| npm DSH | `@deepseek-ai/dsh@0.1.5-rc.3` | 通过现有 `src/adapters/harness_runtime.py` 固定 SDK 启动接缝加载 |
| 有效 Node | 22.23.2，`linux-x64-glibc-217` 分发 | 独立 `.local/node-runtimes`；Conda 当前 Node 20.20.2 不作为有效入口 |
| node-pty | 1.2.0-beta.15，本机 source build | 预构建二进制要求 glibc 2.28；使用系统 GCC 7.5 / make 与本地 Node headers |
| LibreOffice | 7.6.7.2，build `dd47e4b30cb7dab30588d6c79c651f218165e3c5` | DEB 解包到 `.local/libreoffice-7.6`，没有系统安装 |
| 中文字体 | `font-ttf-noto-cjk==2.004`，Conda build `h77eed37_0` | Fontconfig 指向项目字体目录，字体配置参与有效快照 |
| 图片组件 | sharp 0.35.4 / vips 8.18.6 | 本机 native libvips 要求 glibc 2.28；可用兼容路径实际 PNG 像素回归通过 |

`pip check` **没有完全通过**：SDK 声明的 `deepseek-harness-runtime-bin` 缺失。该 wheel 的平台要求不适合本机 glibc 2.27；现有 SDK→npm Node 接缝已由底座集成与 smoke 验证，但不等于标准 SDK 安装。不要把缺依赖隐藏或把此例外推广到其他 SDK 版本。

Python MCP 与两套 Node MCP SDK 的版本已在项目激活后分别读取安装元数据；版本不同不构成矛盾。复核记录在宿主私有 `test-logs/research-ppt-v9-quality-20261012/deploy-version-probe-final.log`。

## 2. Python、Conda 与 venv

在已检出的项目根执行。所有下载和环境只落项目私有目录；不要混用已有用户全局 Python。

```sh
PPT_PROJECT_ROOT="$(pwd -P)"
mkdir -p .local/bootstrap .local/toolchain test-logs
set -o pipefail
```

本轮 micromamba 归档为 `.local/bootstrap/micromamba.tar.bz2`，实际 SHA256：

```text
8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd
```

从 micromamba 官方下载入口获取对应 **2.9.0 / linux-64** 包，核对发行来源及 SHA 后解包。原下载 URL 未进入日志，不能把 `latest` 当作固定版本复现依据。已有包的等价解包操作：

```sh
printf '%s  %s\n' \
  '8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd' \
  '.local/bootstrap/micromamba.tar.bz2' | sha256sum -c - || exit 1
tar -xjf .local/bootstrap/micromamba.tar.bz2 -C .local/bootstrap bin/micromamba
.local/bootstrap/bin/micromamba --version
```

从包管理历史恢复的两条命令（只替换了项目绝对路径）：

```sh
.local/bootstrap/bin/micromamba create -y -p "$PPT_PROJECT_ROOT/.local/toolchain" \
  -c conda-forge python=3.12 nodejs=22 font-ttf-noto-cjk
.local/bootstrap/bin/micromamba install -y -p "$PPT_PROJECT_ROOT/.local/toolchain" \
  -c conda-forge pymupdf=1.26.7
```

第一条初次求解得到 Node 22.6.0；第二次求解后 Node 降为 20.20.2，因此 **不能把宽松 `nodejs=22` 约束当作最后有效 Node 配置**。Python 最终 3.12.15、字体 2.004；完整包版本以 `.local/toolchain/conda-meta` 为准。继续执行后面的独立 Node 固定步骤。

为复用 Conda PyMuPDF，本轮 venv 的 `include-system-site-packages = true`。下列为同样环境布局的等价复现：

```sh
.local/toolchain/bin/python -m venv --system-site-packages .venv-sss
.venv-sss/bin/python -m pip install 'mcp==2.2.0' 'pydantic==2.13.5' 'pytest==8.4.2'
.venv-sss/bin/python -m pip install --no-deps 'deepseek-harness-sdk==0.1.5rc1'
.venv-sss/bin/python -m pip install -r scenarios/research_ppt/requirements.txt
.venv-sss/bin/python -c 'import fitz; print(fitz.VersionBind)'
.venv-sss/bin/python -m pip check
```

最后一条的已知 SDK runtime-bin 缺依赖必须保留。不要在此旧系统重新盲跑根 `npm run setup` 或强制重装 PyMuPDF：它们可能重新触发不兼容 wheel / 源码构建。原 pip 构建失败与依赖例外证据为服务器私有 `test-logs/` 下的 `bootstrap-pip.log`、`bootstrap-pymupdf-conda.log`、`bootstrap-sdk-no-runtime-bin.log`、`bootstrap-pip-check.log`，未随仓库分发。

## 3. 用户目录 LibreOffice 与字体

本轮官方 DEB 归档为 `.local/bootstrap/libreoffice.tar.gz`，实际 SHA256 `5fbd379bd9cedb037fa00b6e7e830619bff503a9451bc321e2b4e8d646081920`。官方归档地址与以下操作是等价复现；实际归档 SHA、解包目录和 `--version` 已核实，原下载命令未完整留存。

```sh
curl -fL --retry 2 -o .local/bootstrap/libreoffice.tar.gz \
  'https://downloadarchive.documentfoundation.org/libreoffice/old/7.6.7.2/deb/x86_64/LibreOffice_7.6.7.2_Linux_x86-64_deb.tar.gz'
printf '%s  %s\n' \
  '5fbd379bd9cedb037fa00b6e7e830619bff503a9451bc321e2b4e8d646081920' \
  '.local/bootstrap/libreoffice.tar.gz' | sha256sum -c - || exit 1
mkdir -p .local/bootstrap/lo-debs .local/libreoffice-7.6 .local/bin
tar -xzf .local/bootstrap/libreoffice.tar.gz -C .local/bootstrap/lo-debs
for package in .local/bootstrap/lo-debs/LibreOffice_7.6.7.2_Linux_x86-64_deb/DEBS/*.deb; do
  dpkg-deb -x "$package" .local/libreoffice-7.6
done
ln -s ../libreoffice-7.6/opt/libreoffice7.6/program/soffice .local/bin/soffice
.local/bin/soffice --version
```

已有入口时先检查，不覆盖用户自己的文件。无需 `sudo` 或 `dpkg -i`。Conda 字体位于 `.local/toolchain/fonts`，本轮还包含 DejaVu Sans Mono 2.37、Inconsolata 3.000、Source Code Pro 2.038、Ubuntu 0.83。实际 Fontconfig 布局的等价复现：

```sh
mkdir -p .local/fontconfig .local/font-cache
cat > .local/fontconfig/fonts.conf <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
<dir>$PPT_PROJECT_ROOT/.local/toolchain/fonts</dir>
<dir>/usr/share/fonts</dir><dir>$PPT_PROJECT_ROOT/.local/fontconfig</dir>
<cachedir>$PPT_PROJECT_ROOT/.local/font-cache</cachedir>
</fontconfig>
EOF
```

在项目激活入口设置 `FONTCONFIG_PATH` / `FONTCONFIG_FILE`，再实际生成 PDF/PNG；仅字体名称存在不能证明无缺字。服务器私有日志为 `test-logs/bootstrap-libreoffice.log`、`test-logs/bootstrap-fonts.log`、`test-logs/v9-scene-python-02.log`。

### 真实任务字体失败与验收勘误

V9 PiSSA 真实任务的预览出现中文全部方框、ASCII 正常，原机械验收却为 `passed`。PDF 仅嵌入 DejaVu 字体，但 `/ActualText` 仍保留中文，原 `page.get_text()` 内容保持检查因此漏报；实际绘制 trace 中中文坍缩到同一字形。该交付不能算合格。原 PDF、PNG、验收报告及 SHA 保留于宿主私有 `.local/research-ppt/v9-quality-20261012/font-diagnosis/`，未覆盖旧证据。

调用链存在两处字体环境缺口：Harness→TypeScript MCP 的场景配置没有显式传 `FONTCONFIG_FILE/PATH`；TypeScript→Python 后端又使用 MCP SDK 的 `getDefaultEnvironment()`，该白名单也不包含这两项。必须在**两个边界**显式传递这两项，保留凭证隔离，不能直接传全部 `process.env`。`cli.py` 私有场景配置及 `ts/mcp-adapter.ts` 已补传递并上传；**本段记录时，真实重导仍待通过字形和逐页预览验收，不能称修复已验证**。

登录 shell 的 `fc-match` 来自 Conda，链接 Conda 字体库；LibreOffice 实际链接系统字体库。系统 `/usr/bin/fc-match` 在有项目 `FONTCONFIG_FILE/PATH` 时选 Noto，缺少时回退 DejaVu，与失败 PDF 一致。Conda 探针或“字体已安装”均不能替代转换进程证据。有效快照须冻结系统字体匹配、配置文件和实际字体 SHA，并在新验收目录重导同一 PPTX；若仍失败再选择已有静态 OTF，当前尚未证明可变字体本身不兼容。诊断日志为宿主私有 `test-logs/research-ppt-v9-quality-20261012/` 下以 `font-` 开头、编号 01–06 的六份日志，底座测试通过也不能替代此次字形验收。

后续实证：补传后中文已正常，但可变字体被LO导为Type3轮廓，MuPDF给出ignored-text与可见CharProcs绘制路径；新PDF没有ActualText。严格字形oracle不能确认这种表示。本机选择已存在的静态 `NotoSansCJKsc-Regular.otf`（SHA256 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`），另建 `fonts-static.conf` 仅指静态字体目录与系统字体，并保留原配置。**上述Conda命令不会自动把该静态OTF放入此目录。** 本轮实际文件位于`.local/fontconfig/NotoSansCJKsc-Regular.otf`，16,437,364字节；获取命令未完整留存，此文不冒称一键安装recipe。新部署须先从可信Noto发行源取得静态OTF并核验字节/SHA，未取得或不匹配时停止，不能只创建配置后依赖默认字体回退。等价配置及启用前检查为：

```sh
cat > .local/fontconfig/fonts-static.conf <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
<dir>$PPT_PROJECT_ROOT/.local/fontconfig</dir>
<dir>/usr/share/fonts</dir>
<cachedir>$PPT_PROJECT_ROOT/.local/font-cache-static</cachedir>
</fontconfig>
EOF
mkdir -p .local/font-cache-static
export FONTCONFIG_PATH="$PPT_PROJECT_ROOT/.local/fontconfig"
export FONTCONFIG_FILE="$PPT_PROJECT_ROOT/.local/fontconfig/fonts-static.conf"
test -f "$PPT_PROJECT_ROOT/.local/fontconfig/NotoSansCJKsc-Regular.otf" || exit 1
printf '%s  %s\n' \
  '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b' \
  "$PPT_PROJECT_ROOT/.local/fontconfig/NotoSansCJKsc-Regular.otf" | sha256sum -c - || exit 1
PPT_MATCHED_FONT="$(/usr/bin/fc-match -f '%{file}' 'Noto Sans CJK SC')"
test "$PPT_MATCHED_FONT" = "$PPT_PROJECT_ROOT/.local/fontconfig/NotoSansCJKsc-Regular.otf" || exit 1
/usr/bin/fc-match -f '%{file}\n' 'Noto Sans CJK SC'
```

将两项选择持久化到项目私有激活入口后，静态重导四页实际CJK绘制覆盖通过；旧PiSSA仍因上标提取顺序不确定被文字检查拒绝，未追改旧计划或放宽。含中文的真实MCP三页交付、两次重启及局部修订诊断 `delivery-smoke-font-static-04` 全部通过，0模型；日志 `test-logs/v9-delivery-smoke-font-static-12.log`。这只验证字体与机械交付链，不证明科学内容合格。Type3/路径化文字仍需可验证字体重导或独立人工核验。

## 4. 固定 Node 22.23.2 与本机 PTY

DSH 固定 npm 入口使用 `import.meta.main`，实际要求 Node 22.18+。Node 20.20.2 不执行入口且退出 0；Node 22.6.0 同样不满足此入口。Conda Node 22.23.2 预演明确要求 glibc 2.28，本轮未强行替换系统库。

本轮使用 Node 项目的 unofficial-builds **22.23.2 / linux-x64-glibc-217** 分发。下载、校验 published `SHASUMS256.txt` 及独立用户目录解包均已实际执行：

```sh
mkdir -p .local/bootstrap/node22-glibc217 .local/node-runtimes
curl -fL --retry 2 -o .local/bootstrap/node22-glibc217/node-v22.23.2-linux-x64-glibc-217.tar.xz \
  'https://unofficial-builds.nodejs.org/download/release/v22.23.2/node-v22.23.2-linux-x64-glibc-217.tar.xz'
curl -fL --retry 2 -o .local/bootstrap/node22-glibc217/SHASUMS256.txt \
  'https://unofficial-builds.nodejs.org/download/release/v22.23.2/SHASUMS256.txt'
printf '%s  %s\n' \
  '333a2c084cbeb3fc8cc026b7cc8eb194cec31803142a0c56e58845eafbfe4495' \
  '.local/bootstrap/node22-glibc217/node-v22.23.2-linux-x64-glibc-217.tar.xz' | sha256sum -c - || exit 1
```

同时核对发布清单中的对应条目；本轮 Python 对每个 tar member 检查目标仍在 `.local/node-runtimes` 内，并使用 Python 3.12 `tarfile.extractall(..., filter='data')`，再得到 `.local/node-runtimes/node-v22.23.2-linux-x64-glibc-217`。在后续激活入口让该版本优先，不能只修改交互终端一次。

```sh
PPT_NODE_ROOT="$PPT_PROJECT_ROOT/.local/node-runtimes/node-v22.23.2-linux-x64-glibc-217"
export PATH="$PPT_NODE_ROOT/bin:$PPT_PROJECT_ROOT/.venv-sss/bin:$PPT_PROJECT_ROOT/.local/toolchain/bin:$PPT_PROJECT_ROOT/.local/bin:$PATH"
npm ci
npm ci --prefix scenarios/research_ppt
npm run build --prefix scenarios/research_ppt
```

Node-pty 包的预构建检查只确认文件存在；实际直接加载报 `GLIBC_2.28 not found`。以下重建使用分发内 headers，避开首次在线取 headers 超时，已由实际 native 加载和 `pty.spawn('/bin/sh', ...)` 验证：

```sh
npm_config_build_from_source=true \
npm_config_python="$PPT_PROJECT_ROOT/.venv-sss/bin/python" \
npm_config_nodedir="$PPT_NODE_ROOT" \
npm rebuild node-pty --foreground-scripts
node -e 'require("./node_modules/node-pty"); console.log("node-pty native import OK")'
```

**每次根 `npm ci` 之后都必须重新重建并验收 PTY。** npm 会替换本机安装产物。该操作只生成 `node_modules` 构建文件，不修改上游源码、锁文件或工具权限。服务器私有日志：`test-logs/v9-node-pty-source-build-01.log`（首次网络失败）、`test-logs/v9-node-pty-source-build-local-headers-02.log`（成功）。

## 5. 本机 sharp / report 加载顺序例外

本轮会话 `run` 在第一 Provider 请求前 SIGSEGV。gdb 无参数堆栈定位到 Node `GetNodeReport → backtrace → libgcc dlopen → ELF relocation`。独立探针中 report-only、PTY、koffi、builtin 均成功；`require(sharp)` 后 `process.report.getReport()` 稳定崩溃。先预热 report，再加载 sharp / report 成功；实际 PNG 40×30→24×12、RGB `[20,80,140]` 检查成功。

因此使用项目私有预加载，不禁用图片工具、报告 API 或有效测试，不设置全局 `LD_LIBRARY_PATH`。已执行方式的匿名化等价复现：

```sh
mkdir -p .local/node-compat/bin
cat > .local/node-compat/warm-report.cjs <<'EOF'
// Ubuntu 18.04 glibc2.27: warm libgcc before sharp/Node report interaction.
// Retain no report, environment, or model data.
process.report.getReport();
EOF
cat > .local/node-compat/bin/node <<EOF
#!/bin/sh
exec "$PPT_NODE_ROOT/bin/node" --require "$PPT_PROJECT_ROOT/.local/node-compat/warm-report.cjs" "\$@"
EOF
chmod 755 .local/node-compat/bin/node
```

脚本不保存或输出 report。公共记录中的本轮实际 SHA：

| 文件 | 实际 SHA256 |
| --- | --- |
| `.local/node-compat/warm-report.cjs` | `963d3c25daa3fe4ce0514981b3a1eb8a346f27c30127f296ac8f980deaf211df` |
| `.local/node-compat/bin/node` | `fd33a3bd406f319cbc6da7a98ab0facf01cf51ce4f86c5bd3fa039af1a3809ca` |

wrapper 内含本机项目绝对路径，换目录后其 SHA 会变化；必须记录新有效 SHA，不能强填历史 hash。原始环境证据保存在私有 `.local/research-ppt/v9-quality-20261012/harness-diagnosis/` 下的 `node22-install-evidence.json`、`node-wrapper-evidence.json`、`final-verification.json`。

服务器私有证据日志为 `test-logs/v9-native-report-isolation-08.log`；主线程同步的宿主日志为 `test-logs/research-ppt-v9-quality-20261012/harness-sharp-report-warm-order-10.log`、`harness-sharp-real-PNG-11.log`。raw 日志、gdb输出和 PNG 不提交。此加载顺序例外只在这台主机被验证，未来 Node/sharp/glibc 变化须复验。

## 6. 激活、验收与回退

实际项目入口 `.local/activate.sh` 为 private 文件。以下是它公开部署部分的等价写法；首次创建可使用，已有文件先备份并检查，不覆盖其中用户自己的配置：

```sh
export PATH="$PPT_PROJECT_ROOT/.venv-sss/bin:$PPT_PROJECT_ROOT/.local/toolchain/bin:$PPT_PROJECT_ROOT/.local/bin:$PATH"
export FONTCONFIG_PATH="$PPT_PROJECT_ROOT/.local/fontconfig"
export FONTCONFIG_FILE="$PPT_PROJECT_ROOT/.local/fontconfig/fonts-static.conf"
export PATH="$PPT_NODE_ROOT/bin:$PATH"
export PATH="$PPT_PROJECT_ROOT/.local/node-compat/bin:$PATH"
```

将项目根/Node 根定位写入私有入口，随后统一 `source .local/activate.sh`。此最终入口选用第3节已核验的静态字体配置；原 `fonts.conf` 仅保留作历史诊断，不再作为最后有效入口。不要把凭证值加入公共文档。每个实验快照记录 `command -v node` 对应 wrapper、`process.execPath` 对应真实 Node，以及二者版本、SHA、preload SHA、字体配置、Python / SDK / LO / 工具版本；不要只写“使用默认环境”。

本轮无付费标准验收：

```sh
source .local/activate.sh
node --input-type=module -e 'console.log({node:process.version,main:import.meta.main})'
node -e 'require("./node_modules/sharp"); process.report.getReport(); console.log("wrapper-sharp-report-passed")'
npm test 2>&1 | tee test-logs/v9-root-tests-linux-node-wrapper-12.log
npm run smoke 2>&1 | tee test-logs/v9-smoke-linux-node-wrapper-12.log
```

新复验使用新日志名，不能覆盖这些历史证据。`npm test` 136 Python / 29 Node、smoke 18 用例已全部通过。SDK 底座集成含本地假 Provider，仅验证协议；真实科研任务须另做质量审阅、图件检查和费用记录。

回退只涉及本次私有激活调整：本轮原入口副本位于 `harness-diagnosis/activate-before-node22.sh`，用户审查后恢复该副本或移除新 Node/wrapper 的 PATH 优先项。独立 runtime/preload 可以保留供审计；不要批量删除 `.local`。回退旧 Node 会重新出现已记录的入口失败，不能把恢复旧环境称为修复。新系统的标准部署与本机兼容方案分别记录，更新前先保留旧有效配置与负面证据。
