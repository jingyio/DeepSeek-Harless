"""真实文件读写回归；只写 .local 中本次创建的测试目录。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.service import ROOT, PPTService
from scenarios.research_ppt.documents import file_hash, parse_document, inspect_pptx


def write_pdf(path: Path, text='Independent replication requires multiple research tasks.'):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612,height=792)
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream = DecodedStreamObject()
    escaped = text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    stream.set_data(f'BT /F1 18 Tf 50 700 Td ({escaped}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as f:
        writer.write(f)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        area = ROOT/'.local/research-ppt/unit-tests'
        area.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.source = Path(self.temp.name)/'input.pdf'
        write_pdf(self.source)
        self.job=prepare([self.source],'验证输入和可编辑产物',2,True,True)
        self.service=PPTService(self.job)
        self.service.rsi=Path(self.temp.name)/'rsi'
        self.service.rsi.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        h=self.service.pin_source('doc_1')['source_id']
        self.service.read_source(h)
        return {'title':'科研流程验证','slides':[
            {'title':'独立任务与证据','bullets':['结构检查用于确认工具协议。'],'sources':[{'source_id':h,'page':1}]},
            {'title':'验证范围','bullets':['科研内容质量需要另外评审。'],'sources':[{'source_id':h,'page':1}],
             'table':[['检查','结果'],['可编辑文字','待生成后检查']]}]}

    def test_editable_pptx_roundtrip_and_source_notes(self):
        out=self.service.render_deck(self.plan())
        self.assertEqual(out['slide_count'],2)
        self.assertTrue(out['each_slide_has_editable_text'])
        self.assertEqual(out['notes_count'],2)
        parsed=parse_document(Path(out['path']))
        self.assertIn('独立任务',parsed['pages'][0]['text'])
        job=prepare([Path(out['path'])],'把已有 PPTX 作为输入',2,True)
        second=PPTService(job)
        pinned=second.pin_source('doc_1')
        self.assertEqual(pinned['format'],'pptx')
        self.assertIn('可编辑文字',second.read_source(pinned['source_id'])['pages'][1]['text'])

    def test_absent_empty_body_is_normalized_without_changing_input_or_evidence(self):
        plan = self.plan()
        plan['slides'][0]['bullets'] = []
        plan['slides'][1]['bullets'] = []
        for slide in plan['slides']:
            del slide['bullets']
        original = copy.deepcopy(plan)
        rendered = self.service.render_deck(plan)
        self.assertEqual(plan, original)
        self.assertEqual(rendered['slide_count'], 2)
        parsed = parse_document(Path(rendered['path']))
        self.assertIn('独立任务', parsed['pages'][0]['text'])
        self.assertIn('可编辑文字', parsed['pages'][1]['text'])
        saved = json.loads((Path(rendered['path']).parent / 'plan.json').read_text(encoding='utf-8'))
        self.assertTrue(all(s['bullets'] == [] for s in saved['slides']))
        self.assertTrue(all(s['sources'] for s in saved['slides']))
        explicit_invalid = copy.deepcopy(plan)
        explicit_invalid['slides'][0]['bullets'] = None
        with self.assertRaises(ValueError):
            self.service.render_deck(explicit_invalid)

    def test_real_preview_changes_block_cached_validation_and_delivery(self):
        source_sha = file_hash(self.source)
        rendered = self.service.render_deck(self.plan())
        deck_id = rendered['deck_id']
        pptx = Path(rendered['path'])
        pptx_sha = file_hash(pptx)
        validated = self.service.validate_deck(deck_id)
        self.assertTrue(validated['passed'], validated['errors'])
        validation_id = validated['validation_id']
        artifacts = validated['artifacts']
        self.assertEqual({row['kind'] for row in artifacts}, {'pdf', 'preview'})
        self.assertIs(self.service.validate_deck(deck_id), validated)
        self.assertEqual(self.service.deliver_deck(validation_id)['file_sha256'], pptx_sha)

        def rejected():
            with self.assertRaisesRegex(ValueError, '核验预览产物已缺失或变化'):
                self.service.validate_deck(deck_id)
            with self.assertRaisesRegex(ValueError, '核验预览产物已缺失或变化'):
                self.service.deliver_deck(validation_id)

        # 一次真实渲染，逐个覆盖 PDF 与全部 PNG 的替换、缺失和原字节恢复。
        for artifact in artifacts:
            path = Path(artifact['path'])
            original = path.read_bytes()
            with self.subTest(kind=artifact['kind'], page=artifact.get('page')):
                try:
                    path.write_bytes(original + b'\nchanged-preview')
                    rejected()
                    path.write_bytes(original)
                    self.assertIs(self.service.validate_deck(deck_id), validated)
                    self.assertEqual(self.service.deliver_deck(validation_id)['validation_id'], validation_id)
                    path.unlink()
                    rejected()
                finally:
                    path.write_bytes(original)

        # 只改变缓存中的路径；不能读取或交付 .local 之外的文件。
        first = artifacts[0]
        original_path = first['path']
        try:
            first['path'] = str(ROOT / 'README.md')
            rejected()
        finally:
            first['path'] = original_path
        self.assertIs(self.service.validate_deck(deck_id), validated)
        self.assertEqual(self.service.deliver_deck(validation_id)['validation_id'], validation_id)
        self.assertEqual(file_hash(self.source), source_sha)
        self.assertEqual(file_hash(pptx), pptx_sha)

    def test_changed_input_blocks_both_read_and_render(self):
        plan=self.plan()
        handle=plan['slides'][0]['sources'][0]['source_id']
        write_pdf(self.source,'Different source version.')
        with self.assertRaisesRegex(ValueError,'版本'):
            self.service.read_source(handle)
        with self.assertRaisesRegex(ValueError,'版本'):
            self.service.render_deck(plan)

    def test_unknown_source_and_preview_cannot_write(self):
        with self.assertRaises(ValueError):
            self.service.pin_source('../../secret')
        plan=self.plan()
        changed=copy.deepcopy(plan)
        changed['slides'][0]['sources'][0]['page']=99
        with self.assertRaises(ValueError):
            self.service.render_deck(changed)
        self.service.job['allow_output']=False
        with self.assertRaisesRegex(ValueError,'预览'):
            self.service.render_deck(plan)

    def test_rejected_rsi_candidate_keeps_active_version(self):
        good={'schema_version':1,'formats':['pdf','pptx'],'min_text_chars':20,'max_pages':100}
        first=self.service.propose_guard(good)
        self.assertTrue(first['accepted'])
        rejected=self.service.propose_guard({**good,'min_text_chars':100})
        self.assertFalse(rejected['accepted'])
        active=json.loads((self.service.rsi/'active-guard.json').read_text())
        self.assertEqual(active['program_digest'],first['program_digest'])
        repair=self.service.propose_guard({**good,'max_pages':150})
        self.assertEqual(repair['previous'],first['program_digest'])

    def test_scanned_pdf_reports_unsupported(self):
        writer=PdfWriter(); writer.add_blank_page(width=600,height=800)
        with self.source.open('wb') as f: writer.write(f)
        self.job=prepare([self.source],'扫描件诊断',2)
        service=PPTService(self.job)
        handle=service.pin_source('doc_1')['source_id']
        with self.assertRaisesRegex(ValueError,'OCR'):
            service.read_source(handle)

    def test_rsi_attempt_limit_persists_and_keeps_active(self):
        good={'schema_version':1,'formats':['pdf','pptx'],'min_text_chars':20,'max_pages':100}
        first=self.service.propose_guard(good)
        for _ in range(2):
            self.service.propose_guard({**good,'min_text_chars':100})
        self.assertEqual(self.service.rsi_status()['attempts_remaining'],0)
        active=(self.service.rsi/'active-guard.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'3 次上限'):
            self.service.propose_guard(good)
        self.assertEqual((self.service.rsi/'active-guard.json').read_bytes(),active)
        restarted=PPTService(self.job)
        restarted.rsi=self.service.rsi
        self.assertEqual(restarted.rsi_status()['guard_attempts_used'],3)
        with self.assertRaisesRegex(ValueError,'3 次上限'):
            restarted.propose_guard(good)
        self.assertEqual(json.loads(active)['program_digest'],first['program_digest'])

    def test_invalid_guard_schema_also_spends_an_attempt(self):
        result=self.service.propose_guard({'arbitrary_code':'not-supported'})
        self.assertFalse(result['accepted'])
        self.assertEqual(self.service.rsi_status()['attempts_remaining'],2)


if __name__=='__main__':
    unittest.main()
