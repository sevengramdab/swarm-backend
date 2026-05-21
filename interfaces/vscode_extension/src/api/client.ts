import * as vscode from 'vscode';

/**
 * API Client — like the RS-485 bus master polling every smart breaker panel.
 * Sends requests to the FastAPI backend and returns parsed JSON.
 */
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
}

export interface AgentInfo {
    agent_id: string;
    status: string;
    node_id?: string;
    tasks_completed: number;
    tasks_failed: number;
    uptime?: number;
    uptime_seconds?: number;
}

export class SwarmClient {
    private baseUrl: string;

    constructor(baseUrl: string = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    setBaseUrl(url: string) {
        this.baseUrl = url;
    }

    private async fetchJson(path: string): Promise<any | null> {
        try {
            const res = await fetch(`${this.baseUrl}${path}`, { cache: 'no-store' });
            if (!res.ok) { return null; }
            return await res.json();
        } catch {
            return null;
        }
    }

    private async postJson(path: string, body?: any): Promise<any | null> {
        try {
            const opts: RequestInit = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                cache: 'no-store',
            };
            if (body) { opts.body = JSON.stringify(body); }
            const res = await fetch(`${this.baseUrl}${path}`, opts);
            if (!res.ok) { return null; }
            return await res.json();
        } catch {
            return null;
        }
    }

    async health(): Promise<{ status: string } | null> {
        return this.fetchJson('/health');
    }

    async getStatus(): Promise<SwarmStatus | null> {
        return this.fetchJson('/swarm/status');
    }

    async getRoutingConfig(): Promise<RoutingConfig | null> {
        return this.fetchJson('/routing/config');
    }

    async getNodes(): Promise<NodeInfo[] | null> {
        return this.fetchJson('/nodes/');
    }

    async getAgents(): Promise<AgentInfo[] | null> {
        return this.fetchJson('/swarm/agents');
    }

    async setThreshold(value: number): Promise<any | null> {
        return this.postJson('/routing/threshold', { threshold: value });
    }

    async forceLocal(): Promise<any | null> {
        return this.postJson('/routing/force-local');
    }

    async forceCloud(): Promise<any | null> {
        return this.postJson('/routing/force-cloud');
    }

    async autoBalance(): Promise<any | null> {
        return this.postJson('/routing/auto');
    }

    async routeInference(req: {
        prompt: string;
        requires_reasoning?: boolean;
        requires_tools?: boolean;
        latency_sensitive?: boolean;
        cost_sensitive?: boolean;
    }): Promise<any | null> {
        return this.postJson('/routing/infer', req);
    }

    async activateSwarm(): Promise<any | null> {
        return this.postJson('/swarm/activate');
    }

    async shutdownSwarm(): Promise<any | null> {
        return this.postJson('/swarm/shutdown');
    }
}
