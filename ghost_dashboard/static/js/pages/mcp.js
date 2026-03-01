/** MCP (Model Context Protocol) Dashboard Page */

import { api, toast } from '../utils.js';

let refreshTimer = null;
let selectedServer = null;
let toolCache = [];

function renderHeader() {
  return `
    <div class="mb-6">
      <h1 class="page-header">Model Context Protocol</h1>
      <p class="page-desc">Connect to MCP servers and use external tools</p>
    </div>
  `;
}

function renderServerCard(server) {
  const statusClass = server.connected 
    ? 'badge badge-green' 
    : (server.enabled ? 'badge badge-zinc' : 'badge badge-red');
  const statusText = server.connected 
    ? 'Connected' 
    : (server.enabled ? 'Disconnected' : 'Disabled');
  
  return `
    <div class="stat-card p-4 cursor-pointer hover:border-ghost-500/50 transition-colors ${selectedServer === server.name ? 'border-ghost-500' : ''}" 
         data-server="${server.name}" onclick="window.selectMcpServer('${server.name}')">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-semibold text-white">${server.name}</h3>
        <span class="${statusClass}">${statusText}</span>
      </div>
      <div class="text-xs text-zinc-500 font-mono truncate mb-2">${server.command} ${server.args.join(' ')}</div>
      <div class="flex items-center justify-between text-xs">
        <span class="text-zinc-400">${server.tool_count} tools</span>
        <div class="flex gap-2">
          ${server.connected ? `
            <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); window.disconnectMcpServer('${server.name}')">Disconnect</button>
          ` : server.enabled ? `
            <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); window.connectMcpServer('${server.name}')">Connect</button>
          ` : ''}
        </div>
      </div>
    </div>
  `;
}

function renderAddServerForm() {
  return `
    <div class="stat-card p-4">
      <h3 class="text-sm font-semibold text-white mb-4">Add MCP Server</h3>
      <form id="mcp-add-form" class="space-y-3">
        <div>
          <label class="form-label">Server Name</label>
          <input type="text" name="name" class="form-input w-full" placeholder="e.g., filesystem" required 
                 pattern="[a-zA-Z0-9_-]+" title="Letters, numbers, underscores, hyphens only">
        </div>
        <div>
          <label class="form-label">Command</label>
          <input type="text" name="command" class="form-input w-full" placeholder="e.g., npx or /usr/local/bin/mcp-server" required>
        </div>
        <div>
          <label class="form-label">Arguments (space-separated)</label>
          <input type="text" name="args" class="form-input w-full" placeholder="-y @modelcontextprotocol/server-filesystem /path/to/allow">
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" name="enabled" checked class="form-checkbox">
          <label class="text-sm text-zinc-400">Enabled</label>
        </div>
        <button type="submit" class="btn btn-primary w-full">Add Server</button>
      </form>
    </div>
  `;
}

function renderToolModal() {
  return `
    <div id="mcp-tool-modal" class="fixed inset-0 bg-black/70 hidden items-center justify-center z-50" onclick="if(event.target===this)window.closeMcpToolModal()">
      <div class="bg-zinc-900 border border-zinc-700 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-white" id="tool-modal-title">Tool Details</h3>
          <button onclick="window.closeMcpToolModal()" class="text-zinc-400 hover:text-white">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div id="tool-modal-content" class="space-y-4"></div>
      </div>
    </div>
  `;
}

function renderToolCard(tool) {
  return `
    <div class="stat-card p-3 cursor-pointer hover:border-ghost-500/50" onclick="window.showMcpToolDetails('${tool.name}')">
      <div class="flex items-center justify-between">
        <h4 class="text-sm font-medium text-white">${tool.name}</h4>
        <span class="text-xs text-zinc-500">${tool.server || 'unknown'}</span>
      </div>
      <p class="text-xs text-zinc-400 mt-1 truncate">${tool.description || 'No description'}</p>
    </div>
  `;
}

export function render() {
  const el = document.createElement('div');
  el.innerHTML = `
    ${renderHeader()}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-1 space-y-4">
        <div id="mcp-server-list" class="space-y-3">
          <div class="text-zinc-500 text-sm">Loading servers...</div>
        </div>
        ${renderAddServerForm()}
      </div>
      <div class="lg:col-span-2">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-white">Tools</h2>
          <button onclick="window.refreshMcpTools()" class="btn btn-sm btn-secondary">Refresh</button>
        </div>
        <div id="mcp-tool-list" class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="text-zinc-500 text-sm">Select a server to view tools</div>
        </div>
      </div>
    </div>
    ${renderToolModal()}
  `;
  
  // Setup auto-refresh
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(loadServers, 10000);
  
  // Initial load
  setTimeout(loadServers, 0);
  
  // Setup form handler
  setTimeout(() => {
    const form = el.querySelector('#mcp-add-form');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const args = formData.get('args') || '';
        const payload = {
          name: formData.get('name'),
          command: formData.get('command'),
          args: args, // Send as string, backend handles conversion
          enabled: formData.has('enabled')
        };
        
        try {
          const res = await api.post('/api/mcp/config', payload);
          if (res.ok) {
            toast.success('Server added');
            form.reset();
            loadServers();
          } else {
            toast.error(res.error || 'Failed to add server');
          }
        } catch (err) {
          toast.error(err.message);
        }
      });
    }
  }, 0);
  
  return el;
}

async function loadServers() {
  try {
    const data = await api.get('/api/mcp/servers');
    const container = document.getElementById('mcp-server-list');
    if (!container) return;
    
    if (!data.servers || data.servers.length === 0) {
      container.innerHTML = '<div class="text-zinc-500 text-sm">No servers configured</div>';
      return;
    }
    
    container.innerHTML = data.servers.map(renderServerCard).join('');
    
    // Load tools for selected server
    if (selectedServer) {
      loadTools(selectedServer);
    }
  } catch (err) {
    console.error('Failed to load MCP servers:', err);
  }
}

async function loadTools(serverName) {
  try {
    const data = await api.get(`/api/mcp/tools?server_name=${encodeURIComponent(serverName)}`);
    toolCache = data.tools || [];
    const container = document.getElementById('mcp-tool-list');
    if (!container) return;
    
    if (toolCache.length === 0) {
      container.innerHTML = '<div class="text-zinc-500 text-sm">No tools available</div>';
      return;
    }
    
    container.innerHTML = toolCache.map(renderToolCard).join('');
  } catch (err) {
    console.error('Failed to load MCP tools:', err);
  }
}

// Global functions for onclick handlers
window.selectMcpServer = (name) => {
  selectedServer = name;
  document.querySelectorAll('[data-server]').forEach(el => {
    el.classList.toggle('border-ghost-500', el.dataset.server === name);
  });
  loadTools(name);
};

window.connectMcpServer = async (name) => {
  try {
    const res = await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/connect`, {});
    if (res.ok) {
      toast.success(`Connected to ${name}`);
      loadServers();
    } else {
      toast.error(res.error || 'Connection failed');
    }
  } catch (err) {
    toast.error(err.message);
  }
};

window.disconnectMcpServer = async (name) => {
  try {
    const res = await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/disconnect`, {});
    if (res.ok) {
      toast.success(`Disconnected from ${name}`);
      loadServers();
    } else {
      toast.error(res.error || 'Disconnect failed');
    }
  } catch (err) {
    toast.error(err.message);
  }
};

window.refreshMcpTools = () => {
  if (selectedServer) loadTools(selectedServer);
};

window.showMcpToolDetails = (toolName) => {
  const tool = toolCache.find(t => t.name === toolName);
  if (!tool) return;
  
  const modal = document.getElementById('mcp-tool-modal');
  const title = document.getElementById('tool-modal-title');
  const content = document.getElementById('tool-modal-content');
  
  title.textContent = tool.name;
  content.innerHTML = `
    <div class="text-sm text-zinc-300">${tool.description || 'No description'}</div>
    <div class="mt-4">
      <h4 class="text-sm font-semibold text-white mb-2">Schema</h4>
      <pre class="bg-zinc-950 p-3 rounded text-xs text-zinc-400 overflow-auto">${JSON.stringify(tool.inputSchema || {}, null, 2)}</pre>
    </div>
  `;
  
  modal.classList.remove('hidden');
  modal.classList.add('flex');
};

window.closeMcpToolModal = () => {
  const modal = document.getElementById('mcp-tool-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
};

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
});checkbox" name="enabled" checked class="rounded border-zinc-600 bg-surface-900 text-ghost-500">
          <label class="text-xs text-zinc-400">Enabled</label>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="btn btn-primary">Add Server</button>
          <button type="button" class="btn btn-ghost" onclick="window.toggleAddForm()">Cancel</button>
        </div>
      </form>
    </div>
  `;
}

function renderServersList(servers) {
  if (!servers || servers.length === 0) {
    return `
      <div class="stat-card p-8 text-center">
        <div class="text-zinc-500 mb-4">
          <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
          </svg>
          <p>No MCP servers configured</p>
        </div>
        <button class="btn btn-primary" onclick="window.toggleAddForm()">Add Your First Server</button>
      </div>
    `;
  }

  return `
    <div class="grid gap-3" id="mcp-servers-grid">
      ${servers.map(renderServerCard).join('')}
    </div>
    <div class="mt-4">
      <button class="btn btn-secondary" onclick="window.toggleAddForm()">+ Add Server</button>
    </div>
  `;
}

function renderToolCard(tool) {
  const schema = tool.inputSchema || {};
  const properties = schema.properties || {};
  const required = schema.required || [];
  
  return `
    <div class="stat-card p-3">
      <div class="flex items-center justify-between mb-2">
        <h4 class="text-xs font-semibold text-ghost-400">${tool.name}</h4>
        ${tool._server ? `<span class="badge badge-blue text-[10px]">${tool._server}</span>` : ''}
      </div>
      <p class="text-xs text-zinc-400 mb-2">${tool.description || 'No description'}</p>
      ${Object.keys(properties).length > 0 ? `
        <div class="text-[10px] text-zinc-500 font-mono">
          ${Object.entries(properties).map(([key, prop]) => `
            <span class="${required.includes(key) ? 'text-amber-400' : 'text-zinc-500'}">${key}${required.includes(key) ? '*' : ''}</span>
          `).join(', ')}
        </div>
      ` : ''}
    </div>
  `;
}

function renderToolsSection() {
  if (!selectedServer) {
    return `
      <div class="stat-card p-8 text-center h-full flex items-center justify-center">
        <div class="text-zinc-600">
          <svg class="w-12 h-12 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
          <p class="text-sm">Select a server to view tools</p>
        </div>
      </div>
    `;
  }

  const serverTools = toolCache.filter(t => !selectedServer || t._server === selectedServer);
  
  if (serverTools.length === 0) {
    return `
      <div class="stat-card p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-semibold text-white">Tools: ${selectedServer}</h3>
          <button class="btn btn-sm btn-ghost" onclick="window.refreshTools()">Refresh</button>
        </div>
        <div class="text-zinc-500 text-center py-8">
          ${selectedServer ? `
            <p>No tools available</p>
            <button class="btn btn-sm btn-primary mt-3" onclick="window.connectMcpServer('${selectedServer}')">Connect to Load Tools</button>
          ` : '<p>Select a connected server to view tools</p>'}
        </div>
      </div>
    `;
  }

  return `
    <div class="stat-card p-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-semibold text-white">Tools: ${selectedServer}</h3>
        <div class="flex gap-2">
          <span class="text-xs text-zinc-500">${serverTools.length} tools</span>
          <button class="btn btn-sm btn-ghost" onclick="window.refreshTools()">Refresh</button>
        </div>
      </div>
      <div class="grid gap-2 max-h-96 overflow-y-auto">
        ${serverTools.map(renderToolCard).join('')}
      </div>
    </div>
  `;
}

export async function render(container) {
  container.innerHTML = `
    ${renderHeader()}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-white">Servers</h2>
          <button class="btn btn-sm btn-ghost" onclick="window.refreshMcpServers()">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
        </div>
        <div id="mcp-servers-container">Loading...</div>
        <div id="mcp-add-form-container" class="hidden mt-4">${renderAddServerForm()}</div>
      </div>
      <div id="mcp-tools-container">
        ${renderToolsSection()}
      </div>
    </div>
  `;

  // Bind global functions
  window.selectMcpServer = (name) => {
    selectedServer = name;
    loadTools();
    loadServers(); // Re-render to show selection
  };

  window.connectMcpServer = async (name) => {
    try {
      const result = await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/connect`);
      if (result.ok) {
        toast.success(`Connected to ${name}`);
        loadServers();
        setTimeout(() => loadTools(), 500);
      } else {
        toast.error(result.error || 'Connection failed');
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  window.disconnectMcpServer = async (name) => {
    try {
      const result = await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/disconnect`);
      if (result.ok) {
        toast.success(`Disconnected from ${name}`);
        if (selectedServer === name) {
          toolCache = toolCache.filter(t => t._server !== name);
        }
        loadServers();
        renderTools();
      } else {
        toast.error(result.error || 'Disconnect failed');
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  window.refreshMcpServers = loadServers;
  window.refreshTools = loadTools;

  window.toggleAddForm = () => {
    const form = document.getElementById('mcp-add-form-container');
    form.classList.toggle('hidden');
  };

  // Handle form submission
  document.getElementById('mcp-add-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    
    const argsStr = formData.get('args')?.toString() || '';
    const args = argsStr.split(/\s+/).filter(a => a);
    
    const data = {
      name: formData.get('name')?.toString() || '',
      command: formData.get('command')?.toString() || '',
      args: args,
      enabled: formData.get('enabled') === 'on',
    };

    try {
      const result = await api.post('/api/mcp/config', data);
      if (result.ok) {
        toast.success('Server added successfully');
        form.reset();
        window.toggleAddForm();
        loadServers();
      } else {
        toast.error(result.error || 'Failed to add server');
      }
    } catch (err) {
      toast.error(err.message);
    }
  });

  await loadServers();
  await loadTools();

  // Auto-refresh every 10 seconds
  refreshTimer = setInterval(() => {
    loadServers();
  }, 10000);
}

async function loadServers() {
  try {
    const { servers } = await api.get('/api/mcp/servers');
    const container = document.getElementById('mcp-servers-container');
    if (container) {
      container.innerHTML = renderServersList(servers);
    }
  } catch (err) {
    console.error('Failed to load MCP servers:', err);
    const container = document.getElementById('mcp-servers-container');
    if (container) {
      container.innerHTML = `<div class="text-red-400 text-sm">Error: ${err.message}</div>`;
    }
  }
}

async function loadTools() {
  try {
    const { tools } = await api.get('/api/mcp/tools');
    toolCache = tools || [];
    const container = document.getElementById('mcp-tools-container');
    if (container) {
      container.innerHTML = renderToolsSection();
    }
  } catch (err) {
    console.error('Failed to load MCP tools:', err);
  }
}

export function cleanup() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  window.selectMcpServer = null;
  window.connectMcpServer = null;
  window.disconnectMcpServer = null;
  window.refreshMcpServers = null;
  window.refreshTools = null;
  window.toggleAddForm = null;
}
