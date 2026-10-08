#!/usr/bin/env python3
"""Create local report handoff folders for Finder read-only audits."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'.local/benchmarks/finder-live-v1'

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)

def main():
    cases={
      'train_a':('ALPHA',True,True),
      'train_b':('BETA',False,True),
      'validate':('GAMMA',True,False),
      'test_a':('DELTA',True,True),
      'test_b':('EPSILON',False,False),
      'test_c':('ZETA',True,False),
    }
    scopes={}
    for case,(project,nonempty,manifest) in cases.items():
        folder=BASE/'folders'/case
        if folder.exists():raise ValueError('Preserving existing Finder folder: '+str(folder))
        folder.mkdir(parents=True)
        report=folder/f'{project}-decision-report.md'
        report.write_text(f'# {project} decision report\nEvidence reviewed.\n' if nonempty else '')
        (folder/'README.txt').write_text('Delivery folder; review report and manifest.\n')
        (folder/'OTHER-notes.md').write_text('Unrelated project notes.\n')
        if manifest:(folder/f'{project}-decision-report.json').write_text(
            json.dumps({'project':project,'report':report.name},indent=2)+'\n')
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        version=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        scope={'path':str(folder.resolve()),'files':files,'sha256':version}
        save(BASE/case/'scope.json',scope)
        save(BASE/case/'reference.json',{'project':project,'report_name':report.name,
             'size_bytes':report.stat().st_size,'nonempty':nonempty,'has_manifest':manifest})
        prompt=(f'请在本机 Finder 中检查交付文件夹 {folder.resolve()} 的 {project} 项目报告。'
                '找到该项目唯一的 Markdown 报告，核对它是否非空，以及同名 JSON 清单是否存在。'
                '不要修改文件。只输出 JSON：project、report_name、size_bytes、nonempty（布尔）、has_manifest（布尔）。')
        p=BASE/case/'prompt.txt';p.write_text(prompt);p.chmod(0o600)
        scopes[case]=scope
        print(json.dumps({'case':case,'files':len(files),'version':version}),flush=True)
    save(BASE/'cases.json',scopes)

if __name__=='__main__':main()
