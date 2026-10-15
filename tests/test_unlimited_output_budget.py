"""Uncapped application output remains metered against finite task budgets."""
import json
from pathlib import Path
import tempfile
import unittest

from src.adapters.deepseek_cost_gate import (State, reservation, normalize_output_limit,
    output_limit_argument, provider_output_reservation)
from src.adapters.web_task_budget import TaskBudgetRegistry


class UnlimitedOutputBudgetTests(unittest.TestCase):
    def test_output_limit_is_explicitly_optional_and_finite_limits_still_work(self):
        for value in (None, 0): self.assertIsNone(normalize_output_limit(value))
        self.assertIsNone(output_limit_argument('0'))
        for value in (-1, True, 1.2, '1000'):
            with self.assertRaises(ValueError): normalize_output_limit(value)
        body = json.dumps({'model': 'deepseek-flash', 'max_tokens': 2000}).encode()
        self.assertGreater(reservation(body, max_output=None)[1], 0)
        with self.assertRaisesRegex(ValueError, 'per-request cap'): reservation(body, max_output=1000)

    def test_omitted_output_uses_provider_defaults_without_mutating_request(self):
        for thinking, effort, expected in (({'type': 'disabled'}, 'off', 8192),
                                           (None, None, 65536), ({'type': 'enabled'}, 'max', 131072)):
            request = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': '你好' * 10001}]}
            if thinking is not None: request['thinking'] = thinking
            if effort != 'off' and effort is not None: request['reasoning_effort'] = effort
            body = json.dumps(request, ensure_ascii=False).encode()
            _, dollars, input_ceiling = reservation(body, max_output=None)
            self.assertAlmostEqual(dollars, (input_ceiling * .30 + expected * 1.20) / 1_000_000)
            self.assertEqual(json.loads(body), request)
            self.assertNotIn('max_tokens', request)
            self.assertEqual(provider_output_reservation('deepseek-flash', request), expected)

    def test_unknown_provider_cannot_reserve_zero_for_missing_output(self):
        with self.assertRaisesRegex(ValueError, 'capacity is unknown'):
            reservation(b'{"model":"unknown-model"}', max_output=None, rates={'unknown-model': (1, 1)})
        for value in (True, -1, 0, 1.5, '1000'):
            with self.assertRaises(ValueError):
                reservation(json.dumps({'model': 'deepseek-flash', 'max_tokens': value}).encode(), max_output=None)
        self.assertEqual(provider_output_reservation('glm-4.6', {}), 131072)

    def test_task_budget_survives_omitted_limit_unknown_usage_and_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / '.local'; root.mkdir()
            checkpoint = root / 'cumulative.json'
            checkpoint.write_text('{"request_count":624,"reserved_usd":0.412557114}')
            state = State(cap_usd=None, output_cap=None, record=root / 'ledger.jsonl', checkpoint=checkpoint)
            registry = TaskBudgetRegistry(run_state=state, tasks_root=root / 'tasks', max_task_budget_usd=.23)
            registry.register('a' * 32, 'session', .23); registry.activate('session')
            route = registry.state_for({'x-deepseek-harness-session-id': 'session'})
            body = b'{"model":"deepseek-flash","thinking":{"type":"disabled"},"messages":[]}'
            booked = route.book(body)
            self.assertIsNotNone(booked)  # No maximum-capacity reservation that rejects every request.
            self.assertGreater(booked[2], 8192 * 1.2 / 1_000_000)
            self.assertLess(booked[2], .23)
            route.settle(booked[0], booked[1], 502, {})
            self.assertEqual(registry.stats('session')['unknown_usage_requests'], 1)
            self.assertIsNone(registry.stats('session')['output_cap'])
            self.assertAlmostEqual(state.reserved_usd, .412557114 + booked[2])
            # Keep admitting until the task's monetary cap, without a request-count cap.
            while route.book(body) is not None: pass
            self.assertLessEqual(route.state.reserved_usd, .23)
            self.assertGreater(route.state.request_count, 1)
            reloaded = State(cap_usd=None, output_cap=None, record=state.record, checkpoint=checkpoint)
            self.assertEqual(reloaded.request_count, state.request_count)
            self.assertEqual(reloaded.reserved_usd, state.reserved_usd)


if __name__ == '__main__': unittest.main()
