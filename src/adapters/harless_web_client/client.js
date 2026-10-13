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
    async function selectOptions(session, options) {
      const response=await fetch(endpoint,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action:'set_scene_options',session_id:session.sessionId,options})});
      const value=await response.json();
      if(!response.ok || value.error)throw Error(value.error?.message || 'Could not save task options');
      return value;
    }
    const modeLabel = mode => mode === 'baseline' ? 'Origin' : mode[0].toUpperCase() + mode.slice(1);
    function options(value, page) {
      const current = value.selection;
      if (page === 'root') {
        const scene = value.scenes.find(row => row.id === value.selection.scene);
        return [
          { id: 'page:scenes', label: 'Scenes', detail: `${scene?.label || 'Current runtime'}  ›` },
          { id: 'page:modes', label: 'Mode', detail: `${modeLabel(current.mode)}  ›` },
          { id: 'page:rsi', label: 'RSI', detail: `${current.rsi ? 'On' : 'Off'}  ›` },
          ...(value.scene_option_fields?.length ? [{id:'page:options',label:'PPT 任务选项',detail:'仅用于下一项任务  ›'}] : []),
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
      if(page==='options')return [{id:'page:root',label:'‹ Back',detail:'Harless'},
        ...(value.scene_option_fields || []).flatMap(field=>field.values.map(choice=>({
          id:`option:${field.key}=${JSON.stringify(choice.value)}`,label:choice.label,detail:choice.detail || field.label,
          active:(value.scene_options?.[field.key] ?? field.default)===choice.value})))];
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
      const detail = value ? [scene?.label, modeLabel(value.selection.mode),
        `RSI ${value.selection.rsi ? 'On' : 'Off'}`].filter(Boolean).join(' · ') : '';
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
            if (kind === 'page' && ['root', 'scenes', 'modes', 'rsi','options'].includes(id)) {
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
            } else if(kind==='option'){
              const current=await settings(session);
              const split=id.indexOf('='),key=id.slice(0,split),selected=JSON.parse(id.slice(split+1));
              const field=current.scene_option_fields?.find(row=>row.key===key);
              if(!field || !field.values.some(row=>row.value===selected))throw Error('Unsupported task option');
              value=await selectOptions(session,{...current.scene_options,[key]:selected});
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
    }
    return { inject, apply };
  },
});
