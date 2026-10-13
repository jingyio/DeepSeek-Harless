"""Generic read-only uploaded files; no example data or unrestricted host paths."""
from pathlib import Path
import hashlib
import sys
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


def create_server(directory: Path):
    root = directory.resolve(strict=True)
    server = MCPServer('Harless session files')

    def list_files() -> dict:
        """List this session's uploaded files with exact content versions."""
        rows = []
        for path in sorted(root.iterdir()):
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                rows.append({'name': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        return {'files': rows}

    def read_file(name: str, sha256: str) -> dict:
        """Read UTF-8 text with the version returned by list_files; reject traversal and changed files."""
        if not name or Path(name).name != name or name in ('.', '..') or '\\' in name:
            raise ToolError('file_not_in_session')
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            raise ToolError('file_not_in_session')
        if path.stat().st_size > 256 * 1024:
            raise ToolError('text_file_too_large')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ToolError('file_version_changed')
        try: text = data.decode('utf-8')
        except UnicodeDecodeError: raise ToolError('not_utf8_text') from None
        return {'name': name, 'sha256': sha256, 'text': text}

    for fn in (list_files, read_file):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    create_server(Path(sys.argv[1])).run(transport='stdio')
