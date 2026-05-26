import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/toaster'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Globe,
  Server,
  RefreshCw,
  Plus,
  Radio,
  ArrowRightLeft,
  Activity,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface MeshNode {
  node_id: string
  name: string
  endpoint: string
  tier: string
  status: string
  latency_ms: number
  last_seen: number
  models: string[]
  vram_mb: number
}

interface LocalNodeInfo {
  node_id: string
  name: string
  endpoint: string
  tier: string
  models: string[]
  vram_mb: number
  routing_mode: string
  local_task_count: number
  remote_task_count: number
}

interface MeshTopology {
  local: LocalNodeInfo
  nodes: MeshNode[]
}

function useMeshTopology() {
  return useQuery<MeshTopology | null>({
    queryKey: ['meshTopology'],
    queryFn: () => api.get('/mesh/topology'),
    refetchInterval: 5000,
  })
}

function useDiscoverNodes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/mesh/nodes/discover'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meshTopology'] }),
  })
}

function useRegisterNode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (node: { node_id: string; name: string; endpoint: string; tier: string }) =>
      api.post('/mesh/nodes/register', node),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meshTopology'] }),
  })
}

function useRemoveNode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (node_id: string) => api.delete(`/mesh/nodes/${node_id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meshTopology'] }),
  })
}

export function Mesh() {
  const { toast } = useToast()
  const { data, isLoading, refetch } = useMeshTopology()
  const discover = useDiscoverNodes()
  const register = useRegisterNode()
  const remove = useRemoveNode()
  const [form, setForm] = useState({ node_id: '', name: '', endpoint: '', tier: 'shadow', vram_mb: 0 })

  const local = data?.local
  const nodes = data?.nodes ?? []

  const handleDiscover = () => {
    discover.mutate(undefined, {
      onSuccess: () => toast({ title: 'Discovery started', description: 'Scanning for mesh nodes…' }),
      onError: () => toast({ title: 'Discovery failed', variant: 'destructive' }),
    })
  }

  const handleRegister = () => {
    if (!form.node_id || !form.endpoint) return
    register.mutate(form, {
      onSuccess: () => {
        toast({ title: 'Node registered' })
        setForm({ node_id: '', name: '', endpoint: '', tier: 'shadow', vram_mb: 0 })
      },
      onError: () => toast({ title: 'Registration failed', variant: 'destructive' }),
    })
  }

  const handleRemove = (node_id: string) => {
    remove.mutate(node_id, {
      onSuccess: () => toast({ title: 'Node removed' }),
      onError: () => toast({ title: 'Remove failed', variant: 'destructive' }),
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Mesh Topology</h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('mr-2 h-4 w-4', isLoading && 'animate-spin')} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleDiscover} disabled={discover.isPending}>
            <Radio className="mr-2 h-4 w-4" />
            Discover
          </Button>
        </div>
      </div>

      {local && (
        <Card className="border-primary/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">{local.name || local.node_id}</CardTitle>
                <Badge variant="default">Local</Badge>
              </div>
              <Badge variant="outline">{local.routing_mode}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-3">
              <div>
                <span className="font-medium text-foreground">Endpoint:</span> {local.endpoint}
              </div>
              <div>
                <span className="font-medium text-foreground">Tier:</span>{' '}
                <TierBadge tier={local.tier} />
              </div>
              <div>
                <span className="font-medium text-foreground">Models:</span>{' '}
                {local.models.join(', ') || '—'}
              </div>
              <div>
                <span className="font-medium text-foreground">VRAM:</span>{' '}
                {local.vram_mb ? `${(local.vram_mb / 1024).toFixed(1)} GB` : '—'}
              </div>
            </div>
            <div className="flex gap-4 pt-1">
              <div className="flex items-center gap-2 text-sm">
                <ArrowRightLeft className="h-4 w-4 text-green-500" />
                <span className="font-medium">{local.local_task_count}</span> local tasks
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Globe className="h-4 w-4 text-blue-500" />
                <span className="font-medium">{local.remote_task_count}</span> remote tasks
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Remote Nodes</CardTitle>
            <span className="text-xs text-muted-foreground">{nodes.length} connected</span>
          </div>
        </CardHeader>
        <CardContent>
          {nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Globe className="mb-2 h-8 w-8 opacity-50" />
              <p>No remote nodes registered.</p>
              <p className="text-xs">Click Discover to scan or add one manually.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Node</th>
                    <th className="pb-2 pr-4">Endpoint</th>
                    <th className="pb-2 pr-4">Tier</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Latency</th>
                    <th className="pb-2 pr-4">VRAM</th>
                    <th className="pb-2 pr-4">Models</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node) => (
                    <tr key={node.node_id} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-medium">{node.name || node.node_id}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{node.endpoint}</td>
                      <td className="py-2 pr-4"><TierBadge tier={node.tier} /></td>
                      <td className="py-2 pr-4">
                        <Badge variant={node.status === 'online' ? 'default' : 'destructive'} className="capitalize">
                          {node.status}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-1">
                          <Activity className={cn('h-3 w-3', node.latency_ms < 50 ? 'text-green-500' : node.latency_ms < 150 ? 'text-yellow-500' : 'text-red-500')} />
                          {node.latency_ms}ms
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {node.vram_mb ? `${(node.vram_mb / 1024).toFixed(1)} GB` : '—'}
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {node.models.slice(0, 3).map((m) => (
                            <Badge key={m} variant="outline" className="text-xs">{m}</Badge>
                          ))}
                          {node.models.length > 3 && (
                            <Badge variant="outline" className="text-xs">+{node.models.length - 3}</Badge>
                          )}
                        </div>
                      </td>
                      <td className="py-2 text-right">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleRemove(node.node_id)}>
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Register Node</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-5">
            <Input placeholder="Node ID" value={form.node_id} onChange={(e) => setForm({ ...form, node_id: e.target.value })} />
            <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input placeholder="http://host:port" value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })} />
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={form.tier}
              onChange={(e) => setForm({ ...form, tier: e.target.value })}
            >
              <option value="local">Local</option>
              <option value="shadow">Shadow</option>
              <option value="cloud">Cloud</option>
            </select>
            <Input
              type="number"
              placeholder="VRAM (MB)"
              value={form.vram_mb || ''}
              onChange={(e) => setForm({ ...form, vram_mb: parseInt(e.target.value) || 0 })}
            />
            <Button onClick={handleRegister} disabled={register.isPending || !form.node_id || !form.endpoint}>
              <Plus className="mr-2 h-4 w-4" />
              Register
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    local: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    shadow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    cloud: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  }
  return (
    <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', colors[tier] || 'bg-muted text-muted-foreground')}>
      {tier}
    </span>
  )
}
