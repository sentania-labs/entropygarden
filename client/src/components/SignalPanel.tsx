import type { EventRecord, HistoryPoint, Role } from '../types'

type Level = 'NOMINAL' | 'ELEVATED' | 'CRITICAL'

interface Signal { label: string; level: Level; detail: string }

const MAINT_IDS  = new Set(['hull_microfracture', 'reactor_instability', 'water_recycler_failure', 'equipment_malfunction'])
const ECO_IDS    = new Set(['crop_blight', 'atmosphere_contamination', 'fungal_bloom', 'contaminated_water'])
const SOCIAL_IDS = new Set(['labor_unrest', 'food_riots'])

function countRecent(events: EventRecord[], ids: Set<string>, ringId: string, windowTicks: number): number {
  const maxTick = events.length ? Math.max(...events.map(e => e.tick)) : 0
  return events.filter(e =>
    e.tick >= maxTick - windowTicks &&
    ids.has(e.event_id) &&
    (e.ring_id === ringId || e.ring_id === null),
  ).length
}

function fromCount(n: number): Level {
  if (n === 0) return 'NOMINAL'
  if (n <= 2)  return 'ELEVATED'
  return 'CRITICAL'
}

type NumKey = 'mean_health' | 'mean_morale' | 'food' | 'water' | 'oxygen' | 'power'

function trendStr(history: HistoryPoint[], ringId: string, key: NumKey): string {
  if (history.length < 12) return 'insufficient data'
  const slice = (a: number, b: number) => history.slice(a, b).map(p => {
    const r = p.rings[ringId]
    if (!r) return 0
    return (r as Record<string, number>)[key] ?? 0
  })
  const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
  const delta = avg(slice(-5, history.length)) - avg(slice(-20, -15))
  if (Math.abs(delta) < 0.005) return 'stable'
  const pct = (delta * 100).toFixed(1)
  return delta > 0 ? `+${pct}%` : `${pct}%`
}

function levelClass(l: Level): string {
  if (l === 'NOMINAL')  return 'text-green'
  if (l === 'ELEVATED') return 'text-amber'
  return 'text-red'
}

function deriveSignals(events: EventRecord[], ringId: string, history: HistoryPoint[], role: Role): Signal[] {
  const w = 90
  const out: Signal[] = []

  // Technical signals — visible to engineer, ecologist, captain
  if (role !== 'governor' && role !== 'ring_delegate') {
    const n = countRecent(events, MAINT_IDS, ringId, w)
    out.push({ label: 'MAINTENANCE', level: fromCount(n),
      detail: n === 0 ? 'no incidents (90d)' : `${n} incident${n > 1 ? 's' : ''} (90d)` })

    const e = countRecent(events, ECO_IDS, ringId, w)
    out.push({ label: 'ECOLOGY', level: fromCount(e),
      detail: e === 0 ? 'no incidents (90d)' : `${e} incident${e > 1 ? 's' : ''} (90d)` })
  }

  // Social signals — visible to governor, ring_delegate, captain
  if (role !== 'engineer' && role !== 'ecologist') {
    const s = countRecent(events, SOCIAL_IDS, ringId, w)
    out.push({ label: 'SOCIAL', level: fromCount(s),
      detail: s === 0 ? 'no incidents (90d)' : `${s} incident${s > 1 ? 's' : ''} (90d)` })
  }

  // Trend signals — always shown
  const moraleTrend = trendStr(history, ringId, 'mean_morale')
  const moraleAlert = moraleTrend.startsWith('-') && Math.abs(parseFloat(moraleTrend)) > 5
  out.push({ label: 'MORALE TREND', level: moraleAlert ? 'ELEVATED' : 'NOMINAL', detail: moraleTrend })

  const healthTrend = trendStr(history, ringId, 'mean_health')
  const healthAlert = healthTrend.startsWith('-') && Math.abs(parseFloat(healthTrend)) > 5
  out.push({ label: 'HEALTH TREND', level: healthAlert ? 'ELEVATED' : 'NOMINAL', detail: healthTrend })

  return out
}

interface Props { events: EventRecord[]; ringId: string; history: HistoryPoint[]; role: Role }

export function SignalPanel({ events, ringId, history, role }: Props) {
  const signals = deriveSignals(events, ringId, history, role)

  return (
    <div className="space-y-[5px]">
      {signals.map(s => (
        <div key={s.label} className="flex items-center gap-3 text-[11px]">
          <span className="w-28 text-dim tracking-wider shrink-0">{s.label}</span>
          <span className={`w-20 font-medium shrink-0 ${levelClass(s.level)}`}>{s.level}</span>
          <span className="text-dim">{s.detail}</span>
        </div>
      ))}
    </div>
  )
}
