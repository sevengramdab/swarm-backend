import { useSwarmStatus, useAgents, useNodes, useActiveTasks } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Activity, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Agent, NodeInfo, ActiveTask } from '@/types/index'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h}h ${m}m ${s}s`
}

export function Dashboard() {
  const { data: status } = useSwarmStatus()
  const { data: agents } = useAgents()
  const { data: nodes } = useNodes()
  const { data: tasks } = useActiveTasks()

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Total Agents" value={status?.agents_total ?? 0} icon={Activity} />
        <MetricCard title="Active Agents" value={status?.agents_active ?? 0} icon={CheckCircle} color="text-green-500" />
        <MetricCard title="Pending Tasks" value={status?.pending_tasks ?? 0} icon={Loader2} color="text-yellow-500" />
        <MetricCard title="Failed Tasks" value={status?.failed_tasks ?? 0} icon={XCircle} color="text-red-500" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Agents</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-80">
              <div className="grid gap-3 sm:grid-cols-2">
                {agents?.map((agent) => (
                  <AgentCard key={agent.agent_id} agent={agent} />
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Nodes</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-80">
              <div className="space-y-3">
                {nodes?.map((node) => (
                  <NodeRow key={node.node_id} node={node} />
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Active Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-64">
            <div className="space-y-2">
              {tasks?.map((task) => (
                <TaskRow key={task.task_id} task={task} />
              ))}
              {!tasks?.length && <p className="text-sm text-muted-foreground">No active tasks</p>}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}

function MetricCard({ title, value, icon: Icon, color }: { title: string; value: number; icon: React.ElementType; color?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-6">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-3xl font-bold">{value}</p>
        </div>
        <Icon className={cn('h-8 w-8', color || 'text-primary')} />
      </CardContent>
    </Card>
  )
}

function AgentCard({ agent }: { agent: Agent }) {
  const statusColor =
    agent.status === 'running'
      ? 'bg-green-500'
      : agent.status === 'idle'
      ? 'bg-blue-500'
      : agent.status === 'degraded'
      ? 'bg-yellow-500'
      : 'bg-red-500'

  return (
    <div className="flex items-start gap-3 rounded-md border p-3 transition-colors hover:bg-accent">
      <div className={cn('mt-1.5 h-2 w-2 rounded-full', statusColor)} />
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{agent.agent_id.slice(0, 12)}...</span>
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
      </div>
    </div>
  )
}

function NodeRow({ node }: { node: NodeInfo }) {
  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <div>
        <p className="text-sm font-medium">{node.node_id}</p>
        <p className="text-xs text-muted-foreground">{node.provider || 'Unknown provider'}</p>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className={cn('h-2 w-2 rounded-full', node.status === 'online' ? 'bg-green-500' : 'bg-red-500')} />
        <span>{node.latency_ms}ms</span>
        <span>{node.models.length} models</span>
      </div>
    </div>
  )
}

function TaskRow({ task }: { task: ActiveTask }) {
  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{task.prompt}</p>
        <p className="text-xs text-muted-foreground">
          {task.agent_id} &bull; {task.model}
        </p>
      </div>
      <Badge variant="secondary" className="ml-2 shrink-0 text-xs capitalize">
        {task.status}
      </Badge>
    </div>
  )
}
