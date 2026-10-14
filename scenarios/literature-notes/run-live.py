"""Load a private API key and reuse the bounded scenario runner; preview by default."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY_FILE = ROOT / '.local/deepseek.env'


def load_key(path: Path, environment: dict[str, str]) -> str:
    """Parse a single assignment as data; never execute or print the file."""
    value = environment.get('DEEPSEEK_API_KEY', '')
    if not value:
        if not path.is_file():
            raise ValueError('请先填写 .local/deepseek.env 中的 DEEPSEEK_API_KEY。')
        lines = [line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines()
                 if line.strip() and not line.lstrip().startswith('#')]
        if len(lines) != 1:
            raise ValueError('密钥文件只能包含注释和一行 DEEPSEEK_API_KEY 赋值。')
        assignment = lines[0].removeprefix('export ').strip()
        name, separator, raw = assignment.partition('=')
        if name.strip() != 'DEEPSEEK_API_KEY' or not separator:
            raise ValueError('密钥文件需要 DEEPSEEK_API_KEY 赋值。')
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError:
            raise ValueError('密钥文件格式错误，请把 Key 放在成对引号内。') from None
        if len(parts) != 1:
            raise ValueError('请先在引号内填写 API Key。')
        value = parts[0]
    if not value or len(value) > 4096 or any(char.isspace() for char in value):
        raise ValueError('API Key 为空或包含空白，请检查本机配置。')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--call-model', action='store_true', help='显式启用付费模型调用')
    action.add_argument('--check-key', action='store_true', help='仅检查本机 Key 是否已填写，不联网')
    parser.add_argument('--case', default='eval_leakage',
                        choices=['train_seed', 'train_protocol', 'certify_cost', 'eval_leakage'])
    args = parser.parse_args(argv)
    env = os.environ.copy()
    if args.call_model or args.check_key:
        try:
            env['DEEPSEEK_API_KEY'] = load_key(KEY_FILE, env)
        except ValueError as exc:
            parser.error(str(exc))
    if args.check_key:
        print('API Key 已配置；未显示密钥、未联网、未产生付费调用。')
        return 0
    # Key stays in the child environment, never command arguments or preview output.
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'),
               '--scenario', str(HERE / 'scenario.json'), '--case', args.case,
               '--model', 'deepseek-flash', '--budget-usd', '0.25',
               '--max-steps', '8', '--max-output', '2000']
    if args.call_model:
        command.append('--call-model')
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
