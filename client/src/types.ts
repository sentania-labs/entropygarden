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

export type JourneySummary = {
  destination: string
  total_distance_ly: number
  distance_remaining_ly: number
  progress_pct: number
  fuel_pct: number
  fuel_efficiency: number
  next_milestone: string | null
  eta_ticks: number | null
  arrival_tick: number | null
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
  journey: JourneySummary | null
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

// Decision windows

export type DecisionWindow = {
  window_id: string
  opened_tick: number
  closes_tick: number
  status: 'open' | 'closed'
  submitted: string[]
}

// Actions

export type ActionType =
  | 'emergency_repair'
  | 'prioritize_maintenance'
  | 'divert_power'
  | 'ration_resource'
  | 'boost_production'
  | 'transfer_resource'
  | 'impose_lockdown'
  | 'impose_civil_restriction'
  | 'impose_labor_draft'
  | 'lift_restriction'

export type ActionRequest = {
  role: string
  action_type: ActionType
  ring_id: string
  parameters: Record<string, unknown>
}

export type ActionResponse = {
  action_id: string
  status: 'accepted' | 'rejected'
  detail: string
  applied_tick: number
}
