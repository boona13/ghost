/** Soul (SOUL.md) editor page */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/soul');

  container.innerHTML = `
    <h1 class="page-header">${t('soul.title')}</h1>
    <p class="page-desc">${t('soul.subtitle')}</p>

    <div class="stat-card mb-4">
      <div class="flex items-center justify-between text-xs text-zinc-500">
        <span>${t('common.file')} <span class="font-mono text-zinc-400">${data.path}</span></span>
        <span id="char-count">${data.content.length} ${t('common.chars')}</span>
      </div>
    </div>

    <textarea id="soul-editor" class="editor-textarea">${u.escapeHtml(data.content)}</textarea>

    <div class="flex gap-3 mt-4">
      <button id="btn-save-soul" class="btn btn-primary">${t('soul.saveSoul')}</button>
      <button id="btn-reset-soul" class="btn btn-danger btn-sm">${t('soul.resetDefault')}</button>
    </div>
  `;

  const editor = document.getElementById('soul-editor');
  editor?.addEventListener('input', () => {
    document.getElementById('char-count').textContent = `${editor.value.length} ${t('common.chars')}`;
  });

  document.getElementById('btn-save-soul')?.addEventListener('click', async () => {
    await api.put('/api/soul', { content: editor.value });
    u.toast(t('soul.saved'));
  });

  document.getElementById('btn-reset-soul')?.addEventListener('click', async () => {
    if (!confirm(t('soul.resetConfirm'))) return;
    const r = await api.post('/api/soul/reset');
    u.toast(t('soul.resetDone'));
    render(container);
  });
}
