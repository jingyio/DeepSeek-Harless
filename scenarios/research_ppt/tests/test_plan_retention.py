"""完整计划到真实 PPTX 的独立内容验收；渲染缺依赖必须明确失败。"""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from scenarios.research_ppt.validation import (
    ROOT, _check_chart_plan, _read_package, plan_expectations, validate_delivery,
)


class PlanRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = ROOT / '.local/research-ppt/plan-retention-tests'
        area.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=area)
        cls.directory = Path(cls.temp.name)
        source = ['Public synthetic source page 1; fixture-only SHA']
        cls.plan = {'title': 'Independent planned-content checks', 'slides': [
            {'title': 'Content slide', 'bullets': ['Evidence stays unchanged.'],
             'takeaway': 'The submitted claim must remain.', 'sources': source, 'notes': 'Private speaker note.'},
            {'title': 'Table slide', 'bullets': [], 'table': [['Metric', 'Value'], ['Accuracy', '87.5']], 'sources': source},
            {'title': 'Comparison slide', 'bullets': [], 'comparison': {
                'left': {'title': 'Method left', 'bullets': ['Left condition']},
                'right': {'title': 'Method right', 'bullets': ['Right condition']}}, 'sources': source},
            {'title': 'Process slide', 'bullets': [], 'layout': 'process', 'process': {'steps': [
                {'label': 'Read', 'detail': 'Keep original evidence'},
                {'label': 'Check', 'detail': 'Verify the retained content'}]}, 'sources': source},
            {'title': 'Bar data', 'bullets': [], 'chart': {'type': 'bar', 'categories': ['xformers', 'Triton'],
                'series': [{'name': 'Measured', 'values': [122, 155]}],
                'x_label': 'Method', 'y_label': 'Latency', 'unit': 'ms'}, 'sources': source},
            {'title': 'Line data', 'bullets': [], 'chart': {'type': 'line', 'categories': ['Length one', 'Length two'],
                'series': [{'name': 'Series one', 'values': [-1.25, 3.75]}, {'name': 'Series two', 'values': [2, 4]}],
                'x_label': 'Input length', 'y_label': 'Throughput', 'unit': 'TFLOP/s'}, 'sources': source},
        ]}
        path = cls.directory / 'plan.json'
        path.write_text(json.dumps(cls.plan), encoding='utf-8')
        cls.pptx = cls.directory / 'original.pptx'
        subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'), str(path), str(cls.pptx)],
            check=True, capture_output=True, timeout=90)
        cls.expected = plan_expectations(cls.plan)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def altered(self, name, change):
        target = self.directory / name
        changed_count = 0
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(target, 'w') as result:
            for item in original.infolist():
                content = original.read(item.filename)
                modified = change(item.filename, content)
                changed_count += modified != content
                result.writestr(item, modified)
        self.assertGreater(changed_count, 0, '反例必须确实改变真实产物')
        return target

    def checked(self, path):
        return validate_delivery(path, 6, expected_texts=self.expected['texts'], expected_charts=self.expected['charts'],
            expected_sources=[slide['sources'] for slide in self.plan['slides']])

    def test_plan_extracts_all_visible_structures_without_notes_or_fake_point_labels(self):
        expected = plan_expectations(self.plan)
        self.assertEqual(expected['texts'][0], ['Content slide', 'Evidence stays unchanged.', 'The submitted claim must remain.'])
        self.assertEqual(expected['texts'][1], ['Table slide', 'Metric', 'Value', 'Accuracy', '87.5'])
        self.assertEqual(expected['texts'][2], ['Comparison slide', 'Method left', 'Left condition', 'Method right', 'Right condition'])
        self.assertEqual(expected['texts'][3], ['Process slide', 'Read', 'Keep original evidence', 'Check', 'Verify the retained content'])
        self.assertEqual(expected['texts'][4], ['Bar data'], '数值点和图例不伪装为slide文字')
        self.assertEqual(expected['charts'][4], self.plan['slides'][4]['chart'])
        expected['charts'][4]['series'][0]['values'][0] = 999
        self.assertEqual(self.plan['slides'][4]['chart']['series'][0]['values'][0], 122, '期望应是独立副本')
        invalid = copy.deepcopy(self.plan)
        invalid['slides'][4]['chart']['series'][0]['values'][0] = float('nan')
        with self.assertRaises(ValueError):
            plan_expectations(invalid)

    def test_actual_native_package_preserves_plan_and_chart_values(self):
        report = {'errors': [], 'warnings': []}
        texts, _ = _read_package(self.pptx, report, include_chart_data=True)
        for page, expected in enumerate(self.expected['texts']):
            self.assertTrue(all(text in ''.join(texts[page]) for text in expected))
            _check_chart_plan(report['native_chart_data'][page], self.expected['charts'][page], report, page + 1)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['native_chart_data'][4][0]['y_title'], 'Latency / ms')
        self.assertEqual(report['native_chart_data'][5][0]['series'][0]['values'], ['-1.25', '3.75'])

    def test_removed_body_is_detected_against_original_plan(self):
        needle = b'<a:t>The submitted claim must remain.</a:t>'
        target = self.altered('missing-body.pptx', lambda name, raw:
            raw.replace(needle, b'<a:t></a:t>') if name == 'ppt/slides/slide1.xml' else raw)
        report = self.checked(target)
        self.assertFalse(report['passed'])
        self.assertIn('submitted_text_missing_in_pptx', {row['code'] for row in report['errors']})
        self.assertEqual(report['text_retention']['mode'], 'submitted_plan')

    def test_missing_axis_unit_and_changed_method_value_are_independently_detected(self):
        def drop_title(name, raw):
            if name.startswith('ppt/charts/') and name.endswith('.xml') and b'Latency / ms' in raw:
                return re.sub(rb'(<c:valAx>[\s\S]*?)<c:title>[\s\S]*?</c:title>', rb'\1', raw, count=1)
            return raw
        axis_report = self.checked(self.altered('missing-axis.pptx', drop_title))
        self.assertIn('chart_axis_title_missing_or_changed', {row['code'] for row in axis_report['errors']})
        def change_data(name, raw):
            if name.startswith('ppt/charts/') and name.endswith('.xml') and b'xformers' in raw:
                return raw.replace(b'<c:v>122</c:v>', b'<c:v>155</c:v>')
            return raw
        value_report = self.checked(self.altered('wrong-value.pptx', change_data))
        self.assertIn('chart_data_missing_or_changed', {row['code'] for row in value_report['errors']})
        self.assertNotIn('submitted_text_missing_in_pptx', {row['code'] for row in value_report['errors']},
            '隐藏的数据点不能被误报为slide文字丢失')

    def test_real_render_checks_labels_without_requiring_hidden_point_values(self):
        # 不模拟缺失的转换器；无依赖也要保存明确failed报告，不能冒称渲染通过。
        report = self.checked(self.pptx)
        self.assertEqual(report['scientific_quality'], 'not_reviewed')
        if not (shutil.which('libreoffice') or shutil.which('soffice')):
            self.assertFalse(report['passed'])
            self.assertEqual([row['code'] for row in report['errors']], ['libreoffice_missing'])
        else:
            self.assertTrue(report['passed'], report['errors'])
            self.assertEqual(report['pdf_page_count'], 6)
            self.assertEqual(report['chart_retention']['scope'], 'native_cached_data_and_rendered_labels_not_scientific_truth')
            self.assertEqual(len(report['artifacts']), 7)


if __name__ == '__main__':
    unittest.main()
