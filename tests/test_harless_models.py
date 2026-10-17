"""Read-only model discovery and budget compatibility diagnostics, no paid calls."""
import io
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.adapters.harless_models import CATALOG_URL, discover_deepseek_models, model_options, price_basis
from src.adapters.deepseek_cost_gate import State
from src.adapters.web_task_budget import TaskBudgetRegistry


class ModelCatalogTests(unittest.TestCase):
    def test_web_launcher_records_verified_catalog_and_actual_price_basis(self):
        repo = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('web_models', repo / 'scripts/harness-web.py')
        web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
        catalog = {'data': [{'id': 'deepseek-flash'}, {'id': 'deepseek-v4-pro'}], 'model_requests': 0}
        args = SimpleNamespace(scenario='new-scene', case='', real_model=True, mode='baseline',
            embedding_endpoint='', embedding_model='diagnostic', fixture='normal', frozen=False,
            manifest=None, task=None, glm=None, port=3080, public_origin=None, budget_usd=.23,
            request_limit=None, run_budget_usd=None, run_request_limit=None, resources=None,
            user_id='diagnostic', control_endpoint='http://127.0.0.1:9', control_token='diagnostic',
            scene_registry='config/harless-scenes.json', deepseek_catalog=catalog)
        with tempfile.TemporaryDirectory() as directory, patch.object(web, 'prepare_scene_registry', return_value=[{'id': 'new-scene'}]):
            root = Path(directory)
            web.prepare(args, root, 'http://127.0.0.1:9/v1')
            policy = json.loads((root / 'policy.json').read_text())
            snapshot = json.loads((root / 'effective-config.json').read_text())
            self.assertEqual(policy['models'], model_options(catalog, budget_usd=.23))
            self.assertEqual(snapshot['configured_models'], policy['models'])
            self.assertEqual(snapshot['deepseek_model_discovery'], catalog)
            self.assertEqual(snapshot['deepseek_price_basis'], price_basis(policy['models']))

    def test_catalog_filters_unpriced_retired_and_duplicate_models_preserves_order(self):
        options = model_options({'data': [{'id': model} for model in (
            'unpriced-future', 'deepseek-v4-pro', 'deepseek-flash', 'deepseek-v4-flash', 'deepseek-flash')]}, budget_usd=.23)
        self.assertEqual([row['model'] for row in options], ['deepseek-flash', 'deepseek-v4-pro'])
        self.assertNotIn('reasoning_unavailable', options[0])
        self.assertEqual(list(options[1]['reasoning_unavailable']), ['low', 'high', 'max'])
        self.assertIn('$0.23', options[1]['reasoning_unavailable']['high'])
        self.assertIn('$0.259523', options[1]['reasoning_unavailable']['high'])
        self.assertIn('$0.519045', options[1]['reasoning_unavailable']['max'])
        max_only = model_options({'data': [{'id': 'deepseek-v4-pro'}]}, budget_usd=.5)[0]
        self.assertEqual(list(max_only['reasoning_unavailable']), ['max'])
        self.assertNotIn('reasoning_unavailable', model_options({'data': [{'id': 'deepseek-v4-pro'}]}, budget_usd=.6)[0])
        prices = price_basis(options)
        self.assertEqual(prices['deepseek-flash']['output'], 1.20)
        self.assertEqual(prices['deepseek-v4-pro']['output'], 3.96)
        self.assertEqual(prices['deepseek-v4-pro']['input_cache_hit'], .044)
        for data in ({}, {'data': []}, {'data': [{'id': 'unpriced'}]}):
            with self.assertRaises(ValueError): model_options(data, budget_usd=.23)

    def test_discovery_makes_only_a_catalog_get_and_removes_unexpected_fields(self):
        calls = []
        class Response(io.BytesIO):
            status = 200
            def geturl(self): return CATALOG_URL
        def open_catalog(request, **kwargs):
            calls.append((request.full_url, request.method, kwargs))
            self.assertEqual(request.get_header('Authorization'), 'Bearer diagnostic-credential')
            return Response(json.dumps({'data': [{'id': 'deepseek-flash', 'name': 'DeepSeek-V4.1-Flash', 'unexpected': 'secret-like-value'}], 'extra': 'private'}).encode())
        snapshot = discover_deepseek_models('diagnostic-credential', opener=open_catalog)
        self.assertEqual(calls, [(CATALOG_URL, 'GET', {'timeout': 20})])
        self.assertEqual(snapshot['model_requests'], 0)
        self.assertEqual(snapshot['data'], [{'id': 'deepseek-flash', 'name': 'DeepSeek-V4.1-Flash'}])
        self.assertNotIn('diagnostic-credential', json.dumps(snapshot))
        def failure(*args, **kwargs): raise RuntimeError('diagnostic-credential private-body')
        with self.assertRaises(ValueError) as error: discover_deepseek_models('diagnostic-credential', opener=failure)
        self.assertNotIn('diagnostic-credential', str(error.exception))
        self.assertNotIn('private-body', str(error.exception))

    def test_unlimited_task_budget_exposes_both_reasoning_modes_for_both_models(self):
        options = model_options({'data': [{'id': 'deepseek-flash'}, {'id': 'deepseek-v4-pro'}]}, budget_usd=None)
        self.assertEqual(len(options), 2)
        self.assertTrue(all(row['available'] and 'reasoning_unavailable' not in row for row in options))
        self.assertTrue(all('supported_reasoning_efforts' not in row for row in options), 'ID-only catalogs defer to installed provider metadata')

    def test_capability_metadata_filters_strengths_without_conflating_budget_annotation(self):
        options = model_options({'data': [
            {'id': 'deepseek-flash', 'supported_reasoning_efforts': ['max', 'low', 'medium', 'low']},
            {'id': 'deepseek-v4-pro', 'supported_reasoning_efforts': ['high']},
        ]}, budget_usd=.23)
        self.assertEqual(options[0]['supported_reasoning_efforts'], ['off', 'low', 'max'])
        self.assertEqual(options[1]['supported_reasoning_efforts'], ['off', 'high'])
        self.assertEqual(list(options[1]['reasoning_unavailable']), ['high'])
        off_only = model_options({'data': [{'id': 'deepseek-flash', 'supported_reasoning_efforts': []}]}, budget_usd=None)
        self.assertEqual(off_only[0]['supported_reasoning_efforts'], ['off'])
        for invalid in (None, 'high', [1], {}):
            with self.assertRaisesRegex(ValueError, 'reasoning capability'):
                model_options({'data': [{'id': 'deepseek-flash', 'supported_reasoning_efforts': invalid}]}, budget_usd=None)

    def test_configured_output_limit_reserves_all_enabled_strengths_consistently(self):
        options = model_options({'data': [{'id': 'deepseek-v4-pro'}]}, budget_usd=.003, max_output_tokens=1000)
        self.assertEqual(list(options[0]['reasoning_unavailable']), ['off', 'low', 'high', 'max'])
        for reason in options[0]['reasoning_unavailable'].values():
            self.assertIn('$0.003960', reason)
            self.assertIn('已配置', reason)

    def test_pro_off_fits_both_comparison_lanes_but_pro_on_is_rejected_before_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / '.local'; root.mkdir()
            state = State(cap_usd=None, output_cap=None, record=root / 'ledger.jsonl')
            registry = TaskBudgetRegistry(run_state=state, tasks_root=root / 'tasks', max_task_budget_usd=.23)
            for index in (1, 2):
                session = f'lane-{index}'
                registry.register(str(index) * 32, session, .115, model='deepseek-v4-pro')
                registry.activate(session)
                route = registry.state_for({'x-deepseek-harness-session-id': session})
                body = b'{"model":"deepseek-v4-pro","thinking":{"type":"disabled"},"messages":[{"role":"user","content":"hello"}]}'
                booked = route.book(body)
                self.assertIsNotNone(booked)
                self.assertLess(booked[2], .115)
                self.assertGreater(booked[2], 8192 * 3.96 / 1_000_000)
                self.assertNotIn('max_tokens', json.loads(body))
            count = state.request_count
            registry.register('3' * 32, 'pro-on', .23, model='deepseek-v4-pro')
            registry.activate('pro-on')
            route = registry.state_for({'x-deepseek-harness-session-id': 'pro-on'})
            self.assertIsNone(route.book(b'{"model":"deepseek-v4-pro","thinking":{"type":"enabled"},"reasoning_effort":"high","messages":[]}'))
            self.assertEqual(state.request_count, count)
            self.assertEqual(registry.stats('pro-on')['upstream_requests'], 0)


if __name__ == '__main__': unittest.main()
