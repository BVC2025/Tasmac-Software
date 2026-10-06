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
