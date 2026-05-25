import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { SwarmStatus, Agent, NodeInfo, RoutingConfig, ActiveTask, AppSettings, AgentConfig } from '@/types/index'

// Swarm
export function useSwarmStatus() {
  return useQuery<SwarmStatus | null>({
    queryKey: ['swarmStatus'],
    queryFn: () => api.get('/swarm/status'),
  })
}

export function useAgents() {
  return useQuery<Agent[] | null>({
    queryKey: ['agents'],
    queryFn: () => api.get('/swarm/agents'),
  })
}

export function useAgent(id: string) {
  return useQuery<Agent | null>({
    queryKey: ['agent', id],
    queryFn: () => api.get(`/swarm/agents/${id}`),
    enabled: !!id,
  })
}

export function useKillAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/swarm/agents/${id}/kill`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      qc.invalidateQueries({ queryKey: ['swarmStatus'] })
    },
  })
}

export function useRemoveAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/swarm/agents/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      qc.invalidateQueries({ queryKey: ['swarmStatus'] })
    },
  })
}

export function useAgentConfig(id: string) {
  return useQuery<AgentConfig | null>({
    queryKey: ['agentConfig', id],
    queryFn: () => api.get(`/swarm/agents/${id}/config`),
    enabled: !!id,
  })
}

export function useUpdateAgentConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, config }: { id: string; config: AgentConfig }) =>
      api.put(`/swarm/agents/${id}/config`, { config }),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['agent', id] })
      qc.invalidateQueries({ queryKey: ['agentConfig', id] })
    },
  })
}

export function useSpawnAgents() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ count, config }: { count: number; config?: AgentConfig }) =>
      api.post('/swarm/agents/spawn', { count, config }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      qc.invalidateQueries({ queryKey: ['swarmStatus'] })
    },
  })
}

// Tasks
export function useActiveTasks() {
  return useQuery<ActiveTask[] | null>({
    queryKey: ['activeTasks'],
    queryFn: () => api.get('/swarm/tasks/active'),
  })
}

export function useTaskResult(id: string) {
  return useQuery<unknown | null>({
    queryKey: ['task', id],
    queryFn: () => api.get(`/swarm/tasks/${id}`),
    enabled: !!id,
  })
}

// Models
export function useModels() {
  return useQuery<string[] | null>({
    queryKey: ['models'],
    queryFn: () => api.get('/swarm/models'),
  })
}

// Nodes
export function useNodes() {
  return useQuery<NodeInfo[] | null>({
    queryKey: ['nodes'],
    queryFn: () => api.get('/nodes/'),
  })
}

// Routing
export function useRoutingConfig() {
  return useQuery<RoutingConfig | null>({
    queryKey: ['routingConfig'],
    queryFn: () => api.get('/routing/config'),
  })
}

export interface InferPayload {
  prompt: string
  model_hint?: string
  temperature?: number
  messages?: { role: string; content: string }[]
  mode?: string
}

export function useInfer() {
  return useMutation({
    mutationFn: (payload: InferPayload) => api.post<{ task_id: string }>('/routing/infer', payload),
  })
}

export async function pollChatTaskResult(taskId: string): Promise<unknown> {
  const result = await api.get<{ status: string; result?: unknown }>(`/swarm/tasks/${taskId}`)
  if (result && (result.status === 'completed' || result.status === 'failed')) {
    return result
  }
  await new Promise((r) => setTimeout(r, 1000))
  return pollChatTaskResult(taskId)
}

// Settings
export function useSettings() {
  return useQuery<AppSettings | null>({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings'),
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (settings: AppSettings) => api.put('/settings', settings),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}

export function useResetSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/settings/reset'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}
