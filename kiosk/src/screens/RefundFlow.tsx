import { useState, type ReactNode } from 'react'
import { api, type InputSource } from '../api'
import { Banner, Button, Countdown, Screen, Spinner, Title } from '../components/ui'
import { ArrowLeftIcon, CheckIcon, ClockIcon, KeypadIcon, MicIcon, QrIcon, SmsIcon } from '../components/Icons'
import { useLang } from '../i18n'
import { normalizeMobile } from '../lib/upi'
import type { MachineView, SessionResult } from '../useMachine'
import { KeypadInput, SmsMobileStep } from './KeypadInput'
import { QrScan } from './QrScan'
import { VoiceInput } from './VoiceInput'

type Step = 'choose' | 'qr' | 'voice' | 'keypad' | 'sms'

/**
 * SELECT_REFUND_METHOD screen. The parent remounts it (key = stateAt) every
 * time the machine asks again, so each attempt starts on "choose".
 */
export function RefundMethod({ view }: { view: MachineView }) {
  const { t, reason } = useLang()
  const [step, setStep] = useState<Step>('choose')
  const [pendingUpi, setPendingUpi] = useState<{ vpa: string; source: InputSource } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const attempt: number = view.stateData.attempt ?? 1
  const maxAttempts: number = view.stateData.max_attempts ?? 3

  const submit = async (value: string, source: InputSource, sms?: string | null) => {
    setBusy(true)
    setError(null)
    try {
      await api.submitDestination(value, source, sms ?? undefined)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  // UPI IDs need an optional SMS number - unless the UPI ID itself is a mobile number
  const gotUpi = (vpa: string, source: InputSource) => {
    if (normalizeMobile(vpa.split('@')[0])) return submit(vpa, source)
    setPendingUpi({ vpa, source })
    setStep('sms')
  }

  const header: Record<Step, string> = {
    choose: t.chooseTitle,
    qr: t.qrTitle,
    voice: t.voiceTitle,
    keypad: t.keypadTitle,
    sms: t.smsTitle,
  }

  let body: ReactNode
  if (busy) {
    body = (
      <div className="flex flex-1 items-center justify-center">
        <Spinner />
      </div>
    )
  } else if (step === 'choose') {
    body = (
      <div className="grid w-full gap-4">
        <MethodCard icon={<QrIcon className="h-12 w-12" />} title={t.methodQr} sub={t.methodQrSub} onClick={() => setStep('qr')} />
        <MethodCard icon={<MicIcon className="h-12 w-12" />} title={t.methodVoice} sub={t.methodVoiceSub} onClick={() => setStep('voice')} />
        <MethodCard icon={<KeypadIcon className="h-12 w-12" />} title={t.methodKeypad} sub={t.methodKeypadSub} onClick={() => setStep('keypad')} />
      </div>
    )
  } else if (step === 'qr') {
    body = <QrScan onResult={(r) => gotUpi(r.vpa, 'qr')} />
  } else if (step === 'voice') {
    body = <VoiceInput onResult={(m) => submit(m, 'voice')} onTypeInstead={() => setStep('keypad')} />
  } else if (step === 'keypad') {
    body = <KeypadInput onResult={(v) => (v.kind === 'mobile' ? submit(v.value, 'keypad') : gotUpi(v.value, 'keypad'))} />
  } else {
    body = <SmsMobileStep onDone={(m) => pendingUpi && submit(pendingUpi.vpa, pendingUpi.source, m)} />
  }

  return (
    <Screen>
      <div className="mb-6 flex w-full items-center justify-between gap-4">
        {step !== 'choose' && !busy ? (
          <Button variant="ghost" className="min-h-12 px-4" onClick={() => setStep('choose')}>
            <ArrowLeftIcon className="h-6 w-6" /> {t.back}
          </Button>
        ) : (
          <span className="rounded-full bg-brand-50 px-4 py-1.5 text-lg font-semibold text-brand-700 ring-1 ring-brand-100">
            {t.eligible}
          </span>
        )}
        <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
      </div>

      <Title>{header[step]}</Title>

      {attempt > 1 && view.inputError && (
        <div className="mb-6 w-full">
          <Banner tone="error">
            {reason(view.inputError)} · {t.attempt(attempt, maxAttempts)}
          </Banner>
        </div>
      )}
      {error && (
        <div className="mb-6 w-full">
          <Banner tone="error">{error}</Banner>
        </div>
      )}

      {body}

      {!busy && (
        <Button variant="danger" className="mt-auto w-full translate-y-2" onClick={() => api.cancel().catch(() => {})}>
          {t.cancel}
        </Button>
      )}
    </Screen>
  )
}

function MethodCard({ icon, title, sub, onClick }: { icon: ReactNode; title: string; sub: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-6 rounded-3xl bg-white p-6 text-left shadow-sm ring-1 ring-slate-200 transition active:scale-[0.99] active:ring-2 active:ring-brand-500"
    >
      <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700">{icon}</span>
      <span>
        <span className="block text-2xl font-bold text-brand-900">{title}</span>
        <span className="mt-1 block text-lg text-slate-500">{sub}</span>
      </span>
    </button>
  )
}

export function Confirm({ view }: { view: MachineView }) {
  const { t } = useLang()
  const [busy, setBusy] = useState(false)
  const c = view.confirm
  const send = async (ok: boolean) => {
    setBusy(true)
    try {
      await api.confirm(ok)
    } catch {
      setBusy(false)
    }
  }
  if (!c) return null
  const rupees = (c.amount_paise / 100).toFixed(0)
  return (
    <Screen>
      <div className="mb-6 flex w-full justify-end">
        <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
      </div>
      <Title>{t.confirmTitle}</Title>
      <div className="w-full overflow-hidden rounded-3xl bg-white shadow ring-1 ring-slate-200">
        <div className="bg-brand-700 px-8 py-8 text-center text-white">
          <p className="text-lg opacity-80">{t.amount}</p>
          <p className="text-7xl font-extrabold">₹{rupees}</p>
        </div>
        <dl className="divide-y divide-slate-100 text-xl">
          <Row label={t.sendTo} value={c.destination} />
          {c.name && <Row label={t.accountName} value={c.name} />}
          {c.sms_mobile && <Row label={t.smsTo} value={c.sms_mobile} icon={<SmsIcon className="h-5 w-5" />} />}
        </dl>
      </div>
      <div className="mt-8 grid w-full grid-cols-3 gap-4">
        <Button variant="secondary" disabled={busy} onClick={() => send(false)}>
          {t.change}
        </Button>
        <Button className="col-span-2" disabled={busy} onClick={() => send(true)}>
          <CheckIcon className="h-7 w-7" strokeWidth={3} /> {t.confirm}
        </Button>
      </div>
    </Screen>
  )
}

function Row({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-8 py-5">
      <dt className="flex items-center gap-2 text-slate-500">
        {icon}
        {label}
      </dt>
      <dd className="break-all text-right font-bold text-brand-900">{value}</dd>
    </div>
  )
}

export function Result({ result, onDone }: { result: SessionResult; onDone: () => void }) {
  const { t, reason } = useLang()
  const success = result.outcome === 'ACCEPTED' && result.final?.code !== 'REFUND_PENDING'
  const pending = result.outcome === 'ACCEPTED' && result.final?.code === 'REFUND_PENDING'

  return (
    <Screen className="justify-center">
      {success || pending ? (
        <>
          <div className={`mb-8 flex h-40 w-40 items-center justify-center rounded-full ${success ? 'bg-brand-600' : 'bg-amber-500'} text-white shadow-lg`}>
            {success ? <CheckIcon className="h-24 w-24" strokeWidth={3} /> : <ClockIcon className="h-24 w-24" />}
          </div>
          <Title sub={success ? t.successSub : t.pendingSub}>{success ? t.successTitle : t.pendingTitle}</Title>
          {result.sms && (
            <p className="flex items-center gap-2 text-xl text-slate-600">
              <SmsIcon className="h-6 w-6" /> {t.smsNote}
            </p>
          )}
          {result.txn_id && (
            <p className="mt-4 rounded-lg bg-slate-200/70 px-4 py-2 font-mono text-lg text-slate-700">
              {t.reference}: {result.txn_id}
            </p>
          )}
        </>
      ) : (
        <>
          <div className="mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-slate-200 text-slate-600">
            <ArrowLeftIcon className="h-20 w-20" />
          </div>
          <Title sub={reason(result.reason)}>
            {result.reason === 'CUSTOMER_CANCELLED' ? t.cancelledTitle : t.returnedTitle}
          </Title>
        </>
      )}
      <Button variant="secondary" className="mt-10 w-64" onClick={onDone}>
        {t.done}
      </Button>
    </Screen>
  )
}
