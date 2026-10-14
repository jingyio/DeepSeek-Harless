"""Bounded offline BibTeX preview using pinned upstream citation-management code."""
import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4
from mcp.server.mcpserver.exceptions import ToolError
from pdf_tools import ROOT, digest, save_private

VENDOR = Path(__file__).resolve().parent / 'vendor/scientific-skills'


def preview_bibliography(bibtex: str) -> dict:
    """Preview BibTeX formatting and possible duplicates; retain every entry, no identity or claim-support approval."""
    if not isinstance(bibtex, str) or not 1 <= len(bibtex) <= 30000:
        raise ToolError('provide 1–30000 characters of BibTeX source, never a filesystem path')
    provenance = json.loads((VENDOR / 'PROVENANCE.json').read_text())
    for row in provenance['files']:
        if hashlib.sha256((VENDOR / row['local_path']).read_bytes()).hexdigest() != row['sha256']:
            raise ToolError('vendored scientific skill digest changed')
    scripts = VENDOR / 'skills/citation-management/scripts'
    spec = importlib.util.spec_from_file_location('literature_bib_formatter', scripts / 'format_bibtex.py')
    formatter_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(formatter_module)
    import _common
    entries = _common.parse_bibtex(bibtex)
    if not 1 <= len(entries) <= 100:
        raise ToolError('no parseable entries or more than 100 entries; inspect bibliography syntax')
    formatter = formatter_module.BibTeXFormatter()
    fixed = [formatter.fix_common_issues(entry) for entry in entries]
    groups, missing = {}, []
    for entry in fixed:
        doi = entry['fields'].get('doi', '').strip().lower()
        groups.setdefault('key:' + entry['key'], []).append(entry['key'])
        if doi: groups.setdefault('doi:' + doi, []).append(entry['key'])
        absent = [name for name in ('title', 'author', 'year') if not entry['fields'].get(name)]
        if absent: missing.append({'key': entry['key'], 'missing': absent})
    duplicates = [{'identity': key, 'keys': keys} for key, keys in groups.items() if len(keys) > 1]
    remainder = bibtex
    for entry in entries: remainder = remainder.replace(entry['raw'], '', 1)
    result = {'source_sha256': digest(bibtex), 'entry_count': len(fixed),
              'formatted_bibtex': '\n\n'.join(formatter.format_entry(entry) for entry in fixed) + '\n',
              'possible_duplicates': duplicates, 'missing_metadata': missing,
              'unparsed_remainder': remainder.strip(), 'all_entries_retained': True,
              'metadata_verified_online': False, 'scholarly_identity_certified': False,
              'claim_support_assessed': False, 'application_enabled': False,
              'upstream_commit': provenance['commit'],
              'warning': 'Preview only. Malformed fields/macros may be skipped; inspect original before exporting.'}
    artifact = ROOT / '.local/literature-notes/bibliography-previews' / (uuid4().hex + '.json')
    save_private(artifact, result)
    return {'artifact': str(artifact), 'artifact_sha256': digest(result), 'entry_count': len(fixed),
            'possible_duplicate_count': len(duplicates), 'missing_metadata_count': len(missing),
            'unparsed_remainder_present': bool(remainder.strip()), 'all_entries_retained': True,
            'metadata_verified_online': False, 'claim_support_assessed': False, 'application_enabled': False}
