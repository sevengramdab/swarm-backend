import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Cpu, DollarSign, TrendingUp, Activity, Zap, CheckCircle2, Clock, BarChart3 } from 'lucide-react'

const BILLING_API = 'http://localhost:8000/billing'
const MESH_API = 'http://localhost:8000/mesh'
const NODE_ID = 'shadow_pc'
const USER_ID = 'shadow_pc'

interface Task {
  task_id: string
  goal: string
  bounty: number
  status: string
  complexity: string
  claimed_by?: string
  claimed_at?: number
  completed_at?: number
  node_payout?: number
  platform_fee?: number
  created_at: number
}

export function NodeDashboard() {
  const [earnings, setEarnings] = useState<any>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [topology, setTopology] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [earnRes, tasksRes, topoRes] = await Promise.all([
        fetch(`${BILLING_API}/earnings/${USER_ID}`),
        fetch(`${BILLING_API}/marketplace/tasks`),
        fetch(`${MESH_API}/topology`),
      ])
      const earnData = await earnRes.json()
      const tasksData = await tasksRes.json()
      const topoData = await topoRes.json()

      setEarnings(earnData)
      setTasks((tasksData.tasks || []).filter((t: Task) => t.claimed_by === NODE_ID))
      setTopology(topoData)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])
  useEffect(() => {
    const iv = setInterval(fetchData, 10000)
    return () => clearInterval(iv)
  }, [])

  const completedTasks = tasks.filter(t => t.status === 'completed')
  const activeTasks = tasks.filter(t => t.status === 'claimed')
  const pendingReview = tasks.filter(t => t.status === 'pending_review')

  const todayEarnings = completedTasks
    .filter(t => t.completed_at && (Date.now() / 1000 - t.completed_at) < 86400)
    .reduce((sum, t) => sum + (t.node_payout || 0), 0)

  const weekEarnings = completedTasks
    .filter(t => t.completed_at && (Date.now() / 1000 - t.completed_at) < 604800)
    .reduce((sum, t) => sum + (t.node_payout || 0), 0)

  const nodeInfo = topology?.nodes?.find((n: any) => n.node_id === NODE_ID)

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Node Operator Dashboard</h1>
          <p className="text-muted-foreground">{NODE_ID} — RTX 3080, 10GB VRAM</p>
        </div>
        <Badge variant={nodeInfo?.status === 'online' ? 'default' : 'secondary'} className="gap-1">
          <Activity className="h-3 w-3" /> {nodeInfo?.status === 'online' ? 'Online' : 'Offline'}
        </Badge>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-gradient-to-br from-green-950/40 to-green-900/20 border-green-500/20">
          <CardContent className="flex items-center gap-4 p-4">
            <DollarSign className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-sm text-muted-foreground">Total Earned</p>
              <p className="text-2xl font-bold text-green-400">${earnings?.total_earned?.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <TrendingUp className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-sm text-muted-foreground">This Week</p>
              <p className="text-2xl font-bold">${weekEarnings.toFixed(2)}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <Zap className="h-8 w-8 text-yellow-400" />
            <div>
              <p className="text-sm text-muted-foreground">Today</p>
              <p className="text-2xl font-bold">${todayEarnings.toFixed(2)}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <CheckCircle2 className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-sm text-muted-foreground">Tasks Completed</p>
              <p className="text-2xl font-bold">{completedTasks.length}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active Work */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2"><Cpu className="h-5 w-5" /> Your Tasks</h2>

          {activeTasks.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-yellow-400 mb-2 flex items-center gap-2"><Clock className="h-4 w-4" /> In Progress</h3>
              {activeTasks.map(task => (
                <Card key={task.task_id} className="mb-2">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">{task.goal}</p>
                        <p className="text-xs text-muted-foreground">Bounty: ${task.bounty.toFixed(2)}</p>
                      </div>
                      <Badge variant="outline" className="bg-yellow-500/20 text-yellow-400">In Progress</Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {pendingReview.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-orange-400 mb-2 flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Pending Review</h3>
              {pendingReview.map(task => (
                <Card key={task.task_id} className="mb-2">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">{task.goal}</p>
                        <p className="text-xs text-muted-foreground">Waiting for poster approval</p>
                      </div>
                      <Badge variant="outline" className="bg-orange-500/20 text-orange-400">Review</Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {completedTasks.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-green-400 mb-2 flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Completed</h3>
              {completedTasks.map(task => (
                <Card key={task.task_id} className="mb-2">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">{task.goal}</p>
                        <p className="text-xs text-muted-foreground">
                          {task.completed_at ? new Date(task.completed_at * 1000).toLocaleDateString() : ''}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-bold text-green-400">+${task.node_payout?.toFixed(2)}</p>
                        <p className="text-xs text-muted-foreground">Fee: ${task.platform_fee?.toFixed(2)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {tasks.length === 0 && (
            <Card className="p-8 text-center">
              <Cpu className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No tasks yet. Go to Marketplace to claim bounties!</p>
            </Card>
          )}
        </div>

        {/* GPU Stats */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2"><Cpu className="h-5 w-5" /> GPU Stats</h2>
          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">GPU</span>
                <span className="font-medium">RTX 3080</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">VRAM</span>
                <span className="font-medium">10240 MB</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Status</span>
                <span className="font-medium">{nodeInfo?.status === 'online' ? 'Online' : 'Offline'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Latency</span>
                <span className="font-medium">{nodeInfo?.latency_ms === 9999 ? 'N/A' : `${nodeInfo?.latency_ms}ms`}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">Performance</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Avg Bounty</span>
                <span className="font-medium">
                  ${completedTasks.length > 0 ? (completedTasks.reduce((s, t) => s + t.bounty, 0) / completedTasks.length).toFixed(2) : '0.00'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Success Rate</span>
                <span className="font-medium text-green-400">{completedTasks.length > 0 ? '100%' : 'N/A'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Platform Fees Paid</span>
                <span className="font-medium">
                  ${completedTasks.reduce((s, t) => s + (t.platform_fee || 0), 0).toFixed(2)}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
