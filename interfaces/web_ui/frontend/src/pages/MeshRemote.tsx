import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Monitor,
  MousePointerClick,
  Keyboard,
  Terminal,
  RefreshCw,
  Crosshair,
  Send,
  Loader2,
  Maximize2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface MeshNode {
  node_id: string
  name: string
  endpoint: string
  tier: string
  status: string
  latency_ms: number
  vram_mb: number
  models: string[]
}

interface MeshTopology {
  local: {
    node_id: string
    name: string
    vram_mb: number
    models: string[]
  }
  nodes: MeshNode[]
}

interface ScreenshotData {
  success: boolean
  image_base64: string
  width: number
  height: number
}

function useMeshTopology() {
  return useQuery<MeshTopology | null>({
    queryKey: ['meshTopology'],
    queryFn: () => api.get('/mesh/topology'),
    refetchInterval: 5000,
  })
}

function useNodeScreenshot(nodeId: string, enabled: boolean) {
  return useQuery<ScreenshotData | null>({
    queryKey: ['meshScreenshot', nodeId],
    queryFn: () => api.get(`/mesh/remote/${nodeId}/screenshot`),
    refetchInterval: enabled ? 2000 : false,
    enabled: enabled && !!nodeId,
  })
}

function useMeshAction(nodeId: string, action: string) {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/mesh/remote/${nodeId}/${action}`, body),
  })
}

export function MeshRemote() {
  const { data: topology } = useMeshTopology()
  const [selectedNode, setSelectedNode] = useState<string>('')
  const [typeText, setTypeText] = useState('')
  const [shellCmd, setShellCmd] = useState('')
  const [clickPos, setClickPos] = useState<{ x: number; y: number } | null>(null)
  const [actionLog, setActionLog] = useState<string[]>([])
  const imgRef = useRef<HTMLImageElement>(null)

  const allNodes: MeshNode[] = [
    ...(topology?.local
      ? [
          {
            node_id: topology.local.node_id,
            name: topology.local.name,
            endpoint: 'local',
            tier: 'local',
            status: 'online',
            latency_ms: 0,
            vram_mb: topology.local.vram_mb,
            models: topology.local.models,
          },
        ]
      : []),
    ...(topology?.nodes || []),
  ]

  const currentNode = allNodes.find((n) => n.node_id === selectedNode)
  const { data: screenshot, isFetching: ssLoading } = useNodeScreenshot(
    selectedNode,
    !!selectedNode
  )

  const clickMut = useMeshAction(selectedNode, 'click')
  const typeMut = useMeshAction(selectedNode, 'type')
  const keysMut = useMeshAction(selectedNode, 'keys')
  const shellMut = useMeshAction(selectedNode, 'shell')
  const scrollMut = useMeshAction(selectedNode, 'scroll')

  const log = useCallback((msg: string) => {
    setActionLog((prev) => [msg, ...prev].slice(0, 50))
  }, [])

  const handleImageClick = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!imgRef.current || !selectedNode) return
    const rect = imgRef.current.getBoundingClientRect()
    const scaleX = screenshot?.width ? screenshot.width / rect.width : 1
    const scaleY = screenshot?.height ? screenshot.height / rect.height : 1
    const x = Math.round((e.clientX - rect.left) * scaleX)
    const y = Math.round((e.clientY - rect.top) * scaleY)
    setClickPos({ x, y })
    clickMut.mutate(
      { x, y, button: 'left', clicks: 1 },
      {
        onSuccess: () => log(`Clicked (${x}, ${y}) on ${selectedNode}`),
        onError: (err: any) => log(`Click failed: ${err?.message || 'unknown'}`),
      }
    )
  }

  const handleType = () => {
    if (!typeText || !selectedNode) return
    typeMut.mutate(
      { text: typeText, interval: 0.01 },
      {
        onSuccess: () => log(`Typed "${typeText}" on ${selectedNode}`),
        onError: (err: any) => log(`Type failed: ${err?.message || 'unknown'}`),
      }
    )
    setTypeText('')
  }

  const handleKeys = (keys: string) => {
    if (!selectedNode) return
    keysMut.mutate(
      { keys },
      {
        onSuccess: () => log(`Sent keys "${keys}" to ${selectedNode}`),
        onError: (err: any) => log(`Keys failed: ${err?.message || 'unknown'}`),
      }
    )
  }

  const handleShell = () => {
    if (!shellCmd || !selectedNode) return
    shellMut.mutate(
      { command: shellCmd, timeout: 30 },
      {
        onSuccess: (res: any) => log(`Shell on ${selectedNode}: ${res?.message || 'ok'}`),
        onError: (err: any) => log(`Shell failed: ${err?.message || 'unknown'}`),
      }
    )
    setShellCmd('')
  }

  const handleScroll = (clicks: number) => {
    if (!selectedNode) return
    scrollMut.mutate(
      { clicks },
      {
        onSuccess: () => log(`Scrolled ${clicks} on ${selectedNode}`),
        onError: (err: any) => log(`Scroll failed: ${err?.message || 'unknown'}`),
      }
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Mesh Remote Control</h1>
          <p className="text-sm text-muted-foreground">
            Control any node in the swarm — click, type, screenshot, shell.
          </p>
        </div>
        <Badge variant="outline" className="text-xs">
          {allNodes.filter((n) => n.status === 'online').length}/{allNodes.length} nodes online
        </Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        {/* Node selector */}
        <div className="space-y-2 lg:col-span-1">
          <h3 className="text-sm font-semibold">Select Node</h3>
          {allNodes.map((node) => (
            <Button
              key={node.node_id}
              variant={selectedNode === node.node_id ? 'default' : 'outline'}
              className="w-full justify-start gap-2 text-left"
              onClick={() => setSelectedNode(node.node_id)}
            >
              <Monitor className="h-4 w-4 shrink-0" />
              <span className="truncate">{node.name}</span>
              <span
                className={cn(
                  'ml-auto h-2 w-2 rounded-full',
                  node.status === 'online' ? 'bg-green-500' : 'bg-red-500'
                )}
              />
            </Button>
          ))}
          {!allNodes.length && (
            <p className="text-xs text-muted-foreground">No mesh nodes found.</p>
          )}
        </div>

        {/* Screenshot + controls */}
        <div className="space-y-4 lg:col-span-3">
          {selectedNode && currentNode ? (
            <>
              {/* Screenshot card */}
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">{currentNode.name}</CardTitle>
                      <Badge variant={currentNode.status === 'online' ? 'default' : 'destructive'}>
                        {currentNode.status}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      {ssLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                      <span className="text-xs text-muted-foreground">
                        {screenshot?.width ?? 0}x{screenshot?.height ?? 0}
                      </span>
                      {clickPos && (
                        <Badge variant="outline" className="text-xs">
                          <Crosshair className="mr-1 h-3 w-3" />
                          {clickPos.x},{clickPos.y}
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {screenshot?.image_base64 ? (
                    <div className="relative overflow-hidden rounded-md border bg-black">
                      <img
                        ref={imgRef}
                        src={`data:image/png;base64,${screenshot.image_base64}`}
                        alt={`Screenshot of ${currentNode.name}`}
                        className="w-full cursor-crosshair object-contain"
                        onClick={handleImageClick}
                        draggable={false}
                      />
                      <div className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-1 text-xs text-white">
                        Click image to send click
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-64 items-center justify-center rounded-md border bg-muted">
                      <p className="text-sm text-muted-foreground">
                        {ssLoading ? 'Capturing...' : 'No screenshot available'}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Control panels */}
              <Tabs defaultValue="keyboard">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="keyboard">
                    <Keyboard className="mr-2 h-4 w-4" />
                    Keyboard
                  </TabsTrigger>
                  <TabsTrigger value="mouse">
                    <MousePointerClick className="mr-2 h-4 w-4" />
                    Mouse
                  </TabsTrigger>
                  <TabsTrigger value="shell">
                    <Terminal className="mr-2 h-4 w-4" />
                    Shell
                  </TabsTrigger>
                  <TabsTrigger value="log">
                    <Maximize2 className="mr-2 h-4 w-4" />
                    Log
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="keyboard" className="space-y-3">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Type text to send..."
                      value={typeText}
                      onChange={(e) => setTypeText(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleType()}
                    />
                    <Button onClick={handleType} disabled={!typeText || typeMut.isPending}>
                      <Send className="mr-2 h-4 w-4" />
                      Send
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {['enter', 'tab', 'esc', 'ctrl+c', 'ctrl+v', 'ctrl+a', 'alt+tab', 'win+d', 'ctrl+shift+esc'].map(
                      (k) => (
                        <Button key={k} variant="outline" size="sm" onClick={() => handleKeys(k)}>
                          {k}
                        </Button>
                      )
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="mouse" className="space-y-3">
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => handleScroll(3)}>
                      Scroll Up
                    </Button>
                    <Button variant="outline" onClick={() => handleScroll(-3)}>
                      Scroll Down
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Click directly on the screenshot above to send a mouse click at that location.
                  </p>
                </TabsContent>

                <TabsContent value="shell" className="space-y-3">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Enter shell command..."
                      value={shellCmd}
                      onChange={(e) => setShellCmd(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleShell()}
                    />
                    <Button onClick={handleShell} disabled={!shellCmd || shellMut.isPending}>
                      <Terminal className="mr-2 h-4 w-4" />
                      Run
                    </Button>
                  </div>
                </TabsContent>

                <TabsContent value="log">
                  <div className="h-48 overflow-auto rounded-md border bg-muted p-3">
                    {actionLog.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No actions yet.</p>
                    ) : (
                      <div className="space-y-1">
                        {actionLog.map((entry, i) => (
                          <p key={i} className="text-xs font-mono">
                            {entry}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </>
          ) : (
            <Card>
              <CardContent className="flex h-96 items-center justify-center">
                <div className="text-center">
                  <Monitor className="mx-auto h-12 w-12 text-muted-foreground" />
                  <p className="mt-4 text-lg font-medium">Select a node to control</p>
                  <p className="text-sm text-muted-foreground">
                    Choose a node from the sidebar to start remote control.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
