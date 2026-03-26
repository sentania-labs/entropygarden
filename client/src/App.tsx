import { useState } from 'react'
import { Dashboard } from './components/Dashboard'
import { GameLobby } from './components/GameLobby'

export default function App() {
  const [gameId, setGameId] = useState<string | null>(null)

  return (
    <div className="h-screen bg-bg text-text font-mono overflow-hidden">
      {gameId
        ? <Dashboard gameId={gameId} onExit={() => setGameId(null)} />
        : <GameLobby onSelect={setGameId} />
      }
    </div>
  )
}
