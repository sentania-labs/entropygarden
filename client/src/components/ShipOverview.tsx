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

  return (
    <div className="p-4 space-y-6">
      {/* Ship status */}
      <div className="flex flex-wrap items-end gap-6 border-b border-border pb-4">
        <div>
          <div className="text-dim text-[10px] tracking-widest mb-1">TOTAL POPULATION</div>
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
