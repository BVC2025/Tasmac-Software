import { useEffect, useReducer } from 'react'
import { MACHINE_WS } from './api'

export type Ev = { type: string; at?: string; [k: string]: any }

export interface LaneView {
  lane: number
  step: string // DETECTED .. VERIFYING | VALID | REJECTED | ACCEPTED | RETURNED
  reason?: string | null
  amount_paise?: number
  brand?: string | null // from the manufacturing QR
}

export interface SessionResult {
  outcome: string // ACCEPTED | RETURNED | CANCELLED | ABORTED
  reason: string
  txn_id: string | null
  amount_paise: number
  accepted: number
  bottles: LaneView[]
  final: Ev | null // REFUND_SUCCESS / REFUND_PENDING message
  sms: boolean // an SMS receipt will be sent
  at: number
}

export interface MachineView {
  connected: boolean
  state: string
  stateData: Ev
  stateAt: number
  message: Ev | null
  machineId: string
  simulation: boolean
  plc: { connected: boolean; state: string; fault: string; bin_fill_pct: number } | null
  laneCount: number
  lanes: Record<number, LaneView> // bottles of the current session, by inlet
  confirm: Ev | null // CONFIRM_REFUND details
  inputError: string | null // last destination error code
  final: Ev | null
  result: SessionResult | null
  fault: string | null
}

const initial: MachineView = {
  connected: false,
  state: 'STARTING',
  stateData: { type: 'state' },
  stateAt: Date.now(),
  message: null,
  machineId: '',
  simulation: false,
  plc: null,
  laneCount: 1,
  lanes: {},
  confirm: null,
  inputError: null,
  final: null,
  result: null,
  fault: null,
}

type Action = { kind: 'event'; ev: Ev } | { kind: 'connected'; value: boolean } | { kind: 'clearResult' }

function reducer(s: MachineView, a: Action): MachineView {
  if (a.kind === 'connected') return { ...s, connected: a.value }
  if (a.kind === 'clearResult') return { ...s, result: null }
  const ev = a.ev
  switch (ev.type) {
    case 'snapshot':
      return {
        ...s,
        state: ev.state,
        stateData: ev.last_state ?? { type: 'state', state: ev.state },
        stateAt: Date.now(),
        message: ev.last_message ?? null,
        machineId: ev.machine_id,
        laneCount: ev.lane_count ?? 1,
        lanes: Object.fromEntries(((ev.lanes ?? []) as LaneView[]).map((l) => [l.lane, l])),
        simulation: ev.simulation,
        plc: ev.plc,
      }
    case 'state': {
      const next = { ...s, state: ev.state, stateData: ev, stateAt: Date.now() }
      if (ev.state === 'READY') next.fault = null
      return next
    }
    case 'message': {
      const next = { ...s, message: ev }
      if (ev.code === 'CONFIRM_REFUND') next.confirm = ev
      if (['INVALID_DESTINATION', 'DESTINATION_NOT_FOUND', 'INVALID_SMS_MOBILE'].includes(ev.code)) next.inputError = ev.code
      if (ev.code === 'REFUND_SUCCESS' || ev.code === 'REFUND_PENDING') next.final = ev
      return next
    }
    case 'session_started':
      // new customer session: forget everything from the previous one
      return { ...s, lanes: {}, confirm: null, inputError: null, final: null, result: null, fault: null }
    case 'lane':
      return {
        ...s,
        lanes: {
          ...s.lanes,
          [ev.lane]: { lane: ev.lane, step: ev.step, reason: ev.reason, amount_paise: ev.amount_paise, brand: ev.brand ?? s.lanes[ev.lane]?.brand },
        },
      }
    case 'session_ended':
      return {
        ...s,
        result: {
          outcome: ev.outcome, reason: ev.reason, txn_id: ev.txn_id, final: s.final, sms: !!s.confirm?.sms,
          amount_paise: ev.amount_paise ?? 0, accepted: ev.accepted ?? 0, bottles: ev.bottles ?? [], at: Date.now(),
        },
      }
    case 'fault':
      return { ...s, fault: ev.reason }
    default:
      return s
  }
}

/** Live machine state over the WebSocket, with automatic reconnect. */
export function useMachine(resultHoldMs = 8000) {
  const [view, dispatch] = useReducer(reducer, initial)

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: number | undefined
    let closed = false

    const connect = () => {
      ws = new WebSocket(MACHINE_WS)
      ws.onopen = () => dispatch({ kind: 'connected', value: true })
      ws.onmessage = (m) => dispatch({ kind: 'event', ev: JSON.parse(m.data) })
      ws.onclose = () => {
        dispatch({ kind: 'connected', value: false })
        if (!closed) retry = window.setTimeout(connect, 1500)
      }
      ws.onerror = () => ws?.close()
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      ws?.close()
    }
  }, [])

  // Keep the result screen visible for a few seconds after the session ends
  useEffect(() => {
    if (!view.result) return
    const t = window.setTimeout(() => dispatch({ kind: 'clearResult' }), resultHoldMs)
    return () => window.clearTimeout(t)
  }, [view.result, resultHoldMs])

  return [view, () => dispatch({ kind: 'clearResult' })] as const
}
