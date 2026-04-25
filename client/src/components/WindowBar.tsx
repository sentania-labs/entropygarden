import type { DecisionWindow, GameSummary, Role } from '../types'

interface Props {
  window: DecisionWindow | null
  summary: GameSummary
  role: Role
}

export function WindowBar({ window: win, summary, role }: Props) {
  if (!win || win.status !== 'open') {
    return (
      <div className="flex items-center gap-2 px-4 py-1.5 bg-surface border-b border-border text-[10px] tracking-widest text-dim">
        <span className="w-1.5 h-1.5 rounded-full bg-dim/40 shrink-0" />
        NO ACTIVE DECISION WINDOW
      </div>
    )
  }

  const remaining = Math.max(0, win.closes_tick - summary.tick)
  const submitted = win.submitted.includes(role)

  return (
    <div className={`flex items-center gap-2 px-4 py-1.5 border-b border-border text-[10px] tracking-widest ${
      submitted ? 'bg-green/5 border-green/20' : 'bg-amber/5 border-amber/20'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
        submitted ? 'bg-green' : 'bg-amber animate-pulse'
      }`} />
      {submitted ? (
        <span className="text-green">ORDER TRANSMITTED — AWAITING WINDOW CLOSE</span>
      ) : (
        <span className="text-amber">
          DECISION WINDOW OPEN — {remaining} DAYS REMAINING
        </span>
      )}
      <span className="ml-auto text-dim tabular-nums">
        WINDOW {win.window_id.slice(0, 8)}
      </span>
    </div>
  )
}
