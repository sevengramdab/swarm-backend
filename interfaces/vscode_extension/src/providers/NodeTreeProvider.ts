import * as vscode from 'vscode';

export class NodeTreeProvider implements vscode.TreeDataProvider<NodeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<NodeItem | undefined | void> = new vscode.EventEmitter<NodeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<NodeItem | undefined | void> = this._onDidChangeTreeData.event;

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: NodeItem): vscode.TreeItem {
        return element;
    }

    getChildren(): Thenable<NodeItem[]> {
        return Promise.resolve([
            new NodeItem('local-msi', 'healthy', 'GTX 1650', '12ms'),
            new NodeItem('shadow-pc', 'healthy', 'RTX 3080', '45ms'),
            new NodeItem('poland-01', 'healthy', 'RTX 5090', '120ms'),
        ]);
    }
}

class NodeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly status: string,
        public readonly gpu: string,
        public readonly latency: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.tooltip = `${label} — ${gpu} — ${latency}`;
        this.description = `${gpu} | ${latency}`;
        const icon = status === 'healthy' ? 'server-environment' : status === 'degraded' ? 'warning' : 'error';
        this.iconPath = new vscode.ThemeIcon(icon);
        this.contextValue = 'node';
    }
}
