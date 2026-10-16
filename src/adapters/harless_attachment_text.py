"""Read-only model context for approved uploads; never execute attachment content.

The caller owns authorization and the approved-source hash check. This module
reads one stable regular file and reports its exact hash, full extracted text,
and explicit extraction coverage. Unsupported files remain accepted metadata.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

MAX_FILE_BYTES = 20 * 1024 * 1024  # Existing upload boundary, not a text limit.
# Match the existing Office parser's archive-bomb protection. No text is sliced.
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
TEXT_SUFFIXES = {'.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.jsonl',
                 '.yaml', '.yml', '.xml', '.html', '.htm', '.tex', '.bib', '.bbl',
                 '.log', '.rst', '.py', '.js', '.ts', '.css', '.sql', '.r'}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
PACKAGE_R = 'http://schemas.openxmlformats.org/package/2006/relationships'
STRICT_NAMESPACES = {
    'http://purl.oclc.org/ooxml/wordprocessingml/main': W,
    'http://purl.oclc.org/ooxml/drawingml/main': A,
    'http://purl.oclc.org/ooxml/officeDocument/relationships': R,
    'http://purl.oclc.org/ooxml/presentationml/main': P,
    'http://purl.oclc.org/ooxml/spreadsheetml/main': S,
}


class ExtractionIssue(ValueError):
    """A stable public code; original parser exceptions never leave the helper."""


class _SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ExtractionIssue('office_xml_doctype_disallowed')


def _xml(data: bytes):
    root = ET.fromstring(data, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    # Strict and Transitional OOXML use the same text structures here. Map
    # only their known namespaces, never local names or document text values.
    def canonical(name):
        if name.startswith('{'):
            namespace, local = name[1:].split('}', 1)
            return '{' + STRICT_NAMESPACES.get(namespace, namespace) + '}' + local
        return name
    for node in root.iter():
        node.tag = canonical(node.tag)
        attributes = {}
        for key, value in node.attrib.items():
            key = canonical(key)
            if key in attributes:
                raise ExtractionIssue('office_xml_ambiguous_attribute')
            attributes[key] = value
        node.attrib = attributes
    return root


def _require_part(root, namespace: str, local: str):
    if root.tag != '{' + namespace + '}' + local:
        raise ExtractionIssue('office_xml_namespace_unsupported')
    return root


def _read(path: Path) -> bytes:
    if path.is_symlink():
        raise ExtractionIssue('attachment_not_regular')
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ExtractionIssue('attachment_not_regular')
            if before.st_size > MAX_FILE_BYTES:
                raise ExtractionIssue('attachment_upload_limit')
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            if len(data) > MAX_FILE_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ExtractionIssue('attachment_changed_during_read')
            return data
    except OSError:
        raise ExtractionIssue('attachment_unavailable') from None


def _text(data: bytes) -> tuple[str, str]:
    for marker, encoding in ((codecs.BOM_UTF32_LE, 'utf-32'), (codecs.BOM_UTF32_BE, 'utf-32'),
                             (codecs.BOM_UTF16_LE, 'utf-16'), (codecs.BOM_UTF16_BE, 'utf-16')):
        if data.startswith(marker):
            text = data.decode(encoding)
            break
    else:
        encoding, text = 'utf-8-sig', data.decode('utf-8-sig')
    if any(ord(character) < 32 and character not in '\t\r\n\f' for character in text):
        raise ExtractionIssue('binary_content_not_text')
    return text, encoding


def _archive(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    infos = archive.infolist()
    names = [item.filename for item in infos]
    if len(infos) > MAX_ARCHIVE_FILES or sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES:
        archive.close()
        raise ExtractionIssue('office_archive_resource_limit')
    if len(names) != len(set(names)) or any(PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
                                          or '\\' in name or ':' in name for name in names):
        archive.close()
        raise ExtractionIssue('office_archive_invalid_paths')
    return archive


def _paragraphs(root, namespace: str) -> str:
    paragraphs = []
    for paragraph in root.iter('{' + namespace + '}p'):
        words = []
        # Stop at nested paragraphs (e.g. text boxes) to avoid duplicating text.
        def walk(node):
            if node is not paragraph and node.tag == '{' + namespace + '}p':
                return
            if node.tag == '{' + namespace + '}t':
                words.append(node.text or '')
            elif node.tag == '{' + namespace + '}tab':
                words.append('\t')
            elif node.tag in ('{' + namespace + '}br', '{' + namespace + '}cr'):
                words.append('\n')
            for child in node:
                walk(child)
        walk(paragraph)
        paragraphs.append(''.join(words))
    return '\n'.join(paragraphs)


def _word_content(root) -> str:
    sections = []
    for child in root:
        if child.tag == '{' + W + '}p':
            sections.append(_paragraphs(child, W))
        elif child.tag == '{' + W + '}tbl':
            table = io.StringIO()
            writer = csv.writer(table, delimiter='\t', lineterminator='\n')
            for row in child.findall('{' + W + '}tr'):
                writer.writerow(_word_content(cell) for cell in row.findall('{' + W + '}tc'))
            sections.append('[Table]\n' + table.getvalue())
        else:
            nested = _word_content(child)
            if nested:
                sections.append(nested)
    return '\n'.join(sections)


def _relationships(archive, main: str):
    directory, leaf = posixpath.split(main)
    root = _require_part(_xml(archive.read(posixpath.join(directory, '_rels', leaf + '.rels'))), PACKAGE_R, 'Relationships')
    result = {}
    for row in root:
        if row.tag != '{' + PACKAGE_R + '}Relationship':
            raise ExtractionIssue('office_relationship_invalid')
        identifier, target = row.get('Id'), row.get('Target')
        if not identifier or identifier in result or not target:
            raise ExtractionIssue('office_relationship_invalid')
        if row.get('TargetMode') == 'External':
            result[identifier] = None  # External content is never retrieved.
            continue
        resolved = posixpath.normpath(posixpath.join(directory, target)) if not target.startswith('/') else target.lstrip('/')
        if resolved.startswith('../') or '\\' in resolved or ':' in resolved:
            raise ExtractionIssue('office_relationship_invalid')
        result[identifier] = resolved
    return result


def _office(data: bytes, suffix: str) -> tuple[str, str, dict]:
    with _archive(data) as archive:
        names = set(archive.namelist())
        warnings = ['Only stored text is extracted; images, charts, layout and embedded objects have not been visually reviewed or OCRed.']
        if 'word/document.xml' in names:
            parts = ['word/document.xml'] + sorted(name for name in names if re.fullmatch(r'word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml', name))
            sections = []
            for part in parts:
                leaf = part.split('/')[-1].removesuffix('.xml')
                local = 'hdr' if leaf.startswith('header') else 'ftr' if leaf.startswith('footer') else leaf
                text = _word_content(_require_part(_xml(archive.read(part)), W, local))
                sections.append(text if part == 'word/document.xml' else '[' + part.split('/')[-1] + ']\n' + text)
            return 'docx', '\n\n'.join(sections), {'warnings': warnings}
        if 'ppt/presentation.xml' in names:
            main = 'ppt/presentation.xml'
            relations = _relationships(archive, main)
            root = _require_part(_xml(archive.read(main)), P, 'presentation')
            slides = root.find('{' + P + '}sldIdLst')
            if slides is None:
                raise ExtractionIssue('presentation_order_unavailable')
            sections = []
            for index, slide in enumerate(slides, 1):
                if slide.tag != '{' + P + '}sldId':
                    raise ExtractionIssue('presentation_order_unavailable')
                part = relations.get(slide.get('{' + R + '}id'))
                if not part or not part.startswith('ppt/slides/') or part not in names:
                    raise ExtractionIssue('presentation_order_unavailable')
                sections.append('[Slide ' + str(index) + ']\n' + _paragraphs(_require_part(_xml(archive.read(part)), P, 'sld'), A))
            warnings.append('Slide text follows the saved presentation order; speaker notes and linked external material are not extracted.')
            return 'pptx', '\n\n'.join(sections), {'warnings': warnings, 'slide_count': len(sections)}
        if 'xl/workbook.xml' in names:
            main = 'xl/workbook.xml'
            relations = _relationships(archive, main)
            strings = []
            if 'xl/sharedStrings.xml' in names:
                shared = _require_part(_xml(archive.read('xl/sharedStrings.xml')), S, 'sst')
                strings = [''.join(node.text or '' for node in row.iter('{' + S + '}t')) for row in shared.findall('{' + S + '}si')]
            sheets = _require_part(_xml(archive.read(main)), S, 'workbook').find('{' + S + '}sheets')
            if sheets is None:
                raise ExtractionIssue('workbook_sheets_unavailable')
            sections = []
            for sheet in sheets:
                if sheet.tag != '{' + S + '}sheet':
                    raise ExtractionIssue('workbook_sheets_unavailable')
                part = relations.get(sheet.get('{' + R + '}id'))
                if not part or not part.startswith('xl/worksheets/') or part not in names:
                    raise ExtractionIssue('workbook_sheets_unavailable')
                lines = ['[Sheet ' + str(sheet.get('name', '')) + ']']
                worksheet = _require_part(_xml(archive.read(part)), S, 'worksheet')
                for row in worksheet.iterfind('.//{' + S + '}sheetData/{' + S + '}row'):
                    cells = []
                    for cell in row.findall('{' + S + '}c'):
                        value = cell.find('{' + S + '}v')
                        text = value.text or '' if value is not None else ''
                        inline, formula = cell.find('{' + S + '}is'), cell.find('{' + S + '}f')
                        if cell.get('t') == 's':
                            text = strings[int(text)]
                        elif inline is not None:
                            text = ''.join(node.text or '' for node in inline.iter('{' + S + '}t'))
                        if formula is not None:
                            text = '=' + (formula.text or '') + (' [cached value: ' + text + ']' if text else ' [no cached value]')
                        cells.append(str(cell.get('r', '')) + ': ' + text)
                    lines.append('\t'.join(cells))
                sections.append('\n'.join(lines))
            warnings.append('Cell values and formulas are stored values only; formulas are not executed or recalculated, and date/number formatting is not interpreted.')
            return 'xlsx', '\n\n'.join(sections), {'warnings': warnings, 'sheet_count': len(sections)}
    raise ExtractionIssue('office_package_not_supported')


def _pdf(data: bytes) -> tuple[str, dict]:
    configured = os.environ.get('HARLESS_PDF_TOOLCHAIN_ROOT')
    executable = str(Path(configured) / 'bin' / 'pdftotext') if configured else shutil.which('pdftotext')
    warnings = ['Only the PDF text layer is extracted; images, charts, visual layout and scanned pages have not been OCRed or visually reviewed.']
    if executable and Path(executable).is_file():
        env = {key: value for key, value in os.environ.items() if key in ('PATH', 'LD_LIBRARY_PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP')}
        if configured:
            env['LD_LIBRARY_PATH'] = str(Path(configured) / 'lib' / 'x86_64-linux-gnu')
        try:
            output = subprocess.run([executable, '-enc', 'UTF-8', '-', '-'], input=data,
                                    capture_output=True, timeout=60, check=False, env=env)
            if output.returncode == 0:
                text = output.stdout.decode('utf-8')
                return text, {'extractor': 'poppler', 'warnings': warnings}
            # Git for Windows ships Xpdf's pdftotext, which rejects stdin as
            # a PDF source. Give it a closed, private copy of the same bytes;
            # never reopen the caller's file or weaken the pypdf fallback.
            with tempfile.TemporaryDirectory(prefix='harless-pdf-text-') as temporary:
                source = Path(temporary) / 'attachment.pdf'
                source.write_bytes(data)
                source.chmod(0o600)
                output = subprocess.run([executable, '-enc', 'UTF-8', str(source), '-'],
                                        capture_output=True, timeout=60, check=False, env=env)
            if output.returncode == 0:
                text = output.stdout.decode('utf-8')
                return text, {'extractor': 'pdftotext', 'warnings': warnings}
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ExtractionIssue('pdf_text_extractor_unavailable') from None
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ExtractionIssue('pdf_encrypted')
        text = '\n\f\n'.join(page.extract_text() or '' for page in reader.pages)
        return text, {'extractor': 'pypdf', 'page_count': len(reader.pages), 'warnings': warnings}
    except ExtractionIssue:
        raise
    except Exception:
        raise ExtractionIssue('pdf_text_extraction_failed') from None


def _legacy_word(data: bytes) -> tuple[str, dict]:
    executable = os.environ.get('HARLESS_ANTIWORD_BIN') or shutil.which('antiword')
    if not executable or not Path(executable).is_file():
        raise ExtractionIssue('legacy_word_requires_text_extractor')
    env = {key: value for key, value in os.environ.items() if key in ('PATH', 'LD_LIBRARY_PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP')}
    mappings = os.environ.get('ANTIWORDHOME') or str(Path(executable).resolve().parent.parent / 'share' / 'antiword')
    if Path(mappings).is_dir():
        env['ANTIWORDHOME'] = mappings
    # Antiword is a text reader, not Office automation: macros, field code and
    # external links are never executed. It receives only our private copy.
    try:
        with tempfile.TemporaryDirectory(prefix='harless-word-text-') as temporary:
            source = Path(temporary) / 'attachment.doc'
            source.write_bytes(data)
            source.chmod(0o600)
            output = subprocess.run([executable, '-m', 'UTF-8.txt', str(source)],
                                    capture_output=True, timeout=60, check=False, env=env)
        if output.returncode:
            raise ExtractionIssue('legacy_word_text_extraction_failed')
        return output.stdout.decode('utf-8'), {'extractor': 'antiword', 'warnings': [
            'Only stored legacy Word text is extracted; images, charts, layout and embedded objects have not been OCRed or visually reviewed.']}
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise ExtractionIssue('legacy_word_text_extraction_failed') from None


def extract_attachment(path: Path | str, original_name: str | None = None) -> dict:
    """Return full text or honest metadata; the path is never included in output."""
    path = Path(path)
    name = (original_name or path.name).replace('\\', '/').split('/')[-1]
    suffix = Path(name).suffix.lower()
    data = _read(path)
    result = {'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'format': suffix.lstrip('.') or 'unknown', 'status': 'unsupported', 'text': '',
              'truncated': False, 'coverage': 'metadata_only', 'visual_content_reviewed': False, 'ocr_performed': False}
    try:
        extra = {}
        if suffix in {'.png','.jpg','.jpeg','.webp','.gif'}:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                if image.width > 10000 or image.height > 10000:
                    raise ExtractionIssue('image_dimensions_too_large')
                dimensions = [image.width, image.height]
                image.verify()
            return {**result, 'status':'visual_input','pixels':dimensions,
                    'reason':'native_image_available_to_model','text':'',
                    'warnings':['本文件为原生图片输入，请根据实际图像识别文字与图表；未运行确定性OCR，不能把视觉识别称为独立验证。']}
        if data.lstrip().startswith(b'%PDF-') or suffix == '.pdf':
            result['format'] = 'pdf'
            text, extra = _pdf(data)
            result.update(extra)
            if not text.strip():
                raise ExtractionIssue('pdf_has_no_extractable_text')
        elif data.startswith(b'PK\x03\x04') or suffix in ('.docx', '.pptx', '.xlsx'):
            kind, text, extra = _office(data, suffix)
            result['format'] = kind
        elif suffix == '.doc':
            text, extra = _legacy_word(data)
        elif suffix in TEXT_SUFFIXES or not suffix:
            text, encoding = _text(data)
            extra['encoding'] = encoding
        else:
            # Binary uploads remain attachments. Do not pretend image/archive/
            # executable bytes were understood merely because upload succeeded.
            result['reason'] = 'no_safe_text_extractor_for_format'
            return result
        result.update(status='extracted', text=text, coverage='text_only', **extra)
        if not text.strip():
            result['warnings'] = [*result.get('warnings', []), 'No stored text was found; visual content has not been read.']
    except ExtractionIssue as error:
        status = 'needs_ocr' if str(error) == 'pdf_has_no_extractable_text' else 'unsupported' if str(error) in ('office_package_not_supported', 'legacy_word_requires_text_extractor') else 'unreadable'
        result.update(status=status, reason=str(error))
    except UnicodeError:
        result.update(status='unreadable', reason='text_encoding_not_supported')
    except (ValueError, KeyError, IndexError, OSError, ET.ParseError, zipfile.BadZipFile, RuntimeError):
        result.update(status='unreadable', reason='attachment_text_extraction_failed')
    return result


def main() -> None:
    request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    files = request.get('files')
    if not isinstance(files, list):
        raise ValueError('files_array_required')
    rows = [extract_attachment(row['path'], row.get('name')) for row in files]
    sys.stdout.buffer.write(json.dumps({'files': rows}, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        # No private source path or parser stack is written to the JSON API.
        sys.stdout.buffer.write(json.dumps({'error': str(error) if isinstance(error, ExtractionIssue) else 'invalid_attachment_request'}).encode('utf-8'))
        sys.exit(1)
