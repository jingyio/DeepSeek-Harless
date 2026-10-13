"""Generic read-only uploaded files; no example data or unrestricted host paths."""
from pathlib import Path
import hashlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.adapters.session_files import SessionFiles
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


def create_server(directory: Path):
    files = SessionFiles(directory)
    server = MCPServer('Harless session files')

    def list_files() -> dict:
        """List this session's uploaded files with exact content versions."""
        return files.list_files()

    def read_file(name: str, sha256: str) -> dict:
        """Read UTF-8 text with the version returned by list_files; reject traversal and changed files."""
        try: data, _ = files.read(name,sha256,limit=256*1024)
        except (ValueError,OSError) as exc:raise ToolError(str(exc)) from None
        try: text = data.decode('utf-8')
        except UnicodeDecodeError: raise ToolError('not_utf8_text') from None
        return {'name': name, 'sha256': sha256, 'text': text}

    for fn in (list_files, read_file):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    create_server(Path(sys.argv[1])).run(transport='stdio')
