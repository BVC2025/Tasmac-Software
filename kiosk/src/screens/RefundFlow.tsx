import { useEffect, useState, type ReactNode } from 'react'
import { api, type InputSource } from '../api'
import { Banner, Button, Countdown, DetailCard, Screen, Spinner, StatusBadge, Title } from '../components/ui'
import {
  ArrowLeftIcon, ArrowRightIcon, BottleIcon, CheckIcon, HourglassIcon, KeypadIcon, LeafIcon, MicIcon, QrIcon, SmsIcon, XIcon,
} from '../components/Icons'
import { useLang } from '../i18n'
import { normalizeMobile } from '../lib/upi'
import { useVoice } from '../voice'
import type { Ev, MachineView, SessionResult } from '../useMachine'
import { EvidencePhoto } from '../components/EvidencePhoto'
import { KeypadInput, SmsMobileStep } from './KeypadInput'
import { BatchSummary, rupees as toRupees } from './StatusScreens'
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
  const voice = useVoice()
  // 'choose' is announced by the machine-state cue, 'voice' by VoiceInput itself
  const STEP_CLIP: Partial<Record<Step, string>> = { qr: 'qr_show', keypad: 'keypad_enter', sms: 'sms_optional' }
  useEffect(() => {
    const clip = STEP_CLIP[step]
    if (clip) voice.play(clip)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])
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

  const amount = toRupees(view.stateData.amount_paise ?? 1000)
  const lanes = Object.values(view.lanes).sort((x, y) => x.lane - y.lane)
  const header: Record<Step, string> = {
    choose: t.chooseMethodTitle,
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
      <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-3">
        <MethodCard icon={<QrIcon className="h-14 w-14" />} title={t.methodQr} sub={t.methodQrSub} onClick={() => setStep('qr')} />
        <MethodCard icon={<MicIcon className="h-14 w-14" />} title={t.methodVoice} sub={t.methodVoiceSub} onClick={() => setStep('voice')} />
        <MethodCard icon={<KeypadIcon className="h-14 w-14" />} title={t.methodKeypad} sub={t.methodKeypadSub} onClick={() => setStep('keypad')} />
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
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-4 py-1.5 text-lg font-semibold text-brand-700 ring-1 ring-brand-100">
            <CheckIcon className="h-5 w-5" strokeWidth={3} />
            {t.eligible(view.stateData.bottle_count ?? 1, amount)}
            {lanes.length === 1 && lanes[0].brand && <span className="font-normal text-slate-600">· {lanes[0].brand}</span>}
          </span>
        )}
        <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
      </div>

      <Title sub={step === 'choose' ? t.creditedSub(amount) : undefined}>{header[step]}</Title>
      {step === 'choose' && lanes.length > 1 && (
        <div className="-mt-4 mb-6 w-full">
          <BatchSummary lanes={lanes} />
        </div>
      )}

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
      className="flex w-full items-center gap-6 rounded-3xl bg-white p-6 text-left shadow-sm ring-2 ring-slate-200 transition active:scale-[0.98] active:ring-brand-500 sm:flex-col sm:gap-4 sm:px-4 sm:py-8 sm:text-center"
    >
      <span className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700 ring-1 ring-brand-100">{icon}</span>
      <span>
        <span className="block text-2xl font-bold text-brand-900">{title}</span>
        <span className="mt-2 block text-lg leading-snug text-slate-500">{sub}</span>
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
  const rows: [ReactNode, ReactNode][] = [
    [t.amount, <span key="amount" className="text-3xl text-brand-700">₹{rupees}</span>],
    ...(c.bottle_count > 1 ? [[t.bottleCount, String(c.bottle_count)] as [ReactNode, ReactNode]] : []),
    [t.refundTo, c.destination],
    ...(c.name ? [[t.accountName, c.name] as [ReactNode, ReactNode]] : []),
    [t.method, c.kind === 'mobile' ? t.methodMobile : t.methodUpiId],
    ...(c.sms_mobile
      ? [[<span key="sms" className="inline-flex items-center gap-2"><SmsIcon className="h-5 w-5" />{t.smsTo}</span>, c.sms_mobile] as [ReactNode, ReactNode]]
      : []),
  ]
  return (
    <Screen className="justify-center">
      <div className="mb-6 flex w-full justify-end">
        <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
      </div>
      <Title sub={t.confirmProceed}>{t.refundDetails}</Title>
      <DetailCard rows={rows} />
      <div className="mt-8 grid w-full grid-cols-3 gap-4">
        <Button className="col-span-2" disabled={busy} onClick={() => send(true)}>
          <CheckIcon className="h-7 w-7" strokeWidth={3} /> {t.confirm(rupees)}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => send(false)}>
          {t.change}
        </Button>
      </div>
    </Screen>
  )
}

const istTime = (ms: number) =>
  new Date(ms).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: true }).toUpperCase()

export function Result({ result, confirm, onDone }: { result: SessionResult; confirm: Ev | null; onDone: () => void }) {
  const { t, reason } = useLang()
  const pending = result.outcome === 'ACCEPTED' && result.final?.code === 'REFUND_PENDING'
  const success = result.outcome === 'ACCEPTED' && !pending
  const amount = toRupees(result.amount_paise || 1000)
  const accepted = result.accepted || 1

  if (success) {
    const rows: [ReactNode, ReactNode][] = [
      ...(result.txn_id ? [[t.txnId, <span key="txn" className="font-mono text-lg">{result.txn_id}</span>] as [ReactNode, ReactNode]] : []),
      ...(confirm?.destination ? [[t.refundTo, confirm.destination] as [ReactNode, ReactNode]] : []),
      [t.time, istTime(result.at)],
    ]
    return (
      <Screen className="justify-center">
        <StatusBadge><CheckIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
        <Title sub={t.creditedDone}>{t.successTitle(amount)}</Title>
        <DetailCard rows={rows} />
        <div className="mt-6 grid w-full gap-3 sm:grid-cols-2">
          <p className="flex items-center gap-3 rounded-2xl bg-brand-50 px-5 py-4 text-lg font-semibold text-brand-800 ring-1 ring-brand-100">
            <BottleIcon className="h-7 w-7" /> {t.bottlesAccepted(accepted)}
          </p>
          {result.sms && (
            <p className="flex items-center gap-3 rounded-2xl bg-brand-50 px-5 py-4 text-lg font-semibold text-brand-800 ring-1 ring-brand-100">
              <SmsIcon className="h-7 w-7" /> {t.smsSent}
            </p>
          )}
        </div>
        {result.bottles.length > 1 && result.accepted < result.bottles.length && (
          <div className="mt-4 w-full"><BatchSummary lanes={result.bottles} /></div>
        )}
        <p className="mt-8 flex items-center gap-2 text-xl text-slate-600"><LeafIcon className="h-6 w-6 text-brand-600" /> {t.successSub}</p>
        <Button className="mt-8 w-full max-w-md" onClick={onDone}>{t.done}</Button>
      </Screen>
    )
  }

  if (pending) {
    return (
      <Screen className="justify-center">
        <StatusBadge tone="warn"><HourglassIcon className="h-20 w-20" /></StatusBadge>
        <Title sub={t.pendingNote}>{t.paymentProcessing}</Title>
        <p className="mb-2 text-xl font-semibold text-brand-800">{t.pendingSub(amount)}</p>
        {result.txn_id && <p className="mt-2 rounded-lg bg-slate-200/70 px-4 py-2 font-mono text-lg text-slate-700">{t.txnId}: {result.txn_id}</p>}
        <Button variant="secondary" className="mt-10 w-full max-w-md" onClick={onDone}>{t.backHome}</Button>
      </Screen>
    )
  }

  const failed = result.reason === 'PAYOUT_FAILED'
  return (
    <Screen className="justify-center">
      <StatusBadge tone={failed ? 'error' : 'muted'}>
        {failed ? <XIcon className="h-20 w-20" strokeWidth={3} /> : <ArrowLeftIcon className="h-20 w-20" />}
      </StatusBadge>
      <Title sub={failed ? t.refundFailedSub : reason(result.reason)}>
        {failed ? t.refundFailed : result.reason === 'CUSTOMER_CANCELLED' ? t.cancelledTitle : t.returnedTitle}
      </Title>
      {result.bottles.length > 1 && <div className="mb-4 w-full"><BatchSummary lanes={result.bottles} /></div>}
      {result.bottles.some((b) => b.evidence) && (
        <div className="mb-6 flex w-full flex-wrap justify-center gap-4">
          {result.bottles.filter((b) => b.evidence).map((b) => (
            <EvidencePhoto key={b.lane} sessionId={result.session_id} lane={b.lane} compact={result.bottles.length > 1} />
          ))}
        </div>
      )}
      {result.txn_id && <p className="mb-4 rounded-lg bg-slate-200/70 px-4 py-2 font-mono text-lg text-slate-700">{t.txnId}: {result.txn_id}</p>}
      {failed && <p className="mt-2 rounded-2xl bg-red-600 px-8 py-4 text-xl font-bold text-white shadow">{t.contactStaff}</p>}
      <Button variant="secondary" className="mt-10 w-full max-w-md" onClick={onDone}>
        {t.backHome} <ArrowRightIcon className="h-6 w-6" />
      </Button>
    </Screen>
  )
}
