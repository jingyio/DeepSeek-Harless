"""Independent PDF geometry and observed-run accounting; no model calls.

Vertical coverage includes image rectangles, not their pixel ink.  This is a
layout diagnostic, never a scientific-quality score or proof of readability.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def union_length(intervals):
    end=None; total=0.0
    for left,right in sorted(intervals):
        if end is None or left>end:
            total+=right-left;end=right
        elif right>end:
            total+=right-end;end=right
    return total


def inspect_pdf(path):
    import fitz
    path=Path(path)
    pages=[]
    with fitz.open(path) as doc:
        for i,page in enumerate(doc):
            top,bottom=44.0,page.rect.height-50.0
            spans=[]; boxes=[]; images=[]; text=page.get_text()
            for block in page.get_text('dict')['blocks']:
                if block['type']==1:
                    images.append(block['bbox']);boxes.append(block['bbox'])
                else:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            if span['text'].strip():
                                spans.append(span);boxes.append(span['bbox'])
            body=[b for b in boxes if b[1]>=top and b[3]<=bottom]
            intervals=[(max(b[1],top),min(b[3],bottom)) for b in body]
            tail=bottom-max((b[3] for b in body),default=top)
            boundary=[list(b) for b in boxes if b[0]<14 or b[1]<14 or b[2]>page.rect.width-14 or b[3]>page.rect.height-14]
            ordered=sorted(intervals);cursor=top;gaps=[]
            for start,stop in ordered:
                if start>cursor:gaps.append(start-cursor)
                cursor=max(cursor,stop)
            gaps.append(max(0,bottom-cursor))
            pages.append({'page':i+1,'characters':len(text.strip()),'images':len(images),
                          'body_vertical_coverage':round(union_length(intervals)/(bottom-top),4),
                          'body_trailing_blank_fraction':round(tail/(bottom-top),4),
                          'largest_vertical_gap_points':round(max(gaps,default=0),2),
                          'boundary_violations':boundary,
                          'minimum_body_font_pt':min((s['size'] for s in spans if s['bbox'][1]>=top and s['bbox'][3]<=bottom),default=None)})
        fulltext='\n'.join(page.get_text() for page in doc)
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'page_count':len(pages),'pages':pages,'text':fulltext,
            'metric_definition':'Body y=44 to page height minus 50pt; union of text spans and image rectangles; not raster white-pixel percentage.',
            'mean_body_vertical_coverage':statistics.mean(p['body_vertical_coverage'] for p in pages),
            'max_nonfinal_trailing_blank_fraction':max((p['body_trailing_blank_fraction'] for p in pages[:-1]),default=0),
            'boundary_pass':not any(p['boundary_violations'] for p in pages)}


def evaluate(experiment):
    experiment=Path(experiment)
    rows=[]
    for directory in sorted((experiment/'runs').iterdir()):
        if not directory.is_dir() or not (directory/'metrics.json').exists():continue
        metrics=read(directory/'metrics.json'); manifest=read(directory/'manifest.json')
        row={'directory':directory.name,'metrics':metrics,'case_id':manifest['case_id'],
             'mode':manifest['mode'],'run_id':manifest['run_id'],
             'input_sha256':manifest.get('input_sha256'),'input_content_digest':manifest.get('input_content_digest'),'prompt_sha256':manifest.get('prompt_sha256'),
             'contracts_digest':manifest.get('contracts_digest'),
             'benchmark_code_sha256':manifest.get('benchmark_code_sha256'),
             'report_candidates':[]}
        audit_path=directory/'motif-audit.jsonl'
        audits=[json.loads(x) for x in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.exists() else []
        verified={a['call_id'] for a in audits if a.get('kind')=='model_request_skipped_verified'}
        event_path=directory/'agent-events.jsonl'
        events=[json.loads(x) for x in event_path.read_text(encoding='utf-8').splitlines()] if event_path.exists() else []
        tools=[];streak=longest=0
        for event in events:
            if event.get('type')!='tool/call':continue
            call=event.get('data',{});auto=call.get('callId') in verified
            streak=streak+1 if auto else 0;longest=max(longest,streak)
            tools.append({'tool':call.get('name'),'call_id':call.get('callId'),'origin':'verified_motif' if auto else 'model_or_unverified'})
        row['observed_tool_sequence']=tools;row['longest_verified_contiguous_bypass']=longest
        seen=set()
        # Inspect actual final report records. Prior failed layout attempts are
        # preserved in the workspace, but never selected as final deliverables.
        for record_path in (directory/'workspace/records').glob('*.json'):
            record=read(record_path)
            if record.get('kind')!='report':continue
            payload=record.get('payload',{})
            candidate=payload.get('path') or payload.get('pdf_path')
            if not candidate:continue
            path=Path(candidate)
            if not path.is_file():
                # Downloaded Linux evidence retains original absolute paths.
                parts=Path(candidate).as_posix().split('/workspace/',1)
                if len(parts)==2:path=directory/'workspace'/parts[1]
            if path.is_file() and path not in seen:
                report=inspect_pdf(path);report['record_id']=record['id'];
                report['record_hash_matches']=payload.get('sha256') in (None,report['sha256'])
                row['report_candidates'].append(report);seen.add(path)
        rows.append(row)
    return {'experiment':experiment.name,'runs':rows,
            'total_upstream_requests':sum(r['metrics'].get('upstream_requests',0) for r in rows),
            'total_peak_estimate_cny':sum(r['metrics'].get('peak_estimate_cny',0) for r in rows),
            'unknown_cost_requests':sum(r['metrics'].get('unknown_cost_requests',0) for r in rows),
            'scope':'Actual run evidence and independent PDF geometry; scientific prose requires separate current-report reading.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path)
    p.add_argument('--pdf',type=Path,nargs='*')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=evaluate(args.experiment) if args.experiment else {'reports':[inspect_pdf(path) for path in args.pdf]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'runs':len(result.get('runs',[]))}))


if __name__=='__main__':main()
