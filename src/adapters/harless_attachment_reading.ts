/** A readable index of existing page observations, never a new verification. */
import {createHash} from 'node:crypto';
import {extname} from 'node:path';

type Source={name:string;sha256:string;origin:string;format?:string};
type Evidence={value:string;origin:'current_turn_upload'|'earlier_conversation_source'};
const hash=(value:unknown)=>createHash('sha256').update(JSON.stringify(value)).digest('hex');

function envelope(value:string):any {
  try{return JSON.parse(value);}catch{}
  try{return JSON.parse(value.slice(value.indexOf('\n')+1));}catch{return undefined;}
}

/** Keep OCR and full declarations in the original envelope. This index lifts
 * only source-bound pixel readings out of escaped/nested source JSON, so a
 * factual question need not restart OCR merely to find an already-read value.
 * Independent failed/successful observations remain independent records.
 */
export function attachmentReadingIndex(evidence:Evidence[],sources:Source[]) {
  const records=new Map<string,any>();
  const visit=(file:any,origin:Evidence['origin'],inherited?:any)=>{
    if(!file||typeof file!=='object')return;
    const identity={...inherited,...file};
    // A reuploaded original can be the catalog's sole current source while
    // retaining earlier successful readings. Context provenance is not source
    // identity: never discard those readings or relabel them as newly read.
    const source=sources.find(row=>row.sha256===identity.sha256&&
      (row.format??extname(row.name).slice(1)).toLowerCase()===identity.format);
    if(!source||!/^[a-f0-9]{64}$/.test(identity.sha256??'')||typeof identity.format!=='string')return;
    if(file.evidence_schema==='source-observations-v1'){
      if(Array.isArray(file.source_observations))for(const observation of file.source_observations)visit(observation,origin,{name:identity.name,sha256:identity.sha256,format:identity.format});
      return;
    }
    if(!Array.isArray(file.pages))return;
    const pages=file.pages.filter((page:any)=>page&&Number.isSafeInteger(page.page)&&page.page>0).map((page:any)=>{
      const report=page.visual_analysis;
      const bound=typeof page.source_id==='string'&&
        [identity.format+':'+identity.sha256+':page:'+page.page,identity.format+':'+identity.sha256+':slide:'+page.page].includes(page.source_id)&&
        report?.source_id===page.source_id&&report?.page===page.page;
      const available=bound&&page.visual_content_reviewed===true&&report?.image_observed===true&&
        /^[a-f0-9]{64}$/.test(page.rendered_image?.sha256??'')&&typeof report?.observations==='string'&&Boolean(report.observations.trim())&&
        Array.isArray(report.unreadable)&&report.unreadable.every((value:any)=>typeof value==='string');
      return {page:page.page,source_id:page.source_id,reading_status:available?'pixel_model_observation':'no_valid_pixel_model_observation',
        ...(available?{rendered_image_sha256:page.rendered_image.sha256,pixel_observation:report.observations,
          unreadable:report.unreadable,verification:'auxiliary_model_reading_not_independent_fact_verification'}:
          {error_code:page.visual_error_code??(report&&!bound?'observation_source_or_page_mismatch':'pixel_observation_unavailable')}),
        ocr_present:Boolean(page.rendered_ocr_text||page.text_method==='ocr'),
        ocr_role:'approximate_retrieval_hint_original_text_retained_in_evidence'};
    });
    if(!pages.length)return;
    const id=hash({sha256:identity.sha256,format:identity.format,origin,pages});
    records.set(id,{observation_id:id,name:source.name,sha256:identity.sha256,format:identity.format,
      origin,admitted_origin:source.origin,provenance:'evidence_context_origin_not_new_visual_execution_or_verification',pages});
  };
  for(const item of evidence){
    const body=envelope(item.value);
    if(Array.isArray(body?.files))for(const file of body.files)visit(file,item.origin);
  }
  return records.size?{schema_version:1,semantics:'source_bound_model_readings_not_new_uploads_or_independent_verification',
    observations:[...records.values()]}:undefined;
}
