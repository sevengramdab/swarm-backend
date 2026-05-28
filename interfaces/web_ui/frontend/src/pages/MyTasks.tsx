import { useState, useEffect } from 'react'
import { useToast } from '@/components/ui/toaster'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ListChecks, ClipboardList, Clock, CheckCircle2, XCircle, Loader2, Cpu, Eye, ThumbsUp, ThumbsDown, Send } from 'lucide-react'

const API = 'http://localhost:8000/billing'
const USER_ID = 'user_001'

interface Task {
  task_id: string
  user_id: string
  goal: string
  bounty: number
  complexity: string
  status: string
  claimed_by?: string
  claimed_by_name?: string
  claimed_at?: number
  completed_at?: number
  result_summary?: string
  node_payout?: number
  platform_fee?: number
  created_at: number
}

export function MyTasks() {
  const { toast } = useToast()
  const [posted, setPosted] = useState<Task[]>([])
  const [claimed, setClaimed] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [reviewText, setReviewText] = useState<Record<string, string>>({})

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/marketplace/tasks`)
      const data = await res.json()
      const all = data.tasks || []
      setPosted(all.filter((t: Task) => t.user_id === USER_ID))
      setClaimed(all.filter((t: Task) => t.claimed_by === USER_ID))
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => { fetchTasks() }, [])
  useEffect(() => {
    const iv = setInterval(fetchTasks, 5000)
    return () => clearInterval(iv)
  }, [])

  const cancelTask = async (taskId: string) => {
    try {
      const res = await fetch(`${API}/marketplace/${taskId}/cancel?user_id=${USER_ID}`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Task Cancelled', description: `$${data.refund} refunded to your balance.` })
        fetchTasks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const submitForReview = async (taskId: string) => {
    const summary = reviewText[taskId] || 'Task completed. Review the generated files in the workspace.'
    try {
      const res = await fetch(`${API}/marketplace/${taskId}/submit-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result_summary: summary }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Submitted for Review', description: 'Poster must approve before payout.' })
        fetchTasks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const approveTask = async (taskId: string) => {
    try {
      const res = await fetch(`${API}/marketplace/${taskId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Approved!', description: `Node paid $${data.node_payout} | Platform fee: $${data.platform_fee}` })
        fetchTasks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const rejectTask = async (taskId: string) => {
    try {
      const res = await fetch(`${API}/marketplace/${taskId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Rejected', description: 'Task is back open for another node.' })
        fetchTasks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const statusConfig: Record<string, { icon: any; color: string; label: string }> = {
    open: { icon: Clock, color: 'bg-blue-500/20 text-blue-400', label: 'Open' },
    claimed: { icon: Loader2, color: 'bg-yellow-500/20 text-yellow-400', label: 'In Progress' },
    pending_review: { icon: Eye, color: 'bg-orange-500/20 text-orange-400', label: 'Pending Review' },
    completed: { icon: CheckCircle2, color: 'bg-green-500/20 text-green-400', label: 'Completed' },
    cancelled: { icon: XCircle, color: 'bg-red-500/20 text-red-400', label: 'Cancelled' },
  }

  const renderTask = (task: Task, isPosted: boolean) => {
    const cfg = statusConfig[task.status] || statusConfig.open
    const Icon = cfg.icon
    return (
      <Card key={task.task_id} className="overflow-hidden">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Badge variant="outline" className={cfg.color}>
                  <Icon className="h-3 w-3 mr-1" /> {cfg.label}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(task.created_at * 1000).toLocaleString()}
                </span>
              </div>
              <p className="text-sm font-medium leading-relaxed">{task.goal}</p>
              {task.claimed_by_name && (
                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                  <Cpu className="h-3 w-3" /> {isPosted ? `Claimed by: ${task.claimed_by_name}` : `Posted by: ${task.user_id}`}
                </p>
              )}
              {task.result_summary && (
                <div className="mt-2 rounded-md bg-muted p-2 text-xs">
                  <p className="text-muted-foreground mb-1">Result:</p>
                  <p className="text-foreground">{task.result_summary}</p>
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0">
              <span className="text-xl font-bold text-green-400">${task.bounty.toFixed(2)}</span>

              {/* Poster actions */}
              {isPosted && task.status === 'open' && (
                <Button size="sm" variant="destructive" onClick={() => cancelTask(task.task_id)}>Cancel</Button>
              )}
              {isPosted && task.status === 'pending_review' && (
                <div className="flex gap-2">
                  <Button size="sm" variant="default" onClick={() => approveTask(task.task_id)} className="gap-1">
                    <ThumbsUp className="h-3.5 w-3.5" /> Approve
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => rejectTask(task.task_id)} className="gap-1">
                    <ThumbsDown className="h-3.5 w-3.5" /> Reject
                  </Button>
                </div>
              )}

              {/* Node actions */}
              {!isPosted && task.status === 'claimed' && (
                <div className="flex flex-col items-end gap-2">
                  <Textarea
                    placeholder="Describe what was completed..."
                    className="w-48 h-16 text-xs"
                    value={reviewText[task.task_id] || ''}
                    onChange={(e) => setReviewText({ ...reviewText, [task.task_id]: e.target.value })}
                  />
                  <Button size="sm" onClick={() => submitForReview(task.task_id)} className="gap-1">
                    <Send className="h-3.5 w-3.5" /> Submit for Review
                  </Button>
                </div>
              )}

              {task.status === 'completed' && (
                <div className="text-right text-xs">
                  <p className="text-green-400">+${task.node_payout?.toFixed(2)}</p>
                  <p className="text-muted-foreground">Fee: ${task.platform_fee?.toFixed(2)}</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">My Tasks</h1>
        <p className="text-muted-foreground">Track bounties, submissions, and approvals.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Posted Tasks */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <ClipboardList className="h-5 w-5" /> Posted Bounties
            <Badge variant="outline">{posted.length}</Badge>
          </h2>
          {posted.length === 0 && (
            <Card className="p-8 text-center">
              <ListChecks className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No bounties posted yet.</p>
            </Card>
          )}
          {posted.map(t => renderTask(t, true))}
        </div>

        {/* Claimed Tasks */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Cpu className="h-5 w-5" /> Claimed Tasks
            <Badge variant="outline">{claimed.length}</Badge>
          </h2>
          {claimed.length === 0 && (
            <Card className="p-8 text-center">
              <Cpu className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No tasks claimed yet. Go to Marketplace!</p>
            </Card>
          )}
          {claimed.map(t => renderTask(t, false))}
        </div>
      </div>
    </div>
  )
}
