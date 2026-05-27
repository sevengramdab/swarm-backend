import { useState, useEffect } from 'react'
import { useToast } from '@/components/ui/toaster'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { DollarSign, TrendingUp, PiggyBank, Users, Trophy, ArrowUpRight, Activity, CreditCard } from 'lucide-react'

const API = 'http://localhost:8000/billing'
const USER_ID = 'user_001'

interface PlatformRevenue {
  platform_revenue: number
  total_tasks: number
  completed_tasks: number
  open_bounties: number
  total_bounty_volume: number
  total_paid_to_nodes: number
  platform_fee_pct: number
  recent_transactions: any[]
}

interface EarningsData {
  user_id: string
  total_earned: number
  total_spent: number
  current_balance: number
  tasks_completed: number
  tasks_posted: number
  completed_tasks: any[]
}

interface LeaderboardEntry {
  user_id: string
  total_earned: number
  tasks_completed: number
}

export function Earnings() {
  const { toast } = useToast()
  const [platform, setPlatform] = useState<PlatformRevenue | null>(null)
  const [personal, setPersonal] = useState<EarningsData | null>(null)
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [depositAmount, setDepositAmount] = useState('10')

  const fetchData = async () => {
    try {
      const [platRes, earnRes, leadRes] = await Promise.all([
        fetch(`${API}/platform/revenue`),
        fetch(`${API}/earnings/${USER_ID}`),
        fetch(`${API}/leaderboard`),
      ])
      setPlatform(await platRes.json())
      setPersonal(await earnRes.json())
      const leadData = await leadRes.json()
      setLeaderboard(leadData.top_earners || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchData() }, [])
  useEffect(() => {
    const iv = setInterval(fetchData, 5000)
    return () => clearInterval(iv)
  }, [])

  const deposit = async () => {
    try {
      const res = await fetch(`${API}/account/${USER_ID}/deposit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, amount: parseFloat(depositAmount), payment_method: 'stripe' }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Credits Added!', description: `+$${depositAmount} added to your balance.` })
        fetchData()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const withdraw = async () => {
    if (!personal || personal.total_earned <= 0) {
      toast({ title: 'Nothing to withdraw', description: 'Complete tasks to earn money first.', variant: 'destructive' })
      return
    }
    try {
      const res = await fetch(`${API}/account/${USER_ID}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, amount: personal.total_earned, destination: 'stripe_connect' }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Withdrawal Initiated!', description: `$${personal.total_earned.toFixed(2)} sent to your account.` })
        fetchData()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Earnings Dashboard</h1>
        <p className="text-muted-foreground">Track revenue, payouts, and platform growth.</p>
      </div>

      {/* Platform-Wide Revenue */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-gradient-to-br from-green-950/40 to-green-900/20 border-green-500/20">
          <CardContent className="flex items-center gap-4 p-4">
            <PiggyBank className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-sm text-muted-foreground">Platform Revenue</p>
              <p className="text-2xl font-bold text-green-400">${platform?.platform_revenue.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <DollarSign className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-sm text-muted-foreground">Bounty Volume</p>
              <p className="text-2xl font-bold">${platform?.total_bounty_volume.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <Users className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-sm text-muted-foreground">Paid to Nodes</p>
              <p className="text-2xl font-bold text-purple-400">${platform?.total_paid_to_nodes.toFixed(2) || '0.00'}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <Activity className="h-8 w-8 text-orange-400" />
            <div>
              <p className="text-sm text-muted-foreground">Completed Tasks</p>
              <p className="text-2xl font-bold">{platform?.completed_tasks || 0} / {platform?.total_tasks || 0}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Personal + Leaderboard */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Your Account */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2"><CreditCard className="h-5 w-5" /> Your Account</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Balance</p>
                <p className="text-3xl font-bold text-green-400">${personal?.current_balance.toFixed(2) || '0.00'}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Total Earned</p>
                <p className="text-3xl font-bold text-yellow-400">${personal?.total_earned.toFixed(2) || '0.00'}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Total Spent</p>
                <p className="text-3xl font-bold">${personal?.total_spent.toFixed(2) || '0.00'}</p>
              </CardContent>
            </Card>
          </div>

          {/* Deposit / Withdraw */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Manage Funds</CardTitle></CardHeader>
            <CardContent className="flex items-center gap-3">
              <input type="number" value={depositAmount} onChange={(e) => setDepositAmount(e.target.value)}
                className="h-10 w-32 rounded-md border border-input bg-background px-3 text-sm" min="1" step="5" />
              <Button onClick={deposit} className="gap-2"><ArrowUpRight className="h-4 w-4" /> Add Credits</Button>
              <Button onClick={withdraw} variant="outline" className="gap-2">
                <TrendingUp className="h-4 w-4" /> Cash Out (${personal?.total_earned.toFixed(2) || '0.00'})
              </Button>
            </CardContent>
          </Card>

          {/* Completed Tasks */}
          {personal && personal.completed_tasks.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-sm">Your Completed Tasks</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {personal.completed_tasks.map((task: any) => (
                  <div key={task.task_id} className="flex items-center justify-between rounded-md bg-muted p-3 text-sm">
                    <div className="flex-1 min-w-0 mr-4">
                      <p className="truncate font-medium">{task.goal}</p>
                      <p className="text-xs text-muted-foreground">{new Date(task.completed_at * 1000).toLocaleString()}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-bold text-green-400">+${task.node_payout?.toFixed(2) || task.bounty.toFixed(2)}</p>
                      <p className="text-xs text-muted-foreground">Fee: ${task.platform_fee?.toFixed(2) || '0.00'}</p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Leaderboard */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold flex items-center gap-2"><Trophy className="h-5 w-5 text-yellow-400" /> Top Earners</h2>
          <Card>
            <CardContent className="p-4 space-y-3">
              {leaderboard.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No earnings yet. Start completing tasks!</p>
              )}
              {leaderboard.map((entry, idx) => (
                <div key={entry.user_id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge variant={idx < 3 ? 'default' : 'outline'} className="w-7 justify-center">
                      {idx + 1}
                    </Badge>
                    <span className="text-sm font-medium">{entry.user_id}</span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-green-400">${entry.total_earned.toFixed(2)}</p>
                    <p className="text-xs text-muted-foreground">{entry.tasks_completed} tasks</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Recent Transactions */}
          {platform && platform.recent_transactions.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-sm">Recent Transactions</CardTitle></CardHeader>
              <CardContent className="max-h-64 overflow-y-auto space-y-2">
                {platform.recent_transactions.map((tx: any) => (
                  <div key={tx.tx_id} className="flex items-center justify-between text-sm">
                    <div>
                      <Badge variant="outline" className="text-xs capitalize">{tx.type.replace(/_/g, ' ')}</Badge>
                      <p className="text-xs text-muted-foreground">{tx.user_id}</p>
                    </div>
                    <span className={`font-mono font-bold ${tx.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {tx.amount >= 0 ? '+' : ''}${Math.abs(tx.amount).toFixed(2)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
