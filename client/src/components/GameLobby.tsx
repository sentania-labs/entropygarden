import { useEffect, useState } from 'react'
import { api } from '../api'
import type { GameListItem } from '../types'

interface Props { onSelect: (gameId: string) => void }

export function GameLobby({ onSelect }: Props) {
  const [games,    setGames]    = useState<GameListItem[]>([])
  const [loading,  setLoading]  = useState(true)
  const [creating, setCreating] = useState(false)
  const [seed,     setSeed]     = useState(42)
  const [tickRate, setTickRate] = useState(2)

  const refresh = async () => {
    try { setGames(await api.listGames()) } catch { /* server may be starting */ }
    setLoading(false)
  }

  useEffect(() => { void refresh() }, [])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const g = await api.createGame(seed, tickRate)
      onSelect(g.game_id)
    } catch { setCreating(false) }
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try { await api.deleteGame(id); await refresh() } catch {}
  }

  return (
    <div className="min-h-full flex flex-col items-center justify-center p-8 bg-bg">
      <div className="w-full max-w-xl space-y-8">

        {/* Title */}
        <div className="text-center space-y-2">
          <div className="text-amber text-3xl font-semibold tracking-[0.35em]">ENTROPY GARDEN</div>
          <div className="text-dim text-[11px] tracking-[0.25em]">GENERATION SHIP SIMULATION</div>
          <div className="text-border text-[10px] mt-1">────────────────────────────────</div>
        </div>

        {/* Create game */}
        <div className="border border-border rounded p-4 space-y-4 bg-surface">
          <div className="text-dim text-[10px] tracking-widest">INITIALIZE NEW MISSION</div>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1">
              <label className="text-dim text-[10px] tracking-wider block">SEED</label>
              <input
                type="number"
                value={seed}
                onChange={e => setSeed(parseInt(e.target.value) || 0)}
                className="bg-surface-2 border border-border rounded px-2 py-1 text-text w-24 text-xs font-mono"
              />
            </div>
            <div className="space-y-1">
              <label className="text-dim text-[10px] tracking-wider block">TICK RATE</label>
              <input
                type="number"
                value={tickRate}
                min={0.1}
                max={100}
                step={0.5}
                onChange={e => setTickRate(parseFloat(e.target.value) || 1)}
                className="bg-surface-2 border border-border rounded px-2 py-1 text-text w-28 text-xs font-mono"
              />
            </div>
            <button
              onClick={handleCreate}
              disabled={creating}
              className="px-4 py-1.5 border border-amber text-amber rounded text-xs tracking-wider hover:bg-amber/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {creating ? 'INITIALIZING...' : '▶ LAUNCH MISSION'}
            </button>
          </div>
        </div>

        {/* Game list */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <div className="text-dim text-[10px] tracking-widest">ACTIVE MISSIONS</div>
            <button
              onClick={refresh}
              className="text-dim text-[11px] hover:text-text transition-colors"
            >
              ↻ REFRESH
            </button>
          </div>

          {loading && (
            <p className="text-dim text-xs py-4 text-center animate-pulse">SCANNING...</p>
          )}
          {!loading && games.length === 0 && (
            <div className="border border-border rounded p-6 text-center text-dim text-xs bg-surface">
              No active missions found. Initialize one above.
            </div>
          )}

          {games.map(g => (
            <div
              key={g.game_id}
              onClick={() => onSelect(g.game_id)}
              className="flex items-center justify-between border border-border rounded p-3 hover:border-amber cursor-pointer group transition-colors bg-surface"
            >
              <div className="space-y-0.5 min-w-0">
                <div className="text-[10px] text-dim font-mono">{g.game_id.slice(0, 14)}…</div>
                <div className="text-xs text-text tabular-nums">
                  Year {g.year.toFixed(1)} · Day {g.tick.toLocaleString()} · Pop {g.total_population.toLocaleString()}
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border tracking-wider ${
                  g.paused ? 'border-dim text-dim' : 'border-green text-green'
                }`}>
                  {g.paused ? 'PAUSED' : 'RUNNING'}
                </span>
                <span className="text-[10px] text-dim">{g.tick_rate}×</span>
                <button
                  onClick={e => handleDelete(g.game_id, e)}
                  className="text-dim hover:text-red transition-colors text-xs px-1 opacity-0 group-hover:opacity-100"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}
