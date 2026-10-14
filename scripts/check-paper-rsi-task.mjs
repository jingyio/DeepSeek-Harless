import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {createRsiTools} from '../scenarios/paper-submission/rsi-server.ts';
const configPath=process.argv[2],config=JSON.parse(readFileSync(configPath,'utf8'));
const result=createRsiTools(config).call('check_report_structure',{});
const v=result.output,passed=['missing_pairs','unexpected_pairs','duplicate_pairs'].every(k=>v[k].length===0)&&
 ['source_mismatch','scope_mismatch','malformed'].every(k=>v[k]===false);
const record={passed,...result,semantic_quality:'not_reviewed'};
writeFileSync(join(dirname(configPath),'structural-validation.json'),JSON.stringify(record,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify(record));if(!passed)process.exit(1);
