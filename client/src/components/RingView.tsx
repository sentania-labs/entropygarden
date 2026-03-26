import type { EventRecord, GameSummary, HistoryPoint, Role } from '../types'
import { EventFeed } from './EventFeed'
import { ResourceBar } from './ResourceBar'
import { SignalPanel } from './SignalPanel'

const CAPACITY = 500

interface Props {
  ringId: string
  summary: GameSummary
  events: EventRecord[]
  history: HistoryPoint[]
  role: Role
}

export function RingView({ ringId, summary, events, history, role }: Props) {
  const ring = summary.rings[ringId]
  if (!ring) return <div className="p-4 text-dim text-sm">Ring data unavailable.</div>

  const resHistory = (key: 'food' | 'water' | 'oxygen' | 'power') =>
    history.map(p => p.rings[ringId]?.[key] ?? 0)

  const moraleHistory = history.map(p => (p.rings[ringId]?.mean_morale ?? 0) * CAPACITY)

  const morale = ring.mean_morale
  const moraleColor = morale > 0.55 ? '#3fb950' : morale > 0.3 ? '#e6a817' : '#f85149'

  return (
    <div className="p-4 space-y-6">
      {/* Ring header */}
      <div className="flex flex-wrap items-end gap-6 border-b border-border pb-4">
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">POPULATION</div>
          <div className="text-amber text-2xl font-semibold tabular-nums">{ring.population}</div>
        </div>
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">MEAN HEALTH</div>
          <div className={`text-lg tabular-nums ${ring.mean_health < 0.3 ? 'text-red' : 'text-text'}`}>
            {Math.round(ring.mean_health * 100)}%
          </div>
        </div>
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">MEAN MORALE</div>
          <div className={`text-lg tabular-nums ${morale < 0.4 ? 'text-amber' : 'text-text'}`}>
            {Math.round(morale * 100)}%
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Resources */}
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-3">RESOURCES</div>
          <div className="space-y-0.5">
            <ResourceBar name="food"   value={ring.resources.food}   history={resHistory('food')} />
            <ResourceBar name="water"  value={ring.resources.water}  history={resHistory('water')} />
            <ResourceBar name="oxygen" value={ring.resources.oxygen} history={resHistory('oxygen')} />
            <ResourceBar name="power"  value={ring.resources.power}  history={resHistory('power')} />
            <div className="pt-2 border-t border-border mt-2">
              <div className="flex items-center gap-2 py-[3px]">
                <span className="w-14 text-dim uppercase text-[11px] tracking-wider shrink-0">morale</span>
                <div className="flex-1 h-[6px] bg-surface-2 rounded-sm overflow-hidden">
                  <div
                    className="h-full rounded-sm transition-[width] duration-700"
                    style={{ width: `${Math.round(morale * 100)}%`, backgroundColor: moraleColor }}
                  />
                </div>
                <span className="w-7 text-right text-[11px] text-dim tabular-nums shrink-0">
                  {Math.round(morale * 100)}%
                </span>
                {history.length > 4 && (
                  <svg width={64} height={16} className="inline-block opacity-60 shrink-0">
                    <polyline
                      points={moraleHistory.map((v, i) => {
                        const x = ((i / (moraleHistory.length - 1)) * 64).toFixed(1)
                        const y = Math.max(0, Math.min(16, 16 - (v / CAPACITY) * 16)).toFixed(1)
                        return `${x},${y}`
                      }).join(' ')}
                      fill="none"
                      stroke={moraleColor}
                      strokeWidth="1.5"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Signals */}
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-3">SIGNALS</div>
          <SignalPanel events={events} ringId={ringId} history={history} role={role} />
        </div>
      </div>

      {/* Ring events */}
      <div>
        <div className="text-dim text-[10px] tracking-widest mb-3">RING LOG</div>
        <EventFeed events={events} ringId={ringId} maxItems={8} />
      </div>
    </div>
  )
}
