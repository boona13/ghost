/** Ghost Dashboard — Device Pairing & Auth page */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  container.innerHTML = `
    <div class="max-w-4xl mx-auto px-6 py-8">
      <div class="page-header mb-8">
        <h1 class="text-2xl font-bold text-white">${t('pairing.title')}</h1>
        <p class="text-zinc-400 text-sm mt-1">${t('pairing.subtitle')}</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8" id="pairing-stats">
        <div class="stat-card">
          <div class="stat-label">${t('pairing.pendingRequests')}</div>
          <div class="stat-value" id="stat-pending">—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${t('pairing.pairedDevices')}</div>
          <div class="stat-value" id="stat-paired">—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${t('common.status')}</div>
          <div class="stat-value text-sm" id="stat-status">${t('common.loading')}</div>
        </div>
      </div>

      <div class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-white">${t('pairing.pendingRequests')}</h2>
          <button id="btn-refresh" class="btn btn-sm bg-surface-600 hover:bg-surface-500 text-zinc-300 px-3 py-1.5 rounded text-xs">
            ${t('common.refresh')}
          </button>
        </div>
        <div id="pending-list" class="space-y-3">
          <div class="text-zinc-500 text-sm">${t('common.loading')}</div>
        </div>
      </div>

      <div class="mb-8">
        <h2 class="text-lg font-semibold text-white mb-4">${t('pairing.pairedDevices')}</h2>
        <div id="devices-list" class="space-y-3">
          <div class="text-zinc-500 text-sm">${t('common.loading')}</div>
        </div>
      </div>

      <div class="border border-surface-600/50 rounded-lg p-5 bg-surface-800/30">
        <h3 class="text-sm font-semibold text-zinc-300 mb-3">${t('pairing.howToPair')}</h3>
        <div class="text-xs text-zinc-500 space-y-2">
          <p>${t('pairing.howStep1')}</p>
          <pre class="bg-surface-900 rounded px-3 py-2 text-zinc-400 overflow-x-auto">curl -X POST http://GHOST_HOST:3333/api/pairing/request \\
  -H "Content-Type: application/json" \\
  -d '{"device_name": "My Phone", "device_type": "mobile"}'</pre>
          <p>${t('pairing.howStep2')}</p>
          <p>${t('pairing.howStep3')}</p>
          <p>${t('pairing.howStep4')}</p>
          <p>${t('pairing.howStep5')}</p>
        </div>
      </div>
    </div>
  `;

  const refresh = () => Promise.all([loadPending(), loadDevices()]);

  document.getElementById('btn-refresh').addEventListener('click', refresh);
  await refresh();
}


async function loadPending() {
  try {
    const data = await window.GhostAPI.get('/api/pairing/pending');
    const el = document.getElementById('pending-list');
    const statEl = document.getElementById('stat-pending');
    const statusEl = document.getElementById('stat-status');

    statEl.textContent = data.count || 0;
    statusEl.textContent = data.count > 0 ? t('pairing.requestsWaiting') : t('status.ready');
    statusEl.className = `stat-value text-sm ${data.count > 0 ? 'text-amber-400' : 'text-emerald-400'}`;

    if (!data.pending || data.pending.length === 0) {
      el.innerHTML = `<div class="text-zinc-500 text-sm py-4 text-center border border-dashed border-surface-600/50 rounded-lg">${t('pairing.noPending')}</div>`;
      return;
    }

    el.innerHTML = data.pending.map(p => `
      <div class="border border-surface-600/50 rounded-lg p-4 bg-surface-800/30 flex items-center justify-between">
        <div class="flex-1">
          <div class="flex items-center gap-3 mb-1">
            <span class="text-white font-medium">${esc(p.device_name)}</span>
            <span class="badge bg-surface-600 text-zinc-400 text-[10px] px-1.5 py-0.5 rounded">${esc(p.device_type)}</span>
            <span class="badge bg-amber-500/20 text-amber-400 text-[10px] px-1.5 py-0.5 rounded">${t('common.pending')}</span>
          </div>
          <div class="text-xs text-zinc-500">
            ${t('pairing.code')}: <span class="font-mono text-violet-400 text-sm font-semibold tracking-wider">${esc(p.code)}</span>
            <span class="ml-3">${t('pairing.expiresIn', {seconds: p.expires_in_s})}</span>
          </div>
        </div>
        <div class="flex items-center gap-2 ml-4">
          <select class="scope-select bg-surface-700 border border-surface-600 text-zinc-300 text-xs rounded px-2 py-1" data-rid="${esc(p.request_id)}">
            <option value="read,write" selected>${t('pairing.readWrite')}</option>
            <option value="read">${t('pairing.readOnly')}</option>
            <option value="read,write,admin">${t('pairing.fullAdmin')}</option>
          </select>
          <button class="btn-approve btn bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded" data-rid="${esc(p.request_id)}">
            ${t('common.approve')}
          </button>
          <button class="btn-reject btn bg-red-600/80 hover:bg-red-500 text-white text-xs px-3 py-1.5 rounded" data-rid="${esc(p.request_id)}">
            ${t('common.reject')}
          </button>
        </div>
      </div>
    `).join('');

    el.querySelectorAll('.btn-approve').forEach(btn => {
      btn.addEventListener('click', async () => {
        const rid = btn.dataset.rid;
        const scopeSelect = el.querySelector(`.scope-select[data-rid="${rid}"]`);
        const scopes = scopeSelect ? scopeSelect.value.split(',') : ['read', 'write'];
        btn.disabled = true;
        btn.textContent = '...';
        try {
          const result = await window.GhostAPI.post(`/api/pairing/${rid}/approve`, { scopes });
          if (result.token) {
            alert(`${t('pairing.tokenShownOnce')}\n\n${result.token}\n\n${t('pairing.saveToken')}`);
          }
        } catch (e) {
          alert(t('common.errorPrefix', {error: e.message}));
        }
        loadPending();
        loadDevices();
      });
    });

    el.querySelectorAll('.btn-reject').forEach(btn => {
      btn.addEventListener('click', async () => {
        const rid = btn.dataset.rid;
        btn.disabled = true;
        await window.GhostAPI.post(`/api/pairing/${rid}/reject`);
        loadPending();
      });
    });
  } catch (e) {
    document.getElementById('pending-list').innerHTML =
      `<div class="text-red-400 text-sm">${t('pairing.errorLoadingPending', {error: esc(e.message)})}</div>`;
  }
}


async function loadDevices() {
  try {
    const data = await window.GhostAPI.get('/api/pairing/devices');
    const el = document.getElementById('devices-list');
    const statEl = document.getElementById('stat-paired');

    statEl.textContent = data.count || 0;

    if (!data.devices || data.devices.length === 0) {
      el.innerHTML = `<div class="text-zinc-500 text-sm py-4 text-center border border-dashed border-surface-600/50 rounded-lg">${t('pairing.noPaired')}</div>`;
      return;
    }

    el.innerHTML = data.devices.map(d => `
      <div class="border border-surface-600/50 rounded-lg p-4 bg-surface-800/30 flex items-center justify-between">
        <div class="flex-1">
          <div class="flex items-center gap-3 mb-1">
            <span class="text-white font-medium">${esc(d.device_name)}</span>
            <span class="badge bg-surface-600 text-zinc-400 text-[10px] px-1.5 py-0.5 rounded">${esc(d.device_type)}</span>
            <span class="badge bg-emerald-500/20 text-emerald-400 text-[10px] px-1.5 py-0.5 rounded">${t('pairing.paired')}</span>
          </div>
          <div class="text-xs text-zinc-500">
            ${t('pairing.deviceId')} <span class="font-mono text-zinc-400">${esc(d.device_id)}</span>
            <span class="ml-3">${t('pairing.scopesLabel')} ${(d.scopes || []).map(s => `<span class="text-violet-400">${esc(s)}</span>`).join(', ')}</span>
            <span class="ml-3">${t('pairing.pairedAt')} ${esc(d.paired_at?.slice(0, 10) || '—')}</span>
            <span class="ml-3">${t('pairing.lastSeen')} ${esc(d.last_seen?.slice(0, 19)?.replace('T', ' ') || '—')}</span>
          </div>
        </div>
        <div class="flex items-center gap-2 ml-4">
          <button class="btn-rotate btn bg-surface-600 hover:bg-surface-500 text-zinc-300 text-xs px-3 py-1.5 rounded" data-did="${esc(d.device_id)}">
            ${t('pairing.rotateToken')}
          </button>
          <button class="btn-revoke btn bg-red-600/80 hover:bg-red-500 text-white text-xs px-3 py-1.5 rounded" data-did="${esc(d.device_id)}" data-name="${esc(d.device_name)}">
            ${t('common.revoke')}
          </button>
        </div>
      </div>
    `).join('');

    el.querySelectorAll('.btn-revoke').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm(t('pairing.revokeConfirm', {name: btn.dataset.name}))) return;
        btn.disabled = true;
        await window.GhostAPI.del(`/api/pairing/devices/${btn.dataset.did}`);
        loadDevices();
      });
    });

    el.querySelectorAll('.btn-rotate').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.textContent = '...';
        try {
          const result = await window.GhostAPI.post(`/api/pairing/devices/${btn.dataset.did}/rotate`);
          if (result.token) {
            alert(`${t('pairing.newTokenMsg')}\n\n${result.token}\n\n${t('pairing.updateDevice')}`);
          }
        } catch (e) {
          alert(t('common.errorPrefix', {error: e.message}));
        }
        loadDevices();
      });
    });
  } catch (e) {
    document.getElementById('devices-list').innerHTML =
      `<div class="text-red-400 text-sm">${t('pairing.errorLoadingDevices', {error: esc(e.message)})}</div>`;
  }
}


function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
