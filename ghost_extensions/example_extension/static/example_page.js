/**
 * Example Extension — Dashboard Page
 *
 * This is the REFERENCE TEMPLATE for extension dashboard pages.
 * When Ghost implements a new extension with a UI, it should follow this pattern.
 *
 * KEY RULES:
 *   1. Register the page object on window.GhostPages.<extension_id>
 *   2. The object MUST have a render(container) method
 *   3. Call API routes via window.GhostAPI.post('/api/<ext_name>/...')
 *      or window.GhostAPI.get('/api/<ext_name>/...')
 *   4. NEVER call /tool/... — tools are NOT HTTP endpoints
 *   5. Use dashboard CSS classes: form-input, form-label, btn, btn-primary,
 *      btn-secondary, stat-card, stat-value, stat-label, page-header, page-desc
 *   6. Form inputs/textareas inside modals MUST use style="width:100%;box-sizing:border-box"
 *   7. Use window.GhostUtils.toast(msg, type) for user feedback
 *
 * UX — VIEWER vs FORM (critical, read carefully):
 *   - AUTOMATION extensions (Ghost uses tools autonomously): Dashboard page must
 *     be a READ-ONLY VIEWER. Show history, let user browse/export/delete. Do NOT
 *     create a form that duplicates tool parameters (session_id, steps, artifacts).
 *   - USER-FACING extensions (human triggers the action): Simple forms are OK
 *     (1-2 fields max). No internal IDs or multi-line structured data.
 *   - This example is USER-FACING — the user types text to summarize. The form
 *     has ONE field (textarea). The history below is a read-only viewer.
 *   - Empty states MUST explain what the page shows and how data will appear.
 */

window.GhostPages = window.GhostPages || {};

window.GhostPages.example_extension = {
  container: null,
  history: [],

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="page-header">
        <h1 class="text-xl font-bold text-white">Example Extension</h1>
        <p class="page-desc">Reference dashboard page — summarize text with LLM intelligence</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="stat-card">
          <div class="stat-value" id="example-total">-</div>
          <div class="stat-label">Total Summaries</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" id="example-last">-</div>
          <div class="stat-label">Last Summary</div>
        </div>
      </div>

      <div class="flex gap-3 mb-6">
        <button class="btn btn-primary" id="btn-example-summarize">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
          </svg>
          New Summary
        </button>
        <button class="btn btn-secondary" id="btn-example-clear">
          Clear History
        </button>
      </div>

      <div class="stat-card">
        <h3 class="text-sm font-medium text-zinc-300 mb-4">Summary History</h3>
        <div id="example-history-list" class="space-y-2">
          <div class="text-zinc-500 text-sm">Loading...</div>
        </div>
      </div>

      <div id="example-modal-overlay" class="fixed inset-0 bg-black/60 z-50 hidden items-center justify-center" style="display:none">
        <div class="bg-[#10101c] rounded-xl border border-white/10 p-6 w-full max-w-lg mx-4">
          <h2 class="text-lg font-semibold text-white mb-4">Summarize Text</h2>
          <div class="mb-4">
            <label class="form-label mb-1">Text to summarize</label>
            <textarea id="example-input-text" class="form-input" rows="6"
              style="width:100%;box-sizing:border-box"
              placeholder="Paste or type text here..."></textarea>
          </div>
          <div class="flex justify-end gap-3">
            <button class="btn btn-secondary" id="btn-example-cancel">Cancel</button>
            <button class="btn btn-primary" id="btn-example-submit">Summarize</button>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    this.loadHistory();
  },

  bindEvents() {
    const btnSummarize = this.container.querySelector('#btn-example-summarize');
    const btnClear = this.container.querySelector('#btn-example-clear');
    const btnCancel = this.container.querySelector('#btn-example-cancel');
    const btnSubmit = this.container.querySelector('#btn-example-submit');
    const overlay = this.container.querySelector('#example-modal-overlay');

    btnSummarize.addEventListener('click', () => this.showModal());
    btnClear.addEventListener('click', () => this.clearHistory());
    btnCancel.addEventListener('click', () => this.hideModal());
    btnSubmit.addEventListener('click', () => this.submitSummary());
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this.hideModal();
    });
  },

  showModal() {
    const overlay = this.container.querySelector('#example-modal-overlay');
    overlay.style.display = 'flex';
    overlay.classList.remove('hidden');
    this.container.querySelector('#example-input-text').value = '';
    this.container.querySelector('#example-input-text').focus();
  },

  hideModal() {
    const overlay = this.container.querySelector('#example-modal-overlay');
    overlay.style.display = 'none';
    overlay.classList.add('hidden');
  },

  async loadHistory() {
    try {
      const resp = await window.GhostAPI.get('/api/example/history');
      if (resp && resp.status === 'ok') {
        this.history = resp.history || [];
        this.renderHistory();
        this.updateStats();
      }
    } catch (err) {
      this.container.querySelector('#example-history-list').innerHTML =
        '<div class="text-red-400 text-sm">Failed to load history</div>';
    }
  },

  renderHistory() {
    const list = this.container.querySelector('#example-history-list');
    if (!this.history.length) {
      list.innerHTML = '<div class="text-zinc-500 text-sm">No summaries yet. Click "New Summary" to get started.</div>';
      return;
    }
    list.innerHTML = this.history.slice().reverse().map(item => `
      <div class="p-3 rounded-lg bg-[#0a0a14] border border-white/5">
        <div class="flex justify-between items-center mb-1">
          <span class="text-xs text-zinc-400">${item.timestamp || 'N/A'}</span>
          <span class="text-xs text-zinc-500">${item.input_length || 0} chars</span>
        </div>
        <div class="text-sm text-zinc-300">${this.escapeHtml(item.summary_preview || '')}</div>
      </div>
    `).join('');
  },

  updateStats() {
    const totalEl = this.container.querySelector('#example-total');
    const lastEl = this.container.querySelector('#example-last');
    totalEl.textContent = this.history.length;
    if (this.history.length) {
      const last = this.history[this.history.length - 1];
      lastEl.textContent = last.timestamp || 'N/A';
    } else {
      lastEl.textContent = 'Never';
    }
  },

  async submitSummary() {
    const textarea = this.container.querySelector('#example-input-text');
    const text = textarea.value.trim();
    if (!text) {
      window.GhostUtils && window.GhostUtils.toast('Please enter some text', 'warning');
      return;
    }

    const btn = this.container.querySelector('#btn-example-submit');
    btn.disabled = true;
    btn.textContent = 'Summarizing...';

    try {
      const resp = await window.GhostAPI.post('/api/example/summarize', { text });
      if (resp && resp.status === 'ok') {
        window.GhostUtils && window.GhostUtils.toast('Summary created!', 'success');
        this.hideModal();
        this.loadHistory();
      } else {
        window.GhostUtils && window.GhostUtils.toast(resp.error || 'Summarization failed', 'error');
      }
    } catch (err) {
      window.GhostUtils && window.GhostUtils.toast('Request failed', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Summarize';
    }
  },

  async clearHistory() {
    try {
      const resp = await window.GhostAPI.post('/api/example/clear', {});
      if (resp && resp.status === 'ok') {
        this.history = [];
        this.renderHistory();
        this.updateStats();
        window.GhostUtils && window.GhostUtils.toast('History cleared', 'success');
      }
    } catch (err) {
      window.GhostUtils && window.GhostUtils.toast('Failed to clear history', 'error');
    }
  },

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
};
