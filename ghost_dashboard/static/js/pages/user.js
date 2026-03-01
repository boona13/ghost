/** User Profile (USER.md) editor page */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/user');

  const parseField = (content, marker) => {
    const re = new RegExp(`\\*\\*${marker}:\\*\\*\\s*(.*)`, 'i');
    const m = content.match(re);
    return m ? m[1].trim() : '';
  };

  const name = parseField(data.content, 'Name');
  const callThem = parseField(data.content, 'What to call them');
  const pronouns = parseField(data.content, 'Pronouns');
  const timezone = parseField(data.content, 'Timezone');

  container.innerHTML = `
    <h1 class="page-header">User Profile</h1>
    <p class="page-desc">Information about you — Ghost reads this to personalize responses</p>

    <div class="stat-card mb-6">
      <h3 class="text-sm font-semibold text-white mb-3">Quick Set</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label class="form-label">Name</label>
          <input id="qf-name" type="text" class="form-input w-full" value="${u.escapeHtml(name)}">
        </div>
        <div>
          <label class="form-label">Call me</label>
          <input id="qf-call" type="text" class="form-input w-full" value="${u.escapeHtml(callThem)}">
        </div>
        <div>
          <label class="form-label">Pronouns</label>
          <input id="qf-pronouns" type="text" class="form-input w-full" value="${u.escapeHtml(pronouns)}" placeholder="e.g. he/him">
        </div>
        <div>
          <label class="form-label">Timezone</label>
          <input id="qf-tz" type="text" class="form-input w-full" value="${u.escapeHtml(timezone)}" placeholder="e.g. UTC-5">
        </div>
      </div>
      <button id="btn-quick-apply" class="btn btn-secondary btn-sm mt-3">Apply to file</button>
    </div>

    <textarea id="user-editor" class="editor-textarea">${u.escapeHtml(data.content)}</textarea>

    <div class="flex gap-3 mt-4">
      <button id="btn-save-user" class="btn btn-primary">Save USER.md</button>
      <button id="btn-reset-user" class="btn btn-danger btn-sm">Reset to Default</button>
    </div>
  `;

  document.getElementById('btn-quick-apply')?.addEventListener('click', () => {
    const editor = document.getElementById('user-editor');
    let content = editor.value;
    const fields = {
      'Name': document.getElementById('qf-name').value,
      'What to call them': document.getElementById('qf-call').value,
      'Pronouns': document.getElementById('qf-pronouns').value,
      'Timezone': document.getElementById('qf-tz').value,
    };
    for (const [marker, val] of Object.entries(fields)) {
      const re = new RegExp(`(\\*\\*${marker}:\\*\\*).*`, 'i');
      if (content.match(re)) {
        content = content.replace(re, `$1 ${val}`);
      }
    }
    editor.value = content;
    u.toast('Fields applied — click Save to persist');
  });

  document.getElementById('btn-save-user')?.addEventListener('click', async () => {
    await api.put('/api/user', { content: document.getElementById('user-editor').value });
    u.toast('USER.md saved');
  });

  document.getElementById('btn-reset-user')?.addEventListener('click', async () => {
    if (!confirm('Reset USER.md to default?')) return;
    await api.post('/api/user/reset');
    u.toast('USER.md reset');
    render(container);
  });
}
