import * as vscode from 'vscode';
import { DashboardPanel } from './panels/DashboardPanel';
import { AgentTreeProvider } from './providers/AgentTreeProvider';
import { NodeTreeProvider } from './providers/NodeTreeProvider';
import { TransferTreeProvider } from './providers/TransferTreeProvider';
import { SwarmClient } from './api/client';

/**
 * Extension state keys — like named layer states in AutoCAD that persist
 * across drawing sessions. We store connection info so Kimi can auto-resume
 * if VS Code's extension host reloads.
 */
const STATE_KEYS = {
    API_URL: 'simplepod.apiUrl',
    DASHBOARD_OPEN: 'simplepod.dashboardOpen',
    LAST_STATUS: 'simplepod.lastStatus',
    AUTO_RESUME: 'simplepod.autoResume',
};

let client: SwarmClient;
let statusBarItem: vscode.StatusBarItem;
let reconnectTimer: NodeJS.Timeout | null = null;

/**
 * ELI5: Like loading a saved workspace in AutoCAD.
 *       All your layers, viewports, and UCS settings come back exactly
 *       as you left them — even if the power went out (VS Code reloaded).
 */
export function activate(context: vscode.ExtensionContext): void {
    // 1. Restore connection settings from globalState (fireproof safe)
    const savedUrl = context.globalState.get<string>(STATE_KEYS.API_URL, 'http://localhost:8000');
    const wasDashboardOpen = context.globalState.get<boolean>(STATE_KEYS.DASHBOARD_OPEN, false);
    const autoResume = context.globalState.get<boolean>(STATE_KEYS.AUTO_RESUME, true);

    client = new SwarmClient(savedUrl);

    // 2. Status bar — the coordinate readout that never disappears
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'simplepod.openDashboard';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // 3. Tree providers — Layer Properties Manager palettes
    vscode.window.registerTreeDataProvider('simplepodAgents', new AgentTreeProvider());
    vscode.window.registerTreeDataProvider('simplepodNodes', new NodeTreeProvider());
    vscode.window.registerTreeDataProvider('simplepodTransfers', new TransferTreeProvider());
    vscode.commands.executeCommand('setContext', 'simplepod:enabled', true);

    // 4. Auto-resume: if the dashboard was open before reload, reopen it
    if (autoResume && wasDashboardOpen) {
        setTimeout(() => {
            DashboardPanel.createOrShow(context.extensionUri, client);
            vscode.window.showInformationMessage('SimplePod Swarm: Auto-resumed dashboard after reload');
        }, 1500); // brief delay so VS Code finishes its own startup
    }

    // 5. Background health polling — like a building automation system
    //     that checks every circuit breaker every 5 seconds
    startHealthPolling(context);

    // 6. Register commands
    registerCommands(context);
}

function registerCommands(context: vscode.ExtensionContext): void {
    // Open Dashboard — creates or reveals the webview layout tab
    const openDashboard = vscode.commands.registerCommand('simplepod.openDashboard', () => {
        DashboardPanel.createOrShow(context.extensionUri, client);
        context.globalState.update(STATE_KEYS.DASHBOARD_OPEN, true);
        vscode.commands.executeCommand('setContext', 'simplepod:dashboardVisible', true);
    });

    // Capture Screen — triggers html2canvas inside the webview
    const captureScreen = vscode.commands.registerCommand('simplepod.captureScreen', async () => {
        if (!DashboardPanel.currentPanel) {
            vscode.window.showWarningMessage('Open the SimplePod dashboard first (Ctrl+Shift+S)');
            return;
        }
        DashboardPanel.currentPanel.requestCapture();
    });

    // Activate Swarm
    const activateSwarm = vscode.commands.registerCommand('simplepod.activateSwarm', async () => {
        const res = await client.activateSwarm();
        if (res) {
            statusBarItem.text = '$(play) SimplePod: Active';
            vscode.window.showInformationMessage('SimplePod Swarm Activated');
        } else {
            vscode.window.showErrorMessage('Failed to activate swarm — backend unreachable');
        }
    });

    // Shutdown Swarm
    const shutdownSwarm = vscode.commands.registerCommand('simplepod.shutdownSwarm', async () => {
        const res = await client.shutdownSwarm();
        if (res) {
            statusBarItem.text = '$(stop) SimplePod: Offline';
            vscode.window.showInformationMessage('SimplePod Swarm Shutdown');
        }
    });

    // Set Main Breaker
    const setBreaker = vscode.commands.registerCommand('simplepod.setMainBreaker', async () => {
        const value = await vscode.window.showInputBox({
            prompt: 'Set Main Breaker Threshold (0.0 - 1.0)',
            placeHolder: '0.5',
            validateInput: (text) => {
                const n = Number(text);
                if (isNaN(n) || n < 0 || n > 1) { return 'Enter a number between 0.0 and 1.0'; }
                return null;
            }
        });
        if (value) {
            const res = await client.setThreshold(parseFloat(value));
            if (res) { vscode.window.showInformationMessage(`Main Breaker set to ${value}`); }
        }
    });

    // Reconnect — manual refresh if auto-resume fails
    const reconnect = vscode.commands.registerCommand('simplepod.reconnect', async () => {
        const newUrl = await vscode.window.showInputBox({
            prompt: 'Backend API URL',
            value: client['baseUrl'] || 'http://localhost:8000',
        });
        if (newUrl) {
            client.setBaseUrl(newUrl);
            await context.globalState.update(STATE_KEYS.API_URL, newUrl);
            vscode.window.showInformationMessage(`Reconnected to ${newUrl}`);
            startHealthPolling(context);
        }
    });

    context.subscriptions.push(openDashboard, captureScreen, activateSwarm, shutdownSwarm, setBreaker, reconnect);
}

/**
 * ELI5: Like a smart panel that checks every circuit every 5 seconds.
 *       If the main breaker trips (backend goes down), the status LED
 *       turns red. When it comes back, it turns green automatically.
 */
function startHealthPolling(context: vscode.ExtensionContext): void {
    if (reconnectTimer) { clearInterval(reconnectTimer); }

    const poll = async () => {
        const health = await client.health();
        if (health && health.status === 'healthy') {
            statusBarItem.text = '$(circuit-board) SimplePod: Online';
            statusBarItem.tooltip = `Backend: ${client['baseUrl']} | All circuits operational`;
            statusBarItem.backgroundColor = undefined;
        } else {
            statusBarItem.text = '$(warning) SimplePod: Disconnected';
            statusBarItem.tooltip = `Backend: ${client['baseUrl']} | Check connection`;
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        }
    };

    poll(); // immediate check
    reconnectTimer = setInterval(poll, 5000);
}

/**
 * ELI5: Like saving your layer state before AutoCAD crashes.
 *       We remember whether the dashboard was open so Kimi can
 *       restore it on the next session without asking.
 */
export async function deactivate(): Promise<void> {
    if (reconnectTimer) { clearInterval(reconnectTimer); }
    // Note: globalState was already updated during commands,
    // so the fireproof safe already has the latest checkpoint.
}
