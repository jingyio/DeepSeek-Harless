"""公开场景配置回归；不发起模型请求，不以此代表科学质量。"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scenarios.research_ppt.cli import ROOT, save, scenario_for, run
from src.adapters.scenario import prepare_scenario


class CLIRuntimeTests(unittest.TestCase):
    def setUp(self):
        area = ROOT / '.local/research-ppt/cli-runtime-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.job = Path(self.temp.name) / 'job.json'
        self.data = {'instruction': '验证可靠入口', 'slides': 2, 'inputs': [], 'design_skill': False}
        save(self.job, self.data)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_is_public_ts_delivery_and_explicit_python(self):
        prepared = prepare_scenario(scenario_for(self.job, False))
        self.assertIn('mcp__ppt__pin_deck_pages', prepared['allowed_tools'])
        self.assertIn('mcp__ppt__list_restorable_decks', prepared['allowed_tools'])
        patch = Path(prepared['patch']).read_text(encoding='utf-8')
        self.assertIn('mcp-adapter.js', patch)
        self.assertIn('SSS_PPT_DELIVERY_PYTHON', patch)
        self.assertEqual(prepared['required_env'], sorted(['SSS_PPT_JOB', *[
            name for name in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH') if os.environ.get(name)]]))

    def test_private_font_configuration_crosses_stdio_boundary_without_secrets(self):
        with patch.dict(os.environ, {'FONTCONFIG_FILE': '/private/fonts.conf',
                'FONTCONFIG_PATH': '/private/fonts', 'DEEPSEEK_API_KEY': 'must-not-copy'}):
            spec = json.loads(scenario_for(self.job, False).read_text(encoding='utf-8'))
            prepared = prepare_scenario(scenario_for(self.job, False))
        env = spec['servers'][0]['env']
        self.assertEqual(env['FONTCONFIG_FILE'], {'from_env': 'FONTCONFIG_FILE'})
        self.assertEqual(env['FONTCONFIG_PATH'], {'from_env': 'FONTCONFIG_PATH'})
        self.assertNotIn('DEEPSEEK_API_KEY', env)
        self.assertEqual(prepared['required_env'], ['FONTCONFIG_FILE', 'FONTCONFIG_PATH', 'SSS_PPT_JOB'])

    def test_legacy_and_rsi_keep_existing_service_and_tool_scope(self):
        legacy = prepare_scenario(scenario_for(self.job, False, 'legacy'))
        self.assertNotIn('mcp__ppt__pin_deck_pages', legacy['allowed_tools'])
        improvement = prepare_scenario(scenario_for(self.job, True))
        self.assertEqual(improvement['allowed_tools'], ['mcp__ppt__rsi_status', 'mcp__ppt__propose_guard'])
        self.assertIn('server.py', Path(improvement['patch']).read_text(encoding='utf-8'))

    def test_reliable_does_not_silently_load_dynamic_candidates(self):
        save(self.job, {**self.data, 'generated_tool_certificate': 'must-not-be-read'})
        with self.assertRaisesRegex(ValueError, 'legacy'):
            scenario_for(self.job, False)

    def test_unknown_runtime_rejected(self):
        with self.assertRaises(ValueError):
            scenario_for(self.job, False, 'unknown')

    def test_output_limit_is_forwarded_and_recorded_without_model(self):
        save(self.job, {**self.data, 'job_id': 'output-limit-regression', 'allow_output': False})
        with patch('scenarios.research_ppt.cli.subprocess.call', return_value=0) as launcher:
            self.assertEqual(run(self.job, max_output=8000), 0)
        args = launcher.call_args.args[0]
        self.assertEqual(args[args.index('--max-output') + 1], '8000')
        invocation = json.loads(next(self.job.parent.glob('invocation-*.json')).read_text(encoding='utf-8'))
        self.assertEqual(invocation['max_output'], 8000)
        self.assertFalse(invocation['model_call_enabled'])

    def test_release_defaults_are_forwarded_without_enabling_model(self):
        save(self.job, {**self.data, 'job_id': 'release-defaults', 'allow_output': False})
        with patch('scenarios.research_ppt.cli.subprocess.call', return_value=0) as launcher:
            self.assertEqual(run(self.job), 0)
        args = launcher.call_args.args[0]
        for option, expected in (('--max-steps', '60'), ('--max-output', '8000'), ('--budget-usd', '1.5')):
            self.assertEqual(args[args.index(option) + 1], expected)
        self.assertNotIn('--call-model', args)
        spec = json.loads(scenario_for(self.job, False).read_text(encoding='utf-8'))
        self.assertEqual(spec['servers'][0]['tool_call_timeout_ms'], 300000)

    def test_invalid_output_limit_rejected_before_starting_or_reading_job(self):
        with patch('scenarios.research_ppt.cli.subprocess.call') as launcher:
            for limit in (0, 8001, True, 5000.0):
                with self.assertRaises(ValueError):
                    run(self.job.parent / 'nonexistent.json', max_output=limit)
            launcher.assert_not_called()
