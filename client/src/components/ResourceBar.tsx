import { Sparkline } from './Sparkline'

const CAPACITY = 500

const RESOURCE_ACCENT: Record<string, string> = {
  food:   '#3fb950',
  water:  '#58a6ff',
  oxygen: '#79c0ff',
  power:  '#e6a817',
}

function barColor(pct: number): string {
  if (pct > 0.55) return '#3fb950'
  if (pct > 0.25) return '#e6a817'
  return '#f85149'
}

interface Props {
  name: string
  value: number
  capacity?: number
  history?: number[]
}

export function ResourceBar({ name, value, capacity = CAPACITY, history }: Props) {
  const pct = Math.min(value / capacity, 1)
  const pctInt = Math.round(pct * 100)
  const alert = pct < 0.2
  const accent = RESOURCE_ACCENT[name]

  return (
    <div className="flex items-center gap-2 py-[3px]">
      <span className="w-14 text-dim uppercase text-[11px] tracking-wider shrink-0">{name}</span>

      <div className="flex-1 h-[6px] bg-surface-2 rounded-sm overflow-hidden">
        <div
          className="h-full rounded-sm transition-[width] duration-700"
          style={{ width: `${pctInt}%`, backgroundColor: barColor(pct) }}
        />
      </div>

      <span className={`w-7 text-right text-[11px] tabular-nums shrink-0 ${alert ? 'text-red' : 'text-dim'}`}>
        {pctInt}%
      </span>

      {history && history.length > 4 && (
        <Sparkline data={history} min={0} max={capacity} color={accent ?? barColor(pct)} />
      )}

      {alert && <span className="text-red text-[10px] shrink-0">!</span>}
    </div>
  )
}
