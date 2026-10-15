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
})();
