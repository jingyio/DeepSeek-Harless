"""明确页面修改的薄启动边界；在线校验和执行由 TypeScript 负责。"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCENE = Path(__file__).resolve().parent


def command(arguments: list[str]) -> list[str]:
    node = shutil.which('node')
    script = SCENE / 'dist/direct-edit-cli.js'
    if not node or not script.is_file():
        raise RuntimeError('需要已安装 Node 与场景构建产物；先 npm run build --prefix scenarios/research_ppt')
    return [node, str(script), *arguments]


def launch(arguments: list[str]) -> int:
    # 仅把项目工具链、字体和当前解释器传给 Node；不把 API 凭证传入 MCP 路径。
    allowed = ('PATH', 'PATHEXT', 'SYSTEMROOT', 'COMSPEC', 'TEMP', 'TMP', 'TMPDIR',
               'HOME', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'USER', 'USERNAME',
               'FONTCONFIG_FILE', 'FONTCONFIG_PATH')
    env = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    env.update(SSS_PPT_DELIVERY_PYTHON=sys.executable, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    return subprocess.call(command(arguments), cwd=ROOT, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(launch(sys.argv[1:]))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
