/** Require a real export after a source was read for a requested paper review. */
export function paperExportRequested(text:string){
  if(/不(?:要|用|需要).{0,12}(?:报告|导出|生成|文件|pdf)|(?:do not|don't|no need to).{0,24}(?:export|report|file|pdf)/i.test(text))return false;
  return /(?:生成|导出|交付|下载|提供|输出).{0,16}(?:报告|pdf|文件)|(?:报告|pdf).{0,8}(?:文件|下载)|(?:export|generate|deliver|download).{0,20}(?:report|pdf|file)/i.test(text);
}
export function createPaperRecovery(){
  let read=false,delivered=false,blocked=false,continuations=0;
  return {
    observe(execution:any,result:any){
      const name=String(execution?.name??'');
      if(!['mcp__paper_checks__read_pinned_document','mcp__paper_checks__export_review_report'].includes(name))return;
      let value=result?.structuredContent;
      if(!value){try{value=JSON.parse(result?.content?.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('')??'{}');}catch{value={};}}
      if(result?.isError===true){blocked=true;return;}
      if(name.endsWith('__read_pinned_document')&&typeof value?.source_id==='string'){
        read=true;blocked=false;
      }
      if(name.endsWith('__export_review_report')){
        delivered=value?.exported===true&&Array.isArray(value?.artifacts)&&value.artifacts.some((f:any)=>
          typeof f.name==='string'&&f.name.endsWith('.pdf')&&/^[a-f0-9]{64}$/.test(f.sha256??''));
        blocked=value?.exported===false&&typeof value?.reason==='string'&&value.reason!=='source_versions_mismatch';
      }
    },
    stop({aborted}:{aborted:boolean}){
      if(aborted||!read||delivered||blocked)return null;
      return {continuation:++continuations,instruction:
        '本轮校对尚无成功的 PDF 导出回执。继续同一任务、同一来源和剩余预算，先复核已写出的发现是否有明确原文依据；'
        +'将猜测、信息缺失和可选润色与已证实错误区分，保留原始事实。然后调用现有 export_review_report 实际生成来源绑定的 PDF/Markdown，'
        +'使用 list_inputs 返回的完整文件名与 SHA256。只有工具成功回执后才总结真实文件，不能编造文件名或把聊天回复称为已导出。'
        +'若上次回复声称已经交付但未执行导出，纠正这个说法并完成导出；不重建任务、不重置预算、不扩大权限。'};
    }
  };
}
