"""无模型论文环境验收；产物仅写入 .local，不读取私人论文。"""
from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'scenarios/paper-submission/environment'
PACKAGES = ('latexmk', 'texlive-latex-extra', 'texlive-fonts-recommended',
            'texlive-fonts-extra', 'texlive-science', 'texlive-publishers',
            'texlive-plain-generic', 'texlive-xetex',
            'texlive-luatex', 'fonts-linuxlibertine', 'fonts-inconsolata',
            'tex-gyre', 'cm-super', 'poppler-utils', 'chktex')
TOOLS = ('latexmk', 'pdflatex', 'xelatex', 'lualatex', 'bibtex', 'kpsewhich',
         'pdfinfo', 'pdffonts', 'pdftotext', 'pdftoppm', 'chktex')


def call(args: list[str], *, cwd: Path = ROOT, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8]
    output = ROOT / '.local/paper-env/runs' / run_id
    output.mkdir(parents=True, mode=0o700)
    summary = {'kind': 'environment_diagnostic', 'run_id': run_id,
               'created_at': datetime.now(timezone.utc).isoformat(),
               'platform': platform.platform(), 'python': platform.python_version(),
               'fixture_sha256': {}, 'tools': {}, 'engines': {},
               'model_requests': 0, 'model_cost_usd': 0, 'failures': []}
    failures = summary['failures']
    commit = call(['git', 'rev-parse', 'HEAD'])
    summary['code_commit'] = commit.stdout.strip() if commit.returncode == 0 else None
    summary['worktree_dirty'] = bool(call(['git', 'status', '--porcelain']).stdout.strip())
    if shutil.which('dpkg-query'):
        packages = call(['dpkg-query', '-W', '-f=${Package}\t${Version}\n', *PACKAGES])
        summary['deb_packages'] = packages.stdout.splitlines()
    for name in TOOLS:
        binary = shutil.which(name)
        if binary is None:
            failures.append('missing_tool:' + name)
            continue
        result = call([binary, '-v' if name in ('latexmk', 'pdfinfo', 'pdffonts',
                                              'pdftotext', 'pdftoppm', 'chktex') else '--version'])
        lines = (result.stdout + result.stderr).strip().splitlines()
        summary['tools'][name] = {'path': binary, 'version': lines[:3]}
    source = output / 'source'
    source.mkdir()
    for name in ('main.tex', 'references.bib'):
        data = (FIXTURE / name).read_bytes()
        summary['fixture_sha256'][name] = hashlib.sha256(data).hexdigest()
        (source / name).write_bytes(data)
    if not failures:
        for engine, flag in (('pdflatex', '-pdf'), ('xelatex', '-xelatex'),
                             ('lualatex', '-lualatex')):
            work = output / engine
            work.mkdir()
            row = {'status': 'failed'}
            summary['engines'][engine] = row
            try:
                args = ['latexmk', '-norc', flag, '-no-shell-escape',
                        '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
                        '-outdir=' + str(work), 'main.tex']
                build = call(args, cwd=source)
                (work / 'build-output.txt').write_text(build.stdout + build.stderr)
                row['command'] = args
                row['exit_code'] = build.returncode
                pdf = work / 'main.pdf'
                if build.returncode != 0 or not pdf.exists():
                    failures.append('compile_failed:' + engine)
                    continue
                for tool in ('pdfinfo', 'pdffonts', 'pdftotext'):
                    args = [tool, str(pdf)] + (['-'] if tool == 'pdftotext' else [])
                    check = call(args)
                    (work / (tool + '.txt')).write_text(check.stdout + check.stderr)
                    if check.returncode:
                        failures.append(tool + '_failed:' + engine)
                    elif tool == 'pdfinfo':
                        row['pdf_metadata'] = check.stdout.splitlines()
                    elif tool == 'pdffonts':
                        font_rows = check.stdout.splitlines()[2:]
                        row['fonts_embedded'] = bool(font_rows) and all(
                            len(line.split()) >= 7 and line.split()[-5] == 'yes'
                            for line in font_rows)
                        if not row['fonts_embedded']:
                            failures.append('font_embedding_failed:' + engine)
                    elif 'Synthetic Bibliography Fixture' not in check.stdout:
                        failures.append('bibliography_missing:' + engine)
                log = (work / 'main.log').read_text(errors='replace')
                if re.search(r'(Citation .* undefined|Reference .* undefined|There were undefined references)', log):
                    failures.append('unresolved_reference:' + engine)
                row['pdf_sha256'] = hashlib.sha256(pdf.read_bytes()).hexdigest()
                row['status'] = 'passed' if not any(item.endswith(':' + engine) for item in failures) else 'failed'
            except (OSError, subprocess.TimeoutExpired) as exc:
                row['error'] = type(exc).__name__ + ': ' + str(exc)
                failures.append('execution_failed:' + engine)
    summary['status'] = 'failed' if failures else 'passed'
    target = output / 'summary.json'
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': summary['status'], 'summary': str(target),
                      'engines': {key: row['status'] for key, row in summary['engines'].items()},
                      'failures': failures}, ensure_ascii=False))
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
