/**
 * SIMPLESWARM -- Autonomous Computer Control + Test Dashboard
 * AGENT-018 (Autonomous Tester)
 * Full mouse, keyboard, screenshot, and shell control via MassAgentOrchestrator.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Play, Square, RotateCcw, Camera, MousePointer, Keyboard,
  Terminal, Monitor, CheckCircle2, XCircle, Loader2, Bot,
  ChevronDown, ChevronUp, Image as ImageIcon, Activity
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'


// ─── TYPES ───
interface PhaseResult {
  phase: string
  status: string
  checks: { name: string; status: string; notes: string }[]
  duration_sec: number
}

interface TestStatus {
  running: boolean
  phases_completed: number
  phases_total: number
  elapsed_sec: number
  latest_results: PhaseResult[]
}

interface ScreenshotData {
  image_base64: string
  width: number
  height: number
}

// ─── API HELPERS ───
const API_BASE = '/simpleswarm'

async function apiPost(path: string, body?: object) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  return res.json()
}

async function apiGet(path: string) {
  const res = await fetch(`${API_BASE}${path}`)
  return res.json()
}

// ─── COMPONENT ───
export function SimpleSwarm() {
  const [status, setStatus] = useState<TestStatus | null>(null)
  const [results, setResults] = useState<PhaseResult[]>([])
  const [screenshot, setScreenshot] = useState<ScreenshotData | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [spawnCount, setSpawnCount] = useState(4)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Poll status every 2 seconds when running
  const pollStatus = useCallback(async () => {
    try {
      const s = await apiGet('/test/status')
      setStatus(s)
      setIsRunning(s.running)
      if (!s.running && isRunning) {
        // Just finished — fetch full results
        const r = await apiGet('/test/results')
        setResults(r.results || [])
      }
    } catch (e) {
      // ignore polling errors
    }
  }, [isRunning])

  useEffect(() => {
    pollStatus()
    pollRef.current = setInterval(pollStatus, 2000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [pollStatus])

  // ─── ACTIONS ───

  const startTest = async () => {
    setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] Starting test...`])
    setResults([])
    await apiPost('/test/start', { parallel: true })
    setIsRunning(true)
    pollStatus()
  }

  const stopTest = async () => {
    await apiPost('/test/stop')
    setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] Stop requested`])
    setIsRunning(false)
  }

  const takeScreenshot = async () => {
    setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] Capturing screenshot...`])
    try {
      const data = await apiGet('/screenshot')
      if (data.image_base64) {
        setScreenshot(data)
        setLog(prev => [...prev, `Screenshot captured: ${data.width}x${data.height}`])
      }
    } catch (e) {
      setLog(prev => [...prev, `Screenshot failed: ${e}`])
    }
  }

  const spawnAgents = async () => {
    setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] Spawning ${spawnCount} agents...`])
    try {
      const res = await apiPost('/agents/spawn', { count: spawnCount, mode: 'test' })
      setLog(prev => [...prev, `Spawned: ${res.spawned?.length || 0} agents`])
    } catch (e) {
      setLog(prev => [...prev, `Spawn failed: ${e}`])
    }
  }

  const sendAction = async (action: string, params: object) => {
    setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] Action: ${action}`])
    try {
      const res = await apiPost('/action', { action, params })
      setLog(prev => [...prev, `Result: ${res.success ? 'OK' : 'FAIL'} — ${res.message}`])
    } catch (e) {
      setLog(prev => [...prev, `Action failed: ${e}`])
    }
  }

  // ─── RENDER ───

  const progressPct = status
    ? Math.round((status.phases_completed / status.phases_total) * 100)
    : 0

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">SimpleSwarm</h1>
            <p className="text-sm text-muted-foreground">
              Autonomous Computer Control + Mass Agent Test Swarm
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && (
            <Badge variant="secondary" className="animate-pulse">
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Testing...
            </Badge>
          )}
          <Button onClick={startTest} disabled={isRunning} size="sm">
            <Play className="mr-1 h-4 w-4" /> Start Test
          </Button>
          <Button onClick={stopTest} disabled={!isRunning} variant="destructive" size="sm">
            <Square className="mr-1 h-4 w-4" /> Stop
          </Button>
          <Button onClick={takeScreenshot} variant="outline" size="sm">
            <Camera className="mr-1 h-4 w-4" /> Screenshot
          </Button>
        </div>
      </div>

      {/* Progress */}
      {status && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Test Progress</span>
              <span className="text-sm text-muted-foreground">
                {status.phases_completed} / {status.phases_total} phases — {status.elapsed_sec}s elapsed
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Phase Results */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" /> Phase Results
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {results.length === 0 && !isRunning && (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No test results yet. Click Start Test to begin.
                </p>
              )}
              {results.map((r) => {
                const isExpanded = expandedPhase === r.phase
                const passCount = r.checks.filter(c => c.status === 'PASS').length
                const totalCount = r.checks.length
                const isPass = r.status === 'PASS'
                return (
                  <div
                    key={r.phase}
                    className={`rounded-md border p-3 cursor-pointer transition-colors ${
                      isPass ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'
                    }`}
                    onClick={() => setExpandedPhase(isExpanded ? null : r.phase)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {isPass ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                        <span className="font-medium text-sm">{r.phase}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={isPass ? 'default' : 'destructive'} className="text-xs">
                          {passCount}/{totalCount}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{r.duration_sec}s</span>
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="mt-2 space-y-1 pl-6">
                        {r.checks.map((c) => (
                          <div key={c.name} className="flex items-start gap-2 text-xs">
                            {c.status === 'PASS' ? (
                              <CheckCircle2 className="h-3 w-3 text-green-500 mt-0.5 shrink-0" />
                            ) : (
                              <XCircle className="h-3 w-3 text-red-500 mt-0.5 shrink-0" />
                            )}
                            <div>
                              <span className={c.status === 'PASS' ? 'text-green-400' : 'text-red-400'}>
                                {c.name}
                              </span>
                              {c.notes && <p className="text-muted-foreground">{c.notes}</p>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {isRunning && results.length === 0 && (
                <div className="flex items-center justify-center py-8 gap-2 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Running tests...
                </div>
              )}
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <MousePointer className="h-4 w-4" /> Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Button variant="outline" size="sm" onClick={() => sendAction('screenshot', {})}>
                <Camera className="mr-1 h-3 w-3" /> Screenshot
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('click_rel', { x_pct: 0.5, y_pct: 0.5 })}>
                <MousePointer className="mr-1 h-3 w-3" /> Center Click
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('type_text', { text: 'Hello SimpleSwarm' })}>
                <Keyboard className="mr-1 h-3 w-3" /> Type Text
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('hotkey', { keys: ['ctrl', 'c'] })}>
                <Keyboard className="mr-1 h-3 w-3" /> Ctrl+C
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('shell', { command: 'echo %COMPUTERNAME%' })}>
                <Terminal className="mr-1 h-3 w-3" /> Shell
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('open_browser', { url: 'http://localhost:8000/orbstudio' })}>
                <Monitor className="mr-1 h-3 w-3" /> Open Dashboard
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('get_screen_size', {})}>
                <Monitor className="mr-1 h-3 w-3" /> Screen Size
              </Button>
              <Button variant="outline" size="sm" onClick={() => sendAction('kill_process', { name: 'python.exe' })}>
                <Square className="mr-1 h-3 w-3" /> Kill Python
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right column: Screenshot + Log + Spawn */}
        <div className="space-y-4">
          {/* Screenshot Viewer */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ImageIcon className="h-4 w-4" /> Live Screenshot
              </CardTitle>
            </CardHeader>
            <CardContent>
              {screenshot ? (
                <img
                  src={`data:image/png;base64,${screenshot.image_base64}`}
                  alt="Desktop screenshot"
                  className="rounded-md border w-full"
                />
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground border rounded-md border-dashed">
                  <Camera className="h-8 w-8 mb-2 opacity-50" />
                  <p className="text-sm">Click Screenshot to capture</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Spawn Agents */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" /> Spawn Agents
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={spawnCount}
                  onChange={(e) => setSpawnCount(Number(e.target.value))}
                  className="w-16 rounded-md border bg-background px-2 py-1 text-sm"
                />
                <Button onClick={spawnAgents} size="sm" variant="secondary">
                  <Bot className="mr-1 h-4 w-4" /> Spawn {spawnCount}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Spawns MassAgent workers with computer control capability.
              </p>
            </CardContent>
          </Card>

          {/* Action Log */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Terminal className="h-4 w-4" /> Action Log
              </CardTitle>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setLog([])}>
                <RotateCcw className="h-3 w-3" />
              </Button>
            </CardHeader>
            <CardContent>
              <div className="h-48 overflow-y-auto rounded-md border bg-black/30 p-2 font-mono text-xs space-y-1">
                {log.length === 0 && (
                  <span className="text-muted-foreground">No actions yet...</span>
                )}
                {log.map((entry, i) => (
                  <div key={i} className="text-green-400">{entry}</div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
