import { useState, useEffect } from 'react'
import { useToast } from '@/components/ui/toaster'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Bell, Plus, Trash2, Send, CheckCircle2, Webhook, MessageSquare, Hash } from 'lucide-react'

const API = 'http://localhost:8000/notifications'
const USER_ID = 'user_001'

interface WebhookSub {
  webhook_id: string
  name: string
  url: string
  webhook_type: string
  events: string
  active: number
  created_at: number
}

export function Webhooks() {
  const { toast } = useToast()
  const [webhooks, setWebhooks] = useState<WebhookSub[]>([])
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [wtype, setWtype] = useState('discord')
  const [events, setEvents] = useState('all')

  const fetchWebhooks = async () => {
    try {
      const res = await fetch(`${API}/webhooks/${USER_ID}`)
      const data = await res.json()
      setWebhooks(data.webhooks || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchWebhooks() }, [])

  const createWebhook = async () => {
    try {
      const res = await fetch(`${API}/webhooks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, name, url, webhook_type: wtype, events }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Webhook Added', description: `${name} is now listening for events.` })
        setName('')
        setUrl('')
        fetchWebhooks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const deleteWebhook = async (id: string) => {
    try {
      const res = await fetch(`${API}/webhooks/${id}?user_id=${USER_ID}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Webhook Deleted' })
        fetchWebhooks()
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const testWebhook = async (url: string, wtype: string) => {
    try {
      const res = await fetch(`${API}/webhooks/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, webhook_type: wtype }),
      })
      const data = await res.json()
      if (data.success) {
        toast({ title: 'Test Sent!', description: 'Check your channel for the test message.' })
      } else {
        toast({ title: 'Test Failed', description: 'Webhook returned an error.', variant: 'destructive' })
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
  }

  const typeIcons: Record<string, any> = {
    discord: MessageSquare,
    slack: Hash,
    generic: Webhook,
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Webhook Notifications</h1>
        <p className="text-muted-foreground">Get notified on Discord, Slack, or any HTTP endpoint when tasks move.</p>
      </div>

      {/* Add webhook */}
      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Plus className="h-4 w-4" /> Add Webhook</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input placeholder="Name (e.g. My Discord)" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={wtype} onChange={(e) => setWtype(e.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm">
              <option value="discord">Discord</option>
              <option value="slack">Slack</option>
              <option value="generic">Generic HTTP</option>
            </select>
          </div>
          <Input placeholder="Webhook URL" value={url} onChange={(e) => setUrl(e.target.value)} />
          <div>
            <label className="text-xs text-muted-foreground">Events to notify</label>
            <select value={events} onChange={(e) => setEvents(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
              <option value="all">All Events</option>
              <option value="claimed">Task Claimed</option>
              <option value="submit_review">Submitted for Review</option>
              <option value="approved,rejected">Approved / Rejected</option>
              <option value="payout">Payout Sent</option>
            </select>
          </div>
          <Button onClick={createWebhook} disabled={!name.trim() || !url.trim()} className="gap-2">
            <Bell className="h-4 w-4" /> Add Webhook
          </Button>
        </CardContent>
      </Card>

      {/* List webhooks */}
      <div className="space-y-3">
        {webhooks.length === 0 && (
          <Card className="p-8 text-center">
            <Webhook className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
            <p className="text-muted-foreground">No webhooks configured. Add one to get notified.</p>
          </Card>
        )}
        {webhooks.map((wh) => {
          const Icon = typeIcons[wh.webhook_type] || Webhook
          return (
            <Card key={wh.webhook_id}>
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{wh.name}</p>
                    <p className="text-xs text-muted-foreground truncate max-w-xs">{wh.url}</p>
                    <div className="flex gap-2 mt-1">
                      <Badge variant="outline" className="text-xs capitalize">{wh.webhook_type}</Badge>
                      <Badge variant={wh.active ? 'default' : 'secondary'} className="text-xs">
                        {wh.active ? 'Active' : 'Paused'}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => testWebhook(wh.url, wh.webhook_type)} className="gap-1">
                    <Send className="h-3.5 w-3.5" /> Test
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteWebhook(wh.webhook_id)} className="text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
