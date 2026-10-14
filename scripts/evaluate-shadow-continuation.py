"""Read-only replay of live shadow evidence, not a counterfactual cost benchmark."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import posixpath
from urllib.parse import urlsplit
from urllib.parse import urlencode


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def read_jsonl(path):
    # U+2028/U+2029 are valid JSON string characters, not JSONL boundaries.
    return [json.loads(line) for line in path.read_text(encoding='utf-8').split('\n') if line.strip()]


def matched_call(call, item, tool, work, prototype=None):
    args = call.get('arguments', {})
    if isinstance(args, str): args = json.loads(args)
    if call.get('name') != tool: return False
    if tool == 'read':
        path = args.get('file_path', '')
        target = posixpath.normpath(posixpath.join(work, item['file_path']))
        return (set(args) <= {'file_path', 'offset', 'limit'} and
                posixpath.normpath(posixpath.join(work, path)) == target)
    if tool != 'web_fetch': return False
    if prototype and prototype.get('contract') == 'crossref-search-fetch-v1':
        spec = prototype['arguments']['url']
        url = spec['base'] + '?' + urlencode([(p['name'], item['query'] if p.get('slot') else p['value']) for p in spec['query']])
        return args == {'url': url}
    return args == {'url': 'https://arxiv.org/abs/' + item['id']}


def request_inventory(events, batches, config):
    """Describe uncovered decisions without granting execution or guessing semantics."""
    selected = {(b.get('turn'), b.get('step')): b for b in batches if 'turn' in b}
    rows = []
    for event in events:
        if event['type'] != 'assistant/message': continue
        data = event['data']; content = data['message']['content']
        calls = [b for b in content if b.get('type') == 'tool-call']
        texts = [b.get('text', '') for b in content if b.get('type') == 'text' and b.get('text', '').strip()]
        other = any(b.get('type') not in {'text', 'tool-call'} for b in content)
        pure = bool(calls) and not texts and not other
        batch = selected.get((data['turn'], data['step']))
        names = Counter(c['name'] for c in calls)
        args = [json.loads(c['arguments']) if isinstance(c.get('arguments'), str) else c.get('arguments', {}) for c in calls]
        selection_path = posixpath.join(config['work'], config['binding_path'])
        binding_write = any(c['name'] == 'write' and
                            posixpath.normpath(posixpath.join(config['work'], a.get('file_path', ''))) == selection_path
                            for c, a in zip(calls, args))
        if batch: scope = 'selected_' + batch['request_classification']
        elif binding_write: scope = 'selection_protocol_overhead'
        elif not calls: scope = 'text_or_other_output'
        elif set(names) <= {'read', 'web_fetch'}: scope = 'unbound_collection_needs_intent_and_contract'
        elif 'bash' in names: scope = 'script_or_command_needs_compilation_and_contract'
        else: scope = 'other_or_mixed_tools_needs_review'
        domains = sorted({urlsplit(a.get('url', '')).hostname or '' for c, a in zip(calls, args) if c['name'] == 'web_fetch'})
        usage = data.get('usage') or {}
        # Harness inputTokens excludes separately reported cache reads/writes.
        buckets = [usage.get(k, 0) for k in ['inputTokens', 'cacheReadTokens', 'cacheWriteTokens']]
        prompt_tokens = sum(buckets) if usage and all(isinstance(v, (int, float)) for v in buckets) else None
        rows.append({'turn': data['turn'], 'step': data['step'], 'tool_counts': dict(names),
                     'pure_tool_output': pure, 'has_text': bool(texts), 'scope': scope,
                     'web_domains': domains, 'observed_prompt_tokens': prompt_tokens,
                     'observed_output_tokens': usage.get('outputTokens'),
                     'execution_authorized_by_inventory': False})
    return {'observed_root_responses': len(rows), 'scope_counts': dict(Counter(r['scope'] for r in rows)),
            'pure_tool_output_responses': sum(r['pure_tool_output'] for r in rows),
            'selection_protocol_responses': sum(r['scope'] == 'selection_protocol_overhead' for r in rows),
            'responses': rows, 'interpretation': 'Unbound or script-only output is not a certified skip opportunity.'}


def evaluate(run):
    metrics = json.loads((run / 'metrics.json').read_text())
    config = json.loads((run / 'parameter-config.json').read_text())
    if config['mode'] != 'shadow' or metrics['verified_skips'] or metrics['unverified_bypasses']:
        raise ValueError('requires live shadow with zero actual bypasses')
    library_path = run / 'library-snapshot.json' if (run / 'library-snapshot.json').exists() else run.parents[1] / 'library.json'
    library = json.loads(library_path.read_text())
    tools = {m['motif_id']: m['prototype']['tool'] for m in library['motifs']}
    prototypes = {m['motif_id']: m['prototype'] for m in library['motifs']}
    audit = read_jsonl(run / 'parameter-motif/audit.jsonl')
    batches, active = [], None
    for row in audit:
        if row['kind'] == 'selection_accepted':
            active = {'binding_digest': row['binding_digest'], 'motif_id': row['motif_id'],
                      'item_ids': row['item_ids'], 'results': {}, 'candidate_tools': None}
            batches.append(active)
        elif active and row['kind'] == 'shadow_candidate': active['candidate_tools'] = row['tool_count']
        elif active and row['kind'] == 'shadow_result': active['results'][row['item_id']] = bool(row.get('verified'))
    root_session = config['session_id']
    # These controllers record all sessions; do not mix child agents into the root decision stream.
    raw = read_jsonl(run / 'session-events.jsonl')
    events = [row['event'] for row in raw if row.get('session_id') == root_session]
    writes, results = {}, {}
    for index, event in enumerate(events):
        data = event['data']
        if event['type'] == 'tool/call' and data['name'] == 'write':
            args = data['arguments']; args = json.loads(args) if isinstance(args,str) else args
            if posixpath.normpath(posixpath.join(config['work'], args.get('file_path',''))) == posixpath.join(config['work'],config['binding_path']):
                try: binding = json.loads(args['content'])
                except (KeyError, ValueError): continue
                writes.setdefault(digest(binding), []).append((data['callId'], binding))
        if event['type'] == 'tool/result':
            for block in data.get('message',{}).get('content',[]):
                if block.get('type') == 'tool-result': results[block['toolCallId']] = (index, block.get('isError',False))
    for batch in batches:
        observations = batch['results']; expected = set(batch['item_ids'])
        batch.update(selected_items=len(expected), verified_items=sum(observations.get(i) is True for i in expected),
                     failed_items=sum(observations.get(i) is False for i in expected),
                     unobserved_items=sum(i not in observations for i in expected))
        batch['complete_result_match'] = batch['verified_items'] == batch['selected_items']
        batch['request_classification'] = 'insufficient_evidence'
        for call_id, binding in writes.get(batch['binding_digest'],[]):
            if call_id not in results or results[call_id][1]: continue
            decision = next((event['data'] for event in events[results[call_id][0]+1:]
                             if event['type']=='assistant/message'), None)
            if not decision: continue
            content = decision['message']['content']
            calls = [block for block in content if block.get('type')=='tool-call']
            text = any(block.get('type')=='text' and block.get('text','').strip() for block in content)
            other = any(block.get('type') not in {'text','tool-call'} for block in content)
            items, tool = binding['items'], tools[batch['motif_id']]
            # A selected graph can match while that model request also does something else.
            exact = (len(calls) == len(items) and
                     all(sum(matched_call(c,i,tool,config['work'],prototypes[batch['motif_id']]) for c in calls)==1 for i in items))
            if batch['candidate_tools'] is None: classification = 'no_provider_boundary_candidate'
            elif exact and not text and not other: classification = 'tool_only_match'
            elif exact: classification = 'matching_tools_requires_semantic_review'
            else: classification = 'mixed_or_different_actions'
            batch['request_classification'] = classification
            batch['turn'], batch['step'] = decision['turn'], decision['step']
            usage = decision.get('usage') or {}
            batch['observed_decision_tokens'] = {k: usage.get(k) for k in ['inputTokens','cacheReadTokens','outputTokens']}
            break
    strict = [b for b in batches if b['complete_result_match'] and b['request_classification']=='tool_only_match']
    inventory = request_inventory(events, batches, config)
    return {'evaluation_kind':'historical_replay_of_real_shadow', 'run_status':metrics['status'],
            'actual_model_requests':metrics['actual_requests'], 'actual_skipped_requests':0,
            'actual_skip_savings_usd':0, 'counterfactual_cost_savings_usd':None,
            'selected_batches':len(batches), 'selected_items':sum(b['selected_items'] for b in batches),
            'verified_items':sum(b['verified_items'] for b in batches),
            'complete_batches':sum(b['complete_result_match'] for b in batches),
            'strict_tool_only_opportunities':len({(b['turn'],b['step']) for b in strict}),
            'classification_counts':dict(Counter(b['request_classification'] for b in batches)),
            'semantic_quality':'not_blind_reviewed', 'independent_task_generalization':False,
            'request_inventory':inventory,
            'batches':batches,
            'library_sha256':hashlib.sha256(library_path.read_bytes()).hexdigest(),
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'input_sha256':{name:hashlib.sha256((run/name).read_bytes()).hexdigest() for name in
                           ['manifest.json','metrics.json','session-events.jsonl','parameter-motif/audit.jsonl','parameter-config.json']}}


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists(): raise ValueError('preserve prior evaluation; use a new output version')
    report=evaluate(args.run)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({k:v for k,v in report.items() if k not in {'batches','input_sha256','request_inventory'}},ensure_ascii=False))

if __name__=='__main__': main()
