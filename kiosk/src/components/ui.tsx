import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { useLang } from '../i18n'
import { useVoice } from '../voice'
import { ClockIcon } from './Icons'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white active:bg-brand-700 disabled:bg-brand-600/40',
  secondary: 'bg-white text-brand-700 ring-2 ring-brand-600/25 active:bg-brand-50 disabled:opacity-40',
  ghost: 'bg-transparent text-slate-600 active:bg-slate-200/60',
  danger: 'bg-white text-red-700 ring-2 ring-red-600/25 active:bg-red-50',
}

export function Button({
  variant = 'primary',
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...rest}
      className={`inline-flex min-h-16 items-center justify-center gap-3 rounded-2xl px-8 text-xl font-semibold transition-colors ${VARIANTS[variant]} ${className}`}
    />
  )
}

export function Screen({ children, className = '', wide = false }: { children: ReactNode; className?: string; wide?: boolean }) {
  return (
    <div className={`mx-auto flex w-full ${wide ? 'max-w-5xl' : 'max-w-3xl'} flex-1 flex-col items-center px-6 py-8 ${className}`}>
      {children}
    </div>
  )
}

export function Title({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-8 text-center">
      <h1 className="text-4xl font-extrabold tracking-tight text-brand-900 sm:text-5xl">{children}</h1>
      {sub && <p className="mt-3 text-xl text-slate-600">{sub}</p>}
    </div>
  )
}

/** Time left for customer input, based on when the machine entered the state. */
export function Countdown({ seconds, since }: { seconds?: number; since: number }) {
  const { t } = useLang()
  const { play } = useVoice()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(id)
  }, [])
  const left = seconds ? Math.max(0, Math.ceil(seconds - (now - since) / 1000)) : 0
  const urgent = left <= 15
  const warned = useRef(false)
  useEffect(() => {
    // only for real customer-input timers, not the few-second batch window
    if (seconds && seconds > 30 && urgent && left > 0 && !warned.current) {
      warned.current = true
      play('hurry')
    }
  }, [seconds, urgent, left, play])
  if (!seconds) return null
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-lg font-semibold tabular-nums ${
        urgent ? 'bg-red-100 text-red-700' : 'bg-slate-200/70 text-slate-700'
      }`}
    >
      <ClockIcon className="h-5 w-5" />
      {t.secondsLeft(left)}
    </div>
  )
}

export function Spinner({ className = 'h-20 w-20', thin = false }: { className?: string; thin?: boolean }) {
  const border = thin ? 'border-[3px]' : 'border-8'
  return (
    <div className={`relative ${className}`}>
      <div className={`absolute inset-0 rounded-full ${border} border-brand-100`} />
      <div className={`absolute inset-0 animate-spin rounded-full ${border} border-transparent border-t-brand-600`} />
    </div>
  )
}

export function Banner({ tone, children }: { tone: 'error' | 'warn' | 'info'; children: ReactNode }) {
  const cls = {
    error: 'bg-red-50 text-red-800 ring-red-200',
    warn: 'bg-amber-50 text-amber-900 ring-amber-200',
    info: 'bg-brand-50 text-brand-900 ring-brand-100',
  }[tone]
  return <div className={`w-full rounded-2xl px-6 py-4 text-center text-xl font-semibold ring-1 ${cls}`}>{children}</div>
}

// ---------------- redesign building blocks ----------------

const BADGE_TONE = {
  ok: 'bg-brand-600 text-white shadow-brand-600/30',
  warn: 'bg-amber-500 text-white shadow-amber-500/30',
  error: 'bg-red-600 text-white shadow-red-600/30',
  muted: 'bg-slate-200 text-slate-600 shadow-transparent',
}

/** Big round status icon (tick, cross, hourglass…) at the top of a screen. */
export function StatusBadge({ tone = 'ok', children, size = 'lg' }: { tone?: keyof typeof BADGE_TONE; children: ReactNode; size?: 'md' | 'lg' }) {
  const dim = size === 'lg' ? 'h-36 w-36 tall:h-44 tall:w-44' : 'h-24 w-24'
  return <div className={`animate-pop mb-8 flex ${dim} items-center justify-center rounded-full shadow-xl ${BADGE_TONE[tone]}`}>{children}</div>
}

/** Progress bar; without a value it slides (work in progress). */
export function ProgressBar({ value, className = '' }: { value?: number; className?: string }) {
  return (
    <div className={`h-3 w-full max-w-md overflow-hidden rounded-full bg-brand-100 ${className}`}>
      {value === undefined ? (
        <div className="animate-progress h-full w-2/5 rounded-full bg-brand-600" />
      ) : (
        <div className="h-full rounded-full bg-brand-600 transition-all duration-500" style={{ width: `${Math.round(value * 100)}%` }} />
      )}
    </div>
  )
}

/** Dark camera window with corner brackets and a moving scan line. */
export function ScanFrame({ tone = 'ok', scanning = true, children, className = '' }: {
  tone?: 'ok' | 'alert'; scanning?: boolean; children?: ReactNode; className?: string
}) {
  const c = tone === 'ok' ? 'border-brand-500' : 'border-red-500'
  const corner = `absolute h-12 w-12 ${c}`
  return (
    <div className={`relative aspect-[4/3] w-full max-w-xl overflow-hidden rounded-3xl bg-slate-900 shadow-xl ${className}`}>
      <div className="absolute inset-0 flex items-center justify-center">{children}</div>
      <span className={`${corner} top-6 left-6 rounded-tl-xl border-t-4 border-l-4`} />
      <span className={`${corner} top-6 right-6 rounded-tr-xl border-t-4 border-r-4`} />
      <span className={`${corner} bottom-6 left-6 rounded-bl-xl border-b-4 border-l-4`} />
      <span className={`${corner} right-6 bottom-6 rounded-br-xl border-r-4 border-b-4`} />
      {scanning && (
        <span className={`animate-scan-line absolute right-10 left-10 h-0.5 ${tone === 'ok' ? 'bg-brand-500 shadow-[0_0_12px_2px_rgba(25,135,84,0.8)]' : 'bg-red-500 shadow-[0_0_12px_2px_rgba(239,68,68,0.8)]'}`} />
      )}
    </div>
  )
}

/** Numbered steps joined by arrows (1 Insert → 2 Detect → 3 Inspect). */
export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex w-full items-start justify-center gap-2">
      {steps.map((s, i) => (
        <li key={s} className="flex items-start gap-2">
          <div className="flex w-28 flex-col items-center gap-2 text-center tall:w-36">
            <span className={`flex h-14 w-14 items-center justify-center rounded-full text-xl font-bold ring-4 ${
              i < current ? 'bg-brand-600 text-white ring-brand-100' : i === current ? 'bg-brand-700 text-white ring-brand-500/40' : 'bg-white text-slate-400 ring-slate-200'
            }`}>
              {i + 1}
            </span>
            <span className={`text-base font-semibold ${i <= current ? 'text-brand-900' : 'text-slate-400'}`}>{s}</span>
          </div>
          {i < steps.length - 1 && <span className="mt-5 text-2xl text-slate-300">→</span>}
        </li>
      ))}
    </ol>
  )
}

/** White card holding label / value rows (refund details, bottle details). */
export function DetailCard({ title, rows }: { title?: ReactNode; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="w-full overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-slate-200">
      {title && <div className="border-b border-slate-100 bg-brand-50 px-8 py-4 text-lg font-bold text-brand-800">{title}</div>}
      <dl className="divide-y divide-slate-100 text-xl">
        {rows.map(([k, v], i) => (
          <div key={i} className="flex items-center justify-between gap-6 px-8 py-4">
            <dt className="text-slate-500">{k}</dt>
            <dd className="text-right font-bold break-all text-brand-900">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
