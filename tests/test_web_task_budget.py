"""Free counter/control diagnostics, with no cloud calls or model runtime."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.adapters.deepseek_cost_gate import State, observed_peak_cost, reservation
from src.adapters.web_task_budget import TaskBudgetRegistry, create_control_server

BODY = b'{"model":"deepseek-flash","max_tokens":100,"messages":[]}'
USAGE = {"prompt_tokens": 12, "prompt_cache_hit_tokens": 8,
         "prompt_cache_miss_tokens": 4, "completion_tokens": 3, "total_tokens": 15}


class WebTaskBudgetTests(unittest.TestCase):
    def test_cancel_exports_only_current_route_receipts_and_does_not_reset_usage(self):
        session=self.register()
        self.registry.activate(session)
        route=self.registry.state_for({'x-deepseek-harness-session-id':session})
        booked=route.book(BODY)
        route.settle(booked[0],booked[1],200,USAGE)
        route.log({'request_id':booked[0],'response_status':200,'response_usage':USAGE,
                   'observed_peak_usd':0.0001,'private_header':'never-export'})
        route.state.log({'task_id':'f'*32,'response_status':200,'private_header':'foreign'})
        before=self.registry.run_state.request_count
        response=self.registry.cancel(session)
        self.assertEqual(len(response['request_receipts']),1)
        self.assertEqual(response['request_receipts'][0]['task_id'],route.task_id)
        self.assertNotIn('private_header',response['request_receipts'][0])
        self.assertEqual(self.registry.run_state.request_count,before)
        self.assertEqual(self.registry.cancel(session)['request_receipts'],response['request_receipts'])

    def test_cumulative_checkpoint_survives_routed_admission_crash_and_cap_expansion(self):
        checkpoint = self.root / 'cumulative.json'
        self.root.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({'request_count': 248, 'reserved_usd': 0.105}))
        state = State(cap_usd=1, output_cap=100, request_limit=1000,
                      record=self.root / 'continued-ledger.jsonl', checkpoint=checkpoint)
        registry = TaskBudgetRegistry(run_state=state, tasks_root=self.root / 'continued',
                                      task_request_limit=24, max_task_budget_usd=0.23)
        registry.register('1' * 32, 'turn-one', 0.23)
        registry.activate('turn-one')
        route = registry.state_for({'x-deepseek-harness-session-id': 'turn-one'})
        booked = route.book(BODY)
        carried = State(cap_usd=1, output_cap=100, request_limit=1000,
                        record=state.record, checkpoint=checkpoint)
        self.assertEqual(carried.request_count, 249)
        self.assertGreater(carried.reserved_usd, 0.105)
        route.settle(booked[0], booked[1], 200, USAGE)
        recovered = State(cap_usd=1, output_cap=100, request_limit=1000,
                          record=state.record, checkpoint=checkpoint)
        self.assertEqual(recovered.request_count, 249)
        self.assertAlmostEqual(recovered.reserved_usd, state.reserved_usd)
        self.assertGreater(recovered.reserved_usd, 0.105)
        for bad in ({'request_count': -1, 'reserved_usd': 0},
                    {'request_count': 248, 'reserved_usd': float('nan')},
                    {'request_count': True, 'reserved_usd': 0}):
            checkpoint.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                State(cap_usd=1, output_cap=100, request_limit=1000,
                      record=state.record, checkpoint=checkpoint)

    def test_active_route_never_charges_a_different_model(self):
        session = self.register()
        with self.assertRaises(PermissionError): self.registry.active_state_for({})
        self.registry.activate(session)
        route = self.registry.active_state_for({})
        self.assertEqual(route.model, 'deepseek-flash')
        with self.assertRaises(ValueError): route.book(b'{"model":"deepseek-v4-pro","max_tokens":10}')
        self.assertEqual(self.registry.stats(session)['upstream_requests'], 0)
        other = self.register(2)
        self.registry.activate(other)
        with self.assertRaises(PermissionError): self.registry.active_state_for({})

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / ".local" / "web" / "run"
        self.run = State(cap_usd=1, output_cap=100, request_limit=4,
                         record=self.root / "ledger.jsonl")
        self.registry = TaskBudgetRegistry(run_state=self.run, tasks_root=self.root / "tasks")

    def tearDown(self):
        self.temporary.cleanup()

    def register(self, number=1, budget=0.5):
        identity = f"{number:032x}"
        session = f"session-{number}"
        self.registry.register(identity, session, budget)
        return session

    def active(self, number=1, budget=0.5):
        session = self.register(number, budget)
        self.registry.activate(session)
        return self.registry.state_for({"x-deepseek-harness-session-id": session})

    def test_registration_inactive_immutable_and_activation_idempotent(self):
        session = self.register()
        with self.assertRaises(PermissionError):
            self.registry.state_for({"X-DeepSeek-Harness-Session-Id": session})
        self.registry.activate(session)
        route = self.registry.state_for({"X-DeepSeek-Harness-Session-Id": session})
        booked = route.book(BODY)
        self.registry.activate(session)
        self.registry.register(f"{1:032x}", session, 0.5)
        self.assertEqual(self.registry.stats(session)["upstream_requests"], 1)
        self.assertEqual(len(route.state.pending), 1)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.registry.register(f"{1:032x}", session, 0.1)
        with self.assertRaises(PermissionError):
            self.registry.state_for({})
        with self.assertRaises(PermissionError):
            self.registry.state_for({"x-deepseek-harness-session-id": "unregistered"})
        route.settle(booked[0], booked[1], 200, USAGE)

    def test_settlement_releases_both_reservations_and_records_only_usage(self):
        route = self.active()
        first = route.book(BODY)
        charged, released = route.settle(first[0], first[1], 200, USAGE)
        self.assertAlmostEqual(charged, observed_peak_cost(first[1], USAGE))
        self.assertGreater(released, 0)
        self.assertAlmostEqual(self.run.reserved_usd, route.state.reserved_usd)
        stats = self.registry.stats(route.session_id)
        self.assertEqual(stats["upstream_requests"], 1)
        self.assertEqual(stats["prompt_cache_hit_tokens"], 8)
        self.assertEqual(stats["prompt_cache_miss_tokens"], 4)
        self.assertEqual(stats["completion_tokens"], 3)
        self.assertTrue(stats["usage_complete"])
        self.assertEqual(stats["pending_requests"], 0)
        with self.assertRaisesRegex(ValueError, "already settled"):
            route.settle(first[0], first[1], 200, USAGE)
        route.log({"request_id": first[0], "response_usage": USAGE})
        task_row = json.loads(route.state.record.read_text(encoding="utf-8"))
        run_row = json.loads(self.run.record.read_text(encoding="utf-8"))
        self.assertEqual(task_row["global_request_id"], run_row["request_id"])
        self.assertEqual(run_row["task_request_id"], first[0])

    def test_whole_launch_request_limit_cannot_be_reset_by_new_tasks(self):
        routes = [self.active(number) for number in (1, 2, 3)]
        for index in range(4):
            route = routes[index % 3]
            booked = route.book(BODY)
            self.assertIsNotNone(booked)
            route.settle(booked[0], booked[1], 200, USAGE)
        self.assertIsNone(routes[-1].book(BODY))
        self.assertEqual(self.run.request_count, 4)
        self.assertEqual(sum(route.state.request_count for route in routes), 4)
        self.assertEqual(self.registry.stats(routes[-1].session_id)["denials"], 1)
        routes[-1].log({"kind": "budget_denied"})
        self.assertEqual(self.registry.stats(routes[-1].session_id)["denials"], 1)

    def test_explicit_task_limit_and_global_limit_are_both_enforced(self):
        self.registry = TaskBudgetRegistry(run_state=self.run, tasks_root=self.root / "tasks",
                                           task_request_limit=2)
        routes = [self.active(number) for number in (1, 2, 3)]
        for route in routes[:2]:
            for _ in range(2):
                booked = route.book(BODY)
                self.assertIsNotNone(booked)
                route.settle(booked[0], booked[1], 200, USAGE)
            self.assertIsNone(route.book(BODY))
            self.assertEqual(self.registry.stats(route.session_id)["request_limit"], 2)
            self.assertEqual(route.state.request_count, 2)
        self.assertIsNone(routes[2].book(BODY))
        self.assertEqual(routes[2].state.request_count, 0)
        self.assertEqual(self.run.request_count, 4)
        self.assertEqual(self.registry.stats(routes[2].session_id)["global_request_limit"], 4)
        for invalid in (-1, True, False, "2", 1.5):
            with self.assertRaisesRegex(ValueError, "task_request_limit"):
                TaskBudgetRegistry(run_state=self.run, tasks_root=self.root / "other", task_request_limit=invalid)

    def test_unlimited_task_and_global_counts_preserve_usage_and_dollar_guards(self):
        for limit in (None, 0):
            with self.subTest(limit=limit):
                self.run = State(cap_usd=1, output_cap=100, request_limit=limit,
                                 record=self.root / f'unlimited-{limit}.jsonl')
                self.registry = TaskBudgetRegistry(run_state=self.run,
                    tasks_root=self.root / f'unlimited-{limit}', task_request_limit=limit)
                route = self.active()
                for _ in range(25):
                    booked = route.book(BODY)
                    self.assertIsNotNone(booked)
                    route.settle(booked[0], booked[1], 200, USAGE)
                stats = self.registry.stats(route.session_id)
                self.assertIsNone(stats['request_limit'])
                self.assertIsNone(stats['global_request_limit'])
                self.assertEqual(stats['upstream_requests'], 25)
                self.assertEqual(stats['global_upstream_requests'], 25)
                route.state.cap_usd = route.state.reserved_usd
                self.assertIsNone(route.book(BODY))
                self.assertEqual(self.run.request_count, 25)
                route.state.cap_usd = 0.5
                self.run.cap_usd = self.run.reserved_usd
                self.assertIsNone(route.book(BODY))
                self.assertEqual(self.run.request_count, 25)

    def test_unlimited_task_does_not_inherit_count_cap_but_global_cap_still_applies(self):
        route = self.active()
        self.assertIsNone(route.state.request_limit)
        for _ in range(4):
            booked = route.book(BODY)
            route.settle(booked[0], booked[1], 200, USAGE)
        self.assertIsNone(route.book(BODY))
        self.assertEqual(self.run.request_count, 4)

    def test_atomic_parallel_booking_enforces_global_dollars(self):
        _, reservation_usd, _ = reservation(BODY, max_output=100)
        self.run.cap_usd = reservation_usd * 1.5
        self.registry.max_task_budget_usd = self.run.cap_usd
        routes = [self.active(number, self.run.cap_usd) for number in (1, 2)]
        with ThreadPoolExecutor(max_workers=2) as workers:
            bookings = list(workers.map(lambda route: route.book(BODY), routes))
        self.assertEqual(sum(value is not None for value in bookings), 1)
        self.assertEqual(self.run.request_count, 1)
        self.assertEqual(sum(route.state.request_count for route in routes), 1)
        successful = next(route for route, booking in zip(routes, bookings) if booking)
        booking = next(value for value in bookings if value)
        successful.settle(booking[0], booking[1], 200, USAGE)
        self.assertIsNotNone(routes[1].book(BODY))

    def test_zero_task_budget_denial_has_no_charge_and_cancel_stops_future_calls(self):
        zero = self.active(1, 0)
        self.assertIsNone(zero.book(BODY))
        self.assertEqual(self.run.request_count, 0)
        self.assertEqual(self.run.reserved_usd, 0)
        route = self.active(2)
        booked = route.book(BODY)
        self.registry.cancel(route.session_id)
        self.registry.cancel(route.session_id)
        with self.assertRaises(PermissionError):
            self.registry.state_for({"x-deepseek-harness-session-id": route.session_id})
        self.assertIsNone(route.book(BODY))
        with self.assertRaisesRegex(ValueError, "cancelled"):
            self.registry.activate(route.session_id)
        # An already sent request still settles after cancellation.
        route.settle(booked[0], booked[1], 200, USAGE)
        self.assertEqual(self.run.request_count, 1)

    def test_failed_or_missing_usage_keeps_conservative_reservation_in_both_states(self):
        route = self.active()
        for status, usage in ((502, {}), (200, {})):
            booked = route.book(BODY)
            self.assertEqual(route.settle(booked[0], booked[1], status, usage), (None, 0.0))
        stats = self.registry.stats(route.session_id)
        self.assertEqual(stats["unknown_usage_requests"], 2)
        self.assertFalse(stats["usage_complete"])
        self.assertAlmostEqual(route.state.reserved_usd, self.run.reserved_usd)
        self.assertGreater(stats["estimated_cost_usd"], 0)

    def test_boundaries_private_ledger_and_cold_registration_are_checked(self):
        for task, session, budget in (("../escape", "session", 0.1), ("a" * 32, "bad\nidentity", 0.1),
                                      ("a" * 32, "session", 2), ("a" * 32, "session", float("nan"))):
            with self.assertRaises(ValueError):
                self.registry.register(task, session, budget)
        with self.assertRaisesRegex(ValueError, "private"):
            TaskBudgetRegistry(run_state=self.run, tasks_root=self.root.parent.parent.parent / "public")
        self.register()
        cold = TaskBudgetRegistry(run_state=self.run, tasks_root=self.root / "tasks")
        with self.assertRaisesRegex(ValueError, "ledger exists"):
            cold.register(f"{1:032x}", "session-1", 0.5)
        route = self.active(2)
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            route.book(b'{"model":"deepseek-flash","max_tokens":101}')

    def test_control_service_authentication_routes_and_no_token_disclosure(self):
        token = "private-control-token-" + "x" * 32
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_control_server("0.0.0.0", 0, self.registry, control_token=token)
        server = create_control_server("127.0.0.1", 0, self.registry, control_token=token)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        endpoint = f"http://127.0.0.1:{server.server_port}"

        def call(path, value=None, authenticated=True):
            request = urllib.request.Request(endpoint + path,
                data=None if value is None else json.dumps(value).encode(),
                headers={"Content-Type": "application/json", **({"X-SSS-Control-Token": token} if authenticated else {})})
            try:
                with opener.open(request, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())

        try:
            registration = {"task_id": f"{1:032x}", "session_id": "session-1", "budget_usd": 0.25}
            self.assertEqual(call("/tasks/register", registration, False)[0], 401)
            code, value = call("/tasks/register", registration)
            self.assertEqual(code, 200)
            self.assertFalse(value["active"])
            self.assertNotIn(token, json.dumps(value))
            self.assertEqual(call("/tasks/activate", {"session_id": "session-1"})[0], 200)
            self.assertEqual(call("/tasks/stats?session_id=session-1")[1]["upstream_requests"], 0)
            self.assertEqual(call("/tasks/cancel", {"session_id": "session-1"})[1]["cancelled"], True)
            self.assertEqual(call("/tasks/activate", {"session_id": "session-1"})[0], 400)
            self.assertEqual(call("/tasks/register", {**registration, "arbitrary": True})[0], 400)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
