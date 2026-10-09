import { useCallback, useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { get } from './api'

export const REFRESH_MS = 5000

/** GET an admin endpoint and refresh it every few seconds. */
export function usePoll<T>(path: string, every = REFRESH_MS) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      setData(await get<T>(path))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [path])
  useEffect(() => {
    load()
    if (!every) return
    const id = window.setInterval(load, every)
    return () => window.clearInterval(id)
  }, [load, every])
  return { data, error, reload: load }
}

export const fmtTime = (s: string | null) =>
  s
    ? new Date(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—'
export const rupees = (paise: number) => `₹${(paise / 100).toLocaleString('en-IN')}`

const TONE: Record<string, string> = {
  SUCCESS: 'bg-emerald-100 text-emerald-800',
  ACCEPTED: 'bg-emerald-100 text-emerald-800',
  CONSUMED: 'bg-emerald-100 text-emerald-800',
  SENT: 'bg-emerald-100 text-emerald-800',
  READY: 'bg-emerald-100 text-emerald-800',
  RESOLVED: 'bg-emerald-100 text-emerald-800',
  ADMIN: 'bg-violet-100 text-violet-800',
  OPERATOR: 'bg-sky-100 text-sky-800',
  VIEWER: 'bg-slate-100 text-slate-700',
  PENDING: 'bg-amber-100 text-amber-800',
  RESERVED: 'bg-amber-100 text-amber-800',
  HELD: 'bg-amber-100 text-amber-800',
  warning: 'bg-amber-100 text-amber-800',
  IN_PROGRESS: 'bg-sky-100 text-sky-800',
  CREATED: 'bg-sky-100 text-sky-800',
  CLOSED: 'bg-amber-100 text-amber-800',
  OPEN: 'bg-red-100 text-red-800',
  FAILED: 'bg-red-100 text-red-800',
  OUT_OF_SERVICE: 'bg-red-100 text-red-800',
  critical: 'bg-red-100 text-red-800',
  RETURNED: 'bg-slate-200 text-slate-700',
  RELEASED: 'bg-slate-200 text-slate-700',
  CANCELLED: 'bg-slate-200 text-slate-700',
}

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-slate-400">—</span>
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[value] ?? 'bg-slate-100 text-slate-700'}`}>{value}</span>
}

export function Table({ head, rows, empty = 'No data yet' }: { head: string[]; rows: ReactNode[][]; empty?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-4 py-3 font-semibold whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={head.length} className="px-4 py-10 text-center text-slate-400">{empty}</td>
            </tr>
          ) : (
            rows.map((r, i) => (
              <tr key={i} className="hover:bg-slate-50">
                {r.map((c, j) => (
                  <td key={j} className="px-4 py-2.5 whitespace-nowrap">{c}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

export const mono = (s: string | null | undefined) => <span className="font-mono text-xs">{s ?? '—'}</span>

type BtnVariant = 'primary' | 'secondary' | 'danger' | 'link'
const BTN: Record<BtnVariant, string> = {
  primary: 'bg-brand-700 text-white hover:bg-brand-600 disabled:opacity-50',
  secondary: 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:opacity-50',
  danger: 'bg-white text-red-700 ring-1 ring-red-300 hover:bg-red-50 disabled:opacity-50',
  link: 'text-brand-700 hover:underline disabled:opacity-50 px-0 py-0',
}
export function Btn({ variant = 'primary', className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  return <button {...rest} className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${BTN[variant]} ${className}`} />
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-600">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}
export const inputCls = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none'

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="text-xl text-slate-400 hover:text-slate-700" aria-label="Close">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function ErrorText({ children }: { children: ReactNode }) {
  return children ? <p className="text-sm text-red-600">{children}</p> : null
}

/** Shows a secret once (machine API keys) with a copy button. */
export function SecretBox({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
      <p className="text-xs font-semibold text-amber-900">{label}</p>
      <p className="mt-1 font-mono text-sm break-all select-all">{value}</p>
      <Btn
        variant="secondary"
        className="mt-2"
        onClick={() => navigator.clipboard?.writeText(value).then(() => setCopied(true))}
      >
        {copied ? 'Copied' : 'Copy'}
      </Btn>
    </div>
  )
}
