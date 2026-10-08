import { useEffect, useState } from 'react'
import { Button } from '../components/ui'
import { DigitDisplay, NumberPad, UpiKeyboard } from '../components/Keypads'
import { useLang } from '../i18n'
import { isValidVpa, normalizeMobile } from '../lib/upi'

export type KeypadValue = { kind: 'mobile' | 'upi'; value: string }

/** Manual entry: mobile number (numeric pad) or UPI ID (on-screen keyboard). */
export function KeypadInput({ onResult }: { onResult: (v: KeypadValue) => void }) {
  const { t } = useLang()
  const [tab, setTab] = useState<'mobile' | 'upi'>('mobile')
  const [mobile, setMobile] = useState('')
  const [upi, setUpi] = useState('')

  // Physical keyboard also works (useful for testing and for service staff)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Backspace') {
        if (tab === 'mobile') setMobile((v) => v.slice(0, -1))
        else setUpi((v) => v.slice(0, -1))
      } else if (tab === 'mobile' && /^\d$/.test(e.key)) {
        setMobile((v) => (v.length < 10 ? v + e.key : v))
      } else if (tab === 'upi' && /^[a-zA-Z0-9.\-_@]$/.test(e.key)) {
        setUpi((v) => (v.length < 80 ? v + e.key.toLowerCase() : v))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab])

  const validMobile = normalizeMobile(mobile)
  const validUpi = isValidVpa(upi)

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <div className="grid w-full max-w-md grid-cols-2 rounded-2xl bg-slate-200/70 p-1.5">
        {(['mobile', 'upi'] as const).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`h-14 rounded-xl text-xl font-semibold ${tab === k ? 'bg-brand-600 text-white shadow' : 'text-slate-600'}`}
          >
            {k === 'mobile' ? t.tabMobile : t.tabUpi}
          </button>
        ))}
      </div>

      {tab === 'mobile' ? (
        <>
          <DigitDisplay digits={mobile} />
          <NumberPad value={mobile} onChange={setMobile} />
          <Button className="w-full max-w-md" disabled={!validMobile} onClick={() => onResult({ kind: 'mobile', value: validMobile! })}>
            {t.next}
          </Button>
        </>
      ) : (
        <>
          <div className="flex min-h-20 w-full items-center justify-center break-all rounded-2xl bg-white px-6 text-3xl font-bold text-brand-900 shadow-inner ring-2 ring-brand-500/30">
            {upi || <span className="font-normal text-slate-300">{t.upiPlaceholder}</span>}
            <span className="ml-0.5 h-9 w-0.5 animate-pulse bg-brand-600" />
          </div>
          <UpiKeyboard value={upi} onChange={setUpi} />
          <Button className="w-full" disabled={!validUpi} onClick={() => onResult({ kind: 'upi', value: upi.trim() })}>
            {t.next}
          </Button>
        </>
      )}
    </div>
  )
}

/** Optional mobile number for the SMS receipt (asked only for UPI IDs). */
export function SmsMobileStep({ onDone }: { onDone: (mobile: string | null) => void }) {
  const { t } = useLang()
  const [mobile, setMobile] = useState('')
  const valid = normalizeMobile(mobile)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Backspace') setMobile((v) => v.slice(0, -1))
      else if (/^\d$/.test(e.key)) setMobile((v) => (v.length < 10 ? v + e.key : v))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <p className="text-center text-xl text-slate-600">{t.smsSub}</p>
      <DigitDisplay digits={mobile} />
      <NumberPad value={mobile} onChange={setMobile} />
      <div className="grid w-full max-w-md grid-cols-2 gap-4">
        <Button variant="secondary" onClick={() => onDone(null)}>
          {t.skip}
        </Button>
        <Button disabled={!valid} onClick={() => onDone(valid)}>
          {t.next}
        </Button>
      </div>
    </div>
  )
}
