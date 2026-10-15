/** Preserve the certified legacy task host while exposing GeneLoop scenes. */
import {readFileSync} from 'node:fs';
import * as legacy from './dsh_web_tasks_legacy.ts';
import * as geneloop from './dsh_geneloop_tasks.ts';
export const name='sss-web-tasks';
export const inject=geneloop.inject;
export function apply(ctx:any){
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
 return Array.isArray(policy.scenes)?geneloop.apply(ctx):legacy.apply(ctx);
}
