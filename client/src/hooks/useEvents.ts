import { useEffect, useState } from 'react'
import { api } from '../api'
import type { EventRecord } from '../types'

export function useEvents(gameId: string | null) {
  const [events, setEvents] = useState<EventRecord[]>([])

  useEffect(() => {
    if (!gameId) { setEvents([]); return }

    let active = true
    const fetch = async () => {
      try {
        const data = await api.getEvents(gameId)
        if (active) setEvents(data)
      } catch { /* server may not be ready */ }
    }

    fetch()
    const id = setInterval(fetch, 10_000)
    return () => { active = false; clearInterval(id) }
  }, [gameId])

  return events
}
