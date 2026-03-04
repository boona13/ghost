/** Models page — multi-provider model browser with fallback chain */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

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
    <h1 class="page-header">${t('models.title')}</h1>
    <p class="page-desc">${t('models.subtitle')}</p>

    <!-- Provider Status Bar -->
    <div class="flex flex-wrap gap-2 mb-4" id="provider-tabs">
      ${providerData.map(p => `
        <button class="provider-tab ${p.id === activeTab ? 'active' : ''}" data-provider="${p.id}">
          <span class="inline-block w-2 h-2 rounded-full mr-1.5 ${p.configured ? 'bg-emerald-400' : 'bg-zinc-600'}"></span>
          ${u.escapeHtml(p.name)}
          ${p.id === primaryProvider ? '<span class="text-[9px] text-ghost-400 ml-1">★</span>' : ''}
        </button>
      `).join('')}
      <button class="provider-tab add-provider-tab" id="btn-add-provider">${t('models.addBtn')}</button>
    </div>

    <!-- Current Model & Chain -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs text-zinc-500 mb-1">${t('models.activeModel')}</div>
            <div class="text-lg font-bold text-white font-mono">${u.escapeHtml(chain.active || current)}</div>
          </div>
          <div class="text-right">
            <div class="text-xs text-zinc-500 mb-1">${t('models.apiKey')}</div>
            <div class="text-sm ${modelsResp.has_api_key ? 'text-emerald-400' : 'text-red-400'}">${modelsResp.has_api_key ? t('models.connectedDot') : t('models.notSet')}</div>
            ${modelsResp.api_key_masked ? `<div class="text-[10px] text-zinc-600 font-mono">${modelsResp.api_key_masked}</div>` : ''}
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="chain-card-header">
          <div>
            <div class="text-xs text-zinc-500 mb-0.5">${t('models.fallbackOrder')}</div>
            <div class="text-[10px] text-zinc-600">${t('models.fallbackOrderDesc')}</div>
          </div>
          <button class="btn btn-primary btn-sm" id="btn-save-provider-order" style="font-size:10px;padding:3px 10px">${t('models.saveOrder')}</button>
        </div>
        <div class="chain-list" id="llm-provider-chain">
          ${(() => {
            const chainProviders = (chain.chain || []).map(e => e.split(':')[0]);
            const allProvIds = providerData.map(p => p.id);
            const seen = new Set();
            const ordered = [];
            for (const pid of chainProviders) { if (!seen.has(pid) && allProvIds.includes(pid)) { seen.add(pid); ordered.push(pid); } }
            for (const pid of allProvIds) { if (!seen.has(pid)) { seen.add(pid); ordered.push(pid); } }
            return ordered.map((pid, i) => {
              const prov = providerData.find(p => p.id === pid);
              const name = prov ? prov.name : pid;
              const configured = prov ? prov.configured : false;
              const isPrimary = pid === primaryProvider;
              const activeEntry = (chain.chain || []).find(e => e.startsWith(pid + ':'));
              const activeModel = activeEntry ? activeEntry.split(':').slice(1).join(':') : '';
              const failed = chain.failures ? Object.entries(chain.failures).find(([k]) => k.startsWith(pid + ':')) : null;
              return '<div class="chain-item' + (configured ? '' : ' disabled') + '" draggable="true" data-provider="' + pid + '">' +
                '<span class="grip">⠿</span>' +
                '<span class="pos">' + (i + 1) + '</span>' +
                '<span class="provider-name" style="text-decoration:none">' +
                  (isPrimary ? '<span style="color:#a78bfa;margin-inline-end:4px">★</span>' : '') +
                  u.escapeHtml(name) +
                  (configured ? '<span style="color:#34d399;margin-inline-start:6px;font-size:9px">●</span>' : '<span style="color:rgba(255,255,255,0.2);margin-inline-start:6px;font-size:9px">○</span>') +
                '</span>' +
                (activeModel ? '<span style="font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + u.escapeHtml(activeModel) + '">' + u.escapeHtml(activeModel) + '</span>' : '') +
                (failed ? '<span style="font-size:9px;color:rgba(239,68,68,0.5)">' + t('common.fail') + '</span>' : '') +
                '</div>';
            }).join('');
          })()}
        </div>
      </div>
    </div>

    <!-- OpenRouter Model Fallback Chain -->
    <div class="stat-card mb-6" id="or-fallback-section">
      <div class="chain-card-header">
        <div>
          <div class="text-xs text-zinc-500 mb-0.5">${t('models.orFallbackChain')}</div>
          <div class="text-[10px] text-zinc-600">${t('models.orFallbackChainDesc')}</div>
        </div>
        <button class="btn btn-primary btn-sm" id="btn-save-or-fallback" style="font-size:10px;padding:3px 10px">${t('common.save')}</button>
      </div>
      <div class="chain-list" id="or-model-chain">
        ${(() => {
          const orChainEntries = (chain.chain || []).filter(e => e.startsWith('openrouter:'));
          const orPrimary = orChainEntries.length > 0
            ? orChainEntries[0].split(':').slice(1).join(':')
            : (providerModels['openrouter'] || cfg.model || current || '');
          const fbModels = cfg.fallback_models || [];
          const allOrModels = [orPrimary, ...fbModels.filter(m => m !== orPrimary)];
          return allOrModels.map((mid, i) => {
            const isPrimary = i === 0;
            const isActive = chain.active && chain.active.startsWith('openrouter:') && chain.active.split(':').slice(1).join(':') === mid;
            const hasFail = chain.failures ? Object.keys(chain.failures).some(k => k === 'openrouter:' + mid) : false;
            return '<div class="chain-item" draggable="true" data-model="' + u.escapeHtml(mid) + '">' +
              '<span class="grip">⠿</span>' +
              '<span class="pos">' + (i + 1) + '</span>' +
              '<span class="provider-name" style="text-decoration:none;font-family:ui-monospace,monospace;font-size:11px">' +
                (isPrimary ? '<span style="color:#a78bfa;margin-inline-end:4px">★</span>' : '') +
                u.escapeHtml(mid) +
                (isActive ? '<span style="color:#34d399;margin-inline-start:6px;font-size:9px">' + t('common.activeDot') + '</span>' : '') +
                (hasFail ? '<span style="color:rgba(239,68,68,0.5);margin-inline-start:6px;font-size:9px">' + t('common.fail') + '</span>' : '') +
              '</span>' +
              (i > 0 ? '<button class="or-remove-model" data-model="' + u.escapeHtml(mid) + '" style="background:none;border:none;color:rgba(255,255,255,0.2);cursor:pointer;font-size:14px;padding:0 4px;line-height:1" title="' + t('common.remove') + '">×</button>' : '') +
              '</div>';
          }).join('');
        })()}
      </div>
      <div class="flex gap-2 mt-3">
        <input id="or-add-model-input" type="text" class="form-input flex-1 font-mono" style="font-size:11px" placeholder="${t('models.addModelPlaceholder')}">
        <button id="btn-or-add-model" class="btn btn-ghost btn-sm" style="font-size:10px">${t('models.addBtn')}</button>
      </div>
    </div>

    <!-- Model Selection -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div>
        <label class="form-label">${t('models.customModelId')}</label>
        <div class="flex gap-2">
          <input id="custom-model" type="text" class="form-input flex-1 font-mono" placeholder="${t('models.modelNamePlaceholder')}" value="${u.escapeHtml(current)}">
          <button id="btn-set-model" class="btn btn-primary">${t('models.set')}</button>
        </div>
      </div>
      <div>
        <label class="form-label">${t('models.orApiKey')}</label>
        <div class="flex gap-2">
          <input id="api-key-input" type="password" class="form-input flex-1 font-mono" placeholder="${t('models.orApiKeyPlaceholder')}">
          <button id="btn-toggle-key" class="btn btn-ghost btn-sm">${t('models.show')}</button>
          <button id="btn-save-key" class="btn btn-secondary">${t('common.save')}</button>
        </div>
      </div>
    </div>

    <!-- Provider Key Management -->
    <div id="provider-keys-section" class="stat-card mb-6 hidden">
      <h3 class="text-sm font-semibold text-white mb-3" id="provider-keys-title">${t('models.manageKeys')}</h3>
      <div id="provider-keys-content"></div>
    </div>

    <!-- Responses Capabilities -->
    <div class="stat-card mb-6" id="responses-capabilities-section">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 class="text-sm font-semibold text-white">${t('models.responsesCapabilities')}</h3>
          <p class="text-xs text-zinc-500 mt-1">${t('models.responsesCapabilitiesDesc')}</p>
          <div class="mt-1"><span class="badge badge-purple">${t('models.appliesGlobally')}</span></div>
        </div>
        <button id="btn-save-responses-capabilities" class="btn btn-primary btn-sm">${t('models.saveCapabilities')}</button>
      </div>
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3 py-2 border-b border-surface-600/30">
          <div>
            <label class="form-label !mb-0">${t('models.enableResponsesSkills')}</label>
            <div class="text-[11px] text-zinc-500">${t('models.enableResponsesSkillsDesc')}</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_responses_skills ? 'on' : ''}" id="toggle-enable-responses-skills" type="button" role="switch" aria-checked="${responsesCapabilities.enable_responses_skills ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div class="flex items-center justify-between gap-3 py-2 border-b border-surface-600/30">
          <div>
            <label class="form-label !mb-0">${t('models.enableHostedShell')}</label>
            <div class="text-[11px] text-zinc-500">${t('models.enableHostedShellDesc')}</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_hosted_shell ? 'on' : ''}" id="toggle-enable-hosted-shell" type="button" role="switch" aria-checked="${responsesCapabilities.enable_hosted_shell ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div class="flex items-center justify-between gap-3 py-2">
          <div>
            <label class="form-label !mb-0">${t('models.enableContainerNetworking')}</label>
            <div class="text-[11px] text-zinc-500">${t('models.enableContainerNetworkingDesc')}</div>
          </div>
          <button class="toggle ${responsesCapabilities.enable_container_networking ? 'on' : ''}" id="toggle-enable-container-networking" type="button" role="switch" aria-checked="${responsesCapabilities.enable_container_networking ? 'true' : 'false'}">
            <span class="toggle-dot"></span>
          </button>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 mb-4">
      <input id="model-search" type="text" class="form-input flex-1" style="min-width:200px" placeholder="${t('models.searchModels')}">
      <select id="model-provider" class="form-input" style="width:150px">
        <option value="">${t('models.allProviders')}</option>
        ${providers.map(p => `<option value="${p}">${p}</option>`).join('')}
      </select>
      <select id="model-tier" class="form-input" style="width:130px">
        <option value="">${t('models.allTiers')}</option>
        ${tiers.map(ti => `<option value="${ti}">${ti}</option>`).join('')}
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
    saveBtn.textContent = t('common.saving');

    try {
      const resp = await api.put('/api/responses-capabilities', payload);
      responsesCapabilities = {
        ...responsesCapabilities,
        ...((resp && resp.responses_capabilities) || {}),
      };
      u.toast(t('models.capabilitiesSaved'));
    } catch (e) {
      u.toast(t('models.failedSaveCapabilities', {error: e.message}), 'error');
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
    u.toast(t('models.modelSetTo', { model: v, provider: activeTab }));
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
    u.toast(t('models.apiKeySaved'));
    keyInput.value = '';
    render(container);
  });

  // ── LLM Provider Chain drag-to-reorder ────────────────────────
  const llmChain = document.getElementById('llm-provider-chain');
  if (llmChain) {
    let dragItem = null;

    llmChain.querySelectorAll('.chain-item').forEach(item => {
      item.addEventListener('dragstart', e => {
        dragItem = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.provider);
      });
      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        llmChain.querySelectorAll('.chain-item').forEach(el => el.classList.remove('drag-over'));
        dragItem = null;
      });
      item.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (dragItem && item !== dragItem) {
          llmChain.querySelectorAll('.chain-item').forEach(el => el.classList.remove('drag-over'));
          item.classList.add('drag-over');
        }
      });
      item.addEventListener('dragleave', () => { item.classList.remove('drag-over'); });
      item.addEventListener('drop', e => {
        e.preventDefault();
        if (!dragItem || item === dragItem) return;
        const items = [...llmChain.querySelectorAll('.chain-item')];
        const fromIdx = items.indexOf(dragItem);
        const toIdx = items.indexOf(item);
        if (fromIdx < toIdx) {
          item.parentNode.insertBefore(dragItem, item.nextSibling);
        } else {
          item.parentNode.insertBefore(dragItem, item);
        }
        llmChain.querySelectorAll('.chain-item').forEach((el, i) => {
          const posEl = el.querySelector('.pos');
          if (posEl) posEl.textContent = i + 1;
        });
      });
    });

    document.getElementById('btn-save-provider-order')?.addEventListener('click', async () => {
      const btn = document.getElementById('btn-save-provider-order');
      const newOrder = [...llmChain.querySelectorAll('.chain-item')].map(el => el.dataset.provider);
      btn.disabled = true;
      btn.textContent = t('common.saving');
      try {
        await api.put('/api/setup/provider-order', { order: newOrder });
        const newPrimary = newOrder[0];
        if (newPrimary !== primaryProvider) {
          await api.put('/api/primary-provider', { provider: newPrimary });
        }
        u.toast(t('models.orderSaved'));
        render(container);
      } catch (e) {
        u.toast(t('common.failedWithError', {error: e.message}), 'error');
        btn.disabled = false;
        btn.textContent = t('models.saveOrder');
      }
    });
  }

  // ── OpenRouter Model Fallback Chain ─────────────────────────────
  const orChain = document.getElementById('or-model-chain');
  if (orChain) {
    let orDragItem = null;

    function attachOrDrag() {
      orChain.querySelectorAll('.chain-item').forEach(item => {
        item.addEventListener('dragstart', e => {
          orDragItem = item;
          item.classList.add('dragging');
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', item.dataset.model);
        });
        item.addEventListener('dragend', () => {
          item.classList.remove('dragging');
          orChain.querySelectorAll('.chain-item').forEach(el => el.classList.remove('drag-over'));
          orDragItem = null;
        });
        item.addEventListener('dragover', e => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          if (orDragItem && item !== orDragItem) {
            orChain.querySelectorAll('.chain-item').forEach(el => el.classList.remove('drag-over'));
            item.classList.add('drag-over');
          }
        });
        item.addEventListener('dragleave', () => { item.classList.remove('drag-over'); });
        item.addEventListener('drop', e => {
          e.preventDefault();
          if (!orDragItem || item === orDragItem) return;
          const items = [...orChain.querySelectorAll('.chain-item')];
          const fromIdx = items.indexOf(orDragItem);
          const toIdx = items.indexOf(item);
          if (fromIdx < toIdx) {
            item.parentNode.insertBefore(orDragItem, item.nextSibling);
          } else {
            item.parentNode.insertBefore(orDragItem, item);
          }
          orChain.querySelectorAll('.chain-item').forEach((el, i) => {
            const posEl = el.querySelector('.pos');
            if (posEl) posEl.textContent = i + 1;
            const star = el.querySelector('.provider-name span[style*="color:#a78bfa"]');
            if (i === 0 && !star) {
              const nameEl = el.querySelector('.provider-name');
              if (nameEl) nameEl.insertAdjacentHTML('afterbegin', '<span style="color:#a78bfa;margin-inline-end:4px">★</span>');
            } else if (i > 0 && star) {
              star.remove();
            }
          });
        });
      });

      orChain.querySelectorAll('.or-remove-model').forEach(btn => {
        btn.addEventListener('click', () => {
          const row = btn.closest('.chain-item');
          if (row) {
            row.remove();
            orChain.querySelectorAll('.chain-item').forEach((el, i) => {
              const posEl = el.querySelector('.pos');
              if (posEl) posEl.textContent = i + 1;
            });
          }
        });
      });
    }

    attachOrDrag();

    document.getElementById('btn-or-add-model')?.addEventListener('click', () => {
      const input = document.getElementById('or-add-model-input');
      const mid = (input?.value || '').trim();
      if (!mid) return;
      const existing = [...orChain.querySelectorAll('.chain-item')].map(el => el.dataset.model);
      if (existing.includes(mid)) { u.toast(t('models.modelAlreadyInChain'), 'error'); return; }
      const idx = existing.length + 1;
      const html = '<div class="chain-item" draggable="true" data-model="' + u.escapeHtml(mid) + '">' +
        '<span class="grip">⠿</span>' +
        '<span class="pos">' + idx + '</span>' +
        '<span class="provider-name" style="text-decoration:none;font-family:ui-monospace,monospace;font-size:11px">' + u.escapeHtml(mid) + '</span>' +
        '<button class="or-remove-model" data-model="' + u.escapeHtml(mid) + '" style="background:none;border:none;color:rgba(255,255,255,0.2);cursor:pointer;font-size:14px;padding:0 4px;line-height:1" title="' + t('common.remove') + '">×</button>' +
        '</div>';
      orChain.insertAdjacentHTML('beforeend', html);
      input.value = '';
      attachOrDrag();
    });

    document.getElementById('or-add-model-input')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); document.getElementById('btn-or-add-model')?.click(); }
    });

    document.getElementById('btn-save-or-fallback')?.addEventListener('click', async () => {
      const btn = document.getElementById('btn-save-or-fallback');
      const models = [...orChain.querySelectorAll('.chain-item')].map(el => el.dataset.model);
      if (models.length === 0) { u.toast(t('models.chainCannotBeEmpty'), 'error'); return; }
      const newPrimary = models[0];
      const newFallbacks = models.slice(1);
      btn.disabled = true;
      btn.textContent = t('common.saving');
      try {
        await api.put('/api/config', { fallback_models: newFallbacks });
        await api.put('/api/models', { model: newPrimary, provider: 'openrouter' });
        u.toast(t('models.orChainSaved'));
        render(container);
      } catch (e) {
        u.toast(t('common.failedWithError', {error: e.message}), 'error');
        btn.disabled = false;
        btn.textContent = t('common.save');
      }
    });
  }
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
    customInput.placeholder = t('models.modelForProvider', {provider: providerId});
  }

  section.classList.remove('hidden');
  const title = document.getElementById('provider-keys-title');
  title.textContent = t('models.configFor', { provider: prov?.name || providerId });
  const content = document.getElementById('provider-keys-content');
  const isPrimary = providerId === primaryProvider;
  const isOpenRouter = providerId === 'openrouter';

  const isOAuth = prov?.auth_type === 'oauth' || prov?.type === 'oauth';

  if (prov?.configured || isOpenRouter) {
    const maskedKey = prov?.masked_key || '';
    const authLabel = isOAuth ? 'OAuth' : (maskedKey || '');
    content.innerHTML = `
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="text-sm text-emerald-400">${t('models.connectedDot')} ${authLabel ? `<span class="text-zinc-500 font-mono text-xs ml-2">${u.escapeHtml(authLabel)}</span>` : ''} ${isPrimary ? '<span class="badge badge-purple ml-2">' + t('models.primary') + '</span>' : ''}</div>
        <div class="flex gap-2 flex-wrap">
          ${!isPrimary ? `<button class="btn btn-primary btn-sm set-primary-btn" data-provider="${providerId}">${t('models.setAsPrimary')}</button>` : ''}
          ${isOAuth ? `<button class="btn btn-secondary btn-sm reauth-btn" data-provider="${providerId}">${t('models.reauthenticate')}</button>` : ''}
          <button class="btn btn-ghost btn-sm test-prov-btn" data-provider="${providerId}">${t('common.test')}</button>
          ${!isOpenRouter ? `<button class="btn btn-ghost btn-sm text-red-400 remove-prov-btn" data-provider="${providerId}">${isOAuth ? t('common.disconnect') : t('common.remove')}</button>` : ''}
        </div>
      </div>
    `;
  } else {
    const connectLabel = isOAuth ? t('models.connectOAuth') : t('common.configure');
    content.innerHTML = `
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <span class="text-sm text-zinc-500">${t('models.notConnected')}</span>
          ${isOAuth
            ? `<button class="btn btn-primary btn-sm reauth-btn" data-provider="${providerId}">${connectLabel}</button>`
            : `<button class="btn btn-primary btn-sm" onclick="window.location.href=window.location.pathname+'#setup'; setTimeout(()=>window.location.reload(),50)">${connectLabel}</button>`
          }
        </div>
        <div class="flex gap-2">
          ${!isPrimary ? `<button class="btn btn-primary btn-sm set-primary-btn" data-provider="${providerId}">${t('models.setAsPrimary')}</button>` : ''}
        </div>
      </div>
    `;
  }

  content.querySelectorAll('.test-prov-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.textContent = t('common.testing');
      const result = await api.post(`/api/providers/${btn.dataset.provider}/test`);
      btn.textContent = t('common.test');
      u.toast(result.ok ? t('models.connectionOK') : (result.error || t('common.failed')), result.ok ? undefined : 'error');
    });
  });

  content.querySelectorAll('.remove-prov-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      const provInfo = providerData.find(p => p.id === pid);
      if (!confirm(t('models.removeConfirm', { provider: provInfo?.name || pid }))) return;
      await api.post(`/api/setup/providers/${pid}/remove`);
      u.toast(`${provInfo?.name || pid} ${(provInfo?.auth_type === 'oauth' || provInfo?.type === 'oauth') ? t('common.disconnecting') : t('models.removed')}`);
      render(container);
    });
  });

  content.querySelectorAll('.set-primary-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = t('common.saving');
      try {
        await api.put('/api/primary-provider', { provider: btn.dataset.provider });
        u.toast(t('models.setPrimarySuccess', { provider: btn.dataset.provider }));
        render(container);
      } catch (e) {
        u.toast(t('common.failedWithError', {error: e.message}), 'error');
        btn.disabled = false;
        btn.textContent = t('models.setAsPrimary');
      }
    });
  });

  content.querySelectorAll('.reauth-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      btn.disabled = true;
      btn.textContent = t('models.startingOAuth');
      try {
        const resp = await api.post('/api/setup/oauth/codex/start');
        if (resp.auth_url) {
          window.open(resp.auth_url, '_blank', 'width=600,height=700');
          btn.textContent = t('models.waitingAuth');
          let attempts = 0;
          const poll = setInterval(async () => {
            attempts++;
            const status = await api.get('/api/setup/oauth/codex/status');
            if (status.authenticated) {
              clearInterval(poll);
              u.toast(t('models.codexConnected'));
              render(container);
            } else if (attempts > 60) {
              clearInterval(poll);
              btn.disabled = false;
              btn.textContent = t('models.reauthenticate');
              u.toast(t('models.oauthTimeout'), 'error');
            }
          }, 2000);
        } else {
          u.toast(resp.error || t('models.oauthStartFailed'), 'error');
          btn.disabled = false;
          btn.textContent = t('models.reauthenticate');
        }
      } catch (e) {
        u.toast(t('models.oauthError', {error: e.message}), 'error');
        btn.disabled = false;
        btn.textContent = t('models.reauthenticate');
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

  count.textContent = models.length + ' ' + t('models.title').toLowerCase();

  if (models.length === 0) {
    grid.innerHTML = '<div class="text-sm text-zinc-600 col-span-3">' + t('models.noModelsMatch') + '</div>';
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
        ${isCurrent ? `<div class="text-[10px] text-ghost-400 mt-1.5 font-medium">${t('models.activeFor', { provider: u.escapeHtml(activeTab) })}</div>` : ''}
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
      u.toast(t('models.modelSetTo', { model: id, provider }));
      render(container);
    });
  });
}
