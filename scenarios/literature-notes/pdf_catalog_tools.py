"""Local PDF catalog service; semantic metadata extraction stays in Harness."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pdf_tools import ROOT, PdfScene, digest, inventory, normalized, save_private
from pdf_dependencies import private_file
from bibliography_tools import preview_bibliography
from catalog_metadata import metadata_candidates, resolve_year, check_author_coverage

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG_QUESTION = '为选定 PDF 建立或更新文献索引和 BibTeX 引用目录，仅抄录原文可见元数据，保留缺失项和所有文件。'


def execution_version():
    names = ['pdf_catalog_tools.py', 'catalog_metadata.py', 'catalog_entry.py', 'pdf-catalog-task.md', 'pdf-catalog-scenario.json',
             'pdf-catalog-contracts.json', 'pdf_tools.py', 'pdf_layout.py', 'pdf_read_plan.py', 'bibliography_tools.py']
    return digest({n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in names})


class LiteralMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: str | None = Field(description='Copy visible text; null when unavailable.', max_length=500)
    anchor: str = Field(description='Continuous verbatim text from this paper packet; empty for null.', max_length=1800)


class CatalogYear(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: str | None = Field(max_length=80, description='Copy a publication/preprint date candidate ID; null permits unambiguous Runtime projection.')


class AuthorCoverage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['covered','partial','unavailable']
    region_ids: list[str] = Field(max_length=16)
    reason: str = Field(max_length=300)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    paper_id: str
    title: LiteralMetadata
    authors: list[LiteralMetadata] = Field(max_length=60)
    author_coverage: AuthorCoverage
    year: CatalogYear
    doi: LiteralMetadata
    arxiv: LiteralMetadata


def escape_bib(value):
    escapes = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%', '&': r'\&',
               '_': r'\_', '#': r'\#', '$': r'\$'}
    return ''.join(escapes.get(c, c) for c in normalized(value))


def render_bib(records):
    rows = []
    for row in records:
        meta = row['metadata']; fields = {}
        for name in ('title', 'year', 'doi'):
            if meta[name]['value'] is not None: fields[name] = meta[name]['value']
        if meta['authors']: fields['author'] = ' and '.join(a['value'] for a in meta['authors'])
        if meta['arxiv']['value'] is not None:
            fields.update(eprint=meta['arxiv']['value'], archivePrefix='arXiv')
        # Filename identity keeps exact duplicate files distinct; scholarly identity is unverified.
        key = 'pdf' + digest(row['paper_id'])[:16]
        rows.append('@misc{' + key + ',\n' + ',\n'.join('  ' + k + ' = {' + escape_bib(v) + '}'
                    for k, v in fields.items()) + '\n}')
    return '\n\n'.join(rows) + '\n'


class CatalogScene(PdfScene):
    def __init__(self, directory, task, output, *, previous=None):
        super().__init__(Path(directory), ROOT / '.local/literature-notes/pdf-cache', task)
        output = Path(output)
        if output.is_symlink() or not output.resolve().is_relative_to(ROOT / '.local'):
            raise ValueError('catalog output must remain private')
        self.output = output.resolve(); self.previous_path = private_file(previous) if previous else None
        self.previous_bytes_sha256 = hashlib.sha256(self.previous_path.read_bytes()).hexdigest() if previous else None
        self.execution_version = execution_version(); self.packets = {}; self.plan_read = False
        self.previous = json.loads(self.previous_path.read_text()) if previous else None
        if self.previous is not None:
            body = self.previous.get('catalog')
            if (self.previous.get('schema_version') != 1 or not isinstance(body, dict)
                    or digest(body) != self.previous.get('catalog_sha256')
                    or body.get('schema_version') != 1 or not isinstance(body.get('records'), list)
                    or len(body['records']) > 20
                    or len({r['paper_id'] for r in body['records']}) != len(body['records'])):
                raise ValueError('previous catalog integrity or unique records changed')

    def _guard(self):
        if inventory(self.root) != self.task['sources'] or execution_version() != self.execution_version:
            raise ToolError('PDF selection or catalog implementation changed; start a new task')
        if self.previous_path and hashlib.sha256(private_file(self.previous_path).read_bytes()).hexdigest() != self.previous_bytes_sha256:
            raise ToolError('previous catalog changed during this task')

    def _packet(self, paper_id):
        self._current(paper_id)
        document = self._document(paper_id)
        text = document['pages'][0][:10000]
        candidates = metadata_candidates(text, self.document_version(paper_id))
        return {'paper_id': paper_id, 'pdf_sha256': self.rows[paper_id]['pdf_sha256'],
                'document_version_sha256': self.document_version(paper_id),
                'parser_profile_sha256': digest(self.profile), 'page': 1, 'start': 0, 'end': len(text),
                'text': text, 'text_sha256': digest(text), 'page_complete': len(text) == len(document['pages'][0]),
                'status': 'low_text_needs_review' if len(text.strip()) < 100 else 'text_available',
                'scope': 'first physical page only; missing metadata does not prove absence in the paper',
                **candidates,
                'cache_stats': dict(self.stats)}

    def _checked(self, submitted, packet):
        row = CatalogEntry.model_validate(submitted).model_dump()
        meta = {k: v for k, v in row.items() if k not in ('paper_id','author_coverage','year')}
        if row['paper_id'] != packet['paper_id']: raise ToolError('metadata belongs to a different PDF')
        values = [(k, v) for k, v in meta.items() if k != 'authors'] + [('author:' + str(i), v) for i,v in enumerate(meta['authors'])]
        issues = []
        for name, v in values:
            value, anchor = v['value'], v['anchor']
            if value is None:
                if anchor or name.startswith('author:'):
                    issues.append({'field':name,'reason':'null requires empty anchor; omit unavailable authors'})
                continue
            if (not normalized(value) or value != value.strip() or not normalized(anchor)
                    or normalized(anchor) not in normalized(packet['text'])
                    or normalized(value) not in normalized(anchor)):
                issues.append({'field':name,'value':value,'reason':'value and anchor must match raw extracted packet text; preserve spaced capitals/missing glyphs',
                    'anchor_in_source':bool(normalized(anchor)) and normalized(anchor) in normalized(packet['text']),
                    'value_in_anchor':bool(normalized(value)) and normalized(value) in normalized(anchor)})
            if name == 'doi' and not re.fullmatch(r'10\.\d{4,9}/\S+', value): issues.append({'field':name,'reason':'invalid visible DOI; copy only 10.xxxx/suffix, without URL prefix'})
            if name == 'arxiv' and not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[A-Za-z.-]+/\d{7})(?:v\d+)?', value):
                issues.append({'field':name,'reason':'invalid visible arXiv ID; copy only identifier/version, without arXiv: prefix'})
        if issues: raise ToolError('catalog metadata validation: ' + json.dumps({'paper_id':row['paper_id'],'issues':issues},ensure_ascii=False))
        author_values = [v['value'] for v in meta['authors']]
        if len(set(author_values)) != len(author_values): raise ToolError('duplicate author metadata')
        meta['year'] = resolve_year(row['year'], packet)
        coverage = check_author_coverage(row['author_coverage'],meta['authors'],packet)
        return {'paper_id': row['paper_id'], 'filename': self.rows[row['paper_id']]['filename'],
                'pdf_sha256': packet['pdf_sha256'], 'document_version_sha256': packet['document_version_sha256'],
                'parser_profile_sha256': packet['parser_profile_sha256'],
                'source_packet_sha256': digest({k: v for k, v in packet.items() if k != 'cache_stats'}),
                'metadata': meta, 'submission':row, 'author_coverage':coverage,
                'metadata_semantics_verified': False, 'scholarly_identity_certified': False}

    def _plan(self):
        old = {r['paper_id']: r for r in self.previous['catalog']['records']} if self.previous else {}
        compatible = bool(self.previous and self.previous['catalog'].get('execution_version_sha256') == self.execution_version)
        retained, work = [], []
        for pid, row in self.rows.items():
            prev = old.get(pid)
            reusable = bool(compatible and prev and prev.get('pdf_sha256') == row['pdf_sha256']
                            and prev.get('document_version_sha256') == self.document_version(pid))
            if reusable:
                checked = self._checked(prev['submission'], self._packet(pid))
                if checked != prev: raise ToolError('retained metadata or source packet changed')
                retained.append(pid)
            else:
                work.append({'paper_id': pid, 'filename': row['filename'], 'reason':
                             'new_file' if not prev else 'source_or_execution_version_changed'})
        groups = {}
        for row in self.rows.values(): groups.setdefault(row['pdf_sha256'], []).append(row['paper_id'])
        body = {'question': self.task['question'], 'task_sha256': digest(self.task),
                'previous_catalog_sha256': self.previous.get('catalog_sha256') if self.previous else None,
                'execution_version_sha256': self.execution_version, 'work': work, 'retained_ids': retained,
                'removed_ids': sorted(set(old) - set(self.rows)),
                'exact_duplicate_files': [ids for ids in groups.values() if len(ids) > 1],
                'duplicates_automatically_merged': False, 'metadata_verified_online': False}
        return {**body, 'plan_sha256': digest(body)}

    def read_catalog_plan(self) -> dict:
        """Return all new/changed PDF IDs, source-checked retained IDs and exact file duplicates."""
        self._guard(); plan = self._plan(); self.plan_read = True
        return plan

    def read_catalog_packet(self, paper_id: str) -> dict:
        """Read a versioned first-page metadata packet for one member of the actual work list."""
        self._guard()
        if not self.plan_read or paper_id not in [r['paper_id'] for r in self._plan()['work']]:
            raise ToolError('read the catalog plan first and read only actual work members')
        packet = self._packet(paper_id); self.packets[paper_id] = packet
        return copy.deepcopy(packet)

    def publish(self, entries, *, persist=True):
        self._guard(); plan = self._plan(); ids = [r['paper_id'] for r in plan['work']]
        if not self.plan_read or not isinstance(entries, list) or len(entries) != len(ids):
            raise ToolError('submit exactly one metadata decision for every work member, including missing values')
        submitted = [CatalogEntry.model_validate(e).model_dump() for e in entries]
        if {e['paper_id'] for e in submitted} != set(ids) or len({e['paper_id'] for e in submitted}) != len(ids):
            raise ToolError('missing, duplicate or out-of-scope catalog entry')
        changed = {}
        for entry in submitted:
            pid = entry['paper_id']
            if pid not in self.packets: raise ToolError('read the current packet before submitting metadata')
            if digest({k:v for k,v in self._packet(pid).items() if k != 'cache_stats'}) != digest({k:v for k,v in self.packets[pid].items() if k != 'cache_stats'}):
                raise ToolError('packet changed after the model read')
            changed[pid] = self._checked(entry, self.packets[pid])
        previous = {r['paper_id']: r for r in self.previous['catalog']['records']} if self.previous else {}
        records = [changed[pid] if pid in changed else copy.deepcopy(previous[pid]) for pid in self.rows]
        missing = [{'paper_id': r['paper_id'], 'fields': [k for k in ('title', 'year', 'doi', 'arxiv')
                    if r['metadata'][k]['value'] is None] + ([] if r['metadata']['authors'] else ['authors'])} for r in records]
        gaps = [{'paper_id':r['paper_id'], 'fields':[k for k in ('title','authors') if
                 (not r['metadata']['authors'] if k=='authors' else r['metadata'][k]['value'] is None)]} for r in records]
        gaps = [g for g in gaps if g['fields']]
        for row in records:
            if row['author_coverage']['status']=='partial':
                gaps.append({'paper_id':row['paper_id'],'fields':['author_coverage'], 'reason':row['author_coverage']['reason']})
            if row['metadata']['year']['selection_origin']=='runtime_ambiguous_dates':
                gaps.append({'paper_id':row['paper_id'],'fields':['year'],'reason':'conflicting explicit date years; no candidate selected'})
        bib = render_bib(records)
        payload = {'schema_version':1, 'status':'needs_review' if gaps else 'preview', 'task_sha256':digest(self.task),
                   'plan_sha256':plan['plan_sha256'], 'execution_version_sha256':self.execution_version,
                   'records':records, 'missing_metadata':missing, 'gaps':gaps,
                   'retained_ids':plan['retained_ids'], 'removed_ids':plan['removed_ids'],
                   'exact_duplicate_files':plan['exact_duplicate_files'], 'submitted_entries':submitted,
                   'bibliography':bib, 'metadata_verified_online':False, 'scholarly_identity_certified':False,
                   'all_current_files_retained':True, 'user_file_writes_enabled':False}
        if not persist: return payload
        # Reuse the existing pinned citation formatter as an offline export check.
        bib_check = preview_bibliography(bib)
        if bib_check['entry_count'] != len(records) or bib_check['unparsed_remainder_present']:
            raise ToolError('generated bibliography failed the existing parser; no catalog receipt')
        envelope = {'schema_version':1, 'catalog':payload, 'catalog_sha256':digest(payload)}
        save_private(self.output/'catalog.json', envelope)
        bib_path = self.output/'catalog.bib'; bib_path.write_text(bib, encoding='utf-8'); bib_path.chmod(0o600)
        md = self.output/'catalog.md'
        md.write_text('# 文献索引\n\n' + '\n\n'.join('## ' + (r['metadata']['title']['value'] or '标题缺失') + '\n\n' +
                      '- 文件：' + r['filename'] + '\n- 作者：' + ('；'.join(a['value'] for a in r['metadata']['authors']) or '缺失') +
                      '\n- 年份：' + (r['metadata']['year']['value'] or '未从首页确认') for r in records) +
                      '\n\n元数据来自模型抄录及原文锚点校验，未联网核验文献身份。\n', encoding='utf-8'); md.chmod(0o600)
        self._guard()
        return {'status':payload['status'], 'artifact':str(self.output/'catalog.json'), 'artifact_sha256':digest(envelope),
                'catalog_sha256':digest(payload),
                'bibtex':str(bib_path), 'bibtex_sha256':hashlib.sha256(bib_path.read_bytes()).hexdigest(),
                'index':str(md), 'entry_count':len(records), 'processed_count':len(ids),
                'retained_count':len(plan['retained_ids']), 'gap_count':len(gaps), 'plan_sha256':plan['plan_sha256'],
                'task_sha256':digest(self.task), 'metadata_verified_online':False, 'application_enabled':False}

    def submit_catalog(self, entries: list[CatalogEntry]) -> dict:
        """Validate exactly the changed metadata records and save private JSON, index and BibTeX."""
        return self.publish([e.model_dump() for e in entries])


def make_server(scene):
    server = MCPServer('Local PDF bibliography catalog')
    for fn in (scene.read_catalog_plan, scene.read_catalog_packet, scene.submit_catalog):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    task = json.loads(Path(os.environ['SSS_PDF_TASK_FILE']).read_text())
    make_server(CatalogScene(Path(task['sources']['root']), task, os.environ['SSS_PDF_CATALOG_OUTPUT'],
                            previous=os.environ.get('SSS_PDF_CATALOG_PREVIOUS') or None)).run(transport='stdio')
