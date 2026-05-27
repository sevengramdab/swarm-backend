import { useState, useEffect } from 'react'
import { useToast } from '@/components/ui/toaster'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { DollarSign, Plus, Target, Cpu, TrendingUp, Wallet, Zap, Hammer } from 'lucide-react'

const API = 'http://localhost:8000/billing'
const USER_ID = 'user_001'

interface BountyTask {
  task_id: string
  goal: string
  bounty: number
  complexity: string
  status: 'open' | 'claimed' | 'completed' | 'cancelled'
  claimed_by?: string
  claimed_by_name?: string
  created_at: number
}

interface Account {
  user_id: string
  credits: number
  total_spent: number
  total_earned: number
  tasks_posted: number
  tasks_completed: number
}

export function Marketplace() {
  const { toast } = useToast()
  const [tasks, setTasks] = useState<BountyTask[]>([])
  const [account, setAccount] = useState<Account | null>(null)
  const [pricingTable, setPricingTable] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  // Post form
  const [goal, setGoal] = useState('')
  const [bounty, setBounty] = useState('2.00')
  const [complexity, setComplexity] = useState('medium')
  const [dialogOpen, setDialogOpen] = useState(false)

  // Price estimator
  const [estVram, setEstVram] = useState(8192)
  const [estGpu, setEstGpu] = useState('rtx_3080')
  const [estComplexity, setEstComplexity] = useState('medium')
  const [estimate, setEstimate] = useState<any>(null)

  const fetchData = async () => {
    try {
      const [tasksRes, acctRes, priceRes] = await Promise.all([
        fetch(`${API}/marketplace/tasks?status=open`),
        fetch(`${API}/account/${USER_ID}`),
        fetch(`${API}/pricing-table`),
      ])
      const tasksData = await tasksRes.json()
      const acctData = await acctRes.json()
      const priceData = await priceRes.json()
      setTasks(tasksData.tasks || [])
      setAccount(acctData)
      setPricingTable(priceData.gpus || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchData() }, [])
  useEffect(() => {
    const iv = setInterval(fetchData, 5000)
    return () => clearInterval(iv)
  }, [])

  const postBounty = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/marketplace/post`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, goal, bounty: parseFloat(bounty), complexity }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Bounty Posted!', description: `$${bounty} held in escrow for: ${goal.slice(0, 40)}...` })
        setDialogOpen(false)
        setGoal('')
        setBounty('2.00')
        fetchData()
      } else {
        toast({ title: 'Failed', description: data.detail || 'Could not post bounty', variant: 'destructive' })
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
    setLoading(false)
  }

  const claimTask = async (taskId: string) => {
    try {
      const res = await fetch(`${API}/marketplace/${taskId}/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: 'local_msi', node_name: 'Local MSI GTX 1650' }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Task Claimed!', description: `You claimed a $${data.task.bounty} bounty.` })
        fetchData()
      } else {
        toast({ title: 'Failed', description: data.detail, variant: 'destructive' })
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const getEstimate = async () => {
    try {
      const res = await fetch(`${API}/price-estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vram_mb: estVram, gpu_type: estGpu, complexity: estComplexity }),
      })
      const data = await res.json()
      setEstimate(data)
    } catch (e) {
      console.error(e)
    }
  }

  const complexityColors: Record<string, string> = {
    simple: 'bg-green-500/20 text-green-400 border-green-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    complex: 'bg-red-500/20 text-red-400 border-red-500/30',
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Task Marketplace</h1>
          <p className="text-muted-foreground">Post coding bounties. Node operators earn real money.</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2"><Plus className="h-4 w-4" /> Post Bounty</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Post a Coding Bounty</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">Task Goal</label>
                <Textarea value={goal} onChange={(e) => setGoal(e.target.value)}
                  placeholder="Build a Python script that scrapes Hacker News and sends top stories to Discord..."
                  className="mt-1" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Bounty ($)</label>
                  <div className="relative mt-1">
                    <DollarSign className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input type="number" min="0.50" step="0.50" value={bounty} onChange={(e) => setBounty(e.target.value)}
                      className="pl-8" />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium">Complexity</label>
                  <select value={complexity} onChange={(e) => setComplexity(e.target.value)}
                    className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm">
                    <option value="simple">Simple ($)</option>
                    <option value="medium">Medium ($$)</option>
                    <option value="complex">Complex ($$$)</option>
                  </select>
                </div>
              </div>
              {account && (
                <div className="text-sm text-muted-foreground">
                  Your balance: <span className="font-semibold text-green-400">${account.credits.toFixed(2)}</span>
                </div>
              )}
              <Button onClick={postBounty} disabled={loading || !goal.trim()} className="w-full gap-2">
                <Target className="h-4 w-4" /> {loading ? 'Posting...' : `Post $${bounty} Bounty`}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <Wallet className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-sm text-muted-foreground">Your Balance</p>
              <p className="text-2xl font-bold text-green-400">${account?.credits.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <TrendingUp className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-sm text-muted-foreground">Total Spent</p>
              <p className="text-2xl font-bold">${account?.total_spent.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <DollarSign className="h-8 w-8 text-yellow-400" />
            <div>
              <p className="text-sm text-muted-foreground">Total Earned</p>
              <p className="text-2xl font-bold text-yellow-400">${account?.total_earned.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <Hammer className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-sm text-muted-foreground">Open Bounties</p>
              <p className="text-2xl font-bold">{tasks.length}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Open Bounties */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2"><Target className="h-5 w-5" /> Open Bounties</h2>
          {tasks.length === 0 && (
            <Card className="p-8 text-center">
              <Zap className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No open bounties yet. Be the first to post one!</p>
            </Card>
          )}
          {tasks.map((task) => (
            <Card key={task.task_id} className="overflow-hidden">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className={complexityColors[task.complexity] || ''}>
                        {task.complexity}
                      </Badge>
                      <span className="text-xs text-muted-foreground">{new Date(task.created_at * 1000).toLocaleString()}</span>
                    </div>
                    <p className="text-sm font-medium leading-relaxed">{task.goal}</p>
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <span className="text-2xl font-bold text-green-400">${task.bounty.toFixed(2)}</span>
                    <Button size="sm" onClick={() => claimTask(task.task_id)} className="gap-1">
                      <Cpu className="h-3.5 w-3.5" /> Claim
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Sidebar: Price Calculator */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="h-4 w-4" /> Price Calculator</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground">GPU Type</label>
                <select value={estGpu} onChange={(e) => setEstGpu(e.target.value)} className="mt-1 flex h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm">
                  {pricingTable.map((g: any) => (
                    <option key={g.gpu} value={g.gpu}>{g.gpu.replace(/_/g, ' ').toUpperCase()} ({g.multiplier}x)</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">VRAM (MB)</label>
                <Input type="number" value={estVram} onChange={(e) => setEstVram(Number(e.target.value))} className="mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Complexity</label>
                <select value={estComplexity} onChange={(e) => setEstComplexity(e.target.value)} className="mt-1 flex h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm">
                  <option value="simple">Simple (1.0x)</option>
                  <option value="medium">Medium (1.5x)</option>
                  <option value="complex">Complex (3.0x)</option>
                </select>
              </div>
              <Button onClick={getEstimate} size="sm" className="w-full">Calculate</Button>
              {estimate && (
                <div className="rounded-md bg-muted p-3 text-sm space-y-1">
                  <div className="flex justify-between"><span>Base cost</span><span>${estimate.base_cost}</span></div>
                  <div className="flex justify-between"><span>VRAM cost</span><span>${estimate.vram_cost}</span></div>
                  <div className="flex justify-between"><span>GPU ({estimate.gpu_multiplier}x)</span><span></span></div>
                  <div className="flex justify-between"><span>Complexity ({estimate.complexity_multiplier}x)</span><span></span></div>
                  <div className="border-t pt-1 flex justify-between font-bold text-green-400">
                    <span>Total</span><span>${estimate.total}</span>
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Node earns</span><span>${estimate.node_earnings}</span>
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Platform fee (15%)</span><span>${estimate.platform_fee}</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">GPU Pricing Tiers</CardTitle></CardHeader>
            <CardContent className="space-y-2 max-h-64 overflow-y-auto">
              {pricingTable.slice(0, 8).map((g: any) => (
                <div key={g.gpu} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{g.gpu.replace(/_/g, ' ').toUpperCase()}</span>
                  <span className="font-mono">${g.example_8gb_medium}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
