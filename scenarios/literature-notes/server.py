"""Read-only, synthetic annotation-to-note scenario; never accesses user apps."""
from __future__ import annotations

import argparse
from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

HERE = Path(__file__).resolve().parent
START = '<!-- literature-evidence:start -->'
END = '<!-- literature-evidence:end -->'


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':')).encode()).hexdigest()


def load_fixture(case: str) -> dict:
    fixtures = json.loads((HERE / 'fixtures.json').read_text(encoding='utf-8'))
    if case not in fixtures:
        raise ValueError('unknown literature fixture case')
    return fixtures[case]


class LiteratureScene:
    """Opaque handles bind the entire selected annotation/paper/note snapshot."""

    def __init__(self, fixture: dict):
        self.fixture = deepcopy(fixture)
        self.handles: dict[str, str] = {}
        self.context_cache: dict[str, dict] = {}

    def pin_annotation_change(self, change_id: str) -> dict:
        """Pin the explicitly selected annotation change and its paper/note snapshot; no relevance selection."""
        if change_id != self.fixture['change_id']:
            raise ToolError('change outside the selected task scope')
        version = digest(self.fixture)
        source_id = 'source-' + digest([change_id, version])[:32]
        self.handles[source_id] = version
        return {'change_id': change_id, 'source_id': source_id,
                'version_sha256': version, 'kind': 'annotation_context',
                'scope': 'synthetic_read_only'}

    def _current(self, source_id: str) -> str:
        if source_id not in self.handles:
            raise ToolError('unknown source_id; pin the selected change first')
        version = self.handles[source_id]
        if digest(self.fixture) != version:
            raise ToolError('source changed; pin the change again')
        return version

    def read_pinned_annotation_context(self, source_id: str) -> dict:
        """Read the pinned annotation, extracted page and selected note; reject any dependency version change."""
        version = self._current(source_id)
        if version not in self.context_cache:
            self.context_cache[version] = deepcopy(self.fixture)
        return {'version_sha256': version, 'context': deepcopy(self.context_cache[version])}

    def preview_note_update(self, source_id: str) -> dict:
        """Preview an attributed quote in the selected note; return semantic gaps without writing files or apps."""
        version = self._current(source_id)
        if version not in self.context_cache:
            raise ToolError('read the pinned context before requesting its preview')
        context = deepcopy(self.context_cache[version])
        annotation, paper = context['annotation'], context['paper']
        note = next((row for row in context['notes']
                     if row['note_id'] == context['selected_note_id']), None)
        dependencies = {'snapshot_sha256': version,
                        'annotation_sha256': digest(annotation),
                        'paper_sha256': digest(paper),
                        'policy_version': 'attributed-quote-v1'}
        result = {'version_sha256': version, 'scope': 'synthetic_read_only',
                  'application_enabled': False, 'dependencies': dependencies}
        if note is None:
            return {**result, 'status': 'needs_review', 'gap': 'note_selection', 'diff': None}
        dependencies['note_sha256'] = digest(note)
        page = next((row for row in paper['pages'] if row['page'] == annotation['page']), None)
        if (annotation['paper_id'] != paper['paper_id'] or page is None
                or not annotation['quote'].strip() or annotation['quote'] not in page['text']):
            return {**result, 'status': 'needs_review', 'gap': 'quote_location', 'diff': None}
        before = note['text']
        if (before.count(START) != 1 or before.count(END) != 1
                or before.index(START) >= before.index(END)):
            return {**result, 'status': 'needs_review', 'gap': 'managed_region', 'diff': None}
        # The marker is a stable annotation identity, not a content-similarity guess.
        marker = '<!-- annotation:' + annotation['annotation_id'] + ' -->'
        citation = {'paper_id': paper['paper_id'], 'page': annotation['page'],
                    'quote': annotation['quote'], 'annotation_id': annotation['annotation_id'],
                    'paper_sha256': dependencies['paper_sha256']}
        common = {**result, 'note_id': note['note_id'], 'before': before,
                  'expected_note_sha256': digest(note), 'citation': citation}
        # Existing evidence may have been manually revised: never overwrite it automatically.
        if marker in before:
            return {**common, 'status': 'needs_review', 'gap': 'existing_annotation', 'diff': None}
        entry = ('\n' + marker + '\n> ' + annotation['quote'].replace('\n', '\n> ')
                 + '\n\n来源：' + paper['title'] + '，p. ' + str(annotation['page'])
                 + '；' + paper['paper_id'] + '；批注 ' + annotation['annotation_id']
                 + '\n\n用户批注：' + annotation['comment'] + '\n\n')
        after = before.replace(END, entry + END, 1)
        diff = ''.join(difflib.unified_diff(before.splitlines(keepends=True),
                     after.splitlines(keepends=True), fromfile=note['note_id'],
                     tofile=note['note_id'] + '.preview'))
        return {**common, 'status': 'preview', 'after': after, 'diff': diff,
                'semantic_status': 'quote_location_checked; claim_support_not_assessed'}


def make_server(scene: LiteratureScene) -> MCPServer:
    server = MCPServer('Synthetic literature note preview')
    for fn in (scene.pin_annotation_change, scene.read_pinned_annotation_context,
               scene.preview_note_update):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', default='eval_leakage')
    args = parser.parse_args()
    make_server(LiteratureScene(load_fixture(args.case or 'eval_leakage'))).run(transport='stdio')
