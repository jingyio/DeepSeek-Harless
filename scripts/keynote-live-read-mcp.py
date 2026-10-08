#!/usr/bin/env python3
"""Scoped read-only MCP access to live Keynote slides through AppleScript."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('digits', ROOT/'.local/numbers-digits-upstream/server/digits_server.py')
rpc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rpc)
SCOPE_ROOT = ROOT/'.local/benchmarks/keynote-live-v1'
RS, US = chr(30), chr(31)


def live(script):
    return rpc._run('tell application "Keynote"\n' + script + '\nend tell')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    scope = json.loads(Path(os.environ['SSS_KEYNOTE_SCOPE']).read_text())
    path = Path(scope['path']).resolve(strict=True)
    if not path.is_relative_to(SCOPE_ROOT):
        raise ValueError('Keynote scope must be an experiment-owned deck')
    document, expected = scope['document'], scope['sha256']

    def guard():
        if sha(path) != expected:
            raise rpc.ToolError('Keynote file revision changed')
        modified = live('return modified of document ' + rpc._q(document))
        if modified != 'false':
            raise rpc.ToolError('Keynote document has unsaved changes')

    def open_document(args):
        if Path(args['path']).resolve() != path:
            raise rpc.ToolError('Deck outside task scope')
        if sha(path) != expected:
            raise rpc.ToolError('Keynote file revision changed')
        result = live('set d to open (POSIX file ' + rpc._q(str(path)) + ')\nreturn name of d')
        if result != document:
            raise rpc.ToolError('Keynote document identity changed')
        guard()
        return {'document':result,'source_version':expected}

    def list_slides(args):
        if args.get('document', document) != document:
            raise rpc.ToolError('Deck outside task scope')
        guard()
        result = live('''set acc to ""
repeat with s in slides of document '''+rpc._q(document)+'''
  set t to object text of default title item of s as text
  if acc is not "" then set acc to acc & character id 30
  set acc to acc & (slide number of s as text) & character id 31 & t
end repeat
return acc''')
        slides = []
        for row in result.split(RS):
            if row:
                number, title = row.split(US,1)
                slides.append({'slide_number':int(number),'title':title})
        selected = [x for x in slides if x['title'] == args.get('title')]
        guard()
        return {'document':document,'slides':slides,
                'selected_slide':str(selected[0]['slide_number']) if len(selected)==1 else None,
                'source_version':expected}

    def read_slide(args):
        if args.get('document', document) != document:
            raise rpc.ToolError('Deck outside task scope')
        try: number = int(args['slide_number'])
        except (ValueError,TypeError): raise rpc.ToolError('Invalid slide number')
        if not 1 <= number <= 100:
            raise rpc.ToolError('Slide number outside bounded range')
        guard()
        result = live('''set s to slide '''+str(number)+' of document '+rpc._q(document)+'''
return (object text of default title item of s as text) & character id 31 & (object text of default body item of s as text) & character id 31 & (presenter notes of s as text)''')
        title, body, notes = result.split(US,2)
        guard()
        return {'title':title,'body':body,'notes':notes,'slide_number':str(number),
                'source_version':expected}

    string = lambda description: {'type':'string','description':description}
    rpc.SERVER_NAME = 'keynote-live'
    rpc.TOOLS = {
      'keynote_open_document': ('Open the selected deck in Keynote and return its exact document name, including .key.',
        {'type':'object','properties':{'path':string('Absolute path to a .key deck')},'required':['path']},open_document),
      'keynote_list_slides': ('List live slide titles and locate one exact title. Use the exact document value returned by keynote_open_document.',
        {'type':'object','properties':{'document':string('Keynote document name'),
          'title':string('Exact slide title to locate')},'required':['document','title']},list_slides),
      'keynote_read_slide': ('Read visible text and presenter notes from a slide in Keynote. Use the exact document value returned by keynote_open_document.',
        {'type':'object','properties':{'document':string('Keynote document name'),
          'slide_number':string('Selected slide number')},'required':['document','slide_number']},read_slide),
    }
    for line in sys.stdin:
        if line.strip(): rpc._handle(json.loads(line))


if __name__ == '__main__':
    main()
