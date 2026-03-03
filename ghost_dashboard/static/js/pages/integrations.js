/** Integrations page — manage Google and Grok API connections */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  
  // Load current integrations status
  let status = {};
  try {
    status = await api.get('/api/integrations');
  } catch (e) {
    container.innerHTML = `<div class="text-red-400 p-4">Error loading integrations: ${e.message}</div>`;
    return;
  }

  const google = status.google || {};
  const grok = status.grok || {};
  const webSearch = status.web_search || { providers: [], active_count: 0 };
  const imageGen = status.image_gen || { providers: [], active_count: 0 };
  const vision = status.vision || { providers: [], active_count: 0 };
  const tts = status.tts || { providers: [], active_count: 0 };
  
  const renderGoogleSection = () => {
    if (google.connected) {
      const user = google.user || {};
      return `
        <div class="stat-card border-l-4 border-emerald-500">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <svg class="w-6 h-6 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-white">Google</h3>
                <p class="text-sm text-zinc-400">${user.email || user.name || 'Connected'}</p>
              </div>
            </div>
            <span class="px-2 py-1 text-xs bg-emerald-500/20 text-emerald-400 rounded">Connected</span>
          </div>
          
          <div class="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4">
            ${['gmail', 'calendar', 'drive', 'docs', 'sheets'].map(svc => {
              const on = google.services?.includes(svc);
              const icon = on
                ? '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#10b981;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>'
                : '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#52525b;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></span>';
              return `
              <div class="flex items-center gap-2 p-2 rounded bg-surface-700/50 ${on ? 'text-emerald-400' : 'text-zinc-600'}">
                ${icon}
                <span class="text-xs capitalize">${svc}</span>
              </div>`;
            }).join('')}
          </div>
          
          <div class="flex gap-2">
            <button id="btn-google-test" class="btn btn-secondary btn-sm">Test Connection</button>
            <button id="btn-google-disconnect" class="btn btn-danger btn-sm">Disconnect</button>
          </div>
        </div>
      `;
    } else {
      return `
        <div class="stat-card">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <svg class="w-6 h-6 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
            </div>
            <div>
              <h3 class="font-semibold text-white">Google</h3>
              <p class="text-sm text-zinc-400">Connect your Google account to access Gmail, Calendar, Drive, Docs & Sheets</p>
            </div>
          </div>
          
          ${!google.ghost_credentials_configured ? `
            <div class="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mb-4">
              <p class="text-sm text-amber-400 mb-2">⚠️ Google OAuth Not Configured</p>
              <p class="text-xs text-zinc-400 mb-3">Ghost needs OAuth credentials to connect with Google. Set them up via:</p>
              <ol class="text-xs text-zinc-400 list-decimal list-inside space-y-1 mb-3">
                <li><a href="https://console.cloud.google.com/apis/credentials" target="_blank" class="text-ghost-400 hover:underline">Google Cloud Console</a></li>
                <li>Create OAuth 2.0 credentials</li>
                <li>Add <code class="bg-surface-700 px-1 rounded">http://localhost:5000/api/integrations/google/callback</code> as redirect URI</li>
              </ol>
              <details class="group">
                <summary class="text-xs text-ghost-400 cursor-pointer hover:text-ghost-300">Advanced: Configure credentials manually</summary>
                <div class="mt-3 space-y-2">
                  <input type="text" id="google-client-id" placeholder="Client ID" class="form-input w-full text-sm">
                  <input type="password" id="google-client-secret" placeholder="Client Secret" class="form-input w-full text-sm">
                  <button id="btn-google-save-creds" class="btn btn-secondary btn-sm w-full">Save Credentials</button>
                </div>
              </details>
            </div>
          ` : `
            <div class="space-y-4">
              <div class="flex justify-center">
                <button id="btn-google-signin" class="group relative flex items-center gap-3 bg-white hover:bg-gray-50 text-gray-700 font-medium py-2.5 px-6 rounded-lg shadow-sm border border-gray-300 transition-all duration-200 hover:shadow-md">
                  <svg class="w-5 h-5" viewBox="0 0 24 24">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  <span>Sign in with Google</span>
                </button>
              </div>
              
              <div class="text-center">
                <p class="text-xs text-zinc-500">Select which services to grant access to:</p>
              </div>
              
              <div class="grid grid-cols-2 md:grid-cols-5 gap-2">
                ${['gmail', 'calendar', 'drive', 'docs', 'sheets'].map(svc => `
                  <label class="flex items-center gap-2 p-2 rounded bg-surface-700/50 cursor-pointer hover:bg-surface-600/50">
                    <input type="checkbox" class="google-service-check" value="${svc}" checked>
                    <span class="text-sm capitalize">${svc}</span>
                  </label>
                `).join('')}
              </div>
            </div>
          `}
        </div>
      `;
    }
  };
  
  const renderGrokSection = () => {
    if (grok.connected) {
      return `
        <div class="stat-card border-l-4 border-emerald-500">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
                <svg class="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.6 8.4l-3.4 6.8h-1.8l3.4-6.8H12V6h8v2.4h-1.4zM6 6h5v2.4H7.6l3.4 6.8h-1.8L5.6 8.4H4V6h2z"/>
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-white">Grok / X AI</h3>
                <p class="text-sm text-zinc-400">Full access (direct xAI key)</p>
              </div>
            </div>
            <span class="px-2 py-1 text-xs bg-emerald-500/20 text-emerald-400 rounded">Connected</span>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
            ${['Text Gen', 'Content Creation', 'Web Search', 'X Search', 'Image Gen', 'Image Edit', 'Vision'].map(s =>
              `<div class="flex items-center gap-2 p-2 rounded bg-surface-700/50 text-emerald-400">
                <span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#10b981;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
                <span class="text-xs">${s}</span>
              </div>`
            ).join('')}
          </div>
          
          <div class="flex gap-2">
            <button id="btn-grok-test" class="btn btn-secondary btn-sm">Test API</button>
            <button id="btn-grok-disconnect" class="btn btn-danger btn-sm">Remove Key</button>
          </div>
        </div>
      `;
    } else if (grok.openrouter_fallback) {
      const caps = [
        {name: 'Text Gen',         on: true},
        {name: 'Content Creation', on: true},
        {name: 'Vision',           on: true},
        {name: 'Web Search',       on: false},
        {name: 'X Search',         on: false},
        {name: 'Image Gen',        on: false},
        {name: 'Image Edit',       on: false},
      ];
      return `
        <div class="stat-card border-l-4 border-amber-500">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
                <svg class="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.6 8.4l-3.4 6.8h-1.8l3.4-6.8H12V6h8v2.4h-1.4zM6 6h5v2.4H7.6l3.4 6.8h-1.8L5.6 8.4H4V6h2z"/>
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-white">Grok / X AI</h3>
                <p class="text-sm text-zinc-400">Partial access via OpenRouter</p>
              </div>
            </div>
            <span class="px-2 py-1 text-xs bg-amber-500/20 text-amber-400 rounded">Fallback</span>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
            ${caps.map(c => {
              const icon = c.on
                ? '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#10b981;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>'
                : '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#52525b;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></span>';
              return `<div class="flex items-center gap-2 p-2 rounded bg-surface-700/50 ${c.on ? 'text-emerald-400' : 'text-zinc-600'}">
                ${icon}
                <span class="text-xs">${c.name}</span>
              </div>`;
            }).join('')}
          </div>
          
          <p class="text-xs text-zinc-500 mb-3">
            Model: configurable in <a href="#config" class="text-ghost-400 hover:underline">Config &rarr; Models</a>.
            Add an xAI key to unlock search, image gen/edit.
          </p>

          <div class="space-y-3">
            <input type="password" id="grok-api-key" placeholder="xAI API Key (starts with xai-)" class="form-input w-full text-sm">
            <button id="btn-grok-connect" class="btn btn-primary w-full">Add xAI Key for Full Access</button>
            <p class="text-xs text-zinc-500">
              Get your key from <a href="https://console.x.ai" target="_blank" class="text-ghost-400 hover:underline">xAI Console</a>
            </p>
          </div>
        </div>
      `;
    } else {
      return `
        <div class="stat-card">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
              <svg class="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M18.6 8.4l-3.4 6.8h-1.8l3.4-6.8H12V6h8v2.4h-1.4zM6 6h5v2.4H7.6l3.4 6.8h-1.8L5.6 8.4H4V6h2z"/>
              </svg>
            </div>
            <div>
              <h3 class="font-semibold text-white">Grok / X AI</h3>
              <p class="text-sm text-zinc-400">Access Grok AI and X/Twitter search</p>
            </div>
          </div>
          
          <div class="space-y-3">
            <input type="password" id="grok-api-key" placeholder="xAI API Key (starts with xai-)" class="form-input w-full text-sm">
            <button id="btn-grok-connect" class="btn btn-primary w-full">Save API Key</button>
            <p class="text-xs text-zinc-500">
              Get your API key from <a href="https://console.x.ai" target="_blank" class="text-ghost-400 hover:underline">xAI Console</a>.
              Or set up OpenRouter on the <a href="#models" class="text-ghost-400 hover:underline">Models page</a> to use Grok via OpenRouter.
            </p>
          </div>
        </div>
      `;
    }
  };

  const renderWebSearchSection = () => {
    const providers = webSearch.providers || [];
    const activeCount = webSearch.active_count || 0;
    const hasActive = activeCount > 0;

    const providerRows = providers.map(p => {
      const on = p.available;
      const icon = on
        ? '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#10b981;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>'
        : '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#52525b;flex-shrink:0"></span>';
      return `
        <div class="flex items-center gap-2 p-2 rounded bg-surface-700/50 ${on ? 'text-emerald-400' : 'text-zinc-500'}">
          ${icon}
          <span class="text-xs">${p.name}</span>
        </div>`;
    }).join('');

    return `
      <div class="stat-card ${hasActive ? 'border-l-4 border-emerald-500' : ''}">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-violet-500/20 flex items-center justify-center">
              <svg class="w-6 h-6 text-violet-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </div>
            <div>
              <h3 class="font-semibold text-white">Web Search</h3>
              <p class="text-sm text-zinc-400">${activeCount} provider${activeCount !== 1 ? 's' : ''} active with auto-fallback</p>
            </div>
          </div>
          ${hasActive
            ? '<span class="px-2 py-1 text-xs bg-emerald-500/20 text-emerald-400 rounded">Active</span>'
            : '<span class="px-2 py-1 text-xs bg-zinc-700 text-zinc-400 rounded">No providers</span>'}
        </div>

        <div class="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
          ${providerRows}
        </div>

        <p class="text-xs text-zinc-500">
          Perplexity uses your OpenRouter key. Grok uses your xAI key. For Brave or Gemini, set
          <code class="bg-surface-700 px-1 rounded">BRAVE_API_KEY</code> or
          <code class="bg-surface-700 px-1 rounded">GEMINI_API_KEY</code> in your environment.
        </p>
      </div>
    `;
  };

  const renderProviderBadges = (providers) => {
    return providers.map(p => {
      const on = p.available;
      const icon = on
        ? '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#10b981;flex-shrink:0"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>'
        : '<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:#52525b;flex-shrink:0"></span>';
      return `
        <div class="flex items-center gap-2 p-2 rounded bg-surface-700/50 ${on ? 'text-emerald-400' : 'text-zinc-500'}">
          ${icon}
          <span class="text-xs">${p.name}</span>
        </div>`;
    }).join('');
  };

  const renderFeatureCard = (title, subtitle, icon, featureData, extraHtml) => {
    const hasActive = featureData.active_count > 0;
    return `
      <div class="stat-card ${hasActive ? 'border-l-4 border-emerald-500' : ''}">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-ghost-500/20 flex items-center justify-center">
              <span class="text-xl">${icon}</span>
            </div>
            <div>
              <h3 class="font-semibold text-white">${title}</h3>
              <p class="text-sm text-zinc-400">${subtitle}</p>
            </div>
          </div>
          ${hasActive
            ? `<span class="px-2 py-1 text-xs bg-emerald-500/20 text-emerald-400 rounded">${featureData.active_count} active</span>`
            : '<span class="px-2 py-1 text-xs bg-zinc-700 text-zinc-400 rounded">No providers</span>'}
        </div>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
          ${renderProviderBadges(featureData.providers)}
        </div>
        ${extraHtml || ''}
      </div>`;
  };

  container.innerHTML = `
    <h1 class="page-header">Integrations</h1>
    <p class="page-desc">Connect Ghost to external services and APIs</p>
    
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      ${renderGoogleSection()}
      ${renderGrokSection()}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      ${renderWebSearchSection()}
      ${renderFeatureCard(
        'Image Generation', 
        `${imageGen.active_count} provider${imageGen.active_count !== 1 ? 's' : ''} with auto-fallback`,
        '🎨', imageGen,
        '<p class="text-xs text-zinc-500">Uses API keys from your configured LLM providers (Models page). Generates images via Gemini, DALL-E, or GPT-Image.</p>'
      )}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      ${renderFeatureCard(
        'Vision / Image Analysis',
        `${vision.active_count} provider${vision.active_count !== 1 ? 's' : ''} with auto-fallback`,
        '👁️', vision,
        '<p class="text-xs text-zinc-500">Uses existing provider keys. Ghost can analyze images, screenshots, and visual content via GPT-4o, Gemini, Claude, or Ollama (local).</p>'
      )}
      ${renderFeatureCard(
        'Text-to-Speech',
        `${tts.active_count} provider${tts.active_count !== 1 ? 's' : ''} available`,
        '🔊', tts,
        `<div class="mt-2 pt-2 border-t border-surface-600/30">
          <div class="flex gap-2">
            <input type="password" id="elevenlabs-api-key" placeholder="ElevenLabs API Key (optional)" class="form-input flex-1 text-xs">
            <button id="btn-elevenlabs-save" class="btn btn-secondary btn-sm">Save</button>
          </div>
          <p class="text-[10px] text-zinc-600 mt-1">Edge TTS is free (no key). OpenAI TTS uses your existing key. <a href="https://elevenlabs.io" target="_blank" class="text-ghost-400 hover:underline">ElevenLabs</a> requires a separate key.</p>
        </div>`
      )}
    </div>

    <div class="stat-card mt-6">
      <h3 class="text-sm font-semibold text-white mb-3">Available Tools</h3>
      <p class="text-sm text-zinc-400 mb-4">Once connected, Ghost can use these tools:</p>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">google_gmail</div>
          <div class="text-xs text-zinc-500 mt-1">Read, send, search emails</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">google_calendar</div>
          <div class="text-xs text-zinc-500 mt-1">List events, create meetings</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">google_drive</div>
          <div class="text-xs text-zinc-500 mt-1">List files, create folders</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">google_docs</div>
          <div class="text-xs text-zinc-500 mt-1">Create and edit documents</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">google_sheets</div>
          <div class="text-xs text-zinc-500 mt-1">Read/write spreadsheet data</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">grok_api</div>
          <div class="text-xs text-zinc-500 mt-1">Text, content creation, X/web search, image gen/edit</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">web_search</div>
          <div class="text-xs text-zinc-500 mt-1">Search the web with auto-fallback</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">generate_image</div>
          <div class="text-xs text-zinc-500 mt-1">AI image generation</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">image_analyze</div>
          <div class="text-xs text-zinc-500 mt-1">Analyze images and screenshots</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">text_to_speech</div>
          <div class="text-xs text-zinc-500 mt-1">Convert text to audio</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">web_fetch</div>
          <div class="text-xs text-zinc-500 mt-1">Fetch & extract web page content</div>
        </div>
        <div class="p-3 rounded bg-surface-700/50">
          <div class="font-medium text-white text-sm">security_audit</div>
          <div class="text-xs text-zinc-500 mt-1">Security scanning & auto-fix</div>
        </div>
      </div>
    </div>
  `;
  
  // Event handlers
  
  // Google credential save (advanced/manual setup)
  document.getElementById('btn-google-save-creds')?.addEventListener('click', async () => {
    const clientId = document.getElementById('google-client-id').value.trim();
    const clientSecret = document.getElementById('google-client-secret').value.trim();
    
    if (!clientId) {
      u.toast('Client ID is required', 'error');
      return;
    }
    
    try {
      await api.put('/api/integrations/google/config', { client_id: clientId, client_secret: clientSecret });
      u.toast('Google credentials saved');
      render(container); // Re-render
    } catch (e) {
      u.toast('Failed to save credentials: ' + e.message, 'error');
    }
  });
  
  // Google Sign In button (new OAuth flow)
  document.getElementById('btn-google-signin')?.addEventListener('click', async () => {
    const checkboxes = document.querySelectorAll('.google-service-check:checked');
    const services = Array.from(checkboxes).map(cb => cb.value);
    
    // If no services selected, default to all
    const selectedServices = services.length > 0 ? services : ['gmail', 'calendar', 'drive', 'docs', 'sheets'];
    
    try {
      const result = await api.get('/api/integrations/google/auth?' + selectedServices.map(s => `services=${s}`).join('&'));
      
      // Open OAuth popup
      const popup = window.open(result.auth_url, 'google-oauth', 'width=500,height=600,scrollbars=yes');
      
      // Listen for message from popup
      const handleMessage = (event) => {
        if (event.data?.type === 'google-auth-success') {
          window.removeEventListener('message', handleMessage);
          u.toast('Google connected successfully');
          render(container); // Re-render
        }
      };
      window.addEventListener('message', handleMessage);
      
      // Check if popup closed without success
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          window.removeEventListener('message', handleMessage);
          // Refresh status
          render(container);
        }
      }, 1000);
      
    } catch (e) {
      u.toast('Failed to start OAuth: ' + e.message, 'error');
    }
  });
  
  // Google connect (legacy, keep for compatibility)
  document.getElementById('btn-google-connect')?.addEventListener('click', async () => {
    const checkboxes = document.querySelectorAll('.google-service-check:checked');
    const services = Array.from(checkboxes).map(cb => cb.value);
    
    if (services.length === 0) {
      u.toast('Select at least one service', 'error');
      return;
    }
    
    try {
      const result = await api.get('/api/integrations/google/auth?' + services.map(s => `services=${s}`).join('&'));
      
      // Open OAuth popup
      const popup = window.open(result.auth_url, 'google-oauth', 'width=500,height=600,scrollbars=yes');
      
      // Listen for message from popup
      const handleMessage = (event) => {
        if (event.data?.type === 'google-auth-success') {
          window.removeEventListener('message', handleMessage);
          u.toast('Google connected successfully');
          render(container); // Re-render
        }
      };
      window.addEventListener('message', handleMessage);
      
      // Check if popup closed without success
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          window.removeEventListener('message', handleMessage);
          // Refresh status
          render(container);
        }
      }, 1000);
      
    } catch (e) {
      u.toast('Failed to start OAuth: ' + e.message, 'error');
    }
  });
  
  // Google disconnect
  document.getElementById('btn-google-disconnect')?.addEventListener('click', async () => {
    if (!confirm('Disconnect Google account?')) return;
    
    try {
      await api.post('/api/integrations/google/disconnect');
      u.toast('Google disconnected');
      render(container);
    } catch (e) {
      u.toast('Failed to disconnect: ' + e.message, 'error');
    }
  });
  
  // Google test
  document.getElementById('btn-google-test')?.addEventListener('click', async () => {
    const service = prompt('Which service to test? (gmail, calendar, drive, docs, sheets)', 'gmail');
    if (!service) return;
    
    try {
      const result = await api.get(`/api/integrations/google/test/${service}`);
      u.toast(`Test successful: ${JSON.stringify(result.data || result.message || result)}`);
    } catch (e) {
      u.toast('Test failed: ' + e.message, 'error');
    }
  });
  
  // Grok connect
  document.getElementById('btn-grok-connect')?.addEventListener('click', async () => {
    const apiKey = document.getElementById('grok-api-key').value.trim();
    
    if (!apiKey) {
      u.toast('API key is required', 'error');
      return;
    }
    
    try {
      await api.put('/api/integrations/grok', { api_key: apiKey });
      u.toast('Grok API key saved');
      render(container);
    } catch (e) {
      u.toast('Failed to save API key: ' + e.message, 'error');
    }
  });
  
  // Grok disconnect
  document.getElementById('btn-grok-disconnect')?.addEventListener('click', async () => {
    if (!confirm('Remove Grok API key?')) return;
    
    try {
      await api.delete('/api/integrations/grok');
      u.toast('Grok disconnected');
      render(container);
    } catch (e) {
      u.toast('Failed to disconnect: ' + e.message, 'error');
    }
  });
  
  // Grok test
  document.getElementById('btn-grok-test')?.addEventListener('click', async () => {
    try {
      u.toast('Grok API is configured');
    } catch (e) {
      u.toast('Test failed: ' + e.message, 'error');
    }
  });

  // ElevenLabs save
  document.getElementById('btn-elevenlabs-save')?.addEventListener('click', async () => {
    const apiKey = document.getElementById('elevenlabs-api-key').value.trim();
    if (!apiKey) {
      u.toast('API key is required', 'error');
      return;
    }
    try {
      await api.put('/api/integrations/elevenlabs', { api_key: apiKey });
      u.toast('ElevenLabs API key saved');
      render(container);
    } catch (e) {
      u.toast('Failed to save: ' + e.message, 'error');
    }
  });
}
