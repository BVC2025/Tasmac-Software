import { useEffect, useRef, useState } from 'react'
import { Clock } from './components/Clock'
import { DevPanel } from './components/DevPanel'
import { SpeakerIcon, SpeakerOffIcon, WifiIcon, WifiOffIcon } from './components/Icons'
import { LangProvider, useLang } from './i18n'
import { Confirm, RefundMethod, Result } from './screens/RefundFlow'
import { Checking, Connecting, isCheckingState, OutOfService, Paying, Ready, Rejecting, Starting, Welcome } from './screens/StatusScreens'
import { useMachine, type MachineView } from './useMachine'
import { cueFor, rejectClip, useVoice, VoiceProvider } from './voice'

function VoiceToggle() {
  const { enabled, available, blocked, toggle } = useVoice()
  if (!available) return null
  return (
    <button
      onClick={toggle}
      aria-label={enabled ? 'Mute voice' : 'Unmute voice'}
      className={`relative flex h-12 w-12 items-center justify-center rounded-full ${enabled ? 'bg-white/15' : 'bg-white/5 text-white/60'}`}
    >
      {enabled ? <SpeakerIcon className="h-7 w-7" /> : <SpeakerOffIcon className="h-7 w-7" />}
      {enabled && blocked && <span className="absolute top-2 right-2 h-3 w-3 animate-pulse rounded-full bg-accent" />}
    </button>
  )
}

function Header({ view }: { view: MachineView }) {
  const { t, lang, setLang } = useLang()
  return (
    <header className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 bg-brand-800 px-6 py-3 text-white shadow-lg">
      <div className="flex items-center gap-3">
        <span title={view.connected ? 'Online' : 'Offline'} className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10">
          {view.connected ? <WifiIcon className="h-7 w-7 text-emerald-300" /> : <WifiOffIcon className="h-7 w-7 text-red-300" />}
        </span>
        <VoiceToggle />
      </div>
      <div className="text-center">
        <p className="text-3xl leading-none font-extrabold tracking-[0.18em]">TASMAC</p>
        <p className="mt-1 text-sm opacity-75">
          {t.appTitle} · {view.machineId || '—'}
        </p>
      </div>
      <div className="flex items-center justify-end gap-4">
        <div className="flex rounded-full bg-white/15 p-1">
          {(['ta', 'en'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`min-h-11 rounded-full px-4 text-base font-semibold ${lang === l ? 'bg-white text-brand-700' : 'text-white'}`}
            >
              {l === 'ta' ? 'தமிழ்' : 'English'}
            </button>
          ))}
        </div>
        <Clock className="text-right" />
      </div>
    </header>
  )
}

function Body({ view, clearResult, welcome, onStart }: {
  view: MachineView; clearResult: () => void; welcome: boolean; onStart: () => void
}) {
  const s = view.state
  if (!view.connected) return <Connecting />
  if (welcome) return <Welcome onStart={onStart} />
  if (s === 'OUT_OF_SERVICE') return <OutOfService reason={view.fault ?? view.stateData.reason} showReason={view.simulation} />
  // Hold the outcome screen for a few seconds after the session ends
  if (view.result && (s === 'READY' || s === 'REJECTING')) return <Result result={view.result} confirm={view.confirm} onDone={clearResult} />
  if (s === 'STARTING' || s === 'HEALTH_CHECK') return <Starting />
  if (s === 'READY') return <Ready lanes={view.laneCount} />
  if (isCheckingState(s)) return <Checking view={view} />
  if (s === 'SELECT_REFUND_METHOD') return <RefundMethod key={view.stateAt} view={view} />
  if (s === 'CONFIRMING') return <Confirm key={view.stateAt} view={view} />
  if (s === 'PAYING' || s === 'ACCEPTING') return <Paying amountPaise={view.stateData.amount_paise ?? view.confirm?.amount_paise} />
  if (s === 'REJECTING')
    return <Rejecting reason={view.stateData.reason} lanes={Object.values(view.lanes).sort((a, b) => a.lane - b.lane)} />
  return <Starting />
}

function Kiosk() {
  const [view, clearResult] = useMachine()
  const { setLang } = useLang()

  const voice = useVoice()

  // Welcome screen until the customer taps Start (a bottle in the inlet skips it)
  const [started, setStarted] = useState(false)
  const welcome = view.state === 'READY' && !view.result && !started

  // Back to Tamil and the welcome screen for the next customer
  // (silently: the old prompt must not replay)
  const hadResult = useRef(false)
  useEffect(() => {
    if (view.result) hadResult.current = true
    else if (hadResult.current) {
      hadResult.current = false
      voice.forget()
      setLang('ta')
      setStarted(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.result, setLang])

  // Nobody inserted a bottle after Start: back to the welcome screen
  useEffect(() => {
    if (!started || view.state !== 'READY') return
    const id = window.setTimeout(() => setStarted(false), 90_000)
    return () => window.clearTimeout(id)
  }, [started, view.state, view.stateAt])

  // Spoken guidance: one clip per new instruction, in the selected language.
  // Played a tick later so a language reset in the same update is applied first.
  const cue = welcome ? null : cueFor(view)
  const cueKey = cue?.key
  const cueClip = cue?.clip
  const cueQueue = cue?.queue
  useEffect(() => {
    if (!cueClip) return
    const t = window.setTimeout(() => voice.play(cueClip, { queue: cueQueue }), 60)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cueKey])

  // Each rejected bottle of a batch is announced with its reason, one after another
  const spokenRejects = useRef(new Set<number>())
  useEffect(() => {
    const lanes = Object.values(view.lanes)
    if (!lanes.length) spokenRejects.current.clear()
    for (const l of lanes) {
      if (l.step === 'REJECTED' && !spokenRejects.current.has(l.lane)) {
        spokenRejects.current.add(l.lane)
        voice.play(rejectClip(l.reason), { queue: true })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.lanes])

  return (
    <div className="flex h-full flex-col">
      <Header view={view} />
      <main className="flex flex-1 flex-col overflow-y-auto">
        <Body view={view} clearResult={clearResult} welcome={welcome} onStart={() => setStarted(true)} />
      </main>
      {view.simulation && <DevPanel view={view} />}
    </div>
  )
}

export default function App() {
  return (
    <LangProvider>
      <VoiceProvider>
        <Kiosk />
      </VoiceProvider>
    </LangProvider>
  )
}
