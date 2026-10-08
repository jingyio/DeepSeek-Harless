#!/usr/bin/env python3
"""Scoped Finder metadata reads over experiment-owned delivery folders."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('digits',ROOT/'.local/numbers-digits-upstream/server/digits_server.py')
rpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(rpc)
BASE=ROOT/'.local/benchmarks/finder-live-v1'

def snapshot(folder):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.iterdir()) if p.is_file()}

def main():
    scope=json.loads(Path(os.environ['SSS_FINDER_SCOPE']).read_text())
    folder=Path(scope['path']).resolve(strict=True)
    if not folder.is_relative_to(BASE) or not folder.is_dir():
        raise ValueError('Finder scope outside experiment')
    expected,version=scope['files'],scope['sha256']
    def guard():
        if snapshot(folder)!=expected:
            raise rpc.ToolError('Delivery folder version changed')
    def live(script):return rpc._run('tell application "Finder"\n'+script+'\nend tell')
    target='(POSIX file '+rpc._q(str(folder))+' as alias)'
    def open_folder(args):
        if Path(args['path']).resolve()!=folder:raise rpc.ToolError('Folder outside task scope')
        guard()
        # Finder resolves this actual directory; the document address is its
        # full path so equal folder names in other locations cannot collide.
        live('set f to '+target+'\nreturn name of f')
        guard();return {'folder':str(folder),'source_version':version}
    def list_files(args):
        if args.get('folder')!=str(folder):raise rpc.ToolError('Folder outside task scope')
        guard()
        raw=live('''set f to '''+target+'''
set entries to name of every file of f
set AppleScript's text item delimiters to character id 30
return entries as text''')
        names=[x for x in raw.split(chr(30)) if x]
        project=args['project']
        matches=[n for n in names if n.startswith(project+'-') and n.endswith('.md')]
        guard();return {'folder':str(folder),'names':names,
           'selected_report':matches[0] if len(matches)==1 else None,
           'match_count':len(matches),'source_version':version}
    def file_info(args):
        if args.get('folder')!=str(folder):raise rpc.ToolError('Folder outside task scope')
        name=args['name']
        if name not in expected or '/' in name:raise rpc.ToolError('File outside task scope')
        guard()
        raw=live('''set f to '''+target+'''
set itemRef to file '''+rpc._q(name)+''' of f
return (name of itemRef) & character id 31 & (size of itemRef as text) & character id 31 & (kind of itemRef as text)''')
        actual,size,kind=raw.split(chr(31),2)
        if actual!=name:raise rpc.ToolError('Finder returned a different file')
        guard();return {'name':actual,'size_bytes':int(size),'kind':kind,
                         'source_version':version}
    string=lambda description:{'type':'string','description':description}
    rpc.SERVER_NAME='finder-live'
    rpc.TOOLS={
      'finder_open_folder':('Open and identify a local delivery folder in Finder.',
        rpc._schema({'path':string('Absolute folder path')},['path']),open_folder),
      'finder_list_files':('List file names in Finder and locate one report for a project.',
        rpc._schema({'folder':string('Exact folder path from finder_open_folder'),
                     'project':string('Project code from the request')},['folder','project']),list_files),
      'finder_file_info':('Read Finder file name, size and kind for a selected report.',
        rpc._schema({'folder':string('Exact folder path'),'name':string('Selected report file name')},
                    ['folder','name']),file_info),
    }
    for line in sys.stdin:
        if line.strip():rpc._handle(json.loads(line))

if __name__=='__main__':main()
