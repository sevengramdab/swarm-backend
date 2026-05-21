import * as vscode from 'vscode';

export class AgentTreeProvider implements vscode.TreeDataProvider<AgentItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<AgentItem | undefined | void> = new vscode.EventEmitter<AgentItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<AgentItem | undefined | void> = this._onDidChangeTreeData.event;

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: AgentItem): vscode.TreeItem {
        return element;
    }

    getChildren(): Thenable<AgentItem[]> {
        // In a full implementation, this would fetch from the backend API
        // and refresh every few seconds via setInterval.
        return Promise.resolve([
            new AgentItem('AGENT-001', 'running', 'local-msi', '$(debug-start)'),
            new AgentItem('AGENT-002', 'idle', 'local-msi', '$(debug-pause)'),
            new AgentItem('AGENT-003', 'idle', 'poland-01', '$(debug-pause)'),
        ]);
    }
}

class AgentItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly status: string,
        public readonly node: string,
        public readonly icon: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.tooltip = `${label} on ${node} — ${status}`;
        this.description = `${status} @ ${node}`;
        this.iconPath = new vscode.ThemeIcon(icon.replace('$(', '').replace(')', ''));
        this.contextValue = 'agent';
    }
}
