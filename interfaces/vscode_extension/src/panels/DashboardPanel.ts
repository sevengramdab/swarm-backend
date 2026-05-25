import * as vscode from 'vscode';
import { SwarmClient } from '../api/client';

/**
 * DashboardPanel
 * ==============
 * Embeds the real SimplePod Swarm web UI (http://localhost:8000)
 * directly inside VS Code via an iframe.  This guarantees the
 * dashboard looks *exactly* like the browser version because it
 * IS the browser version — just hosted in a webview.
 *
 * A minimal toolbar sits above the iframe for refresh / capture
 * so you don't lose VS Code-native shortcuts.
 */
export class DashboardPanel {
    public static currentPanel: DashboardPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private readonly _disposables: vscode.Disposable[] = [];
    private _client: SwarmClient;

    public static createOrShow(extensionUri: vscode.Uri, client: SwarmClient): void {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (DashboardPanel.currentPanel) {
            DashboardPanel.currentPanel._panel.reveal(column);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'simplepod.dashboard',
            'SimplePod Swarm Dashboard',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                // Allow the webview to load external resources (our iframe)
            }
        );

        DashboardPanel.currentPanel = new DashboardPanel(panel, extensionUri, client);
    }

    /**
     * Trigger a screen capture from outside the webview.
     * The iframe content can't be screenshotted directly by the parent,
     * so we open the URL in a browser for capture instead.
     */
    public requestCapture(): void {
        const url = this._client['baseUrl'] || 'http://localhost:8000';
        this._panel.webview.postMessage({ command: 'triggerCapture', url });
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, client: SwarmClient) {
        this._panel = panel;
        this._client = client;
        this._update(extensionUri);

        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        this._panel.webview.onDidReceiveMessage(
            async (message: any) => {
                switch (message.command) {
                    case 'refresh':
                        this._update(extensionUri);
                        return;
                    case 'openExternal':
                        vscode.env.openExternal(vscode.Uri.parse(message.url));
                        return;
                }
            },
            null,
            this._disposables
        );
    }

    private _update(_extensionUri: vscode.Uri): void {
        this._panel.webview.html = this._getHtmlForWebview(this._panel.webview);
    }

    /**
     * The webview is just a thin chrome around an iframe.
     * The iframe loads the actual FastAPI / static UI so everything
     * (styling, JS, WebSockets, etc.) works exactly like in Chrome.
     */
    private _getHtmlForWebview(webview: vscode.Webview): string {
        const apiBase = this._client['baseUrl'] || 'http://localhost:8000';
        const csp = [
            "default-src 'none'",
            "script-src 'unsafe-inline'",
            "style-src 'unsafe-inline'",
            `frame-src ${apiBase} http://localhost:* http://127.0.0.1:*`,
            "img-src 'self' data: blob: *",
        ].join('; ');

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="${csp}">
    <title>SimplePod Swarm Dashboard</title>
    <style>
        html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; background: #0b0d12; }
        .toolbar {
            display: flex; align-items: center; gap: 8px;
            height: 36px; padding: 0 12px;
            background: #13161f; border-bottom: 1px solid #252a3a;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 12px; color: #94a3b8; user-select: none;
        }
        .toolbar .spacer { flex: 1; }
        .toolbar .btn {
            background: #1a1e2a; border: 1px solid #252a3a; border-radius: 4px;
            color: #e2e8f0; padding: 4px 10px; font-size: 11px; cursor: pointer;
        }
        .toolbar .btn:hover { background: #252d3d; }
        .toolbar .url { font-family: 'SF Mono', Consolas, monospace; color: #22c55e; }
        iframe {
            width: 100%; height: calc(100% - 36px); border: none; display: block;
        }
        .offline {
            display: none; position: absolute; inset: 36px 0 0 0;
            background: #0b0d12; color: #ef4444; place-items: center;
            text-align: center; font-family: sans-serif;
        }
        .offline.visible { display: grid; }
    </style>
</head>
<body>
    <div class="toolbar">
        <span>⚡ SimplePod Swarm</span>
        <span class="url">● ${apiBase}</span>
        <span class="spacer"></span>
        <button class="btn" id="btnRefresh" title="Reload iframe">🔄 Refresh</button>
        <button class="btn" id="btnExternal" title="Open in system browser">↗️ Open Browser</button>
    </div>

    <iframe id="appFrame" src="${apiBase}" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"></iframe>

    <div id="offline" class="offline">
        <div>
            <div style="font-size:2rem;margin-bottom:8px;">🔌</div>
            <div style="font-weight:700;font-size:1.1rem;">Backend unreachable</div>
            <div style="color:#94a3b8;margin-top:4px;">Could not connect to ${apiBase}</div>
            <button class="btn" style="margin-top:12px;" id="btnRetry">Retry</button>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const frame = document.getElementById('appFrame');
        const offline = document.getElementById('offline');
        const API_BASE = '${apiBase}';

        document.getElementById('btnRefresh').addEventListener('click', () => {
            frame.src = API_BASE;
        });

        document.getElementById('btnExternal').addEventListener('click', () => {
            vscode.postMessage({ command: 'openExternal', url: API_BASE });
        });

        document.getElementById('btnRetry').addEventListener('click', () => {
            frame.src = API_BASE;
            offline.classList.remove('visible');
        });

        // Simple connectivity probe — if the backend is down we show a friendly overlay
        async function probe() {
            try {
                const r = await fetch(API_BASE + '/health', { method: 'GET', cache: 'no-store' });
                if (r.ok) { offline.classList.remove('visible'); }
                else { offline.classList.add('visible'); }
            } catch (e) {
                offline.classList.add('visible');
            }
        }
        probe();
        setInterval(probe, 5000);

        // Listen for capture shortcut from extension host
        window.addEventListener('message', event => {
            if (event.data.command === 'triggerCapture') {
                vscode.postMessage({ command: 'openExternal', url: event.data.url });
            }
        });
    </script>
</body>
</html>`;
    }

    public dispose(): void {
        DashboardPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) { x.dispose(); }
        }
    }
}
