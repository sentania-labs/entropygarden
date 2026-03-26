import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { GameSummary } from '../types'

export function useGameSocket(gameId: string | null) {
  const [summary, setSummary] = useState<GameSummary | null>(null)
  const [connected, setConnected] = useState(false)
  const activeRef = useRef(true)

  useEffect(() => {
    if (!gameId) {
      setSummary(null)
      setConnected(false)
      return
    }

    activeRef.current = true
    let ws: WebSocket
    let retryTimer: ReturnType<typeof setTimeout>

    const connect = () => {
      ws = new WebSocket(api.wsUrl(gameId))

      ws.onopen = () => {
        if (activeRef.current) setConnected(true)
      }
      ws.onclose = () => {
        if (activeRef.current) {
          setConnected(false)
          retryTimer = setTimeout(connect, 2000)
        }
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        if (!activeRef.current) return
        try {
          const msg = JSON.parse(e.data as string) as { type: string; data: GameSummary }
          if (msg.type === 'state') setSummary(msg.data)
        } catch { /* ignore malformed frames */ }
      }
    }

    connect()

    return () => {
      activeRef.current = false
      clearTimeout(retryTimer)
      ws?.close()
    }
  }, [gameId])

  return { summary, connected }
}
