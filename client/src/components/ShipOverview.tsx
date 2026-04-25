import type { EventRecord, GameSummary, HistoryPoint, Role } from '../types'
import { EventFeed } from './EventFeed'
import { RingCard } from './RingCard'

const CRIT_IDS = new Set(['reactor_instability', 'atmosphere_contamination', 'food_riots'])

interface Props {
  summary: GameSummary
  events: EventRecord[]
  history: HistoryPoint[]
  role: Role
  onSelectRing: (ringId: string) => void
}

export function ShipOverview({ summary, events, role: _role, onSelectRing }: Props) {
  const ringIds = Object.keys(summary.rings).sort()
  const recentAlerts = events.filter(e => e.tick >= summary.tick - 30 && CRIT_IDS.has(e.event_id))
  const j = summary.journey

  return (
    <div className="p-4 space-y-6">
      {/* Journey progress */}
      {j && (
        <div className="border border-border rounded bg-surface p-3 space-y-2">
          <div className="flex items-center justify-between text-[10px] tracking-widest">
            <span className="text-amber font-semibold">DESTINATION: {j.destination.toUpperCase()}</span>
            {j.arrival_tick != null ? (
              <span className="text-green">ARRIVED — DAY {j.arrival_tick.toLocaleString()}</span>
            ) : j.fuel_pct <= 0 ? (
              <span className="text-red">STRANDED — NO FUEL</span>
            ) : (
              <span className="text-dim">
                ETA {j.eta_ticks != null ? `${Math.round(j.eta_ticks / 365)} YR` : '---'}
              </span>
            )}
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-bg rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm transition-[width] duration-1000"
                style={{
                  width: `${Math.min(100, j.progress_pct)}%`,
                  backgroundColor: j.arrival_tick != null ? '#3fb950' : '#e6a817',
                }}
              />
            </div>
            <span className="text-[11px] text-amber tabular-nums w-12 text-right shrink-0">
              {j.progress_pct.toFixed(1)}%
            </span>
          </div>

          {/* Stats row */}
          <div className="flex flex-wrap gap-4 text-[10px] tracking-wider">
            <div>
              <span className="text-dim">DISTANCE </span>
              <span className="text-text tabular-nums">
                {(j.total_distance_ly - j.distance_remaining_ly).toFixed(2)} / {j.total_distance_ly} LY
              </span>
            </div>
            <div>
              <span className="text-dim">FUEL </span>
              <span className={`tabular-nums ${j.fuel_pct < 20 ? 'text-red' : j.fuel_pct < 40 ? 'text-amber' : 'text-text'}`}>
                {j.fuel_pct.toFixed(1)}%
              </span>
            </div>
            <div>
              <span className="text-dim">EFFICIENCY </span>
              <span className={`tabular-nums ${j.fuel_efficiency < 0.6 ? 'text-red' : j.fuel_efficiency < 0.8 ? 'text-amber' : 'text-text'}`}>
                {Math.round(j.fuel_efficiency * 100)}%
              </span>
            </div>
            {j.next_milestone && (
              <div>
                <span className="text-dim">NEXT </span>
                <span className="text-text">{j.next_milestone.toUpperCase()}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Ship status */}
      <div className="flex flex-wrap items-end gap-6 border-b border-border pb-4">
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">TOTAL SETTLERS</div>
          <div className="text-amber text-2xl font-semibold tabular-nums">
            {summary.total_population.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">SHIP YEAR</div>
          <div className="text-text text-lg tabular-nums">{summary.year.toFixed(1)}</div>
        </div>
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">SIM DAY</div>
          <div className="text-text tabular-nums">{summary.tick.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">TICK RATE</div>
          <div className="text-text tabular-nums">{summary.tick_rate}×</div>
        </div>
        {recentAlerts.length > 0 && (
          <div className="ml-auto flex items-center gap-1.5 text-red text-xs">
            <span>!</span>
            <span>{recentAlerts.length} CRITICAL ALERT{recentAlerts.length > 1 ? 'S' : ''} (LAST 30 DAYS)</span>
          </div>
        )}
      </div>

      {/* Ring cards */}
      <div>
        <div className="text-dim text-[10px] tracking-widest mb-3">RING STATUS — click to inspect</div>
        <div className="grid grid-cols-3 gap-3">
          {ringIds.map(id => (
            <RingCard
              key={id}
              ringId={id}
              summary={summary}
              events={events}
              active={false}
              onClick={() => onSelectRing(id)}
            />
          ))}
        </div>
      </div>

      {/* Event feed */}
      <div>
        <div className="text-dim text-[10px] tracking-widest mb-3">SHIP LOG</div>
        <EventFeed events={events} maxItems={15} />
      </div>
    </div>
  )
}
