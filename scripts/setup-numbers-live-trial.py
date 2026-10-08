#!/usr/bin/env python3
"""Create experimental Numbers documents from existing, non-content API ledgers.

All cell values and formula evaluation go through Numbers.app via Digits.
Existing user documents are never edited. Cases and originals remain private.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.local/benchmarks/numbers-live-v1'
spec = importlib.util.spec_from_file_location('digits', ROOT / '.local/numbers-digits-upstream/server/digits_server.py')
digits = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digits)


def private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def main():
    if '--freeze-names' in sys.argv:
        cases = json.loads((BASE / 'cases.json').read_text())
        for case, scope in cases.items():
            doc = scope['document']
            previous = dict(scope)
            if hashlib.sha256(Path(scope['path']).read_bytes()).hexdigest() != scope['sha256']:
                raise ValueError('workbook changed before freezing')
            sheet = digits.list_sheets({'document': doc})[0]
            table = digits.list_tables({'document': doc, 'sheet': sheet})[0]['name']
            new_sheet, new_table = '费用_' + case, '请求_' + case
            digits._run('tell application "Numbers"\n'
                        f'set name of table {digits._q(table)} of sheet {digits._q(sheet)} of document {digits._q(doc)} to {digits._q(new_table)}\n'
                        f'set name of sheet {digits._q(sheet)} of document {digits._q(doc)} to {digits._q(new_sheet)}\nend tell')
            digits.save_document({'document': doc})
            scope['sha256'] = hashlib.sha256(Path(scope['path']).read_bytes()).hexdigest()
            private(BASE / case / 'scope.json', {k:scope[k] for k in ('path','document','sha256')})
            private(BASE / case / 'setup-revision.json', {'before':previous, 'after':scope,
                'reason':'Distinct native worksheet/table names test rebinding rather than constant default names. Pilot trajectories preserved.'})
            prompt_path = BASE / case / 'prompt.txt'
            old_prompt = prompt_path.read_text()
            private(BASE / case / 'pilot-prompt.json', {'prompt':old_prompt})
            prompt_path.write_text(old_prompt + '为避免混淆同时打开的工作簿，发现名称后请在查询工作表、表格和数据时显式填写适用的 document、sheet、table；仍可自行选择调用顺序与批量读取方式。')
        private(BASE / 'cases.json', cases)
        print('Native workbook and table names frozen; pilot records retained.')
        return
    extra='--extra-v2' in sys.argv
    sources = {
        'train_zotero': 'zotero/budget-ledger.jsonl',
        'train_obsidian': 'obsidian/budget-ledger.jsonl',
        'validate_literature': 'literature/budget-ledger.jsonl',
        'test_calendar_a': 'calendar/availability-v1/agent-a/budget-ledger.jsonl',
        'test_calendar_b': 'calendar/availability-v1/agent-b/budget-ledger.jsonl',
        'test_calendar_c': 'calendar/availability-v1/agent-c/budget-ledger.jsonl',
    }
    if extra:
        sources={
          'debug_d':'calendar/motif-continuation-v1/agent-d/budget-ledger.jsonl',
          'debug_e':'calendar/motif-continuation-v1/agent-e/budget-ledger.jsonl',
          'debug_f':'calendar/agent-a/budget-ledger.jsonl',
        }
        previous=json.loads((BASE/'cases.json').read_text())
        private(BASE/'cases-before-v2.json',previous)
        cases=previous
    else:
        cases = {}
    for case, relative in sources.items():
        out = BASE / 'workbooks' / (case + '.numbers')
        if out.exists():
            raise ValueError('Refusing to replace an existing workbook: ' + case)
        source = ROOT / '.local/benchmarks/mcp-app-internal-v2' / relative
        records = [json.loads(x) for x in source.read_text().splitlines() if x.strip()]
        records = [x for x in records if x.get('response_status') == 200 and 'observed_peak_usd' in x]
        if not records:
            raise ValueError('No billable successful requests: ' + case)
        costs = [x['observed_peak_usd'] for x in records]
        digits.create_document({})
        doc = digits._run('tell application "Numbers" to get name of front document')
        sheet = digits.list_sheets({'document': doc})[0]
        table = digits.list_tables({'document': doc, 'sheet': sheet})[0]['name']
        count = len(records) + 2
        target = digits._target(doc, sheet, table)
        digits._run('tell application "Numbers"\n'
                    f'tell {target}\nset row count to {count}\nset column count to 3\n'
                    'set width of column 1 to 200\nset width of column 2 to 170\n'
                    'set width of column 3 to 210\nend tell\nend tell')
        updates = [{'cell': 'A1', 'value': 'Request'}, {'cell': 'B1', 'value': 'Cost USD'},
                   {'cell': 'C1', 'value': 'HTTP status'}]
        for i, row in enumerate(records, 2):
            updates += [{'cell': f'A{i}', 'value': 'request-' + str(i-1)},
                        {'cell': f'B{i}', 'value': row['observed_peak_usd']},
                        {'cell': f'C{i}', 'value': row['response_status']}]
        updates += [{'cell': f'A{count}', 'value': 'TOTAL'},
                    {'cell': f'B{count}', 'value': f'=SUM(B2:B{count-1})'}]
        digits.set_cells({'document': doc, 'sheet': sheet, 'table': table, 'updates': updates})
        out.parent.mkdir(parents=True, exist_ok=True)
        digits.save_as({'document': doc, 'path': str(out)})
        name = digits.open_document({'path': str(out)})
        if extra:
            new_sheet,new_table='费用_'+case,'请求_'+case
            digits._run('tell application "Numbers"\n'
                        f'set name of table {digits._q(table)} of sheet {digits._q(sheet)} of document {digits._q(name)} to {digits._q(new_table)}\n'
                        f'set name of sheet {digits._q(sheet)} of document {digits._q(name)} to {digits._q(new_sheet)}\nend tell')
            digits.save_document({'document':name})
        actual = digits.read_table({'document': name, 'include_formulas': True})
        total = actual['rows'][-1][1]
        if abs(total - sum(costs)) > 1e-10 or not actual['formulas'][-1][1]:
            raise ValueError('Numbers formula did not reconcile')
        scope = {'path': str(out), 'document': name,
                 'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}
        prompt = (f'请在本机 Numbers 中审核工作簿 {out} 的费用账本。'
                  '检查数据行的费用合计与 TOTAL 行是否一致，并确认 TOTAL 由公式计算。'
                  '可自行选择工具及调用顺序，允许直接或批量读取整表；不要修改工作簿。'
                  '费用是此前实验按 usage 估算的美元值，不是供应商已对账账单。'
                  '最后只输出 JSON：request_count（不含标题和 TOTAL）、total_usd、'
                  'most_expensive_request、total_matches（布尔）、total_is_formula（布尔）。')
        if extra:
            prompt+='为避免混淆同时打开的工作簿，发现名称后请在查询工作表、表格和数据时显式填写适用的 document、sheet、table；仍可自行选择调用顺序与批量读取方式。'
        private(BASE / case / 'scope.json', scope)
        private(BASE / case / 'reference.json', {'request_count': len(costs),
                  'total_usd': sum(costs), 'most_expensive_request': 'request-' + str(costs.index(max(costs))+1),
                  'total_matches': True, 'total_is_formula': True,
                  'source_ledger_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        p = BASE / case / 'prompt.txt'; p.write_text(prompt); p.chmod(0o600)
        private(BASE / case / 'native-verification.json', actual)
        cases[case] = {'role': case.split('_')[0], **scope}
        print(json.dumps({'case': case, 'rows': len(costs), 'native_formula_verified': True}), flush=True)
    private(BASE / 'cases.json', cases)


if __name__ == '__main__':
    main()
