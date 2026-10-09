import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { Banner, Countdown, DetailCard, ProgressBar, ScanFrame, Screen, Spinner, StatusBadge, Stepper, Title } from '../components/ui'
import { AlertIcon, ArrowRightIcon, BottleIcon, CheckIcon, ClockIcon, LeafIcon, XIcon } from '../components/Icons'
import { InsertAnimation } from '../components/InsertAnimation'
import { RealBottle, StickerCloseup } from '../components/BottleArt'
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

// ---------------- welcome (attract screen) ----------------

function BottlesArt({ className = '' }: { className?: string }) {
  const shapes = [
    { x: 70, h: 150 },
    { x: 120, h: 190 },
    { x: 175, h: 220 },
    { x: 230, h: 175 },
    { x: 280, h: 140 },
  ]
  return (
    <svg viewBox="0 0 340 230" className={className} aria-hidden>
      {shapes.map(({ x, h }) => {
        const top = 215 - h
        return (
          <g key={x} fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinejoin="round">
            <rect x={x - 6} y={top} width="12" height="10" rx="2" />
            <path d={`M${x - 6} ${top + 10}v${h * 0.18}c0 8 -14 14 -14 30v${h * 0.82 - 40 - h * 0.18}a6 6 0 0 0 6 6h28a6 6 0 0 0 6 -6v${-(h * 0.82 - 40 - h * 0.18)}c0 -16 -14 -22 -14 -30v${-h * 0.18}`} />
            <path d={`M${x - 20} ${top + h * 0.55}h40M${x - 20} ${top + h * 0.75}h40`} opacity="0.6" />
          </g>
        )
      })}
      <g transform="translate(14 150) rotate(-25)" fill="currentColor" opacity="0.9">
        <path d="M0 40C0 15 18 0 45 0C43 26 27 40 0 40z" />
      </g>
      <line x1="10" y1="217" x2="330" y2="217" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.5" />
    </svg>
  )
}

/** First screen for a new customer: what the machine does, language, Start. */
export function Welcome({ onStart }: { onStart: () => void }) {
  const { t, lang, setLang } = useLang()
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-gradient-to-b from-brand-800 to-brand-900 px-8 py-10 text-center text-white">
      {/* TASMAC and the service name are already in the header */}
      <h1 className="text-6xl font-extrabold tall:text-7xl">{t.welcomeTitle}</h1>
      <p className="mt-4 max-w-2xl text-2xl text-white/85">{t.welcomeSub}</p>
      <BottlesArt className="my-10 h-60 w-auto text-emerald-300 tall:my-16 tall:h-80" />
      <div className="flex rounded-full bg-white/10 p-1.5 ring-1 ring-white/20">
        {(['en', 'ta'] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLang(l)}
            className={`min-h-14 min-w-40 rounded-full px-6 text-xl font-bold ${lang === l ? 'bg-emerald-400 text-brand-900' : 'text-white'}`}
          >
            {l === 'ta' ? 'தமிழ்' : 'English'}
          </button>
        ))}
      </div>
      <button
        onClick={onStart}
        className="mt-10 inline-flex min-h-20 w-full max-w-lg items-center justify-center gap-4 rounded-2xl bg-brand-500 text-3xl font-extrabold shadow-lg shadow-black/30 active:bg-brand-600"
      >
        {t.start} <ArrowRightIcon className="h-9 w-9" strokeWidth={2.5} />
      </button>
      <p className="mt-10 flex items-center gap-2 text-lg text-emerald-200/80">
        <LeafIcon className="h-6 w-6" /> {t.tagline}
      </p>
    </div>
  )
}

// ---------------- insert ----------------

export function Ready({ lanes }: { lanes: number }) {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <Title sub={t.insertSub(lanes)}>{t.insertTitle}</Title>
      <div className="mb-8 rounded-[2rem] bg-gradient-to-b from-slate-800 to-slate-950 p-4 shadow-2xl ring-8 ring-slate-200">
        <InsertAnimation className="h-[20rem] w-auto sm:h-[24rem] tall:h-[38rem]" />
      </div>
      <Stepper steps={t.flowSteps} current={0} />
      <div className="mt-8 inline-flex items-baseline gap-2 rounded-full bg-accent/15 px-6 py-2 text-2xl font-extrabold text-amber-800">
        ₹10 <span className="text-lg font-semibold">/ {t.appSub}</span>
      </div>
    </Screen>
  )
}

// ---------------- checking ----------------

const STEP_INDEX: Record<string, number> = {
  DETECTED: 0,
  POSITIONING: 0,
  INSPECTING: 1,
  SCANNING_REFUND_QR: 2,
  SCANNING_MFG_QR: 3,
  VERIFYING: 4,
  VALID: 5,
  ACCEPTED: 5,
}

export const isCheckingState = (s: string) => s === 'COLLECTING' || s === 'CHECKING'

/** Live picture from the machine camera (vision_driver: camera), else null. */
function useCameraFeed(active: boolean, lane: number) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [image, setImage] = useState<string | null>(null)
  useEffect(() => {
    api.cameraStatus().then((s) => setEnabled(s.enabled), () => setEnabled(false))
  }, [])
  useEffect(() => {
    if (!active || !enabled) return
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const p = await api.cameraPreview(lane, 640)
        if (!stopped) setImage(p.image)
      } catch {
        /* keep the last picture */
      }
      if (!stopped) timer = window.setTimeout(tick, 400)
    }
    tick()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [active, enabled, lane])
  return active ? image : null
}

function DoneChip({ children }: { children: string }) {
  return (
    <span className="mb-6 inline-flex items-center gap-2 rounded-full bg-brand-50 px-5 py-2 text-lg font-semibold text-brand-700 ring-1 ring-brand-100">
      <CheckIcon className="h-5 w-5" strokeWidth={3} /> {children}
    </span>
  )
}

function StepDots({ current }: { current: number }) {
  const { t } = useLang()
  return (
    <ol className="mb-10 flex w-full max-w-2xl items-center">
      {t.stepShort.map((label, i) => (
        <li key={label} className="flex flex-1 flex-col items-center gap-2">
          <div className="flex w-full items-center">
            <span className={`h-1 flex-1 ${i === 0 ? 'opacity-0' : i <= current ? 'bg-brand-600' : 'bg-slate-200'}`} />
            <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
              i < current ? 'bg-brand-600 text-white' : i === current ? 'bg-white text-brand-700 ring-4 ring-brand-500' : 'bg-slate-200 text-slate-400'
            }`}>
              {i < current ? <CheckIcon className="h-5 w-5" strokeWidth={3} /> : i + 1}
            </span>
            <span className={`h-1 flex-1 ${i === t.stepShort.length - 1 ? 'opacity-0' : i < current ? 'bg-brand-600' : 'bg-slate-200'}`} />
          </div>
          <span className={`text-center text-sm font-semibold ${i <= current ? 'text-brand-800' : 'text-slate-400'}`}>{label}</span>
        </li>
      ))}
    </ol>
  )
}

/** One bottle: a full screen per check step, as in the customer flow design. */
function BottleSteps({ lane }: { lane: LaneView }) {
  const { t, reason } = useLang()
  const idx = STEP_INDEX[lane.step] ?? (lane.step === 'REJECTED' || lane.step === 'RETURNED' ? -1 : 0)
  const camera = useCameraFeed(idx >= 1 && idx <= 3, lane.lane)
  const picture = (fallback: ReactNode) =>
    camera ? <img src={camera} alt="" className="h-full w-full object-cover" /> : fallback

  if (idx === -1) {
    return (
      <>
        <StatusBadge tone="error"><XIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
        <Title sub={reason(lane.reason)}>{t.returnedTitle}</Title>
        <TakeBottle />
      </>
    )
  }

  let body
  if (idx === 0) {
    body = (
      <>
        <StatusBadge><CheckIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
        <Title sub={t.detectedSub}>{t.detectedTitle}</Title>
        <ProgressBar />
        <RealBottle turning={false} className="mt-10 h-56 w-auto drop-shadow-xl" />
      </>
    )
  } else if (idx === 1) {
    body = (
      <>
        <Title sub={t.inspectingSub}>{t.inspectingTitle}</Title>
        <ScanFrame>{picture(<RealBottle className="h-[88%] w-auto" />)}</ScanFrame>
        <p className="mt-6 flex items-center gap-3 text-lg text-slate-600"><Spinner className="h-6 w-6" thin /> {t.cameraAnalysis}</p>
      </>
    )
  } else if (idx === 2 || idx === 3) {
    body = (
      <>
        <DoneChip>{idx === 2 ? t.conditionOk : t.refundQrOk}</DoneChip>
        <Title sub={idx === 2 ? t.refundQrSub : t.mfgQrSub}>{idx === 2 ? t.refundQrTitle : t.mfgQrTitle}</Title>
        <ScanFrame tone="alert">
          {picture(<StickerCloseup key={idx} kind={idx === 2 ? 'refund' : 'mfg'} className="h-full w-full" />)}
        </ScanFrame>
        <p className="mt-6 flex items-center gap-3 text-lg text-slate-600"><Spinner className="h-6 w-6" thin /> {t.scanning}</p>
      </>
    )
  } else if (idx === 4) {
    body = (
      <>
        <StatusBadge><CheckIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
        <Title sub={t.verifyingTitle}>{t.refundQrOk}</Title>
        <ProgressBar />
      </>
    )
  } else {
    body = (
      <>
        <StatusBadge><CheckIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
        <Title>{t.verifiedTitle}</Title>
        <div className="w-full max-w-xl">
          <DetailCard rows={[
            ...(lane.brand ? [[t.brand, lane.brand] as [string, string]] : []),
            [t.refund, `₹${rupees(lane.amount_paise ?? 1000)}`],
          ]} />
        </div>
      </>
    )
  }

  return (
    <>
      <StepDots current={Math.min(idx, 5)} />
      {body}
    </>
  )
}

/** One inlet's bottle when several are checked together. */
function LaneCard({ lane, compact }: { lane: LaneView; compact: boolean }) {
  const { t, reason } = useLang()
  const done = lane.step in STEP_INDEX && STEP_INDEX[lane.step] < 5 ? null : lane.step
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
          <span className="animate-pop flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-white">
            <CheckIcon className="h-10 w-10" strokeWidth={3} />
          </span>
          <span className="text-xl font-bold text-brand-800">{done === 'ACCEPTED' ? t.laneAccepted : t.laneValid}</span>
          {lane.brand && <span className="text-base text-slate-600">{lane.brand}</span>}
          <span className="text-2xl font-extrabold text-brand-900">₹{rupees(lane.amount_paise ?? 1000)}</span>
        </div>
      ) : done === 'REJECTED' || done === 'RETURNED' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-4 text-center">
          <span className="animate-pop flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-red-600">
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

  const hand = handWarning && (
    <div className="mb-6 w-full">
      <Banner tone="warn">{t.removeHand}</Banner>
    </div>
  )

  // Several inlets: show which ones have a bottle while the batch window is open
  if (collecting && view.laneCount > 1) {
    const filled = (view.stateData.lanes as number[] | undefined) ?? lanes.map((l) => l.lane)
    return (
      <Screen wide>
        <div className="mb-4 flex w-full justify-end">
          <Countdown seconds={view.stateData.timeout_s} since={view.stateAt} />
        </div>
        <Title sub={t.collectingSub}>{t.collectingTitle}</Title>
        {hand}
        <div className={`grid w-full gap-4 ${view.laneCount === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {Array.from({ length: view.laneCount }, (_, i) => i + 1).map((ln) => {
            const on = filled.includes(ln)
            return (
              <div key={ln} className={`flex flex-col items-center gap-3 rounded-3xl p-6 ring-2 ${on ? 'bg-brand-50 ring-brand-500' : 'border-dashed bg-white/60 ring-slate-200'}`}>
                <BottleIcon className={`h-16 w-16 ${on ? 'text-brand-700' : 'text-slate-300'}`} />
                <span className={`text-xl font-bold ${on ? 'text-brand-900' : 'text-slate-400'}`}>{t.laneLabel(ln)}</span>
                {on && <CheckIcon className="h-7 w-7 text-brand-600" strokeWidth={3} />}
              </div>
            )
          })}
        </div>
      </Screen>
    )
  }

  // One bottle: step-by-step screens
  if (lanes.length <= 1) {
    return (
      <Screen className="justify-center">
        {hand}
        <BottleSteps lane={lanes[0] ?? { lane: 1, step: 'DETECTED' }} />
      </Screen>
    )
  }

  return (
    <Screen wide>
      <Title sub={t.checkingSub}>{t.checkingMany(lanes.length)}</Title>
      {hand}
      <div className={`grid w-full gap-4 ${lanes.length === 3 ? 'grid-cols-1 sm:grid-cols-3' : 'grid-cols-1 sm:grid-cols-2'}`}>
        {lanes.map((l) => (
          <LaneCard key={l.lane} lane={l} compact />
        ))}
      </div>
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

function TakeBottle() {
  const { t } = useLang()
  return (
    <div className="mt-4 flex items-center gap-4 rounded-2xl bg-amber-50 px-8 py-5 text-2xl font-bold text-amber-900 ring-1 ring-amber-200">
      <BottleIcon className="h-10 w-10" />
      {t.takeBottle}
    </div>
  )
}

export function Paying({ amountPaise }: { amountPaise?: number }) {
  const { t } = useLang()
  const amount = rupees(amountPaise ?? 1000)
  return (
    <Screen className="justify-center">
      <div className="relative mb-10 flex h-48 w-48 items-center justify-center">
        <div className="absolute inset-0 animate-spin rounded-full border-[12px] border-brand-100 border-t-brand-600" />
        <span className="text-5xl font-extrabold text-brand-800">₹{amount}</span>
      </div>
      <Title sub={t.payingSub}>{t.payingTitle(amount)}</Title>
      <p className="flex items-center gap-3 rounded-2xl bg-amber-50 px-6 py-3 text-xl font-semibold text-amber-900 ring-1 ring-amber-200">
        <BottleIcon className="h-7 w-7" /> {t.doNotRemove}
      </p>
    </Screen>
  )
}

export function Rejecting({ reason, lanes }: { reason?: string; lanes: LaneView[] }) {
  const { t, reason: reasonText } = useLang()
  return (
    <Screen className="justify-center">
      <StatusBadge tone="error"><XIcon className="h-20 w-20" strokeWidth={3} /></StatusBadge>
      {/* each bottle failed its own check: the chips say why; otherwise the batch reason (e.g. payment failed) */}
      <Title sub={lanes.length > 1 && lanes.every((l) => l.step === 'REJECTED') ? undefined : reasonText(reason)}>
        {reason === 'PAYOUT_FAILED' ? t.refundFailed : t.returnedTitle}
      </Title>
      {lanes.length > 1 && (
        <div className="mb-6 w-full">
          <BatchSummary lanes={lanes} handingBack={reason} />
        </div>
      )}
      <TakeBottle />
    </Screen>
  )
}

/** "10:00" -> "10:00 AM" */
const clock12 = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

/** Outside service hours: when the machine is open, and when it opens next. */
export function Closed({ hours, nextOpen }: { hours: { start: string; end: string }[]; nextOpen?: string | null }) {
  const { t } = useLang()
  const [now] = useState(() => new Date())
  let opens: string | null = null
  if (nextOpen) {
    const d = new Date(nextOpen)
    const ist = (x: Date) => x.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
    const day = ist(d) === ist(now) ? t.today : t.tomorrow
    const time = d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit', hour12: true }).toUpperCase()
    opens = t.opensAt(`${day} ${time}`)
  }
  return (
    <Screen className="justify-center">
      <StatusBadge tone="warn"><ClockIcon className="h-20 w-20" /></StatusBadge>
      <Title sub={t.closedSub}>{t.closedTitle}</Title>
      <div className="w-full max-w-xl overflow-hidden rounded-3xl bg-white text-center shadow-sm ring-1 ring-slate-200">
        <p className="bg-brand-50 px-8 py-4 text-xl font-bold text-brand-800">{t.serviceHours}</p>
        <ul className="divide-y divide-slate-100">
          {hours.map((w) => (
            <li key={w.start + w.end} className="px-8 py-5 text-3xl font-extrabold text-brand-900 tabular-nums">
              {clock12(w.start)} – {clock12(w.end)}
            </li>
          ))}
        </ul>
      </div>
      {opens && <p className="mt-8 rounded-full bg-amber-50 px-6 py-3 text-2xl font-bold text-amber-900 ring-1 ring-amber-200">{opens}</p>}
      <p className="mt-8 flex items-center gap-2 text-xl text-slate-600"><LeafIcon className="h-6 w-6 text-brand-600" /> {t.closedThanks}</p>
    </Screen>
  )
}

export function OutOfService({ reason, showReason }: { reason: string | null; showReason: boolean }) {
  const { t } = useLang()
  return (
    <Screen className="justify-center">
      <StatusBadge tone="error"><AlertIcon className="h-20 w-20" /></StatusBadge>
      <Title sub={t.oosSub}>{t.oosTitle}</Title>
      <p className="text-xl text-slate-600">{t.oosContact}</p>
      {showReason && reason && (
        <p className="mt-6 inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 font-mono text-sm text-amber-300">
          <AlertIcon className="h-4 w-4" /> {reason}
        </p>
      )}
    </Screen>
  )
}

