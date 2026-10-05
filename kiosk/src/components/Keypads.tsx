import { BackspaceIcon } from './Icons'
import { UPI_HANDLES } from '../lib/upi'

const key = 'flex h-20 items-center justify-center rounded-2xl bg-white text-3xl font-semibold text-slate-800 shadow-sm ring-1 ring-slate-200 active:bg-brand-50 active:ring-brand-500'

/** Numeric keypad for mobile numbers. */
export function NumberPad({ value, onChange, max = 10 }: { value: string; onChange: (v: string) => void; max?: number }) {
  const press = (d: string) => value.length < max && onChange(value + d)
  return (
    <div className="grid w-full max-w-md grid-cols-3 gap-3">
      {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
        <button key={d} className={key} onClick={() => press(d)}>
          {d}
        </button>
      ))}
      <button className={`${key} text-xl text-slate-500`} onClick={() => onChange('')}>
        C
      </button>
      <button className={key} onClick={() => press('0')}>
        0
      </button>
      <button className={key} onClick={() => onChange(value.slice(0, -1))} aria-label="Backspace">
        <BackspaceIcon className="h-8 w-8" />
      </button>
    </div>
  )
}

const ROWS = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']
const small = 'flex h-14 min-w-0 flex-1 items-center justify-center rounded-xl bg-white text-2xl font-semibold text-slate-800 shadow-sm ring-1 ring-slate-200 active:bg-brand-50'

/** On-screen keyboard for UPI IDs (lowercase, digits, . - _ @). */
export function UpiKeyboard({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const add = (s: string) => value.length < 80 && onChange(value + s)
  const hasAt = value.includes('@')
  return (
    <div className="flex w-full flex-col gap-2">
      <div className="mb-2 flex flex-wrap justify-center gap-2">
        {UPI_HANDLES.map((h) => (
          <button
            key={h}
            disabled={hasAt}
            className="rounded-full bg-brand-50 px-4 py-2 text-lg font-semibold text-brand-700 ring-1 ring-brand-100 active:bg-brand-100 disabled:opacity-30"
            onClick={() => add(h)}
          >
            {h}
          </button>
        ))}
      </div>
      {ROWS.map((row) => (
        <div key={row} className="flex gap-1.5">
          {row.split('').map((c) => (
            <button key={c} className={small} onClick={() => add(c)}>
              {c}
            </button>
          ))}
        </div>
      ))}
      <div className="flex gap-1.5">
        {['.', '-', '_'].map((c) => (
          <button key={c} className={small} onClick={() => add(c)}>
            {c}
          </button>
        ))}
        <button className={`${small} flex-[2]`} disabled={hasAt} onClick={() => add('@')}>
          @
        </button>
        <button className={`${small} flex-[2]`} onClick={() => onChange(value.slice(0, -1))} aria-label="Backspace">
          <BackspaceIcon className="h-7 w-7" />
        </button>
      </div>
    </div>
  )
}

/** Big display for a 10-digit number, grouped 5+5. */
export function DigitDisplay({ digits, total = 10 }: { digits: string; total?: number }) {
  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="contents">
          {i === 5 && <div className="w-3" />}
          <div
            className={`flex h-16 w-11 items-center justify-center rounded-xl text-4xl font-bold tabular-nums sm:h-20 sm:w-14 ${
              digits[i] ? 'bg-white text-brand-900 shadow ring-2 ring-brand-500/40' : 'bg-slate-200/60 text-transparent'
            }`}
          >
            {digits[i] ?? '0'}
          </div>
        </div>
      ))}
    </div>
  )
}
