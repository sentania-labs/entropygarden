import { useState } from 'react'
import { api } from '../api'
import type { ActionResponse, ActionType, DecisionWindow, Role } from '../types'

// Which actions each role can use
const ROLE_ACTIONS: Record<Role, ActionType[]> = {
  captain:       ['emergency_repair', 'prioritize_maintenance', 'transfer_resource', 'ration_resource', 'boost_production', 'impose_lockdown', 'impose_labor_draft', 'lift_restriction'],
  engineer:      ['emergency_repair', 'prioritize_maintenance', 'divert_power'],
  ecologist:     ['transfer_resource', 'ration_resource', 'boost_production'],
  governor:      ['ration_resource', 'impose_civil_restriction', 'lift_restriction'],
  ring_delegate: ['ration_resource', 'impose_civil_restriction', 'lift_restriction'],
}

const ACTION_LABELS: Record<ActionType, string> = {
  emergency_repair:          'EMERGENCY REPAIR',
  prioritize_maintenance:    'PRIORITIZE MAINT.',
  divert_power:              'DIVERT POWER',
  transfer_resource:         'TRANSFER RESOURCE',
  ration_resource:           'RATION RESOURCE',
  boost_production:          'BOOST PRODUCTION',
  impose_lockdown:           'LOCKDOWN',
  impose_civil_restriction:  'CIVIL RESTRICTION',
  impose_labor_draft:        'LABOR DRAFT',
  lift_restriction:          'LIFT RESTRICTION',
}

const ACTION_DESC: Record<ActionType, string> = {
  emergency_repair:          'Reduce maintenance debt by 5%, costs 5 power',
  prioritize_maintenance:    'Focus engineers on debt reduction for 50 days',
  divert_power:              'Transfer power to another ring',
  transfer_resource:         'Transfer a resource to another ring (waste applies)',
  ration_resource:           'Reduce consumption 20% for 30 days',
  boost_production:          'Increase production 20% for 30 days',
  impose_lockdown:           'Block all settler movement in/out (drains morale)',
  impose_civil_restriction:  'Block settler inflow to this ring (drains morale)',
  impose_labor_draft:        'Prevent productive workers from leaving (drains morale)',
  lift_restriction:          'Remove all movement restrictions on this ring',
}

const RESOURCES = ['food', 'water', 'oxygen', 'power'] as const

const RINGS = ['ring_1', 'ring_2', 'ring_3'] as const

interface Props {
  window: DecisionWindow
  gameId: string
  ringId: string
  role: Role
}

export function ActionPanel({ window: win, gameId, ringId, role }: Props) {
  const [selectedAction, setSelectedAction] = useState<ActionType | null>(null)
  const [targetRing, setTargetRing] = useState<string>(RINGS.find(r => r !== ringId) ?? 'ring_1')
  const [amount, setAmount] = useState(50)
  const [resource, setResource] = useState<string>('food')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<ActionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const actions = ROLE_ACTIONS[role]
  const submitted = win.submitted.includes(role)

  if (submitted && !result) {
    return (
      <div className="border border-green/20 bg-green/5 rounded px-3 py-2 text-[11px] text-green tracking-wider">
        ORDER ALREADY TRANSMITTED THIS WINDOW
      </div>
    )
  }

  if (result) {
    const ok = result.status === 'accepted'
    return (
      <div className={`border rounded px-3 py-2 text-[11px] tracking-wider ${
        ok ? 'border-green/20 bg-green/5 text-green' : 'border-red/20 bg-red/5 text-red'
      }`}>
        {ok ? `ORDER ACCEPTED — ACTION ${result.action_id.slice(0, 8)}` : `REJECTED: ${result.detail}`}
      </div>
    )
  }

  const handleSubmit = async () => {
    if (!selectedAction) return
    setSubmitting(true)
    setError(null)

    const parameters: Record<string, unknown> = {}
    if (selectedAction === 'divert_power') {
      parameters.target_ring = targetRing
      parameters.amount = amount
    } else if (selectedAction === 'transfer_resource') {
      parameters.resource = resource
      parameters.target_ring = targetRing
      parameters.amount = amount
    }

    try {
      const resp = await api.submitAction(gameId, {
        role,
        action_type: selectedAction,
        ring_id: ringId,
        parameters,
      })
      setResult(resp)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Transmission failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="border border-border rounded bg-surface p-3 space-y-3">
      <div className="text-dim text-[10px] tracking-widest">SUBMIT ORDER</div>

      {/* Action selector */}
      <div className="flex flex-wrap gap-1.5">
        {actions.map(a => (
          <button
            key={a}
            onClick={() => { setSelectedAction(a); setResult(null); setError(null) }}
            className={`px-2 py-1 text-[10px] tracking-wider border rounded transition-colors ${
              selectedAction === a
                ? 'border-amber text-amber bg-amber/10'
                : 'border-border text-dim hover:text-text hover:border-text/30'
            }`}
          >
            {ACTION_LABELS[a]}
          </button>
        ))}
      </div>

      {/* Action details */}
      {selectedAction && (
        <div className="space-y-2">
          <div className="text-dim text-[10px]">{ACTION_DESC[selectedAction]}</div>

          {/* Divert power needs target ring + amount */}
          {selectedAction === 'divert_power' && (
            <div className="flex items-center gap-3 text-[11px]">
              <label className="text-dim">TARGET</label>
              <select
                value={targetRing}
                onChange={e => setTargetRing(e.target.value)}
                className="bg-bg border border-border text-text px-2 py-0.5 rounded text-[11px]"
              >
                {RINGS.filter(r => r !== ringId).map(r => (
                  <option key={r} value={r}>{r.replace('_', ' ').toUpperCase()}</option>
                ))}
              </select>
              <label className="text-dim">AMOUNT</label>
              <input
                type="range"
                min={5}
                max={200}
                step={5}
                value={amount}
                onChange={e => setAmount(Number(e.target.value))}
                className="w-24 accent-amber"
              />
              <span className="text-amber tabular-nums w-8">{amount}</span>
            </div>
          )}

          {/* Transfer resource needs resource type + target ring + amount */}
          {selectedAction === 'transfer_resource' && (
            <div className="flex flex-wrap items-center gap-3 text-[11px]">
              <label className="text-dim">RESOURCE</label>
              <select
                value={resource}
                onChange={e => setResource(e.target.value)}
                className="bg-bg border border-border text-text px-2 py-0.5 rounded text-[11px]"
              >
                {RESOURCES.map(r => (
                  <option key={r} value={r}>{r.toUpperCase()}</option>
                ))}
              </select>
              <label className="text-dim">TO</label>
              <select
                value={targetRing}
                onChange={e => setTargetRing(e.target.value)}
                className="bg-bg border border-border text-text px-2 py-0.5 rounded text-[11px]"
              >
                {RINGS.filter(r => r !== ringId).map(r => (
                  <option key={r} value={r}>{r.replace('_', ' ').toUpperCase()}</option>
                ))}
              </select>
              <label className="text-dim">AMOUNT</label>
              <input
                type="range"
                min={5}
                max={200}
                step={5}
                value={amount}
                onChange={e => setAmount(Number(e.target.value))}
                className="w-24 accent-amber"
              />
              <span className="text-amber tabular-nums w-8">{amount}</span>
            </div>
          )}

          {/* Submit */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-3 py-1 border border-amber text-amber text-[10px] tracking-widest rounded hover:bg-amber/10 transition-colors disabled:opacity-40"
            >
              {submitting ? 'TRANSMITTING...' : 'TRANSMIT ORDER'}
            </button>
            {error && <span className="text-red text-[10px]">{error}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
