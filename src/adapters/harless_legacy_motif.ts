/** Compatibility with the existing learned formats. No retraining or new graph construction. */
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createInterceptor as createReportInterceptor,validateLibrary} from '../../benchmarks/research_report_agent_v3/motif_plugin.mjs';
import {digest,observation} from '../motif_core/online_skill_runtime.mjs';
const sha=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
export function validateExistingData(library:any){validateLibrary(library);}
export function dataInterceptor(library:any,workspace:string,mode:string,audit:(row:any)=>void){
  const root=join(workspace,'report/sources/cases/uploaded'),run=join(workspace,'outputs/report');
  const source_files=['data.csv','study.json','task.txt'].map(name=>({path:join(root,name),sha256:sha(readFileSync(join(root,name)))}));
  const csv=source_files[0].sha256;
  if([...library.training_csv_sha256,library.certification_csv_sha256].includes(csv))throw Error('training_source_not_prospective');
  const task={workspace:run,workspace_id:'workspace-'+sha(Buffer.from(run)).slice(0,24),
    source_files,csv_sha256:csv,study_version:digest(Object.fromEntries(source_files.map(row=>[row.path.split('/').pop(),row.sha256])))};
  const delegate=createReportInterceptor({library,task,mode,audit});
  return{observe(_session:string,exec:any,result:any){delegate.observe(exec,result);},
    intercept(_session:string,request:any,next:any){return delegate.intercept(request,next);}};
}
export function paperShadowInterceptor(library:any,schemas:any[],audit:(row:any)=>void){
  if(library.kind!=='paper_batch_shadow_v1'||library.execution_policy!=='shadow_only'||!Array.isArray(library.motifs))throw Error('invalid_existing_paper_shadow_library');
  const permitted=new Map(library.tools.map((row:any)=>[row.name,row.parameters]));
  let latest:any=null;
  return{
    observe(_session:string,exec:any,result:any){
      const value=observation(result,exec.name);
      latest=value&&!result?.isError&&!result?.value?.isError&&typeof value.input_id==='string'?{tool:exec.name,value}:null;
    },
    intercept(_session:string,_request:any,next:any){
      if(latest){
        const current=latest;latest=null;
        for(const motif of library.motifs){
          if(motif.anchor!==current.tool||motif.training_session_count<2)continue;
          const valid=motif.batch.every((node:any)=>{
            const schema=schemas.find(row=>row.name===node.tool)?.parameters;
            return schema&&digest(schema)===digest(permitted.get(node.tool))&&
              Object.values(node.arguments_binding).every(pointer=>pointer==='/input_id')&&typeof current.value.input_id==='string';
          });
          if(valid)audit({kind:'shadow_candidate',motif_id:motif.motif_id,tools:motif.batch.map((row:any)=>row.tool),
            reason:'existing_shadow_only_library',execution:false});
        }
      }
      return next(); // The original library authorizes prediction only.
    },
  };
}
