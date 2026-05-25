import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, Send, Square, Terminal, FileCode, CheckCircle, XCircle, Clock } from 'lucide-react'

interface TaskLog {
  timestamp: number
  step: number
  action: string
  result: string
  success: boolean
}

interface CoderTask {
  task_id: string
  goal: string
  status: string
  current_step: number
  total_steps: number
  created_at: number
  updated_at: number
  result_summary: string
  logs: TaskLog[]
}

export function SwarmCoder() {
  const [goal, setGoal] = useState('')
  const [tasks, setTasks] = useState<CoderTask[]>([])
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchTasks = useCallback(async () => {
    try {
      const res = await api.get('/swarmcoder/tasks') as { tasks?: CoderTask[] }
      if (res.tasks) {
        setTasks(res.tasks)
        const running = res.tasks.find((t) => t.status === 'RUNNING' || t.status === 'PLANNING')
        if (running && !activeTaskId) {
          setActiveTaskId(running.task_id)
        }
      }
    } catch {
      // ignore
    }
  }, [activeTaskId])

  useEffect(() => {
    fetchTasks()
    pollRef.current = setInterval(fetchTasks, 1500)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [fetchTasks])

  const submitGoal = async () => {
    if (!goal.trim()) return
    setLoading(true)
    try {
      const res = await api.post('/swarmcoder/task', { goal: goal.trim() }) as CoderTask
      setActiveTaskId(res.task_id)
      setGoal('')
      await fetchTasks()
    } finally {
      setLoading(false)
    }
  }

  const stopTask = async (taskId: string) => {
    await api.post(`/swarmcoder/task/${taskId}/stop`, {})
    await fetchTasks()
  }

  const activeTask = tasks.find((t) => t.task_id === activeTaskId) || tasks[0]

  const statusColor = (s: string) => {
    if (s === 'COMPLETED') return 'bg-green-500'
    if (s === 'FAILED') return 'bg-red-500'
    if (s === 'RUNNING') return 'bg-blue-500 animate-pulse'
    if (s === 'PLANNING') return 'bg-yellow-500 animate-pulse'
    return 'bg-gray-500'
  }

  const statusBadge = (s: string) => {
    if (s === 'COMPLETED') return <Badge className="bg-green-600"><CheckCircle className="w-3 h-3 mr-1" />Done</Badge>
    if (s === 'FAILED') return <Badge className="bg-red-600"><XCircle className="w-3 h-3 mr-1" />Failed</Badge>
    if (s === 'RUNNING') return <Badge className="bg-blue-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" />Running</Badge>
    if (s === 'PLANNING') return <Badge className="bg-yellow-600"><Clock className="w-3 h-3 mr-1" />Planning</Badge>
    return <Badge variant="outline">{s}</Badge>
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">SwarmCoder</h1>
          <p className="text-muted-foreground">Autonomous coding agent. Describe a task, let SimplePod execute it.</p>
        </div>
      </div>

      {/* Goal Input */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode className="w-5 h-5" />
            New Task
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="e.g. Add a health check endpoint to the FastAPI app, write a test for it, and verify it returns 200"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitGoal()}
              disabled={loading}
            />
            <Button onClick={submitGoal} disabled={loading || !goal.trim()}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Task List */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Tasks</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {tasks.length === 0 && (
                  <p className="text-sm text-muted-foreground">No tasks yet. Submit a goal above.</p>
                )}
                {tasks.map((t) => (
                  <button
                    key={t.task_id}
                    onClick={() => setActiveTaskId(t.task_id)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                      activeTaskId === t.task_id ? 'bg-accent border-primary' : 'hover:bg-accent/50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-muted-foreground">{t.task_id}</span>
                      {statusBadge(t.status)}
                    </div>
                    <p className="text-sm font-medium truncate">{t.goal}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Step {t.current_step} / {t.total_steps}
                    </p>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Active Task Detail */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Execution Log</span>
              {activeTask && (activeTask.status === 'RUNNING' || activeTask.status === 'PLANNING') && (
                <Button size="sm" variant="destructive" onClick={() => stopTask(activeTask.task_id)}>
                  <Square className="w-3 h-3 mr-1" /> Stop
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {activeTask ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${statusColor(activeTask.status)}`} />
                  <span className="font-medium">{activeTask.goal}</span>
                </div>

                {/* Progress */}
                {activeTask.total_steps > 0 && (
                  <div className="w-full bg-secondary rounded-full h-2">
                    <div
                      className="bg-primary h-2 rounded-full transition-all"
                      style={{ width: `${Math.min(100, (activeTask.current_step / activeTask.total_steps) * 100)}%` }}
                    />
                  </div>
                )}

                {/* Result Summary */}
                {activeTask.result_summary && (
                  <div className="p-3 bg-muted rounded-lg text-sm">
                    <strong>Result:</strong> {activeTask.result_summary}
                  </div>
                )}

                {/* Logs */}
                <ScrollArea className="h-[320px] border rounded-lg bg-black/5">
                  <div className="p-3 space-y-2 font-mono text-xs">
                    {activeTask.logs.length === 0 && (
                      <p className="text-muted-foreground">Waiting for execution to start...</p>
                    )}
                    {activeTask.logs.map((log, i) => (
                      <div key={i} className="border-l-2 pl-2 py-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">#{log.step}</span>
                          <Badge variant={log.success ? 'default' : 'destructive'} className="text-[10px]">
                            {log.action}
                          </Badge>
                          <span className="text-muted-foreground">
                            {new Date(log.timestamp * 1000).toLocaleTimeString()}
                          </span>
                        </div>
                        <pre className="whitespace-pre-wrap break-all text-muted-foreground">{log.result}</pre>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-[400px] text-muted-foreground">
                <Terminal className="w-12 h-12 mb-4 opacity-50" />
                <p>Select a task to view execution details</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
