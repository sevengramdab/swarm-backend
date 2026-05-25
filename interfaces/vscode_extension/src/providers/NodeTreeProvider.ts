import * as vscode from 'vscode';
import { SwarmClient } from '../api/client';

export class NodeTreeItem extends vscode.TreeItem {
    constructor(
        public readonly nodeId: string,
        public readonly status: string,
        public readonly models: string[],
        public readonly latency: number
    ) {
        super(nodeId, vscode.TreeItemCollapsibleState.None);
        const modelList = models?.slice(0, 2).join(', ') || 'none';
        const extra = models?.length > 2 ? ` +${models.length - 2}` : '';
        this.description = `${status} · ${latency}ms · ${modelList}${extra}`;
        this.tooltip = `${nodeId}\nStatus: ${status}\nLatency: ${latency}ms\nModels: ${models?.join(', ') || 'none'}`;
        this.iconPath = new vscode.ThemeColor(status === 'healthy' ? 'charts.green' : 'charts.red');
        this.contextValue = 'node';
    }
}

export class NodeTreeProvider implements vscode.TreeDataProvider<NodeTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<NodeTreeItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private _client?: SwarmClient;
    private _timer?: NodeJS.Timeout;

    setClient(client: SwarmClient) {
        this._client = client;
        this.refresh();
    }

    startPolling(intervalMs: number = 5000) {
        if (this._timer) { clearInterval(this._timer); }
        this._timer = setInterval(() => this.refresh(), intervalMs);
    }

    stopPolling() {
        if (this._timer) { clearInterval(this._timer); }
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: NodeTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<NodeTreeItem[]> {
        if (!this._client) {
            return [new NodeTreeItem('Not connected', 'offline', [], 0)];
        }
        const nodes = await this._client.getNodes();
        if (!nodes || !nodes.length) {
            return [new NodeTreeItem('No nodes', 'offline', [], 0)];
        }
        return nodes.map(n => new NodeTreeItem(
            n.node_id,
            n.status,
            n.models || [],
            n.latency_ms || 0
        ));
    }
}
