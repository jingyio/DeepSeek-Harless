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
          if (active.current) onPicked(result.workspace.path);
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
  };
})();
