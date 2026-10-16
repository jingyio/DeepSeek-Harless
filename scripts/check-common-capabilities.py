#!/usr/bin/env python3
"""Opt-in real-model acceptance against a private running Web instance.

Outputs belong in ignored .local; this does not replace browser acceptance.
"""
import argparse
import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_check', ROOT / 'scripts/check-web-tasks.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--base', default='http://127.0.0.1:33512')
    parser.add_argument('--scenes', nargs='+', default=['new-scene', 'ppt', 'research-data-analysis', 'paper-proofreading', 'files'])
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--mode', choices=['baseline','shadow','execute'], default='baseline')
    parser.add_argument('--account-session', type=Path, help='Private JSON cookie/origin for an isolated test account')
    parser.add_argument('--reasoning', choices=['off', 'high'], default='off')
    parser.add_argument('--real-model', action='store_true', required=True)
    args = parser.parse_args()
    opener = web.client()
    if args.account_session:
        auth=json.loads(args.account_session.read_text())
        opener.addheaders=[('Cookie',auth['cookie']),('Origin',auth['origin'])]
    else:
        opener.open((args.run / 'access-url.txt').read_text().strip()).close()
    if args.account_session:
        for _ in range(120):
            status,value=web.request(opener,args.base,'/api/workspace/ready')
            if status==200:break
            if status not in (202,503):raise RuntimeError('isolated account workspace failed to start')
            time.sleep(.5)
        else:raise RuntimeError('isolated account workspace startup timeout')
    records = []
    for scene in args.scenes:
        started = time.monotonic()
        prompt = ('这是通用能力验收，不需要专业报告或附件。请实际执行以下步骤：'
                  '1. web_search 搜索 Python json 官方文档，选择官方来源。'
                  '2. web_fetch 阅读 https://docs.python.org/3/library/json.html，说明 dumps 和 loads 的区别并引用直接链接。'
                  '3. 用 bash 运行 Python，对 [3,5,8,13] 计算总和与均值，以 sum、mean 两个数值字段保存 /work/outputs/capability-result.json。'
                  '4. 再用 bash 的 run_in_background 启动一个延迟 2 秒输出 BACKGROUND_OK 的命令，'
                  '使用 job_list 和 job_output 取得它的真实结果。'
                  '5. 再启动一个延迟 30 秒的后台命令，立即用 job_kill 取消，并核对已停止。'
                  '最终用中文简短报告计算值、网页来源和后台输出。工具失败须如实说明。')
        draft = web.api(opener, args.base, {'action':'preview','request':{'instruction': prompt, 'capability_profile': scene,
            'mode': args.mode, 'model': args.model, 'reasoning_effort': args.reasoning}})
        web.submit(opener, args.base, draft)
        row = web.wait_task(opener, args.base, draft['task_id'], seconds=600)
        directory = args.run / 'tasks' / draft['task_id']
        config = json.loads((directory / 'effective-config.json').read_text())
        events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines() if line]
        calls = [e.get('data', {}).get('name') for e in events if e.get('type') == 'tool/call']
        expected = {'web_search', 'web_fetch', 'bash', 'job_list', 'job_output', 'job_kill'}
        errors = [e for e in events if e.get('type') == 'tool/result' and
                  any(p.get('isError') for p in e.get('data', {}).get('message', {}).get('content', []))]
        result = args.run / 'sessions' / draft['session_id'] / 'work/outputs/code/capability-result.json'
        record = {'scene': scene, 'mode': args.mode, 'model': args.model, 'reasoning': args.reasoning, 'task_id': draft['task_id'],
                  'session_id': draft['session_id'], 'status': row['status'], 'tools': calls, 'tool_errors': len(errors),
                  'all_tools_called': expected <= set(calls), 'file_exists': result.is_file(),
                  'file_value': json.loads(result.read_text()) if result.is_file() else None,
                  'elapsed_seconds': round(time.monotonic()-started, 2), 'stats': row['stats']}
        record['correct_calculation'] = record['file_value'] == {'sum':29,'mean':7.25}
        results = [e for e in events if e.get('type') == 'tool/result']
        output_calls = {e['data']['callId'] for e in events if e.get('type')=='tool/call' and e['data']['name']=='job_output'}
        output_parts = [p for e in results for p in e.get('data',{}).get('message',{}).get('content',[])
                        if p.get('toolCallId') in output_calls and not p.get('isError')]
        record['background_verified'] = 'BACKGROUND_OK' in json.dumps(output_parts)
        result_text='\n'.join(c.get('text','') for e in results for p in e.get('data',{}).get('message',{}).get('content',[])
                              if not p.get('isError') for c in p.get('content',[]) if c.get('type')=='text')
        record['cancellation_verified'] = 'killed' in result_text or 'cancelled' in result_text
        record['official_page_read'] = 'Fetched https://docs.python.org/3/library/json.html (HTTP 200)' in result_text
        records.append(record)
        target = args.run / ('capability-acceptance-' + args.model + '-' + args.reasoning + '-' + args.mode + '.json')
        target.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(json.dumps(record, ensure_ascii=False), flush=True)
    if not all(r['all_tools_called'] and r['correct_calculation'] and r['background_verified'] and r['cancellation_verified']
               and r['official_page_read'] and not r['tool_errors'] for r in records):
        raise SystemExit('Capability acceptance failed; inspect private task events.')


if __name__ == '__main__':
    main()
