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
    let selected, navigating = 0, creating = false, notice = '', contextMenu = null;
    const listeners = new Set();
    const notify = () => { for (const fn of listeners) fn(); };
    const subscription = fn => { listeners.add(fn); return () => listeners.delete(fn); };
    const setNotice = value => { notice = value; notify(); };
    const setMenu = value => { contextMenu = value; notify(); };
    const openMenu = (event, kind, id, title) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      setMenu(contextMenu?.id === id && contextMenu.kind === kind ? null : { kind, id, title, trigger: event.currentTarget,
        left: Math.max(8, Math.min(bounds.right - 208, window.innerWidth - 224)), top: Math.max(8, Math.min(bounds.bottom + 4, window.innerHeight - 240)) });
    };
    const currentGroup = () => workspaces.list.getSnapshot().items.find(row => row.sessionIds.includes(sessions.list.getSnapshot().current))?.workspaceId;
    selected = currentGroup();
    let lastCurrent = sessions.list.getSnapshot().current;
    ctx.effect(() => sessions.list.subscribe(() => {
      const current = sessions.list.getSnapshot().current;
      if (current && current !== lastCurrent) { selected = currentGroup(); lastCurrent = current; notify(); }
    }), 'geneloop-selected-workspace');
    const originalStart = navigation.startSession;
    const openSession = id => { navigating++; sessions.open(id); layout?.selectPanel(null); };
    // These stores use `this`; passing their methods directly to React loses it.
    const workspaceSource = { subscribe: fn => workspaces.list.subscribe(fn), snapshot: () => workspaces.list.getSnapshot() };
    const sessionSource = { subscribe: fn => sessions.list.subscribe(fn), snapshot: () => sessions.list.getSnapshot() };
    const publicSession = row => row && row.projectionValues?.harlessComparisonLane !== true && row.origin !== 'subagent';
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
    const icon = (name, size = 18) => h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.65,
      strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, focusable: false },
      ...(name === 'folder' ? [h('path', { key: 1, d: 'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v1' }), h('path', { key: 2, d: 'M3 7h5l2 2h10a1 1 0 0 1 1 1.3l-2 8a2 2 0 0 1-2 1.7H5a2 2 0 0 1-2-2V7Z' })]
      : name === 'compose' ? [h('path', { key: 1, d: 'M14 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-9M16 3l5 5M10 14l2-6 6-6 5 5-6 6-7 1Z' })]
      : name === 'search' ? [h('circle', { key: 1, cx: 10.5, cy: 10.5, r: 6.5 }), h('path', { key: 2, d: 'm16 16 5 5' })]
      : name === 'pin' ? [h('path', { key: 1, d: 'm15 3 6 6-4 1-3 5-2-2-5 5-1-1 5-5-2-2 5-3 1-4Z' })]
      : [h('path', { key: 1, d: 'M12 5v14M5 12h14' })]));
    function ActionMenu({ menu, close, children }) {
      const ref = React.useRef(null);
      React.useEffect(() => {
        if (!menu) return;
        ref.current?.querySelector('[role="menuitem"]')?.focus();
        const outside = event => { if (!ref.current?.contains(event.target) && !menu.trigger?.contains(event.target)) close(false); };
        document.addEventListener('pointerdown', outside);
        const dismiss = () => close(false);
        window.addEventListener('resize', dismiss);
        return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', dismiss); };
      }, [menu]);
      if (!menu) return null;
      return h('div', { className: 'geneloop-workspace-menu', role: 'menu', 'aria-label': menu.title + '的操作', ref,
        style: { left: menu.left, top: menu.top }, onKeyDown: event => {
          if (event.key === 'Escape') { event.preventDefault(); close(true); }
          else if (event.key === 'Tab') close(false);
          else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault(); const items = [...ref.current.querySelectorAll('[role="menuitem"]:not(:disabled)')];
            const index = items.indexOf(document.activeElement), next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
            items[next]?.focus();
          }
        } }, children);
    }
    function Browser({ wide = true }) {
      const ws = React.useSyncExternalStore(workspaceSource.subscribe, workspaceSource.snapshot);
      const list = React.useSyncExternalStore(sessionSource.subscribe, sessionSource.snapshot);
      const selectedId = React.useSyncExternalStore(subscription, () => selected);
      const status = React.useSyncExternalStore(subscription, () => notice);
      const [expandedGroups, setExpandedGroups] = React.useState(new Set(selected ? [selected] : []));
      React.useEffect(() => { if (selectedId) setExpandedGroups(old => new Set([...old, selectedId])); }, [selectedId]);
      const [query, setQuery] = React.useState(''), [searching, setSearching] = React.useState(false), [adding, setAdding] = React.useState(false);
      const [editing, setEditing] = React.useState(null), [name, setName] = React.useState(''), [saving, setSaving] = React.useState(false);
      const menu = React.useSyncExternalStore(subscription, () => contextMenu);
      const [removing, setRemoving] = React.useState(null), [pinned, setPinned] = React.useState([]);
      const [pinning, setPinning] = React.useState(false), [showArchived, setShowArchived] = React.useState(false);
      const preferenceVersion = React.useRef(0);
      React.useEffect(() => {
        let active = true; const version = preferenceVersion.current;
        fetch('/api/harless/workspaces/preferences', { credentials: 'same-origin', cache: 'no-store' })
          .then(async response => { if (!response.ok) throw Error(); return response.json(); })
          .then(value => { if (active && version === preferenceVersion.current) setPinned(value.pinned_workspace_ids || []); })
          .catch(() => { if (active) setNotice('置顶设置暂时未加载，可在工作区菜单中重试。'); });
        return () => { active = false; };
      }, []);
      const error = message => setNotice(message);
      const visible = row => publicSession(row) && !ws.archivedSessionIds.includes(row.id) && (!query || (row.title || row.displayTitle || '新会话').toLowerCase().includes(query.toLowerCase()));
      const open = openSession;
      const edit = (kind, id, title) => { setMenu(null); setName(title); setEditing({ kind, id }); setNotice(''); };
      const closeMenu = restore => { if (restore) menu?.trigger?.focus(); setMenu(null); };
      const togglePin = async () => {
        if (pinning) return; preferenceVersion.current++; setPinning(true); setNotice('');
        try {
          const response = await fetch('/api/harless/workspaces/preferences', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workspace_id: menu.id, pinned: !pinned.includes(menu.id) }) });
          if (!response.ok) throw Error(); const value = await response.json(); setPinned(value.pinned_workspace_ids || []); closeMenu(true);
        } catch { error('置顶设置未能保存，请重新打开工作区菜单重试。'); }
        finally { setPinning(false); }
      };
      const remove = async () => {
        if (saving || !removing) return; setSaving(true); setNotice('');
        try {
          await workspaces.delete(removing.workspaceId);
          if (selected === removing.workspaceId) { selected = undefined; notify(); }
          setPinned(old => old.filter(id => id !== removing.workspaceId)); setRemoving(null);
        } catch { error('工作区未能删除，对话和文件保持原样，请重试。'); }
        finally { setSaving(false); }
      };
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
        h('button', { className: 'geneloop-row-action', 'aria-label': '会话操作 ' + (item.title || '新会话'), 'aria-haspopup': 'menu',
          'aria-expanded': menu?.kind === 'session' && menu.id === item.id, onClick: event => openMenu(event, 'session', item.id, item.title || '新会话') }, '⋯'));
      const grouped = new Set(ws.items.flatMap(item => item.sessionIds));
      const ordered = [...ws.items].sort((a, b) => Number(pinned.includes(b.workspaceId)) - Number(pinned.includes(a.workspaceId)));
      const ungrouped = list.ids.map(id => list.byId[id]).filter(item => item && !grouped.has(item.id) && visible(item));
      return h('section', { className: 'geneloop-workspaces', 'aria-label': '工作区' },
        h('div', { className: 'geneloop-workspace-heading' }, wide && h('span', null, '工作区'),
          h('span', { className: 'geneloop-workspace-heading-actions' },
            wide && h('button', { onClick: () => { setSearching(!searching); setQuery(''); }, 'aria-label': searching ? '关闭搜索' : '搜索对话', 'aria-expanded': searching }, icon('search')),
            h('button', { onClick: () => setAdding(true), 'aria-label': '新建工作区' }, icon('plus')))),
        wide && searching && h('input', { className: 'geneloop-workspace-search', type: 'search', 'aria-label': '搜索对话', placeholder: '搜索对话', autoFocus: true, value: query, onChange: event => setQuery(event.target.value) }),
        status && h('p', { role: 'alert' }, status),
        wide && h('div', { className: 'geneloop-workspace-list' }, ordered.map(item => {
          const children = item.sessionIds.map(id => list.byId[id]).filter(Boolean).filter(visible);
          if (query && !children.length && !item.title.toLowerCase().includes(query.toLowerCase())) return null;
          const expanded = Boolean(query) || expandedGroups.has(item.workspaceId);
          return h('section', { key: item.workspaceId, 'aria-label': item.title },
            h('div', { className: 'geneloop-workspace-row', 'data-selected': selectedId === item.workspaceId },
              h('button', { className: 'geneloop-workspace-toggle', 'aria-label': (expanded ? '收起 ' : '展开 ') + item.title, 'aria-expanded': expanded,
                onClick: () => setExpandedGroups(old => { const next = new Set(old); expanded ? next.delete(item.workspaceId) : next.add(item.workspaceId); return next; }) }, icon('folder', 20), h('span', { className: 'geneloop-workspace-chevron', 'aria-hidden': true }, expanded ? '⌄' : '›')),
              h('button', { className: 'geneloop-workspace-name', 'aria-pressed': selectedId === item.workspaceId,
                onClick: () => { navigating++; selected = item.workspaceId; notify(); setExpandedGroups(old => new Set([...old, item.workspaceId])); layout?.selectPanel('geneloop-workspace'); } }, item.title),
              pinned.includes(item.workspaceId) && h('span', { className: 'geneloop-workspace-pin', 'aria-label': '已置顶' }, icon('pin', 13)),
              h('button', { className: 'geneloop-row-action', 'aria-label': '工作区操作 ' + item.title, 'aria-haspopup': 'menu', 'aria-expanded': menu?.kind === 'workspace' && menu.id === item.workspaceId,
                onClick: event => openMenu(event, 'workspace', item.workspaceId, item.title) }, '⋯'),
              h('button', { className: 'geneloop-row-action', 'aria-label': '在“' + item.title + '”中新建会话', onClick: () => { void start(item.workspaceId); } }, icon('compose', 16))),
            expanded && (children.length ? children.map(row) : query ? h('p', { className: 'geneloop-workspace-empty' }, '没有匹配的对话') : h('button', { className: 'geneloop-workspace-empty', onClick: () => { void start(item.workspaceId); } }, '开始新对话')));
        }), ungrouped.length > 0 && h('div', { className: 'geneloop-ungrouped' }, h('div', { className: 'geneloop-workspace-subheading' }, '未分组'), ungrouped.map(row)),
        ws.items.length === 0 && !query && h('button', { className: 'geneloop-workspace-empty', onClick: () => setAdding(true) }, '创建第一个工作区'),
        ws.archivedSessionIds.length > 0 && h('button', { className: 'geneloop-workspace-empty', onClick: () => setShowArchived(true) }, '已归档对话')),
        h(ActionMenu, { menu, close: closeMenu }, menu?.kind === 'workspace' ? [
          h('button', { key: 'pin', role: 'menuitem', disabled: pinning, onClick: () => { void togglePin(); } }, icon('pin'), pinned.includes(menu.id) ? '取消置顶' : '置顶工作区'),
          h('button', { key: 'settings', role: 'menuitem', onClick: () => edit('workspace', menu.id, menu.title) }, '工作区设置'),
          h('hr', { key: 'separator' }), h('button', { key: 'delete', role: 'menuitem', className: 'danger', onClick: () => { setRemoving(ws.items.find(item => item.workspaceId === menu.id)); closeMenu(false); setNotice(''); } }, '删除工作区')
        ] : menu ? [
          h('button', { key: 'rename', role: 'menuitem', onClick: () => edit('session', menu.id, menu.title) }, '重命名对话'),
          h('button', { key: 'fork', role: 'menuitem', onClick: () => { const id = menu.id; closeMenu(false); void navigation.forkSession(id).catch(() => error('暂时无法创建分支，请等待本轮回复完成后重试。')); } }, '在新对话中分支'),
          h('button', { key: 'archive', role: 'menuitem', onClick: () => { const id = menu.id; closeMenu(false); void navigation.archiveSession(id).catch(() => error('暂时无法归档，请重试。')); } }, '归档对话')
        ] : null),
        h(NameFlow, { open: adding, busy: false, onCancel: () => setAdding(false), onPicked: async path => {
          try { const workspace = await workspaces.create({ path }); selected = workspace.workspaceId; notify(); setAdding(false); void start(selected); }
          catch { error('工作区已保存，列表更新暂时失败，请重试。'); }
        } }),
        h(primitives.Modal, { open: Boolean(editing), onClose: () => { if (!saving) setEditing(null); }, title: editing?.kind === 'workspace' ? '工作区设置' : '重命名对话', headless: true, className: 'geneloop-workspace-modal' },
          h('form', { className: 'geneloop-workspace-form', onSubmit: rename }, h('h2', null, editing?.kind === 'workspace' ? '工作区设置' : '重命名对话'),
            h('label', null, editing?.kind === 'workspace' ? '工作区名称' : '对话名称'),
            h('input', { 'aria-label': '名称', autoFocus: true, value: name, maxLength: 64, onChange: event => setName(event.target.value) }),
            status && h('p', { className: 'error', role: 'alert' }, status),
            h('div', { className: 'geneloop-workspace-actions' }, h('button', { type: 'button', disabled: saving, onClick: () => setEditing(null) }, '取消'),
              h('button', { type: 'submit', className: 'primary', disabled: saving || !name.trim() }, saving ? '保存中…' : '保存')))),
        h(primitives.Modal, { open: Boolean(removing), onClose: () => { if (!saving) setRemoving(null); }, title: '删除工作区', headless: true, className: 'geneloop-workspace-modal' },
          h('div', { className: 'geneloop-workspace-form' }, h('h2', null, '删除工作区“' + (removing?.title || '') + '”？'),
            h('p', null, '这会删除此工作区的分组。已有对话将移至“未分组”，对话记录和文件都会保留。'),
            status && h('p', { className: 'error', role: 'alert' }, status),
            h('div', { className: 'geneloop-workspace-actions' }, h('button', { disabled: saving, onClick: () => setRemoving(null) }, '取消'),
              h('button', { className: 'danger', disabled: saving, onClick: () => { void remove(); } }, saving ? '正在删除…' : '删除工作区')))),
        h(primitives.Modal, { open: showArchived, onClose: () => setShowArchived(false), title: '已归档对话', headless: true, className: 'geneloop-workspace-modal' },
          h('div', { className: 'geneloop-workspace-form' }, h('h2', null, '已归档对话'),
            h('div', { className: 'geneloop-archived-list' }, ws.archivedSessionIds.map(id => list.byId[id]).filter(publicSession).map(item => h('button', { key: item.id,
              className: 'geneloop-chat-name', onClick: () => { open(item.id); setShowArchived(false); } }, item.title || '新会话'))),
            h('div', { className: 'geneloop-workspace-actions' }, h('button', { onClick: () => setShowArchived(false) }, '关闭')))));
    }
    function WorkspaceHome() {
      const ws = React.useSyncExternalStore(workspaceSource.subscribe, workspaceSource.snapshot);
      const list = React.useSyncExternalStore(sessionSource.subscribe, sessionSource.snapshot);
      const selectedId = React.useSyncExternalStore(subscription, () => selected);
      const status = React.useSyncExternalStore(subscription, () => notice);
      const busy = React.useSyncExternalStore(subscription, () => creating);
      const menu = React.useSyncExternalStore(subscription, () => contextMenu);
      const workspace = ws.items.find(item => item.workspaceId === selectedId);
      if (!workspace) return h('main', { className: 'geneloop-workspace-home' }, h('h1', null, '选择工作区'),
        h('p', null, '从侧栏选择一个工作区，或开始新的对话。'), h('button', { onClick: () => { layout?.selectPanel(null); } }, '返回对话'));
      const chats = workspace.sessionIds.map(id => list.byId[id]).filter(item => publicSession(item) && !ws.archivedSessionIds.includes(item.id));
      const stamp = value => { if (!value) return ''; const date = new Date(value); return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(date) : ''; };
      return h('main', { className: 'geneloop-workspace-home', 'aria-label': workspace.title + '工作区' },
        h('header', null, icon('folder', 30), h('h1', null, workspace.title),
          h('button', { className: 'geneloop-workspace-home-menu', 'aria-label': '工作区操作 ' + workspace.title, 'aria-haspopup': 'menu',
            'aria-expanded': menu?.kind === 'workspace' && menu.id === workspace.workspaceId,
            onClick: event => openMenu(event, 'workspace', workspace.workspaceId, workspace.title) }, '⋯')),
        h('button', { className: 'geneloop-workspace-start', disabled: busy, onClick: () => { void start(workspace.workspaceId); } },
          h('span', null, busy ? '正在创建对话…' : '在“' + workspace.title + '”中新建对话'), icon('compose', 22)),
        status && h('p', { className: 'error', role: 'alert' }, status),
        h('div', { className: 'geneloop-workspace-home-heading' }, h('h2', null, '对话'), h('span', null, chats.length + ' 个')),
        chats.length ? h('div', { className: 'geneloop-workspace-home-chats' }, chats.map(item => h('button', { key: item.id, onClick: () => openSession(item.id) },
          h('span', null, item.blank ? '新会话' : item.title || '新会话'), h('time', null, stamp(item.updatedAt || item.createdAt)))))
          : h('p', { className: 'geneloop-workspace-home-empty' }, '这个工作区还没有对话。点击上方开始，文字和上传资料都可以。'));
    }
    ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: 'geneloop-workspace' }, WorkspaceHome));
    style.textContent += `.geneloop-workspaces{display:flex;flex-direction:column;min-height:0;flex:1;color:var(--dsw-alias-label-primary);font-size:14px}.geneloop-workspace-heading{display:flex;align-items:center;justify-content:space-between;color:var(--dsw-alias-label-secondary);padding:8px}.geneloop-workspaces button{font:inherit;color:inherit;cursor:pointer;border:0;background:none;border-radius:8px}.geneloop-workspaces button:focus-visible{outline:2px solid #6e95ed}.geneloop-workspace-heading button{font-size:23px;width:30px;height:30px}.geneloop-workspace-list{overflow-y:auto;flex:1;min-height:0}.geneloop-workspace-list>section{margin:5px 0}.geneloop-workspace-row,.geneloop-chat-row{display:flex;align-items:center;border-radius:8px;min-height:36px}.geneloop-workspace-row[data-selected=true]{color:var(--dsw-alias-state-business-primary,#729cf7);background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-name,.geneloop-chat-name{flex:1;min-width:0;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:8px 4px}.geneloop-chat-name{padding-left:26px!important}.geneloop-chat-row:has([aria-current=page]){background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-toggle{width:22px;flex-shrink:0}.geneloop-row-action{opacity:0;width:25px;height:28px;flex-shrink:0}.geneloop-workspace-row:hover .geneloop-row-action,.geneloop-chat-row:hover .geneloop-row-action,.geneloop-row-action:focus-visible{opacity:1}.geneloop-workspaces button:hover{background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-search{box-sizing:border-box;width:calc(100% - 12px);margin:0 6px 8px;padding:7px 10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:transparent;color:inherit;font:inherit}.geneloop-workspaces p[role=alert]{font-size:12px;line-height:1.5;padding:0 8px;color:var(--dsw-alias-state-error-primary)}`;
    style.textContent += `.geneloop-workspace-heading-actions{display:flex;gap:2px}.geneloop-workspace-heading-actions button,.geneloop-row-action{display:inline-flex;align-items:center;justify-content:center}.geneloop-workspace-row[data-selected=true]{color:inherit}.geneloop-workspace-toggle{position:relative;display:flex;align-items:center;justify-content:center;gap:1px;width:30px;height:32px;padding:0;margin-left:3px}.geneloop-workspace-toggle svg{flex-shrink:0}.geneloop-workspace-chevron{position:static;order:-1;flex-shrink:0;width:7px;font-size:12px;line-height:1;color:var(--dsw-alias-label-secondary)}.geneloop-workspace-name{padding-left:4px}.geneloop-workspace-row .geneloop-row-action{width:28px}.geneloop-chat-name{padding-left:34px!important}.geneloop-ungrouped .geneloop-chat-name{padding-left:10px!important}.geneloop-row-action[aria-expanded=true],.geneloop-workspace-row:focus-within .geneloop-row-action,.geneloop-chat-row:focus-within .geneloop-row-action{opacity:1}.geneloop-workspace-pin{display:flex;color:var(--dsw-alias-label-secondary);margin:0 3px}.geneloop-workspace-subheading{padding:20px 10px 8px;color:var(--dsw-alias-label-secondary);font-size:13px}.geneloop-workspace-empty{padding:8px 12px 8px 34px;font-size:12px!important;color:var(--dsw-alias-label-secondary)!important;text-align:left;margin:0}.geneloop-workspace-menu{position:fixed;z-index:2000;display:flex;flex-direction:column;min-width:208px;max-width:calc(100vw - 24px);padding:6px;border:1px solid var(--dsw-alias-border-l2);border-radius:12px;background:var(--dsw-alias-bg-base);box-shadow:0 8px 28px #0003;color:var(--dsw-alias-label-primary)}.geneloop-workspace-menu button{display:flex;gap:10px;align-items:center;width:100%;min-height:38px;padding:9px 12px;text-align:left;border:0;border-radius:7px;background:none;color:inherit;font:inherit;font-size:14px;cursor:pointer}.geneloop-workspace-menu button:hover,.geneloop-workspace-menu button:focus-visible{background:var(--dsw-alias-interactive-bg-hover);outline:2px solid transparent}.geneloop-workspace-menu button:focus-visible{outline-color:#6e95ed;outline-offset:-2px}.geneloop-workspace-menu hr{width:100%;margin:5px 0;border:0;border-top:1px solid var(--dsw-alias-border-l2)}.geneloop-workspace-menu .danger,.geneloop-workspace-actions .danger{color:var(--dsw-alias-state-error-primary,#ef6464)}.geneloop-workspace-menu button:disabled{opacity:.5;cursor:wait}.geneloop-archived-list{display:flex;flex-direction:column;max-height:55vh;overflow:auto}.geneloop-archived-list button{font:inherit;color:inherit;background:transparent;border:0;border-radius:8px;padding:10px!important;text-align:left;cursor:pointer}.geneloop-archived-list button:hover{background:var(--dsw-alias-interactive-bg-hover)}@media(hover:none){.geneloop-row-action{opacity:1}}`;
    style.textContent += `.geneloop-workspace-home{width:min(800px,100%);box-sizing:border-box;margin:0 auto;padding:56px 36px 40px;overflow-y:auto;height:100%;color:var(--dsw-alias-label-primary)}.geneloop-workspace-home header{display:flex;gap:15px;align-items:center;margin-bottom:30px}.geneloop-workspace-home h1{flex:1;min-width:0;margin:0;font-size:28px;line-height:1.3;font-weight:600;overflow-wrap:anywhere}.geneloop-workspace-home button{font:inherit;border:0;color:inherit;cursor:pointer;background:none;border-radius:12px}.geneloop-workspace-home button:focus-visible{outline:2px solid #6e95ed;outline-offset:3px}.geneloop-workspace-home .geneloop-workspace-start{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:24px;width:100%;min-height:100px;text-align:left;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-interactive-bg-hover);border:1px solid var(--dsw-alias-border-l2);border-radius:20px}.geneloop-workspace-start:disabled{opacity:.6;cursor:wait}.geneloop-workspace-home .geneloop-workspace-home-menu{flex-shrink:0;width:36px;height:36px;font-size:24px}.geneloop-workspace-home-menu:hover{background:var(--dsw-alias-interactive-bg-hover)}.geneloop-workspace-home-heading{display:flex;align-items:center;gap:12px;margin-top:32px;padding-bottom:12px;border-bottom:1px solid var(--dsw-alias-border-l2)}.geneloop-workspace-home-heading h2{font-size:16px;margin:0;font-weight:500}.geneloop-workspace-home-heading span,.geneloop-workspace-home time,.geneloop-workspace-home-empty{font-size:13px;color:var(--dsw-alias-label-secondary)}.geneloop-workspace-home-chats{display:flex;flex-direction:column}.geneloop-workspace-home-chats button{display:flex;align-items:center;justify-content:space-between;gap:16px;text-align:left;min-height:62px;padding:16px 12px;border-bottom:1px solid var(--dsw-alias-border-l2);border-radius:0}.geneloop-workspace-home-chats button:hover{background:var(--dsw-alias-interactive-bg-hover);border-radius:8px}.geneloop-workspace-home-chats button span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.geneloop-workspace-home time{flex-shrink:0}.geneloop-workspace-home-empty{padding-top:16px;line-height:1.6}.geneloop-workspace-home .error{color:var(--dsw-alias-state-error-primary)}@media(max-width:600px){.geneloop-workspace-home{padding:28px 18px}.geneloop-workspace-home h1{font-size:24px}.geneloop-workspace-home time{font-size:11px}}`;
    ctx.slots.inject('sidebar.workspaces', () => ctx.slots.register({ name: 'sidebar.workspaces', priority: -100 }, Browser));
  };
})();
