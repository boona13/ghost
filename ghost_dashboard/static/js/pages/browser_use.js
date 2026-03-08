/** Browser-Use page — AI-native browser automation dashboard */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api } = window;

  let sessions = [];
  let selectedSession = null;
  let isAvailable = false;

  container.innerHTML = `
    <div class="page-header">${t('browser_use.title')}</div>
    <div class="page-desc">${t('browser_use.subtitle')}</div>
    
    <div id="bu-llm-info" class="flex items-center gap-2 mb-4 text-xs text-zinc-400">
      <span>${t('browser_use.poweredBy')}:</span>
      <span id="bu-llm-label" class="badge badge-zinc">${t('common.loading')}</span>
    </div>
    
    <div id="bu-status-banner" class="stat-card mb-4 hidden">
      <div class="text-zinc-300 text-sm">
        ${t('browser_use.notInstalled')}
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-1">
        <div class="stat-card">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-white font-medium">${t('browser_use.sessions')}</h3>
            <button id="bu-new-session" class="btn btn-primary btn-sm">${t('browser_use.newSession')}</button>
          </div>
          <div id="bu-sessions-list" class="space-y-2 max-h-96 overflow-y-auto">
            <div class="text-zinc-500 text-sm text-center py-4">${t('common.loading')}</div>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2">
        <div id="bu-detail-panel" class="stat-card hidden">
          <div class="flex items-center justify-between mb-4">
            <div>
              <h3 class="text-white font-medium" id="bu-detail-title">${t('browser_use.session')}</h3>
              <p class="text-zinc-500 text-xs" id="bu-detail-url"></p>
            </div>
            <div class="flex gap-2">
              <span id="bu-detail-status" class="badge badge-zinc">idle</span>
              <button id="bu-close-session" class="btn btn-danger btn-sm">${t('browser_use.close')}</button>
            </div>
          </div>

          <div class="mb-4">
            <label class="form-label">${t('browser_use.taskDescription')}</label>
            <textarea id="bu-task-input" class="form-input w-full" rows="3" 
              placeholder="${t('browser_use.taskPlaceholder')}"></textarea>
            <div class="flex items-center gap-3 mt-2">
              <label class="flex items-center gap-2 text-zinc-400 text-xs">
                <input type="checkbox" id="bu-headless" checked> ${t('browser_use.headless')}
              </label>
              <button id="bu-run-task" class="btn btn-primary btn-sm ml-auto">${t('browser_use.runTask')}</button>
            </div>
          </div>

          <div class="flex gap-2 mb-4">
            <button id="bu-get-html" class="btn btn-secondary btn-sm">${t('browser_use.getHtml')}</button>
            <button id="bu-screenshot" class="btn btn-secondary btn-sm">${t('browser_use.screenshot')}</button>
            <button id="bu-navigate-btn" class="btn btn-secondary btn-sm">${t('browser_use.navigate')}</button>
          </div>

          <div id="bu-output-panel" class="hidden">
            <div class="flex items-center justify-between mb-2">
              <span class="text-zinc-400 text-xs">${t('browser_use.output')}</span>
              <button id="bu-clear-output" class="text-zinc-500 hover:text-zinc-300 text-xs">${t('common.clear')}</button>
            </div>
            <pre id="bu-output-content" class="bg-surface-800 p-3 rounded text-xs text-zinc-300 overflow-auto max-h-64 font-mono"></pre>
          </div>

          <div class="mt-4">
            <h4 class="text-zinc-400 text-xs mb-2">${t('browser_use.historyLabel')}</h4>
            <div id="bu-history-list" class="space-y-2 max-h-48 overflow-y-auto">
              <div class="text-zinc-600 text-xs">${t('browser_use.noHistory')}</div>
            </div>
          </div>
        </div>

        <div id="bu-empty-state" class="stat-card text-center py-12">
          <p class="text-zinc-500">${t('browser_use.selectOrCreate')}</p>
        </div>
      </div>
    </div>

    <div id="bu-new-modal" class="fixed inset-0 bg-black/60 hidden items-center justify-center z-50">
      <div class="stat-card w-full max-w-md">
        <h3 class="text-white font-medium mb-4">${t('browser_use.newBrowserSession')}</h3>
        <div class="mb-4">
          <label class="form-label">${t('browser_use.startingUrl')}</label>
          <input type="text" id="bu-new-url" class="form-input w-full" value="https://google.com">
        </div>
        <div class="flex justify-end gap-2">
          <button id="bu-cancel-new" class="btn btn-ghost">${t('common.cancel')}</button>
          <button id="bu-confirm-new" class="btn btn-primary">${t('common.create')}</button>
        </div>
      </div>
    </div>

    <div id="bu-navigate-modal" class="fixed inset-0 bg-black/60 hidden items-center justify-center z-50">
      <div class="stat-card w-full max-w-md">
        <h3 class="text-white font-medium mb-4">${t('browser_use.navigateToUrl')}</h3>
        <div class="mb-4">
          <label class="form-label">${t('browser_use.urlLabel')}</label>
          <input type="text" id="bu-navigate-url" class="form-input w-full" placeholder="${t('browser_use.urlPlaceholder')}">
        </div>
        <div class="flex justify-end gap-2">
          <button id="bu-cancel-navigate" class="btn btn-ghost">${t('common.cancel')}</button>
          <button id="bu-confirm-navigate" class="btn btn-primary">${t('browser_use.navigate')}</button>
        </div>
      </div>
    </div>
  `;

  const statusBanner = container.querySelector('#bu-status-banner');
  const sessionsList = container.querySelector('#bu-sessions-list');
  const detailPanel = container.querySelector('#bu-detail-panel');
  const emptyState = container.querySelector('#bu-empty-state');
  const detailTitle = container.querySelector('#bu-detail-title');
  const detailUrl = container.querySelector('#bu-detail-url');
  const detailStatus = container.querySelector('#bu-detail-status');
  const historyList = container.querySelector('#bu-history-list');
  const outputPanel = container.querySelector('#bu-output-panel');
  const outputContent = container.querySelector('#bu-output-content');
  const taskInput = container.querySelector('#bu-task-input');
  const headlessCheck = container.querySelector('#bu-headless');
  const newModal = container.querySelector('#bu-new-modal');
  const navigateModal = container.querySelector('#bu-navigate-modal');

  function showOutput(content) {
    outputContent.textContent = typeof content === 'object' ? JSON.stringify(content, null, 2) : content;
    outputPanel.classList.remove('hidden');
  }

  function clearOutput() {
    outputContent.textContent = '';
    outputPanel.classList.add('hidden');
  }

  function getStatusBadgeClass(status) {
    switch (status) {
      case 'idle': return 'badge-zinc';
      case 'running': return 'badge-blue';
      case 'completed': return 'badge-green';
      case 'error': return 'badge-red';
      default: return 'badge-zinc';
    }
  }

  async function loadSessions() {
    try {
      const data = await api.get('/api/browser-use/sessions');
      if (!data.success) {
        sessionsList.innerHTML = `<div class="text-red-400 text-sm text-center">${data.error}</div>`;
        return;
      }
      sessions = data.sessions || [];
      isAvailable = data.browser_use_available;
      if (!isAvailable) statusBanner.classList.remove('hidden');
      renderSessionsList();
    } catch (err) {
      sessionsList.innerHTML = `<div class="text-red-400 text-sm text-center">${t('browser_use.failedToLoad')}</div>`;
    }
  }

  function renderSessionsList() {
    if (sessions.length === 0) {
      sessionsList.innerHTML = `<div class="text-zinc-500 text-sm text-center py-4">${t('browser_use.noActiveSessions')}</div>`;
      return;
    }
    sessionsList.innerHTML = sessions.map(s => `
      <div class="bu-session-item p-3 rounded cursor-pointer ${selectedSession?.id === s.id ? 'bg-ghost-purple/20' : 'bg-surface-700'}"
           data-id="${s.id}">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-zinc-200 text-sm">${s.id}</div>
            <div class="text-zinc-500 text-xs truncate">${s.url}</div>
          </div>
          <span class="badge ${getStatusBadgeClass(s.status)}">${s.status}</span>
        </div>
      </div>
    `).join('');
    container.querySelectorAll('.bu-session-item').forEach(el => {
      el.addEventListener('click', () => selectSession(el.dataset.id));
    });
  }

  async function selectSession(sessionId) {
    try {
      const data = await api.get(`/api/browser-use/sessions/${sessionId}`);
      if (!data.success) return;
      selectedSession = data.session;
      renderSessionsList();
      renderSessionDetail();
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  }

  function renderSessionDetail() {
    if (!selectedSession) {
      detailPanel.classList.add('hidden');
      emptyState.classList.remove('hidden');
      return;
    }
    detailPanel.classList.remove('hidden');
    emptyState.classList.add('hidden');
    detailTitle.textContent = selectedSession.id;
    detailUrl.textContent = selectedSession.url;
    detailStatus.textContent = selectedSession.status;
    detailStatus.className = `badge ${getStatusBadgeClass(selectedSession.status)}`;
    
    if (selectedSession.history?.length > 0) {
      historyList.innerHTML = selectedSession.history.slice().reverse().map(h => `
        <div class="bg-surface-700 p-2 rounded text-xs">
          <div class="flex justify-between">
            <span class="text-zinc-400">${new Date(h.timestamp).toLocaleTimeString()}</span>
            <span class="badge ${h.success ? 'badge-green' : 'badge-red'}">${h.success ? t('common.ok') : t('common.err')}</span>
          </div>
          <div class="text-zinc-300 truncate">${h.task}</div>
        </div>
      `).join('');
    } else {
      historyList.innerHTML = `<div class="text-zinc-600 text-xs">${t('browser_use.noHistory')}</div>`;
    }
  }

  // Event handlers
  container.querySelector('#bu-new-session').addEventListener('click', () => {
    newModal.classList.remove('hidden');
    newModal.classList.add('flex');
  });

  container.querySelector('#bu-cancel-new').addEventListener('click', () => {
    newModal.classList.add('hidden');
    newModal.classList.remove('flex');
  });

  container.querySelector('#bu-confirm-new').addEventListener('click', async () => {
    const url = container.querySelector('#bu-new-url').value;
    try {
      const data = await api.post('/api/browser-use/sessions', { url });
      if (data.success) {
        newModal.classList.add('hidden');
        newModal.classList.remove('flex');
        await loadSessions();
        selectSession(data.session_id);
      }
    } catch (err) {
      alert(t('browser_use.failedCreate') + ' ' + err);
    }
  });

  container.querySelector('#bu-close-session').addEventListener('click', async () => {
    if (!selectedSession) return;
    if (!confirm(t('browser_use.closeConfirm', {id: selectedSession.id}))) return;
    try {
      await api.del(`/api/browser-use/sessions/${selectedSession.id}`);
      selectedSession = null;
      await loadSessions();
      renderSessionDetail();
    } catch (err) {
      alert(t('browser_use.failedClose') + ' ' + err);
    }
  });

  container.querySelector('#bu-run-task').addEventListener('click', async () => {
    if (!selectedSession) return;
    const task = taskInput.value.trim();
    if (!task) return alert(t('browser_use.enterTask'));
    detailStatus.textContent = 'running';
    detailStatus.className = 'badge badge-blue';
    try {
      const data = await api.post(`/api/browser-use/sessions/${selectedSession.id}/task`, {
        task, headless: headlessCheck.checked
      });
      showOutput(data);
      await selectSession(selectedSession.id);
    } catch (err) {
      showOutput({ error: err.message });
    }
  });

  container.querySelector('#bu-get-html').addEventListener('click', async () => {
    if (!selectedSession) return;
    try {
      const data = await api.get(`/api/browser-use/sessions/${selectedSession.id}/html`);
      showOutput(data);
    } catch (err) {
      showOutput({ error: err.message });
    }
  });

  container.querySelector('#bu-screenshot').addEventListener('click', async () => {
    if (!selectedSession) return;
    try {
      const data = await api.post(`/api/browser-use/sessions/${selectedSession.id}/screenshot`, {});
      showOutput(data);
    } catch (err) {
      showOutput({ error: err.message });
    }
  });

  container.querySelector('#bu-navigate-btn').addEventListener('click', () => {
    navigateModal.classList.remove('hidden');
    navigateModal.classList.add('flex');
  });

  container.querySelector('#bu-cancel-navigate').addEventListener('click', () => {
    navigateModal.classList.add('hidden');
    navigateModal.classList.remove('flex');
  });

  container.querySelector('#bu-confirm-navigate').addEventListener('click', async () => {
    const url = container.querySelector('#bu-navigate-url').value.trim();
    if (!url) return alert(t('browser_use.navigateToUrl'));
    try {
      const data = await api.post(`/api/browser-use/sessions/${selectedSession.id}/navigate`, { url });
      showOutput(data);
      navigateModal.classList.add('hidden');
      navigateModal.classList.remove('flex');
      await selectSession(selectedSession.id);
    } catch (err) {
      showOutput({ error: err.message });
    }
  });

  container.querySelector('#bu-clear-output').addEventListener('click', clearOutput);

  // Close modals on backdrop click
  newModal.addEventListener('click', (e) => {
    if (e.target === newModal) {
      newModal.classList.add('hidden');
      newModal.classList.remove('flex');
    }
  });
  navigateModal.addEventListener('click', (e) => {
    if (e.target === navigateModal) {
      navigateModal.classList.add('hidden');
      navigateModal.classList.remove('flex');
    }
  });

  // Close on Escape key (with cleanup when page navigates away)
  function onEscape(e) {
    if (e.key === 'Escape') {
      newModal.classList.add('hidden');
      newModal.classList.remove('flex');
      navigateModal.classList.add('hidden');
      navigateModal.classList.remove('flex');
    }
  }
  document.addEventListener('keydown', onEscape);

  // Auto-refresh sessions every 5s
  const refreshTimer = setInterval(async () => {
    if (!document.body.contains(container)) return;
    await loadSessions();
    if (selectedSession) {
      try {
        const data = await api.get(`/api/browser-use/sessions/${selectedSession.id}`);
        if (data.success) {
          selectedSession = data.session;
          renderSessionDetail();
        }
      } catch (_) { /* session may have been deleted */ }
    }
  }, 5000);

  // Cleanup when navigating away from this page
  const observer = new MutationObserver(() => {
    if (!document.body.contains(container)) {
      document.removeEventListener('keydown', onEscape);
      clearInterval(refreshTimer);
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // Fetch LLM status
  async function loadLlmStatus() {
    const llmLabel = container.querySelector('#bu-llm-label');
    try {
      const data = await api.get('/api/browser-use/status');
      if (data.llm?.resolved) {
        llmLabel.textContent = data.llm.description || `${data.llm.provider} / ${data.llm.model}`;
        llmLabel.className = 'badge badge-green';
      } else {
        llmLabel.textContent = t('browser_use.noLlmConfigured');
        llmLabel.className = 'badge badge-yellow';
      }
    } catch {
      llmLabel.textContent = '\u2014';
    }
  }

  // Initial load
  await Promise.all([loadSessions(), loadLlmStatus()]);
}
