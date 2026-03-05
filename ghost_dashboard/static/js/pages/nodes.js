/** GhostNodes management page — browse, install, enable/disable AI nodes + GPU status */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

const CATEGORY_ICONS = {
  image_generation: '🎨',
  video: '🎬',
  audio: '🎵',
  vision: '👁',
  llm: '🧠',
  '3d': '📐',
  data: '📊',
  utility: '🔧',
};

function getCategoryLabel(cat) {
  const key = 'nodes.cat_' + cat;
  const val = t(key);
  return val !== key ? val : cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, ' ');
}

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let nodesData, gpuData;
  try {
    [nodesData, gpuData] = await Promise.all([
      api.get('/api/nodes'),
      api.get('/api/gpu/status'),
    ]);
  } catch (e) {
    container.innerHTML = `<div class="text-red-400 p-4">${t('nodes.loadError')}: ${u.escapeHtml(e.message)}</div>`;
    return;
  }

  const nodes = nodesData.nodes || [];
  const categories = nodesData.categories || {};
  const gpu = gpuData.device || {};
  const loadedModels = gpuData.loaded_models || [];

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('nodes.title')}</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-green">${nodes.filter(n => n.loaded).length} ${t('nodes.loaded')}</span>
        <span class="badge badge-zinc">${nodes.length} ${t('nodes.installed')}</span>
      </div>
    </div>
    <p class="page-desc">${t('nodes.subtitle')}</p>

    <!-- GPU Status Card -->
    <div class="stat-card mb-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-white">${t('nodes.gpuStatus')}</h2>
        <span class="text-xs px-2 py-0.5 rounded-full ${gpu.has_cuda ? 'bg-emerald-500/20 text-emerald-400' : gpu.has_mlx ? 'bg-purple-500/20 text-purple-400' : gpu.has_mps ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-700 text-zinc-400'}">
          ${gpu.has_cuda ? t('nodes.gpuCuda') + ': ' + u.escapeHtml(gpu.cuda_device_name || 'GPU') : gpu.has_mlx ? t('nodes.gpuMlx') + ' v' + u.escapeHtml(gpu.mlx_version || '') : gpu.has_mps ? t('nodes.gpuMps') : t('nodes.gpuCpuOnly')}
        </span>
      </div>
      ${gpuData.budget_gb > 0 ? `
        <div class="mb-2">
          <div class="flex justify-between text-xs text-zinc-400 mb-1">
            <span>${gpu.has_cuda ? t('nodes.vramUsage') : t('nodes.memoryUsage')}</span>
            <span>${gpuData.used_gb?.toFixed(1) || 0} / ${gpuData.budget_gb?.toFixed(1) || 0} GB${gpu.unified_memory_gb ? ` (${t('nodes.unified')})` : ''}</span>
          </div>
          <div class="w-full bg-surface-800 rounded-full h-2" role="progressbar" aria-valuenow="${gpuData.used_gb?.toFixed(1) || 0}" aria-valuemin="0" aria-valuemax="${gpuData.budget_gb?.toFixed(1) || 0}" aria-label="${gpu.has_cuda ? t('nodes.vramUsage') : t('nodes.memoryUsage')}">
            <div class="${(gpuData.used_gb / gpuData.budget_gb) > 0.85 ? 'bg-red-500' : (gpuData.used_gb / gpuData.budget_gb) > 0.65 ? 'bg-amber-500' : 'bg-ghost-500'} h-2 rounded-full transition-all" style="width: ${gpuData.budget_gb ? Math.min(100, (gpuData.used_gb / gpuData.budget_gb) * 100) : 0}%"></div>
          </div>
        </div>
      ` : ''}
      ${loadedModels.length > 0 ? `
        <div class="mt-3">
          <div class="text-xs text-zinc-500 mb-2">${t('nodes.loadedModels')}</div>
          <div class="space-y-1">
            ${loadedModels.map(m => `
              <div class="flex items-center justify-between bg-surface-800 rounded px-3 py-1.5">
                <span class="text-xs text-zinc-300 font-mono">${u.escapeHtml(m.model_id)}</span>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-zinc-500">${m.vram_gb?.toFixed(1) || '?'} GB</span>
                  <span class="text-xs text-zinc-600">${m.device}</span>
                  <button class="text-xs text-red-400 hover:text-red-300 unload-btn" data-model="${u.escapeHtml(m.model_id)}" aria-label="${t('nodes.unload')} ${u.escapeHtml(m.model_id)}">${t('nodes.unload')}</button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
    </div>

    <!-- Category Filter -->
    <div class="flex gap-2 mb-6 flex-wrap" role="tablist" aria-label="${t('nodes.categoryFilter')}">
      <button class="node-cat-btn active px-3 py-1.5 text-xs rounded-full bg-ghost-600 text-white" data-cat="all" role="tab" aria-selected="true">${t('common.all')} (${nodes.length})</button>
      ${Object.entries(categories).map(([cat, count]) => `
        <button class="node-cat-btn px-3 py-1.5 text-xs rounded-full bg-surface-700 text-zinc-400 hover:bg-surface-600" data-cat="${cat}" role="tab" aria-selected="false">
          <span aria-hidden="true">${CATEGORY_ICONS[cat] || '📦'}</span> ${getCategoryLabel(cat)} (${count})
        </button>
      `).join('')}
    </div>

    <!-- Nodes Grid -->
    <div id="nodes-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      ${nodes.length === 0 ? `
        <div class="col-span-full text-center py-12 text-zinc-500">
          <div class="text-4xl mb-3">🧩</div>
          <div>${t('nodes.empty')}</div>
          <div class="text-xs mt-1">${t('nodes.emptyHint')}</div>
        </div>
      ` : nodes.map(n => renderNodeCard(n, u)).join('')}
    </div>

    <!-- ComfyUI Workflow Import -->
    <div class="mt-8 stat-card" id="comfyui-section">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-white">${t('nodes.comfyTitle')}</h2>
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400">ComfyUI</span>
      </div>
      <p class="text-xs text-zinc-400 mb-4">${t('nodes.comfyDesc')}</p>

      <div class="border-2 border-dashed border-surface-600 rounded-lg p-6 text-center hover:border-ghost-500/40 transition-colors cursor-pointer" id="comfy-dropzone">
        <div class="text-2xl mb-2">📂</div>
        <div class="text-sm text-zinc-300 mb-1">${t('nodes.comfyDrop')}</div>
        <div class="text-xs text-zinc-500">${t('nodes.comfyDropHint')}</div>
        <input type="file" id="comfy-file-input" accept=".json" class="hidden">
      </div>

      <div id="comfy-analysis" class="hidden mt-4">
        <div class="bg-surface-800 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <span class="text-sm font-semibold text-white" id="comfy-wf-name">${t('nodes.comfyAnalysis')}</span>
            <span id="comfy-native-badge" class="text-[10px] px-2 py-0.5 rounded-full"></span>
          </div>
          <div class="grid grid-cols-2 gap-3 text-xs mb-3">
            <div><span class="text-zinc-500">${t('nodes.comfyNodes')}:</span> <span id="comfy-node-count" class="text-zinc-300"></span></div>
            <div><span class="text-zinc-500">${t('nodes.comfyModels')}:</span> <span id="comfy-model-count" class="text-zinc-300"></span></div>
            <div><span class="text-zinc-500">${t('nodes.comfyInputs')}:</span> <span id="comfy-input-count" class="text-zinc-300"></span></div>
            <div><span class="text-zinc-500">${t('nodes.comfyOutputs')}:</span> <span id="comfy-output-count" class="text-zinc-300"></span></div>
          </div>
          <div id="comfy-models-list" class="mb-3 hidden">
            <div class="text-xs text-zinc-500 mb-1">${t('nodes.comfyRequiredModels')}:</div>
            <div id="comfy-models-items" class="flex flex-wrap gap-1"></div>
          </div>
          <div id="comfy-missing" class="mb-3 hidden">
            <div class="text-xs text-amber-400 mb-1">${t('nodes.comfyMissing')}:</div>
            <div id="comfy-missing-items" class="text-xs text-zinc-400"></div>
          </div>
          <div class="flex gap-3 items-end mt-4">
            <div class="flex-1">
              <label class="text-xs text-zinc-400 mb-1 block">${t('nodes.comfyNodeName')}</label>
              <input id="comfy-node-name" type="text" class="form-input w-full" placeholder="my-workflow">
            </div>
            <div class="flex-1">
              <label class="text-xs text-zinc-400 mb-1 block">${t('common.description')}</label>
              <input id="comfy-node-desc" type="text" class="form-input w-full" placeholder="${t('nodes.comfyDescPlaceholder')}">
            </div>
            <button id="comfy-import-btn" class="btn btn-primary btn-sm whitespace-nowrap">${t('nodes.comfyImport')}</button>
          </div>
          <div id="comfy-import-status" class="mt-2 text-xs hidden"></div>
        </div>
      </div>
    </div>

    <!-- Install Section -->
    <div class="mt-6 stat-card">
      <h2 class="text-sm font-semibold text-white mb-3">${t('nodes.installNode')}</h2>
      <div class="flex gap-3">
        <input id="install-source" type="text" class="form-input flex-1" placeholder="${t('nodes.installPlaceholder')}" aria-label="${t('nodes.installPlaceholder')}">
        <button id="install-btn" class="btn btn-primary btn-sm">${t('nodes.install')}</button>
      </div>
      <div id="install-status" class="mt-2 text-xs text-zinc-500 hidden"></div>
    </div>
  `;

  container.querySelectorAll('.unload-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const modelId = btn.dataset.model;
      btn.disabled = true;
      btn.textContent = t('nodes.unloading');
      try {
        await api.post('/api/gpu/unload', { model_id: modelId });
        u.toast(t('nodes.unloaded', { name: modelId }), 'success');
        render(container);
      } catch (e) {
        u.toast(e.message || t('nodes.unloadFailed'), 'error');
        btn.disabled = false;
        btn.textContent = t('nodes.unload');
      }
    });
  });

  container.querySelectorAll('.node-toggle-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.node;
      const action = btn.dataset.action;
      btn.disabled = true;
      btn.textContent = action === 'enable' ? t('nodes.enabling') : t('nodes.disabling');
      try {
        const result = await api.post(`/api/nodes/${name}/${action}`);
        if (result.ok) {
          u.toast(action === 'enable' ? t('nodes.statusEnabled') : t('nodes.statusDisabled'), 'success');
        } else {
          u.toast(result.error || t('common.error'), 'error');
        }
        render(container);
      } catch (e) {
        u.toast(e.message || t('common.error'), 'error');
        btn.disabled = false;
        btn.textContent = action === 'enable' ? t('nodes.enable') : t('nodes.disable');
      }
    });
  });

  container.querySelectorAll('.node-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.node-cat-btn').forEach(b => {
        b.classList.remove('active', 'bg-ghost-600', 'text-white');
        b.classList.add('bg-surface-700', 'text-zinc-400');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active', 'bg-ghost-600', 'text-white');
      btn.classList.remove('bg-surface-700', 'text-zinc-400');
      btn.setAttribute('aria-selected', 'true');

      const cat = btn.dataset.cat;
      container.querySelectorAll('.node-card').forEach(card => {
        const visible = cat === 'all' || card.dataset.category === cat;
        card.style.display = visible ? '' : 'none';
        card.setAttribute('aria-hidden', !visible);
      });
    });
  });

  // ── ComfyUI workflow import handlers ───────────────────────────
  const dropzone = container.querySelector('#comfy-dropzone');
  const fileInput = container.querySelector('#comfy-file-input');
  const analysisPanel = container.querySelector('#comfy-analysis');
  let _pendingWorkflow = null;

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('border-ghost-500/60'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('border-ghost-500/60'));
    dropzone.addEventListener('drop', e => {
      e.preventDefault();
      dropzone.classList.remove('border-ghost-500/60');
      const file = e.dataTransfer?.files?.[0];
      if (file) handleComfyFile(file);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files?.[0]) handleComfyFile(fileInput.files[0]);
    });
  }

  async function handleComfyFile(file) {
    try {
      const text = await file.text();
      const workflow = JSON.parse(text);
      const resp = await api.post('/api/comfyui/analyze', { workflow });
      if (!resp.ok) { u.toast(resp.error || t('common.error'), 'error'); return; }
      _pendingWorkflow = workflow;
      showAnalysis(resp.analysis, file.name);
    } catch (e) {
      u.toast(e.message || t('nodes.comfyInvalidJson'), 'error');
    }
  }

  function showAnalysis(a, filename) {
    if (!analysisPanel) return;
    analysisPanel.classList.remove('hidden');
    container.querySelector('#comfy-wf-name').textContent = filename;
    container.querySelector('#comfy-node-count').textContent = a.node_count;
    container.querySelector('#comfy-model-count').textContent = a.models_needed?.length || 0;
    container.querySelector('#comfy-input-count').textContent = a.input_nodes?.length || 0;
    container.querySelector('#comfy-output-count').textContent = a.output_nodes?.length || 0;

    const badge = container.querySelector('#comfy-native-badge');
    if (a.native_coverage) {
      badge.textContent = t('nodes.comfyNative');
      badge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400';
    } else {
      badge.textContent = t('nodes.comfyNeedsComfy');
      badge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400';
    }

    const modelsList = container.querySelector('#comfy-models-list');
    const modelsItems = container.querySelector('#comfy-models-items');
    if (a.models_needed?.length) {
      modelsList.classList.remove('hidden');
      modelsItems.innerHTML = a.models_needed.map(m =>
        `<span class="text-[10px] px-2 py-0.5 bg-surface-700 text-zinc-300 rounded font-mono">${u.escapeHtml(m.filename)}</span>`
      ).join('');
    } else {
      modelsList.classList.add('hidden');
    }

    const missingEl = container.querySelector('#comfy-missing');
    const missingItems = container.querySelector('#comfy-missing-items');
    if (a.missing_native?.length) {
      missingEl.classList.remove('hidden');
      missingItems.textContent = a.missing_native.join(', ');
    } else {
      missingEl.classList.add('hidden');
    }

    const nameInput = container.querySelector('#comfy-node-name');
    if (nameInput && !nameInput.value) {
      nameInput.value = filename.replace(/\.json$/i, '').replace(/[^a-zA-Z0-9-]/g, '-').toLowerCase();
    }
  }

  const importBtn = container.querySelector('#comfy-import-btn');
  const importStatus = container.querySelector('#comfy-import-status');
  if (importBtn) {
    importBtn.addEventListener('click', async () => {
      const nodeName = container.querySelector('#comfy-node-name')?.value?.trim();
      const nodeDesc = container.querySelector('#comfy-node-desc')?.value?.trim();
      if (!_pendingWorkflow) { u.toast(t('nodes.comfyUploadFirst'), 'error'); return; }
      if (!nodeName) { u.toast(t('nodes.comfyNameRequired'), 'error'); return; }

      importBtn.disabled = true;
      importBtn.textContent = t('nodes.comfyImporting');
      if (importStatus) { importStatus.classList.remove('hidden'); importStatus.textContent = t('nodes.comfyImporting'); importStatus.className = 'mt-2 text-xs text-zinc-400'; }

      try {
        const resp = await api.post('/api/comfyui/import', {
          workflow: _pendingWorkflow,
          node_name: nodeName,
          description: nodeDesc || '',
        });
        if (resp.ok) {
          u.toast(t('nodes.comfyImportSuccess', { name: nodeName }), 'success');
          if (importStatus) { importStatus.textContent = t('nodes.comfyImportSuccess', { name: nodeName }); importStatus.className = 'mt-2 text-xs text-emerald-400'; }
          setTimeout(() => render(container), 1500);
        } else {
          u.toast(resp.error || t('common.error'), 'error');
          if (importStatus) { importStatus.textContent = resp.error; importStatus.className = 'mt-2 text-xs text-red-400'; }
        }
      } catch (e) {
        u.toast(e.message, 'error');
        if (importStatus) { importStatus.textContent = e.message; importStatus.className = 'mt-2 text-xs text-red-400'; }
      }
      importBtn.disabled = false;
      importBtn.textContent = t('nodes.comfyImport');
    });
  }

  const installBtn = container.querySelector('#install-btn');
  const installInput = container.querySelector('#install-source');
  const installStatus = container.querySelector('#install-status');
  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      const source = installInput.value.trim();
      if (!source) return;
      installBtn.disabled = true;
      installBtn.textContent = t('nodes.installing');
      installInput.disabled = true;
      if (installStatus) {
        installStatus.classList.remove('hidden');
        installStatus.textContent = source.includes('github') ? t('nodes.installProgress') : t('nodes.installing');
      }
      try {
        const result = await api.post('/api/nodes/install', { source });
        if (result.status === 'ok') {
          u.toast(t('nodes.installSuccess', { name: result.name }), 'success');
          render(container);
        } else {
          u.toast(result.error || t('nodes.installFailed'), 'error');
        }
      } catch (e) {
        u.toast(e.message, 'error');
      }
      installBtn.disabled = false;
      installBtn.textContent = t('nodes.install');
      installInput.disabled = false;
      if (installStatus) installStatus.classList.add('hidden');
    });
  }
}

function renderNodeCard(node, u) {
  const m = node.manifest || {};
  const cat = m.category || 'utility';
  const icon = CATEGORY_ICONS[cat] || '📦';
  const isLoaded = node.loaded;
  const isEnabled = node.enabled;
  const hasError = !!node.error;

  const statusColor = hasError ? 'text-red-400' : isLoaded ? 'text-emerald-400' : isEnabled ? 'text-yellow-400' : 'text-zinc-500';
  const statusText = hasError ? t('nodes.statusError') : isLoaded ? t('nodes.statusLoaded') : isEnabled ? t('nodes.statusEnabled') : t('nodes.statusDisabled');
  const statusDot = hasError ? 'bg-red-400' : isLoaded ? 'bg-emerald-400' : isEnabled ? 'bg-yellow-400' : 'bg-zinc-600';

  return `
    <div class="node-card stat-card hover:border-ghost-500/30 transition-colors" data-category="${cat}">
      <div class="flex items-start justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-lg" aria-hidden="true">${icon}</span>
          <div>
            <div class="text-sm font-semibold text-white truncate max-w-[160px]" title="${u.escapeHtml(node.name)}">${u.escapeHtml(node.name)}</div>
            <div class="text-xs text-zinc-500">${u.escapeHtml(m.version || '?')} · ${u.escapeHtml(m.author || t('common.unknown'))}</div>
          </div>
        </div>
        <div class="flex items-center gap-1.5" title="${statusText}">
          <span class="w-2 h-2 rounded-full ${statusDot}" aria-hidden="true"></span>
          <span class="text-xs ${statusColor}" role="status">${statusText}</span>
        </div>
      </div>
      <p class="text-xs text-zinc-400 mb-3 line-clamp-2">${u.escapeHtml(m.description || '')}</p>
      <div class="flex items-center justify-between">
        <div class="flex gap-1 flex-wrap">
          ${(m.tags || []).slice(0, 3).map(tag => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-zinc-500 rounded">${u.escapeHtml(tag)}</span>`).join('')}
        </div>
        <div class="flex gap-1">
          ${m.cloud_provider ? `<span class="text-[10px] px-1.5 py-0.5 bg-sky-500/20 text-sky-400 rounded">☁️ Cloud</span>` : ''}
          ${m.requires_gpu ? `<span class="text-[10px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded">${t('nodes.badgeGpu')}</span>` : ''}
          ${node.source === 'bundled' ? `<span class="text-[10px] px-1.5 py-0.5 bg-ghost-500/20 text-ghost-400 rounded">${t('nodes.badgeBundled')}</span>` : ''}
        </div>
      </div>
      ${node.tools?.length ? `<div class="mt-2 text-[10px] text-zinc-600 truncate" title="${node.tools.map(tool => u.escapeHtml(tool)).join(', ')}">${t('nodes.tools')}: ${node.tools.map(tool => u.escapeHtml(tool)).join(', ')}</div>` : ''}
      ${hasError ? `<div class="mt-2 text-[10px] text-red-400/70 truncate cursor-help" title="${u.escapeHtml(node.error)}">${u.escapeHtml(node.error)}</div>` : ''}
      <div class="mt-3 flex gap-2">
        ${isEnabled
          ? `<button class="node-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-red-500/20 hover:text-red-400 transition-colors" data-node="${u.escapeHtml(node.name)}" data-action="disable">${t('nodes.disable')}</button>`
          : `<button class="node-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-emerald-500/20 hover:text-emerald-400 transition-colors" data-node="${u.escapeHtml(node.name)}" data-action="enable">${t('nodes.enable')}</button>`
        }
        ${hasError ? `<button class="node-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-amber-500/20 hover:text-amber-400 transition-colors" data-node="${u.escapeHtml(node.name)}" data-action="enable">${t('common.retry')}</button>` : ''}
      </div>
    </div>
  `;
}
