/**
 * Grok Video Extension Dashboard Page
 * 
 * View video generation history and configure API key.
 */

export function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1 class="text-xl font-bold text-white">Grok Video</h1>
      <p class="page-desc">Generate videos from text prompts using xAI's Grok Imagine Video API</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
      <!-- API Key Card -->
      <div class="stat-card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-medium text-zinc-300">API Configuration</h3>
          <span id="api-status" class="badge badge-zinc">Not Configured</span>
        </div>
        <div class="form-group mb-4">
          <label class="form-label">xAI API Key</label>
          <input type="password" id="api-key-input" class="form-input" 
                 placeholder="Enter your xAI API key (from console.x.ai)" />
          <p class="text-xs text-zinc-500 mt-1">
            Get your key from <a href="https://console.x.ai" target="_blank" class="text-ghost-400 hover:underline">console.x.ai</a>. 
            OpenRouter keys will NOT work.
          </p>
        </div>
        <div class="flex gap-2">
          <button id="save-key-btn" class="btn btn-primary">Save Key</button>
          <button id="test-key-btn" class="btn btn-secondary">Test Connection</button>
        </div>
      </div>

      <!-- Quick Generate Card -->
      <div class="stat-card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-medium text-zinc-300">Quick Generate</h3>
        </div>
        <div class="form-group mb-3">
          <label class="form-label">Prompt</label>
          <textarea id="quick-prompt" class="form-input" rows="3" 
                    placeholder="Describe the video you want to generate..."></textarea>
        </div>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div class="form-group">
            <label class="form-label">Aspect Ratio</label>
            <select id="quick-ratio" class="form-input">
              <option value="16:9">16:9 (Landscape)</option>
              <option value="9:16">9:16 (Portrait)</option>
              <option value="1:1">1:1 (Square)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Count</label>
            <select id="quick-count" class="form-input">
              <option value="1">1 video</option>
              <option value="2">2 videos</option>
              <option value="3">3 videos</option>
              <option value="4">4 videos</option>
            </select>
          </div>
        </div>
        <button id="quick-generate-btn" class="btn btn-primary w-full">
          Generate Video
        </button>
      </div>
    </div>

    <!-- History Section -->
    <div class="stat-card">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-medium text-zinc-300">Generation History</h3>
        <div class="flex gap-2">
          <button id="refresh-history-btn" class="btn btn-ghost btn-sm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
              <path d="M16 21h5v-5"/>
            </svg>
            Refresh
          </button>
          <button id="clear-history-btn" class="btn btn-danger btn-sm">Clear</button>
        </div>
      </div>
      <div id="history-container" class="space-y-3">
        <div class="text-center text-zinc-500 py-8">
          <p>No videos generated yet.</p>
          <p class="text-xs mt-1">Videos will appear here when you use the grok_video tool or Quick Generate.</p>
        </div>
      </div>
    </div>
  `;

  // Load initial state
  loadApiStatus();
  loadHistory();

  // Bind events
  container.querySelector('#save-key-btn').addEventListener('click', saveApiKey);
  container.querySelector('#test-key-btn').addEventListener('click', testConnection);
  container.querySelector('#quick-generate-btn').addEventListener('click', quickGenerate);
  container.querySelector('#refresh-history-btn').addEventListener('click', loadHistory);
  container.querySelector('#clear-history-btn').addEventListener('click', clearHistory);
}

async function loadApiStatus() {
  try {
    const resp = await fetch('/api/grok_video/settings');
    const data = await resp.json();
    const hasKey = data.xai_api_key && data.xai_api_key.length > 0;
    const statusEl = document.getElementById('api-status');
    if (hasKey) {
      statusEl.textContent = 'Configured';
      statusEl.className = 'badge badge-green';
    } else {
      statusEl.textContent = 'Not Configured';
      statusEl.className = 'badge badge-zinc';
    }
  } catch (err) {
    console.error('Failed to load API status:', err);
  }
}

async function saveApiKey() {
  const input = document.getElementById('api-key-input');
  const key = input.value.trim();
  
  if (!key) {
    showToast('Please enter an API key', 'error');
    return;
  }
  
  try {
    const resp = await fetch('/api/grok_video/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xai_api_key: key }),
    });
    
    if (resp.ok) {
      showToast('API key saved', 'success');
      input.value = '';
      loadApiStatus();
    } else {
      showToast('Failed to save API key', 'error');
    }
  } catch (err) {
    showToast('Error saving API key', 'error');
  }
}

async function testConnection() {
  try {
    const resp = await fetch('/api/grok_video/test', { method: 'POST' });
    const data = await resp.json();
    
    if (data.success) {
      showToast('Connection successful', 'success');
    } else {
      showToast(data.error || 'Connection failed', 'error');
    }
  } catch (err) {
    showToast('Error testing connection', 'error');
  }
}

async function quickGenerate() {
  const prompt = document.getElementById('quick-prompt').value.trim();
  const ratio = document.getElementById('quick-ratio').value;
  const count = parseInt(document.getElementById('quick-count').value);
  
  if (!prompt) {
    showToast('Please enter a prompt', 'error');
    return;
  }
  
  const btn = document.getElementById('quick-generate-btn');
  btn.disabled = true;
  btn.textContent = 'Generating...';
  
  try {
    const resp = await fetch('/api/grok_video/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, aspect_ratio: ratio, n: count }),
    });
    
    const data = await resp.json();
    
    if (data.success) {
      showToast(`Generated ${data.videos?.length || 0} video(s)`, 'success');
      document.getElementById('quick-prompt').value = '';
      loadHistory();
    } else {
      showToast(data.error || 'Generation failed', 'error');
    }
  } catch (err) {
    showToast('Error generating video', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Video';
  }
}

async function loadHistory() {
  try {
    const resp = await fetch('/api/grok_video/history');
    const data = await resp.json();
    renderHistory(data.history || []);
  } catch (err) {
    console.error('Failed to load history:', err);
  }
}

function renderHistory(history) {
  const container = document.getElementById('history-container');
  
  if (!history || history.length === 0) {
    container.innerHTML = `
      <div class="text-center text-zinc-500 py-8">
        <p>No videos generated yet.</p>
        <p class="text-xs mt-1">Videos will appear here when you use the grok_video tool or Quick Generate.</p>
      </div>
    `;
    return;
  }
  
  container.innerHTML = history.slice().reverse().map(item => {
    const time = new Date(item.timestamp).toLocaleString();
    const statusBadge = item.success 
      ? '<span class="badge badge-green">Success</span>'
      : '<span class="badge badge-red">Failed</span>';
    
    const videosHtml = item.videos?.map((v, i) => `
      <div class="mt-2 p-2 bg-surface-700 rounded">
        <div class="flex items-center gap-2">
          <span class="text-xs text-zinc-400">Video ${i + 1}</span>
          <a href="${v.url}" target="_blank" class="text-xs text-ghost-400 hover:underline truncate">
            ${v.url}
          </a>
        </div>
      </div>
    `).join('') || '';
    
    const errorHtml = item.error 
      ? `<div class="mt-2 text-xs text-red-400">${escapeHtml(item.error)}</div>`
      : '';
    
    return `
      <div class="p-3 bg-surface-700 rounded border border-zinc-700">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs text-zinc-500">${time}</span>
          ${statusBadge}
        </div>
        <div class="text-sm text-zinc-300 mb-2">${escapeHtml(item.prompt)}</div>
        <div class="flex gap-2 text-xs text-zinc-500">
          <span>Ratio: ${item.aspect_ratio}</span>
          <span>•</span>
          <span>Count: ${item.n}</span>
        </div>
        ${videosHtml}
        ${errorHtml}
      </div>
    `;
  }).join('');
}

async function clearHistory() {
  if (!confirm('Clear all video generation history?')) return;
  
  try {
    await fetch('/api/grok_video/history', { method: 'DELETE' });
    loadHistory();
    showToast('History cleared', 'success');
  } catch (err) {
    showToast('Error clearing history', 'error');
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showToast(message, type = 'info') {
  if (window.GhostUtils?.toast) {
    window.GhostUtils.toast(message, type);
  } else {
    alert(message);
  }
}
