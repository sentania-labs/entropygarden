import { useState } from 'react'
import { api } from '../api'
import { useEvents } from '../hooks/useEvents'
import { useGameSocket } from '../hooks/useGameSocket'
import { useHistory } from '../hooks/useHistory'
import type { Role, Tab } from '../types'
import { Header } from './Header'
import { RingView } from './RingView'
import { ShipOverview } from './ShipOverview'

const TABS: { id: Tab; label: string }[] = [
  { id: 'ship',   label: 'SHIP'   },
  { id: 'ring_1', label: 'RING 1' },
  { id: 'ring_2', label: 'RING 2' },
  { id: 'ring_3', label: 'RING 3' },
]

interface Props {
  gameId: string
  onExit: () => void
}

export function Dashboard({ gameId, onExit }: Props) {
  const [role, setRole] = useState<Role>('captain')
  const [tab,  setTab]  = useState<Tab>('ship')

  const { summary, connected } = useGameSocket(gameId)
  const events  = useEvents(gameId)
  const history = useHistory(gameId)

  if (!summary) {
    return (
      <div className="flex items-center justify-center h-full text-dim text-sm">
        <span className="animate-pulse">CONNECTING TO SHIP SYSTEMS...</span>
      </div>
    )
  }

  // Ring delegate only sees ship overview + their assigned ring (ring_1 by default for MVP)
  const visibleTabs = role === 'ring_delegate'
    ? TABS.filter(t => t.id === 'ship' || t.id === 'ring_1')
    : TABS

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <Header
        summary={summary}
        connected={connected}
        role={role}
        onRoleChange={(r) => { setRole(r); setTab('ship') }}
        onPause={()  => api.pauseGame(gameId).catch(() => {})}
        onResume={() => api.resumeGame(gameId).catch(() => {})}
        onExit={onExit}
      />

      {/* Tab bar */}
      <nav className="flex border-b border-border bg-surface shrink-0">
        {visibleTabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-[11px] tracking-widest border-b-2 transition-colors ${
              tab === t.id
                ? 'border-amber text-amber'
                : 'border-transparent text-dim hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-y-auto bg-bg">
        {tab === 'ship' ? (
          <ShipOverview
            summary={summary}
            events={events}
            history={history}
            role={role}
            onSelectRing={id => setTab(id as Tab)}
          />
        ) : (
          <RingView
            ringId={tab}
            summary={summary}
            events={events}
            history={history}
            role={role}
          />
        )}
      </main>
    </div>
  )
}
