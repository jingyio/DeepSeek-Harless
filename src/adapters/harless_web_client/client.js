/** Native /harless popup and persistent composer status. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: (require) => {
    const React = require('react');
    const inject = ['commandUi', 'sessions', 'slots'];
    const endpoint = '/api/harless/settings';
    const observers = new Map();
    function publish(sessionId, value) {
      for (const listener of observers.get(sessionId) || []) listener(value);
    }
    async function settings(session, signal) {
      const response = await fetch(`${endpoint}?session_id=${encodeURIComponent(session.sessionId)}`,
        { credentials: 'same-origin', cache: 'no-store', signal });
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error?.message || 'Could not load Harless settings');
      return value;
    }
    async function select(session, patch) {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'select', session_id: session.sessionId, selection: patch }),
      });
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error?.message || 'Could not save Harless settings');
      return value;
    }
    const modeLabel = mode => mode === 'baseline' ? 'Origin' : mode[0].toUpperCase() + mode.slice(1);
    function PptChatCard({ node, sessionId }) {
      const [value, setValue] = React.useState(null), [error, setError] = React.useState(''), [pending, setPending] = React.useState(false), [downloaded, setDownloaded] = React.useState(false);
      const url = `/api/harless/ppt/chat?session_id=${encodeURIComponent(sessionId)}&turn_id=${encodeURIComponent(node.commandId)}`;
      React.useEffect(() => {
        let live = true, timer;
        const pull = async () => {
          try { const res = await fetch(url, { credentials:'same-origin', cache:'no-store' }); const data = await res.json();
            if (!res.ok) throw Error(data.error || '状态暂时不可用'); if (live) { setValue(data); setError(''); }
          } catch(e) { if (live) setError(e.message); }
          if (live) timer = setTimeout(pull, 2000);
        }; pull(); return () => { live = false; clearTimeout(timer); };
      }, [url]);
      const stop = async () => {
        setPending(true); setError('');
        try { const res = await fetch('/api/harless/ppt/chat', {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({action:'cancel',session_id:sessionId,turn_id:node.commandId})});
          const data=await res.json(); if(!res.ok)throw Error(data.error);setValue(data);
        } catch(e) { setError(e.message); } finally { setPending(false); }
      };
      const h=React.createElement, delivery=value?.delivery, files=delivery?.artifacts||[];
      const images=files.filter(a=>['png','preview'].includes(a.kind)), pptx=files.find(a=>a.kind==='pptx'), pdf=files.find(a=>a.kind==='pdf');
      const active=!value||['preparing','preview','queued','running'].includes(value.status);
      const labels={preparing:'准备资料',preview:'准备资料',queued:'已接收',running:'正在处理',completed:'已完成',failed:'暂未完成',cancelled:'已停止',interrupted:'已中断'};
      const stages=value?.kind==='feedback'?['revising','complete']:['reading','planning','checking','complete'];
      const stageNames={reading:'读取资料',planning:'整理与编排',checking:'检查与预览',revising:'处理反馈',complete:'完成'};
      const index=stages.indexOf(value?.progress?.stage);
      return h('section',{className:'ppt-task', 'aria-label':'PPT 工作进度'},
        h('style',null,`.ppt-task{--ppt-bg:var(--dsw-alias-bg-layer-1,#fff);--ppt-soft:var(--dsw-alias-bg-layer-2,#f6f6f7);--ppt-ink:var(--dsw-alias-label-primary,#202123);--ppt-muted:var(--dsw-alias-label-secondary,#777980);--ppt-line:var(--dsw-alias-border-primary,#e5e6e8);color:var(--ppt-ink);font:inherit;max-width:780px;margin:10px 0;padding:16px 0}.ppt-task *{box-sizing:border-box}.ppt-task .ppt-head{display:flex;align-items:center;gap:9px;font-size:14px}.ppt-task .ppt-dot{width:7px;height:7px;border-radius:50%;background:#81848b;flex-shrink:0}.ppt-task .ppt-dot.done{background:#26845b}.ppt-task .ppt-dot.busy{animation:ppt-pulse 1.8s ease-in-out infinite}.ppt-task .ppt-label{color:var(--ppt-muted);font-size:12px;margin-left:auto}.ppt-task .ppt-description{font-size:14px;line-height:1.65;margin:12px 0;color:var(--ppt-muted)}.ppt-task .ppt-progress{margin:10px 0 16px;font-size:12px;color:var(--ppt-muted)}.ppt-task summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:6px}.ppt-task summary::-webkit-details-marker{display:none}.ppt-task summary:before{content:'›';font-size:16px}.ppt-task details[open]>summary:before{transform:rotate(90deg)}.ppt-task .ppt-stages{display:flex;flex-wrap:wrap;gap:8px 20px;padding:12px 0}.ppt-task .ppt-stage.current{color:var(--ppt-ink)}.ppt-task .ppt-delivery{border:1px solid var(--ppt-line);border-radius:14px;overflow:hidden;display:flex;background:var(--ppt-bg);margin-top:16px}.ppt-task .ppt-cover{display:block;width:210px;max-width:100%;aspect-ratio:16/9;object-fit:contain;background:var(--ppt-soft);border-right:1px solid var(--ppt-line)}.ppt-task .ppt-content{padding:18px;display:flex;flex-direction:column;justify-content:center;gap:9px;min-width:0}.ppt-task .ppt-title{font-size:16px;font-weight:600}.ppt-task .ppt-meta{font-size:12px;color:var(--ppt-muted)}.ppt-task .ppt-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:3px}.ppt-task .ppt-action{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--ppt-line);border-radius:8px;padding:7px 12px;background:var(--ppt-bg);color:var(--ppt-ink);text-decoration:none;font:inherit;font-size:12px;cursor:pointer}.ppt-task .ppt-action:hover{background:var(--ppt-soft)}.ppt-task .ppt-action:focus-visible,.ppt-task summary:focus-visible{outline:2px solid #90939a;outline-offset:3px}.ppt-task .ppt-primary{background:var(--ppt-ink);color:var(--ppt-bg);border-color:var(--ppt-ink)}.ppt-task .ppt-primary:hover{opacity:.86;background:var(--ppt-ink)}.ppt-task .ppt-preview{margin-top:14px;font-size:12px;color:var(--ppt-muted)}.ppt-task .ppt-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;padding-top:12px}.ppt-task .ppt-thumb{display:block;text-decoration:none;color:var(--ppt-muted)}.ppt-task .ppt-thumb img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:var(--ppt-soft);border:1px solid var(--ppt-line);border-radius:7px}.ppt-task .ppt-thumb span{display:block;margin-top:5px}.ppt-task .ppt-reply{white-space:pre-wrap;font-size:14px;line-height:1.75;margin:14px 0}.ppt-task .ppt-foot{font-size:12px;color:var(--ppt-muted);margin:12px 0 0}.ppt-task .ppt-error{font-size:13px;color:#b25148;line-height:1.6}@keyframes ppt-pulse{50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.ppt-task .ppt-dot.busy{animation:none}}@media(max-width:580px){.ppt-task .ppt-delivery{flex-direction:column}.ppt-task .ppt-cover{width:100%;border-right:0;border-bottom:1px solid var(--ppt-line)}}`),
        h('div',{className:'ppt-head'},h('span',{className:'ppt-dot '+(active?'busy':value?.status==='completed'?'done':'')}),h('strong',null,'PPT Agent'),h('span',{className:'ppt-label'},labels[value?.status]||'连接中')),
        h('p',{className:'ppt-description',role:'status','aria-live':'polite'},value?.progress?.summary||'正在准备你的任务。'),
        h('details',{className:'ppt-progress',open:active},h('summary',null,'工作进度'),h('div',{className:'ppt-stages'},...stages.map((s,i)=>h('span',{key:s,className:'ppt-stage '+(s===value?.progress?.stage?'current':'')},`${index>=0&&i<index?'✓ ':i===index&&active?'◦ ':''}${stageNames[s]}`)))),
        value?.reply&&h('p',{className:'ppt-reply'},value.reply),
        value?.failure&&h('p',{className:'ppt-error'},value.failure),
        active&&h('button',{className:'ppt-action',disabled:pending,onClick:stop},pending?'正在停止…':'停止'),
        pptx&&h('div',{className:'ppt-delivery'},images[0]&&h('img',{className:'ppt-cover',alt:'PPT 封面预览',src:images[0].download_url+'&inline=1'}),
          h('div',{className:'ppt-content'},h('div',{className:'ppt-title'},value.kind==='feedback'?'当前科研汇报稿':'科研汇报 PPT'),h('div',{className:'ppt-meta'},`${delivery.slides} 页 · 可编辑 PPTX${delivery.version?' · 修订版':''}`),
            h('div',{className:'ppt-actions'},h('a',{className:'ppt-action ppt-primary',href:pptx.download_url,download:'research-ppt.pptx',onClick:()=>setDownloaded(true)},downloaded?'已开始下载':'下载 PPTX'),pdf&&h('a',{className:'ppt-action',href:pdf.download_url+'&inline=1',target:'_blank',rel:'noopener'},'查看 PDF')))),
        images.length>0&&h('details',{className:'ppt-preview'},h('summary',null,`预览全部 ${images.length} 页`),h('div',{className:'ppt-gallery'},...images.map((a,i)=>h('a',{key:a.id,className:'ppt-thumb',href:a.download_url+'&inline=1',target:'_blank',rel:'noopener'},h('img',{loading:'lazy',alt:`第 ${i+1} 页`,src:a.download_url+'&inline=1'}),h('span',null,`第 ${i+1} 页`))))),
        pptx&&h('p',{className:'ppt-foot'},'继续在聊天中提问，或指定页码修改这份稿件。'),
        error&&h('p',{role:'alert',className:'ppt-error'},error));
    }
    function options(value, page) {
      const current = value.selection;
      if (page === 'root') {
        const scene = value.scenes.find(row => row.id === value.selection.scene);
        return [
          { id: 'page:scenes', label: 'Scenes', detail: `${scene?.label || 'Current runtime'}  ›` },
          { id: 'page:modes', label: 'Mode', detail: `${modeLabel(current.mode)}  ›` },
          { id: 'page:rsi', label: 'RSI', detail: `${current.rsi ? 'On' : 'Off'}  ›` },
        ];
      }
      if (page === 'scenes') return [
        { id: 'page:root', label: '‹ Back', detail: 'Harless' },
        ...value.scenes.map(scene => ({
          id: `scene:${scene.id}`, label: scene.label,
          detail: scene.available === false ? `Unavailable: ${scene.unavailable_reason}` : 'Use this scenario',
          active: current.scene === scene.id,
        })),
      ];
      if (page === 'modes') return [
        { id: 'page:root', label: '‹ Back', detail: 'Harless' },
        ...[
          ['baseline', 'Origin', 'Standard Harness execution'],
          ['shadow', 'Shadow', 'Observe RSI candidates'],
          ['execute', 'Execute', 'Run certified motifs'],
        ].map(([id, label, detail]) => ({ id: `mode:${id}`, label, detail,
          active: current.mode === id })),
      ];
      return [
        { id: 'page:root', label: '‹ Back', detail: 'Harless' },
        { id: 'rsi:on', label: 'On', detail: 'Enable RSI', active: current.rsi },
        { id: 'rsi:off', label: 'Off', detail: 'Use standard Harness', active: !current.rsi },
      ];
    }
    function HarlessStatus({ sessionId }) {
      const [value, setValue] = React.useState(null);
      React.useEffect(() => {
        let live = true;
        const listener = (next) => { if (live) setValue(next); };
        const group = observers.get(sessionId) || new Set();
        group.add(listener);
        observers.set(sessionId, group);
        settings({ sessionId }).then(listener).catch(() => { if (live) setValue(null); });
        return () => {
          live = false;
          group.delete(listener);
          if (!group.size) observers.delete(sessionId);
        };
      }, [sessionId]);
      const scene = value?.scenes.find(row => row.id === value.selection.scene);
      const detail = value ? (value.ppt_native_chat && scene?.id === 'ppt'
        ? [scene.label, '发送后自动制作']
        : [scene?.label, modeLabel(value.selection.mode), `RSI ${value.selection.rsi ? 'On' : 'Off'}`]).filter(Boolean).join(' · ') : '';
      const label = detail ? `Harless · ${detail}` : 'Harless';
      return React.createElement('span', {
        role: 'status', 'aria-label': label, title: label,
        style: { display: 'inline-flex', alignItems: 'center', gap: '5px', maxWidth: 'min(360px, 52vw)', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap', borderRadius: '999px', padding: '2px 9px',
          background: 'var(--dsw-alias-bg-layer-2, #f1f3f6)',
          color: 'var(--dsw-alias-label-primary, #1f2937)', fontSize: '13px', lineHeight: '20px' },
      }, React.createElement('strong', { style: { fontWeight: 700 } }, 'Harless'),
      detail && React.createElement('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, `· ${detail}`));
    }
    function apply(ctx) {
      const command = ctx.get('commandUi');
      const sessions = ctx.get('sessions');
      function openPage(page, session) {
        const scope = sessions.scope(session.sessionId);
        if (!scope) throw Error('Harless session is no longer available');
        const popup = command.popupFor(scope);
        // Preserve the native command token across submenu transitions so the
        // final choice consumes exactly the token that opened the first menu.
        const segment = popup.binding?.segment;
        if (!segment) throw Error('Harless menu is no longer open');
        popup.open('harless', menu(page), session, segment);
      }
      function menu(page) {
        return {
          kind: 'popupSelect',
          options: async (session, signal) => {
            const value = await settings(session, signal);
            publish(session.sessionId, value);
            return options(value, page);
          },
          onSelect: async (option, session) => {
            const [kind, id] = option.id.split(':', 2);
            if (kind === 'page' && ['root', 'scenes', 'modes', 'rsi'].includes(id)) {
              openPage(id, session);
              return;
            }
            let value;
            if (kind === 'scene') {
              value = await select(session, { scene: id });
            } else if (kind === 'mode' && ['baseline', 'shadow', 'execute'].includes(id)) {
              value = await select(session, { mode: id });
            } else if (kind === 'rsi' && ['on', 'off'].includes(id)) {
              value = await select(session, { rsi: id === 'on' });
            } else throw Error('Unknown Harless option');
            publish(session.sessionId, value);
          },
        };
      }
      ctx.effect(() => command.decorate({
        name: 'harless', available: () => true,
        ui: menu('root'),
      }), 'harless: native command picker');
      ctx.slots.inject('conversation.input.left', () => ctx.slots.register(
        { name: 'conversation.input.left', id: 'harless-status', order: 40,
          inject: sessionId => ({ sessionId }) }, HarlessStatus));
      ctx.slots.inject('conversation.chat.commandview', () => ctx.slots.register(
        {name:'conversation.chat.commandview',key:'ppt-agent',inject:sessionId=>({sessionId})},PptChatCard));
    }
    return { inject, apply };
  },
});
