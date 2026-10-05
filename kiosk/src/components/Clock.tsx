import { useEffect, useState } from 'react'
import { useLang } from '../i18n'

/** Live India time (IST), ticking every second; date in Tamil or English. */
export function Clock() {
  const { lang } = useLang()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const tz = { timeZone: 'Asia/Kolkata' } as const
  const time = now.toLocaleTimeString('en-IN', { ...tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
  const date = now.toLocaleDateString(lang === 'ta' ? 'ta-IN' : 'en-IN', { ...tz, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  return (
    <div className="text-center leading-tight" aria-live="off">
      <p className="text-2xl font-bold tabular-nums">{time.toUpperCase()}</p>
      <p className="text-sm opacity-80">{date}</p>
    </div>
  )
}
