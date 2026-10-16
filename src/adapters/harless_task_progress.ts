/** Public execution progress from native model/tool lifecycle events, never simulated prose. */
export type TaskActivity = { label: string; status: 'running' | 'completed' | 'failed' | 'cancelled'; tool?: string };
export type TaskMessage = { id: string; text: string; status: 'streaming' | 'completed' | 'interrupted'; attempt: number; started_at: string; finished_at?: string };
export type TaskTrace = TaskActivity & { id: string; time: string; kind: 'assistant' | 'thinking' | 'tool' | 'motif' | 'request'; text?: string; optimized: boolean; verified_skip: boolean };
export type TaskProgressSnapshot = { answer: string; progress: TaskActivity; activity: TaskActivity[]; messages: TaskMessage[]; trace: TaskTrace[] };
const toolLabels: [RegExp, string][] = [
  [/^read_pending_plan$/, '读取需要修正的页面'],
  [/^repair_pending_plan$/, '修正页面并重新核验'],
  [/^(?:render_delivery|render_deck)$/, '生成并核验演示文稿'],
  [/exec|shell|command|terminal|bash|powershell/i, '运行命令'],
  [/pin|list|inspect|inventory|discover/i, '检查资料'],
  [/read|extract|parse|load/i, '读取资料'],
  [/analy|statistic|fit_|regress|compute|plan_analysis/i, '分析数据'],
  [/plot|figure|chart|visual/i, '生成图表'],
  [/slide|ppt|deck/i, '制作演示文稿'],
  [/proof|revision|revise|audit_paper/i, '检查和修订论文'],
  [/verify|validate|audit|check/i, '核验结果'],
  [/report|compose|export|deliver|write|save|layout|render/i, '生成交付文件'],
];
export function taskToolLabel(name: unknown): string {
  const tool = typeof name === 'string' ? name.split('__').at(-1)! : '';
  return toolLabels.find(([pattern]) => pattern.test(tool))?.[1] ?? '执行工具';
}

/** Reasoning is represented by its real lifecycle, not private reasoning text or arguments. */
export function createTaskProgress(saved?: Partial<TaskProgressSnapshot>, now = () => new Date().toISOString()) {
  const restored = (value: any): TaskActivity | undefined => value && typeof value.label === 'string' && value.label.length <= 160 &&
    ['running', 'completed', 'failed', 'cancelled'].includes(value.status)
      ? { label: value.label, status: value.status, ...(typeof value.tool === 'string' && /^[a-zA-Z0-9_-]{1,160}$/.test(value.tool) ? { tool: value.tool } : {}) } : undefined;
  let answer = typeof saved?.answer === 'string' ? saved.answer : '';
  let progress: TaskActivity = restored(saved?.progress) ?? { label: '准备处理请求', status: 'running' };
  let currentText = new Map<number, string>();
  const activities: TaskActivity[] = Array.isArray(saved?.activity) ? saved.activity.slice(-40).map(restored).filter((row): row is TaskActivity => Boolean(row)) : [];
  const messages: TaskMessage[] = Array.isArray(saved?.messages) ? structuredClone(saved.messages) : [];
  const trace: TaskTrace[] = Array.isArray(saved?.trace) ? structuredClone(saved.trace) : [];
  let attempt = Math.max(0,...messages.map(row=>row.attempt)), serial = trace.length;
  let current: TaskMessage | undefined, requestRow: TaskTrace | undefined, thinking: TaskTrace | undefined, messageRow: TaskTrace | undefined;
  const tools = new Map<string, { activity: TaskActivity; trace: TaskTrace }>();
  const seenMessages = new Set<string>();
  const setProgress = (label: string, status: TaskActivity['status'] = 'running') => { progress = { label, status }; };
  const safeTool = (name: any) => typeof name === 'string' && /^[a-zA-Z0-9_-]{1,160}$/.test(name) ? name : undefined;
  const row = (kind: TaskTrace['kind'], label: string, status: TaskActivity['status']='running', time=now()): TaskTrace => {
    const item: TaskTrace={id:'trace-'+(++serial),time,kind,label,status,optimized:false,verified_skip:false}; trace.push(item); return item;
  };
  const settleAttempt = (status: 'completed'|'interrupted') => {
    if(current?.status==='streaming'){current.status=status;current.finished_at=now();}
    for(const entry of [requestRow,thinking,messageRow])if(entry?.status==='running')entry.status=status==='completed'?'completed':'cancelled';
  };
  const updateText = () => {
    answer=[...currentText.entries()].sort(([a],[b])=>a-b).map(([,text])=>text).join('\n');
    if(!current){
      if(!attempt)attempt=1;
      current={id:'assistant-'+attempt+'-'+messages.length,text:'',status:'streaming',attempt,started_at:now()};messages.push(current);
      messageRow=row('assistant','回复内容');
    }
    current.text=answer;if(messageRow)messageRow.text=answer;
    if(thinking?.status==='running')thinking.status='completed';
  };
  return {
    recovery() { row('request','正在修正演示文稿');setProgress('正在修正演示文稿'); },
    beginAttempt() {
      settleAttempt('completed'); attempt++; currentText=new Map(); current=undefined; thinking=undefined;messageRow=undefined;
      requestRow=row('request','准备回复');setProgress('正在组织回复');
    },
    chunk(chunk: any) {
      if(chunk?.type==='text-delta'&&typeof chunk.text==='string'&&Number.isSafeInteger(chunk.index)){
        currentText.set(chunk.index,(currentText.get(chunk.index)??'')+chunk.text);updateText();setProgress('正在回复');
      }else if(chunk?.type==='block-end'&&chunk.block?.type==='text'&&typeof chunk.block.text==='string'){
        currentText.set(chunk.index,chunk.block.text);updateText();
      }else if(chunk?.type==='reasoning-delta'){
        thinking??=row('thinking','正在思考');setProgress('正在思考');
      }else if(chunk?.type==='tool-call-delta'&&chunk.name){
        if(thinking?.status==='running')thinking.status='completed';setProgress('准备'+taskToolLabel(chunk.name));
      }
    },
    event(event: any) {
      const time=typeof event?.time==='number'?new Date(event.time).toISOString():now();
      if(event?.type==='tool/call'){
        const key=String(event.data?.callId??'');if(!key||tools.has(key))return;
        settleAttempt('completed');
        const activity:TaskActivity={label:taskToolLabel(event.data?.name),status:'running',...(safeTool(event.data?.name)?{tool:event.data.name}:{})};
        const entry=row('tool',activity.label,'running',time);if(activity.tool)entry.tool=activity.tool;
        tools.set(key,{activity,trace:entry});activities.push(activity);if(activities.length>40)activities.shift();progress={...activity};
      }else if(event?.type==='tool/result'){
        const key=String(event.data?.message?.source?.callId??event.data?.callId??''), item=tools.get(key);if(!item)return;
        const failed=Boolean(event.data?.error)||event.data?.message?.content?.some((part:any)=>part.isError===true);
        item.activity.status=item.trace.status=failed?'failed':'completed';progress={...item.activity};
      }else if(event?.type==='assistant/message'){
        const message=event.data?.message, id=message?.id;if(id&&seenMessages.has(id))return;if(id)seenMessages.add(id);
        if(Array.isArray(message?.content)){
          const text=message.content.filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n');
          // Tool-only assistant messages must not erase a preceding explanation.
          if(text){if(!current||current.status!=='streaming'){current=undefined;messageRow=undefined;attempt++;}
            currentText=new Map([[0,text]]);updateText();current!.started_at=time;}
          settleAttempt(event.data?.interrupted ? 'interrupted' : 'completed');
        }
      }
    },
    audit(value: any) {
      const kind=value?.kind;
      const labels:Record<string,string>={model_request_skipped_verified:'已验证跳过一次模型请求',motif_bypass_attempt:'正在核验 Motif 流程',
        shadow_candidate:'发现 Motif 候选（仅观察）',motif_fallback:'转交模型继续处理',motif_result_unverified:'Motif 结果未通过核验',
        bypass_result_unverified:'Motif 结果未通过核验',motif_tool_result_verified:'Motif 工具结果已核验',motif_tool_result_unverified:'Motif 工具结果未通过核验'};
      if(!labels[kind])return;
      const failed=/unverified$/.test(kind), entry=row('motif',labels[kind],failed?'failed':kind==='motif_bypass_attempt'?'running':'completed',value.at??now());
      entry.verified_skip=kind==='model_request_skipped_verified';entry.optimized=entry.verified_skip;
      if(safeTool(value.tool))entry.tool=value.tool;
      if(kind==='model_request_skipped_verified'||failed)for(const prior of trace)if(prior.kind==='motif'&&prior.status==='running')prior.status=failed?'failed':'completed';
    },
    finish(status: string) {
      const state=status==='completed'?'completed':status==='cancelled'?'cancelled':'failed';
      settleAttempt(state==='completed'?'completed':'interrupted');
      for(const item of activities)if(item.status==='running')item.status=state==='completed'?'failed':state;
      for(const item of trace)if(item.status==='running')item.status=state==='completed'?'failed':state;
      setProgress(state==='completed'?'回复完成':state==='cancelled'?'已停止':'处理未完成',state);
    },
    snapshot(): TaskProgressSnapshot { return {answer,progress:{...progress},activity:activities.map(item=>({...item})),messages:structuredClone(messages),trace:structuredClone(trace)}; },
  };
}
