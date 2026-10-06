import { Banner, Countdown, Screen, Spinner, Title } from '../components/ui'
import { AlertIcon, BottleIcon, CheckIcon, WrenchIcon, XIcon } from '../components/Icons'
import { InsertAnimation } from '../components/InsertAnimation'
import { useLang } from '../i18n'
import type { LaneView, MachineView } from '../useMachine'

export const rupees = (paise: number | undefined) => String(Math.round((paise ?? 0) / 100))

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

export function Ready({ lanes }: { lanes: number }) {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <Title sub={t.insertSub(lanes)}>{t.insertTitle}</Title>
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

// Lane step -> index in t.steps (positioning .. eligibility)
const STEP_INDEX: Record<string, number> = {
  DETECTED: 0,
  POSITIONING: 0,
  INSPECTING: 1,
  SCANNING_REFUND_QR: 2,
  SCANNING_MFG_QR: 3,
  VERIFYING: 4,
}

export const isCheckingState = (s: string) => s === 'COLLECTING' || s === 'CHECKING'

/** One inlet's bottle: live step list while checking, then its verdict. */
function LaneCard({ lane, compact }: { lane: LaneView; compact: boolean }) {
  const { t, reason } = useLang()
  const done = lane.step in STEP_INDEX ? null : lane.step
  const current = STEP_INDEX[lane.step] ?? 0

  const tone =
    done === 'VALID' || done === 'ACCEPTED'
      ? 'ring-brand-500 bg-brand-50'
      : done === 'REJECTED' || done === 'RETURNED'
        ? 'ring-red-300 bg-red-50'
        : 'ring-slate-200 bg-white'

  return (
    <div className={`flex flex-col rounded-3xl p-5 shadow-sm ring-2 ${tone}`}>
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-700 text-white">
          <BottleIcon className="h-6 w-6" />
        </span>
        <span className="text-2xl font-extrabold text-brand-900">{t.laneLabel(lane.lane)}</span>
      </div>

      {done === 'VALID' || done === 'ACCEPTED' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-4 text-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-white">
            <CheckIcon className="h-10 w-10" strokeWidth={3} />
          </span>
          <span className="text-xl font-bold text-brand-800">{done === 'ACCEPTED' ? t.laneAccepted : t.laneValid}</span>
          <span className="text-2xl font-extrabold text-brand-900">₹{rupees(lane.amount_paise ?? 1000)}</span>
        </div>
      ) : done === 'REJECTED' || done === 'RETURNED' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-4 text-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-red-600">
            <XIcon className="h-10 w-10" strokeWidth={3} />
          </span>
          <span className="text-lg font-bold text-red-800">{reason(lane.reason)}</span>
          <span className="text-base font-semibold text-amber-800">{t.laneReturned}</span>
        </div>
      ) : (
        <ol className={compact ? 'space-y-2' : 'space-y-3'}>
          {t.steps.map((label, i) => {
            const passed = i < current
            const active = i === current
            return (
              <li key={label} className="flex items-center gap-3">
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm ${
                    passed ? 'bg-brand-600 text-white' : active ? 'bg-brand-50' : 'bg-slate-200 text-slate-400'
                  }`}
                >
                  {passed ? <CheckIcon className="h-5 w-5" strokeWidth={3} /> : active ? <Spinner className="h-5 w-5" thin /> : i + 1}
                </span>
                <span className={`${compact ? 'text-base' : 'text-lg'} ${active ? 'font-bold text-brand-900' : passed ? 'text-slate-700' : 'text-slate-400'}`}>
                  {label}
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export function Checking({ view }: { view: MachineView }) {
  const { t } = useLang()
  const collecting = view.state === 'COLLECTING'
  const lanes = Object.values(view.lanes).sort((a, b) => a.lane - b.lane)
  const handWarning = view.message?.code === 'REMOVE_HAND'
  const many = lanes.length > 1 || (collecting && view.laneCount > 1)

  return (
    <Screen wide>
      {collecting ? (
        <>
          <div className="mb-4 flex w-full justify-end">
            <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
          </div>
          <Title sub={t.collectingSub}>{t.collectingTitle}</Title>
        </>
      ) : (
        <Title sub={t.checkingSub}>{lanes.length > 1 ? t.checkingMany(lanes.length) : t.checkingTitle}</Title>
      )}
      {handWarning && (
        <div className="mb-6 w-full">
          <Banner tone="warn">{t.removeHand}</Banner>
        </div>
      )}

      {collecting ? (
        <div className={`grid w-full gap-4 ${view.laneCount === 3 ? 'grid-cols-3' : view.laneCount === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {Array.from({ length: view.laneCount }, (_, i) => i + 1).map((ln) => {
            const filled = (view.stateData.lanes as number[] | undefined)?.includes(ln)
            return (
              <div key={ln} className={`flex flex-col items-center gap-3 rounded-3xl p-6 ring-2 ${filled ? 'bg-brand-50 ring-brand-500' : 'border-dashed bg-white/60 ring-slate-200'}`}>
                <BottleIcon className={`h-16 w-16 ${filled ? 'text-brand-700' : 'text-slate-300'}`} />
                <span className={`text-xl font-bold ${filled ? 'text-brand-900' : 'text-slate-400'}`}>{t.laneLabel(ln)}</span>
                {filled && <CheckIcon className="h-7 w-7 text-brand-600" strokeWidth={3} />}
              </div>
            )
          })}
        </div>
      ) : (
        <div className={`grid w-full gap-4 ${lanes.length === 3 ? 'grid-cols-1 sm:grid-cols-3' : lanes.length === 2 ? 'grid-cols-1 sm:grid-cols-2' : 'mx-auto max-w-xl grid-cols-1'}`}>
          {lanes.map((l) => (
            <LaneCard key={l.lane} lane={l} compact={many} />
          ))}
        </div>
      )}
    </Screen>
  )
}

/** Small per-bottle summary used on the refund, result and returned screens. */
export function BatchSummary({ lanes, handingBack }: { lanes: LaneView[]; handingBack?: string }) {
  const { t, reason } = useLang()
  if (lanes.length < 2) return null
  return (
    <div className="flex w-full flex-wrap justify-center gap-2">
      {lanes.map((l) => {
        // while the whole batch is handed back, held (VALID) bottles are on their way out too
        if (handingBack && l.step === 'VALID') l = { ...l, step: 'RETURNED', reason: handingBack }
        const ok = l.step === 'VALID' || l.step === 'ACCEPTED'
        return (
          <span key={l.lane} className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-base font-semibold ${ok ? 'bg-brand-50 text-brand-800 ring-1 ring-brand-100' : 'bg-red-50 text-red-800 ring-1 ring-red-100'}`}>
            {ok ? <CheckIcon className="h-5 w-5" strokeWidth={3} /> : <XIcon className="h-5 w-5" strokeWidth={3} />}
            {t.laneLabel(l.lane)}
            {!ok && <span className="font-normal">· {reason(l.reason)}</span>}
          </span>
        )
      })}
    </div>
  )
}

export function Paying({ amountPaise }: { amountPaise?: number }) {
  const { t } = useLang()
  const amount = rupees(amountPaise ?? 1000)
  return (
    <Screen className="justify-center">
      <div className="relative mb-10 flex h-40 w-40 items-center justify-center">
        <div className="animate-pulse-ring absolute inset-0 rounded-full bg-brand-500/30" />
        <div className="relative flex h-32 w-32 items-center justify-center rounded-full bg-brand-600 text-5xl font-extrabold text-white">
          ₹{amount}
        </div>
      </div>
      <Title sub={t.payingSub}>{t.payingTitle(amount)}</Title>
    </Screen>
  )
}

export function Rejecting({ reason, lanes }: { reason?: string; lanes: LaneView[] }) {
  const { t, reason: reasonText } = useLang()
  return (
    <Screen className="justify-center">
      <div className="mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-red-100">
        <XIcon className="h-20 w-20 text-red-600" strokeWidth={2.5} />
      </div>
      {/* each bottle failed its own check: the chips say why; otherwise the batch reason (e.g. payment failed) */}
      <Title sub={lanes.length > 1 && lanes.every((l) => l.step === 'REJECTED') ? undefined : reasonText(reason)}>
        {t.returnedTitle}
      </Title>
      {lanes.length > 1 && (
        <div className="mb-6 w-full">
          <BatchSummary lanes={lanes} handingBack={reason} />
        </div>
      )}
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
