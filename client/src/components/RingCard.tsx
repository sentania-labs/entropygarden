import type { EventRecord, GameSummary } from '../types'

const CAPACITY = 500
const CRIT_IDS = new Set(['reactor_instability', 'atmosphere_contamination', 'food_riots'])

function fillBar(pct: number, len = 7): string {
  const n = Math.round(Math.max(0, Math.min(1, pct)) * len)
  return '█'.repeat(n) + '░'.repeat(len - n)
}

function barClass(pct: number): string {
  if (pct > 0.55) return 'text-green'
  if (pct > 0.25) return 'text-amber'
  return 'text-red'
}

interface Props {
  ringId: string
  summary: GameSummary
  events: EventRecord[]
  active: boolean
  onClick: () => void
}

export function RingCard({ ringId, summary, events, active, onClick }: Props) {
  const ring = summary.rings[ringId]
  if (!ring) return null

  const fp = ring.resources.food   / CAPACITY
  const op = ring.resources.oxygen / CAPACITY
  const wp = ring.resources.water  / CAPACITY
  const pp = ring.resources.power  / CAPACITY

  const alerts = events.filter(e =>
    (e.ring_id === ringId || e.ring_id === null) &&
    e.tick >= summary.tick - 90 &&
    CRIT_IDS.has(e.event_id),
  ).length

  return (
    <button
      onClick={onClick}
      className={`text-left p-3 border rounded transition-colors w-full ${
        active
          ? 'border-amber bg-surface-2'
          : 'border-border bg-surface hover:border-dim'
      }`}
    >
      <div className="flex justify-between items-baseline mb-2">
        <span className={`text-[11px] font-semibold tracking-widest ${active ? 'text-amber' : 'text-dim'}`}>
          {ringId.replace('_', ' ').toUpperCase()}
        </span>
        <span className="text-[11px] text-dim tabular-nums">POP {ring.population}</span>
      </div>

      <div className="space-y-[2px] font-mono text-[11px]">
        {([['FD', fp], ['O2', op], ['H2O', wp], ['PWR', pp]] as [string, number][]).map(([lbl, pct]) => (
          <div key={lbl} className="flex items-center gap-1.5">
            <span className="text-dim w-6 shrink-0">{lbl}</span>
            <span className={barClass(pct)}>{fillBar(pct)}</span>
            <span className="text-dim w-6 tabular-nums text-right">{Math.round(pct * 100)}%</span>
          </div>
        ))}
      </div>

      <div className="mt-2 flex justify-between text-[11px]">
        <span className="text-dim">MRL {Math.round(ring.mean_morale * 100)}%</span>
        <span className="text-dim">HLT {Math.round(ring.mean_health * 100)}%</span>
        {alerts > 0 && <span className="text-red">! {alerts}</span>}
      </div>
    </button>
  )
}
