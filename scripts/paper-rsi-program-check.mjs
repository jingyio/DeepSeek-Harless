/** Free independent validation/promotion; never calls a model. */
import {readFileSync,writeFileSync} from 'node:fs';
import {validateCandidate,runReportCheck,canonical,digest} from '../src/adapters/paper_rsi_program.ts';
const [candidatePath,fixturesPath,destination,provenancePath]=process.argv.slice(2);
const candidate=validateCandidate(JSON.parse(readFileSync(candidatePath,'utf8')));
const fixtures=JSON.parse(readFileSync(fixturesPath,'utf8'));
const rows=fixtures.map(f=>{try{const actual=runReportCheck(candidate,f.input);return {id:f.id,passed:canonical(actual)===canonical(f.expected),actual,expected:f.expected};}catch(e){return {id:f.id,passed:false,error:String(e)};}});
const result={passed:rows.every(r=>r.passed),cases:rows};
console.log(JSON.stringify(result));
if(!result.passed)process.exit(1);
if(destination){
 const provenance=JSON.parse(readFileSync(provenancePath,'utf8'));
 if(fixtures.length<6||provenance.development_passed!==true||provenance.trial_observed!==true||
   !/^[a-f0-9]{64}$/.test(provenance.cordis_source_sha256??'')||
   fixtures.some(f=>provenance.training_input_sha256?.includes(digest(f.input))))throw Error('independent_promotion_evidence_required');
 const body={schema_version:1,kind:'model_generated_pure_tool',candidate,candidate_sha256:digest(candidate),provenance,
   certification:{status:'passed',heldout_cases:rows.length,fixture_sha256:digest(fixtures),results_sha256:digest(rows)}};
 writeFileSync(destination,JSON.stringify({...body,manifest_digest:digest(body)},null,2)+'\n',{mode:0o600,flag:'wx'});
}
