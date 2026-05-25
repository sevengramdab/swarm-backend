import { useState } from 'react'
import { useSettings } from '@/hooks/useSettings'
import { useToast } from '@/components/ui/toaster'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RotateCw } from 'lucide-react'

const TABS = [
  { id: 'api', label: 'API', keys: ['api_key', 'base_url'] },
  { id: 'ollama', label: 'Ollama', keys: ['ollama_host', 'ollama_port', 'ollama_timeout'] },
  { id: 'swarm', label: 'Swarm', keys: ['swarm_max_agents', 'swarm_default_model', 'swarm_auto_spawn'] },
  { id: 'routing', label: 'Routing', keys: ['routing_mode', 'routing_threshold', 'routing_fallback_enabled'] },
  { id: 'tiers', label: 'Tiers', keys: ['tier_premium', 'tier_standard', 'tier_basic'] },
  { id: 'ui', label: 'UI', keys: ['ui_theme', 'ui_sidebar_collapsed'] },
  { id: 'telemetry', label: 'Telemetry', keys: ['telemetry_enabled', 'telemetry_endpoint'] },
  { id: 'discovery', label: 'Discovery', keys: ['discovery_enabled', 'discovery_interval'] },
  { id: 'security', label: 'Security', keys: ['security_auth_enabled', 'security_api_key_required'] },
  { id: 'advanced', label: 'Advanced', keys: ['advanced_debug', 'advanced_log_level', 'advanced_max_retries'] },
]

export function Settings() {
  const { settings, isLoading, update, save, reset, isSaving, isResetting } = useSettings()
  const { toast } = useToast()
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    try {
      await save()
      setSaved(true)
      toast({ title: 'Settings saved' })
      setTimeout(() => setSaved(false), 2000)
    } catch {
      toast({ title: 'Save failed', variant: 'destructive' })
    }
  }

  const handleReset = async () => {
    try {
      await reset()
      toast({ title: 'Settings reset to defaults' })
    } catch {
      toast({ title: 'Reset failed', variant: 'destructive' })
    }
  }

  if (isLoading) {
    return <div className="p-6">Loading settings...</div>
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Settings</h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleReset} disabled={isResetting}>
            <RotateCw className="mr-2 h-4 w-4" />
            Reset
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="api">
        <TabsList className="flex flex-wrap gap-1">
          {TABS.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id} className="text-xs">
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((tab) => (
          <TabsContent key={tab.id} value={tab.id}>
            <Card>
              <CardHeader>
                <CardTitle>{tab.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {tab.keys.map((key) => (
                  <div key={key} className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium capitalize">{key.replace(/_/g, ' ')}</label>
                    <Input
                      value={String(settings[key] ?? '')}
                      onChange={(e) => update(key, e.target.value)}
                      placeholder={`Enter ${key.replace(/_/g, ' ')}`}
                    />
                  </div>
                ))}
                {Object.entries(settings)
                  .filter(([k]) => k.startsWith(`${tab.id}_`) && !tab.keys.includes(k))
                  .map(([k, v]) => (
                    <div key={k} className="flex flex-col gap-1.5">
                      <label className="text-sm font-medium capitalize">{k.replace(/_/g, ' ')}</label>
                      <Input value={String(v ?? '')} onChange={(e) => update(k, e.target.value)} />
                    </div>
                  ))}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
