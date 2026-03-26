export type RingSummary = {
  population: number
  mean_health: number
  mean_morale: number
  resources: {
    food: number
    water: number
    oxygen: number
    power: number
  }
  pressures: {
    maintenance_debt: number
    ecological_drift: number
    social_tension: number
  }
}

export type GameSummary = {
  game_id: string
  seed: number
  tick: number
  year: number
  total_population: number
  tick_rate: number
  paused: boolean
  rings: Record<string, RingSummary>
}

export type GameListItem = {
  game_id: string
  seed: number
  tick: number
  year: number
  total_population: number
  tick_rate: number
  paused: boolean
}

export type EventRecord = {
  tick: number
  ring_id: string | null
  event_id: string
  event_name: string
  description: string
  effects_applied: Record<string, number>
}

export type RingHistoryPoint = {
  population: number
  mean_health: number
  mean_morale: number
  food: number
  water: number
  oxygen: number
  power: number
}

export type HistoryPoint = {
  tick: number
  year: number
  rings: Record<string, RingHistoryPoint>
}

export type Role = 'captain' | 'engineer' | 'ecologist' | 'governor' | 'ring_delegate'

export type Tab = 'ship' | 'ring_1' | 'ring_2' | 'ring_3'
