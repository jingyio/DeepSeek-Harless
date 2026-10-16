/* Product presentation only: provider names, chat content and protocols stay intact. */
(() => {
  const installed = new WeakSet();
  const logo = '/assets/geneloop-spiral.svg?v=1';
  const name = 'GeneLoop';
  // The head script paints this before the application starts. Readiness comes
  // from public Session state and committed views, never DOM mutation timing.
  const loading = (() => {
    if (!document.documentElement?.append) return;
    const style = document.createElement('style');
    style.textContent = `.geneloop-page-loader{position:fixed;inset:0;z-index:2000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;background:var(--dsw-alias-background-primary,#141414);color:var(--dsw-alias-label-secondary,#b7bbc2);font:14px/1.5 var(--geneloop-ui-font,system-ui,sans-serif)}.geneloop-page-loader[hidden],.geneloop-load-notice[hidden]{display:none}.geneloop-loading-mark{position:relative;display:grid;place-items:center;width:76px;height:76px}.geneloop-loading-mark:before{content:"";position:absolute;inset:0;border:2px solid #729cf72b;border-top-color:#8b9cf7;border-right-color:#41cabb;border-radius:50%;animation:geneloop-loading-spin 1s linear infinite}.geneloop-loading-mark img{width:30px;height:48px;object-fit:contain}.geneloop-page-loader button,.geneloop-load-notice button{border:0;background:transparent;color:inherit;font:inherit;text-decoration:underline;cursor:pointer;padding:6px 10px}.geneloop-page-loader button:focus-visible,.geneloop-load-notice button:focus-visible{outline:2px solid #8b9cf7;outline-offset:3px;border-radius:6px}.geneloop-load-notice{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2000;max-width:calc(100vw - 32px);padding:12px 16px;border:1px solid #8885;border-radius:12px;background:var(--dsw-specific-menu,#262626);color:var(--dsw-alias-label-primary,#eee);font:13px/1.5 var(--geneloop-ui-font,system-ui,sans-serif)}@keyframes geneloop-loading-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.geneloop-loading-mark:before{animation:none}}`;
    document.head.append(style);
    const cover = document.createElement('div'), mark = document.createElement('span'), image = document.createElement('img');
    cover.className = 'geneloop-page-loader'; cover.setAttribute('role', 'status'); cover.setAttribute('aria-live', 'polite');
    mark.className = 'geneloop-loading-mark'; mark.setAttribute('aria-hidden', 'true'); image.src = logo; image.alt = '';
    mark.append(image);
    const label = document.createElement('span'); label.textContent = '正在加载 GeneLoop…';
    cover.append(mark, label);
    const notice = document.createElement('div'); notice.className = 'geneloop-load-notice'; notice.hidden = true; notice.setAttribute('role', 'status');
    const message = document.createElement('span'); message.textContent = '页面加载较慢，已显示可用内容。';
    const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = '刷新重试'; retry.onclick = () => window.location.reload();
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.textContent = '关闭'; dismiss.onclick = () => { notice.hidden = true; };
    notice.append(message, retry, dismiss); document.documentElement.append(cover, notice);
    let current = { id: Symbol('boot'), nativeReady: false, committed: false, pending: new Set(), released: false }, timeout;
    const release = (slow = false) => {
      current.released = true; cover.hidden = true; clearTimeout(timeout);
      if (slow) notice.hidden = false;
    };
    const check = () => { if (current.nativeReady && current.committed && !current.pending.size) release(); };
    const arm = () => {
      clearTimeout(timeout);
      // This is a failure escape, not a successful-load heuristic. Errors and
      // network stalls must never leave an opaque mask over the application.
      timeout = setTimeout(() => release(true), 20000);
    };
    style.textContent += `.geneloop-page-loader{background:var(--dsw-alias-bg-base,#141414)}.geneloop-loading-mark:before{corner-shape:round}.geneloop-conversation-load-region{display:contents}.geneloop-conversation-load-host{position:relative;isolation:isolate}.geneloop-conversation-load-region>.geneloop-page-loader{position:absolute;z-index:20}.geneloop-conversation-load-region>.geneloop-load-notice{position:absolute;z-index:21;max-width:calc(100% - 32px)}`;
    let mountedHost;
    arm();
    return window.__geneLoopPageLoad = {
      mount(region) {
        if (!region) return;
        // Keep the sidebar and settings outside the history-loading boundary.
        // Slot seats can use display:contents. The first actual layout box is
        // the conversation root; preserving it also keeps blank-chat layout.
        let host = region.parentElement;
        while (host && getComputedStyle(host).display === 'contents') host = host.parentElement;
        if (mountedHost !== host) mountedHost?.classList.remove('geneloop-conversation-load-host');
        mountedHost = host; host?.classList.add('geneloop-conversation-load-host');
        region.append(cover, notice); label.textContent = '正在加载对话…';
      },
      select(id, ready, state) {
        if (current.id !== id) {
          current = { id, nativeReady: false, committed: id === undefined, pending: new Set(), released: false };
          cover.hidden = false; notice.hidden = true; arm();
        }
        if (current.released) return;
        if (state === 'error') { release(); return; }
        current.nativeReady = ready && (id === undefined || state === 'open'); check();
      },
      commit(id) { if (current.id === id) { current.committed = true; check(); } },
      hold(id) {
        const owner = current, token = {};
        if (owner.id === id && !owner.released) owner.pending.add(token);
        // A lease belongs to one navigation, so late completions cannot reveal
        // the next page. Once revealed, streaming updates never mask it again.
        return () => { owner.pending.delete(token); if (owner === current) check(); };
      },
      fail() { release(); },
    };
  })();
  const loadingInstalled = new WeakSet();
  window.__installGeneLoopLoading = (ctx, React, mirrorPublicSlot) => {
    if (!loading || loadingInstalled.has(ctx)) return;
    loadingInstalled.add(ctx);
    const sessions = ctx.get('sessions');
    ctx.effect(() => {
      let selected, unsubscribeSession;
      const sync = () => {
        const list = sessions.list.getSnapshot(), face = list.current === undefined ? undefined : sessions.binding(list.current)?.session;
        if (face !== selected) { unsubscribeSession?.(); selected = face; unsubscribeSession = face?.subscribe(sync); }
        loading.select(list.current, list.phase === 'ready', face?.getSnapshot().openState);
      };
      const unsubscribe = sessions.list.subscribe(sync); sync();
      return () => { unsubscribe(); unsubscribeSession?.(); loading.fail(); };
    }, 'geneloop: page readiness');
    ctx.slots.inject('conversation.view', () => {
      const original = ctx.slots.entries('conversation.session')[0];
      if (!original) { loading.fail(); return; }
      const alias = 'geneloop.loading.view';
      function LoadedSession(props) {
        const state = props.useSession(value => value.openState);
        React.useLayoutEffect(() => { if (state === 'open' || state === 'error') loading.commit(props.sessionId); }, [props.sessionId, state]);
        return React.createElement('div', { className: 'geneloop-conversation-load-region', ref: loading.mount },
          React.createElement(original.component, { ...props,
            renderSlot: (slot, owner, options) => props.renderSlot(slot === 'conversation.view' ? alias : slot, owner, options) }));
      }
      const stop = ctx.slots.register({ name: 'conversation.session', ...original.options, priority: -100,
        inject: original.inject, ...(original.store ? { store: original.store } : {}),
        children: { [alias]: { kind: 'list', scope: 'session' } } }, LoadedSession);
      const unmirror = mirrorPublicSlot('conversation.view', alias);
      return () => { unmirror(); stop(); };
    });
  };
  window.__installGeneLoopBrand = (ctx, React) => {
    if (installed.has(ctx)) return;
    installed.add(ctx);
    function Mark({ size = 32, className }) {
      return React.createElement('span', { className, role: 'img', 'aria-label': name,
        style: { width: size, height: size, display: 'inline-block', flexShrink: 0 } },
      React.createElement('img', { src: logo, alt: '', 'aria-hidden': true,
        style: { display: 'block', width: '100%', height: '100%', objectFit: 'contain' } }));
    }
    function Name() {
      return React.createElement('span', { style: { fontFamily: 'var(--geneloop-ui-font)',
        fontSize: 22, fontWeight: 650, letterSpacing: '-.6px', whiteSpace: 'nowrap', lineHeight: 1.2 } }, name);
    }
    // Slot priority is an explicit public composition contract: lowest renders.
    // The upstream official brand remains untouched and is shadowed as a unit.
    ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.inject('sidebar.brand.name', function* () {
      yield ctx.slots.register({ name: 'sidebar.brand.mark', priority: -100 }, Mark);
      yield ctx.slots.register({ name: 'sidebar.brand.name', priority: -100 }, Name);
    }));
    ctx.slots.inject('conversation.hero.brand.mark', () =>
      ctx.slots.register({ name: 'conversation.hero.brand.mark', priority: -100 }, Mark));

    // GeneLoop chooses its scene through the slash reference. These upstream
    // preset controls change a different setting and expose internal preset IDs.
    // Keep their removal independent from workspace and composer installation.
    ctx.slots.inject('conversation.hero.agentPreset', () => ctx.slots.register(
      { name: 'conversation.hero.agentPreset', priority: -100 }, () => null));
    ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register(
      { name: 'conversation.session.header.actions', id: 'agent-preset', priority: -100 }, () => null));

    // Replace only the upstream developer notice, not model setup or any user
    // approval. Completing this public slot advances the onboarding coordinator;
    // do not forge an acknowledgement in the user's persistent settings.
    function SkipDeveloperNotice({ complete }) {
      React.useLayoutEffect(() => { complete(); }, [complete]);
      return null;
    }
    ctx.slots.inject('settings.onboarding', () => ctx.slots.register(
      { name: 'settings.onboarding', id: 'welcome-notice', order: -100, priority: -100 }, SkipDeveloperNotice));
  };
  const updateTitle = () => {
    const current = document.title;
    const next = current.replace(/DeepSeek\s+(?:Harness|Harless)|\bHarness\b|\bHarless\b/gi, name);
    if (next !== current) document.title = next;
  };
  updateTitle();
  // Session navigation can change the title; only the document title is branded.
  new MutationObserver(updateTitle).observe(document.head, { childList: true, subtree: true, characterData: true });
  for (const icon of document.querySelectorAll('link[rel~="icon"]')) icon.remove();
  const icon = document.createElement('link');
  icon.rel = 'icon'; icon.type = 'image/svg+xml'; icon.href = logo;
  document.head.append(icon);

  // Old owner patches injected this link directly under body, outside the slot
  // system. Remove that exact legacy entry, including before plugin startup;
  // links inside a conversation and every other dialog/control remain intact.
  const legacySelector = 'body > a[href="/paper-revision"]';
  const legacyStyle = document.createElement('style');
  legacyStyle.textContent = legacySelector + '{display:none!important}';
  document.head.append(legacyStyle);
  // Set the document font as well as the public theme token: inherited text
  // otherwise falls back to the browser's serif default in some native slots.
  const typography = document.createElement('style');
  typography.textContent = `:root,body{--geneloop-ui-font:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",Arial,sans-serif;--dsw-font-family:var(--geneloop-ui-font)}body{font-family:var(--geneloop-ui-font);font-weight:400;line-height:1.5;-webkit-font-smoothing:antialiased}button,input,textarea,select{font-family:inherit}.harless-paired-answer{line-height:1.7}`;
  document.head.append(typography);
  const removeLegacyEntry = () => {
    for (const entry of document.querySelectorAll(legacySelector)) entry.remove();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', removeLegacyEntry, { once: true });
  else removeLegacyEntry();
})();
