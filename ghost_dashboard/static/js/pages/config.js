/** Configuration page — tabbed layout */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/config');
  const cfg = data.config;
  const defs = data.defaults;

  const toggle = (key, label, desc) => {
    const on = cfg[key];
    const displayLabel = label || key.replace(/^enable_/, '').replace(/_/g, ' ');
    return `<div class="flex items-center justify-between py-2">
      <div>
        <span class="text-sm text-zinc-300">${displayLabel}</span>
        ${desc ? `<div class="text-[10px] text-zinc-600 mt-0.5">${desc}</div>` : ''}
      </div>
      <div class="toggle ${on ? 'on' : ''}" data-toggle="${key}"><span class="toggle-dot"></span></div>
    </div>`;
  };

  const numInput = (key, label, min, max, step) => `
    <div>
      <label class="form-label">${label}</label>
      <input type="number" class="form-input w-full" data-key="${key}" value="${cfg[key] ?? defs[key]}" min="${min}" max="${max}" step="${step || 1}">
    </div>`;

  const tabs = [
    { id: 'general',  label: 'General',  icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
    { id: 'features', label: 'Features', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
    { id: 'voice',    label: 'Voice',    icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z' },
    { id: 'growth',   label: 'Growth',   icon: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6' },
    { id: 'security', label: 'Security', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
    { id: 'models',   label: 'Models',   icon: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z' },
  ];

  container.innerHTML = `
    <h1 class="page-header">Configuration</h1>
    <p class="page-desc">All Ghost settings — saved to ~/.ghost/config.json</p>

    <div class="cfg-tabs">
      ${tabs.map((t, i) => `
        <button class="cfg-tab ${i === 0 ? 'active' : ''}" data-tab="${t.id}">
          <svg class="inline-block w-3.5 h-3.5 mr-1 -mt-0.5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${t.icon}"/></svg>
          ${t.label}
        </button>
      `).join('')}
    </div>

    <!-- ── General ──────────────────────────────────────────── -->
    <div class="cfg-tab-panel active" data-panel="general">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Timing &amp; Limits</h3>
          <div class="grid grid-cols-2 gap-3">
            ${numInput('poll_interval', 'Poll Interval (s)', 0.1, 10, 0.1)}
            ${numInput('min_length', 'Min Text Length', 1, 200, 1)}
            ${numInput('rate_limit_seconds', 'Rate Limit (s)', 0, 30, 1)}
            ${numInput('max_input_chars', 'Max Input Chars', 500, 50000, 500)}
            ${numInput('max_feed_items', 'Max Feed Items', 10, 500, 10)}
            ${numInput('tool_loop_max_steps', 'Max Tool Steps', 1, 500, 10)}
          </div>
        </div>
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Current Model</h3>
          <div class="font-mono text-sm text-ghost-400">${u.escapeHtml(cfg.model || defs.model)}</div>
          <div class="text-[10px] text-zinc-600 mt-1">Change on the Models page</div>
        </div>
      </div>
    </div>

    <!-- ── Features ─────────────────────────────────────────── -->
    <div class="cfg-tab-panel" data-panel="features">
      <div class="stat-card">
        <h3 class="text-sm font-semibold text-white mb-3">Feature Toggles</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8">
          ${['enable_tool_loop','enable_memory_db','enable_plugins','enable_skills','enable_system_tools','enable_browser_tools','enable_cron','enable_evolve','enable_integrations','enable_web_search','enable_web_fetch','enable_image_gen','enable_vision','enable_tts','enable_canvas','enable_security_audit','enable_session_memory'].map(k => toggle(k)).join('')}
        </div>
      </div>
    </div>

    <!-- ── Voice ────────────────────────────────────────────── -->
    <div class="cfg-tab-panel" data-panel="voice">
      <div class="stat-card" id="voice-section">
        <div class="flex items-center justify-between py-2 border-b border-surface-600/30 mb-4">
          <div>
            <span class="text-sm text-zinc-300">Enable voice features</span>
            <div class="text-[10px] text-zinc-600 mt-0.5">Voice Wake, Talk Mode, and push-to-talk mic in Chat</div>
          </div>
          <div class="toggle ${cfg.enable_voice !== false ? 'on' : ''}" data-toggle="enable_voice"><span class="toggle-dot"></span></div>
        </div>

        <div id="voice-controls" class="mb-4">
          <div class="flex items-center gap-3 mb-2">
            <span class="text-xs text-zinc-400">Status:</span>
            <span id="voice-state" class="text-xs text-zinc-500">Loading…</span>
          </div>
          <div class="flex gap-2">
            <button id="btn-voice-wake" class="btn btn-sm" style="font-size:0.7rem">Start Wake</button>
            <button id="btn-voice-talk" class="btn btn-sm" style="font-size:0.7rem">Start Talk</button>
            <button id="btn-voice-stop" class="btn btn-sm btn-danger hidden" style="font-size:0.7rem">Stop</button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="form-label">Wake Words</label>
            <input type="text" class="form-input w-full text-xs" id="cfg-voice-wake-words" value="${(cfg.voice_wake_words || ['ghost','hey ghost']).join(', ')}" placeholder="ghost, hey ghost">
            <div class="text-[10px] text-zinc-600 mt-1">Comma-separated trigger phrases</div>
          </div>
          <div>
            <label class="form-label">STT Provider</label>
            <select class="form-input w-full text-xs" id="cfg-voice-stt">
              <option value="auto" ${(cfg.voice_stt_provider||'auto')==='auto'?'selected':''}>Auto</option>
              <option value="moonshine" ${cfg.voice_stt_provider==='moonshine'?'selected':''}>Moonshine</option>
              <option value="openrouter" ${cfg.voice_stt_provider==='openrouter'?'selected':''}>OpenRouter</option>
              <option value="whisper" ${cfg.voice_stt_provider==='whisper'?'selected':''}>Whisper</option>
              <option value="groq" ${cfg.voice_stt_provider==='groq'?'selected':''}>Groq</option>
              <option value="vosk" ${cfg.voice_stt_provider==='vosk'?'selected':''}>Vosk</option>
            </select>
          </div>
          <div>
            <label class="form-label">Silence Threshold</label>
            <input type="number" class="form-input w-full text-xs" data-key="voice_silence_threshold" value="${cfg.voice_silence_threshold ?? 0.02}" min="0.001" max="1" step="0.005">
            <div class="text-[10px] text-zinc-600 mt-1">Volume level below which is considered silence</div>
          </div>
          <div>
            <label class="form-label">Silence Duration (s)</label>
            <input type="number" class="form-input w-full text-xs" data-key="voice_silence_duration" value="${cfg.voice_silence_duration ?? 2.0}" min="0.5" max="10" step="0.5">
            <div class="text-[10px] text-zinc-600 mt-1">Seconds of silence before ending capture</div>
          </div>
        </div>
        <label class="flex items-center gap-2 cursor-pointer mt-4">
          <input id="cfg-voice-chime" type="checkbox" ${cfg.voice_chime !== false ? 'checked' : ''}
            class="w-3.5 h-3.5 rounded bg-surface-700 border-surface-600 text-ghost-500">
          <span class="text-xs text-zinc-400">Chime on wake word detection</span>
        </label>
      </div>
    </div>

    <!-- ── Growth ───────────────────────────────────────────── -->
    <div class="cfg-tab-panel" data-panel="growth">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Self-Evolution</h3>
          <div class="flex items-center justify-between py-2 border-b border-surface-600/30 mb-3">
            <div>
              <span class="text-sm text-zinc-300">Auto-approve all evolutions</span>
              <div class="text-[10px] text-zinc-600 mt-0.5">Skip approval prompts — Ghost modifies itself autonomously</div>
            </div>
            <div class="toggle ${cfg.evolve_auto_approve ? 'on' : ''}" data-toggle="evolve_auto_approve"><span class="toggle-dot"></span></div>
          </div>
          <div class="flex items-center justify-between py-2">
            <div>
              <span class="text-sm text-zinc-300">Max evolutions per hour</span>
              <div class="text-[10px] text-zinc-600 mt-0.5">Rate limit on self-modifications</div>
            </div>
            <input type="number" min="1" max="100" class="bg-surface-700 text-white text-sm rounded px-2 py-1 w-20 text-right" data-key="max_evolutions_per_hour" value="${cfg.max_evolutions_per_hour ?? 25}">
          </div>
        </div>

        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Autonomous Growth</h3>
          <div class="flex items-center justify-between py-2 border-b border-surface-600/30 mb-3">
            <div>
              <span class="text-sm text-zinc-300">Enable autonomous growth</span>
              <div class="text-[10px] text-zinc-600 mt-0.5">Ghost proactively improves itself on a schedule</div>
            </div>
            <div class="toggle ${cfg.enable_growth !== false ? 'on' : ''}" data-toggle="enable_growth"><span class="toggle-dot"></span></div>
          </div>
          <div class="space-y-2" id="growth-schedules-container"></div>
          <div class="text-[10px] text-zinc-600 mt-2">Cron expressions — e.g. "0 */6 * * *" = every 6 hours</div>
        </div>
      </div>
    </div>

    <!-- ── Security ─────────────────────────────────────────── -->
    <div class="cfg-tab-panel" data-panel="security">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Allowed Commands</h3>
          <textarea id="allowed-commands" class="form-input w-full h-40 font-mono text-xs">${(cfg.allowed_commands || []).join(', ')}</textarea>
          <div class="text-[10px] text-zinc-600 mt-1">Comma-separated list of shell commands Ghost is allowed to run</div>
        </div>

        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Allowed Roots</h3>
          <textarea id="allowed-roots" class="form-input w-full h-40 font-mono text-xs">${(cfg.allowed_roots || []).join('\n')}</textarea>
          <div class="text-[10px] text-zinc-600 mt-1">One path per line — directories Ghost can read/write</div>
        </div>

        <div class="stat-card md:col-span-2">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-semibold text-white">Dangerous Interpreter Policy</h3>
            <div class="flex items-center gap-2">
              <span class="text-xs text-zinc-400">Enable dangerous interpreters</span>
              <div class="toggle ${cfg.enable_dangerous_interpreters ? 'on' : ''}" data-toggle="enable_dangerous_interpreters" id="toggle-dangerous-interpreters"><span class="toggle-dot"></span></div>
            </div>
          </div>
          <div class="text-[10px] text-zinc-600 mb-4">Controls access to python, pip, and other potentially dangerous shell commands. Requires confirmation to enable.</div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="dangerous-policy-container" style="${cfg.enable_dangerous_interpreters ? '' : 'opacity: 0.5; pointer-events: none;'}">
            <!-- Python Policy -->
            <div class="bg-surface-700/30 rounded p-3">
              <h4 class="text-xs font-medium text-ghost-400 mb-3 flex items-center gap-2">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>
                Python
              </h4>
              <div class="space-y-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs text-zinc-400">Allow Python execution</span>
                  <div class="toggle ${(cfg.dangerous_command_policy?.python?.allow !== false) ? 'on' : ''}" data-toggle="python_allow"><span class="toggle-dot"></span></div>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-xs text-zinc-400">Require workspace context</span>
                  <div class="toggle ${cfg.dangerous_command_policy?.python?.require_workspace ? 'on' : ''}" data-toggle="python_require_workspace"><span class="toggle-dot"></span></div>
                </div>
                <div>
                  <label class="text-xs text-zinc-500 block mb-1">Deny flags (comma-separated)</label>
                  <input type="text" class="form-input w-full text-xs font-mono" id="python-deny-flags" value="${(cfg.dangerous_command_policy?.python?.deny_flags || []).join(', ')}" placeholder="-c, -m, exec, eval, compile, __import__, os.system, subprocess, pty">
                </div>
              </div>
            </div>

            <!-- Pip Policy -->
            <div class="bg-surface-700/30 rounded p-3">
              <h4 class="text-xs font-medium text-amber-400 mb-3 flex items-center gap-2">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
                Pip
              </h4>
              <div class="space-y-3">
                <div class="flex items-center justify-between">
                  <span class="text-xs text-zinc-400">Allow pip execution</span>
                  <div class="toggle ${(cfg.dangerous_command_policy?.pip?.allow !== false) ? 'on' : ''}" data-toggle="pip_allow"><span class="toggle-dot"></span></div>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-xs text-zinc-400">Require workspace context</span>
                  <div class="toggle ${cfg.dangerous_command_policy?.pip?.require_workspace ? 'on' : ''}" data-toggle="pip_require_workspace"><span class="toggle-dot"></span></div>
                </div>
                <div>
                  <label class="text-xs text-zinc-500 block mb-1">Allow subcommands (comma-separated)</label>
                  <input type="text" class="form-input w-full text-xs font-mono" id="pip-allow-subcommands" value="${(cfg.dangerous_command_policy?.pip?.allow_subcommands || ['install', 'show', 'freeze', 'list', 'index']).join(', ')}" placeholder="install, show, freeze, list, index">
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tool Registration Security -->
        <div class="stat-card md:col-span-2">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-white">Tool Registration Security</h3>
            <div class="flex items-center gap-2">
              <span class="text-xs text-zinc-400">Strict tool registration</span>
              <div class="toggle ${cfg.strict_tool_registration !== false ? 'on' : ''}" data-toggle="strict_tool_registration"><span class="toggle-dot"></span></div>
            </div>
          </div>
          <div class="text-[10px] text-zinc-600">When enabled, prevents tools from being shadowed or replaced by malicious registrations. Disable only for debugging.</div>
        </div>
      </div>
    </div>

    <!-- ── Models ───────────────────────────────────────────── -->
    <div class="cfg-tab-panel" data-panel="models">
      <div class="stat-card mb-4">
        <h3 class="text-sm font-semibold text-white mb-1">Skill Model Aliases</h3>
        <div class="text-[10px] text-zinc-600 mb-3">Model aliases used by skills for per-skill model overrides. Built-in aliases: cheap, fast, capable, smart, vision, code. Changes take effect on next restart.</div>
        <div id="skill-model-aliases-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"></div>
        <div class="mt-3 pt-3 border-t border-surface-600/30">
          <div class="flex gap-2">
            <input type="text" id="new-alias-name" class="form-input text-xs w-32" placeholder="alias name">
            <input type="text" id="new-alias-model" class="form-input text-xs flex-1 font-mono" placeholder="provider/model-id">
            <button id="btn-add-alias" class="btn btn-sm btn-primary">Add</button>
          </div>
        </div>
      </div>
      <div class="stat-card">
        <h3 class="text-sm font-semibold text-white mb-1">Tool Models</h3>
        <div class="text-[10px] text-zinc-600 mb-3">Override the model IDs used by each tool. Leave blank to use defaults. Changes take effect on next restart.</div>
        <div id="tool-models-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"></div>
      </div>
    </div>

    <!-- ── Save bar ─────────────────────────────────────────── -->
    <div class="flex gap-3 mt-6">
      <button id="btn-save-config" class="btn btn-primary">Save Configuration</button>
      <button id="btn-reset-config" class="btn btn-danger btn-sm">Reset to Defaults</button>
    </div>
  `;

  // ── Tab switching ────────────────────────────────────────────
  container.querySelectorAll('.cfg-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.cfg-tab').forEach(t => t.classList.remove('active'));
      container.querySelectorAll('.cfg-tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = container.querySelector(`[data-panel="${btn.dataset.tab}"]`);
      if (panel) panel.classList.add('active');
    });
  });

  // ── Growth schedules ─────────────────────────────────────────
  const routines = [
    {id: 'tech_scout', label: 'Tech Scout', desc: 'Browse AI/tech news for improvements'},
    {id: 'health_check', label: 'Health Check', desc: 'Test APIs, tools, disk, connectivity'},
    {id: 'user_context', label: 'User Context', desc: 'Learn from emails & calendar'},
    {id: 'skill_improver', label: 'Skill Improver', desc: 'Review and improve skills'},
    {id: 'soul_evolver', label: 'Soul Evolver', desc: 'Reflect and refine SOUL.md'},
    {id: 'bug_hunter', label: 'Bug Hunter', desc: 'Scan logs and fix errors'},
    {id: 'competitive_intel', label: 'Competitive Intel', desc: 'Research OpenClaw for feature ideas'},
    {id: 'content_health', label: 'Content Health', desc: 'Test web_fetch extraction quality'},
    {id: 'security_patrol', label: 'Security Patrol', desc: 'Run security audit & auto-fix'},
    {id: 'visual_monitor', label: 'Visual Monitor', desc: 'Analyze screenshots for anomalies'},
  ];
  const defaultScheds = {tech_scout:'0 */12 * * *',health_check:'0 */2 * * *',user_context:'0 */4 * * *',skill_improver:'0 3 * * *',soul_evolver:'0 4 * * 0',bug_hunter:'0 */6 * * *',competitive_intel:'0 6 * * 1,4',content_health:'0 4 * * 0',security_patrol:'0 5 * * *',visual_monitor:'0 */8 * * *'};
  const schedContainer = container.querySelector('#growth-schedules-container');
  if (schedContainer) {
    schedContainer.innerHTML = routines.map(r => {
      const val = (cfg.growth_schedules || {})[r.id] || defaultScheds[r.id] || '';
      return '<div class="flex items-center gap-2 py-1">' +
        '<div class="flex-1 min-w-0">' +
        '<div class="text-xs text-zinc-300">' + u.escapeHtml(r.label) + '</div>' +
        '<div class="text-[10px] text-zinc-600">' + u.escapeHtml(r.desc) + '</div>' +
        '</div>' +
        '<input type="text" class="form-input text-xs w-28 font-mono growth-schedule" data-routine="' + r.id + '" value="' + u.escapeHtml(val) + '" placeholder="cron expr">' +
        '</div>';
    }).join('');
  }

  // ── Tool models ──────────────────────────────────────────────
  const toolModelDefs = [
    {key: 'image_gen_openrouter', label: 'Image Gen (OpenRouter)', def: 'google/gemini-3-pro-image-preview'},
    {key: 'image_gen_gemini', label: 'Image Gen (Gemini)', def: 'gemini-3-pro-image-preview'},
    {key: 'image_gen_openai', label: 'Image Gen (OpenAI)', def: 'gpt-image-1'},
    {key: 'vision_openai', label: 'Vision (OpenAI)', def: 'gpt-4o'},
    {key: 'vision_openrouter', label: 'Vision (OpenRouter)', def: 'openai/gpt-4o'},
    {key: 'vision_gemini', label: 'Vision (Gemini)', def: 'gemini-2.5-flash'},
    {key: 'vision_anthropic', label: 'Vision (Anthropic)', def: 'claude-sonnet-4-20250514'},
    {key: 'vision_ollama', label: 'Vision (Ollama)', def: 'llava'},
    {key: 'web_search_perplexity', label: 'Search (Perplexity/OR)', def: 'perplexity/sonar-pro'},
    {key: 'web_search_perplexity_direct', label: 'Search (Perplexity Direct)', def: 'sonar-pro'},
    {key: 'web_search_grok', label: 'Search (Grok)', def: 'grok-3-fast'},
    {key: 'web_search_openai', label: 'Search (OpenAI)', def: 'gpt-4.1-mini'},
    {key: 'web_search_gemini', label: 'Search (Gemini)', def: 'gemini-2.5-flash'},
    {key: 'tts_openai', label: 'TTS (OpenAI)', def: 'tts-1'},
    {key: 'tts_elevenlabs', label: 'TTS (ElevenLabs)', def: 'eleven_multilingual_v2'},
    {key: 'embedding_openrouter', label: 'Embedding (OpenRouter)', def: 'openai/text-embedding-3-small'},
    {key: 'embedding_gemini', label: 'Embedding (Gemini)', def: 'text-embedding-004'},
    {key: 'embedding_ollama', label: 'Embedding (Ollama)', def: 'nomic-embed-text'},
    {key: 'vision_deepseek', label: 'Vision (DeepSeek)', def: 'deepseek-chat'},
  ];
  const tmContainer = container.querySelector('#tool-models-container');
  if (tmContainer) {
    const saved = cfg.tool_models || {};
    tmContainer.innerHTML = toolModelDefs.map(m => {
      const val = saved[m.key] || '';
      return '<div>' +
        '<label class="text-[11px] text-zinc-400 block mb-0.5">' + u.escapeHtml(m.label) + '</label>' +
        '<input type="text" class="form-input w-full text-xs font-mono tool-model-input" ' +
          'data-tm-key="' + m.key + '" ' +
          'value="' + u.escapeHtml(val) + '" ' +
          'placeholder="' + u.escapeHtml(m.def) + '">' +
        '</div>';
    }).join('');
  }

  // ── Skill Model Aliases ──────────────────────────────────────
  const aliasContainer = container.querySelector('#skill-model-aliases-container');
  const aliasNameInput = container.querySelector('#new-alias-name');
  const aliasModelInput = container.querySelector('#new-alias-model');
  const addAliasBtn = container.querySelector('#btn-add-alias');
  let currentAliases = { ...(cfg.skill_model_aliases || {}) };

  function renderAliases() {
    if (!aliasContainer) return;
    const entries = Object.entries(currentAliases);
    if (entries.length === 0) {
      aliasContainer.innerHTML = '<div class="text-[11px] text-zinc-600 col-span-full">No custom aliases defined. Add one below.</div>';
      return;
    }
    aliasContainer.innerHTML = entries.map(([name, model]) => {
      return '<div class="flex items-center gap-2 bg-surface-700/50 rounded px-2 py-1.5">' +
        '<span class="text-xs text-ghost-400 font-medium">' + u.escapeHtml(name) + '</span>' +
        '<span class="text-[10px] text-zinc-500 flex-1 truncate font-mono">' + u.escapeHtml(model) + '</span>' +
        '<button class="btn btn-ghost btn-sm text-zinc-500 hover:text-red-400 remove-alias" data-alias="' + u.escapeHtml(name) + '" title="Remove">×</button>' +
        '</div>';
    }).join('');
    // Attach remove handlers
    aliasContainer.querySelectorAll('.remove-alias').forEach(btn => {
      btn.addEventListener('click', () => {
        const aliasName = btn.dataset.alias;
        delete currentAliases[aliasName];
        renderAliases();
      });
    });
  }

  renderAliases();

  if (addAliasBtn) {
    addAliasBtn.addEventListener('click', () => {
      const name = aliasNameInput?.value.trim();
      const model = aliasModelInput?.value.trim();
      if (!name || !model) {
        u.toast('Both alias name and model ID are required', 'error');
        return;
      }
      if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        u.toast('Alias name must be alphanumeric with hyphens/underscores only', 'error');
        return;
      }
      currentAliases[name] = model;
      if (aliasNameInput) aliasNameInput.value = '';
      if (aliasModelInput) aliasModelInput.value = '';
      renderAliases();
    });
  }

  // ── Toggles ──────────────────────────────────────────────────
  container.querySelectorAll('.toggle').forEach(el => {
    el.addEventListener('click', () => {
      el.classList.toggle('on');
      // Handle dangerous interpreters toggle to enable/disable policy container
      if (el.dataset.toggle === 'enable_dangerous_interpreters') {
        const containerEl = document.getElementById('dangerous-policy-container');
        if (containerEl) {
          if (el.classList.contains('on')) {
            containerEl.style.opacity = '1';
            containerEl.style.pointerEvents = 'auto';
          } else {
            containerEl.style.opacity = '0.5';
            containerEl.style.pointerEvents = 'none';
          }
        }
      }
    });
  });

  // ── Voice controls ───────────────────────────────────────────
  const voiceStateEl = container.querySelector('#voice-state');
  const wakeBtn = container.querySelector('#btn-voice-wake');
  const talkBtn = container.querySelector('#btn-voice-talk');
  const stopBtn2 = container.querySelector('#btn-voice-stop');

  async function refreshVoiceState() {
    try {
      const vs = await api.get('/api/voice/status');
      const active = vs.ok && vs.state !== 'idle' && vs.state !== 'unavailable';
      const labels = { wake_listening:'Wake active', talk_listening:'Talk active', capturing:'Capturing…', processing:'Processing…', speaking:'Speaking…' };
      voiceStateEl.textContent = active ? (labels[vs.state] || vs.state) : (vs.ok ? 'Idle' : 'Unavailable');
      voiceStateEl.className = active ? 'text-xs text-emerald-400' : 'text-xs text-zinc-500';
      if (active) { wakeBtn.classList.add('hidden'); talkBtn.classList.add('hidden'); stopBtn2.classList.remove('hidden'); }
      else { wakeBtn.classList.remove('hidden'); talkBtn.classList.remove('hidden'); stopBtn2.classList.add('hidden'); }
    } catch { voiceStateEl.textContent = 'Unavailable'; }
  }
  refreshVoiceState();

  wakeBtn?.addEventListener('click', async () => { await api.post('/api/voice/wake/start'); refreshVoiceState(); });
  talkBtn?.addEventListener('click', async () => { await api.post('/api/voice/talk/start'); refreshVoiceState(); });
  stopBtn2?.addEventListener('click', async () => { await api.post('/api/voice/wake/stop'); refreshVoiceState(); });

  // ── Save ─────────────────────────────────────────────────────
  document.getElementById('btn-save-config')?.addEventListener('click', async () => {
    const updates = {};
    container.querySelectorAll('[data-key]').forEach(inp => {
      const k = inp.dataset.key;
      updates[k] = inp.type === 'number' ? parseFloat(inp.value) : inp.value;
    });
    container.querySelectorAll('[data-toggle]').forEach(el => {
      updates[el.dataset.toggle] = el.classList.contains('on');
    });
    const cmds = document.getElementById('allowed-commands').value;
    updates.allowed_commands = cmds.split(',').map(s => s.trim()).filter(Boolean);
    const roots = document.getElementById('allowed-roots').value;
    updates.allowed_roots = roots.split('\n').map(s => s.trim()).filter(Boolean);

    // Dangerous interpreter policy
    const enableDangerous = container.querySelector('[data-toggle="enable_dangerous_interpreters"]')?.classList.contains('on') || false;
    updates.enable_dangerous_interpreters = enableDangerous;
    if (enableDangerous && !cfg.enable_dangerous_interpreters) {
      const token = prompt('WARNING: Enabling dangerous interpreters allows Python/pip execution.\n\nType "I_UNDERSTAND_THE_RISK" to confirm:');
      if (token === 'I_UNDERSTAND_THE_RISK') {
        updates.dangerous_interpreters_confirmation = token;
      } else {
        u.toast('Confirmation required to enable dangerous interpreters', 'error');
        return;
      }
    }
    const pythonAllowEl = container.querySelector('[data-toggle="python_allow"]');
    const pythonRequireWsEl = container.querySelector('[data-toggle="python_require_workspace"]');
    const pythonDenyFlagsEl = document.getElementById('python-deny-flags');
    const pipAllowEl = container.querySelector('[data-toggle="pip_allow"]');
    const pipRequireWsEl = container.querySelector('[data-toggle="pip_require_workspace"]');
    const pipAllowSubcommandsEl = document.getElementById('pip-allow-subcommands');

    updates.dangerous_command_policy = {
      python: {
        allow: pythonAllowEl ? pythonAllowEl.classList.contains('on') : true,
        require_workspace: pythonRequireWsEl ? pythonRequireWsEl.classList.contains('on') : false,
        deny_flags: pythonDenyFlagsEl ? pythonDenyFlagsEl.value.split(',').map(s => s.trim()).filter(Boolean) : []
      },
      pip: {
        allow: pipAllowEl ? pipAllowEl.classList.contains('on') : true,
        require_workspace: pipRequireWsEl ? pipRequireWsEl.classList.contains('on') : false,
        allow_subcommands: pipAllowSubcommandsEl ? pipAllowSubcommandsEl.value.split(',').map(s => s.trim()).filter(Boolean) : []
      }
    };

    const schedules = {};
    container.querySelectorAll('.growth-schedule').forEach(inp => {
      if (inp.value.trim()) schedules[inp.dataset.routine] = inp.value.trim();
    });
    if (Object.keys(schedules).length > 0) updates.growth_schedules = schedules;

    const toolModels = {};
    container.querySelectorAll('.tool-model-input').forEach(inp => {
      const v = inp.value.trim();
      if (v) toolModels[inp.dataset.tmKey] = v;
    });
    updates.tool_models = toolModels;

    // Include skill model aliases
    updates.skill_model_aliases = currentAliases;

    const wakeWordsEl = document.getElementById('cfg-voice-wake-words');
    if (wakeWordsEl) updates.voice_wake_words = wakeWordsEl.value.split(',').map(s => s.trim()).filter(Boolean);
    const sttEl = document.getElementById('cfg-voice-stt');
    if (sttEl) updates.voice_stt_provider = sttEl.value;
    const chimeEl = document.getElementById('cfg-voice-chime');
    if (chimeEl) updates.voice_chime = chimeEl.checked;

    await api.put('/api/config', updates);

    try { await api.post('/api/autonomy/reschedule'); } catch {}

    if (updates.voice_wake_words || updates.voice_stt_provider || updates.voice_chime !== undefined || updates.voice_silence_threshold || updates.voice_silence_duration) {
      try {
        const voicePayload = {};
        if (updates.voice_wake_words) voicePayload.voice_wake_words = updates.voice_wake_words;
        if (updates.voice_stt_provider) voicePayload.voice_stt_provider = updates.voice_stt_provider;
        if (updates.voice_chime !== undefined) voicePayload.voice_chime = updates.voice_chime;
        if (updates.voice_silence_threshold) voicePayload.voice_silence_threshold = updates.voice_silence_threshold;
        if (updates.voice_silence_duration) voicePayload.voice_silence_duration = updates.voice_silence_duration;
        await api.put('/api/voice/config', voicePayload);
      } catch {}
    }

    u.toast('Configuration saved');
  });

  document.getElementById('btn-reset-config')?.addEventListener('click', async () => {
    if (!confirm('Reset all settings to defaults?')) return;
    await api.put('/api/config', defs);
    u.toast('Reset to defaults');
    render(container);
  });
}
