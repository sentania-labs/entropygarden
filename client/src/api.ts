import type { ActionRequest, ActionResponse, DecisionWindow, EventRecord, GameListItem, GameSummary, HistoryPoint } from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
export const WS_BASE = BASE.replace(/^http/, 'ws')

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error(`DELETE ${path} → ${res.status}`)
}

export const api = {
  listGames:  () => get<GameListItem[]>('/games'),
  createGame: (seed: number, tickRate: number, paused = false, destination = 'proxima') =>
    post<GameSummary>('/games', { seed, tick_rate: tickRate, paused, destination }),
  getGame:    (id: string) => get<GameSummary>(`/games/${id}`),
  getEvents:  (id: string, since = 0) => get<EventRecord[]>(`/games/${id}/events?since=${since}`),
  getHistory: (id: string, limit = 200) => get<HistoryPoint[]>(`/games/${id}/history?limit=${limit}`),
  pauseGame:  (id: string) => post<GameSummary>(`/games/${id}/pause`),
  resumeGame: (id: string) => post<GameSummary>(`/games/${id}/resume`),
  deleteGame: (id: string) => del(`/games/${id}`),
  wsUrl:      (id: string) => `${WS_BASE}/games/${id}/ws`,

  // Decision windows
  getCurrentWindow: (id: string) => get<DecisionWindow | null>(`/games/${id}/window/current`),
  submitAction:     (id: string, action: ActionRequest) =>
    post<ActionResponse>(`/games/${id}/window/action`, action),
}
