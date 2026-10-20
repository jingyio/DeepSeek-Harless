/** Current evidence, actual provider warning and prospective-argument guards. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {negativeOutcome} from '../src/adapters/negative_outcome.ts';
import {currentShapeIssues,validateCurrentConstraint} from '../src/adapters/negative_constraint_runtime.ts';
import {createNegativeRuntime} from '../src/adapters/script_negative_runtime.ts';
import {Context} from '@deepseek-ai/cordis';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
const hash=x=>createHash('sha256').update(x).digest('hex');
function py(code){const p=spawnSync(process.env.SSS_PYTHON??'python3',['-c',code],{encoding:'utf8'});assert.equal(p.status,0,p.stderr);return JSON.parse(p.stdout);}
const certified=()=>validateCurrentConstraint(py("import sys,json;sys.path.insert(0,'tests');from test_negative_constraints import fixture_guard;print(json.dumps(fixture_guard()))"));
test('Python and TS agree on failed checks, mixed outcomes, opaque errors and strict success',()=>{
 const cases=py("import sys,json;sys.path.insert(0,'tests');from test_negative_outcome import cases;from src.adapters.negative_outcome import negative_outcome;print(json.dumps([[v,negative_outcome(v)] for v in cases()]))");
 for(const [value,outcome] of cases)assert.deepEqual(negativeOutcome(value),outcome);
});
function fixture(t){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'negative-current-')));t.after(()=>rmSync(root,{recursive:true,force:true}));mkdirSync(join(root,'inputs'));writeFileSync(join(root,'inputs/source.txt'),'current');
 const sources={'source.txt':hash('current')};writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files:sources}));
 const goal={kind:'current_review_recovery_scope',version:1,task_id:'current',source_versions:sources,arguments:{title:'keep',note:'keep too',rows:['one','two','three'],source_versions:sources},policy:'preserve_structure_allow_semantic_leaf_revisions',origin:'explicit_current_recovery_requirement_not_inferred_from_history'};
 const grant={schema_version:1,task_id:'current',allow_output:true};const write=(name,v)=>writeFileSync(join(root,name),JSON.stringify(v));write('review-recovery-scope.json',goal);write('paper-output-grant.json',grant);
 const tools=[{name:'mcp__test__export',parameters:{type:'object'}}],guard=certified(),events=[];
 const rule={id:'test',tool:tools[0].name,tools_sha256:digest(tools),failure_code:'shape_mismatch',failure_source:'failed_checks',retry_policy:'warn_then_current_constraint',argument_guard:guard,failure_flags:[['exported']],version_slots:[]};
 const r=createNegativeRuntime({workspace:root,library:{rules:[rule]},mode:'enforce',audit:v=>events.push(v)}),request={tools,messages:[]};r.update(request);
 const args={...goal.arguments,rows:['combined']};const call={name:rule.tool,callId:'first',arguments:args};
 const failure={exported:false,failed_checks:['shape_mismatch'],scope_issues:currentShapeIssues(goal.arguments,args),execution_evidence:{version:1,kind:'review_execution_evidence',arguments_sha256:digest(args),recovery_scope_sha256:hash(readFileSync(join(root,'review-recovery-scope.json'))),task_id:'current',source_versions:sources,grant_sha256:digest(grant)}};
 const fail=()=>r.observe(call,{content:[{type:'text',text:JSON.stringify(failure)}]});
 const warn=()=>{const text=r.takeNotice();r.beforeRequest({...request,messages:[{role:'user',source:{kind:'plugin',plugin:'script-motif-negative'},content:[{type:'text',text}]}]});return text;};
 return {r,root,goal,grant,tools,rule,request,call,failure,fail,warn,events,write};
}
test('a warning accessor or a virtual provider update never authorizes stopping; a real appended warning does',t=>{
 const f=fixture(t);f.fail();const text=f.r.takeNotice();assert.ok(text.includes('expected_items'));f.r.update({...f.request,messages:[{role:'user',source:{kind:'plugin',plugin:'script-motif-negative'},content:text}]});
 assert.equal(f.r.guard(f.call),undefined);f.r.beforeRequest({...f.request,messages:[{role:'user',source:{kind:'plugin',plugin:'script-motif-negative'},content:text}]});
 assert.match(f.r.guard(f.call),/早停/);assert.equal(f.events.filter(e=>e.kind==='negative_prompt_delivered').length,1);
});
test('changed unrelated text or invalid shape stays blocked, corrected current shape releases',t=>{
 const f=fixture(t);f.fail();f.warn();
 const candidate={...f.call,callId:'retry',arguments:{...f.call.arguments,title:'unrelated change',rows:['different','still short']}};
 assert.match(f.r.guard(candidate),/expected_items.*3/);
 candidate.arguments.rows=['semantic revision','two','three'];assert.equal(f.r.guard(candidate),undefined);
});
test('new user/schema/source/grant/scope or forged receipt invalidates applicability',t=>{
 for(const changed of ['user','schema','source','grant','goal','receipt']){
  const f=fixture(t);
  if(changed==='receipt')f.failure.execution_evidence.arguments_sha256='0'.repeat(64);
  f.fail();f.warn();
  if(changed==='user')f.r.update({...f.request,messages:[{role:'user',source:{kind:'user'},content:'new requirement'}]});
  if(changed==='schema')f.r.update({tools:[],messages:[]});
  if(changed==='source')writeFileSync(join(f.root,'inputs/source.txt'),'new');
  if(changed==='grant')f.write('paper-output-grant.json',{...f.grant,allow_output:false});
  if(changed==='goal')f.write('review-recovery-scope.json',{...f.goal,task_id:'other'});
  assert.equal(f.r.guard(f.call),undefined,changed);
 }
});
test('shape validation agrees with Python, is bounded and refuses uncertified interventions',()=>{
 const guard=certified(),bad=structuredClone(guard);bad.certification.interventions[0].repair_passed=false;assert.throws(()=>validateCurrentConstraint(bad));
 assert.equal(currentShapeIssues({n:1},{n:1}),null);
 assert.deepEqual(currentShapeIssues({'a/b':{x:['one','two']}},{'a/b':{x:['one']}}),[{pointer:'/a~1b/x',expected_items:2,actual_items:1}]);
});
test('native tool runtime stops invalid prospective arguments after a real warning, but executes valid repairs',async t=>{
 const f=fixture(t),ctx=new Context();ctx.systemPrompt={tools(){}};const tools=new ToolRuntime(ctx);let calls=0;
 const disposers=[tools.guard(f.r.guard),ctx.on('tools/result',f.r.observe)];t.after(()=>disposers.reverse().forEach(d=>d()));
 for(const name of [f.call.name,'mcp__test__other'])disposers.push(tools.register({name,description:'diagnostic',parameters:{type:'object'},output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},async execute(args){calls++;return args.rows?.length===3?{exported:true}:f.failure;}}));
 const run=(name,id,args)=>tools.execute({name,arguments:args,callId:id,signal:new AbortController().signal});
 assert.equal((await run(f.call.name,'first',f.call.arguments)).isError,false);f.warn();
 assert.equal((await run(f.call.name,'repeat',{...f.call.arguments,title:'unrelated'})).isError,true);assert.equal(calls,1);
 assert.equal((await run('mcp__test__other','other',{})).isError,false);assert.equal(calls,2);
 assert.equal((await run(f.call.name,'fixed',f.goal.arguments)).isError,false);assert.equal(calls,3);
});
