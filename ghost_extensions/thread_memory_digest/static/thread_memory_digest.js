export function renderThreadMemoryDigestPage(container) {
  container.innerHTML = `
    <div class="space-y-4">
      <div>
        <h1 class="page-header">Thread Digest</h1>
        <p class="page-desc">View recent thread-to-memory digests created by the extension tools.</p>
      </div>
      <div class="stat-card p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="text-xs text-zinc-400">Recent Digests</div>
          <button id="tmd-refresh" class="btn btn-secondary btn-sm">Refresh</button>
        </div>
        <div id="tmd-list" class="space-y-2 text-xs text-zinc-300"></div>
      </div>
    </div>
  `;

  const listEl = container.querySelector('#tmd-list');
  const refreshBtn = container.querySelector('#tmd-refresh');

  async function loadHistory() {
    listEl.innerHTML = '<div class="text-zinc-500">Loading…</div>';
    try {
      const res = await fetch('/api/extensions');
      const data = await res.json();
      const ext = (data.extensions || []).find((x) => x.name === 'thread_memory_digest');
      if (!ext || !ext.loaded) {
        listEl.innerHTML = '<div class="text-amber-400">Extension not loaded.</div>';
        return;
      }

      const raw = await fetch('/extensions/thread_memory_digest/data/digest_history.json');
      if (!raw.ok) {
        listEl.innerHTML = '<div class="text-zinc-500">No digest history yet.</div>';
        return;
      }
      const rows = await raw.json();
      if (!Array.isArray(rows) || rows.length === 0) {
        listEl.innerHTML = '<div class="text-zinc-500">No digest history yet.</div>';
        return;
      }

      listEl.innerHTML = rows.slice(0, 25).map((row) => {
        const bullets = Array.isArray(row.bullets) ? row.bullets : [];
        return `
          <div class="rounded border border-zinc-800 p-3 bg-[#0a0a12]">
            <div class="flex items-center justify-between gap-2 mb-1">
              <div class="text-zinc-200">${escapeHtml(row.title || 'Thread Digest')}</div>
              <span class="badge ${row.saved ? 'badge-green' : 'badge-zinc'}">${row.saved ? 'saved' : 'unsaved'}</span>
            </div>
            <div class="text-[10px] text-zinc-500 mb-2">${escapeHtml(row.channel || 'unknown')} ${row.thread_id ? `• ${escapeHtml(row.thread_id)}` : ''}</div>
            <ul class="list-disc ml-4 space-y-1">
              ${bullets.slice(0, 5).map((b) => `<li>${escapeHtml(String(b))}</li>`).join('')}
            </ul>
          </div>
        `;
      }).join('');
    } catch (err) {
      listEl.innerHTML = `<div class="text-red-400">Failed to load history: ${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  refreshBtn.addEventListener('click', loadHistory);
  loadHistory();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
