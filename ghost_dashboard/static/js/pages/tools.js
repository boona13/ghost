/** Ghost Tools management page — browse, configure, enable/disable, and delete LLM tools */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

const CATEGORY_ICONS = {
  utility: '🔧', data: '📊', llm: '🧠', media: '🎨',
  integration: '🔗', automation: '⚙️', security: '🔒',
};

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let data;
  try {
    data = await api.get('/api/tools');
  } catch (e) {
    container.innerHTML = `<div class="text-red-400 p-4">${t('tools.loadError')}: ${u.escapeHtml(e.message)}</div>`;
    return;
  }

  const tools = data.tools || [];
  const loadedCount = tools.filter(t => t.loaded).length;

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('tools.title')}</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-green">${loadedCount} ${t('tools.loaded')}</span>
        <span class="badge badge-zinc">${tools.length} ${t('tools.total')}</span>
      </div>
    </div>
    <p class="page-desc">${t('tools.subtitle')}</p>

    <div id="tools-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
      ${tools.length === 0 ? `
        <div class="col-span-full text-center py-12 text-zinc-500">
          <div class="text-4xl mb-3">🧩</div>
          <div>${t('tools.empty')}</div>
          <div class="text-xs mt-1">${t('tools.emptyHint')}</div>
        </div>
      ` : tools.map(tool => renderToolCard(tool, u)).join('')}
    </div>
  `;

  bindCardEvents(container, api, u);
}

function renderToolCard(tool, u) {
  const m = tool.manifest || {};
  const cat = m.category || 'utility';
  const icon = CATEGORY_ICONS[cat] || '📦';
  const isLoaded = tool.loaded;
  const isEnabled = tool.enabled;
  const hasError = !!tool.error;
  const hasSettings = (tool.settings_schema || []).length > 0;

  const statusDot = hasError ? 'bg-red-400' : isLoaded ? 'bg-emerald-400' : isEnabled ? 'bg-yellow-400' : 'bg-zinc-600';
  const statusColor = hasError ? 'text-red-400' : isLoaded ? 'text-emerald-400' : isEnabled ? 'text-yellow-400' : 'text-zinc-500';
  const statusText = hasError ? t('tools.errorStatus') : isLoaded ? t('tools.loadedStatus') : isEnabled ? t('tools.enabledStatus') : t('tools.disabledStatus');

  return `
    <div class="tool-card stat-card hover:border-ghost-500/30 transition-colors" data-tool="${u.escapeHtml(tool.name)}">
      <div class="flex items-start justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-lg" aria-hidden="true">${icon}</span>
          <div>
            <div class="text-sm font-semibold text-white truncate max-w-[180px]" title="${u.escapeHtml(tool.name)}">${u.escapeHtml(tool.name)}</div>
            <div class="text-xs text-zinc-500">${t('tools.version', { version: m.version || '?' })} · ${t('tools.by', { author: m.author || 'ghost' })}</div>
          </div>
        </div>
        <div class="flex items-center gap-1.5" title="${statusText}">
          <span class="w-2 h-2 rounded-full ${statusDot}" aria-hidden="true"></span>
          <span class="text-xs ${statusColor}" role="status">${statusText}</span>
        </div>
      </div>

      <p class="text-xs text-zinc-400 mb-3 line-clamp-2">${u.escapeHtml(m.description || '')}</p>

      ${tool.tools?.length ? `
        <div class="mb-3 text-[10px] text-zinc-600 truncate" title="${tool.tools.map(n => u.escapeHtml(n)).join(', ')}">
          ${t('tools.registeredTools')}: ${tool.tools.map(n => `<span class="text-zinc-400">${u.escapeHtml(n)}</span>`).join(', ')}
        </div>
      ` : ''}

      ${hasError ? `<div class="mb-2 text-[10px] text-red-400/70 truncate cursor-help" title="${u.escapeHtml(tool.error)}">${u.escapeHtml(tool.error)}</div>` : ''}

      <div class="flex gap-2 mt-auto pt-1">
        ${isEnabled
          ? `<button class="tool-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-red-500/20 hover:text-red-400 transition-colors" data-tool="${u.escapeHtml(tool.name)}" data-action="disable">${t('tools.disable')}</button>`
          : `<button class="tool-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-emerald-500/20 hover:text-emerald-400 transition-colors" data-tool="${u.escapeHtml(tool.name)}" data-action="enable">${t('tools.enable')}</button>`
        }
        ${hasSettings ? `<button class="tool-settings-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-ghost-500/20 hover:text-ghost-400 transition-colors" data-tool="${u.escapeHtml(tool.name)}">${t('tools.settings')}</button>` : ''}
        <button class="tool-delete-btn btn btn-sm text-xs bg-surface-700 text-zinc-300 hover:bg-red-500/20 hover:text-red-400 transition-colors ml-auto" data-tool="${u.escapeHtml(tool.name)}">${t('tools.delete')}</button>
      </div>
    </div>
  `;
}

function bindCardEvents(container, api, u) {
  container.querySelectorAll('.tool-toggle-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.tool;
      const action = btn.dataset.action;
      btn.disabled = true;
      btn.textContent = action === 'enable' ? t('tools.enabling') : t('tools.disabling');
      try {
        const result = await api.post(`/api/tools/${encodeURIComponent(name)}/${action}`);
        if (result.status === 'ok') {
          u.toast(action === 'enable' ? t('tools.enabledStatus') : t('tools.disabledStatus'), 'success');
        } else {
          u.toast(result.error || t('common.error'), 'error');
        }
        render(container);
      } catch (e) {
        u.toast(e.message || t('common.error'), 'error');
        btn.disabled = false;
        btn.textContent = action === 'enable' ? t('tools.enable') : t('tools.disable');
      }
    });
  });

  container.querySelectorAll('.tool-settings-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.tool;
      try {
        const data = await api.get(`/api/tools/${encodeURIComponent(name)}/settings`);
        openSettingsModal(name, data.schema || [], data.values || {}, api, u, container);
      } catch (e) {
        u.toast(e.message || t('common.error'), 'error');
      }
    });
  });

  container.querySelectorAll('.tool-delete-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      openDeleteModal(btn.dataset.tool, api, u, container);
    });
  });
}

/* ── Settings Modal ─────────────────────────────────────────────── */

function buildSettingField(setting, value, u) {
  const key = setting.key || '';
  const label = u.escapeHtml(setting.label || key.replace(/_/g, ' '));
  const desc = u.escapeHtml(setting.description || '');
  const req = setting.required ? ' *' : '';
  const isSecret = setting.secret === true;
  const envVar = setting.env_var || '';
  const type = setting.type || 'string';

  if (type === 'boolean') {
    const chk = value ? ' checked' : '';
    return `
      <div class="mb-4 flex items-center gap-2">
        <input type="checkbox" name="${key}" class="rounded bg-surface-700 border-surface-600 text-ghost-500"${chk}>
        <label class="text-xs text-zinc-400">${label}${req}</label>
        ${desc ? `<span class="text-[10px] text-zinc-600">${desc}</span>` : ''}
      </div>`;
  }

  if (type === 'select') {
    const options = (setting.options || []).map(opt => {
      const sel = (String(value) === String(opt)) ? ' selected' : '';
      return `<option value="${u.escapeHtml(opt)}"${sel}>${u.escapeHtml(opt)}</option>`;
    }).join('');
    return `
      <div class="mb-4">
        <label class="block text-xs text-zinc-400 mb-1">${label}${req}</label>
        <select name="${key}" class="form-input w-full text-sm">${options}</select>
        ${desc ? `<div class="text-[10px] text-zinc-600 mt-0.5">${desc}</div>` : ''}
      </div>`;
  }

  if (type === 'number') {
    const val = value !== undefined && value !== '' ? ` value="${value}"` : '';
    return `
      <div class="mb-4">
        <label class="block text-xs text-zinc-400 mb-1">${label}${req}</label>
        <input type="number" name="${key}" step="any" class="form-input w-full text-sm" placeholder="${desc}"${val}>
        ${desc ? `<div class="text-[10px] text-zinc-600 mt-0.5">${desc}</div>` : ''}
      </div>`;
  }

  const inputType = isSecret ? 'password' : 'text';
  const maskedVal = isSecret && value ? '••••••••' : (value || '');
  const val = value !== undefined && value !== '' ? ` value="${u.escapeHtml(String(value))}"` : '';

  return `
    <div class="mb-4">
      <label class="block text-xs text-zinc-400 mb-1">${label}${req}</label>
      <div class="flex gap-2 items-center">
        <input type="${inputType}" name="${key}" class="form-input flex-1 text-sm" placeholder="${isSecret ? t('tools.secretPlaceholder') : desc}"${val}>
        ${isSecret ? `<button type="button" class="secret-toggle-btn btn btn-sm text-xs bg-surface-700 text-zinc-400 hover:text-zinc-200 shrink-0" data-field="${key}">${t('tools.showSecret')}</button>` : ''}
      </div>
      ${desc ? `<div class="text-[10px] text-zinc-600 mt-0.5">${desc}</div>` : ''}
      ${envVar ? `<div class="text-[10px] text-zinc-500 mt-0.5">${t('tools.envHint', { var: envVar })}</div>` : ''}
    </div>`;
}

function openSettingsModal(toolName, schema, savedValues, api, u, pageContainer) {
  const existing = document.getElementById('tool-settings-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'tool-settings-overlay';
  overlay.className = 'modal-overlay';

  const fieldsHtml = schema.length
    ? schema.map(s => buildSettingField(s, savedValues[s.key], u)).join('')
    : `<p class="text-xs text-zinc-500">${t('tools.noSettings')}</p>`;

  overlay.innerHTML = `
    <div class="modal-panel" style="max-width:520px">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-base font-semibold text-white">${t('tools.settingsTitle', { name: toolName })}</h2>
        </div>
        <button id="settings-close" class="text-zinc-500 hover:text-white text-lg leading-none" aria-label="${t('tools.close')}">&times;</button>
      </div>

      <form id="settings-form" autocomplete="off">
        ${fieldsHtml}
        ${schema.length ? `
          <div class="flex items-center gap-3 mt-4 pt-3 border-t border-surface-700">
            <button type="submit" class="btn btn-primary btn-sm text-sm px-6">${t('tools.saveSettings')}</button>
            <span id="settings-feedback" class="text-[10px] text-emerald-400" style="display:none">${t('tools.saved')}</span>
          </div>
        ` : ''}
      </form>
    </div>`;

  document.body.appendChild(overlay);

  function close() {
    overlay.classList.add('modal-closing');
    setTimeout(() => overlay.remove(), 200);
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') close(); }
  document.addEventListener('keydown', onEsc);

  overlay.querySelector('#settings-close')?.addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  overlay.querySelectorAll('.secret-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const fieldName = btn.dataset.field;
      const input = overlay.querySelector(`[name="${fieldName}"]`);
      if (!input) return;
      const isHidden = input.type === 'password';
      input.type = isHidden ? 'text' : 'password';
      btn.textContent = isHidden ? t('tools.hideSecret') : t('tools.showSecret');
    });
  });

  const form = overlay.querySelector('#settings-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const vals = {};
    for (const setting of schema) {
      const key = setting.key;
      const el = form.querySelector(`[name="${key}"]`);
      if (!el) continue;
      if (setting.type === 'boolean') {
        vals[key] = el.checked;
        continue;
      }
      const raw = el.value.trim();
      if (!raw) continue;
      if (setting.type === 'number') vals[key] = parseFloat(raw);
      else vals[key] = raw;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      await api.post(`/api/tools/${encodeURIComponent(toolName)}/settings`, { settings: vals });
      const fb = overlay.querySelector('#settings-feedback');
      if (fb) {
        fb.style.display = 'inline';
        setTimeout(() => { fb.style.display = 'none'; }, 2000);
      }
      u.toast(t('tools.settingsSaved'), 'success');
    } catch (err) {
      u.toast(t('tools.settingsSaveError'), 'error');
    }
    if (submitBtn) submitBtn.disabled = false;
  });
}

/* ── Delete Confirmation Modal ──────────────────────────────────── */

function openDeleteModal(toolName, api, u, pageContainer) {
  const existing = document.getElementById('tool-delete-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'tool-delete-overlay';
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-panel" style="max-width:420px">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-white">${t('tools.deleteTitle')}</h2>
        <button id="delete-close" class="text-zinc-500 hover:text-white text-lg leading-none" aria-label="${t('tools.close')}">&times;</button>
      </div>
      <p class="text-sm text-zinc-400 mb-4">
        ${t('tools.deleteConfirm', { name: u.escapeHtml(toolName) })}
      </p>
      <div class="flex items-center gap-3 pt-2">
        <button id="delete-confirm" class="btn btn-sm text-xs bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30 px-5 transition-colors">${t('tools.delete')}</button>
        <button id="delete-cancel" class="btn btn-sm text-xs bg-surface-700 text-zinc-400 hover:text-zinc-200 transition-colors">${t('tools.cancel')}</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  function close() {
    overlay.classList.add('modal-closing');
    setTimeout(() => overlay.remove(), 200);
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') close(); }
  document.addEventListener('keydown', onEsc);

  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('#delete-close')?.addEventListener('click', close);
  overlay.querySelector('#delete-cancel')?.addEventListener('click', close);

  overlay.querySelector('#delete-confirm')?.addEventListener('click', async () => {
    const btn = overlay.querySelector('#delete-confirm');
    btn.disabled = true;
    btn.textContent = t('tools.deleting');

    try {
      const result = await api.post(`/api/tools/${encodeURIComponent(toolName)}/delete`);
      if (result.status === 'ok') {
        close();
        u.toast(t('tools.deleteSuccess', { name: toolName }), 'success');
        render(pageContainer);
      } else {
        u.toast(result.error || t('tools.deleteFailed'), 'error');
        btn.disabled = false;
        btn.textContent = t('tools.delete');
      }
    } catch (e) {
      u.toast(e.message || t('tools.deleteFailed'), 'error');
      btn.disabled = false;
      btn.textContent = t('tools.delete');
    }
  });
}
