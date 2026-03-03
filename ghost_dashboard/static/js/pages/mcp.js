/** MCP (Model Context Protocol) page — server management, tool discovery, and testing */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let data;
  try {
    data = await api.get('/api/mcp');
  } catch (e) {
    container.innerHTML = `<h1 class="page-header">MCP Servers</h1>
      <div class="stat-card"><p class="text-zinc-500 text-sm">MCP system not available. Enable <code>enable_mcp</code> in config.</p></div>`;
    return;
  }

  if (!data.enabled) {
    container.innerHTML = `<h1 class="page-header">MCP Servers</h1>
      <div class="stat-card">
        <p class="text-zinc-500 text-sm">MCP is disabled. Set <code>enable_mcp: true</code> in your Ghost config to enable it.</p>
      </div>`;
    return;
  }

  const servers = data.servers || [];
  const connected = servers.filter(s => s.connected);
  const disconnected = servers.filter(s => !s.connected);

  const statusDot = (s) => {
    const c = s.connected ? 'bg-emerald-400' : 'bg-zinc-600';
    return `<span class="inline-block w-2 h-2 rounded-full ${c}"></span>`;
  };

  container.innerHTML = `
    <h1 class="page-header">MCP Servers</h1>
    <p class="page-desc">Model Context Protocol — extend Ghost with external tools from MCP-compatible servers</p>

    <div class="mb-6">
      <button id="mcp-add-server-btn" class="px-4 py-2 bg-ghost-600 hover:bg-ghost-500 text-white text-sm rounded font-medium">+ Add Server</button>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-2xl font-bold text-white">${servers.length}</div>
        <div class="text-xs text-zinc-500">Configured</div>
      </div>
      <div class="stat-card">
        <div class="text-2xl font-bold text-emerald-400">${data.connected_count || 0}</div>
        <div class="text-xs text-zinc-500">Connected</div>
      </div>
      <div class="stat-card">
        <div class="text-2xl font-bold text-ghost-400">${data.total_tools || 0}</div>
        <div class="text-xs text-zinc-500">Available Tools</div>
      </div>
      <div class="stat-card">
        <div class="text-2xl font-bold ${data.enabled ? 'text-emerald-400' : 'text-zinc-600'}">${data.enabled ? 'ON' : 'OFF'}</div>
        <div class="text-xs text-zinc-500">MCP Status</div>
      </div>
    </div>

    ${servers.length === 0 ? `
    <div class="stat-card mb-6">
      <div class="text-center py-8">
        <div class="w-16 h-16 mx-auto mb-4 rounded-xl bg-surface-700 flex items-center justify-center">
          <svg class="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </div>
        <p class="text-sm text-zinc-400 mb-2">No MCP servers configured</p>
        <p class="text-xs text-zinc-600 max-w-md mx-auto">Add MCP servers to your Ghost config under <code class="text-ghost-400">mcp_servers</code>. Each server provides external tools that Ghost can use during conversations and autonomous tasks.</p>
        <pre class="text-left text-[11px] text-zinc-400 bg-surface-700 rounded-lg px-4 py-3 mt-4 mx-auto max-w-sm font-mono">{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "enabled": true
    }
  }
}</pre>
      </div>
    </div>
    ` : ''}

    ${servers.length > 0 ? `
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-white">Servers</h3>
      <div class="flex gap-2">
        <button id="mcp-reconnect-all" class="text-[10px] px-2 py-1 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30" title="Reconnect any dead servers">Reconnect Dead</button>
      </div>
    </div>
    <div id="mcp-servers-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      ${servers.map(s => _renderServerCard(s, u)).join('')}
    </div>
    ` : ''}

    <div id="mcp-tools-section" class="${connected.length > 0 ? '' : 'hidden'}">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-white">Available Tools</h3>
        <button id="mcp-refresh-tools" class="text-[10px] px-2 py-1 rounded bg-surface-600 text-zinc-400 hover:bg-surface-500">Refresh</button>
      </div>
      <div id="mcp-tools-list" class="space-y-2 mb-6">
        <div class="text-xs text-zinc-600 py-4 text-center animate-pulse">Loading tools...</div>
      </div>
    </div>

    <div id="mcp-test-section" class="${connected.length > 0 ? '' : 'hidden'}">
      <h3 class="text-sm font-semibold text-white mb-3">Test Tool</h3>
      <div class="stat-card">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          <div>
            <label class="block text-[11px] text-zinc-400 mb-1">Server</label>
            <select id="mcp-test-server" class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:border-zinc-500">
              ${connected.map(s => `<option value="${u.escapeHtml(s.name)}">${u.escapeHtml(s.name)}</option>`).join('')}
            </select>
          </div>
          <div>
            <label class="block text-[11px] text-zinc-400 mb-1">Tool</label>
            <select id="mcp-test-tool" class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:border-zinc-500">
              <option value="">Select a server first</option>
            </select>
          </div>
        </div>
        <div class="mb-3">
          <label class="block text-[11px] text-zinc-400 mb-1">Arguments (JSON)</label>
          <textarea id="mcp-test-args" rows="3" placeholder='{}'
            class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 font-mono"></textarea>
        </div>
        <div class="flex items-center gap-3">
          <button id="mcp-test-run" class="px-4 py-2 bg-ghost-600 hover:bg-ghost-500 text-white text-sm rounded font-medium">Run Tool</button>
          <span id="mcp-test-status" class="text-xs text-zinc-500"></span>
        </div>
        <pre id="mcp-test-result" class="hidden mt-3 text-[11px] text-zinc-300 bg-surface-700 rounded-lg px-4 py-3 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto"></pre>
      </div>
    </div>
  `;

  // --- Connect / Disconnect buttons ---
  container.querySelectorAll('.mcp-btn-connect').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      const orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Connecting...';
      btn.classList.add('opacity-60');
      try {
        const res = await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/connect`, {});
        if (res.ok) {
          btn.textContent = 'Connected!';
          btn.classList.remove('bg-emerald-500/20', 'text-emerald-400');
          btn.classList.add('bg-emerald-500/30', 'text-emerald-300');
          setTimeout(() => render(container), 600);
        } else {
          btn.textContent = 'Failed';
          btn.classList.add('bg-red-500/20', 'text-red-400');
          setTimeout(() => { btn.textContent = orig; btn.disabled = false; btn.classList.remove('opacity-60', 'bg-red-500/20', 'text-red-400'); }, 2000);
        }
      } catch (e) {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = orig; btn.disabled = false; btn.classList.remove('opacity-60'); }, 2000);
      }
    });
  });

  container.querySelectorAll('.mcp-btn-disconnect').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      btn.disabled = true;
      btn.textContent = 'Disconnecting...';
      btn.classList.add('opacity-60');
      try {
        await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/disconnect`, {});
        btn.textContent = 'Disconnected';
        setTimeout(() => render(container), 600);
      } catch (e) {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = 'Disconnect'; btn.disabled = false; btn.classList.remove('opacity-60'); }, 2000);
      }
    });
  });

  // --- Add Server button ---
  container.querySelector('#mcp-add-server-btn')?.addEventListener('click', () => {
    _showAddServerModal(container, api, u);
  });

  // --- Remove buttons ---
  container.querySelectorAll('.mcp-btn-remove').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      if (!confirm(`Remove MCP server "${name}"? This will disconnect it and delete its config.`)) return;
      btn.disabled = true;
      btn.textContent = 'Removing...';
      try {
        await api.post(`/api/mcp/servers/${encodeURIComponent(name)}/remove`, {});
        setTimeout(() => render(container), 400);
      } catch (e) {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = 'Remove'; btn.disabled = false; }, 2000);
      }
    });
  });

  // --- Reconnect dead servers ---
  container.querySelector('#mcp-reconnect-all')?.addEventListener('click', async () => {
    const btn = container.querySelector('#mcp-reconnect-all');
    btn.disabled = true;
    btn.textContent = 'Reconnecting...';
    btn.classList.add('opacity-60');
    try {
      await api.post('/api/mcp/reconnect', {});
      btn.textContent = 'Done';
      setTimeout(() => render(container), 800);
    } catch (e) {
      btn.textContent = 'Error';
      setTimeout(() => { btn.textContent = 'Reconnect Dead'; btn.disabled = false; btn.classList.remove('opacity-60'); }, 2000);
    }
  });

  // --- Load tools ---
  if (connected.length > 0) {
    await _loadTools(container, api, u);
  }

  // --- Refresh tools button ---
  container.querySelector('#mcp-refresh-tools')?.addEventListener('click', async () => {
    const btn = container.querySelector('#mcp-refresh-tools');
    btn.textContent = 'Refreshing...';
    btn.disabled = true;
    await _loadTools(container, api, u);
    btn.textContent = 'Refresh';
    btn.disabled = false;
  });

  // --- Test tool: server selection populates tools ---
  const testServer = container.querySelector('#mcp-test-server');
  const testTool = container.querySelector('#mcp-test-tool');
  if (testServer && testTool) {
    const populateTools = async () => {
      const serverName = testServer.value;
      if (!serverName) { testTool.innerHTML = '<option value="">Select a server</option>'; return; }
      try {
        const res = await api.get(`/api/mcp/servers/${encodeURIComponent(serverName)}/tools`);
        const tools = res.tools || [];
        testTool.innerHTML = tools.length === 0
          ? '<option value="">No tools available</option>'
          : tools.map(t => `<option value="${u.escapeHtml(t.name)}">${u.escapeHtml(t.name)}</option>`).join('');
      } catch {
        testTool.innerHTML = '<option value="">Error loading tools</option>';
      }
    };
    testServer.addEventListener('change', populateTools);
    if (testServer.value) populateTools();
  }

  // --- Test tool: run ---
  container.querySelector('#mcp-test-run')?.addEventListener('click', async () => {
    const serverName = testServer?.value;
    const toolName = testTool?.value;
    const argsText = container.querySelector('#mcp-test-args')?.value?.trim() || '{}';
    const resultPre = container.querySelector('#mcp-test-result');
    const statusEl = container.querySelector('#mcp-test-status');
    const runBtn = container.querySelector('#mcp-test-run');

    if (!serverName || !toolName) {
      statusEl.textContent = 'Select a server and tool first';
      statusEl.className = 'text-xs text-red-400';
      return;
    }

    let args;
    try {
      args = JSON.parse(argsText);
    } catch (e) {
      statusEl.textContent = `Invalid JSON: ${e.message}`;
      statusEl.className = 'text-xs text-red-400';
      return;
    }

    runBtn.disabled = true;
    runBtn.textContent = 'Running...';
    statusEl.textContent = '';
    resultPre.classList.add('hidden');
    const startTime = performance.now();

    try {
      const res = await api.post('/api/mcp/tools/call', {
        server_name: serverName,
        tool_name: toolName,
        arguments: args,
      });
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
      resultPre.classList.remove('hidden');

      if (res.ok) {
        statusEl.textContent = `Completed in ${elapsed}s`;
        statusEl.className = 'text-xs text-emerald-400';
        resultPre.textContent = JSON.stringify(res.result, null, 2);
      } else {
        statusEl.textContent = `Failed (${elapsed}s)`;
        statusEl.className = 'text-xs text-red-400';
        resultPre.textContent = JSON.stringify(res, null, 2);
      }
    } catch (e) {
      resultPre.classList.remove('hidden');
      statusEl.textContent = 'Error';
      statusEl.className = 'text-xs text-red-400';
      resultPre.textContent = e.message;
    }

    runBtn.disabled = false;
    runBtn.textContent = 'Run Tool';
  });
}


function _renderServerCard(server, u) {
  const connected = server.connected;
  const borderClass = connected ? 'border-emerald-500/20' : 'border-surface-600';
  const toolCount = server.tool_count || 0;

  const uptimeStr = () => {
    if (!connected || !server.connected_at) return '';
    const secs = Math.floor(Date.now() / 1000 - server.connected_at);
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  };

  return `
    <div class="stat-card border ${borderClass}">
      <div class="flex items-center gap-3 mb-3">
        <div class="w-10 h-10 rounded-lg ${connected ? 'bg-emerald-500/10' : 'bg-surface-700'} flex items-center justify-center flex-shrink-0">
          <svg class="w-5 h-5 ${connected ? 'text-emerald-400' : 'text-zinc-600'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-white truncate">${u.escapeHtml(server.name)}</span>
            ${!server.enabled ? '<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-zinc-700 text-zinc-500">disabled</span>' : ''}
          </div>
          <div class="flex items-center gap-1.5 mt-0.5">
            <span class="inline-block w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-zinc-600'}"></span>
            <span class="text-[11px] ${connected ? 'text-emerald-400' : 'text-zinc-500'}">${connected ? 'connected' : 'disconnected'}</span>
          </div>
        </div>
      </div>

      <div class="text-[11px] text-zinc-500 mb-2 font-mono truncate" title="${u.escapeHtml(server.command + ' ' + (server.args || []).join(' '))}">
        ${u.escapeHtml(server.command)}${server.args?.length ? ' ' + u.escapeHtml(server.args.join(' ')) : ''}
      </div>

      ${connected ? `
      <div class="flex flex-wrap gap-x-4 gap-y-1 mb-3 text-[10px] text-zinc-500">
        <span>uptime: <span class="text-zinc-400">${uptimeStr()}</span></span>
        <span>requests: <span class="text-zinc-400">${server.request_count || 0}</span></span>
        <span>idle: <span class="text-zinc-400">${server.idle_seconds != null ? Math.floor(server.idle_seconds) + 's' : '—'}</span></span>
      </div>
      ` : ''}

      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          ${connected ? `<span class="text-[10px] px-1.5 py-0.5 rounded bg-ghost-500/20 text-ghost-400">${toolCount} tool${toolCount !== 1 ? 's' : ''}</span>` : ''}
        </div>
        <div class="flex gap-2">
          ${connected
            ? `<button class="mcp-btn-disconnect text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20" data-name="${u.escapeHtml(server.name)}">Disconnect</button>`
            : `<button class="mcp-btn-connect text-[10px] px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30" data-name="${u.escapeHtml(server.name)}" ${!server.enabled ? 'disabled' : ''}>Connect</button>`
          }
          <button class="mcp-btn-remove text-[10px] px-2 py-1 rounded bg-surface-600 text-zinc-500 hover:bg-red-500/20 hover:text-red-400" data-name="${u.escapeHtml(server.name)}" title="Remove server">Remove</button>
        </div>
      </div>
    </div>
  `;
}


async function _loadTools(container, api, u) {
  const toolsList = container.querySelector('#mcp-tools-list');
  if (!toolsList) return;

  toolsList.innerHTML = '<div class="text-xs text-zinc-600 py-4 text-center animate-pulse">Loading tools...</div>';

  try {
    const res = await api.get('/api/mcp/tools');
    const tools = res.tools || [];

    if (tools.length === 0) {
      toolsList.innerHTML = '<div class="text-xs text-zinc-600 py-4 text-center">No tools available from connected servers</div>';
      return;
    }

    const byServer = {};
    for (const t of tools) {
      const srv = t._server || 'unknown';
      if (!byServer[srv]) byServer[srv] = [];
      byServer[srv].push(t);
    }

    let html = '';
    for (const [srv, srvTools] of Object.entries(byServer)) {
      html += `
        <div class="stat-card">
          <div class="flex items-center gap-2 mb-3">
            <span class="inline-block w-2 h-2 rounded-full bg-emerald-400"></span>
            <span class="text-xs font-semibold text-white">${u.escapeHtml(srv)}</span>
            <span class="text-[10px] text-zinc-500">${srvTools.length} tool${srvTools.length !== 1 ? 's' : ''}</span>
          </div>
          <div class="space-y-2">
            ${srvTools.map(t => `
              <div class="mcp-tool-item group px-3 py-2 rounded-lg bg-surface-700/50 hover:bg-surface-700 transition-colors cursor-pointer" data-tool-name="${u.escapeHtml(t.name)}" data-tool-server="${u.escapeHtml(srv)}">
                <div class="flex items-center justify-between">
                  <span class="text-[12px] font-medium text-ghost-400 font-mono">${u.escapeHtml(t.name)}</span>
                  <button class="mcp-use-tool text-[9px] px-1.5 py-0.5 rounded bg-ghost-500/20 text-ghost-300 opacity-0 group-hover:opacity-100 transition-opacity" data-server="${u.escapeHtml(srv)}" data-tool="${u.escapeHtml(t.name)}">Use</button>
                </div>
                ${t.description ? `<div class="text-[11px] text-zinc-500 mt-1 line-clamp-2">${u.escapeHtml(t.description)}</div>` : ''}
                ${t.inputSchema?.properties ? `<div class="flex flex-wrap gap-1 mt-1.5">${Object.keys(t.inputSchema.properties).map(p =>
                  `<span class="text-[9px] px-1 py-0.5 rounded bg-surface-600/80 text-zinc-500 font-mono">${u.escapeHtml(p)}</span>`
                ).join('')}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    toolsList.innerHTML = html;

    toolsList.querySelectorAll('.mcp-use-tool').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const serverName = btn.dataset.server;
        const toolName = btn.dataset.tool;
        const testServer = container.querySelector('#mcp-test-server');
        const testTool = container.querySelector('#mcp-test-tool');

        if (testServer) {
          testServer.value = serverName;
          testServer.dispatchEvent(new Event('change'));
          setTimeout(() => {
            if (testTool) testTool.value = toolName;
          }, 300);
        }

        container.querySelector('#mcp-test-section')?.scrollIntoView({ behavior: 'smooth' });
      });
    });

  } catch (e) {
    toolsList.innerHTML = `<div class="text-xs text-red-400 py-4 text-center">Error loading tools: ${u.escapeHtml(e.message)}</div>`;
  }
}


function _showAddServerModal(pageContainer, api, u) {
  const overlay = document.createElement('div');
  overlay.className = 'fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4';
  overlay.innerHTML = `
    <div class="bg-surface-800 rounded-xl border border-surface-600 p-6 w-full max-w-lg shadow-2xl">
      <h3 class="text-sm font-semibold text-white mb-4">Add MCP Server</h3>
      <div class="space-y-3">
        <div>
          <label class="block text-[11px] text-zinc-400 mb-1">Name <span class="text-red-400">*</span></label>
          <input id="mcp-add-name" type="text" placeholder="e.g. filesystem, github, sqlite"
            class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 font-mono" />
          <div class="text-[10px] text-zinc-600 mt-0.5">Alphanumeric, hyphens, underscores only</div>
        </div>
        <div>
          <label class="block text-[11px] text-zinc-400 mb-1">Command <span class="text-red-400">*</span></label>
          <input id="mcp-add-command" type="text" placeholder="e.g. npx, node, python, uvx"
            class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 font-mono" />
        </div>
        <div>
          <label class="block text-[11px] text-zinc-400 mb-1">Arguments</label>
          <input id="mcp-add-args" type="text" placeholder="e.g. -y @modelcontextprotocol/server-filesystem /tmp"
            class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 font-mono" />
          <div class="text-[10px] text-zinc-600 mt-0.5">Space-separated arguments</div>
        </div>
        <div>
          <label class="block text-[11px] text-zinc-400 mb-1">Environment Variables (JSON, optional)</label>
          <input id="mcp-add-env" type="text" placeholder='e.g. {"API_KEY": "sk-..."}'
            class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 font-mono" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] text-zinc-400 mb-1">Timeout (seconds)</label>
            <input id="mcp-add-timeout" type="number" value="30" min="5" max="300"
              class="w-full bg-surface-700 border border-surface-600 rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500" />
          </div>
          <div class="flex items-end pb-1">
            <label class="flex items-center gap-2 cursor-pointer">
              <input id="mcp-add-enabled" type="checkbox" checked class="rounded bg-surface-700 border-surface-600 text-ghost-500 focus:ring-ghost-500" />
              <span class="text-[11px] text-zinc-400">Enabled</span>
            </label>
          </div>
        </div>
      </div>

      <div class="mt-4 p-3 rounded-lg bg-surface-700/50 border border-surface-600/50">
        <div class="text-[10px] text-zinc-500 mb-2">Popular MCP servers:</div>
        <div class="flex flex-wrap gap-1.5">
          ${[
            { label: 'Filesystem', cmd: 'npx', args: '-y @modelcontextprotocol/server-filesystem /tmp' },
            { label: 'GitHub', cmd: 'npx', args: '-y @modelcontextprotocol/server-github', env: '{"GITHUB_PERSONAL_ACCESS_TOKEN":""}' },
            { label: 'SQLite', cmd: 'npx', args: '-y @modelcontextprotocol/server-sqlite /tmp/test.db' },
            { label: 'Brave Search', cmd: 'npx', args: '-y @modelcontextprotocol/server-brave-search', env: '{"BRAVE_API_KEY":""}' },
            { label: 'MarkItDown', cmd: 'uvx', args: 'mcp-server-markitdown' },
          ].map(p => `<button class="mcp-preset text-[9px] px-2 py-1 rounded bg-ghost-500/15 text-ghost-400 hover:bg-ghost-500/25"
            data-cmd="${u.escapeHtml(p.cmd)}" data-args="${u.escapeHtml(p.args)}" data-name="${u.escapeHtml(p.label.toLowerCase())}"
            ${p.env ? `data-env="${u.escapeHtml(p.env)}"` : ''}>${p.label}</button>`).join('')}
        </div>
      </div>

      <div class="flex justify-end gap-2 mt-5">
        <button id="mcp-add-cancel" class="px-3 py-1.5 rounded bg-surface-600 text-zinc-400 text-sm hover:bg-surface-500">Cancel</button>
        <button id="mcp-add-save" class="px-4 py-1.5 rounded bg-ghost-600 text-white text-sm hover:bg-ghost-500 font-medium">Add & Connect</button>
      </div>
      <div id="mcp-add-result" class="text-xs mt-2 hidden"></div>
    </div>
  `;

  document.body.appendChild(overlay);

  const $ = (sel) => overlay.querySelector(sel);
  const cleanup = () => overlay.remove();

  overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(); });
  $('#mcp-add-cancel').addEventListener('click', cleanup);

  overlay.querySelectorAll('.mcp-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      $('#mcp-add-name').value = btn.dataset.name;
      $('#mcp-add-command').value = btn.dataset.cmd;
      $('#mcp-add-args').value = btn.dataset.args;
      if (btn.dataset.env) $('#mcp-add-env').value = btn.dataset.env;
    });
  });

  $('#mcp-add-save').addEventListener('click', async () => {
    const name = $('#mcp-add-name').value.trim();
    const command = $('#mcp-add-command').value.trim();
    const argsStr = $('#mcp-add-args').value.trim();
    const envStr = $('#mcp-add-env').value.trim();
    const timeout = parseInt($('#mcp-add-timeout').value) || 30;
    const enabled = $('#mcp-add-enabled').checked;
    const resultDiv = $('#mcp-add-result');

    if (!name || !command) {
      resultDiv.classList.remove('hidden');
      resultDiv.textContent = 'Name and command are required';
      resultDiv.className = 'text-xs text-red-400 mt-2';
      return;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      resultDiv.classList.remove('hidden');
      resultDiv.textContent = 'Name must be alphanumeric (hyphens/underscores allowed)';
      resultDiv.className = 'text-xs text-red-400 mt-2';
      return;
    }

    let env = {};
    if (envStr) {
      try { env = JSON.parse(envStr); } catch (e) {
        resultDiv.classList.remove('hidden');
        resultDiv.textContent = `Invalid env JSON: ${e.message}`;
        resultDiv.className = 'text-xs text-red-400 mt-2';
        return;
      }
    }

    const args = argsStr ? argsStr.split(/\s+/) : [];
    const saveBtn = $('#mcp-add-save');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Adding...';

    try {
      const res = await api.post('/api/mcp/servers/add', {
        name, command, args, env, timeout, enabled, auto_connect: true,
      });
      resultDiv.classList.remove('hidden');
      if (res.ok) {
        const connOk = res.connect_result?.ok;
        resultDiv.textContent = connOk
          ? `Server "${name}" added and connected!`
          : `Server "${name}" added (connect: ${res.connect_result?.error || 'pending'})`;
        resultDiv.className = `text-xs ${connOk ? 'text-emerald-400' : 'text-amber-400'} mt-2`;
        setTimeout(() => { cleanup(); render(pageContainer); }, 800);
      } else {
        resultDiv.textContent = res.error || 'Failed to add server';
        resultDiv.className = 'text-xs text-red-400 mt-2';
        saveBtn.disabled = false;
        saveBtn.textContent = 'Add & Connect';
      }
    } catch (e) {
      resultDiv.classList.remove('hidden');
      resultDiv.textContent = `Error: ${e.message}`;
      resultDiv.className = 'text-xs text-red-400 mt-2';
      saveBtn.disabled = false;
      saveBtn.textContent = 'Add & Connect';
    }
  });
}
