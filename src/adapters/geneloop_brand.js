/* Product presentation only: provider names, chat content and protocols stay intact. */
(() => {
  const installed = new WeakSet();
  const logo = '/assets/geneloop.jpg?v=1';
  const name = 'GeneLoop';
  window.__installGeneLoopBrand = (ctx, React) => {
    if (installed.has(ctx)) return;
    installed.add(ctx);
    function Mark({ size = 32, className }) {
      return React.createElement('span', { className, role: 'img', 'aria-label': name,
        style: { width: size, height: size, display: 'inline-block', position: 'relative',
          overflow: 'hidden', borderRadius: '50%', flexShrink: 0, background: '#fff' } },
      React.createElement('img', { src: logo, alt: '', 'aria-hidden': true,
        style: { position: 'absolute', width: '216.21%', maxWidth: 'none', height: 'auto',
          left: '-58.62%', top: '-37.93%' } }));
    }
    function Name() {
      return React.createElement('span', { style: { fontFamily: 'Georgia, "Times New Roman", serif',
        fontSize: 23, fontWeight: 600, letterSpacing: '-.65px', whiteSpace: 'nowrap', lineHeight: 1 } }, name);
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
  icon.rel = 'icon'; icon.type = 'image/jpeg'; icon.href = logo;
  document.head.append(icon);

  // Old owner patches injected this link directly under body, outside the slot
  // system. Remove that exact legacy entry, including before plugin startup;
  // links inside a conversation and every other dialog/control remain intact.
  const legacySelector = 'body > a[href="/paper-revision"]';
  const legacyStyle = document.createElement('style');
  legacyStyle.textContent = legacySelector + '{display:none!important}';
  document.head.append(legacyStyle);
  const removeLegacyEntry = () => {
    for (const entry of document.querySelectorAll(legacySelector)) entry.remove();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', removeLegacyEntry, { once: true });
  else removeLegacyEntry();
})();
