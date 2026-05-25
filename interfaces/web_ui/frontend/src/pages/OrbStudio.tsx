/**
 * ORBSTUDIO SWARM — AGENT-014 (Dashboard UI/UX) v2.0
 * CIRCUIT: Main Breaker Panel + Hardware Sourcing + Build Analysis
 * TIMESTAMP: 2026-05-23_0100_PST
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Zap, Thermometer, Activity, Server, AlertTriangle, Power, RotateCcw,
  Wrench, BookOpen, Fish, Cable, ShoppingCart, BarChart3, FileText,
  ChevronDown, ExternalLink, Search, CheckCircle2, AlertCircle,
  TrendingUp, Clock, MapPin, DollarSign, ShieldAlert, Truck, Copy,
  PowerOff
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'

// ─── TYPES ───
interface ZoneSnapshot {
  current_temp_c: number; target_temp_c: number; thermal_mass_kg: number
  heat_input_w: number; heat_loss_w: number; breaker_state: string
  latest_history: Array<{ timestamp: number; temp_c: number; heat_input_w: number; breaker: string }>
}
interface RackSnapshot {
  max_tdp_w: number; current_load_pct: number; throttle_pct: number
  is_online: boolean; actual_heat_output_w: number
}
interface Snapshot {
  timestamp: number; ambient_earth_temp_c: number; max_safe_water_temp_c: number
  zones: Record<string, ZoneSnapshot>; racks: Record<string, RackSnapshot>
}
interface Status {
  running: boolean; tick_interval_s: number; ambient_earth_temp_c: number
  max_safe_water_temp_c: number; max_server_exhaust_c: number
  min_water_temp_c: number; zone_count: number; rack_count: number
}

interface SupplierOption {
  supplier_name: string; location: string; unit_price_usd: number
  currency: string; url: string; shipping_days: number
  min_order_qty: number; in_stock: boolean; notes: string; reliability_score: number
}
interface BOMItem {
  part_number: string; description: string; category: string; qty: number
  datasheet_url: string; notes: string; options: SupplierOption[]
  selected_option_idx: number; selected_price_usd: number
  selected_supplier: string; selected_location: string; selected_url: string
  extended_price_usd: number
}
interface BuildProfileSummary {
  id: string; name: string; description: string; icon: string
  color: string; strategy: string; summary: {
    profile_name: string; total_usd: number; max_shipping_days: number
    by_supplier: Record<string, number>; by_location: Record<string, number>
    item_count: number; suppliers_needed: number; items: any[]
  }
}
interface BuildReport {
  profile_name: string; generated_at: string; total_cost_usd: number
  cost_by_category: Record<string, number>; cost_by_location: Record<string, number>
  most_expensive_item: string; max_shipping_days: number; suppliers_needed: number
  single_source_risks: string[]; local_vs_online_pct: [number, number]
  server_heat_output_w: number; heat_recovered_w: number; heat_losses_w: Record<string, number>
  net_thermal_balance_w: number; equilibrium_temp_c: number; thermal_recommendation: string
  species: string; optimal_temp_c: number; temp_margin_to_stress_c: number
  max_stocking_kg: number; estimated_yield_kg_per_year: number
  feed_cost_usd_per_year: number; roi_months: number; break_even_analysis: string
  risks: Array<{ level: string; category: string; description: string }>
}

export function OrbStudio() {
  // ─── STATE ───
  const [status, setStatus] = useState<Status | null>(null)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'dashboard' | 'hardware' | 'build' | 'aquaculture'>('dashboard')

  // Hardware tab sub-state
  const [hardwareSubTab, setHardwareSubTab] = useState<'bom' | 'wiring' | 'profiles' | 'analysis'>('bom')
  const [bomItems, setBomItems] = useState<BOMItem[] | null>(null)
  const [bomSearch, setBomSearch] = useState('')
  const [customSelections, setCustomSelections] = useState<Record<string, number>>({})
  const [profiles, setProfiles] = useState<BuildProfileSummary[] | null>(null)
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null)
  const [report, setReport] = useState<BuildReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [wiringText, setWiringText] = useState<string>('')
  const [thermalEng, setThermalEng] = useState<any>(null)
  const [aquaSpec, setAquaSpec] = useState<any>(null)
  const [copiedReport, setCopiedReport] = useState(false)

  const wiringRef = useRef<HTMLPreElement>(null)

  // ─── FETCHERS ───
  const fetchStatus = useCallback(async () => {
    try { const res = await fetch('/orbstudio/status'); if (res.ok) setStatus(await res.json()) } catch {}
  }, [])
  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch('/orbstudio/snapshot')
      if (res.ok) { setSnapshot(await res.json()); setError(null) }
    } catch (e: any) { setError(e.message || 'Failed to fetch') }
  }, [])

  useEffect(() => {
    fetchStatus(); fetchSnapshot()
    const interval = setInterval(() => { fetchStatus(); fetchSnapshot() }, 3000)
    return () => clearInterval(interval)
  }, [fetchStatus, fetchSnapshot])

  useEffect(() => {
    fetch('/hardware/manifest').then(r => r.ok ? r.json() : null).then(d => { if (d) { setBomItems(d.items); setCustomSelections(Object.fromEntries(d.items.map((i: BOMItem) => [i.part_number, i.selected_option_idx]))); } })
    fetch('/hardware/build-profiles').then(r => r.ok ? r.json() : null).then(d => { if (d) { setProfiles(d.profiles); setActiveProfileId(d.profiles[1]?.id); } })
    fetch('/hardware/thermal-engineering').then(r => r.ok ? r.json() : null).then(d => d && setThermalEng(d))
    fetch('/hardware/aquaculture-spec').then(r => r.ok ? r.json() : null).then(d => d && setAquaSpec(d))
    fetch('/hardware/wiring-schematic').then(r => r.ok ? r.text() : '').then(t => setWiringText(t))
  }, [])

  // Auto-scroll wiring to top on load
  useEffect(() => {
    if (wiringRef.current && wiringText) {
      wiringRef.current.scrollTop = 0
    }
  }, [wiringText, hardwareSubTab])

  const sendCommand = async (endpoint: string, body?: object) => {
    setLoading(true)
    try {
      const res = await fetch(`/orbstudio${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await fetchSnapshot(); await fetchStatus()
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }

  const handleSupplierChange = (partNumber: string, optionIdx: number) => {
    const next = { ...customSelections, [partNumber]: optionIdx }
    setCustomSelections(next)
    // Refresh manifest with new selections
    fetch(`/hardware/manifest?selections=${encodeURIComponent(JSON.stringify(next))}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setBomItems(d.items))
  }

  const analyzeActiveProfile = async () => {
    setReportLoading(true)
    try {
      const profile = profiles?.find(p => p.id === activeProfileId)
      const body = activeProfileId && activeProfileId !== 'custom'
        ? { profile_id: activeProfileId }
        : { custom_selections: customSelections }
      const res = await fetch('/hardware/analyze-build', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (res.ok) {
        const data = await res.json()
        setReport(data)
        setHardwareSubTab('analysis')
      }
    } catch (e: any) { setError(e.message) }
    finally { setReportLoading(false) }
  }

  const copyReport = () => {
    if (!report) return
    const text = generateReportText(report)
    navigator.clipboard.writeText(text).then(() => { setCopiedReport(true); setTimeout(() => setCopiedReport(false), 2000) })
  }

  const tempColor = (temp: number, max: number) => { const pct = temp / max; if (pct > 0.95) return 'text-red-500'; if (pct > 0.8) return 'text-orange-500'; if (pct > 0.6) return 'text-yellow-500'; return 'text-emerald-500' }
  const tempBg = (temp: number, max: number) => { const pct = temp / max; if (pct > 0.95) return 'bg-red-500/10 border-red-500/30'; if (pct > 0.8) return 'bg-orange-500/10 border-orange-500/30'; if (pct > 0.6) return 'bg-yellow-500/10 border-yellow-500/30'; return 'bg-emerald-500/10 border-emerald-500/30' }

  const filteredBom = bomItems?.filter(i =>
    i.part_number.toLowerCase().includes(bomSearch.toLowerCase()) ||
    i.description.toLowerCase().includes(bomSearch.toLowerCase()) ||
    i.category.toLowerCase().includes(bomSearch.toLowerCase())
  )

  const profileColor = (color: string) => {
    const map: Record<string, string> = { yellow: 'bg-yellow-500/20 border-yellow-500/40 text-yellow-400', blue: 'bg-blue-500/20 border-blue-500/40 text-blue-400', emerald: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400', orange: 'bg-orange-500/20 border-orange-500/40 text-orange-400', purple: 'bg-purple-500/20 border-purple-500/40 text-purple-400' }
    return map[color] || map.blue
  }

  const categoryIcons: Record<string, string> = { sensor: '🌡️', actuator: '⚡', pump: '💧', heat_exchanger: '♨️', controller: '🧠', enclosure: '📦', power: '🔌', misc: '🔧' }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Zap className="h-6 w-6 text-yellow-500" />
            Main Breaker Panel
          </h1>
          <p className="text-sm text-muted-foreground mt-1">OrbStudio Swarm — Subterranean Server Farm & Circular Aquaculture Sanctuary</p>
        </div>
        <div className="flex items-center gap-3">
          {status?.running ? (
            <Badge variant="default" className="gap-1 bg-emerald-600"><Activity className="h-3 w-3" /> CIRCUITS LIVE</Badge>
          ) : (
            <Badge variant="destructive" className="gap-1"><AlertTriangle className="h-3 w-3" /> BREAKER OPEN</Badge>
          )}
          <Button size="sm" variant={status?.running ? 'destructive' : 'default'} onClick={() => sendCommand(status?.running ? '/stop' : '/start')} disabled={loading}>
            <Power className="h-4 w-4 mr-1" /> {status?.running ? 'EMERGENCY STOP' : 'CLOSE MAIN BREAKER'}
          </Button>
          <Button size="sm" variant="outline" className="gap-1 text-muted-foreground hover:text-red-400 hover:border-red-400/50" onClick={async () => {
            if (confirm('Shutdown OrbStudio backend server?\nThis will stop the API and close all circuits.')) {
              await sendCommand('/shutdown')
              setStatus(null)
            }
          }} disabled={loading || !status?.running}>
            <PowerOff className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="outline" onClick={fetchSnapshot} disabled={loading}><RotateCcw className="h-4 w-4" /></Button>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-2 border-b pb-2">
        <Button variant={activeTab === 'dashboard' ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab('dashboard')}><Activity className="h-4 w-4 mr-1" /> Dashboard</Button>
        <Button variant={activeTab === 'hardware' ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab('hardware')}><Wrench className="h-4 w-4 mr-1" /> Hardware</Button>
        <Button variant={activeTab === 'aquaculture' ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab('aquaculture')}><Fish className="h-4 w-4 mr-1" /> Aquaculture</Button>
        <Button variant={activeTab === 'build' ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab('build')}><BookOpen className="h-4 w-4 mr-1" /> Build Guide</Button>
      </div>

      {error && <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">{error}</div>}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* DASHBOARD TAB */}
      {/* ═══════════════════════════════════════════════════════ */}
      {activeTab === 'dashboard' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Ambient Earth</div><div className="text-2xl font-bold mt-1">{snapshot?.ambient_earth_temp_c ?? '--'}°C</div></CardContent></Card>
            <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Max Safe Water</div><div className="text-2xl font-bold mt-1 text-red-500">{snapshot?.max_safe_water_temp_c ?? '--'}°C</div></CardContent></Card>
            <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Zones</div><div className="text-2xl font-bold mt-1">{status?.zone_count ?? '--'}</div></CardContent></Card>
            <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Compute Racks</div><div className="text-2xl font-bold mt-1">{status?.rack_count ?? '--'}</div></CardContent></Card>
          </div>

          <div>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2"><Thermometer className="h-5 w-5 text-blue-500" /> Thermal Zones</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {snapshot ? Object.entries(snapshot.zones).map(([zid, zone]) => (
                <Card key={zid} className={`border-2 transition-colors ${tempBg(zone.current_temp_c, snapshot.max_safe_water_temp_c)}`}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium uppercase tracking-wider">{zid.replace(/_/g, ' ')}</CardTitle>
                      <Badge variant={zone.breaker_state === 'CLOSED' ? 'default' : 'destructive'} className="text-xs">{zone.breaker_state === 'CLOSED' ? 'CLOSED' : 'OPEN'}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-end justify-between">
                      <div><div className="text-xs text-muted-foreground">Current Temp</div><div className={`text-3xl font-bold ${tempColor(zone.current_temp_c, snapshot.max_safe_water_temp_c)}`}>{zone.current_temp_c.toFixed(1)}°C</div></div>
                      <div className="text-right"><div className="text-xs text-muted-foreground">Target</div><div className="text-lg font-semibold">{zone.target_temp_c}°C</div></div>
                    </div>
                    {zone.latest_history.length > 1 && (
                      <div className="h-10 flex items-end gap-px">
                        {zone.latest_history.map((h, i) => { const max = snapshot.max_safe_water_temp_c; const hPct = Math.min(1, Math.max(0, h.temp_c / max)); return (
                          <div key={i} className="flex-1 rounded-sm transition-all" style={{ height: `${hPct * 100}%`, backgroundColor: hPct > 0.95 ? '#ef4444' : hPct > 0.8 ? '#f97316' : '#10b981' }} title={`${h.temp_c.toFixed(1)}°C`} />
                        )})}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded bg-background/50 px-2 py-1"><span className="text-muted-foreground">Heat In:</span> <span className="font-mono font-semibold">{zone.heat_input_w.toFixed(0)} W</span></div>
                      <div className="rounded bg-background/50 px-2 py-1"><span className="text-muted-foreground">Heat Loss:</span> <span className="font-mono font-semibold">{zone.heat_loss_w.toFixed(0)} W</span></div>
                      <div className="rounded bg-background/50 px-2 py-1"><span className="text-muted-foreground">Thermal Mass:</span> <span className="font-mono font-semibold">{zone.thermal_mass_kg.toLocaleString()} kg</span></div>
                      <div className="rounded bg-background/50 px-2 py-1"><span className="text-muted-foreground">Net:</span> <span className="font-mono font-semibold">{(zone.heat_input_w - zone.heat_loss_w).toFixed(0)} W</span></div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" className="flex-1" onClick={() => sendCommand('/breaker/override', { zone_id: zid, state: 'CLOSED' })} disabled={loading || zone.breaker_state === 'CLOSED'}>Close Breaker</Button>
                      <Button size="sm" variant="destructive" className="flex-1" onClick={() => sendCommand('/breaker/override', { zone_id: zid, state: 'OPEN' })} disabled={loading || zone.breaker_state === 'OPEN'}>Open Breaker</Button>
                    </div>
                  </CardContent>
                </Card>
              )) : <div className="col-span-full text-center text-muted-foreground py-12">Loading Model Space viewport...</div>}
            </div>
          </div>

          <div>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2"><Server className="h-5 w-5 text-purple-500" /> Compute Racks</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {snapshot ? Object.entries(snapshot.racks).map(([rid, rack]) => (
                <Card key={rid} className={rack.is_online ? '' : 'opacity-50'}>
                  <CardHeader className="pb-2"><CardTitle className="text-sm font-medium uppercase tracking-wider">{rid.replace(/_/g, ' ')}</CardTitle></CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between"><div className="text-xs text-muted-foreground">Heat Output</div><div className="text-lg font-bold font-mono">{rack.actual_heat_output_w.toFixed(0)} W</div></div>
                    <div><div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">Load</span><span className="font-mono">{rack.current_load_pct.toFixed(0)}%</span></div><div className="h-2 rounded-full bg-muted overflow-hidden"><div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${rack.current_load_pct}%` }} /></div></div>
                    <div><div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">Throttle</span><span className="font-mono">{rack.throttle_pct.toFixed(0)}%</span></div><div className="h-2 rounded-full bg-muted overflow-hidden"><div className={`h-full rounded-full transition-all ${rack.throttle_pct < 50 ? 'bg-red-500' : rack.throttle_pct < 80 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${rack.throttle_pct}%` }} /></div></div>
                    <div className="text-xs text-muted-foreground">Max TDP: <span className="font-mono font-semibold text-foreground">{rack.max_tdp_w} W</span></div>
                  </CardContent>
                </Card>
              )) : <div className="col-span-full text-center text-muted-foreground py-12">Loading rack telemetry...</div>}
            </div>
          </div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* HARDWARE TAB */}
      {/* ═══════════════════════════════════════════════════════ */}
      {activeTab === 'hardware' && (
        <div className="space-y-4">
          {/* Hardware Sub-Tab Bar */}
          <div className="flex flex-wrap gap-2 border-b pb-2">
            <Button variant={hardwareSubTab === 'bom' ? 'default' : 'ghost'} size="sm" onClick={() => setHardwareSubTab('bom')}><ShoppingCart className="h-4 w-4 mr-1" /> Bill of Materials</Button>
            <Button variant={hardwareSubTab === 'wiring' ? 'default' : 'ghost'} size="sm" onClick={() => setHardwareSubTab('wiring')}><Cable className="h-4 w-4 mr-1" /> Wiring Schematic</Button>
            <Button variant={hardwareSubTab === 'profiles' ? 'default' : 'ghost'} size="sm" onClick={() => setHardwareSubTab('profiles')}><BarChart3 className="h-4 w-4 mr-1" /> Build Profiles</Button>
            <Button variant={hardwareSubTab === 'analysis' ? 'default' : 'ghost'} size="sm" onClick={() => setHardwareSubTab('analysis')}><FileText className="h-4 w-4 mr-1" /> Analysis Report</Button>
          </div>

          {/* ─── BOM SUB-TAB ─── */}
          {hardwareSubTab === 'bom' && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="relative flex-1 max-w-sm">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input placeholder="Search parts..." value={bomSearch} onChange={e => setBomSearch(e.target.value)} className="pl-8" />
                </div>
                <div className="text-sm text-muted-foreground">
                  {filteredBom ? `${filteredBom.length} items` : 'Loading...'}
                </div>
              </div>

              {filteredBom ? (
                <div className="space-y-3">
                  {filteredBom.map((item, idx) => (
                    <Card key={idx} className="overflow-hidden">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-lg">{categoryIcons[item.category] || '🔧'}</span>
                              <span className="font-mono text-xs text-muted-foreground">{item.part_number}</span>
                              <Badge variant="outline" className="text-[10px] uppercase">{item.category}</Badge>
                              <span className="text-xs text-muted-foreground">×{item.qty}</span>
                            </div>
                            <div className="font-medium text-sm">{item.description}</div>
                            <div className="text-xs text-muted-foreground mt-1">{item.notes}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-lg font-bold font-mono">${item.extended_price_usd.toFixed(2)}</div>
                            <div className="text-xs text-muted-foreground">${item.selected_price_usd.toFixed(2)} / unit</div>
                          </div>
                        </div>

                        {/* Supplier Selector */}
                        <div className="mt-3 pt-3 border-t">
                          <div className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1"><ShoppingCart className="h-3 w-3" /> Source from:</div>
                          <div className="flex flex-wrap gap-2">
                            {item.options.map((opt, oi) => (
                              <button
                                key={oi}
                                onClick={() => handleSupplierChange(item.part_number, oi)}
                                className={`relative rounded-md border px-3 py-2 text-left text-xs transition-all ${
                                  customSelections[item.part_number] === oi
                                    ? 'border-primary bg-primary/10 ring-1 ring-primary'
                                    : 'border-muted bg-background hover:bg-muted/50'
                                }`}
                                title={opt.notes}
                              >
                                <div className="font-semibold flex items-center gap-1">
                                  {opt.supplier_name}
                                  {opt.in_stock ? <span className="text-emerald-500">●</span> : <span className="text-red-500">●</span>}
                                </div>
                                <div className="text-muted-foreground flex items-center gap-1 mt-0.5">
                                  <MapPin className="h-3 w-3" /> {opt.location}
                                </div>
                                <div className="flex items-center gap-3 mt-1">
                                  <span className="font-mono font-bold text-foreground">${opt.unit_price_usd.toFixed(2)}</span>
                                  <span className="text-muted-foreground flex items-center gap-0.5"><Clock className="h-3 w-3" /> {opt.shipping_days}d</span>
                                  {opt.url && (
                                    <span
                                      className="text-blue-400 hover:underline flex items-center gap-0.5 cursor-pointer"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        window.open(opt.url, '_blank', 'noopener,noreferrer');
                                      }}
                                    >
                                      <ExternalLink className="h-3 w-3" /> Buy
                                    </span>
                                  )}
                                </div>
                                {customSelections[item.part_number] === oi && (
                                  <div className="absolute -top-1.5 -right-1.5 bg-primary text-primary-foreground rounded-full p-0.5">
                                    <CheckCircle2 className="h-3 w-3" />
                                  </div>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}

                  {/* BOM Total */}
                  <Card className="bg-muted/50">
                    <CardContent className="p-4 flex items-center justify-between">
                      <div className="font-semibold">Custom Build Total</div>
                      <div className="text-2xl font-bold font-mono">
                        ${filteredBom.reduce((s, i) => s + i.extended_price_usd, 0).toFixed(2)}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ) : (
                <div className="text-center text-muted-foreground py-12">Loading manifest...</div>
              )}
            </div>
          )}

          {/* ─── WIRING SUB-TAB ─── */}
          {hardwareSubTab === 'wiring' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold flex items-center gap-2"><Cable className="h-5 w-5 text-blue-500" /> Wiring Schematic</h2>
                <span className="text-xs text-muted-foreground">Use horizontal scroll to view full diagram</span>
              </div>
              <div className="rounded-md border bg-[#0d1117] overflow-hidden">
                <pre
                  ref={wiringRef}
                  className="text-[11px] leading-[1.4] font-mono text-[#7ee787] p-4 overflow-x-auto whitespace-pre"
                  style={{ fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace", minWidth: 'max-content' }}
                >
                  {wiringText || 'Loading schematic...'}
                </pre>
              </div>
            </div>
          )}

          {/* ─── PROFILES SUB-TAB ─── */}
          {hardwareSubTab === 'profiles' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold flex items-center gap-2"><BarChart3 className="h-5 w-5 text-purple-500" /> Build Profiles</h2>
                <Button size="sm" onClick={analyzeActiveProfile} disabled={reportLoading || !activeProfileId}>
                  {reportLoading ? 'Analyzing...' : <><FileText className="h-4 w-4 mr-1" /> Analyze Selected Build</>}
                </Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {profiles?.map(p => (
                  <Card
                    key={p.id}
                    className={`cursor-pointer transition-all ${activeProfileId === p.id ? 'ring-2 ring-primary' : 'opacity-70 hover:opacity-100'}`}
                    onClick={() => setActiveProfileId(p.id)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-2xl">{p.icon}</span>
                        <div className={`text-xs font-bold uppercase px-2 py-0.5 rounded border ${profileColor(p.color)}`}>{p.strategy}</div>
                      </div>
                      <div className="font-semibold">{p.name}</div>
                      <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{p.description}</div>
                      <div className="mt-3 pt-3 border-t space-y-1">
                        <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total</span><span className="font-mono font-bold">${p.summary.total_usd.toFixed(2)}</span></div>
                        <div className="flex justify-between text-xs"><span className="text-muted-foreground">Shipping</span><span className="font-mono">{p.summary.max_shipping_days} days max</span></div>
                        <div className="flex justify-between text-xs"><span className="text-muted-foreground">Suppliers</span><span className="font-mono">{p.summary.suppliers_needed}</span></div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Active Profile Detail */}
              {activeProfileId && profiles && (
                <Card>
                  <CardHeader><CardTitle>{profiles.find(p => p.id === activeProfileId)?.name} — Item Breakdown</CardTitle></CardHeader>
                  <CardContent>
                    <div className="rounded-md border overflow-hidden">
                      <table className="w-full text-sm">
                        <thead className="bg-muted"><tr><th className="px-3 py-2 text-left">Part</th><th className="px-3 py-2 text-left">Supplier</th><th className="px-3 py-2 text-left">Location</th><th className="px-3 py-2 text-right">Unit</th><th className="px-3 py-2 text-right">Ext</th></tr></thead>
                        <tbody>
                          {profiles.find(p => p.id === activeProfileId)?.summary.items.map((it: any, i: number) => (
                            <tr key={i} className="border-t"><td className="px-3 py-2 font-mono text-xs">{it.part_number} <span className="text-muted-foreground">×{it.qty}</span></td><td className="px-3 py-2 text-xs">{it.supplier}</td><td className="px-3 py-2 text-xs text-muted-foreground">{it.location}</td><td className="px-3 py-2 text-right font-mono text-xs">${it.unit_price.toFixed(2)}</td><td className="px-3 py-2 text-right font-mono font-semibold text-xs">${it.extended.toFixed(2)}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* ─── ANALYSIS SUB-TAB ─── */}
          {hardwareSubTab === 'analysis' && (
            <div className="space-y-6">
              {!report && !reportLoading && (
                <div className="text-center py-12 space-y-4">
                  <FileText className="h-12 w-12 text-muted-foreground mx-auto" />
                  <div className="text-lg font-medium">No Analysis Report Yet</div>
                  <div className="text-sm text-muted-foreground">Select a build profile and click "Analyze Selected Build" to generate a full engineering report.</div>
                  <Button onClick={() => setHardwareSubTab('profiles')}><BarChart3 className="h-4 w-4 mr-1" /> Go to Build Profiles</Button>
                </div>
              )}

              {reportLoading && (
                <div className="text-center py-12">
                  <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
                  <div className="text-sm text-muted-foreground">Running thermal, cost, and risk analysis...</div>
                </div>
              )}

              {report && !reportLoading && (
                <>
                  {/* Report Header */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2"><FileText className="h-5 w-5 text-primary" /> Build Analysis: {report.profile_name}</h2>
                      <div className="text-xs text-muted-foreground mt-0.5">Generated {report.generated_at}</div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={copyReport}>
                        {copiedReport ? <><CheckCircle2 className="h-4 w-4 mr-1" /> Copied</> : <><Copy className="h-4 w-4 mr-1" /> Copy Report</>}
                      </Button>
                      <Button size="sm" onClick={analyzeActiveProfile} disabled={reportLoading}><RotateCcw className="h-4 w-4 mr-1" /> Re-Analyze</Button>
                    </div>
                  </div>

                  {/* Cost Overview */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase flex items-center gap-1"><DollarSign className="h-3 w-3" /> Total Cost</div><div className="text-2xl font-bold font-mono mt-1">${report.total_cost_usd.toFixed(2)}</div></CardContent></Card>
                    <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase flex items-center gap-1"><Clock className="h-3 w-3" /> Max Shipping</div><div className="text-2xl font-bold font-mono mt-1">{report.max_shipping_days}d</div></CardContent></Card>
                    <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase flex items-center gap-1"><Truck className="h-3 w-3" /> Suppliers</div><div className="text-2xl font-bold font-mono mt-1">{report.suppliers_needed}</div></CardContent></Card>
                    <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground uppercase flex items-center gap-1"><TrendingUp className="h-3 w-3" /> ROI</div><div className="text-2xl font-bold font-mono mt-1 text-emerald-500">{report.roi_months.toFixed(1)} mo</div></CardContent></Card>
                  </div>

                  {/* Risk Register */}
                  <Card>
                    <CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert className="h-5 w-5 text-red-500" /> Risk Register</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {report.risks.map((risk, i) => (
                        <div key={i} className={`rounded-md border px-3 py-2 text-sm flex items-start gap-2 ${
                          risk.level === 'HIGH' ? 'bg-red-500/10 border-red-500/30 text-red-400' :
                          risk.level === 'MEDIUM' ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400' :
                          'bg-blue-500/10 border-blue-500/30 text-blue-400'
                        }`}>
                          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold">[{risk.level}] {risk.category}:</span> {risk.description}
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  {/* Cost Breakdown */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Card>
                      <CardHeader><CardTitle className="text-sm">Cost by Category</CardTitle></CardHeader>
                      <CardContent className="space-y-2">
                        {Object.entries(report.cost_by_category).map(([cat, cost]) => (
                          <div key={cat} className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-1"><span>{categoryIcons[cat] || '🔧'}</span> {cat.replace(/_/g, ' ')}</span>
                            <span className="font-mono font-semibold">${(cost as number).toFixed(2)}</span>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader><CardTitle className="text-sm">Sourcing Split</CardTitle></CardHeader>
                      <CardContent className="space-y-3">
                        <div className="flex items-center gap-2 text-sm">
                          <MapPin className="h-4 w-4 text-emerald-500" />
                          <span className="flex-1">Local / In-Store</span>
                          <span className="font-mono font-bold">{report.local_vs_online_pct[0]}%</span>
                        </div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden flex">
                          <div className="h-full bg-emerald-500" style={{ width: `${report.local_vs_online_pct[0]}%` }} />
                          <div className="h-full bg-blue-500" style={{ width: `${report.local_vs_online_pct[1]}%` }} />
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Truck className="h-4 w-4 text-blue-500" />
                          <span className="flex-1">Online / Shipped</span>
                          <span className="font-mono font-bold">{report.local_vs_online_pct[1]}%</span>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          Most expensive: <span className="text-foreground font-medium">{report.most_expensive_item}</span>
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Thermal Analysis */}
                  <Card>
                    <CardHeader><CardTitle className="flex items-center gap-2"><Thermometer className="h-5 w-5 text-orange-500" /> Thermal Engineering Analysis</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div><div className="text-xs text-muted-foreground">Server Heat Output</div><div className="text-lg font-bold font-mono">{report.server_heat_output_w} W</div></div>
                        <div><div className="text-xs text-muted-foreground">Heat Recovered (HX)</div><div className="text-lg font-bold font-mono text-emerald-500">{report.heat_recovered_w} W</div></div>
                        <div><div className="text-xs text-muted-foreground">Net Balance</div><div className={`text-lg font-bold font-mono ${report.net_thermal_balance_w >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{report.net_thermal_balance_w >= 0 ? '+' : ''}{report.net_thermal_balance_w} W</div></div>
                        <div><div className="text-xs text-muted-foreground">Equilibrium Temp</div><div className="text-lg font-bold font-mono">{report.equilibrium_temp_c}°C</div></div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                        {Object.entries(report.heat_losses_w).map(([k, v]) => (
                          <div key={k} className="rounded bg-muted/50 px-2 py-1"><span className="text-muted-foreground">{k.replace(/_/g, ' ')}:</span> <span className="font-mono font-semibold">{(v as number).toFixed(1)} W</span></div>
                        ))}
                      </div>
                      <div className={`rounded-md px-3 py-2 text-sm ${report.net_thermal_balance_w >= 0 ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400' : 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-400'}`}>
                        {report.thermal_recommendation}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Aquaculture & ROI */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Card>
                      <CardHeader><CardTitle className="flex items-center gap-2"><Fish className="h-5 w-5 text-blue-500" /> Aquaculture Forecast</CardTitle></CardHeader>
                      <CardContent className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-muted-foreground">Species</span><span className="font-medium">{report.species}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Optimal Temp</span><span className="font-medium">{report.optimal_temp_c}°C</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Temp Margin to Stress</span><span className={`font-medium ${report.temp_margin_to_stress_c < 2 ? 'text-red-500' : 'text-emerald-500'}`}>{report.temp_margin_to_stress_c}°C</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Max Stocking</span><span className="font-medium">{report.max_stocking_kg} kg</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Est. Annual Yield</span><span className="font-medium text-emerald-500">{report.estimated_yield_kg_per_year} kg</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Feed Cost / Year</span><span className="font-medium">${report.feed_cost_usd_per_year}</span></div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader><CardTitle className="flex items-center gap-2"><TrendingUp className="h-5 w-5 text-emerald-500" /> Break-Even Analysis</CardTitle></CardHeader>
                      <CardContent className="space-y-3">
                        <div className="text-sm">{report.break_even_analysis}</div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden">
                          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${Math.min(100, (12 / report.roi_months) * 100)}%` }} />
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Payback period: <span className="font-mono font-semibold text-emerald-500">{report.roi_months.toFixed(1)} months</span>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* AQUACULTURE TAB */}
      {/* ═══════════════════════════════════════════════════════ */}
      {activeTab === 'aquaculture' && (
        <div className="space-y-6">
          {aquaSpec && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Fish className="h-5 w-5 text-blue-500" /> Tilapia Parameters (FAO Data)</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div><div className="text-muted-foreground text-xs">Species</div><div className="font-medium">{aquaSpec.species}</div></div>
                <div><div className="text-muted-foreground text-xs">Optimal Temp</div><div className="font-medium">{aquaSpec.temperature?.optimal_c}°C</div></div>
                <div><div className="text-muted-foreground text-xs">Stress Threshold</div><div className="font-medium text-orange-500">{aquaSpec.temperature?.stress_threshold_c}°C</div></div>
                <div><div className="text-muted-foreground text-xs">Lethal Max</div><div className="font-medium text-red-500">{aquaSpec.temperature?.lethal_max_c}°C</div></div>
                <div><div className="text-muted-foreground text-xs">Lethal Min</div><div className="font-medium text-red-500">{aquaSpec.temperature?.lethal_min_c}°C</div></div>
                <div><div className="text-muted-foreground text-xs">Stocking Density</div><div className="font-medium">{aquaSpec.stocking_density?.recommended_kg_per_m3} kg/m³</div></div>
                <div><div className="text-muted-foreground text-xs">Max Density</div><div className="font-medium">{aquaSpec.stocking_density?.max_kg_per_m3} kg/m³</div></div>
                <div><div className="text-muted-foreground text-xs">Optimal pH</div><div className="font-medium">{aquaSpec.water_quality?.ph?.optimal?.[0]} – {aquaSpec.water_quality?.ph?.optimal?.[1]}</div></div>
                <div><div className="text-muted-foreground text-xs">Optimal DO</div><div className="font-medium">{aquaSpec.water_quality?.dissolved_oxygen_mg_l?.optimal} mg/L</div></div>
                <div><div className="text-muted-foreground text-xs">Min DO (stress)</div><div className="font-medium text-orange-500">{aquaSpec.water_quality?.dissolved_oxygen_mg_l?.minimum} mg/L</div></div>
                <div><div className="text-muted-foreground text-xs">Days to Harvest</div><div className="font-medium">{aquaSpec.growth?.days_to_harvest} days</div></div>
                <div><div className="text-muted-foreground text-xs">Growth Rate</div><div className="font-medium">{aquaSpec.growth?.average_g_per_day} g/day</div></div>
              </CardContent>
            </Card>
          )}

          {thermalEng && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Thermometer className="h-5 w-5 text-red-500" /> Thermal Engineering Analysis</CardTitle></CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div><div className="text-muted-foreground text-xs">Server Heat Output</div><div className="font-medium">{thermalEng.server_heat_output?.total_tdp_w} W</div></div>
                  <div><div className="text-muted-foreground text-xs">Heat Recovered (HX)</div><div className="font-medium text-emerald-500">{thermalEng.server_heat_output?.heat_recovered_via_hx_w} W</div></div>
                  <div><div className="text-muted-foreground text-xs">HX Efficiency</div><div className="font-medium">{(thermalEng.server_heat_output?.hx_efficiency * 100).toFixed(0)}%</div></div>
                  <div><div className="text-muted-foreground text-xs">Water Volume</div><div className="font-medium">{thermalEng.water_system?.total_volume_l} L</div></div>
                  <div><div className="text-muted-foreground text-xs">Temp Rise / Hour</div><div className="font-medium">{thermalEng.water_system?.temp_rise_per_hour_c}°C</div></div>
                  <div><div className="text-muted-foreground text-xs">Grow Bed Loss</div><div className="font-medium text-red-500">{thermalEng.heat_losses?.grow_bed_loss_w} W</div></div>
                  <div><div className="text-muted-foreground text-xs">Earth Berm Loss</div><div className="font-medium">{thermalEng.heat_losses?.earth_loss_w} W</div></div>
                  <div><div className="text-muted-foreground text-xs">Evap Cooling</div><div className="font-medium">{thermalEng.heat_losses?.evaporative_cooling_w} W</div></div>
                  <div><div className="text-muted-foreground text-xs">Makeup Cooling</div><div className="font-medium">{thermalEng.heat_losses?.makeup_water_cooling_w} W</div></div>
                  <div className="col-span-2 md:col-span-3"><div className="text-muted-foreground text-xs">Net Thermal Balance</div><div className={`font-bold text-lg ${thermalEng.net_balance_w >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{thermalEng.net_balance_w >= 0 ? '+' : ''}{thermalEng.net_balance_w} W</div></div>
                </div>
                <div className="rounded-md bg-yellow-500/10 border border-yellow-500/30 px-3 py-2 text-xs text-yellow-400">{thermalEng.recommendation}</div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* BUILD GUIDE TAB */}
      {/* ═══════════════════════════════════════════════════════ */}
      {activeTab === 'build' && (
        <div className="space-y-6 max-w-3xl">
          <h2 className="text-lg font-semibold flex items-center gap-2"><BookOpen className="h-5 w-5 text-purple-500" /> Physical Build Guide</h2>

          <Card><CardHeader><CardTitle>Phase 1: Earth Berm Excavation</CardTitle></CardHeader><CardContent className="text-sm space-y-2">
            <p>Excavate a 4m × 8m × 2.5m pit. Slope walls at 45° for stability. Line with 200mm rigid XPS foam insulation (U-value ≈ 0.05). Place 6mil polyethylene vapor barrier between soil and foam.</p>
            <p><strong>Concrete pad:</strong> Pour 150mm reinforced slab with 1% slope toward central drain sump. Install 4" PVC drain pipe with check valve before backfill.</p>
          </CardContent></Card>

          <Card><CardHeader><CardTitle>Phase 2: Tank & Grow Bed Installation</CardTitle></CardHeader><CardContent className="text-sm space-y-2">
            <p><strong>Tanks:</strong> Two 5,000L HDPE cylindrical tanks (2m dia × 1.6m height). Place on foam bedding. Connect with 2" PVC overflow weir at 1.5m height.</p>
            <p><strong>Grow Beds:</strong> Four 2,000L DWC raft beds (2m × 1m × 0.3m depth). Construct from food-grade HDPE liner over 2×4 frame. Drill 5cm net pot holes on 20cm grid.</p>
            <p><strong>Biofilter:</strong> 200L moving bed biofilter (MBBR) with K1 media. Air lift pump recirculates from sump through biofilter to tanks.</p>
          </CardContent></Card>

          <Card><CardHeader><CardTitle>Phase 3: Server Room & Heat Exchanger</CardTitle></CardHeader><CardContent className="text-sm space-y-2">
            <p><strong>Server Room:</strong> 2m × 3m × 2.2m insulated closet adjacent to tanks. Install 4-post rack. Run 1" PEX glycol loop from each server water block to plate HX.</p>
            <p><strong>Heat Exchanger:</strong> Mount 30-plate brazed HX on wall between server room and tank area. Hot glycol inlet at TOP. Warm water outlet at TOP (counter-flow). Insulate all pipes with Armaflex.</p>
            <p><strong>Glycol Mix:</strong> 50/50 propylene glycol + distilled water. Add corrosion inhibitor. Expansion tank rated for 150kPa.</p>
          </CardContent></Card>

          <Card><CardHeader><CardTitle>Phase 4: Electrical & Control</CardTitle></CardHeader><CardContent className="text-sm space-y-2">
            <p><strong>Main Panel:</strong> 100A subpanel with GFCI breaker on EVERY circuit touching water. 15A for pumps, 20A for server rack, 15A for heaters.</p>
            <p><strong>Controllers:</strong> Mount 4× NEMA 4X enclosures on wall. Run 22 AWG sensor cables through liquid-tight conduit. Use Wago lever nuts for all terminations — no wire nuts near moisture.</p>
            <p><strong>Network:</strong> Run CAT6 to Pi 5 in server room. ESP32s on dedicated IoT VLAN. MQTT broker on Pi for local message bus.</p>
          </CardContent></Card>

          <Card><CardHeader><CardTitle>Phase 5: Commissioning</CardTitle></CardHeader><CardContent className="text-sm space-y-2">
            <p>1. Fill tanks with dechlorinated water. Cycle for 7 days before adding fish.</p>
            <p>2. Seed biofilter with commercial nitrifying bacteria (FritzZyme 7).</p>
            <p>3. Add tilapia fingerlings (10g) at 20 kg/m³ density. Gradually increase to 40 kg/m³ over 60 days.</p>
            <p>4. Start servers at 30% load. Monitor tank temps for 48 hours before increasing load.</p>
            <p>5. Calibrate pH and DO probes with fresh buffer solutions. Log calibration dates.</p>
          </CardContent></Card>
        </div>
      )}
    </div>
  )
}

// ─── REPORT TEXT GENERATOR ───
function generateReportText(report: BuildReport): string {
  return `# OrbStudio Build Analysis Report
## ${report.profile_name}
Generated: ${report.generated_at}

---

## COST SUMMARY
- Total Cost: $${report.total_cost_usd.toFixed(2)}
- Suppliers Needed: ${report.suppliers_needed}
- Max Shipping Time: ${report.max_shipping_days} days
- Local vs Online: ${report.local_vs_online_pct[0]}% / ${report.local_vs_online_pct[1]}%

## THERMAL ANALYSIS
- Server Heat Output: ${report.server_heat_output_w} W
- Heat Recovered: ${report.heat_recovered_w} W
- Net Balance: ${report.net_thermal_balance_w} W
- Equilibrium Temp: ${report.equilibrium_temp_c}°C
- Recommendation: ${report.thermal_recommendation}

## AQUACULTURE FORECAST
- Species: ${report.species}
- Max Stocking: ${report.max_stocking_kg} kg
- Annual Yield: ${report.estimated_yield_kg_per_year} kg
- Feed Cost/Year: $${report.feed_cost_usd_per_year}

## ROI
- Break-even: ${report.roi_months.toFixed(1)} months
- ${report.break_even_analysis}

## RISK REGISTER
${report.risks.map(r => `- [${r.level}] ${r.category}: ${r.description}`).join('\n')}

## COST BY CATEGORY
${Object.entries(report.cost_by_category).map(([k, v]) => `- ${k}: $${(v as number).toFixed(2)}`).join('\n')}
`
}
