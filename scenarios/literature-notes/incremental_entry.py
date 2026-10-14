"""Guarded affected-PDF frontier; update-plan objects supply runtime parameters."""
import hashlib
import json
from pathlib import Path
from pdf_tools import ROOT, digest
from pdf_dependencies import private_file
from inventory_entry import entry_task as inventory_task, HERE, PREPARE

SOURCE = 'mcp__literature_pdf__read_update_plan'


def execution_version():
    return digest({n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in
        ['pdf_tools.py', 'pdf_layout.py', 'pdf_read_plan.py', 'pdf-contracts.json',
         'pdf_incremental_tools.py', 'pdf_dependencies.py', 'pdf-incremental-policy.ts',
         'incremental_entry.py', 'pdf-incremental-contracts.json']})


def entry_task(scene, task_id):
    plan = scene.read_update_plan()
    if not plan['work']:
        raise ValueError('empty work is not a certified incremental frontier')
    task = inventory_task(scene, task_id)
    ids = [r['paper_id'] for r in plan['work']]
    task.update(execution_version_sha256=execution_version(), target_ids=ids,
        target_ids_sha256=digest(ids), inventory_papers=[scene.rows[pid] for pid in ids],
        target_versions={pid: scene.document_version(pid) for pid in ids},
        source_result_sha256=digest(plan), plan_sha256=plan['plan_sha256'])
    task['inventory_sha256'] = digest(task['inventory_papers'])
    return task


def private_policy(path):
    value = json.loads(private_file(path).read_text())
    if (value.get('format') != 'sss-entry-incremental-v1'
            or value.get('execution_version_sha256') != execution_version()
            or value.get('policy_digest') != digest({k: v for k, v in value.items() if k != 'policy_digest'})):
        raise ValueError('incremental policy or dependency reader changed; independently recertify')
    return value
