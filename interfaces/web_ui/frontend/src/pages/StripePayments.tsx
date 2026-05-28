import { useState, useEffect } from 'react'
import { useToast } from '@/components/ui/toaster'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CreditCard, Zap, DollarSign, ExternalLink, AlertTriangle, CheckCircle2 } from 'lucide-react'

const API = 'http://localhost:8000/stripe'
const USER_ID = 'user_001'

export function StripePayments() {
  const { toast } = useToast()
  const [config, setConfig] = useState<{ enabled: boolean; publishable_key: string | null; mode: string | null } | null>(null)
  const [depositAmount, setDepositAmount] = useState('10')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch(`${API}/config`).then(r => r.json()).then(setConfig).catch(console.error)
  }, [])

  const createCheckout = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/checkout/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, amount: parseFloat(depositAmount) }),
      })
      const data = await res.json()
      if (data.success && data.checkout_url) {
        window.location.href = data.checkout_url
      } else {
        toast({ title: 'Checkout Failed', description: data.detail || 'Could not create session', variant: 'destructive' })
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
    setLoading(false)
  }

  const onboardConnect = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/connect/onboard`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, email: 'node@example.com' }),
      })
      const data = await res.json()
      if (data.success && data.onboarding_url) {
        window.open(data.onboarding_url, '_blank')
      } else {
        toast({ title: 'Onboarding Failed', description: data.detail || 'Could not create Connect account', variant: 'destructive' })
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
    setLoading(false)
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Payments</h1>
        <p className="text-muted-foreground">Buy credits with Stripe. Node operators get paid via Stripe Connect.</p>
      </div>

      {/* Status */}
      <Card>
        <CardContent className="flex items-center gap-4 p-4">
          {config?.enabled ? (
            <>
              <CheckCircle2 className="h-8 w-8 text-green-400" />
              <div>
                <p className="text-sm font-medium">Stripe {config.mode?.toUpperCase()} Mode</p>
                <p className="text-xs text-muted-foreground">Payments are live and ready.</p>
              </div>
              <Badge variant="default" className="ml-auto">Active</Badge>
            </>
          ) : (
            <>
              <AlertTriangle className="h-8 w-8 text-yellow-400" />
              <div>
                <p className="text-sm font-medium">Stripe Not Configured</p>
                <p className="text-xs text-muted-foreground">Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY env vars.</p>
              </div>
              <Badge variant="secondary" className="ml-auto">Demo Mode</Badge>
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Buy Credits */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" /> Buy Credits</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">Add credits to your account using a credit card. 1 credit = $1 USD.</p>
            <div className="flex items-center gap-3">
              <DollarSign className="h-5 w-5 text-muted-foreground" />
              <Input type="number" min="5" max="1000" step="5" value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)} className="w-32" />
              <Button onClick={createCheckout} disabled={loading || !config?.enabled} className="gap-2">
                <Zap className="h-4 w-4" /> {loading ? 'Loading...' : `Pay $${depositAmount}`}
              </Button>
            </div>
            {!config?.enabled && (
              <p className="text-xs text-yellow-400">Payments are in demo mode. Credits can still be added manually via the Earnings page.</p>
            )}
          </CardContent>
        </Card>

        {/* Node Operator Payouts */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ExternalLink className="h-5 w-5" /> Node Operator Setup</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">Connect your Stripe account to receive automatic payouts when tasks are approved.</p>
            <Button onClick={onboardConnect} disabled={loading || !config?.enabled} variant="outline" className="gap-2">
              <ExternalLink className="h-4 w-4" /> Connect Stripe Account
            </Button>
            {!config?.enabled && (
              <p className="text-xs text-yellow-400">Connect onboarding requires Stripe keys to be configured.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
