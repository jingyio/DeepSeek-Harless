"""Minimal custom MCP extension: pinned, versioned read-only evidence."""
import hashlib
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

NOTES = {'note:alpha': 'Trial A has two seeds. Conclusions need independent replication.',
         'note:beta': 'Trial B has five seeds, but uses a different evaluation protocol.'}
handles = {}


def pin_note(object_id: str) -> dict:
    """Bind one public demo note to its content version. Accept note:alpha or note:beta."""
    if object_id not in NOTES:
        raise ToolError('unknown demo object')
    version = hashlib.sha256(NOTES[object_id].encode()).hexdigest()
    source_id = 'source-' + hashlib.sha256((object_id + version).encode()).hexdigest()[:32]
    handles[source_id] = (object_id, version)
    return {'object_id': object_id, 'source_id': source_id, 'version_sha256': version}


def read_pinned_note(source_id: str) -> dict:
    """Read a note using only the source_id returned by pin_note; reject changed versions."""
    if source_id not in handles:
        raise ToolError('unknown source_id; pin a note first')
    object_id, version = handles[source_id]
    if hashlib.sha256(NOTES[object_id].encode()).hexdigest() != version:
        raise ToolError('source changed; pin again')
    return {'source_id': source_id, 'object_id': object_id,
            'version_sha256': version, 'text': NOTES[object_id]}


if __name__ == '__main__':
    server = MCPServer('SSS demo evidence')
    for fn in (pin_note, read_pinned_note):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    server.run(transport='stdio')
