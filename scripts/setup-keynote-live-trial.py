#!/usr/bin/env python3
"""Create experiment-owned Keynote decks for a live presenter-note check."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'.local/benchmarks/keynote-live-v1'
spec=importlib.util.spec_from_file_location('digits',ROOT/'.local/numbers-digits-upstream/server/digits_server.py')
rpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(rpc)

def run(script):
    return rpc._run('tell application "Keynote"\n'+script+'\nend tell')

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)

def main():
    cases={
      'train_a':('Results Alpha',120,120,'SRC-A1'),
      'train_b':('Milestone Beta',135,140,'SRC-B2'),
      'validate':('Delivery Gamma',210,210,'SRC-C3'),
      'test_a':('Budget Delta',320,310,'SRC-D4'),
      'test_b':('Forecast Epsilon',440,440,'SRC-E5'),
      'test_c':('Costs Zeta',590,610,'SRC-F6'),
    }
    extra='--extra-positions' in sys.argv
    if extra:
        cases={
          'train_position':('Schedule Eta',175,175,'SRC-G7',3),
          'test_d':('Budget Theta',275,260,'SRC-H8',1),
          'test_e':('Review Iota',380,380,'SRC-I9',3),
          'test_f':('Update Kappa',505,515,'SRC-J10',2),
        }
    scopes=json.loads((BASE/'cases.json').read_text()) if extra else {}
    for case,case_data in cases.items():
        title,claim,note,source=case_data[:4]
        target_index=case_data[4] if len(case_data)>4 else 2
        path=(BASE/'decks'/f'{case}.key').resolve()
        if path.exists():raise ValueError('Preserving existing Keynote deck: '+str(path))
        path.parent.mkdir(parents=True,exist_ok=True)
        # Each deck has three slides; only the task-named slide should be read.
        script='set d to make new document with properties {document theme:theme "基本（白色）"}\n'
        for index in range(1,4):
            script+=('set s to slide 1 of d\n' if index==1
                     else 'set s to make new slide at end of slides of d\n')
            slide_title=title if index==target_index else ('Overview' if index==1 else 'Appendix')
            body=('Approved cap: $'+str(claim) if index==target_index
                  else 'Internal project review')
            script+='set title showing of s to true\nset body showing of s to true\n'
            script+='set object text of default title item of s to '+rpc._q(slide_title)+'\n'
            script+='set object text of default body item of s to '+rpc._q(body)+'\n'
            if index==target_index:
                script+='set presenter notes of s to '+rpc._q('Source '+source+' confirms approved cap: $'+str(note))+'\n'
        script+='save d in POSIX file '+rpc._q(str(path))+'\nreturn name of d'
        document=run(script)
        actual=run('''set s to slide '''+str(target_index)+' of document '+rpc._q(document)+'''
return (object text of default title item of s as text) & character id 31 & (object text of default body item of s as text) & character id 31 & (presenter notes of s as text)''').split(chr(31))
        if actual != [title,'Approved cap: $'+str(claim),'Source '+source+' confirms approved cap: $'+str(note)]:
            raise ValueError('Keynote native read differs from created slide')
        scope={'path':str(path),'document':document,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        save(BASE/case/'scope.json',scope)
        save(BASE/case/'reference.json',{'slide_title':title,'slide_number':target_index,'claim_usd':claim,
             'note_usd':note,'consistent':claim==note,'source_code':source})
        save(BASE/case/'native-verification.json',{'title':actual[0],'body':actual[1],'notes':actual[2]})
        prompt=(f'请用 Keynote 审核演示文稿 {path} 中标题恰好为「{title}」的幻灯片。'
                '核对正文中的批准金额与演讲者备注中的来源金额是否一致，记录备注的来源编号。'
                '请先打开文稿并查找该标题，再读取这张幻灯片；不要修改文稿。'
                '只输出 JSON：slide_title、claim_usd、note_usd、consistent（布尔）、source_code。')
        p=BASE/case/'prompt.txt';p.write_text(prompt);p.chmod(0o600)
        scopes[case]=scope
        print(json.dumps({'case':case,'native_read_verified':True,'sha256':scope['sha256']}),flush=True)
    save(BASE/'cases.json',scopes)

if __name__=='__main__':main()
