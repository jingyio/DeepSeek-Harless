"""Web窄桥接：复用冻结双路trial，不新建Agent循环。"""
import json
import sys
from pathlib import Path
from .trial import prepare_trial

def main():
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError('请求过大')
    data = json.loads(raw)
    path = prepare_trial([Path(p) for p in data['inputs']], data['instruction'], data['slides'],
                         budget=data['budget_usd'], max_steps=60, max_output=8000,
                         template=data['template'], operation=data['operation'], allow_output=True)
    print(json.dumps({'trial': str(path)}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
