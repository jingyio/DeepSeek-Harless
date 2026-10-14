"""Task acceptance from files and actual observations, not model self-evaluation."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from collections import defaultdict
from common import digest,snapshot

def verify(spec, report, output, events):
    initial={k:v for k,v in spec['initial_snapshot'].items() if k!='.experiment-copy'}
    final={k:v for k,v in snapshot(spec['workspace']).items() if k!='.experiment-copy'}
    errors=[]; family=spec['family']; expected=dict(initial)
    read_paths=[]; statuses={}
    for p in (Path(output)/'reads').glob('*.json'):
        row=json.loads(p.read_text()); read_paths.append(row['path']); statuses[row['path']]=row['status']
    inbox=sorted(n for n in initial if n.startswith('inbox/'))
    if family in ('inventory','index'):
        if set(read_paths)!=set(initial): errors.append('not every file was inspected')
        if statuses.get('bad/broken.docx')!='unreadable' or statuses.get('bad/disguised.pdf')!='unreadable':
            errors.append('corrupt file diagnostics missing')
        if statuses.get('inbox/poster.png')!='metadata_only': errors.append('image metadata/OCR boundary missing')
    if family=='index':
        p=Path(output)/'index.json'
        if not p.is_file() or {r['path'] for r in json.loads(p.read_text())['entries']}!=set(initial):
            errors.append('incomplete index coverage')
    if family=='attribute_search':
        targets={n for n in initial if Path(n).suffix in ('.docx','.xlsx')}
        if not targets<=set(read_paths): errors.append('Word/Excel inspection incomplete')
    if family=='content_search':
        required={'inbox/brief.docx','inbox/minutes.txt','inbox/notes.md'}
        selected=set(report.get('file_ids',[])) if report else set()
        paths={('file:local:'+digest({'path':n,'sha':s})[:24]):n for n,s in final.items()}
        chosen={paths[fid] for fid in selected if fid in paths}
        if not required<=chosen or 'inbox/invoice.txt' in chosen: errors.append('search known positive/negative fixtures differ')
        if not required<=set(read_paths): errors.append('semantic search did not read required content')
    if family=='rule_classify':
        for n in inbox:
            expected[f'organized/{Path(n).suffix[1:]}/{Path(n).name}']=expected.pop(n)
    if family=='content_classify':
        for name,category in [('brief.docx','research'),('minutes.txt','research'),('notes.md','research'),('invoice.txt','administration')]:
            n='inbox/'+name; expected[f'categories/{category}/{name}']=expected.pop(n)
        if not {'inbox/'+n for n in ('brief.docx','minutes.txt','notes.md','invoice.txt')}<=set(read_paths):
            errors.append('classification lacks actual content reads')
    if family=='rename':
        for i,n in enumerate(inbox,1):
            ext=Path(n).suffix[1:]; expected[f'normalized/{ext}/item_{i:02d}.{ext}']=expected.pop(n)
    if family=='deduplicate':
        groups=defaultdict(list)
        for n,s in initial.items():groups[s].append(n)
        for names in groups.values():
            for n in sorted(names)[1:]:expected['quarantine/'+n]=expected.pop(n)
    if family=='conflict':
        for side in ('left','right'):expected[f'resolved/brief_{side}.txt']=initial[f'{side}/brief.txt']
        if not {'left/brief.txt','right/brief.txt'}<=set(read_paths): errors.append('conflict contents not read')
    if family=='convert':
        for n in ('converted/brief.txt','converted/ledger.csv','converted/poster.jpg'):
            if n not in final: errors.append('conversion missing: '+n)
            else: expected[n]=final[n]
        root=Path(spec['workspace'])
        if (root/'converted/brief.txt').is_file() and 'research project' not in (root/'converted/brief.txt').read_text():
            errors.append('Word conversion lost content')
        if (root/'converted/ledger.csv').is_file():
            rows=list(csv.reader((root/'converted/ledger.csv').open()))
            if not rows or rows[0][:2]!=['Item','Category'] or len(rows)<4: errors.append('spreadsheet CSV content invalid')
        if (root/'converted/poster.jpg').is_file():
            from PIL import Image
            try:
                with Image.open(root/'converted/poster.jpg') as im:
                    if im.format!='JPEG': errors.append('image conversion is not JPEG')
            except OSError: errors.append('image conversion cannot decode')
    if family=='incremental':
        old=spec['previous_snapshot']; changed={n for n in initial if n not in old or initial[n]!=old[n]}
        if set(read_paths)!=changed: errors.append('incremental read set differs from changed files')
        p=Path(output)/'index.json'
        if not p.is_file() or {r['path'] for r in json.loads(p.read_text())['entries']}!=changed:
            errors.append('incremental index differs from changed files')
    if family=='archive_restore':
        journals=[json.loads(p.read_text()) for p in (Path(output)/'journals').glob('*.json')]
        if not any(j.get('status')=='restored_verified' and any(a['op']=='archive' for a in j['actions']) for j in journals):
            errors.append('archive and verified restoration absent')
    if final!=expected: errors.append('final directory differs from task postconditions')
    if not report: errors.append('no actual submit_report receipt')
    # Content selection is independently checked for generated anchors; real PDF semantics are unreviewed.
    return {'task_id':spec['task_id'],'passed':not errors,'errors':errors,'read_paths':read_paths,
            'final_snapshot_sha256':digest(final),'real_pdf_semantic_quality':'not_evaluated',
            'generated_fixture_postconditions_checked':True}
