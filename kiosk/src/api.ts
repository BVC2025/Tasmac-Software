export const MACHINE_API = (import.meta.env.VITE_MACHINE_API as string | undefined) ?? 'http://127.0.0.1:8765'
export const MACHINE_WS = MACHINE_API.replace(/^http/, 'ws') + '/ws'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(MACHINE_API + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export type InputSource = 'qr' | 'voice' | 'keypad'

export const api = {
  submitDestination: (value: string, source: InputSource, smsMobile?: string) =>
    request('POST', '/api/customer/destination', { value, source, sms_mobile: smsMobile || null }),
  cancel: () => request('POST', '/api/customer/destination', { cancel: true }),
  confirm: (ok: boolean) => request('POST', '/api/customer/confirm', { ok }),
  sessions: () => request<SessionRow[]>('GET', '/api/sessions?limit=15'),
  simBottles: () => request<SimBottle[]>('GET', '/api/sim/bottles'),
  simInsert: (bottle?: string, lane?: number) =>
    request<{ inserted: boolean; lane: number | null; bottle: string | null }>('POST', '/api/sim/insert', { bottle, lane }),
  simInsertBatch: (bottles: (string | null)[]) =>
    request<{ inserted: { lane: number; bottle: string | null }[] }>('POST', '/api/sim/insert-batch', { bottles }),
  simRefresh: () => request<{ refreshed: number }>('POST', '/api/sim/refresh'),
  simEstop: (pressed: boolean) => request('POST', '/api/sim/estop', { pressed }),
}

export interface SimBottle {
  name: string
  condition: string
  destination: string | null
  payout: string
  has_refund_qr: boolean
  has_mfg_qr: boolean
}

export interface SessionRow {
  id: string
  started_at: string
  outcome: string
  reason: string
  destination: string | null
  txn_id: string | null
  payout_status: string | null
  bottles: { lane: number; step: string; reason: string }[]
  accepted: number
  amount_paise: number
}
