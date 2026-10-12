"""实际 PPTX 位置化数值保留反例；无模型调用，失败产物留在 .local。"""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from uuid import uuid4
import zipfile

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.service import PPTService
from scenarios.research_ppt.tests.test_service import write_pdf
from scenarios.research_ppt.validation import (
    ROOT, _check_table_plan, _missing_texts, _read_package, plan_expectations, validate_delivery,
)


class PositionalRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = ROOT / '.local/research-ppt/positional-retention-tests' / uuid4().hex
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.plan = {'title': 'Independent table evidence', 'slides': [
            {'title': 'Direct results', 'bullets': [],
             'table': [['Method', 'Accuracy'], ['Method A', '87.5'], ['Method B', '92.2']],
             'sources': ['Public synthetic source page 1; fixture-only SHA']},
        ]}
        cls.expected = plan_expectations(cls.plan)
        plan_path = cls.area / 'plan.json'
        plan_path.write_text(json.dumps(cls.plan), encoding='utf-8')
        cls.pptx = cls.area / 'original.pptx'
        subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'), str(plan_path), str(cls.pptx)],
                       check=True, capture_output=True, timeout=90)

    def changed(self, name, replacement):
        target = self.area / name
        modified = False
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(target, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                if item.filename == 'ppt/slides/slide1.xml':
                    revised = replacement(raw)
                    modified = raw != revised
                    raw = revised
                result.writestr(item, raw)
        self.assertTrue(modified, '反例必须修改真实 PPTX')
        return target

    def checked(self, target):
        return validate_delivery(target, 1, expected_texts=self.expected['texts'],
                                 expected_charts=self.expected['charts'],
                                 expected_tables=self.expected['tables'],
                                 expected_sources=[self.plan['slides'][0]['sources']])

    def test_numeric_boundary_and_multiplicity_reject_longer_or_fewer_values(self):
        for actual in ('187.5', '-87.5', '87.50', '87.5e2', '87.5.0'):
            with self.subTest(actual=actual):
                self.assertEqual(_missing_texts(['87.5'], actual), ['87.5'])
        self.assertEqual(_missing_texts(['87.5', '87.5'], '87.5'), ['87.5'])
        self.assertEqual(_missing_texts(['Measured 87.5', 'Measured 87.5'], 'Measured 87.5'), ['Measured 87.5'])
        self.assertEqual(_missing_texts(['87.5', '87.5'], '87.5% and 87.5%'), [])
        self.assertEqual(_missing_texts(['-0.5', '87.5'], '-0.5 and 87.5'), [])
        self.assertEqual(_missing_texts(['87.5', '92.2'], '87.5\n92.2'), [])
        self.assertEqual(_missing_texts(['Measured 87.5'], 'Measured\n87.5'), [])

    def test_actual_table_cells_match_plan_by_row_and_column(self):
        report = {'errors': [], 'warnings': []}
        _read_package(self.pptx, report, include_table_data=True)
        self.assertEqual(report['native_table_data'][0], [self.plan['slides'][0]['table']])
        _check_table_plan(report['native_table_data'][0], self.expected['tables'][0], report, 1)
        self.assertEqual(report['errors'], [])
        expected = plan_expectations(self.plan)
        expected['tables'][0][1][1] = 'changed'
        self.assertEqual(self.plan['slides'][0]['table'][1][1], '87.5')

    def test_actual_longer_number_is_rejected_in_same_cell(self):
        target = self.changed('wrong-prefix-number.pptx', lambda raw:
                              raw.replace(b'<a:t>87.5</a:t>', b'<a:t>187.5</a:t>', 1))
        report = self.checked(target)
        self.assertFalse(report['passed'])
        codes = {row['code'] for row in report['errors']}
        self.assertIn('table_cell_missing_or_changed', codes)
        self.assertIn('submitted_text_missing_in_pptx', codes)
        error = next(row for row in report['errors'] if row['code'] == 'table_cell_missing_or_changed')
        self.assertEqual(error['cells'], [{'row': 2, 'column': 2}])

    def test_swapped_method_values_fail_despite_unchanged_global_text(self):
        target = self.changed('swapped-values.pptx', lambda raw:
                              raw.replace(b'<a:t>87.5</a:t>', b'<a:t>TEMP</a:t>', 1)
                                 .replace(b'<a:t>92.2</a:t>', b'<a:t>87.5</a:t>', 1)
                                 .replace(b'<a:t>TEMP</a:t>', b'<a:t>92.2</a:t>', 1))
        report = self.checked(target)
        self.assertFalse(report['passed'])
        codes = {row['code'] for row in report['errors']}
        self.assertIn('table_cell_missing_or_changed', codes)
        self.assertNotIn('submitted_text_missing_in_pptx', codes)

    def test_service_uses_original_table_plan_to_reject_renderer_wrong_value(self):
        source = self.area / 'synthetic-paper.pdf'
        write_pdf(source, 'Method A accuracy 87.5; Method B accuracy 92.2.')
        service = PPTService(prepare([source], '保留指定方法和数值', 1, True))
        handle = service.pin_source('doc_1')['source_id']
        service.read_source(handle)
        plan = copy.deepcopy(self.plan)
        plan['slides'][0]['sources'] = [{'source_id': handle, 'page': 1}]
        rendered = service.render_deck(plan)
        target = Path(rendered['path'])
        candidate = target.with_suffix('.wrong.pptx')
        modified = False
        with zipfile.ZipFile(target) as original, zipfile.ZipFile(candidate, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                if item.filename == 'ppt/slides/slide1.xml':
                    revised = raw.replace(b'<a:t>87.5</a:t>', b'<a:t>187.5</a:t>', 1)
                    modified = raw != revised
                    raw = revised
                result.writestr(item, raw)
        self.assertTrue(modified)
        candidate.replace(target)
        # 模拟渲染器已登记错误产物，后验收须独立核计划，而非只检查产物哈希。
        service.deck_records[rendered['deck_id']]['sha256'] = file_hash(target)
        report = service.validate_deck(rendered['deck_id'])
        self.assertFalse(report['passed'])
        self.assertIn('table_cell_missing_or_changed', {row['code'] for row in report['errors']})
        with self.assertRaisesRegex(ValueError, '未通过真实渲染'):
            service.deliver_deck(report['validation_id'])


if __name__ == '__main__':
    unittest.main()
