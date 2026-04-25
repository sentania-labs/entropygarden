import type { GameSummary, Role } from '../types'

const ROLES: { value: Role; label: string }[] = [
  { value: 'captain',       label: 'CAPTAIN'       },
  { value: 'engineer',      label: 'ENGINEER'      },
  { value: 'ecologist',     label: 'ECOLOGIST'     },
  { value: 'governor',      label: 'GOVERNOR'      },
  { value: 'ring_delegate', label: 'RING DELEGATE' },
]

interface Props {
  summary: GameSummary
  connected: boolean
  role: Role
  onRoleChange: (r: Role) => void
  onPause: () => void
  onResume: () => void
  onExit: () => void
}

export function Header({ summary, connected, role, onRoleChange, onPause, onResume, onExit }: Props) {
  return (
    <header className="flex items-center gap-3 px-4 py-2 border-b border-border bg-surface shrink-0 text-[11px]">
      <span className="text-amber font-semibold tracking-[0.2em] shrink-0">ENTROPY GARDEN</span>

      <span className="text-border select-none">│</span>

      <span className="text-dim tabular-nums shrink-0">YR {summary.year.toFixed(1)}</span>
      <span className="text-dim tabular-nums shrink-0">DAY {summary.tick.toLocaleString()}</span>
      <span className="text-dim tabular-nums shrink-0">POP {summary.total_population.toLocaleString()}</span>
      {summary.journey && (
        <>
          <span className="text-border select-none">│</span>
          <span className={`tabular-nums shrink-0 ${
            summary.journey.arrival_tick != null ? 'text-green' :
            summary.journey.fuel_pct <= 0 ? 'text-red' : 'text-amber'
          }`}>
            {summary.journey.destination.toUpperCase()} — {summary.journey.progress_pct.toFixed(1)}%
          </span>
        </>
      )}

      <span className="text-border select-none">│</span>

      <div className={`flex items-center gap-1 shrink-0 ${connected ? 'text-green' : 'text-red'}`}>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? 'bg-green' : 'bg-red'}`} />
        {connected ? 'LIVE' : 'RECONNECTING'}
      </div>

      <button
        onClick={summary.paused ? onResume : onPause}
        className={`px-2 py-0.5 border rounded transition-colors shrink-0 ${
          summary.paused
            ? 'border-green text-green hover:bg-green/10'
            : 'border-amber text-amber hover:bg-amber/10'
        }`}
      >
        {summary.paused ? '▶ RESUME' : '⏸ PAUSE'}
      </button>

      <div className="ml-auto flex items-center gap-2 shrink-0">
        <span className="text-dim">ROLE</span>
        <select
          value={role}
          onChange={e => onRoleChange(e.target.value as Role)}
          className="bg-surface border border-border text-text px-2 py-0.5 rounded text-[11px] cursor-pointer"
        >
          {ROLES.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>

        <button
          onClick={onExit}
          className="ml-1 text-dim hover:text-text transition-colors px-1"
        >
          ✕
        </button>
      </div>
    </header>
  )
}
