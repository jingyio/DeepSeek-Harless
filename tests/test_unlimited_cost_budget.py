"""No-model diagnostics for optional cumulative caps and retained task limits."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.adapters.deepseek_cost_gate import State, cost_cap_argument, reservation
from src.adapters.web_task_budget import TaskBudgetRegistry

ROOT = Path(__file__).resolve().parents[1]
BODY = b'{"model":"deepseek-flash","max_tokens":1000,"messages":[]}'
USAGE = {'prompt_tokens': 12, 'prompt_cache_hit_tokens': 8,
         'prompt_cache_miss_tokens': 4, 'completion_tokens': 3, 'total_tokens': 15}


class UnlimitedCostBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / '.local' / 'budget'
        self.root.mkdir(parents=True)
        self.checkpoint = self.root / 'cumulative.json'
        self.checkpoint.write_text(json.dumps({'request_count': 1001, 'reserved_usd': 1.5}))

    def state(self, cap=None, request_limit=None):
        return State(cap_usd=cap, output_cap=1000, record=self.root / 'ledger.jsonl',
                     request_limit=request_limit, checkpoint=self.checkpoint)

    def test_null_cap_keeps_counts_cost_settlement_and_restart(self):
        state = self.state()
        booked = state.book(BODY)
        self.assertIsNotNone(booked)
        self.assertEqual(state.request_count, 1002)
        # Restart before usage arrives retains the full reservation.
        pending = self.state()
        self.assertEqual(pending.reserved_usd, state.reserved_usd)
        self.assertGreater(pending.reserved_usd, 1.5)
        observed, _ = state.settle(booked[0], booked[1], 200, USAGE)
        self.assertGreater(observed, 0)
        recovered = self.state()
        self.assertAlmostEqual(recovered.reserved_usd, 1.5 + observed)
        self.assertEqual(recovered.request_count, 1002)
        # Reintroducing a finite cap never discards usage to make it fit.
        self.assertIsNone(self.state(1).book(BODY))
        self.assertIsNotNone(self.state(2).book(BODY))

    def test_unlimited_cost_still_enforces_output_and_optional_count_caps(self):
        state = self.state(request_limit=1001)
        self.assertIsNone(state.book(BODY))
        with self.assertRaisesRegex(ValueError, 'per-request cap'):
            self.state().book(BODY.replace(b'1000', b'1001'))
        self.assertEqual(self.state().request_count, 1001)

    def test_cli_zero_is_unlimited_but_internal_zero_is_zero_budget(self):
        self.assertIsNone(cost_cap_argument('0'))
        self.assertEqual(cost_cap_argument('0.23'), .23)
        for value in ('-1', 'nan', 'inf', '-inf', 'null'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cost_cap_argument(value)
        for value in (-1, float('nan'), float('inf'), True, False, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.state(value)
        zero = State(cap_usd=0, output_cap=1000, record=self.root / 'zero.jsonl')
        self.assertIsNone(zero.book(BODY))

    def test_task_cap_remains_atomic_and_other_task_can_continue(self):
        state = self.state()
        registry = TaskBudgetRegistry(run_state=state, tasks_root=self.root / 'tasks',
                                      max_task_budget_usd=.23)
        cost = reservation(BODY, max_output=1000)[1]
        registry.register('a' * 32, 'first', cost * 2.5)
        registry.register('b' * 32, 'second', .23)
        registry.activate('first')
        registry.activate('second')
        first = registry.state_for({'x-deepseek-harness-session-id': 'first'})
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: first.book(BODY), range(16)))
        self.assertEqual(sum(result is not None for result in results), 2)
        second = registry.state_for({'x-deepseek-harness-session-id': 'second'})
        self.assertIsNotNone(second.book(BODY))
        stats = registry.stats('second')
        self.assertIsNone(stats['global_budget_usd'])
        self.assertEqual(stats['budget_usd'], .23)
        self.assertIsNone(stats['request_limit'])
        self.assertIsNone(stats['global_request_limit'])
        self.assertEqual(state.request_count, 1004)
        self.assertGreater(state.reserved_usd, 1.5)
        self.assertEqual(self.state().request_count, 1004)

    def test_unlimited_global_requires_explicit_finite_task_maximum(self):
        for maximum in (None, float('inf'), float('nan'), -.1):
            with self.subTest(maximum=maximum), self.assertRaisesRegex(ValueError, 'finite task maximum'):
                TaskBudgetRegistry(run_state=self.state(), tasks_root=self.root / 'tasks',
                                   max_task_budget_usd=maximum)
        registry = TaskBudgetRegistry(run_state=self.state(), tasks_root=self.root / 'tasks',
                                      max_task_budget_usd=.23)
        for task_cap in (None, .24):
            with self.subTest(task_cap=task_cap), self.assertRaises(ValueError):
                registry.register('a' * 32, 'first', task_cap)
        registry.register('a' * 32, 'first', 0)
        registry.activate('first')
        self.assertIsNone(registry.state_for({'x-deepseek-harness-session-id': 'first'}).book(BODY))

    def test_budget_service_emits_null_policy_without_resetting_checkpoint(self):
        spec = importlib.util.spec_from_file_location('serve_budget_test', ROOT / 'scripts/serve-web-budget.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_checkpoint = self.checkpoint.read_bytes()
        control, gate = Mock(server_port=40001), Mock(server_port=40002)
        argv = ['serve-web-budget.py', '--output', str(self.root), '--checkpoint', str(self.checkpoint),
                '--budget-usd', '0', '--request-limit', '0', '--task-request-limit', '0']
        with patch('sys.argv', argv), patch.object(module.signal, 'pause', create=True), \
                patch.object(module, 'create_control_server', return_value=control) as control_factory, \
                patch.object(module, 'create_server', return_value=gate) as gate_factory, patch('builtins.print'):
            module.main()
        policy = json.loads((self.root / 'policy.json').read_text())
        self.assertIsNone(policy['run_budget_usd'])
        self.assertIsNone(policy['request_limit'])
        self.assertIsNone(policy['run_request_limit'])
        self.assertEqual(policy['budget_usd'], .23)
        registry = control_factory.call_args.args[2]
        state = gate_factory.call_args.args[3]
        self.assertIsNone(state.cap_usd)
        self.assertIsNone(state.output_cap)
        self.assertIsNone(policy['max_output_tokens'])
        self.assertEqual(state.request_count, 1001)
        self.assertEqual(state.reserved_usd, 1.5)
        self.assertEqual(registry.max_task_budget_usd, .23)
        self.assertEqual(self.checkpoint.read_bytes(), original_checkpoint)


if __name__ == '__main__':
    unittest.main()
