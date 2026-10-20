/** No error code does not mean success. Keep Python/TS outcomes identical. */
export function negativeOutcome(value:any){
 if(!value||typeof value!=='object'||Array.isArray(value))return {status:'unknown',failures:[]};
 const flags=['exported','finalized','staged','ok','success','done'].filter(k=>Object.hasOwn(value,k)).map(k=>value[k]);
 const code=value.validation_error,checks=value.failed_checks,valid=(s:any)=>typeof s==='string'&&/^[a-zA-Z][a-zA-Z0-9_:-]{0,127}$/.test(s);
 const hasError=value.error!=null&&value.error!==false&&value.error!=='';
 if(code!=null&&!valid(code)||checks!=null&&(!Array.isArray(checks)||checks.length>32||!checks.every(valid)))return {status:'unknown',failures:[]};
 const failures=[...(code?[{source:'validation_error',code}]:[]),...[...new Set<string>(checks??[])].sort().map(code=>({source:'failed_checks',code}))];
 if(flags.includes(true)&&(failures.length||flags.includes(false)||hasError))return {status:'unknown',failures:[]};
 if(failures.length)return {status:'failure',failures};
 if(flags.includes(false)||hasError)return {status:'failure_unknown',failures:[]};
 return {status:flags.includes(true)?'success':'unknown',failures:[]};
}
