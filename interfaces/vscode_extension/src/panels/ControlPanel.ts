import * as vscode from 'vscode';
import { SwarmClient } from '../api/client';

export class ControlPanel {
    public static currentPanel: ControlPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private readonly _disposables: vscode.Disposable[] = [];
    private _client: SwarmClient;
    private _pollTimer: NodeJS.Timeout | null = null;

    public static createOrShow(extensionUri: vscode.Uri, client: SwarmClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (ControlPanel.currentPanel) {
            ControlPanel.currentPanel._panel.reveal(column);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'simplepod.control',
            '🎛️ SimplePod Control',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        ControlPanel.currentPanel = new ControlPanel(panel, extensionUri, client);
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, client: SwarmClient) {
        this._panel = panel;
        this._client = client;
        this._update(extensionUri);

        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        this._panel.webview.onDidReceiveMessage(
            async (message: any) => {
                switch (message.command) {
                    case 'sendPrompt':
                        await this._handleSendPrompt(message.text, message.model, message.temp, message.mode);
                        return;
                    case 'activateSwarm':
                        await this._handleActivate();
                        return;
                    case 'shutdownSwarm':
                        await this._handleShutdown();
                        return;
                    case 'spawnAgents':
                        await this._handleSpawn(message.count);
                        return;
                    case 'killAgent':
                        await this._handleKill(message.agentId);
                        return;
                    case 'removeAgent':
                        await this._handleRemove(message.agentId);
                        return;
                    case 'setAgentConfig':
                        await this._handleSetConfig(message.agentId, message.config);
                        return;
                    case 'refresh':
                        await this._pushState();
                        return;
                    case 'getModels':
                        await this._pushModels();
                        return;
                    case 'openExternal':
                        vscode.env.openExternal(vscode.Uri.parse(message.url));
                        return;
                }
            },
            null,
            this._disposables
        );

        this._startPolling();
    }

    private async _handleSendPrompt(text: string, model: string, temp: number, mode: string) {
        this._panel.webview.postMessage({ command: 'thinking', show: true });
        const res = await this._client.infer(text, model, temp, mode);
        if (res && res.task_id) {
            this._panel.webview.postMessage({ command: 'taskQueued', taskId: res.task_id, model: res.model });
            // Poll for result
            let attempts = 0;
            const poll = setInterval(async () => {
                attempts++;
                if (attempts > 60) {
                    clearInterval(poll);
                    this._panel.webview.postMessage({ command: 'taskResult', error: 'Timed out waiting for response' });
                    this._panel.webview.postMessage({ command: 'thinking', show: false });
                    return;
                }
                const task = await this._client.getTask(res.task_id);
                if (task) {
                    if (task.status === 'completed') {
                        clearInterval(poll);
                        const responseText = task.result?.response || '';
                        this._panel.webview.postMessage({
                            command: 'taskResult',
                            text: responseText,
                            model: task.result?.model || res.model,
                            agent: task.assigned_agent,
                        });
                        this._panel.webview.postMessage({ command: 'thinking', show: false });
                    } else if (task.status === 'failed') {
                        clearInterval(poll);
                        const err = task.result?.error || task.error || 'Unknown error';
                        this._panel.webview.postMessage({ command: 'taskResult', error: err });
                        this._panel.webview.postMessage({ command: 'thinking', show: false });
                    }
                }
            }, 2000);
        } else {
            this._panel.webview.postMessage({ command: 'taskResult', error: 'Failed to queue task' });
            this._panel.webview.postMessage({ command: 'thinking', show: false });
        }
    }

    private async _handleActivate() {
        const res = await this._client.activateSwarm();
        vscode.window.showInformationMessage(res ? '✅ Swarm activated' : '❌ Failed to activate');
        await this._pushState();
    }

    private async _handleShutdown() {
        const res = await this._client.shutdownSwarm();
        vscode.window.showInformationMessage(res ? '🛑 Swarm shutdown' : '❌ Failed to shutdown');
        await this._pushState();
    }

    private async _handleSpawn(count: number) {
        const res = await this._client.spawnAgents(count);
        vscode.window.showInformationMessage(res?.success ? `✅ Spawned ${res.spawned?.length || 0} agent(s)` : '❌ Spawn failed');
        await this._pushState();
    }

    private async _handleKill(agentId: string) {
        const res = await this._client.killAgent(agentId);
        vscode.window.showInformationMessage(res ? `💀 ${agentId} killed` : '❌ Kill failed');
        await this._pushState();
    }

    private async _handleRemove(agentId: string) {
        const res = await this._client.removeAgent(agentId);
        vscode.window.showInformationMessage(res ? `🗑️ ${agentId} removed` : '❌ Remove failed');
        await this._pushState();
    }

    private async _handleSetConfig(agentId: string, config: Record<string, unknown>) {
        const res = await this._client.setAgentConfig(agentId, config);
        vscode.window.showInformationMessage(res ? `⚙️ ${agentId} config updated` : '❌ Config update failed');
    }

    private async _pushState() {
        const [status, agents, nodes, models, config] = await Promise.all([
            this._client.getStatus(),
            this._client.getAgents(),
            this._client.getNodes(),
            this._client.getModels(),
            this._client.getRoutingConfig(),
        ]);
        this._panel.webview.postMessage({
            command: 'stateUpdate',
            status,
            agents,
            nodes,
            models,
            routing: config,
        });
    }

    private async _pushModels() {
        const models = await this._client.getModels();
        this._panel.webview.postMessage({ command: 'modelsUpdate', models });
    }

    private _startPolling() {
        this._pushState();
        this._pollTimer = setInterval(() => this._pushState(), 3000);
    }

    private _update(_extensionUri: vscode.Uri): void {
        this._panel.webview.html = this._getHtml();
    }

    private _getHtml(): string {
        const csp = [
            "default-src 'none'",
            "script-src 'unsafe-inline'",
            "style-src 'unsafe-inline'",
            "img-src 'self' data: blob: *",
        ].join('; ');

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="${csp}">
    <title>SimplePod Control</title>
    <style>
        :root {
            --bg: #0b0d12;
            --bg-card: #13161f;
            --bg-hover: #1a1e2a;
            --border: #252a3a;
            --text: #e2e8f0;
            --text-dim: #94a3b8;
            --green: #22c55e;
            --red: #ef4444;
            --blue: #3b82f6;
            --yellow: #eab308;
            --radius: 6px;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            font-size: 13px;
            line-height: 1.5;
            padding: 12px;
            min-height: 100vh;
        }
        .grid { display: grid; gap: 12px; }
        .grid-2 { grid-template-columns: 1fr 1fr; }
        .grid-3 { grid-template-columns: repeat(3, 1fr); }
        @media (max-width: 500px) { .grid-2, .grid-3 { grid-template-columns: 1fr; } }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px;
        }
        .card-title {
            font-weight: 600;
            font-size: 12px;
            color: var(--text-dim);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .metric-row { display: flex; gap: 8px; flex-wrap: wrap; }
        .metric {
            background: var(--bg-hover);
            border-radius: var(--radius);
            padding: 8px 12px;
            min-width: 80px;
            text-align: center;
        }
        .metric-value { font-size: 18px; font-weight: 700; }
        .metric-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }

        .btn {
            background: var(--bg-hover);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 12px;
            border-radius: var(--radius);
            cursor: pointer;
            font-size: 12px;
            transition: all 0.15s;
        }
        .btn:hover { background: var(--border); }
        .btn-green { border-color: var(--green); color: var(--green); }
        .btn-green:hover { background: rgba(34,197,94,0.15); }
        .btn-red { border-color: var(--red); color: var(--red); }
        .btn-red:hover { background: rgba(239,68,68,0.15); }
        .btn-blue { border-color: var(--blue); color: var(--blue); }
        .btn-blue:hover { background: rgba(59,130,246,0.15); }
        .btn-sm { padding: 4px 8px; font-size: 11px; }

        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .spacer { flex: 1; }

        .chat-area {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .chat-input {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 8px;
            border-radius: var(--radius);
            font-family: inherit;
            font-size: 13px;
            resize: vertical;
            min-height: 60px;
            max-height: 200px;
        }
        .chat-input:focus { outline: none; border-color: var(--blue); }
        .response-box {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 10px;
            min-height: 80px;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .response-box.empty { color: var(--text-dim); font-style: italic; }
        .response-box.error { border-color: var(--red); color: var(--red); }

        .thinking {
            display: none;
            align-items: center;
            gap: 6px;
            color: var(--text-dim);
            font-size: 12px;
        }
        .thinking.visible { display: flex; }
        .dot {
            width: 6px; height: 6px;
            background: var(--blue);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }

        .agent-list { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
        .agent-item {
            display: flex; align-items: center; gap: 8px;
            padding: 6px 8px;
            background: var(--bg-hover);
            border-radius: var(--radius);
            cursor: pointer;
        }
        .agent-item:hover { background: var(--border); }
        .agent-status {
            width: 8px; height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .agent-status.idle { background: var(--blue); }
        .agent-status.running { background: var(--green); }
        .agent-status.dead { background: var(--red); }
        .agent-name { font-weight: 500; flex: 1; }
        .agent-meta { font-size: 10px; color: var(--text-dim); }

        select, input[type="number"] {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 4px 8px;
            border-radius: var(--radius);
            font-size: 12px;
        }
        select:focus, input:focus { outline: none; border-color: var(--blue); }

        .mode-tabs {
            display: flex; gap: 4px; flex-wrap: wrap;
        }
        .mode-tab {
            padding: 4px 10px;
            border-radius: var(--radius);
            border: 1px solid var(--border);
            background: var(--bg-hover);
            color: var(--text-dim);
            cursor: pointer;
            font-size: 11px;
        }
        .mode-tab.active {
            background: var(--blue);
            color: white;
            border-color: var(--blue);
        }

        .scroll { max-height: 180px; overflow-y: auto; }
        .node-item {
            padding: 6px;
            background: var(--bg-hover);
            border-radius: var(--radius);
            margin-bottom: 4px;
            font-size: 11px;
        }
        .node-name { font-weight: 500; }
        .node-meta { color: var(--text-dim); }

        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
    </style>
</head>
<body>
    <div class="grid">
        <!-- Quick Actions -->
        <div class="card">
            <div class="card-title">🎛️ Quick Actions</div>
            <div class="row">
                <button class="btn btn-green" id="btnActivate">▶ Activate</button>
                <button class="btn btn-red" id="btnShutdown">⏹ Shutdown</button>
                <span class="spacer"></span>
                <input type="number" id="spawnCount" value="1" min="1" max="50" style="width:50px;">
                <button class="btn btn-blue" id="btnSpawn">➕ Spawn</button>
                <button class="btn btn-sm" id="btnRefresh">🔄 Refresh</button>
            </div>
        </div>

        <!-- Metrics -->
        <div class="card">
            <div class="card-title">📊 Swarm Status</div>
            <div class="metric-row" id="metricsRow">
                <div class="metric"><div class="metric-value" id="mTotal">-</div><div class="metric-label">Agents</div></div>
                <div class="metric"><div class="metric-value" id="mActive">-</div><div class="metric-label">Active</div></div>
                <div class="metric"><div class="metric-value" id="mIdle">-</div><div class="metric-label">Idle</div></div>
                <div class="metric"><div class="metric-value" id="mPending">-</div><div class="metric-label">Pending</div></div>
            </div>
        </div>

        <!-- Chat -->
        <div class="card">
            <div class="card-title">💬 AI Control</div>
            <div class="chat-area">
                <div class="mode-tabs" id="modeTabs">
                    <div class="mode-tab active" data-mode="agent">🤖 Agent</div>
                    <div class="mode-tab" data-mode="plan">📋 Plan</div>
                    <div class="mode-tab" data-mode="research">🔬 Research</div>
                    <div class="mode-tab" data-mode="swarm_code">💻 Code</div>
                    <div class="mode-tab" data-mode="debug">🐛 Debug</div>
                    <div class="mode-tab" data-mode="auto">✨ Auto</div>
                </div>
                <div class="row">
                    <select id="modelSelect"><option>Loading models...</option></select>
                    <label style="font-size:11px;color:var(--text-dim);">Temp: <span id="tempVal">0.7</span></label>
                    <input type="range" id="tempSlider" min="0" max="20" value="7" style="width:80px;">
                </div>
                <textarea class="chat-input" id="chatInput" placeholder="Type a command or question..."></textarea>
                <div class="row">
                    <div class="thinking" id="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div><span id="thinkingText">Processing...</span></div>
                    <span class="spacer"></span>
                    <button class="btn btn-blue" id="btnSend">➤ Send</button>
                </div>
                <div class="response-box empty" id="responseBox">Response will appear here...</div>
            </div>
        </div>

        <div class="grid grid-2">
            <!-- Agents -->
            <div class="card">
                <div class="card-title">👷 Agents</div>
                <div class="agent-list" id="agentList">
                    <div style="color:var(--text-dim);font-size:12px;">Loading...</div>
                </div>
            </div>
            <!-- Nodes -->
            <div class="card">
                <div class="card-title">🖥️ Nodes</div>
                <div class="scroll" id="nodeList">
                    <div style="color:var(--text-dim);font-size:12px;">Loading...</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        let currentMode = 'agent';
        let selectedAgent = null;

        // Mode tabs
        document.getElementById('modeTabs').addEventListener('click', (e) => {
            if (e.target.classList.contains('mode-tab')) {
                document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                currentMode = e.target.dataset.mode;
            }
        });

        // Temp slider
        const tempSlider = document.getElementById('tempSlider');
        const tempVal = document.getElementById('tempVal');
        tempSlider.addEventListener('input', () => {
            tempVal.textContent = (tempSlider.value / 10).toFixed(1);
        });

        // Send
        document.getElementById('btnSend').addEventListener('click', () => {
            const input = document.getElementById('chatInput');
            const text = input.value.trim();
            if (!text) return;
            const model = document.getElementById('modelSelect').value;
            const temp = parseInt(tempSlider.value) / 10;
            vscode.postMessage({ command: 'sendPrompt', text, model, temp, mode: currentMode });
        });

        // Enter to send
        document.getElementById('chatInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                document.getElementById('btnSend').click();
            }
        });

        // Quick actions
        document.getElementById('btnActivate').addEventListener('click', () => {
            vscode.postMessage({ command: 'activateSwarm' });
        });
        document.getElementById('btnShutdown').addEventListener('click', () => {
            vscode.postMessage({ command: 'shutdownSwarm' });
        });
        document.getElementById('btnSpawn').addEventListener('click', () => {
            const count = parseInt(document.getElementById('spawnCount').value) || 1;
            vscode.postMessage({ command: 'spawnAgents', count });
        });
        document.getElementById('btnRefresh').addEventListener('click', () => {
            vscode.postMessage({ command: 'refresh' });
        });

        // Agent list clicks
        document.getElementById('agentList').addEventListener('click', (e) => {
            const item = e.target.closest('.agent-item');
            if (!item) return;
            const agentId = item.dataset.agentId;
            const alive = item.dataset.alive === 'true';
            selectedAgent = agentId;
            if (alive) {
                vscode.postMessage({ command: 'killAgent', agentId });
            } else {
                vscode.postMessage({ command: 'removeAgent', agentId });
            }
        });

        // Listen from extension host
        window.addEventListener('message', (event) => {
            const msg = event.data;
            switch (msg.command) {
                case 'thinking':
                    document.getElementById('thinking').classList.toggle('visible', msg.show);
                    break;
                case 'taskQueued':
                    document.getElementById('thinkingText').textContent = \`Queued on \${msg.model || 'default'}...\`;
                    break;
                case 'taskResult':
                    const box = document.getElementById('responseBox');
                    box.classList.remove('empty');
                    if (msg.error) {
                        box.classList.add('error');
                        box.textContent = '❌ ' + msg.error;
                    } else {
                        box.classList.remove('error');
                        box.textContent = msg.text;
                        if (msg.model || msg.agent) {
                            const meta = document.createElement('div');
                            meta.style.cssText = 'margin-top:8px;font-size:10px;color:var(--text-dim);border-top:1px solid var(--border);padding-top:4px;';
                            meta.textContent = \`\${msg.agent || 'Unknown'} · \${msg.model || 'default'}\`;
                            box.appendChild(meta);
                        }
                    }
                    break;
                case 'stateUpdate':
                    updateState(msg.status, msg.agents, msg.nodes, msg.models);
                    break;
                case 'modelsUpdate':
                    updateModels(msg.models);
                    break;
            }
        });

        function updateState(status, agents, nodes, models) {
            if (status) {
                document.getElementById('mTotal').textContent = status.agents_total ?? '-';
                document.getElementById('mActive').textContent = status.agents_active ?? '-';
                document.getElementById('mIdle').textContent = status.agents_idle ?? '-';
                document.getElementById('mPending').textContent = status.pending_tasks ?? '-';
            }

            const agentList = document.getElementById('agentList');
            if (agents && agents.length) {
                agentList.innerHTML = agents.map(a => {
                    const statusCls = a.status === 'running' ? 'running' : a.status === 'dead' || !a.alive ? 'dead' : 'idle';
                    const isDead = a.status === 'dead' || !a.alive;
                    return \`<div class="agent-item" data-agent-id="\${a.agent_id || a.id}" data-alive="\${a.alive}">
                        <div class="agent-status \${statusCls}"></div>
                        <span class="agent-name">\${a.agent_id || a.id}</span>
                        <span class="agent-meta">\${a.tasks_completed || 0}✓ \${isDead ? '💀 click to remove' : '⚡ click to kill'}</span>
                    </div>\`;
                }).join('');
            } else {
                agentList.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No agents</div>';
            }

            const nodeList = document.getElementById('nodeList');
            if (nodes && nodes.length) {
                nodeList.innerHTML = nodes.map(n => \`<div class="node-item">
                    <div class="node-name">\${n.node_id} <span style="color:\${n.status==='healthy'?'var(--green)':'var(--red)'}">●</span></div>
                    <div class="node-meta">\${n.models?.slice(0,3).join(', ') || ''} \${n.models?.length > 3 ? '+'+(n.models.length-3) : ''}</div>
                </div>\`).join('');
            } else {
                nodeList.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No nodes</div>';
            }

            updateModels(models);
        }

        function updateModels(models) {
            const select = document.getElementById('modelSelect');
            if (!models || !models.length) return;
            const current = select.value;
            const html = models.map(m => \`<option value="\${m}">\${m}</option>\`).join('');
            if (select.innerHTML !== html) {
                select.innerHTML = html;
                if (current && models.includes(current)) select.value = current;
                else if (models.includes('llama3.2')) select.value = 'llama3.2';
                else if (models.includes('llama3.2:latest')) select.value = 'llama3.2:latest';
            }
        }

        vscode.postMessage({ command: 'getModels' });
    </script>
</body>
</html>`;
    }

    public dispose(): void {
        if (this._pollTimer) { clearInterval(this._pollTimer); }
        ControlPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) { x.dispose(); }
        }
    }
}
