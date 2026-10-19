"""Free MCP introspection: frontend preserves the certified SDK parameter limits."""
import asyncio,json,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import TOOLS
from common import save
from src.adapters.file_scenario import prepare_scenario
from src.adapters.continuous_rsi import actual_schemas
from src.motif_core.offline.operation_graph import catalog

def test_native_wrapper_preserves_exact_sdk_catalog_and_array_constraints():
    home=ROOT/'.local/management-schema-tests'/uuid4().hex;work=home/'work';work.mkdir(parents=True)
    (work/'sample.txt').write_text('free schema material')
    prepare(home/'task',work,task_id=uuid4().hex,objective='inspect schema',owner='schema-test',workspace_id='schema-test')
    sdk=prepare_scenario(home/'task/scenario.json');value=json.loads((home/'task/scenario.json').read_text())
    value['servers'][0].update(args=['${PROJECT_ROOT}/scenarios/file-management/management_native.py'],env={'FM_WEB_WORKSPACE':str(home/'native')})
    save(home/'native.json',value);native=prepare_scenario(home/'native.json')
    async def inspect():
        a=await actual_schemas(sdk,home/'task/input.json',home/'probe-sdk','management_v3',{'FM_TASK_FILE':str(home/'task/input.json'),'FM_OUTPUT':str(home/'delivery'),'FM_JOB_FILE':str(home/'job.json')})
        b=await actual_schemas(native,home/'task/input.json',home/'probe-native','management_v3',{})
        assert len(a)==len(b)==len(TOOLS) and catalog(a)==catalog(b)
        for name,param in [('pin_files','file_ids'),('read_files','source_ids')]:
            tool=next(t for t in b if t['name']==name)
            field=tool.get('inputSchema',tool.get('input_schema'))['properties'][param]
            assert field['minItems']==1 and field['maxItems']==40
    asyncio.run(inspect())
