"""将已训练产物整理为可分发运行包；不训练、不生成新的模体或科研判断。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ppt', type=Path, required=True)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--paper', type=Path, required=True)
    p.add_argument('--paper-audit', type=Path, required=True)
    args = p.parse_args()
    out = ROOT / 'motif-libraries'
    originals = {}
    for name in ['library.json', 'online-manifest.json', 'tool-schemas.json', 'task.json', 'certification.json']:
        source = args.ppt / name
        destination = out / 'ppt' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha(destination) != sha(source):
            raise ValueError('existing PPT artifact differs: ' + name)
        shutil.copyfile(source, destination)
        originals[name] = sha(source)
    # The full data library contains synthetic case IDs/hashes and receipt edges,
    # not raw HTTP logs, API headers, user CSV values, or manuscripts.
    source = json.loads(args.data.read_text(encoding='utf-8'))
    if source.get('kind') != 'benchmark_workspace_receipt_motifs' or len(source['artifacts']) != 10:
        raise ValueError('unexpected existing V3.1 library')
    (out / 'data').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.data, out / 'data/library.json')
    paper = json.loads(args.paper.read_text(encoding='utf-8'))
    if paper.get('kind') != 'trace_rsi_batch_continuation_shadow' or paper['execution_policy'] != 'shadow_only':
        raise ValueError('expected original paper Shadow library')
    motifs = [{key: value for key, value in row.items() if key != 'witnesses'} for row in paper['motifs']]
    # Keep the learned anchors/batches exactly. Publish evidence hashes/counts,
    # never the private request bodies, source paths or session receipt values.
    portable = {'schema_version': 1, 'kind': 'paper_batch_shadow_v1', 'execution_policy': 'shadow_only',
        'original_file_sha256': sha(args.paper), 'original_manifest_digest': paper['manifest_digest'],
        'tools': paper['tools'], 'motifs': motifs, 'scope': paper['scope'], 'limitations': paper['limitations'],
        'witness_sha256': hashlib.sha256(json.dumps([row['witnesses'] for row in paper['motifs']], sort_keys=True).encode()).hexdigest()}
    save(out / 'paper/library.json', portable)
    frozen = json.loads(args.paper_audit.read_text(encoding='utf-8'))
    save(out / 'paper/audit-program.json', frozen['candidate'])
    # An existing public generated program, unchanged; permissions remain in
    # report_patch_protocol.ts and writes apply only to private task copies.
    shutil.copyfile(ROOT / 'examples/rsi-tools/report-patch-v1/candidate.generated.json', out / 'paper/patch-program.json')
    entries = [('ppt', 'ppt', 'ppt_read_v1', 'execute', originals['library.json']),
               ('data', 'research-data-analysis', 'data_receipts_v3', 'execute', sha(args.data)),
               ('paper', 'paper-proofreading', 'paper_shadow_v1', 'shadow', sha(args.paper))]
    for folder, scene, kind, mode, origin in entries:
        base = out / folder
        files = {f.name: sha(f) for f in base.iterdir() if f.is_file() and f.name != 'entry.json'}
        save(base / 'entry.json', {'schema_version': 1, 'scene': scene, 'runtime_kind': kind,
            'mode': mode, 'origin_sha256': origin, 'files': files, 'new_training': False,
            'scientific_quality_reviewed': False})
    save(out / 'catalog.json', {'schema_version': 1, 'scenes': {scene: folder for folder, scene, *_ in entries},
        'notice': '复用历史库，功能兼容检查不构成科研质量或节省效果认证。'})
    print(json.dumps({'scenes': 3, 'new_training': False, 'directory': 'motif-libraries'}))

if __name__ == '__main__':
    main()
