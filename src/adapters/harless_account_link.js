/* Keep the account entry inside the shipped Harness settings navigation. */
(() => {
  const install = () => {
    for (const dialog of document.querySelectorAll('[role="dialog"]')) {
      const nav = dialog.querySelector('nav');
      if (!nav || !Array.from(nav.querySelectorAll('button')).some(button => button.textContent?.includes('通用设置')))
        continue;
      if (nav.querySelector('[data-harless-account]')) continue;
      const reference = Array.from(nav.querySelectorAll('button')).find(button => button.textContent?.includes('通用设置'));
      const button = document.createElement('button');
      button.type = 'button';
      button.className = reference.className.replace(/\b\S*active\S*\b/g, '').trim();
      button.dataset.harlessAccount = 'true';
      button.setAttribute('aria-label', '账户与安全');
      const label = document.createElement('span');
      label.className = reference.querySelector('span')?.className ?? '';
      label.textContent = '账户与安全';
      button.append(label);
      button.addEventListener('click', () => { window.location.href = '/account'; });
      reference.parentElement.append(button);
    }
  };
  new MutationObserver(install).observe(document.documentElement, { childList: true, subtree: true });
  install();
})();
