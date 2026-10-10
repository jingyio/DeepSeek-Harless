"""Zero-API real statistics receipts plus unchanged-plugin replay, TEST ONLY.

Test decisions and an in-memory library fixture are not learned motifs. This
diagnostic invokes actual Python tools, then replays their actual file receipts
through the production interceptor. It does not claim a live DSH/MCP transport.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v31.prepare_experiment import prepare, save
from benchmarks.research_report_agent_v2 import common as c
from benchmarks.research_report_agent_v3 import workflow_tools as w
from benchmarks.research_report_agent_v3.tests.test_workflow_tools import example_analysis


def generate_receipts(output: Path):
    output = output.resolve()
    prepare(output, seed_offset=9000000, experiment_id='v31-offline-diagnostic-NOT-FORMAL')
    scenarios = []
    for case, design in [('v3_train_materials','independent_groups'), ('v3_train_ml','paired'),
                         ('v3_cert_environment','regression')]:
        for allow in (True, False):
            run = output/'diagnostic-workspaces'/(case+('-true' if allow else '-false'))
            with patch.dict(os.environ, {'RRA_DATA_ROOT':str(output/'data'), 'RRA_RUN_ROOT':str(run), 'RRA_CASE':case}):
                plan = example_analysis(design, allow)
                approved = w.approve_analysis(case, plan)
                assert approved['ok'], approved
                calls = [{'name':'approve_analysis','arguments':{'study_id':case,'plan':plan},'output':approved}]
                for tool, param, previous_field in [('run_analysis','plan_id','plan_id'),
                                                    ('verify_analysis','analysis_id','analysis_id'),
                                                    ('build_evidence','verified_id','verified_id')]:
                    arguments = {param:calls[-1]['output'][previous_field]}
                    result = getattr(w,tool)(**arguments)
                    assert result.get('ok') is True, result
                    calls.append({'name':tool,'arguments':arguments,'output':result})
                expected = [['run_analysis'],['verify_analysis'],['build_evidence'],[]] if allow else [[],[],[],[]]
                assert [row['output']['_provenance']['authorized_tools'] for row in calls] == expected
                assert calls[-1]['output']['semantic_handoff_required'] is True
                original = c.get_record(approved['plan_id'])['payload']['semantic_approval']['arguments']['plan']
                assert original['allow_deterministic_continuation'] is allow
                source = c.get_case_dir()
                task = {'workspace':str(c.get_run_dir()),'workspace_id':c.workspace_id(),
                        'study_version':c.study_version(),'csv_sha256':c.sha256_file(source/'data.csv'),
                        'source_files':[{'path':str(source/name),'sha256':c.sha256_file(source/name)}
                                        for name in ('data.csv','study.json','task.txt')]}
                scenarios.append({'case_id':case,'design':design,'allow':allow,'task':task,'calls':calls})
    evidence = {'kind':'TEST_FIXTURE_ONLY_actual_tool_receipts','api_calls':0,
                'mcp_transport_used':False,'actual_statistical_tool_executions':18,
                'scope':'Real tool execution followed by plugin receipt replay. No learned-library or paid-agent evidence.',
                'scenarios':scenarios}
    save(output/'diagnostic-receipts.json',evidence)
    return output/'diagnostic-receipts.json'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--node',default='node')
    p.add_argument('--node-deps-root',type=Path,help='Optional existing checkout with installed Node dependencies; no packages downloaded')
    args=p.parse_args()
    receipt_path=generate_receipts(args.output)
    command=[args.node,str(HERE/'replay_statistics_plugin.mjs'),str(receipt_path)]
    if args.node_deps_root:
        command.append(str(args.node_deps_root.resolve()))
    subprocess.run(command,check=True,cwd=ROOT)
    print(json.dumps({'api_calls':0,'actual_statistical_tool_executions':18,
                      'output':str(args.output.resolve()),'learned_library_created':False}))


if __name__=='__main__':
    main()
