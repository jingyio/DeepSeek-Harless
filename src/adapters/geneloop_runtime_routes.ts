/** Keep public mode controls on their admitted runtime, across HTTP and WS RPC. */
import {symbols} from '@deepseek-ai/cordis';
import {RemoteError} from '@deepseek-ai/dsh-typert-protocol';
const fileModes=new WeakMap<object,(session:string)=>boolean>();
const host=(ctx:any)=>ctx.sessionController[symbols.original]??ctx.sessionController;
export function registerIndependentFileMode(ctx:any,selected:(session:string)=>boolean){
 const key=host(ctx);fileModes.set(key,selected);
 return ()=>{if(fileModes.get(key)===selected)fileModes.delete(key);};
}
export function independentFileMode(ctx:any,session:string){return fileModes.get(host(ctx))?.(session)??false;}
export function guardNativeModeCommand(ctx:any,handler:(invocation:any)=>any){
 return (invocation:any)=>independentFileMode(ctx,invocation.agent.session.id)
  ?{kind:'error',text:'当前文件管理由独立 SDK 执行，暂不支持此模式命令。请在普通对话或 Paper/PPT/Data 中使用；文件管理的自动压缩与原任务恢复仍按其自身流程处理。'}
  :handler(invocation);
}
/** The native GoalService methods remain unchanged for the trusted task/driver.
 * Both physical carriers dispatch through this public Gateway method. Blocking
 * mutations here prevents the upstream UI/RPC from rearming an unmetered task.
 */
export function protectGoalRpc(ctx:any){
 const gateway=ctx.get('typertGateway');if(!gateway)return ()=>{};
 const restores:(()=>void)[]=[];
 for(const method of ['invoke','stream']){
  const original=gateway[method];if(typeof original!=='function')continue;
  const replacement=async function(request:any){
   if(request.namespace==='goals'&&request.method!=='get')throw new RemoteError('gateway/forbidden',
    '请使用当前对话的 /goal 命令；目标创建与恢复须经过任务准入和计量。');
   return original.call(gateway,request);
  };
  gateway[method]=replacement;restores.push(()=>{if(gateway[method]===replacement)gateway[method]=original;});
 }
 return ()=>restores.reverse().forEach(restore=>restore());
}
