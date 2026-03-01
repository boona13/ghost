/** Soul (SOUL.md) editor page */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/soul');

  container.innerHTML = `
    <h1 class="page-header">Soul</h1>
    <p class="page-desc">Ghost's personality, tone, and boundaries — injected into every prompt</p>

    <div class="stat-card mb-4">
      <div class="flex items-center justify-between text-xs text-zinc-500">
        <span>File: <span class="font-mono text-zinc-400">${data.path}</span></span>
        <span id="char-count">${data.content.length} chars</span>
      </div>
    </div>

    <textarea id="soul-editor" class="editor-textarea">${u.escapeHtml(data.content)}</textarea>

    <div class="flex gap-3 mt-4">
      <button id="btn-save-soul" class="btn btn-primary">Save SOUL.md</button>
      <button id="btn-reset-soul" class="btn btn-danger btn-sm">Reset to Default</button>
    </div>
  `;

  const editor = document.getElementById('soul-editor');
  editor?.addEventListener('input', () => {
    document.getElementById('char-count').textContent = `${editor.value.length} chars`;
  });

  document.getElementById('btn-save-soul')?.addEventListener('click', async () => {
    await api.put('/api/soul', { content: editor.value });
    u.toast('SOUL.md saved');
  });

  document.getElementById('btn-reset-soul')?.addEventListener('click', async () => {
    if (!confirm('Reset SOUL.md to default? Your current soul will be lost.')) return;
    const r = await api.post('/api/soul/reset');
    u.toast('SOUL.md reset');
    render(container);
  });
}
