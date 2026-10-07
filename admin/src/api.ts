export const BACKEND = (import.meta.env.VITE_BACKEND_API as string | undefined) ?? 'http://127.0.0.1:8000'
const BASE = `${BACKEND}/api/admin/v1`

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let token = ''
let onUnauthorized: () => void = () => {}

export function setAuth(t: string, onExpired: () => void) {
  token = t
  onUnauthorized = onExpired
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401 && token) onUnauthorized()
  if (!res.ok) {
    let msg = res.statusText
    try {
      const d = (await res.json()).detail
      msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e.msg).join(', ') : msg
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const get = <T>(path: string) => call<T>('GET', path)
export const post = <T>(path: string, body?: unknown) => call<T>('POST', path, body ?? {})
export const patch = <T>(path: string, body: unknown) => call<T>('PATCH', path, body)
export const del = <T>(path: string) => call<T>('DELETE', path)

export async function download(path: string, filename: string) {
  const res = await fetch(BASE + path, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new ApiError(res.status, res.statusText)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function login(username: string, password: string) {
  return call<{ access_token: string; user: User }>('POST', '/auth/login', { username, password })
}

export type Role = 'VIEWER' | 'OPERATOR' | 'ADMIN'
export const RANK: Record<Role, number> = { VIEWER: 1, OPERATOR: 2, ADMIN: 3 }

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  active: boolean
  last_login_at: string | null
  locked_until: string | null
}
export interface Stats {
  machines_total: number
  machines_online: number
  sessions_today: number
  bottles_accepted_today: number
  bottles_returned_today: number
  refunds_success_today: number
  refunds_pending: number
  refunds_failed_today: number
  amount_refunded_today_paise: number
  open_alerts: number
}
export interface MachineRow {
  id: string
  name: string
  location: string | null
  active: boolean
  state: string | null
  bin_fill_pct: number | null
  software_version: string | null
  fault_reason: string | null
  last_seen_at: string | null
}
export interface TxnRow {
  id: string
  session_id: string
  machine_id: string
  refund_serial: string
  amount_paise: number
  dest_kind: string
  dest_value: string
  status: string
  bottle_status: string
  provider_ref: string | null
  failure_reason: string | null
  sms_sent: boolean
  created_at: string
  completed_at: string | null
}
export interface SessionRow {
  id: string
  machine_id: string
  refund_serial: string | null
  mfg_serial: string | null
  brand: string | null
  outcome: string
  reason: string | null
  started_at: string
  ended_at: string | null
}
export interface ClaimRow {
  refund_serial: string
  mfg_serial: string
  brand: string
  status: string
  machine_id: string
  session_id: string
  consumed_at: string | null
  updated_at: string
}
export interface SmsRow {
  id: number
  txn_id: string | null
  mobile: string
  body: string
  status: string
  created_at: string
}
export interface AuditRow {
  at: string
  actor: string
  action: string
  entity: string | null
  entity_id: string | null
  data: Record<string, unknown> | null
}
export interface AlertRow {
  id: number
  type: string
  severity: 'info' | 'warning' | 'critical'
  machine_id: string | null
  entity_id: string
  message: string
  status: string
  auto: boolean
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  note: string | null
}
export interface Brand {
  code: string
  name: string
  active: boolean
}
export interface ReportRow {
  day: string
  machine_id: string
  sessions: number
  accepted: number
  returned: number
  paid: number
  amount_paise: number
  failed: number
  pending: number
}
export interface Report {
  from: string
  to: string
  rows: ReportRow[]
  totals: Omit<ReportRow, 'day' | 'machine_id'>
}

export interface QrCodeRow {
  code_hash: string
  raw: string
  kind: 'refund' | 'mfg' | 'product' | null
  serial: string
  brand: string | null
  batch: string | null
  label: string | null
  active: boolean
  seen_count: number
  last_seen_at: string | null
  last_machine_id: string | null
  registered_by: string | null
  created_at: string
}
