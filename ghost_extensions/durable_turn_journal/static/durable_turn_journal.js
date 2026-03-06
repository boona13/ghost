/**
 * Durable Turn Journal Dashboard Page
 * Manage checkpoint journals for long-running tasks
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
        <p class="page-desc">Checkpoint and resume long-running tasks</p>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div class="stat-card">
          <div class="stat-value" id="journal-total-sessions">-</div>
          <div class="stat-label">Active Sessions</div>
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
        <button class="btn btn-primary" id="btn-new-checkpoint">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
          </svg>
          New Checkpoint
        </button>
        <button class="btn btn-secondary" id="btn-refresh">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
          Refresh
        </button>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="stat-card">
          <h3 class="text-sm font-medium text-zinc-300 mb-4">Sessions</h3>
          <div id="sessions-list" class="space-y-2">
            <div class="text-zinc-500 text-sm">Loading...</div>
          </div>
        </div>
        
        <div class="stat-card">
          <h3 class="text-sm font-medium text-zinc-300 mb-4">Checkpoints</h3>
          <div id="checkpoints-list" class="space-y-2">
            <div class="text-zinc-500 text-sm">Select a session to view checkpoints</div>
          </div>
        </div>
      </div>
      
      <!-- New Checkpoint Modal -->
      <div id="checkpoint-modal" class="fixed inset-0 bg-black/60 hidden items-center justify-center z-50" style="display:none">
        <div class="stat-card w-full max-w-lg mx-4">
          <div class="flex justify-between items-center mb-6">
            <h3 class="text-lg font-medium text-white">Create Checkpoint</h3>
            <button class="text-zinc-400 hover:text-white" id="btn-close-modal">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
          
          <form id="checkpoint-form" class="space-y-4" style="width:100%">
            <div>
              <label class="form-label" for="input-session-id">Session ID</label>
              <input type="text" class="form-input" id="input-session-id" placeholder="e.g., task-123" style="width:100%;box-sizing:border-box">
            </div>
            <div>
              <label class="form-label" for="input-label">Label</label>
              <input type="text" class="form-input" id="input-label" placeholder="Checkpoint description" style="width:100%;box-sizing:border-box">
            </div>
            <div>
              <label class="form-label" for="input-goal">Goal</label>
              <textarea class="form-input" id="input-goal" rows="2" placeholder="Current objective" style="width:100%;box-sizing:border-box"></textarea>
            </div>
            <div>
              <label class="form-label" for="input-completed">Completed Steps (one per line)</label>
              <textarea class="form-input" id="input-completed" rows="3" style="width:100%;box-sizing:border-box"></textarea>
            </div>
            <div>
              <label class="form-label" for="input-pending">Pending Steps (one per line)</label>
              <textarea class="form-input" id="input-pending" rows="3" style="width:100%;box-sizing:border-box"></textarea>
            </div>
          </form>
          
          <div class="flex justify-end gap-3 mt-6">
            <button class="btn btn-ghost" id="btn-cancel">Cancel</button>
            <button class="btn btn-primary" id="btn-save-checkpoint">Create Checkpoint</button>
          </div>
        </div>
      </div>
      
      <!-- Checkpoint Detail Modal -->
      <div id="detail-modal" class="fixed inset-0 bg-black/60 hidden items-center justify-center z-50" style="display:none">
        <div class="stat-card w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-medium text-white">Checkpoint Details</h3>
            <button class="text-zinc-400 hover:text-white" id="btn-close-detail">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div id="detail-content" class="space-y-4">
            <div class="text-zinc-500 text-sm">Loading...</div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button class="btn btn-secondary" id="btn-export-json">Export JSON</button>
            <button class="btn btn-secondary" id="btn-export-md">Export Markdown</button>
            <button class="btn btn-primary" id="btn-resume">Resume</button>
          </div>
        </div>
      </div>
    `;
    
    this.bindEvents();
    this.loadSessions();
  },

  bindEvents() {
    document.getElementById('btn-refresh').addEventListener('click', () => this.loadSessions());
    document.getElementById('btn-new-checkpoint').addEventListener('click', () => this.showModal());
    document.getElementById('btn-close-modal').addEventListener('click', () => this.hideModal());
    document.getElementById('btn-cancel').addEventListener('click', () => this.hideModal());
    document.getElementById('btn-save-checkpoint').addEventListener('click', () => this.saveCheckpoint());
    document.getElementById('btn-close-detail').addEventListener('click', () => this.hideDetailModal());
    document.getElementById('btn-resume').addEventListener('click', () => this.resumeCheckpoint());
    document.getElementById('btn-export-json').addEventListener('click', () => this.exportSession('json'));
    document.getElementById('btn-export-md').addEventListener('click', () => this.exportSession('markdown'));
    
    document.getElementById('checkpoint-modal').addEventListener('click', (e) => {
      if (e.target.id === 'checkpoint-modal') this.hideModal();
    });
    document.getElementById('detail-modal').addEventListener('click', (e) => {
      if (e.target.id === 'detail-modal') this.hideDetailModal();
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
      document.getElementById('sessions-list').innerHTML = `
        <div class="text-red-400 text-sm">Failed to load sessions</div>
      `;
    }
  },

  renderSessions() {
    const container = document.getElementById('sessions-list');
    if (!this.sessions.length) {
      container.innerHTML = `<div class="text-zinc-500 text-sm">No sessions found</div>`;
      return;
    }
    
    container.innerHTML = this.sessions.map(s => `
      <div class="p-3 bg-surface-700 rounded cursor-pointer hover:bg-surface-600 transition-colors ${s.session_id === this.currentSession ? 'ring-1 ring-ghost-500' : ''}"
           data-session="${window.GhostUtils.escapeHtml(s.session_id)}">
        <div class="flex justify-between items-start">
          <div class="font-medium text-sm text-white truncate">${window.GhostUtils.escapeHtml(s.session_id)}</div>
          <span class="badge badge-blue text-xs">${s.checkpoint_count}</span>
        </div>
        <div class="text-xs text-zinc-500 mt-1">${window.GhostUtils.formatDate(s.last_checkpoint)}</div>
        <div class="text-xs text-zinc-400 truncate mt-1">${window.GhostUtils.escapeHtml(s.last_label || '')}</div>
      </div>
    `).join('');
    
    container.querySelectorAll('[data-session]').forEach(el => {
      el.addEventListener('click', () => {
        this.currentSession = el.dataset.session;
        this.renderSessions();
        this.loadCheckpoints(this.currentSession);
      });
    });
  },

  async loadCheckpoints(sessionId) {
    const container = document.getElementById('checkpoints-list');
    container.innerHTML = `<div class="text-zinc-500 text-sm">Loading...</div>`;
    
    try {
      const result = await window.GhostAPI.post('/api/journal/list', { session_id: sessionId });
      this.checkpoints = result.checkpoints || [];
      this.renderCheckpoints();
    } catch (err) {
      console.error('Failed to load checkpoints:', err);
      container.innerHTML = `<div class="text-red-400 text-sm">Failed to load checkpoints</div>`;
    }
  },

  renderCheckpoints() {
    const container = document.getElementById('checkpoints-list');
    if (!this.checkpoints.length) {
      container.innerHTML = `<div class="text-zinc-500 text-sm">No checkpoints for this session</div>`;
      return;
    }
    
    container.innerHTML = this.checkpoints.map((cp, idx) => `
      <div class="p-3 bg-surface-700 rounded cursor-pointer hover:bg-surface-600 transition-colors checkpoint-item"
           data-idx="${idx}">
        <div class="flex justify-between items-start">
          <div class="font-medium text-sm text-white">${window.GhostUtils.escapeHtml(cp.label)}</div>
          <span class="text-xs text-zinc-500">${window.GhostUtils.formatDate(cp.timestamp)}</span>
        </div>
        <div class="flex gap-2 mt-2">
          <span class="badge badge-green text-xs">${cp.completed_count} done</span>
          ${cp.pending_count > 0 ? `<span class="badge badge-yellow text-xs">${cp.pending_count} pending</span>` : ''}
        </div>
        ${cp.goal_preview ? `<div class="text-xs text-zinc-400 truncate mt-2">${window.GhostUtils.escapeHtml(cp.goal_preview)}</div>` : ''}
      </div>
    `).join('');
    
    container.querySelectorAll('.checkpoint-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.idx);
        this.showCheckpointDetail(this.checkpoints[idx]);
      });
    });
  },

  async showCheckpointDetail(checkpointSummary) {
    const detailContent = document.getElementById('detail-content');
    detailContent.innerHTML = `<div class="text-zinc-500 text-sm">Loading checkpoint details...</div>`;

    document.getElementById('detail-modal').style.display = 'flex';
    document.getElementById('detail-modal').classList.remove('hidden');
    document.getElementById('detail-modal').classList.add('flex');

    try {
      const result = await window.GhostAPI.post('/api/journal/detail', {
        journal_id: checkpointSummary.journal_id,
      });

      if (result.status !== 'ok' || !result.checkpoint) {
        detailContent.innerHTML = `<div class="text-red-400 text-sm">Failed to load details: ${window.GhostUtils.escapeHtml(result.error || 'unknown error')}</div>`;
        return;
      }

      const cp = result.checkpoint;
      this.selectedCheckpoint = cp;

      detailContent.innerHTML = `
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-zinc-500">ID:</span>
            <span class="text-zinc-300 font-mono text-xs ml-1">${window.GhostUtils.escapeHtml(cp.journal_id || '')}</span>
          </div>
          <div>
            <span class="text-zinc-500">Timestamp:</span>
            <span class="text-zinc-300 ml-1">${window.GhostUtils.formatDate(cp.timestamp)}</span>
          </div>
        </div>
        
        ${cp.label ? `
          <div>
            <span class="text-zinc-500 text-sm">Label:</span>
            <span class="text-zinc-300 text-sm ml-1">${window.GhostUtils.escapeHtml(cp.label)}</span>
          </div>
        ` : ''}
        
        ${cp.goal ? `
          <div>
            <div class="text-zinc-500 text-sm mb-1">Goal</div>
            <p class="text-zinc-300 text-sm bg-surface-700 rounded p-3">${window.GhostUtils.escapeHtml(cp.goal)}</p>
          </div>
        ` : ''}
        
        ${cp.completed_steps?.length ? `
          <div>
            <div class="text-zinc-500 text-sm mb-1">Completed Steps</div>
            <ul class="space-y-1 bg-surface-700 rounded p-3">
              ${cp.completed_steps.map(s => `
                <li class="text-zinc-300 text-sm flex items-start gap-2">
                  <span class="text-emerald-400 mt-0.5">&#10003;</span>
                  <span>${window.GhostUtils.escapeHtml(s)}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}
        
        ${cp.pending_steps?.length ? `
          <div>
            <div class="text-zinc-500 text-sm mb-1">Pending Steps</div>
            <ul class="space-y-1 bg-surface-700 rounded p-3">
              ${cp.pending_steps.map(s => `
                <li class="text-zinc-300 text-sm flex items-start gap-2">
                  <span class="text-yellow-400 mt-0.5">&#9675;</span>
                  <span>${window.GhostUtils.escapeHtml(s)}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}

        ${cp.artifacts && Object.keys(cp.artifacts).length ? `
          <div>
            <div class="text-zinc-500 text-sm mb-1">Artifacts</div>
            <div class="bg-surface-700 rounded p-3 space-y-1">
              ${Object.entries(cp.artifacts).map(([k, v]) => `
                <div class="text-sm">
                  <span class="text-zinc-400">${window.GhostUtils.escapeHtml(k)}:</span>
                  <span class="text-zinc-300 ml-1">${window.GhostUtils.escapeHtml(String(v))}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      `;
    } catch (err) {
      console.error('Failed to load checkpoint detail:', err);
      detailContent.innerHTML = `<div class="text-red-400 text-sm">Failed to load checkpoint details</div>`;
    }
  },

  hideDetailModal() {
    document.getElementById('detail-modal').style.display = 'none';
    document.getElementById('detail-modal').classList.add('hidden');
    document.getElementById('detail-modal').classList.remove('flex');
    this.selectedCheckpoint = null;
  },

  showModal() {
    const modal = document.getElementById('checkpoint-modal');
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    if (this.currentSession) {
      document.getElementById('input-session-id').value = this.currentSession;
    }
  },

  hideModal() {
    const modal = document.getElementById('checkpoint-modal');
    modal.style.display = 'none';
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.getElementById('input-session-id').value = '';
    document.getElementById('input-label').value = '';
    document.getElementById('input-goal').value = '';
    document.getElementById('input-completed').value = '';
    document.getElementById('input-pending').value = '';
  },

  async saveCheckpoint() {
    const sessionId = document.getElementById('input-session-id').value.trim();
    const label = document.getElementById('input-label').value.trim();
    const goal = document.getElementById('input-goal').value.trim();
    const completedText = document.getElementById('input-completed').value;
    const pendingText = document.getElementById('input-pending').value;
    
    if (!sessionId) {
      window.GhostUtils.toast('Session ID is required', 'error');
      return;
    }
    
    const completed = completedText.split('\n').map(s => s.trim()).filter(Boolean);
    const pending = pendingText.split('\n').map(s => s.trim()).filter(Boolean);
    
    try {
      const result = await window.GhostAPI.post('/api/journal/checkpoint', {
        session_id: sessionId,
        label: label || undefined,
        goal: goal || undefined,
        completed_steps: completed,
        pending_steps: pending,
      });
      
      if (result.status === 'ok') {
        window.GhostUtils.toast('Checkpoint created', 'success');
        this.hideModal();
        this.currentSession = sessionId;
        this.loadSessions();
        this.loadCheckpoints(sessionId);
      } else {
        window.GhostUtils.toast(result.error || 'Failed to create checkpoint', 'error');
      }
    } catch (err) {
      console.error('Failed to create checkpoint:', err);
      window.GhostUtils.toast('Failed to create checkpoint', 'error');
    }
  },

  async resumeCheckpoint() {
    if (!this.selectedCheckpoint) return;
    
    try {
      const result = await window.GhostAPI.post('/api/journal/resume', {
        journal_id: this.selectedCheckpoint.journal_id,
      });
      
      if (result.status === 'ok') {
        window.GhostUtils.toast('Checkpoint loaded — ready to resume', 'success');
        this.hideDetailModal();
      } else {
        window.GhostUtils.toast(result.error || 'Failed to resume', 'error');
      }
    } catch (err) {
      console.error('Failed to resume:', err);
      window.GhostUtils.toast('Failed to resume checkpoint', 'error');
    }
  },

  async exportSession(format) {
    if (!this.currentSession) {
      window.GhostUtils.toast('Select a session first', 'error');
      return;
    }
    
    try {
      const result = await window.GhostAPI.post('/api/journal/export', {
        session_id: this.currentSession,
        format: format,
      });
      
      if (result.status === 'ok') {
        const blob = new Blob([result.content], { type: format === 'json' ? 'application/json' : 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `journal-${this.currentSession}.${format === 'json' ? 'json' : 'md'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        window.GhostUtils.toast('Export downloaded', 'success');
      } else {
        window.GhostUtils.toast(result.error || 'Export failed', 'error');
      }
    } catch (err) {
      console.error('Export failed:', err);
      window.GhostUtils.toast('Export failed', 'error');
    }
  },

  updateStats() {
    document.getElementById('journal-total-sessions').textContent = this.sessions.length;
    const totalCheckpoints = this.sessions.reduce((sum, s) => sum + (s.checkpoint_count || 0), 0);
    document.getElementById('journal-total-checkpoints').textContent = totalCheckpoints;
    
    const lastActivity = this.sessions.length > 0 
      ? this.sessions[0].last_checkpoint 
      : null;
    document.getElementById('journal-last-activity').textContent = lastActivity 
      ? window.GhostUtils.formatDate(lastActivity, { relative: true }) 
      : '-';
  },
};

export function render(container) {
  return window.GhostPages.durable_turn_journal.render(container);
}
