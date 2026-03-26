import { useEffect, useState } from 'react'
import { api } from '../api'
import type { HistoryPoint } from '../types'

export function useHistory(gameId: string | null) {
  const [history, setHistory] = useState<HistoryPoint[]>([])

  useEffect(() => {
    if (!gameId) { setHistory([]); return }

    let active = true
    const fetch = async () => {
      try {
        const data = await api.getHistory(gameId, 200)
        if (active) setHistory(data)
      } catch { /* history may be empty early in the game */ }
    }

    fetch()
    const id = setInterval(fetch, 15_000)
    return () => { active = false; clearInterval(id) }
  }, [gameId])

  return history
}
