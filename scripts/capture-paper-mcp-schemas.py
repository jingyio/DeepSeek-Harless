#!/usr/bin/env python3
"""Capture the complete current paper MCP schema without a model request."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def capture(output: Path):
    private = (ROOT / '.local').resolve()
    output = output.resolve()
    if not output.is_relative_to(private):
        raise ValueError('schema snapshot must remain private')
    rows = []
    with TemporaryDirectory(prefix='paper-schema-', dir=private) as temporary:
        work = Path(temporary) / 'work'
        inputs = work / 'inputs'
        inputs.mkdir(parents=True)
        (work / 'approved-inputs.json').write_text('{"files":{}}')
        servers = [
            ('paper_checks', sys.executable,
             [str(ROOT / 'scenarios/paper_proofreading/server.py'), str(inputs)], {}),
            ('paper_trace_rsi', 'node',
             ['--experimental-strip-types', str(ROOT / 'scenarios/paper_proofreading/revision_session.ts'), str(work)],
             {'HARLESS_PRIVATE_ROOT': temporary}),
        ]
        for name, command, args, extra in servers:
            async with Client(StdioServerParameters(command=command, args=args, cwd=ROOT,
                                                    env={**os.environ, **extra})) as client:
                listing = await client.list_tools()
                for tool in listing.tools:
                    row = tool.model_dump(mode='json')
                    rows.append({'name': f'mcp__{name}__{row["name"]}',
                                 'description': row['description'],
                                 'parameters': row.get('inputSchema', row.get('input_schema'))})
    rows.sort(key=lambda row: row['name'])
    scenario = json.loads((ROOT / 'scenarios/paper_proofreading/scenario.json').read_text())
    if [row['name'] for row in rows] != sorted(scenario['allowed_tools']):
        raise ValueError('actual MCP tools differ from paper scenario whitelist')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({'schemas': str(output), 'tool_count': len(rows), 'model_requests': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(capture(parser.parse_args().output))
