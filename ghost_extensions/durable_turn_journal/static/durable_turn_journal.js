/**
 * Durable Turn Journal — Dashboard Page
 * View and manage checkpoint journals for Ghost's long-running tasks.
 *
 * This is a READ-FOCUSED viewer. Checkpoints are created automatically
 * by Ghost during tool loops. The dashboard lets you browse, inspect,
 * export, and clean up sessions.
 */

window.GhostPages = window.GhostPages || {};

window.GhostPages.durable_turn_journal = {
  container: null,
  currentSession: null,
  checkpoints: [],
  sessions: [],
  selectedCheckpoint: null,

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="page-header">
        <h1 class="text-xl font-bold text-white">Turn Journal</h1>
        <p class="page-desc">Browse checkpoint journals created during Ghost's long-running tasks</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div class="stat-card">
          <div class="stat-value" id="journal-total-sessions">-</div>
          <div class="stat-label">Sessions</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" id="journal-total-checkpoints">-</div>
          <div class="stat-label">Total Checkpoints</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" id="journal-last-activity">-</div>
          <div class="stat-label">Last Activity</div>
        </div>
      </div>

      <div class="flex gap-3 mb-6">
        <button class="btn btn-secondary" id="btn-refresh">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
          Refresh
        </button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="stat-card" style="min-height:200px">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-sm font-medium text-zinc-300">Sessions</h3>
            <span class="text-xs text-zinc-500" id="sessions-hint">Select a session to view checkpoints</span>
          </div>
          <div id="sessions-list" class="space-y-2">
            <div class="text-zinc-500 text-sm">Loading...</div>
          </div>
        </div>

        <div class="stat-card" style="min-height:200px">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-sm font-medium text-zinc-300">Checkpoints</h3>
            <div class="flex gap-2" id="checkpoint-actions" style="display:none">
              <button class="btn btn-ghost text-xs py-1 px-2" id="btn-export-json" title="Export JSON">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
              </button>
              <button class="btn btn-ghost text-xs py-1 px-2" id="btn-export-md" title="Export Markdown">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              </button>
            </div>
          </div>
          <div id="checkpoints-list" class="space-y-2">
            <div class="text-zinc-500 text-sm">Select a session to view its checkpoints</div>
          </div>
        </div>
      </div>

      <!-- Checkpoint Detail Modal -->
      <div id="detail-modal" class="fixed inset-0 bg-black/60 z-50" style="display:none">
        <div class="flex items-center justify-center min-h-full p-4">
          <div class="bg-[#10101c] rounded-xl border border-white/10 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div class="sticky top-0 bg-[#10101c] border-b border-white/5 px-6 py-4 flex justify-between items-center">
              <h3 class="text-lg font-medium text-white">Checkpoint Details</h3>
              <button class="text-zinc-400 hover:text-white" id="btn-close-detail">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>
            <div id="detail-content" class="p-6 space-y-4">
              <div class="text-zinc-500 text-sm">Loading...</div>
            </div>
            <div class="sticky bottom-0 bg-[#10101c] border-t border-white/5 px-6 py-4 flex justify-end gap-3">
              <button class="btn btn-secondary" id="btn-detail-export">Export</button>
              <button class="btn btn-primary" id="btn-resume">Resume in Chat</button>
            </div>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    this.loadSessions();
  },

  bindEvents() {
    this.container.querySelector('#btn-refresh').addEventListener('click', () => this.loadSessions());
    this.container.querySelector('#btn-close-detail').addEventListener('click', () => this.hideDetailModal());
    this.container.querySelector('#btn-resume').addEventListener('click', () => this.resumeCheckpoint());
    this.container.querySelector('#btn-detail-export').addEventListener('click', () => this.exportCurrentCheckpoint());
    this.container.querySelector('#btn-export-json').addEventListener('click', () => this.exportSession('json'));
    this.container.querySelector('#btn-export-md').addEventListener('click', () => this.exportSession('markdown'));

    this.container.querySelector('#detail-modal').addEventListener('click', (e) => {
      if (e.target === this.container.querySelector('#detail-modal')) this.hideDetailModal();
    });
  },

  async loadSessions() {
    try {
      const result = await window.GhostAPI.post('/api/journal/list', {});
      this.sessions = result.sessions || [];
      this.renderSessions();
      this.updateStats();
    } catch (err) {
      console.error('Failed to load sessions:', err);
      this.container.querySelector('#sessions-list').innerHTML =
        '<div class="text-red-400 text-sm">Failed to load sessions</div>';
    }
  },

  renderSessions() {
    const container = this.container.querySelector('#sessions-list');
    const hint = this.container.querySelector('#sessions-hint');

    if (!this.sessions.length) {
      container.innerHTML = `
        <div class="flex flex-col items-center justify-center py-8 text-center">
          <svg class="w-10 h-10 text-zinc-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
          </svg>
          <p class="text-zinc-500 text-sm">No journal sessions yet</p>
          <p class="text-zinc-600 text-xs mt-1">Checkpoints appear here automatically when Ghost runs long tasks</p>
        </div>`;
      hint.textContent = '';
      return;
    }

    hint.textContent = this.currentSession ? '' : 'Select a session';

    container.innerHTML = this.sessions.map(s => {
      const isActive = s.session_id === this.currentSession;
      return `
        <div class="p-3 rounded-lg cursor-pointer transition-colors ${isActive ? 'bg-[#1a1a2e] ring-1 ring-purple-500/40' : 'bg-[#0a0a14] hover:bg-[#12121f]'}"
             data-session="${this.escapeHtml(s.session_id)}">
          <div class="flex justify-between items-start">
            <div class="font-medium text-sm text-white truncate flex-1 mr-2">${this.escapeHtml(s.session_id)}</div>
            <span class="text-xs px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 flex-shrink-0">${s.checkpoint_count} cp</span>
          </div>
          <div class="text-xs text-zinc-500 mt-1.5">${this.formatTime(s.last_checkpoint)}</div>
          ${s.last_label ? `<div class="text-xs text-zinc-400 truncate mt-1">${this.escapeHtml(s.last_label)}</div>` : ''}
        </div>`;
    }).join('');

    container.querySelectorAll('[data-session]').forEach(el => {
      el.addEventListener('click', () => {
        this.currentSession = el.dataset.session;
        this.renderSessions();
        this.loadCheckpoints(this.currentSession);
      });
    });
  },

  async loadCheckpoints(sessionId) {
    const container = this.container.querySelector('#checkpoints-list');
    const actions = this.container.querySelector('#checkpoint-actions');
    container.innerHTML = '<div class="text-zinc-500 text-sm">Loading...</div>';

    try {
      const result = await window.GhostAPI.post('/api/journal/list', { session_id: sessionId });
      this.checkpoints = result.checkpoints || [];
      actions.style.display = this.checkpoints.length ? 'flex' : 'none';
      this.renderCheckpoints();
    } catch (err) {
      console.error('Failed to load checkpoints:', err);
      container.innerHTML = '<div class="text-red-400 text-sm">Failed to load checkpoints</div>';
    }
  },

  renderCheckpoints() {
    const container = this.container.querySelector('#checkpoints-list');
    if (!this.checkpoints.length) {
      container.innerHTML = '<div class="text-zinc-500 text-sm">No checkpoints for this session</div>';
      return;
    }

    container.innerHTML = this.checkpoints.map((cp, idx) => {
      const isAuto = (cp.label || '').startsWith('Auto:');
      return `
        <div class="p-3 rounded-lg cursor-pointer transition-colors bg-[#0a0a14] hover:bg-[#12121f] checkpoint-item"
             data-idx="${idx}">
          <div class="flex justify-between items-start">
            <div class="font-medium text-sm text-white truncate flex-1 mr-2">
              ${isAuto ? '<span class="text-xs text-zinc-500 mr-1">auto</span>' : ''}
              ${this.escapeHtml(cp.label || 'Untitled')}
            </div>
            <span class="text-xs text-zinc-500 flex-shrink-0">${this.formatTime(cp.timestamp)}</span>
          </div>
          <div class="flex gap-2 mt-2">
            ${cp.completed_count ? `<span class="text-xs px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">${cp.completed_count} done</span>` : ''}
            ${cp.pending_count ? `<span class="text-xs px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400">${cp.pending_count} pending</span>` : ''}
          </div>
          ${cp.goal_preview ? `<div class="text-xs text-zinc-400 truncate mt-2">${this.escapeHtml(cp.goal_preview)}</div>` : ''}
        </div>`;
    }).join('');

    container.querySelectorAll('.checkpoint-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.idx);
        this.showCheckpointDetail(this.checkpoints[idx]);
      });
    });
  },

  async showCheckpointDetail(checkpointSummary) {
    const detailContent = this.container.querySelector('#detail-content');
    detailContent.innerHTML = '<div class="text-zinc-500 text-sm">Loading checkpoint details...</div>';

    this.container.querySelector('#detail-modal').style.display = 'block';

    try {
      const result = await window.GhostAPI.post('/api/journal/detail', {
        journal_id: checkpointSummary.journal_id,
      });

      if (result.status !== 'ok' || !result.checkpoint) {
        detailContent.innerHTML = `<div class="text-red-400 text-sm">Failed to load details: ${this.escapeHtml(result.error || 'unknown error')}</div>`;
        return;
      }

      const cp = result.checkpoint;
      this.selectedCheckpoint = cp;

      detailContent.innerHTML = `
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-zinc-500">Session:</span>
            <span class="text-zinc-300 font-mono text-xs ml-1">${this.escapeHtml(cp.session_id || '')}</span>
          </div>
          <div>
            <span class="text-zinc-500">Time:</span>
            <span class="text-zinc-300 ml-1">${this.formatTime(cp.timestamp)}</span>
          </div>
        </div>

        ${cp.label ? `
          <div>
            <span class="text-zinc-500 text-sm">Label:</span>
            <span class="text-zinc-300 text-sm ml-1">${this.escapeHtml(cp.label)}</span>
          </div>
        ` : ''}

        ${cp.goal ? `
          <div>
            <div class="text-zinc-500 text-xs font-medium uppercase tracking-wide mb-1">Goal</div>
            <p class="text-zinc-300 text-sm bg-[#0a0a14] rounded-lg p-3">${this.escapeHtml(cp.goal)}</p>
          </div>
        ` : ''}

        ${cp.completed_steps && cp.completed_steps.length ? `
          <div>
            <div class="text-zinc-500 text-xs font-medium uppercase tracking-wide mb-1">Completed Steps</div>
            <ul class="space-y-1 bg-[#0a0a14] rounded-lg p-3">
              ${cp.completed_steps.map(s => `
                <li class="text-zinc-300 text-sm flex items-start gap-2">
                  <span class="text-emerald-400 mt-0.5 flex-shrink-0">&#10003;</span>
                  <span>${this.escapeHtml(s)}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}

        ${cp.pending_steps && cp.pending_steps.length ? `
          <div>
            <div class="text-zinc-500 text-xs font-medium uppercase tracking-wide mb-1">Pending Steps</div>
            <ul class="space-y-1 bg-[#0a0a14] rounded-lg p-3">
              ${cp.pending_steps.map(s => `
                <li class="text-zinc-300 text-sm flex items-start gap-2">
                  <span class="text-yellow-400 mt-0.5 flex-shrink-0">&#9675;</span>
                  <span>${this.escapeHtml(s)}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}

        ${cp.artifacts && Object.keys(cp.artifacts).length ? `
          <div>
            <div class="text-zinc-500 text-xs font-medium uppercase tracking-wide mb-1">Artifacts</div>
            <div class="bg-[#0a0a14] rounded-lg p-3 space-y-1">
              ${Object.entries(cp.artifacts).map(([k, v]) => `
                <div class="text-sm">
                  <span class="text-zinc-500">${this.escapeHtml(k)}:</span>
                  <span class="text-zinc-300 ml-1">${this.escapeHtml(String(v))}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <div class="text-xs text-zinc-600 pt-2 border-t border-white/5">
          ID: <span class="font-mono">${this.escapeHtml(cp.journal_id || '')}</span>
        </div>
      `;
    } catch (err) {
      console.error('Failed to load checkpoint detail:', err);
      detailContent.innerHTML = '<div class="text-red-400 text-sm">Failed to load checkpoint details</div>';
    }
  },

  hideDetailModal() {
    this.container.querySelector('#detail-modal').style.display = 'none';
    this.selectedCheckpoint = null;
  },

  async resumeCheckpoint() {
    if (!this.selectedCheckpoint) return;

    const btn = this.container.querySelector('#btn-resume');
    btn.disabled = true;
    btn.textContent = 'Loading...';

    try {
      const result = await window.GhostAPI.post('/api/journal/resume', {
        journal_id: this.selectedCheckpoint.journal_id,
      });

      if (result.status === 'ok') {
        window.GhostUtils && window.GhostUtils.toast('Checkpoint context loaded — switch to Chat to continue', 'success');
        this.hideDetailModal();
      } else {
        window.GhostUtils && window.GhostUtils.toast(result.error || 'Failed to resume', 'error');
      }
    } catch (err) {
      console.error('Failed to resume:', err);
      window.GhostUtils && window.GhostUtils.toast('Failed to resume checkpoint', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Resume in Chat';
    }
  },

  async exportSession(format) {
    if (!this.currentSession) {
      window.GhostUtils && window.GhostUtils.toast('Select a session first', 'error');
      return;
    }

    try {
      const result = await window.GhostAPI.post('/api/journal/export', {
        session_id: this.currentSession,
        format: format,
      });

      if (result.status === 'ok') {
        const mimeType = format === 'json' ? 'application/json' : 'text/markdown';
        const ext = format === 'json' ? 'json' : 'md';
        const blob = new Blob([result.content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `journal-${this.currentSession}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        window.GhostUtils && window.GhostUtils.toast('Export downloaded', 'success');
      } else {
        window.GhostUtils && window.GhostUtils.toast(result.error || 'Export failed', 'error');
      }
    } catch (err) {
      console.error('Export failed:', err);
      window.GhostUtils && window.GhostUtils.toast('Export failed', 'error');
    }
  },

  async exportCurrentCheckpoint() {
    if (!this.selectedCheckpoint) return;
    const data = JSON.stringify(this.selectedCheckpoint, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `checkpoint-${this.selectedCheckpoint.journal_id || 'export'}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    window.GhostUtils && window.GhostUtils.toast('Checkpoint exported', 'success');
  },

  updateStats() {
    this.container.querySelector('#journal-total-sessions').textContent = this.sessions.length;
    const totalCheckpoints = this.sessions.reduce((sum, s) => sum + (s.checkpoint_count || 0), 0);
    this.container.querySelector('#journal-total-checkpoints').textContent = totalCheckpoints;

    const lastActivity = this.sessions.length > 0 ? this.sessions[0].last_checkpoint : null;
    this.container.querySelector('#journal-last-activity').textContent = lastActivity
      ? this.formatTime(lastActivity)
      : '-';
  },

  formatTime(ts) {
    if (!ts) return 'N/A';
    if (window.GhostUtils && window.GhostUtils.formatDate) {
      return window.GhostUtils.formatDate(ts);
    }
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return ts;
    }
  },

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
};

export function render(container) {
  return window.GhostPages.durable_turn_journal.render(container);
}
