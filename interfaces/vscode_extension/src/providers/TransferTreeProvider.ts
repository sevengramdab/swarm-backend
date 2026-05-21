import * as vscode from 'vscode';

export class TransferTreeProvider implements vscode.TreeDataProvider<TransferItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<TransferItem | undefined | void> = new vscode.EventEmitter<TransferItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<TransferItem | undefined | void> = this._onDidChangeTreeData.event;

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: TransferItem): vscode.TreeItem {
        return element;
    }

    getChildren(): Thenable<TransferItem[]> {
        return Promise.resolve([
            new TransferItem('payload-001', 'poland-01', 'completed', '$(check)'),
        ]);
    }
}

class TransferItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly target: string,
        public readonly status: string,
        public readonly icon: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.tooltip = `${label} → ${target}`;
        this.description = `${status} → ${target}`;
        this.iconPath = new vscode.ThemeIcon(icon.replace('$(', '').replace(')', ''));
        this.contextValue = 'transfer';
    }
}
