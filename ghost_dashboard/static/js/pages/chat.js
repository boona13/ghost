/** Chat page — unified conversation UI replacing native panel */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

let eventSource = null;
let voicePollTimer = null;
let _lastMessageFromVoice = false;
let _activeProjectId = null;
let _reasoningMode = false;
let _currentSessionId = 'default';

window.addEventListener('hashchange', () => {
  if (voicePollTimer) { clearInterval(voicePollTimer); voicePollTimer = null; }
});

function _getActiveMessage() {
  try {
    const raw = sessionStorage.getItem('ghost_chat_active');
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function _setActiveMessage(messageId, userMessage) {
  sessionStorage.setItem('ghost_chat_active', JSON.stringify({ messageId, userMessage }));
}

function _clearActiveMessage() {
  sessionStorage.removeItem('ghost_chat_active');
}

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  if (eventSource) { eventSource.close(); eventSource = null; }
  if (voicePollTimer) { clearInterval(voicePollTimer); voicePollTimer = null; }

  let history = [];
  try {
    const data = await api.get('/api/chat/history');
    history = data.messages || [];
  } catch { /* empty */ }

  let voiceStatus = null;
  try {
    voiceStatus = await api.get('/api/voice/status');
  } catch { /* voice module may not be available */ }

  const voiceActive = voiceStatus && voiceStatus.ok && voiceStatus.state !== 'idle' && voiceStatus.state !== 'unavailable';
  const voiceAvailable = voiceStatus && voiceStatus.ok;

  const voiceStateLabels = {
    wake_listening: t('chat.voiceWake'),
    talk_listening: t('chat.talkMode'),
    capturing: t('chat.hearing'),
    processing: t('chat.processingVoice'),
    speaking: t('chat.speaking'),
  };
  const voiceStateLabel = voiceActive ? (voiceStateLabels[voiceStatus.state] || voiceStatus.state) : '';

  container.innerHTML = `
    <div class="chat-canvas-layout">
    <div class="chat-wrapper">
      <div class="chat-header">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-ghost-600/20 flex items-center justify-center">
            <svg class="w-5 h-5 text-ghost-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
            </svg>
          </div>
          <div>
            <div class="text-sm font-semibold text-white">${t('chat.title')}</div>
            <div id="chat-status" class="text-xs text-zinc-500">${t('chat.ready')}</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div id="voice-indicator" class="${voiceActive ? '' : 'hidden'}">
            <div class="voice-chat-indicator">
              <span class="voice-chat-dot"></span>
              <span id="voice-indicator-label" class="text-[10px] text-emerald-400">${voiceStateLabel}</span>
            </div>
          </div>
          <button id="canvas-toggle" class="btn btn-sm btn-ghost text-xs hidden" title="${t('chat.toggleCanvas')}">
            <svg class="w-3.5 h-3.5 inline -mt-0.5 mr-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"/>
            </svg>
            ${t('chat.canvas')}
          </button>
        </div>
      </div>

      <div id="project-bar" class="chat-project-bar">
        <svg class="w-3 h-3 text-zinc-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <select id="project-select" class="chat-project-select">
          <option value="">${t('chat.noProject')}</option>
        </select>
      </div>

      <div id="chat-messages" class="chat-messages">
        ${history.length === 0 ? `
          <div id="chat-empty" class="chat-empty">
            <div class="text-3xl mb-3 opacity-40">&#x1F47B;</div>
            <div class="text-sm font-medium text-zinc-400">${t('chat.noMessages')}</div>
            <div class="text-xs text-zinc-600 mt-1 mb-4">${t('chat.typeBelow')}</div>
            <div class="flex flex-wrap gap-2 justify-center max-w-md">
              <button class="chat-hint-chip" data-hint="What can you do?">${t('chat.hintCapabilities')}</button>
              <button class="chat-hint-chip" data-hint="Help me with my project">${t('chat.hintProject')}</button>
              <button class="chat-hint-chip" data-hint="Search the web for the latest news">${t('chat.hintWeb')}</button>
              <button class="chat-hint-chip" data-hint="Remember that I prefer dark mode">${t('chat.hintMemory')}</button>
            </div>
          </div>
        ` : ''}
      </div>

      <div class="chat-input-area chat-drop-zone" id="chat-drop-zone">
        <div id="chat-attachments" class="chat-attachments" style="display:none"></div>
        <div class="chat-input-wrapper">
          <button id="chat-clear" class="chat-new-session-btn" title="${t('chat.newSessionTitle')}">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 4v16m8-8H4"/>
            </svg>
            <span>${t('chat.newSessionTitle')}</span>
          </button>
          <button id="chat-attach" class="chat-attach-btn" title="${t('chat.attachFile')}">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/>
            </svg>
          </button>
          <input type="file" id="chat-file-input" class="chat-file-input" multiple
            accept=".wav,.mp3,.m4a,.flac,.ogg,.webm,.aac,.jpg,.jpeg,.png,.gif,.webp,.bmp,.mp4,.mov,.avi,.mkv,.flv,.wmv,.m4v">
          <textarea id="chat-input" class="chat-input"
            placeholder="${t('chat.messagePlaceholder')}"
            rows="1"></textarea>
          <button id="chat-voice-toggle" class="chat-voice-btn ${voiceAvailable ? '' : 'hidden'}" title="${t('chat.pushToTalk')}">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
            </svg>
          </button>
          <button id="chat-reasoning-toggle" class="chat-reasoning-btn" title="${t('chat.toggleReasoning')}">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
          </button>
          <button id="chat-send" class="chat-send-btn" title="${t('chat.sendEnter')}">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 19V5m0 0l-7 7m7-7l7 7"/>
            </svg>
          </button>
          <button id="chat-stop" class="chat-stop-btn" title="${t('common.stop')}" style="display:none">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
          </button>
        </div>
        <div class="text-[10px] text-zinc-600 mt-1 text-center">
          ${t('chat.enterToSend')}
        </div>
      </div>
    </div>

    <div id="canvas-panel" class="canvas-panel hidden">
      <div class="canvas-panel-header">
        <div class="flex items-center gap-2">
          <svg class="w-3.5 h-3.5 text-ghost-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"/>
          </svg>
          <span class="text-xs font-medium text-white">${t('chat.canvas')}</span>
        </div>
        <div class="flex items-center gap-1">
          <button id="canvas-open-tab" class="canvas-header-btn" title="${t('chat.openNewTab')}">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
            </svg>
          </button>
          <button id="canvas-refresh" class="canvas-header-btn" title="${t('common.refresh')}">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
          <button id="canvas-close" class="canvas-header-btn" title="${t('chat.closeCanvas')}">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
      <iframe id="canvas-iframe" class="canvas-iframe" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" src="about:blank"></iframe>
    </div>
    </div>
  `;

  const messagesEl = container.querySelector('#chat-messages');
  const inputEl = container.querySelector('#chat-input');
  const sendBtn = container.querySelector('#chat-send');
  const stopBtn = container.querySelector('#chat-stop');
  const statusEl = container.querySelector('#chat-status');
  const clearBtn = container.querySelector('#chat-clear');
  const attachBtn = container.querySelector('#chat-attach');
  const fileInput = container.querySelector('#chat-file-input');
  const dropZone = container.querySelector('#chat-drop-zone');
  const attachmentsEl = container.querySelector('#chat-attachments');
  const reasoningBtn = container.querySelector('#chat-reasoning-toggle');
  let processing = false;
  let activeMessageId = null;
  let attachments = [];

  for (const msg of history) {
    appendMessage(messagesEl, 'user', msg.user_message || '');
    if (msg.still_processing) {
      // Will be picked up by the reconnection logic below
    } else if (msg.assistant_message) {
      appendMessage(messagesEl, 'assistant', msg.assistant_message);
    }
  }
  scrollToBottom(messagesEl);

  const projectSelect = container.querySelector('#project-select');
  api.get('/api/projects').then(data => {
    const projects = data.projects || [];
    for (const p of projects) {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      projectSelect.appendChild(opt);
    }
    const saved = sessionStorage.getItem('ghost_active_project');
    if (saved && projectSelect.querySelector(`option[value="${saved}"]`)) {
      projectSelect.value = saved;
      _activeProjectId = saved;
    }
  }).catch(() => {});
  projectSelect.addEventListener('change', () => {
    _activeProjectId = projectSelect.value || null;
    if (_activeProjectId) {
      sessionStorage.setItem('ghost_active_project', _activeProjectId);
    } else {
      sessionStorage.removeItem('ghost_active_project');
    }
  });

  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
  });

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!processing) sendMessage();
    }
  });

  sendBtn.addEventListener('click', () => {
    if (!processing) sendMessage();
  });

  stopBtn.addEventListener('click', async () => {
    if (!activeMessageId) return;
    stopBtn.disabled = true;
    statusEl.textContent = t('chat.stopping');
    try {
      await api.post(`/api/chat/stop/${activeMessageId}`);
    } catch (err) {
      console.warn('Failed to stop chat session:', err);
    }
    try {
      await api.post('/api/chat/interrupt', { session_id: activeMessageId });
    } catch (err) {
      console.warn('Failed to interrupt generation:', err);
    }
  });

  container.addEventListener('click', (e) => {
    const chip = e.target.closest('.chat-hint-chip');
    if (!chip) return;
    inputEl.value = chip.dataset.hint;
    inputEl.focus();
    inputEl.dispatchEvent(new Event('input'));
  });

  clearBtn.addEventListener('click', async () => {
    try { await api.post('/api/chat/clear'); } catch {}
    messagesEl.innerHTML = `
      <div id="chat-empty" class="chat-empty">
        <div class="text-3xl mb-3 opacity-40">&#x1F47B;</div>
        <div class="text-sm font-medium text-zinc-400">${t('chat.newSession')}</div>
        <div class="text-xs text-zinc-600 mt-1">${t('chat.prevContextCleared')}</div>
      </div>
    `;
  });

  // ── Push-to-talk mic button ─────────────────────────────────
  const voiceToggleBtn = container.querySelector('#chat-voice-toggle');
  const voiceIndicator = container.querySelector('#voice-indicator');
  const voiceIndicatorLabel = container.querySelector('#voice-indicator-label');
  let pttPolling = false;

  function setPttState(state) {
    if (!voiceToggleBtn) return;
    if (state === 'listening') {
      voiceToggleBtn.classList.add('voice-active');
      voiceToggleBtn.title = t('chat.listening');
      inputEl.placeholder = t('chat.listening');
      if (voiceIndicator) voiceIndicator.classList.remove('hidden');
      if (voiceIndicatorLabel) voiceIndicatorLabel.textContent = t('chat.listening');
    } else if (state === 'transcribing') {
      voiceToggleBtn.classList.add('voice-active');
      voiceToggleBtn.title = t('chat.transcribing');
      inputEl.placeholder = t('chat.transcribing');
      if (voiceIndicatorLabel) voiceIndicatorLabel.textContent = t('chat.transcribing');
    } else {
      voiceToggleBtn.classList.remove('voice-active');
      voiceToggleBtn.title = t('chat.pushToTalk');
      inputEl.placeholder = t('chat.messagePlaceholder');
      if (voiceIndicator) voiceIndicator.classList.add('hidden');
    }
  }

  async function pollPttResult() {
    if (pttPolling) return;
    pttPolling = true;
    try {
      for (let i = 0; i < 200; i++) {
        await sleep(300);
        const ps = await api.get('/api/voice/ptt/status');
        if (ps.state === 'listening') {
          setPttState('listening');
        } else if (ps.state === 'transcribing') {
          setPttState('transcribing');
        } else if (ps.state === 'done') {
          setPttState('idle');
          if (ps.text) {
            _lastMessageFromVoice = true;
            inputEl.value = ps.text;
            inputEl.style.height = 'auto';
            inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
            sendMessage();
          }
          return;
        } else if (ps.state === 'error') {
          setPttState('idle');
          if (u?.toast) u.toast(`${t('chat.voiceError')} ${ps.error}`, 'error');
          return;
        } else {
          setPttState('idle');
          return;
        }
      }
      setPttState('idle');
    } finally {
      pttPolling = false;
    }
  }

  if (voiceToggleBtn) {
    voiceToggleBtn.addEventListener('click', async () => {
      if (processing || pttPolling) return;
      try {
        const result = await api.post('/api/voice/ptt/start');
        if (result.ok) {
          setPttState('listening');
          pollPttResult();
        } else {
          if (u?.toast) u.toast(t('chat.voicePrefix', {error: result.error}), 'error');
        }
      } catch (e) {
        if (u?.toast) u.toast(t('chat.voicePrefix', {error: e.message}), 'error');
      }
    });
  }

  // ── Voice Wake/Talk → Chat bridge ──────────────────────────
  let voiceStreamingMsgId = null;

  function updateVoiceIndicator(vs) {
    if (pttPolling) return;
    const active = vs.ok && vs.state !== 'idle' && vs.state !== 'unavailable';
    const labels = {
      wake_listening: t('chat.voiceWake'),
      talk_listening: t('chat.talkMode'),
      capturing: t('chat.hearing'),
      processing: t('chat.processingVoice'),
      speaking: t('chat.speaking'),
    };
    if (voiceIndicator) {
      if (active) {
        voiceIndicator.classList.remove('hidden');
        if (voiceIndicatorLabel) voiceIndicatorLabel.textContent = labels[vs.state] || vs.state;
      } else if (!pttPolling) {
        voiceIndicator.classList.add('hidden');
      }
    }
  }

  function handleVoiceMessage(vs) {
    if (processing) return;

    const msgId = vs.active_message_id;
    const userMsg = vs.last_user_message || vs.last_transcript || '';

    if (msgId && msgId !== voiceStreamingMsgId && userMsg) {
      voiceStreamingMsgId = msgId;

      const emptyEl = messagesEl.querySelector('#chat-empty');
      if (emptyEl) emptyEl.remove();

      appendMessage(messagesEl, 'user', userMsg);
      const thinkingEl = appendThinking(messagesEl);
      scrollToBottom(messagesEl);

      processing = true;
      activeMessageId = msgId;
      sendBtn.style.display = 'none';
      stopBtn.style.display = '';
      stopBtn.disabled = false;
      statusEl.textContent = t('chat.processingVoiceMsg');
      statusEl.className = 'text-xs text-amber-400 animate-pulse';

      streamResponse(msgId, thinkingEl, messagesEl, statusEl);
    }
  }

  if (voiceAvailable) {
    if (voiceActive && voiceStatus?.active_message_id) {
      handleVoiceMessage(voiceStatus);
    }

    voicePollTimer = setInterval(async () => {
      try {
        const vs = await api.get('/api/voice/status');
        updateVoiceIndicator(vs);
        if (vs.active_message_id && vs.active_message_id !== voiceStreamingMsgId) {
          handleVoiceMessage(vs);
        }
      } catch {}
    }, 1500);
  }

  // ── Reasoning mode toggle ───────────────────────────────────
  function updateReasoningButton() {
    if (_reasoningMode) {
      reasoningBtn.classList.add('active');
      reasoningBtn.style.color = '#a78bfa';
      reasoningBtn.title = t('chat.reasoningOn');
    } else {
      reasoningBtn.classList.remove('active');
      reasoningBtn.style.color = '';
      reasoningBtn.title = t('chat.toggleReasoning');
    }
  }
  
  async function toggleReasoningMode() {
    try {
      const res = await api.post('/api/chat/reasoning', { session_id: _currentSessionId });
      if (res.ok) {
        _reasoningMode = res.enabled;
        updateReasoningButton();
        showToast(_reasoningMode ? t('chat.reasoningOn') : t('chat.reasoningOff'));
      }
    } catch (e) {
      console.error('Failed to toggle reasoning mode:', e);
    }
  }
  
  async function loadReasoningStatus() {
    try {
      const res = await api.get(`/api/chat/reasoning/${_currentSessionId}`);
      if (res.ok) {
        _reasoningMode = res.enabled;
        updateReasoningButton();
      }
    } catch (e) {
      console.log('Reasoning mode not available');
    }
  }
  loadReasoningStatus();
  
  reasoningBtn.addEventListener('click', toggleReasoningMode);
  
  // ── Attachment handling ──────────────────────────────────────
  attachBtn.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      for (const file of fileInput.files) uploadFile(file);
      fileInput.value = '';
    }
  });

  ['dragenter', 'dragover'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('drag-over');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    if (e.dataTransfer?.files?.length) {
      for (const file of e.dataTransfer.files) uploadFile(file);
    }
  });

  async function uploadFile(file) {
    const id = Math.random().toString(36).slice(2, 10);
    const att = { id, filename: file.name, uploading: true, error: null, type: null, path: null, transcript: null };
    attachments.push(att);
    renderAttachments();

    try {
      const form = new FormData();
      form.append('file', file);
      const resp = await fetch('/api/chat/upload', { method: 'POST', body: form });
      const data = await resp.json();

      if (!data.ok) {
        att.uploading = false;
        att.error = data.error || t('chat.uploadFailed');
      } else {
        att.uploading = false;
        att.type = data.type;
        att.path = data.path;
        att.size_mb = data.size_mb || null;
        att.duration_secs = data.duration_secs || null;
        att.transcript = data.transcript || null;
        att.transcriptError = data.transcript_error || null;
      }
    } catch (err) {
      att.uploading = false;
      att.error = err.message || t('chat.uploadFailed');
    }
    renderAttachments();
  }

  function renderAttachments() {
    if (attachments.length === 0) {
      attachmentsEl.style.display = 'none';
      attachmentsEl.innerHTML = '';
      return;
    }
    attachmentsEl.style.display = '';
    attachmentsEl.innerHTML = attachments.map(att => {
      const icon = att.type === 'audio' ? '\u{1F3B5}' : att.type === 'video' ? '\u{1F3AC}' : att.type === 'image' ? '\u{1F5BC}' : '\u{1F4CE}';
      let stateClass = 'ready';
      let statusText = '';
      if (att.uploading) { stateClass = 'uploading'; statusText = t('chat.uploading'); }
      else if (att.error) { stateClass = 'error'; statusText = att.error; }
      else if (att.transcript) { statusText = t('chat.transcribed'); }
      else if (att.transcriptError) { statusText = t('chat.noSTT'); }
      else if (att.duration_secs) { statusText = `${att.duration_secs}s`; }
      else if (att.size_mb) { statusText = `${att.size_mb}MB`; }
      return `
        <div class="chat-att-pill ${stateClass}" data-att-id="${att.id}">
          <span class="chat-att-icon">${icon}</span>
          <span class="chat-att-name" title="${att.filename}">${att.filename}</span>
          ${statusText ? `<span class="chat-att-status">${statusText}</span>` : ''}
          <button class="chat-att-remove" data-att-id="${att.id}" title="${t('common.remove')}">&times;</button>
        </div>`;
    }).join('');

    attachmentsEl.querySelectorAll('.chat-att-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        attachments = attachments.filter(a => a.id !== btn.dataset.attId);
        renderAttachments();
      });
    });
  }

  // Reconnect to an in-progress message if the user navigated away and came back
  const active = _getActiveMessage();
  if (active && active.messageId) {
    (async () => {
      try {
        const data = await api.get(`/api/chat/status/${active.messageId}`);
        if (data.status === 'complete') {
          _clearActiveMessage();
          if (data.result) {
            const alreadyShown = history.some(
              m => (m.message_id === active.messageId) && m.assistant_message && m.assistant_message !== t('chat.interruptedMessage')
            );
            if (!alreadyShown) {
              appendMessage(messagesEl, 'assistant', data.result);
              scrollToBottom(messagesEl);
            }
          }
        } else if (data.status === 'processing') {
          processing = true;
          activeMessageId = active.messageId;
          sendBtn.style.display = 'none';
          stopBtn.style.display = '';
          stopBtn.disabled = false;
          statusEl.textContent = t('chat.processingReconnected');
          statusEl.className = 'text-xs text-amber-400 animate-pulse';

          const thinkingEl = appendThinking(messagesEl);
          const stepsContainer = document.createElement('div');
          stepsContainer.className = 'chat-steps';
          thinkingEl.parentNode.insertBefore(stepsContainer, thinkingEl);
          scrollToBottom(messagesEl);

          streamResponse(active.messageId, thinkingEl, messagesEl, statusEl);
        } else if (data.status === 'error') {
          _clearActiveMessage();
        }
      } catch {
        try {
          const rec = await api.get('/api/chat/restart-recovery');
          if (rec.recovery) {
            appendMessage(messagesEl, 'assistant', rec.recovery.result_hint);
            scrollToBottom(messagesEl);
          }
        } catch { /* server not up yet */ }
        _clearActiveMessage();
      }
    })();
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    const readyAtts = attachments.filter(a => !a.uploading && !a.error);

    if (!text && readyAtts.length === 0) return;

    const emptyEl = messagesEl.querySelector('#chat-empty');
    if (emptyEl) emptyEl.remove();

    processing = true;
    inputEl.value = '';
    inputEl.style.height = 'auto';
    sendBtn.style.display = 'none';
    stopBtn.style.display = '';
    stopBtn.disabled = false;

    const attsToSend = [...readyAtts];
    attachments = [];
    renderAttachments();

    let displayText = text;
    if (attsToSend.length > 0) {
      const names = attsToSend.map(a => a.filename).join(', ');
      displayText = text ? `${text}\n[${t('chat.attached')} ${names}]` : `[${t('chat.attached')} ${names}]`;
    }

    appendMessage(messagesEl, 'user', displayText);
    const thinkingEl = appendThinking(messagesEl);
    scrollToBottom(messagesEl);

    statusEl.textContent = t('chat.processing');
    statusEl.className = 'text-xs text-amber-400 animate-pulse';

    try {
      const payload = { message: text, enable_reasoning: _reasoningMode };
      if (_activeProjectId) {
        payload.project_id = _activeProjectId;
      }
      if (attsToSend.length > 0) {
        payload.attachments = attsToSend.map(a => ({
          filename: a.filename,
          type: a.type,
          path: a.path,
          size_mb: a.size_mb,
          duration_secs: a.duration_secs,
          transcript: a.transcript
        }));
      }
      const resp = await api.post('/api/chat/send', payload);
      if (!resp.ok) {
        thinkingEl.remove();
        appendMessage(messagesEl, 'error', resp.error || t('chat.failedToSend'));
        resetInput();
        return;
      }

      activeMessageId = resp.message_id;
      _setActiveMessage(resp.message_id, text);
      streamResponse(resp.message_id, thinkingEl, messagesEl, statusEl);
    } catch (err) {
      thinkingEl.remove();
      appendMessage(messagesEl, 'error', err.message);
      resetInput();
    }
  }

  function resetInput() {
    processing = false;
    activeMessageId = null;
    _lastMessageFromVoice = false;
    _clearActiveMessage();
    stopBtn.style.display = 'none';
    stopBtn.disabled = false;
    sendBtn.style.display = '';
    statusEl.textContent = t('chat.ready');
    statusEl.className = 'text-xs text-zinc-500';
    inputEl.focus();
  }

  function streamResponse(messageId, thinkingEl, messagesEl, statusEl) {
    if (eventSource) { eventSource.close(); eventSource = null; }

    const stepsContainer = document.createElement('div');
    stepsContainer.className = 'chat-steps';
    thinkingEl.parentNode.insertBefore(stepsContainer, thinkingEl);

    eventSource = new EventSource(`/api/chat/stream/${messageId}`);
    let stepCount = 0;
    let progressEl = null;
    let streamingEl = null;
    let streamBuf = '';

    function _ensureStreamingEl() {
      if (streamingEl) return;
      thinkingEl.style.display = 'none';
      streamingEl = document.createElement('div');
      streamingEl.className = 'chat-msg chat-msg-assistant';
      streamingEl.innerHTML = `
        <div class="chat-avatar">
          <svg class="w-4 h-4 text-ghost-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
          </svg>
        </div>
        <div class="chat-bubble chat-bubble-assistant">
          <div class="prose-ghost chat-streaming-text"></div>
        </div>
      `;
      messagesEl.appendChild(streamingEl);
    }

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'token') {
        _ensureStreamingEl();
        streamBuf += data.text;
        const textEl = streamingEl.querySelector('.chat-streaming-text');
        if (textEl) {
          textEl.innerHTML = formatMarkdown(streamBuf);
        }
        statusEl.textContent = t('chat.streaming') || 'Streaming...';
        scrollToBottom(messagesEl);
        return;
      }

      if (data.type === 'progress') {
        const msg = data.progress?.message || '';
        if (!progressEl) {
          progressEl = document.createElement('div');
          progressEl.className = 'chat-progress';
          stepsContainer.appendChild(progressEl);
        }
        const esc = window.GhostUtils?.escapeHtml || ((s) => s);
        progressEl.innerHTML = `
          <div class="chat-progress-inner">
            <span class="chat-progress-spinner"></span>
            <span class="chat-progress-text">${esc(msg)}</span>
          </div>`;
        statusEl.textContent = msg;
        scrollToBottom(messagesEl);
      }

      if (data.type === 'step') {
        if (progressEl) { progressEl.remove(); progressEl = null; }
        stepCount++;
        if (data.step.tool !== 'task_complete' && streamingEl) {
          streamBuf = '';
          const textEl = streamingEl.querySelector('.chat-streaming-text');
          if (textEl) textEl.innerHTML = '';
          streamingEl.style.display = 'none';
        }
        statusEl.textContent = t('chat.stepProgress', {n: stepCount, tool: data.step.tool});
        appendStep(stepsContainer, data.step);
        scrollToBottom(messagesEl);
      }

      if (data.type === 'approval_needed') {
        statusEl.textContent = t('chat.waitingApproval');
        statusEl.className = 'text-xs text-amber-400';
        appendApprovalCard(stepsContainer, data.approval, messagesEl);
        scrollToBottom(messagesEl);
      }

      if (data.type === 'done') {
        eventSource.close();
        eventSource = null;
        thinkingEl.remove();

        if (stepCount > 0) {
          collapseSteps(stepsContainer, stepCount);
        } else {
          stepsContainer.remove();
        }

        if (streamingEl) {
          const textEl = streamingEl.querySelector('.chat-streaming-text');
          if (textEl) {
            textEl.classList.remove('chat-streaming-text');
            textEl.innerHTML = formatMarkdown(data.result || t('chat.noResponse'));
          }
          streamingEl = null;
        } else {
          appendMessage(messagesEl, 'assistant', data.result || t('chat.noResponse'));
        }

        if (data.elapsed) {
          const meta = document.createElement('div');
          meta.className = 'chat-meta';
          meta.textContent = t('chat.metaInfo', {tools: data.tools_used?.length || 0, elapsed: data.elapsed});
          messagesEl.appendChild(meta);
        }

        if (_lastMessageFromVoice && data.result) {
          _lastMessageFromVoice = false;
          try { api.post('/api/voice/speak', { text: data.result }); } catch {}
        }

        scrollToBottom(messagesEl);
        resetInput();
      }

      if (data.type === 'error') {
        eventSource.close();
        eventSource = null;
        thinkingEl.remove();
        if (streamingEl) { streamingEl.remove(); streamingEl = null; }
        stepsContainer.remove();
        appendMessage(messagesEl, 'error', data.error);
        scrollToBottom(messagesEl);
        resetInput();
      }

      if (data.done && data.error) {
        eventSource.close();
        eventSource = null;
        thinkingEl.remove();
        if (streamingEl) { streamingEl.remove(); streamingEl = null; }
        stepsContainer.remove();
        appendMessage(messagesEl, 'error', data.error);
        scrollToBottom(messagesEl);
        resetInput();
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      eventSource = null;
      try { thinkingEl.remove(); } catch {}
      try { stepsContainer.remove(); } catch {}

      stopBtn.style.display = 'none';
      sendBtn.style.display = 'none';
      statusEl.textContent = t('chat.connectionLost');
      statusEl.className = 'text-xs text-amber-400 ghost-restart-pulse';

      _showRestartBanner(messagesEl);
      fallbackPoll(messageId, messagesEl, statusEl);
    };
  }

  function _showRestartBanner(messagesEl) {
    let banner = document.getElementById('ghost-restart-banner');
    if (banner) return;
    banner = document.createElement('div');
    banner.id = 'ghost-restart-banner';
    banner.className = 'chat-restart-banner';
    banner.innerHTML = `
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-amber-400 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        <span class="text-amber-300 text-sm font-medium">${t('chat.ghostRestartingCode')}</span>
      </div>
      <span class="text-zinc-500 text-xs">${t('chat.pageUpdateAuto')}</span>
    `;
    messagesEl.appendChild(banner);
    scrollToBottom(messagesEl);
  }

  function _removeRestartBanner() {
    const banner = document.getElementById('ghost-restart-banner');
    if (banner) banner.remove();
  }

  async function fallbackPoll(messageId, messagesEl, statusEl) {
    let consecutiveFailures = 0;

    for (let attempt = 0; attempt < 60; attempt++) {
      await sleep(1500);
      try {
        const data = await api.get(`/api/chat/status/${messageId}`);
        consecutiveFailures = 0;
        _removeRestartBanner();
        statusEl.textContent = t('chat.processingSteps', {n: data.steps?.length || 0});
        statusEl.className = 'text-xs text-amber-400 animate-pulse';

        if (data.status === 'complete') {
          appendMessage(messagesEl, 'assistant', data.result || t('chat.noResponse'));
          scrollToBottom(messagesEl);
          resetInput();
          return;
        }
        if (data.status === 'error') {
          appendMessage(messagesEl, 'error', data.error);
          scrollToBottom(messagesEl);
          resetInput();
          return;
        }
      } catch {
        consecutiveFailures++;
        statusEl.textContent = t('chat.systemRestarting');
        statusEl.className = 'text-xs text-amber-400 ghost-restart-pulse';

        if (consecutiveFailures >= 2) {
          const recovered = await _waitForRestart(messageId, messagesEl, statusEl);
          if (recovered) return;
        }
      }
    }

    _removeRestartBanner();
    appendMessage(messagesEl, 'error', t('chat.timedOut'));
    resetInput();
  }

  async function _waitForRestart(messageId, messagesEl, statusEl) {
    for (let i = 0; i < 30; i++) {
      await sleep(2000);
      try {
        const rec = await api.get('/api/chat/restart-recovery');

        _removeRestartBanner();

        if (rec.recovery && rec.recovery.result_hint) {
          appendMessage(messagesEl, 'assistant', rec.recovery.result_hint);
          scrollToBottom(messagesEl);
          resetInput();
          return true;
        }

        if (rec.ok) {
          try {
            const status = await api.get(`/api/chat/status/${messageId}`);
            if (status.status === 'complete' && status.result) {
              appendMessage(messagesEl, 'assistant', status.result);
              scrollToBottom(messagesEl);
              resetInput();
              return true;
            }
          } catch { /* session from old process, expected */ }

          appendMessage(messagesEl, 'assistant', t('chat.deploySuccess'));
          scrollToBottom(messagesEl);
          resetInput();
          return true;
        }
      } catch {
        statusEl.textContent = `${t('chat.systemRestarting')} (${i + 1}s)`;
      }
    }
    return false;
  }

  window.addEventListener('ghost:restarted', async () => {
    if (!processing || !activeMessageId) return;
    _removeRestartBanner();
    try {
      const rec = await api.get('/api/chat/restart-recovery');
      if (rec.recovery && rec.recovery.result_hint) {
        appendMessage(messagesEl, 'assistant', rec.recovery.result_hint);
      } else {
        appendMessage(messagesEl, 'assistant', t('chat.deploySuccess'));
      }
      scrollToBottom(messagesEl);
      resetInput();
    } catch { /* recovery handled by fallbackPoll / _waitForRestart */ }
  });

  // Show toast helper
  function showToast(msg, type='info') {
    if (window.GhostUtils?.toast) {
      window.GhostUtils.toast(msg, type);
    } else {
      const toast = document.createElement('div');
      toast.className = `toast toast-${type}`;
      toast.textContent = msg;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    }
  }

  // ── Canvas panel ──────────────────────────────────────────────
  const canvasPanel = container.querySelector('#canvas-panel');
  const canvasIframe = container.querySelector('#canvas-iframe');
  const canvasToggleBtn = container.querySelector('#canvas-toggle');
  const canvasCloseBtn = container.querySelector('#canvas-close');
  const canvasRefreshBtn = container.querySelector('#canvas-refresh');
  const canvasOpenTabBtn = container.querySelector('#canvas-open-tab');
  let _canvasVersion = -1;
  let _canvasVisible = false;
  let _canvasPollTimer = null;

  function showCanvas(target, forceReload) {
    const url = target ? (target.startsWith('http') ? target : (location.origin + target)) : '';
    if (url && (canvasIframe.src !== url || forceReload)) {
      canvasIframe.src = url + (url.includes('?') ? '&' : '?') + '_v=' + Date.now();
    }
    canvasPanel.classList.remove('hidden');
    canvasToggleBtn.classList.remove('hidden');
    container.querySelector('.chat-wrapper').classList.add('chat-with-canvas');
    _canvasVisible = true;
  }

  function hideCanvas() {
    canvasPanel.classList.add('hidden');
    container.querySelector('.chat-wrapper').classList.remove('chat-with-canvas');
    _canvasVisible = false;
  }

  canvasCloseBtn?.addEventListener('click', () => {
    hideCanvas();
    api.post('/api/canvas/hide').catch(() => {});
  });

  canvasToggleBtn?.addEventListener('click', () => {
    if (_canvasVisible) {
      hideCanvas();
    } else {
      showCanvas();
      api.post('/api/canvas/present').catch(() => {});
    }
  });

  canvasRefreshBtn?.addEventListener('click', () => {
    if (canvasIframe.src && canvasIframe.src !== 'about:blank') {
      canvasIframe.src = canvasIframe.src;
    }
  });

  canvasOpenTabBtn?.addEventListener('click', () => {
    if (canvasIframe.src && canvasIframe.src !== 'about:blank') {
      window.open(canvasIframe.src, '_blank');
    }
  });

  async function pollCanvas() {
    if (!location.hash.match(/^#?chat$/)) return;
    try {
      const state = await api.get('/api/canvas/state');
      if (state.version !== _canvasVersion) {
        const versionChanged = _canvasVersion > 0;
        _canvasVersion = state.version;
        if (state.visible && state.target) {
          showCanvas(state.target, versionChanged);
          canvasToggleBtn.classList.remove('hidden');
        } else if (!state.visible && _canvasVisible) {
          hideCanvas();
        }
        if (state.session_id) {
          canvasToggleBtn.classList.remove('hidden');
        }
      }
      const jsData = await api.get('/api/canvas/pending_js');
      if (jsData.scripts && jsData.scripts.length > 0) {
        for (const code of jsData.scripts) {
          try {
            canvasIframe.contentWindow?.eval(code);
          } catch (e) { console.warn('Canvas eval error:', e); }
        }
      }
    } catch { /* canvas unavailable */ }
  }

  pollCanvas();
  _canvasPollTimer = setInterval(pollCanvas, 2000);
  const _origHashChange = window._canvasHashCleanup;
  window._canvasHashCleanup = () => {
    if (_canvasPollTimer) { clearInterval(_canvasPollTimer); _canvasPollTimer = null; }
  };
  window.addEventListener('hashchange', () => {
    if (!location.hash.match(/^#?chat$/)) {
      if (_canvasPollTimer) { clearInterval(_canvasPollTimer); _canvasPollTimer = null; }
    }
  }, { once: true });
}


function appendMessage(container, role, content) {
  const div = document.createElement('div');
  const esc = window.GhostUtils?.escapeHtml || ((s) => s);

  if (role === 'user') {
    div.className = 'chat-msg chat-msg-user';
    div.innerHTML = `
      <div class="chat-bubble chat-bubble-user">
        <div class="whitespace-pre-wrap">${esc(content)}</div>
      </div>
    `;
  } else if (role === 'assistant') {
    div.className = 'chat-msg chat-msg-assistant';
    const { thinking, answer } = _parseThinking(content);
    let bodyHtml;
    if (thinking) {
      bodyHtml = `
        <details class="chat-thinking-block">
          <summary class="chat-thinking-summary">
            <svg class="w-3.5 h-3.5 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
            ${t('chat.thinking')}
          </summary>
          <div class="chat-thinking-content prose-ghost">${formatMarkdown(thinking)}</div>
        </details>
        <div class="prose-ghost">${formatMarkdown(answer)}</div>
      `;
    } else {
      bodyHtml = `<div class="prose-ghost">${formatMarkdown(content)}</div>`;
    }
    div.innerHTML = `
      <div class="chat-avatar">
        <svg class="w-4 h-4 text-ghost-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
        </svg>
      </div>
      <div class="chat-bubble chat-bubble-assistant">
        ${bodyHtml}
      </div>
    `;
  } else if (role === 'error') {
    div.className = 'chat-msg chat-msg-error';
    div.innerHTML = `
      <div class="chat-bubble chat-bubble-error">
        <span class="text-red-400 text-xs font-medium">${t('common.error')}:</span>
        <span class="text-red-300 text-xs">${esc(content)}</span>
      </div>
    `;
  }

  container.appendChild(div);
}

function appendThinking(container) {
  const div = document.createElement('div');
  div.className = 'chat-msg chat-msg-assistant';
  div.innerHTML = `
    <div class="chat-avatar">
      <svg class="w-4 h-4 text-ghost-400 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
      </svg>
    </div>
    <div class="chat-bubble chat-bubble-assistant">
      <div class="chat-thinking">
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
      </div>
    </div>
  `;
  container.appendChild(div);
  return div;
}

function _tryRenderAudioPlayer(resultStr) {
  try {
    const data = JSON.parse(resultStr);
    if (data.status === 'ok' && data.file) {
      const filename = data.file.replace(/\\/g,'/').split('/').pop();
      const provider = data.provider || 'tts';
      const voice = data.voice || '';
      return `
        <div class="chat-audio-player">
          <audio controls autoplay src="/api/audio/${encodeURIComponent(filename)}"></audio>
          <div class="chat-audio-meta">${provider}${voice ? ' / ' + voice : ''}</div>
        </div>`;
    }
  } catch { /* not JSON or no file field */ }
  return '';
}

function _audioPathToPlayer(text) {
  return text.replace(
    /(?:[A-Za-z]:[\\\/])?[\w/\\.-]+[\\\/]\.ghost[\\\/]audio[\\\/](tts_[\w.-]+\.mp3)/g,
    (match, filename) =>
      `<div class="chat-audio-player"><audio controls src="/api/audio/${encodeURIComponent(filename)}"></audio></div>`
  );
}

function appendStep(container, step) {
  const div = document.createElement('div');
  div.className = 'chat-step';
  const result = step.result || '';
  const preview = result.substring(0, 120).replace(/\n/g, ' ');
  const esc = window.GhostUtils?.escapeHtml || ((s) => s);

  const needsApproval = step.tool === 'evolve_plan' && result.includes('WAITING_FOR_APPROVAL');

  if (needsApproval) {
    const evoIdMatch = result.match(/Evolution planned:\s*(\w+)/);
    const evoId = evoIdMatch ? evoIdMatch[1] : '';
    const levelMatch = result.match(/Level:\s*(\d+)/);
    const level = levelMatch ? levelMatch[1] : '?';

    div.className = 'chat-step chat-step-approval';
    div.innerHTML = `
      <div class="chat-approval-card">
        <div class="chat-approval-header">
          <svg class="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
          </svg>
          <span class="text-amber-400 font-semibold text-xs">${t('chat.evoApprovalRequired')}</span>
          <span class="badge badge-yellow ml-auto">Level ${level}</span>
        </div>
        <div class="text-xs text-zinc-400 mt-1 mb-3">
          ${t('chat.evoApprovalMsg')}
          ${evoId ? `<span class="text-zinc-600 ml-1">(${evoId})</span>` : ''}
        </div>
        <div class="flex gap-2" id="approval-btns-${evoId}">
          <button class="btn btn-sm btn-primary chat-approve-btn" data-evo-id="${evoId}">
            ${t('common.approve')}
          </button>
          <button class="btn btn-sm btn-danger chat-reject-btn" data-evo-id="${evoId}">
            ${t('common.reject')}
          </button>
        </div>
      </div>
    `;

    container.appendChild(div);

    div.querySelector('.chat-approve-btn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const id = btn.dataset.evoId;
      btn.disabled = true;
      btn.textContent = t('chat.approving');
      try {
        await window.GhostAPI.post(`/api/evolve/approve/${id}`);
        const btnContainer = document.getElementById(`approval-btns-${id}`);
        if (btnContainer) {
          btnContainer.innerHTML = '<span class="text-emerald-400 text-xs font-medium">' + t('chat.approvedContinuing') + '</span>';
        }
      } catch (err) {
        btn.textContent = t('common.error');
      }
    });

    div.querySelector('.chat-reject-btn')?.addEventListener('click', async (e) => {
      const btn = e.target;
      const id = btn.dataset.evoId;
      btn.disabled = true;
      btn.textContent = t('chat.rejecting');
      try {
        await window.GhostAPI.post(`/api/evolve/reject/${id}`);
        const btnContainer = document.getElementById(`approval-btns-${id}`);
        if (btnContainer) {
          btnContainer.innerHTML = '<span class="text-red-400 text-xs font-medium">' + t('chat.rejectedStop') + '</span>';
        }
      } catch (err) {
        btn.textContent = t('common.error');
      }
    });

    return;
  }

  let audioHtml = '';
  if (step.tool === 'text_to_speech') {
    audioHtml = _tryRenderAudioPlayer(result);
  }

  div.innerHTML = `
    <div class="chat-step-header">
      <span class="chat-step-num">${t('chat.stepN', {n: step.step})}</span>
      <span class="chat-step-tool">${step.tool}</span>
      <span class="chat-step-time">${new Date(step.time).toLocaleTimeString()}</span>
    </div>
    ${audioHtml || (preview ? `<div class="chat-step-preview">${esc(preview)}</div>` : '')}
  `;
  container.appendChild(div);
}

function appendApprovalCard(container, approval, messagesEl) {
  const evoId = approval.evo_id || '';
  const level = approval.level || '?';
  const div = document.createElement('div');
  div.className = 'chat-step chat-step-approval';
  div.innerHTML = `
    <div class="chat-approval-card">
      <div class="chat-approval-header">
        <svg class="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
        </svg>
        <span class="text-amber-400 font-semibold text-xs">${t('chat.evoApprovalRequired')}</span>
        <span class="badge badge-yellow ml-auto">Level ${level}</span>
      </div>
      <div class="text-xs text-zinc-400 mt-1 mb-3">
        ${t('chat.evoApprovalMsg')}
        <span class="text-zinc-600 ml-1">(${evoId})</span>
      </div>
      <div class="flex gap-2" id="approval-btns-${evoId}">
        <button class="btn btn-sm btn-primary chat-approve-btn" data-evo-id="${evoId}">${t('common.approve')}</button>
        <button class="btn btn-sm btn-danger chat-reject-btn" data-evo-id="${evoId}">${t('common.reject')}</button>
      </div>
    </div>
  `;
  container.appendChild(div);

  div.querySelector('.chat-approve-btn')?.addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = t('chat.approving');
    try {
      await window.GhostAPI.post(`/api/evolve/approve/${evoId}`);
      const bc = document.getElementById(`approval-btns-${evoId}`);
      if (bc) bc.innerHTML = '<span class="text-emerald-400 text-xs font-medium">' + t('chat.approvedContinuing') + '</span>';
    } catch { btn.textContent = t('common.error'); }
  });

  div.querySelector('.chat-reject-btn')?.addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = t('chat.rejecting');
    try {
      await window.GhostAPI.post(`/api/evolve/reject/${evoId}`);
      const bc = document.getElementById(`approval-btns-${evoId}`);
      if (bc) bc.innerHTML = '<span class="text-red-400 text-xs font-medium">' + t('chat.rejectedCancelled') + '</span>';
    } catch { btn.textContent = t('common.error'); }
  });

  scrollToBottom(messagesEl);
}

function collapseSteps(container, count) {
  const steps = container.querySelectorAll('.chat-step');
  const summary = document.createElement('div');
  summary.className = 'chat-steps-summary';
  summary.innerHTML = `
    <button class="chat-steps-toggle">
      <svg class="w-3 h-3 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
      <span>${count} ${t('chat.toolSteps')}</span>
    </button>
  `;
  container.insertBefore(summary, container.firstChild);

  steps.forEach(s => s.style.display = 'none');

  summary.querySelector('.chat-steps-toggle').addEventListener('click', () => {
    const hidden = steps[0]?.style.display === 'none';
    steps.forEach(s => s.style.display = hidden ? '' : 'none');
    summary.querySelector('svg').style.transform = hidden ? 'rotate(90deg)' : '';
  });
}

function _parseThinking(text) {
  if (!text) return { thinking: null, answer: text || '' };
  const xmlMatch = text.match(/<thinking>([\s\S]*?)<\/thinking>\s*([\s\S]*)/i);
  if (xmlMatch) return { thinking: xmlMatch[1].trim(), answer: xmlMatch[2].trim() };
  const mdMatch = text.match(/\*\*Thinking:\*\*\s*([\s\S]*?)\s*\*\*Answer:\*\*\s*([\s\S]*)/i);
  if (mdMatch) return { thinking: mdMatch[1].trim(), answer: mdMatch[2].trim() };
  const plainMatch = text.match(/^Thinking:\s*\n([\s\S]*?)\n\s*Answer:\s*\n([\s\S]*)/im);
  if (plainMatch) return { thinking: plainMatch[1].trim(), answer: plainMatch[2].trim() };
  return { thinking: null, answer: text };
}

function formatMarkdown(text) {
  if (!text) return '';
  const esc = window.GhostUtils?.escapeHtml || ((s) => s);
  let html = esc(text);

  html = html.replace(/```(\w*)\n([\s\S]*?)```/g,
    '<pre class="chat-code-block"><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code class="chat-code-inline">$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/^### (.+)$/gm, '<h4 class="text-sm font-semibold text-white mt-3 mb-1">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 class="text-base font-semibold text-white mt-3 mb-1">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 class="text-lg font-bold text-white mt-3 mb-1">$1</h2>');
  html = html.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
  html = html.replace(/\n{2,}/g, '</p><p class="mt-2">');
  html = '<p>' + html + '</p>';
  html = html.replace(/<p>\s*<\/p>/g, '');

  html = _audioPathToPlayer(html);

  return html;
}

function scrollToBottom(el) {
  requestAnimationFrame(() => {
    el.scrollTop = el.scrollHeight;
  });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
