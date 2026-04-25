import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DecisionWindow, GameSummary } from '../types'

type WindowMsg = {
  type: 'decision_window'
  window_id: string | null
  closes_tick: number | null
  tick: number
}

export function useGameSocket(gameId: string | null) {
  const [summary, setSummary] = useState<GameSummary | null>(null)
  const [connected, setConnected] = useState(false)
  const [window, setWindow] = useState<DecisionWindow | null>(null)
  const activeRef = useRef(true)

  useEffect(() => {
    if (!gameId) {
      setSummary(null)
      setConnected(false)
      setWindow(null)
      return
    }

    activeRef.current = true
    let ws: WebSocket
    let retryTimer: ReturnType<typeof setTimeout>

    // Fetch current window state on connect (in case we missed the broadcast)
    api.getCurrentWindow(gameId).then(w => {
      if (activeRef.current) setWindow(w)
    }).catch(() => {})

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
          const msg = JSON.parse(e.data as string) as { type: string; data?: GameSummary }
          if (msg.type === 'state' && msg.data) {
            setSummary(msg.data)
          } else if (msg.type === 'decision_window') {
            const wm = msg as unknown as WindowMsg
            if (wm.window_id) {
              setWindow({
                window_id: wm.window_id,
                opened_tick: wm.tick,
                closes_tick: wm.closes_tick!,
                status: 'open',
                submitted: [],
              })
            } else {
              setWindow(null)
            }
          }
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

  return { summary, connected, window }
}
