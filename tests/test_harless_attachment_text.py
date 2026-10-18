"""No-model extraction diagnostics, including real minimal PDF and OOXML files."""
import codecs
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from src.adapters import harless_attachment_text as attachment


def put(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
    return path


def package(tmp_path, name, members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for part, text in members.items():
            archive.writestr(part, text)
    return put(tmp_path, name, stream.getvalue())


def pdf_bytes(text='Real uploaded PDF text'):
    stream = b'BT /F1 12 Tf 72 720 Td (' + text.encode('ascii') + b') Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    data, offsets = b'%PDF-1.4\n', []
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode() + b' 0 obj\n' + body + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
    return data + b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'


@pytest.mark.parametrize('suffix', ['txt', 'md', 'json', 'csv', 'tsv', 'py'])
def test_full_text_and_exact_source_hash_no_execution(tmp_path, suffix):
    text = '中文内容\n' + 'x' * 70000 + '\n__import__("os").system("not-executed")'
    path = put(tmp_path, 'source.' + suffix, text)
    result = attachment.extract_attachment(path, 'uploaded.' + suffix)
    assert result['status'] == 'extracted'
    assert result['text'] == text
    assert result['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['bytes'] == len(path.read_bytes())
    assert result['name'] == 'uploaded.' + suffix and result['truncated'] is False
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'utf-32'])
def test_bom_text_encodings_are_decoded_without_replacement(tmp_path, encoding):
    text = '完整说明：αβγ\n第二行'
    result = attachment.extract_attachment(put(tmp_path, 'request.txt', text.encode(encoding)))
    assert result['text'] == text and result['status'] == 'extracted'


@pytest.mark.parametrize('namespace', [attachment.W, 'http://purl.oclc.org/ooxml/wordprocessingml/main'])
def test_docx_paragraph_table_header_and_long_text_are_read_without_macro_execution(tmp_path, namespace):
    words = '完整正文' * 10000
    path = package(tmp_path, 'paper.docx', {
        'word/document.xml': f'<w:document xmlns:w="{namespace}"><w:body><w:p><w:r><w:t>{words}</w:t></w:r></w:p>'
                             '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>组别</w:t></w:r></w:p></w:tc>'
                             '<w:tc><w:p><w:r><w:t>数值</w:t></w:r></w:p></w:tc></w:tr>'
                             '<w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>'
                             '<w:tc><w:p><w:r><w:t>12.5</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
        'word/header1.xml': f'<w:hdr xmlns:w="{namespace}"><w:p><w:r><w:t>页眉</w:t></w:r></w:p></w:hdr>',
        'word/footer1.xml': f'<w:ftr xmlns:w="{namespace}"><w:p><w:r><w:t>页脚</w:t></w:r></w:p></w:ftr>',
        'word/footnotes.xml': f'<w:footnotes xmlns:w="{namespace}"><w:footnote w:id="1"><w:p><w:r><w:t>脚注</w:t></w:r></w:p></w:footnote></w:footnotes>',
        'word/endnotes.xml': f'<w:endnotes xmlns:w="{namespace}"><w:endnote w:id="1"><w:p><w:r><w:t>尾注</w:t></w:r></w:p></w:endnote></w:endnotes>',
        'word/comments.xml': f'<w:comments xmlns:w="{namespace}"><w:comment w:id="0"><w:p><w:r><w:t>批注</w:t></w:r></w:p></w:comment></w:comments>',
        'word/vbaProject.bin': b'not executable content',
        'word/media/image.png': b'not parsed as text',
    })
    result = attachment.extract_attachment(path)
    assert result['status'] == 'extracted' and words in result['text']
    assert '组别\t数值\nA\t12.5' in result['text'] and '页眉' in result['text']
    assert all(text in result['text'] for text in ('页脚', '脚注', '尾注', '批注'))
    assert 'not executable' not in result['text'] and result['visual_content_reviewed'] is False
    assert result['ocr_performed'] is False and result['warnings']


def test_docx_entities_are_not_expanded_or_read_from_the_host(tmp_path):
    xml = f'<!DOCTYPE document [<!ENTITY secret SYSTEM "file:///private/secret">]><w:document xmlns:w="{attachment.W}"><w:body><w:p><w:r><w:t>&secret;</w:t></w:r></w:p></w:body></w:document>'
    for index, data in enumerate([xml.encode('utf-8'), xml.encode('utf-16')]):
        result = attachment.extract_attachment(package(tmp_path, f'unsafe{index}.docx', {'word/document.xml': data}))
        assert result['status'] == 'unreadable'
        assert result['reason'] == 'office_xml_doctype_disallowed'
        assert result['text'] == '' and '/private/' not in json.dumps(result)


def test_archive_bombs_and_unsafe_member_paths_are_explicit_not_truncated(tmp_path, monkeypatch):
    path = package(tmp_path, 'large.docx', {'word/document.xml': 'x' * 3000})
    monkeypatch.setattr(attachment, 'MAX_ARCHIVE_BYTES', 1000)
    result = attachment.extract_attachment(path)
    assert result['reason'] == 'office_archive_resource_limit' and result['truncated'] is False
    monkeypatch.setattr(attachment, 'MAX_ARCHIVE_BYTES', 150 * 1024 * 1024)
    unsafe = package(tmp_path, 'unsafe.docx', {'../escape.xml': 'x', 'word/document.xml': '<root/>'})
    assert attachment.extract_attachment(unsafe)['reason'] == 'office_archive_invalid_paths'
    assert not (tmp_path.parent / 'escape.xml').exists()


@pytest.mark.parametrize('strict', [False, True])
def test_pptx_text_follows_presentation_order_not_part_number(tmp_path, strict):
    p, a, r = (('http://purl.oclc.org/ooxml/presentationml/main', 'http://purl.oclc.org/ooxml/drawingml/main',
                'http://purl.oclc.org/ooxml/officeDocument/relationships') if strict else (attachment.P, attachment.A, attachment.R))
    path = package(tmp_path, 'deck.pptx', {
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{p}" xmlns:r="{r}"><p:sldIdLst><p:sldId r:id="second"/><p:sldId r:id="first"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{attachment.PACKAGE_R}"><Relationship Id="first" Target="slides/slide1.xml"/><Relationship Id="second" Target="slides/slide2.xml"/></Relationships>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><a:p><a:r><a:t>Second visible slide</a:t></a:r></a:p></p:sld>',
        'ppt/slides/slide2.xml': f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><a:p><a:r><a:t>First visible slide</a:t></a:r></a:p></p:sld>',
    })
    result = attachment.extract_attachment(path)
    assert result['status'] == 'extracted' and result['slide_count'] == 2
    assert result['text'].index('First visible') < result['text'].index('Second visible')


@pytest.mark.parametrize('strict', [False, True])
def test_xlsx_cells_preserve_addresses_and_do_not_recalculate_or_fetch_external_data(tmp_path, strict):
    s, r = (('http://purl.oclc.org/ooxml/spreadsheetml/main', 'http://purl.oclc.org/ooxml/officeDocument/relationships')
            if strict else (attachment.S, attachment.R))
    path = package(tmp_path, 'data.xlsx', {
        'xl/workbook.xml': f'<workbook xmlns="{s}" xmlns:r="{r}"><sheets><sheet name="研究数据" r:id="one"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="{attachment.PACKAGE_R}"><Relationship Id="one" Target="worksheets/sheet1.xml"/><Relationship Id="external" TargetMode="External" Target="https://private.invalid"/></Relationships>',
        'xl/sharedStrings.xml': f'<sst xmlns="{s}" xmlns:fake="urn:unknown"><si><t>组别</t><fake:t>fake text</fake:t></si></sst>',
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{s}" xmlns:fake="urn:unknown"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1"><v>10</v></c><c r="D1"><f>C1*2</f><v>20</v></c><c r="E1" t="inlineStr"><is><t>完整说明</t><fake:t>fake text</fake:t></is></c></row></sheetData></worksheet>',
    })
    result = attachment.extract_attachment(path)
    assert result['status'] == 'extracted'
    assert 'A1: 组别\tC1: 10\tD1: =C1*2 [cached value: 20]' in result['text']
    assert 'E1: 完整说明' in result['text']
    assert 'private.invalid' not in json.dumps(result) and 'fake text' not in result['text']


@pytest.mark.parametrize('kind, main, local', [('docx', 'word/document.xml', 'document'),
                                               ('pptx', 'ppt/presentation.xml', 'presentation'),
                                               ('xlsx', 'xl/workbook.xml', 'workbook')])
def test_unknown_office_namespaces_are_not_claimed_as_extracted_text(tmp_path, kind, main, local):
    directory, leaf = main.rsplit('/', 1)
    members = {main: f'<{local} xmlns="urn:unknown"><p><t>not recognized document content</t></p></{local}>',
               f'{directory}/_rels/{leaf}.rels': f'<Relationships xmlns="{attachment.PACKAGE_R}"/>'}
    result = attachment.extract_attachment(package(tmp_path, 'invalid.' + kind, members))
    assert result['status'] == 'unreadable' and result['reason'] == 'office_xml_namespace_unsupported'
    assert result['text'] == ''


def test_known_document_namespace_does_not_make_unknown_header_namespace_valid(tmp_path):
    path = package(tmp_path, 'header.docx', {
        'word/document.xml': f'<w:document xmlns:w="{attachment.W}"><w:body/></w:document>',
        'word/header1.xml': '<hdr xmlns="urn:unknown"><p><t>unrecognized header</t></p></hdr>',
    })
    result = attachment.extract_attachment(path)
    assert result['status'] == 'unreadable' and result['text'] == ''


def test_relationship_namespaces_are_validated_before_resolving_parts(tmp_path):
    path = package(tmp_path, 'relationships.pptx', {
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{attachment.P}"/>',
        'ppt/_rels/presentation.xml.rels': '<Relationships xmlns="urn:unknown"><Relationship Id="one" Target="slides/slide1.xml"/></Relationships>',
    })
    result = attachment.extract_attachment(path)
    assert result['status'] == 'unreadable' and result['reason'] == 'office_xml_namespace_unsupported'


@pytest.mark.skipif(not shutil.which('pdftotext') and importlib.util.find_spec('pypdf') is None, reason='PDF text parser not installed')
def test_real_pdf_text_and_scan_only_state(tmp_path):
    result = attachment.extract_attachment(put(tmp_path, 'source.pdf', pdf_bytes()))
    assert result['status'] == 'extracted' and 'Real uploaded PDF text' in result['text'], result.get('reason')
    assert result['ocr_performed'] is False and result['coverage'] in ('text_only','page_text_and_ocr')
    blank = attachment.extract_attachment(put(tmp_path, 'scan.pdf', pdf_bytes('')))
    assert blank['status'] == 'needs_ocr' and blank['text'] == ''
    assert blank['reason'] == 'pdf_has_no_extractable_text' and blank['warnings']


def test_pdf_file_only_reader_uses_private_exact_bytes_without_pypdf(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'fitz', None)  # Exercise the legacy fallback explicitly.
    executable = put(tmp_path, 'pdftotext.exe', b'test executable placeholder')
    monkeypatch.delenv('HARLESS_PDF_TOOLCHAIN_ROOT', raising=False)
    monkeypatch.setattr(attachment.shutil, 'which', lambda name: str(executable))
    monkeypatch.setitem(sys.modules, 'pypdf', None)
    monkeypatch.setenv('SECRET_PDF_TEST_KEY', 'must-not-be-inherited')
    source = put(tmp_path, 'source.pdf', pdf_bytes())
    data, text, copies, calls = source.read_bytes(), '完整PDF文本\n' * 12000, [], []
    def run(command, **options):
        calls.append(command)
        assert command[:3] == [str(executable), '-enc', 'UTF-8']
        assert 'SECRET_PDF_TEST_KEY' not in options['env']
        if command[3] == '-':
            assert options['input'] == data
            return subprocess.CompletedProcess(command, 99, b'', b'Xpdf requires a file name')
        copy = Path(command[3]); copies.append(copy)
        assert copy != source and copy.read_bytes() == data and 'input' not in options
        return subprocess.CompletedProcess(command, 0, text.encode('utf-8'), b'')
    monkeypatch.setattr(attachment.subprocess, 'run', run)
    result = attachment.extract_attachment(source)
    assert len(calls) == 2 and result['status'] == 'extracted' and result['text'] == text
    assert result['extractor'] == 'pdftotext' and result['truncated'] is False
    assert result['sha256'] == hashlib.sha256(data).hexdigest() and source.read_bytes() == data
    assert len(copies) == 1 and not copies[0].exists()


def test_pdf_failed_file_retry_cleans_private_copy_without_fabricating_text(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'fitz', None)
    executable = put(tmp_path, 'pdftotext.exe', b'test executable placeholder')
    monkeypatch.delenv('HARLESS_PDF_TOOLCHAIN_ROOT', raising=False)
    monkeypatch.setattr(attachment.shutil, 'which', lambda name: str(executable))
    monkeypatch.setitem(sys.modules, 'pypdf', None)
    copies = []
    def run(command, **options):
        if command[3] != '-':
            copies.append(Path(command[3]))
            assert copies[-1].exists()
        return subprocess.CompletedProcess(command, 1, b'partial invalid output', b'/private/source.pdf parser failed')
    monkeypatch.setattr(attachment.subprocess, 'run', run)
    result = attachment.extract_attachment(put(tmp_path, 'broken.pdf', b'not a PDF'))
    assert result['status'] == 'unreadable' and result['text'] == ''
    assert len(copies) == 1 and not copies[0].exists()
    assert '/private/' not in json.dumps(result)


def test_real_pypdf_strict_fallback_reads_the_valid_fixture(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'fitz', None)
    pytest.importorskip('pypdf')
    monkeypatch.delenv('HARLESS_PDF_TOOLCHAIN_ROOT', raising=False)
    monkeypatch.setattr(attachment.shutil, 'which', lambda name: None)
    source = attachment.extract_attachment(put(tmp_path, 'source.pdf', pdf_bytes()))
    assert source['status'] == 'extracted' and source['extractor'] == 'pypdf'
    assert 'Real uploaded PDF text' in source['text']
    blank = attachment.extract_attachment(put(tmp_path, 'blank.pdf', pdf_bytes('')))
    assert blank['status'] == 'needs_ocr'
    malformed = attachment.extract_attachment(put(tmp_path, 'broken.pdf', b'%PDF-1.4\nbroken'))
    assert malformed['status'] == 'unreadable' and malformed['text'] == ''


def test_unknown_binary_and_legacy_doc_are_accepted_as_honest_metadata(tmp_path, monkeypatch):
    monkeypatch.delenv('HARLESS_ANTIWORD_BIN', raising=False)
    monkeypatch.setattr(attachment.shutil, 'which', lambda name: None)
    for name, reason in [('opaque.bin', 'no_safe_text_extractor_for_format'), ('old.doc', 'legacy_word_requires_text_extractor')]:
        path = put(tmp_path, name, b'\x00\x01\xffunknown binary')
        result = attachment.extract_attachment(path)
        assert result['status'] == 'unsupported' and result['reason'] == reason and result['text'] == ''
        assert result['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    result = attachment.extract_attachment(put(tmp_path, 'binary.txt', b'\x00\x01'))
    assert result['status'] == 'unreadable' and result['text'] == ''


def test_legacy_word_reader_uses_a_private_copy_utf8_mapping_and_preserves_full_text(tmp_path, monkeypatch):
    executable = tmp_path / 'usr/bin/antiword'
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'test tool placeholder')
    mappings = tmp_path / 'usr/share/antiword'
    mappings.mkdir(parents=True)
    monkeypatch.setenv('HARLESS_ANTIWORD_BIN', str(executable))
    monkeypatch.setenv('SECRET_TEST_KEY', 'must-not-be-inherited')
    monkeypatch.delenv('ANTIWORDHOME', raising=False)
    document = put(tmp_path, 'legacy.doc', b'\xd0\xcf\x11\xe0exact binary source')
    text = '全部Word内容' * 12000
    copies = []
    def run(command, **options):
        assert command[:3] == [str(executable), '-m', 'UTF-8.txt']
        copy = Path(command[3]); copies.append(copy)
        assert copy != document and copy.read_bytes() == document.read_bytes()
        assert options['env']['ANTIWORDHOME'] == str(mappings)
        assert 'SECRET_TEST_KEY' not in options['env']
        return subprocess.CompletedProcess(command, 0, text.encode('utf-8'), b'')
    monkeypatch.setattr(attachment.subprocess, 'run', run)
    result = attachment.extract_attachment(document)
    assert result['status'] == 'extracted' and result['text'] == text and result['extractor'] == 'antiword'
    assert not copies[0].exists() and document.exists()
    assert result['sha256'] == hashlib.sha256(document.read_bytes()).hexdigest()


def test_legacy_word_parser_failure_is_explicit_and_does_not_leak_private_stderr(tmp_path, monkeypatch):
    executable = put(tmp_path, 'antiword', b'test tool placeholder')
    monkeypatch.setenv('HARLESS_ANTIWORD_BIN', str(executable))
    monkeypatch.setattr(attachment.subprocess, 'run', lambda command, **options:
                        subprocess.CompletedProcess(command, 1, b'', b'/home/private/host.doc failed'))
    result = attachment.extract_attachment(put(tmp_path, 'broken.doc', b'bad'))
    assert result['status'] == 'unreadable' and result['reason'] == 'legacy_word_text_extraction_failed'
    assert result['text'] == '' and 'private' not in json.dumps(result)


def test_cli_accepts_mixed_types_and_never_returns_source_paths(tmp_path):
    text, binary = put(tmp_path, 'hello.txt', '你好'), put(tmp_path, 'opaque.bin', b'\xff')
    payload = {'files': [{'path': str(text), 'name': '用户说明.txt'}, {'path': str(binary), 'name': '数据.bin'}]}
    result = subprocess.run([sys.executable, str(Path(attachment.__file__))], input=json.dumps(payload).encode('utf-8'), capture_output=True, check=True,
                            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
    rows = json.loads(result.stdout)['files']
    assert rows[0]['text'] == '你好' and rows[1]['status'] == 'unsupported'
    assert all(row['sha256'] and row['name'] for row in rows)
    assert str(tmp_path) not in result.stdout.decode('utf-8') and not result.stderr


def test_file_identity_and_existing_upload_limit_fail_closed(tmp_path, monkeypatch):
    path = put(tmp_path, 'source.txt', 'source')
    monkeypatch.setattr(attachment, 'MAX_FILE_BYTES', 3)
    with pytest.raises(attachment.ExtractionIssue, match='attachment_upload_limit'):
        attachment.extract_attachment(path)
    monkeypatch.setattr(attachment, 'MAX_FILE_BYTES', 20 * 1024 * 1024)
    try:
        linked = tmp_path / 'linked.txt'
        os.link(path, linked)
    except OSError:
        pytest.skip('hard links unavailable')
    with pytest.raises(attachment.ExtractionIssue, match='attachment_not_regular'):
        attachment.extract_attachment(linked)
