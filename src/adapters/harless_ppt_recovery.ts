/** Continue the same native Harness turn after a repairable PPT failure. */
const generation = new Set(['render_deck','restyle_deck','revise_deck','render_delivery','revise_delivery','build_delivery','repair_pending_plan']);
const delivery = new Set(['deliver_deck','render_delivery','revise_delivery','build_delivery','repair_pending_plan']);
const repairable = /^(?:slide_count_mismatch|invalid_(?:arguments|plan|slide|revision|pending_patch|pending_plan|image)|no_changes|out_of_bounds|content_overlap|(?:text|content|layout|title|body|table|process|evidence_note|chart_label)[a-z_]*(?:overflow|capacity|too_long)|plan_validation_failed|layout_rejected|validation_failed)$/;
function repairCode(value:any,depth=0):string|undefined {
  if(depth>5||!value||typeof value!=='object')return;
  if(typeof value.code==='string'&&repairable.test(value.code))return value.code;
  if(typeof value.error==='string'&&repairable.test(value.error))return value.error;
  // The TS adapter wraps real renderer failures, retaining their structured report.
  for(const key of ['backend_report','report','details','structuredContent']){
    const found=repairCode(value[key],depth+1);if(found)return found;
  }
  for(const part of value.content??[]){
    if(part?.type!=='text'||typeof part.text!=='string'||part.text.length>80000)continue;
    try{const found=repairCode(JSON.parse(part.text.replace(/^Error:\s*/,'')),depth+1);if(found)return found;}catch{}
  }
}
function payload(result:any):any {
  if(result?.structuredContent && typeof result.structuredContent==='object')return result.structuredContent;
  const text=result?.content?.filter((p:any)=>p.type==='text');
  if(text?.length!==1||typeof text[0].text!=='string')return {};
  try{return JSON.parse(text[0].text.replace(/^Error:\s*/,''));}catch{return {};}
}
export function createPptRecovery(){
  let attempted=false,delivered=false,blocked=false,continuations=0;
  let failure:{tool:string;code:string}|undefined;
  return {
    observe(execution:any,result:any){
      const tool=String(execution?.name??'').replace(/^mcp__ppt__/,'');
      if(!String(execution?.name??'').startsWith('mcp__ppt__'))return;
      const value=payload(result),failed=result?.isError===true||value?.ok===false||(tool==='validate_deck'&&value?.passed===false);
      if(generation.has(tool)){attempted=true;delivered=false;}
      if(failed){
        if(!generation.has(tool)&&tool!=='validate_deck')return;
        const code=result?.error?.info?.code==='INVALID_ARGS'?'invalid_arguments':
          repairCode(value)??(tool==='validate_deck'&&value?.passed===false?'validation_failed':typeof value?.code==='string'?value.code:'');
        blocked=!repairable.test(code);failure=blocked?undefined:{tool,code};
        return;
      }
      if(generation.has(tool)){blocked=false;failure=undefined;}
      const atomicReceipt=tool==='deliver_deck'&&typeof value?.deck_id==='string'&&/^[a-f0-9]{64}$/.test(value?.file_sha256??'')
        &&typeof value?.validation_id==='string'&&/^[a-f0-9]{64}$/.test(value?.input_version??'')
        &&Array.isArray(value?.artifacts)&&value.artifacts.length>0;
      if(delivery.has(tool)&&(value?.delivered===true||value?.status==='delivered'||atomicReceipt)){delivered=true;failure=undefined;blocked=false;}
    },
    stop({aborted,expectedSlides}:{aborted:boolean;expectedSlides?:number}){
      if(aborted||!attempted||delivered||blocked)return null;
      return {continuation:++continuations,error:failure??null,
        instruction:'本轮演示文稿尚未交付。继续同一任务，使用原工具、原来源、原权限和剩余任务预算完成修正与交付。'
          +'用户已授权你自行纠正模型的参数、页数和排版错误，不因这些错误结束回复或再次要求用户确认。'
          +(Number.isInteger(expectedSlides)?'本轮已绑定的总页数（含封面和结尾）为 '+expectedSlides+'，按此修正计划。':'')
          +'根据实际工具反馈修改错误字段后继续；保留来源、科研条件与未修改内容。有失败草稿且恢复工具可用时只修改失败页，否则按工具契约提交修正后的完整计划。'
          +'生成后继续 inspect_deck、validate_deck、deliver_deck，或使用已有的等价交付工具；真实交付回执成功后再总结。'
          +'这条续接不新增权限、不重建任务、不重置预算，不允许伪造数据或把失败说成成功。'
          +'若确实缺少无法推断的资料或用户取消，明确说明缺少什么。'
          +'\n可修复工具反馈：'+JSON.stringify(failure??{code:'delivery_not_yet_published'})};
    },
    state:()=>({attempted,delivered,blocked,continuations,failure:failure??null})
  };
}
