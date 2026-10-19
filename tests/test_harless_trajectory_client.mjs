/** Public-slot integration diagnostics; real browser acceptance is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const source=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
function fixture({header=false}={}) {
  let plugin,wrapper,cursor=0,states=[],deps=[],pending=[],tree,cleanups=[];
  const Native=function NativeTrajectory(){},Images=function NativeImages(){},imageInject=()=>({imageAction:'native'});
  const original={options:{id:'trajectory',order:10,label:()=> '轨迹'},component:Native,locale:'trajectory',inject:()=>({loadOlder:'original'})};
  const image={options:{priority:0},component:Images,locale:'conversation',inject:imageInject};
  const entries=new Map([['conversation.view',[original]],['conversation.trajectory.images',[image]]]);
  const declared=new Set(['conversation.view','conversation.chat.node','conversation.trajectory.images']),listeners=new Map(),disposers=[];
  const NativeHeader=function NativeHeader(){},HeaderAction=function HeaderAction(){},selectView=()=>{},headerStore={name:'native header store'};
  let tabRows=[{id:'trajectory',label:'轨迹'},{id:'chat',label:'对话'},{id:'trajectory',label:'轨迹'}];
  const tabSource={subscribe:()=>()=>{},getSnapshot:()=>tabRows};
  if(header){
    const child='conversation.session.header.lineage';declared.add(child);
    entries.set('conversation.session.header',[{component:NativeHeader,options:{},locale:'conversation',store:headerStore,
      children:{[child]:{kind:'single',scope:'session'}},inject:()=>({selectView,hooks:{conversationViews:tabSource}})}]);
    entries.set(child,[{component:HeaderAction,options:{},locale:'conversation'}]);
    entries.get('conversation.view').push({component:()=>{},options:{id:'chat',order:0}});
  }
  const React={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat()}),
    useState(initial){const n=cursor++;if(!(n in states))states[n]=initial;return[states[n],value=>{states[n]=typeof value==='function'?value(states[n]):value;}];},
    useRef(initial){const n=cursor++;return states[n]||(states[n]={current:initial});},
    useEffect(fn,values){const n=cursor++,old=deps[n];if(!old||values.some((value,i)=>value!==old[i])){deps[n]=values;pending.push(()=>{cleanups[n]?.();cleanups[n]=fn();});}},
  };
  const slots={
    entries:name=>entries.get(name)||[],subscribe(name,fn){listeners.set(name,fn);return()=>listeners.delete(name);},
    inject(name,fn){if(name==='conversation.trajectory.images'||name==='conversation.chat.node'||(header&&name==='conversation.session.header.lineage')){const dispose=fn();if(dispose)disposers.push(dispose);}},
    register(spec,component){
      for(const name of Object.keys(spec.children||{})){assert.equal(declared.has(name),false,`slot ${name} has one declaration owner`);declared.add(name);}
      const entry={component,options:spec,locale:spec.locale,inject:spec.inject,store:spec.store};
      entries.set(spec.name,[...(entries.get(spec.name)||[]),entry]);
      if(spec.name==='conversation.view'&&spec.id==='trajectory')wrapper=entry;
      return()=>{entries.set(spec.name,(entries.get(spec.name)||[]).filter(row=>row!==entry));Object.keys(spec.children||{}).forEach(name=>declared.delete(name));};
    },
  };
  const window={__ModuleLoader__:{load(value){plugin=value;}}};
  runInNewContext(source,{window});
  plugin.factory(name=>name==='react'?React:{}).apply({get:name=>({sessions:{},conversation:{},commandUi:{decorate(){}},inputTriggers:{registerSource(){}}})[name],
    effect:()=>{},uiConversation:{events:{register(){}}},slots});
  let rows=[],older=0,inspection={eventNodes:[],requests:[]},session={hasMore:false};const routed=[];
  const owner={sessionId:'a',useChat:selector=>selector({order:rows.map(row=>row.key),nodes:new Map(rows.map(row=>[row.key,row]))}),
    useSession:selector=>selector(session),loadOlder:()=>{older++;return Promise.resolve(true);},renderSlot:(...args)=>{routed.push(args);return'image';},
    useTrajectory:selector=>selector(inspection),useDuration:'native duration',loadImage:'native images',setActualDuration:'native setter',t:'native locale'};
  const render=()=>{cursor=0;tree=wrapper.component(owner);const todo=pending;pending=[];todo.forEach(fn=>fn());return tree;};
  const all=(predicate,node=tree)=>!node||typeof node!=='object'?[]:[...(predicate(node)?[node]:[]),...(node.children||[]).flatMap(child=>all(predicate,child))];
  const content=node=>typeof node==='string'?node:(node?.children||[]).map(content).join('');
  return{render,all,content,owner,original,Native,Images,entries,imageInject,routed,wrapper,declared,
    NativeHeader,HeaderAction,selectView,headerStore,setTabs:rows=>{tabRows=rows;},
    setRows:value=>{rows=value;},setInspection:value=>{inspection=value;},setSession:value=>{session=value;},older:()=>older,notifyImages:()=>listeners.get('conversation.trajectory.images')?.(),
    dispose:()=>{cleanups.forEach(fn=>fn?.());disposers.reverse().forEach(fn=>fn());}};
}
const node=(id,scene='research-data-analysis')=>({key:id,kind:'harless-comparison',visibility:'visible',data:{id,scene,session_id:'a'}});

test('trajectory preserves server-admitted original text and files without guessing parser provenance',()=>{
  const f=fixture(),content=[{type:'text',text:'请总结'},{type:'file',attachment:{name:'paper.pdf'}},
    {type:'text',text:'用户附件的只读提取结果（资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'a'.repeat(64),status:'extracted',text:'raw evidence'}]})}];
  const before=JSON.stringify(content);
  f.setInspection({eventNodes:[{kind:'user',seq:1,content}]});
  const text=f.content(f.render());
  assert.match(text,/请总结/);assert.match(text,/paper.pdf/);assert.match(text,/raw evidence|只读提取结果/);
  assert.equal(JSON.stringify(content),before);f.dispose();
});

test('internal attachment context never creates trajectory rounds or empty context records',()=>{
  const f=fixture(),source={kind:'plugin',plugin:'geneloop-attachment-context',form:'catalog'};
  f.setInspection({eventNodes:[{kind:'context',seq:1,source,content:[]},
    {kind:'user',seq:2,content:[{type:'text',text:'你好'}]},
    {kind:'user',seq:3,source:{...source,form:'recall'},content:[]},
    {kind:'context',seq:4,source,content:[{type:'text',text:'private extraction'}]},
    {kind:'assistant',seq:5,blocks:[{kind:'text',text:'你好！'}]}]});
  const text=f.content(f.render());assert.match(text,/你好/);assert.doesNotMatch(text,/private extraction|上下文|第 2 轮/);
  assert.equal(f.all(row=>row.props.className==='geneloop-trace-round').length,1);f.dispose();
});

test('trajectory shadows the existing tab through public slots and preserves native inject and authorized image rendering',()=>{
  const f=fixture();assert.equal(f.wrapper.options.id,'trajectory');assert.equal(f.wrapper.options.priority,-100);
  assert.equal(f.wrapper.inject,f.original.inject);assert.equal(f.wrapper.locale,'trajectory');
  assert.deepEqual(Object.keys(f.wrapper.options.children),['harless.trajectory.images']);
  const images=f.entries.get('harless.trajectory.images');assert.equal(images.length,1);
  assert.equal(images[0].component,f.Images);assert.equal(images[0].inject,f.imageInject);assert.equal(images[0].locale,'conversation');
  const attachment={id:'approved',name:'图像.png'};
  f.setInspection({eventNodes:[{kind:'user',seq:1,content:[{type:'image',attachment}]}]});
  f.render();assert.equal(f.all(row=>row.type===f.Native).length,0,'ordinary rounds share the unified view');
  assert.equal(f.routed[0][0],'harless.trajectory.images');assert.equal(f.routed[0][1].images[0].attachment,attachment);
  assert.equal(f.routed[0][1].loadImage,'native images');
  f.notifyImages();assert.equal(f.entries.get('harless.trajectory.images').length,1,'late native image registrations mirror without duplicates');
  f.dispose();assert.equal(f.entries.get('conversation.view').length,1);assert.equal(f.declared.has('harless.trajectory.images'),false);
});

test('native header deduplicates shadowed trajectory tabs without replacing title actions or the shared view store',()=>{
  const f=fixture({header:true});const entry=f.entries.get('conversation.session.header').find(row=>row.options.priority===-100);
  assert.ok(entry);assert.equal(entry.store,f.headerStore);assert.equal(entry.locale,'conversation');
  const injected=entry.inject('a',{}),source=injected.hooks.conversationViews;
  assert.equal(injected.selectView,f.selectView);
  const tabs=source.getSnapshot();assert.deepEqual(JSON.parse(JSON.stringify(tabs)),[{id:'chat',label:'对话'},{id:'trajectory',label:'轨迹'}]);
  assert.equal(source.getSnapshot(),tabs,'derived store snapshot remains stable');
  f.setTabs([{id:'trajectory',label:'Trace'},{id:'chat',label:'Chat'},{id:'trajectory',label:'Trace'}]);
  assert.equal(source.getSnapshot()[0].label,'Chat');assert.notEqual(source.getSnapshot(),tabs);
  const aliases=Object.keys(entry.options.children);assert.deepEqual(aliases,['harless.conversation.session.header.lineage']);
  assert.equal(f.entries.get(aliases[0])[0].component,f.HeaderAction);
  const renders=[];const tree=entry.component({renderSlot:(...args)=>renders.push(args)});assert.equal(tree.type,f.NativeHeader);
  tree.props.renderSlot('conversation.session.header.lineage',{title:'原标题'});
  assert.equal(renders[0][0],aliases[0]);assert.equal(renders[0][1].title,'原标题');f.dispose();
});

const user=(seq,text='你好')=>({kind:'user',seq,time:1700000000000+seq*1000,content:[{type:'text',text}]});
const assistant=(seq,text)=>({kind:'assistant',seq,time:1700000000000+seq*1000,blocks:[{kind:'text',text}]});
const task=(id,seq,single=false)=>({...node(id),anchorSeq:seq,location:{turn:{turn:4}},data:{...node(id).data,
  presentation:single?'single':'paired',lanes:{baseline:{trace:[{id:'b'+id,kind:'assistant',text:'baseline '+id,label:'回复'}]},
    ...(!single?{motif:{trace:[{id:'m'+id,kind:'tool',text:'motif '+id,label:'核验',optimized:true}]}}:{})}}});

test('all actual rounds stay in chronological order and only paired rounds have per-round graph lane controls',()=>{
  const f=fixture();f.setRows([task('four',40),task('five',50,true),task('six',60)]);
  f.setInspection({eventNodes:[...Array.from({length:8},(_,i)=>user((i+1)*10)),assistant(11,'第一轮回复'),assistant(21,'第二轮回复'),assistant(31,'第三轮回复'),assistant(71,'普通对话')].reverse()});
  f.render();f.render();
  assert.deepEqual(f.all(row=>row.props['data-round-key']).map(row=>row.props['aria-label']),Array.from({length:8},(_,i)=>'第 '+(i+1)+' 轮'));
  assert.equal(f.all(row=>row.type==='select').length,0);
  assert.equal(f.all(row=>row.type==='button'&&['普通对话','对照任务'].includes(f.content(row))).length,0);
  const controls=()=>f.all(row=>row.props.className==='geneloop-trace-lanes');assert.equal(controls().length,2);
  assert.equal(controls()[0].props['aria-label'],'第 4 轮图示轨迹');assert.equal(controls()[1].props['aria-label'],'第 6 轮图示轨迹');
  const plots=()=>f.all(row=>row.props.className==='geneloop-trace-plot');assert.equal(plots()[4].props['data-shown-lane'],'single');
  f.all(row=>row.type==='button'&&f.content(row)==='Motif',controls()[0])[0].props.onClick();f.render();
  assert.equal(plots()[3].props['data-shown-lane'],'motif');assert.equal(plots()[5].props['data-shown-lane'],'baseline');
  assert.equal(f.all(row=>row.props['data-optimized']==='true',plots()[3]).length,1);
  assert.deepEqual(f.all(row=>row.props.traceOnly===true).map(row=>row.props.node.data.id),['four','five','six']);
  f.all(row=>row.type==='input')[0].props.onChange({target:{value:'第二轮回复'}});f.render();
  assert.deepEqual(f.all(row=>row.props['data-round-key']).map(row=>row.props['aria-label']),['第 2 轮']);
  assert.equal(f.all(row=>row.props['data-chart-turn']).length,8,'search does not renumber or remove chart turns');f.dispose();
});

const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
test('history is loaded across pages before numbering and failures have an explicit retry',async()=>{
  const f=fixture();let page=0;f.setInspection({eventNodes:[user(30)]});f.setSession({hasMore:true,loadingOlder:false});
  f.owner.loadOlder=async()=>{page++;f.setSession({hasMore:true,loadingOlder:true});f.render();await Promise.resolve();
    if(page===1){f.setSession({hasMore:true,loadingOlder:false});throw Error('offline');}
    f.setInspection({eventNodes:[user(10),user(20),user(30)]});f.setSession({hasMore:false,loadingOlder:false});return true;};
  f.render();assert.equal(f.all(row=>row.props['data-round-key']).length,0);await flush();f.render();
  assert.match(f.content(f.all(row=>row.props.role==='alert')[0]),/读取更早记录失败/);assert.equal(page,1);
  f.all(row=>row.type==='button'&&f.content(row)==='重试')[0].props.onClick();f.render();await flush();f.render();
  assert.equal(page,2);assert.deepEqual(f.all(row=>row.props['data-round-key']).map(row=>row.props['aria-label']),['第 1 轮','第 2 轮','第 3 轮']);f.dispose();
});

test('paging continues after loadingOlder changes and a late old-session error cannot affect a new session',async()=>{
  const f=fixture();let page=0,fail;f.setSession({hasMore:true,loadingOlder:false});
  f.owner.loadOlder=async()=>{page++;f.setSession({hasMore:true,loadingOlder:true});f.render();await Promise.resolve();
    f.setSession({hasMore:page<2,loadingOlder:false});f.setInspection({eventNodes:[user(10),user(20)]});return true;};
  f.render();await flush();f.render();await flush();f.render();assert.equal(page,2);
  f.owner.loadOlder=()=>new Promise((_,reject)=>{fail=reject;});f.setSession({hasMore:true});f.render();await flush();
  f.owner.sessionId='b';f.setSession({hasMore:false});f.setInspection({eventNodes:[user(1,'new')]});f.render();
  fail(Error('old session'));await flush();f.render();assert.equal(f.all(row=>row.props.role==='alert').length,0);f.dispose();
});

test('native tool results, image-only replies and active output remain represented',()=>{
  const f=fixture();const attachment={id:'generated'};
  f.setInspection({eventNodes:[user(1),{...assistant(2,''),blocks:[{kind:'tool-call',callId:'x',name:'read',argsRaw:'{}'},{kind:'image',attachment}]},
    {kind:'tool-result',seq:3,callId:'x',call:{name:'read',argsRaw:'{}'},content:[{type:'text',text:'读取完成'}]}],
    partial:{blocks:[{kind:'reasoning',text:'思考记录'},{kind:'text',text:'正在回复'}]},runningCalls:[{callId:'live',name:'analyze',argsRaw:'{}'}]});
  f.render();const list=f.all(row=>row.type?.name==='TraceRows')[0].props.items;
  assert.equal(list.filter(row=>row.tool==='read').length,1);assert.equal(list[0].images[0],attachment);
  assert.equal(list.at(-3).kind,'thinking');assert.equal(list.at(-3).text,'思考记录');
  assert.equal(list.at(-2).text,'正在回复');assert.equal(list.at(-1).status,'running');f.dispose();
});
