/** Models page — multi-provider model browser with fallback chain */

let allModels = [];
let providerData = [];
let activeTab = 'openrouter';
let providerModels = {};
let primaryProvider = 'openrouter';
let responsesCapabilities = {
  enable_responses_skills: false,
  enable_hosted_shell: false,
  enable_container_networking: false,
};

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [modelsResp, providersResp, chainResp, primaryResp, configResp, responsesCapsResp] = await Promise.all([
    api.get('/api/models'),
    api.get('/api/providers').catch(() => ({ providers: [] })),
    api.get('/api/fallback-chain').catch(() => ({ chain: [], active: '' })),
    api.get('/api/primary-provider').catch(() => ({ primary_provider: 'openrouter' })),
    api.get('/api/config').catch(() => ({ config: {} })),
    api.get('/api/responses-capabilities').catch(() => ({ responses_capabilities: {} })),
  ]);
  primaryProvider = primaryResp.primary_provider || 'openrouter';
  const cfg = configResp.config || configResp || {};
  providerModels = cfg.provider_models || {};

  allModels = modelsResp.models || [];
  providerData = providersResp.providers || [];
  responsesCapabilities = {
    ...responsesCapabilities,
    ...(responsesCapsResp.responses_capabilities || {}),
  };
  const current = modelsResp.current;
  const chain = chainResp;

  const providers = [...new Set(allModels.map(m => m.provider).filter(Boolean))].sort();
  const tiers = [...new Set(allModels.map(m => m.tier).filter(Boolean))].sort();

  container.innerHTML = `
    <h1 class="page-header">Models</h1>
    <p class="page-desc">Multi-provider model management</p>

    <!-- Provider Status Bar -->
    <div class="flex flex-wrap gap-2 mb-4" id="provider-tabs">
      ${providerData.map(p => `
        <button class="provider-tab ${p.id === activeTab ? 'active' : ''}" data-provider="${p.id}">
          <span class="inline-block w-2 h-2 rounded-full mr-1.5 ${p.configured ? 'bg-emerald-400' : 'bg-zinc-600'}"></span>
          ${u.escapeHtml(p.name)}
          ${p.id === primaryProvider ? '<span class="text-[9px] text-ghost-400 ml-1">★</span>' : ''}
        </button>
      `).join('')}
      <button class="provider-tab add-provider-tab" id="btn-add-provider">+ Add</button>
    </div>

    <!-- Current Model & Chain -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs text-zinc-500 mb-1">Active Model</div>
            <div class="text-lg font-bold text-white font-mono">${u.escapeHtml(chain.active || current)}</div>
          </div>
          <div class="text-right">
            <div class="text-xs text-zinc-500 mb-1">API Key</div>
            <div class="text-sm ${modelsResp.has_api_key ? 'text-emerald-400' : 'text-red-400'}">${modelsResp.has_api_key ? '● Connected' : '○ Not set'}</div>
            ${modelsResp.api_key_masked ? `<div class="text-[10px] text-zinc-600 font-mono">${modelsResp.api_key_masked}</div>` : ''}
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="text-xs text-zinc-500 mb-2">Fallback Chain <span class="text-zinc-600">(★ = primary provider)</span></div>
        <div class="flex flex-wrap gap-1" id="chain-display">
          ${(chain.chain || []).map((entry, i) => {
            const isActive = entry === chain.active;
            const isPrimary = i === 0;
            const failed = chain.failures && chain.failures[entry];
            let color = 'bg-surface-800 text-zinc-400 border-surface-600/30';
            if (isActive) color = 'bg-ghost-900/30 text-ghost-400 border-ghost-500/40';
            else if (failed) color = 'bg-red-900/20 text-red-400/60 border-red-500/20';
            return `
              <div class="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono border ${color}">
                ${isPrimary ? '<span class="text-ghost-400">★</span>' : ''}
                ${u.escapeHtml(entry)}
                ${isActive ? '<span class="text-ghost-400">●</span>' : ''}
                ${failed ? `<span class="text-red-400/50">(${failed}s ago)</span>` : ''}
              </div>
              ${i < (chain.chain || []).length - 1 ? '<span class="text-zinc-600 text-xs">→</span>' : ''}
            `;
          }).join('')}
        </div>
      </div>
    </div>

    <!-- Model Selection -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div>
        <label class="form-label">Custom Model ID</label>
        <div class="flex gap-2">
          <input id="custom-model" type="text" class="form-input flex-1 font-mono" placeholder="model-name" value="${u.escapeHtml(current)}">
          <button id="btn-set-model" class="btn btn-primary">Set</button>
        </div>
      </div>
      <div>
        <label class="form-label">OpenRouter API Key</label>
        <div class="flex gap-2">
          <input id="api-key-input" type="password" class="form-input flex-1 font-mono" placeholder="sk-or-...">
          <button id="btn-toggle-key" class="btn btn-ghost btn-sm">Show</button>
          <button id="btn-save-key" class="btn btn-secondary">Save</button>
        </div>
      </div>
    </div>

    <!-- Provider Key Management -->
    <div id="provider-keys-section" class="stat-card mb-6 hidden">
      <h3 class="text-sm font-semibold text-white mb-3" id="provider-keys-title">Manage Keys</h3>
      <div id="provider-keys-content"></div>
    </div>

    <!-- Responses Capabilities -->
    <div class="stat-card mb-6" id="responses-capabilities-section">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 class="text-sm font-semibold text-white">Responses Capabilities</h3>
          <p class="text-xs text-zinc-500 mt-1">Control advanced responses features for hosted tools and networking.</p>
          <div class="mt-1"><span class="badge badge-purple">Applies globally to OpenAI + OpenAI Codex</span></div>
        </div>
        <button id="btn-save-responses-capabilities" class="btn btn-primary btn-sm">Save Capabilities</button>
      </div>
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3 py-2 border-b border-surface-600/30">
          <div>
            <label class="form-label !mb-0">Enable Responses Skills</label>
            <div class="text-[11px] text-zinc-500">Allow responses-native skills in supported providers.</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_responses_skills ? 'on' : ''}" id="toggle-enable-responses-skills" type="button" role="switch" aria-checked="${responsesCapabilities.enable_responses_skills ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div class="flex items-center justify-between gap-3 py-2 border-b border-surface-600/30">
          <div>
            <label class="form-label !mb-0">Enable Hosted Shell</label>
            <div class="text-[11px] text-zinc-500">Allow shell execution in hosted responses environments.</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_hosted_shell ? 'on' : ''}" id="toggle-enable-hosted-shell" type="button" role="switch" aria-checked="${responsesCapabilities.enable_hosted_shell ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div class="flex items-center justify-between gap-3 py-2">
          <div>
            <label class="form-label !mb-0">Enable Container Networking</label>
            <div class="text-[11px] text-zinc-500">Permit network access in hosted containers (requires Hosted Shell).</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_container_networking ? 'on' : ''}" id="toggle-enable-container-networking" type="button" role="switch" aria-checked="${responsesCapabilities.enable_container_networking ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 mb-4">
      <input id="model-search" type="text" class="form-input flex-1" style="min-width:200px" placeholder="Search models...">
      <select id="model-provider" class="form-input" style="width:150px">
        <option value="">All Providers</option>
        ${providers.map(p => `<option value="${p}">${p}</option>`).join('')}
      </select>
      <select id="model-tier" class="form-input" style="width:130px">
        <option value="">All Tiers</option>
        ${tiers.map(t => `<option value="${t}">${t}</option>`).join('')}
      </select>
    </div>

    <div class="text-xs text-zinc-500 mb-3" id="results-count"></div>
    <div id="models-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"></div>
  `;

  const capsMap = [
    { id: 'toggle-enable-responses-skills', key: 'enable_responses_skills' },
    { id: 'toggle-enable-hosted-shell', key: 'enable_hosted_shell' },
    { id: 'toggle-enable-container-networking', key: 'enable_container_networking' },
  ];

  capsMap.forEach(({ id, key }) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener('click', () => {
      const nextVal = !responsesCapabilities[key];
      responsesCapabilities[key] = nextVal;
      btn.classList.toggle('on', nextVal);
      btn.setAttribute('aria-checked', nextVal ? 'true' : 'false');

      if (key === 'enable_hosted_shell' && !nextVal && responsesCapabilities.enable_container_networking) {
        responsesCapabilities.enable_container_networking = false;
        const netBtn = document.getElementById('toggle-enable-container-networking');
        if (netBtn) {
          netBtn.classList.remove('on');
          netBtn.setAttribute('aria-checked', 'false');
        }
      }
    });
  });

  document.getElementById('btn-save-responses-capabilities')?.addEventListener('click', async (evt) => {
    const saveBtn = evt.currentTarget;
    const payload = {
      responses_capabilities: {
        enable_responses_skills: !!responsesCapabilities.enable_responses_skills,
        enable_hosted_shell: !!responsesCapabilities.enable_hosted_shell,
        enable_container_networking: !!responsesCapabilities.enable_container_networking,
      },
    };

    saveBtn.disabled = true;
    const oldText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';

    try {
      const resp = await api.put('/api/responses-capabilities', payload);
      responsesCapabilities = {
        ...responsesCapabilities,
        ...((resp && resp.responses_capabilities) || {}),
      };
      u.toast('Responses capabilities saved');
    } catch (e) {
      u.toast('Failed to save capabilities: ' + e.message, 'error');
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = oldText;
    }
  });

  // Provider tabs
  container.querySelectorAll('.provider-tab:not(.add-provider-tab)').forEach(tab => {
    tab.addEventListener('click', async () => {
      activeTab = tab.dataset.provider;
      container.querySelectorAll('.provider-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      await loadProviderModels(activeTab, current, container, u, api);
    });
  });

  // Load models for the active tab (persists across re-renders)
  await loadProviderModels(activeTab, current, container, u, api);

  // Add provider button
  document.getElementById('btn-add-provider')?.addEventListener('click', () => {
    window.location.href = window.location.pathname + '#setup';
    setTimeout(() => window.location.reload(), 50);
  });

  // Filters
  document.getElementById('model-search')?.addEventListener('input', () => applyFilters(current, container, u, api));
  document.getElementById('model-provider')?.addEventListener('change', () => applyFilters(current, container, u, api));
  document.getElementById('model-tier')?.addEventListener('change', () => applyFilters(current, container, u, api));

  // Set model (provider-aware)
  document.getElementById('btn-set-model')?.addEventListener('click', async () => {
    const v = document.getElementById('custom-model').value.trim();
    if (!v) return;
    await api.put('/api/models', { model: v, provider: activeTab });
    providerModels[activeTab] = v;
    u.toast(`Model set to ${v} for ${activeTab}`);
    render(container);
  });

  // API key management
  const keyInput = document.getElementById('api-key-input');
  document.getElementById('btn-toggle-key')?.addEventListener('click', () => {
    keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
  });

  document.getElementById('btn-save-key')?.addEventListener('click', async () => {
    const k = keyInput.value.trim();
    if (!k) return;
    await api.put('/api/models', { api_key: k });
    u.toast('API key saved');
    keyInput.value = '';
    render(container);
  });
}

async function loadProviderModels(providerId, current, container, u, api) {
  const section = document.getElementById('provider-keys-section');
  const prov = providerData.find(p => p.id === providerId);

  const customInput = document.getElementById('custom-model');
  if (customInput) {
    const tabModel = providerId === 'openrouter'
      ? (providerModels['openrouter'] || current)
      : (providerModels[providerId] || '');
    customInput.value = tabModel;
    customInput.placeholder = `Model for ${providerId}`;
  }

  section.classList.remove('hidden');
  const title = document.getElementById('provider-keys-title');
  title.textContent = `${prov?.name || providerId} Configuration`;
  const content = document.getElementById('provider-keys-content');
  const isPrimary = providerId === primaryProvider;
  const isOpenRouter = providerId === 'openrouter';

  const isOAuth = prov?.auth_type === 'oauth' || prov?.type === 'oauth';

  if (prov?.configured || isOpenRouter) {
    const maskedKey = prov?.masked_key || '';
    const authLabel = isOAuth ? 'OAuth' : (maskedKey || '');
    content.innerHTML = `
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="text-sm text-emerald-400">● Connected ${authLabel ? `<span class="text-zinc-500 font-mono text-xs ml-2">${u.escapeHtml(authLabel)}</span>` : ''} ${isPrimary ? '<span class="badge badge-purple ml-2">Primary</span>' : ''}</div>
        <div class="flex gap-2 flex-wrap">
          ${!isPrimary ? `<button class="btn btn-primary btn-sm set-primary-btn" data-provider="${providerId}">Set as Primary</button>` : ''}
          ${isOAuth ? `<button class="btn btn-secondary btn-sm reauth-btn" data-provider="${providerId}">Re-authenticate</button>` : ''}
          <button class="btn btn-ghost btn-sm test-prov-btn" data-provider="${providerId}">Test</button>
          ${!isOpenRouter ? `<button class="btn btn-ghost btn-sm text-red-400 remove-prov-btn" data-provider="${providerId}">${isOAuth ? 'Disconnect' : 'Remove'}</button>` : ''}
        </div>
      </div>
    `;
  } else {
    const connectLabel = isOAuth ? 'Connect with OAuth' : 'Configure';
    content.innerHTML = `
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <span class="text-sm text-zinc-500">Not connected</span>
          ${isOAuth
            ? `<button class="btn btn-primary btn-sm reauth-btn" data-provider="${providerId}">${connectLabel}</button>`
            : `<button class="btn btn-primary btn-sm" onclick="window.location.href=window.location.pathname+'#setup'; setTimeout(()=>window.location.reload(),50)">${connectLabel}</button>`
          }
        </div>
        <div class="flex gap-2">
          ${!isPrimary ? `<button class="btn btn-primary btn-sm set-primary-btn" data-provider="${providerId}">Set as Primary</button>` : ''}
        </div>
      </div>
    `;
  }

  content.querySelectorAll('.test-prov-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.textContent = 'Testing...';
      const result = await api.post(`/api/providers/${btn.dataset.provider}/test`);
      btn.textContent = 'Test';
      u.toast(result.ok ? 'Connection OK' : (result.error || 'Failed'), result.ok ? undefined : 'error');
    });
  });

  content.querySelectorAll('.remove-prov-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      const provInfo = providerData.find(p => p.id === pid);
      const isOAuthProv = provInfo?.auth_type === 'oauth' || provInfo?.type === 'oauth';
      const action = isOAuthProv ? 'Disconnect' : 'Remove';
      if (!confirm(`${action} ${provInfo?.name || pid}? This will clear its credentials.`)) return;
      await api.post(`/api/setup/providers/${pid}/remove`);
      u.toast(`${provInfo?.name || pid} ${isOAuthProv ? 'disconnected' : 'removed'}`);
      render(container);
    });
  });

  content.querySelectorAll('.set-primary-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Setting...';
      try {
        await api.put('/api/primary-provider', { provider: btn.dataset.provider });
        u.toast(`${btn.dataset.provider} set as primary provider`);
        render(container);
      } catch (e) {
        u.toast('Failed: ' + e.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Set as Primary';
      }
    });
  });

  content.querySelectorAll('.reauth-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      btn.disabled = true;
      btn.textContent = 'Starting OAuth...';
      try {
        const resp = await api.post('/api/setup/oauth/codex/start');
        if (resp.auth_url) {
          window.open(resp.auth_url, '_blank', 'width=600,height=700');
          btn.textContent = 'Waiting for auth...';
          let attempts = 0;
          const poll = setInterval(async () => {
            attempts++;
            const status = await api.get('/api/setup/oauth/codex/status');
            if (status.authenticated) {
              clearInterval(poll);
              u.toast('OpenAI Codex connected successfully!');
              render(container);
            } else if (attempts > 60) {
              clearInterval(poll);
              btn.disabled = false;
              btn.textContent = 'Re-authenticate';
              u.toast('OAuth timed out — try again', 'error');
            }
          }, 2000);
        } else {
          u.toast(resp.error || 'Failed to start OAuth', 'error');
          btn.disabled = false;
          btn.textContent = 'Re-authenticate';
        }
      } catch (e) {
        u.toast('OAuth error: ' + e.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Re-authenticate';
      }
    });
  });

  if (!isOpenRouter) {
    try {
      const resp = await api.get(`/api/providers/${providerId}/models`);
      const models = resp.models || [];
      if (models.length > 0) {
        renderModels(models, current, container, u, api);
        return;
      }
    } catch {}
  }

  const filtered = providerId === 'openrouter' ? allModels : allModels.filter(m => (m.source || 'openrouter') === providerId);
  renderModels(filtered, current, container, u, api);
}

function applyFilters(current, container, u, api) {
  const q = (document.getElementById('model-search').value || '').toLowerCase().trim();
  const provider = document.getElementById('model-provider').value;
  const tier = document.getElementById('model-tier').value;

  let filtered = allModels;
  if (q) {
    filtered = filtered.filter(m => {
      const hay = (m.id + ' ' + m.name + ' ' + m.provider + ' ' + m.description).toLowerCase();
      return hay.includes(q);
    });
  }
  if (provider) filtered = filtered.filter(m => m.provider === provider);
  if (tier) filtered = filtered.filter(m => m.tier === tier);

  renderModels(filtered, current, container, u, api);
}

function renderModels(models, current, container, u, api) {
  const grid = document.getElementById('models-grid');
  const count = document.getElementById('results-count');
  if (!grid) return;

  count.textContent = models.length + ' models';

  if (models.length === 0) {
    grid.innerHTML = '<div class="text-sm text-zinc-600 col-span-3">No models match filters</div>';
    return;
  }

  const activeModel = activeTab === 'openrouter'
    ? current
    : (providerModels[activeTab] || '');

  const tierColors = { free: 'green', fast: 'blue', standard: 'purple', premium: 'yellow', reasoning: 'red' };
  const sourceColors = {
    openrouter: 'purple', openai: 'blue', 'openai-codex': 'green',
    anthropic: 'yellow', google: 'blue', deepseek: 'blue', ollama: 'green',
    xai: 'red',
  };

  grid.innerHTML = models.map(m => {
    const isCurrent = m.id === activeModel;
    const pIn = m.pricing?.prompt_per_m;
    const pOut = m.pricing?.completion_per_m;
    const ctx = m.context_length;
    const ctxLabel = ctx >= 1000000 ? (ctx / 1000000).toFixed(1) + 'M' : ctx >= 1000 ? Math.round(ctx / 1000) + 'K' : ctx || '';
    const source = m.source || 'openrouter';

    return `
      <div class="model-card ${isCurrent ? 'selected' : ''}" data-model-id="${m.id}" data-model-source="${source}">
        <div class="flex items-center justify-between mb-1">
          <span class="font-medium text-sm text-white truncate" title="${u.escapeHtml(m.id)}">${u.escapeHtml(m.name)}</span>
          <div class="flex gap-1 flex-shrink-0 ml-2">
            <span class="badge badge-${sourceColors[source] || 'zinc'} text-[9px]">${source}</span>
            <span class="badge badge-${tierColors[m.tier] || 'zinc'}">${m.tier}</span>
          </div>
        </div>
        <div class="text-[11px] font-mono text-zinc-500 mb-2 truncate">${u.escapeHtml(m.id)}</div>
        <div class="flex items-center gap-3 text-[10px] text-zinc-500">
          <span class="text-zinc-400">${u.escapeHtml(m.provider)}</span>
          ${ctxLabel ? `<span>${ctxLabel} ctx</span>` : ''}
          ${pIn !== undefined && pIn > 0 ? `<span>$${pIn}/M in</span>` : ''}
          ${pOut !== undefined && pOut > 0 ? `<span>$${pOut}/M out</span>` : ''}
        </div>
        ${isCurrent ? `<div class="text-[10px] text-ghost-400 mt-1.5 font-medium">● Active for ${u.escapeHtml(activeTab)}</div>` : ''}
      </div>
    `;
  }).join('');

  grid.querySelectorAll('.model-card').forEach(card => {
    card.addEventListener('click', async () => {
      const id = card.dataset.modelId;
      const source = card.dataset.modelSource || activeTab;
      const provider = activeTab !== 'openrouter' ? activeTab : (source !== 'openrouter' ? source : 'openrouter');

      await api.put('/api/models', { model: id, provider });
      providerModels[provider] = id;
      u.toast(`${id} set for ${provider}`);
      render(container);
    });
  });
}
