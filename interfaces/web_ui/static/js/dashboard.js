/**
 * dashboard.js
 * ============
 * The brain of the wall-mounted tablet.
 */

// ─── Settings-driven configuration ─────────────────────────────────────────
let appSettings = {};
let settingsLoaded = false;

function cfg(key, fallback) {
    const val = appSettings[key];
    return val !== undefined ? val : fallback;
}

const API_BASE = window.location.origin;

// Dynamic config (updated after settings load)
let POLL_INTERVAL = 2000;
let TASK_POLL_INTERVAL = 2000;
let TASK_POLL_MAX_ATTEMPTS = 60;
let TELEMETRY_MAX_ENTRIES = 50;
let ERROR_BANNER_TIMEOUT = 5000;

// State cache
let lastSwarmStatus = null;
let lastRoutingConfig = null;
let lastNodes = [];
let lastAgents = [];
let pollTimer = null;
let selectedAgentId = null;

// Chat state
let chatHistory = [];
let currentMode = 'agent';
let activeTaskId = null;

// Conversation persistence
const CONV_STORAGE_KEY = 'simplepod_conversations';
let conversations = [];
let activeConversationId = null;

// ─── Utility ───────────────────────────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }
function fmtNum(n) { return n === undefined || n === null ? '—' : n; }
function timeAgo(ts) {
    const s = Math.floor((Date.now() / 1000) - ts);
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    return Math.floor(s / 3600) + 'h ago';
}
function generateId() {
    return 'conv-' + Date.now().toString(36) + '-' + Math.random().toString(36).substr(2, 5);
}
function formatDate(ts) {
    const d = new Date(ts);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ─── API Client ────────────────────────────────────────────────────────────
async function apiGet(path) {
    try {
        const timeout = cfg('request_timeout_seconds', 30) * 1000;
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        const r = await fetch(API_BASE + path, { cache: 'no-store', signal: ctrl.signal });
        clearTimeout(timer);
        if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
        return await r.json();
    } catch (e) {
        console.error('API error', path, e);
        showError('Backend unreachable: ' + e.message);
        return null;
    }
}

async function apiPost(path, body = {}) {
    try {
        const timeout = cfg('request_timeout_seconds', 30) * 1000;
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        const r = await fetch(API_BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: ctrl.signal,
        });
        clearTimeout(timer);
        if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
        return await r.json();
    } catch (e) {
        console.error('API error', path, e);
        showError('Command failed: ' + e.message);
        return null;
    }
}

async function apiPut(path, body = {}) {
    try {
        const timeout = cfg('request_timeout_seconds', 30) * 1000;
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        const r = await fetch(API_BASE + path, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: ctrl.signal,
        });
        clearTimeout(timer);
        if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
        return await r.json();
    } catch (e) {
        console.error('API error', path, e);
        showError('Command failed: ' + e.message);
        return null;
    }
}

async function apiDelete(path) {
    try {
        const timeout = cfg('request_timeout_seconds', 30) * 1000;
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        const r = await fetch(API_BASE + path, {
            method: 'DELETE',
            signal: ctrl.signal,
        });
        clearTimeout(timer);
        if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
        return await r.json();
    } catch (e) {
        console.error('API error', path, e);
        showError('Command failed: ' + e.message);
        return null;
    }
}

function showError(msg) {
    const banner = $('#errorBanner');
    banner.textContent = msg;
    banner.classList.add('visible');
    setTimeout(() => banner.classList.remove('visible'), ERROR_BANNER_TIMEOUT);
}

// ─── Conversation Persistence ──────────────────────────────────────────────
function loadConversations() {
    try {
        const raw = localStorage.getItem(CONV_STORAGE_KEY);
        if (raw) {
            const data = JSON.parse(raw);
            conversations = data.conversations || [];
            activeConversationId = data.activeConversationId || null;
        }
    } catch (e) {
        console.warn('[conv] Failed to load conversations:', e);
        conversations = [];
    }
}

function saveConversations() {
    try {
        localStorage.setItem(CONV_STORAGE_KEY, JSON.stringify({
            conversations,
            activeConversationId,
        }));
    } catch (e) {
        console.warn('[conv] Failed to save conversations:', e);
    }
}

function createConversation(name, mode = 'agent') {
    const conv = {
        id: generateId(),
        name: name || 'Conversation ' + (conversations.length + 1),
        mode: mode,
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
    };
    conversations.unshift(conv);
    activeConversationId = conv.id;
    saveConversations();
    return conv;
}

function deleteConversation(id) {
    conversations = conversations.filter(c => c.id !== id);
    if (activeConversationId === id) {
        activeConversationId = conversations.length > 0 ? conversations[0].id : null;
    }
    saveConversations();
}

function renameConversation(id, name) {
    const conv = conversations.find(c => c.id === id);
    if (conv) {
        conv.name = name;
        conv.updatedAt = Date.now();
        saveConversations();
    }
}

function switchConversation(id) {
    activeConversationId = id;
    const conv = conversations.find(c => c.id === id);
    if (conv) {
        chatHistory = JSON.parse(JSON.stringify(conv.messages));
        currentMode = conv.mode || 'agent';
        // Update mode tabs
        $$('.mode-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.mode === currentMode);
        });
    } else {
        chatHistory = [];
    }
    saveConversations();
    renderChat();
    renderConversationList();
}

function saveCurrentConversation() {
    if (!activeConversationId) {
        if (chatHistory.length === 0) return;
        createConversation(null, currentMode);
    }
    const conv = conversations.find(c => c.id === activeConversationId);
    if (conv) {
        conv.messages = JSON.parse(JSON.stringify(chatHistory));
        conv.mode = currentMode;
        conv.updatedAt = Date.now();
        saveConversations();
        renderConversationList();
    }
}

function renderConversationList() {
    const select = $('#conversationSelect');
    if (!select) return;
    const opts = conversations.map(c => {
        const selected = c.id === activeConversationId ? 'selected' : '';
        return `<option value="${c.id}" ${selected}>${escapeHtml(c.name)} · ${formatDate(c.updatedAt)}</option>`;
    });
    select.innerHTML = '<option value="">New conversation...</option>' + opts.join('');
}

// ─── Settings System ───────────────────────────────────────────────────────
async function loadSettings() {
    const data = await apiGet('/settings');
    if (data) {
        appSettings = data;
        settingsLoaded = true;
        applySettings();
        console.log('[settings] Loaded', Object.keys(data).length, 'keys');
        addTelemetry('SETTINGS', 'Configuration loaded');
        return true;
    }
    console.warn('[settings] Failed to load settings, using defaults');
    return false;
}

function applySettings() {
    POLL_INTERVAL = cfg('ui_poll_interval_ms', 2000);
    TASK_POLL_INTERVAL = cfg('ui_task_poll_interval_ms', 2000);
    TASK_POLL_MAX_ATTEMPTS = cfg('ui_task_poll_max_attempts', 60);
    TELEMETRY_MAX_ENTRIES = cfg('ui_telemetry_log_max_entries', 50);
    ERROR_BANNER_TIMEOUT = cfg('ui_error_banner_auto_hide_ms', 5000);

    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = setInterval(pollAll, POLL_INTERVAL);
    }

    const theme = cfg('ui_theme', 'dark');
    document.body.classList.toggle('theme-light', theme === 'light');

    const fontSize = cfg('ui_font_size', 'medium');
    document.body.classList.remove('font-small', 'font-medium', 'font-large');
    document.body.classList.add('font-' + fontSize);

    document.body.classList.toggle('compact-mode', cfg('ui_compact_mode', false));
}

function populateSettingsForm() {
    $$('.setting-input').forEach(el => {
        const key = el.dataset.key;
        if (!key) return;
        const val = appSettings[key];
        if (val === undefined) return;

        if (el.type === 'checkbox') {
            el.checked = !!val;
        } else if (el.dataset.type === 'csv') {
            el.value = Array.isArray(val) ? val.join(', ') : String(val);
        } else if (el.classList.contains('setting-json')) {
            el.value = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        } else {
            el.value = String(val);
        }
    });
}

function collectSettingsFromForm() {
    const updates = {};
    $$('.setting-input').forEach(el => {
        const key = el.dataset.key;
        if (!key) return;

        let val;
        if (el.type === 'checkbox') {
            val = el.checked;
        } else if (el.dataset.type === 'csv') {
            val = el.value.split(',').map(s => s.trim()).filter(s => s);
        } else if (el.classList.contains('setting-json')) {
            try {
                val = JSON.parse(el.value);
            } catch (e) {
                showError('Invalid JSON for ' + key + ': ' + e.message);
                val = appSettings[key];
            }
        } else if (el.type === 'number') {
            val = el.value.includes('.') ? parseFloat(el.value) : parseInt(el.value, 10);
            if (isNaN(val)) val = appSettings[key];
        } else {
            val = el.value;
        }
        updates[key] = val;
    });
    return updates;
}

async function saveSettings() {
    const updates = collectSettingsFromForm();
    const result = await apiPut('/settings', updates);
    if (result) {
        appSettings = result;
        applySettings();
        const status = $('#settingsStatus');
        status.textContent = '✅ Saved!';
        status.classList.add('success');
        setTimeout(() => { status.textContent = ''; status.classList.remove('success'); }, 3000);
        addTelemetry('SETTINGS', 'Settings saved');
    }
}

async function resetSettings() {
    if (!confirm('Are you sure? This will reset ALL settings to factory defaults.')) return;
    const result = await apiPost('/settings/reset');
    if (result) {
        appSettings = result;
        populateSettingsForm();
        applySettings();
        const status = $('#settingsStatus');
        status.textContent = '✅ Reset to defaults!';
        status.classList.add('success');
        setTimeout(() => { status.textContent = ''; status.classList.remove('success'); }, 3000);
        addTelemetry('SETTINGS', 'Factory reset performed');
    }
}

function exportSettings() {
    const blob = new Blob([JSON.stringify(appSettings, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'simplepod_settings.json';
    a.click();
    URL.revokeObjectURL(url);
    addTelemetry('SETTINGS', 'Settings exported to file');
}

async function importSettings(file) {
    try {
        const text = await file.text();
        const imported = JSON.parse(text);
        const result = await apiPut('/settings', imported);
        if (result) {
            appSettings = result;
            populateSettingsForm();
            applySettings();
            const status = $('#settingsStatus');
            status.textContent = '✅ Imported!';
            status.classList.add('success');
            setTimeout(() => { status.textContent = ''; status.classList.remove('success'); }, 3000);
            addTelemetry('SETTINGS', 'Settings imported from file');
        }
    } catch (e) {
        showError('Import failed: ' + e.message);
    }
}

// ─── Settings UI ─────────────────────────────────────────────────────────────
function openSettings() {
    populateSettingsForm();
    $('#settingsOverlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeSettings() {
    $('#settingsOverlay').classList.remove('active');
    document.body.style.overflow = '';
}

function initSettingsUI() {
    $('#btnSettings').addEventListener('click', openSettings);
    $('#btnCloseSettings').addEventListener('click', closeSettings);
    $('#btnSaveSettings').addEventListener('click', saveSettings);
    $('#btnResetSettings').addEventListener('click', resetSettings);
    $('#btnExportSettings').addEventListener('click', exportSettings);
    $('#btnImportSettings').addEventListener('click', () => $('#importFileInput').click());
    $('#importFileInput').addEventListener('change', (e) => {
        if (e.target.files[0]) importSettings(e.target.files[0]);
        e.target.value = '';
    });

    $$('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const section = tab.dataset.tab;
            $$('.settings-tab').forEach(t => t.classList.remove('active'));
            $$('.settings-section').forEach(s => s.classList.remove('active'));
            tab.classList.add('active');
            $(`.settings-section[data-section="${section}"]`).classList.add('active');
        });
    });

    $('#settingsOverlay').addEventListener('click', (e) => {
        if (e.target === $('#settingsOverlay')) closeSettings();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSettings();
    });
}

// ─── Agent Detail Modal ──────────────────────────────────────────────────────
function openAgentDetail(agentId) {
    selectedAgentId = agentId;
    loadAgentDetail(agentId);
    $('#agentDetailOverlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeAgentDetail() {
    $('#agentDetailOverlay').classList.remove('active');
    document.body.style.overflow = '';
    selectedAgentId = null;
}

async function loadAgentDetail(agentId) {
    const data = await apiGet(`/swarm/agents/${agentId}`);
    if (!data) {
        $('#agentDetailTitle').textContent = '👷 Agent Not Found';
        return;
    }
    $('#agentDetailTitle').textContent = `👷 ${data.agent_id}`;
    $('#agentDetailStatus').textContent = data.alive ? (data.status || 'idle') : 'DEAD';
    $('#agentDetailStatus').style.color = data.alive ? 'var(--accent-green)' : 'var(--accent-red)';
    $('#agentDetailUptime').textContent = fmtNum(data.uptime_seconds) + 's';
    $('#agentDetailCompleted').textContent = fmtNum(data.tasks_completed);
    $('#agentDetailFailed').textContent = fmtNum(data.tasks_failed);
    $('#agentDetailHeartbeat').textContent = data.last_heartbeat ? timeAgo(data.last_heartbeat) : '—';

    if (data.current_task) {
        $('#agentDetailTask').innerHTML = `
            <div><strong>Task ID:</strong> ${data.current_task.task_id}</div>
            <div><strong>Status:</strong> ${data.current_task.status}</div>
            <div><strong>Model:</strong> ${data.current_task.model || '—'}</div>
            <div style="margin-top:4px;white-space:pre-wrap;word-break:break-word;">${escapeHtml(data.current_task.prompt || '')}</div>
        `;
    } else {
        $('#agentDetailTask').textContent = 'No active task';
    }

    // Load per-agent config
    const cfgData = await apiGet(`/swarm/agents/${agentId}/config`);
    if (cfgData && cfgData.config) {
        $('#agentDetailModel').value = cfgData.config.model || '';
        $('#agentDetailTemp').value = cfgData.config.temperature ?? '';
        $('#agentDetailMaxTokens').value = cfgData.config.max_tokens ?? '';
    } else {
        $('#agentDetailModel').value = '';
        $('#agentDetailTemp').value = '';
        $('#agentDetailMaxTokens').value = '';
    }

    // Show/hide remove button based on alive status
    const removeBtn = $('#btnRemoveAgent');
    if (removeBtn) {
        removeBtn.style.display = data.alive ? 'none' : 'inline-block';
    }

    // Populate model dropdown with available models
    populateAgentDetailModels();
}

async function populateAgentDetailModels() {
    const select = $('#agentDetailModel');
    if (!select || select.dataset.populated) return;
    const models = await apiGet('/swarm/models');
    const current = select.value;
    let opts = '<option value="">Use global default</option>';
    if (models && models.length) {
        opts += models.map(m => `<option value="${m}">${m}</option>`).join('');
    }
    select.innerHTML = opts;
    select.value = current;
    select.dataset.populated = 'true';
}

function initAgentDetailUI() {
    $('#btnCloseAgentDetail').addEventListener('click', closeAgentDetail);
    $('#agentDetailOverlay').addEventListener('click', (e) => {
        if (e.target === $('#agentDetailOverlay')) closeAgentDetail();
    });
    $('#btnKillAgent').addEventListener('click', async () => {
        if (!selectedAgentId) return;
        if (!confirm(`Kill ${selectedAgentId}? Its task will be requeued.`)) return;
        const res = await apiPost(`/swarm/agents/${selectedAgentId}/kill`);
        if (res) {
            addTelemetry('AGENT', `${selectedAgentId} killed by user`);
            closeAgentDetail();
            pollAll();
        }
    });
    $('#btnRemoveAgent').addEventListener('click', async () => {
        if (!selectedAgentId) return;
        if (!confirm(`Permanently remove ${selectedAgentId} from the registry?`)) return;
        const res = await apiDelete(`/swarm/agents/${selectedAgentId}`);
        if (res) {
            addTelemetry('AGENT', `${selectedAgentId} removed by user`);
            closeAgentDetail();
            pollAll();
        }
    });
    $('#btnSaveAgentConfig').addEventListener('click', async () => {
        if (!selectedAgentId) return;
        const config = {};
        const model = $('#agentDetailModel').value;
        const temp = $('#agentDetailTemp').value;
        const maxTokens = $('#agentDetailMaxTokens').value;
        if (model) config.model = model;
        if (temp !== '') config.temperature = parseFloat(temp);
        if (maxTokens !== '') config.max_tokens = parseInt(maxTokens);
        const res = await apiPut(`/swarm/agents/${selectedAgentId}/config`, { config });
        const status = $('#agentConfigStatus');
        if (res) {
            status.textContent = '✅ Saved!';
            status.className = 'settings-status success';
            addTelemetry('AGENT', `${selectedAgentId} config updated`);
        } else {
            status.textContent = '❌ Failed';
            status.className = 'settings-status';
        }
        setTimeout(() => { status.textContent = ''; status.className = 'settings-status'; }, 3000);
    });
}

// ─── Chat System ─────────────────────────────────────────────────────────────
function initChatUI() {
    loadConversations();
    renderConversationList();

    // If there's an active conversation, load it
    if (activeConversationId) {
        const conv = conversations.find(c => c.id === activeConversationId);
        if (conv) {
            chatHistory = JSON.parse(JSON.stringify(conv.messages));
            currentMode = conv.mode || 'agent';
        }
    }
    renderChat();

    // Update mode tabs to reflect loaded mode
    $$('.mode-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.mode === currentMode);
    });

    // Mode tabs
    $$('.mode-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            currentMode = tab.dataset.mode;
            $$('.mode-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            saveCurrentConversation();
        });
    });

    // Conversation selector
    $('#conversationSelect').addEventListener('change', (e) => {
        const id = e.target.value;
        if (!id) {
            // New conversation selected
            startNewConversation();
        } else {
            switchConversation(id);
        }
    });

    // New conversation button
    $('#btnNewConv').addEventListener('click', () => {
        startNewConversation();
    });

    // Rename conversation
    $('#btnRenameConv').addEventListener('click', () => {
        if (!activeConversationId) {
            showError('No active conversation to rename');
            return;
        }
        const conv = conversations.find(c => c.id === activeConversationId);
        if (!conv) return;
        const name = prompt('Rename conversation:', conv.name);
        if (name && name.trim()) {
            renameConversation(activeConversationId, name.trim());
            renderConversationList();
        }
    });

    // Delete conversation
    $('#btnDeleteConv').addEventListener('click', () => {
        if (!activeConversationId) {
            showError('No active conversation to delete');
            return;
        }
        const conv = conversations.find(c => c.id === activeConversationId);
        if (!conv) return;
        if (!confirm(`Delete "${conv.name}"? This cannot be undone.`)) return;
        deleteConversation(activeConversationId);
        if (conversations.length > 0) {
            switchConversation(conversations[0].id);
        } else {
            startNewConversation();
        }
    });

    // Send message
    $('#chatForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = $('#chatInput');
        const text = input.value.trim();
        if (!text || activeTaskId) return;

        // Ensure we have an active conversation
        if (!activeConversationId) {
            createConversation(null, currentMode);
        }

        // Add user message
        chatHistory.push({ role: 'user', content: text });
        input.value = '';
        input.style.height = 'auto';
        renderChat();
        saveCurrentConversation();

        // Show thinking
        showThinking(true);

        // Build messages payload from history (exclude the last user msg since we send prompt separately)
        const messagesPayload = chatHistory.slice(0, -1).map(m => ({
            role: m.role,
            content: m.content,
        }));

        const modelHint = $('#inferModel')?.value || cfg('default_model', 'llama3.2');
        const temperature = $('#inferTemp') ? (parseInt($('#inferTemp').value) / 10) : cfg('default_temperature', 0.7);

        const res = await apiPost('/routing/infer', {
            prompt: text,
            model_hint: modelHint,
            temperature: temperature,
            messages: messagesPayload,
            mode: currentMode,
        });

        if (res && res.task_id) {
            activeTaskId = res.task_id;
            addTelemetry('CHAT', `Task ${res.task_id} queued on ${res.tier}`);
            pollChatTaskResult(res.task_id);
        } else {
            showThinking(false);
            chatHistory.push({ role: 'assistant', content: '❌ Failed to queue message. ' + (res?.reason || ''), error: true });
            renderChat();
            saveCurrentConversation();
        }
    });

    // Auto-resize textarea
    $('#chatInput').addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });
    $('#chatInput').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            $('#chatForm').dispatchEvent(new Event('submit'));
        }
    });

    // Temperature slider
    const tempSlider = $('#inferTemp');
    if (tempSlider) {
        tempSlider.addEventListener('input', (e) => {
            $('#tempValue').textContent = (e.target.value / 10).toFixed(1);
        });
    }
}

function startNewConversation() {
    activeConversationId = null;
    chatHistory = [];
    currentMode = 'agent';
    $$('.mode-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === 'agent'));
    renderChat();
    renderConversationList();
    $('#chatInput').focus();
    addTelemetry('CHAT', 'New conversation started');
}

function renderChat() {
    const container = $('#chatMessages');
    if (chatHistory.length === 0) {
        container.innerHTML = `
            <div class="chat-welcome">
                <div class="chat-welcome-icon">🤖</div>
                <div class="chat-welcome-text">SimplePod Swarm is ready.</div>
                <div class="chat-welcome-sub">Select a mode above and start chatting. Conversations are saved automatically.</div>
            </div>
        `;
        return;
    }

    container.innerHTML = chatHistory.map((msg, i) => {
        if (msg.role === 'user') {
            return `
            <div class="chat-msg user">
                <div class="chat-msg-bubble">${escapeHtml(msg.content)}</div>
            </div>
            `;
        } else {
            const agentBadge = msg.agent ? `<span class="chat-msg-agent" data-agent-id="${msg.agent}">${msg.agent}</span>` : '';
            return `
            <div class="chat-msg assistant">
                <div class="chat-msg-bubble">${escapeHtml(msg.content)}</div>
                <div class="chat-msg-meta">
                    <span>🤖 Assistant</span>
                    ${agentBadge}
                    ${msg.model ? `<span>· ${msg.model}</span>` : ''}
                </div>
            </div>
            `;
        }
    }).join('');

    // Make agent badges clickable
    $$('.chat-msg-agent').forEach(badge => {
        badge.addEventListener('click', (e) => {
            e.stopPropagation();
            openAgentDetail(badge.dataset.agentId);
        });
    });

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function showThinking(show) {
    $('#chatThinking').style.display = show ? 'flex' : 'none';
    if (show) {
        const container = $('#chatMessages');
        container.scrollTop = container.scrollHeight;
    }
}

async function pollChatTaskResult(taskId, attempts = 0) {
    if (attempts > TASK_POLL_MAX_ATTEMPTS) {
        showThinking(false);
        activeTaskId = null;
        chatHistory.push({ role: 'assistant', content: '❌ Response timed out. The agent may have gotten stuck.', error: true });
        renderChat();
        saveCurrentConversation();
        return;
    }

    const task = await apiGet(`/swarm/tasks/${taskId}`);
    if (!task) {
        setTimeout(() => pollChatTaskResult(taskId, attempts + 1), TASK_POLL_INTERVAL);
        return;
    }

    if (task.status === 'completed') {
        showThinking(false);
        activeTaskId = null;
        const response = task.result?.response || '';
        const model = task.result?.model || '';
        chatHistory.push({
            role: 'assistant',
            content: response,
            agent: task.assigned_agent,
            model: model,
        });
        renderChat();
        saveCurrentConversation();
        addTelemetry('CHAT', `Response from ${task.assigned_agent} (${model})`);
    } else if (task.status === 'failed') {
        showThinking(false);
        activeTaskId = null;
        let errorMsg = task.error || 'Unknown error';
        // Make Ollama out-of-memory errors user-friendly
        if (errorMsg.includes('too large') || errorMsg.includes('system memory') || errorMsg.includes('out of memory')) {
            errorMsg = '🚫 ' + errorMsg + '\n\n💡 Try switching to a smaller model like **llama3.2** or **dolphin-llama3** in the dropdown above.';
        } else if (errorMsg.includes('Ollama error')) {
            errorMsg = '🤖 Ollama Error: ' + errorMsg;
        }
        chatHistory.push({
            role: 'assistant',
            content: '❌ ' + errorMsg,
            error: true,
        });
        renderChat();
        saveCurrentConversation();
        addTelemetry('CHAT', `Task ${taskId} failed`);
    } else {
        $('#thinkingText').textContent = `${task.status}... (${attempts + 1})`;
        setTimeout(() => pollChatTaskResult(taskId, attempts + 1), TASK_POLL_INTERVAL);
    }
}

// ─── Renderers ───────────────────────────────────────────────────────────────
function renderMetrics(status) {
    if (!status) return;
    $('#metricTotal').textContent = fmtNum(status.agents_total);
    $('#metricActive').textContent = fmtNum(status.agents_active);
    $('#metricIdle').textContent = fmtNum(status.agents_idle);
    $('#metricPending').textContent = fmtNum(status.pending_tasks);
    $('#metricCompleted').textContent = fmtNum(status.completed_tasks);
}

function renderRouting(config) {
    if (!config) return;
    const slider = $('#breakerSlider');
    const valDisplay = $('#breakerValue');
    const modeDisplay = $('#modeDisplay');

    if (document.activeElement !== slider) {
        slider.value = Math.round(config.threshold * 100);
    }
    valDisplay.textContent = config.threshold.toFixed(2);

    $('#btnLocal').classList.toggle('active', config.mode === 'force_local');
    $('#btnAuto').classList.toggle('active', config.mode === 'auto');
    $('#btnCloud').classList.toggle('active', config.mode === 'force_cloud');

    const modeLabels = { force_local: '☀️ FORCE LOCAL', auto: '⚖️ AUTO', force_cloud: '☁️ FORCE CLOUD' };
    modeDisplay.textContent = modeLabels[config.mode] || config.mode.toUpperCase();

    const tierContainer = $('#tierGrid');
    const healthy = config.healthy_tiers || [];
    const tripped = config.tripped_tiers || [];
    const all = [...new Set([...healthy, ...tripped])];

    if (all.length === 0) {
        tierContainer.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;">No tiers configured</div>';
        return;
    }

    const tierColorMap = {
        'local': { cls: 'local', color: 'var(--accent-green)' },
        'shadow': { cls: 'shadow', color: 'var(--accent-yellow)' },
    };

    tierContainer.innerHTML = all.map(name => {
        const isHealthy = healthy.includes(name);
        const display = name === 'local' ? 'Local' : name === 'shadow' ? 'Shadow PC' : name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        const cls = tierColorMap[name]?.cls || 'cloud';
        return `
        <div class="tier-box ${cls}">
            <div class="tier-name">${display}</div>
            <div class="tier-status">${isHealthy ? '🟢 Healthy' : '🔴 Offline'}</div>
        </div>
        `;
    }).join('');
}

function renderAgents(agents) {
    if (!agents) return;
    const container = $('#agentList');
    const statusMap = {
        running: { cls: 'running', icon: '🟢' },
        idle: { cls: 'idle', icon: '🔵' },
        degraded: { cls: 'degraded', icon: '🟡' },
        dead: { cls: 'dead', icon: '🔴' },
    };
    container.innerHTML = agents.map(a => {
        const s = statusMap[a.status] || statusMap.idle;
        const isDead = a.status === 'dead' || !a.alive;
        const configBadge = (a.config && (a.config.model || a.config.temperature !== undefined)) ? '<span class="agent-config-badge" title="Custom config">⚙️</span>' : '';
        return `
        <div class="agent-card" data-agent-id="${a.agent_id || a.id || 'Unknown'}" style="${isDead ? 'opacity:0.5;' : ''}" title="Click to configure">
            <div class="agent-status ${s.cls}"></div>
            <div class="agent-info">
                <div class="agent-id">${a.agent_id || a.id || 'Unknown'}${configBadge}</div>
                <div class="agent-meta">Node: ${a.node_id || '—'} | Uptime: ${fmtNum(a.uptime || a.uptime_seconds)}s</div>
            </div>
            <div class="agent-stats">${a.tasks_completed || 0} ✅ / ${a.tasks_failed || 0} ❌</div>
        </div>
        `;
    }).join('');

    $$('.agent-card').forEach(card => {
        card.addEventListener('click', () => {
            const agentId = card.dataset.agentId;
            if (agentId) openAgentDetail(agentId);
        });
    });
}

function renderNodes(nodes) {
    if (!nodes) return;
    const container = $('#nodeList');
    if (nodes.length === 0) {
        container.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:1rem;">No nodes discovered yet. Trigger a scan in Settings → Discovery.</div>';
        return;
    }
    container.innerHTML = nodes.map(n => {
        const gpuPct = n.gpu_utilization || 0;
        const gpuColor = gpuPct < 50 ? 'var(--accent-green)' : gpuPct < 80 ? 'var(--accent-yellow)' : 'var(--accent-red)';
        const vramUsed = n.vram_used_mb || 0;
        const vramTotal = n.vram_total_mb || 0;
        const vramPct = vramTotal ? (vramUsed / vramTotal * 100) : 0;

        return `
        <div class="node-card">
            <div class="node-header">
                <div class="node-name">${n.node_id}</div>
                <div class="node-health ${n.status}">${n.status.toUpperCase()}</div>
            </div>
            <div class="node-details">
                <span>Latency: ${fmtNum(n.latency_ms)}ms</span>
                <span>Last seen: ${timeAgo(n.last_seen)}</span>
                ${n.provider ? `<span>Provider: ${n.provider}</span>` : ''}
            </div>
            ${n.models && n.models.length ? `
            <div style="margin-top:0.5rem;font-size:0.7rem;color:var(--text-secondary);">
                Models: ${n.models.slice(0, 3).join(', ')}${n.models.length > 3 ? ' +' + (n.models.length - 3) + ' more' : ''}
            </div>` : ''}
            ${cfg('ui_show_gpu_bars', true) && n.gpu_utilization !== undefined ? `
            <div class="gpu-bar-wrap">
                <div class="gpu-bar-track">
                    <div class="gpu-bar-fill" style="width:${gpuPct}%; background:${gpuColor}"></div>
                </div>
                <div class="gpu-bar-labels">
                    <span>GPU: ${gpuPct.toFixed(0)}%</span>
                    <span>VRAM: ${vramUsed} / ${vramTotal} MB (${vramPct.toFixed(0)}%)</span>
                </div>
            </div>
            ` : ''}
        </div>
        `;
    }).join('');
}

// ─── Telemetry ───────────────────────────────────────────────────────────────
const telemetryEntries = [];
function addTelemetry(type, msg) {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    telemetryEntries.unshift({ time: timeStr, type, msg });
    if (telemetryEntries.length > TELEMETRY_MAX_ENTRIES) telemetryEntries.pop();
    renderTelemetry();
}

function renderTelemetry() {
    const container = $('#telemetryLog');
    container.innerHTML = telemetryEntries.map(e => `
        <div class="log-entry">
            <span class="log-time">${e.time}</span>
            <span class="log-type">${e.type}</span>
            <span class="log-msg">${e.msg}</span>
        </div>
    `).join('');
}

// ─── Polling Loop ────────────────────────────────────────────────────────────
async function pollAll() {
    if (!cfg('ui_auto_refresh', true)) return;

    const [status, routing, nodes, agents, activeTasks] = await Promise.all([
        apiGet('/swarm/status'),
        apiGet('/routing/config'),
        apiGet('/nodes/'),
        apiGet('/swarm/agents'),
        apiGet('/swarm/tasks/active'),
    ]);

    if (status) {
        renderMetrics(status);
        lastSwarmStatus = status;
        const chatStatus = $('#chatStatus');
        if (chatStatus) {
            const working = activeTasks && activeTasks.length ? ` · ${activeTasks.length} working` : '';
            chatStatus.textContent = `${status.agents_total} agents · ${status.agents_idle} idle · ${status.pending_tasks} pending${working}`;
        }
    }
    if (routing) {
        renderRouting(routing);
        lastRoutingConfig = routing;
    }
    if (nodes) {
        renderNodes(nodes);
        lastNodes = nodes;
    }
    if (agents) {
        renderAgents(agents);
        lastAgents = agents;
    }
    if (activeTasks !== undefined) {
        renderActiveTasks(activeTasks);
    }

    if (status && lastSwarmStatus) {
        if (status.pending_tasks > (lastSwarmStatus.pending_tasks || 0)) {
            addTelemetry('QUEUE', `+${status.pending_tasks - lastSwarmStatus.pending_tasks} tasks queued`);
        }
    }

    if (selectedAgentId) {
        loadAgentDetail(selectedAgentId);
    }
}

function renderActiveTasks(tasks) {
    // Update thinking indicator if we have an active chat task
    if (activeTaskId && tasks && tasks.length) {
        const myTask = tasks.find(t => t.task_id === activeTaskId);
        if (myTask) {
            $('#thinkingText').textContent = `${myTask.agent_id} working · ${myTask.model || 'default model'}`;
        }
    }
}

// ─── Event Handlers ──────────────────────────────────────────────────────────
function initControls() {
    const slider = $('#breakerSlider');
    slider.addEventListener('input', (e) => {
        $('#breakerValue').textContent = (e.target.value / 100).toFixed(2);
    });
    slider.addEventListener('change', async (e) => {
        const val = parseInt(e.target.value) / 100;
        const res = await apiPost('/routing/threshold', { threshold: val });
        if (res) addTelemetry('BREAKER', `Threshold set to ${val}`);
    });

    $('#btnLocal').addEventListener('click', async () => {
        const res = await apiPost('/routing/force-local');
        if (res) { addTelemetry('BREAKER', 'Forced LOCAL'); pollAll(); }
    });
    $('#btnAuto').addEventListener('click', async () => {
        const res = await apiPost('/routing/auto');
        if (res) { addTelemetry('BREAKER', 'Set to AUTO'); pollAll(); }
    });
    $('#btnCloud').addEventListener('click', async () => {
        const res = await apiPost('/routing/force-cloud');
        if (res) { addTelemetry('BREAKER', 'Forced CLOUD'); pollAll(); }
    });

    $('#btnActivate').addEventListener('click', async () => {
        const res = await apiPost('/swarm/activate');
        if (res) { addTelemetry('SWARM', 'Activated'); pollAll(); }
    });
    $('#btnShutdown').addEventListener('click', async () => {
        const res = await apiPost('/swarm/shutdown');
        if (res) { addTelemetry('SWARM', 'Shutdown initiated'); pollAll(); }
    });

    $('#btnSpawn').addEventListener('click', async () => {
        const btn = $('#btnSpawn');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Spawning...';
        btn.disabled = true;
        const count = parseInt($('#spawnCount').value) || 1;
        const modelOverride = $('#agentDetailModel')?.value || null;
        const config = modelOverride ? { model: modelOverride } : null;
        const res = await apiPost('/swarm/agents/spawn', { count, config });
        btn.textContent = originalText;
        btn.disabled = false;
        if (res && res.success) {
            addTelemetry('SWARM', `Spawned ${res.spawned.length} agent(s)`);
            pollAll();
        } else {
            showError(res?.message || 'Spawn failed');
        }
    });
}

// ─── Model loader ────────────────────────────────────────────────────────────
async function loadModels() {
    const models = await apiGet('/swarm/models');
    console.log('[models] Loaded', models);

    const select = $('#inferModel');
    if (!select) return;

    if (!models || !models.length) {
        select.innerHTML = '<option value="llama3.2">llama3.2</option>';
        return;
    }

    const current = select.value;
    select.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
    if (current && models.includes(current)) {
        select.value = current;
    } else if (models.includes('llama3.2')) {
        select.value = 'llama3.2';
    } else {
        select.value = models[0];
    }

    const settingSelect = $('#settingDefaultModel');
    if (settingSelect) {
        const settingCurrent = settingSelect.value;
        settingSelect.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
        if (settingCurrent && models.includes(settingCurrent)) {
            settingSelect.value = settingCurrent;
        }
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ─── Boot ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    initControls();
    initSettingsUI();
    initAgentDetailUI();
    initChatUI();
    await loadSettings();
    pollAll();
    loadModels();
    pollTimer = setInterval(pollAll, POLL_INTERVAL);
    addTelemetry('SYSTEM', 'Dashboard connected');
});
