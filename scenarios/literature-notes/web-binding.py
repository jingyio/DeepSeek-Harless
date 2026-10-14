"""Server-owned Web binding preflight/collection; never runs a model."""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_review_tools import ReviewScene
sys.path.insert(0, str(ROOT))
from src.adapters.scenario import prepare_scenario


def prepare(payload):
    request = payload['request']
    content = request['content']
    if len(content) != 1 or content[0]['type'] != 'text':
        raise ValueError('文献任务仅接受研究问题文本；PDF请使用服务端登记目录')
    question = content[0]['text']
    if not 1 <= len(question.strip()) <= 4000:
        raise ValueError('研究问题需要1–4000字符')
    root = Path(payload['papers_dir']).resolve()
    sources = inventory(root)
    references = request['resources']
    if (len(references) > 1 or references and
        (references[0]['resource_id'] != 'pdf:library' or
         references[0].get('version', digest(sources)) != digest(sources))):
        raise ValueError('只能选择当前登记的pdf:library版本；客户端不能传本地路径')
    task = {'schema_version': 1, 'question': question, 'sources': sources}
    directory = Path(payload['output']).resolve() / 'binding'
    if not directory.is_relative_to(ROOT / '.local/web/runs'):
        raise ValueError('binding output must be owned by this Web run')
    save_private(directory / 'task.json', task)
    spec = importlib.util.spec_from_file_location('literature_run_pdf', Path(__file__).with_name('run-pdf.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    save_private(directory / 'input-snapshot.json', {'task': task, 'task_sha256': digest(task),
        'cache_policy': 'reuse', 'runtime': mod.runtime_snapshot(), 'scope': 'web_session_bound'})
    scene_config = json.loads(Path(__file__).with_name('web-scenario.json').read_text())
    scene_config['prompt'] = str(Path(__file__).with_name('web-task.md'))
    scene_config['servers'][0]['env'] = {'SSS_PDF_WEB_TASK': str(directory)}
    save_private(directory / 'scenario.json', scene_config)
    prepared = prepare_scenario(directory / 'scenario.json')
    return {'directory': str(directory), 'task_sha256': digest(task), 'question': question, 'papers': sources['papers'],
            'allowed_tools': prepared['allowed_tools'],
            'rows': prepared['mcp_rows'] + prepared['agent_plugins'],
            'prompt': prepared['prompt'] + '\n当前研究问题（必须与list_pdfs一致）：\n' + question,
            'sources': [{'resource_id': 'pdf:library', 'version': digest(sources), 'sha256': digest(sources)}]}


def check(directory):
    task = json.loads((directory / 'task.json').read_text())
    if inventory(Path(task['sources']['root'])) != task['sources']:
        raise ValueError('PDF来源在预览后已变化；请创建新任务')
    return task


def collect(payload):
    directory = Path(payload['directory']).resolve()
    task = check(directory)
    receipt = json.loads((directory / 'delivery-receipt.json').read_text())
    path = directory / 'evidence.json'
    if path.is_symlink() or Path(receipt['artifact']).resolve() != path or digest(json.loads(path.read_text())) != receipt['artifact_sha256']:
        raise ValueError('delivery artifact hash/location mismatch')
    if receipt['task_sha256'] != digest(task) or receipt['question'] != task['question']:
        raise ValueError('delivery belongs to a different frozen task')
    calls, witnessed = {}, False
    for line in Path(payload['events']).read_text().splitlines():
        e = json.loads(line); data = e.get('data', {})
        if e['type'] == 'tool/call': calls[data['callId']] = data['name']
        if e['type'] == 'tool/result':
            for block in data.get('message', {}).get('content', []):
                if (block.get('type') == 'tool-result' and not block.get('isError') and
                    calls.get(block.get('toolCallId')) == 'mcp__literature_web__deliver_research_notes'):
                    texts = [b['text'] for b in block.get('content', []) if b.get('type') == 'text']
                    if len(texts) == 1:
                        try: witnessed |= json.loads(texts[0]) == receipt
                        except ValueError: pass
    if not witnessed: raise ValueError('no successful native delivery tool receipt')
    # Use the existing exact source/quote replay rather than trust the final answer.
    save_private(directory / 'pdf-input-snapshot.json', json.loads((directory / 'input-snapshot.json').read_text()))
    replay = ReviewScene(directory, directory / 'collection-replay')
    if replay.evidence['task_sha256'] != digest(task): raise ValueError('replay task changed')
    audit = json.loads((directory / 'review-1/claim-review.json').read_text())
    expected = {'claim:' + p['paper_id'] + ':' + f['name'] for p in replay.evidence['draft']['papers'] for f in p['fields']}
    if set(audit['target_claim_ids']) != expected or not replay.evidence.get('synthesis_assessed'):
        raise ValueError('automatic review/final synthesis missing')
    return {'status': receipt['status'], 'question': task['question'], 'task_sha256': digest(task),
        'artifact_sha256': receipt['artifact_sha256'], 'markdown': replay.evidence['markdown'],
        'claim_count': receipt['claim_count'], 'citation_count': receipt['citation_count'],
        'gap_count': receipt['gap_count'], 'gaps': replay.evidence['gaps'],
        'research_quality': 'automatic_model_reviewed_unverified', 'human_review_required': False}


if __name__ == '__main__':
    payload = json.load(sys.stdin)
    action = payload['action']
    if action == 'prepare': result = prepare(payload)
    elif action == 'check': result = {'task_sha256': digest(check(Path(payload['directory'])))}
    elif action == 'collect': result = collect(payload)
    else: raise ValueError('unknown binding action')
    print(json.dumps(result, ensure_ascii=False))
