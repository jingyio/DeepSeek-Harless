/** Real RSI generation: only the bounded program submission tool is exposed. */
import {readFileSync} from 'node:fs';
export const name='sss-patch-rsi-generation';
export const inject=['agents'];
export function apply(ctx:any):void {
  const config=JSON.parse(readFileSync(process.env.SSS_PATCH_RSI_GENERATION!,'utf8'));
  ctx.on('agent/created',({agent}:any)=>{
    if(agent.session.id===config.session_id)agent.ctx.tools.restrict({allow:['mcp__paper_patch_learning__submit_generated_program']});
  });
}
