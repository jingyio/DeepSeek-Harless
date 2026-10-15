/* Native workspace directory-flow replacement: ask for a name, never a host path. */
(() => {
  const installed = new WeakSet();
  window.__installGeneLoopWorkspaces = (ctx, React, primitives) => {
    if (installed.has(ctx)) return;
    installed.add(ctx);
    const h = React.createElement;
    const style = document.createElement('style');
    style.textContent = `.geneloop-workspace-modal{width:min(440px,calc(100vw - 32px))!important;padding:24px!important}.geneloop-workspace-form{display:flex;flex-direction:column;gap:12px;color:var(--dsw-alias-label-primary)}.geneloop-workspace-form h2{margin:0;font-size:20px;font-weight:600}.geneloop-workspace-form p{margin:0;color:var(--dsw-alias-label-secondary);font-size:13px;line-height:1.6}.geneloop-workspace-form label{font-size:13px;margin-top:8px}.geneloop-workspace-form input{box-sizing:border-box;width:100%;height:44px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;padding:10px 12px;background:var(--dsw-alias-bg-base);color:inherit;font:inherit}.geneloop-workspace-form input:focus-visible{outline:2px solid #5f9a96;outline-offset:2px}.geneloop-workspace-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:8px}.geneloop-workspace-actions button{font:inherit;font-size:14px;min-height:38px;padding:8px 18px;border:1px solid var(--dsw-alias-border-l2);border-radius:9px;cursor:pointer;background:transparent;color:inherit}.geneloop-workspace-actions .primary{background:#2d6369;border-color:#2d6369;color:white}.geneloop-workspace-actions button:disabled{opacity:.55;cursor:wait}.geneloop-workspace-actions button:focus-visible{outline:2px solid #5f9a96;outline-offset:2px}.geneloop-workspace-form .error{color:var(--dsw-alias-state-error-primary);font-size:13px;line-height:1.5}`;
    document.head.append(style);
    ctx.effect(() => () => { style.remove(); installed.delete(ctx); }, 'geneloop-managed-workspace-style');
    function NameFlow({ open, busy, onPicked, onCancel }) {
      const [name, setName] = React.useState('');
      const [pending, setPending] = React.useState(false);
      const [error, setError] = React.useState('');
      const requestId = React.useRef('');
      const submittedName = React.useRef('');
      const active = React.useRef(false);
      const fieldId = React.useId();
      React.useEffect(() => {
        active.current = open;
        if (open) { requestId.current = crypto.randomUUID(); submittedName.current = ''; setName(''); setError(''); setPending(false); }
        return () => { active.current = false; };
      }, [open]);
      const locked = pending || busy;
      const close = () => { if (!locked) onCancel(); };
      const submit = async event => {
        event.preventDefault();
        if (locked || !name.trim()) return;
        if (submittedName.current && submittedName.current !== name.trim()) requestId.current = crypto.randomUUID();
        submittedName.current = name.trim();
        setPending(true); setError('');
        try {
          const response = await fetch('/api/harless/workspaces', { method: 'POST', credentials: 'same-origin',
            cache: 'no-store', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim(), request_id: requestId.current }) });
          if (response.status === 401) throw Error('登录已过期，请重新登录后创建工作区。');
          let result;
          try { result = await response.json(); } catch { throw Error('连接暂时中断，请重试。'); }
          if (!response.ok || !result.workspace?.path) throw Error(result.error?.message || '工作区暂时无法创建，请重试。');
          if (active.current) await onPicked(result.workspace.path);
        } catch (failure) {
          if (active.current) setError(failure instanceof TypeError ? '连接暂时中断，名称已保留，请重试。' : failure.message);
        } finally { if (active.current) setPending(false); }
      };
      return h(primitives.Modal, { open, onClose: close, title: '新建工作区', headless: true, className: 'geneloop-workspace-modal' },
        h('form', { className: 'geneloop-workspace-form', onSubmit: submit },
          h('h2', null, '新建工作区'),
          h('p', null, '为课题或项目取一个名称。对话和文件会保存在你的独立工作区中。'),
          h('label', { htmlFor: fieldId }, '工作区名称'),
          h('input', { id: fieldId, value: name, autoFocus: true, maxLength: 64, required: true, disabled: locked,
            placeholder: '例如：毕业论文', autoComplete: 'off',
            onChange: event => { setName(event.target.value); setError(''); },
            onKeyDown: event => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); } }),
          error ? h('div', { className: 'error', role: 'alert' }, error) : null,
          h('div', { className: 'geneloop-workspace-actions' },
            h('button', { type: 'button', disabled: locked, onClick: close }, '取消'),
            h('button', { type: 'submit', className: 'primary', disabled: locked || !name.trim() }, locked ? '正在创建…' : '创建工作区'))));
    }
    ctx.slots.inject('conversation.hero.workspace.directoryFlow', () => ctx.slots.inject('sidebar.workspaces.directoryFlow', function* () {
      for (const name of ['conversation.hero.workspace.directoryFlow', 'sidebar.workspaces.directoryFlow']) {
        // The renderer supplies owner props at render time. `inject` runs once
        // with no arguments and is only for additional plugin dependencies.
        yield ctx.slots.register({ name, priority: -100 }, NameFlow);
      }
    }));
    // The native browser treats a workspace click as expand-only and exposes
    // host cwd in its hover card. This user-facing browser consumes identities
    // and names exclusively, using the same public workspace/session services.
    const workspaces = ctx.get?.('workspaces'), sessions = ctx.get?.('sessions');
    const navigation = ctx.get?.('uiWorkspace'), layout = ctx.get?.('layout');
    if (!workspaces || !sessions || !navigation) return;
    let selected, navigating = 0, creating = false, notice = '';
    const listeners = new Set();
    const notify = () => { for (const fn of listeners) fn(); };
    const subscription = fn => { listeners.add(fn); return () => listeners.delete(fn); };
    const setNotice = value => { notice = value; notify(); };
    const currentGroup = () => workspaces.list.getSnapshot().items.find(row => row.sessionIds.includes(sessions.list.getSnapshot().current))?.workspaceId;
    selected = currentGroup();
    let lastCurrent = sessions.list.getSnapshot().current;
    ctx.effect(() => sessions.list.subscribe(() => {
      const current = sessions.list.getSnapshot().current;
      if (current && current !== lastCurrent) { selected = currentGroup(); lastCurrent = current; notify(); }
    }), 'geneloop-selected-workspace');
    const originalStart = navigation.startSession;
    // These stores use `this`; passing their methods directly to React loses it.
    const workspaceSource = { subscribe: fn => workspaces.list.subscribe(fn), snapshot: () => workspaces.list.getSnapshot() };
    const sessionSource = { subscribe: fn => sessions.list.subscribe(fn), snapshot: () => sessions.list.getSnapshot() };
    const start = async workspaceId => {
      if (creating) return;
      const target = workspaceId ?? selected ?? currentGroup();
      if (target && !workspaces.list.getSnapshot().items.some(row => row.workspaceId === target)) {
        selected = undefined; setNotice('此工作区已移除，请重新选择。'); return;
      }
      const generation = ++navigating; creating = true; setNotice('');
      try {
        const id = await sessions.create(target ? { workspaceId: target } : {});
        if (generation === navigating) { selected = target; sessions.open(id); layout?.selectPanel(null); }
      } catch { setNotice('新会话暂时无法创建，请重试。'); }
      finally { creating = false; notify(); }
    };
    navigation.startSession = workspaceId => { void start(workspaceId); };
    ctx.effect(() => () => { navigation.startSession = originalStart; navigating++; }, 'geneloop-new-session-target');
    function Browser({ wide = true }) {
      const ws = React.useSyncExternalStore(workspaceSource.subscribe, workspaceSource.snapshot);
      const list = React.useSyncExternalStore(sessionSource.subscribe, sessionSource.snapshot);
      const selectedId = React.useSyncExternalStore(subscription, () => selected);
      const status = React.useSyncExternalStore(subscription, () => notice);
      const [expandedGroups, setExpandedGroups] = React.useState(new Set(selected ? [selected] : []));
      React.useEffect(() => { if (selectedId) setExpandedGroups(old => new Set([...old, selectedId])); }, [selectedId]);
      const [query, setQuery] = React.useState(''), [adding, setAdding] = React.useState(false);
      const [editing, setEditing] = React.useState(null), [name, setName] = React.useState(''), [saving, setSaving] = React.useState(false);
      const error = message => setNotice(message);
      const visible = row => !ws.archivedSessionIds.includes(row.id) && (!query || (row.title || row.displayTitle || '新会话').toLowerCase().includes(query.toLowerCase()));
      const open = id => { navigating++; sessions.open(id); layout?.selectPanel(null); };
      const edit = (kind, id, title) => { setName(title); setEditing({ kind, id }); setNotice(''); };
      const rename = async event => {
        event.preventDefault(); if (saving || !name.trim()) return; setSaving(true);
        try {
          if (editing.kind === 'workspace') await workspaces.rename(editing.id, name.trim());
          else {
            const result = await sessions.binding(editing.id).session.rename(name.trim());
            if (!result.ok) throw Error();
          }
          setEditing(null);
        } catch { error('名称未能保存，请检查是否重名后重试。'); }
        finally { setSaving(false); }
      };
      const row = item => h('div', { className: 'geneloop-chat-row', key: item.id },
        h('button', { className: 'geneloop-chat-name', 'aria-current': list.current === item.id ? 'page' : undefined, onClick: () => open(item.id) },
          item.blank ? '新会话' : item.title || '新会话'),
        h('button', { className: 'geneloop-row-action', 'aria-label': '重命名会话', onClick: () => edit('session', item.id, item.title || '新会话') }, '⋯'),
        h('button', { className: 'geneloop-row-action', 'aria-label': '归档会话', onClick: () => { void workspaces.archiveSession(item.id).catch(() => error('暂时无法归档，请重试。')); } }, '−'));
      const grouped = new Set(ws.items.flatMap(item => item.sessionIds));
      return h('section', { className: 'geneloop-workspaces', 'aria-label': '工作区' },
        h('div', { className: 'geneloop-workspace-heading' }, wide && h('span', null, '工作区'),
          h('button', { onClick: () => setAdding(true), 'aria-label': '新建工作区', title: '新建工作区' }, '+')),
        wide && h('input', { className: 'geneloop-workspace-search', type: 'search', 'aria-label': '搜索对话', placeholder: '搜索对话', value: query, onChange: event => setQuery(event.target.value) }),
        status && h('p', { role: 'alert' }, status),
        wide && h('div', { className: 'geneloop-workspace-list' }, ws.items.map(item => {
          const children = item.sessionIds.map(id => list.byId[id]).filter(Boolean).filter(visible);
          if (query && !children.length && !item.title.toLowerCase().includes(query.toLowerCase())) return null;
          const expanded = Boolean(query) || expandedGroups.has(item.workspaceId);
          return h('section', { key: item.workspaceId, 'aria-label': item.title },
            h('div', { className: 'geneloop-workspace-row', 'data-selected': selectedId === item.workspaceId },
              h('button', { className: 'geneloop-workspace-toggle', 'aria-label': (expanded ? '收起 ' : '展开 ') + item.title, 'aria-expanded': expanded,
                onClick: () => setExpandedGroups(old => { const next = new Set(old); expanded ? next.delete(item.workspaceId) : next.add(item.workspaceId); return next; }) }, expanded ? '▾' : '▸'),
              h('button', { className: 'geneloop-workspace-name', 'aria-pressed': selectedId === item.workspaceId,
                onClick: () => { navigating++; selected = item.workspaceId; notify(); setExpandedGroups(old => new Set([...old, item.workspaceId])); } }, item.title),
              h('button', { className: 'geneloop-row-action', 'aria-label': '重命名工作区 ' + item.title, onClick: () => edit('workspace', item.workspaceId, item.title) }, '⋯'),
              h('button', { className: 'geneloop-row-action', 'aria-label': '在“' + item.title + '”中新建会话', onClick: () => { void start(item.workspaceId); } }, '+')),
            expanded && children.map(row));
        }), list.ids.map(id => list.byId[id]).filter(item => item && !grouped.has(item.id) && visible(item)).map(row)),
        h(NameFlow, { open: adding, busy: false, onCancel: () => setAdding(false), onPicked: async path => {
          try { const workspace = await workspaces.create({ path }); selected = workspace.workspaceId; notify(); setAdding(false); void start(selected); }
          catch { error('工作区已保存，列表更新暂时失败，请重试。'); }
        } }),
        h(primitives.Modal, { open: Boolean(editing), onClose: () => { if (!saving) setEditing(null); }, title: '修改名称', headless: true, className: 'geneloop-workspace-modal' },
          h('form', { className: 'geneloop-workspace-form', onSubmit: rename }, h('h2', null, '修改名称'),
            h('input', { 'aria-label': '名称', autoFocus: true, value: name, maxLength: 64, onChange: event => setName(event.target.value) }),
            h('div', { className: 'geneloop-workspace-actions' }, h('button', { type: 'button', disabled: saving, onClick: () => setEditing(null) }, '取消'),
              h('button', { type: 'submit', className: 'primary', disabled: saving || !name.trim() }, saving ? '保存中…' : '保存')))));
    }
    style.textContent += `.geneloop-workspaces{display:flex;flex-direction:column;min-height:0;flex:1;color:var(--dsw-alias-label-primary);font-size:14px}.geneloop-workspace-heading{display:flex;align-items:center;justify-content:space-between;color:var(--dsw-alias-label-secondary);padding:8px}.geneloop-workspaces button{font:inherit;color:inherit;cursor:pointer;border:0;background:none;border-radius:8px}.geneloop-workspaces button:focus-visible{outline:2px solid #6e95ed}.geneloop-workspace-heading button{font-size:23px;width:30px;height:30px}.geneloop-workspace-list{overflow-y:auto;flex:1;min-height:0}.geneloop-workspace-list>section{margin:5px 0}.geneloop-workspace-row,.geneloop-chat-row{display:flex;align-items:center;border-radius:8px;min-height:36px}.geneloop-workspace-row[data-selected=true]{color:var(--dsw-alias-state-business-primary,#729cf7);background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-name,.geneloop-chat-name{flex:1;min-width:0;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:8px 4px}.geneloop-chat-name{padding-left:26px!important}.geneloop-chat-row:has([aria-current=page]){background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-toggle{width:22px;flex-shrink:0}.geneloop-row-action{opacity:0;width:25px;height:28px;flex-shrink:0}.geneloop-workspace-row:hover .geneloop-row-action,.geneloop-chat-row:hover .geneloop-row-action,.geneloop-row-action:focus-visible{opacity:1}.geneloop-workspaces button:hover{background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-search{box-sizing:border-box;width:calc(100% - 12px);margin:0 6px 8px;padding:7px 10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:transparent;color:inherit;font:inherit}.geneloop-workspaces p[role=alert]{font-size:12px;line-height:1.5;padding:0 8px;color:var(--dsw-alias-state-error-primary)}`;
    ctx.slots.inject('sidebar.workspaces', () => ctx.slots.register({ name: 'sidebar.workspaces', priority: -100 }, Browser));
  };
})();
