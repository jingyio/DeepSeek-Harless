/** Free post-run diagnostic; never used as a training tool-call witness. */
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {createTraceRsiTaskTools} from '../scenarios/paper-submission/trace-rsi-task-server.ts';
const config=JSON.parse(readFileSync(process.argv[2],'utf8'));
const tools=createTraceRsiTaskTools(config), state=tools.call('read_task_state',{});
const checked=tools.call(tools.definitions[2].name,{input_id:state.input_id});
const o=checked.output;
const passed=o.keys_match_query_items===true&&['missing','extra','arxiv_id_mismatches'].every(k=>Array.isArray(o[k])&&o[k].length===0);
writeFileSync(join(dirname(process.argv[2]),'generated-check.json'),JSON.stringify({passed,...checked,diagnostic:true},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({passed,diagnostic:true}));
