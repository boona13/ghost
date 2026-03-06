/** Ghost Extensions management page — browse, install, enable/disable, configure extensions + Community Hub */

let _extCatFilter = '';

const CATEGORY_ICONS = {
  integration: '🔗',
  dashboard: '📊',
  tool: '🛠',
  channel: '💬',
  automation: '⚡',
  monitoring: '📡',
  utility: '🔧',
  node: '🧪',
};

function getCategoryLabel(cat) {
  return cat ? cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, ' ') : 'Utility';
}

let _activeTab = 'installed';

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let data;
  try {
    data = await api.get('/api/extensions');
  } catch (e) {
    container.innerHTML = `<div class="text-red-400 p-4">Failed to load extensions: ${u.escapeHtml(e.message)}</div>`;
    return;
  }

  const exts = data.extensions || [];
  const categories = data.categories || {};

  const loaded = exts.filter(e => e.loaded);
  const withErrors = exts.filter(e => e.error);

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">Extensions</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-green">${loaded.length} loaded</span>
        <span class="badge badge-zinc">${exts.length} installed</span>
        ${withErrors.length ? `<span class="badge badge-red">${withErrors.length} errors</span>` : ''}
      </div>
    </div>
    <p class="page-desc">Self-contained feature plugins. Extensions add tools, dashboard pages, cron jobs, and hooks without modifying Ghost core.</p>

    <!-- Tab Bar -->
    <div class="flex gap-1 mb-6 border-b border-surface-600/30">
      <button class="ext-tab px-4 py-2 text-sm font-medium ${_activeTab === 'installed' ? 'text-white border-b-2 border-ghost-500' : 'text-zinc-400 hover:text-zinc-300'}" data-tab="installed">Installed</button>
      <button class="ext-tab px-4 py-2 text-sm font-medium ${_activeTab === 'hub' ? 'text-white border-b-2 border-ghost-500' : 'text-zinc-400 hover:text-zinc-300'}" data-tab="hub">Community Hub</button>
    </div>

    <!-- Installed Tab -->
    <div id="tab-installed" class="${_activeTab === 'installed' ? '' : 'hidden'}">
      <!-- Install Section -->
      <div class="stat-card mb-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-white">Install Extension</h2>
        </div>
        <div class="flex gap-2">
          <input id="ext-install-source" type="text" placeholder="GitHub URL or local path..." 
                 class="flex-1 bg-surface-800 border border-surface-600 rounded px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-ghost-500 focus:outline-none" />
          <button id="ext-install-btn" class="btn btn-primary text-sm px-4 py-2">Install</button>
        </div>
        <div id="ext-install-msg" class="mt-2 text-xs hidden"></div>
      </div>

      <!-- Category Filter -->
      ${Object.keys(categories).length > 1 ? `
        <div class="flex gap-2 mb-4 flex-wrap">
          <button class="ext-cat-filter btn btn-sm ${!_extCatFilter ? 'btn-primary' : 'btn-ghost'}" data-cat="">All</button>
          ${Object.entries(categories).map(([cat, count]) => `
            <button class="ext-cat-filter btn btn-sm ${_extCatFilter === cat ? 'btn-primary' : 'btn-ghost'}" data-cat="${cat}">
              ${CATEGORY_ICONS[cat] || '📦'} ${getCategoryLabel(cat)} (${count})
            </button>
          `).join('')}
        </div>
      ` : ''}

      <!-- Extensions Grid -->
      <div id="ext-grid" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${exts.length === 0 ? `
          <div class="col-span-2 text-center py-12 text-zinc-500">
            <p class="text-lg mb-2">No extensions installed</p>
            <p class="text-sm">Ghost will build extensions autonomously when implementing new features, or you can install them from GitHub.</p>
          </div>
        ` : exts.filter(ext => {
          if (!_extCatFilter) return true;
          const m = ext.manifest || {};
          return (m.category || 'utility') === _extCatFilter;
        }).map(ext => renderExtensionCard(ext, u)).join('')}
      </div>
    </div>

    <!-- Community Hub Tab -->
    <div id="tab-hub" class="${_activeTab === 'hub' ? '' : 'hidden'}">
      <div class="stat-card mb-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-white">Community Hub</h2>
          <span id="hub-status" class="text-xs text-zinc-500">Checking...</span>
        </div>
        <p class="text-xs text-zinc-400 mb-3">Discover and install extensions and nodes shared by the Ghost community.</p>
        <div class="flex gap-2 mb-4">
          <input id="hub-search" type="text" placeholder="Search extensions and nodes..." 
                 class="flex-1 bg-surface-800 border border-surface-600 rounded px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-ghost-500 focus:outline-none" />
          <select id="hub-kind" class="bg-surface-800 border border-surface-600 rounded px-3 py-2 text-sm text-white">
            <option value="extensions">Extensions</option>
            <option value="nodes">Nodes</option>
          </select>
          <button id="hub-search-btn" class="btn btn-primary text-sm px-4 py-2">Search</button>
        </div>
      </div>
      <div id="hub-results" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="col-span-2 text-center py-8 text-zinc-500 text-sm">
          Search the Community Hub to discover extensions and nodes, or browse by category.
        </div>
      </div>
    </div>
  `;

  // Tab switching
  container.querySelectorAll('.ext-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeTab = btn.dataset.tab;
      render(container);
    });
  });

  // Install handler
  const installBtn = container.querySelector('#ext-install-btn');
  const installInput = container.querySelector('#ext-install-source');
  const installMsg = container.querySelector('#ext-install-msg');

  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      const source = installInput.value.trim();
      if (!source) return;
      installBtn.disabled = true;
      installBtn.textContent = 'Installing...';
      installMsg.className = 'mt-2 text-xs text-zinc-400';
      installMsg.textContent = 'Installing extension...';
      installMsg.classList.remove('hidden');

      try {
        const result = await api.post('/api/extensions/install', { source });
        if (result.status === 'ok') {
          installMsg.className = 'mt-2 text-xs text-emerald-400';
          installMsg.textContent = `Installed ${result.name}. Tools: ${(result.tools || []).join(', ') || 'none'}. Restart may be needed for routes/pages.`;
          installInput.value = '';
          setTimeout(() => render(container), 1500);
        } else {
          installMsg.className = 'mt-2 text-xs text-red-400';
          installMsg.textContent = result.error || 'Install failed';
        }
      } catch (e) {
        installMsg.className = 'mt-2 text-xs text-red-400';
        installMsg.textContent = e.message;
      } finally {
        installBtn.disabled = false;
        installBtn.textContent = 'Install';
      }
    });
  }

  // Category filter handlers
  container.querySelectorAll('.ext-cat-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      _extCatFilter = btn.dataset.cat || '';
      render(container);
    });
  });

  // Enable/disable/uninstall handlers
  container.querySelectorAll('[data-ext-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.dataset.extAction;
      const name = btn.dataset.extName;
      btn.disabled = true;
      try {
        if (action === 'enable') await api.post(`/api/extensions/${name}/enable`);
        else if (action === 'disable') await api.post(`/api/extensions/${name}/disable`);
        else if (action === 'uninstall') {
          if (!confirm(`Uninstall extension "${name}"? This cannot be undone.`)) return;
          await api.post(`/api/extensions/${name}/uninstall`);
        }
        render(container);
      } catch (e) {
        u.toast?.(`Error: ${e.message}`, 'error');
      } finally {
        btn.disabled = false;
      }
    });
  });

  // Settings toggle handlers
  container.querySelectorAll('[data-ext-settings]').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.extSettings;
      const panel = container.querySelector(`#ext-settings-${name}`);
      if (panel) panel.classList.toggle('hidden');
    });
  });

  // Publish handlers
  container.querySelectorAll('[data-ext-publish]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.extPublish;
      if (!confirm(`Publish extension "${name}" to the Community Hub? This requires a GitHub token.`)) return;
      btn.disabled = true;
      btn.textContent = 'Publishing...';
      try {
        const result = await api.post('/api/hub/publish', { name, kind: 'extension' });
        if (result.status === 'ok') {
          btn.textContent = 'Published!';
          btn.className = 'btn btn-sm text-xs text-emerald-400';
          u.toast?.(`Extension published: ${result.message}`, 'success');
        } else {
          btn.textContent = 'Publish';
          btn.disabled = false;
          u.toast?.(result.error || 'Publish failed', 'error');
        }
      } catch (e) {
        btn.textContent = 'Publish';
        btn.disabled = false;
        u.toast?.(`Error: ${e.message}`, 'error');
      }
    });
  });

  // Community Hub tab handlers
  if (_activeTab === 'hub') {
    const hubStatus = container.querySelector('#hub-status');
    api.get('/api/hub/status').then(s => {
      hubStatus.textContent = s.reachable ? 'Connected' : 'Offline';
      hubStatus.className = `text-xs ${s.reachable ? 'text-emerald-400' : 'text-red-400'}`;
    }).catch(() => {
      hubStatus.textContent = 'Offline';
      hubStatus.className = 'text-xs text-red-400';
    });

    const searchBtn = container.querySelector('#hub-search-btn');
    const searchInput = container.querySelector('#hub-search');
    const kindSelect = container.querySelector('#hub-kind');
    const resultsDiv = container.querySelector('#hub-results');

    const doSearch = async () => {
      const q = searchInput.value.trim();
      const kind = kindSelect.value;
      const endpoint = kind === 'nodes' ? '/api/hub/nodes' : '/api/hub/extensions';
      const params = q ? `?q=${encodeURIComponent(q)}` : '';

      resultsDiv.innerHTML = '<div class="col-span-2 text-center py-4 text-zinc-500 text-sm animate-pulse">Loading...</div>';

      try {
        const data = await api.get(endpoint + params);
        const items = data[kind] || [];
        if (items.length === 0) {
          resultsDiv.innerHTML = '<div class="col-span-2 text-center py-8 text-zinc-500 text-sm">No results found. The Community Hub registry may not be populated yet.</div>';
          return;
        }
        resultsDiv.innerHTML = items.map(item => renderHubCard(item, kind, u)).join('');
        resultsDiv.querySelectorAll('[data-hub-install]').forEach(btn => {
          btn.addEventListener('click', async () => {
            const name = btn.dataset.hubInstall;
            const itemKind = btn.dataset.hubKind;
            btn.disabled = true;
            btn.textContent = 'Installing...';
            try {
              const result = await api.post('/api/hub/install', { name, kind: itemKind });
              if (result.status === 'ok') {
                btn.textContent = 'Installed!';
                btn.className = 'btn btn-sm text-xs text-emerald-400';
              } else {
                btn.textContent = result.error || 'Failed';
                btn.className = 'btn btn-sm text-xs text-red-400';
              }
            } catch (e) {
              btn.textContent = 'Error';
              btn.className = 'btn btn-sm text-xs text-red-400';
            }
          });
        });
      } catch (e) {
        resultsDiv.innerHTML = `<div class="col-span-2 text-center py-4 text-red-400 text-sm">${u.escapeHtml(e.message)}</div>`;
      }
    };

    if (searchBtn) searchBtn.addEventListener('click', doSearch);
    if (searchInput) searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

    doSearch();
  }
}

function renderHubCard(item, kind, u) {
  const cat = item.category || 'utility';
  const icon = CATEGORY_ICONS[cat] || '📦';
  const verified = item.verified ? '<span class="text-[10px] px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 rounded">verified</span>' : '';
  const installKind = kind === 'nodes' ? 'node' : 'extension';

  return `
    <div class="stat-card">
      <div class="flex items-start justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-lg">${icon}</span>
          <div>
            <h3 class="text-sm font-semibold text-white">${u.escapeHtml(item.name || '')}</h3>
            <span class="text-[10px] text-zinc-500">${u.escapeHtml(item.version || '')} · ${u.escapeHtml(item.author || 'unknown')}</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          ${verified}
          <span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-400 rounded">${getCategoryLabel(cat)}</span>
        </div>
      </div>
      <p class="text-xs text-zinc-400 mb-3">${u.escapeHtml(item.description || 'No description')}</p>
      <div class="flex flex-wrap gap-1.5 mb-3">
        ${(item.tags || []).map(tag => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-800 text-zinc-400 rounded">${u.escapeHtml(tag)}</span>`).join('')}
        ${item.stars ? `<span class="text-[10px] text-zinc-500">⭐ ${item.stars}</span>` : ''}
        ${item.downloads ? `<span class="text-[10px] text-zinc-500">📥 ${item.downloads}</span>` : ''}
      </div>
      <div class="flex gap-2 mt-auto pt-2 border-t border-surface-600/30">
        <button data-hub-install="${item.name}" data-hub-kind="${installKind}" class="btn btn-sm btn-primary text-xs">Install</button>
        ${item.repo ? `<a href="${u.escapeHtml(item.repo)}" target="_blank" rel="noopener" class="btn btn-sm btn-ghost text-xs">View Source</a>` : ''}
      </div>
    </div>
  `;
}

function renderExtensionCard(ext, u) {
  const m = ext.manifest || {};
  const cat = m.category || 'utility';
  const icon = CATEGORY_ICONS[cat] || '📦';
  const hasSettings = (m.settings || []).length > 0;
  const isBundled = ext.source === 'bundled';

  const statusColor = ext.error ? 'text-red-400' :
                      ext.loaded ? 'text-emerald-400' :
                      ext.enabled ? 'text-amber-400' : 'text-zinc-500';
  const statusText = ext.error ? 'Error' :
                     ext.loaded ? 'Loaded' :
                     ext.enabled ? 'Enabled (not loaded)' : 'Disabled';

  const tools = ext.tools || [];
  const pages = ext.pages || [];
  const cron = ext.cron_jobs || [];
  const hooks = ext.hooks || [];

  return `
    <div class="stat-card">
      <div class="flex items-start justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-lg">${icon}</span>
          <div>
            <h3 class="text-sm font-semibold text-white">${u.escapeHtml(ext.name)}</h3>
            <span class="text-[10px] text-zinc-500">${u.escapeHtml(m.version || '0.1.0')} · ${u.escapeHtml(m.author || 'unknown')}</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] ${statusColor}">${statusText}</span>
          ${isBundled ? '<span class="text-[10px] px-1.5 py-0.5 bg-ghost-500/20 text-ghost-400 rounded">bundled</span>' : ''}
        </div>
      </div>

      <p class="text-xs text-zinc-400 mb-3">${u.escapeHtml(m.description || 'No description')}</p>

      <!-- Provides summary -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        ${tools.length ? `<span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-300 rounded">${tools.length} tool${tools.length !== 1 ? 's' : ''}</span>` : ''}
        ${pages.length ? `<span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-300 rounded">${pages.length} page${pages.length !== 1 ? 's' : ''}</span>` : ''}
        ${cron.length ? `<span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-300 rounded">${cron.length} cron</span>` : ''}
        ${hooks.length ? `<span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-300 rounded">${hooks.length} hook${hooks.length !== 1 ? 's' : ''}</span>` : ''}
        <span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-400 rounded">${getCategoryLabel(cat)}</span>
      </div>

      ${ext.error ? `<div class="text-xs text-red-400/80 bg-red-500/10 rounded p-2 mb-3 font-mono overflow-auto max-h-24">${u.escapeHtml(ext.error)}</div>` : ''}

      ${tools.length ? `
        <div class="mb-3">
          <div class="text-[10px] text-zinc-500 mb-1">Tools</div>
          <div class="flex flex-wrap gap-1">${tools.map(tn => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-800 text-zinc-300 rounded font-mono">${u.escapeHtml(tn)}</span>`).join('')}</div>
        </div>
      ` : ''}

      <!-- Actions -->
      <div class="flex gap-2 mt-auto pt-2 border-t border-surface-600/30">
        ${ext.enabled
          ? `<button data-ext-action="disable" data-ext-name="${ext.name}" class="btn btn-sm btn-ghost text-xs">Disable</button>`
          : `<button data-ext-action="enable" data-ext-name="${ext.name}" class="btn btn-sm btn-primary text-xs">Enable</button>`
        }
        ${!isBundled ? `<button data-ext-action="uninstall" data-ext-name="${ext.name}" class="btn btn-sm btn-ghost text-xs text-red-400 hover:text-red-300">Uninstall</button>` : ''}
        ${!isBundled ? `<button data-ext-publish="${ext.name}" class="btn btn-sm btn-ghost text-xs">Publish</button>` : ''}
        ${hasSettings ? `<button data-ext-settings="${ext.name}" class="btn btn-sm btn-ghost text-xs ml-auto">Settings</button>` : ''}
      </div>

      ${hasSettings ? `<div id="ext-settings-${ext.name}" class="hidden mt-3 pt-3 border-t border-surface-600/30 text-xs text-zinc-400">Settings panel — coming soon</div>` : ''}
    </div>
  `;
}
