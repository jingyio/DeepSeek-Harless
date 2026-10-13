"""生成工具宿主的真实 Node/TypeScript 工程回归。

这里的手写小函数、JSON 与声明均为诊断夹具，不是模型生成工具、真实论文
任务、RSI 学习或成本效果证据。没有模拟 subprocess、编译器或工具返回。
所有运行产物保留在 .local，由服务器入口保留测试日志。
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from scenarios.research_ppt import generated_tools as host


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['source_id', 'rows'],
          'properties': {'source_id': {'type': 'string'}, 'rows': {'type': 'array', 'maxItems': 50,
          'items': {'type': 'object', 'additionalProperties': False, 'required': ['id', 'page'],
                    'properties': {'id': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}}}}}}

# 仅验证宿主是否调用了真实模块，不承担最终目录算法或科研效果。
CODE = '''export function run(input: any): object {
  const rows = input.rows.filter((row: any) => row.page > 0);
  return {source_id: input.source_id, ids: rows.map((row: any) => row.id)};
}'''


class GeneratedToolHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = host.ROOT / '.local/research-ppt/generated-tool-tests' / uuid4().hex
        cls.area.mkdir(parents=True)
        print('生成工具真实工程诊断目录：' + str(cls.area), flush=True)

    def job(self, **updates) -> Path:
        directory = self.area / uuid4().hex
        path = write_json(directory / 'job.json', {'job_id': uuid4().hex, 'allow_rsi': True,
                                                  'allow_output': True, **updates})
        return path

    def provenance(self, job: Path, *, provider='engineering-diagnostic') -> dict:
        response = write_json(job.parent / ('response-' + uuid4().hex + '.json'),
                              {'diagnostic_fixture': True, 'candidate_is_handwritten': True})
        trajectory = write_json(job.parent / ('trace-' + uuid4().hex + '.json'),
                                {'diagnostic_fixture': True, 'no_model_call': True})
        return {'provider': provider, 'model': 'handwritten-engineering-fixture',
                'run_id': 'diagnostic-proposal-' + uuid4().hex, 'reasoning_effort': 'off',
                'response_path': str(response), 'response_sha256': digest(response),
                'trajectory_path': str(trajectory), 'trajectory_sha256': digest(trajectory),
                'training_run_ids': ['diagnostic-training-a', 'diagnostic-training-b']}

    def propose(self, job: Path, *, code=CODE, schema=None):
        return host.propose_candidate(job, {'name': 'read_pinned_diagnostic',
            'description': 'Handwritten host diagnostic; not a learned or model-generated tool.',
            'input_schema': copy.deepcopy(schema or SCHEMA), 'code': code}, self.provenance(job))

    def valid(self, job=None):
        job = job or self.job()
        result = self.propose(job)
        self.assertTrue(result['compile_passed'], result['diagnostics'])
        self.assertFalse(result['certified'])
        return Path(result['candidate_path'])

    def case(self, directory: Path, identity: str, *, expected=None, source=None):
        directory = directory / identity
        value = {'source_id': identity, 'rows': [{'id': 'figure-' + identity, 'page': 1}]}
        inp = write_json(directory / 'input.json', value)
        exp = write_json(directory / 'expected.json', expected or
                         {'source_id': identity, 'ids': ['figure-' + identity]})
        src = write_json(directory / 'source.json', {'diagnostic_source': source or identity})
        return {'id': identity, 'task_id': 'diagnostic-task-' + identity,
                'run_id': 'diagnostic-case-' + identity, 'input_path': str(inp), 'input_sha256': digest(inp),
                'expected_path': str(exp), 'expected_sha256': digest(exp),
                'source_evidence': [{'path': str(src), 'sha256': digest(src)}]}

    def test_permissions_status_is_readonly_and_limit_survives_restart(self):
        denied = self.job(allow_rsi=False)
        self.assertEqual(host.candidate_status(denied)['attempts_used'], 0)
        self.assertFalse((denied.parent / 'generated-tools').exists())
        with self.assertRaisesRegex(ValueError, '明确允许 RSI'):
            self.propose(denied)
        job = self.job()
        for number in range(1, 4):
            result = self.propose(job, code='not valid TypeScript')
            self.assertFalse(result['compile_passed'])
            self.assertEqual(result['attempt'], number)
            self.assertTrue(Path(result['diagnostic_path']).exists())
        self.assertEqual(host.candidate_status(Path(str(job)))['attempts_remaining'], 0)
        with self.assertRaisesRegex(ValueError, '3 次提案上限'):
            self.propose(job)

    def test_real_compilation_execution_schema_and_code_guard(self):
        candidate = self.valid()
        value = {'source_id': 'fixture', 'rows': [{'id': 'a', 'page': 1}, {'id': 'b', 'page': 2}]}
        result = host.run_candidate(candidate, value)
        self.assertEqual(result['output'], {'source_id': 'fixture', 'ids': ['a', 'b']})
        self.assertTrue(Path(result['execution_evidence']).exists())
        self.assertEqual(value['rows'][0]['id'], 'a')
        with self.assertRaisesRegex(ValueError, 'type=integer'):
            host.run_candidate(candidate, {'source_id': 'fixture', 'rows': [{'id': 'a', 'page': True}]})
        with self.assertRaisesRegex(ValueError, '未声明字段'):
            host.run_candidate(candidate, {**value, 'unrecognised': 1})
        with self.assertRaisesRegex(ValueError, '禁止的属性名'):
            host.run_candidate(candidate, {'source_id': 'fixture', 'rows': [], '__proto__': {}})
        code = candidate.parent / 'candidate.ts'
        code.write_text(CODE + '\n// changed after compilation\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '已变化'):
            host.run_candidate(candidate, value)

    def test_ast_rejects_process_import_eval_and_computed_constructor(self):
        unsafe = [
            "export function run(input:any):object { return {key:process.env.KEY}; }",
            "import {readFileSync} from 'node:fs'; export function run(input:any):object { return {}; }",
            "export function run(input:any):object { return eval(input.code); }",
            "export function run(input:any):object { const key='con'+'structor'; return input.rows[key]('return process')(); }",
            "export function run(input:any):object { return {value: input.rows.constructor}; }",
            "export function run(input:any):object { return {value: gl\\u006fbalThis}; }",
            "export async function run(input:any):Promise<object> { return {}; }",
        ]
        for code in unsafe:
            with self.subTest(code=code):
                result = self.propose(self.job(), code=code)
                self.assertFalse(result['compile_passed'], result)
                self.assertTrue(result['diagnostics'])

    def test_type_error_is_compile_failure_and_input_cannot_be_mutated(self):
        result = self.propose(self.job(), code="export function run(input:any):object { const wrong: number='text'; return {wrong}; }")
        self.assertFalse(result['compile_passed'])
        self.assertIn('编译失败', result['diagnostics'][0])
        candidate = self.valid(self.job())
        mutated = self.propose(self.job(), code="export function run(input:any):object { input.rows.push({id:'x',page:1}); return {source_id:input.source_id}; }")
        self.assertTrue(mutated['compile_passed'], mutated['diagnostics'])
        with self.assertRaisesRegex(ValueError, '真实执行失败'):
            host.run_candidate(mutated['candidate_path'], {'source_id': 'fixture', 'rows': []})
        self.assertEqual(host.run_candidate(candidate, {'source_id': 'fixture', 'rows': []})['output']['ids'], [])

    def test_real_reference_comparison_and_diagnostic_not_promoted(self):
        job = self.job()
        candidate = self.valid(job)
        cases = [self.case(job.parent, identity) for identity in ('train_a', 'train_b')]
        training = host.evaluate_candidate(candidate, cases)
        self.assertTrue(training['passed'])
        self.assertTrue(all(Path(row['execution_evidence']).exists() for row in training['cases']))
        wrong = self.case(job.parent, 'wrong', expected={'source_id': 'wrong', 'ids': []})
        self.assertFalse(host.evaluate_candidate(candidate, [wrong])['passed'])
        with self.assertRaisesRegex(ValueError, '工程诊断候选'):
            host.certify_candidate(candidate, training['evaluation_path'], [self.case(job.parent, 'heldout')])
        self.assertFalse((candidate.parent / 'certificate.json').exists())
        self.assertFalse(host.candidate_status(job)['training_closed'])
        changed = Path(cases[0]['expected_path'])
        changed.write_text('{"changed": true}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            host.certify_candidate(candidate, training['evaluation_path'], [self.case(job.parent, 'heldout_after_change')])

    def test_compiled_manifest_is_not_certificate_and_nonprivate_paths_rejected(self):
        candidate = self.valid()
        with self.assertRaisesRegex(ValueError, '有效独立认证'):
            host.load_certified_tool(candidate)
        with self.assertRaisesRegex(ValueError, '仓库 .local'):
            host.candidate_status(host.SCENE / 'scenario.json')
        schema = copy.deepcopy(SCHEMA)
        schema['properties']['rows']['items']['properties']['page']['minimum'] = 5
        schema['properties']['rows']['items']['properties']['page']['maximum'] = 1
        result = self.propose(self.job(), schema=schema)
        self.assertFalse(result['compile_passed'])
        self.assertIn('上下限', result['diagnostics'][0])


if __name__ == '__main__':
    unittest.main()
