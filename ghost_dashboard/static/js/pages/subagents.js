/** Sub-Agents page — Manage and monitor sub-agent instances */

import { toast } from '../utils.js';

const STATUS_COLORS = {
  pending: 'badge-yellow',
  running: 'badge-blue',
  completed: 'badge-green',
  failed: 'badge-red',
  cancelled: 'badge-zinc',
};

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  container.innerHTML = `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="page-header">Sub-Agents</h1>
          <p class="page-desc">Spawn isolated workers for parallel task execution</p>
        </div>
        <button id="btn-spawn" class="btn btn-primary">Spawn Sub-Agent</button>
      </div>

      <div id="agents-list" class="grid gap-4">
        <div class="text-zinc-500 text-sm">Loading...</div>
      </div>
    </div>

    <!-- Spawn Modal -->
    <div id="spawn-modal" class="fixed inset-0 z-50 hidden">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm modal-backdrop"></div>
      <div class="absolute inset-0 flex items-center justify-center p-4">
        <div class="stat-card w-full max-w-lg border border-purple-500/30">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-white">Spawn Sub-Agent</h3>
            <button class="modal-close text-zinc-400 hover:text-white">&#xd7;</button>
          </div>
          <form id="spawn-form" class="space-y-4">
            <div>
              <label class="form-label">Task Description</label>
              <textarea id="task-input" class="form-input" rows="3" placeholder="Describe the task for this sub-agent..." required></textarea>
            </div>
            <div>
              <label class="form-label">Skills (comma-separated)</label>
              <input type="text" id="skills-input" class="form-input" placeholder="e.g., research, coding, analysis">
              <p class="text-xs text-zinc-500 mt-1">Assign skills to filter available tools</p>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="form-label">Max Steps</label>
                <input type="number" id="steps-input" class="form-input" value="50" min="1" max="200">
              </div>
              <div>
                <label class="form-label">Timeout (seconds)</label>
                <input type="number" id="timeout-input" class="form-input" value="300" min="10" max="3600">
              </div>
            </div>
            <div class="flex justify-end gap-2 pt-4">
              <button type="button" class="modal-close btn btn-ghost">Cancel</button>
              <button type="submit" class="btn btn-primary">Spawn</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- Result Modal -->
    <div id="result-modal" class="fixed inset-0 z-50 hidden">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm modal-backdrop"></div>
      <div class="absolute inset-0 flex items-center justify-center p-4">
        <div class="stat-card w-full max-w-3xl max-h-[80vh] flex flex-col border border-purple-500/30">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-white">Sub-Agent Result</h3>
            <button class="modal-close text-zinc-400 hover:text-white">&#xd7;</button>
          </div>
          <div id="result-content" class="overflow-auto flex-1 text-sm text-zinc-300 whitespace-pre-wrap font-mono bg-black/20 rounded p-4"></div>
        </div>
      </div>
    </div>
  `;

  // Modal handlers
  const spawnModal = container.querySelector('#spawn-modal');
  const resultModal = container.querySelector('#result-modal');
  
  function openModal(modal) {
    modal.classList.remove('hidden');
  }
  
  function closeModal(modal) {
    modal.classList.add('hidden');
  }

  container.querySelector('#btn-spawn').addEventListener('click', () => openModal(spawnModal));
  
  container.querySelectorAll('.modal-close, .modal-backdrop').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target === el) {
        closeModal(el.closest('.fixed'));
      }
    });
  });

  // Escape key to close modals
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal(spawnModal);
      closeModal(resultModal);
    }
  });

  // Spawn form
  container.querySelector('#spawn-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const task = container.querySelector('#task-input').value.trim();
    const skillsStr = container.querySelector('#skills-input').value.trim();
    const maxSteps = parseInt(container.querySelector('#steps-input').value) || 50;
    const timeout = parseInt(container.querySelector('#timeout-input').value) || 300;
    
    const skills = skillsStr ? skillsStr.split(',').map(s => s.trim()).filter(Boolean) : [];
    
    try {
      const result = await api.post('/api/chat/message', {
        message: `Spawn a sub-agent with task: ${task}`,
        tool_calls: [{
          name: 'spawn_subagent',
          arguments: { task, skills, max_steps: maxSteps, timeout_seconds: timeout }
        }]
      });
      
      toast.success('Sub-agent spawned');
      closeModal(spawnModal);
      container.querySelector('#spawn-form').reset();
      loadAgents();
      
    } catch (err) {
      toast.error(`Failed to spawn: ${err.message}`);
    }
  });

  // Load and render agents
  async function loadAgents() {
    try {
      const data = await api.get('/api/subagents');
      const listEl = container.querySelector('#agents-list');
      
      if (!data.agents || data.agents.length === 0) {
        listEl.innerHTML = `
          <div class="stat-card text-center py-12">
            <div class="text-zinc-500 mb-2">No sub-agents running</div>
            <div class="text-sm text-zinc-600">Spawn a sub-agent to delegate tasks</div>
          </div>
        `;
        return;
      }

      // Sort by created_at descending
      const agents = data.agents.sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
      );

      listEl.innerHTML = agents.map(agent => {
        const statusClass = STATUS_COLORS[agent.status] || 'badge-zinc';
        const duration = agent.result?.duration_ms 
          ? `${(agent.result.duration_ms / 1000).toFixed(1)}s`
          : '-';
        const toolCalls = agent.result?.tool_calls || 0;
        
        return `
          <div class="stat-card" data-id="${agent.id}">
            <div class="flex items-start justify-between">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-3 mb-2">
                  <span class="badge ${statusClass}">${agent.status}</span>
                  <span class="text-xs text-zinc-500 font-mono">${agent.id}</span>
                </div>
                <div class="text-zinc-300 text-sm truncate">${u.escapeHtml(agent.config.task)}</div>
                ${agent.config.skills?.length ? `
                  <div class="flex gap-1 mt-2">
                    ${agent.config.skills.map(s => `<span class="badge badge-purple">${s}</span>`).join('')}
                  </div>
                ` : ''}
              </div>
              <div class="flex items-center gap-2 ml-4">
                ${agent.status === 'running' ? `
                  <button class="btn-cancel btn btn-danger btn-sm" data-id="${agent.id}">Cancel</button>
                ` : ''}
                ${agent.result ? `
                  <button class="btn-result btn btn-ghost btn-sm" data-id="${agent.id}">View Result</button>
                ` : ''}
                ${['completed', 'failed', 'cancelled'].includes(agent.status) ? `
                  <button class="btn-delete btn btn-ghost btn-sm" data-id="${agent.id}">Remove</button>
                ` : ''}
              </div>
            </div>
            <div class="flex items-center gap-6 mt-3 text-xs text-zinc-500">
              <span>Duration: ${duration}</span>
              <span>Tools: ${toolCalls}</span>
              <span>Steps: ${agent.config.max_steps}</span>
              <span>Created: ${u.formatDate(agent.created_at)}</span>
            </div>
          </div>
        `;
      }).join('');

      // Bind action handlers
      listEl.querySelectorAll('.btn-cancel').forEach(btn => {
        btn.addEventListener('click', async () => {
          const id = btn.dataset.id;
          try {
            await api.post(`/api/subagents/${id}/cancel`);
            toast.success('Sub-agent cancelled');
            loadAgents();
          } catch (err) {
            toast.error(`Failed to cancel: ${err.message}`);
          }
        });
      });

      listEl.querySelectorAll('.btn-result').forEach(btn => {
        btn.addEventListener('click', async () => {
          const id = btn.dataset.id;
          try {
            const data = await api.get(`/api/subagents/${id}`);
            const result = data.agent?.result;
            if (result) {
              const content = result.success 
                ? result.output || 'No output'
                : `Error: ${result.error || 'Unknown error'}`;
              container.querySelector('#result-content').textContent = content;
              openModal(resultModal);
            }
          } catch (err) {
            toast.error(`Failed to load result: ${err.message}`);
          }
        });
      });

      listEl.querySelectorAll('.btn-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
          const id = btn.dataset.id;
          try {
            await api.del(`/api/subagents/${id}`);
            toast.success('Sub-agent removed');
            loadAgents();
          } catch (err) {
            toast.error(`Failed to remove: ${err.message}`);
          }
        });
      });

    } catch (err) {
      container.querySelector('#agents-list').innerHTML = `
        <div class="stat-card text-center py-8 text-red-400">
          Failed to load sub-agents: ${err.message}
        </div>
      `;
    }
  }

  // Initial load
  await loadAgents();
  
  // Auto-refresh every 5 seconds
  const interval = setInterval(loadAgents, 5000);
  
  // Cleanup on page change
  return () => {
    clearInterval(interval);
  };
}
