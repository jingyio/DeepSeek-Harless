/** Public-slot integration diagnostics; real browser acceptance is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const source=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
function fixture({header=false}={}) {
  let plugin,wrapper,cursor=0,states=[],deps=[],pending=[],tree;
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
    useEffect(fn,values){const n=cursor++,old=deps[n];if(!old||values.some((value,i)=>value!==old[i])){deps[n]=values;pending.push(fn);}},
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
  let rows=[],older=0;const routed=[];
  const owner={sessionId:'a',useChat:selector=>selector({order:rows.map(row=>row.key),nodes:new Map(rows.map(row=>[row.key,row]))}),
    useSession:selector=>selector({hasMore:true}),loadOlder:()=>{older++;},renderSlot:(...args)=>{routed.push(args);return'image';},
    useTrajectory:'native hook',useDuration:'native duration',loadImage:'native images',setActualDuration:'native setter',t:'native locale'};
  const render=()=>{cursor=0;tree=wrapper.component(owner);const todo=pending;pending=[];todo.forEach(fn=>fn());return tree;};
  const all=(predicate,node=tree)=>!node||typeof node!=='object'?[]:[...(predicate(node)?[node]:[]),...(node.children||[]).flatMap(child=>all(predicate,child))];
  const content=node=>typeof node==='string'?node:(node?.children||[]).map(content).join('');
  return{render,all,content,owner,original,Native,Images,entries,imageInject,routed,wrapper,declared,
    NativeHeader,HeaderAction,selectView,headerStore,setTabs:rows=>{tabRows=rows;},
    setRows:value=>{rows=value;},older:()=>older,notifyImages:()=>listeners.get('conversation.trajectory.images')?.(),
    dispose:()=>disposers.reverse().forEach(fn=>fn())};
}
const node=(id,scene='research-data-analysis')=>({key:id,kind:'harless-comparison',visibility:'visible',data:{id,scene,session_id:'a'}});

test('trajectory shadows the existing tab through public slots and preserves native inject and authorized image rendering',()=>{
  const f=fixture();assert.equal(f.wrapper.options.id,'trajectory');assert.equal(f.wrapper.options.priority,-100);
  assert.equal(f.wrapper.inject,f.original.inject);assert.equal(f.wrapper.locale,'trajectory');
  assert.deepEqual(Object.keys(f.wrapper.options.children),['harless.trajectory.images']);
  const images=f.entries.get('harless.trajectory.images');assert.equal(images.length,1);
  assert.equal(images[0].component,f.Images);assert.equal(images[0].inject,f.imageInject);assert.equal(images[0].locale,'conversation');
  let tree=f.render();assert.equal(tree.type,f.Native,'normal chat keeps the native trajectory');
  assert.equal(tree.props.useTrajectory,'native hook');assert.equal(tree.props.loadImage,'native images');
  assert.equal(tree.props.renderSlot('conversation.trajectory.images',{images:['approved']}),'image');
  assert.equal(f.routed[0][0],'harless.trajectory.images');assert.deepEqual(f.routed[0][1],{images:['approved']});
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

test('each comparison round has an explicit selector and reuses its own live comparison node',()=>{
  const f=fixture();f.setRows([{...node('first'),location:{turn:{turn:2}}},{...node('second','ppt'),location:{turn:{turn:5}}}]);f.render();f.render();
  const select=f.all(row=>row.type==='select')[0];assert.equal(select.props.value,'second');
  assert.equal(f.all(row=>row.type==='option').length,2);assert.match(f.content(select),/第 2 轮 · \/data.*第 5 轮 · \/ppt/);
  select.props.onChange({target:{value:'first'}});f.render();
  const comparison=f.all(row=>row.props.traceOnly===true)[0];assert.equal(comparison.props.node.data.id,'first');assert.equal(comparison.props.key,'first');
  f.all(row=>row.type==='button'&&f.content(row)==='加载更早记录')[0].props.onClick();assert.equal(f.older(),1);
  f.all(row=>row.type==='button'&&f.content(row)==='普通对话')[0].props.onClick();f.render();assert.equal(f.all(row=>row.type===f.Native).length,1);
  assert.equal(f.all(row=>row.props.traceOnly===true).length,0);
  f.owner.sessionId='b';f.setRows([node('other','paper-proofreading')]);f.render();f.render();
  assert.equal(f.all(row=>row.props.traceOnly===true)[0].props.node.data.id,'other','new session resets ordinary/comparison selection');
  f.dispose();
});
