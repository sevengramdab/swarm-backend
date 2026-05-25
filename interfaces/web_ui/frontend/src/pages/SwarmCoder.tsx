import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/components/ui/toaster'
import { Loader2, Send, Square, Terminal, FileCode, CheckCircle, XCircle, Clock, Lightbulb, Zap, Brain } from 'lucide-react'
import { cn } from '@/lib/utils'

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

interface PlanOption {
  option_id: string
  title: string
  description: string
  approach: string
  estimated_files: number
  complexity: string
  tools_needed: string[]
}

interface Plan {
  plan_id: string
  goal: string
  status: string
  options: PlanOption[]
  selected_option_id: string | null
  task_id: string | null
}

interface ReactTurn {
  turn_number: number
  tool: string
  params: Record<string, unknown>
  reasoning: string
  result: Record<string, unknown>
  success: boolean
}

interface ReactTask {
  task_id: string
  goal: string
  status: string
  result_summary: string
  turn_count: number
  turns: ReactTurn[]
}

type Mode = 'direct' | 'plan' | 'react'

export function SwarmCoder() {
  const { toast } = useToast()
  const [mode, setMode] = useState<Mode>('direct')
  const [goal, setGoal] = useState('')
  const [tasks, setTasks] = useState<CoderTask[]>([])
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Plan state
  const [currentPlan, setCurrentPlan] = useState<Plan | null>(null)
  const [planLoading, setPlanLoading] = useState(false)

  // ReAct state
  const [reactTasks, setReactTasks] = useState<ReactTask[]>([])
  const [activeReactId, setActiveReactId] = useState<string | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchTasks = useCallback(async () => {
    try {
      const res = await api.get('/swarmcoder/tasks') as { tasks?: CoderTask[] }
      if (res.tasks) {
        setTasks(res.tasks)
        const running = res.tasks.find((t) => t.status === 'RUNNING')
        if (running && !activeTaskId && mode !== 'react') {
          setActiveTaskId(running.task_id)
        }
      }
      // Also fetch react tasks
      const rres = await api.get('/swarmcoder/react/tasks') as { tasks?: ReactTask[] }
      if (rres.tasks) {
        setReactTasks(rres.tasks)
        const rrunning = rres.tasks.find((t) => t.status === 'running')
        if (rrunning && !activeReactId && mode === 'react') {
          setActiveReactId(rrunning.task_id)
        }
      }
    } catch {
      // ignore
    }
  }, [activeTaskId, activeReactId, mode])

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

  const submitPlan = async () => {
    if (!goal.trim()) return
    setPlanLoading(true)
    try {
      const res = await api.post('/swarmcoder/plan', { goal: goal.trim() }) as Plan
      setCurrentPlan(res)
      toast({ title: 'Plan created', description: `${res.options.length} options available` })
    } catch {
      toast({ title: 'Plan failed', variant: 'destructive' })
    } finally {
      setPlanLoading(false)
    }
  }

  const executePlanOption = async (optionId: string) => {
    if (!currentPlan) return
    setLoading(true)
    try {
      const res = await api.post(`/swarmcoder/plan/${currentPlan.plan_id}/execute`, { option_id: optionId }) as CoderTask
      setActiveTaskId(res.task_id)
      setCurrentPlan(null)
      setGoal('')
      setMode('direct')
      await fetchTasks()
      toast({ title: 'Plan executing', description: `Task ${res.task_id} started` })
    } catch {
      toast({ title: 'Execution failed', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  const submitReact = async () => {
    if (!goal.trim()) return
    setLoading(true)
    try {
      const res = await api.post('/swarmcoder/react/task', { goal: goal.trim() }) as ReactTask
      setActiveReactId(res.task_id)
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

  const stopReactTask = async (taskId: string) => {
    await api.post(`/swarmcoder/react/task/${taskId}/stop`, {})
    await fetchTasks()
  }

  const activeTask = tasks.find((t) => t.task_id === activeTaskId) || tasks[0]
  const activeReact = reactTasks.find((t) => t.task_id === activeReactId) || reactTasks[0]

  const statusColor = (s: string) => {
    if (s === 'COMPLETED') return 'bg-green-500'
    if (s === 'FAILED' || s === 'failed') return 'bg-red-500'
    if (s === 'RUNNING' || s === 'running') return 'bg-blue-500 animate-pulse'
    return 'bg-gray-500'
  }

  const statusBadge = (s: string) => {
    if (s === 'COMPLETED') return <Badge className="bg-green-600"><CheckCircle className="w-3 h-3 mr-1" />Done</Badge>
    if (s === 'FAILED' || s === 'failed') return <Badge className="bg-red-600"><XCircle className="w-3 h-3 mr-1" />Failed</Badge>
    if (s === 'RUNNING' || s === 'running') return <Badge className="bg-blue-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" />Running</Badge>
    return <Badge variant="outline">{s}</Badge>
  }

  const complexityColor = (c: string) => {
    if (c === 'low') return 'bg-green-100 text-green-800'
    if (c === 'medium') return 'bg-yellow-100 text-yellow-800'
    if (c === 'high') return 'bg-red-100 text-red-800'
    return 'bg-gray-100 text-gray-800'
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">SwarmCoder</h1>
          <p className="text-muted-foreground">Autonomous coding agent. Describe a task, let SimplePod execute it.</p>
        </div>
      </div>

      {/* Mode Selector */}
      <div className="flex gap-2">
        <Button variant={mode === 'direct' ? 'default' : 'outline'} size="sm" onClick={() => setMode('direct')}>
          <Zap className="w-4 h-4 mr-1" /> Direct
        </Button>
        <Button variant={mode === 'plan' ? 'default' : 'outline'} size="sm" onClick={() => setMode('plan')}>
          <Lightbulb className="w-4 h-4 mr-1" /> Plan First
        </Button>
        <Button variant={mode === 'react' ? 'default' : 'outline'} size="sm" onClick={() => setMode('react')}>
          <Brain className="w-4 h-4 mr-1" /> ReAct Agent
        </Button>
      </div>

      {/* Input Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode className="w-5 h-5" />
            {mode === 'direct' && 'New Task'}
            {mode === 'plan' && 'Plan a Task'}
            {mode === 'react' && 'ReAct Agent Task'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder={
                mode === 'direct'
                  ? "e.g. Add a health check endpoint to the FastAPI app"
                  : mode === 'plan'
                  ? "e.g. Build a log monitoring system with alerts and auto-restart"
                  : "e.g. Research the best Python async HTTP library and write a comparison script"
              }
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                if (mode === 'direct') submitGoal()
                if (mode === 'plan') submitPlan()
                if (mode === 'react') submitReact()
              }}
              disabled={loading || planLoading}
            />
            {mode === 'direct' && (
              <Button onClick={submitGoal} disabled={loading || !goal.trim()}>
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </Button>
            )}
            {mode === 'plan' && (
              <Button onClick={submitPlan} disabled={planLoading || !goal.trim()}>
                {planLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lightbulb className="w-4 h-4" />}
              </Button>
            )}
            {mode === 'react' && (
              <Button onClick={submitReact} disabled={loading || !goal.trim()}>
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {mode === 'direct' && 'Executes immediately using plan-first or reactive mode.'}
            {mode === 'plan' && 'The agent sketches 3-4 approaches first. You pick one, then it builds.'}
            {mode === 'react' && 'Multi-turn agent with web search, file access, and shell commands.'}
          </p>
        </CardContent>
      </Card>

      {/* Plan Options */}
      {currentPlan && mode === 'plan' && (
        <Card>
          <CardHeader>
            <CardTitle>Choose an Approach</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              {currentPlan.options.map((opt) => (
                <Card key={opt.option_id} className="border-2 border-transparent hover:border-primary/50 transition-colors">
                  <CardContent className="p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold">{opt.title}</h3>
                      <span className={cn('text-xs px-2 py-0.5 rounded font-medium', complexityColor(opt.complexity))}>
                        {opt.complexity}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">{opt.description}</p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Approach:</span> {opt.approach}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <FileCode className="w-3 h-3" />
                      ~{opt.estimated_files} files
                    </div>
                    {opt.tools_needed.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {opt.tools_needed.map((t) => (
                          <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
                        ))}
                      </div>
                    )}
                    <Button size="sm" className="w-full" onClick={() => executePlanOption(opt.option_id)} disabled={loading}>
                      {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Build This'}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Task List */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>{mode === 'react' ? 'ReAct Tasks' : 'Tasks'}</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {mode !== 'react' && tasks.length === 0 && (
                  <p className="text-sm text-muted-foreground">No tasks yet. Submit a goal above.</p>
                )}
                {mode === 'react' && reactTasks.length === 0 && (
                  <p className="text-sm text-muted-foreground">No ReAct tasks yet.</p>
                )}
                {mode !== 'react' && tasks.map((t) => (
                  <button
                    key={t.task_id}
                    onClick={() => { setActiveTaskId(t.task_id); setActiveReactId(null) }}
                    className={cn('w-full text-left p-3 rounded-lg border transition-colors', activeTaskId === t.task_id ? 'bg-accent border-primary' : 'hover:bg-accent/50')}
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
                {mode === 'react' && reactTasks.map((t) => (
                  <button
                    key={t.task_id}
                    onClick={() => { setActiveReactId(t.task_id); setActiveTaskId(null) }}
                    className={cn('w-full text-left p-3 rounded-lg border transition-colors', activeReactId === t.task_id ? 'bg-accent border-primary' : 'hover:bg-accent/50')}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-muted-foreground">{t.task_id}</span>
                      {statusBadge(t.status)}
                    </div>
                    <p className="text-sm font-medium truncate">{t.goal}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t.turn_count} turns
                    </p>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Active Detail */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>{mode === 'react' ? 'ReAct Execution Log' : 'Execution Log'}</span>
              {mode !== 'react' && activeTask && (activeTask.status === 'RUNNING') && (
                <Button size="sm" variant="destructive" onClick={() => stopTask(activeTask.task_id)}>
                  <Square className="w-3 h-3 mr-1" /> Stop
                </Button>
              )}
              {mode === 'react' && activeReact && (activeReact.status === 'running') && (
                <Button size="sm" variant="destructive" onClick={() => stopReactTask(activeReact.task_id)}>
                  <Square className="w-3 h-3 mr-1" /> Stop
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {mode !== 'react' && activeTask ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className={cn('w-3 h-3 rounded-full', statusColor(activeTask.status))} />
                  <span className="font-medium">{activeTask.goal}</span>
                </div>
                {activeTask.total_steps > 0 && (
                  <div className="w-full bg-secondary rounded-full h-2">
                    <div className="bg-primary h-2 rounded-full transition-all" style={{ width: `${Math.min(100, (activeTask.current_step / activeTask.total_steps) * 100)}%` }} />
                  </div>
                )}
                {activeTask.result_summary && (
                  <div className="p-3 bg-muted rounded-lg text-sm">
                    <strong>Result:</strong> {activeTask.result_summary}
                  </div>
                )}
                <ScrollArea className="h-[320px] border rounded-lg bg-black/5">
                  <div className="p-3 space-y-2 font-mono text-xs">
                    {activeTask.logs.length === 0 && <p className="text-muted-foreground">Waiting for execution...</p>}
                    {activeTask.logs.map((log, i) => (
                      <div key={i} className="border-l-2 pl-2 py-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">#{log.step}</span>
                          <Badge variant={log.success ? 'default' : 'destructive'} className="text-[10px]">{log.action}</Badge>
                          <span className="text-muted-foreground">{new Date(log.timestamp * 1000).toLocaleTimeString()}</span>
                        </div>
                        <pre className="whitespace-pre-wrap break-all text-muted-foreground">{log.result}</pre>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            ) : mode === 'react' && activeReact ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className={cn('w-3 h-3 rounded-full', statusColor(activeReact.status))} />
                  <span className="font-medium">{activeReact.goal}</span>
                </div>
                {activeReact.result_summary && (
                  <div className="p-3 bg-muted rounded-lg text-sm">
                    <strong>Result:</strong> {activeReact.result_summary}
                  </div>
                )}
                <ScrollArea className="h-[320px] border rounded-lg bg-black/5">
                  <div className="p-3 space-y-3 font-mono text-xs">
                    {activeReact.turns.length === 0 && <p className="text-muted-foreground">Waiting for agent...</p>}
                    {activeReact.turns.map((turn, i) => (
                      <div key={i} className="border rounded-lg p-2 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Turn {turn.turn_number}</span>
                          <Badge variant={turn.success ? 'default' : 'destructive'} className="text-[10px]">{turn.tool}</Badge>
                        </div>
                        <p className="text-blue-600">{turn.reasoning}</p>
                        <pre className="whitespace-pre-wrap break-all text-muted-foreground">{JSON.stringify(turn.result, null, 2)}</pre>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-[400px] text-muted-foreground">
                <Terminal className="w-12 h-12 mb-4 opacity-50" />
                <p>Select a task to view details</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
