import * as vscode from 'vscode';
import { SwarmClient } from '../api/client';

export class AgentTreeItem extends vscode.TreeItem {
    constructor(
        public readonly agentId: string,
        public readonly status: string,
        public readonly alive: boolean,
        public readonly tasksCompleted: number,
        public readonly tasksFailed: number,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState = vscode.TreeItemCollapsibleState.None
    ) {
        super(agentId, collapsibleState);
        const isDead = status === 'dead' || !alive;
        const icon = isDead ? '$(debug-disconnect)' : status === 'running' ? '$(play-circle)' : '$(circle-large-filled)';
        this.description = `${tasksCompleted}✓ / ${tasksFailed}✗ · ${isDead ? 'DEAD' : status}`;
        this.tooltip = `${agentId}\nStatus: ${status}\nAlive: ${alive}\nCompleted: ${tasksCompleted}\nFailed: ${tasksFailed}\n\n${isDead ? 'Click to remove from registry' : 'Click to open detail / kill'}`;
        this.iconPath = new vscode.ThemeColor(isDead ? 'charts.red' : status === 'running' ? 'charts.green' : 'charts.blue');
        this.contextValue = isDead ? 'deadAgent' : 'aliveAgent';
    }
}

export class AgentTreeProvider implements vscode.TreeDataProvider<AgentTreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<AgentTreeItem | undefined | void> = new vscode.EventEmitter<AgentTreeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<AgentTreeItem | undefined | void> = this._onDidChangeTreeData.event;
    private _client?: SwarmClient;
    private _timer?: NodeJS.Timeout;

    setClient(client: SwarmClient) {
        this._client = client;
        this.refresh();
    }

    startPolling(intervalMs: number = 3000) {
        if (this._timer) { clearInterval(this._timer); }
        this._timer = setInterval(() => this.refresh(), intervalMs);
    }

    stopPolling() {
        if (this._timer) { clearInterval(this._timer); }
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: AgentTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<AgentTreeItem[]> {
        if (!this._client) {
            return [new AgentTreeItem('Not connected', 'offline', false, 0, 0)];
        }
        const agents = await this._client.getAgents();
        if (!agents || !agents.length) {
            return [new AgentTreeItem('No agents', 'idle', false, 0, 0)];
        }
        return agents.map(a => new AgentTreeItem(
            a.agent_id || 'Unknown',
            a.status || 'idle',
            a.alive !== false,
            a.tasks_completed || 0,
            a.tasks_failed || 0
        ));
    }
}
