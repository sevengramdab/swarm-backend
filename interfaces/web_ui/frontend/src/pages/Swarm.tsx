import { useState } from 'react'
import { useAgents, useSwarmStatus, useKillAgent, useRemoveAgent, useSpawnAgents } from '@/hooks/useApi'
import { useToast } from '@/components/ui/toaster'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Power, PowerOff, Plus, Skull, Trash2, Clock, CheckCircle, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Agent } from '@/types/index'

export function Swarm() {
  const { data: status } = useSwarmStatus()
  const { data: agents } = useAgents()
  const kill = useKillAgent()
  const remove = useRemoveAgent()
  const spawn = useSpawnAgents()
  const { toast } = useToast()
  const [spawnCount, setSpawnCount] = useState(1)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)

  const handleSpawn = () => {
    spawn.mutate(
      { count: spawnCount },
      {
        onSuccess: () => toast({ title: 'Spawned agents', description: `${spawnCount} new agent(s)` }),
        onError: () => toast({ title: 'Spawn failed', description: 'Could not spawn agents', variant: 'destructive' }),
      }
    )
  }

  const handleKill = (id: string) => {
    kill.mutate(id, {
      onSuccess: () => {
        toast({ title: 'Agent killed', description: id })
        setSelectedAgent(null)
      },
      onError: () => toast({ title: 'Kill failed', description: id, variant: 'destructive' }),
    })
  }

  const handleRemove = (id: string) => {
    remove.mutate(id, {
      onSuccess: () => {
        toast({ title: 'Agent removed', description: id })
        setSelectedAgent(null)
      },
      onError: () => toast({ title: 'Remove failed', description: id, variant: 'destructive' }),
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-bold">Swarm Controls</h2>
        <div className="flex items-center gap-2">
          <Button
            variant={status?.running ? 'destructive' : 'default'}
            disabled
            title="Not implemented"
          >
            {status?.running ? <PowerOff className="mr-2 h-4 w-4" /> : <Power className="mr-2 h-4 w-4" />}
            {status?.running ? 'Shutdown' : 'Activate'}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Spawn Agents</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Input
            type="number"
            min={1}
            max={100}
            value={spawnCount}
            onChange={(e) => setSpawnCount(Number(e.target.value))}
            className="w-24"
          />
          <Button onClick={handleSpawn} disabled={spawn.isPending}>
            <Plus className="mr-2 h-4 w-4" />
            Spawn
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[600px]">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {agents?.map((agent) => (
                <AgentItem
                  key={agent.agent_id}
                  agent={agent}
                  onClick={() => setSelectedAgent(agent)}
                  onKill={() => handleKill(agent.agent_id)}
                  onRemove={() => handleRemove(agent.agent_id)}
                />
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Dialog open={!!selectedAgent} onOpenChange={() => setSelectedAgent(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agent Detail</DialogTitle>
            <DialogDescription>{selectedAgent?.agent_id}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <Badge className="capitalize">{selectedAgent?.status}</Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Alive</span>
              <span>{selectedAgent?.alive ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Node</span>
              <span>{selectedAgent?.node_id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tasks Completed</span>
              <span>{selectedAgent?.tasks_completed}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tasks Failed</span>
              <span>{selectedAgent?.tasks_failed}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Uptime</span>
              <span>{selectedAgent ? formatUptime(selectedAgent.uptime_seconds) : '-'}</span>
            </div>
            {selectedAgent?.current_task ? (
              <div className="rounded-md border p-3">
                <p className="font-medium">Current Task</p>
                <p className="text-xs text-muted-foreground">{selectedAgent.current_task.task_id}</p>
                <p className="mt-1 text-xs">{selectedAgent.current_task.prompt}</p>
              </div>
            ) : null}
          </div>
          <div className="flex gap-2 pt-2">
            <Button variant="destructive" onClick={() => handleKill(selectedAgent!.agent_id)}>
              <Skull className="mr-2 h-4 w-4" />
              Kill
            </Button>
            {selectedAgent?.status === 'dead' && (
              <Button variant="outline" onClick={() => handleRemove(selectedAgent.agent_id)}>
                <Trash2 className="mr-2 h-4 w-4" />
                Remove
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function AgentItem({ agent, onClick, onKill, onRemove }: { agent: Agent; onClick: () => void; onKill: () => void; onRemove: () => void }) {
  const statusColor =
    agent.status === 'running'
      ? 'bg-green-500'
      : agent.status === 'idle'
      ? 'bg-blue-500'
      : agent.status === 'degraded'
      ? 'bg-yellow-500'
      : 'bg-red-500'

  return (
    <div
      className="flex cursor-pointer flex-col gap-2 rounded-md border p-4 transition-colors hover:bg-accent"
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn('h-2.5 w-2.5 rounded-full', statusColor)} />
          <span className="text-sm font-medium">{agent.agent_id.slice(0, 12)}...</span>
        </div>
        <Badge variant="outline" className="text-xs capitalize">
          {agent.status}
        </Badge>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <CheckCircle className="h-3 w-3" />
          {agent.tasks_completed}
        </span>
        <span className="flex items-center gap-1">
          <XCircle className="h-3 w-3" />
          {agent.tasks_failed}
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatUptime(agent.uptime_seconds)}
        </span>
      </div>
      <div className="flex gap-2 pt-1">
        <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={(e) => { e.stopPropagation(); onKill() }}>
          <Skull className="mr-1 h-3 w-3" />
          Kill
        </Button>
        {agent.status === 'dead' && (
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={(e) => { e.stopPropagation(); onRemove() }}>
            <Trash2 className="mr-1 h-3 w-3" />
            Remove
          </Button>
        )}
      </div>
    </div>
  )
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h}h ${m}m ${s}s`
}
