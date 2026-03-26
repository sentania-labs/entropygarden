import type { EventRecord } from '../types'

const SEVERITY: Record<string, 'crit' | 'warn' | 'good' | 'info'> = {
  hull_microfracture:       'warn',
  reactor_instability:      'crit',
  water_recycler_failure:   'warn',
  crop_blight:              'warn',
  atmosphere_contamination: 'crit',
  labor_unrest:             'warn',
  food_riots:               'crit',
  equipment_malfunction:    'warn',
  fungal_bloom:             'info',
  community_festival:       'good',
  contaminated_water:       'warn',
  stellar_radiation:        'warn',
}

const SEV_CLASS = { crit: 'text-red', warn: 'text-amber', good: 'text-green', info: 'text-blue' }

function effectSummary(effects: Record<string, number>): string {
  return Object.entries(effects)
    .filter(([, v]) => Math.abs(v) > 0.0001)
    .map(([k, v]) => `${v > 0 ? '+' : ''}${v.toFixed(3)} ${k.replace(/_/g, ' ')}`)
    .join('  ')
}

interface Props {
  events: EventRecord[]
  ringId?: string
  maxItems?: number
}

export function EventFeed({ events, ringId, maxItems = 12 }: Props) {
  const filtered = events
    .filter(e => !ringId || e.ring_id === ringId || e.ring_id === null)
    .slice(-maxItems)
    .reverse()

  if (filtered.length === 0) {
    return <p className="text-dim text-xs py-2 italic">No events recorded.</p>
  }

  return (
    <div className="space-y-[3px] font-mono">
      {filtered.map((e, i) => {
        const sev = SEVERITY[e.event_id] ?? 'info'
        return (
          <div key={i} className="flex gap-2 items-baseline text-[11px] leading-5">
            <span className="text-dim shrink-0 tabular-nums w-[72px]">
              yr {(e.tick / 365).toFixed(2)}
            </span>
            <span className={`shrink-0 w-[52px] ${e.ring_id ? 'text-cyan' : 'text-blue'}`}>
              {e.ring_id ? e.ring_id.replace('_', ' ').toUpperCase() : 'SHIP  '}
            </span>
            <span className={`shrink-0 ${SEV_CLASS[sev]}`}>{e.event_name}</span>
            <span className="text-dim truncate text-[10px]">{effectSummary(e.effects_applied)}</span>
          </div>
        )
      })}
    </div>
  )
}
