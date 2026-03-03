/** Langfuse page — Observability and Tracing */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [statusData, tracesData, statsData] = await Promise.all([
    api.get('/api/langfuse/status').catch(() => ({ enabled: false })),
    api.get('/api/langfuse/traces?limit=50').catch(() => ({ traces: [] })),
    api.get('/api/langfuse/stats?hours=24').catch(() => ({
      total_traces: 0, completed: 0, errors: 0, total_tokens: 0, total_cost_usd: 0
    })),
  ]);

  const status = statusData || { enabled: false, configured: false };
  const traces = tracesData?.traces || [];
  const stats = statsData || { total_traces: 0, completed: 0, errors: 0, total_tokens: 0, total_cost_usd: 0 };

  const isEnabled = status.enabled;
  const isConfigured = status.configured;
  const statusColor = isEnabled && isConfigured ? 'badge-green' : (isEnabled ? 'badge-yellow' : 'badge-zinc');
  const statusText = isEnabled && isConfigured ? 'Active' : (isEnabled ? 'Enabled (No Credentials)' : 'Disabled');

  container.innerHTML = `
    <div class="max-w-6xl mx-auto">
      <div class="page-header">Langfuse Observability</div>
      <div class="page-desc">LLM tracing, monitoring, and cost analytics</div>

      <!-- Status Card -->
      <div class="stat-card mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-white mb-2">Connection Status</h3>
            <div class="flex items-center gap-3">
              <span class="badge ${statusColor}">${statusText}</span>
              ${status.host ? `<span class="text-xs text-zinc-500">${u.escapeHtml(status.host)}</span>` : ''}
            </div>
          </div>
          <div class="flex gap-2">
            <button id="lf-test-btn" class="btn btn-secondary btn-sm" ${!isEnabled ? 'disabled' : ''}>
              Test Connection
            </button>
            <a href="#config" class="btn btn-primary btn-sm">Configure</a>
          </div>
        </div>
        <div id="lf-test-result" class="mt-3 text-sm hidden"></div>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="stat-card text-center">
          <div class="text-2xl font-bold text-white">${stats.total_traces}</div>
          <div class="text-xs text-zinc-500 mt-1">Total Calls (24h)</div>
        </div>
        <div class="stat-card text-center">
          <div class="text-2xl font-bold text-emerald-400">${stats.completed}</div>
          <div class="text-xs text-zinc-500 mt-1">Completed</div>
        </div>
        <div class="stat-card text-center">
          <div class="text-2xl font-bold ${stats.errors > 0 ? 'text-red-400' : 'text-zinc-400'}">${stats.errors}</div>
          <div class="text-xs text-zinc-500 mt-1">Errors</div>
        </div>
        <div class="stat-card text-center">
          <div class="text-2xl font-bold text-ghost-400">${stats.total_tokens.toLocaleString()}</div>
          <div class="text-xs text-zinc-500 mt-1">Tokens</div>
        </div>
        <div class="stat-card text-center">
          <div class="text-2xl font-bold text-amber-400">$${stats.total_cost_usd.toFixed(4)}</div>
          <div class="text-xs text-zinc-500 mt-1">Est. Cost</div>
        </div>
      </div>

      <!-- Traces Table -->
      <div class="stat-card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-semibold text-white">Recent Traces</h3>
          <span class="text-xs text-zinc-500">Last 50 traces</span>
        </div>
        
        ${traces.length === 0 ? `
          <div class="text-center py-8 text-zinc-500">
            <svg class="w-12 h-12 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
            </svg>
            <p class="text-sm">No traces recorded yet</p>
            <p class="text-xs mt-1">Traces will appear here when Langfuse is enabled and LLM calls are made.</p>
          </div>
        ` : `
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-zinc-500 border-b border-surface-600">
                  <th class="pb-2 font-medium">Name</th>
                  <th class="pb-2 font-medium">Status</th>
                  <th class="pb-2 font-medium">Time</th>
                  <th class="pb-2 font-medium">Duration</th>
                  <th class="pb-2 font-medium">Spans</th>
                  <th class="pb-2 font-medium">Tokens</th>
                  <th class="pb-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody class="text-zinc-300">
                ${traces.map(t => `
                  <tr class="border-b border-surface-600/50 hover:bg-surface-700/30">
                    <td class="py-3">
                      <div class="font-medium text-white">${u.escapeHtml(t.name)}</div>
                      ${t.session_id ? `<div class="text-xs text-zinc-500">session: ${t.session_id.slice(0, 8)}...</div>` : ''}
                    </td>
                    <td class="py-3">
                      ${t.status === 'completed' 
                        ? '<span class="badge badge-green">Done</span>'
                        : t.status === 'error'
                        ? '<span class="badge badge-red">Error</span>'
                        : '<span class="badge badge-yellow">Running</span>'
                      }
                    </td>
                    <td class="py-3 text-xs text-zinc-400">
                      ${new Date(t.start_time).toLocaleTimeString()}
                    </td>
                    <td class="py-3 text-xs">
                      ${t.duration_ms ? `${t.duration_ms}ms` : '-'}
                    </td>
                    <td class="py-3 text-xs text-zinc-400">
                      ${t.span_count}
                    </td>
                    <td class="py-3 text-xs text-zinc-400">
                      ${t.total_tokens > 0 ? t.total_tokens.toLocaleString() : '-'}
                    </td>
                    <td class="py-3 text-xs text-zinc-400">
                      ${t.total_cost_usd > 0 ? `$${t.total_cost_usd.toFixed(4)}` : '-'}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>

      <!-- Setup Info -->
      ${!isEnabled ? `
        <div class="stat-card mt-6 border-l-4 border-l-amber-500">
          <h3 class="text-sm font-semibold text-white mb-2">Getting Started</h3>
          <ol class="text-sm text-zinc-400 space-y-2 ml-4 list-decimal">
            <li>Sign up at <a href="https://langfuse.com" target="_blank" class="text-ghost-400 hover:underline">langfuse.com</a> (free tier available)</li>
            <li>Create a new project and copy your API keys</li>
            <li>Go to <a href="#config" class="text-ghost-400 hover:underline">Configuration</a> and enable Langfuse</li>
            <li>Add your public key, secret key, and host URL</li>
            <li>Click "Test Connection" to verify</li>
          </ol>
        </div>
      ` : ''}
    </div>
  `;

  // Test connection button handler
  const testBtn = container.querySelector('#lf-test-btn');
  const testResult = container.querySelector('#lf-test-result');
  
  if (testBtn) {
    testBtn.addEventListener('click', async () => {
      testBtn.disabled = true;
      testBtn.textContent = 'Testing...';
      testResult.classList.add('hidden');
      
      try {
        const result = await api.post('/api/langfuse/test');
        testResult.innerHTML = `
          <span class="text-emerald-400">${u.escapeHtml(result.message || 'Connection successful')}</span>
          ${result.test_trace_id ? `<span class="text-zinc-500 ml-2">(test trace: ${result.test_trace_id.slice(0, 8)}...)</span>` : ''}
        `;
        testResult.classList.remove('hidden');
      } catch (err) {
        const msg = err?.error || err?.message || 'Connection failed';
        const details = err?.details || '';
        testResult.innerHTML = `
          <span class="text-red-400">${u.escapeHtml(msg)}</span>
          ${details ? `<div class="text-zinc-500 mt-1">${u.escapeHtml(details)}</div>` : ''}
        `;
        testResult.classList.remove('hidden');
      } finally {
        testBtn.disabled = false;
        testBtn.textContent = 'Test Connection';
      }
    });
  }
}
