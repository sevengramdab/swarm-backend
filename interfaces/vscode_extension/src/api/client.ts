import * as vscode from 'vscode';

export interface SwarmStatus {
    running: boolean;
    agents_total: number;
    agents_active: number;
    agents_idle: number;
    pending_tasks: number;
    completed_tasks: number;
    failed_tasks: number;
    uptime_seconds: number;
}

export interface RoutingConfig {
    mode: string;
    threshold: number;
    healthy_tiers: string[];
    tripped_tiers: string[];
}

export interface NodeInfo {
    node_id: string;
    status: string;
    gpu_utilization?: number;
    vram_used_mb?: number;
    vram_total_mb?: number;
    latency_ms: number;
    last_seen: number;
    provider?: string;
    models?: string[];
}

export interface AgentInfo {
    agent_id: string;
    status: string;
    node_id?: string;
    tasks_completed: number;
    tasks_failed: number;
    uptime?: number;
    uptime_seconds?: number;
    alive?: boolean;
    config?: Record<string, unknown>;
}

export interface TaskResult {
    task_id: string;
    status: string;
    result?: {
        response?: string;
        model?: string;
        error?: string;
        status?: string;
    };
    error?: string;
    assigned_agent?: string;
}

export interface SettingsMap {
    [key: string]: unknown;
}

export class SwarmClient {
    private baseUrl: string;

    constructor(baseUrl: string = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    setBaseUrl(url: string) {
        this.baseUrl = url;
    }

    getBaseUrl(): string {
        return this.baseUrl;
    }

    private async request(path: string, options?: RequestInit): Promise<any | null> {
        try {
            const res = await fetch(`${this.baseUrl}${path}`, { cache: 'no-store', ...options } as any);
            if (!res.ok) { return null; }
            return await res.json();
        } catch {
            return null;
        }
    }

    private async get(path: string): Promise<any | null> {
        return this.request(path, { method: 'GET' });
    }

    private async post(path: string, body?: any): Promise<any | null> {
        return this.request(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined,
        });
    }

    private async put(path: string, body?: any): Promise<any | null> {
        return this.request(path, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined,
        });
    }

    private async del(path: string): Promise<any | null> {
        return this.request(path, { method: 'DELETE' });
    }

    async health(): Promise<{ status: string } | null> {
        return this.get('/health');
    }

    async getStatus(): Promise<SwarmStatus | null> {
        return this.get('/swarm/status');
    }

    async getRoutingConfig(): Promise<RoutingConfig | null> {
        return this.get('/routing/config');
    }

    async getNodes(): Promise<NodeInfo[] | null> {
        return this.get('/nodes/');
    }

    async getAgents(): Promise<AgentInfo[] | null> {
        return this.get('/swarm/agents');
    }

    async getAgent(agentId: string): Promise<AgentInfo | null> {
        return this.get(`/swarm/agents/${agentId}`);
    }

    async getAgentConfig(agentId: string): Promise<{ config: Record<string, unknown> } | null> {
        return this.get(`/swarm/agents/${agentId}/config`);
    }

    async setAgentConfig(agentId: string, config: Record<string, unknown>): Promise<any | null> {
        return this.put(`/swarm/agents/${agentId}/config`, { config });
    }

    async killAgent(agentId: string): Promise<any | null> {
        return this.post(`/swarm/agents/${agentId}/kill`);
    }

    async removeAgent(agentId: string): Promise<any | null> {
        return this.del(`/swarm/agents/${agentId}`);
    }

    async spawnAgents(count: number, config?: Record<string, unknown>): Promise<any | null> {
        return this.post('/swarm/agents/spawn', { count, config });
    }

    async getTask(taskId: string): Promise<TaskResult | null> {
        return this.get(`/swarm/tasks/${taskId}`);
    }

    async getActiveTasks(): Promise<any[] | null> {
        return this.get('/swarm/tasks/active');
    }

    async getModels(): Promise<string[] | null> {
        return this.get('/swarm/models');
    }

    async getSettings(): Promise<SettingsMap | null> {
        return this.get('/settings');
    }

    async updateSettings(updates: SettingsMap): Promise<SettingsMap | null> {
        return this.put('/settings', updates);
    }

    async resetSettings(): Promise<SettingsMap | null> {
        return this.post('/settings/reset');
    }

    async setThreshold(value: number): Promise<any | null> {
        return this.post('/routing/threshold', { threshold: value });
    }

    async forceLocal(): Promise<any | null> {
        return this.post('/routing/force-local');
    }

    async forceCloud(): Promise<any | null> {
        return this.post('/routing/force-cloud');
    }

    async autoBalance(): Promise<any | null> {
        return this.post('/routing/auto');
    }

    async infer(prompt: string, model?: string, temperature?: number, mode?: string, messages?: any[]): Promise<any | null> {
        return this.post('/routing/infer', {
            prompt,
            model_hint: model,
            temperature: temperature ?? 0.7,
            mode: mode ?? 'agent',
            messages: messages ?? [],
        });
    }

    async activateSwarm(): Promise<any | null> {
        return this.post('/swarm/activate');
    }

    async shutdownSwarm(): Promise<any | null> {
        return this.post('/swarm/shutdown');
    }

    async remoteType(text: string, interval?: number): Promise<any | null> {
        return this.post('/remote/type', { text, interval: interval ?? 0.01 });
    }

    async remoteClick(x: number, y: number, button?: string, clicks?: number): Promise<any | null> {
        return this.post('/remote/click', { x, y, button: button ?? 'left', clicks: clicks ?? 1 });
    }

    async remoteKeys(keys: string): Promise<any | null> {
        return this.post('/remote/keys', { keys });
    }

    async remoteShell(command: string, cwd?: string, timeout?: number): Promise<any | null> {
        return this.post('/remote/shell', { command, cwd, timeout: timeout ?? 30 });
    }

    async remoteScroll(clicks: number, x?: number, y?: number): Promise<any | null> {
        return this.post('/remote/scroll', { clicks, x, y });
    }

    async remoteDrag(x1: number, y1: number, x2: number, y2: number, duration?: number, button?: string): Promise<any | null> {
        return this.post('/remote/drag', { x1, y1, x2, y2, duration: duration ?? 0.5, button: button ?? 'left' });
    }

    async remoteScreenshot(): Promise<{ success: boolean; image_base64: string; width: number; height: number } | null> {
        return this.get('/remote/screenshot');
    }
}
