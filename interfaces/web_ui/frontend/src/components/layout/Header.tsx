import { Activity, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { useSwarmStatus } from '@/hooks/useApi'

export function Header() {
  const { data: status } = useSwarmStatus()

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-6">
      <div className="flex items-center gap-2">
        <Activity className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-semibold">Swarm Dashboard</h1>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Circle
            className={cn(
              'h-2.5 w-2.5 fill-current',
              status?.running ? 'text-green-500' : 'text-red-500'
            )}
          />
          <span>{status?.running ? 'Online' : 'Offline'}</span>
        </div>
        <Badge variant="secondary">
          {status?.agents_active ?? 0} active / {status?.agents_total ?? 0} total
        </Badge>
      </div>
    </header>
  )
}
