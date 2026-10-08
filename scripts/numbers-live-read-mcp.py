#!/usr/bin/env python3
"""Read-only, one-file scope around unmodified Digits live Numbers handlers.

No spreadsheet data is simulated or parsed outside Numbers. Native tool
parameters/defaults and batching are retained. JSON envelopes add the frozen
file revision and unambiguous singleton aliases for trace provenance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '.local/numbers-digits-upstream/server/digits_server.py'
spec = importlib.util.spec_from_file_location('digits', UPSTREAM)
digits = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digits)
ALLOWED = ('numbers_open_document', 'numbers_list_sheets',
           'numbers_list_tables', 'numbers_read_table')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    scope = json.loads(Path(os.environ['SSS_NUMBERS_SCOPE']).read_text())
    path = Path(scope['path']).resolve(strict=True)
    if not path.is_relative_to(ROOT / '.local/benchmarks/numbers-live-v1'):
        raise ValueError('scope must identify an experiment-owned workbook')
    expected = scope['sha256']
    document = scope['document']
    def assert_saved():
        modified = digits._run('tell application "Numbers" to get modified of document ' + digits._q(document))
        if modified.strip() != 'false':
            raise digits.ToolError('Workbook has unsaved changes; stop and refresh the task scope.')
    # Opening by default keeps the upstream front-document convenience while
    # ensuring it always refers to the authorized file, even across UI changes.
    def call(name, args):
        if file_hash(path) != expected:
            raise digits.ToolError('Workbook revision changed; stop and refresh the task scope.')
        supplied = dict(args)
        if name == 'numbers_open_document':
            if Path(supplied['path']).resolve() != path:
                raise digits.ToolError('Workbook is outside this task scope.')
        else:
            if supplied.get('document', document) != document:
                raise digits.ToolError('Document is outside this task scope.')
            supplied['document'] = document
            assert_saved()
        result = digits.TOOLS[name][2](supplied)
        assert_saved()
        if file_hash(path) != expected:
            raise digits.ToolError('Workbook changed during the read.')
        output = {'source_version': expected, 'native_result': result}
        if name == 'numbers_open_document':
            if result != document:
                raise digits.ToolError('Opened document identity differs from the frozen scope.')
            output['document'] = result
        elif name == 'numbers_list_sheets':
            output['only_sheet'] = result[0] if len(result) == 1 else None
        elif name == 'numbers_list_tables':
            output['only_table'] = result[0]['name'] if len(result) == 1 else None
        return output

    original = dict(digits.TOOLS)
    # Store native handlers separately; wrapper lookups must not recurse.
    def wrapped(name):
        def handler(args):
            # call uses the native table, while the RPC dispatcher uses allowed.
            current = digits.TOOLS
            digits.TOOLS = original
            try:
                return call(name, args)
            finally:
                digits.TOOLS = current
        return handler
    digits.TOOLS = {name: (original[name][0], original[name][1], wrapped(name))
                    for name in ALLOWED}
    for line in sys.stdin:
        if line.strip():
            digits._handle(json.loads(line))


if __name__ == '__main__':
    main()
