import { useState } from 'react'
import type { Report } from '../api'
import { rupees, usePoll } from '../ui'

const DAYS = 7
const BAR = '#1a7f4e' // validated against the light surface (dataviz validator)

const isoDay = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })

function niceMax(v: number): number {
  if (v <= 4) return 4
  const pow = 10 ** Math.floor(Math.log10(v))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= v) return m * pow
  return 10 * pow
}

interface Day {
  day: string
  label: string
  accepted: number
  returned: number
  amount: number
}

/** Single-series column chart: bottles accepted per day (IST), last 7 days. */
export function DailyChart() {
  const to = new Date()
  const from = new Date(to.getTime() - (DAYS - 1) * 864e5)
  const { data } = usePoll<Report>(`/reports/daily?from=${isoDay(from)}&to=${isoDay(to)}`, 30_000)
  const [hover, setHover] = useState<number | null>(null)

  const days: Day[] = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(from.getTime() + i * 864e5)
    const key = isoDay(d)
    const rows = (data?.rows ?? []).filter((r) => r.day === key)
    return {
      day: key,
      label: d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric' }),
      accepted: rows.reduce((s, r) => s + r.accepted, 0),
      returned: rows.reduce((s, r) => s + r.returned, 0),
      amount: rows.reduce((s, r) => s + r.amount_paise, 0),
    }
  })
  const max = niceMax(Math.max(...days.map((d) => d.accepted)))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f))
  const total = days.reduce((s, d) => s + d.accepted, 0)
  const H = 200

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-slate-900">Bottles accepted · last 7 days</h3>
          <p className="text-sm text-slate-500">Daily totals across all machines (IST)</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-slate-900 tabular-nums">{total.toLocaleString('en-IN')}</p>
          <p className="text-xs text-slate-500">this week</p>
        </div>
      </div>

      <div className="flex gap-3">
        {/* y axis */}
        <div className="relative w-8 shrink-0 text-right text-xs text-slate-400 tabular-nums" style={{ height: H }}>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0" style={{ bottom: `${(t / max) * 100}%`, transform: 'translateY(50%)' }}>
              {t.toLocaleString('en-IN')}
            </span>
          ))}
        </div>
        {/* plot */}
        <div className="relative flex-1">
          <div className="relative" style={{ height: H }}>
            {ticks.map((t) => (
              <div key={t} className="absolute right-0 left-0 border-t border-slate-100" style={{ bottom: `${(t / max) * 100}%` }} />
            ))}
            <div className="absolute inset-0 flex">
              {days.map((d, i) => {
                const h = (d.accepted / max) * 100
                const last = i === days.length - 1
                return (
                  <div key={d.day} className="relative flex flex-1 items-end justify-center"
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                    {hover === i && <div className="absolute inset-y-0 w-full rounded-lg bg-slate-100/70" />}
                    {last && d.accepted > 0 && (
                      <span className="absolute text-xs font-semibold text-slate-700 tabular-nums" style={{ bottom: `calc(${h}% + 6px)` }}>
                        {d.accepted}
                      </span>
                    )}
                    <div className="relative w-6 rounded-t" style={{ height: `${h}%`, background: BAR, minHeight: d.accepted ? 2 : 0 }} />
                    {hover === i && (
                      <div className={`pointer-events-none absolute top-0 z-10 w-44 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg ${
                        i >= days.length - 2 ? 'right-1/2 mr-5' : 'left-1/2 ml-5'}`}>
                        <p className="mb-1 font-semibold">{d.label}</p>
                        <p className="flex justify-between"><span className="text-white/70">Accepted</span><span className="tabular-nums">{d.accepted}</span></p>
                        <p className="flex justify-between"><span className="text-white/70">Returned</span><span className="tabular-nums">{d.returned}</span></p>
                        <p className="flex justify-between"><span className="text-white/70">Refunded</span><span className="tabular-nums">{rupees(d.amount)}</span></p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="mt-2 flex border-t border-slate-200 pt-2">
            {days.map((d) => (
              <span key={d.day} className="flex-1 text-center text-xs text-slate-500">{d.label}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
