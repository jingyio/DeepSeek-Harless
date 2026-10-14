"""Reuse the existing incremental work-array IR for catalog metadata packets."""
import json
from pdf_tools import digest
from pdf_dependencies import private_file
from pdf_catalog_tools import HERE, execution_version
SOURCE = 'mcp__literature_catalog__read_catalog_plan'
PREPARE = 'mcp__literature_catalog__read_catalog_packet'


def entry_task(scene, task_id):
    plan = scene.read_catalog_plan(); ids = [r['paper_id'] for r in plan['work']]
    if not ids: raise ValueError('unchanged catalog is ordinary zero-model reuse, not a Motif frontier')
    papers = [scene.rows[pid] for pid in ids]
    return {'schema_version':1, 'task_id':task_id, 'input_version':digest(scene.task),
            'execution_version_sha256':execution_version(), 'inventory_papers':papers,
            'inventory_sha256':digest(papers), 'question':scene.task['question'],
            'target_ids':ids, 'target_ids_sha256':digest(ids),
            'target_versions':{pid:scene.document_version(pid) for pid in ids},
            'parser_profile_sha256':digest(scene.profile), 'source_result_sha256':digest(plan),
            'plan_sha256':plan['plan_sha256']}


def private_policy(path):
    value = json.loads(private_file(path).read_text())
    if (value.get('format') != 'sss-entry-incremental-v1' or value.get('execution_version_sha256') != execution_version()
            or value.get('policy_digest') != digest({k:v for k,v in value.items() if k != 'policy_digest'})
            or value.get('artifact',{}).get('tools') != [SOURCE,PREPARE]):
        raise ValueError('catalog policy/reader changed or different tools; independently recertify')
    return value
