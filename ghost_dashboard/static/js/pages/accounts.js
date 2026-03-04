/** Accounts page — list and manage saved credentials */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let data = { accounts: [], total: 0 };
  try {
    data = await api.get('/api/accounts');
  } catch { /* empty */ }

  const accounts = data.accounts || [];

  container.innerHTML = `
    <h1 class="page-header">${t('accounts.title')}</h1>
    <p class="page-desc">${t('accounts.subtitle')}</p>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('accounts.totalAccounts')}</div>
        <div class="text-2xl font-bold text-white">${accounts.length}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('accounts.services')}</div>
        <div class="flex flex-wrap gap-1 mt-1">
          ${serviceBadges(accounts)}
        </div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('accounts.latest')}</div>
        <div class="text-sm text-zinc-300 mt-1">${accounts.length ? formatDate(accounts[accounts.length - 1].created_at) : t('common.noneYet')}</div>
      </div>
    </div>

    <div class="stat-card">
      ${accounts.length === 0 ? `
        <div class="text-center py-8">
          <div class="text-3xl mb-3 opacity-30">&#x1F511;</div>
          <div class="text-sm text-zinc-500">${t('accounts.noAccounts')}</div>
          <div class="text-xs text-zinc-600 mt-1">${t('accounts.noAccountsDesc')}</div>
        </div>
      ` : `
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-surface-600/50">
                <th class="text-left py-2 px-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">${t('accounts.service')}</th>
                <th class="text-left py-2 px-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">${t('accounts.email')}</th>
                <th class="text-left py-2 px-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">${t('accounts.username')}</th>
                <th class="text-left py-2 px-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">${t('common.created')}</th>
                <th class="text-left py-2 px-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">${t('accounts.notes')}</th>
                <th class="py-2 px-3"></th>
              </tr>
            </thead>
            <tbody id="accounts-tbody">
              ${accounts.map(renderRow).join('')}
            </tbody>
          </table>
        </div>
      `}
    </div>
  `;

  container.querySelectorAll('.btn-delete-account').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const idx = parseInt(e.currentTarget.dataset.index);
      const label = e.currentTarget.dataset.label;
      if (!confirm(t('accounts.deleteConfirm', { name: label }))) return;
      try {
        await api.del(`/api/accounts/${idx}`);
        u.toast(t('accounts.deletedName', { name: label }));
        render(container);
      } catch (err) {
        u.toast(t('common.errorPrefix', {error: err.message}), 'error');
      }
    });
  });
}

function renderRow(acc) {
  const esc = window.GhostUtils?.escapeHtml || ((s) => s);
  const colors = {
    'mail.tm': 'ghost',
    'x.com': 'blue',
    'twitter': 'blue',
    'instagram': 'pink',
    'outlook': 'cyan',
  };
  const svc = acc.service || 'unknown';
  const color = colors[svc] || 'zinc';
  const label = acc.email || acc.username || svc;

  return `
    <tr class="border-b border-surface-600/30 hover:bg-surface-800/50 transition-colors">
      <td class="py-2.5 px-3">
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-${color}-500/10 text-${color}-400">${esc(svc)}</span>
      </td>
      <td class="py-2.5 px-3 font-mono text-xs text-zinc-300">${esc(acc.email || '-')}</td>
      <td class="py-2.5 px-3 font-mono text-xs text-zinc-400">${esc(acc.username || '-')}</td>
      <td class="py-2.5 px-3 text-xs text-zinc-500">${formatDate(acc.created_at)}</td>
      <td class="py-2.5 px-3 text-xs text-zinc-600 max-w-[200px] truncate">${esc(acc.notes || '')}</td>
      <td class="py-2.5 px-3 text-right">
        <button class="btn-delete-account text-zinc-600 hover:text-red-400 transition-colors p-1" data-index="${acc.index}" data-label="${esc(label)}" title="${t('common.delete')}">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
          </svg>
        </button>
      </td>
    </tr>
  `;
}

function serviceBadges(accounts) {
  const counts = {};
  for (const a of accounts) {
    const s = a.service || 'unknown';
    counts[s] = (counts[s] || 0) + 1;
  }
  if (Object.keys(counts).length === 0) {
    return `<span class="text-xs text-zinc-600">${t('accounts.none')}</span>`;
  }
  return Object.entries(counts)
    .map(([s, c]) => `<span class="badge badge-zinc">${s}: ${c}</span>`)
    .join('');
}

function formatDate(iso) {
  if (!iso) return '-';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}
