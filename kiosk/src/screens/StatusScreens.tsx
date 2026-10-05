import { Banner, Screen, Spinner, Title } from '../components/ui'
import { AlertIcon, BottleIcon, CheckIcon, WrenchIcon, XIcon } from '../components/Icons'
import { InsertAnimation } from '../components/InsertAnimation'
import { useLang } from '../i18n'
import type { MachineView } from '../useMachine'

export function Connecting() {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <Spinner />
      <p className="mt-8 text-2xl text-slate-600">{t.connecting}</p>
    </Screen>
  )
}

export function Starting() {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <Spinner />
      <Title sub={t.startingSub}>{t.starting}</Title>
    </Screen>
  )
}

export function Ready() {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <Title sub={t.insertSub}>{t.insertTitle}</Title>
      <InsertAnimation className="my-4 h-[22rem] w-auto drop-shadow-xl sm:h-[26rem] tall:my-10 tall:h-[44rem]" />
      <div className="mt-6 inline-flex items-baseline gap-2 rounded-full bg-accent/15 px-6 py-2 text-2xl font-extrabold text-amber-800">
        ₹10 <span className="text-lg font-semibold">/ {t.appSub}</span>
      </div>
      <ol className="mt-10 grid w-full grid-cols-3 gap-4">
        {t.insertSteps.map((s, i) => (
          <li key={s} className="flex flex-col items-center gap-3 rounded-2xl bg-white p-5 text-center shadow-sm ring-1 ring-slate-200">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-600 text-xl font-bold text-white">
              {i + 1}
            </span>
            <span className="text-lg font-semibold text-slate-700">{s}</span>
          </li>
        ))}
      </ol>
    </Screen>
  )
}

const CHECK_STEP: Record<string, number> = {
  BOTTLE_DETECTED: 0,
  POSITIONING: 1,
  INSPECTING: 2,
  SCANNING_REFUND_QR: 3,
  SCANNING_MFG_QR: 4,
  VERIFYING: 5,
}

export const isCheckingState = (s: string) => s in CHECK_STEP

export function Checking({ view }: { view: MachineView }) {
  const { t } = useLang()
  const current = CHECK_STEP[view.state] ?? 0
  const handWarning = view.message?.code === 'REMOVE_HAND' && view.state === 'BOTTLE_DETECTED'
  return (
    <Screen>
      <Title sub={t.checkingSub}>{t.checkingTitle}</Title>
      {handWarning && (
        <div className="mb-6 w-full">
          <Banner tone="warn">{t.removeHand}</Banner>
        </div>
      )}
      <ol className="w-full max-w-xl space-y-3">
        {t.steps.map((label, i) => {
          const done = i < current
          const active = i === current
          return (
            <li
              key={label}
              className={`flex items-center gap-5 rounded-2xl px-6 py-4 transition-all ${
                active ? 'bg-white shadow-md ring-2 ring-brand-500' : done ? 'bg-white/70' : 'bg-white/40'
              }`}
            >
              <span
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${
                  done ? 'bg-brand-600 text-white' : active ? 'bg-brand-50' : 'bg-slate-200 text-slate-400'
                }`}
              >
                {done ? <CheckIcon className="h-6 w-6" strokeWidth={3} /> : active ? <Spinner className="h-7 w-7" thin /> : i + 1}
              </span>
              <span className={`text-xl ${active ? 'font-bold text-brand-900' : done ? 'text-slate-700' : 'text-slate-400'}`}>
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </Screen>
  )
}

export function Paying() {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <div className="relative mb-10 flex h-40 w-40 items-center justify-center">
        <div className="animate-pulse-ring absolute inset-0 rounded-full bg-brand-500/30" />
        <div className="relative flex h-32 w-32 items-center justify-center rounded-full bg-brand-600 text-5xl font-extrabold text-white">
          ₹10
        </div>
      </div>
      <Title sub={t.payingSub}>{t.payingTitle}</Title>
    </Screen>
  )
}

export function Rejecting({ reason }: { reason?: string }) {
  const { t, reason: reasonText } = useLang()
  return (
    <Screen className="justify-center">
      <div className="mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-red-100">
        <XIcon className="h-20 w-20 text-red-600" strokeWidth={2.5} />
      </div>
      <Title sub={reasonText(reason)}>{t.returnedTitle}</Title>
      <div className="mt-4 flex items-center gap-4 rounded-2xl bg-amber-50 px-8 py-5 text-2xl font-bold text-amber-900 ring-1 ring-amber-200">
        <BottleIcon className="h-10 w-10" />
        {t.takeBottle}
      </div>
    </Screen>
  )
}

export function OutOfService({ reason, showReason }: { reason: string | null; showReason: boolean }) {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <div className="mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-slate-200">
        <WrenchIcon className="h-16 w-16 text-slate-600" />
      </div>
      <Title sub={t.oosSub}>{t.oosTitle}</Title>
      {showReason && reason && (
        <p className="mt-2 inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 font-mono text-sm text-amber-300">
          <AlertIcon className="h-4 w-4" /> {reason}
        </p>
      )}
    </Screen>
  )
}
