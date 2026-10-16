/* Account and model pages occupy public settings seats inside the native shell. */
(() => {
  const installed = new WeakSet();
  window.__installGeneLoopAccountSettings = (ctx, React) => {
    if (installed.has(ctx)) return;
    installed.add(ctx);
    ctx.effect(() => () => installed.delete(ctx), 'geneloop-account-settings-lifetime');
    const h = React.createElement;
    const request = async (path, body, signal) => {
      const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal,
        ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
      if (response.status === 401) throw Error('登录已过期，请重新登录。');
      if (response.status === 403) throw Error('当前账号没有执行此操作的权限。');
      const value = await response.json().catch(() => { throw Error('连接暂时中断，请重试。'); });
      if (!response.ok) throw Error(typeof value.error === 'string' ? value.error : '操作未完成，请重试。');
      return value;
    };
    const errorText = error => error instanceof TypeError ? '连接暂时中断，请重试。' : error.message;
    function AccountSettings() {
      const [user, setUser] = React.useState(null), [loading, setLoading] = React.useState(true), [revision, setRevision] = React.useState(0);
      const [profile, setProfile] = React.useState({ displayName: '', username: '' });
      const [password, setPassword] = React.useState({ currentPassword: '', newPassword: '', repeatPassword: '' });
      const [invitePassword, setInvitePassword] = React.useState(''), [invite, setInvite] = React.useState('');
      const [busy, setBusy] = React.useState(''), [notice, setNotice] = React.useState(null);
      const active = React.useRef(false), pending = React.useRef(false);
      React.useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
      React.useEffect(() => {
        const abort = new AbortController(); let current = true;
        setLoading(true); setNotice(null);
        request('/api/account/me', undefined, abort.signal).then(value => {
          if (!current) return;
          if (!value.user) throw Error('暂时无法读取账户，请重试。');
          setUser(value.user); setProfile({ displayName: value.user.displayName, username: value.user.username });
        }).catch(error => { if (current) setNotice({ scope: 'load', error: true, text: errorText(error) }); })
          .finally(() => { if (current) setLoading(false); });
        return () => { current = false; abort.abort(); };
      }, [revision]);
      const save = async (event, scope, body, done) => {
        event.preventDefault(); if (pending.current) return;
        pending.current = true; setBusy(scope); setNotice(null);
        try { const value = await request('/api/account/' + scope, body); if (active.current) done(value); }
        catch (error) { if (active.current) setNotice({ scope, error: true, text: errorText(error) }); }
        finally { pending.current = false; if (active.current) setBusy(''); }
      };
      const status = scope => notice?.scope === scope && h('p', { role: notice.error ? 'alert' : 'status' }, notice.text,
        notice.text.includes('重新登录') && h('a', { href: '/login' }, ' 前往登录'));
      const field = (label, props) => h('label', null, label, h('input', { required: true, disabled: !!busy, ...props }));
      if (loading) return h('section', { className: 'geneloop-settings-page', 'aria-label': '账户与安全' }, h('h2', null, '账户与安全'), h('p', { role: 'status' }, '正在加载账户…'));
      if (!user) return h('section', { className: 'geneloop-settings-page', 'aria-label': '账户与安全' }, h('h2', null, '账户与安全'), status('load'),
        h('button', { type: 'button', onClick: () => setRevision(value => value + 1) }, '重试'));
      return h('section', { className: 'geneloop-settings-page', 'aria-label': '账户与安全' }, h('h2', null, '账户与安全'),
        h('section', { className: 'geneloop-settings-section' }, h('h3', null, '个人资料'),
          h('form', { onSubmit: event => save(event, 'profile', profile, value => {
            setUser(value.user); setProfile({ displayName: value.user.displayName, username: value.user.username });
            setNotice({ scope: 'profile', text: '资料已保存。' });
          }) }, field('显示名称', { name: 'displayName', value: profile.displayName, maxLength: 40, autoComplete: 'name',
            onChange: event => setProfile({ ...profile, displayName: event.target.value }) }),
            field('用户名', { name: 'username', value: profile.username, minLength: 3, maxLength: 32, pattern: '[a-zA-Z][a-zA-Z0-9_-]{2,31}', autoComplete: 'username',
              onChange: event => setProfile({ ...profile, username: event.target.value }) }),
            h('button', { type: 'submit', disabled: !!busy }, busy === 'profile' ? '保存中…' : '保存资料')), status('profile')),
        h('section', { className: 'geneloop-settings-section' }, h('h3', null, '密码与安全'), h('p', null, '修改密码后，所有设备都需要重新登录。'),
          h('form', { onSubmit: event => {
            if (password.newPassword !== password.repeatPassword) { event.preventDefault(); setNotice({ scope: 'password', error: true, text: '两次输入的新密码不一致。' }); return; }
            void save(event, 'password', password, () => { window.location.replace('/login?changed=1'); });
          } }, ...[['currentPassword', '当前密码'], ['newPassword', '新密码'], ['repeatPassword', '确认新密码']].map(([name, label]) => field(label, {
            key: name, name, type: 'password', value: password[name], minLength: name === 'currentPassword' ? undefined : 10,
            autoComplete: name === 'currentPassword' ? 'current-password' : 'new-password', onChange: event => setPassword({ ...password, [name]: event.target.value }),
          })), h('button', { type: 'submit', disabled: !!busy }, busy === 'password' ? '修改中…' : '修改密码')), status('password')),
        user.role === 'owner' && h('section', { className: 'geneloop-settings-section' }, h('h3', null, '邀请同学'), h('p', null, '生成一次性邀请码，供受邀者自行注册。'),
          h('form', { onSubmit: event => { setInvite(''); void save(event, 'invites', { currentPassword: invitePassword, count: 1 }, value => {
            setInvite(value.codes?.[0] || ''); setInvitePassword(''); setNotice({ scope: 'invites', text: '邀请码只显示这一次，请复制并单独发送给同学。' });
          }); } }, field('确认当前密码', { name: 'currentPassword', type: 'password', autoComplete: 'current-password', value: invitePassword,
            onChange: event => setInvitePassword(event.target.value) }), h('button', { type: 'submit', disabled: !!busy }, busy === 'invites' ? '生成中…' : '生成邀请码')),
          status('invites'), invite && h('output', { 'aria-label': '新邀请码' }, invite)),
        h('section', { className: 'geneloop-settings-section' }, h('h3', null, '登录状态'), h('p', null, user.role === 'owner' ? '所有者账号' : '成员账号'),
          h('button', { type: 'button', disabled: !!busy, onClick: event => save(event, 'logout', {}, () => { window.location.replace('/login'); }) }, '退出登录'), status('logout')));
    }
    function ModelsSettings() {
      const [catalog, setCatalog] = React.useState(null), [error, setError] = React.useState(''), [revision, setRevision] = React.useState(0);
      React.useEffect(() => {
        const abort = new AbortController(); let active = true; setError(''); setCatalog(null);
        request('/api/harless/models', undefined, abort.signal).then(value => { if (active) setCatalog(value); })
          .catch(error => { if (active) setError(errorText(error)); });
        return () => { active = false; abort.abort(); };
      }, [revision]);
      return h('section', { className: 'geneloop-settings-page', 'aria-label': '模型' }, h('h2', null, '模型'),
        h('p', null, '这里显示当前账号可用的模型与推理模式。在对话输入框中选择本轮使用的模型。'),
        error ? h('div', null, h('p', { role: 'alert' }, error), h('button', { type: 'button', onClick: () => setRevision(value => value + 1) }, '重试'))
          : !catalog ? h('p', { role: 'status' }, '正在加载模型…')
            : catalog.models?.length ? catalog.models.map(model => h('article', { key: model.provider + '/' + model.model, className: 'geneloop-settings-model' },
              h('header', null, h('strong', null, model.label || model.model), h('small', null, model.available === false ? '暂不可用' :
                catalog.default?.provider === model.provider && catalog.default?.model === model.model ? '默认模型' : '可用')),
              h('ul', null, ...(model.reasoning_modes || []).map(mode => h('li', { key: mode.id }, '推理 ' + mode.label + ' · ' +
                (mode.available ? '可用' : mode.unavailable_reason || model.reasoning_unavailable || '暂不可用'))))))
              : h('p', null, '当前账号还没有可用模型，请联系管理员。'));
    }
    ctx.slots.inject('settings.section', function* () {
      yield ctx.slots.register({ name: 'settings.section', id: 'geneloop-account', order: 90, label: () => '账户与安全' }, AccountSettings);
      yield ctx.slots.register({ name: 'settings.section', id: 'models', order: 10, priority: -100, label: () => '模型' }, ModelsSettings);
    });
    // Native SettingsRoot enumerates raw registrations, including shadowed
    // pages. Preserve its shell and stores, deduplicate only the section list,
    // and mirror child seats under aliases to preserve slot ownership.
    if (ctx.slots.entries && ctx.slots.subscribe) ctx.slots.inject('sidebar.settings', () => {
      let stopShell, installing = false;
      const mirror = (source, target) => {
        let releases = [];
        const sync = () => {
          releases.reverse().forEach(dispose => dispose()); releases = [];
          for (const [index, entry] of ctx.slots.entries(source).entries()) {
            const names = Object.fromEntries(Object.keys(entry.children || {}).map(name => [name, `${target}.${index}.${name}`]));
            const children = Object.fromEntries(Object.entries(entry.children || {}).map(([name, spec]) => [names[name], spec]));
            const component = Object.keys(names).length ? props => h(entry.component, { ...props,
              renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options),
              ...(props.renderSlotChain ? { renderSlotChain: (name, owner, options) => props.renderSlotChain(names[name] || name, owner, options) } : {}),
            }) : entry.component;
            releases.push(ctx.slots.register({ name: target, ...entry.options, locale: entry.locale, inject: entry.inject,
              ...(entry.store ? { store: entry.store } : {}), ...(entry.select ? { select: entry.select } : {}),
              ...(Object.keys(children).length ? { children } : {}) }, component));
            for (const name of Object.keys(names)) releases.push(mirror(name, names[name]));
          }
        };
        sync(); const unsubscribe = ctx.slots.subscribe(source, sync);
        return () => { unsubscribe(); releases.reverse().forEach(dispose => dispose()); };
      };
      const installShell = () => {
        if (stopShell || installing) return;
        const original = ctx.slots.entries('sidebar.settings').find(entry => (entry.options.priority ?? 0) >= 0 && entry.children?.['settings.section']);
        if (!original) return;
        installing = true;
        try {
        const names = Object.fromEntries(Object.keys(original.children).map(name => [name, 'geneloop.' + name]));
        const children = Object.fromEntries(Object.entries(original.children).map(([name, spec]) => [names[name], spec]));
        const inject = (...args) => {
          const value = original.inject(...args), source = value.hooks.sections; let last, rows;
          return { ...value, hooks: { ...value.hooks, sections: { subscribe: callback => source.subscribe(callback), getSnapshot: () => {
            const next = source.getSnapshot(); if (next !== last) { last = next; const seen = new Set();
              const paths = {
                'geneloop-archived': 'M4 8h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8ZM3 3h18v5H3V3ZM9 12h6',
                'geneloop-trash': 'M4.5 6.5h15M9 6V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V6M6 7l.8 12.1A2 2 0 0 0 8.8 21h6.4a2 2 0 0 0 2-1.9L18 7M10 10v7M14 10v7',
                'geneloop-account': 'M12 3 4.5 6v5.7c0 4.2 3.1 7.5 7.5 9.3 4.4-1.8 7.5-5.1 7.5-9.3V6L12 3ZM9.5 11a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0ZM8 17c.6-1.5 2-2.3 4-2.3s3.4.8 4 2.3',
              };
              rows = next.filter(row => !seen.has(row.id) && seen.add(row.id)).map(row => !paths[row.id] ? row : { ...row,
                label: h('span', { 'data-geneloop-section-icon': row.id },
                  h('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.65,
                    strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, focusable: false }, h('path', { d: paths[row.id] })), row.label) });
            }
            return rows;
          } } } };
        };
        const release = ctx.slots.register({ name: 'sidebar.settings', priority: -100, locale: original.locale, inject, children,
          ...(original.store ? { store: original.store } : {}) }, props => h(original.component, { ...props,
          renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options) }));
        const mirrors = Object.keys(names).map(name => mirror(name, names[name]));
        stopShell = () => { mirrors.reverse().forEach(dispose => dispose()); release(); };
        } finally { installing = false; }
      };
      installShell(); const unsubscribe = ctx.slots.subscribe('sidebar.settings', installShell);
      return () => { unsubscribe(); stopShell?.(); };
    });
  };
})();
