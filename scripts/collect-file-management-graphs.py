"""Unified observation archive; runtime-produced nodes are never training evidence."""
import importlib.util,json,sys
from pathlib import Path
from collections import defaultdict,Counter
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scenarios/file-management'))
from common import digest,sha,save
spec=importlib.util.spec_from_file_location('fm_graph_observer',root/'scenarios/file-management/learn.py')
learning=importlib.util.module_from_spec(spec);spec.loader.exec_module(learning)
exp=Path(sys.argv[1]).resolve();protocol=json.loads((exp/'protocol.json').read_text())
all_experiments=list(dict.fromkeys([*([Path(protocol['parent'])] if 'parent' in protocol else []),*[Path(p).resolve() for p in sys.argv[2:]],exp]));graphs=[];edge_tasks=defaultdict(set);edge_families=defaultdict(set)
for origin in all_experiments:
    origin_protocol=json.loads((origin/'protocol.json').read_text())
    for case in origin_protocol['tasks']:
        for p in (Path(case['task_dir'])/'attempts').glob('*/outcome.json'):
            out=json.loads(p.read_text());run=Path(out['run']['output_dir']);events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            task=json.loads((Path(case['task_dir'])/'input.json').read_text())
            condition=digest({k:({n:s for n,s in task.get(k,{}).items() if n!='.experiment-copy'} if k in ('initial_snapshot','previous_snapshot') else task.get(k))
                              for k in ('family','variant','objective','rules','allowed_operations','initial_snapshot','previous_snapshot')})
            assert sha(run/'agent-events.jsonl')==out['events_sha256']
            graph=learning.graph(events,run.name,case['family'])
            graph.update(experiment=origin.name,task_id=out['task_id'],task_accepted=out['acceptance']['passed'],
                         arm=out.get('arm','H'),successful_normal_observation=out.get('arm','H')=='H' and out['acceptance']['passed'],
                         current_evaluation_used_for_retraining=False)
            by_id={n['call_id']:n for n in graph['nodes']}
            for node in graph['nodes']:
                node['runtime_generated']=node['call_id'].startswith('sss-')
                node['producer']=('handwritten_script' if graph['arm']=='S' else 'certified_runtime') if node['runtime_generated'] else 'normal_harness'
                if node['tool'].removeprefix('mcp__file_management__') in ('select_files','collect_reads','preview_actions','authorize_plan'):node['effectful']=False
            for edge in graph['edges']:
                if edge['kind']!='observed_parameter':continue
                a,b=by_id[edge['from']],by_id[edge['to']]
                if a['runtime_generated'] or b['runtime_generated']:continue
                if not graph['successful_normal_observation']:continue
                key=(a['tool'],edge['field'],b['tool'],edge['argument'])
                edge_tasks[key].add(condition);edge_families[key].add(case['family'])
            graphs.append(graph)
candidates=[{'from_tool':a,'from_field':field,'to_tool':b,'to_param':param,
             'distinct_successful_normal_task_conditions':len(tasks),'families':sorted(edge_families[(a,field,b,param)]),
             'effectful':any(n['tool'] in (a,b) and n['effectful'] for g in graphs for n in g['nodes']),
             'status':'observed_candidate_only','execution_permission':False}
            for (a,field,b,param),tasks in edge_tasks.items() if len(tasks)>=2]
body={'experiments':[p.name for p in all_experiments],'graphs':len(graphs),
      'nodes':sum(len(g['nodes']) for g in graphs),'parameter_candidates':candidates,
      'normal_harness_graphs':sum(g['arm']=='H' for g in graphs),'motif_intervention_graphs':sum(g['arm'] in ('M','L1','L2') for g in graphs),
      'accepted_normal_graphs':sum(g['successful_normal_observation'] for g in graphs),
      'handwritten_script_graphs':sum(g['arm']=='S' for g in graphs),
      'runtime_nodes_excluded_from_learning':sum(n['runtime_generated'] for g in graphs for n in g['nodes']),
      'effectful_graphs_certified':0,'current_library_unchanged':True,
      'status_conditions':'observed statuses do not prove a conditional program',
      'observer_limitations':'legacy source/result scalar edges only; new array/capability proofs remain in separate certified artifacts',
      'certification_scope':'this observation collector certifies no graph; new plan certificate is separate',
      'training_data_modified':False}
save(exp/'unified-observed-graphs.json',graphs);save(exp/'unified-graph-summary.json',body)
print(json.dumps(body,ensure_ascii=False))
