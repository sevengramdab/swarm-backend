export interface SwarmStatus {
  running: boolean
  agents_total: number
  agents_active: number
  agents_idle: number
  pending_tasks: number
  completed_tasks: number
  failed_tasks: number
  uptime_seconds: number
}

export interface Agent {
  agent_id: string
  status: 'running' | 'idle' | 'degraded' | 'dead'
  alive: boolean
  tasks_completed: number
  tasks_failed: number
  node_id: string
  uptime: number
  uptime_seconds: number
  last_heartbeat: number
  config?: Record<string, unknown>
  current_task?: {
    task_id: string
    status: string
    model?: string
    prompt?: string
    started_at?: number
  } | null
}

export interface NodeInfo {
  node_id: string
  status: string
  latency_ms: number
  last_seen: number
  provider?: string
  models: string[]
  gpu_utilization?: number
  vram_used_mb?: number
  vram_total_mb?: number
}

export interface RoutingConfig {
  mode: string
  threshold: number
  healthy_tiers: string[]
  tripped_tiers: string[]
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  agent?: string
  model?: string
  error?: boolean
}

export interface Conversation {
  id: string
  name: string
  mode: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
}

export interface ActiveTask {
  task_id: string
  agent_id: string
  status: string
  prompt: string
  model: string
  started_at: number
}

export interface TelemetryEvent {
  time: string
  type: string
  msg: string
}

export interface AgentConfig {
  model?: string
  temperature?: number
  max_tokens?: number
}

export interface AppSettings {
  [key: string]: unknown
}
