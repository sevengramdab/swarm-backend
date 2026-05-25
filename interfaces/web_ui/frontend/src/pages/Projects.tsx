/**
 * PROJECTS — SwarmCoder Project Hub
 * Discovers, tests, and launches all generated apps.
 * Integrated into SimpleSwarm dashboard.
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Play, Square, RefreshCw, Camera, Terminal, CheckCircle, XCircle,
  Loader2, Monitor, Rocket, FileCode, Activity, Image as ImageIcon
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'

// ─── TYPES ───
interface Project {
  name: string
  file: string
  type: string
  lines: number
  size_kb: number
  created: string
  running: boolean
  port?: number
}

interface TestResult {
  test: string
  passed: boolean | null
  error: string | null
}

interface TestReport {
  name: string
  type: string
  results: TestResult[]
  passed: number
  failed: number
  total: number
}

// ─── COMPONENT ───
export function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [testReports, setTestReports] = useState<Record<string, TestReport>>({})
  const [runningApps, setRunningApps] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [shellOutput, setShellOutput] = useState('')
  const [shellCommand, setShellCommand] = useState('')
  const [log, setLog] = useState<string[]>([])

  const addLog = (msg: string) => setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])

  const fetchProjects = useCallback(async () => {
    const res = await api.get<{ projects: Project[] }>('/projects/')
    if (res?.projects) setProjects(res.projects)
    const running = await api.get<{ running: Record<string, any> }>('/projects/running')
    if (running?.running) setRunningApps(running.running)
  }, [])

  useEffect(() => {
    fetchProjects()
    const iv = setInterval(fetchProjects, 3000)
    return () => clearInterval(iv)
  }, [fetchProjects])

  const testProject = async (name: string) => {
    setLoading(prev => ({ ...prev, [name]: true }))
    addLog(`Testing ${name}...`)
    const res = await api.get<TestReport>(`/projects/${name}/test`)
    if (res) {
      setTestReports(prev => ({ ...prev, [name]: res }))
      addLog(`${name}: ${res.passed}/${res.total} tests passed`)
    }
    setLoading(prev => ({ ...prev, [name]: false }))
  }

  const launchProject = async (name: string) => {
    setLoading(prev => ({ ...prev, [name]: true }))
    addLog(`Launching ${name}...`)
    const res = await api.post<{ success: boolean; port?: number; url?: string; message: string }>(`/projects/${name}/launch`, {})
    if (res?.success) {
      addLog(`${name} running on port ${res.port} → ${res.url}`)
      await fetchProjects()
    } else {
      addLog(`Launch failed: ${res?.message}`)
    }
    setLoading(prev => ({ ...prev, [name]: false }))
  }

  const stopProject = async (name: string) => {
    addLog(`Stopping ${name}...`)
    await api.post(`/projects/${name}/stop`, {})
    await fetchProjects()
    addLog(`${name} stopped`)
  }

  const takeScreenshot = async () => {
    addLog('Capturing desktop screenshot...')
    const res = await api.get<{ image_base64?: string; width?: number; height?: number }>('/simpleswarm/screenshot')
    if (res?.image_base64) {
      setScreenshot(res.image_base64)
      addLog(`Screenshot captured: ${res.width}x${res.height}`)
    } else {
      addLog('Screenshot failed')
    }
  }

  const runShell = async () => {
    if (!shellCommand.trim()) return
    addLog(`Shell: ${shellCommand}`)
    const res = await api.post<{ success: boolean; data?: { stdout?: string; stderr?: string } }>('/simpleswarm/action', {
      action: 'shell', params: { command: shellCommand, timeout: 30 }
    })
    const out = res?.data?.stdout || res?.data?.stderr || 'No output'
    setShellOutput(out)
    addLog(`Shell result: ${res?.success ? 'OK' : 'FAIL'}`)
  }

  const typeColor = (t: string) => {
    const map: Record<string, string> = {
      streamlit: 'bg-orange-500',
      flask: 'bg-green-500',
      fastapi: 'bg-blue-500',
      cli: 'bg-gray-500',
      script: 'bg-yellow-500',
    }
    return map[t] || 'bg-gray-400'
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Rocket className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
            <p className="text-sm text-muted-foreground">
              Discover, test, and launch everything SwarmCoder has built.
            </p>
          </div>
        </div>
        <Button onClick={fetchProjects} variant="outline" size="sm">
          <RefreshCw className="mr-1 h-4 w-4" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Projects Grid */}
        <div className="lg:col-span-2 space-y-4">
          {projects.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <FileCode className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No projects found yet. Use SwarmCoder to build something!</p>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((proj) => {
              const report = testReports[proj.file]
              const isLoading = loading[proj.file]
              const isRunning = proj.running

              return (
                <Card key={proj.file} className="overflow-hidden">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${typeColor(proj.type)}`} />
                        {proj.name}
                      </CardTitle>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {proj.type}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{proj.lines} lines</span>
                      <span>{proj.size_kb} KB</span>
                      <span>{proj.created}</span>
                    </div>

                    {/* Test Status */}
                    {report && (
                      <div className={`text-xs rounded-md px-2 py-1 ${
                        report.failed === 0 ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                      }`}>
                        <div className="flex items-center gap-1">
                          {report.failed === 0 ? (
                            <CheckCircle className="h-3 w-3" />
                          ) : (
                            <XCircle className="h-3 w-3" />
                          )}
                          Tests: {report.passed}/{report.total} passed
                        </div>
                        {report.results.map((r, i) => (
                          r.error && <div key={i} className="text-[10px] text-red-300 mt-0.5">{r.error.slice(0, 80)}</div>
                        ))}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => testProject(proj.file)}
                        disabled={isLoading}
                      >
                        {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3 mr-1" />}
                        Test
                      </Button>

                      {isRunning ? (
                        <Button size="sm" variant="destructive" onClick={() => stopProject(proj.file)}>
                          <Square className="h-3 w-3 mr-1" /> Stop
                        </Button>
                      ) : (
                        <Button size="sm" variant="default" onClick={() => launchProject(proj.file)} disabled={proj.type === 'cli' || proj.type === 'script'}>
                          <Play className="h-3 w-3 mr-1" /> Launch
                        </Button>
                      )}

                      {isRunning && proj.port && (
                        <a href={`http://localhost:${proj.port}`} target="_blank" rel="noreferrer">
                          <Button size="sm" variant="outline">
                            <Monitor className="h-3 w-3 mr-1" /> Open
                          </Button>
                        </a>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>

        {/* Right Panel: Tools */}
        <div className="space-y-4">
          {/* Screenshot */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Camera className="h-4 w-4" /> Desktop Screenshot
              </CardTitle>
            </CardHeader>
            <CardContent>
              {screenshot ? (
                <img src={`data:image/png;base64,${screenshot}`} alt="Desktop" className="rounded-md border w-full" />
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground border rounded-md border-dashed">
                  <ImageIcon className="h-8 w-8 mb-2 opacity-50" />
                  <p className="text-sm">Click capture to see desktop</p>
                </div>
              )}
              <Button onClick={takeScreenshot} variant="outline" size="sm" className="w-full mt-2">
                <Camera className="mr-1 h-3 w-3" /> Capture
              </Button>
            </CardContent>
          </Card>

          {/* Shell */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Terminal className="h-4 w-4" /> Shell
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={shellCommand}
                  onChange={(e) => setShellCommand(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && runShell()}
                  placeholder="echo hello"
                  className="flex-1 rounded-md border bg-background px-2 py-1 text-sm"
                />
                <Button onClick={runShell} size="sm">
                  <Terminal className="h-3 w-3" />
                </Button>
              </div>
              {shellOutput && (
                <pre className="text-xs bg-black/30 p-2 rounded-md overflow-auto max-h-32 font-mono">{shellOutput}</pre>
              )}
            </CardContent>
          </Card>

          {/* Action Log */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Terminal className="h-4 w-4" /> Log
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-40 overflow-y-auto rounded-md border bg-black/30 p-2 font-mono text-xs space-y-1">
                {log.length === 0 && <span className="text-muted-foreground">No actions yet...</span>}
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
