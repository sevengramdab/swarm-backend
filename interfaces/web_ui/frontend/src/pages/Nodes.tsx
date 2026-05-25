import { useNodes } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Server, Cpu } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { NodeInfo } from '@/types/index'

export function Nodes() {
  const { data: nodes } = useNodes()

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Node Map</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {nodes?.map((node) => <NodeCard key={node.node_id} node={node} />)}
        {!nodes?.length && <p className="text-muted-foreground">No nodes connected</p>}
      </div>
    </div>
  )
}

function NodeCard({ node }: { node: NodeInfo }) {
  const gpuPercent = node.vram_total_mb ? Math.round(((node.vram_used_mb ?? 0) / node.vram_total_mb) * 100) : 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{node.node_id}</CardTitle>
          <Badge variant={node.status === 'online' ? 'default' : 'destructive'} className="capitalize">
            {node.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Server className="h-4 w-4" />
          <span>{node.provider || 'Unknown'}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Cpu className="h-4 w-4" />
          <span>Latency: {node.latency_ms}ms</span>
        </div>
        {node.vram_total_mb ? (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>GPU VRAM</span>
              <span>
                {node.vram_used_mb} / {node.vram_total_mb} MB
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={cn('h-full rounded-full', gpuPercent > 90 ? 'bg-destructive' : gpuPercent > 70 ? 'bg-yellow-500' : 'bg-green-500')}
                style={{ width: `${gpuPercent}%` }}
              />
            </div>
          </div>
        ) : null}
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Models</p>
          <ScrollArea className="h-20">
            <div className="flex flex-wrap gap-1">
              {node.models.map((m) => (
                <Badge key={m} variant="outline" className="text-xs">
                  {m}
                </Badge>
              ))}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  )
}
