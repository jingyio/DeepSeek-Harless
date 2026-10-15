"""独立私有模型预算服务：显式沿用累计 checkpoint，重启不清零。"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import threading
from pathlib import Path
from secrets import token_hex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.deepseek_cost_gate import State, create_server, request_limit_argument
from src.adapters.web_task_budget import TaskBudgetRegistry, create_control_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--budget-usd', type=float, required=True)
    parser.add_argument('--request-limit', type=request_limit_argument, required=True,
                        help='cumulative request cap; 0 means unlimited without resetting usage')
    parser.add_argument('--task-budget-usd', type=float, default=0.23)
    parser.add_argument('--task-request-limit', type=request_limit_argument, default=None,
                        help='per-task request cap; 0 means unlimited (default)')
    parser.add_argument('--max-output', type=int, default=1000)
    args = parser.parse_args()
    if (not math.isfinite(args.budget_usd) or not 0 < args.budget_usd <= 100 or
            not 0 < args.task_budget_usd <= args.budget_usd or not 1 <= args.max_output <= 8000):
        parser.error('invalid explicit spending limits')
    output, checkpoint = args.output.resolve(), args.checkpoint.resolve()
    if '.local' not in output.parts or not checkpoint.is_relative_to(output):
        parser.error('budget data must remain in a private .local output')
    if not checkpoint.is_file():
        parser.error('an explicit cumulative checkpoint is required; refusing to reset usage')
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=True)
    state = State(cap_usd=args.budget_usd, output_cap=args.max_output,
                  record=output / 'ledger.jsonl', request_limit=args.request_limit,
                  checkpoint=checkpoint)
    registry = TaskBudgetRegistry(run_state=state, tasks_root=output / 'tasks',
                                  max_task_budget_usd=args.task_budget_usd,
                                  task_request_limit=args.task_request_limit)
    token = token_hex(32)
    control = create_control_server('127.0.0.1', 0, registry, control_token=token)
    gate = create_server('127.0.0.1', 0, 'https://api.deepseek.com', state,
                         state_selector=registry.state_for,
                         allowed_models={'deepseek-flash', 'deepseek-v4-pro'})
    policy = {'endpoint': f'http://127.0.0.1:{gate.server_port}/v1',
              'control_endpoint': f'http://127.0.0.1:{control.server_port}',
              'control_token': token, 'budget_usd': args.task_budget_usd,
              'request_limit': args.task_request_limit,
              'run_budget_usd': args.budget_usd, 'run_request_limit': args.request_limit}
    (output / 'policy.json').write_text(json.dumps(policy) + '\n')
    for server in (gate, control):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'ready': True, 'request_count': state.request_count,
                      'request_limit': args.task_request_limit, 'run_request_limit': state.request_limit,
                      'reserved_usd': state.reserved_usd}), flush=True)
    signal.pause()


if __name__ == '__main__':
    main()
