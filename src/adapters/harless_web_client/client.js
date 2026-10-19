/** Scene references use Harness's native trigger, editor chip and session APIs. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: (require) => {
    const React = require('react');
    const ReactDOM = require('react-dom');
    // Use the exact safe AST renderer used by native Harness assistant messages.
    const primitives = require('@deepseek-ai/dsh-client-ui-primitives');
    const MarkdownText = primitives?.MarkdownText;
    // Display-only pacing: leave the authenticated snapshots, copying, files
    // and model events intact. Render at most 25 times/s, in the text seat only.
    function useBufferedBlocks(blocks, live, identity) {
      const text = blocks.map(block => typeof block.text === 'string' ? block.text : '').join('');
      const state = React.useRef(null), [, redraw] = React.useState(0);
      if (!state.current || state.current.identity !== identity) {
        state.current = { identity, target: text, shown: live ? Math.min(8, text.length) : text.length,
          live, seenLive: live, timer: null, last: Date.now(), ended: null };
      }
      const cursor = state.current;
      if (!text.startsWith(cursor.target)) cursor.shown = text.length; // authoritative correction, never stale prose
      cursor.target = text;
      cursor.live = live;
      cursor.seenLive ||= live;
      if (!live && cursor.ended === null) cursor.ended = Date.now();
      if (live) cursor.ended = null;
      const instant = document.hidden || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      if (instant || !cursor.seenLive) cursor.shown = text.length;
      if (cursor.shown < text.length && /[\uD800-\uDBFF]/.test(text[cursor.shown - 1])) cursor.shown++;
      React.useEffect(() => {
        if (cursor.timer !== null || cursor.shown >= cursor.target.length) return;
        cursor.last = Date.now();
        const advance = () => {
          cursor.timer = null;
          const now = Date.now(), remaining = cursor.target.length - cursor.shown;
          // Keep a small reserve through uneven chunks; catch up faster when
          // the backlog grows, and finish a completed response within 1.2s.
          const elapsed = Math.min(80, Math.max(1, now - cursor.last)); cursor.last = now;
          const rate = Math.max(90, Math.min(720, remaining / 0.7));
          const finalRate = cursor.ended === null ? 0 : remaining / Math.max(0.04, (1200 - (now - cursor.ended)) / 1000);
          let next = Math.min(cursor.target.length, cursor.shown + Math.max(1, Math.floor(Math.max(rate, finalRate) * elapsed / 1000)));
          // Never split an emoji's UTF-16 surrogate pair.
          if (next < cursor.target.length && /[\uD800-\uDBFF]/.test(cursor.target[next - 1])) next++;
          if (document.hidden) next = cursor.target.length;
          cursor.shown = next; redraw(value => value + 1);
          if (next < cursor.target.length) cursor.timer = setTimeout(advance, 40);
        };
        cursor.timer = setTimeout(advance, 40);
      }, [identity, text, live]);
      React.useEffect(() => () => { clearTimeout(cursor.timer); cursor.timer = null; }, [identity]);
      let remaining = cursor.shown;
      return blocks.map(block => {
        if (typeof block.text !== 'string') return block;
        const length = Math.min(remaining, block.text.length); remaining -= length;
        return length === block.text.length ? block : { ...block, text: block.text.slice(0, length) };
      });
    }
    function BufferedMarkdown({ text, streaming, identity, ...props }) {
      const blocks = useBufferedBlocks([{ text }], streaming, identity);
      return MarkdownText ? React.createElement(MarkdownText, { ...props, text: blocks[0].text,
        streaming: streaming || blocks[0].text !== text }) : React.createElement('p', null, blocks[0].text);
    }
    const inject = ['commandUi', 'inputTriggers', 'sessions', 'conversation', 'uiConversation', 'slots', 'workspaces', 'uiWorkspace', 'layout', 'sidebarRight', 'sidebarRightTabs'];
    const endpoint = '/api/harless/settings';
    const observers = new Map(), lexiconObservers = new Map(), cache = new Map(), choosing = new Map(), revisions = new Map();
    const draftSelections = new Map();
    const aliases = { ppt: 'ppt', 'paper-proofreading': 'paper', 'research-data-analysis': 'data', files:'file', 'new-scene': 'chat' };
    const shortcut = scene => scene.id === 'files' ? 'file' : scene.shortcut || aliases[scene.id] || scene.id;
    const selectableScene = scene => !['new-scene'].includes(scene.id) && !['chat', 'files'].includes(shortcut(scene));
    const modeLabel = mode => ({ baseline: '标准执行', shadow: '观察候选', execute: '校验后复用' })[mode] || mode;
    const modeDetail = mode => ({ baseline: '按标准流程执行，不复用 Motif', shadow: '只记录候选，不跳过模型请求', execute: '允许在校验通过后复用已有 Motif' })[mode];
    const displayValue = (id, value) => value && draftSelections.has(id) ? { ...value,
      selection: { ...value.selection, scene: draftSelections.get(id) },
      ...(draftSelections.get(id) === 'new-scene' ? { paired_comparison: false } : {}) } : value;
    function publish(id, value) {
      const oldNames = cache.get(id)?.scenes.map(shortcut).join('\n');
      cache.set(id, value);
      for (const listener of observers.get(id) || []) listener(displayValue(id, value));
      // Native controllers refetch candidates when their lexicon changes. A
      // settings read must not invalidate the unchanged lexicon and recursively
      // trigger another settings read while the menu is open.
      if (oldNames !== value.scenes.map(shortcut).join('\n'))
        for (const listener of lexiconObservers.get(id) || []) listener();
    }
    async function request(session, body, signal) {
      if (body) revisions.set(session.sessionId, (revisions.get(session.sessionId) || 0) + 1);
      const filePick = body?.action === 'select' && body.selection?.scene === 'files';
      const nativeBody = filePick ? undefined : body;
      const response = await fetch(nativeBody ? endpoint : `${endpoint}?session_id=${encodeURIComponent(session.sessionId)}`, {
        method: nativeBody ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal,
        ...(nativeBody ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(nativeBody) } : {}),
      });
      const value = await response.json();
      if (!response.ok || value.error) {
        const error = Error(value.error?.message || '无法加载场景设置'); error.code = value.error?.code; throw error;
      }
      // File management is an additive plugin; the three existing scenes keep
      // their original host, libraries, settings and request semantics.
      if (value.scenes?.some(scene => scene.id === 'files')) {
        const changing = body?.action === 'select' && body.selection?.scene !== undefined;
        const fileResponse = await fetch('/api/harless/file-scene' + (changing ? '' : '?session_id=' + encodeURIComponent(session.sessionId)), {
          method: changing ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal,
          ...(changing ? {headers: {'Content-Type':'application/json'}, body: JSON.stringify({action:'select',session_id:session.sessionId,selected:filePick})} : {}),
        });
        if (fileResponse.ok) {
          const file = await fileResponse.json();
          value.scenes = value.scenes.map(scene => scene.id === 'files' ? {...scene,...file.scene} : scene);
          if (file.selected) Object.assign(value, {selection:{scene:'files',mode:'execute',rsi:true},scene_locked:false,paired_comparison:false,scene_option_fields:[],scene_options:{}});
        } else if (filePick) throw Error('文件管理扩展尚未启用，请更新服务后重试。');
      }
      return value;
    }
    async function settings(session, signal) {
      const revision = revisions.get(session.sessionId) || 0;
      const value = await request(session, undefined, signal);
      if (!signal?.aborted && revision === (revisions.get(session.sessionId) || 0)) publish(session.sessionId, value);
      return value;
    }
    const reference = scene => ({ source: 'harless-scenes', ref: shortcut(scene),
      label: '/' + shortcut(scene), appearance: 'file', clipboardText: '/' + shortcut(scene) });
    function HarlessStatus({ sessionId, openSession, draftInput }) {
      const [value, setValue] = React.useState(null);
      React.useEffect(() => {
        const abort = new AbortController();
        const listener = next => {
          if (abort.signal.aborted) return;
          const draft = draftInput?.state.getSnapshot().draft;
          if (typeof draft === 'string') {
            const token = /^(?:\s*)\/([a-z][a-z0-9_-]*)(?=$|\s|[\u3400-\u9fff])/i.exec(draft)?.[1]?.toLowerCase();
            const scene = next?.scenes.find(row => shortcut(row) === token)?.id || Object.keys(aliases).find(id => aliases[id] === token) || 'new-scene';
            next = { ...next, selection: { ...next?.selection, scene } };
          }
          setValue(next);
        };
        const sync = () => listener(displayValue(sessionId, cache.get(sessionId)) || null);
        sync(); const unsubscribe = draftInput?.state.subscribe(sync);
        const group = observers.get(sessionId) || new Set(); group.add(listener); observers.set(sessionId, group);
        settings({ sessionId }, abort.signal).catch(() => {});
        return () => { abort.abort(); unsubscribe?.(); group.delete(listener); if (!group.size) observers.delete(sessionId); };
      }, [sessionId, draftInput]);
      const sceneId = value?.selection?.scene;
      const scene = value?.scenes?.find(row => row.id === sceneId);
      const name = scene ? '/' + shortcut(scene) : aliases[sceneId] ? '/' + aliases[sceneId] : '';
      if ((!name || sceneId === 'new-scene') && !value?.comparison_parent_session_id) return null;
      return React.createElement('span', { className: 'geneloop-draft-scene', role: 'status', 'aria-label': name, title: name,
        style: { display: 'inline-flex', alignItems: 'center', gap: '6px', maxWidth: 'min(380px, 52vw)', overflow: 'hidden',
          whiteSpace: 'nowrap', borderRadius: '6px', padding: '2px 7px', fontSize: '13px', lineHeight: '20px',
          color: 'var(--dsw-alias-label-secondary, #767c88)' } },
        sceneId !== 'new-scene' && React.createElement('strong', { style: { fontWeight: 600, color: 'var(--dsw-alias-state-business-primary, #4d78e8)' } }, name),
        value?.comparison_parent_session_id && React.createElement('button', { type: 'button', onClick: () => openSession(value.comparison_parent_session_id),
          style: { color: 'var(--dsw-alias-link, #729cf7)', background: 'none', border: 0, cursor: 'pointer', padding: '2px 4px', font: 'inherit', flexShrink: 0 } }, '返回双栏结果与下载'));
    }
    function apply(ctx) {
      window.__installGeneLoopBrand?.(ctx, React);
      window.__installGeneLoopWorkspaces?.(ctx, React, primitives);
      const styleChoices = [
        { id: 'clear', title: '清晰', detail: '石墨色与清楚的文字，专注阅读。' },
        { id: 'air', title: '轻盈', detail: '冷白与柔和的层次，轻巧安静。' },
        { id: 'aurora', title: '极光', detail: '青绿与紫色螺旋，更鲜明的 GeneLoop。' },
      ];
      const styleKey = 'geneloop-visual-style-v1';
      const storedStyle = () => { try { const value = window.localStorage?.getItem(styleKey); return styleChoices.some(row => row.id === value) ? value : 'clear'; } catch { return 'clear'; } };
      if (typeof document !== 'undefined' && document.body?.dataset) document.body.dataset.geneloopStyle = storedStyle();
      function StyleChoices() {
        const [selected, setSelected] = React.useState(storedStyle), [notice, setNotice] = React.useState('');
        return React.createElement('section', { className: 'geneloop-style-choices', 'aria-label': '界面风格' },
          React.createElement('h3', null, '界面风格'), React.createElement('p', null, '默认使用清晰风格。这里仅调整工作区，登录页使用独立的黑灰主题。'),
          React.createElement('div', { role: 'radiogroup', 'aria-label': '界面风格' }, ...styleChoices.map(style => React.createElement('button', {
            key: style.id, type: 'button', role: 'radio', 'aria-checked': selected === style.id, 'data-style': style.id,
            onClick: () => { document.body.dataset.geneloopStyle = style.id; setSelected(style.id);
              try { window.localStorage?.setItem(styleKey, style.id); setNotice('已应用' + style.title + '风格。'); } catch { setNotice('已预览此风格；浏览器未能保存选择。'); }
              // Use the native preference writer so the displayed px value and
              // actual content size agree. Subsequent manual resizing is retained.
              const theme = ctx.get('theme'); if (theme?.setFontSize) theme.setFontSize(16);
            }, onKeyDown: event => { const delta = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 0;
              if (!delta) return; event.preventDefault(); const buttons = [...event.currentTarget.parentElement.querySelectorAll('[role=radio]')];
              const next = buttons[(buttons.indexOf(event.currentTarget) + delta + buttons.length) % buttons.length]; next.focus(); next.click(); },
          }, React.createElement('span', { className: 'geneloop-style-swatch', 'aria-hidden': true }), React.createElement('strong', null, style.title), React.createElement('small', null, style.detail)))),
          notice && React.createElement('p', { role: 'status' }, notice));
      }
      ctx.slots.inject('settings.general.item', () => ctx.slots.register({ name: 'settings.general.item', id: 'geneloop-visual-style', order: 5 }, StyleChoices));
      const command = ctx.get('commandUi'), triggers = ctx.get('inputTriggers');
      const sessions = ctx.get('sessions'), conversation = ctx.get('conversation');
      // The server allocates branch suffixes atomically. Native client-side
      // incrementing only sees one source and would rename every branch (1).
      if (typeof sessions.fork === 'function') {
        const originalFork = sessions.fork;
        sessions.fork = function (options) { return originalFork.call(this, { ...options, increaseTitle: false }); };
        ctx.effect(() => () => { sessions.fork = originalFork; }, 'harless: durable branch names');
      }
      const h = React.createElement;
      const uploads = new Map();
      const liveStyle = '.geneloop-process-status{font:inherit;font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary);margin:0 0 12px}.geneloop-looping{font:inherit;font-size:14px;color:var(--dsw-alias-state-business-primary,#729cf7);margin:20px 0 8px}.geneloop-menu-name{display:inline-flex;align-items:center;gap:10px}.geneloop-menu-name svg{flex:none;vertical-align:middle}';
      const liveStatus = label => h('p', { role: 'status', 'aria-live': 'polite', className: 'geneloop-process-status' }, label + '…');
      const documentSubject = raw => {
        let args; try { args = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return; }
        if (!args || typeof args !== 'object' || Array.isArray(args)) return;
        for (const key of ['filename', 'file_name', 'name', 'file', 'path']) {
          const value = args[key];
          if (typeof value !== 'string' || value.length > 200 || /^(?:[a-z]:|[\\/])|(?:^|[\\/])\.\.(?:[\\/]|$)/i.test(value)) continue;
          const name = value.split(/[\\/]/).pop();
          if (/^[^\x00-\x1f<>:"|?*]{1,100}\.(?:pdf|docx?|xlsx?|csv|tsv|json|txt|md|pptx?|png|jpe?g|webp)$/i.test(name)) return name;
        }
      };
      const workLabel = (name, subject) => {
        const tool = String(name || '').split('__').pop();
        const detail = typeof subject === 'string' && subject ? '：' + subject : '';
        if (tool === 'web_fetch') return '正在读取网页';
        if (tool === 'job_output') return '正在读取后台任务结果';
        if (tool === 'job_list') return '正在检查后台任务';
        if (tool === 'job_kill') return '正在停止后台任务';
        if (/read|extract|parse|load/.test(tool)) return '正在阅读文档' + detail;
        if (/search|browse/.test(tool)) return '正在搜索资料' + detail;
        if (/exec|shell|command|terminal|bash|powershell/.test(tool)) return '正在执行命令' + detail;
        return '正在调用工具' + (tool ? '：' + tool : '');
      };
      const progressText = result => {
        const progress = result.progress;
        if (result.status === 'queued') return '等待执行';
        if (progress?.tool && progress.status === 'running') return workLabel(progress.tool, progress.subject);
        if (progress?.status === 'running' && progress.label && !/准备|组织回复/.test(progress.label))
          return progress.label.startsWith('正在') ? progress.label : '正在' + progress.label;
        return '正在回复';
      };
      const busyComparisons = new Map();
      // The journal stores the submission snapshot, not its eventual result.
      // Keep recent authenticated snapshots across chat/trace navigation only;
      // never persist private replies in browser storage.
      const comparisonSnapshots = new Map(), comparisonObservers = new Map();
      const comparisonActivityListeners = new Set();
      let comparisonActivityRevision = 0;
      const comparisonActivity = {
        subscribe: listener => { comparisonActivityListeners.add(listener); return () => comparisonActivityListeners.delete(listener); },
        getSnapshot: () => comparisonActivityRevision,
      };
      function notifyComparisonActivity() {
        comparisonActivityRevision++;
        for (const listener of comparisonActivityListeners) listener();
      }
      let comparisonIdentity = 0;
      const comparisonKey = value => value.session_id + ':' + value.id;
      const olderSnapshot = (next, previous) => previous && (
        Number(next.snapshot_epoch ?? 0) < Number(previous.snapshot_epoch ?? 0)
        || (Number(next.snapshot_epoch ?? 0) === Number(previous.snapshot_epoch ?? 0)
          && (Number(next.snapshot_revision ?? -1) < Number(previous.snapshot_revision ?? -1)
            || (Number(next.snapshot_revision ?? -1) === Number(previous.snapshot_revision ?? -1)
              && Number(next.score_revision ?? -1) < Number(previous.score_revision ?? -1)))));
      const rememberedSnapshot = value => {
        const cached = comparisonSnapshots.get(comparisonKey(value));
        return cached && !olderSnapshot(cached, value) ? cached : value;
      };
      function rememberSnapshot(value) {
        const key = comparisonKey(value);
        if (olderSnapshot(value, comparisonSnapshots.get(key))) return false;
        comparisonSnapshots.delete(key); comparisonSnapshots.set(key, value);
        if (comparisonSnapshots.size > 40) comparisonSnapshots.delete(comparisonSnapshots.keys().next().value);
        for (const listener of comparisonObservers.get(key) || []) listener(value);
        notifyComparisonActivity();
        return true;
      }
      function discardComparisonMemory() {
        comparisonIdentity++;
        comparisonSnapshots.clear();
        notifyComparisonActivity();
      }
      ctx.effect(() => {
        const leavePage = () => discardComparisonMemory();
        window.addEventListener?.('pagehide', leavePage);
        return () => { window.removeEventListener?.('pagehide', leavePage); leavePage(); };
      }, 'harless: account-scoped comparison memory');
      const busyReason = '正在处理当前请求，请等待完成或停止生成。';
      function updateBusy(session,id,busy){
        const group=busyComparisons.get(session)||new Map(), count=(group.get(id)||0)+(busy?1:-1);
        if(count>0)group.set(id,count);else group.delete(id);
        if(group.size)busyComparisons.set(session,group);else busyComparisons.delete(session);
        const current=conversation.blocks.storeFor(session).getSnapshot();
        if(group.size&&(!current||current.reason===busyReason))conversation.blocks.set(session,{reason:busyReason});
        if(!group.size&&current?.reason===busyReason)conversation.blocks.set(session,undefined);
      }
      const settled = value => ['completed', 'failed', 'cancelled'].includes(value.status);
      const markdownLabels = { code: { copyLabel: '复制', copiedLabel: '已复制' }, footnotes: '注释' };
      function apiError(status, message) {
        const labels = { 401: '登录已过期，请重新登录。', 403: '当前账号没有权限访问此结果。',
          404: '该结果或文件不存在，或不属于当前账号。', 409: '结果已更新，请刷新后再操作。',
          429: '请求较多，请稍后重试。', 502: '服务器连接暂时中断，请稍后重试。',
          503: '服务正在恢复，请稍后重试。', 504: '服务器响应超时，请稍后重试。' };
        const error = Error(labels[status] || message || `请求失败（HTTP ${status}）`);
        error.status = status; return error;
      }
      const networkMessage = error => error.status ? error.message : '网络连接暂时中断，已保留当前结果。';
      function comparisonUrl(value, lane, file) {
        return (value.id?.startsWith('file-') ? '/api/harless/file-scene' : value.id?.startsWith('native-') ? '/api/harless/deliveries' : '/api/harless/comparisons') + '?session_id=' + encodeURIComponent(value.session_id) + '&id=' + encodeURIComponent(value.id)
          + (lane ? '&lane=' + lane + '&file=' + encodeURIComponent(file.id) : '');
      }
      async function withDeadline(signal, milliseconds, operation) {
        const abort = new AbortController(); let expired = false;
        const cancel = () => abort.abort();
        if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
        const timer = setTimeout(() => { expired = true; abort.abort(); }, milliseconds);
        try {
          // Keep the deadline through response body consumption and integrity checks.
          const result = await operation(abort.signal);
          if (expired) throw apiError(408, '连接超时，请稍后重试。');
          return result;
        } catch (error) {
          if (expired && !signal?.aborted) throw apiError(408, '连接超时，请稍后重试。');
          throw error;
        } finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel); }
      }
      async function comparisonRequest(value, body, signal) {
        const identity = comparisonIdentity;
        return withDeadline(signal, 30000, async requestSignal => {
          const response = await fetch(comparisonUrl(value), { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: requestSignal,
            ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: value.session_id, id: value.id }) } : {}) });
          if (identity !== comparisonIdentity) throw apiError(401);
          if ([401, 403].includes(response.status)) {
            const error = apiError(response.status); discardComparisonMemory(); throw error;
          }
          let result;
          try { result = await response.json(); } catch { throw apiError(response.status || 502, '服务器未返回有效结果，请稍后刷新。'); }
          if (identity !== comparisonIdentity) throw apiError(401);
          if (!response.ok || result.error) throw apiError(response.status, result.error?.message);
          if (result.id !== value.id || result.session_id !== value.session_id || !result.lanes?.baseline || (result.presentation !== 'single' && !result.lanes?.motif))
            throw apiError(502, '服务器未返回当前对照结果。');
          return result;
        });
      }
      function artifactFor(files, raw) {
        let path = String(raw || '').trim();
        try { path = decodeURIComponent(path); } catch { return undefined; }
        path = path.replace(/^sandbox:/, '').replace(/^file:\/\//, '').replace(/\\/g, '/');
        // Match only immutable server-approved rows; ambiguous basenames stay inert.
        const exact = files.filter(file => path === file.name || path.endsWith('/' + file.name) ||
          (file.name.startsWith('outputs/code/') && [file.name.replace('outputs/code/', '/work/outputs/'), file.name.replace('outputs/code/', 'outputs/')].includes(path)) ||
          (file.name.startsWith('code/') && path === file.name.replace('code/', '/work/')));
        if (exact.length === 1) return exact[0];
        if (!path.includes('/')) {
          const matches = files.filter(file => file.name.split('/').pop() === path);
          if (matches.length === 1) return matches[0];
        }
        return undefined;
      }
      function compactArtifactLabels(root, files) {
        if (!root) return;
        // Native Markdown uses resolve().label only for aria-label and keeps
        // the raw inline-code path as visible button text. Adapt that rendered
        // label, not the Markdown source or the authenticated download target.
        for (const link of root.querySelectorAll('code > button, a')) {
          if (link.closest('pre')) continue;
          const isButton = link.nodeName.toLowerCase() === 'button';
          const target = link.getAttribute(isButton ? 'title' : 'href') || '';
          if (!isButton && /^(?:https?:|mailto:|#)/i.test(target)) continue;
          const textNodes = [];
          const visit = node => {
            if (node.nodeType === 3) { if (node.nodeValue?.trim()) textNodes.push(node); return; }
            if (node.nodeName?.toLowerCase() === 'svg') return;
            for (const child of node.childNodes || []) visit(child);
          };
          visit(link);
          const label = textNodes.length === 1 ? textNodes[0].nodeValue.trim() : '';
          const labeledFile = artifactFor(files, label);
          // Native mentions may already have a compact title; the rendered
          // full path still identifies exactly one approved receipt.
          const file = artifactFor(files, target) || (isButton && labeledFile && target === labeledFile.name.split('/').pop() ? labeledFile : undefined);
          if (!file) continue;
          const name = file.name.split(/[\\/]/).pop();
          link.setAttribute('data-harless-artifact-link', '');
          if (isButton && link.parentElement?.nodeName.toLowerCase() === 'code')
            link.parentElement.setAttribute('data-harless-artifact-inline', '');
          // Preserve custom and formatted captions. Only replace a matching
          // approved path label, never ordinary inline code or a remote URL.
          if (textNodes.length === 1 && /[\\/]/.test(label) && !/^(?:https?:|mailto:|#)/i.test(label)
              && /^(?:[./\\]|[a-z]:[\\/]|sandbox:|file:\/\/|[^\s/\\:]+[\\/])/i.test(label) && labeledFile?.id === file.id)
            textNodes[0].nodeValue = name;
          link.setAttribute('title', name);
        }
      }
      const artifactName = file => file.name.split(/[\\/]/).pop();
      // A delivery address contains only public identities, never a workspace path.
      const previewAddress = (value, lane, file) => 'dsh-resource://geneloop-delivery/' +
        [value.session_id, value.id, lane, file.id, artifactName(file)].map(encodeURIComponent).join('/');
      const artifactPreviewLink = (value, lane, file) => new URL('/#geneloop-preview=' + encodeURIComponent(previewAddress(value, lane, file)), window.location.href).href;
      // Native Markdown intentionally omits relative links. Give only approved
      // delivery links a same-origin preview address; retain captions and code.
      function artifactMarkdown(text, files, value, lane) {
        let fence;
        return text.split('\n').map(line => {
          const marker = /^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
          if (marker) { if (!fence) fence = marker; else if (marker[0] === fence[0] && marker.length >= fence.length) fence = undefined; return line; }
          if (fence) return line;
          return line.replace(/(`+)[\s\S]*?\1|(!?\[(?:\\.|[^\]\\])*\]\()(<[^>\n]+>|[^\s)]+)([^)\n]*\))/g,
            (match, code, caption, target, tail) => {
              if (code || caption.startsWith('!')) return match;
              const path = target.startsWith('<') ? target.slice(1, -1) : target;
              if (/^(?:https?:|mailto:|#)/i.test(path)) return match;
              const file = artifactFor(files, path);
              return file ? caption + artifactPreviewLink(value, lane, file) + tail : match;
            });
        }).join('\n');
      }
      function parsePreview(address) {
        const prefix = 'dsh-resource://geneloop-delivery/';
        if (!address.startsWith(prefix)) throw Error('无效的文件预览。');
        const parts = address.slice(prefix.length).split('/').map(decodeURIComponent);
        if (parts.length !== 5 || parts.slice(0, 4).some(part => !/^[a-zA-Z0-9-]{1,120}$/.test(part)) ||
            !['baseline', 'motif'].includes(parts[2]) || /[\\/\x00-\x1f]/.test(parts[4])) throw Error('无效的文件预览。');
        return { value: { session_id: parts[0], id: parts[1] }, lane: parts[2], file: { id: parts[3], name: parts[4] } };
      }
      async function readArtifact(value, lane, file, signal) {
        const response = await fetch(comparisonUrl(value, lane, file), { credentials: 'same-origin', cache: 'no-store', signal });
        if (!response.ok) throw apiError(response.status);
        const contentType = response.headers.get('content-type') || '';
        if (/text\/html|application\/json/i.test(contentType) && !/\.(html|json)$/i.test(file.name)) throw apiError(502, '未收到交付文件，请刷新后重试。');
        const blob = await response.blob();
        if (Number.isFinite(file.bytes) && blob.size !== file.bytes) throw apiError(409, '文件大小校验失败，请刷新后重试。');
        if (file.sha256 && window.crypto?.subtle) {
          const digest = await window.crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
          const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
          if (hex !== file.sha256) throw apiError(409, '文件内容校验失败，请刷新后重试。');
        }
        return blob;
      }
      const previewType = name => {
        const ext = name.split('.').pop().toLowerCase();
        if (ext === 'pdf') return 'pdf';
        if (/^(png|jpe?g|gif|webp|bmp|ico|svg)$/.test(ext)) return 'image';
        if (/^(md|markdown)$/.test(ext)) return 'markdown';
        if (/^(csv|tsv)$/.test(ext)) return 'table';
        if (/^(docx|pptx|xlsx)$/.test(ext)) return 'office';
        if (/^(txt|json|jsonl|log|tex|bib|py|js|ts|css|yaml|yml|xml|html|htm)$/.test(ext)) return 'text';
        return 'unsupported';
      };
      // CSV keeps quoted delimiters and embedded newlines. Rendering uses text nodes.
      function previewTable(text, delimiter = ',') {
        const rows = []; let row = [], cell = '', quoted = false;
        for (let i = 0; i < text.length; i++) {
          const ch = text[i];
          if (ch === '"') { if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted; }
          else if (!quoted && ch === delimiter) { row.push(cell); cell = ''; }
          else if (!quoted && (ch === '\n' || ch === '\r')) {
            if (ch === '\r' && text[i + 1] === '\n') i++;
            row.push(cell); rows.push(row); row = []; cell = '';
          } else cell += ch;
        }
        if (cell || row.length) { row.push(cell); rows.push(row); }
        if (quoted) throw Error('表格中的引号未闭合，请下载原文件检查。');
        return rows;
      }
      // Office content previews are bounded local XML extraction. No document is
      // sent to an external viewer; macros, external links and scripts never run.
      async function officePreview(blob, name, signal) {
        const bytes = new Uint8Array(await blob.arrayBuffer()), view = new DataView(bytes.buffer);
        if (bytes.length < 22) throw Error('文件内容不完整。');
        let end = bytes.length - 22;
        while (end >= Math.max(0, bytes.length - 65557) && view.getUint32(end, true) !== 0x06054b50) end--;
        if (end < 0 || view.getUint32(end, true) !== 0x06054b50) throw Error('无法读取此 Office 文件。');
        const count = view.getUint16(end + 10, true), offset = view.getUint32(end + 16, true);
        if (count > 10000 || offset >= bytes.length) throw Error('文件结构过大，建议下载查看。');
        const xml = new Map(); let cursor = offset, total = 0;
        for (let i = 0; i < count; i++) {
          signal.throwIfAborted();
          if (cursor + 46 > bytes.length || view.getUint32(cursor, true) !== 0x02014b50) throw Error('文件目录损坏。');
          const flags = view.getUint16(cursor + 8, true), method = view.getUint16(cursor + 10, true);
          const size = view.getUint32(cursor + 20, true), length = view.getUint32(cursor + 24, true);
          const n = view.getUint16(cursor + 28, true), extra = view.getUint16(cursor + 30, true), comment = view.getUint16(cursor + 32, true);
          const local = view.getUint32(cursor + 42, true);
          const path = new TextDecoder().decode(bytes.subarray(cursor + 46, cursor + 46 + n));
          cursor += 46 + n + extra + comment;
          if (!/^(word\/document|ppt\/slides\/slide\d+|xl\/sharedStrings|xl\/worksheets\/sheet\d+)\.xml$/.test(path)) continue;
          if (flags & 1 || length > 8 * 1024 * 1024 || (total += length) > 24 * 1024 * 1024 || local + 30 > bytes.length) throw Error('此文件已加密或超出预览容量，请下载查看。');
          if (view.getUint32(local, true) !== 0x04034b50) throw Error('文件结构损坏。');
          const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
          if (start + size > bytes.length) throw Error('文件内容不完整。');
          let data = bytes.subarray(start, start + size);
          if (method === 8) {
            const reader = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader();
            const chunks = []; let received = 0;
            const cancel = () => { void reader.cancel(); }; signal.addEventListener('abort', cancel, { once: true });
            try { while (true) { const chunk = await reader.read(); if (chunk.done) break;
              if ((received += chunk.value.length) > length) { await reader.cancel(); throw Error('文件解压内容不符合声明。'); } chunks.push(chunk.value); }
            } finally { signal.removeEventListener('abort', cancel); reader.releaseLock(); }
            data = new Uint8Array(await new Blob(chunks).arrayBuffer());
          } else if (method !== 0) throw Error('此文件压缩方式暂不支持，请下载查看。');
          if (data.length !== length) throw Error('文件内容长度不匹配。');
          const source = new TextDecoder('utf-8', { fatal: true }).decode(data);
          if (/<!DOCTYPE|<!ENTITY/i.test(source)) throw Error('此文件包含不支持的 XML 声明，请下载查看。');
          const document = new DOMParser().parseFromString(source, 'application/xml');
          if (document.getElementsByTagName('parsererror').length || document.doctype) throw Error('文件 XML 损坏。');
          xml.set(path, document);
        }
        const nodes = (root, local) => [...root.getElementsByTagNameNS('*', local)];
        const ext = name.split('.').pop().toLowerCase();
        if (ext === 'xlsx') {
          const strings = xml.get('xl/sharedStrings.xml');
          const shared = strings ? nodes(strings, 'si').map(n => nodes(n, 't').map(t => t.textContent).join('')) : [];
          const sheets = [...xml].filter(([path]) => path.startsWith('xl/worksheets/')).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
          if (!sheets.length) throw Error('没有可预览的工作表。');
          return sheets.map(([path, doc], i) => ({ title: '工作表 ' + (i + 1), rows: nodes(doc, 'row').map(row => {
            const result = []; for (const cell of nodes(row, 'c')) {
              const ref = cell.getAttribute('r')?.match(/^[A-Z]+/)?.[0]; let col = 0;
              if (ref) for (const ch of ref) col = col * 26 + ch.charCodeAt(0) - 64;
              if (col > 256) continue;
              const raw = nodes(cell, 'v')[0]?.textContent || '';
              result[(col || result.length + 1) - 1] = cell.getAttribute('t') === 's' ? shared[Number(raw)] || '' : cell.getAttribute('t') === 'inlineStr' ? nodes(cell, 't').map(n => n.textContent).join('') : raw;
            } return Array.from(result, value => value ?? '');
          }) }));
        }
        const documents = [...xml].filter(([path]) => ext === 'docx' ? path === 'word/document.xml' : path.startsWith('ppt/slides/')).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
        if (!documents.length) throw Error('没有可预览的正文。');
        return documents.map(([path, doc], i) => ({ title: ext === 'pptx' ? '第 ' + (i + 1) + ' 页' : '文档正文',
          paragraphs: nodes(doc, 'p').map(p => nodes(p, 't').map(t => t.textContent).join('')).filter(Boolean) }));
      }
      function openArtifact(value, lane, file) {
        const sidebar = ctx.get('sidebarRight');
        if (!sidebar) throw Error('文件预览暂未就绪，请稍后重试。');
        sidebar.openResource(previewAddress(value, lane, file));
      }
      function DeliveryPreview({ useTabInfo, renderSlot }) {
        const { tab } = useTabInfo(), address = tab.contentId;
        const [state, setState] = React.useState({ phase: 'loading' }), [revision, setRevision] = React.useState(0);
        const [downloadState, setDownloadState] = React.useState('');
        const scrollportRef = React.useRef(null), busy = React.useRef(false);
        const identity = parsePreview(address), name = identity.file.name;
        React.useEffect(() => {
          const abort = new AbortController(); let objectUrl;
          const cancel = () => abort.abort(); tab.signal.addEventListener('abort', cancel, { once: true });
          setState({ phase: 'loading' }); setDownloadState('');
          (async () => {
            // Refresh the authenticated list; persisted layout metadata is never a grant.
            const current = await withDeadline(abort.signal, 60000, async signal => {
              const response = await fetch(comparisonUrl(identity.value), { credentials: 'same-origin', cache: 'no-store', signal });
              if (!response.ok) throw apiError(response.status);
              const value = await response.json();
              if (value.session_id !== identity.value.session_id || value.id !== identity.value.id) throw Error('文件不属于当前预览。');
              return value;
            });
            const file = current.lanes?.[identity.lane]?.artifacts?.find(row => row.id === identity.file.id);
            if (!file) throw Error('文件已不可用，请返回对话重新选择。');
            // Decoder failure must not remove the independent original-file
            // download. It still goes through authenticated byte checks.
            setState({ phase: 'loading', file, current });
            let shown = file;
            const companion = /\.(pptx|docx)$/i.test(name) && current.lanes[identity.lane].artifacts.find(row => row.name === file.name.replace(/\.[^.]+$/, '.pdf'));
            if (companion) shown = companion;
            const blob = await withDeadline(abort.signal, 60000, signal => readArtifact(current, identity.lane, shown, signal));
            const kind = previewType(shown.name); let content;
            if (kind === 'office') content = await officePreview(blob, shown.name, abort.signal);
            else if (['text', 'markdown', 'table'].includes(kind)) {
              content = await blob.text();
              if (kind === 'table') content = previewTable(content.replace(/^\uFEFF/, ''), /\.tsv$/i.test(name) ? '\t' : ',');
              else if (/\.json$/i.test(name)) { try { content = JSON.stringify(JSON.parse(content), null, 2); } catch {} }
            } else if (kind === 'pdf') content = new Uint8Array(await blob.arrayBuffer());
            else if (kind === 'image') objectUrl = URL.createObjectURL(new Blob([blob], { type: /\.svg$/i.test(name) ? 'image/svg+xml' : 'image/' + name.split('.').pop().replace('jpg', 'jpeg') }));
            if (!abort.signal.aborted) setState({ phase: 'ready', kind, content, objectUrl, file, current, companion: companion && artifactName(companion) });
          })().catch(error => { if (!abort.signal.aborted) setState(previous => ({ ...previous, phase: 'error', message: networkMessage(error) })); });
          return () => { abort.abort(); tab.signal.removeEventListener('abort', cancel); if (objectUrl) URL.revokeObjectURL(objectUrl); };
        }, [address, revision, tab.signal]);
        const downloadCurrent = async () => {
          if (busy.current || !state.file) return; busy.current = true; setDownloadState('正在准备下载…');
          try {
            const blob = await withDeadline(tab.signal, 60000, signal => readArtifact(state.current, identity.lane, state.file, signal));
            if (tab.signal.aborted) return;
            const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = name; link.hidden = true;
            document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
            setDownloadState('已交给浏览器下载。');
          } catch (error) { if (!tab.signal.aborted) setDownloadState(networkMessage(error) + ' 可重新点击下载。'); }
          finally { busy.current = false; }
        };
        const table = rows => h('div', { className: 'geneloop-preview-table' }, h('table', null, h('tbody', null,
          ...rows.map((row, i) => h('tr', { key: i }, ...row.map((cell, j) => h(i === 0 ? 'th' : 'td', { key: j }, cell)))))));
        return h('section', { className: 'geneloop-delivery-preview', 'aria-label': '文件预览：' + name },
          h('header', null, h('div', null, h('strong', { title: name }, name), h('small', null, identity.lane === 'motif' ? 'Motif 交付文件' : 'Baseline 交付文件')),
            h('button', { type: 'button', 'aria-label': '重新加载预览', onClick: () => setRevision(n => n + 1) }, '刷新'),
            h('button', { type: 'button', disabled: !state.file || busy.current, 'aria-label': '下载 ' + name, onClick: downloadCurrent }, h(primitives.IconDownloadOutline16), '下载')),
          state.phase === 'loading' ? h('div', { className: 'geneloop-preview-status', role: 'status', 'aria-busy': true }, h('span', { className: 'harless-artifact-spinner' }), '正在打开文件…')
          : state.phase === 'error' ? h('div', { className: 'geneloop-preview-status', role: 'alert' }, h('p', null, state.message), h('button', { type: 'button', onClick: () => setRevision(n => n + 1) }, '重试'))
          : h(React.Fragment, null,
            state.companion && h('p', { className: 'geneloop-preview-note' }, '显示配套 PDF 的排版预览；下载获取原文件。'),
            state.kind === 'office' && h('p', { className: 'geneloop-preview-note' }, '内容预览，原始排版、图形和公式请下载查看。'),
            h('div', { className: 'geneloop-preview-content', ref: scrollportRef },
              state.kind === 'pdf' ? renderSlot('geneloop.delivery.document', { resourceAddress: address, content: { kind: 'bytes', data: state.content }, wrap: true, scrollportRef },
                { entryKey: '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/pdf', hookContext: useTabInfo, fallback: h('p', null, 'PDF 预览器暂未就绪，请刷新重试。') })
              : state.kind === 'image' ? h('img', { src: state.objectUrl, alt: name, onError: () => setState(previous => ({ ...previous, phase: 'error', message: '无法显示这张图片，请下载原文件查看。' })) })
              : state.kind === 'markdown' && MarkdownText ? h(MarkdownText, { text: state.content, streaming: false, labels: markdownLabels })
              : state.kind === 'table' ? table(state.content)
              : state.kind === 'office' ? state.content.map((part, i) => h('section', { key: i, className: 'geneloop-office-page' }, h('h2', null, part.title), part.rows ? table(part.rows) : part.paragraphs.map((p, j) => h('p', { key: j }, p))))
              : state.kind === 'unsupported' ? h('p', null, '此格式暂不支持在线预览，可使用上方下载按钮保存原文件。')
              : h('pre', null, state.content))),
          downloadState && h('p', { className: 'geneloop-preview-note', role: 'status' }, downloadState));
      }
      // Public right-sidebar slots retain native tabs, resizing and fullscreen.
      if (ctx.slots.entries && ctx.get('sidebarRightTabs')) {
        const id = 'geneloop-delivery-preview';
        ctx.effect(() => ctx.get('sidebarRightTabs').register({ id, kind: id, patterns: ['dsh-resource://geneloop-delivery/**'],
          canOpen: address => { try { parsePreview(address); return true; } catch { return false; } }, title: address => parsePreview(address).file.name }));
        ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: id,
          children: { 'geneloop.delivery.document': { kind: 'keyed', scope: 'session', inject: { hooks: { tabInfo: (_standard, useTabInfo) => useTabInfo } } } },
        }, DeliveryPreview));
        ctx.slots.inject('sidebar.right.tab.document', () => mirrorPublicSlot('sidebar.right.tab.document', 'geneloop.delivery.document'));
      }
      const artifactMeta = file => {
        const name = artifactName(file);
        const extension = (primitives.fileExtension ? primitives.fileExtension(name) : name.includes('.') ? name.split('.').pop() : '').toUpperCase().slice(0, 8);
        const bytes = Number.isFinite(file.bytes) && file.bytes >= 0 ? file.bytes : undefined;
        const size = bytes === undefined ? '' : primitives.fileSizeText ? primitives.fileSizeText(bytes) : bytes < 1024 ? bytes + 'B' : bytes < 1048576 ? Math.round(bytes / 1024) + 'KB' : (bytes / 1048576).toFixed(1) + 'MB';
        return [extension || '文件', size].filter(Boolean).join(' ');
      };
      const artifactLinkStyle = `.harless-paired code[data-harless-artifact-inline],.geneloop-product-turn :not(pre)>code:has(>button){display:contents!important;background:transparent!important;border:0!important;padding:0!important;box-shadow:none!important;font:inherit!important;color:inherit!important}.harless-paired [data-harless-artifact-link],.geneloop-product-turn [data-harless-artifact-link],.geneloop-product-turn :not(pre)>code>button{display:inline-flex;vertical-align:baseline;align-items:baseline;gap:0;min-height:0;max-width:100%;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;padding:0!important;color:var(--dsw-alias-link,#729cf7)!important;font:inherit!important;line-height:inherit;white-space:normal;overflow-wrap:anywhere;text-decoration:none;cursor:pointer}.harless-paired [data-harless-artifact-link] code{background:transparent!important;border:0!important;padding:0!important;font:inherit!important;color:inherit}.harless-paired [data-harless-artifact-link] svg,.geneloop-product-turn :not(pre)>code>button svg{display:none}.harless-paired [data-harless-artifact-link]:hover,.geneloop-product-turn :not(pre)>code>button:hover{text-decoration:underline;text-underline-offset:3px}.harless-paired [data-harless-artifact-link]:focus-visible,.geneloop-product-turn :not(pre)>code>button:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:3px;border-radius:2px!important}`;
      // Public primitives are shared with native Chat; do not duplicate SVGs or
      // depend on private Chat components / generated CSS class names.
      const messageIcon = kind => h(primitives[({ copy: 'IconCopyOutline16', check: 'IconCheckOutline16',
        up: 'IconLikeOutline16', upSelected: 'IconLikeFill16', down: 'IconDislikeOutline16', downSelected: 'IconDislikeFill16',
        fork: 'IconBranchOutline16', usage: 'IconDatabaseOutline16', clock: 'IconClockOutline16' })[kind]], { 'aria-hidden': true });
      const actionButton = (props, icon, label) => h(primitives.Tooltip, { label, side: 'bottom', key: props.key },
        h('button', { type: 'button', className: 'harless-message-icon', ...props }, messageIcon(icon)));
      const durationLabel = milliseconds => {
        if (!Number.isFinite(milliseconds)) return '待统计';
        const seconds = Math.max(0, Math.floor(milliseconds / 1000));
        return seconds < 60 ? seconds + '秒' : Math.floor(seconds / 60) + '分' + String(seconds % 60).padStart(2, '0') + '秒';
      };
      const tokenLabel = total => {
        if (!Number.isFinite(total)) return '待统计';
        const scaled = value => String(value >= 100 ? Math.round(value) : Math.round(value * 10) / 10);
        return (total < 1000 ? total : total < 1000000 ? scaled(total / 1000) + 'K' : scaled(total / 1000000) + 'M') + ' tok';
      };
      const usageFacts = result => {
        const stats = result.stats || {}, usage = result.usage || stats.usage || {};
        const input = usage.input ?? usage.prompt_tokens ?? stats.prompt_tokens ?? stats.input_tokens;
        const output = usage.output ?? usage.completion_tokens ?? stats.completion_tokens ?? stats.output_tokens;
        const total = usage.total ?? usage.total_tokens ?? stats.total_tokens ?? (Number.isFinite(input) && Number.isFinite(output) ? input + output : undefined);
        return { input, output, total };
      };
      const messageClock = time => {
        const date = new Date(time), now = new Date();
        if (!Number.isFinite(date.getTime())) return '';
        const clock = String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');
        if (date.toDateString() === now.toDateString()) return clock;
        return (date.getFullYear() === now.getFullYear() ? '' : date.getFullYear() + '年') + (date.getMonth() + 1) + '月' + date.getDate() + '日 ' + clock;
      };
      function ReplyMetric({ kind, label, rows, title }) {
        const [open, setOpen] = React.useState(false), rootRef = React.useRef(null), panelRef = React.useRef(null);
        const pos = primitives.useAnchoredPosition({ open, anchorRef: rootRef, panelRef, side: 'top', gap: 8, margin: 12 });
        primitives.useDismissOnOutsidePointer(rootRef, open, setOpen, panelRef);
        React.useEffect(() => {
          if (!open) return;
          const close = event => { if (event.key === 'Escape') { setOpen(false); rootRef.current?.querySelector('button')?.focus(); } };
          document.addEventListener('keydown', close);
          return () => document.removeEventListener('keydown', close);
        }, [open]);
        return h('span', { className: 'harless-message-metric', ref: rootRef, 'data-open': open || undefined },
          h('button', { type: 'button', className: 'harless-message-metric-trigger', 'aria-label': label,
            'aria-haspopup': 'dialog', 'aria-expanded': open, onClick: () => setOpen(!open) }, messageIcon(kind), h('span', { className: 'harless-message-metric-label' }, label)),
          open && ReactDOM.createPortal(h('div', { ref: panelRef, role: 'dialog', 'aria-label': title, className: 'harless-message-stat-panel',
            style: pos || { visibility: 'hidden', left: 0, top: 0 } }, h('strong', null, title),
            h('dl', null, ...rows.flatMap(([name, value]) => [h('dt', { key: name }, name), h('dd', { key: name + '-value' }, value)]))), document.body));
      }
      function TraceRows({ items, renderImages }) {
        const states = { running: '进行中', completed: '完成', failed: '失败', interrupted: '已中断', cancelled: '已取消', skipped: '已跳过' };
        return h('ol', { className: 'harless-trace-list' }, ...items.map((entry, index) => {
          const skip = entry.verified_skip === true, optimized = entry.optimized === true;
          const label = skip ? '已验证跳过模型请求' : optimized ? '已应用优化' : undefined;
          const detail = entry.text || entry.details;
          const preview = typeof detail === 'string' ? detail.slice(0, 220) : '';
          const time = traceTime(entry.time);
          return h('li', { key: entry.id || index, 'data-kind': entry.kind, 'data-optimized': skip || optimized ? 'true' : undefined },
            h('div', { className: 'harless-trace-event' }, h('span', { className: 'harless-trace-dot', 'aria-hidden': true }),
              h('strong', null, entry.label || ({ assistant: '回复', thinking: '正在思考', tool: '工具调用', motif: 'Motif 核验', request: '模型请求' })[entry.kind] || '执行记录'),
              entry.status && h('small', null, states[entry.status] || entry.status),
              Number.isFinite(time) && h('time', { dateTime: new Date(time).toISOString() }, new Date(time).toLocaleTimeString('zh-CN', { hour12: false }))),
            label && h('span', { className: 'harless-trace-optimization' }, label),
            entry.tool && h('small', { className: 'harless-trace-tool' }, entry.tool),
            preview && h('p', { className: 'harless-trace-preview' }, preview),
            renderImages?.(entry.images),
            entry.args && h('details', null, h('summary', null, '调用参数'), h('pre', null, typeof entry.args === 'string' ? entry.args : JSON.stringify(entry.args, null, 2))),
            detail && h('details', null, h('summary', null, '展开完整内容'), h('pre', null, typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2))));
        }));
      }
      function ComparisonNode({ node, traceOnly = false, useChat }) {
        // Observe the whole timeline, including later ordinary Chat turns.
        const latestTurn = useChat?.(snapshot => snapshot.timeline?.turnOrder.at(-1));
        const turn = node.location?.turn?.turn;
        const isLatestTurn = latestTurn === undefined || turn === undefined || latestTurn === turn;
        const key = comparisonKey(node.data), initial = rememberedSnapshot(node.data);
        const [snapshot, setValue] = React.useState(initial), [error, setError] = React.useState(''), [saving, setSaving] = React.useState(false);
        const value = comparisonKey(snapshot) === key ? snapshot : initial;
        const [loadedKey, setLoadedKey] = React.useState(comparisonSnapshots.has(key) || settled(initial) ? key : '');
        const hydrated = loadedKey === key || comparisonSnapshots.has(key) || settled(initial);
        const serverSnapshot = React.useRef(initial);
        const [connection, setConnection] = React.useState(''), [downloads, setDownloads] = React.useState({});
        const pageLoadRelease = React.useRef();
        React.useLayoutEffect(() => {
          const release = window.__geneLoopPageLoad?.hold(node.data.session_id);
          pageLoadRelease.current = release;
          if (hydrated || error || connection) release?.();
          return () => { release?.(); if (pageLoadRelease.current === release) pageLoadRelease.current = undefined; };
        }, [node.data.id, node.data.session_id]);
        React.useLayoutEffect(() => {
          if (hydrated || error || connection) pageLoadRelease.current?.();
        }, [hydrated, error, connection]);
        const [branching, setBranching] = React.useState(''), branchBusy = React.useRef(false);
        const [copied, setCopied] = React.useState('');
        const copyTimer = React.useRef(), copyPending = React.useRef(false);
        const generation = React.useRef(0), actionBusy = React.useRef(false), downloadBusy = React.useRef(new Set());
        const alive = React.useRef(true), transferControllers = React.useRef(new Set()), refreshNow = React.useRef(() => {});
        const streamConnected = React.useRef(false);
        const streamBlocked = React.useRef(false);
        const closeLiveStream = React.useRef(() => {});
        const acceptSnapshot = next => {
          if (olderSnapshot(next, serverSnapshot.current) || !rememberSnapshot(next)) return false;
          serverSnapshot.current = next; setValue(next); setLoadedKey(comparisonKey(next)); return true;
        };
        React.useEffect(() => {
          alive.current = true; streamBlocked.current = false; setDownloads({}); setError(''); setConnection(''); setSaving(false);
          setCopied(''); setBranching(''); branchBusy.current = false;
          serverSnapshot.current = initial;
          actionBusy.current = false; downloadBusy.current.clear(); generation.current++;
          return () => { alive.current = false; clearTimeout(copyTimer.current); for (const abort of transferControllers.current) abort.abort(); };
        }, [node.data.id, node.data.session_id]);
        // Persisted start-event data may be reassembled with a fresh object while
        // GET already holds newer results. Reset only when viewing another turn.
        React.useEffect(() => { setValue(initial); setLoadedKey(comparisonSnapshots.has(key) || settled(initial) ? key : ''); }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          // Chat and trajectory can both render the same turn. A result saved
          // by either view must also update the other without a stale flash.
          const listener = next => {
            if (!alive.current || olderSnapshot(next, serverSnapshot.current)) return;
            serverSnapshot.current = next; setValue(next); setLoadedKey(key);
          };
          const group = comparisonObservers.get(key) || new Set(); group.add(listener); comparisonObservers.set(key, group);
          return () => { group.delete(listener); if (!group.size) comparisonObservers.delete(key); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          const abort = new AbortController(); let timer, failures = 0, pending = false, rerun = false;
          const poll = async () => {
            if (abort.signal.aborted) return;
            if (pending) { rerun = true; return; }
            clearTimeout(timer); pending = true; let delay = 0;
            const revision = generation.current;
            try {
              const next = await comparisonRequest(node.data, undefined, abort.signal);
              let applied = false;
              if (!abort.signal.aborted && revision === generation.current && !actionBusy.current) {
                applied = acceptSnapshot(next); setConnection(''); failures = 0;
              }
              // An open HTTP connection does not prove that its proxy forwards
              // snapshots. Keep a low-frequency, read-only recovery path even
              // after the stream has delivered data; never replay a submission.
              if (!applied || !settled(next) || actionBusy.current)
                delay = document.hidden ? 8000 : streamConnected.current ? 5000 : 1800;
            } catch (e) {
              if (!abort.signal.aborted) {
                failures++;
                const denied = [401, 403, 404].includes(e.status);
                if (denied) { streamBlocked.current = true; closeLiveStream.current(); }
                setConnection(networkMessage(e) + (denied ? '' : ' 正在自动重连…'));
                if (!denied) delay = Math.min(30000, 1800 * 2 ** Math.min(failures, 5));
              }
            } finally { pending = false; }
            if (!abort.signal.aborted && (delay || rerun)) { timer = setTimeout(poll, rerun ? 0 : delay); rerun = false; }
          };
          const wake = () => { if (!document.hidden) void poll(); };
          refreshNow.current = poll;
          window.addEventListener('online', wake); window.addEventListener('focus', wake); document.addEventListener('visibilitychange', wake);
          void poll();
          return () => { abort.abort(); clearTimeout(timer); refreshNow.current = () => {};
            window.removeEventListener('online', wake); window.removeEventListener('focus', wake); document.removeEventListener('visibilitychange', wake); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          if (settled(value) || !window.EventSource) return;
          const identity = comparisonIdentity;
          let stream, retryTimer, stallTimer, disposed = false, failures = 0;
          const stopStream = () => { clearTimeout(stallTimer); stream?.close(); streamConnected.current = false; };
          const close = () => { disposed = true; clearTimeout(retryTimer); stopStream(); };
          closeLiveStream.current = close;
          const connect = () => {
            if (disposed || streamBlocked.current || identity !== comparisonIdentity) return;
            const current = new window.EventSource(comparisonUrl(node.data) + '&stream=1', { withCredentials: true });
            stream = current;
            const alive = () => !disposed && stream === current && !streamBlocked.current && identity === comparisonIdentity;
            const watch = () => { clearTimeout(stallTimer); stallTimer = setTimeout(() => { if (alive()) current.onerror(); }, 10000); };
            // Only an authenticated snapshot establishes stream liveness.
            current.onopen = () => { if (alive()) watch(); };
            current.onmessage = event => {
              if (!alive() || actionBusy.current) return;
              try {
                const next = JSON.parse(event.data);
                if (next.id !== node.data.id || next.session_id !== node.data.session_id || !next.lanes?.baseline
                  || (next.presentation !== 'single' && !next.lanes?.motif)) throw Error('Invalid stream result');
                if (!acceptSnapshot(next)) return;
                streamConnected.current = true; failures = 0; watch();
                generation.current++; setConnection('');
                if (settled(next)) close();
              } catch { current.onerror(); }
            };
            current.addEventListener('snapshot', current.onmessage);
            current.onerror = () => {
              if (!alive()) return;
              stopStream(); stream = undefined;
              // A stream reconnect is read-only. Never replay a paid request.
              void refreshNow.current();
              retryTimer = setTimeout(connect, Math.min(30000, 2000 * 2 ** Math.min(failures++, 4)));
            };
            watch();
          };
          connect();
          return () => { close(); if (closeLiveStream.current === close) closeLiveStream.current = () => {}; };
        }, [node.data.id, node.data.session_id, settled(value)]);
        React.useEffect(() => {
          if (!hydrated || settled(value)) return;
          updateBusy(value.session_id, value.id, true);
          return () => updateBusy(value.session_id, value.id, false);
        }, [value.session_id, value.id, value.status, hydrated]);
        const action = async body => {
          if (actionBusy.current) return;
          actionBusy.current = true; generation.current++; setSaving(true); setError('');
          const revision = generation.current, abort = new AbortController(); transferControllers.current.add(abort);
          const current = () => alive.current && generation.current === revision && !abort.signal.aborted;
          try { const next = await comparisonRequest(value, body, abort.signal); if (current()) { acceptSnapshot(next); setConnection(''); } }
          catch (e) { if (current()) setError(networkMessage(e) + (!e.status || e.status === 408 ? ' 将重新读取状态，请勿重复提交。' : '')); }
          finally {
            transferControllers.current.delete(abort);
            if (alive.current && generation.current === revision) { actionBusy.current = false; setSaving(false); void refreshNow.current(); }
          }
        };
        const fork = async lane => {
          const output = value.lanes[lane].output_sha256;
          if (branchBusy.current || !output || !settled(value)) return;
          branchBusy.current = true; setBranching(lane); setError('');
          const abort = new AbortController(); transferControllers.current.add(abort);
          try {
            const result = await withDeadline(abort.signal, 30000, async signal => {
              const response = await fetch(comparisonUrl(value), { method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: value.session_id, id: value.id,
                  action: 'fork', lane, output_sha256: output }) });
              let body; try { body = await response.json(); } catch { throw apiError(502); }
              if (!response.ok || body.error) throw apiError(response.status, body.error?.message);
              if (typeof body.sessionId !== 'string' || !body.sessionId) throw apiError(502, '服务器未返回分支会话。');
              return body;
            });
            if (alive.current && !abort.signal.aborted) sessions.open(result.sessionId);
          } catch (error) { if (alive.current && !abort.signal.aborted) setError(networkMessage(error)); }
          finally { transferControllers.current.delete(abort); branchBusy.current = false; if (alive.current) setBranching(''); }
        };
        const copy = async lane => {
          const result = value.lanes[lane], text = (result.answer_display ?? result.answer) || result.messages?.at(-1)?.text;
          if (!text || copyPending.current || copied === lane) return;
          const revision = generation.current; copyPending.current = true;
          try {
            if (primitives.writeClipboard) { if (!await primitives.writeClipboard(text)) throw Error('clipboard unavailable'); }
            else { if (!window.navigator?.clipboard?.writeText) throw Error('clipboard unavailable'); await window.navigator.clipboard.writeText(text); }
            if (alive.current && generation.current === revision) {
              clearTimeout(copyTimer.current); setCopied(lane); setError('');
              copyTimer.current = setTimeout(() => { if (alive.current) setCopied(''); }, 1000);
            }
          } catch { if (alive.current && generation.current === revision) setError('未能复制，请选中回复文字后复制。'); }
          finally { copyPending.current = false; }
        };
        const download = async (lane, file) => {
          const key = lane + ':' + file.id;
          if (downloadBusy.current.has(key)) return;
          downloadBusy.current.add(key);
          const abort = new AbortController(); transferControllers.current.add(abort);
          const state = row => { if (alive.current) setDownloads(old => ({ ...old, [key]: row })); };
          state({ phase: 'pending', message: '正在准备下载…' });
          try {
            const blob = await withDeadline(abort.signal, 60000, requestSignal => readArtifact(value, lane, file, requestSignal));
            if (abort.signal.aborted) return;
            const url = URL.createObjectURL(blob), link = document.createElement('a');
            link.href = url; link.download = file.name.split('/').pop(); link.hidden = true;
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 60000);
            state({ phase: 'success', message: '已交给浏览器下载，请查看下载列表。' });
          } catch (e) { if (!abort.signal.aborted) state({ phase: 'error', message: networkMessage(e) + ' 点击下载按钮重试。' }); }
          finally { downloadBusy.current.delete(key); transferControllers.current.delete(abort); }
        };
        const labels = { preparing: '准备中', queued: '等待执行', running: '运行中', completed: '回复完成', failed: '失败', cancelled: '已取消' };
        // Cold history has no verified output yet. Render no result frame until
        // hydration finishes; keep connection recovery reachable on failure.
        if (!hydrated) return !traceOnly && !connection ? null : h('div', { 'data-comparison-id': value.id, 'aria-busy': true },
          traceOnly && h('p', { role: 'status' }, '正在加载此轮轨迹…'),
          connection && h('div', { role: 'status', className: 'harless-paired-connection' }, connection,
            h('button', { type: 'button', onClick: () => refreshNow.current() }, '重新连接'),
            connection.includes('登录') && h('a', { href: '/login', style: { marginLeft: 8 } }, '登录')));
        const pane = lane => {
          const result = value.lanes[lane], files = result.artifacts || [], title = lane === 'baseline' ? 'Baseline' : result.mode === 'shadow' ? 'Motif · 影子评估' : 'Motif';
          const single = value.presentation === 'single';
          const notStarted = result.delivery_status === 'not_started';
          const activity = Array.isArray(result.activity) ? result.activity : [];
          const messages = Array.isArray(result.messages) ? result.messages.filter(message => message.text) : [];
          const answer = (result.answer_display ?? result.answer) || messages.at(-1)?.text || '';
          // The latest message occupies the answer seat. On completion its
          // bound answer_display may differ from raw template text; do not show
          // the unbound last message a second time in the process section.
          const previousMessages = messages.slice(0, -1);
          const progressLabel = progressText(result);
          const captureLink = event => {
            const link = event.target.closest?.('a'); if (!link) return;
            const raw = link.getAttribute('href') || '', file = artifactFor(files, raw) || files.find(file => raw === artifactPreviewLink(value, lane, file));
            if (file) { event.preventDefault(); event.stopPropagation(); try { openArtifact(value, lane, file); } catch (error) { setError(error.message); } }
            else if (raw && !/^(https?:|mailto:|#)/i.test(raw)) {
              event.preventDefault(); event.stopPropagation();
              setError('此路径尚未登记为可下载成品，请使用该侧“交付文件”中的下载按钮。');
            }
          };
          const mentions = { resolve: raw => { const file = artifactFor(files, raw); return file ? {
            title: artifactName(file), label: '预览 ' + artifactName(file), open: () => { try { openArtifact(value, lane, file); } catch (error) { setError(error.message); } },
          } : undefined; } };
          const usage = usageFacts(result), duration = result.duration_ms ?? (Number.isFinite(result.stats?.elapsed_seconds) ? result.stats.elapsed_seconds * 1000 : undefined);
          const count = value => Number.isFinite(value) ? value.toLocaleString('en-US') + ' tok' : '待统计';
          return h('section', { key: lane, className: 'harless-paired-pane' + (single ? ' harless-single-pane' : ''), 'aria-label': single ? '回复' : title,
            'data-actions-reveal': isLatestTurn ? 'always' : 'hover' },
            !single && h('header', null, h('strong', null, title), h('span', { role: 'status' }, notStarted ? '任务未启动' : result.status === 'completed' && result.delivery_status === 'available' ? '已交付' : labels[result.status] || result.status)),
            h('style', null, liveStyle),
            single && !settled(result) && liveStatus(progressLabel),
            (activity.length > 0 || previousMessages.length > 0) && h('details', { className: 'harless-activity' },
              h('summary', null, '查看执行过程'),
              activity.length > 0 && h('ol', null, ...activity.map((entry, index) => h('li', { key: index, 'data-status': entry.status },
                h('span', null, entry.label), h('small', null, ({ running: '进行中', completed: '完成', failed: '未完成' })[entry.status] || '')))),
              ...(!settled(result) ? [] : previousMessages).map(message => h('section', { key: message.id, className: 'harless-process-message',
                onClickCapture: captureLink, ref: root => compactArtifactLabels(root, files) },
                MarkdownText ? h(MarkdownText, { text: artifactMarkdown(message.text, files, value, lane), streaming: message.status === 'streaming', labels: markdownLabels, fileMentions: mentions }) : h('p', null, message.text)))),
            result.fallback_reason && h('p', { className: result.fallback_reason === 'rsi_requires_approved_sources' ? 'harless-paired-muted' : 'harless-paired-notice' },
              result.fallback_reason === 'rsi_requires_approved_sources'
                ? '本轮未绑定可复用的资料，按标准流程回答。上传资料并通过校验后，才会尝试优化。'
                : '优化未启用，已回退普通模式：' + result.fallback_reason),
            result.failure && h('p', { role: 'alert', className: 'harless-paired-notice' }, result.failure),
            !settled(result) && previousMessages.length > 0 && h('div', { className: 'harless-stream-messages', onClickCapture: captureLink,
              ref: root => compactArtifactLabels(root, files) }, ...previousMessages.map(message => h('section', {
                key: message.id, className: 'harless-process-message', 'data-message-id': message.id,
              }, MarkdownText ? h(MarkdownText, { text: artifactMarkdown(message.text, files, value, lane), streaming: message.status === 'streaming', labels: markdownLabels, fileMentions: mentions }) : h('p', null, message.text)))),
            h('div', { className: 'harless-paired-answer', ref: root => compactArtifactLabels(root, files), onClickCapture: captureLink }, answer
              ? h(BufferedMarkdown, { text: artifactMarkdown(answer, files, value, lane), streaming: !settled(result), identity: key + ':' + lane + ':' + (messages.at(-1)?.id || 'answer'), labels: markdownLabels, fileMentions: mentions })
              : null),
            files.length > 0 && h('section', { className: 'harless-paired-deliveries', 'aria-label': title + '交付文件' },
              h('h4', null, '交付文件'), h('ul', { className: 'harless-paired-files' }, ...files.map(file => {
                const status = downloads[lane + ':' + file.id];
                const name = artifactName(file);
                return h('li', { key: file.id }, h('div', { className: 'harless-artifact-card' },
                  h('button', { className: 'harless-artifact-preview', type: 'button', 'aria-label': '预览 ' + name,
                    onClick: () => { try { openArtifact(value, lane, file); } catch (error) { setError(error.message); } } },
                  h('span', { className: 'harless-artifact-icon', 'aria-hidden': true }, primitives.FileTypeIcon ? h(primitives.FileTypeIcon, { path: name }) : h('span', null, '▤')),
                  h('span', { className: 'harless-artifact-body' },
                    h('span', { className: 'harless-paired-filename', title: name }, name),
                    h('span', { className: 'harless-artifact-meta' }, artifactMeta(file)))),
                  h(primitives.Tooltip, { label: status?.phase === 'pending' ? '正在准备下载…' : '下载 ' + name, side: 'bottom' },
                    h('a', { className: 'harless-artifact-download', href: comparisonUrl(value, lane, file), download: name, rel: 'nofollow',
                      'aria-label': '下载 ' + name, 'aria-disabled': status?.phase === 'pending', 'aria-busy': status?.phase === 'pending',
                      onClick: event => { event.preventDefault(); void download(lane, file); } },
                      status?.phase === 'pending' ? h('span', { className: 'harless-artifact-spinner', 'aria-hidden': true }) : h(primitives.IconDownloadOutline16, { 'aria-hidden': true })))),
                  status && h('small', { role: status.phase === 'error' ? 'alert' : 'status', className: status.phase === 'error' ? 'harless-paired-error' : 'harless-paired-muted' }, status.message));
              }))),
            !single && !settled(result) && h('p', { className: 'geneloop-looping', role: 'status',
              'aria-label': title + ' 正在处理', title: progressLabel }, 'GeneLooping…'),
            settled(result) && h('footer', null,
              h('div', { className: 'harless-message-actions', 'aria-label': title + '回复操作' },
                actionButton({ 'aria-label': '复制 ' + title + ' 回复', disabled: !answer, onClick: () => copy(lane) }, copied === lane ? 'check' : 'copy', copied === lane ? '已复制' : '复制'),
                ...['up', 'down'].map(vote => actionButton({ key: vote,
                  'aria-label': (vote === 'up' ? '赞 ' : '踩 ') + title + ' 回复', 'aria-pressed': result.feedback === vote,
                  disabled: saving || !settled(result) || !result.output_sha256,
                  onClick: () => action({ action: 'feedback', lane, vote: result.feedback === vote ? null : vote, output_sha256: result.output_sha256 }) },
                  vote + (result.feedback === vote ? 'Selected' : ''), result.feedback === vote ? '取消标记' : vote === 'up' ? '好的回答' : '有问题的回答')),
                actionButton({ 'aria-label': '从 ' + title + ' 在新对话中分支', disabled: !!branching || !settled(value) || !result.output_sha256,
                  onClick: () => fork(lane) }, 'fork', branching === lane ? '正在创建分支…' : '在新对话中分支'),
                h('span', { className: 'harless-message-metrics' },
                Number.isFinite(usage.total) && h(ReplyMetric, { kind: 'usage', label: '用量 ' + tokenLabel(usage.total), title: title + ' · 本轮用量',
                  rows: [['总用量', count(usage.total)], ['输入', count(usage.input)], ['输出', count(usage.output)]] }),
                Number.isFinite(duration) && h(ReplyMetric, { kind: 'clock', label: '用时 ' + durationLabel(duration), title: title + ' · 本轮用时',
                  rows: [['本轮总用时', durationLabel(duration)], ...(result.started_at ? [['开始时间', messageClock(result.started_at)]] : []),
                    ...(result.finished_at ? [['完成时间', messageClock(result.finished_at)]] : [])] }),
                result.finished_at && messageClock(result.finished_at) && h('time', { className: 'harless-message-time', dateTime: result.finished_at }, messageClock(result.finished_at))),
                copied === lane && h('span', { role: 'status', className: 'harless-visually-hidden' }, '已复制')),
              h('small', null, `模型请求 ${result.stats?.upstream_requests || 0} · ${result.mode === 'shadow' ? '预测候选 ' + (result.stats?.shadow_candidates || 0) : '已验证跳过 ' + (result.stats?.verified_skips || 0)}`),
              ['failed', 'cancelled'].includes(result.status) && settled(value) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'retry', lane }) }, '重试此侧')));
        };
        if (traceOnly) {
          const paired = isPairedTrace(value), laneKeys = paired ? ['baseline', 'motif'] : ['baseline'];
          return h('section', { className: 'harless-comparison-trace', 'data-comparison-id': value.id },
            h('div', { className: 'harless-trace-columns', 'data-single': paired ? undefined : 'true' }, ...laneKeys.map(lane => {
              const result = value.lanes[lane];
              return h('section', { key: lane, className: 'harless-trace-column', 'data-lane': lane },
                h('header', null, h('strong', null, paired ? lane === 'baseline' ? 'Baseline' : result.mode === 'shadow' ? 'Motif · 影子评估' : 'Motif' : '执行过程'),
                  h('p', { role: 'status', 'aria-live': 'polite', className: 'harless-live-status' }, result.progress?.label || labels[result.status])),
                result.trace?.length ? h(TraceRows, { items: result.trace }) : h('p', { className: 'harless-paired-muted' },
                  settled(result) ? '此轮没有可用的执行事件。' : '等待实际执行事件…'));
            })),
            connection && h('p', { role: 'status', className: 'harless-paired-connection' }, connection));
        }
        return h('div', { className: 'harless-paired', 'data-comparison-id': value.id },
          h('style', null, `.harless-paired{width:100%;min-width:0;container-type:inline-size;margin:18px 0;color:var(--dsw-alias-label-primary,inherit);font-family:var(--dsw-font-family,inherit);font-size:var(--dsh-content-font-size,14px)}.harless-paired-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.harless-paired-pane{min-width:0;container-type:inline-size;border:0;border-radius:0;padding:18px;background:transparent;box-shadow:none}.harless-paired-pane>header{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #8883;padding-bottom:12px}.harless-paired-pane>header>span,.harless-paired-pane small{font-size:12px;line-height:1.5;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-pane>header>strong{font-size:15px}.harless-paired-answer{overflow-wrap:anywhere;line-height:1.65;margin:18px 0;min-width:0}.harless-paired-answer pre{max-width:100%;overflow-x:auto}.harless-paired-answer table{font-size:inherit}.harless-paired-notice{font-size:13px;line-height:1.6;border-left:3px solid #b99555;padding-left:10px}.harless-paired-pane>footer{display:grid;gap:12px;margin-top:20px;padding-top:14px;border-top:1px solid #8883}.harless-paired button{border:1px solid #8885;border-radius:8px;padding:7px 12px;background:transparent;color:inherit;cursor:pointer;font:inherit}.harless-paired button:disabled{opacity:.5}.harless-paired-error{font-size:13px;line-height:1.6;color:var(--dsw-alias-state-error-primary,#d66)!important;margin-top:10px}.harless-paired-connection{font-size:13px;line-height:1.6;margin:12px 0;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-connection button{margin-left:8px}.harless-paired-deliveries h4{font-size:13px;font-weight:500;margin:0 0 10px}.harless-paired-files{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:10px}.harless-paired-files>li{flex:0 1 260px;min-width:0;max-width:100%}.harless-artifact-card{display:flex;align-items:center;gap:10px;box-sizing:border-box;width:100%;height:64px;padding:0 12px;border:.5px solid var(--dsw-alias-border-l2,#8884);border-radius:16px;background:var(--dsw-specific-input-major,transparent);text-align:left}.harless-artifact-icon{display:flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px}.harless-artifact-icon>svg{width:28px;height:28px}.harless-artifact-body{display:flex;flex-direction:column;flex:1;min-width:0;gap:2px}.harless-paired-filename{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--dsw-alias-label-primary,inherit);font-size:14px;font-weight:500;line-height:22px}.harless-artifact-meta{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--dsw-alias-label-tertiary,#888);font-size:12px;line-height:15px}.harless-artifact-download{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;border:0;border-radius:8px;background:transparent;color:var(--dsw-alias-label-secondary,inherit);text-decoration:none;cursor:pointer}.harless-artifact-download:hover{background:var(--dsw-alias-interactive-bg-hover,#8882);color:var(--dsw-alias-label-primary,inherit)}.harless-artifact-download:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}.harless-artifact-download[aria-disabled=true]{cursor:progress;color:var(--dsw-alias-label-secondary,inherit)}.harless-artifact-spinner{box-sizing:border-box;width:14px;height:14px;border:1.5px solid currentColor;border-top-color:transparent;border-radius:50%;animation:harless-artifact-spin .8s linear infinite}@keyframes harless-artifact-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.harless-artifact-spinner{animation:none;border-style:dotted}}.harless-paired-muted{color:var(--dsw-alias-label-secondary,inherit);font-size:13px}.harless-paired-files small{display:block;margin:5px 4px 0;overflow-wrap:anywhere}@container(max-width:650px){.harless-paired-grid{grid-template-columns:1fr}.harless-paired-pane{padding:16px}}`),
          h('style', null, artifactLinkStyle),
          h('style', null, `.harless-single-pane{border:0;border-radius:0;padding:0;background:transparent}.harless-activity{font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary,inherit);margin:12px 0}.harless-activity summary{cursor:pointer}.harless-activity ol{padding-left:20px;margin:8px 0}.harless-activity li{padding:4px 0}.harless-activity li small{margin-left:12px}.harless-activity li[data-status=running]{color:var(--dsw-alias-state-business-primary,#729cf7)}`),
          h('style', null, `.harless-message-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-height:calc(28px + var(--dsh-content-font-delta,0px));margin-left:-6px;color:var(--dsw-alias-label-tertiary)}
.harless-paired .harless-message-icon{display:inline-flex;align-items:center;justify-content:center;width:calc(28px + var(--dsh-content-font-delta,0px));height:calc(28px + var(--dsh-content-font-delta,0px));padding:6px;border:0;border-radius:28px;flex:none;color:var(--dsw-alias-label-tertiary)}
.harless-message-actions svg{width:calc(15px + var(--dsh-content-font-delta,0px));height:calc(15px + var(--dsh-content-font-delta,0px));flex:none}
.harless-paired .harless-message-icon:hover,.harless-paired .harless-message-metric-trigger:hover{background:var(--dsw-alias-interactive-bg-hover);color:var(--dsw-alias-label-secondary)}
.harless-paired .harless-message-icon:disabled{cursor:default;opacity:.4;background:transparent}
.harless-message-icon:focus-visible,.harless-message-metric-trigger:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}
.harless-message-metrics{display:inline-flex;align-items:center;flex-wrap:wrap;gap:8px;max-width:100%}.harless-message-metric{display:inline-flex;min-width:0}.harless-message-metric+.harless-message-metric{margin-left:-6px}
.harless-paired .harless-message-metric-trigger{display:inline-flex;align-items:center;gap:4px;min-width:0;height:calc(28px + var(--dsh-content-font-delta,0px));padding:6px 8px;border:0;border-radius:28px;color:var(--dsw-alias-label-tertiary);font-size:var(--dsh-content-font-size-secondary,13px);font-variant-numeric:tabular-nums;line-height:calc(24px + var(--dsh-content-font-delta,0px));white-space:nowrap}
.harless-message-metric-label{min-width:0;overflow:hidden;text-overflow:ellipsis}.harless-message-time{font-size:var(--dsh-content-font-size-secondary,13px);line-height:calc(24px + var(--dsh-content-font-delta,0px));color:var(--dsw-alias-label-tertiary);white-space:nowrap}
.harless-visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(hover:hover){.harless-paired-pane[data-actions-reveal=hover] .harless-message-actions{opacity:0;transition:opacity 80ms}.harless-paired-pane[data-actions-reveal=hover]:hover .harless-message-actions,.harless-paired-pane[data-actions-reveal=hover]:focus-within .harless-message-actions,.harless-paired-pane[data-actions-reveal=hover]:has(.harless-message-metric[data-open]) .harless-message-actions{opacity:1}}
@media(prefers-reduced-motion:reduce){.harless-paired-pane[data-actions-reveal=hover] .harless-message-actions{transition:none}}
@media(max-width:480px){.harless-message-metric-label{display:none}}
.harless-message-stat-panel{position:fixed;z-index:1100;box-sizing:border-box;width:280px;max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);overflow:auto;border:1px solid var(--dsw-alias-outline-default,#8885);border-radius:12px;padding:16px;background:var(--dsw-specific-menu,#262626);color:var(--dsw-alias-label-primary);font-family:inherit;font-size:13px;line-height:1.5;box-shadow:0 8px 32px #0003}
.harless-message-stat-panel>strong{display:block;padding-bottom:12px;border-bottom:1px solid var(--dsw-alias-outline-default,#8885);font-weight:500}.harless-message-stat-panel dl{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;margin:12px 0 0}.harless-message-stat-panel dt{color:var(--dsw-alias-label-secondary)}.harless-message-stat-panel dd{margin:0;font-variant-numeric:tabular-nums}
.harless-live-status{display:flex;align-items:center;gap:8px;font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary,inherit);margin:12px 0}.harless-live-dot{width:6px;height:6px;flex:none;border-radius:50%;background:var(--dsw-alias-state-business-primary,#729cf7)}.harless-process-message{padding:10px 0;border-top:1px solid #8883;overflow-wrap:anywhere}.harless-process-message pre{max-width:100%;overflow-x:auto}`),
          h('div', { className: value.presentation === 'single' ? 'harless-single' : 'harless-paired-grid' }, pane('baseline'), value.presentation !== 'single' && pane('motif')),
          !settled(value) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'cancel' }), style: { marginTop: 12 } }, '停止生成'),
          connection && h('div', { role: 'status', className: 'harless-paired-connection' }, connection,
            h('button', { type: 'button', onClick: () => refreshNow.current() }, '重新连接'),
            connection.includes('登录') && h('a', { href: '/login', style: { marginLeft: 8 } }, '登录')),
          error && h('div', { role: 'alert', className: 'harless-paired-error' }, error));
      }
      ctx.effect(() => ctx.uiConversation.events.register({ kind: 'harless-comparison', target: 'chat',
        match: event => event.type === 'user/message' && event.data.harless_comparison ? { id: event.data.harless_comparison.id, role: 'start' } : null,
        start: (_context, match) => match.event.data.harless_comparison.value,
        update: context => context.state,
        buildViewNode: context => context.start && context.state ? { key: context.key, kind: 'harless-comparison', id: context.id, target: 'chat',
          anchorSeq:context.start.event.seq,location:context.start.location,visibility:'visible',data: context.state } : null,
      }), 'harless-comparison-definition');
      ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({ name: 'conversation.chat.node', key: 'harless-comparison' }, ComparisonNode));
      function mirrorPublicSlot(source, target) {
        let cleanups = [];
        const sync = () => {
          cleanups.reverse().forEach(dispose => dispose()); cleanups = [];
          for (const [index, entry] of (ctx.slots.entries(source) || []).entries()) {
            const names = Object.fromEntries(Object.keys(entry.children || {}).map(name => [name, `${target}.${index}.${name}`]));
            const children = Object.fromEntries(Object.entries(entry.children || {}).map(([name, spec]) => [names[name], spec]));
            const component = Object.keys(names).length ? props => h(entry.component, { ...props,
              renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options),
              ...(props.renderSlotChain ? { renderSlotChain: (name, owner, options) => props.renderSlotChain(names[name] || name, owner, options) } : {}),
            }) : entry.component;
            cleanups.push(ctx.slots.register({ name: target, ...entry.options, locale: entry.locale, inject: entry.inject,
              ...(entry.select ? { select: entry.select } : {}), ...(entry.store ? { store: entry.store } : {}),
              ...(Object.keys(children).length ? { children } : {}),
            }, component));
            for (const [name, alias] of Object.entries(names)) cleanups.push(mirrorPublicSlot(name, alias));
          }
        };
        sync(); const unsubscribe = ctx.slots.subscribe?.(source, sync);
        return () => { unsubscribe?.(); cleanups.reverse().forEach(dispose => dispose()); };
      }
      window.__installGeneLoopLoading?.(ctx, React, mirrorPublicSlot);
      // Adapt public seats/stores only: preserve native upload/editor ownership
      // and server-side permission enforcement; add an accessible effort range.
      if (ctx.slots.entries && ctx.slots.subscribe) {
        const hiddenCommands = new Set(['export', 'feedback', 'harless', 'permission', 'model']);
        const filteredMenus = new WeakSet(), modelChoices = new Map();
        function webMenu(id) {
          const scope = sessions.scope(id), menu = scope && triggers.sessionOf?.(scope)?.menu;
          if (!menu || filteredMenus.has(menu)) return;
          filteredMenus.add(menu);
          const filter = () => {
            const before = menu.getSnapshot(); let changed = false;
            const groups = before.groups.map(group => {
              if (group.source === 'reference') {
                const items = group.items.filter(item => {
                  try { return JSON.parse(item.value).kind === 'session'; } catch { return false; }
                }).map(item => item.description === undefined ? item : { ...item, description: undefined });
                if (items.length !== group.items.length || items.some((item, i) => item !== group.items[i])) {
                  changed = true; return { ...group, items };
                }
                return group;
              }
              if (group.source !== 'command') return group;
              const items = group.items.filter(item => !hiddenCommands.has(item.name));
              if (items.length === group.items.length) return group;
              changed = true; return { ...group, items };
            });
            if (!changed) return;
            const previous = before.highlight && before.groups.find(group => group.source === before.highlight.source)?.items[before.highlight.index];
            const highlighted = before.highlight && groups.find(group => group.source === before.highlight.source);
            const index = highlighted?.items.indexOf(previous) ?? -1;
            const first = groups.find(group => group.items.length);
            menu.set({ ...before, groups, open: before.open && groups.some(group => group.status === 'pending' || group.items.length),
              highlight: index >= 0 ? { source: highlighted.source, index } : first ? { source: first.source, index: 0 } : null });
          };
          filter(); scope.effect(() => menu.subscribe(filter), 'geneloop: web command menu');
        }
        function optimisticModel(id, native) {
          if (modelChoices.has(id)) return modelChoices.get(id);
          const scope = sessions.scope(id), face = sessions.binding(id)?.session;
          let tail = Promise.resolve(), latestChoice = Promise.resolve(true), pending = 0, revision = 0, disposed = false;
          let desired, confirmed = native.directory.getSnapshot().current, awaitingProjection, error = null, snapshot;
          const listeners = new Set();
          const same = (a, b) => a?.provider === b?.provider && a?.model === b?.model && a?.reasoningEffort === b?.reasoningEffort;
          const publishModel = () => {
            if (disposed) return;
            const source = native.directory.getSnapshot();
            if (awaitingProjection && same(source.current, awaitingProjection)) awaitingProjection = undefined;
            if (!pending && !awaitingProjection) confirmed = source.current;
            snapshot = { ...source, current: desired || confirmed, selectionPending: pending > 0, status: pending ? 'ready' : error ? 'error' : source.status,
              error: error || (pending ? null : source.error) };
            for (const listener of listeners) listener();
          };
          const enqueue = operation => {
            const run = tail.then(() => { if (disposed) throw Error('会话已关闭，请重新打开后重试。'); return operation(); });
            tail = run.catch(() => {}); return run;
          };
          const value = { ...native, directory: { getSnapshot: () => snapshot,
            subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); } },
            select(selection) {
              if (!native.available || disposed) return Promise.resolve(false);
              const chosen = { ...selection }, version = ++revision;
              pending++; desired = chosen; error = null; publishModel();
              const operation = enqueue(async () => {
                let accepted = false, failure;
                try {
                  accepted = await native.select(chosen);
                  if (!accepted) failure = native.directory.getSnapshot().error || '服务器未接受此选项。';
                } catch (cause) { failure = cause.message || '连接暂时中断。'; }
                if (disposed) return false;
                if (accepted) { confirmed = chosen; awaitingProjection = chosen; }
                pending--;
                if (version === revision) {
                  desired = undefined;
                  if (!accepted) {
                    error = '模型切换未保存，已恢复之前的选项。' + failure;
                    conversation.input.for(scope)?.notify?.('error', error);
                  }
                  // New sends may use the restored selection; an already
                  // queued send keeps the failed promise and retains its draft.
                  latestChoice = Promise.resolve(true);
                }
                publishModel(); return accepted;
              });
              latestChoice = operation;
              operation.catch(() => {});
              // Native menu closes now; the queue persists across navigation.
              return Promise.resolve(true);
            } };
          publishModel();
          const unsubscribe = native.directory.subscribe(publishModel);
          const prompt = face?.prompt;
          const beginSubmission = face?.beginSubmission, submissions = new Map();
          const beginEcho = beginSubmission && function (input) {
            let handle;
            handle = beginSubmission.call(this, { ...input, onRetire: settlement => {
              submissions.delete(handle?.requestId); input.onRetire?.(settlement);
            } });
            submissions.set(handle.requestId, handle); return handle;
          };
          if (beginEcho) face.beginSubmission = beginEcho;
          const queuedPrompt = prompt && function (...args) {
            const selection = latestChoice;
            return enqueue(async () => {
              if (!await selection) throw Error('模型切换未成功，消息尚未发送，请确认模型后重试。');
              if (args[2]?.aborted) throw Error('发送已取消。');
              return prompt.apply(this, args);
            }).catch(error => { submissions.get(args[3])?.abandon(); throw error; });
          };
          if (queuedPrompt) face.prompt = queuedPrompt;
          scope.effect(() => () => {
            disposed = true; unsubscribe(); listeners.clear(); modelChoices.delete(id);
            if (queuedPrompt && face.prompt === queuedPrompt) face.prompt = prompt;
            if (beginEcho && face.beginSubmission === beginEcho) face.beginSubmission = beginSubmission;
          }, 'geneloop: model selection queue');
          modelChoices.set(id, value); return value;
        }
        // One public model seat, the native directory and the same serialized
        // selection queue. Range steps come from the selected model's metadata.
        function ReasoningModelSelect({ locked, available, directory, load, select }) {
          const state = React.useSyncExternalStore(directory.subscribe, directory.getSnapshot);
          const [open, setOpen] = React.useState(false), [position, setPosition] = React.useState(null);
          const trigger = React.useRef(null), panel = React.useRef(null), root = React.useRef(null), placedFocus = React.useRef(false);
          const slider = React.useRef(null), previewLabel = React.useRef(null), previewHint = React.useRef(null);
          const dragging = React.useRef(false);
          const id = React.useId();
          const choices = state.groups.flatMap(group => group.models.map(model => ({ provider: group.id, model })));
          const chosen = choices.find(row => row.provider === state.current?.provider && row.model.id === state.current?.model);
          const levels = chosen?.model.reasoning?.efforts || [];
          const effort = state.current?.reasoningEffort ?? chosen?.model.reasoning?.defaultEffort;
          const index = levels.findIndex(row => row.id === effort);
          const labels = { off: '关闭', low: '低', high: '高', max: '最高' };
          const levelName = row => labels[row?.id] || row?.name || row?.id || '';
          const currentName = index < 0 ? '' : levelName(levels[index]);
          const disabled = locked || !available || state.status === 'selecting';
          const close = (restore = false) => { setOpen(false); if (restore) trigger.current?.focus(); };
          const within = target => target && (root.current?.contains(target) || panel.current?.contains(target));
          const chooseEffort = row => {
            const current = directory.getSnapshot().current;
            if (!row || !current || disabled || current.reasoningEffort === row.id) return;
            // Read the current optimistic choice, including changes made in the
            // same input event batch, instead of submitting a stale render.
            select({ ...current, reasoningEffort: row.id });
          };
          // Keep continuous pointer feedback local to the range. Neither React
          // renders nor backend writes belong on every pointer movement.
          const paintEffort = (input, raw) => {
            const value = Math.max(0, Math.min(levels.length - 1, Number(raw) || 0));
            const fraction = levels.length < 2 ? 0 : value / (levels.length - 1);
            const row = levels[Math.round(value)];
            input.value = String(value);
            input.style.setProperty('--geneloop-effort-progress', fraction * 100 + '%');
            input.style.setProperty('--geneloop-effort-color', 'hsl(' + (214 + fraction * 58) + ' 82% 68%)');
            input.setAttribute('aria-valuetext', levelName(row));
            if (previewLabel.current) previewLabel.current.textContent = levelName(row);
            if (previewHint.current) previewHint.current.textContent = row?.description || '拖动滑杆调整，或点击档位；也可用方向键。';
          };
          const commitEffort = input => {
            dragging.current = false;
            const next = Math.max(0, Math.min(levels.length - 1, Math.round(Number(input.value))));
            paintEffort(input, next); chooseEffort(levels[next]);
          };
          const cancelDrag = input => {
            if (!dragging.current) return;
            dragging.current = false;
            paintEffort(input, Math.max(0, levels.findIndex(row => row.id === directory.getSnapshot().current?.reasoningEffort)));
          };
          React.useLayoutEffect(() => {
            if (slider.current && !dragging.current) paintEffort(slider.current, Math.max(index, 0));
          }, [open, index, chosen?.model, disabled]);
          React.useEffect(() => {
            if (!open) return;
            const outside = event => { if (!within(event.target)) close(); };
            document.addEventListener('pointerdown', outside);
            return () => document.removeEventListener('pointerdown', outside);
          }, [open]);
          React.useLayoutEffect(() => {
            if (!open) { setPosition(null); return; }
            const place = () => {
              const box = trigger.current?.getBoundingClientRect(), menu = panel.current;
              if (!box || !menu) return;
              const margin = 12;
              setPosition({ left: Math.max(margin, Math.min(box.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - margin)),
                top: Math.max(margin, Math.min(box.top - menu.offsetHeight - 8, window.innerHeight - menu.offsetHeight - margin)) });
            };
            place();
            window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
            return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
          }, [open, chosen?.model, state.error]);
          React.useEffect(() => {
            if (!open) { placedFocus.current = false; return; }
            if (!position || placedFocus.current) return;
            const target = panel.current?.querySelector('input[type="range"]:not(:disabled),button[aria-pressed="true"]:not(:disabled),button:not(:disabled)');
            if (target) { target.focus(); placedFocus.current = true; }
          }, [open, Boolean(position), choices.length, levels.length, state.error, disabled]);
          if (!available) return null;
          const toggle = () => { if (disabled) return; setOpen(!open); if (!open) load(); };
          const keyDown = event => {
            if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(true); }
          };
          const blur = event => { if (!event.relatedTarget || !within(event.relatedTarget)) close(); };
          const panelNode = open && h('div', { id, ref: panel, role: 'dialog', 'aria-label': '模型与思考强度',
            className: 'geneloop-model-panel', style: position || { visibility: 'hidden', left: 0, top: 0 }, onKeyDown: keyDown, onBlur: blur },
            h('div', { className: 'geneloop-model-heading' }, '模型'),
            h('div', { className: 'geneloop-model-choices', role: 'group', 'aria-label': '选择模型' }, ...choices.map(row => {
              const active = row === chosen;
              return h('button', { key: row.provider + '/' + row.model.id, type: 'button', 'aria-pressed': active,
                className: 'geneloop-model-choice', disabled, onClick: () => {
                  if (active) return;
                  const defaultEffort = row.model.reasoning?.defaultEffort;
                  select({ provider: row.provider, model: row.model.id, ...(defaultEffort === undefined ? {} : { reasoningEffort: defaultEffort }) });
                } }, h('span', null, row.model.name || row.model.id), active && h('span', { 'aria-hidden': true }, '✓'));
            })),
            levels.length > 0 && h('section', { className: 'geneloop-reasoning' },
              h('div', { className: 'geneloop-reasoning-heading' }, h('span', { id: id + '-label' }, '思考强度'),
                h('strong', { ref: previewLabel, 'aria-live': 'polite', 'aria-atomic': true }, currentName)),
              index >= 0 ? h('input', { ref: slider, type: 'range', min: 0, max: levels.length - 1, step: 'any', defaultValue: index,
                disabled: disabled || levels.length < 2, 'aria-labelledby': id + '-label', 'aria-valuetext': currentName, 'aria-describedby': id + '-hint',
                onPointerDown: event => { if (!disabled) { dragging.current = true; event.currentTarget.setPointerCapture(event.pointerId); } },
                onInput: event => paintEffort(event.currentTarget, event.currentTarget.value),
                onChange: event => { if (!dragging.current) commitEffort(event.currentTarget); },
                onPointerUp: event => { if (dragging.current) commitEffort(event.currentTarget); },
                onPointerCancel: event => cancelDrag(event.currentTarget),
                onLostPointerCapture: event => cancelDrag(event.currentTarget),
                onBlur: event => cancelDrag(event.currentTarget),
                onPointerMove: event => {
                  const input = event.currentTarget, box = input.getBoundingClientRect();
                  const fraction = levels.length < 2 ? 0 : Number(input.value) / (levels.length - 1);
                  input.dataset.thumbNear = String(dragging.current || Math.abs(event.clientX - (box.left + 9 + fraction * (box.width - 18))) < 24);
                },
                onPointerLeave: event => { event.currentTarget.dataset.thumbNear = 'false'; },
                onKeyDown: event => {
                  const delta = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[event.key];
                  if (delta === undefined && event.key !== 'Home' && event.key !== 'End') return;
                  event.preventDefault();
                  const next = event.key === 'Home' ? 0 : event.key === 'End' ? levels.length - 1 : Math.round(Number(event.currentTarget.value)) + delta;
                  paintEffort(event.currentTarget, next); commitEffort(event.currentTarget);
                } })
                : h('p', { role: 'status', className: 'geneloop-model-status' }, '当前思考档位不在可用目录中，请重新选择。'),
              h('div', { className: 'geneloop-reasoning-stops' },
                ...levels.map((row, i) => {
                  const fraction = levels.length < 2 ? .5 : i / (levels.length - 1);
                  return h('button', { key: row.id, type: 'button', disabled, 'aria-pressed': row.id === effort, title: row.description,
                    style: { left: 'calc(' + fraction * 100 + '% + ' + (8 - fraction * 16) + 'px)' },
                    'aria-label': '思考强度：' + levelName(row), onClick: () => chooseEffort(row) }, levelName(row));
                })),
              h('p', { ref: previewHint, id: id + '-hint', className: 'geneloop-model-hint' }, levels[index]?.description || '拖动滑杆调整，或点击档位；也可用方向键。')),
            state.status === 'loading' && h('div', { className: 'geneloop-model-status', role: 'status' }, '正在读取模型…'),
            state.error && h('div', { className: 'geneloop-model-error', role: 'alert' }, state.error,
              h('button', { type: 'button', onClick: () => load() }, '重新读取')));
          return h('div', { ref: root, className: 'geneloop-model-select', onKeyDown: keyDown, onBlur: blur },
            h('style', null, `.geneloop-model-select{min-width:0}
.geneloop-model-trigger{display:flex;align-items:center;gap:5px;max-width:min(360px,45cqw);height:28px;padding:0 8px;border:0;border-radius:24px;background:transparent;color:var(--dsw-alias-label-secondary);font:inherit;font-size:13px;cursor:pointer}
.geneloop-model-trigger:hover,.geneloop-model-trigger[aria-expanded=true]{background:var(--dsw-alias-interactive-bg-hover)}
.geneloop-model-chevron{width:14px;height:14px;flex:none;color:var(--dsw-alias-label-tertiary);transition:transform 160ms ease}
.geneloop-model-trigger[aria-expanded=true] .geneloop-model-chevron{transform:rotate(180deg)}
.geneloop-model-trigger>span:first-child{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.geneloop-model-effort{white-space:nowrap;color:var(--dsw-alias-label-tertiary)}
.geneloop-model-trigger:disabled{cursor:default;opacity:.5}
.geneloop-model-panel{position:fixed;z-index:1100;box-sizing:border-box;width:320px;max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);overflow:auto;padding:16px;border:1px solid var(--dsw-alias-border-l1,#8883);border-radius:18px;background:var(--dsw-specific-menu,#262626);color:var(--dsw-alias-label-primary);box-shadow:var(--dsw-elevation-prominent,0 8px 32px #0003);font-family:var(--dsw-font-family,inherit);font-size:13px;line-height:1.5}
.geneloop-model-heading{margin:0 0 6px;color:var(--dsw-alias-label-tertiary);font-size:12px}
.geneloop-model-choices{display:grid;gap:4px}
.geneloop-model-choice{display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;min-height:38px;padding:8px 10px;border:0;border-radius:9px;background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer}
.geneloop-model-choice[aria-pressed=true],.geneloop-model-choice:hover{background:var(--dsw-alias-interactive-bg-hover,#8882)}
.geneloop-reasoning{margin-top:14px;padding-top:14px;border-top:1px solid var(--dsw-alias-border-l1,#8883)}
.geneloop-reasoning-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px}
.geneloop-reasoning-heading strong{font-size:12px;font-weight:500;color:var(--dsw-alias-state-business-primary,#729cf7)}
.geneloop-reasoning input[type=range]{display:block;box-sizing:border-box;width:100%;height:32px;margin:0;appearance:none;-webkit-appearance:none;background:transparent;cursor:ew-resize;touch-action:pan-y}
.geneloop-reasoning input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:6px;background:linear-gradient(to right,#6aabf5,var(--geneloop-effort-color,#6aabf5)) 0/var(--geneloop-effort-progress,0%) 100% no-repeat,var(--dsw-alias-border-l3,#8885)}
.geneloop-reasoning input[type=range]::-moz-range-track{height:6px;border-radius:6px;background:var(--dsw-alias-border-l3,#8885)}
.geneloop-reasoning input[type=range]::-moz-range-progress{height:6px;border-radius:6px;background:linear-gradient(to right,#6aabf5,var(--geneloop-effort-color,#6aabf5))}
.geneloop-reasoning input[type=range]::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;box-sizing:border-box;width:18px;height:18px;margin-top:-6px;border:2px solid var(--geneloop-effort-color,#6aabf5);border-radius:50%;background:var(--dsw-specific-menu,#262626);box-shadow:0 1px 4px #0002;transition:transform 140ms ease}
.geneloop-reasoning input[type=range]::-moz-range-thumb{box-sizing:border-box;width:18px;height:18px;border:2px solid var(--geneloop-effort-color,#6aabf5);border-radius:50%;background:var(--dsw-specific-menu,#262626);transition:transform 140ms ease}
.geneloop-reasoning input[type=range][data-thumb-near=true]::-webkit-slider-thumb,.geneloop-reasoning input[type=range]:active::-webkit-slider-thumb{transform:scale(1.18)}
.geneloop-reasoning input[type=range][data-thumb-near=true]::-moz-range-thumb,.geneloop-reasoning input[type=range]:active::-moz-range-thumb{transform:scale(1.18)}
.geneloop-reasoning-stops{position:relative;height:32px}
.geneloop-reasoning-stops button{position:absolute;transform:translateX(-50%);min-width:32px;min-height:32px;padding:4px;border:0;border-radius:8px;background:transparent;color:var(--dsw-alias-label-tertiary);font:inherit;font-size:12px;cursor:pointer}
.geneloop-reasoning-stops button:hover{background:var(--dsw-alias-interactive-bg-hover,#8882)}
.geneloop-reasoning-stops button[aria-pressed=true]{color:var(--dsw-alias-state-business-primary,#729cf7);font-weight:600}
.geneloop-model-hint{margin:6px 0 0;color:var(--dsw-alias-label-tertiary);font-size:12px;line-height:1.6}
.geneloop-model-status{margin-top:6px;color:var(--dsw-alias-label-tertiary);font-size:12px}
.geneloop-model-error{margin-top:8px;color:var(--dsw-alias-state-error-primary,#d66);font-size:12px;overflow-wrap:anywhere}
.geneloop-model-error button{border:0;background:transparent;color:inherit;text-decoration:underline;cursor:pointer;font:inherit}
.geneloop-model-trigger:focus-visible,.geneloop-model-panel button:focus-visible,.geneloop-reasoning input:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}
.geneloop-model-panel button:disabled,.geneloop-reasoning input:disabled{cursor:default;opacity:.5}
@media(prefers-reduced-motion:reduce){.geneloop-model-chevron{transition:none}.geneloop-reasoning input[type=range]::-webkit-slider-thumb{transition:none}.geneloop-reasoning input[type=range]::-moz-range-thumb{transition:none}}
@media(forced-colors:active){.geneloop-reasoning input[type=range]{appearance:auto;-webkit-appearance:auto}
.geneloop-model-choice[aria-pressed=true],.geneloop-reasoning-stops button[aria-pressed=true]{outline:1px solid Highlight}
}
`),
            h('button', { ref: trigger, type: 'button', className: 'geneloop-model-trigger', disabled,
              'aria-haspopup': 'dialog', 'aria-expanded': open, 'aria-controls': id,
              'aria-label': '选择模型，当前 ' + (chosen?.model.name || state.current?.model || '未选择') + (currentName ? '，思考强度' + currentName : ''),
              onClick: toggle, onKeyDown: event => { if (event.key === 'ArrowDown' && !open) { event.preventDefault(); toggle(); } } },
              h('span', null, chosen?.model.name || state.current?.model || '选择模型'),
              currentName && h('span', { className: 'geneloop-model-effort' }, currentName),
              h('svg', { className: 'geneloop-model-chevron', viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': true },
                h('path', { d: 'm4.5 6.25 3.5 3.5 3.5-3.5', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' }))),
            panelNode && ReactDOM.createPortal(panelNode, document.body));
        }
        function wrapWebSeat(name, adapt, options = {}) {
          ctx.slots.inject(name, () => {
            let release, mirrors = [], installing = false;
            const install = () => {
              if (release || installing) return;
              const original = ctx.slots.entries(name).find(entry => (entry.options.priority ?? 0) >= 0 && (!options.id || entry.options.id === options.id));
              if (!original) return;
              installing = true;
              try {
                const names = Object.fromEntries(Object.keys(original.children || {}).map(child => [child, 'geneloop.web.' + child]));
                const children = Object.fromEntries(Object.entries(original.children || {}).map(([child, spec]) => [names[child], spec]));
                release = ctx.slots.register({ name, ...original.options, priority: -100, locale: original.locale,
                  ...(original.store ? { store: original.store } : {}), ...(original.select ? { select: original.select } : {}),
                  children, inject: (...args) => adapt(original.inject?.(...args) || {}, args[0]) }, props => h(options.component || original.component, {
                  ...props, ...(options.renderProps?.(props) || {}), renderSlot: (child, owner, options) => props.renderSlot(names[child] || child, owner, options),
                  ...(props.renderSlotChain ? { renderSlotChain: (child, owner, options) => props.renderSlotChain(names[child] || child, owner, options) } : {}),
                }));
                mirrors = Object.keys(names).map(child => mirrorPublicSlot(child, names[child]));
              } finally { installing = false; }
            };
            install(); const unsubscribe = ctx.slots.subscribe(name, install);
            return () => { unsubscribe(); mirrors.reverse().forEach(stop => stop()); release?.(); };
          });
        }
        wrapWebSeat('conversation.composer.bar', (props, id) => {
          if (id) webMenu(id);
          if (id && props.addFiles) uploads.set(id, props.addFiles);
          const launcher = props.hooks?.menuLauncher;
          return { ...props, command: undefined,
            ...(launcher ? { hooks: { ...props.hooks, menuLauncher: {
              subscribe: listener => launcher.subscribe(listener),
              getSnapshot: () => launcher.getSnapshot() === 'harless-scenes' ? 'command' : launcher.getSnapshot(),
            } } } : {}), toggleCommandMenu: id ? () => {
            props.keyboard.dismissPopup();
            const draft = props.keyboard.snapshot;
            const prefix = /^(\s*)\/[a-z0-9_-]*/i.exec(draft.draft);
            triggers.sessionOf(sessions.scope(id)).toggleSource('harless-scenes', { trigger: '/', query: '', quoted: false,
              position: 'leading', span: { start: prefix ? prefix[1].length : 0,
                end: prefix ? prefix[0].length : 0, draftRev: draft.draftRev } });
          } : props.toggleCommandMenu };
        });
        wrapWebSeat('conversation.input.model', (props, id) => optimisticModel(id, props), { component: ReasoningModelSelect });
        wrapWebSeat('conversation.view', props => props, { id: 'chat',
          renderProps: props => {
            // Paired results own one footer per live lane after hydration.
            // Native Chat still covers local sends and single-lane execution.
            React.useSyncExternalStore(comparisonActivity.subscribe, comparisonActivity.getSnapshot);
            const chat = props.useChat?.(value => value);
            const latest = chat?.timeline?.turnOrder.at(-1);
            const child = (chat?.order || []).map(key => {
              const node = chat.nodes.get(key);
              return node?.kind === 'harless-comparison' && node.location?.turn?.turn === latest ? node : undefined;
            }).find(Boolean);
            const cached = child && comparisonSnapshots.get(child.data.session_id + ':' + child.data.id);
            const value = cached || child?.data;
            const childRunning = value && !['completed', 'failed', 'cancelled'].includes(value.status);
            const laneFooters = value && value.presentation !== 'single' &&
              (cached || ['completed', 'failed', 'cancelled'].includes(value.status));
            return { t: (key, ...args) => key === 'chat.deepDiving' ? h('span', { className: 'geneloop-native-looping' }, 'GeneLooping…') : props.t(key, ...args),
            // The native submission echo exists synchronously on Send, before
            // model selection/network dispatch. Project activity only in this
            // view; never change the session's execution/queue state.
            useSession: select => props.useSession(snapshot => select({ ...snapshot,
              running: !laneFooters && Boolean(snapshot.running || snapshot.pendingSubmissions?.some(row => row.placement !== 'queued') || childRunning) })) };
          } });
        // Only adapt display data. The native controller still owns keyboard
        // navigation, focus, outside-click dismissal and atomic reference picks.
        const menuFaces = new WeakMap();
        function menuIcon(item) {
          const key = item.value, color = key === 'ppt' ? '#c28b42' : key === 'research-data-analysis' ? '#42a99b' : key === 'paper-proofreading' ? '#729cf7' : 'currentColor';
          const paths = key === 'ppt' ? ['M3 4h18v12H3zM12 16v5M8 21l4-5 4 5M7 8h10M7 12h6']
            : key === 'research-data-analysis' ? ['M4 3v17h17M8 16v-5M13 16V7M18 16V4']
            : key === 'paper-proofreading' ? ['M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6']
            : ['M8 13l7-7a3 3 0 0 1 4 4l-9 9a5 5 0 0 1-7-7l9-9a7 7 0 0 1 10 10l-8 8'];
          return h('svg', { width: 19, height: 19, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: 1.6,
            strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }, ...paths.map(d => h('path', { key: d, d })));
        }
        wrapWebSeat('conversation.input.overlay', props => {
          if (!props.menu) return props;
          if (!menuFaces.has(props.menu)) {
            let before, snapshot;
            menuFaces.set(props.menu, { subscribe: fn => props.menu.subscribe(fn), getSnapshot: () => {
              const next = props.menu.getSnapshot();
              if (next !== before) { before = next; snapshot = { ...next, groups: next.groups.map(group => group.source !== 'harless-scenes' ? group : {
                ...group, items: group.items.map(item => ({ ...item, icon: undefined,
                  name: h('span', { className: 'geneloop-menu-name', style: { display: 'inline-flex', alignItems: 'center', gap: 10 } }, menuIcon(item), item.name) })) }) }; }
              return snapshot;
            } });
          }
          return { ...props, menu: menuFaces.get(props.menu) };
        }, { id: 'slash-menu' });
      }
      // The pinned native tab roster enumerates shadowed entries as well as
      // winners. Adapt only the header's public source to one tab per id; keep
      // the native header, store, title management and scoped child actions.
      ctx.slots.inject('conversation.session.header.lineage', () => {
        const original = ctx.slots.entries?.('conversation.session.header')[0];
        if (!original) return () => {};
        const names = Object.fromEntries(Object.keys(original.children || {}).map(name => [name, 'harless.' + name]));
        const children = Object.fromEntries(Object.entries(original.children || {}).map(([name, spec]) => [names[name], spec]));
        const stop = ctx.slots.register({ name: 'conversation.session.header', priority: -100, locale: original.locale,
          ...(original.store ? { store: original.store } : {}), children,
          inject: (...args) => {
            const face = original.inject(...args), source = face.hooks.conversationViews;
            let previous, cached;
            return { ...face, hooks: { ...face.hooks, conversationViews: {
              subscribe: listener => source.subscribe(listener),
              getSnapshot: () => {
                const rows = source.getSnapshot();
                if (rows !== previous) {
                  previous = rows; const ids = new Set();
                  const orders = new Map(ctx.slots.entries('conversation.view').map(entry => [entry.options.id, entry.options.order || 0]));
                  cached = rows.filter(row => !ids.has(row.id) && ids.add(row.id)).sort((a, b) => (orders.get(a.id) || 0) - (orders.get(b.id) || 0));
                }
                return cached;
              },
            } } };
          },
        }, props => h(original.component, { ...props, renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options) }));
        const mirrors = Object.entries(names).map(([name, alias]) => mirrorPublicSlot(name, alias));
        return () => { mirrors.reverse().forEach(dispose => dispose()); stop(); };
      });
      const unifiedTraceStyle = `
.geneloop-unified-trace{display:flex;flex-direction:column;height:100%;min-height:0;min-width:0;overflow:hidden;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-base,transparent);font-family:var(--dsw-font-family,ui-sans-serif,system-ui,sans-serif);font-size:13px;line-height:1.55}
.geneloop-unified-trace *{box-sizing:border-box}.geneloop-unified-trace button,.geneloop-unified-trace input{font:inherit;color:inherit;background:transparent;border:1px solid transparent;border-radius:6px;padding:4px 8px}.geneloop-unified-trace button{cursor:pointer}.geneloop-unified-trace button:hover{background:var(--dsw-alias-interactive-bg-hover,#8882)}.geneloop-unified-trace button:focus-visible,.geneloop-unified-trace input:focus-visible,.geneloop-unified-trace summary:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}
.geneloop-trace-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:10px 16px;border-bottom:1px solid #8883;flex:none}.geneloop-trace-toolbar>div{display:flex;gap:4px}.geneloop-trace-toolbar button[aria-pressed=true]{background:var(--dsw-alias-interactive-bg-hover,#8882)}.geneloop-trace-count{color:var(--dsw-alias-label-secondary);font-size:12px}.geneloop-trace-toolbar input{margin-left:auto;border-color:#8883;max-width:220px;min-width:100px}.geneloop-trace-history-error{padding:10px 16px;color:var(--dsw-alias-state-error-primary,#e79b85)}
.geneloop-trace-overview{display:flex;flex:none;max-height:180px;overflow:auto;border-bottom:1px solid #8883;padding:8px 12px 6px;background:var(--dsw-alias-interactive-bg-hover,#8881)}.geneloop-trace-axis{display:flex;flex-direction:column;gap:0;min-width:36px;padding-top:58px;color:var(--dsw-alias-label-secondary);font-size:11px}.geneloop-trace-axis span{height:16px;line-height:16px}.geneloop-trace-chart{display:flex;min-width:0;flex:1;gap:4px}.geneloop-trace-chart-turn{min-width:148px;flex-basis:0;border-left:1px solid #8883;padding:0 5px}.geneloop-trace-jump{display:block!important;font-weight:500!important;white-space:nowrap}.geneloop-trace-lanes{display:flex;gap:2px;height:29px;align-items:center}.geneloop-trace-lanes button{font-size:11px;padding:2px 5px;border-color:#8883;color:var(--dsw-alias-label-secondary)}.geneloop-trace-lanes button[aria-pressed=true]{color:var(--dsw-alias-label-primary);background:#8882;border-color:#8887}.geneloop-trace-lanes button[data-lane=motif][aria-pressed=true]{color:#48c5a1;border-color:#48c5a177;background:#48c5a112}.geneloop-trace-chart-turn:not(:has(.geneloop-trace-lanes)) .geneloop-trace-jump{margin-bottom:29px}.geneloop-trace-plot{height:50px;position:relative;background:repeating-linear-gradient(transparent 0 15px,#8881 15px 16px)}.geneloop-unified-trace .geneloop-trace-mark{position:absolute;border:0;border-radius:2px;padding:0;width:6px;height:7px;min-width:0;background:#ac91c8}.geneloop-unified-trace .geneloop-trace-mark[data-kind="0"]{background:#729cf7}.geneloop-unified-trace .geneloop-trace-mark[data-kind="2"]{background:#d5a55b}.geneloop-unified-trace .geneloop-trace-mark[data-optimized=true]{background:#48c5a1;box-shadow:0 0 0 1px #48c5a177}.geneloop-trace-chart-turn>small{font-size:10px;color:var(--dsw-alias-label-secondary)}
.geneloop-trace-rounds{overflow:auto;min-height:0;flex:1;padding:8px 20px calc(var(--dsh-composer-height,152px) + 24px)}.geneloop-trace-round{padding:16px 0 24px;border-bottom:1px solid #8883;scroll-margin-top:8px}.geneloop-trace-round>header{display:flex;align-items:center;gap:10px;margin-bottom:14px}.geneloop-trace-round>header strong{font-weight:600;font-size:13px}.geneloop-trace-round>header>span{color:var(--dsw-alias-label-secondary);font-size:12px}.geneloop-trace-user{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;margin:0 0 12px}.geneloop-trace-user>span{color:#87a9f3;background:#729cf718;border-radius:4px;padding:1px 6px;font-size:12px}.geneloop-trace-user>p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;flex:1;min-width:0}.geneloop-trace-user>div{flex-basis:100%}.geneloop-trace-system{color:var(--dsw-alias-label-secondary);padding:10px 0;border-bottom:1px solid #8883}.geneloop-trace-system summary{cursor:pointer}.geneloop-trace-system pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
.harless-trace-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.harless-trace-columns[data-single=true]{grid-template-columns:1fr}.harless-trace-column{min-width:0}.harless-trace-column>header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 0;border-bottom:1px solid #8883}.harless-trace-column>header>strong{font-size:13px;font-weight:600}.harless-trace-column[data-lane=motif]>header>strong{color:#48c5a1}.harless-live-status{font-size:12px;color:var(--dsw-alias-label-secondary);margin:0 0 0 auto}.harless-trace-list{list-style:none;padding:0;margin:12px 0}.harless-trace-list>li{position:relative;border-left:2px solid #8883;padding:0 0 18px 14px;margin-left:4px;overflow-wrap:anywhere}.harless-trace-event{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.harless-trace-event strong{font-size:13px;font-weight:500}.harless-trace-event small,.harless-trace-event time,.harless-trace-tool{font-size:11px;color:var(--dsw-alias-label-secondary)}.harless-trace-event time{margin-left:auto;white-space:nowrap}.harless-trace-dot{position:absolute;left:-5px;top:7px;width:8px;height:8px;border-radius:50%;background:#ac91c8}.harless-trace-list>li[data-kind=tool] .harless-trace-dot{background:#d5a55b}.harless-trace-list>li[data-optimized=true]{border-color:#48c5a177}.harless-trace-list>li[data-optimized=true] .harless-trace-dot{background:#48c5a1}.harless-trace-optimization{display:inline-block;font-size:11px;color:#48c5a1;background:#36a38316;border:1px solid #36a38366;border-radius:5px;padding:2px 6px;margin-top:6px}.harless-trace-tool{display:block;margin:4px 0}.harless-trace-list details{margin-top:5px}.harless-trace-list summary{cursor:pointer;color:var(--dsw-alias-label-secondary)}.harless-trace-list pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.65;padding:10px;border:1px solid #8883;border-radius:6px}.harless-trace-preview{margin:5px 0;color:var(--dsw-alias-label-secondary);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-wrap}.harless-paired-muted{color:var(--dsw-alias-label-secondary);font-size:12px}
@media(max-width:650px){.geneloop-trace-toolbar{padding:8px;gap:8px}.geneloop-trace-toolbar input{width:130px}.geneloop-trace-rounds{padding:8px 12px calc(var(--dsh-composer-height,152px) + 24px)}.harless-trace-columns{grid-template-columns:1fr;gap:16px}.geneloop-trace-overview{padding-left:8px}.harless-trace-event time{margin-left:0}}
`;

      // Unified trajectory uses public snapshots and source sequence anchors.
      // A user message starts a displayed round, including legacy task messages
      // whose native turn location stayed on the preceding ordinary turn.
      const traceTime = value => typeof value === 'number' ? value : Date.parse(value);
      const traceText = node => (node.kind === 'user' ? displayUserContent(node.blocks || node.content || []) : (node.blocks || node.content || [])).map(part =>
        part.text || (part.type === 'file' ? '文件：' + (part.attachment?.name || part.attachment?.filename || '附件') : '')).filter(Boolean).join('\n') || node.message || node.text || '';
      function nativeTraceRows(nodes) {
        const rows = [];
        const append = node => {
          const kind = node.kind === 'tool-result' ? 'tool' : node.kind === 'assistant' ? 'assistant' : node.kind;
          const tools = (node.blocks || []).filter(block => block.kind === 'tool-call');
          const reasoning = (node.blocks || []).filter(part => part.kind === 'reasoning').map(part => part.text).filter(Boolean).join('\n');
          if (reasoning) rows.push({ id: 'thinking-' + node.seq, kind: 'thinking', label: '思考', text: reasoning,
            time: node.time, status: node.streaming ? 'running' : 'completed' });
          const text = traceText(node.kind === 'assistant' ? { ...node, blocks: (node.blocks || []).filter(part => part.kind !== 'reasoning') } : node);
          if (text || (node.blocks || []).some(part => part.kind === 'image') || node.kind !== 'assistant') rows.push({ id: 'native-' + node.seq, kind,
            label: ({ assistant: '回复', context: '上下文', steering: '补充消息', 'tool-result': '工具调用',
              'turn-error': '执行失败', 'model-retry': '重试', 'turn-max-tokens': '输出已停止', command: '指令', 'compaction-summary': '历史摘要' })[node.kind] || '执行记录',
            status: node.isError || node.kind === 'turn-error' ? 'failed' : node.interrupted ? 'interrupted' : node.streaming ? 'running' : 'completed',
            time: node.time, text, tool: node.call?.name, args: node.call?.argsRaw,
            images: (node.blocks || node.content || []).filter(part => (part.kind || part.type) === 'image').map(part => part.attachment).filter(Boolean),
            optimized: false, verified_skip: false });
          for (const tool of tools) if (!nodes.some(row => row.callId === tool.callId)) rows.push({ id: 'call-' + tool.callId,
            kind: 'tool', label: '工具调用', tool: tool.name, args: tool.argsRaw, time: node.time, status: node.interrupted ? 'interrupted' : 'running' });
          for (const child of node.subCalls || []) append({ ...child, seq: child.callId,
            kind: child.kind || 'tool-result', call: child.call || { name: child.name, argsRaw: child.argsRaw } });
        };
        nodes.filter(node => node.kind !== 'user').forEach(append);
        return rows;
      }
      function trajectoryRounds(chat, inspection) {
        const nodes = [...(inspection.eventNodes || [])].sort((a, b) => a.seq - b.seq);
        const comparisons = (chat.order || []).map(key => chat.nodes.get(key)).filter(row => row?.kind === 'harless-comparison' && row.visibility !== 'hidden');
        const anchors = new Map(nodes.filter(node => node.kind === 'user').map(node => [node.seq, { seq: node.seq, user: node }]));
        for (const comparison of comparisons) {
          const seq = comparison.anchorSeq;
          if (!Number.isFinite(seq)) continue;
          anchors.set(seq, { ...anchors.get(seq), seq, comparison });
        }
        const turns = [...anchors.values()].sort((a, b) => a.seq - b.seq).map((turn, i, all) => {
          const end = all[i + 1]?.seq ?? Infinity;
          const records = nodes.filter(node => node.seq >= turn.seq && node.seq < end);
          return { ...turn, number: i + 1, key: 'round-' + turn.seq, records,
            rows: nativeTraceRows(records) };
        });
        const last = turns.at(-1);
        if (last && inspection.partial?.blocks?.length) last.rows.push(...nativeTraceRows([{ kind: 'assistant', seq: 'partial', streaming: true, blocks: inspection.partial.blocks }]));
        if (last) for (const call of inspection.runningCalls || []) if (!last.rows.some(row => row.id === 'call-' + call.callId))
          last.rows.push({ id: 'call-' + call.callId, kind: 'tool', label: '工具调用', tool: call.name, args: call.argsRaw, time: call.time, status: 'running' });
        return turns;
      }
      const isPairedTrace = value => value?.presentation !== 'single' && !!value?.lanes?.baseline && !!value?.lanes?.motif;
      const traceChartRows = (turn, lane) => {
        const result = turn.value?.lanes?.[lane];
        const rows = result ? result.trace || [] : turn.rows;
        return [{ id: 'input', kind: 'user', label: '输入', time: turn.user?.time || turn.value?.created_at }, ...rows].map(row => ({ ...row,
          chartLane: ['user', 'context', 'steering'].includes(row.kind) ? 0 : ['tool', 'motif'].includes(row.kind) ? 2 : 1,
          timestamp: traceTime(row.time) }));
      };
      ctx.slots.inject('conversation.trajectory.images', () => {
        const original = ctx.slots.entries?.('conversation.view').find(entry => entry.options.id === 'trajectory');
        if (!original) return () => {};
        const imageSlot = 'harless.trajectory.images';
        function ProductTrajectory(owner) {
          const chat = owner.useChat(snapshot => snapshot), inspection = owner.useTrajectory(snapshot => snapshot);
          const session = owner.useSession(snapshot => snapshot);
          const [lanes, setLanes] = React.useState({}), [query, setQuery] = React.useState(''), [scale, setScale] = React.useState('turn');
          const [historyError, setHistoryError] = React.useState(''), [retry, setRetry] = React.useState(0), [revision, refresh] = React.useState(0);
          const rootRef = React.useRef(null), historyBusy = React.useRef(null), historyScope = React.useRef(null);
          const comparisons = (chat.order || []).map(key => chat.nodes.get(key)).filter(row => row?.kind === 'harless-comparison' && row.visibility !== 'hidden');
          const identities = comparisons.map(row => comparisonKey(row.data)).join('|');
          React.useEffect(() => {
            const scope = {}; historyScope.current = scope; historyBusy.current = null;
            setLanes({}); setQuery(''); setHistoryError('');
            return () => { if (historyScope.current === scope) historyScope.current = null; };
          }, [owner.sessionId]);
          React.useEffect(() => {
            const disposers = comparisons.map(row => {
              const key = comparisonKey(row.data), listener = () => refresh(value => value + 1);
              const group = comparisonObservers.get(key) || new Set(); group.add(listener); comparisonObservers.set(key, group);
              return () => { group.delete(listener); if (!group.size) comparisonObservers.delete(key); };
            });
            return () => disposers.forEach(stop => stop());
          }, [owner.sessionId, identities]);
          React.useEffect(() => {
            if (!session.hasMore || session.loadingOlder || historyBusy.current || historyError) return;
            const scope = historyScope.current; historyBusy.current = scope;
            Promise.resolve().then(() => owner.loadOlder()).then(changed => {
              if (historyScope.current === scope && changed === false) setHistoryError('更早记录暂未加载，请重试。');
            }, () => { if (historyScope.current === scope) setHistoryError('读取更早记录失败，请重试。'); }).finally(() => {
              if (historyBusy.current === scope) historyBusy.current = null;
              if (historyScope.current === scope) refresh(value => value + 1);
            });
          }, [owner.sessionId, session.hasMore, session.loadingOlder, inspection.eventNodes?.[0]?.seq, historyError, retry, revision]);
          const turns = trajectoryRounds(chat, inspection).map(turn => ({ ...turn,
            value: turn.comparison ? rememberedSnapshot(turn.comparison.data) : undefined }));
          const selectedLane = turn => isPairedTrace(turn.value) ? lanes[turn.key] || 'baseline' : 'baseline';
          const go = key => rootRef.current?.querySelector('[data-round-key="' + key + '"]')?.scrollIntoView({ block: 'start', behavior: 'auto' });
          const lanePicker = turn => isPairedTrace(turn.value) && h('div', { className: 'geneloop-trace-lanes', role: 'group', 'aria-label': '第 ' + turn.number + ' 轮图示轨迹' },
            ...['baseline', 'motif'].map(lane => h('button', { type: 'button', key: lane, 'data-lane': lane,
              'aria-pressed': selectedLane(turn) === lane, onClick: () => setLanes(old => ({ ...old, [turn.key]: lane })) }, lane === 'baseline' ? 'Baseline' : 'Motif')));
          const textOfTurn = turn => [traceText(turn.user || {}), ...turn.rows.map(row => [row.label, row.text, row.tool].join(' ')),
            ...Object.values(turn.value?.lanes || {}).flatMap(lane => (lane.trace || []).map(row => [row.label, row.text, row.tool].join(' ')))].join('\n').toLowerCase();
          const visible = turns.filter(turn => !query.trim() || textOfTurn(turn).includes(query.trim().toLowerCase()));
          const renderImages = images => images?.length ? owner.renderSlot(imageSlot, { images: images.map(attachment => ({ attachment })), loadImage: owner.loadImage, align: 'start', compact: true }) : null;
          return h('div', { className: 'harless-trajectory-view geneloop-unified-trace', 'data-conversation-composer-overlay': '', ref: rootRef },
            h('style', null, unifiedTraceStyle),
            h('div', { className: 'geneloop-trace-toolbar' },
              h('div', { role: 'group', 'aria-label': '轨迹排列方式' }, ...[['turn', '按轮次'], ['duration', '按时间'], ['call', '按事件']].map(([key, label]) =>
                h('button', { key, type: 'button', 'aria-pressed': scale === key, onClick: () => setScale(key) }, label))),
              h('span', { className: 'geneloop-trace-count', role: 'status' }, session.hasMore ? '正在加载全部轮次…' : '共 ' + turns.length + ' 轮'),
              h('input', { type: 'search', 'aria-label': '搜索轨迹', placeholder: '搜索轨迹', value: query, onChange: event => setQuery(event.target.value) })),
            historyError && h('div', { role: 'alert', className: 'geneloop-trace-history-error' }, historyError, h('button', { type: 'button', onClick: () => { setHistoryError(''); setRetry(value => value + 1); } }, '重试')),
            h('div', { className: 'geneloop-trace-overview', 'aria-label': '所有轮次的执行轨迹图' },
              h('div', { className: 'geneloop-trace-axis', 'aria-hidden': true }, h('span', null, '输入'), h('span', null, '模型'), h('span', null, '工具')),
              h('div', { className: 'geneloop-trace-chart' }, ...(session.hasMore ? [] : turns).map(turn => {
                const rows = traceChartRows(turn, selectedLane(turn)), times = rows.map(row => row.timestamp).filter(Number.isFinite);
                const start = Math.min(...times), span = Math.max(1, Math.max(...times) - start);
                // Time scaling uses actual event timestamps, never inferred tool durations.
                const weight = scale === 'duration' ? span : scale === 'call' ? Math.max(1, rows.length) : 1;
                return h('div', { key: turn.key, className: 'geneloop-trace-chart-turn', 'data-chart-turn': turn.number, style: { flexGrow: weight } },
                  h('button', { type: 'button', className: 'geneloop-trace-jump', onClick: () => go(turn.key) }, '第 ' + turn.number + ' 轮'),
                  lanePicker(turn),
                  h('div', { className: 'geneloop-trace-plot', 'data-shown-lane': isPairedTrace(turn.value) ? selectedLane(turn) : 'single' },
                    ...rows.map((row, index) => h('button', { key: row.id || index, type: 'button', className: 'geneloop-trace-mark',
                      'data-kind': row.chartLane, 'data-optimized': row.verified_skip === true || row.optimized === true ? 'true' : undefined,
                      'aria-label': '第 ' + turn.number + ' 轮 · ' + row.label + (row.verified_skip ? ' · 已验证优化' : ''),
                      title: row.label + (row.tool ? ' · ' + row.tool : '') + (Number.isFinite(row.timestamp) ? ' · ' + new Date(row.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) : ''),
                      style: { left: (scale === 'call' || !Number.isFinite(row.timestamp) ? (index + .5) / Math.max(1, rows.length) : (row.timestamp - start) / span) * 92 + 2 + '%', top: row.chartLane * 16 + 6 + 'px' },
                      onClick: () => go(turn.key) }))),
                  isPairedTrace(turn.value) && h('small', null, '图示：' + (selectedLane(turn) === 'baseline' ? 'Baseline' : 'Motif')));
              }))),
            h('div', { className: 'geneloop-trace-rounds' },
              session.hasMore && h('p', { role: 'status' }, historyError ? '请重试以完整显示所有轮次。' : '正在读取完整对话记录…'),
              ...(inspection.systemPrompts || []).map(prompt => h('details', { key: 'system-' + prompt.seq, className: 'geneloop-trace-system' },
                h('summary', null, prompt.update ? '系统提示词更新' : '初始系统提示词'), h('pre', null, prompt.text))),
              !turns.length && h('p', { role: 'status' }, session.openState === 'loading' ? '正在加载轨迹…' : '开始对话后，执行轨迹会显示在这里。'),
              turns.length > 0 && !visible.length && h('p', { role: 'status' }, '没有匹配的轨迹。'),
              ...(session.hasMore ? [] : visible).map(turn => h('section', { key: turn.key, className: 'geneloop-trace-round', 'data-round-key': turn.key, 'aria-label': '第 ' + turn.number + ' 轮' },
                h('header', null, h('strong', null, '第 ' + turn.number + ' 轮'), h('span', null, '/' + (aliases[turn.value?.scene] || turn.value?.scene || 'chat'))),
                h('div', { className: 'geneloop-trace-user' }, h('span', null, '用户'), h('p', null, traceText(turn.user || {}) || '查看本轮任务'),
                  renderImages((turn.user?.content || []).filter(part => part.type === 'image').map(part => part.attachment))),
                turn.comparison ? h(ComparisonNode, { key: turn.comparison.data.id, node: turn.comparison, traceOnly: true })
                  : h(TraceRows, { items: turn.rows, renderImages }),
                !turn.comparison && !turn.rows.length && h('p', { className: 'harless-paired-muted' }, '本轮尚无执行记录。')))));
        }
        const removeView = ctx.slots.register({ name: 'conversation.view', ...original.options, priority: -100,
          locale: original.locale, inject: original.inject, ...(original.store ? { store: original.store } : {}),
          children: { [imageSlot]: { kind: 'single', scope: 'session' } } }, ProductTrajectory);
        const stopImages = mirrorPublicSlot('conversation.trajectory.images', imageSlot);
        return () => { stopImages(); removeView(); };
      });
      // Keep the native event stream and safe assistant renderer. Product chat
      // groups process evidence itself: native Compact deliberately expands open
      // turns and incomplete history, which is unsuitable for this interface.
      const processKinds = new Set(['context', 'assistant-step', 'tool-call', 'model-retry']);
      const hiddenChatNode = () => null;
      const turnOf = node => node.location?.turn?.turn ?? node.data?.turn;
      const visibleBlocks = node => (node.data.blocks || []).filter(block => block.kind === 'text' || block.kind === 'image');
      const hasAnswer = node => visibleBlocks(node).some(block => block.kind === 'image' || block.text?.trim());
      const publicProcessText = text => String(text ?? '')
        .replace(/@deepseek-ai\/dsh[\w./-]*/gi, 'GeneLoop')
        .replace(/\bdsh(?:[-_][a-z0-9]+)+\b/gi, 'GeneLoop')
        .replace(/\bDSH\b/gi, 'GeneLoop');
      const contentText = content => (content || []).filter(block => block.type === 'text').map(block => publicProcessText(block.text)).join('\n');
      const toolLabel = block => {
        const name = (block.call?.name || block.name || '').split('__').pop();
        return ({ list_files: '查看文件', read_file: '读取文件', inspect_study: '检查研究资料',
          analyze_data: '分析数据', run_analysis: '分析数据', create_presentation: '生成演示文稿',
          export_report: '生成报告', web_search: '搜索资料', search: '搜索资料' })[name] || '工具调用';
      };
      const toolCount = block => 1 + (block.subCalls || []).reduce((count, child) => count + toolCount(child), 0);
      function ToolEvidence({ block }) {
        const done = block.kind === 'tool-result', text = contentText(block.content);
        return h('section', { className: 'geneloop-tool-evidence' },
          h('div', { className: 'geneloop-process-label' }, toolLabel(block), ' · ', done ? block.isError ? '未完成' : '完成' : '进行中'),
          (block.call?.argsRaw || block.argsRaw) && h('pre', null, publicProcessText(block.call?.argsRaw || block.argsRaw)),
          text && h('pre', null, text),
          ...(block.subCalls || []).map(child => h(ToolEvidence, { key: child.callId, block: child })));
      }
      function AssistantContent({ node, owner, process = false, live = false, delivery }) {
        const original = ctx.slots.entries?.('conversation.chat.node').find(entry => entry.options.key === 'assistant-step' && entry.component !== ProductChatNode);
        const sourceBlocks = process ? node.data.blocks.filter(block => ['text', 'image', 'reasoning'].includes(block.kind)) : visibleBlocks(node);
        const buffered = useBufferedBlocks(sourceBlocks, !process && live, owner.sessionId + ':' + node.key + ':' + process);
        const files = delivery?.lanes.baseline.artifacts || [];
        const blocks = delivery ? buffered.map(block => typeof block.text === 'string' ? { ...block, text: artifactMarkdown(block.text, files, delivery, 'baseline') } : block) : buffered;
        const mentions = delivery ? { resolve: raw => { const file = artifactFor(files, raw); return file ? {
          title: artifactName(file), label: '预览 ' + artifactName(file), open: () => openArtifact(delivery, 'baseline', file),
        } : undefined; } } : undefined;
        // A registered public renderer preserves authorized file mentions,
        // images, Markdown and interruption presentation without private APIs.
        if (original) return h(original.component, { ...owner, ...(mentions ? { fileMentions: () => mentions } : {}), node: { ...node, data: { ...node.data, blocks } }, turnProcess: undefined });
        return h('div', { 'data-streaming': node.data.status === 'running' }, ...blocks.map((block, i) =>
          block.kind === 'text' || block.kind === 'reasoning' ? MarkdownText
            ? h(MarkdownText, { key: i, text: block.text, streaming: node.data.status === 'running', labels: markdownLabels, fileMentions: mentions })
            : h('p', { key: i }, block.text)
            : block.kind === 'image' ? owner.renderMessageImages?.({ images: [{ attachment: block.attachment }], align: 'start' }) : null));
      }
      function ProductTurn({ owner, rows, answer, running }) {
        const [open, setOpen] = React.useState(false);
        const id = React.useId();
        const [delivery, setDelivery] = React.useState(null), [deliveryError, setDeliveryError] = React.useState('');
        const [deliveryRetry, retryDelivery] = React.useState(0);
        const session = owner.sessionId, turn = turnOf(answer || rows.at(-1));
        React.useEffect(() => {
          setDelivery(null); setDeliveryError('');
          if (running || !Number.isInteger(turn)) return;
          const abort = new AbortController();
          withDeadline(abort.signal, 30000, async signal => {
            let response;
            do {
              response = await fetch('/api/harless/deliveries?session_id=' + encodeURIComponent(session) + '&turn=' + turn,
                { credentials: 'same-origin', cache: 'no-store', signal });
              if (response.status === 404) response = await fetch('/api/harless/file-scene?session_id=' + encodeURIComponent(session) + '&turn=' + turn, {credentials:'same-origin',cache:'no-store',signal});
              if (response.status === 202) await new Promise(resolve => setTimeout(resolve, 250));
            } while (response.status === 202 && !signal.aborted);
            signal.throwIfAborted();
            if (response.status === 404) return;
            if (!response.ok) throw apiError(response.status);
            const value = await response.json();
            if (value.session_id !== session || value.turn !== turn || value.presentation !== 'single' || !value.lanes?.baseline) throw apiError(502);
            if (!signal.aborted) setDelivery(value);
          }).catch(error => { if (!abort.signal.aborted) setDeliveryError(networkMessage(error)); });
          return () => abort.abort();
        }, [session, turn, running, deliveryRetry]);
        const evidence = rows.filter(row => row !== answer);
        const reasoning = (answer?.data.blocks || []).filter(block => block.kind === 'reasoning' && block.text);
        const tools = rows.filter(row => row.kind === 'tool-call');
        const count = tools.reduce((total, row) => total + toolCount(row.data.root), 0);
        const messageCount = evidence.filter(row => row.kind === 'assistant-step' && hasAnswer(row)).length;
        const hasProcess = evidence.length > 0 || reasoning.length > 0;
        const active = tools.findLast(row => row.data.root.kind !== 'tool-result');
        const activeRoot = active?.data.root;
        const latestBlock = answer?.data.blocks?.at(-1);
        const status = activeRoot ? workLabel(activeRoot.call?.name || activeRoot.name, documentSubject(activeRoot.call?.argsRaw || activeRoot.argsRaw))
          : latestBlock?.kind === 'reasoning' && answer?.data.status === 'running' ? '正在思考' : '正在回复';
        const label = count ? `${count} 次工具调用${messageCount ? ` · ${messageCount} 条过程消息` : ''}` : '查看处理过程';
        const files = delivery?.lanes.baseline.artifacts || [];
        const captureDelivery = event => {
          const link = event.target.closest?.('a'); if (!link || !delivery) return;
          const target = link.getAttribute('href') || '';
          const file = files.find(file => target === artifactPreviewLink(delivery, 'baseline', file));
          if (file) { event.preventDefault(); event.stopPropagation(); openArtifact(delivery, 'baseline', file); }
        };
        return h('section', { className: 'geneloop-product-turn', onClickCapture: captureDelivery,
          ref: root => compactArtifactLabels(root, files) },
          h('style', null, artifactLinkStyle),
          h('style', null, liveStyle),
          h('style', null, `.geneloop-product-turn{min-width:0}.geneloop-process-toggle{display:flex;align-items:center;gap:8px;border:0;border-radius:8px;padding:7px 9px;margin:0 0 8px -9px;background:transparent;color:var(--dsw-alias-label-secondary);font:inherit;font-size:13px;cursor:pointer;text-align:left}.geneloop-process-toggle:hover{background:var(--dsw-alias-interactive-bg-hover)}.geneloop-process-toggle:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}.geneloop-process-toggle svg{flex:none;transition:transform .15s}.geneloop-process-toggle[aria-expanded=true] svg{transform:rotate(90deg)}.geneloop-process-evidence{border-left:2px solid var(--dsw-alias-border-l2,#8885);padding-left:14px;margin:4px 0 18px;color:var(--dsw-alias-label-secondary);font-size:13px;line-height:1.6}.geneloop-process-evidence>section{margin:12px 0}.geneloop-process-evidence pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0}.geneloop-process-label{font-weight:500}.geneloop-process-status{font-size:13px;color:var(--dsw-alias-label-secondary);margin:0 0 8px}@media(prefers-reduced-motion:reduce){.geneloop-process-toggle svg{transition:none}}`),
          running && liveStatus(status),
          hasProcess && h('button', { type: 'button', className: 'geneloop-process-toggle', 'aria-expanded': open, 'aria-controls': id,
            onClick: () => setOpen(value => !value) },
            h('svg', { width: 12, height: 12, viewBox: '0 0 12 12', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, 'aria-hidden': true }, h('path', { d: 'm4 2 4 4-4 4' })), label),
          h('div', { id, className: 'geneloop-process-evidence', hidden: !open }, open && [
            ...evidence.map(row => row.kind === 'assistant-step'
              ? h('section', { key: row.key }, h('div', { className: 'geneloop-process-label' }, '过程消息'), h(AssistantContent, { node: row, owner, process: true }))
              : row.kind === 'tool-call' ? h(ToolEvidence, { key: row.key, block: row.data.root })
              : h('section', { key: row.key }, h('div', { className: 'geneloop-process-label' }, row.kind === 'model-retry' ? '请求重试' : '上下文'),
                h('pre', null, row.kind === 'model-retry' ? '请求暂未完成，正在尝试恢复。' : contentText(row.data.content)))),
            ...reasoning.map((block, i) => h('section', { key: 'reasoning-' + i }, h('div', { className: 'geneloop-process-label' }, '思考过程'), h('pre', null, publicProcessText(block.text))))]),
          answer && h(AssistantContent, { node: answer, owner, delivery, live: running && answer.data.status === 'running' }),
          delivery?.id?.startsWith('file-') && delivery.status === 'interrupted' && !delivery.resumed && h('button', {type:'button',onClick:async()=>{
            try { await comparisonRequest(delivery,{action:'resume',session_id:session,id:delivery.id}); setDelivery({...delivery,resumed:true}); }
            catch(error){setDeliveryError(networkMessage(error));}
          }}, '恢复原文件管理任务'),
          delivery?.lanes.baseline.artifacts.length > 0 && h('div', { className: 'geneloop-chat-deliveries', 'aria-label': '交付文件' },
            ...delivery.lanes.baseline.artifacts.map(file => h('div', { key: file.id },
              h('button', { type: 'button', onClick: () => openArtifact(delivery, 'baseline', file) }, '预览 ' + artifactName(file)),
              ' · ', h('a', { href: comparisonUrl(delivery, 'baseline', file), download: artifactName(file) }, '下载')))),
          deliveryError && h('p', { role: 'alert' }, deliveryError, h('button', { type: 'button', onClick: () => retryDelivery(value => value + 1) }, '重试文件加载')));
      }
      function displayUserContent(content) {
        if (!Array.isArray(content) || !content.some(part => part.type === 'file')) return content;
        // Old queued messages can concatenate the prompt and extraction into
        // one text block. Preserve the actual prompt and native file cards.
        return content.flatMap(part => {
          if (part.type !== 'text' || typeof part.text !== 'string') return [part];
          const start = part.text.indexOf('用户附件的只读提取结果（');
          const newline = part.text.indexOf('\n', start);
          if (start < 0 || newline < 0) return [part];
          try {
            const value = JSON.parse(part.text.slice(newline + 1));
            const generated = Array.isArray(value.files) && value.files.length && value.files.every(file =>
              typeof file.name === 'string' && /^[a-f0-9]{64}$/.test(file.sha256) && typeof file.status === 'string');
            if (!generated) return [part];
            return start ? [{ ...part, text: part.text.slice(0, start) }] : [];
          } catch { return [part]; }
        });
      }
      ctx.slots.inject('conversation.chat.node', () => {
        const originals = (ctx.slots.entries?.('conversation.chat.node') || []).filter(entry =>
          ['user', 'steering'].includes(entry.options.key) && (entry.options.priority ?? 0) >= 0);
        const cleanups = originals.map(original => ctx.slots.register({ name: 'conversation.chat.node', ...original.options, priority: -100, locale: original.locale,
          inject: original.inject, ...(original.store ? { store: original.store } : {}) }, owner => h(original.component, {
          ...owner, node: { ...owner.node, data: { ...owner.node.data, content: displayUserContent(owner.node.data.content) } } })));
        return () => cleanups.forEach(dispose => dispose?.());
      });
      function ProductChatNode(owner) {
        const { node } = owner;
        const snapshot = owner.useChat(value => value), turn = turnOf(node);
        const rows = snapshot.order.map(key => snapshot.nodes.get(key)).filter(row => row && row.visibility !== 'hidden' && turnOf(row) === turn && processKinds.has(row.kind));
        const assistants = rows.filter(row => row.kind === 'assistant-step');
        const closed = (snapshot.timeline?.turns.get(turn)?.status ?? node.location?.turn?.status) === 'closed';
        // While generating, show the latest real text delta. After completion,
        // retain the final content-bearing message even if the tail is empty.
        const answer = closed ? assistants.findLast(hasAnswer) : assistants.at(-1);
        // Respect the public outer-seat boundary even when the last native
        // assistant block is an extension type rather than visible prose.
        const declaredAnswer = closed ? assistants.find(row => row.data.step === owner.turnProcess?.spec?.answerStep) : undefined;
        const anchor = declaredAnswer || answer || rows.at(-1);
        if (!anchor || anchor.key !== node.key) return hiddenChatNode();
        return h(ProductTurn, { key: `${owner.sessionId}:${turn}`, owner, rows, answer, running: !closed });
      }
      for (const key of processKinds) ctx.slots.inject('conversation.chat.node', () =>
        ctx.slots.register({ name: 'conversation.chat.node', key, priority: -100, locale: 'chat' }, ProductChatNode));
      for (const key of ['system-prompt', 'turn-process']) ctx.slots.inject('conversation.chat.node', () =>
        ctx.slots.register({ name: 'conversation.chat.node', key, priority: -100 }, hiddenChatNode));
      function inputFor(id) {
        const scope = sessions.scope(id);
        if (!scope) throw Error('会话已关闭，请重新打开');
        return conversation.input.for(scope);
      }
      const isCurrent = session => !sessions.list || sessions.list.getSnapshot().current === session.sessionId;
      function watchSession(session, signal) {
        const abort = new AbortController();
        const check = () => { if (!isCurrent(session)) abort.abort(); };
        const cancel = () => abort.abort();
        if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
        const off = sessions.list?.subscribe(check) || (() => {}); check();
        return { signal: abort.signal, dispose() { off(); signal?.removeEventListener('abort', cancel); }, check() {
          if (abort.signal.aborted) { const error = Error('会话已切换，原输入已保留'); error.name = 'AbortError'; throw error; }
        } };
      }
      function leadingSpan(id) {
        const state = inputFor(id).state.getSnapshot();
        const match = /^(\s*)\/[a-z0-9_-]*/i.exec(state.draft);
        if (!match) throw Error('输入已改变，请重新选择场景');
        return { start: match[1].length, end: match[0].length, draftRev: state.draftRev };
      }
      const sceneToken = draft => /^(\s*)\/([a-z][a-z0-9_-]*)(?=$|\s|[\u3400-\u9fff])/i.exec(draft);
      const choiceVersions = new Map(), draftWatches = new Map(), suppressDraftReset = new Set();
      const resetReason = '正在切换为普通对话…';
      const cancelledChoice = () => { const error = Error('场景选择已取消'); error.name = 'AbortError'; return error; };
      function displaySelection(id, scene) {
        if (scene) draftSelections.set(id, scene); else draftSelections.delete(id);
        const value = cache.get(id);
        if (value) for (const listener of observers.get(id) || []) listener(displayValue(id, value));
      }
      function clearResetBlock(id) {
        const blocks = conversation.blocks;
        if (blocks?.storeFor(id).getSnapshot()?.reason?.startsWith('普通对话切换失败')
          || blocks?.storeFor(id).getSnapshot()?.reason === resetReason) blocks.set(id, undefined);
      }
      const knownDraftScene = (id, draft) => {
        const token = sceneToken(draft);
        if (!token) return undefined;
        const name = token[2].toLowerCase(), value = cache.get(id);
        return value ? value.scenes.find(scene => shortcut(scene) === name)?.id
          : Object.keys(aliases).find(id => aliases[id] === name);
      };
      function watchDraft(session) {
        const id = session.sessionId;
        if (draftWatches.has(id)) return;
        const face = sessions.binding?.(id)?.session;
        const beginSubmission = face?.beginSubmission;
        const pendingSubmissions = new Set();
        // The public retirement callback distinguishes accepted sends from a
        // native optimistic editor clear. Never consume a scene on rejection.
        if (beginSubmission) face.beginSubmission = function (submission) {
          const version = choiceVersions.get(id) || 0, pending = {};
          pendingSubmissions.add(pending);
          try { return beginSubmission.call(this, { ...submission, onRetire: settlement => {
            pendingSubmissions.delete(pending);
            if (settlement.reason === 'observed' && version === (choiceVersions.get(id) || 0)) {
              revisions.set(id, (revisions.get(id) || 0) + 1);
              displaySelection(id, knownDraftScene(id, inputFor(id).state.getSnapshot().draft) || 'new-scene');
              const value = cache.get(id);
              if (value) publish(id, { ...value, selection: { ...value.selection, scene: 'new-scene' }, paired_comparison: false });
            }
            submission.onRetire?.(settlement);
          } }); } catch (error) { pendingSubmissions.delete(pending); throw error; }
        };
        const input = inputFor(id); let previous = input.state.getSnapshot();
        // The composer describes this draft, never the scene used by history.
        displaySelection(id, knownDraftScene(id, previous.draft) || 'new-scene');
        const off = input.state.subscribe(() => {
          const next = input.state.getSnapshot(), before = previous; previous = next;
          if (suppressDraftReset.has(id) || before.draftRev === next.draftRev || before.phase !== 'plain' || next.phase !== 'plain') return;
          // Native sends clear the draft before acceptance. The callback above
          // resets only the next input; the server owns the frozen running task.
          if (pendingSubmissions.size && !next.draft.trim()) return;
          const removed = knownDraftScene(id, before.draft), selected = knownDraftScene(id, next.draft);
          // Typed/pasted commands and native space-to-chip insertion do not
          // pass through onPick. The badge still describes this draft now.
          displaySelection(id, selected || 'new-scene');
          if (removed && removed !== 'new-scene' && !selected) void resetScene(session);
        });
        draftWatches.set(id, () => { off(); if (beginSubmission) face.beginSubmission = beginSubmission; });
      }
      async function resetScene(session) {
        const id = session.sessionId, previous = choosing.get(id), version = (choiceVersions.get(id) || 0) + 1;
        choiceVersions.set(id, version); revisions.set(id, (revisions.get(id) || 0) + 1);
        displaySelection(id, 'new-scene');
        const blocks = conversation.blocks, existing = blocks?.storeFor(id).getSnapshot();
        if (!existing || existing.reason === resetReason) blocks?.set(id, { reason: resetReason });
        const current = () => choiceVersions.get(id) === version;
        const operation = (async () => {
          // An aborted HTTP request can still mutate the server. Let the old
          // mount settle, then overwrite it; never race a reset against a pick.
          await previous?.catch(() => {});
          if (!current()) return;
          // The visible conversation owns the scene choice. Immutable tool
          // agents are rotated privately by the server; drafts never move.
          const next = await request(session, { action: 'select', session_id: id, selection: { scene: 'new-scene' } });
          if (current()) displaySelection(id, knownDraftScene(id, inputFor(id).state.getSnapshot().draft) || 'new-scene');
          publish(id, next); // Canonical state may change under a newer draft overlay.
        })();
        choosing.set(id, operation);
        try { await operation; if (current()) clearResetBlock(id); }
        catch (error) {
          if (current()) {
            blocks?.set(id, { reason: '普通对话切换失败，请刷新页面后重试。' });
            report(session, error);
          }
        } finally { if (choosing.get(id) === operation) choosing.delete(id); }
      }
      ctx.effect(() => {
        const attach = () => {
          const id = sessions.list?.getSnapshot().current;
          if (!id) return;
          try {
            watchDraft({ sessionId: id });
          } catch (error) {
            if (conversation.blocks?.storeFor(id).getSnapshot()?.reason === resetReason)
              conversation.blocks.set(id, { reason: '普通对话切换失败，请刷新页面后重试。' });
            report({ sessionId: id }, error);
          }
        };
        const off = sessions.list?.subscribe(attach) || (() => {}); attach();
        return () => { off(); for (const stop of draftWatches.values()) stop(); draftWatches.clear(); };
      }, 'harless: scene draft cancellation');
      const sameAttachments = (left, right) => left.length === right.length && left.every((id, index) => id === right[index]);
      const draftSnapshot = input => { const state = input.state.getSnapshot(); return { ...state, attachmentIds: [...state.attachmentIds] }; };
      const sameDraft = (input, span, expectedAttachments) => {
        const state = input.state.getSnapshot();
        return state.draftRev === span.draftRev && state.phase === 'plain'
          && (expectedAttachments === undefined || sameAttachments(state.attachmentIds, expectedAttachments));
      };
      async function chooseScene(session, id, span, fromCommand = false, automatic = false) {
        // The current span, not a formerly highlighted menu row, owns the pick.
        watchDraft(session);
        const oldInput = inputFor(session.sessionId), initial = draftSnapshot(oldInput);
        if (!sameDraft(oldInput, span)) throw Error('输入已改变，请重新选择场景');
        const token = initial.draft.slice(span.start, span.end).toLowerCase();
        const known = cache.get(session.sessionId)?.scenes.find(row => row.id === id);
        const leadingInsertion = span.start === 0 && span.end === 0;
        // The add menu can replace a complete, existing scene chip. Partial
        // typed queries still constrain candidates; stale spans still fail CAS.
        const replacingScene = !automatic && !fromCommand
          && span.start === (initial.draft.match(/^\s*/)?.[0].length || 0)
          && cache.get(session.sessionId)?.scenes.some(row => '/' + shortcut(row) === token);
        if ((!leadingInsertion && !/^\/[a-z0-9_-]*$/i.test(token)) || (fromCommand ? token !== '/harless' : known && !replacingScene && !('/' + shortcut(known)).startsWith(token)))
          throw Error('候选已更新，请按当前输入重新选择场景');
        const previous = choosing.get(session.sessionId), version = (choiceVersions.get(session.sessionId) || 0) + 1;
        choiceVersions.set(session.sessionId, version);
        // Commit the native chip synchronously. The backend may need to mount
        // an MCP; that must not delay visual acknowledgement of a valid pick.
        let expectedSpan = span, optimistic = false;
        if (known && known.available !== false) {
          // The launcher spans clipboard text; native chips occupy ONE detect
          // character. Keep the native edit/undo path and all following chips.
          let insertSpan = span;
          if (replacingScene && oldInput.editor) {
            const children = oldInput.editor.getEditorState().toJSON().root.children[0]?.children || [];
            let offset = 0;
            for (const node of children) {
              if (node.type === 'reference-chip') {
                if (offset === span.start && node.source === 'harless-scenes' && node.clipboardText.toLowerCase() === token)
                  insertSpan = { ...span, end: span.start + 1 };
                break;
              }
              if (node.type !== 'text' || !/^\s*$/.test(node.text)) break;
              offset += node.text.length;
            }
          }
          if (!oldInput.insertReference(reference(known), insertSpan)) throw Error('输入已改变，请重新选择场景');
          optimistic = true;
          expectedSpan = { ...span, draftRev: oldInput.state.getSnapshot().draftRev };
          displaySelection(session.sessionId, id);
        }
        const guard = watchSession(session);
        const checkChoice = () => { guard.check(); if (choiceVersions.get(session.sessionId) !== version) throw cancelledChoice(); };
        const operation = (async () => {
          if (previous) await previous.catch(() => {});
          checkChoice();
          const oldInput = inputFor(session.sessionId);
          const value = cache.get(session.sessionId) || await settings(session, guard.signal), scene = value.scenes.find(row => row.id === id);
          checkChoice();
          if (!scene || scene.available === false) throw Error('该场景暂不可用：' + (scene?.unavailable_reason || '未部署'));
          if (!sameDraft(oldInput, expectedSpan, initial.attachmentIds)
            && !(optimistic && !automatic && knownDraftScene(session.sessionId, oldInput.state.getSnapshot().draft) === id))
            throw Error('输入或附件已改变，请重新选择场景');
          if (!fromCommand && !replacingScene && !('/' + shortcut(scene)).startsWith(token)) throw Error('候选已更新，请按当前输入重新选择场景');
          const next = await request(session, { action: 'select', session_id: session.sessionId, selection: { scene: id } }, guard.signal);
          checkChoice();
          if (!optimistic && !sameDraft(oldInput, expectedSpan, initial.attachmentIds)
            && !knownDraftScene(session.sessionId, oldInput.state.getSnapshot().draft)) {
            void resetScene(session); throw cancelledChoice();
          }
          displaySelection(session.sessionId, knownDraftScene(session.sessionId, oldInput.state.getSnapshot().draft) || 'new-scene');
          clearResetBlock(session.sessionId); publish(session.sessionId, next);
          // A manual pick only selects; typing while its mount completes is
          // normal. Keep those edits. Automatic handoff still requires CAS.
          if (optimistic && !automatic && !sameDraft(oldInput, expectedSpan, initial.attachmentIds))
            return { input: oldInput, state: draftSnapshot(oldInput), sessionId: session.sessionId };
          if (!sameDraft(oldInput, expectedSpan, initial.attachmentIds) || (!optimistic && !oldInput.insertReference(reference(scene), span)))
            throw Error('场景已选择，但输入或附件已改变；已保留草稿，请确认后重新发送。');
          return { input: oldInput, state: draftSnapshot(oldInput), sessionId: session.sessionId };
        })();
        choosing.set(session.sessionId, operation);
        try { return await operation; }
        catch (error) {
          if (choiceVersions.get(session.sessionId) === version) {
            displaySelection(session.sessionId, undefined);
            clearResetBlock(session.sessionId);
            if (optimistic && sameDraft(oldInput, expectedSpan, initial.attachmentIds)) {
              suppressDraftReset.add(session.sessionId);
              try { oldInput.setDraft(initial.draft); } finally { suppressDraftReset.delete(session.sessionId); }
            }
          }
          throw error;
        } finally { guard.dispose(); if (choosing.get(session.sessionId) === operation) choosing.delete(session.sessionId); }
      }
      const report = (session, error) => { if (!isCurrent(session) || error.name === 'AbortError') return; try { inputFor(session.sessionId).notify('error', error.message); } catch {} };
      // The native trigger recomputes candidates after every character and owns
      // keyboard/IME handling, span CAS, atomic chip deletion and undo.
      ctx.effect(() => triggers.registerSource({ trigger: '/', name: 'harless-scenes', order: -10,
        candidates: async (session, req) => {
          watchDraft(session);
          if (req.position !== 'leading') return [];
          const query = req.query.toLowerCase();
          if (!/^[a-z0-9_-]*$/.test(query)) return [];
          const value = cache.get(session.sessionId) || await settings(session, req.signal);
          if (req.signal?.aborted) return [];
          return [...(!query && uploads.has(session.sessionId) ? [{ name: '添加照片或文件', value: 'upload', section: '添加', description: '从电脑上传' }] : []),
            ...value.scenes.filter(scene => selectableScene(scene) && shortcut(scene).startsWith(query)).map(scene => ({
            name: shortcut(scene), value: scene.id, section: '场景', description: scene.available === false
              ? `暂不可用：${scene.unavailable_reason}` : ({ ppt: '演示文稿', 'paper-proofreading': '论文校对', 'research-data-analysis': '数据分析',files:'文件管理' })[scene.id] || scene.label,
          }))];
        },
        onPick: pick => {
          if (pick.candidate.value === 'upload') {
            if (!isCurrent(pick.session)) return 'handled';
            const input = document.createElement('input'); input.type = 'file'; input.multiple = true; input.hidden = true;
            const remove = () => input.remove();
            input.oncancel = remove;
            input.onchange = () => {
              if (isCurrent(pick.session) && input.files?.length) {
                const error = uploads.get(pick.session.sessionId)?.(Array.from(input.files));
                if (error) report(pick.session, Error(error));
              }
              remove();
            };
            document.body.appendChild(input); input.click(); return 'handled';
          }
          void chooseScene(pick.session, pick.candidate.value, pick.span).catch(error => report(pick.session, error)); return 'handled';
        },
        matchSpace: (session, token) => {
          const scene = cache.get(session.sessionId)?.scenes.find(row => '/' + shortcut(row) === token.toLowerCase());
          // Hot, synchronous native insertion. Selection is confirmed by the
          // Enter hook, so typing quickly cannot send with a previous scene.
          return scene?.available !== false && scene ? { insert: reference(scene) } : undefined;
        },
        matchEnter: (session, line, signal) => {
          const token = sceneToken(line);
          if (!token) return;
          const name = token[2].toLowerCase(), hot = cache.get(session.sessionId);
          if (hot && !hot.scenes.some(scene => shortcut(scene) === name)) return;
          if (!isCurrent(session)) return 'handled';
          const scene = hot?.scenes.find(row => shortcut(row) === name);
          if (scene?.available === false) throw Error('该场景暂不可用：' + (scene.unavailable_reason || '未部署'));
          if (signal?.aborted) throw Error('场景选择已取消，输入已保留');
          // The native sender paints its message/attachment echo before I/O.
          // The server parses this exact prefix atomically during admission;
          // fetching or mounting a scene here would block that first paint.
        },
        lexicon: session => cache.get(session.sessionId)?.scenes.filter(selectableScene).map(shortcut),
        subscribeLexicon: (session, listener) => {
          const group = lexiconObservers.get(session.sessionId) || new Set(); group.add(listener); lexiconObservers.set(session.sessionId, group);
          return () => { group.delete(listener); if (!group.size) lexiconObservers.delete(session.sessionId); };
        },
        warm: session => { watchDraft(session); void settings(session).catch(() => {}); },
        codec: { clipboardText: ref => '/' + ref, serialize: async ref => {
          if (!/^[a-z][a-z0-9_-]{0,63}$/.test(ref)) throw Error('无效的场景标识'); return '/' + ref;
        } },
      }), 'harless: scene reference source');
      ctx.effect(() => command.decorate({ name: 'harless', available: () => true, ui: {
        kind: 'popupSelect',
        options: async (session, signal) => {
          const value = await settings(session, signal);
          return [
            ...value.scenes.map(scene => ({ id: `scene:${scene.id}`, label: '/' + shortcut(scene),
              detail: scene.available === false ? `暂不可用：${scene.unavailable_reason}` : scene.label,
              active: value.selection.scene === scene.id })),
            ...(!value.scene_locked ? (value.scene_option_fields || []).flatMap(field => field.values.map(choice => ({
              id: `option:${field.key}=${JSON.stringify(choice.value)}`, label: choice.label,
              detail: choice.detail || field.label, active: (value.scene_options?.[field.key] ?? field.default) === choice.value,
            }))) : []),
            ...(!value.paired_comparison && value.selection.scene !== 'files' ? ['baseline', 'shadow', 'execute'].map(mode => ({ id: `mode:${mode}`, label: modeLabel(mode), detail: modeDetail(mode), active: value.selection.mode === mode })) : []),
            ...(!value.paired_comparison && value.selection.scene !== 'files' ? [true, false].map(rsi => ({ id: `rsi:${rsi ? 'on' : 'off'}`, label: `Motif 复用：${rsi ? '允许' : '关闭'}`, detail: rsi ? '需选择校验后复用模式；标准执行不受此开关影响' : '本轮按标准流程执行', active: value.selection.rsi === rsi })) : []),
          ];
        },
        onSelect: async (option, session) => {
          const separator = option.id.indexOf(':'), kind = option.id.slice(0, separator), id = option.id.slice(separator + 1);
          if (kind === 'scene') return chooseScene(session, id, leadingSpan(session.sessionId), true);
          if (kind === 'option') {
            const current = await settings(session), split = id.indexOf('='), key = id.slice(0, split);
            if (current.scene_locked) throw Error('当前任务已固定选项，请在新会话中设置');
            const selected = JSON.parse(id.slice(split + 1)), field = current.scene_option_fields?.find(row => row.key === key);
            if (!field || !field.values.some(row => row.value === selected)) throw Error('未知任务选项');
            publish(session.sessionId, await request(session, { action: 'set_scene_options', session_id: session.sessionId,
              options: { ...current.scene_options, [key]: selected } }));
            return;
          }
          const patch = kind === 'mode' ? { mode: id } : kind === 'rsi' ? { rsi: id === 'on' } : undefined;
          if (!patch) throw Error('未知设置');
          publish(session.sessionId, await request(session, { action: 'select', session_id: session.sessionId, selection: patch }));
        },
      } }), 'harless: native command picker');
      ctx.slots.inject('conversation.input.left', () => ctx.slots.register(
        { name: 'conversation.input.left', id: 'harless-status', order: 40, inject: sessionId => ({ sessionId, draftInput: inputFor(sessionId), openSession: id => sessions.open(id) }) }, HarlessStatus));
    }
    return { inject, apply };
  },
});
